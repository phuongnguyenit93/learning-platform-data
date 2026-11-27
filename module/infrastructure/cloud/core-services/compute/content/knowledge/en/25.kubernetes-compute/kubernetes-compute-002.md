# Requests, Limits, and How the Scheduler Places Pods

In Kubernetes, **requests** and **limits** describe a container's resource demands and boundaries. The scheduler uses requests together with workload constraints to select an appropriate node for a Pod. After the Pod is assigned to a node, the kubelet and container runtime on that node create the containers and enforce resource limits.

Understanding this mechanism helps avoid two common situations: Pods remaining in the Pending state even when current node resource utilization looks low, or Pods being scheduled successfully only to later suffer CPU throttling, OOMKilled, or eviction. This is foundational when choosing CPU, memory, network configuration, and scaling strategies for cloud workloads.

## 1. Resources Managed by Kubernetes

For typical workloads, the two most important resources are:

- **CPU:** a compressible, time-shared resource. Kubernetes expresses CPU in cores or millicores; `1` CPU equals one core, and `100m` equals 0.1 CPU.
- **Memory:** a container's working memory, typically declared in binary units such as `Mi` and `Gi`. `1Gi` equals `1024Mi`.

Kubernetes also supports declaring resources such as ephemeral storage and extended resources advertised by nodes, such as GPUs. Each resource type has its own scheduling and enforcement behavior; do not assume all resources behave like CPU.

Resources are declared per container. When scheduling, the scheduler evaluates the Pod's aggregate demand, including concurrently running containers, init containers, and Pod overhead if present. Therefore, evaluate resources at the Pod level rather than looking at a single container in isolation.

## 2. Requests: Demand Used for Scheduling

A request is the amount of resource a container declares it needs. The scheduler uses requests to determine whether a node has sufficient capacity in its resource accounting. Once a Pod is assigned to a node, requests also factor into how the system allocates CPU shares when multiple containers contend for CPU.

Example:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
~~~

This configuration declares that the container needs 0.5 CPU and 512Mi of memory. That does not mean the container always consumes that exact amount. An application may use less CPU than requested during low traffic; CPU usage may also burst above the request if the node has spare capacity and the container is not constrained by a CPU limit.

Requests directly affect Pod placement decisions:

- A Pod requesting 1 CPU and 1Gi memory is only eligible for nodes with enough of both resources based on allocatable capacity and already-booked requests.
- A node with plenty of CPU but insufficient memory relative to the request is still ineligible.
- Low actual usage does not automatically reduce the declared requests.
- Requests set too high can leave Pods Pending even though the application rarely uses all that capacity.
- Requests set too low can cause the scheduler to pack too many Pods onto the same node, increasing contention and risk when load rises.

Requests should therefore reflect reasonable operational demand. They are an input to scheduling and resource-sharing management, not a real-time measurement of application usage.

## 3. Limits: Runtime Resource Boundaries

A limit sets the maximum amount of a resource a container is allowed to use for resources that support enforcement.

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

In this example, the container declares a demand of 0.5 CPU and 512Mi, along with a ceiling of 1 CPU and 1Gi of memory.

CPU and memory are enforced differently:

| Resource | Effect of Request | Effect of Limit | When Exceeding Limit |
|---|---|---|---|
| CPU | Used for scheduling and determining sharing weights under contention | Sets a CPU usage ceiling via quota | Container is throttled; usually keeps running but processes more slowly |
| Memory | Used for scheduling and informs evaluation under node memory pressure | Sets a memory limit via cgroup | Process may be OOM killed; container is typically restarted per restart policy |
| Ephemeral storage | Used to account for temporary storage demand during scheduling | Bounds declared usage and helps detect over-consumption | Pod may be evicted when exceeding the limit or when the node runs low on disk space |

A CPU limit is not like a memory limit. CPU is a time-shared resource, so exceeding demand typically results in throttling. Memory cannot be reclaimed in the same way; when a process exceeds its cgroup limit, the operating system may terminate the process to protect the node.

If no CPU limit is set, a container can consume spare CPU beyond its request when the node has available capacity. This can benefit latency-sensitive services, though consumption should still be governed by appropriate requests, quotas, and workload policies. If no memory limit is set, a container can continue allocating memory until the node experiences pressure and the kubelet may have to evict Pods.

Key rules to remember:

- If only a limit is specified and the request is omitted for the same resource, Kubernetes may default the request to match the limit unless an admission policy supplies another value.
- A `LimitRange` in a namespace can inject default requests/limits and enforce minimum or maximum bounds.
- A `ResourceQuota` controls total requests, limits, or object counts in a namespace.
- Requests must be consistent with limits when both are declared; a request greater than a limit is an invalid configuration.

## 4. How the Scheduler Decides Where to Place a Pod

The Kubernetes scheduler is a control plane component that watches for Pods without an assigned node. The scheduler selects a suitable node and records the binding of the Pod to that node. The kubelet on the target node picks up the assigned Pod and is responsible for creating and monitoring its containers.

The high-level workflow includes these steps:

~~~mermaid
flowchart TD
    A["Unassigned Pod"] --> B["Scheduler picks up Pod"]
    B --> C["Filter: eliminate ineligible nodes"]
    C --> D{"Any feasible nodes?"}
    D -- "No" --> E["Pod stays Pending<br/>records reason event"]
    D -- "Yes" --> F["Score: rank feasible nodes"]
    F --> G["Select best-scoring node"]
    G --> H["Bind Pod to node"]
    H --> I["Kubelet receives Pod"]
    I --> J["Create containers and monitor status"]
~~~

### 4.1. Filter: Identifying Feasible Nodes

The scheduler filters out nodes that fail to satisfy the Pod's requirements. Common checks include:

- **Resource fit:** the node has sufficient remaining CPU, memory, ephemeral storage, or extended resources for the Pod's requests.
- **Node selector and node affinity:** the Pod can only be placed on nodes with matching labels or belonging to matching node groups.
- **Taints and tolerations:** a tainted node only accepts Pods with matching tolerations.
- **Pod affinity and anti-affinity:** requires Pods to be placed near or away from other Pods based on labels and topology scope.
- **Topology spread constraints:** distributes Pods across zones or nodes within declared skew limits.
- **Volume and network constraints:** specific PersistentVolumes, storage topology, host ports, or other constraints may disqualify a node.

A node with plenty of CPU and memory can still be filtered out due to taints, labels, storage zones, or topology constraints. Therefore, when a Pod is Pending, do not check only CPU and memory.

### 4.2. Score: Ranking the Remaining Nodes

After filtering, the scheduler scores feasible nodes using configured plugins and policies. Scores can reflect resource balance, affinity preferences, topology spread, volume alignment, or other scheduling objectives.

Higher-scoring nodes are preferred. This does not mean the scheduler always chooses the node with the most free CPU. The goal is to satisfy constraints and optimize according to the active policy set in the cluster.

### 4.3. Bind and Pod Startup

Once a node is chosen, the scheduler binds the Pod to that node. The kubelet on the node performs subsequent steps such as preparing volumes, pulling images, creating containers, and running readiness/liveness probes.

The scheduler does not directly start processes inside containers. A Pod that already has a `nodeName` may still fail to start containers due to image pull errors, missing secrets, volume mount failures, or invalid runtime configurations. Always distinguish scheduling failures from post-scheduling startup failures.

## 5. How the Scheduler Calculates Pod Resources

The scheduler compares the Pod's total resource demand against the node's remaining **allocatable** capacity. For a Pod with multiple concurrently running application containers, the requests of those containers are summed per resource type.

For run-to-completion init containers, the Pod's effective request also accounts for the maximum demand among init containers compared against the sum of concurrently running application containers. Pod overhead, if declared, is added to the calculation as well. Long-running init containers such as native sidecars follow specific calculation rules depending on Kubernetes version and configuration.

Example of a Pod with two application containers:

| Container | CPU Request | Memory Request |
|---|---:|---:|
| API | 500m | 512Mi |
| Log sidecar | 100m | 128Mi |
| Sum of both concurrently running containers | 600m | 640Mi |

The scheduler must find a node with at least `600m` CPU and `640Mi` memory in schedulable resources before considering other constraints. If the Pod also has init containers or Pod overhead, the effective demand may be higher than the simple sum in the table.

### Allocatable vs. Capacity

Nodes report two key metrics:

- **Capacity:** total physical/virtual resources the node has.
- **Allocatable:** the portion of node resources reserved for Pods after subtracting allocations for the OS, kubelet, runtime, and configured reservations.

The scheduler relies on allocatable capacity for scheduling. For example, if a node has 8 CPU capacity but only 7 CPU allocatable, a Pod cannot request 7.5 CPUs simply because Capacity shows 8.

Furthermore, the scheduler tracks requests already assigned to the node. It does not merely look at instantaneous CPU or memory usage when a new Pod arrives. That is why a node can display low CPU utilization yet still reject new Pods: total scheduled requests have already consumed the remaining allocatable capacity.

## 6. Example: Why Is a Pod Still Pending?

Suppose a node has:

- Allocatable CPU: 4 CPUs.
- Allocatable memory: 8Gi.
- Already-assigned Pods declare total requests of: 3.2 CPUs and 6.5Gi memory.

The remaining schedulable headroom is 0.8 CPU and 1.5Gi memory. A new Pod requests 1 CPU and 1Gi memory. Although memory is sufficient, only 0.8 CPU remains, so the node fails the resource fit check. The Pod will not be placed on that node.

~~~text
Node allocatable
CPU:    4.0 CPU
Memory: 8.0 Gi

Already scheduled requests
CPU:    3.2 CPU
Memory: 6.5 Gi

New Pod requests
CPU:    1.0 CPU
Memory: 1.0 Gi

Result
CPU remaining 0.8 CPU  -> insufficient
Memory remaining 1.5 Gi -> sufficient
Node filtered out during Filter phase due to insufficient CPU
~~~

If no nodes have enough CPU for the request, the Pod remains Pending and events typically show messages such as **Insufficient cpu**. Lowering requests just to get the Pod scheduled can mask genuine resource shortages. Before tuning values, determine whether requests were overestimated, whether nodes need scaling, whether the workload can scale out, or whether it belongs in a different node pool.

## 7. Example Pod Configuration with Requests and Limits

The following manifest illustrates an API requiring 0.5 CPU, 512Mi memory, and 1Gi ephemeral storage. Limits allow bursting up to 1 CPU core, 1Gi memory, and 2Gi ephemeral storage.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: checkout-api
  namespace: production
  labels:
    app: checkout-api
spec:
  containers:
    - name: api
      image: registry.example.com/checkout-api:v2
      ports:
        - name: http
          containerPort: 8080
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
          ephemeral-storage: "1Gi"
        limits:
          cpu: "1"
          memory: "1Gi"
          ephemeral-storage: "2Gi"
~~~

Apply the manifest:

~~~bash
kubectl apply -f checkout-api-pod.yaml
kubectl get pod checkout-api -n production -o wide
kubectl describe pod checkout-api -n production
~~~

In real environments, long-running workloads are normally declared via a Deployment or StatefulSet rather than standalone Pods. The controller creates Pods to match the desired replica count; each Pod still carries its requests and limits for the scheduler.

To spread three API replicas across nodes or zones, you can configure topology spread constraints in the Pod template. Choose the topology key, label selector, and behavior when constraints cannot be satisfied. Stricter constraints enforce clearer distribution, but can also leave Pods Pending if the cluster lacks nodes in a given zone.

## 8. QoS Classes and Behavior Under Node Resource Pressure

Kubernetes assigns each Pod one of three Quality of Service classes based on the resource configuration of all its containers:

| QoS Class | Basic Condition | Operational Significance |
|---|---|---|
| Guaranteed | Every container declares CPU and memory requests and limits; request equals limit for each resource | Higher protection priority in certain node pressure scenarios |
| Burstable | At least one request or limit is set, without meeting Guaranteed criteria | Can burst above requests within permitted limits |
| BestEffort | No container declares any CPU or memory request or limit | No CPU/memory resource requests for the scheduler to rely on |

The QoS class influences how the kubelet treats Pods under node resource pressure, but it does not replace requests, limits, priority, or scheduling configurations. When eviction is needed, the kubelet also evaluates usage relative to requests and Pod Priority. Do not interpret Guaranteed as a guarantee that a Pod can never be stopped.

Distinguish between two situations:

- **OOMKilled:** a container exceeds its memory limit and the OS terminates the process. The Pod may remain in Running phase while the container restarts, depending on the restart policy.
- **Evicted:** the kubelet terminates a Pod to reclaim resources when the node faces pressure such as low memory or disk space. Pods managed by a Deployment are normally replaced by the controller if cluster conditions permit.

For critical workloads, set requests close to operational demand, provide appropriate memory limit headroom, configure priority based on criticality, and ensure the cluster maintains spare capacity.

## 9. Trade-offs When Choosing Requests and Limits

**CPU request too low** lets the scheduler pack many Pods onto a single node. Under load spikes, containers contend for CPU and latency can climb. **CPU request too high** reduces Pod density and can leave workloads Pending even when actual CPU is underutilized.

**CPU limit too low** can trigger throttling even when the node has idle CPU. For latency-sensitive services, a tight CPU limit can increase tail latency. Omitting CPU limits can reduce throttling, but requires governing total requests, quotas, and workload trust boundaries.

**Memory request too low** causes the scheduler to underestimate Pod demand and overcommit workloads onto the same node. As load increases, the node easily hits memory pressure. **Memory limit too low** causes containers to be OOMKilled; limits set too high or omitted increase the risk of one memory-hungry workload impacting neighboring Pods.

**Ephemeral storage** must also be tracked for workloads writing logs, caches, or temporary files. Without appropriate requests/limits, a node can run out of disk space and force the kubelet to evict Pods.

Sizing recommendations:

1. Measure CPU and memory under representative load, including peak hours and background jobs.
2. Set CPU requests to reflect steady-state demand and required sharing weight; monitor throttling before raising limits.
3. Set memory requests based on actual working set and memory limits with reasonable burst headroom.
4. Inspect usage per container, since sidecars also consume Pod resources.
5. Account for HPA: percentage-based CPU utilization targets are calculated relative to CPU requests. Without CPU requests on relevant containers, CPU-based autoscaling may fail to compute utilization as expected.
6. Cross-check requests against `ResourceQuota`, `LimitRange`, and node pool allocatable capacity.
7. For GPUs or extended resources, verify that nodes advertise the exact resource name and have available devices.

## 10. Verifying and Troubleshooting Scheduling Issues

When a Pod is Pending, start by describing the Pod to inspect events and reasons the scheduler rejected nodes:

~~~bash
kubectl describe pod checkout-api -n production
kubectl get events -n production --sort-by=.metadata.creationTimestamp
~~~

Look for messages such as **Insufficient cpu**, **Insufficient memory**, **node(s) had untolerated taint**, **didn't match Pod's node affinity/selector**, or volume-related errors. Each message points to a different line of investigation.

Inspect node resources and already-booked requests:

~~~bash
kubectl describe node NODE_NAME
kubectl get nodes
~~~

In the `Allocated resources` section of `kubectl describe node`, compare total requests and limits against allocatable capacity. This clarifies why the scheduler considers a node out of capacity for additional Pods.

To inspect actual runtime usage, use Metrics Server:

~~~bash
kubectl top nodes
kubectl top pods -n production
kubectl top pod checkout-api -n production --containers
~~~

**kubectl top** reflects utilization at the moment of measurement, not the total requests booked by the scheduler. Combine these outputs with **kubectl describe node** and **kubectl describe pod** to distinguish request-based capacity exhaustion from high runtime consumption.

If a container is OOMKilled or restarting repeatedly, inspect its status and previous logs:

~~~bash
kubectl get pod checkout-api -n production
kubectl describe pod checkout-api -n production
kubectl logs checkout-api -n production --previous
~~~

If a Pod has been assigned to a node but is not starting, check image pulls, secrets, volume mounts, runtime events, and probes. Those are post-scheduling errors; increasing CPU requests will not fix them.

## 11. Configuration and Operations Checklist

- [ ] CPU and memory requests are declared per container based on measured data.
- [ ] CPU and memory limits are set according to latency, stability, and resource-sharing requirements.
- [ ] Sidecars, init containers, and Pod overhead are included when estimating Pod demand.
- [ ] Requests are checked against node allocatable capacity, not only node capacity.
- [ ] Node selectors, affinity, taints/tolerations, topology spread, and volume constraints are verified.
- [ ] Namespace `LimitRange` and `ResourceQuota` rules are reviewed.
- [ ] QoS class, Pod Priority, and behavior under node memory or disk pressure are checked.
- [ ] Actual usage is measured and distinguished from scheduler-tracked requests.
- [ ] HPA has required CPU requests to compute utilization when scaling on CPU.
- [ ] When a Pod is Pending or restarting, events, container states, and logs are inspected before adjusting resources.

Requests tell the scheduler how much resource a Pod needs for placement; limits control resource consumption while containers run. The scheduler combines requests with node, topology, volume, and policy constraints to choose where to place each Pod. Good configuration accurately reflects application needs, allowing the cluster to utilize compute efficiently while preserving stability as load shifts.
