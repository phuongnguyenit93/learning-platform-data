# Private Clusters and Kubernetes API Access Control

Azure Kubernetes Service (AKS) enables running Kubernetes on Microsoft Azure without manually managing the entire control plane. However, a Kubernetes cluster does not serve only application end users: administrators, CI/CD pipelines, GitOps tools, and controllers also need to communicate with the **Kubernetes API server** to read or modify system state. If the API access path and authorization mechanisms are not carefully designed, a compromised identity can view sensitive data, deploy new workloads, alter network configurations, or take over the cluster.

An **AKS private cluster** is an option that reduces the Kubernetes API attack surface by using private connectivity to the control plane instead of exposing Kubernetes management over a standard public API endpoint. Yet **private does not mean authorized**: once a valid network path exists, callers must still authenticate and be authorized for each action.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter of the CLOUD_PROVIDERS_AZURE module. The content connects AKS with subscriptions, resource groups, Microsoft Entra ID, Azure RBAC, VNets, Private DNS, VPN/ExpressRoute, Azure Monitor, security, and costs when operating application architectures on Azure.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish the Kubernetes control plane, Kubernetes API server, worker nodes, API endpoint, and applications published via ingress.
2. Explain how an AKS private cluster restricts API access paths and the limitations of this model.
3. Design DNS and administrative connectivity from a VNet VM, peered network, VPN/ExpressRoute, or private CI/CD runner.
4. Distinguish three concerns: **network reachability**, **authentication**, and **authorization**.
5. Understand Microsoft Entra ID authentication, Azure RBAC for Kubernetes Authorization, and Kubernetes native RBAC.
6. Create a test cluster and inspect configurations via Azure CLI; retrieve kubeconfig and use kubelogin/kubectl in an authorized environment.
7. Design least-privilege namespace authorization, separating runtime identities from cluster permissions.
8. Troubleshoot DNS, TCP/TLS, 401, 403, role assignment, kubeconfig, and CI/CD failures.
9. Build a checklist for monitoring, break-glass access, configuration changes, recovery, and cost control.

Commands in this lesson are examples for an authorized lab environment, **not executed automatically**. For real deployments, verify SKUs, regions, features, and API server/networking options against current Azure documentation.

## 2. Control plane and Kubernetes API server

### 2.1. Kubernetes manages the cluster via its API

Kubernetes uses the API server as the entry point for management requests: creating Deployments, reading Pods, updating ConfigMaps, creating RoleBindings, viewing nodes, and many other operations.

~~~mermaid
flowchart LR
    U["Admin / kubectl"] --> A["Kubernetes API server"]
    C["CI/CD or GitOps"] --> A
    A --> E["Control plane: cluster state"]
    E --> N["Worker nodes / kubelet"]
    N --> P["Pods: applications"]
    X["Application users"] --> I["Ingress / Load Balancer"]
    I --> P
~~~

These traffic groups are **not the same**:

- **Kubernetes management:** kubectl, controllers, or pipelines sending requests to the Kubernetes API server.
- **Application:** users accessing websites/APIs via ingress, Services, or load balancers; they do not need Kubernetes API access.
- **Node and control plane:** kubelet, node components, and control components exchanging data per AKS architecture.

You can have an AKS private cluster whose applications remain publicly exposed through a protected ingress. Conversely, a cluster with a public API endpoint can run purely internal applications. **A private cluster does not mean all application Services or ingresses are private.**

### 2.2. Managed control plane does not mean skipping access control

AKS manages many control plane components, yet your organization must still:

- Define who can create and modify the cluster in the Azure management plane.
- Choose authentication models for users and workloads.
- Choose Kubernetes authorization policies by namespace and resource type.
- Configure VNets, DNS, egress, firewalls, and management paths.
- Manage Kubernetes versions, node pools, workloads, and secrets per shared responsibility.
- Enable logging/auditing and incident response procedures.

An Azure-managed control plane never bypasses validation of requests to the Kubernetes API.

## 3. Public cluster, private cluster, and API access variants

### 3.1. Public API endpoint

In an AKS model with a public API endpoint, machines with suitable network connectivity can reach the endpoint over the Internet, then must still pass authentication and authorization checks.

A public cluster can use **API server authorized IP ranges** or other protective measures to restrict source IP addresses where supported. However:

- Authorized IP ranges do not turn the endpoint into a private endpoint.
- Source IP allowlists must be maintained whenever admin egress/NAT IPs change.
- Leaked credentials or tokens remain dangerous if an attacker has an allowed network path.
- IP allowlists do not replace Entra ID or RBAC.

### 3.2. Private cluster

With an AKS private cluster, Kubernetes API access is designed over a **private network path**. Connectivity depends on the chosen API server/control plane networking type, DNS setup, and VNets or hybrid networks routed to the private endpoint/API address.

~~~mermaid
flowchart LR
    O["On-premises admin"] --> V["VPN / ExpressRoute"]
    J["Jump host / runner in VNet"] --> VNET["VNet or connected network"]
    V --> VNET
    VNET --> DNS["Private DNS resolution"]
    DNS --> API["Private AKS API endpoint"]
    API --> CP["Managed control plane"]
    CP --> NP["Node pool"]
    NP --> APP["Application Pods"]
    USER["App clients"] --> INGRESS["Separate App Ingress / LB"]
    INGRESS --> APP
~~~

**A private cluster protects the API entry path, not every other component automatically.** Someone with access to a VM or pod that can reach the API can still attempt authentication. Therefore you still need network segmentation, host/runner hardening, strong authentication, least privilege, and auditing.

### 3.3. Two concepts to distinguish in AKS

AKS documentation covers API server deployment models that have evolved over time, including private clusters built on private control plane connectivity and **API server VNet integration** in supported configurations.

Distinguish:

- **Private cluster:** the goal of accessing the Kubernetes API over a private network.
- **API server VNet integration:** a specific architecture for integrating the API server into a virtual network under specific product terms; can be combined with private access where supported.
- **API endpoint public/private mode:** an actual property of the cluster to inspect rather than inferring solely from a Portal feature name.
- **Private DNS zone:** the mechanism resolving the API hostname to a private IP within connected networks.

Deployment patterns may differ in Private DNS zone names, API server IPs, network resources, and whether mode switching after creation is supported. Do not force a single legacy pattern onto all new clusters; inspect the cluster's **apiServerAccessProfile, privateFqdn, and networking mode** properties.

## 4. Three mandatory layers: network, authentication, authorization

A successful kubectl request must pass three independent layers:

~~~mermaid
flowchart TD
    K["kubectl / API client"] --> N{"1. DNS + network to API OK?"}
    N -->|No| NE["Timeout / DNS failure"]
    N -->|Yes| A{"2. Authentication valid?"}
    A -->|No| AE["Unauthorized / login error"]
    A -->|Yes| R{"3. Authorized for verb/resource/scope?"}
    R -->|No| RE["Forbidden (403)"]
    R -->|Yes| OK["API accepts request"]
~~~

| Layer | Question | Verification method |
|---|---|---|
| Network reachability | Can the client resolve the FQDN and reach TCP 443 on the API? | DNS, routes, NSG/firewall, VPN/peering, TLS |
| Authentication | Does the API know who the caller is, and is the token valid? | Entra ID, kubelogin, token, service account, or supported mechanism |
| Authorization | Is the caller allowed to perform that verb on that resource/namespace? | Azure RBAC for Kubernetes Authorization or Kubernetes native RBAC |

For example: an engineer holding Azure Kubernetes Service RBAC Reader whose laptop lacks a VPN route to the private endpoint will see a timeout, **not a role error**. Conversely, a VNet VM connecting over TCP 443 successfully without permission to list pods will receive a Forbidden error.

Fix the exact layer that is failing—never grant cluster-admin to fix DNS or expose a public API to fix a 403 error.

## 5. Network and Private DNS design for private AKS

### 5.1. Reference components

Suppose a production AKS cluster runs in this network:

~~~text
Subscription: sub-platform-prod
Resource group: rg-aks-prod
Region: southeastasia

VNet: vnet-platform-prod         10.50.0.0/16
  snet-aks-nodes                 10.50.0.0/22
  snet-admin-tools               10.50.8.0/24
  snet-private-endpoints         as planned if needed

On-premises: 172.20.0.0/16
  ↔ VPN or ExpressRoute
  ↔ Hub/VNet with matching routes and DNS

AKS: aks-orders-private
  API access: private
  App ingress: designed separately, public or private
~~~

This is an illustrative CIDR layout. In real networks, verify overlaps, subnet delegations, node/pod IP demand, network plugin, load balancers, and hub-spoke planning.

**Private AKS API networking is not the same concept as Pod networking.** Azure CNI, CNI Overlay, and pod IP configs govern application and node traffic; private cluster primarily describes how management clients and the control plane communicate over the API.

### 5.2. Private FQDN and DNS

An AKS private cluster has a **private FQDN** for the Kubernetes API. Clients must resolve this name to a private IP or target network address matching the deployment model.

Inspect after cluster creation:

~~~bash
az aks show \
  --resource-group rg-aks-prod \
  --name aks-orders-private \
  --query "{fqdn:fqdn,privateFqdn:privateFqdn,api:apiServerAccessProfile}" \
  --output json
~~~

The Private DNS zone name may involve `azmk8s.io` with patterns depending on cluster type and Azure region. **Do not hardcode a single zone name** for every case. Read the actual FQDN and zone created or configured by AKS, then check VNet links/forwarding.

From an authorized client:

~~~bash
nslookup <PRIVATE_AKS_FQDN>
~~~

The result must match your private network design. If it returns an unexpected public IP, NXDOMAIN, or an unroutable address, kubectl will fail before reaching authentication.

### 5.3. Private DNS zones and VNet links

There are two common operational approaches:

- **AKS-managed private DNS:** AKS manages part of the DNS configuration per the chosen service mechanism.
- **Custom private DNS zone:** the organization manages the zone, network links, and corresponding permissions as supported by AKS.

With custom DNS, you must:

1. Plan the zone according to the active API server model.
2. Grant the AKS identity required permissions on the DNS zone/network per service documentation.
3. Create VNet links for authorized querying networks.
4. Configure DNS forwarders or Azure DNS Private Resolver when clients use corporate DNS.
5. Test resolution from each real network segment: nodes, jump hosts, runners, and on-premises.
6. Monitor zone/record changes and maintain a runbook.

**Never hastily edit or delete AKS-managed DNS records** to troubleshoot an error. Doing so can break management connectivity or disrupt cluster operations.

### 5.4. Accessing from on-premises

Having a VPN/ExpressRoute to a VNet does not automatically guarantee access to a private API. You need all of:

- Routes from on-premises networks to the private API IP/target.
- Properly designed return routes.
- DNS forwarders for the private FQDN via matching DNS infrastructure.
- Firewalls/NSGs permitting TCP 443 to the endpoint.
- Client TLS trust and valid identity.

If your enterprise uses custom DNS servers in a datacenter, configure conditional forwarding for the private zone via Azure-supported DNS mechanisms. Never send internal queries to a public DNS resolver expecting it to know your VNet's Private DNS zone.

### 5.5. Accessing via VNet peering and hub-spoke

When managing through a hub:

- Jump hosts or runners may sit in the hub VNet while AKS nodes sit in a spoke VNet.
- Routes, peering, and DNS links/forwarding must be configured on both sides.
- NSGs, Azure Firewall, or NVAs can block traffic even when two VNets are peered.
- If using UDRs or inspection, ensure the path to the API is not blackholed.
- Never assume peering alone grants API reachability; DNS and security policies still govern the outcome.

Test from **the exact environment running kubectl**, not just any random VM in the same subscription.

## 6. Secure ways to access the Kubernetes API

### 6.1. Admin VM or jump host in a private network

An easily controlled option is placing an admin VM inside a protected subnet:

~~~text
Engineer → Azure Bastion/VPN → Jump VM → Private AKS API
~~~

Minimum requirements:

1. Never expose SSH/RDP directly to the open Internet unnecessarily.
2. Keep the VM patched, running EDR/host firewall, using managed authentication.
3. Grant access only to authorized admin groups.
4. Never store long-lived kubeconfigs/tokens in unprotected shared directories.
5. Audit admin sessions and apply scoped Azure RBAC/Kubernetes RBAC.
6. Configure Private DNS and routes to the API.

Azure Bastion manages access to the VM; it is **not an automatic proxy for Kubernetes API requests**. That VM still needs network reachability to the private endpoint and valid Kubernetes permissions.

### 6.2. VPN/ExpressRoute from corporate devices

Engineers can run kubectl from corporate laptops if:

- The device connects via an organization-approved VPN or dedicated network.
- Private DNS resolves over that network path.
- Entra ID tokens and Kubernetes permissions are valid.
- Firewalls and routes permit API TCP 443.

This suits organizations with strong endpoint management. If the VPN drops, kubectl cannot reach the API even though Azure Portal and management-plane commands still work.

### 6.3. CI/CD runners in a private network

GitHub Actions or Azure DevOps pipelines using hosted runners are **not by default** inside your VNet. If deploying via kubectl/Helm directly to a private API, a public hosted runner will fail without a network path.

Typical suitable pattern:

~~~mermaid
flowchart LR
    G["GitHub / Azure DevOps"] --> R["Self-hosted runner / private agent"]
    R --> D["Private DNS + VNet routes"]
    D --> A["Private AKS Kubernetes API"]
    A --> W["Deployments / Services"]
    I["Entra ID / federated identity"] -.-> R
~~~

The runner needs:

- Placement in a subnet/VNet or connected network routed to the private API.
- Minimal outbound connectivity to the pipeline system and required services.
- Workload identity federation/OIDC or managed identity where supported instead of long-lived service principal secrets.
- Deployment permissions restricted solely to permitted namespaces.
- Patching, isolation between project groups/trust levels, and safeguards blocking unreviewed PRs from executing with production credentials.
- Audit trails recording commit, artifact, approval, kubectl actions, and rollout outcomes.

**Separate build from deploy:** building and pushing images to Azure Container Registry does not necessarily require access to the private Kubernetes API. Only the deploy step needs private connectivity to the cluster if using kubectl/Helm directly.

### 6.4. In-cluster GitOps agent

With GitOps, a controller running **inside the cluster** watches an approved repository and reconciles Kubernetes manifests. This reduces the need for external pipelines to open inbound connectivity to the Kubernetes API.

However, a GitOps controller is itself a workload with cluster-changing permissions:

- Use a dedicated identity and least-privilege namespace permissions.
- Protect Git sources, branches, commit signing, and approvals.
- Control egress to Git/registries.
- Never embed an admin kubeconfig in a repository.
- Monitor drift and unexpected apply/delete actions.

GitOps does not remove Kubernetes authorization requirements; it shifts deployment privileges to a service account/controller that must be governed.

### 6.5. AKS Run Command

AKS can run certain commands via **az aks command invoke** in supported configurations, using the Azure management plane and AKS execution mechanisms. This helps in operational scenarios where an operator lacks direct connectivity to a private API.

Read-only example:

~~~bash
az aks command invoke \
  --resource-group rg-aks-prod \
  --name aks-orders-private \
  --command "kubectl get namespaces"
~~~

**Warning:** this is not equivalent to an individual low-privilege Kubernetes RBAC path. Run Command capabilities depend on Azure permissions, features, cluster configs, and execution limits. Users permitted to run commands may hold broad impact over the cluster. Treat this permission as sensitive operational access, audit usage, and never use it to bypass routine network/least-privilege policies.

Do not treat Run Command as a permanent substitute for private runners or well-designed administrative connectivity.

## 7. Kubernetes API authentication with Microsoft Entra ID

### 7.1. What is authentication?

When a kubectl client calls the API, the API server must verify the caller. With **AKS managed Microsoft Entra ID integration**, users sign in with their Entra identity and clients obtain valid tokens via platform-supported flows.

Key components:

- **Entra tenant:** manages users, groups, and certain workload identities.
- **AKS cluster identity:** identity used by AKS to interact with Azure resources; distinct from a kubectl user's identity.
- **kubectl/kubeconfig:** client and endpoint/certificate/credential configuration executing requests.
- **kubelogin:** helper tool handling Entra ID login and token/credential acquisition for Kubernetes clients in supported scenarios.
- **Kubernetes authorization:** decides whether the authenticated user may perform the requested action.

### 7.2. Kubeconfig is not an all-access pass

A kubeconfig file typically contains:

- Cluster name and API server URL.
- Certificate/CA or TLS settings.
- Default context.
- Instructions on how to fetch or present credentials.

**Having a kubeconfig does not grant full access.** Without an assigned role, kubectl still receives Forbidden. Outside a private network, a kubeconfig with the exact endpoint still fails to connect.

Treat kubeconfigs and tokens as sensitive secrets: restrict file permissions, never commit to Git, and never paste into public tickets.

### 7.3. Entra ID integration

With AKS managed Entra ID integration, you can use Entra users or groups as administrative principals rather than distributing shared cluster-admin credentials. Benefits:

- Individual identities and centralized authentication.
- Can enforce MFA, Conditional Access, and PIM where applicable.
- Disable or update group memberships as staff roles change.
- Record sign-in and activity events in corresponding log sources.
- Separate read-only observers, namespace deployers, and platform operators.

However, enabling Entra authentication **does not by itself decide** read/write permissions inside Kubernetes; you must still choose an authorization system.

## 8. Two authorization options: Azure RBAC vs. Kubernetes native RBAC

This is the most commonly confused area of AKS administration.

### 8.1. Azure management-plane RBAC

Azure RBAC at the management plane governs who can create, read, update, or delete clusters, or invoke ARM actions like retrieving user credentials.

Example roles:

- **Azure Kubernetes Service Cluster User Role:** enables retrieving user kubeconfig/credentials per role permissions.
- **Azure Kubernetes Service Cluster Admin Role:** relates to retrieving admin credentials; sensitive and not a routine Kubernetes reader role.

These management-plane roles **do not automatically** grant permission to list/create/delete Pods in a namespace under Kubernetes authorization. Distinguish credential-retrieval roles from Kubernetes API authorization roles.

### 8.2. Azure RBAC for Kubernetes Authorization

AKS can use **Azure RBAC for Kubernetes Authorization**, meaning Azure role assignments grant permissions to call the Kubernetes API at supported scopes.

Typical Kubernetes data-plane roles:

| Role | Common purpose | Notes |
|---|---|---|
| Azure Kubernetes Service RBAC Reader | View supported Kubernetes resource types | Does not read secrets by default depending on role definition |
| Azure Kubernetes Service RBAC Writer | Create/edit supported resources within granted scope | Should not be granted cluster-wide to a pipeline deploying only one namespace |
| Azure Kubernetes Service RBAC Admin | Manage most Kubernetes resources within scope | High privilege; review exact data actions |
| Azure Kubernetes Service RBAC Cluster Admin | Cluster-wide Kubernetes administration | Only for a tightly restricted platform group, with approval |

Exact role names and data actions must be verified against current Azure documentation. A role named Writer does not guarantee every Kubernetes verb/resource is allowed. If a built-in role does not fit, design an appropriate scope/custom role as supported rather than granting Cluster Admin to clear a 403.

### 8.3. Kubernetes native RBAC

In the **Kubernetes RBAC** model, permissions are defined via:

- **Role:** list of resources/verbs in a single namespace.
- **RoleBinding:** binds a Role or ClusterRole to Users/Groups/ServiceAccounts in a namespace.
- **ClusterRole:** defines cluster-wide permissions or reusable templates across namespaces.
- **ClusterRoleBinding:** binds a ClusterRole to subjects cluster-wide.

When Entra ID authenticates users while the cluster uses Kubernetes native RBAC, Entra groups are mapped using the group identifier provided by AKS, and RoleBindings grant permissions. Verify group object IDs and group claim configurations carefully.

### 8.4. Do not mix the two models unintentionally

Choose one authorization model in your cluster design:

- If using **Azure RBAC for Kubernetes Authorization**, manage user/group access via Azure role assignments and scopes per supported config.
- If using **Kubernetes native RBAC**, manage permissions with Role/RoleBinding/ClusterRole/ClusterRoleBinding. Entra ID can still authenticate users.
- Service accounts and controllers have their own authorization bindings inside Kubernetes; never assume an Entra role assignment automatically handles every Pod permission.

Whichever model is chosen, test with real actions in the target namespace. Some `kubectl auth can-i` checks behave differently depending on the authorizer and configuration, so cross-check against real API calls or audit logs if discrepancies appear.

### 8.5. Permission matrix for an application

Suppose namespace `orders` has several groups:

| Principal | Recommended permissions | Should NOT have |
|---|---|---|
| App observers | Read pods/deployments/events in namespace `orders` | Read secrets, edit workloads, modify cluster |
| `orders` pipeline | Update required Deployments/Services/ConfigMaps in `orders` per policy | Create ClusterRoleBindings, modify other namespaces |
| Platform operator | Manage required cluster settings via PIM/approval | Shared un-audited accounts |
| App inside Pod | Only Kubernetes API permissions genuinely required; many apps need none | Automatic privileged token mounts or cluster-admin |
| Auditor | View appropriate configs and logs | Modify or delete production resources |

Never use the Entra **Global Administrator** group as a method for granting Kubernetes API access. Tenant, Azure subscription, and Kubernetes cluster permissions are distinct scopes.

## 9. Hands-on 1: creating an AKS private cluster in a lab

The example below illustrates the sequence of steps. It requires quota, Azure permissions, properly sized subnets, network policies, and cost budgeting. A private cluster may be unreachable from your laptop unless you have a VM or private runner inside the network.

### 9.1. Confirm subscription and create lab network

Bash example:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az group create \
  --name rg-aks-lab \
  --location southeastasia

az network vnet create \
  --resource-group rg-aks-lab \
  --name vnet-aks-lab \
  --location southeastasia \
  --address-prefixes 10.50.0.0/16 \
  --subnet-name snet-nodes \
  --subnet-prefixes 10.50.0.0/22
~~~

This is an illustrative network. Production environments must size node/pod IPs, service addresses, Kubernetes network plugin, outbound connectivity, UDRs, and additional subnets. Never use CIDRs overlapping hybrid networks.

Retrieve the subnet resource ID:

~~~bash
SUBNET_ID=$(az network vnet subnet show \
  --resource-group rg-aks-lab \
  --vnet-name vnet-aks-lab \
  --name snet-nodes \
  --query id --output tsv)

echo "$SUBNET_ID"
~~~

When running in practice, verify the ID belongs to the intended subscription/VNet and the identity holds required subnet permissions. Never assign subscription-wide Owner just to fix a subnet assignment error.

### 9.2. Create cluster using Entra ID and Azure RBAC authorization

Example:

~~~bash
az aks create \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --location southeastasia \
  --node-count 2 \
  --node-vm-size Standard_D2s_v5 \
  --network-plugin azure \
  --vnet-subnet-id "$SUBNET_ID" \
  --enable-managed-identity \
  --enable-private-cluster \
  --enable-aad \
  --enable-azure-rbac \
  --disable-local-accounts \
  --generate-ssh-keys
~~~

Key options:

- **--enable-private-cluster:** requests a private API server per the supported AKS deployment model.
- **--enable-aad:** enables Microsoft Entra ID integration for Kubernetes authentication per AKS/CLI version.
- **--enable-azure-rbac:** selects Azure RBAC for Kubernetes Authorization instead of native-only Kubernetes authorization.
- **--disable-local-accounts:** disables local admin/user credential mechanisms; use only when Entra/RBAC and break-glass procedures are ready.
- **--enable-managed-identity:** uses managed identity for the cluster.
- **--vnet-subnet-id:** places nodes in the prepared subnet.
- **--network-plugin azure:** example network plugin; choose network mode/overlay per actual design.

Do not treat every flag in this example as the optimal default for all clusters. API server VNet integration, Private DNS zones, outbound type, Azure CNI Overlay, node OS, SKUs, and network policies are separate architectural decisions. Check version-specific feature support before running.

**Important:** disabling local accounts can make admin kubeconfig access unavailable. Test Entra login and role assignments before enforcing restrictive policies in production.

### 9.3. Verify private properties

~~~bash
az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query "{name:name,private:apiServerAccessProfile.enablePrivateCluster,privateFqdn:privateFqdn,api:apiServerAccessProfile,identity:identity.type}" \
  --output json
~~~

The goal is verifying that the cluster reports private mode and a private FQDN matching its model. Certain fields may be null or represented differently depending on API integration mode/AKS version. If output differs from expectations, inspect the actual deployment model before assuming the cluster is broken.

### 9.4. Prepare the machine running kubectl

You need a VM/runner on a network permitted to reach the private API, equipped with:

- Azure CLI signed in via Entra ID.
- `kubectl` and `kubelogin` compatible with the cluster/client.
- DNS resolving the private FQDN accurately.
- TCP 443 allowed to the API endpoint.
- User or identity authorized to retrieve kubeconfig and perform Kubernetes actions.

Do not create a public IP for the Kubernetes API just for lab convenience. You can use an admin VM inside the VNet or a peered/VPN network, provided management access to the VM and software patching are handled properly.

## 10. Hands-on 2: retrieving kubeconfig and authenticating

### 10.1. Connect from a private-network environment

On the prepared VM/runner, verify the FQDN:

~~~bash
PRIVATE_FQDN=$(az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query privateFqdn --output tsv)

echo "$PRIVATE_FQDN"
nslookup "$PRIVATE_FQDN"
~~~

If the hostname does not resolve to the expected private API address, fix DNS first. There is no point troubleshooting roles until network connectivity works.

For TCP 443, on Linux you can run:

~~~bash
nc -vz "$PRIVATE_FQDN" 443
~~~

On Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName "<PRIVATE_AKS_FQDN>" -Port 443
~~~

A TCP check only proves network reachability; it does not prove authentication or authorization passes.

### 10.2. Fetch user kubeconfig

~~~bash
az aks get-credentials \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --overwrite-existing
~~~

This command retrieves credential config via the Azure management plane per caller permissions. It **does not guarantee the client currently has connectivity to the private Kubernetes API**. Thus `get-credentials` can succeed while `kubectl` times out outside the VNet.

If the cluster uses Entra ID and kubeconfig includes an exec plugin, configure `kubelogin` per your client version:

~~~bash
kubelogin convert-kubeconfig -l azurecli
~~~

This configures `kubelogin` to use Azure CLI login in supported scenarios; CI/CD environments may use workload identity methods instead. Never use interactive human logins as long-lived credentials for production automation.

Verify context:

~~~bash
kubectl config current-context
kubectl config view --minify
~~~

`config view` can display sensitive details depending on kubeconfig contents; never print full outputs to CI logs or tickets. Avoid `--raw` when sharing.

### 10.3. Test permissions with kubectl

~~~bash
kubectl get namespaces
kubectl get pods -n orders
kubectl auth can-i list pods -n orders
kubectl auth can-i create deployments -n orders
~~~

These commands succeed only if the namespace exists, networking works, and the identity has sufficient permissions. For a namespace-scoped reader, listing all namespaces may return Forbidden while listing pods inside the granted namespace succeeds; that is **correct authorization behavior**, not a cluster bug.

Never fix this by granting `cluster-admin` just to make all commands succeed. Check which actions actually belong to the user's job.

### 10.4. Avoid routine use of admin credentials

Some clusters permit fetching admin credentials via the admin option depending on configuration. If local accounts are disabled or policy forbids it, this will fail.

Even when available, admin credentials carry extreme privileges and obscure individual identities in audit logs. Use Entra-authenticated user credentials, scoped role assignments, and just-in-time elevation procedures.

## 11. Hands-on 3: granting namespace-scoped Azure RBAC

Suppose the organization has an Entra ID group permitted **read-only** access to workloads in the `orders` namespace.

### 11.1. Find the cluster resource ID

~~~bash
AKS_ID=$(az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query id --output tsv)

echo "$AKS_ID"
~~~

Obtain the approved Entra group's object ID from identity management. Never guess by display name, as duplicate names or unprivileged groups may exist in the tenant.

### 11.2. Permission to retrieve user kubeconfig

An operations group may need the kubeconfig retrieval role if no existing management-plane role already grants that action:

~~~bash
az role assignment create \
  --assignee-object-id "<ENTRA_GROUP_OBJECT_ID>" \
  --assignee-principal-type Group \
  --role "Azure Kubernetes Service Cluster User Role" \
  --scope "$AKS_ID"
~~~

This role relates to fetching user credentials; **do not confuse it with permission to list Pods in the Kubernetes API**.

### 11.3. Permission to read the orders namespace

With Azure RBAC for Kubernetes Authorization enabled, data-plane roles can be assigned at a supported namespace scope:

~~~bash
az role assignment create \
  --assignee-object-id "<ENTRA_GROUP_OBJECT_ID>" \
  --assignee-principal-type Group \
  --role "Azure Kubernetes Service RBAC Reader" \
  --scope "$AKS_ID/namespaces/orders"
~~~

The `orders` namespace must be created by an authorized user before readers test access. Scope syntax and actual role permissions must be verified against the cluster's Azure RBAC model. Never assign a cluster-wide role simply because a namespace-scoped command had a typo.

You can list role assignments (output depends on caller permissions):

~~~bash
az role assignment list \
  --scope "$AKS_ID" \
  --include-inherited \
  --output table
~~~

To inspect roles at namespace scope, query the namespace scope when needed; a cluster-scope query does not automatically show all child-scope assignments.

### 11.4. Verify least privilege

Sign in as a member of the permitted group from a machine with private network access:

~~~bash
kubectl get pods -n orders
kubectl auth can-i get deployments -n orders
kubectl auth can-i delete deployments -n orders
kubectl auth can-i get pods -n kube-system
~~~

Expected outcome: the reader can inspect permitted resources in `orders`, but cannot delete Deployments or view out-of-scope namespaces. If results are unexpected, check role assignments, token refresh, Entra group membership, and authorizer configuration. Role changes can take time to propagate; do not assume instant effect.

**Security note:** read access to certain Kubernetes resources can indirectly expose configuration, image names, and workload parameters. Never grant secret-reading or Pod `exec` permissions unnecessarily.

## 12. Kubernetes native RBAC example for comparison

If the cluster uses **Kubernetes RBAC authorization**, do not use the Azure RBAC examples above in place of the RoleBindings below. Choose one mechanism deliberately.

### 12.1. Read-only Namespace Role

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-observer
  namespace: orders
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
~~~

This Role grants no access to read secrets, modify workloads, or administer the cluster.

### 12.2. Binding the Role to an Entra group

With Entra authentication paired with Kubernetes native RBAC, after verifying the cluster's group identity format:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-observers
  namespace: orders
subjects:
  - kind: Group
    name: "<ENTRA_GROUP_OBJECT_ID>"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: orders-observer
  apiGroup: rbac.authorization.k8s.io
~~~

If the cluster emits group claims in a different format, configure the subject using the exact real identifier; never assume a group display name works in place of its object ID.

The RoleBinding's effect is confined to the `orders` namespace. A ClusterRoleBinding with elevated permissions grants access across the entire cluster and must be governed as a privileged change.

### 12.3. ServiceAccount permissions inside a Pod

A typical application serving HTTP requests and querying a database **does not need to call the Kubernetes API**. When unneeded, consider disabling automatic mounting of the service account token:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-example
  namespace: orders
spec:
  automountServiceAccountToken: false
  containers:
    - name: app
      image: "<APPROVED_REGISTRY>/orders-api:<VERSION>"
~~~

This manifest is a conceptual Pod example; running it in practice requires a valid image, resource requests/limits, security context, and policy-compliant fields. Do not equate a Kubernetes ServiceAccount token with **Azure Workload Identity**: when a Pod needs Azure Key Vault or Storage, use Microsoft Entra Workload ID as configured separately, and remember Azure permissions do not automatically grant Kubernetes API permissions.

## 13. CI/CD and GitOps: principle of least privilege

### 13.1. Three distinct identities

In a container deployment pipeline:

1. **Build identity:** pulls source, builds images, pushes to Azure Container Registry.
2. **Deploy identity:** updates Kubernetes manifests in authorized namespaces.
3. **Runtime identity:** Pod accessing Key Vault, Storage, Event Hubs, or business services.

Separate these identities to shrink blast radius. A runtime Pod that only reads secrets from Key Vault has no reason to be allowed to create ClusterRoleBindings.

### 13.2. Example secure deployment pipeline

~~~text
Pull request / code review
          |
          v
CI build + test + image scan
          |
          v
Approved ACR image digest
          |
          v
CD approval
          |
          v
Private runner with VNet/DNS to AKS API
          |
          v
Entra auth + namespace-scoped RBAC
          |
          v
kubectl/Helm deploy into orders
          |
          v
Rollout status + app health + audit log
~~~

Critical conditions:

- Never grant production deploy permissions to pipelines executing unreviewed PR code.
- Use OIDC/workload identity federation or managed identity where supported instead of static service principal secrets.
- Build artifacts once, recording commit SHA and image digest.
- Store short-lived kubeconfigs in controlled isolated workspaces; never commit or print tokens to logs.
- Never reuse the same `cluster-admin` permission across all environments.
- Separate deployment approvals from merge permissions when strict controls are required.
- Monitor role assignments, ClusterRoleBindings, and namespace changes.

### 13.3. Risks of Helm charts and manifests

A chart may include cluster-scoped ClusterRoles, ClusterRoleBindings, CRDs, or webhooks. If a pipeline only holds namespace permissions, these operations may rightly be rejected **by policy**.

Do not open cluster-wide permissions just because `helm install` asks for broad privileges. Instead:

- Have the platform team install shared CRDs/controllers via a separate controlled process.
- Let application teams deploy only namespace-scoped workloads.
- Use reviewed charts to avoid creating out-of-scope resources.
- Inspect `helm template` or rendered manifests before applying, especially RBAC and admission webhooks.

## 14. Monitoring, auditing, and change management

### 14.1. Monitor both planes

| Plane | Signal source | Purpose |
|---|---|---|
| Azure management plane | Azure Activity Log, AKS resource changes, Azure role assignments | Who created/edited clusters, changed networks, identities, and Azure RBAC |
| Kubernetes API/data plane | Kubernetes audit logs via AKS diagnostic settings | Who invoked which verb on which resource/namespace and whether it succeeded |
| Identity | Entra sign-in/audit logs | Signing-in identities and group/permission changes |
| Cluster operations | Azure Monitor, Container insights, node/pod health | Whether the API/cluster and workloads are healthy |
| Network | DNS logs where available, firewalls, VPN/ER, Network Watcher | Name resolution faults or broken private API connectivity |
| CI/CD | Runner/pipeline logs, approvals, commits, image digests | Which artifact entered the cluster and by whom |
| Security posture | Defender for Cloud and policy evaluation when enabled | Misconfigurations, overly broad permissions, risky images |

**Azure Activity Log does not replace Kubernetes audit logs.** It primarily records management-plane operations and does not automatically capture every `kubectl get/apply/delete` inside the cluster. To investigate Kubernetes API activity, enable and collect the appropriate audit logs before incidents happen, subject to AKS logging capabilities and retention.

### 14.2. Diagnostic settings and logging costs

At deployment time, review AKS-supported log categories such as `kube-audit`, `kube-audit-admin`, or other control-plane log groups. Pick categories matching security needs, granularity, and ingestion/retention costs.

- `kube-audit` can generate high event volume and significant cost.
- Filtered audit groups focus on specific operation subsets; verify coverage/limitations before relying on them for compliance audits.
- Govern Log Analytics workspace permissions and retention per organizational policy.
- When exporting logs to Storage, Event Hubs, or Log Analytics, verify data actually arrives.
- Never expose tokens or secrets from audit/log outputs in public locations.

You can use Azure Monitor Alerts and Microsoft Sentinel if deployed to detect privilege changes, sensitive operations, or anomalous API behavior.

### 14.3. Events worth alerting on

1. Adding Kubernetes Cluster Admin role assignments or sensitive Azure permissions.
2. Creating ClusterRoleBindings granting `cluster-admin` in Kubernetes native RBAC.
3. Disabling or altering cluster authentication/security mechanisms.
4. Modifying Private DNS zones, VNet links, API endpoint modes, or firewalls.
5. Editing `kube-system` or critical controllers outside approved change windows.
6. Kubernetes API calls from unapproved identities or anomalous access patterns.
7. CI/CD runners losing API connectivity, failing repeatedly, or suddenly using a different identity.
8. Spikes in API errors/timeouts, network/DNS errors, or `NotReady` nodes.

Define realistic thresholds and log sources; never treat an alert rule alone as proof that every event is being captured.

## 15. Common issues and troubleshooting

### 15.1. Quick diagnostic table

| Symptom | Likely failing layer | Where to check |
|---|---|---|
| `kubectl`: lookup host failed / NXDOMAIN | DNS | Private FQDN, zone/link, resolver, and conditional forwarding |
| `kubectl`: i/o timeout | Network | VNet/peering, VPN, UDR, firewall, TCP 443, return route |
| `x509: certificate signed by unknown authority` | TLS/client | Kubeconfig CA data, FQDN, proxy/TLS inspection, system clock |
| HTTP 401 Unauthorized | Authentication | Entra login, kubelogin, token expiry, tenant, kubeconfig |
| HTTP 403 Forbidden | Authorization | Azure RBAC/Kubernetes RBAC, scope, groups, verb/resource |
| `az aks get-credentials` succeeds yet `kubectl` fails | Private endpoint or data-plane permissions | Check DNS/TCP then token/role, not just ARM rights |
| Cannot retrieve kubeconfig | Azure management-plane permission | Cluster User Role, scope, tenant/subscription |
| Admin credential retrieval denied | Local accounts disabled or lacking permission | Check policy and break-glass procedure |
| Hosted CI runner cannot deploy | Runner lacks private route | Use private agent/VNet integration per supported model |
| New Azure role assignment still returns 403 | Propagation delay/token/groups/scope | Refresh login, verify identity and namespace scope |
| User can view pods but not namespaces | Valid namespace-scoped permissions | Do not widen permissions unless business requires it |
| `kubectl` works from jump host, fails on-premises | Hybrid DNS/route/firewall | Check source network path and private DNS forwarding |
| AKS creation fails with custom DNS | Identity lacks zone rights or invalid zone config | DNS zone permissions, VNet link, feature prerequisites |
| API works yet nodes are NotReady | Other network/egress/runtime fault | Check node pools, outbound dependencies, CNI, and logs |

### 15.2. Sequential troubleshooting workflow

**Step 1 — Verify cluster and subscription:**

~~~bash
az account show --output table

az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query "{state:provisioningState,private:apiServerAccessProfile.enablePrivateCluster,privateFqdn:privateFqdn}" \
  --output json
~~~

**Step 2 — Verify DNS and TCP from the actual client:**

~~~bash
nslookup <PRIVATE_AKS_FQDN>
nc -vz <PRIVATE_AKS_FQDN> 443
~~~

**Step 3 — Inspect kubeconfig, identity, and token:**

~~~bash
kubectl config current-context
az account show --query "{tenant:tenantId,subscription:id,user:user.name}" -o json
kubelogin --version
~~~

**Step 4 — Separate 401 from 403:**

- **401:** check sign-in, token, tenant, and clock skew.
- **403:** check role, namespace, group membership, and authorizer type.
- **Timeout/DNS:** never edit roles before network connectivity works.
- **TLS:** check FQDN, certificates, and proxies; never disable TLS verification as a workaround.

**Step 5 — Cross-check logs and recent changes:**

Check Azure Activity Log, Kubernetes audit logs, role assignments, DNS changes, and pipeline logs. Record UTC timestamps, caller, source IP if available, resource ID, and namespace.

### 15.3. Never "quick-fix" by opening the API publicly

Enabling a public endpoint just to run kubectl from a laptop is a risky change that can violate network segmentation or compliance rules. Diagnose why private routing/DNS failed and use approved administrative channels.

Similarly, granting Azure Kubernetes Service RBAC Cluster Admin before understanding a Forbidden error weakens access governance. Elevate privileges only through approved emergency procedures with time limits and auditing.

## 16. Break-glass and recovering management access

A private cluster with Entra ID and disabled local accounts blocks non-centralized logins. Yet you must answer: **if DNS, VPN, or Entra role config breaks, who recovers the system and how?**

A proper break-glass plan specifies:

1. Who is authorized to trigger it and through which approval channel?
2. Is there an independent network path or standby management VM?
3. Which Azure identity can repair networking/DNS and IAM, and how is it protected by PIM/auditing?
4. Can the Private DNS Zone and VNet links be restored from Infrastructure as Code?
5. With local accounts disabled, what **product-supported** recovery path exists without violating policy?
6. Can Run Command be used in approved emergencies, and who is authorized to invoke it?
7. Where are backups/restores for Kubernetes configs, GitOps state, and app data?
8. Are periodic recovery drills conducted with documented results and action items?

**Never promise that an admin kubeconfig will always work during an Entra/RBAC outage**, especially when local accounts are disabled. Likewise, never delete or alter a cluster's DNS zone mid-incident without understanding AKS-managed resources.

### 16.1. Change control for networking and identity

Changes such as switching DNS, altering outbound type, editing VNet peering, changing API server mode, or migrating identities can sever cluster administration. For production:

- Prepare a runbook and backout plan.
- Test changes in staging or an equivalent lab cluster.
- Use IaC to preserve a known-good configuration.
- Verify both Azure ARM and Kubernetes API permissions of the operator.
- Observe from at least two connectivity paths post-change where possible.
- Record approvals, timestamps, and verification results.

## 17. Cost and operations of a private cluster

Using a private Kubernetes API does not make the system free or automatically satisfy availability goals.

Items to budget:

- AKS control plane tier/pricing model and node pools.
- Node VMs, managed disks, load balancers, and data transfer.
- VNets, Private DNS zones, Private DNS Resolvers, or DNS forwarders if used.
- Azure Bastion, VPN Gateway, ExpressRoute, Firewalls/NAT if required.
- Private runners/agents and compute capacity for pipelines.
- Azure Monitor, Container insights, Log Analytics, and audit log retention.
- Microsoft Defender for Cloud and additional security plans.
- Operational effort for identity management, RBAC reviews, DNS updates, and DR drills.

**A private API reduces one exposure surface**; it does not automatically provide multi-region high availability. Design workload replicas, node pools, zones, backups, and DR per application targets.

Operationally, a private API narrows network exposure while increasing DNS and hybrid connectivity complexity. Weigh the security benefit against your operations team's readiness and management capability.

## 18. Real-world scenario: AKS running a production orders service

Suppose an enterprise runs an AKS cluster `aks-orders-private` serving an orders API, receiving customer traffic via a protected public ingress while wanting **only authorized operations staff and pipelines** to manage the Kubernetes API.

### 18.1. Architecture choices

- AKS API in private mode under a supported deployment model.
- Node pools running in planned subnets.
- Private API FQDN resolved via Private DNS and required links/forwarders.
- Engineers connect via VPN or Azure Bastion to a jump host.
- CI/CD deploys via self-hosted runners in the VNet; CI source control may live elsewhere.
- Entra ID authenticates users; Azure RBAC for Kubernetes Authorization grants namespace-scoped permissions.
- Platform team holds elevated privileges via PIM; the orders team has permissions only in the `orders` namespace.
- Runtime ServiceAccounts hold no Kubernetes API permissions if the app doesn't need them.
- ACR stores images; Container insights/Defender for Cloud/audit logs provide monitoring.
- Databases/Storage are protected by Private Endpoints and separate runtime identities.

### 18.2. User matrix

| Principal | API access path | Kubernetes permissions | Controls |
|---|---|---|---|
| Platform engineer | VPN → private VM or direct private route | Scoped cluster ops permissions, PIM for elevation | MFA, auditing, approval |
| Orders developer | VPN/VM when granted | Reader in `orders` | No secrets access, no cluster-wide actions |
| Orders CI/CD | Private runner | Deploy in `orders` per policy | Federated/managed identity, artifact approval |
| Security analyst | Controlled management path | Read access for investigation | Audited, no standing admin |
| Orders app | Inside Pods | No K8s API calls unless truly needed | Dedicated ServiceAccount, minimal token mount |

### 18.3. Acceptance test scenarios

1. A laptop without VPN cannot reach the private API directly.
2. A laptop/runner on VPN or inside the VNet resolves the private FQDN accurately.
3. An Entra user without a role can fetch credentials if permitted by policy, but is denied unauthorized Kubernetes actions.
4. The Reader group can view Pods in `orders` but cannot edit Deployments.
5. CI/CD can update Deployments in `orders` but cannot create ClusterRoleBindings or delete namespaces.
6. GitOps/service accounts hold only the permissions needed by their controllers.
7. Kubernetes audit logs record key actions per enabled settings.
8. Private DNS failures are detected and covered by a recovery runbook.
9. Container images deploy by approved digest with rollback capability.
10. Applications still serve via ingress as required even though the management Kubernetes API is private.

Success is not merely `kubectl get pods` returning output; more importantly, **the right people perform the right actions in the right scope, over the right network, with an audit trail**.

## 19. Production deployment checklist

### Networking and DNS

- [ ] Decided private vs. public cluster and documented the rationale.
- [ ] Diagrammed the private API path, subnets, routes, and DNS.
- [ ] Designated management clients have a private route to the Kubernetes API.
- [ ] VNet peering, VPN/ExpressRoute, and firewalls/NSGs allow TCP 443.
- [ ] Private FQDN resolves accurately from jump hosts, runners, and on-premises.
- [ ] Custom DNS zones, VNet links, and DNS forwarding have clear owners.
- [ ] API is never exposed publicly just to work around a network misconfiguration.

### Identity and authorization

- [ ] Entra ID authentication integrated and tested with real user accounts.
- [ ] Chosen Azure RBAC or Kubernetes native RBAC deliberately.
- [ ] Kubeconfig retrieval permissions separated from Kubernetes API action permissions.
- [ ] Namespace roles/group mappings follow least privilege.
- [ ] Deployment pipelines do not run with standing `cluster-admin`.
- [ ] Workload identities and service accounts hold zero unnecessary permissions.
- [ ] Local accounts and break-glass access are governed by tested policies.
- [ ] Alerts/audits exist for role assignment and ClusterRoleBinding changes.

### CI/CD and operations

- [ ] Private runners / GitOps controllers are hardened and patched.
- [ ] Images/digests, approvals, and rollouts are traceable.
- [ ] Kubeconfigs/tokens are never stored in repositories or printed in pipeline logs.
- [ ] Kubernetes audit and AKS diagnostic logs are collected with proper retention.
- [ ] Dashboards exist for API errors, node health, DNS, and connectivity.
- [ ] Runbooks exist for investigating 401/403/DNS/timeouts.
- [ ] Management connectivity loss and recovery have been rehearsed.
- [ ] Costs for nodes, networking, resolvers, runners, and log ingestion are budgeted.

## 20. Self-check questions

1. **What surface does a private AKS cluster primarily protect?** The Kubernetes API/control plane access path from networks outside private boundaries, under supported deployment models.
2. **Does a private cluster automatically make application ingress private?** No. Application ingress and Services have their own separate network design.
3. **Does having a kubeconfig mean having cluster-admin permissions?** No. Kubeconfig specifies the endpoint and authentication method; authorization is evaluated separately.
4. **Why can `get-credentials` succeed while `kubectl` times out?** Fetching kubeconfig uses the Azure management plane; the client running `kubectl` may lack DNS or routing to the private API.
5. **What should DNS return?** The private AKS API hostname must resolve to the private target matching the deployed architecture.
6. **Does a successful TCP 443 connection mean a user can list Pods?** No. Authentication and authorization still apply.
7. **How do 401 and 403 differ?** 401 relates to authentication/credentials; 403 means the identity was authenticated but lacks authorization.
8. **Does Azure Kubernetes Service Cluster User Role grant permission to edit Deployments?** Not by default. It relates to fetching user kubeconfig via the management plane.
9. **Are Azure Kubernetes Service RBAC Reader and Cluster User Role the same?** No. Reader is a Kubernetes API authorization role in the Azure RBAC model; Cluster User Role retrieves credentials.
10. **How do Kubernetes RoleBinding and ClusterRoleBinding differ?** RoleBinding is scoped to a namespace; ClusterRoleBinding applies cluster-wide.
11. **Why avoid granting cluster-admin to CI/CD?** It enlarges blast radius if a pipeline or token is compromised; namespace-scoped permissions are usually sufficient.
12. **Can a hosted CI runner always reach a private API?** No. It requires an appropriate private network path or private agent.
13. **Does Azure Activity Log record every kubectl command?** No. You need Kubernetes audit logs for that.
14. **Does Pod Workload Identity automatically grant Kubernetes API permissions?** No. Azure permissions and Kubernetes permissions are two distinct mechanisms.
15. **Should you enable a public API to fix a 403 error?** No. A 403 is an authorization issue, not a reachability issue.
16. **Is Run Command a low-privilege replacement for kubectl?** No. It relies on sensitive Azure permissions and requires separate governance.
17. **Can someone view Pods without being able to list namespaces?** Yes. That can be a valid namespace-scoped RBAC design.
18. **Does a private cluster replace backups or NetworkPolicy?** No. It only protects part of the API exposure surface.
19. **What happens if the private DNS zone is lost?** Admin machines/runners cannot resolve the API, blocking operations and deployments.
20. **What defines a successful private AKS deployment?** Private networking works, authentication and least privilege are right, applications stay healthy, monitoring is active, and recovery plans are tested.

## 21. References

- [Azure Kubernetes Service documentation](https://learn.microsoft.com/azure/aks/) — AKS architecture, networking, identity, and operations.
- [Create an AKS private cluster](https://learn.microsoft.com/azure/aks/private-clusters) — prerequisites, private endpoints, DNS, and private cluster models.
- [API Server VNet Integration](https://learn.microsoft.com/azure/aks/api-server-vnet-integration) — API server VNet integration model.
- [AKS networking concepts](https://learn.microsoft.com/azure/aks/concepts-network) — CNI, node/pod networking, and outbound connectivity.
- [AKS authentication with Microsoft Entra ID](https://learn.microsoft.com/azure/aks/enable-authentication-microsoft-entra-id) — identity authentication.
- [Azure RBAC for Kubernetes Authorization](https://learn.microsoft.com/azure/aks/manage-azure-rbac) — managing Kubernetes API permissions via Azure RBAC.
- [Kubernetes RBAC documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — Role, RoleBinding, ClusterRole, and ClusterRoleBinding.
- [kubelogin documentation](https://learn.microsoft.com/azure/aks/kubelogin-authentication) — credential plugin for Entra ID-integrated AKS.
- [AKS Run Command](https://learn.microsoft.com/azure/aks/access-private-cluster) — private cluster access options per supported features.
- [AKS monitoring](https://learn.microsoft.com/azure/aks/monitor-aks) — AKS monitoring and logging.
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview) — private DNS zones and private network links.
- [Azure Policy for AKS](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes) — workload configuration policies and governance.

**Conclusion:** an AKS private cluster restricts Kubernetes API access over private networking, yet it does not replace authentication, authorization, or workload security. A secure architecture needs all three layers—**DNS/network → Entra authentication → Azure RBAC or Kubernetes native RBAC**—with private CI/CD runners, least-privilege namespace permissions, audit logs, and rehearsed break-glass recovery. In real deployments, always verify the API server networking mode, Private DNS setup, and feature support on your exact AKS version and region rather than guessing from config names.
