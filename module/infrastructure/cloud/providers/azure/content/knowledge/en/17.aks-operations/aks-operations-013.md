# Diagnosing Pod, Node, DNS, and Connectivity Failures in AKS

An API running on **Azure Kubernetes Service (AKS)** returns HTTP 503 right after a new release. The development team says the image built cleanly; the networking team says the VNet is healthy; and the Kubernetes dashboard shows several Pods in `Running` state. The real fault may lie in a **readiness probe**, a **Service with zero ready endpoints**, **CoreDNS**, a **NetworkPolicy**, **resource-starved nodes**, the **Azure Load Balancer**, or an external dependency. Blindly restarting all Pods without identifying the failing layer may bring temporary relief while leaving the root cause intact.

This lesson provides an **evidence-based, layer-by-layer diagnostic workflow**: from Pods and containers, nodes/node pools, and DNS resolution to internal Kubernetes networking, Azure networking, and client access paths. Each step explains which commands to run, expected signals, how to classify the failure, and which changes to avoid in Production.

This lesson belongs to the **AKS Operations** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces the Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, while guiding deployment, monitoring, security, and cost control for application architectures. Troubleshooting AKS incidents therefore goes beyond `kubectl` and touches **Azure RBAC, node pools, VNets, Azure CNI, NSGs, routing, Storage, registries, and monitoring**.

> Examples here use illustrative names such as namespace `shop`, Service `catalog-api`, AKS cluster `aks-prod-example`, and a private VNet. Observation commands are primarily read-only. Commands that create debug Pods, mutate configs, restart workloads, or drain nodes are **explicitly marked** because they alter cluster state and carry operational impact. Exact features and output depend on your deployed AKS version, Kubernetes version, networking dataplane, and add-ons.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish failures across **container, Pod, scheduler, node, DNS, Service, networking, ingress, and dependency** layers.
2. Read `Pod phase`, `container state`, `Conditions`, Kubernetes Events, and exit codes without misinterpreting `Running`.
3. Diagnose `Pending`, `ImagePullBackOff`, `CrashLoopBackOff`, `OOMKilled`, `Evicted`, and `FailedMount`.
4. Analyze `NotReady`, `MemoryPressure`, `DiskPressure`, node taints, kubelet, and AKS node pool states.
5. Verify **CoreDNS, the `kube-dns` Service, search domains**, and external DNS including Azure Private DNS.
6. Trace traffic from client to **Ingress/LoadBalancer → Service → EndpointSlice → Pod**.
7. Distinguish **Kubernetes NetworkPolicy** blocks from **Azure NSG, UDR, firewall, private endpoint, and outbound/SNAT** issues.
8. Use Azure CLI, `kubectl`, connectivity probes, and Azure Monitor/Log Analytics in a controlled manner.
9. Author an incident runbook covering evidence collection, mitigation, verification, and rollback.
10. Identify when to escalate to Platform, Networking, Identity, or Application teams.

## 2. Mental Model: Diagnosing from Symptom to Root-Cause Layer

A single request traverses many components:

```text
Client / user
        |
        v
Public or private DNS
        |
        v
Public or internal Load Balancer / Ingress / Gateway
        |
        v
Kubernetes Service (ClusterIP / NodePort / LB)
        |
        v
EndpointSlice: ready Pod IPs
        |
        v
Pod IP + container port
        |
        v
Application process
        |
        +--> CoreDNS --> Other internal Services
        |
        +--> VNet / firewall / DNS --> DB, Storage, Key Vault
        |
       Node / kubelet / container runtime / CNI
```

An "application unreachable" symptom can originate at any link. Ask questions in order:

- **Is the app running?** Did the Pod/container start without crashing, and is it passing readiness?
- **Does the Service point to the right Pods?** Do selectors, `targetPort`, EndpointSlices, and Ready states align?
- **Does DNS resolve the right address?** Which name (internal or external) is queried from where?
- **Does networking allow packets through?** Check Kubernetes policies, Azure routes, NSGs/firewalls, and private endpoints.
- **Is the public entrypoint healthy?** Check Ingress, TLS, load balancer health probes, hostnames, and backend routing.
- **Are dependencies healthy?** DB, registry, Key Vault, Storage, external APIs?
- **Did the outage follow a specific change?** Deployment, image, node pool upgrade, DNS, routes, policies, or secret rotation?

**Core principle:** isolate faults via **observed evidence**—never label something a "DNS bug" just because a log mentions `lookup`, and never assume a "healthy node" just because the Azure VM reports `Running`.

## 3. Preparing an Investigation: Scope, Timing, and Permissions

Before running commands, record:

| Field | Example |
|---|---|
| Subscription / tenant | Production subscription, company tenant |
| AKS cluster / resource group | `aks-prod-example` / `rg-platform-prod` |
| Namespace / workload | `shop` / Deployment `catalog-api` |
| Service / ingress | `catalog-api` / `shop.example.com` |
| Incident start time | 2026-11-20 08:10 UTC |
| Blast radius | All users, or a single zone/replica? |
| Expected behavior | HTTP 200 within target latency |
| Observed behavior | HTTP 503, timeout, NXDOMAIN, `Pending`... |
| Most recent change | Image rollout, DNS edit, node pool upgrade |
| Owners / incident ID | App team, Platform, Networking |

### Ensure You Are Targeting the Right Cluster

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

kubectl config current-context
kubectl cluster-info
kubectl get namespaces
```

**Common hazard:** `kubectl` pointing to a different cluster than the one you are viewing in the Azure Portal. Verify context before running any mutating command.

On an authorized cluster, an admin may use `az aks get-credentials` to fetch credentials, but note that **modifies your local kubeconfig**. Never switch your context onto a Production session without verifying the target cluster, permissions, and approved login flow.

### Use Least-Privilege Permissions

`get`, `describe`, and `logs` can require distinct RBAC permissions. Check first:

```bash
kubectl auth can-i get pods -n shop
kubectl auth can-i get pods/log -n shop
kubectl auth can-i get events -n shop
kubectl auth can-i create pods -n shop
```

Do not request `cluster-admin` merely to read logs. Commands like `describe` can print environment variables or sensitive config if an app hardcodes values; **redact secrets** before sharing output.

## 4. Quick Diagnostic Toolkit: The First Ten Minutes

Start with read-only data:

```bash
kubectl get nodes -o wide

kubectl get pods -A -o wide

kubectl -n shop get deploy,replicaset,pod,svc,ingress

kubectl -n shop get events \
  --sort-by=.metadata.creationTimestamp
```

Next, inspect the specific Pod:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop logs <POD_NAME> \
  --all-containers=true --since=30m --timestamps=true

kubectl -n shop logs <POD_NAME> \
  -c <CONTAINER_NAME> --previous --timestamps=true
```

`--previous` only works when logs from the **immediately preceding container instance** exist and have not rotated away. If no previous logs appear, that does not prove the Pod never restarted earlier in the cluster's history.

Finally, inspect the Service and endpoints:

```bash
kubectl -n shop get svc catalog-api -o wide

kubectl -n shop describe svc catalog-api

kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=catalog-api \
  -o wide
```

If a Service has a `ClusterIP` yet **no EndpointSlice with ready endpoints**, the bug is usually in selectors, Pod readiness, or backend declarations—**not proof of broken DNS**.

### Preliminary Decision Tree

```text
Application returning errors / timeouts?
       |
       +-- No Ready Pods
       |      |
       |      +-- Pending → scheduler / requests / taints / PVC / quota
       |      +-- ImagePull... → registry / auth / DNS / network
       |      +-- CrashLoop... → process / config / secret / probes
       |      +-- Node NotReady → kubelet / CNI / pressure / infrastructure
       |
       +-- Ready Pods exist
              |
              +-- Pod IP unreachable → app port / policy / CNI
              |
              +-- Pod IP works, Service fails
              |      → selector / EndpointSlice / port / dataplane
              |
              +-- Service IP works, DNS name fails
              |      → DNS client / CoreDNS / search domains
              |
              +-- Internal works, external fails
                     → ingress / LB / external DNS / NSG / TLS / routes
```

This tree is a starting point; a Ready Pod can still return HTTP 500 due to business bugs, and multiple failures can overlap.

## 5. Reading Pod Phase, Container State, and Pod Conditions

Do not equate every status printed by `kubectl get pods` with `Pod phase`.

| Signal | Actual Meaning |
|---|---|
| **Pending** | Kubernetes accepted the Pod, yet cannot schedule it or has not finished preparing containers. |
| **Running** | Pod is bound to a node and at least one container was created/started/running per Pod phase semantics; **does not mean the app is Ready**. |
| **Succeeded** | Main containers exited cleanly, common for Jobs. |
| **Failed** | Pod terminated with failure per Kubernetes semantics. |
| **Unknown** | Control plane lost Pod state due to communication issues or similar. |
| **`CrashLoopBackOff`** | Container waiting to restart with exponential backoff after repeated exits; a **waiting reason**, not a standalone Pod phase. |
| **`ImagePullBackOff`** | Container waiting to retry pulling an image after failures; not a Pod phase. |

**Pod Conditions** (`PodScheduled`, `Initialized`, `ContainersReady`, `Ready`) supply finer detail.

Example:

```bash
kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{.status.phase}{"\n"}'

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}{" "}{.reason}{"\n"}{end}'
```

If `phase=Running` yet `Ready=False`, Services normally **exclude that Pod from ready traffic endpoints**. Inspect readiness probes, startup behavior, dependencies, and Pod Conditions before touching the Azure Load Balancer.

## 6. Pending Pods: Scheduler Cannot Find a Node

Common causes:

| Event Message | Failure Layer | What to Check |
|---|---|---|
| `Insufficient cpu` / `Insufficient memory` | Requests exceed available node allocatable resources. | Resource requests, node allocatable, autoscaler. |
| `untolerated taint` | Pod lacks a matching toleration. | Node taints, Pod tolerations. |
| `node affinity/selector mismatch` | No node matches placement rules. | `nodeSelector`, affinity, node labels. |
| `Too many pods` | Hit node maxPods cap or IP allocation cap. | Node `maxPods`, CNI/IP capacity. |
| `unbound immediate PersistentVolumeClaims` | PVC/PV or StorageClass not ready. | `kubectl get pvc,pv,storageclass`. |
| `TopologySpreadConstraints` or zone shortage | Spread rules unsatisfiable. | Labels, topology, per-zone capacity. |
| Cannot provision new nodes | Cluster Autoscaler, quota, SKU capacity, or node pool limits. | AKS node pools, Azure quotas, autoscaler events. |

Commands:

```bash
kubectl -n shop describe pod <PENDING_POD>

kubectl -n shop get pvc

kubectl get nodes \
  -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints,UNSCHEDULABLE:.spec.unschedulable

kubectl describe node <NODE_NAME>
```

### Requests Differ from Limits

- **Requests** tell the scheduler how much declared capacity a Pod needs on a node.
- **Limits** cap container runtime resource usage per Kubernetes/runtime mechanisms.
- A Pod with overly high requests stays `Pending` even when actual node CPU usage is low.
- A Pod with overly low memory limits can get `OOMKilled` even when the node has plenty of free RAM.

**Never blindly slash requests or raise limits** just to force a Pod onto a node; verify real workload demand and memory-contention risks at scale.

## 7. `ImagePullBackOff`, `ErrImagePull`, and Container Creation Errors

Image pull errors fall into common categories:

1. Wrong registry name, repository, tag, or image digest.
2. Image missing or tag deleted from the registry.
3. Node lacks pull rights to **Azure Container Registry (ACR)** or external registry.
4. Missing, wrong, or expired `imagePullSecrets` when using credential-based pulls.
5. DNS failure to registry or blocked outbound networking.
6. Network throttling, registry rate limits, or transient registry outage.
7. Image CPU architecture or OS mismatch on container startup.

Inspection commands:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get deploy catalog-api \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'

az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "{Name:name,Identity:identity,Network:networkProfile}" \
  --output json
```

For AKS pulling from ACR, inspect the **kubelet/node image-pull identity** and registry permissions. Never confuse the app's Pod workload identity with the kubelet's image-pull identity. Required roles/policies vary by ACR permission mode (classic RBAC vs ABAC repository permissions).

**Classifying Event messages:**

- `manifest unknown`: tag or digest does not exist.
- `unauthorized` / `denied`: inspect identity, credentials, and registry permissions.
- `no such host` / timeout: inspect DNS, egress, and registry endpoints.
- `exec format error` after pull succeeds: check image platform/architecture and binary compatibility.

Never "fix" a pull error by enabling public registry access or granting broad Owner rights when the issue is simply a mistyped tag.

## 8. `CrashLoopBackOff`: Process Repeatedly Exiting

**`CrashLoopBackOff`** means Kubernetes is delaying restarts of a container that keeps terminating. Always look at **exit reason, exit code, logs, and Events**.

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop logs <POD_NAME> \
  -c <CONTAINER_NAME> --previous --tail=200 --timestamps

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restarts="}{.restartCount}{" lastReason="}{.lastState.terminated.reason}{" lastExit="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

| Symptom | Possible Cause |
|---|---|
| Non-zero exit code | App exception, bad config, unavailable dependency, startup error. |
| `OOMKilled` / typically exit code 137 | Exceeded memory limit or killed by runtime; verify exact termination reason. |
| `Error: missing environment variable` | Missing ConfigMap/Secret or mismatched env var name. |
| `connection refused` to DB | DB/Service not up yet, wrong host/port, readiness race. |
| TLS handshake / permission error | Invalid cert/CA, identity, RBAC, or rotated secret. |
| Probe failures triggering restart | Overly aggressive liveness/startup probe or hung endpoint. |

**Never assume exit code 137 always means Kubernetes memory-limit OOM.** Confirm using `OOMKilled` in container status, node memory pressure, and runtime logs.

### Remediation Workflow

1. Confirm exact image and `command`/`args`.
2. Read **`--previous`** logs.
3. Inspect container last termination reason and Pod Events.
4. Correlate with rollout, ConfigMap, or Secret changes.
5. Verify dependency health and DNS/network paths.
6. Fix the root cause, roll out cleanly, and watch restarts and readiness.
7. Keep a rollback ready if a new version introduced the regression.

Restarting a Pod when the fault is a bad config value or broken secret only starts a **fresh crash loop**.

## 9. Probes: Readiness, Liveness, and Startup

Kubernetes provides three probes with distinct roles:

| Probe | Question Answered | On Failure |
|---|---|---|
| **Readiness** | Is the container ready to receive traffic? | Pod marked NotReady; excluded from normal Service traffic endpoints. |
| **Liveness** | Is the container wedged and needing a restart? | Kubelet restarts the container after exceeding `failureThreshold`. |
| **Startup** | Has the application finished booting? | Defers liveness/readiness checks during startup; restarts if `failureThreshold` is exceeded. |

Excerpt manifest:

```yaml
containers:
  - name: catalog-api
    image: example.azurecr.io/catalog-api:1.2.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /startup
        port: 8080
      periodSeconds: 5
      failureThreshold: 24
    readinessProbe:
      httpGet:
        path: /ready
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8080
      periodSeconds: 20
      timeoutSeconds: 2
      failureThreshold: 3
```

This is illustrative only. Paths must genuinely be exposed by the application, and thresholds must match real startup times, load, and service requirements.

**Common mistake:** tying liveness probes to an external database. When the DB blips, kubelet restarts healthy Pods in a storm, worsening the outage. Separate **process liveness** from **traffic readiness**.

If readiness fails while liveness passes, Pods stay `Running` without receiving Service traffic—explaining why `Running` Pods can coincide with Ingress 503s.

## 10. `OOMKilled`, CPU Throttling, and Eviction

### Memory OOM

When a container exceeds its memory limit, the runtime terminates it and records `OOMKilled`. Inspect:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" "}{.lastState.terminated.reason}{"\n"}{end}'

kubectl -n shop top pod <POD_NAME> --containers
```

`kubectl top` requires a working Metrics API / metrics-server; missing metrics never mean zero memory usage.

Next steps:

- Compare limits/requests against peak memory consumption.
- Check for memory leaks, caches, buffers, and batch sizes.
- Inspect node `MemoryPressure` and eviction history.
- Tune workload or resources from measurements, then benchmark.
- With HPA, verify scaling replicas actually lowers per-instance memory pressure.

### Disk / Ephemeral Storage Pressure

Pods can be **`Evicted`** when nodes run low on resources—especially **ephemeral storage**, memory, or other pressure signals. Large logs, image layers, caches, and writable-layer files can fill node disks.

```bash
kubectl describe node <NODE_NAME>

kubectl -n shop describe pod <POD_NAME>
```

Check Conditions (`DiskPressure`, `MemoryPressure`, `PIDPressure`) and Events. Never manually delete logs or system files on nodes without a runbook: you risk destroying forensic evidence or breaking kubelet/runtime state.

### CPU Throttling

An overly tight CPU limit can throttle the app, spiking p95 latency or timing out probes while the Pod stays `Running`. Confirm using **container CPU throttling metrics** from observability tooling rather than VM-level CPU averages.

## 11. Node `NotReady`: Isolating Kubelet vs Infrastructure Failures

When a node becomes `NotReady` or `Unknown`, Pods on that node may stop serving; Kubernetes controllers and the scheduler react per cluster policies.

Start here:

```bash
kubectl get nodes -o wide

kubectl describe node <NODE_NAME>

kubectl get pods -A \
  --field-selector spec.nodeName=<NODE_NAME> -o wide
```

In `describe node`, inspect:

- **Conditions:** `Ready`, `MemoryPressure`, `DiskPressure`, `PIDPressure`, `NetworkUnavailable` if present.
- **Capacity/Allocatable:** resources available for Pods.
- **Taints:** `node.kubernetes.io/not-ready`, `unreachable`, or operator taints.
- **Events:** kubelet registration errors, network unavailable, container runtime/evictions.
- **Allocated resources:** total requests/limits on the node.

### Common Causes

| Symptom | Likely Cause |
|---|---|
| Lost node heartbeat | Kubelet, VM/host infra, or network path to control plane. |
| `NetworkUnavailable` or CNI unready | Network plugin/dataplane, Pod IP allocation, or routes. |
| `DiskPressure` | OS or ephemeral disk running out of space. |
| `MemoryPressure` | Memory contention, evictions, runaway apps. |
| `PIDPressure` | Process/thread exhaustion. |
| Temporary unavailability during upgrade | Node image upgrade, cordon/drain, or planned rolling update. |
| New node fails to join | Networking, provisioning, bootstrap, identity, quota, or capacity. |

**`NotReady` does not mean the VM is powered off.** A VM may remain running in Azure while kubelet or its path to the API Server is broken.

## 12. AKS Node Pools: Autoscaler, Quotas, Images, and Availability

AKS manages node pools over Azure compute infrastructure. `Pending` Pods or `NotReady` nodes can stem from **VM family, quotas, regional capacity, autoscaler bounds, or node upgrades**.

Read-only Azure CLI commands:

```bash
az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "{Name:name,Provisioning:provisioningState,Network:networkProfile}" \
  --output json

az aks nodepool list \
  --resource-group "<RESOURCE_GROUP>" \
  --cluster-name "<AKS_CLUSTER>" \
  --output table

az aks nodepool show \
  --resource-group "<RESOURCE_GROUP>" \
  --cluster-name "<AKS_CLUSTER>" \
  --name "<POOL_NAME>" \
  --output json
```

### When Autoscaler Cannot Add Nodes

Check:

1. Is autoscaling enabled on the pool, and is current count below `maxCount`?
2. Does the subscription have enough **regional vCPU** and **VM family** quota?
3. Does the region/zone have live capacity for that VM size?
4. Are node labels, taints, affinities, or topology spread rules too restrictive?
5. Do the VNet/subnet and CNI mode have free IPs/network capacity?
6. Are Azure Policies or identity permissions blocking provisioning?
7. Is a node pool upgrade/maintenance reducing available nodes?

**Available quota does not guarantee live Azure capacity at VM creation time.** If a pool is already at `maxCount`, the autoscaler cannot fix Pending Pods—revisit scaling bounds and workload sizing.

### Cordon, Drain, and Upgrade Are Mutating Operations

Commands like `kubectl cordon`, `kubectl drain`, `az aks nodepool upgrade`, and node image upgrades **are not read-only diagnostic commands**. They relocate and disrupt Pods. In Production AKS, follow AKS upgrade/repair runbooks and check PodDisruptionBudgets, replica spread, and zones beforehand.

## 13. PodDisruptionBudget, DaemonSet, and Node Incidents

Before maintaining or replacing a troubled node, distinguish:

- **Deployment/ReplicaSet:** normally recreates Pods elsewhere if capacity and constraints allow.
- **StatefulSet:** carries persistent state, ordinals, and ordering/volume constraints.
- **DaemonSet:** typically schedules one Pod per eligible node (e.g., logging/network agents).
- **PodDisruptionBudget (PDB):** limits **voluntary evictions**; does not stop crashes or sudden node failures.
- **Static/critical system Pods:** follow special lifecycle rules—never delete arbitrarily.

Inspect:

```bash
kubectl get pdb -A

kubectl -n shop get deploy,statefulset,daemonset

kubectl -n shop get pods \
  -o wide
```

An overly strict PDB or too few replicas can stall `drain`. If a node pool runs only one node hosting a critical workload, draining causes an outage regardless of PDBs. Design **multiple replicas, node/zone spread, readiness probes, and spare capacity** upfront.

Never lower a PDB to 0 just to speed up a drain without explicit approval of the availability impact.

## 14. DNS in AKS: Where Do Queries Go?

In Kubernetes, Pods typically resolve Service names via cluster DNS—provided by **CoreDNS** in standard AKS setups. A Pod may query:

- `catalog-api`: short name within the same namespace when search domains apply.
- `catalog-api.shop.svc.cluster.local`: full FQDN for the default cluster domain.
- `api.partner.example`: external name forwarded by CoreDNS to upstream resolvers.

Conceptual flow:

```text
Pod: shop/frontend
      |
      | nslookup catalog-api.shop.svc.cluster.local
      v
/etc/resolv.conf
      |
      v
Cluster DNS Service (typically named kube-dns)
      |
      v
CoreDNS replicas
      |
      +-- Kubernetes service record
      |      └── Matching ClusterIP / records
      |
      +-- External zone
             └── Forward upstream / Azure DNS / corporate DNS
```

**Do not confuse:**

- **Azure DNS / Azure Private DNS**: manages Azure domains and private zones.
- **CoreDNS**: handles in-cluster Kubernetes name resolution.
- **Kubelet/node DNS config**: shapes upstream resolver paths and can affect Pods.
- **Service and EndpointSlices**: govern backend network routing once a name resolves.

For headless Services or special DNS modes, DNS may return Pod IPs instead of a ClusterIP. Never apply one assumption to all Service types.

## 15. Inspecting CoreDNS and the DNS Service

Start read-only:

```bash
kubectl -n kube-system get svc kube-dns -o wide

kubectl -n kube-system get deployments

kubectl -n kube-system get pods -o wide

kubectl -n kube-system get events \
  --sort-by=.metadata.creationTimestamp
```

Standard AKS clusters run CoreDNS deployments and a `kube-dns` Service, yet **exact resource names, labels, and node-local DNS options can vary** by version/configuration. Read live output instead of hardcoding fixed selectors.

Inspect a Pod's DNS config:

```bash
kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{.spec.dnsPolicy}{"\n"}'

kubectl -n shop exec <POD_NAME> -- cat /etc/resolv.conf
```

`exec` requires a running container containing `cat`; distroless images lack shells/binaries even when DNS and the app work fine. Avoid `kubectl exec` where RBAC or policy prohibits it.

### What Matters in `/etc/resolv.conf`?

Example:

```text
nameserver 10.0.0.10
search shop.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

`10.0.0.10` is an **example**, not a fixed AKS DNS IP across all clusters. Check:

- `nameserver`: IP of the DNS Service (or node-local DNS cache if configured).
- `search`: suffixes appended to short names per namespace and cluster domain.
- `ndots`: controls when queries try search domains first—can multiply DNS queries for external hostnames.
- `dnsPolicy` / `dnsConfig`: overrides default Pod resolver settings.

Editing the CoreDNS ConfigMap or Pod DNS policies globally **is never step one**. First confirm whether the issue affects one Pod or the entire cluster.

## 16. Testing Internal and External DNS from the Right Source

Testing DNS from your laptop does not prove Pod DNS works. Test from **the affected Pod or a debug Pod in the same namespace/node/policy scope**.

If the container has `nslookup`:

```bash
kubectl -n shop exec <POD_NAME> -- \
  nslookup kubernetes.default.svc.cluster.local

kubectl -n shop exec <POD_NAME> -- \
  nslookup catalog-api.shop.svc.cluster.local

kubectl -n shop exec <POD_NAME> -- \
  nslookup example.com
```

Interpretation:

| Test | Result | Isolation |
|---|---|---|
| `kubernetes.default.svc.cluster.local` fails | Cannot resolve basic cluster Services. | Pod DNS, `kube-dns`/CoreDNS, network path to DNS. |
| Base Kubernetes Service works, `catalog-api` fails | Wrong name/namespace, missing Service, or CoreDNS cache/config. | Verify Service and FQDN. |
| Internal FQDN works, external domain fails | Forwarding/upstream DNS, egress, or DNS policy. | CoreDNS upstream and Azure/corporate DNS. |
| DNS returns right IP yet TCP times out | DNS is likely fine; inspect routes/policies/backend ports. | Shift to Service/network testing. |
| Private endpoint name returns public IP or NXDOMAIN | Misconfigured Private DNS, zone link, or forwarder. | Azure Private DNS, custom resolvers, VNet links. |

**`NXDOMAIN`** suggests the queried resolver has no such record; **`SERVFAIL`** indicates resolver/upstream failure; **timeout** points to blocked DNS traffic, overloaded resolvers, or unreachable upstreams. Treat these as clues, not sole proof.

### When Containers Lack DNS Tools

A separate debug Pod helps, though **creating a Pod mutates cluster state**. Run only when authorized:

```bash
kubectl -n shop run dns-check \
  --image=busybox:1.36 \
  --restart=Never \
  --command -- sleep 1800
```

Once Running:

```bash
kubectl -n shop exec dns-check -- \
  nslookup catalog-api.shop.svc.cluster.local

kubectl -n shop exec dns-check -- \
  nslookup example.com
```

Delete the lab Pod per approved runbook when done; never litter Production with debug Pods. Debug images must come from trusted, pullable registries. Remember that a debug Pod with **different labels, ServiceAccount, or node** may hit different NetworkPolicies than the app Pod.

## 17. CoreDNS Is Healthy Yet Specific Names Still Fail

Causes outside the CoreDNS Deployment itself:

1. Service has not been created, or wrong name/namespace.
2. Pod uses `dnsPolicy: Default` instead of a policy supporting cluster Service DNS.
3. FQDN uses a custom cluster domain other than `cluster.local`.
4. CoreDNS forwards a custom zone to a DNS server unaware of that zone.
5. Application or client library caches stale DNS records.
6. Too few CoreDNS replicas, CPU throttling, or overload under spikes.
7. NetworkPolicy egress blocks UDP/TCP port 53 from Pods to DNS.
8. NodeLocal DNSCache or an optional DNS plugin misbehaving.
9. VNet custom DNS fails to forward required zones.
10. DNS Service IP or service CIDR mismatched with network config.

Check CoreDNS logs if permitted:

```bash
kubectl -n kube-system logs deployment/coredns \
  --since=30m --all-containers=true
```

If your AKS setup uses a different deployment name or layout, list `kubectl -n kube-system get deployments,pods` first.

**Never carelessly enable CoreDNS query logging in Production**: it generates huge log volumes, adds latency/cost, and exposes internal hostnames. Time-box, approve, and secure logs if ever needed.

## 18. Azure Private DNS, VNet DNS, and Private Endpoints

An AKS app reaching Azure SQL, Storage, Key Vault, or ACR over private endpoints requires both **private routing** and **proper DNS**.

Example:

```text
AKS Pod
  |
  v
CoreDNS
  |
  v
Configured upstream DNS
  |
  v
Matching Private DNS zone / resolver
  |
  v
db-prod.database.windows.net
  --> Private Endpoint IP in VNet
  |
  v
TCP to private IP, routing, firewall, authentication
```

Exact zone names depend on the Azure service, private link setup, and DNS architecture. **Never hand-create static A records arbitrarily**, as that breaks resolution if private endpoint IPs change.

### Checklist

- Is the Private Endpoint `Approved`/`Connected`?
- Does the AKS VNet have a **DNS resolution path** to the target Private DNS zone?
- Does the Private DNS zone have the right VNet link or custom forwarder?
- If using on-prem DNS, is there a conditional forwarder to Azure DNS Private Resolver or compatible infrastructure?
- Does the Pod resolve the endpoint to the expected private IP?
- Do NSGs, UDRs, and Azure Firewalls allow traffic to that private IP and destination port?
- Are app identities and credentials still valid?

**Accurate Private DNS resolution does not guarantee TCP/HTTPS succeeds.** Conversely, raw TCP connectivity to an IP does not prove TLS passes with the right hostname/certificate.

## 19. Service, Selector, EndpointSlice, and `targetPort`

When Pods are Ready yet the API is unreachable via its Service, trace the mapping.

Suppose the Deployment Pod specifies:

```yaml
metadata:
  labels:
    app: catalog-api
spec:
  containers:
    - name: catalog-api
      image: example.azurecr.io/catalog-api:1.2.0
      ports:
        - containerPort: 8080
```

And the Service specifies:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
```

Check step by step:

1. Service has `selector.app=catalog-api`.
2. Pods in the same namespace carry matching labels.
3. Pods are **Ready** so they become active endpoints.
4. Clients call Service port **80**.
5. The dataplane forwards to Pod IP on **`targetPort` 8080**.
6. The app **listens** on port 8080 on an interface reachable via Pod IP (not just `127.0.0.1`).

### Inspection Commands

```bash
kubectl -n shop get svc catalog-api -o yaml

kubectl -n shop get pods -l app=catalog-api -o wide

kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=catalog-api \
  -o yaml
```

YAML output can be long; redact sensitive data or annotations before sharing.

If the Service has **0 endpoints**, check:

- Do selectors match existing Pods?
- Are Pods `Ready=False`?
- Is the Service declared **selectorless** with externally managed EndpointSlices? (special case)
- Are Pods in a different namespace? Service selectors only match Pods in the Service's own namespace.
- Is the EndpointSlice controller or control plane unhealthy?

If endpoints exist yet connections fail, check **exact ports, app listener binding, NetworkPolicies, and dataplane**. Do not touch DNS before checking selectors and readiness.

## 20. Distinguishing Pod IP, ClusterIP, and Service DNS

Each target tests a different layer:

| Test Target | What It Tests | Limitation |
|---|---|---|
| **Pod IP:port** | Direct network path to the Pod and app listener. | Pod IPs change on recreation; usually unreachable from outside the cluster. |
| **Service ClusterIP:port** | Service routing/load balancing through the Kubernetes dataplane. | Skips DNS when calling raw IP. |
| **Service FQDN:port** | Adds DNS resolution ahead of Service routing. | Subject to DNS caching and Pod DNS policies. |
| **Ingress/LB hostname** | Full public/private entrypoint chain, TLS, and backend. | Adds multiple extra layers; test last after verifying internals. |

Sensible progression from an authorized debug Pod:

```text
1. http://<POD_IP>:8080/health
2. http://<SERVICE_CLUSTER_IP>:80/health
3. http://catalog-api.shop.svc.cluster.local/health
4. https://shop.example.com/health
```

Interpretation:

- **1 fails:** inspect app listener, Pod, NetworkPolicies, CNI.
- **1 works, 2 fails:** Service mapping, dataplane, or policy.
- **2 works, 3 fails:** DNS resolution/path from client Pod.
- **3 works, 4 fails:** ingress, LB, external DNS, TLS, or routing.
- **All 4 work yet users fail:** request path/headers/auth, client network, DNS cache, or uneven load.

This sequence assumes a **valid network path** from your test source to each IP. Testing a `Pod IP` or `ClusterIP` from a laptop outside the cluster will fail normally depending on networking mode.

## 21. CNI and IP Addressing: Pod Networking in AKS

AKS supports multiple networking models, such as **Azure CNI Overlay** and **Azure CNI Pod Subnet** on supported versions/configs; older clusters may use other modes. Do not guess the CNI mode solely from a Pod IP.

Key components:

- **Node IP:** VM address in the Azure VNet.
- **Pod IP:** assigned by the cluster networking model; scope/routing depends on the network plugin.
- **Service CIDR:** virtual address range for Kubernetes Services, not an Azure VM subnet.
- **DNS Service IP:** sits inside the Service CIDR per cluster config.
- **VNet/subnet CIDR:** address space for VMs, private endpoints, or Pod Subnets per design.
- **Kube-proxy or alternative dataplane:** handles Kubernetes Service routing per cluster mode; AKS supports different dataplanes.

Inspect the network profile:

```bash
az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "networkProfile" \
  --output json
```

Check `networkPlugin`, `networkPluginMode`, `networkDataplane`, `serviceCidr`, `dnsServiceIP`, and whatever fields the API returns. Do not assume identical field presence across all versions.

### IP Exhaustion and Overlapping CIDRs

Node pools can fail to scale or Pods can fail to get IPs due to:

- Exhausted subnet addresses under the active allocation model.
- `maxPods`/node limits combined with insufficient node count planning.
- Overlapping Pod CIDR, Service CIDR, or VNet/on-prem ranges.
- CNI/IPAM/agent allocation failures.
- Routes or NATs failing to match the topology.

**Trying to fix IP exhaustion by adding more nodes** often backfires when the node/Pod subnet itself is out of IPs. Audit AKS IP addressing against live subnet capacity.

## 22. NetworkPolicy, NSG, Routes, and Firewalls: Four Distinct Layers

| Layer | Scope | What to Inspect |
|---|---|---|
| **Kubernetes NetworkPolicy** | Filters Pod ingress/egress enforced by the network policy engine. | Namespaces, labels, policy selectors, ports/protocols, DNS egress. |
| **Azure NSG** | Filters Azure subnet/NIC traffic per network plugin and traffic path. | Source/destination CIDRs, service tags, ports, effective rules. |
| **User-defined routes (UDRs)** | Controls next hops within VNets/subnets. | Routes to Azure Firewall/NVA, symmetric return paths. |
| **Azure Firewall / NVA** | Enforces centralized ingress/egress network/app rules. | Application/network rules, FQDNs, SNAT, firewall logs. |

**Blocking at any one layer** breaks connectivity. Conversely, opening an Azure NSG will not bypass a Kubernetes NetworkPolicy. Under Azure CNI/Cilium or different dataplanes, enforcement paths differ—never assume every cluster uses classic iptables/kube-proxy identically.

### Inspecting NetworkPolicies

```bash
kubectl get networkpolicy -A

kubectl -n shop describe networkpolicy <POLICY_NAME>

kubectl -n shop get pod <POD_NAME> \
  --show-labels
```

When a policy selects a Pod and defaults egress to deny, the Pod cannot reach CoreDNS unless DNS egress is explicitly allowed. Check **both UDP and TCP port 53** where used by queries/responses, noting the real DNS target may be the DNS Service IP or a node-local cache depending on setup.

### Separating DNS Issues from Policy Blocks

- `nslookup` times out and Pod has a NetworkPolicy: check DNS egress rules.
- `nslookup` returns the right IP yet `curl` times out: check egress to destination port, NSGs, UDRs, and firewalls.
- One namespace fails while another works: compare NetworkPolicies, Pod labels, ServiceAccounts, DNS policies, and node placement.
- Only one node fails: inspect node-level CNI/dataplane, routes, and network agents.

**Never "fix" issues by deleting all NetworkPolicies.** Policy changes require approval, lab validation, and both ingress/egress verification.

## 23. Egress and SNAT: Intermittent Outbound Failures

A classic AKS incident is **random outbound request timeouts** as concurrent connections climb. Beyond DNS and endpoint health, check **SNAT port allocation/exhaustion** along the outbound path.

Possible path:

```text
Pod → Node/CNI → AKS egress configuration
                 |
                 +-- Load Balancer outbound rules / NAT Gateway
                 +-- Azure Firewall / NVA
                 +-- UserDefinedRouting / egress gateway
                 |
                 v
           External API / database
```

Not every AKS cluster uses the same outbound mechanism; inspect `networkProfile.outboundType` and actual routing.

### Signals of SNAT / Connection Exhaustion

- New connections time out while existing established connections keep working.
- Errors spike alongside surges in outbound connection count.
- An external endpoint fails when many replicas open short-lived connections simultaneously.
- Azure Monitor / Load Balancer / NAT Gateway / Firewall metrics show port/connection saturation where supported.
- Error rates drop once connection reuse/keep-alive improves.

Never conclude SNAT exhaustion from a single `ETIMEDOUT` log line. Also check external API latency, firewall rules, DNS caching, connection pools, and service quotas.

### Mitigations

1. Reuse HTTP/TCP connections via keep-alive and connection pooling.
2. Check DNS caching/TTL and retry/backoff tuning.
3. Size egress capacity (NAT Gateway / Firewall) to load and supported features.
4. Cap unbounded outbound concurrency per client.
5. Use private endpoints or private service-to-service networking where feasible.
6. Monitor outbound metrics and run controlled load tests.

## 24. Ingress, Azure Load Balancer, and External Client Errors

If internal Services work while external users hit errors, inspect:

1. Is the client querying the **right DNS record** pointing to the public/internal entrypoint?
2. Is the Ingress Controller / Application Gateway / gateway matching the right host/path?
3. Are TLS certificates, SNI, hostnames, and HTTP/HTTPS redirects valid?
4. Do the Kubernetes Service type and backend mapping match?
5. Does the external Load Balancer have valid frontend IPs, rules, and health probes?
6. Do NSGs, firewalls, routes, and public/private access policies allow the client source?
7. Are Ready endpoints present in the target namespace and port?
8. Is the failure isolated to a single ingress replica or availability zone?

Observation commands:

```bash
kubectl get ingress -A

kubectl get svc -A -o wide

kubectl -n shop describe ingress <INGRESS_NAME>

kubectl -n shop describe svc <EXTERNAL_SERVICE_NAME>
```

**Having an Ingress resource does not guarantee an Ingress Controller is running.** AKS may use NGINX, AGIC, Application Gateway for Containers, or another controller depending on deployment. Logs, health probes, and layer mapping depend on the exact controller—never apply a generic NGINX runbook blindly to every topology.

### Do 502, 503, and 504 Always Mean the Same Thing?

No. Different ingress controllers, gateways, and proxies emit these codes with distinct semantics. Typical conventions:

- **502:** gateway received an invalid response from upstream.
- **503:** upstream unavailable or zero ready backends.
- **504:** gateway timed out waiting on upstream.

However, an application itself can **also return these status codes**. Inspect response headers, ingress logs, request IDs, and application logs to see which hop generated the code.

## 25. Distinguishing TCP, HTTP, and TLS Failures

A connection passes through distinct stages:

```text
DNS lookup → TCP connect → TLS handshake → HTTP request
                                     |
                                     v
                               HTTP response
```

| Error | Likely Meaning | What to Check |
|---|---|---|
| `no such host` / `NXDOMAIN` | DNS name failed to resolve. | Resolver, hostname, zone/forwarders. |
| TCP timeout | No connection reply within timeout. | Routes, policies, firewalls, down server, SNAT. |
| `connection refused` | Target responded with no listener, or policy actively rejected at that layer. | Port, app process, Service mapping. |
| TLS certificate verify failed | Invalid CA, hostname, expiry, or cert chain. | Certificate, SANs, SNI, trust store. |
| HTTP 401/403 | Authentication/authorization failure in app, proxy, or target service. | Tokens, roles, access policies; network is reachable. |
| HTTP 404 | Route/path/host mismatch or missing object. | Ingress rules, app path, deployed version. |
| HTTP 5xx | Application or upstream/gateway failure. | Logs by request ID, dependencies, probes. |

Sample probe from an authorized network location with `curl`:

```bash
curl -sv --connect-timeout 5 \
  http://catalog-api.shop.svc.cluster.local/health

curl -sv --connect-timeout 5 \
  https://shop.example.com/health
```

`curl -v` prints request/response headers including tokens or cookies if supplied; **never leave credentials in shared logs**. Never use `curl -k` to ignore TLS verification as a Production workaround; if ever used briefly to isolate certificate issues, clearly note the server remained unverified.

## 26. When Do You Need a Debug Pod or Ephemeral Container?

Many minimal application images (distroless) omit shells, `curl`, and `nslookup`. You have three options:

1. Use built-in application diagnostics/logging if policy permits.
2. Launch a temporary **debug Pod** in the same namespace to test DNS/networking.
3. Attach an **ephemeral debug container** to the live Pod where Kubernetes version, RBAC, and policy allow.

### Risks of Debug Pods

- Creating a Pod mutates cluster state and requires RBAC.
- Unvetted debug images may violate security policy or carry risky tools.
- A debug Pod may differ in labels, node, and ServiceAccount, experiencing different NetworkPolicies/identities.
- Ephemeral containers may require elevated privileges and touch the Pod's runtime namespaces; require approval.
- Forgotten debug Pods waste resources or retain sensitive data.

**Rule:** use organization-approved images, keep them short-lived, and never mount Production secrets unless strictly necessary. When CNI/node-level debugging is required, coordinate with the Platform team rather than running privileged host-networked containers to bypass policy.

## 27. Azure Monitor, Container Insights, and System Logs

AKS observability sources:

| Source | What It Observes |
|---|---|
| `kubectl get/describe/events` | Near-real-time Kubernetes state, scheduling, probes, and node conditions. |
| `kubectl logs` | Container stdout/stderr per runtime mechanics and retention. |
| **Azure Monitor Container insights** | Pod/node inventory, performance, and container logs when configured with active agents. |
| **Azure Monitor managed Prometheus** | Kubernetes/Prometheus metrics per scrape configs and supported setup. |
| **Log Analytics** | Historical log queries by workspace, table, and configured retention. |
| **Azure Activity Log** | Azure control-plane operations on AKS resources, node pools, and networking. |
| **Network Watcher / flow logs / diagnostics** | Azure-layer network telemetry where features and configs support it. |
| **Application Insights / OpenTelemetry** | Request traces, dependencies, and exceptions when apps are instrumented. |

**You do not automatically get all of these sources** simply by creating an AKS cluster. Verify add-ons, Data Collection Rules, workspaces, agents/extensions, retention, RBAC, and telemetry costs.

### Diagnostic Logs Need Correlation

Strong application logs include:

- UTC timestamp, service/version, namespace, Pod/replica identifier.
- Trace ID or request ID.
- HTTP route/status/latency.
- Failing dependency name and sanitized error code.
- Startup, initialization, and secret-refresh events.

Never log passwords, tokens, storage account keys, Kubernetes ServiceAccount tokens, or unnecessary PII.

## 28. Log Analytics and KQL: Finding Errors by Pod or Time

When AKS sends container logs to Log Analytics, **`ContainerLogV2`** is a common table in modern configurations. Table and column names can vary by agent version, DCR, and workload logging schema.

Example searching error logs in namespace `shop` over the past two hours:

```kusto
ContainerLogV2
| where TimeGenerated > ago(2h)
| where PodNamespace == "shop"
| where tostring(LogMessage) has_any ("error", "exception", "failed")
| project TimeGenerated, PodNamespace, PodName,
          ContainerName, LogMessage
| order by TimeGenerated desc
```

Query Pod inventory if collected by your workspace:

```kusto
KubePodInventory
| where TimeGenerated > ago(2h)
| where Namespace == "shop"
| summarize LastSeen=max(TimeGenerated) by Name, PodStatus
| order by LastSeen desc
```

**These queries follow a reference schema** and do not guarantee every workspace has those exact tables or columns. Open **Tables** in Log Analytics to verify the live schema before concluding "zero errors."

### Combining Logs and Metrics

Suppose HTTP 503s spike at 08:15 UTC:

1. Identify when the Deployment revision rolled out.
2. Check `Ready replicas` and endpoint counts at that timestamp.
3. Query container errors between 08:10–08:20.
4. Cross-check Node `NotReady`, CoreDNS, and autoscaler events.
5. If the app calls a DB, inspect traces by request ID and dependency latency.
6. Inspect Azure LB/NSG/Firewall if internal Services are healthy while external clients fail.

Never assume every `timeout` log means an Azure network failure; timeouts also happen when apps block on locks, exhaust connection pools, or hit slow database queries.

## 29. Observability Costs and Preserving Incident Evidence

Logging and monitoring carry real costs:

- Log Analytics ingestion and retention.
- Managed Prometheus metrics and storage.
- Container insights agents and performance collection.
- Trace sampling and Application Insights ingestion.
- Network flow logs, Storage, exports, and retention.
- Engineering time and lab reproduction environments.

Never disable error logs completely just to cut costs. Instead:

1. Trim unnecessary debug logs in Production.
2. Use structured logging and time-boxed elevated log levels during incidents.
3. Align retention with risk and compliance requirements.
4. Apply sensible sampling for traces/metrics while preserving critical errors.
5. Enforce budgets/alerts, tags, and clear workspace ownership.
6. Avoid logging full HTTP bodies, credentials, or sensitive payloads.
7. Build dashboards and runbooks to cut Mean Time to Recovery (MTTR).

## 30. Safe Remediation Rules: Never Destroy Evidence

Premature changes can wipe vital forensic clues. Before restarting, rolling back, or editing networking:

- Capture Events, Pod statuses, and logs permitted for retention under policy.
- Record image name/digest, Deployment revision, and rollout timestamp.
- Verify ConfigMap/Secret *references* without copying secret values.
- Cross-check Service selectors and EndpointSlices.
- Test the smallest possible scoped change.
- Verify rollback paths and PodDisruptionBudgets.
- Obtain approval for Production changes.
- Define metrics/alerts that will prove the incident is resolved.

The following commands **mutate cluster state**—run only when authorized and covered by a runbook:

```bash
# Example app-impacting action; DO NOT run as a default diagnostic step:
kubectl -n shop rollout restart deployment/catalog-api

# Example rollback; verify target revision and any data/schema impact:
kubectl -n shop rollout undo deployment/catalog-api
```

Deployment rollback **does not automatically roll back** database schemas, persistent volume files, Storage data, or Azure network changes. Separate migration or compensation steps may be required.

### Post-Fix Verification Checklist

1. New Pods are created, scheduled, and Ready.
2. Services list the expected Ready endpoints.
3. Requests succeed along Pod IP → Service IP → Service DNS → Ingress from valid test sources.
4. 5xx errors, timeouts, restarts, and OOMs return to baseline.
5. Zero new errors appear in nodes, CNI, or CoreDNS.
6. Success rates and latency meet SLOs.
7. Temporary firewall rules, debug Pods, and elevated permissions are revoked.
8. Post-incident lessons and preventive guardrails are committed to IaC/GitOps.

## 31. Five-Phase Incident Runbook

### Phase 1 – Intake and Scoping

1. Log incident ID, UTC timestamp, and user impact.
2. Scope whether it affects **one app**, **one namespace**, **one node**, **one zone**, or **the entire cluster**.
3. Check recent changes: rollouts, secret rotations, DNS, VNets/NSGs, AKS upgrades, autoscaling.
4. Do not delete Pods/nodes or alter DNS without evidence.

### Phase 2 – Inspect Pods and Services

1. `kubectl get pods -o wide`, `describe pod`, and events.
2. Inspect exit reasons and readiness/liveness/startup probes.
3. Read current and `--previous` logs.
4. Verify Service selectors, `port`/`targetPort`, and EndpointSlices.
5. If Pods are unready, focus on app/scheduling first.

### Phase 3 – Inspect Nodes and Cluster

1. `kubectl get nodes`, `describe node`.
2. Node pool state, autoscaler, quotas, capacity, IP allocation.
3. System Pods, network agents, CoreDNS, and Kubernetes control-plane reachability.
4. If failures affect only one node, compare it against a healthy node in the same pool.

### Phase 4 – Inspect DNS, Network, and Dependencies

1. Test internal and external DNS from the exact Pod/source scope.
2. Probe Pod IP, Service IP, and Service FQDN within reachable scopes.
3. Check NetworkPolicies, CNI, NSGs, UDRs, and Firewalls.
4. If only ingress fails, inspect the controller, LB, TLS, and external DNS.
5. If external APIs time out under load, inspect SNAT, connection pools, and capacity.

### Phase 5 – Remediate, Verify, and Learn

1. Choose the smallest reversible change.
2. Measure Ready endpoints, success rate, p95 latency, and error counts.
3. Validate with real business transactions.
4. Clean up debug resources/temporary access and archive evidence.
5. Update runbooks, alerts, and change-review gates.

## 32. Scenario A: Pods `Running` Yet Ingress Returns 503

**Context:** `catalog-api:v2` deployed cleanly; Ingress returns 503. `kubectl get pods` shows 3 Pods `Running`, yet `READY` is `0/1`.

**Investigation:**

1. `kubectl -n shop describe pod`: readiness probe `/ready` returns 404.
2. `kubectl -n shop get svc catalog-api`: port 80, `targetPort` 8080.
3. `kubectl -n shop get endpointslice -l kubernetes.io/service-name=catalog-api`: zero Ready backends.
4. App logs show v2 renamed the health endpoint from `/ready` to `/health/ready`, yet the Deployment probe was not updated.

**Root cause:** readiness probe path mismatch prevented Pods from becoming healthy Service endpoints. The issue is neither DNS nor the public LB.

**Remediation:** update the probe path in the Deployment/IaC to the real route, deploy safely, confirm Pod Ready and EndpointSlice population, then verify via Ingress.

**Takeaway:** `Running` is never enough to prove traffic readiness. Always verify **Pod Conditions + EndpointSlices + live request results**.

## 33. Scenario B: Pods `Pending` After Scaling Replicas Up

**Context:** Deployment scaled from 6 to 18 replicas. Six new Pods stay `Pending`, and Cluster Autoscaler adds no nodes.

**Investigation:**

1. Events show `Insufficient cpu` and `Too many pods`.
2. The node pool is already near `maxCount`.
3. Several nodes hit Pod IP/slot caps under the networking model.
4. Azure quotas and node pool policies are checked for headroom.

**Resolution path:**

- Verify real capacity and Pod requests/limits.
- Adjust autoscaler/node pool bounds with approval if quotas, capacity, and IPs permit.
- Review subnet/Pod IP planning and `maxPods`.
- Right-size requests from measured load rather than shrinking arbitrarily.
- Review cluster distribution and cost before scaling out.

**Takeaway:** not every `Pending` Pod is a scheduler bug; **CPU, pods/node, subnet IPs, quotas, and node pool `maxCount`** can intersect.

## 34. Scenario C: Internal DNS Works, Key Vault Private Endpoint Fails

**Context:** Pods resolve `kubernetes.default.svc.cluster.local` and internal Services, yet cannot fetch secrets from a Key Vault private endpoint.

**Investigation:**

1. From an authorized source, resolve the Key Vault hostname from inside a Pod.
2. It returns an unexpected IP instead of the Private Endpoint IP.
3. Internal CoreDNS is healthy; an upstream DNS / Private DNS zone VNet link was recently altered.
4. After pinpointing the resolution path, Platform checks DNS forwarders, Private DNS zone VNet links, and A records.
5. Once resolved properly, also verify TCP 443, Key Vault firewall, workload identity, and Key Vault RBAC.

**Takeaway:** healthy CoreDNS does not prove **external/private DNS zones** are wired properly; resolving the right IP does not prove **HTTPS and authorization** succeed either.

## 35. Scenario D: Only Some Pods Time Out Reaching an External API

**Context:** an AKS app calls a payment API. Requests succeed during quiet hours; peak hours trigger timeouts on new connections.

**Investigation:**

1. External API DNS resolves cleanly, and error onset does not match any image deploy.
2. Timeouts climb alongside Pod count and outbound connections.
3. Measure retry rates, connection pools, external API latency, and egress metrics.
4. Check `outboundType`, NAT/LB/Firewall metrics, and signs of SNAT port pressure.
5. Compare source/destination connection counts to rule out upstream API rate limiting.

**Remediation:** enable HTTP keep-alive, bound connection pools, add jittered backoff, and right-size egress NAT capacity per supported architecture—never add infinite retries, which worsen connection storms.

**Takeaway:** load-correlated intermittent timeouts are not automatically "flaky CoreDNS"; measure **connections, SNAT, dependencies, and application concurrency**.

## 36. Hands-On Exercise: Layer-by-Layer AKS Incident Triage

**Lab environment:** AKS cluster `aks-lab`, namespace `shop`, Deployment `catalog-api`, Service `catalog-api`, and Ingress `shop.example.com`. Your team holds read-only cluster access unless authorized to launch a debug Pod in the lab namespace.

### Assigned Scenario

- Deployment has 3 replicas: two Pods Ready, one Pod with rising `RestartCount`.
- Service `catalog-api` maps port 80 → `targetPort` 8080.
- Some users hit HTTP 502/503 during rollout.
- A dependency requires reaching a private hostname in Azure Private DNS.
- Logs show both startup errors and occasional DNS timeouts.

### Tasks

1. Record tenant, subscription, cluster context, and UTC incident window.
2. Fetch Pod status via `kubectl get pods -o wide`.
3. Pick the Pod with the highest restarts, inspect `describe`, and read `logs --previous`.
4. Inspect readiness/liveness/startup probes in the Deployment.
5. Inspect Service selector/`targetPort` against Pod labels and listening port.
6. List EndpointSlices and count truly Ready endpoints.
7. Check whether the node hosting the failing Pod is `NotReady` or under pressure.
8. Check the cluster DNS Service and CoreDNS health.
9. Test internal DNS, then the dependency's private hostname from an eligible Pod or debug Pod.
10. If DNS returns the right IP yet TCP still times out, name three network layers to check next.
11. Distinguish a 502 generated by ingress vs a 500 returned by the app.
12. Propose the smallest change, verification plan, and rollback steps.
13. Build an evidence table for escalation to Platform/Networking.
14. Draft two alerts: one for Pod restarts/OOM, one for HTTP 5xx/readiness.
15. Describe how to clean up debug Pods and revoke temporary permissions post-incident.

### Expected Evidence Matrix

| Layer | Command or Data | Question to Answer |
|---|---|---|
| Cluster | `az account show`, `kubectl config current-context` | Are we inspecting the right cluster? |
| Pod | `get pods`, `describe pod`, `logs --previous` | Is the container crashing, OOMKilled, or failing probes? |
| Node | `describe node`, node pool state | Is the node under pressure, `NotReady`, or hitting scheduling limits? |
| Service | `get svc`, `get endpointslice` | Does the Service have Ready backends on the right port? |
| DNS | Internal/private `nslookup` | Which query fails, and what IP does the resolver return? |
| Network | NetworkPolicy, CNI, NSG, UDR, Firewall | Which layer could be dropping traffic? |
| Ingress | Controller logs, LB health, request IDs | Which component emitted the status code? |
| Observability | Container logs, metrics, traces | Do we have correlated evidence within the UTC window? |

### Reference Solution Guide

1. **Restarting Pod:** check `--previous` logs and last termination reason first. If the liveness probe kills the process due to slow startup, adjust probes based on measured boot time.
2. **EndpointSlices missing one Pod:** when the third Pod is NotReady, Services normally route only to Ready Pods. That alone is not a CoreDNS bug.
3. **Two Ready Pods still returning 5xx:** inspect proxy/gateway upstream status, app logs, and dependencies.
4. **Private DNS name failing:** if internal Service DNS works, focus on upstream/Private DNS zone resolution and network access rather than restarting CoreDNS.
5. **Node pressure:** if Pods on one node repeatedly OOM or get Evicted, check requests/limits and node conditions rather than blindly adding replicas.
6. **Closure:** roll out the approved fix, verify Ready endpoints, HTTP success rate, latency, restart rate, and external dependencies. Document the incident to improve alerts and IaC.

### Acceptance Criteria

- Evidence clearly separates **symptom, root cause, and contributing factors**.
- Does not use mass Pod deletions/restarts as a default diagnostic step.
- Verified **Pod → Service → DNS → Ingress** from appropriate network sources.
- Clearly separated **Kubernetes vs Azure networking** boundaries.
- Proposed minimal fix with a verified rollback path.
- Included post-fix verification and recurrence-prevention actions.

## 37. Knowledge Self-Check

**Question 1.** A Pod shows `Running` yet `Ready=False`. Can you assume it receives normal Service traffic?

**Answer:** No. `Running` does not guarantee app readiness; readiness controls whether a Pod joins active Service traffic endpoints.

**Question 2.** Is `CrashLoopBackOff` a Pod phase or a signal that a container is waiting to restart?

**Answer:** It is a container waiting reason / backoff state after repeated failures, not a standalone Pod phase.

**Question 3.** Will a `Pending` Pod with `Insufficient cpu` definitely be fixed by raising its memory limit?

**Answer:** No. The scheduler evaluates CPU requests against allocatable capacity. Inspect requests, node capacity, and autoscaler instead of changing unrelated memory limits.

**Question 4.** Does `ImagePullBackOff` always mean Azure Container Registry is down?

**Answer:** No. Causes include wrong image/tag, missing pull permissions, expired credentials, DNS failures, egress blocks, or registry unavailability.

**Question 5.** Why is `kubectl logs --previous` valuable during `CrashLoopBackOff`?

**Answer:** The current container attempt may not have started or logged yet; previous instance logs show the exception or exit cause.

**Question 6.** Does a failing readiness probe automatically make kubelet restart the container?

**Answer:** No. It marks the Pod NotReady; liveness/startup probes trigger restarts when `failureThreshold` is exceeded.

**Question 7.** A node is `NotReady` while its Azure VM is `Running`. Is that a contradiction?

**Answer:** No. The VM can be up while kubelet, CNI, container runtime, or connectivity to the control plane is broken.

**Question 8.** A Service has a ClusterIP yet zero Ready endpoints. Is DNS definitely broken?

**Answer:** No. Inspect selectors, Pod labels, readiness, EndpointSlices, and ports first.

**Question 9.** A Pod resolves `kubernetes.default.svc.cluster.local` cleanly yet fails `example.com`. Which layer should you investigate?

**Answer:** CoreDNS forwarding/upstream DNS, DNS policies, node DNS, and egress to resolvers—do not assume all cluster DNS is broken.

**Question 10.** Does resolving a Key Vault private endpoint to its right private IP prove the app has permission to read secrets?

**Answer:** No. You still need TCP/TLS reachability, vault firewall rules, and Key Vault/Entra RBAC permissions.

**Question 11.** Does an allow NetworkPolicy override an Azure NSG Deny?

**Answer:** No. Kubernetes policies, NSGs, UDRs, and firewalls are independent layers; traffic must pass every enforced layer along the path.

**Question 12.** Pods on one specific node cannot reach a Service while other nodes succeed. What could cause that?

**Answer:** Node-level CNI/dataplane, NetworkPolicy, routes, node network agents, Pod IP allocation, or backend Pod health; compare against a healthy node.

**Question 13.** `kubectl top` returns no metrics. Can you conclude the Pod uses zero CPU/RAM?

**Answer:** No. The Metrics API or agent may be missing or unhealthy; check another telemetry source.

**Question 14.** Why does curling a ClusterIP from your laptop time out even when the Service inside AKS is healthy?

**Answer:** ClusterIP is an internal Kubernetes virtual IP; external networks outside the cluster lack routes/dataplane access to it by default.

**Question 15.** Do HPA and Cluster Autoscaler always resolve overload?

**Answer:** No. Node pool `maxCount`, quotas/capacity, IP exhaustion, PDBs, scheduling constraints, metrics gaps, and app bottlenecks can all block scaling.

**Question 16.** When external request timeouts climb with load, what else should you check besides DNS?

**Answer:** Connection pools, egress `outboundType`, NAT/LB SNAT, firewalls, retry storms, and external API capacity.

**Question 17.** When Ingress returns 503, can you be sure the Ingress Controller is broken?

**Answer:** No. The Service may have zero Ready endpoints, the upstream app may be returning 503, or another proxy may be emitting it. Correlate logs and backend health.

**Question 18.** Why shouldn't you disable NetworkPolicies or open NSGs to `Any` directly in Production to test?

**Answer:** It creates severe security exposure and obscures the true root cause. Test narrowly with approval, time bounds, and rollback.

**Question 19.** If a Pod was just `OOMKilled`, is restarting it a permanent fix?

**Answer:** No. Without fixing memory leaks, limits/requests, or load spikes, the Pod will likely OOM again; profile memory and find the root cause.

**Question 20.** To declare an incident resolved, is seeing Pods return to Ready enough?

**Answer:** No. Verify Service endpoints, DNS/network paths, successful live requests, latency/SLOs, dependencies, alert clearance, and cleanup of temporary debug pods/permissions.

**Summary:** Effective AKS troubleshooting starts from **Pod and node evidence**, checks **Services and EndpointSlices**, verifies **CoreDNS and upstream DNS**, and then expands to **CNI, NetworkPolicies, VNets, NSGs, UDRs, firewalls, Load Balancers, and dependencies**. Never treat `Running` as proof of health, and never treat `kubectl rollout restart` as a diagnostic method. A trustworthy incident workflow always establishes **clear scope, testing from the true source, minimal reversible changes, and metrics proving service recovery**.
