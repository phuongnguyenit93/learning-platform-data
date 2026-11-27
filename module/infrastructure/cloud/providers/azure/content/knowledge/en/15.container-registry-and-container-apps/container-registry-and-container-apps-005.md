# Multi-Region Image Distribution and Restricting Registry Access

When a system deploys containers across multiple Azure regions, each region needs the exact **container image** to start or update the application. If the registry resides in only one region, pulling images over long distances increases latency and creates a dependency on that region. Conversely, if the registry has overly broad permissions or uncontrolled public network access, an untrusted identity or network could read internal images, push malicious code, or alter tags used in production.

**Azure Container Registry (ACR)** is a managed service for storing container images and OCI-compliant artifacts. With **geo-replication** on a supported SKU, a single registry can maintain replicas across multiple regions while still using **one registry name and one login server**. Alongside image distribution, you must design **Microsoft Entra ID/managed identities, pull/push permissions, private networking, DNS, logging, and digest-based release workflows** to secure the software supply chain.

This lesson belongs to the **Container Registry and Container Apps** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module covers Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data, while deploying, monitoring, securing, and controlling application costs. This lesson combines **container delivery**, **multi-region networking**, **registry access permissions**, and **failover operations**.

After studying this lesson, you will be able to:

- Explain repositories, tags, digests, manifests, and ACR's role in CI/CD.
- Design ACR **Premium geo-replication** to serve multi-region workloads.
- Distinguish image replication from application deployment, data replication, and disaster recovery.
- Choose how to grant pull/push permissions following the **least privilege** principle, including RBAC and supported repository-level models.
- Restrict network paths using **public firewall rules**, **Private Endpoints**, and Private DNS.
- Deploy images to **Azure Container Apps** or AKS with managed identities where appropriate.
- Verify replicas, test pulling images from each region, and diagnose 401/403/DNS/timeout errors.
- Establish runbooks for releasing, recovering, rotating credentials, and controlling costs.

## 1. What Components Does ACR Store?

A container image is packaged into data layers and metadata describing how the container starts. In ACR, the primary components are:

| Concept | Meaning | Example |
|---|---|---|
| **Registry** | Managed store with its own login server | acmeprod.azurecr.io |
| **Repository** | Collection of images sharing a logical name | orders/api |
| **Tag** | Human-readable label pointing to a manifest | 1.8.4, release-20261120 |
| **Digest** | Content-hash identifier of a manifest | sha256:... |
| **Manifest** | Describes layers, config, and sometimes a multi-arch index | OCI image manifest |
| **Artifact** | Standards-compliant object supported by the registry | Container image, OCI artifact per features |

An image referenced by tag:

~~~text
acmeprod.azurecr.io/orders/api:1.8.4
~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~ ~~~~~
     registry       repository  tag
~~~

Or referenced by digest:

~~~text
acmeprod.azurecr.io/orders/api@sha256:<MANIFEST_DIGEST>
~~~

The names above are illustrative. **Tags can change** if the registry allows overwrites, whereas a **digest** identifies a specific manifest. For production rollouts, specifying the digest ensures regions deploy **the exact same artifact** rather than relying on a tag that might move between pulls.

### Why Avoid Using :latest as a Release Identifier?

Suppose pipeline A pushes **orders/api:latest** at 10:00, and pipeline B pushes the same tag at 10:03. A container in region A pulling at 10:01 and region B pulling at 10:04 could run two different versions. With asynchronous geo-replication, behavior also depends on when manifests/layers replicate to each replica.

Use **immutable release tags** (e.g., version or commit SHA), verify digests, and pin digests when high reproducibility is required. If mechanisms exist to lock write operations on tags/repositories, enable them as well to reduce accidental overwrites.

## 2. Why Is Multi-Region Image Distribution Needed?

A SaaS system runs APIs in Southeast Asia and East Asia. Normally users are routed to a nearby or healthy region. Each region can scale out containers when traffic rises:

~~~text
                      CI/CD pipeline
                            |
                      Build + Scan
                            |
                     Push 1 image
                            |
                 Azure Container Registry
                 single login server name
                    /             \
             Replica A         Replica B
           Southeast Asia       East Asia
                 |                 |
             Image pull         Image pull
                 |                 |
        Container Apps/AKS    Container Apps/AKS
            Region A             Region B
~~~

If images live in only one region, workload B may depend on network connectivity back to the registry's home region to pull when creating new pods/replicas. If the primary region or network link fails, **scale-out, restarts, node replacements, or rollouts** can struggle.

**Geo-replication** brings images closer to workloads and reduces dependence on a single storage location. However, it does not change application code, does not automatically grant registry permissions, and **does not replicate database data**. A region-resilient architecture must prepare compute, ingress, databases, secrets, networking, and all other dependencies.

### Image Distribution Differs from Application Failover

| Component | Who Is Responsible? |
|---|---|
| Image and manifest present across regions | ACR geo-replication |
| Running containers in A/B | Container Apps, AKS, or compute platform |
| Routing user traffic A → B | Azure Front Door, Traffic Manager, or appropriate ingress solution |
| Application data recovery | Database/storage replication, backups, and DR runbooks |
| Workload pull permissions | Managed identity/RBAC, tokens, or supported auth mechanisms |
| Workload network path to ACR | VNet, routing, DNS, Private Endpoint/firewall |

A replicated image **does not guarantee** the application in region B can serve business traffic if database B is not ready.

## 3. Choosing the Registry SKU and Replication Architecture

ACR offers tiers such as **Basic, Standard, and Premium**, differing in capacity, limits, and features. **Geo-replication is an ACR Premium feature** under the supported service model. Do not expect a Basic or Standard registry to replicate automatically across regions just because workloads span multiple clusters.

| Criterion | Basic/Standard | Premium |
|---|---|---|
| Private registry for storing OCI/container images | Yes | Yes |
| Pull/push using supported identities | Yes | Yes |
| Multi-region geo-replication | No | Yes |
| Private Link/Private Endpoint for ACR | No on standard lower tiers | Yes |
| Enterprise/network firewall features | Limited by SKU | More comprehensive per current capabilities |
| Cost | Lower for basic needs | Higher, plus replica and related service costs |

**An SKU supporting a feature does not mean the feature works in every region or every configuration.** Before choosing, verify quotas, supported regions, networking features, private endpoints, pricing, and Azure Policy rules in the subscription.

### How Does Geo-Replication Work?

- You create **one ACR Premium** in a primary region and add **replication resources** in supported regions.
- Images/manifests and registry data are **asynchronously replicated** across regions by the service via supported mechanisms.
- Clients use the **same login server**, e.g., **acmeprod.azurecr.io**, rather than creating distinct registry names per replica.
- The service routes access to an appropriate replica based on location and availability. When using Private Link or specialized networking policies, inspect routing and private DNS separately.
- Replicas serve pulls in regions where they are ready. A newly pushed artifact may take time to propagate to all replicas.

ACR geo-replication follows an **active-active** registry model: one registry has multiple replicas serving operations per service capabilities. This is **not** a guarantee of instantaneous synchronous consistency across all regions. If multiple pipelines simultaneously push/overwrite the same tag from different locations, conflicts or unintended outcomes can occur. Use **one controlled release source**, immutable tags, and digests to avoid contention.

## 4. Choosing Replication Regions

Selecting a secondary region is not simply choosing the location farthest from the primary region:

1. **Workload locality:** wherever containers run, they should be able to pull images locally or from a nearby region.
2. **Data residency/compliance:** images may contain internal binaries, embedded configs, or regulated components; verify permitted regions.
3. **Resiliency:** avoid single-region failure dependency; plan for regional outages.
4. **SKU/feature availability:** are ACR Premium, replicas, networking, and Private Link supported in that region?
5. **Deployment network:** can VMs, AKS, Container Apps, build runners, private DNS, egress, and proxies connect?
6. **Cost:** Premium replicas, traffic, private endpoints, logging, and related costs.
7. **Operations:** who has permission to configure replicas, how health is measured, and what are the rollback conditions?

The pair **southeastasia** and **eastasia** in examples only illustrates design concepts. Verify they satisfy service conditions and organizational policies at deployment time rather than treating them as a universally guaranteed DR pair for every workload.

### When Is Geo-Replication Unnecessary?

- The application runs in only one region, has light pull demand, and has no multi-region DR target.
- Budget is constrained and a verified build/re-push or backup registry strategy already meets RTO.
- Large artifacts change infrequently; pull times and regional risks have been assessed as acceptable.

Not every development team needs Premium. Set targets for **availability, latency, recovery time, and total cost**, then select the corresponding solution.

## 5. Managing Releases with Tags, Digests, and Manifests

A reliable release pipeline must distinguish:

~~~text
Source commit 6f2a...
      |
      v
CI: test + build + scan
      |
      v
Image: orders/api:1.8.4
      |
      v
Digest: sha256:<HASH>
      |
      +----> Region A: deploy exact digest
      |
      +----> Region B: deploy exact digest
~~~

A **Tag** is a readable pointer; a **digest** is the content identifier. A multi-platform image can have an **OCI image index/manifest list** pointing to manifests for **linux/amd64** and **linux/arm64**. If target clusters use nodes with different CPU architectures, confirm the image supports the required platform; geo-replication **does not automatically turn an amd64 image into arm64**.

### Recommended Promotion Workflow

1. Build the image **once** from a specific commit.
2. Run unit/integration tests and security checks in the pipeline.
3. Push the image with a **unique release tag**; never reuse a tag to overwrite another artifact.
4. Capture/record the **manifest digest** from the registry.
5. Wait for ACR replication readiness; test actual pulls from target networks/regions.
6. Deploy to staging using the fixed tag or digest; run smoke tests.
7. Promote to production using the **exact same digest** without rebuilding separately per region.
8. Record commit, digest, registry, timestamp, approver, and every rolled-out region.

During rollback, point workloads back to the **previous known-good digest**; verify the older manifest/layers have not been deleted by retention policies and remain available in all serving regions.

### Preventing Tag Overwrites

ACR supports managing repository/image attributes and write permissions per service capabilities. For example, once a release is approved, you can apply policies or **write-enabled=false** attributes on tags/manifests where appropriate. However, understand the exact scope of locking: it does not necessarily stop every principal from creating other tags or modifying the repository via all APIs.

Prioritize **immutable release naming + narrow push permissions + auditing**. Do not rely on a single "lock tag" toggle alone to protect the supply chain.

## 6. Registry Access Model: Identity, Permissions, and Network

ACR has two independent yet complementary control planes:

- **Authentication + authorization:** who can log in, pull, push, alter repositories, delete artifacts, or administer the registry?
- **Network access:** from where can clients connect to the registry's **login server and data endpoints**?

~~~text
             Identity / Credentials
           Entra ID, managed identity,
           workload federation, tokens
                      |
                      v
       Authorization: pull/push/admin
                      |
                      v
       Network: public firewall rule
          or Private Endpoint
                      |
                      v
             Azure Container Registry
                      |
                      v
           Manifest + layers / artifacts
~~~

**Having AcrPull permission without a network path still fails to pull. Having a Private Endpoint path without repository read permission still gets denied.** Separate these two layers during diagnosis.

### Common Actor Groups

| Actor | Required Actions | Permission Design |
|---|---|---|
| CI build pipeline | Push release images | Only assigned repositories/scopes |
| Container Apps/AKS workload | Pull images when creating replicas | Pull only required repositories |
| Security team | View logs, scans, manage image policies | Read/scan per supported products |
| Registry administrator | Configure SKU, replicas, Private Endpoints, policies | Controlled management plane, audited |
| Vendor/partner | Pull a subset of images per contract | Repository-scoped token or role, expiration/revocation workflow |

Never grant **push** permissions to a workload that only needs to run images. A compromised container holding push rights could tamper with other deployments.

## 7. Microsoft Entra ID, RBAC, and Repository-Scoped Authorization

### Registry-Level RBAC

For registries using standard **Azure RBAC Registry Permissions** mode, roles like **AcrPull** and **AcrPush** grant data-plane permissions at the registry scope:

- **AcrPull:** serves pull/metadata-listing requests per role capabilities.
- **AcrPush:** serves push and related write operations within the granted scope.
- Additional roles handle deletion, administration, and specialized scenarios.

**Contributor/Owner** roles on the Azure resource (management plane) do not automatically represent a **least privilege** design for registry contents. Conversely, someone who only pulls does not need rights to modify network firewalls, replicas, or SKUs.

### Repository Permissions Mode with ABAC

Azure ACR offers an **RBAC Registry + ABAC Repository Permissions** model for supported registries/configurations. This model enables repository-level authorization via specialized roles and attribute conditions, including **Container Registry Repository Reader**, **Repository Writer**, and **Repository Contributor** per current role definitions.

**Important:** Do not assume legacy **AcrPull/AcrPush** can be used the old way on a registry created in ABAC repository permissions mode. Supported roles and assignment patterns vary by the registry's **role assignment permissions mode**; check the mode and service documentation before applying roles.

| Objective | Selection |
|---|---|
| Workload pulls across whole registry in standard RBAC | AcrPull at appropriate scope |
| CI pushes across whole registry in standard RBAC | AcrPush as needed, limit broad scope |
| Workload pulls only **orders/api** in ABAC model | Repository Reader + supported repository condition |
| CI pushes only **orders/api** in ABAC model | Repository Writer/Contributor per actual operations |
| Needs to list catalog/repositories in ABAC model | Check **Catalog Lister** role/permissions when needed |

Never guess an ABAC condition and assume the repository is isolated. During real deployment, verify with both an **authorized identity** and an **unauthorized identity**, testing pulls against both permitted and forbidden repositories.

### Repository-Scoped Tokens and Scope Maps

ACR supports **repository-scoped tokens** with **scope maps** in service-supported scenarios. This is an ACR-specific credential mechanism, **distinct** from Microsoft Entra ID managed identities. It can grant a partner access to a specific repository, for example:

~~~text
Scope map:
  repository: partner/sdk
  actions: content/read, metadata/read

Token:
  permissions derived from scope map
  credential managed, rotated, and revoked
~~~

Tokens carry their own secret/password, must be stored in a secure secret store with bounded lifetimes, and must never be sent over chat or committed to repositories. For Azure workloads capable of using Entra ID and managed identities, prefer passwordless approaches.

## 8. Managed Identities for Container Apps and AKS

### Azure Container Apps

Container Apps can use **system-assigned** or **user-assigned managed identities** to authenticate with ACR in supported configurations. Logical flow:

1. Create the required registry and repository.
2. Enable an identity on the Container App or attach an existing one.
3. Assign pull permissions matching the ACR mode.
4. Configure the Container App to use the registry and corresponding identity.
5. Ensure the Container Apps environment has network/DNS reachability to ACR.
6. Deploy an image/tag or digest and verify the new revision pulls successfully.

In Azure CLI, a sample Container App registry config when the identity already exists and holds appropriate permissions:

~~~bash
az containerapp registry set \
  --resource-group "<APP_RESOURCE_GROUP>" \
  --name "<CONTAINER_APP_NAME>" \
  --server "<ACR_NAME>.azurecr.io" \
  --identity system
~~~

This example uses a system-assigned identity. For a user-assigned identity, supply the appropriate ID per supported CLI and Container Apps configuration. This command **does not guarantee** the identity has been assigned the data-plane role or that private networking is working.

### Azure Kubernetes Service (AKS)

With AKS, the identity used to **pull images for nodes/kubelet** is not necessarily the managed identity application pods use to call other services. Identify the exact **kubelet identity/service principal** used for image pulls.

On standard ACR RBAC, the AKS **--attach-acr** command can automate part of assigning pull rights where supported. **For ACR ABAC repository permissions mode, that attach mechanism has limitations/does not support assigning roles under the new mode**; manually assign the appropriate repository reader role and check catalog roles if the scenario requires them.

Never assign **AcrPush** to the kubelet identity to "fix" a pull error. A standard production pod only needs pull permissions.

### CI/CD Should Use Short-Lived Identities

Pipelines can use a Microsoft Entra ID service principal with **workload identity federation/OIDC** where supported by the provider and organization. This reduces the need to store long-lived client secrets in CI.

Separate:

- **CI identity:** has push/release permissions, cannot arbitrarily edit firewalls or geo-replicas.
- **Workload identity:** pull-only.
- **Admin identity:** creates replicas, Private Endpoints, and modifies policies through an approval workflow.

## 9. Why Not Enable the ACR Admin User?

ACR has an **admin user** option generating a broad-privilege username/password, handy for some labs or legacy integrations. However, it is a high-risk credential: hard to attribute per workload and, if leaked, exposes multiple repositories.

For production:

- **Disable the admin user** unless an approved special exception exists.
- Use Entra ID, managed identities, or narrowly scoped credentials.
- Never store registry passwords in Dockerfiles, plain Kubernetes manifests, or CI logs.
- Maintain revocation, rotation, and anomalous push/pull monitoring procedures.

Inspect management configuration:

~~~bash
az acr show \
  --name "<ACR_NAME>" \
  --query "{name:name,sku:sku.name,adminUserEnabled:adminUserEnabled}" \
  --output json
~~~

To disable the admin user on a registry you are authorized to modify:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --admin-enabled false
~~~

Do not run this change on a shared registry without first checking whether legacy systems still depend on admin credentials.

## 10. Restricting Access Over Public Networks

ACR has a **public login endpoint** by default in many configurations. Even when images are private, a public endpoint accepts Internet connections before authentication checks occur. A public registry endpoint **does not mean repositories allow anonymous pulls**, yet restricting network access shrinks the attack surface.

With supported SKUs and features, control options include:

1. **Selected networks/IP allowlist:** accept public connections only from trusted egress IPs.
2. **Private Endpoint + public access disabled:** allow only configured private paths.
3. **Trusted services/network bypass** when genuinely needed and service-supported, with separate risk assessment.

### IP-Based Firewall Rules

Suppose a self-hosted build runner has a fixed public egress IP managed by your organization. You can add a network rule for the actual IP/CIDR as supported by ACR Premium:

~~~bash
az acr network-rule add \
  --name "<ACR_NAME>" \
  --ip-address "<APPROVED_PUBLIC_EGRESS_IP_OR_CIDR>"
~~~

Once all legitimate sources are prepared, configure deny-by-default:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --default-action Deny
~~~

**Do not run this sequence on a production registry without fallback administration and build runner paths.** Firewall changes can lock out CI/CD, container scale-out, or operators from the data plane. Verify SKU/feature support, actual sources passing through NAT/proxies, and rollback steps.

If your pipeline runs on a SaaS service with dynamic egress IPs, allowlisting one laptop IP will not solve it. Consider self-hosted runners on managed networks, Private Endpoints, and an appropriate CI model.

### What to Know When Choosing IP Allowlisting

- The IP must be the **public egress IP** seen by ACR, not the runner's private 10.x address.
- Behind NAT Gateways/firewalls, outbound traffic may use an egress IP different from the VM IP.
- Network rules do not grant pull/push permissions. Managed identities/RBAC are still required.
- Having geo-replication on ACR does not mean you can skip network governance across regions.
- "Allow trusted services" is not an arbitrary user-picked list; understand the actual bypass scope before enabling it.

## 11. Private Endpoints and Private Link for ACR

With **Azure Private Link**, you create a **Private Endpoint** inside a VNet/subnet to access ACR over a private IP address. This is common for internal container workloads and registries that must avoid public network exposure.

~~~text
                   Azure Container Registry
                     Premium + replicas
                       /           \
             Region A replica    Region B replica
                     ^                 ^
                     |                 |
                 Private Link access / DNS
                     |                 |
           VNet A + Private EP   VNet B + Private EP
                     |                 |
                 AKS / ACA           AKS / ACA
                  Region A            Region B
~~~

This diagram shows the logical architecture. A Private Endpoint is a **network interface inside a subnet**, not an ACR replica itself, and does not automatically create replicas. Clients still need valid authentication with the registry.

### Safe Design Sequence

1. Confirm **ACR Premium**, regions, feature support, and container network platforms.
2. Identify the VNets/subnets where **AKS/Container Apps, build runners, and admin tools** actually operate.
3. Create Private Endpoints to the registry following approved network procedures and permissions.
4. Configure Private DNS per Azure-provided endpoints; for ACR this typically involves **privatelink.azurecr.io**.
5. Ensure DNS resolution and connectivity to both the **registry login endpoint** **and data endpoints** used to pull layers.
6. Test pull/push from every approved source network, including standby regions.
7. **Only after private paths work reliably**, consider disabling public network access.
8. Document rollback steps, verify cross-region DNS, and run DR drills.

### DNS Is Easily Overlooked

ACR uses a login endpoint and **regional data endpoints** for image content. With geo-replication, the number of endpoints requiring resolution scales with regions. Data endpoint names follow patterns related to:

~~~text
<REGISTRY_NAME>.azurecr.io
<REGISTRY_NAME>.<REGION>.data.azurecr.io
~~~

With Private Link, private DNS records for the login server and configured data endpoints can be created/managed via Private DNS zone integration. Never invent static A records/IPs from an example: inspect the Private Endpoint's **DNS configuration**, Private DNS zone group, and ACR documentation for multi-replica registries.

**It is possible for login to succeed while layer pulls time out** if the client resolves only the registry login server while data endpoints are unreachable. This is a classic issue when combining geo-replication with Private Link.

### Multi-Region Networking and DNS

If two regions have disconnected VNets, each needs its own **private path** to the registry and matching DNS setup. With hub-spoke or custom DNS resolvers, verify private DNS zones are properly linked/forwarded without overlapping records across endpoints or misrouting traffic during a regional outage.

**Private Link does not re-encrypt images or bypass pull/push rules.** HTTPS/TLS remains in use per service; RBAC/identity remains mandatory.

## 12. Disabling Public Access Requires Testing and Rollback Paths

After establishing Private Endpoints, you may consider configuring **publicNetworkAccess=Disabled**:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --public-network-enabled false
~~~

**This command changes policy and can sever registry access. Do not run it purely for learning without a lab environment and recovery permissions.**

When disabling public access, verify that every required actor can still pull/push:

- Container Apps environments/AKS kubelets in region A.
- Standby workloads in region B.
- CI runners that push new images.
- Security inspection tools, scanners, webhooks, or supported integrations.
- Operators have a path to inspect and adjust settings without relying on public data-plane access.

A Microsoft-operated Azure service **does not automatically** reach your private ACR. Integrations like ACR Tasks, cloud-hosted runners, or scanning services have specific networking, trusted-services, and identity conditions. Test each integration rather than enabling broad bypasses to quickly patch a broken pipeline.

### Self-Lockout CI Scenario

Before the change:

~~~text
Hosted CI Runner -- Internet --> ACR public endpoint --> Push succeeds
~~~

After disabling public networking:

~~~text
Hosted CI Runner -- Internet -X-> ACR
                                      ^
                                      |
                         Private Endpoint in VNet
                                      ^
                                      |
                            Self-hosted Runner
~~~

For CI to keep pushing, you may need a self-hosted runner inside an authorized network or another **service-supported** integration. Disabling public access does not automatically move CI runners into your VNet.

## 13. How Do Geo-Replication and Private Endpoints Combine?

This is a critical intersection in this lesson:

- **Geo-replication** places registry data on regional replicas.
- **Private Endpoint** provides private connectivity from a VNet to the registry.
- **DNS** determines which IP/endpoint a client resolves.
- **Identity and roles** determine whether pull/push operations are allowed.

In practice, do not assume **one Private Endpoint in region A automatically suffices for region B**. The service may require corresponding endpoints and DNS records matching your architecture, especially when two workloads use independent private networks.

### Verification Matrix

| Test | Region A | Region B |
|---|---|---|
| Registry login FQDN resolves over right network path | Mandatory | Mandatory |
| Regional data endpoints are reachable | Mandatory | Mandatory |
| Workload identity has repository read permission | Mandatory | Mandatory |
| Pull a successfully replicated image | Mandatory | Mandatory |
| Spin up new instances/pods from the same digest | Mandatory | Mandatory |
| Pull while the other region experiences an outage | Drill if approved | Drill if approved |
| CI has a valid push path | Per design | Per design |

Only by testing the **actual data path** can you conclude the registry is ready for failover needs. A green replica status screen alone does not prove networking, IAM, and runtime are all correct.

## 14. Deploying via the Azure Portal

Illustrative steps with a Premium registry; UI details may vary across Portal versions:

1. Open [Azure Portal](https://portal.azure.com) and select your subscription and resource group.
2. Search for **Container registries**, create an ACR or open an assigned Premium registry.
3. Choose **Premium SKU**, primary region, and a globally unique registry name per ACR rules.
4. Ensure **Admin user** is Disabled when designing for production.
5. Go to **Replications / Geo-replications** and create a replica in the approved secondary region.
6. Check provisioning/replication status and storage usage.
7. Under **Access control (IAM)**, assign pull/push roles matching the exact identity and **role assignment permissions mode**.
8. Under **Networking**, configure Private Endpoints or public network rules per design.
9. With Private Endpoints, verify the private DNS zone, login/data records, and client paths.
10. Enable **Diagnostic settings** to route supported logs/metrics to the right monitoring destination.
11. Push/pull a sample image using the authorized identity and test from each region.

**Do not disable public access on step one** before CI runners, AKS, or Container Apps have private paths ready. Follow the sequence **configure → test → restrict → retest**.

### Permission Scopes and Approval Steps

Users permitted to edit ACR Networking/Replications generally need an appropriate resource management role; someone who only pushes images should not also hold permissions to change firewalls. Use change management, Azure Policy, Activity Log, and change reviews to prevent misconfiguration outages.

## 15. Azure CLI: Inspecting Registries and Creating Replicas

The sample commands below are for Azure CLI in **Bash/Cloud Shell**. This is **learning content**, not actions already executed on your subscription. Run create/modify commands only in an approved lab environment after evaluating Premium costs.

### Sign In and Select Subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table

RG="rg-acr-geo-lab"
LOCATION_A="southeastasia"
LOCATION_B="eastasia"
ACR="<GLOBALLY_UNIQUE_REGISTRY_NAME>"
~~~

**You must replace** ACR with a valid unused name; ACR names have specific rules, usually alphanumeric only with service-supported lengths. Never use sample names verbatim in production.

### Create Resource Group and ACR Premium

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION_A" \
  --tags environment=learning purpose=acr-georeplication

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --location "$LOCATION_A" \
  --sku Premium \
  --admin-enabled false
~~~

This Premium registry **can begin incurring costs** immediately upon creation. The example leaves networking open to avoid locking learners out during lab exercises; **it is not a complete production security configuration**.

### Create a Replica in the Second Region

~~~bash
az acr replication create \
  --resource-group "$RG" \
  --registry "$ACR" \
  --location "$LOCATION_B"
~~~

Results must be verified; a successful command invocation does not mean all images replicate instantaneously.

### Inspect Registry, Replicas, and Network Settings

~~~bash
az acr show \
  --name "$ACR" \
  --query "{name:name,sku:sku.name,loginServer:loginServer,adminUserEnabled:adminUserEnabled,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az acr replication list \
  --resource-group "$RG" \
  --registry "$ACR" \
  --query "[].{name:name,region:location,provisioningState:provisioningState}" \
  --output table

az acr network-rule list \
  --name "$ACR" \
  --output json
~~~

The **show/list** commands report configuration; **they do not prove a client in each region can successfully pull**. To prove usability, test from real networks and identities.

### If the Registry Does Not Support a Command or Region

Check Azure CLI version, **az acr replication --help** support, SKU, region, and Azure Policy. Never create another replica simply because of a permission or quota error; resolve the root cause first.

## 16. Image Distribution Demo: Build Once, Push Once

Suppose the development team has a container project with a **Dockerfile** and has tested the image. You can build and push with Docker CLI in an **environment permitted to access ACR**:

~~~bash
REPO="orders/api"
TAG="1.8.4"
LOGIN_SERVER="$ACR.azurecr.io"

az acr login --name "$ACR"

docker build -t "$LOGIN_SERVER/$REPO:$TAG" .
docker push "$LOGIN_SERVER/$REPO:$TAG"
~~~

**Requirements:** the host running commands has a Docker engine, sufficient registry permissions, network paths to login/data endpoints, and valid code/Dockerfile. Sign in to ACR with Entra ID whenever possible rather than enabling the admin user.

Verify repository/image:

~~~bash
az acr repository list \
  --name "$ACR" \
  --output table

az acr repository show-tags \
  --name "$ACR" \
  --repository "$REPO" \
  --output table

az acr repository show \
  --name "$ACR" \
  --image "$REPO:$TAG" \
  --output json
~~~

Save the manifest digest returned on push or queried from registry metadata, then use that exact digest for workload deployments as supported by the platform:

~~~text
<ACR_NAME>.azurecr.io/orders/api@sha256:<DIGEST>
~~~

**Do not copy an arbitrary digest from an example** and treat it as a real image. The digest must be verified from the registry for the built release, especially for multi-platform images.

### Testing Replication in Each Region

1. Confirm the registry has replicas in A/B with healthy provisioning states.
2. Use a **lab runner/VM in region A** with pull permission and proper networking to pull the image by digest.
3. Use a **lab runner/VM in region B** under the same conditions to pull **that exact digest**.
4. Verify tag/digest, CPU platform, and start a container or deploy a test workload.
5. If pulling in B does not find the manifest yet, check sync status and wait for asynchronous replication; do not re-push the same tag from B to "force" synchronization.
6. Record push timestamp, replica readiness time, and pull latency to evaluate operational needs.

Running test machines across two regions incurs compute, disk, and egress charges. You may practice **on paper** if you lack a sandbox; creating VMs solely for this exercise is not required.

### When Testing Without a Docker Daemon

Some workflows use **az acr import** from an allowed source registry, or **az acr build** for service-side builds. However, these operations have their own networking/permission requirements, especially when the registry is locked behind Private Link. Do not treat cloud-side import/build as a default way to bypass ACR firewalls.

## 17. Pinning Digests and Multi-Region Rollouts

A system runs two Container Apps environments or two AKS clusters. Once the image is present in A/B:

~~~text
CI pushes orders/api:1.8.4 (digest D)
                   |
                   v
             ACR geo-replication
              /              \
         Replica A          Replica B
              |                 |
         Stage region A     Stage region B
              |                 |
         Smoke tests        Smoke tests
              \                 /
               \               /
               Production rollout
                same digest D
~~~

With **Azure Container Apps**, revisions retain image/config versions and support traffic controls per platform capabilities. With **AKS**, Deployment/Helm/GitOps can reference the image digest. Rollout mechanics differ, but the principle stays the same: **one verified artifact, rolled out sequentially or via canary**.

### Why Are Warm Deployments Necessary?

During a regional outage, an app with replicas already running in B can keep serving even if the registry briefly experiences issues. However, when B needs to scale out or replace nodes, the system may have to pull images. Therefore:

- Compute failover capacity should be tested with the current image **before** an incident occurs.
- Never assume every node caches the exact image digest; node caches can be garbage-collected.
- Ensure the registry/Private Endpoint/DNS in B remain operational during failover scenarios.
- Retain previous release artifacts long enough for rollback.

Geo-replication improves **artifact distribution availability**; it does not guarantee application-wide RTO/RPO.

## 18. Verifying Permissions with Two Control Identities

To prove least privilege, do not test solely with an Owner account:

| Test Identity | Operation | Expected Result |
|---|---|---|
| CI writer for **orders/api** repository | Push release image to orders/api | Permitted per assigned role |
| CI writer | Modify ACR firewall or create replica | Denied if lacking management permissions |
| Container workload reader | Pull orders/api | Succeeds |
| Container workload reader | Push orders/api | Denied |
| Repository-scoped workload reader | Pull another ungranted repository | Denied under matching ABAC/scope model |
| Unprivileged identity | Pull private image | Denied |
| Authorized identity outside allowed network | Pull image | Fails due to network restriction |

Expected outcomes must match the **registry mode** and **actual configuration**. If using standard RBAC with AcrPull across the whole registry, do not expect automatic repository isolation simply because repository names differ.

### Interpreting 401 and 403 Properly

- **401 Unauthorized:** unauthenticated, invalid/expired token, or registry requires login; check auth challenge/credentials.
- **403 Forbidden:** authentication succeeded but lacks permission, or denied by policy/network access path depending on API/scenario.
- **Timeout/DNS/connection refused:** typically points to networking, DNS, firewall/Private Endpoint, proxy, or unreachable service.
- **manifest unknown:** image/tag/digest does not exist, has not replicated yet, or wrong reference.

Never conclude solely from an HTTP code that the root cause must be RBAC. Inspect detailed error messages, the active identity, network conditions, and logs to distinguish them.

## 19. Diagnostics with Azure CLI, DNS, and Registry Diagnostics

### Checking Login/Pull

From a machine with Docker or an appropriate registry tool:

~~~bash
az acr login --name "<ACR_NAME>"

docker pull "<ACR_NAME>.azurecr.io/orders/api:1.8.4"
~~~

The standard **az acr login** command uses the Docker CLI/daemon to cache credentials; **--expose-token** exists for scenarios without a Docker daemon, though its output contains a short-lived access token that must be protected. Never print tokens to logs or share them in screenshots.

Check DNS:

~~~bash
nslookup <ACR_NAME>.azurecr.io
~~~

Test from the **actual VNets/runners in regions A and B**, not just an administrator's laptop. With Private Link, DNS should resolve along the designed private path; seeing a public IP when a private IP is expected indicates misconfigured resolvers or zone links.

### Health Check Tool

The ACR CLI provides a **check-health** utility for registries and environments, depending on flags and CLI version:

~~~bash
az acr check-health \
  --name "<ACR_NAME>" \
  --yes
~~~

Check **az acr check-health --help** to confirm prerequisites, local/Docker checks, and impact. This tool aids diagnostics but **does not replace** testing pulls from real workloads and networks.

### Logs and Monitoring

In ACR, configure **Diagnostic settings** to send supported logs and metrics to Azure Monitor / Log Analytics per organizational policy. Depending on logging type, you can capture **login events**, **repository events**, authentication/operations, and registry metrics.

Distinguish between:

- **Management-plane Activity Log:** creating/deleting replicas, firewall edits, SKU/IAM/policy changes.
- **Data-plane registry events:** push/pull, repository operations, and related errors per supported log categories.
- **Workload platform logs:** Container Apps revisions, AKS pod events (such as ImagePullBackOff/ErrImagePull), CI pipeline logs.
- **Network/DNS logs:** firewall, DNS resolver, VNet, and Private Endpoint logs when enabled.

Log Analytics table names vary between **resource-specific** and **AzureDiagnostics** modes, as well as service features. Do not run a KQL query assuming a table definitely exists; inspect Diagnostic settings and the workspace schema first.

### Example Investigation Flow for ImagePullBackOff

1. Record the exact image reference, tag/digest, cluster/region, and timestamp.
2. Read the pod/revision error: **401, 403, manifest unknown, DNS timeout, or no matching manifest**?
3. Identify the kubelet/Container App identity and registry permissions mode.
4. Test Private DNS and login/data endpoints from the workload subnet.
5. Inspect replica status and test pulling the same digest from an authorized client in the region.
6. Check if a pipeline recently moved a tag, deleted a manifest, or ran cleanup.
7. Change only one specific root cause at a time, then retry in a controlled manner.

Never immediately enable the ACR admin user or open public access to the entire Internet to "cure" ImagePullBackOff in production.

## 20. Common Failure Scenarios

| Symptom | Possible Causes | Investigation / Remediation |
|---|---|---|
| ACR Basic lacks Replications menu | SKU does not support geo-replication | Review Premium requirements, pricing, and migration plan |
| Replica created successfully, new image fails to pull in B | Asynchronous replication lag or data endpoint path | Check replica health, wait for sync, test same digest |
| Registry login succeeds, layer pull times out | Missing DNS/Private Endpoint for data endpoints | Check regional data endpoints and private DNS records |
| Container Apps fails to pull image | Managed identity lacks permission, wrong registry config/port/network | Check ACA identity, ACR role, VNet/DNS, and revision logs |
| AKS ImagePullBackOff with ACR ABAC | Legacy attach-acr does not grant repository-mode role | Assign conditional repo reader per mode, verify kubelet identity |
| CI pipeline pushed before disabling public access, then 403/timeout | Hosted runner is not inside private network | Use supported CI path, deploy private runner, or appropriate config |
| Same tag, but A/B run different binaries | Tag was overwritten, release race, or inconsistent image | Verify digests, lock promotion, and roll back |
| Pull returns **manifest unknown** | Wrong repo/tag, artifact deleted, or not yet replicated | Check repository metadata, tag history/retention, replica status |
| Pull returns **no matching manifest for linux/arm64** | Image lacks manifest for CPU architecture | Build appropriate multi-platform image; do not blame the region |
| CI has AcrPush yet cannot modify firewall | Data-plane role does not include management plane | Grant admin permissions separately through IAM workflows |
| Runner has AcrPush yet push times out | No network path to ACR | Check DNS, firewall allowlist, Private Endpoint |
| Private Endpoint reachable from A but not B | B's VNets/DNS/endpoint topology not prepared | Verify zone links, resolvers, data endpoints, and routing |
| External users can pull internal images | Broad permissions/tokens/public config, leaked credentials | Revoke tokens, inspect audits, review permissions/network |
| After locking network, scanner/automation stops working | Integration lacks private support or bypass undesigned | Evaluate features, private runners, or official access paths |
| ACR cost increases after adding replicas | Premium geo-replication, storage, transfer, and monitoring | Review Cost Management and necessity of each replica |

**Principle:** a pull error can stem from **identity**, **network**, **image reference**, **replication timing**, or **runtime platform**. Never alter multiple layers simultaneously, making the root cause impossible to isolate.

## 21. Handling an ACR Region Outage

Suppose an application operates in two regions and ACR has replicas A and B. Region A becomes unavailable right as CI releases a new version.

### Impact to Analyze

- Do running containers in B continue serving?
- Does B have enough compute/database/network capacity to handle additional traffic?
- Has the **latest release digest** replicated to B yet?
- Are B's registry login/data endpoints, private DNS, and identities still usable?
- Should CI continue pushing or **freeze releases** while registry consistency is unverified?
- Should the application roll back to a tested digest confirmed present in B?

### Suggested Runbook

1. **Freeze non-urgent image changes** to avoid racing with replication.
2. Inspect registry/replica health, image digests, and logs from workload B.
3. Verify pulling the known-good release in B; avoid manually re-pushing mutable tags from another pipeline.
4. Evaluate application, database, and ingress failover conditions **independently of the registry**.
5. If the new image is unsafe or unavailable in B, use a verified stable digest.
6. Shift traffic via the designed application mechanism (e.g., Front Door) per runbook.
7. Monitor scale-out, ImagePullBackOff, latency, HTTP errors, and business transactions.
8. Once A recovers, confirm replica synchronization, intact policies, and absence of anomalous images before reopening pipelines.

A **healthy replica** does not mean the application meets RTO: verify container startup, data connectivity, and request handling. **ACR geo-replication does not replace database backups/redundancy or application logic.**

## 22. Protecting the Image Supply Chain

Networking and identity are necessary but insufficient. A compromised identity with push permissions can still push malicious images into a private registry.

Additional controls to implement:

- **Build provenance:** record source commit, pipeline/job ID, approver, and digest.
- **Dependency/image scanning:** use scanners or Microsoft Defender for Cloud/Containers per supported tier and features.
- **SBOM:** retain software bills of materials per organizational workflow.
- **Image signing/verification:** consider OCI signatures and pipeline/admission verification policies with compatible tools.
- **Tag immutability/promotion discipline:** never reuse production tags for different content.
- **Principle of least privilege:** CI pushes only to assigned repos, workloads pull only; avoid admin accounts.
- **Secret hygiene:** never bake access tokens, keys, or passwords into image layers/Dockerfiles.
- **Artifact retention:** keep enough digests for rollback, with cleanup policies preventing deletion of running releases.
- **Audit + alerting:** alert on anomalous pushes, firewall/IAM edits, repository deletions, and rising pull errors.

**A registry does not automatically certify an image as safe** merely because it resides in ACR Premium. Images must still be vetted from source through build, deployment, and runtime.

## 23. Costs and Operational Decisions

Geo-replication and Private Link improve availability and security, yet increase costs:

| Component | Cost Categories to Review |
|---|---|
| **ACR Premium** | Pricing per tier/capacity and billable service usage |
| **Geo replicas** | Ongoing cost per replicated region at current rates |
| **Registry storage** | Layer/manifest/artifact volume and retention policies |
| **Data transfer** | Pull/push network traffic, especially cross-region or Internet egress if applicable |
| **Private Endpoints** | Private link resources and traffic under billing models |
| **Private DNS/Resolver** | Zones, queries/forwarders, and resolvers per usage |
| **Compute/CI runners** | AKS/Container Apps, VM runners, and network egress |
| **Diagnostic logs** | Ingestion, retention, analytics, and alerting |
| **Security scanning** | Security plans or appropriate scanning tools |

Never quote fixed prices without specifying region, tier, replica count, and workload. Use **Azure Pricing Calculator** and **Cost Management** to estimate, assign tags/environment owners, and set budget alerts. **Budget alerts do not automatically halt billing.**

For build-heavy workloads, watch pull frequency, image size, duplicate layers, caching, and data transfer costs. Optimizing Dockerfiles and shrinking image sizes can cut startup time and transfer costs without adding replicas.

### When to Clean Up Resources

After labs, Premium registries and replicas can continue accruing charges even when no images are pushed. Delete a registry or resource group **only when certain no other workloads depend on it** and needed artifacts are preserved. Never delete images/digests actively used by production just to reclaim a few GiB.

## 24. Safe Lab Exercise: Designing and Verifying Multi-Region ACR

This exercise has two tiers: **design/read-only** requiring no new resources, and a **billable lab** if you have a dedicated subscription.

### Scenario

An enterprise operates across two regions:

- **Region A:** primary production Container Apps and CI runner.
- **Region B:** standby/active Container Apps able to scale out if A fails.
- Business image **orders/api:1.8.4** is built by one pipeline.
- Requirements: workloads only pull images, CI pushes only to required repositories; arbitrary public access to the registry is disallowed.
- Policy requires keeping the previous release digest for rollback.

### Part A — Create the Design

Complete the table:

| Item | Proposed Design | What Must Be Proven |
|---|---|---|
| SKU | ACR Premium | Geo-replication/private networking features supported |
| Replicas | A and B in permitted regions | Provisioning health + pulls in both regions |
| Image identity | Immutable tag + pinned digest | Both regions run the exact same digest |
| CI identity | Managed/federated identity with narrow push rights | Pushes to right repo, cannot administer network |
| Workload identity | Pull-only managed identity | Cannot push |
| Registry endpoint | Single login server | DNS/network paths work from A/B |
| Private networking | Private Endpoints and DNS per topology | Both login and data endpoints reachable |
| Public access | Restricted or disabled after private testing | Does not break CI/scale-out |
| Observability | Registry/workload/network logs | Distinguish 401, 403, timeout, and replica lag |
| Recovery | Previous image digest + B runbook | Pull/start in B when A fails |

### Part B — Read-Only Checks in Azure CLI

With a registry where you have read permissions:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

ACR="<EXISTING_LAB_ACR>"
RG="<LAB_RESOURCE_GROUP>"

az acr show \
  --name "$ACR" \
  --query "{name:name,sku:sku.name,loginServer:loginServer,publicNetworkAccess:publicNetworkAccess,adminEnabled:adminUserEnabled}" \
  --output json

az acr replication list \
  --registry "$ACR" \
  --resource-group "$RG" \
  --output table

az acr network-rule list \
  --name "$ACR" \
  --output json
~~~

Listing repositories requires **appropriate data-plane permissions** and a network path to ACR:

~~~bash
az acr repository list \
  --name "$ACR" \
  --output table
~~~

If you get 401/403 or a timeout, record the error type and inspect permissions/networking rather than enabling the admin user. You do not need to create images or VMs to complete the design portion.

### Part C — Billable Resource Creation Lab (Optional)

If your organization provides a **lab subscription**, budget, and approval to create a Premium registry:

1. Select two supported regions; verify data policies and costs.
2. Create a dedicated lab resource group and ACR Premium with admin user disabled.
3. Create replica B; observe status with **az acr replication list**.
4. Push a test image with a unique tag from an authorized runner and record the digest.
5. Verify pulling that exact digest from A and B using two lab clients with valid network paths and roles.
6. If practicing Private Endpoint, create and test DNS/Private Endpoints under network team guidance; disable public access only after private connectivity works.
7. Test a **pull-only identity** and confirm push operations are denied.
8. Perform simulated "CI offline," "replica lag," or "network failure" drills without disrupting shared registries.
9. Document results and delete **lab-only resources** once certain no needed data remains.

**Never intentionally disrupt a production registry, lock firewalls, or delete replicas to simulate real incidents.** Any real failover test requires an approved runbook, authorization, and maintenance window.

### Evidence to Submit

| Item | Evidence |
|---|---|
| Registry | SKU, primary region, login server, role assignment permissions mode |
| Replicas | Region list, status, check timestamps |
| Image | Repository, tag, digest, target CPU architecture |
| Identity | CI and workload pull/push permissions, no secrets recorded |
| Network | Public policy, Private Endpoint, login/data endpoint DNS |
| Test | Pulls from A/B, errors and remediation if any failed |
| Security | Admin disabled, public access restricted, appropriate repo permissions |
| DR | How prior releases are kept, how B scales out, and business checks |
| Cost | Estimated Premium/replica/private networking costs and cleanup result |

## 25. Pre-Production Checklist for Multi-Region ACR

- [ ] Justified geo-replication per workload/RTO and selected appropriate Premium SKU.
- [ ] Regions A/B meet residency, service support, and quota requirements.
- [ ] Uses one registry login server and accounts for asynchronous replication.
- [ ] CI builds once, pushes once, applies a unique tag, and records the digest.
- [ ] Clusters/Container Apps in each region can pull the exact digest and CPU architecture.
- [ ] Checked ACR **role assignment permissions mode**; did not mix AcrPull with ABAC without verification.
- [ ] CI holds write rights only to required repositories; workloads are pull-only.
- [ ] Admin user disabled unless an approved, controlled exception exists.
- [ ] Private Endpoints/DNS configured per VNet; verified both login and data endpoints.
- [ ] Did not disable public access before confirming CI/AKS/Container Apps have valid private paths or allowlists.
- [ ] Logging, auditing, alerting, and procedures to diagnose 401/403/DNS/replication errors are active.
- [ ] Image signing/scanning/SBOM and secret hygiene follow supply chain policy.
- [ ] Previous release retained for rollback, and B scale-out tested.
- [ ] Runbook ready for single-region outage, release freeze, digest verification, and pipeline recovery.
- [ ] Budget/cost monitoring enabled for Premium, replicas, networking, and log retention.
- [ ] Verified cleanup paths in lab without impacting production.

## 26. Self-Check Questions

1. Does a geo-replicated Premium ACR use one login server or a different login server per region?
2. Does geo-replication synchronize images instantaneously and automatically deploy apps to Container Apps B?
3. Why record the digest on release instead of relying solely on the **latest** tag?
4. If ACR already has replica B but AKS B lacks pull permissions, does geo-replication solve that?
5. How do **AcrPull/AcrPush** differ from repository-level ABAC permissions?
6. Why should a CI writer not have permission to edit firewall and geo-replication settings?
7. How does a repository-scoped token differ from a managed identity? When is each appropriate?
8. Why does a Private Endpoint not automatically grant permission to read images?
9. If login succeeds yet layer pulls time out, which endpoints/DNS records should be inspected?
10. With a private two-region ACR, why must DNS and pulls be tested from both VNets?
11. How can disabling public network access break a hosted CI pipeline?
12. Why do production Container Apps/AKS workloads typically need only pull permissions?
13. When might **manifest unknown** appear even after a replica has been created?
14. Why might an image with a valid digest still fail to run on an ARM64 node?
15. Does geo-replication guarantee database RPO or Front Door failover?
16. What data must be collected when investigating ImagePullBackOff?
17. What costs arise when adding geo replicas and Private Endpoints?
18. Why retain older release images even after a pipeline successfully pushes a new release?

## 27. References

- [Azure Container Registry overview](https://learn.microsoft.com/azure/container-registry/container-registry-intro) — registries, repositories, and the role of ACR.
- [Geo-replication in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-geo-replication) — Premium geo replicas and multi-region distribution architecture.
- [Azure Container Registry service tiers](https://learn.microsoft.com/azure/container-registry/container-registry-skus) — Basic/Standard/Premium and limits.
- [Authenticate with an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — Entra ID, service principals, managed identities, and credentials.
- [Overview of permissions and roles in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-built-in-roles-overview) — registry and repository permissions by mode.
- [Repository permissions using ABAC](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions) — attribute-based permission conditions by repository.
- [Repository-scoped permissions](https://learn.microsoft.com/azure/container-registry/container-registry-repository-scoped-permissions) — tokens and scope maps.
- [Restrict access to an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-access-selected-networks) — public network firewall/IP rules.
- [Connect privately to an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-private-link) — Private Endpoints and DNS.
- [Managed identity image pull in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull) — connecting ACA–ACR using identity.
- [Authenticate from AKS to ACR](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration) — kubelet identity and pull permissions.
- [Azure CLI: az acr](https://learn.microsoft.com/cli/azure/acr) — registry management, login, and health.
- [Azure CLI: az acr replication](https://learn.microsoft.com/cli/azure/acr/replication) — creating and listing geo replicas.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating Premium/replication/networking costs by region.

**Conclusion:** Secure multi-region image distribution requires solving **the right artifact**, **sufficient replicas**, **the right identity/permissions**, and **the right network paths** simultaneously. ACR Premium geo-replication provides the foundation for multi-region image distribution through a single registry, yet replication has latency and does not replace application deployment or DR mechanisms. Use immutable tags and digests, scope push/pull permissions to the supported mode, test Private Link/DNS from each region, monitor real errors, and maintain rollback runbooks alongside a cost plan.
