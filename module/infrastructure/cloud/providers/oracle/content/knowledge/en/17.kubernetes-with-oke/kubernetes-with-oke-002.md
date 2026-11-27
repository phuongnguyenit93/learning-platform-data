# Choosing Cluster Types and Worker Node Management Models

In the **Kubernetes with OKE** chapter of the **CLOUD_PROVIDERS_ORACLE** module, Kubernetes infrastructure choices must align with tenancy, compartment, IAM, VCN, Compute, and storage in Oracle Cloud Infrastructure. A cluster that can run an application is only the starting point; the design must also answer who upgrades worker nodes, how resources scale, which failures the application can withstand, and how budgets are controlled.

This lesson focuses on two decisions: choosing a **basic cluster or enhanced cluster**, and then selecting **managed nodes, virtual nodes, or self-managed nodes** suited to the workload. The examples target a system with a Java service, background jobs, and connections to an Oracle Database outside the cluster.

## 1. Objectives and Prerequisites

After this lesson, you can:

- Distinguish cluster types from worker node management models and how the Kubernetes API endpoint is exposed.
- Choose an option based on application requirements, operational responsibilities, cost, and availability.
- Design worker groups with intentional replacement, scaling, and workload placement capabilities.
- Verify both OCI configuration and Kubernetes state before concluding that the architecture meets requirements.

You should know Pods, Deployments, Services, requests/limits, the node concept, and how to use kubectl. On OCI, you need to understand compartments as the scope for organizing and authorizing resources, VCNs for providing private networks, and compute shapes for describing compute machine configurations.

## 2. Separating Three Questions Often Lumped Together

A cluster decision does not replace decisions about workers and networking.

| Question | Main Options | What Must Be Determined |
| --- | --- | --- |
| Which feature set does the cluster use? | Basic or enhanced | OKE features, service commitment, and cluster fee |
| Who manages the infrastructure running Pods? | Managed, virtual, or self-managed nodes | Responsibility for hosts, capacity, and worker lifecycle |
| Where is the Kubernetes API accessed from? | Private or public endpoint per supported configuration | Administrative network path and access rules |

For example, an enhanced cluster can still use managed nodes. Choosing enhanced does not mean all Pods run in serverless mode. Conversely, choosing a private endpoint does not determine whether workers are managed by Oracle or by your team.

The **control plane** receives the Kubernetes API and orchestrates cluster state. The **data plane** runs workloads. In OKE, Oracle operates the control plane; the remaining responsibilities vary by worker model. Managing workers yourself does not turn the OKE control plane into a self-installed control plane. [Source: OKE Concepts](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengclustersnodes.htm).

~~~mermaid
flowchart TD
    A["Application and operational requirements"] --> B["Choose cluster type"]
    B --> C["Basic"]
    B --> D["Enhanced"]
    C --> E["Managed nodes"]
    D --> F["Managed node pools"]
    D --> G["Virtual node pools"]
    D --> H["Self-managed nodes"]
    F --> I["Group and route workloads"]
    G --> I
    H --> I
    E --> I
    I --> J["Verify cost, capacity, and resilience"]
~~~

## 3. Choosing Between a Basic Cluster and an Enhanced Cluster

### 3.1. Key Differences

| Capability | Basic | Enhanced |
| --- | --- | --- |
| Core Kubernetes, managed node pools | Yes | Yes |
| Virtual node pools | No | Yes |
| Self-managed nodes | No | Yes |
| Advanced add-on management, workload identity | Lacks these enhanced features | Yes |
| Built-in node cycling for managed nodes | No | Yes |
| Service commitment | SLO | SLA with financial backing per terms |

An SLO is a service level objective; an SLA defines a commitment and mechanism per the provider's terms. The OKE service SLA does not automatically provide an availability guarantee for the entire application. [Source: Comparing Enhanced Clusters with Basic Clusters](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingenhancedwithbasicclusters_topic.htm).

### 3.2. When to Consider Basic

Basic is suitable to evaluate when requirements only need core Kubernetes with managed nodes, such as a learning or testing environment with a small budget. Clearly document the excluded needs: not using virtual nodes yet, not needing OKE workload identity yet, and accepting the corresponding worker management workflow.

This is a requirement-driven decision. A small environment that requires workload identity still has a valid reason to choose enhanced; a low Pod count alone is not sufficient criteria to pick basic.

### 3.3. When to Consider Enhanced

Enhanced is worth considering when you need capabilities such as granular add-on management, reducing node replacement effort via node cycling, using virtual nodes, or adding self-managed nodes. For production, include service support and operational requirements in the evaluation alongside cost.

Do not choose enhanced and assume features will configure themselves properly. Workload IAM permissions, add-on update policies, and application distribution still require design and testing.

### 3.4. Upgrading Cluster Type Is Not a Rollback Plan

Oracle allows upgrading eligible VCN-native basic clusters to enhanced; enhanced cannot be directly downgraded to basic. Check the existing cluster's eligibility before planning a conversion. [Source: Working with Enhanced Clusters and Basic Clusters](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengworkingwithenhancedclusters.htm).

If business requirements demand returning to a different architecture, the plan must cover the target cluster, workload redeployment, data handling, and traffic cutover. Do not treat changing the cluster type as a toggle you can freely flip back and forth.

## 4. Managed Nodes: OKE Assists Lifecycle, You Still Manage Workers

### 4.1. Operating Model

Managed nodes are workers on OCI Compute in your tenancy, created by OKE and organized into **managed node pools**. A pool describes the configuration for provisioning workers, such as shape, image, Kubernetes version, node count, and placement.

In this model, the operations team still needs to monitor node health, adjust capacity, and apply updates. Oracle provides the service, images, and supporting tools; the responsibility to update workers does not disappear just because the name includes "managed." [Source: Support and Shared Responsibilities](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengsupportsharedresponsibilities.htm).

Managed nodes are typically the starting option to evaluate when an application needs the broad Kubernetes ecosystem, per-node components, or host configuration capabilities within OKE's supported scope.

### 4.2. Designing Replaceable Workers

A node pool should be treated as a reproducible template for creating workers. Avoid letting application behavior depend on software packages manually installed via SSH on a single machine.

For example, if a new node must have an additional configuration, place that configuration into a supported, version-controlled image or initialization mechanism. Also put labels needed for scheduling into the node-level configuration. When replacing a worker, the new node must meet the same requirements without needing to remember prior manual steps.

For data, determine what is ephemeral and what needs persistent storage. An important file sitting only on a worker's local filesystem creates risk when that worker is replaced.

### 4.3. Changing Pool Configuration Does Not Mean Workers Have Changed

Changing the Kubernetes version configured on a pool does not automatically upgrade the version running on existing managed nodes. You must apply an appropriate worker replacement or upgrade workflow. [Source: Updating a Managed Node Pool](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/update-node-pool.htm).

Enhanced supports node cycling for managed nodes. Depending on the operation, OKE can cordon and drain, then replace the boot volume or replace the instance; verify which attributes apply in each mode. [Source: Performing an In-Place Worker Node Update by Cycling Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengupgradingimageworkernode_topic-Performing_an_InPlace_Worker_Node_Update_By_Cycling_an_Existing_Node_Pool.htm).

- **Cordon:** prevents the scheduler from placing new Pods onto the node through normal scheduling.
- **Drain:** moves workloads off via an appropriate eviction workflow.
- **Replace:** brings a worker matching the desired configuration into service.

A sound update workflow requires spare capacity, Pod Ready checks, and stop-on-failure conditions. Do not treat work request completion as the sole proof that users can still access the application normally.

## 5. Virtual Nodes: Less Server Operations, Check Pod-Level Compatibility

### 5.1. What Changes?

Virtual nodes provide a serverless model for worker infrastructure and are only used with enhanced clusters. Oracle manages the worker layer; you focus on Pods and applications. Virtual node infrastructure runs in the OKE service tenancy, rather than being a set of Compute machines you manage like managed nodes. [Source: Comparing Managed Nodes with Virtual Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingmanagednodeswithvirtualnodes_topic.htm).

This reduces server management work, but does not transfer responsibility for source code, container images, application security configuration, or database connectivity to Oracle.

### 5.2. Requests/Limits Become Critical Inputs

With virtual nodes, CPU and memory allocation is evaluated at the Pod level. Allocation rules consider per-container settings and overhead; do not assume the declared memory amount always equals the exact total allocated or billed amount. [Source: Resources Allocated to Pods Provisioned by Virtual Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengvirtualnodepodresourceallocation.htm).

For Java, measure actual process memory, including heap, metaspace, thread stacks, and native memory. For example, setting the heap equal to the entire memory limit can cause the container to exceed its limit even before the heap is full. Load-test with the planned resource settings before comparing costs across models.

### 5.3. Constraints That Directly Affect Selection

According to Oracle's support table checked on **2026-11-20**:

- Virtual nodes use OCI VCN-Native Pod Networking.
- DaemonSets, privileged containers, and hostPath are not supported.
- SSH access and custom cloud-init for workers are not provided.
- PVCs are supported with File Storage; Block Volume PVCs are not supported.
- Some ingress, metrics, and observability integrations require different deployment approaches.

Limits may change; verify workloads against the actual service version. [Source: Comparing Virtual Nodes with Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingvirtualwithmanagednodes_topic.htm).

Therefore, a stateless API whose data resides in external services is a candidate to test on virtual nodes. A system requiring a DaemonSet-based security agent should evaluate managed nodes, or change how the security requirement is met before migrating the workload.

Do not conclude that no StatefulSet can be used, nor conclude that every PVC is supported. The specific Kubernetes resource type, storage backend, and integration capabilities must be reviewed together.

## 6. Self-Managed Nodes: Provision Compute Yourself and Own Integration

### 6.1. How Do They Differ from Managed Nodes?

A self-managed node is a worker on a Compute instance or instance pool that you create via the Compute service and join to OKE. These nodes do not belong to an OKE managed node pool or virtual node pool. This is often called Bring Your Own Nodes, within OCI infrastructure and OKE support conditions. [Source: OKE Concepts](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengclustersnodes.htm).

This model is useful when you need a shape and image combination or provisioning flow that managed node pools do not satisfy. Needing GPUs alone is not enough to conclude you must use self-managed: first check shapes, images, and managed node capabilities in the chosen region.

### 6.2. Prerequisites and Work to Take On

Self-managed nodes require an enhanced cluster, an appropriate image, and a compatible Kubernetes version. The CNI also has specific prerequisites; check the current requirements rather than assuming any Linux image can join OKE. [Source: Prerequisites for Self-Managed Node Creation](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengprereqsforselfmanagednodes.htm).

The node creation flow includes provisioning Compute and bootstrapping to connect to the target cluster, with the appropriate endpoint information and certificates. [Source: Creating Self-Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingselfmanagednodes.htm).

The team owning this option must be able to describe the full lifecycle:

1. Create machines with the right networking, image, permissions, and bootstrap configuration.
2. Confirm the worker joins the cluster, reports Ready, and has expected labels.
3. Monitor for bootstrap failures, capacity exhaustion, and misconfigurations.
4. Update images, OS, and Kubernetes components within the supported scope.
5. Drain, remove the node, and reclaim Compute in the proper sequence.
6. Recreate nodes from version-controlled configuration to prove recoverability.

Compute instance pool autoscaling alone does not prove that Pods have usable additional workers. You must verify both the Kubernetes join process and whether scale-in handles workloads safely.

## 7. Scenario-Based Selection Table

The following table provides design suggestions based on the characteristics covered; confirm against your specific system requirements and testing.

| Scenario | Option to Evaluate First | Evidence to Gather |
| --- | --- | --- |
| Small Kubernetes lab using core features | Basic + managed nodes | Total lab cost and how workers are replaced |
| Production with per-node agents, needing add-on management | Enhanced + managed nodes | Agents run properly, node updates do not cause excessive disruption |
| Highly variable stateless API, wanting less server operations | Enhanced + virtual nodes | Pod compatibility, networking, metrics, startup time, and cost |
| Need specialized Compute/image combinations | Enhanced + self-managed nodes if supported | Reproducible bootstrap and operations team able to handle lifecycle |
| Workloads with mixed requirements | Enhanced with appropriate worker groups | Clear scheduling rules and per-group observability separation |

Using multiple worker models in one cluster is an option to evaluate, but it increases the number of testing branches. Set clear roles for each group, such as one group serving platform components and another running serverless-eligible APIs. Do not expect Pods to automatically fall back to another model when scheduling conditions or features are incompatible.

## 8. Organizing Node Pools and Placing Workloads Properly

### 8.1. Split Pools for Meaningful Requirements

Reasons often worth considering for separating managed node pools include CPU architecture, CPU/memory profiles, mandatory host components, and maintenance schedules. For example:

| Planned Group | Workload | What to Check |
| --- | --- | --- |
| General | Java APIs and typical services | Capacity during replica scaling and maintenance |
| Memory | Memory-intensive jobs | Native memory, GC pauses, and Pod bin-packing |
| Specialized | Compute requiring specific hardware or config | Shape, image, drivers, and support scope |
| Platform | Appropriate operational components | Minimum resources and desired isolation level |

Do not split a pool just because another namespace exists. Too many small pools can create idle capacity and increase update overhead. Conversely, lumping all workloads into a single configuration can cause teams to contend for resources or be constrained by differing upgrade schedules.

If using Arm and x86, check container images and native libraries for the matching architecture. A Java application can still depend on native libraries, monitoring tools, or binaries that lack an equivalent build.

### 8.2. Combining Labels, Selectors, and Taints

For example, configure a general worker group with the label **learning.example.com/pool=general**. Workloads using a matching nodeSelector can only be placed on nodes satisfying that label along with other scheduling constraints.

If a group of machines must be reserved for specialized workloads, you can combine taints and tolerations. **A toleration only permits a Pod to pass the corresponding taint; it does not force the Pod to run on that group.** To force placement on a group, add an appropriate selector or node affinity. [Source: Kubernetes Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/).

Labels and taints are scheduling tools, not replacements for security boundaries. Strong isolation requirements also involve permissions, networking, workload policies, and sometimes cluster separation.

## 9. Capacity, Autoscaling, and Availability

### 9.1. Separate Scaling Pods from Scaling Workers

With managed nodes, HPA adjusts replica counts based on configured signals; Cluster Autoscaler can adjust worker counts in correspondingly configured managed node pools. These two control loops solve two different problems.

With virtual nodes, scaling resources for Pods does not operate like adding VMs to a managed pool. Do not use Kubernetes Cluster Autoscaler for virtual nodes under current support; you still need to manage limits, quotas, and logical capacity of virtual node pools. [Source: Scaling Kubernetes Clusters and Node Pools](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengscalingkubernetesclustersnodepools.htm).

A Pending Pod is not sufficient proof of CPU shortage. It might lack nodes matching a selector, be blocked by a taint, lack IPs, fail to attach a volume, or hit topology constraints. Adding workers to the wrong group will not resolve that cause.

### 9.2. Capacity Calculation Example for Managed Nodes

Suppose a service needs at most 24 Pods, each requesting **500m CPU and 1Gi memory**. After reserving resources for system and per-node components, each worker has **3 CPU and 6Gi allocatable** remaining for the service.

~~~text
Total CPU requests       = 24 × 0.5 = 12 CPU
Total memory requests    = 24 × 1   = 24Gi

Max Pods per node        = min(3 / 0.5, 6 / 1) = 6
Minimum nodes            = ceil(24 / 6) = 4
~~~

Four workers is the result calculated from requests under the assumptions above. That is not yet a fault-tolerant design: when one worker is lost, the three remaining workers can only hold 18 Pods under the same assumptions.

If you want to survive losing one worker while keeping enough room for 24 Pods, you need at least five workers of this configuration. If the region has three availability domains and the target is surviving losing one AD, a six-worker layout split evenly with two workers per AD leaves four workers after failure, enough for 24 Pods in theoretical capacity.

This is a self-constructed example to illustrate the reasoning, not a default sizing recommendation for OCI. Real results also depend on Pod distribution, IP limits, platform components, volume topology, and shape availability in the region. Do not equate the OCPU count in an OCI shape name with Kubernetes CPU units without checking actual architecture and allocatable capacity.

### 9.3. Fault Distribution Must Accompany Pod Distribution

Creating multiple workers does not guarantee replicas of the same service are spread out. Use topology spread or appropriate affinity rules, and verify actual node topology labels.

With topology spread, **DoNotSchedule** can keep Pods Pending to preserve the constraint; **ScheduleAnyway** prefers spreading while allowing more flexible scheduling. Choose based on priority between spread and the ability to place Pods during resource shortages. [Source: Kubernetes Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/).

If a region has only one AD, spreading across fault domains mitigates some failure modes within the AD, but does not substitute for surviving the loss of an entire AD or region.

### 9.4. PDBs Help Maintenance, Not All Outages

A PodDisruptionBudget can limit how many Pods are disrupted through voluntary eviction operations that respect PDBs. It does not prevent machine failures and does not create spare resources on its own. [Source: Kubernetes Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/).

For example, three replicas with minAvailable equal to two allows draining one Pod under normal conditions. If only two healthy Pods remain, the next drain may be blocked. Identify the root cause, restore replicas, or add capacity per procedure; forcibly removing a node can cause availability targets to fail.

## 10. Incorporating IAM, Networking, Storage, and Databases into the Decision

Worker choices must fit the overall OCI architecture. Before finalizing, clarify the following points:

| Component | Questions to Answer |
| --- | --- |
| Compartment and IAM | Who can create, modify, view, and delete clusters or Compute? Are permissions scoped to the right resources? |
| Kubernetes RBAC | Who can act on namespaces, Deployments, Secrets, and nodes via the Kubernetes API? |
| VCN, subnet, and NSG | Do network paths for administration, workers, Pods, registry, and dependent services work? |
| IPs and quotas | When scaling out or creating replacement workers, are sufficient addresses and quotas available? |
| Storage | Does the workload use ephemeral storage, File Storage, or Block Volume? Does the worker model support that integration? |
| Oracle Database | Are network paths, TLS, credentials, and connection pools sized for the maximum replica count? |

Permission to create clusters via OCI IAM and permission to operate on Kubernetes resources are two scopes to review separately. Similarly, permissions for node operators and permissions for applications accessing OCI should be designed per acting principal, avoiding broad host permissions as the default for every Pod.

If the Java API connects to Autonomous Database or an Oracle Database service outside OKE, increasing replicas increases the total number of connections that can be opened. For example, 24 replicas with a maximum pool of 20 connections create the potential to open up to 480 connections. This is a configuration ceiling calculation, not always-active connections; database load capacity must still be checked.

Adding workers does not solve connection exhaustion on the database. Conversely, autoscaling without appropriate limits can make the problem worse.

## 11. Comparing Total Cost Across Options

According to Oracle's price list, a basic cluster has zero cluster service fee; enhanced clusters and virtual nodes have their own billing units. Compute, storage, and supporting services are still billed based on actual usage. Do not infer that the entire system is free from the basic cluster price. [Source: Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/).

You can build an estimation model:

~~~text
Managed:
  cluster fee
  + worker Compute over time
  + boot volumes and data storage
  + networking, load balancing, and observability

Virtual:
  enhanced cluster fee
  + virtual nodes fee
  + CPU/memory allocated to Pods per billing rules
  + storage, networking, load balancing, and observability

Self-managed:
  enhanced cluster fee
  + Compute and related resources
  + operational, automation, and incident response effort
~~~

These expressions are a comparison framework, not an invoice or complete billing formula. Obtain unit prices, resource allocation rules, and contract terms at estimation time; measure the same workload with the same performance targets to compare.

For steady workloads, managed nodes with well-packed Pods can utilize resources efficiently. For spiky workloads, virtual nodes can reduce the effort of maintaining and scaling workers. Actual results depend on real configuration, Pod resource allocations, and fixed costs; no single model is always cheapest in every scenario.

Include nights, weekends, rollout phases, and reserve capacity in estimates. Apply tags for cost tracking, and configure budgets and alerts within supported scopes. A budget alert must have an assigned responder; it does not automatically shrink the cluster when thresholds are exceeded.

## 12. Hands-On: Inspecting Options on an Existing Cluster

This section uses an authorized cluster in the learning environment. The OCI commands below only read configuration; they do not create clusters or provision new workers. OCI CLI must be authenticated to the right tenancy, profile, and region. kubectl must point to the corresponding kubeconfig, with a network path to the Kubernetes API and required permissions.

### 12.1. Checking Cluster Type and Node Pools

Example using PowerShell; replace OCID values with resources from your learning environment.

~~~powershell
$ClusterId = "<CLUSTER_OCID>"
$CompartmentId = "<NODE_POOLS_COMPARTMENT_OCID>"

oci ce cluster get --cluster-id $ClusterId --query "data.type" --raw-output
oci ce node-pool list --compartment-id $CompartmentId --cluster-id $ClusterId --all
oci ce virtual-node-pool list --compartment-id $CompartmentId --cluster-id $ClusterId --all

kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -L learning.example.com/pool,kubernetes.io/arch,topology.kubernetes.io/zone
~~~

Command sources: [cluster get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/cluster/get.html), [node-pool list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/node-pool/list.html), [virtual-node-pool list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/virtual-node-pool/list.html).

Read the output layer by layer:

- The type field indicates the cluster type; do not infer it solely from node counts.
- The lists of managed and virtual node pools show pools returned by the API within the queried compartment and current permissions.
- Self-managed nodes do not appear as a managed node pool; cross-reference Kubernetes nodes with Compute inventory and the owning team's bootstrap configuration.
- Node Ready represents one part of Kubernetes health; it does not yet prove workloads can be placed on that node.

If node pools are in different compartments, query each applicable compartment. An empty list does not by itself prove the cluster has no workers: first check query scope and permissions.

### 12.2. Example Routing Workloads to a Managed Pool

Suppose target managed nodes have been assigned the label **learning.example.com/pool=general** in the node creation configuration. The following example is a **manifest template**; replace the image with a tested application image and configure image pull permissions if using a private registry. The template does not yet include Services, probes, Secrets, or database connectivity.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      nodeSelector:
        learning.example.com/pool: general
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: order-api
      containers:
        - name: order-api
          image: "<TESTED_OCIR_IMAGE>"
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "1"
              memory: "2Gi"
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: order-api
  namespace: default
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: order-api
~~~

The manifest illustrates three decisions: selecting a worker group by label, preferring spread across hostnames, and limiting voluntary evictions with a PDB. Because ScheduleAnyway is used, the three replicas might still not sit on three different nodes when scheduling conditions are constrained.

Do not use this template as-is to conclude a workload is compatible with virtual nodes. If changing the worker model, re-evaluate Pod capabilities, networking, storage, resource allocation, and metrics collection.

### 12.3. Observing After Deployment in the Lab

After the practitioner applies the completed manifest in the learning environment, you can verify:

~~~powershell
kubectl rollout status deployment/order-api -n default
kubectl get pods -n default -l app=order-api -o wide
kubectl get pdb order-api -n default
kubectl get events -n default --sort-by=.metadata.creationTimestamp
~~~

If a Pod is Pending, take the Pod name from the output and run kubectl describe pod in the right namespace. Read the scheduling events to distinguish insufficient resources from selector mismatches, taints, or other integration issues.

If you need to view CPU/memory usage via kubectl top, first confirm that the metrics pipeline is deployed and works with the worker model in use. Do not interpret missing metrics errors as proof that nodes cannot run applications.

### 12.4. Lab Completion Criteria

Results should include evidence that:

1. The cluster type matches the documented requirements.
2. The actual worker model matches the chosen option.
3. Pods are placed in the intended group and reach the appropriate ready state.
4. Reserve capacity has been calculated for a concrete failure scenario.
5. Permissions, network paths, and dependent service limits have been checked.
6. Costs have been estimated for normal load, peak load, and update periods.

There is no need to create an additional cluster to complete this lesson if the current environment already provides enough data for comparison and verification.

## 13. Concise Architectural Decision Template

The following example is a proposal for a hypothetical system, not a default OKE configuration.

| Item | Decision and Rationale |
| --- | --- |
| Workload | Java API connecting to Oracle Database outside the cluster; has a per-node operational agent |
| Cluster type | Enhanced to use required management capabilities and meet service requirements |
| Initial workers | Managed nodes, because the team needs per-node components and wants node pool lifecycle management |
| Distribution | Across available ADs or fault domains, paired with Pod spread rules and sufficient post-failure capacity |
| Scaling | HPA for replicas; capacity management on managed pools with clear limits |
| Updates | Managed images and versions; verify drain capability, resource headroom, and post-replacement observation |
| Authorization | Properly scoped OCI and Kubernetes admin permissions; separate service access permissions for applications |
| Cost | Track Compute, cluster, storage, networking, and observability; maintain budgets with alert responders |
| Re-evaluation triggers | Agent is replaced, workloads qualify for virtual nodes, or specialized Compute requirements arise |

A good decision must state the conditions that could change it. For example, if the per-node agent is no longer mandatory, an API group can be tested on virtual nodes; switching is only accepted after meeting performance, observability, and budget targets.

## 14. Pitfalls to Recognize

| Misconception | Proper Handling |
| --- | --- |
| Enhanced means all workers are serverless | Determine cluster type and each worker model separately |
| Managed nodes handle all patching automatically | Clearly assign owners for updating, testing, and replacing workers |
| Having three replicas survives losing an AD | Check replica placement, remaining capacity, and dependent services |
| When HPA adds Pods, machines will always be available | Check worker capacity, quotas, IPs, and scheduling constraints |
| Only the node pool version needs to be edited | Verify the actual version on workers after the update workflow |
| Every PVC transfers as-is to virtual nodes | Cross-reference storage backends and supportability |
| Self-managed nodes reduce operational cost due to more control | Include bootstrap, updates, replacement, and incident handling effort |
| Switching worker models only requires changing a selector | Re-test all Pod requirements and related integrations |

When choosing an OKE option, explicitly record the cluster feature set required, the portion of the worker lifecycle the team owns, and evidence of capacity, cost, and resilience. This forms the basis for deploying OCI infrastructure with authorization, monitoring, and automation suited to real applications.
