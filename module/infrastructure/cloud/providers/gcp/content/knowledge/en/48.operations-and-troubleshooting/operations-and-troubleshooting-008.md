# Handling GKE Node Pressure, Image Pull Errors, and IP Exhaustion

An application on Google Kubernetes Engine (GKE) can suddenly leave Pods in `Pending`, get evicted, fail to pull container images, or fail to receive IP addresses. These incidents often surface together during a deployment or traffic surge, yet their root causes live at separate layers: node resources, kubelet/container runtime, registry permissions, or network IP planning.

This runbook walks through distinguishing and resolving three problem classes:

- **Node pressure:** nodes run short on memory, disk/ephemeral storage, or PIDs; kubelet may reject new Pods or evict workloads.
- **Image pull failure:** Pods fail to pull images from Artifact Registry or external registries due to wrong name/tag/digest, permissions, networking, or image architecture.
- **IP exhaustion:** the cluster runs out of eligible addresses for nodes, Pods, or Services; Pods can stay `Pending` even when CPU and memory are still available.

The objective is to pinpoint the exact failing layer, protect workloads and data, recover in a controlled manner, and then add capacity or fix configurations so the failure does not recur.

## 1. Classify Symptoms Before Making Changes

Start by identifying the affected object and the first error message.

| Symptom | Observed Signal | Priority Cause Category |
|---|---|---|
| Pod `Pending` | Events `Insufficient memory`, `Insufficient cpu`, `Too many pods`, or IP allocation failure | Scheduling, node capacity, IP space |
| Pod evicted | Reason `Evicted`, node condition `MemoryPressure` or `DiskPressure` | Node pressure |
| Container fails to start | `ErrImagePull`, `ImagePullBackOff` | Image, registry, IAM, networking |
| Node `NotReady` | Node condition, kubelet, or runtime anomaly | Node/system pressure, network, control plane |
| Pod sandbox creation fails | Events involving CNI/IP allocation | Pod IP range, CNI, node |
| Service unreachable | Pods have IPs yet Service does not work | Endpoints, selector, NetworkPolicy, Service IP/routing |
| Node pool fails to scale | Autoscaler reports quota, subnet, or resource constraint | Node IP range, quota, capacity |

Do not start by immediately deleting Pods or bumping node counts. If the cause is a missing image or an exhausted subnet, adding nodes only wastes money without fixing the error.

### Determine Scope

- One Pod or all Pods in a namespace?
- One node or an entire node pool?
- A single zone or multiple zones?
- Only newly deployed workloads or running workloads as well?
- One registry/image or all images?
- Only Pod IPs, or also node IPs and Service IPs?

Record start time, latest deployment, IAM/network changes, autoscaling events, and related alerts.

## 2. Gather Initial Evidence

Select the right `kubeconfig` context and namespace before running commands:

~~~bash
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
~~~

Inspect cluster and node pool state:

~~~bash
gcloud container clusters list --project="PROJECT_ID"
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

If the cluster uses a regional control plane, `CLUSTER_LOCATION` is typically a region; if zonal, a zone. Use the exact location from your actual configuration.

Archive evidence before applying fixes:

- Pod name, namespace, node, and event messages.
- Node name, node pool, zone, and conditions.
- Cluster/node pool version and autoscaling configuration.
- UTC timestamp and change/release ID.
- Workload logs, kubelet/container runtime logs, and GKE events where available.
- CPU, memory, disk, IP allocation, and quota metrics.

Never paste tokens, private keys, image pull secrets, or Kubernetes Secret contents into tickets or logs.

## 3. Understanding Node Pressure Types

Kubernetes node conditions generally indicate these states:

| Condition | Meaning | Potential Impact |
|---|---|---|
| `MemoryPressure` | Node lacks available memory relative to eviction thresholds | Pods evicted, scheduling restricted |
| `DiskPressure` | Node lacks free disk space or inodes on relevant filesystems | Evictions, image/container creation failures |
| `PIDPressure` | Node is nearing its process ID limit | Cannot spawn new processes/containers |
| `Ready=False/Unknown` | Node is unhealthy or lost heartbeat | Pods fail to schedule normally; workloads impacted |

Node pressure does not mean CPU is always high. A node with low CPU can still run out of memory, ephemeral storage, or inodes.

### Reading Conditions and Resources

~~~bash
kubectl describe node "NODE_NAME"
kubectl top nodes
kubectl describe pods -n "NAMESPACE" "POD_NAME"
~~~

`kubectl top` requires Metrics Server or a matching metrics pipeline and reports near-real-time usage. It does not replace historical charts or filesystem/inode metrics.

In `describe node` output, check:

- Conditions.
- Capacity and Allocatable.
- Allocated resources.
- Non-terminated Pods.
- Taints and labels.
- Events at the bottom of the output.

## 4. Distinguishing Capacity, Allocatable, Requests, and Usage

Four frequently confused concepts:

- **Capacity:** total physical/virtual resources on the node.
- **Allocatable:** portion Kubernetes can schedule to workloads after system reservations.
- **Requests:** resources declared by Pods for scheduler placement.
- **Usage:** actual point-in-time consumption.

The scheduler relies primarily on `requests` and `allocatable` for placement—not just current CPU/memory usage.

Example:

| Memory Metric | Illustrative Value |
|---|---:|
| Node capacity | 16 GiB |
| Allocatable | 14 GiB |
| Total committed requests | 13 GiB |
| Current usage | 7 GiB |

A node can have low actual usage yet very little unrequested allocatable memory left. A new Pod requesting 2 GiB cannot schedule there if no other suitable node exists.

Conversely, setting `requests` too low lets too many Pods pack onto one node; when usage spikes, kubelet hits `MemoryPressure`.

### Inspecting Pod Requests/Limits

~~~bash
kubectl get pods -n "NAMESPACE" -o json
kubectl describe node "NODE_NAME"
~~~

Use `kubectl get pod` with YAML output to inspect a specific Pod's resources. Check main containers, sidecars, and init containers; total Pod requests can exceed what appears on the application container alone.

## 5. Handling `MemoryPressure`

### Signs

- Node condition `MemoryPressure=True`.
- Pods with reason `Evicted` or events citing memory thresholds.
- Containers `OOMKilled`.
- Rising memory working set, JVM heap/GC pressure, or growing caches.
- Nodes packed with Pods whose `requests` sit far below actual usage.

### Diagnostic Workflow

1. Identify the affected node and memory-heavy Pods.
2. Compare actual usage against `requests` and `limits`.
3. Inspect memory trends alongside deploy and traffic-spike timestamps.
4. Inspect JVM heap, native memory, direct buffers, thread counts, and sidecar memory.
5. Distinguish container `OOMKilled` from node-level eviction.
6. Check whether the autoscaler can add nodes and whether quotas suffice.

Inspection commands:

~~~bash
kubectl top pods -A --sort-by=memory
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl describe node "NODE_NAME"
~~~

### Recovery

- If a workload has a memory leak, roll back or deploy a tested fix.
- If `requests`/`limits` fail to reflect workload needs, tune them from empirical metrics and re-verify scheduling.
- If load growth is legitimate, scale the workload and node pool within capacity limits.
- If node pressure triggered evictions, confirm replicas recreated and the app recovered.
- Do not raise memory limits endlessly; doing so can simply shift the failure from the container to the node.

### Java/Spring Boot

For containerized JVMs, keep heap below the container memory limit and leave headroom for metaspace, thread stacks, direct buffers, native libraries, and agents. Never set `-Xmx` to 100% of container memory.

Monitor GC pauses, allocation rates, live heap, thread counts, and container memory. Too small a heap causes excessive GC; too large a heap risks container `OOMKilled` when native memory grows.

## 6. Handling `DiskPressure` and Ephemeral Storage

Kubernetes nodes hold several types of temporary data:

- Writable container layers.
- Container logs.
- `emptyDir` volumes.
- Image layers and image cache.
- Runtime/kubelet data.
- Application-written temporary files.

`DiskPressure` can result from low filesystem space or exhausted inodes. Checking free bytes while ignoring inodes can mislead your diagnosis.

### Signs

- Node condition `DiskPressure=True`.
- Pods evicted with ephemeral storage messages.
- Image pulls or image unpacking fail.
- Container runtime fails to create filesystems/layers.
- Log volume spikes or temporary files go uncleaned.

### Inspection

~~~bash
kubectl describe node "NODE_NAME"
kubectl get pods -A -o wide
kubectl describe pod -n "NAMESPACE" "POD_NAME"
~~~

On GKE, use Cloud Logging and enabled node/system metrics to inspect disk usage, filesystems, and container logs. Direct node access depends on GKE mode, node image, and organizational policy; do not assume you can SSH into every node.

### Remediation

- Curb log verbosity and configure proper log retention/rotation.
- Clean temporary files via application logic; never delete runtime directories manually.
- Set `ephemeral-storage` requests/limits on workloads that write temporary files.
- Move durable data to `PersistentVolume`s or appropriate storage services.
- Size node boot disks and node pools according to measured demand.
- Audit image sizes and prune old images using supported runtime mechanisms.

Never run recursive deletes inside container runtime or kubelet directories on a live node. Doing so corrupts container state and forces the node `NotReady`.

## 7. Handling `PIDPressure`

`PIDPressure` occurs when a node approaches its process ID limit. Common causes include:

- Applications spawning too many child processes.
- Process leaks or unreaped zombie processes.
- Sidecars/agents spawning excessive workers.
- Unbounded containers or uncontrolled application forking.
- One runaway workload consuming most node PIDs.

### Diagnosis

~~~bash
kubectl describe node "NODE_NAME"
kubectl top pods -A
kubectl get pods -A -o wide
~~~

Process/PID metrics may require node-level monitoring or dedicated logs. Never infer PID usage solely from CPU or memory.

### Remediation

- Identify the owning Pod/process and fix process lifecycle management.
- Bound concurrency and process pools inside the application.
- Audit sidecars, init containers, and agents.
- Isolate the offending workload if safe to do so.
- Adjust capacity or Pod density only when you understand node limits and GKE policies.

Adding nodes spreads workloads out, yet never cures a process leak; autoscaling can even replicate a buggy workload further.

## 8. Taints, Eviction, and `PodDisruptionBudget`

When a node experiences pressure, kubelet can apply taints such as `node.kubernetes.io/memory-pressure` or `node.kubernetes.io/disk-pressure`. The scheduler uses taints/tolerations to keep new Pods off unhealthy nodes.

When replacing nodes, understand:

- **`cordon`** marks a node unschedulable for new Pods.
- **`drain`** evicts Pods via Kubernetes eviction APIs, which can be blocked by a `PodDisruptionBudget` (PDB).
- DaemonSet Pods require explicit handling during drain.
- `emptyDir` data can be lost when Pods move.
- Stateful workloads require evaluating volume detach/attach and quorum.

Controlled operation example:

~~~bash
kubectl cordon "NODE_NAME"
kubectl get pdb -A
kubectl drain "NODE_NAME" --ignore-daemonsets
~~~

`drain` may wait or fail if a PDB blocks disruptions. Only pass options that delete `emptyDir` data when owners approve and data is reproducible. Before draining, check replicas, topology, replacement node capacity, and maintenance windows.

Do not manually delete VMs/nodes from a GKE-managed node pool to relieve pressure. Use supported node pool upgrade, repair, or resize mechanisms.

## 9. Distinguishing `OOMKilled`, `Evicted`, and `CrashLoopBackOff`

| Status / Reason | Meaning | First Step |
|---|---|---|
| `OOMKilled` | Container exceeded memory limit or was killed by kernel OOM | Check limits, heap, memory usage |
| `Evicted` | Kubelet removed Pod due to node pressure or eviction conditions | Inspect node conditions and eviction message |
| `CrashLoopBackOff` | Container starts and exits repeatedly | Inspect `--previous` logs, exit code, and startup config |
| `Pending` | Pod unscheduled or sandbox creation failed | Read events and scheduler/CNI messages |
| `ContainerCreating` | Runtime preparing container; may wait on image/volume/network | Inspect events, image pull, and volume attach |

Fetch logs from the previous container run:

~~~bash
kubectl logs -n "NAMESPACE" "POD_NAME" --previous
kubectl describe pod -n "NAMESPACE" "POD_NAME"
~~~

A Pod can transition through multiple states sequentially: `Pending` due to image pull, then `CrashLoopBackOff` due to bad config. Always rely on the latest events and timestamps, not only the `STATUS` column in `kubectl get pods`.

## 10. Diagnosing `ErrImagePull` and `ImagePullBackOff`

`ErrImagePull` indicates an image pull attempt failed. `ImagePullBackOff` indicates kubelet/runtime is backing off before retrying. These are recurring symptoms, not the root cause.

### Check the Image Reference

~~~bash
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl get pod -n "NAMESPACE" "POD_NAME" -o yaml
~~~

Verify:

- Is the registry hostname right?
- Are project, repository, and image path right?
- Does the tag or digest exist?
- Was the image built for the node architecture (e.g., `amd64`/`arm64`)?
- Was the repository renamed or deleted?
- Does the manifest reference the right image for the current environment?

Prefer pinning images by digest in production to guarantee repeatable deployments. Mutable tags like `latest` obscure exactly which image is pulled.

### Reading Error Messages

| Common Event / Message | Investigation Path |
|---|---|
| `manifest unknown` / `not found` | Wrong image path, tag, or digest |
| `unauthorized` / `denied` | IAM, registry credentials, or repository ACL |
| `no basic auth credentials` | Missing external registry authentication config |
| `i/o timeout` / DNS error | Egress, DNS, proxy, or registry endpoint |
| `x509 certificate error` | CA trust or TLS proxy |
| `no matching manifest` | Image lacks a matching platform/architecture |
| `toomanyrequests` / rate limit | Registry quota or pull rate limits |
| `no space left on device` | Node disk or image filesystem pressure |

Do not treat every error by creating a new `imagePullSecret`. With Artifact Registry on GKE, you should generally grant repository access to the node service account; external registries may require different mechanisms.

## 11. Artifact Registry: Image Pull Permissions on GKE

For private images in Artifact Registry, nodes need an identity with repository read permissions. In the standard GKE model, **kubelet/container runtime uses the node service account to pull images**. A Pod's Workload Identity is used by the application once the container runs; it does not replace node image pull permissions.

### Inspecting the Node Service Account

~~~bash
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID" \
  --format="yaml(nodeConfig.serviceAccount,nodePools)"
~~~

Output format may vary by cluster mode and node pool. Inspect individual node pools with:

~~~bash
gcloud container node-pools describe "NODE_POOL" \
  --cluster="CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

Verify the active node service account and IAM policy on the exact repository.

### Granting Least Privilege

Example granting Artifact Registry Reader at the repository level:

~~~bash
gcloud artifacts repositories add-iam-policy-binding "REPOSITORY" \
  --location="REPOSITORY_LOCATION" \
  --project="ARTIFACT_PROJECT_ID" \
  --member="serviceAccount:NODE_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/artifactregistry.reader"
~~~

Run this only after verifying the repository, node service account, and approval. If images live in another project, grant access on the project/repository hosting the images. Never grant Project Owner or Editor to resolve image pulls.

### Workload Identity vs. Node Identity

- Node identity: serves node-level operations such as image pulls per GKE configuration.
- Workload Identity: gives in-Pod applications an identity to call Google Cloud APIs.
- Kubernetes service account: in-cluster identity tied to RBAC.

Keeping these three identities distinct prevents granting permissions to the wrong principal.

## 12. External Registries, `imagePullSecrets`, and Networking

If images come from Docker Hub or another private registry, verify the authentication mechanism supported by that provider. Namespace-scoped Kubernetes `imagePullSecrets` can be used, provided secrets are protected and rotated.

Example referencing a securely created secret:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: registry-check
  namespace: app-lab
spec:
  imagePullSecrets:
    - name: external-registry-credentials
  containers:
    - name: check
      image: registry.example.invalid/team/app@sha256:REPLACE_WITH_DIGEST
~~~

This is an illustrative manifest; domain and digest are not real deployment values. Never commit secret contents to Git; use secret management and GitOps secret integrations appropriately.

### Network Checks

- DNS from nodes to the registry.
- Egress firewalls and Cloud NAT if nodes use private IPs.
- Proxy settings and TLS certificates.
- VPC Service Controls or organization policies where applicable.
- Registry rate limits and quotas.
- Private Google Access / Google API routing per network design.

If every Pod across a node pool fails pulls, check networking and node identity before editing individual Pods. If only one image fails, check path, tag, and repository permissions first.

## 13. Checking IP Exhaustion in VPC-Native GKE

VPC-native GKE uses alias IP ranges. Distinguish three address pools:

| IP Type | Usage Scope | Common Source |
|---|---|---|
| Node IP | VM/node addresses on the VPC | Primary subnet range |
| Pod IP | Addresses for Pods running on nodes | Secondary Pod range |
| Service ClusterIP | Internal addresses for Kubernetes Services | Secondary Service range or cluster-configured range |

A cluster can exhaust Pod IPs while the primary subnet still has node IPs left. Conversely, a cluster may fail to add nodes because the primary range or VM quota is exhausted even though Pod ranges still have room.

### Determining Factors

- Primary subnet range size.
- Secondary Pod range and Service range sizes.
- Projected maximum node count.
- Maximum Pods per node (`maxPodsPerNode`).
- How GKE allocates Pod CIDRs per node.
- Number of Services and consumed ClusterIPs.
- Whether the cluster uses VPC-native or another networking mode.

Never take a naive CIDR math calculation as exact capacity. GKE allocates per-node CIDR blocks based on configured Pod density; reserved addresses can exceed the number of currently running Pods.

## 14. Identifying Pod IP Exhaustion

Signs:

- Pods stay `Pending` with events reporting Pod sandbox creation failure or IP allocation failure.
- GKE cluster/network events report exhaustion in the Pod secondary range.
- Node pools scale up yet new Pods fail to start.
- CNI/Dataplane logs allocation errors.
- Pods per node or node pool hit configured ceilings.

Inspection:

~~~bash
kubectl get pods -A -o wide
kubectl get nodes -o wide
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl describe node "NODE_NAME"
~~~

Check the cluster's IP allocation config:

~~~bash
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID" \
  --format="yaml(ipAllocationPolicy,network,subnetwork,defaultMaxPodsConstraint)"
~~~

Check the subnet and secondary ranges:

~~~bash
gcloud compute networks subnets describe "SUBNET_NAME" \
  --region="REGION" \
  --project="PROJECT_ID" \
  --format="yaml(ipCidrRange,secondaryIpRanges,network)"
~~~

Match Pod secondary range and Service secondary range names against the cluster configuration. Do not confuse IP ranges belonging to another cluster sharing the same subnet.

### Pinpoint the Exact Exhausted Pool

- Pod range exhausted: cannot allocate Pod IPs for new nodes or workloads.
- Primary range exhausted: cannot provision new node VMs or resources using primary IPs.
- Service range exhausted: cannot allocate new ClusterIPs for Services.
- Per-node Pod allocation reached: one node cannot accept more Pods even when the subnet still has free space.
- Node/Pod quotas or autoscaler limits: capacity blocked by quotas/config, not IP exhaustion.

## 15. Remediating Insufficient Pod IP Ranges

Before changing anything:

1. Confirm the cluster is VPC-native and identify active Pod ranges.
2. Check for IP overlap with VPCs, peering, VPNs, on-premises networks, or other subnets.
3. Estimate node counts, max Pods/node, and growth headroom.
4. Verify GKE feature and cluster-mode support for expanding Pod ranges.
5. Plan the IaC/network change, maintenance window, and rollback.
6. Check related firewalls, routes, peering, and security appliances.

### Remediation Options

- **Expand the existing secondary range** if the subnet/range type and GKE conditions allow it, without overlapping other ranges.
- **Add an additional Pod secondary range** and configure the cluster/node pool to use it if supported by your GKE version/mode.
- **Provision a new cluster with redesigned CIDRs** when the existing cluster has constraints preventing safe expansion.
- **Adjust max Pods per node for new node pools** when current Pod density is higher than needed; understand the impact on CIDR allocation and scheduling.
- **Remove unneeded Pods** or clean up terminated resources, though never treat this as a substitute for capacity planning.

Expanding ranges and adding Pod ranges carry specific conditions by cluster type, version, and network topology. Consult current GKE documentation and verify CLI/API support before applying; never run a primary subnet expansion assuming it automatically expands secondary ranges.

### Overlap Warning

Never pick a CIDR simply because it looks unused. Audit every subnet, peering link, VPN, Interconnect, and on-premises network range. An overlapping Pod range creates hard-to-debug routing failures or breaks cross-network connectivity.

## 16. Remediating Node IP Exhaustion and Blocked Node Pool Scaling

When the autoscaler wants to add nodes yet fails, check:

- Does the primary subnet range have enough free addresses?
- Compute Engine quotas per region/zone.
- Node pool max size and cluster autoscaling limits.
- Physical availability for the machine type and zone.
- Reservation or Spot/Preemptible constraints if used.
- Network tags, service accounts, and node startup configuration.
- Organization policy restrictions.

Inspect node pools:

~~~bash
gcloud container node-pools list \
  --cluster="CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

Check events and autoscaler status via the GKE UI or Cloud Logging. Autoscaler messages often report specific causes such as insufficient resources, quotas, or IP address exhaustion.

### Recovery

- Expand the primary subnet range only after checking for overlaps and VPC limits.
- Request matching quotas if quota is the bottleneck.
- Adjust autoscaling min/max within approved capacity and budget.
- If a zone lacks capacity, evaluate alternative node pools, regions, or zones along with latency and HA impacts.
- Never force the autoscaler past limits or delete existing nodes to free IPs without knowing what workloads run on them.

## 17. Service IP Exhaustion and Differences from Pod IPs

Kubernetes `ClusterIP` Services allocate addresses from the Service range. If that range fills up, creating new Services fails even when Pod IPs remain available.

Signs:

- Creating a new Service fails with a ClusterIP allocation error.
- Pods run with valid IPs, yet new Service objects fail to provision properly.
- Service/ClusterIP count nears the range capacity.

Inspection:

~~~bash
kubectl get services -A
kubectl get services -A -o wide
kubectl describe service -n "NAMESPACE" "SERVICE_NAME"
~~~

Check the cluster's `ipAllocationPolicy` and Service range. Never delete active ClusterIPs or Services to free addresses without confirming dependencies and downtime impact.

Remediation often requires redesigning Service CIDRs or migrating to a new cluster when the current range cannot expand in place. Changing a Service CIDR carries major constraints; review GKE documentation and migration plans before proceeding.

## 18. Do Not Confuse IP Exhaustion with Service Routing Errors

A Pod having an IP does not guarantee its Service works. When clients cannot reach a Service, walk through the chain:

1. Pod is Ready and holds an IP.
2. Service selector matches Pod labels.
3. `EndpointSlice` lists the Pod endpoint.
4. `NetworkPolicy` allows the traffic.
5. CNI/dataplane and `kube-proxy`/eBPF mode are healthy.
6. DNS resolves the service name properly.
7. Firewalls, Load Balancers, and Ingress route properly.

Inspection commands:

~~~bash
kubectl get svc -n "NAMESPACE"
kubectl get endpointslices -n "NAMESPACE"
kubectl get networkpolicy -A
kubectl get pods -n "NAMESPACE" --show-labels
~~~

If `EndpointSlice` is empty, the issue is likely selector mismatch or Pod readiness, not IP exhaustion. If Pods have IPs yet remain unreachable, check routing and policies before expanding CIDRs.

## 19. GKE Observability and Alerting

An operational dashboard should include at minimum:

| Group | Signal | Purpose |
|---|---|---|
| Node | Memory/Disk/PID pressure, `Ready` status | Detect nodes losing scheduling/serving health |
| Scheduling | `Pending` Pods, unschedulable reasons | Identify resource or IP shortages |
| Storage | Ephemeral storage, filesystem, inodes | Detect `DiskPressure` early |
| Container | Image pull errors, restarts, `OOMKilled` | Classify startup vs. runtime faults |
| Network | Pod IP allocation, subnet ranges, Service counts | Detect address exhaustion |
| Autoscaling | Desired/current nodes, failed scale-ups | Separate quota, IP, and capacity blocks |
| App | p95/p99 latency, 5xx rate, request rate | Measure user impact |

Cloud Monitoring provides GKE and Compute Engine metrics and alerting per your observability setup. Metric names and granularity depend on collection mode, agents, and versions. Cloud Logging captures Kubernetes events, node/system logs, and autoscaler messages when corresponding logging is enabled.

### Alert Before Hitting Hard Limits

- Memory/disk pressure conditions appear.
- Ephemeral storage or inode usage spikes abnormally.
- Pods stay `Pending` longer than allowed.
- Image pull failure rates climb.
- Node pool scale-ups fail.
- Pod/Service IP range headroom drops below capacity-plan thresholds.
- Restart/`OOMKilled` counts exceed baseline.

Do not alert only after Pods are evicted; alert on trends and remaining headroom.

## 20. Coordinated Runbook When Multiple Failures Strike Together

For example, after a release, new Pods stay `Pending`, some old Pods get `OOMKilled`, and some containers report `ImagePullBackOff`.

Proceed in order:

1. **Preserve evidence:** capture Pod events, node conditions, deployment revisions, and autoscaler logs.
2. **Determine blast radius:** namespaces, node pools, zones, images, and services.
3. **Halt rollout if release-induced:** pause/roll back per release process; stop spawning failing Pods.
4. **Separate root causes:** node pressure, image/registry, and IP/networking.
5. **Protect workloads:** never drain nodes without replacement capacity and PDB checks; never delete disks or stateful Pods blindly.
6. **Fix root causes:** adjust resource requests, IAM/images, networking, or CIDRs.
7. **Recover cleanly:** canary one node pool or workload first.
8. **Verify SLOs:** Pod Ready counts, API latency/errors, queues, and database connections.
9. **Close the incident:** document timeline, root cause, impact, and action items.

### When to Roll Back?

Rollback fits when errors begin right after changing images, resource requests/limits, node selectors, tolerations, or manifests. If the root cause is pre-existing subnet exhaustion, rolling back an image will not free IP addresses. Avoid unrelated simultaneous edits that obscure root cause.

## 21. Preventing Node Pressure

- Set `requests`/`limits` from profiling and representative load tests.
- Monitor memory working sets, GC, disk, and inodes.
- Set `ephemeral-storage` requests/limits for file-generating workloads.
- Match node pools to workloads and isolate heavy/batch jobs where needed.
- Configure autoscaling min/max bounds with quota headroom.
- Avoid overcommitting Pods onto nodes relative to real capacity.
- Control log verbosity, retention, and container image sizes.
- Use PDBs, topology spread constraints, and proper readiness/liveness probes.
- Test capacity before major campaigns or batch runs.
- Maintain node image/Kubernetes upgrade procedures with post-upgrade monitoring.

### JVM Workloads

For Java/Spring Boot:

- Size heap from the container memory limit, not developer workstation RAM.
- Monitor GC pauses and native memory.
- Bound thread pools and request concurrency.
- Avoid unbounded in-memory buffers and temporary files.
- Enforce timeouts so requests do not hold threads and connections indefinitely.
- Run load tests whenever changing CPU/memory or concurrency.

## 22. Preventing Image Pull Failures

- Pin production images by digest.
- Use planned Artifact Registry repositories and regions.
- Grant `roles/artifactregistry.reader` to the exact node service account on the right repository.
- Keep node image-pull identity separate from workload runtime identity.
- Verify image architecture matches node pools.
- Manage image retention so actively deployed tags/digests are not deleted.
- For external registries, use securely managed `imagePullSecrets`.
- Verify DNS, NAT, proxies, TLS, and registry rate limits.
- Add pre-deploy checks confirming images exist and are pullable.
- Monitor image pull latency and errors during rollouts.

An immutable image digest enables exact rollbacks compared to tags that can be overwritten.

## 23. Capacity Planning for Pods, Nodes, and IPs

Capacity planning must model three layers together:

~~~text
Workload replicas
   |
   +-- Pod requests/limits and max Pods per node
           |
           +-- Node pool size and machine capacity
                   |
                   +-- Primary subnet range for nodes
                   +-- Secondary Pod range
                   +-- Service CIDR/range
~~~

### Estimation Table

Build a table per cluster:

| Parameter | Data to Collect |
|---|---|
| Current/max node count | Per node pool and autoscaler config |
| Max Pods per node | Actual cluster/node pool configuration |
| Pod secondary range | CIDR, total addresses, and allocated portion |
| Primary subnet | CIDR and node IP headroom |
| Service range | CIDR and consumed ClusterIPs |
| Pod requests | CPU/memory/ephemeral storage per workload |
| Quotas | Compute, IP/networking, and related limits |
| Growth forecast | Projected replica, cluster, and peak traffic growth |

Calculations should reserve headroom for rollout surges, autoscaling, node upgrades, and zone failures. Sizing solely for currently running Pods can exhaust IPs precisely when scaling or upgrading.

### Rollout Surge

Rolling Deployment updates temporarily spin up extra Pods beyond desired replicas. Capacity plans must account for `maxSurge`, PDBs, node pools, and Pod CIDR allocation; otherwise upgrades can stall even when steady-state fits comfortably.

## 24. Hands-On Practice: Resolving Three Errors in a Lab Cluster

Provision a dedicated lab cluster with non-production workloads, defined budgets, and cleanup rules. Practice sequentially—never intentionally exhaust production resources.

### Exercise A — Memory Pressure

1. Deploy a test workload with controlled `requests`/`limits`.
2. Watch `kubectl top pods` and node conditions.
3. Apply gradually increasing load within safe bounds.
4. Record `OOMKilled` or pressure events if triggered.
5. Tune resource sizing and re-run.
6. Verify Pods become Ready, nodes stay healthy, and SLOs hold.

Never intentionally starve a shared cluster node of all memory.

### Exercise B — `ImagePullBackOff`

1. Deploy a Pod referencing a non-existent tag in the lab registry.
2. Inspect events and identify `manifest unknown`.
3. Update the image to an existing digest.
4. If using private Artifact Registry, verify the node service account holds Reader on the repository.
5. Confirm the Pod pulls cleanly.
6. Revoke any temporary test permissions afterward.

### Exercise C — IP Allocation

1. Inspect the lab cluster's `ipAllocationPolicy`, subnet, and secondary ranges.
2. Calculate capacity from max Pods/node and node pool size.
3. Observe Pod events when sandbox creation fails on IP allocation.
4. Cross-check node scale-up and primary subnet capacity.
5. Draft a plan to add a Pod range or provision a new lab cluster with wider CIDRs per GKE support.
6. Never modify CIDRs on a live cluster without a migration and rollback plan.

### Exercise D — Write the Incident Report

Document:

- Symptoms and timestamps.
- First observed event/condition.
- Root cause.
- Remediation steps taken.
- Post-recovery evidence.
- Alerts or capacity changes to prevent recurrence.

## 25. Incident Response Checklist

### Node Pressure

- [ ] Identified Memory/Disk/PID pressure and affected nodes.
- [ ] Checked capacity, allocatable, requests, and usage.
- [ ] Inspected evicted/`OOMKilled` Pods and logs.
- [ ] Checked inodes and ephemeral storage for `DiskPressure`.
- [ ] Checked PDBs, replicas, and drain/replacement readiness.
- [ ] Restored SLOs and verified node stability.

### Image Pull

- [ ] Verified image path, tag/digest, and architecture.
- [ ] Read Pod events and classified registry, network, or auth failures.
- [ ] Verified node service account permissions for Artifact Registry.
- [ ] Checked `imagePullSecrets` for external registries.
- [ ] Checked DNS, egress, proxies, TLS, and rate limits.
- [ ] Tested deployment and verified Pod Ready status.

### IP Exhaustion

- [ ] Distinguished node IPs, Pod IPs, and Service IPs.
- [ ] Checked primary and secondary subnet ranges.
- [ ] Verified max Pods/node, node pools, and autoscaler state.
- [ ] Checked compute quotas and zonal capacity.
- [ ] Checked for CIDR overlaps across VPCs, peering, VPNs, and on-premises.
- [ ] Prepared a supported, approved expansion or migration plan.

### Incident Closure

- [ ] No abnormal `Pending` Pods or pressure conditions remain.
- [ ] Node pools and autoscalers operate normally.
- [ ] Image pulls succeed across required workloads.
- [ ] Service endpoints, networking, and API SLOs verified.
- [ ] Temporary secrets and test artifacts cleaned up.
- [ ] Root cause, timeline, owner, and preventive actions documented.

## 26. Official References

- [GKE node auto-repair and node health](https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-repair)
- [GKE VPC-native clusters and IP address management](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [GKE networking and Pod IP ranges](https://cloud.google.com/kubernetes-engine/docs/how-to/multi-pod-cidr)
- [Kubernetes node pressure and eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)
- [Kubernetes container images and image pull](https://kubernetes.io/docs/concepts/containers/images/)
- [Artifact Registry access control](https://cloud.google.com/artifact-registry/docs/access-control)
- [GKE troubleshooting](https://cloud.google.com/kubernetes-engine/docs/troubleshooting)

Metric names, CLI flags, and networking behaviors can vary by GKE mode, version, and cluster configuration. Before modifying production, cross-check current documentation against your cluster's live output.

**Conclusion:** Node pressure, image pull failures, and IP exhaustion can all prevent Pods from becoming ready, yet require three distinct diagnostic paths. By inspecting conditions and events first, separating node/workload identities and registry access, distinguishing node/Pod/Service IP ranges, and recovering under change control and SLOs, operations teams resolve GKE incidents faster while safeguarding data, workloads, and long-term scalability.
