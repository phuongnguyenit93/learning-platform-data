# Private Pools and Accessing Private Network Resources During Builds

A CI/CD pipeline may need to fetch source code from an internal Git server, install dependencies from a private package registry, run tests against a database without a public IP, or deploy applications to a Kubernetes cluster with only a private endpoint. Builds running in the service's default environment typically lack a direct network path to those resources. Opening public endpoints for every system solely for builds increases the attack surface and adds operational overhead.

**Cloud Build private pools** provide dedicated worker groups managed by Google Cloud for your organization. When a private pool connects to a VPC via Private Services Access, workers can communicate with internal resources over internal IP addresses. Consequently, pipelines can reach private repositories, internal registries, databases, private secret store endpoints, or runtimes in the connected network.

In the CLOUD_PROVIDERS_GCP module, private pools connect CI/CD with VPC, IAM, Shared VPC, Cloud DNS, Cloud VPN, Cloud Interconnect, and VPC Service Controls. The module focuses on exploring projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases; private pools bring the build process inside that same network and security boundary.

After this lesson, you will be able to:

- Distinguish between Cloud Build's default pool and private pools.
- Describe the service producer network and VPC peering connectivity via Private Services Access.
- Select IP ranges for a private pool, avoid CIDR conflicts, and configure firewall rules.
- Create a private pool with the Google Cloud CLI and select the pool in cloudbuild.yaml.
- Configure private DNS, Shared VPC, and on-premises network access.
- Understand transitive peering limitations when connecting to Google-managed services in another VPC.
- Distinguish worker pool administration permissions, build invocation permissions, and build runtime permissions.
- Restrict public egress, apply VPC Service Controls, and verify connectivity.

## 1. Default Pool vs. Private Pool

### Default Pool

When running a build without specifying a worker pool, Cloud Build uses a Google-managed default worker environment. Each build runs in an isolated environment and can reach the public Internet. The default environment suits pipelines that do not require deep worker customization or access to resources behind a VPC firewall.

### Private Pool

A private pool is a dedicated group of workers tailored to customer configuration while still managed by Cloud Build. You do not need to provision, patch, or scale worker VMs yourself. The pool scales automatically with build demand and scales down to zero when idle. You can configure machine type, disk size, region, internal IP range, and egress options.

A key distinction: the name private pool does not mean workers reside directly inside your VPC. Workers are hosted in a Google-owned **service producer network**. If you want workers to reach private resources in your VPC, you must establish a private connection between the service producer network and that VPC.

| Capability | Default Pool | Private Pool |
|---|---|---|
| Google-managed workers | Yes | Yes |
| Machine type and disk configuration | More limited | More flexible |
| Public Internet access | Yes | Configurable |
| Connect to VPC for private resources | No equivalent peering configuration | Yes, via Private Services Access |
| Disable worker public IPs | No equivalent configuration | Can use NO_PUBLIC_EGRESS |
| VPC Service Controls integration | Limited by default model | Private pool can be configured in perimeter |

Choose a private pool when builds need private network access, egress controls, custom machine types/disks, or compliance with organizational security policies. If a pipeline only downloads public source, builds images, and pushes to public registries, the default pool may suffice.

## 2. Network Connectivity Architecture

Private pools run inside a service producer network. Private Services Access establishes a connection between the customer's VPC and the service producer network using VPC Network Peering. Once active, workers can send traffic to subnets or private endpoints that have matching routes and firewall rules in the peered VPC.

~~~mermaid
flowchart LR
    A[Cloud Build trigger or user] --> B[Cloud Build service]
    B --> C[Private pool workers]
    subgraph G[Google-owned service producer network]
        C
    end
    G <-->|Private Services Access / VPC peering| V[Organization VPC]
    subgraph N[Customer VPC]
        V --> R[Private repository]
        V --> D[Internal database]
        V --> K[Private GKE endpoint or runtime]
        V --> S[Secret / artifact service]
    end
~~~

This connection uses internal IP addresses. You do not need to assign a public IP to a database or Git server just so workers can reach it. However, network connectivity does not automatically grant permission to read repositories, databases, or secrets; firewalls, DNS, and IAM must still be configured separately.

### Two Network Configuration Modes

1. **Use the default service producer network:** do not configure peering to a customer VPC. The pool still gets custom machine types and disks, and can access the Internet according to the chosen egress option. Use this when builds do not need private resources.
2. **Connect the service producer network to a VPC:** declare the VPC to peer with and the IP range allocated to workers. Use this when builds must reach private resources in a VPC.

### Private Services Access and VPC Network Peering

Private Services Access involves these main steps:

1. Enable the Service Networking API in the project managing the VPC.
2. Select an unused CIDR block and reserve it for the service producer.
3. Create a private connection to the Service Networking API.
4. Configure the private pool to use the connected VPC and worker IP range.

The reserved CIDR range is the address space allocated to the service producer. The IP range configured in the private pool is the subset of addresses workers may use within that allocation. These two values have a containment relationship; neither may be chosen arbitrarily or overlap with subnets, routes, on-premises networks, or other service allocations.

## 3. IP Address Planning

Before creating the connection, inventory:

- Existing subnets in the VPC.
- CIDR ranges of peered VPCs.
- On-premises network ranges advertised via Cloud VPN or Cloud Interconnect.
- IP ranges already reserved for other Private Services Access connections.
- IP ranges used internally by build tools or containers inside workers.
- Concurrent builds and the number of workers needing IP allocation.

Cloud Build reserves the ranges 192.168.10.0/24 and 172.17.0.0/16 for Docker bridge networks. Avoid using these ranges as destination addresses for resources builders need to access, as overlaps can misroute traffic or prevent reaching destinations.

Illustrative design example:

| Component | Sample IP Range | Purpose |
|---|---|---|
| Application VPC | 10.20.0.0/16 | Subnets for VMs, GKE nodes, and workloads |
| Private Services Access allocation | 10.90.0.0/16 | Space reserved for service producer |
| Private pool worker range | 10.90.0.0/24 | Internal IPs allocated to the worker pool |
| On-premises network | 10.120.0.0/16 | Data center network via VPN or Interconnect |

This is only an example. Confirm ranges do not overlap with any connected network and provide sufficient capacity for the expected worker count.

### Sizing the Allocation and Worker Range

For a Private Services Access allocation, Google Cloud requires at least a /24 block and recommends /16 for multiple Google services. A numerically smaller prefix, such as /16, contains more addresses than /24.

The private pool's peeredNetworkIpRange field can be left empty so Cloud Build automatically allocates a default /24 range. If specified, the CIDR must lie within the reserved allocation and its prefix size must not be smaller than /29 (larger than /29 in prefix length). A /24 provides 254 usable host addresses; a /29 provides only 6 usable host addresses. Maximum concurrent workers are capped by usable IPs in the range.

Avoid picking /29 just to save addresses when a pool might run multiple concurrent builds. Estimate concurrency, scaling headroom, and spare IPs before creating the pool.

## 4. Preparing APIs and IAM

### APIs to Enable

In the project creating the private pool, enable the Cloud Build API. In the project hosting the VPC, enable the Service Networking API. If using Cloud DNS private zones or DNS peering, also enable the Cloud DNS API in the project managing DNS.

~~~bash
gcloud services enable cloudbuild.googleapis.com \
  --project=PRIVATEPOOL_PROJECT_ID

gcloud services enable servicenetworking.googleapis.com \
  --project=NETWORK_PROJECT_ID

gcloud services enable dns.googleapis.com \
  --project=NETWORK_PROJECT_ID
~~~

Replace sample values with real project IDs. The principal enabling APIs needs `serviceusage.services.enable` permission, typically granted via Service Usage Admin.

### Distinguishing Three Identities

Private pools involve three permission groups that should be kept distinct:

| Identity | Common Role | Purpose |
|---|---|---|
| Pool administrator user or service account | Cloud Build WorkerPool Owner: roles/cloudbuild.workerPoolOwner | Create, update, view, and delete worker pools |
| Build requester user or service account | Cloud Build WorkerPool User: roles/cloudbuild.workerPoolUser | Submit builds to run on the pool |
| Service account executing build steps | Roles per target resource, e.g., Artifact Registry Reader or Secret Manager access | Read dependencies, fetch secrets, write artifacts, or deploy applications |

The person creating the private connection in the network project needs Compute Network Admin (roles/compute.networkAdmin) or an equivalent custom role. This permission covers reserving IP ranges and managing private connections.

### Building from a Different Project Than the Pool's Project

Cloud Build allows builds to be launched from a different project than the one hosting the private pool. When invoking builds via gcloud CLI or API, grant `roles/cloudbuild.workerPoolUser` on the pool project to the user or service account requesting the build.

For triggers running in another project, grant WorkerPool User to the service account used by the trigger on the pool project. If the trigger and pool reside in the same project, this cross-project permission is not needed under standard trigger execution.

Example granting permission to a trigger's service account:

~~~bash
gcloud projects add-iam-policy-binding PRIVATEPOOL_PROJECT_ID \
  --member="serviceAccount:BUILD_TRIGGER_SA" \
  --role="roles/cloudbuild.workerPoolUser"
~~~

Permission to use a worker pool does not imply permission to read data. The build execution service account still needs separate roles to access Artifact Registry, Secret Manager, GKE, databases, or target resources. VPC peering also does not replace IAM.

## 5. Creating Private Services Access for the VPC

The following example creates a connection from Cloud Build's service producer network to a VPC named `ci-vpc` in the network project. Choose an allocation that does not overlap with existing subnets or routes.

### Step 1: Reserve an IP Range

~~~bash
export NETWORK_PROJECT_ID="shared-network-prod"
export NETWORK_NAME="ci-vpc"
export RESERVED_RANGE_NAME="cloudbuild-private-pool"

gcloud compute addresses create "$RESERVED_RANGE_NAME" \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --description="Private Services Access range for Cloud Build" \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

The command lets Google Cloud pick an available /16 block. If the organization already plans CIDRs, you can additionally specify `--addresses` with an appropriate starting address. Never pick a CIDR solely from an example without checking current routes and allocations.

### Step 2: Create the Private Connection

~~~bash
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$RESERVED_RANGE_NAME" \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

This command initiates a long-running operation. Monitor the operation until it finishes successfully before creating the private pool:

~~~bash
gcloud services vpc-peerings list \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

You can inspect the created allocation:

~~~bash
gcloud compute addresses list \
  --global \
  --filter="purpose=VPC_PEERING" \
  --project="$NETWORK_PROJECT_ID"
~~~

Do not delete the private connection while private pools still depend on it. If the connection is deleted, builds can remain stuck in a queued state and time out because workers lose their expected network path. Delete dependent private pools first, then tear down the connection per procedure.

## 6. Creating the Private Pool

### Creating the Pool Configuration File

The private pool configuration file and `cloudbuild.yaml` serve different purposes:

- The private pool config file describes networking, egress, and worker pool settings.
- The Cloud Build config file describes build steps, images, artifacts, timeout, and the pool used to run the build.

Example `private-pool.yaml`:

~~~yaml
privatePoolV1Config:
  networkConfig:
    egressOption: NO_PUBLIC_EGRESS
    peeredNetwork: projects/shared-network-prod/global/networks/ci-vpc
    peeredNetworkIpRange: 10.90.0.0/24
  workerConfig:
    machineType: e2-standard-4
    diskSizeGb: 200
    workerRelease: stable
~~~

In this example:

- peeredNetwork is the resource URL of the VPC hosting internal resources.
- peeredNetworkIpRange is the worker range inside the reserved allocation.
- machineType and diskSizeGb adjust worker resources.
- workerRelease selects the worker release channel; stable is an illustrative choice.
- NO_PUBLIC_EGRESS creates workers without public IPs and blocks direct access to public IPs unless routed through an appropriate proxy.

If builds need public Internet access to download dependencies, design an approved egress path before selecting NO_PUBLIC_EGRESS. You can use internal repository mirrors or an organization-managed proxy. Do not disable public egress and still expect workers to pull packages directly from the Internet.

### Step 2: Create the Worker Pool

~~~bash
export PRIVATEPOOL_PROJECT_ID="ci-platform-prod"
export PRIVATEPOOL_ID="ci-private-pool"
export REGION="asia-southeast1"

gcloud services enable cloudbuild.googleapis.com \
  --project="$PRIVATEPOOL_PROJECT_ID"

gcloud builds worker-pools create "$PRIVATEPOOL_ID" \
  --project="$PRIVATEPOOL_PROJECT_ID" \
  --region="$REGION" \
  --config-from-file=private-pool.yaml
~~~

The account running the command needs `roles/cloudbuild.workerPoolOwner` on the pool project and necessary permissions on the network project to establish the connection. The pool can only be used after creation succeeds and network configuration is ready.

Check status:

~~~bash
gcloud builds worker-pools describe "$PRIVATEPOOL_ID" \
  --project="$PRIVATEPOOL_PROJECT_ID" \
  --region="$REGION"
~~~

## 7. Selecting a Private Pool for a Build

In `cloudbuild.yaml`, specify the full pool name under `options.pool.name`:

~~~yaml
steps:
  - name: "asia-southeast1-docker.pkg.dev/ci-platform-prod/ci-tools/db-check:1.0"
    entrypoint: bash
    args:
      - "-c"
      - |
        pg_isready -h 10.20.4.15 -p 5432 -d appdb

options:
  pool:
    name: "projects/ci-platform-prod/locations/asia-southeast1/workerPools/ci-private-pool"
  logging: CLOUD_LOGGING_ONLY
~~~

This example uses a tool image stored in Artifact Registry and checks TCP connectivity to a PostgreSQL private IP. The build service account must have permission to read the image and permissions needed for other operations. Ensure the tool image is available in an accessible registry; with a pool that has no public egress, do not depend on images hosted only on public registries.

Submit the build to the matching region:

~~~bash
gcloud builds submit \
  --project="application-build-prod" \
  --region="asia-southeast1" \
  --config="cloudbuild.yaml" \
  .
~~~

The pool can live in a different project from the one submitting the build. In that case, the pool name in `cloudbuild.yaml` must point to the pool-owning project, and the principal requesting the build must hold WorkerPool User on that project.

## 8. Configuring Firewalls and Routes

Private Services Access establishes connectivity and exchanges subnet routes, but it does not automatically open all firewall ports. You must still allow traffic from the worker range to the exact private resources.

### Ingress Firewalls

For example, if PostgreSQL has private IP 10.20.4.15 and listens on TCP 5432, the firewall rule in the destination VPC must allow the private pool's worker range as source:

| Attribute | Example |
|---|---|
| Direction | Ingress |
| Source range | 10.90.0.0/24 |
| Destination | VM or workload running the database |
| Protocol/port | TCP 5432 |
| Action | Allow |

Do not open the entire VPC on all ports. Create rules scoped to required workloads, ports, and source ranges. If using firewall rules based on target tags or service accounts, confirm destination resources actually carry the corresponding tags or identities.

### Routes and Address Ranges

VPC peering is not a general-purpose site-to-site VPN. The service producer network learns subnet routes from your VPC by default. If access to on-premises networks via Cloud VPN or Cloud Interconnect is needed, configure appropriate custom route exchange so the service producer network learns routes to on-premises networks and the on-premises side has return routes to the allocation/private pool range.

When enabling custom route export on the private connection, inspect advertised routes and avoid overlapping with Private Google Access ranges. On the on-premises side, advertise necessary prefixes via Cloud Router/BGP or configure corresponding routes. VPN tunnels or VLAN attachments must terminate in the same VPC (or Shared VPC) as the private connection because VPC Network Peering does not support transitive routing.

### No Transitive Peering

Suppose:

1. The private pool peers with VPC A.
2. VPC A peers with VPC B.
3. A database or private GKE endpoint resides in VPC B.

Private pool workers do not automatically traverse VPC A to reach VPC B. VPC Network Peering does not propagate routes across an intermediate VPC. For a private GKE control plane, the control plane lives in a Google-managed project and connects to the customer VPC via Private Service Connect; thus, peering from the private pool and GKE's PSC connection do not automatically form a transitive path. Cloud Build documentation guides connecting two customer-managed VPCs with Cloud VPN to complete routing, or using GKE's DNS-based endpoint if requirements permit.

This is a common reason workers can reach a VM in the directly peered VPC but cannot reach the private endpoint of a Google-managed service peered into that same VPC.

## 9. Private DNS for Private Resources

If builds use hostnames like `git.corp.example.com` or `db.corp.example.com`, IP connectivity is not enough; workers must resolve those domain names properly. Cloud DNS private zones are visible only to VPC networks attached to the zone by default. To let the service producer network resolve names from a private zone, configure DNS peering with the corresponding DNS suffix.

Example:

~~~bash
gcloud services peered-dns-domains create cloudbuild-corp-dns \
  --network="ci-vpc" \
  --dns-suffix="corp.example.com." \
  --project="NETWORK_PROJECT_ID"
~~~

The DNS suffix must be a fully qualified domain name ending with a period. Enable the Cloud DNS API before configuring. Share only suffixes workers need to look up; avoid forwarding your entire internal DNS namespace unnecessarily.

Verify sequentially:

- The hostname has appropriate A/AAAA records in the private zone.
- The private zone is attached to the VPC peered with the private pool.
- DNS peering uses the exact suffix.
- Firewalls and routes allow connections to the returned IP.
- No duplicate public record causes clients to resolve the wrong endpoint.

## 10. Shared VPC and On-Premises Networks

### Shared VPC

In a Shared VPC architecture, the host project owns the VPC, subnets, firewalls, and routes; service projects create private pools. To use a private pool with Shared VPC:

1. Attach the project containing the private pool to the host project owning the Shared VPC.
2. Reserve the allocation and create the Private Services Access connection in the host project.
3. Select that Shared VPC as `peeredNetwork` in the pool configuration.
4. Grant network administration permissions to the host project management team.
5. Ensure the pool project and host project belong to the same organization per Cloud Build requirements.

Do not create the allocation in the service project and expect the host project to automatically see it. Allocations and private connections belong to the VPC project that owns the network.

### Connecting to On-Premises

If private resources reside in a data center, the VPC can connect to the on-premises network via Cloud VPN or Cloud Interconnect. For workers to reach them:

- The VPC must have routes to on-premises subnets via VPN/Interconnect.
- The private connection must export necessary custom routes to the service producer network.
- The on-premises side must have return routes to the private pool IP range.
- On-premises firewalls must allow the worker source range to target service ports.
- Internal DNS must be configured so workers resolve service names.
- Verify MTU, BGP routes, stateful firewalls, and return traffic paths.

If an organization has multiple peered VPCs, design explicit routing paths rather than assuming networks can transitively forward routes across one another. Use VPN or Interconnect where appropriate when bridging organization-managed networks.

## 11. Controlling Egress and Securing the Supply Chain

### PUBLIC_EGRESS and NO_PUBLIC_EGRESS

The `egressOption` field controls worker public IP/egress behavior:

| Value | Behavior | When to Use |
|---|---|---|
| PUBLIC_EGRESS | Workers have public IPs and can reach the public Internet | Builds need to fetch dependencies or images from public sources |
| NO_PUBLIC_EGRESS | Workers have no public IPs; cannot directly egress to public IPs unless via proxy | Builds require restricted public egress or sit inside a VPC Service Controls perimeter |

If `egressOption` is omitted from the pool config, public egress is enabled. `NO_PUBLIC_EGRESS` reduces data exfiltration paths to the Internet, but it does not replace firewalls, IAM, or build data controls. Prepare dependency mirrors, Artifact Registry, proxies, and Google API access paths to match your network design.

### VPC Service Controls

VPC Service Controls establishes security perimeters around supported Google Cloud services, helping restrict data access from outside the perimeter. Private pools can be configured inside a perimeter; Cloud Build documentation directs setting `egressOption` to `NO_PUBLIC_EGRESS` for this configuration.

VPC Service Controls adds a service-level control layer. It does not replace ingress/egress firewalls, IAM permissions, build service accounts, or database authentication. Verify ingress/egress policies, projects included in the perimeter, and APIs used by the pipeline.

### Static Egress IP

Public IPs attached to private pools when public egress is enabled are not static customer-controlled addresses. If an external service requires allowlisting a fixed source IP, you can deploy an organization-managed proxy/NAT gateway and route traffic through it. This approach requires designing routes, firewalls, external IP addresses, and proxies; do not assume a private pool automatically receives a fixed public IP.

### Securing Dependencies and Secrets

- Store critical base images and dependencies in Artifact Registry or internal mirrors.
- Use dedicated build service accounts granted only permissions to read artifacts, fetch secrets, and write necessary outputs.
- Access Secret Manager via appropriate IAM and APIs; never write secrets into logs or visible build arguments.
- Pin images by digest and verify builder provenance.
- Separate pools by trust level or environment when builds from different teams hold different access privileges.
- Use VPC Service Controls and egress policies to reduce exfiltration risk while logging and monitoring access.
- Prevent build scripts from running arbitrary commands against production data; review source code and triggers.

## 12. Layer-by-Layer Connectivity Verification

When a build cannot reach a private resource, check in this order:

1. **Pool:** Is the build actually running in the right private pool and region?
2. **Pool IAM:** Does the user or trigger service account have `roles/cloudbuild.workerPoolUser` on the pool project when needed?
3. **Peering:** Is the Private Services Access connection active?
4. **CIDR:** Is the worker range inside the allocation and free of overlaps with other subnets/routes?
5. **Routes:** Does the VPC have a route to the destination and a return route back to the workers?
6. **Firewalls:** Is the pool's source range permitted to the right port on the target resource?
7. **DNS:** Does the hostname resolve to the expected private IP?
8. **Runtime IAM:** Does the build service account have permission to access the resource?
9. **Egress:** Does the pool use `NO_PUBLIC_EGRESS` while the build attempts to download images or packages from the Internet?
10. **Transitive peering:** Is the destination behind another VPC peering link or a Google-managed service producer network?

### Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Pool creation reports network not peered with Service Networking API | Private connection not created or created in wrong VPC/project | Check Service Networking API, allocation, and VPC peering list |
| Build runs but times out connecting to private IP | Incorrect firewall, route, or CIDR | Verify source range, port, bidirectional routes, and VPC Flow Logs |
| Hostname does not resolve | Private zone not attached to right VPC or missing DNS peering | Verify Cloud DNS zone, suffix, and records |
| Can reach VM directly but cannot reach private GKE/Cloud SQL | Target service has its own service producer network; no transitive peering | Use VPN/Interconnect, PSC, or service-supported DNS endpoint architecture |
| Build fails to download public images/packages | Pool uses NO_PUBLIC_EGRESS | Use internal mirrors or an approved proxy/egress path |
| Build from another project cannot use pool | Missing roles/cloudbuild.workerPoolUser | Grant permission to requesting principal or trigger service account on the pool project |
| Network connection succeeds but API returns permission denied | Build service account lacks IAM | Grant role on target resource and verify the service account used by the build |
| Build stays queued then times out after network changes | Private connection deleted or peering inactive | Restore or recreate connection per procedure; never delete PSA while pools depend on it |
| Pool created but insufficient concurrent workers | Worker IP range too small | Increase range within allowed limits and recalculate usable IPs |

## 13. Hands-On Exercise: Testing a Private Database

Suppose the development team needs to run migration tests against a PostgreSQL instance with a private IP in a VPC. Minimum design:

1. Create a private pool in a region close to the database.
2. Connect the pool to the VPC via Private Services Access.
3. Reserve a worker range without overlapping subnets and routes.
4. Allow TCP 5432 ingress from the worker range to the database.
5. Create a private DNS record if using a hostname instead of an IP.
6. Grant Artifact Registry Reader to the build service account to pull test images.
7. Grant scoped secret access if the password is stored in Secret Manager.
8. Route the build to the private pool via `options.pool.name`.
9. Run `pg_isready` or a short-timeout connectivity check.
10. After confirming connectivity, run migration tests with a least-privilege database account.

Never put database passwords in `cloudbuild.yaml` or command-line arguments. Fetch secrets in build steps using Cloud Build-supported mechanisms and restrict access for the build service account.

## 14. Checklist Before Using a Private Pool in Production

- [ ] Identify exact private resources the build needs to access.
- [ ] Select the region and project owning the private pool.
- [ ] Enable Cloud Build API and Service Networking API in the proper projects.
- [ ] Reserve an allocation without overlapping VPC, on-premises, or existing ranges.
- [ ] Create the Private Services Access connection and verify its status.
- [ ] Configure `peeredNetwork` and worker IP range in the private pool.
- [ ] Select `PUBLIC_EGRESS` or `NO_PUBLIC_EGRESS` per dependencies and policy.
- [ ] Grant WorkerPool Owner to pool administrators.
- [ ] Grant WorkerPool User to principals submitting builds via CLI/API and to trigger service accounts when triggers reside in another project.
- [ ] Grant separate IAM roles to the build service account on target resources.
- [ ] Configure firewalls for only the needed source range and ports.
- [ ] Verify routes, return routes, and transitive peering constraints.
- [ ] Configure DNS peering if using private hostnames.
- [ ] Verify Shared VPC or hybrid connectivity if applicable.
- [ ] Plan dependency mirrors, image mirrors, and proxies if disabling public egress.
- [ ] Test builds and retain logs/VPC Flow Logs for investigation.
- [ ] Do not delete the private connection while pools still depend on it.

## 15. Conclusion

Cloud Build private pools bring build workers close to internal resources while preserving the Google-managed worker model. Private Services Access connects the service producer network to your VPC via VPC Network Peering; from there, routes, firewalls, DNS, and IAM determine which resources builds can reach.

Successful deployment requires coordinating four layers: network connectivity, name resolution, build service account permissions, and egress policy. In particular, account for the lack of transitive peering when accessing Google-managed services or other VPC networks. When these layers are configured and tested individually, private pools support secure pipelines to build, test, and deploy applications in GCP environments with private network resources.

## References

- [Private pools overview – Cloud Build](https://docs.cloud.google.com/build/docs/private-pools/private-pools-overview)
- [Set up private pools in a VPC network](https://docs.cloud.google.com/build/docs/private-pools/set-up-private-pool-to-use-in-vpc-network)
- [Create and manage private pools](https://docs.cloud.google.com/build/docs/private-pools/create-manage-private-pools)
- [Private pool configuration file schema](https://docs.cloud.google.com/build/docs/private-pools/private-pool-config-file-schema)
- [Run builds in a private pool](https://docs.cloud.google.com/build/docs/private-pools/run-builds-in-private-pool)
- [Using Cloud Build in a private network](https://docs.cloud.google.com/build/docs/private-pools/use-in-private-network)
- [Access private GKE clusters with Cloud Build private pools](https://docs.cloud.google.com/build/docs/private-pools/accessing-private-gke-clusters-with-cloud-build-private-pools)
- [Use VPC Service Controls with private pools](https://docs.cloud.google.com/build/docs/private-pools/using-vpc-service-controls)
- [Configure private services access](https://docs.cloud.google.com/vpc/docs/configure-private-services-access)
- [Cloud Build IAM roles and permissions](https://docs.cloud.google.com/build/docs/iam-roles-permissions)
- [Troubleshoot Cloud Build](https://docs.cloud.google.com/build/docs/troubleshooting)
