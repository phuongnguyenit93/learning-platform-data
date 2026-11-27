# OCI VCN-Native Pod Networking and Flannel

In the **Kubernetes with OKE** chapter of the **CLOUD_PROVIDERS_ORACLE** module, Pod networking must be designed alongside tenancy, compartment, IAM, VCN, and Compute. Networking choices directly affect how many IP addresses must be reserved, connectivity paths to Oracle databases, traffic observability, and how the cluster scales.

This lesson explains the two models **OCI VCN-Native Pod Networking** and **Flannel overlay**, from packet paths to CIDR planning and connectivity testing. The hands-on section uses an existing cluster; the examples do not require creating new infrastructure to understand the differences.

## 1. Objectives and Scope

After this lesson, you can:

- Distinguish worker IPs, Pod IPs, Service ClusterIPs, and the Kubernetes API endpoint address.
- Explain why Pods using VCN-native can be routed in the OCI network, while Flannel Pods reside in an overlay.
- Calculate address capacity for growth, rollouts, and worker replacement.
- Distinguish routing, OCI network rules, NetworkPolicy, and administrative permissions.
- Test DNS, Services, Pod connectivity, and connectivity to external services in order.

Examples focus on **IPv4**, standard Pods, and managed nodes. Pods using hostNetwork, virtual nodes, and multi-interface designs must cross-reference their respective support conditions. You should know Pods, Services, Deployments, CIDRs, subnets, and route tables.

## 2. What Does CNI Do in Kubernetes Networking?

**Container Network Interface — CNI** is the interface for container systems to integrate network configuration components for Pods. In OKE, the network type chosen at cluster creation determines the plugin serving Pod networking.

According to Oracle documentation checked on **2026-11-20**, node pools in a cluster use the same selected CNI; you cannot directly switch that plugin after creating the cluster. Therefore, do not design one managed pool using Flannel and another pool using OCI VCN-native in the same cluster to migrate gradually. [Source: Pod Networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking.htm).

Separate the following address domains:

| Component | Role | Illustrative Example |
| --- | --- | --- |
| VCN CIDR | OCI network address space | 10.40.0.0/16 |
| Worker subnet | Addresses used for worker networking | 10.40.16.0/24 |
| VCN-native Pod subnet | VCN addresses allocated to Pods | 10.40.32.0/22 |
| Flannel Pod CIDR | Pod overlay address space | 10.244.0.0/16 |
| Service CIDR | Virtual addresses for Kubernetes Services | 10.96.0.0/16 |
| API endpoint subnet | Address receiving the Kubernetes API | 10.40.0.0/28 |

These ranges are lesson examples, not mandatory defaults. When using VCN-native, do not create an additional Flannel Pod CIDR; when using Flannel, a VCN-native pod subnet is not needed just to assign IPs to standard Pods.

**ClusterIP is not a Pod IP.** A Service provides a logical access point to backends, typically tracked via EndpointSlices. A normal Service keeps its access address throughout its lifecycle even as backing Pods change. [Source: Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Consequently, a Pod having a VCN-routable IP does not make ClusterIP a VCN address. You should also not use a specific Pod's IP as a long-term configuration address for another application.

## 3. Flannel: Overlay Network Running on Top of Worker Networking

### 3.1. Addressing and Packet Delivery

Flannel allocates Pod addresses from a separate overlay space rather than taking Pod addresses from the VCN CIDR. In this OKE model, overlay Pods are not directly reachable from a Compute instance outside the cluster purely via VCN routing. Flannel works with managed nodes and self-managed nodes within supported scope; it is not used with virtual node pools. [Source: Using the flannel CNI plugin](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking_topic-flannel_CNI_plugin.htm).

Consider two Pods on two workers:

~~~text
Worker A: 10.40.16.10
Pod A:    10.244.1.5

Worker B: 10.40.16.11
Pod B:    10.244.2.9
~~~

The cross-node path can be pictured in two layers:

1. The inner packet represents the connection from Pod A to Pod B.
2. The overlay transport layer carries the packet across worker A's network to worker B.
3. The destination worker processes the overlay layer and forwards the packet to Pod B.

In OKE's Flannel, VXLAN provides this encapsulation layer. The VCN transports traffic between workers, while the overlay handles Pod addresses inside. [Source: Large Cluster Best Practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Large-Scale-Clusters-best-practices.htm).

~~~mermaid
flowchart LR
    A["Pod A<br/>10.244.1.5"] --> B["Worker A<br/>10.40.16.10"]
    B --> C["Overlay packet over VCN network"]
    C --> D["Worker B<br/>10.40.16.11"]
    D --> E["Pod B<br/>10.244.2.9"]
~~~

The diagram illustrates **cross-node** traffic. Two Pods on the same node can use a local path; do not use same-node test results to assert that cross-node networking is working.

### 3.2. Design Implications

Flannel decouples the Pod address budget from the VCN address budget. However, you still must reserve enough worker IPs, overlay CIDR, Service CIDR, and host network capacity.

If an application host outside the cluster needs to call order-api, the standard option is an appropriate Service/Ingress/load balancer entry point. Merely adding a route to 10.244.0.0/16 does not turn Flannel into VCN-native or establish bidirectional connectivity.

For Pods calling an external database, verify how egress and masquerading behave. If the path performs SNAT, the database sees the translated address. When configuring allowlists or investigating errors, use the actual observed address; do not assume the database always sees the raw overlay IP.

### 3.3. Overlay Does Not Mean Encryption or Full Isolation

Packet encapsulation and payload encryption are different mechanisms. Do not treat VXLAN as a substitute for TLS between applications and databases.

Similarly, having Pods inside an overlay does not automatically enforce rules like "frontend can call backend, other namespaces are blocked." For workload-level control, you need a policy mechanism enforced in the cluster.

## 4. OCI VCN-Native: Pods Receive Addresses in the VCN Network

### 4.1. Basic Model

OCI VCN-Native Pod Networking assigns Pod IPs from the VCN address space. Resources in the VCN, connected VCNs, and on-premises networks can route to Pod IPs when network paths and access rules allow it.

With managed nodes, worker networking uses the primary VNIC; Pod networking uses secondary VNICs per supported configuration. The Pod subnet is a private regional subnet. [Source: Using the OCI VCN-Native Pod Networking CNI plugin](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking_topic-OCI_CNI_plugin.htm).

Example:

~~~text
Worker A: 10.40.16.10
Pod A:    10.40.32.20

Worker B: 10.40.16.11
Pod B:    10.40.32.21
~~~

Traffic from Pod A to Pod B flows through VCN network integration rather than adding a Flannel overlay layer. The path still involves host networking components and corresponding rules; "native" does not mean all checks on workers can be skipped.

~~~mermaid
flowchart LR
    A["Pod A<br/>10.40.32.20"] --> B["Pod networking via VNIC"]
    B --> C["VCN and access rules"]
    C --> D["Pod networking via VNIC"]
    D --> E["Pod B<br/>10.40.32.21"]
    C --> F["Database private endpoint<br/>when path and permissions exist"]
~~~

### 4.2. Routability Does Not Equal Reachability

An on-premises client wanting to call a Pod must satisfy all of the following simultaneously:

- Source and destination addresses do not conflict with existing address spaces.
- Network connectivity and routes exist for both outbound and return paths.
- Network filtering layers allow the exact protocol and port.
- The application is listening on the appropriate interface and port.
- Authentication and TLS match the application design.

Suppose TCP to a Pod IP succeeds, yet HTTPS fails because the hostname does not match the certificate. In that case, IP transport is already working; editing route tables will not solve a TLS hostname mismatch.

VCN-native also does not mean Pods receive public IPs for direct internet access. Exposing applications publicly still requires explicitly designed entry points and protection layers.

### 4.3. Do Not Apply One Legacy IP/VNIC Number to Every Configuration

OCI added the ability to attach multiple secondary VNIC profiles for Pod networking. Each profile has its own subnet, NSG, and IP allocation settings; this capability requires VCN-native and is subject to shape limits and service conditions. [Source: OKE support for multiple secondary VNIC attachments](https://docs.oracle.com/en-us/iaas/releasenotes/conteng/conteng-Generic-VNIC-attachments.htm).

When using these profiles, calculate using **ipCount** configuration, shape network capacity, actual Pod limits, and CNI version. If using Application Resources to select profiles, usable capacity also depends on the requested profile. Multiple interfaces for one Pod via Multus is a different design from selecting one profile for the primary network path. [Source: Attaching Multiple Secondary VNICs for Pod Networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengAttaching_Multiple_VNICs.htm).

Therefore, do not grab a Pod density formula from old documentation and apply it to every node pool. Before choosing a shape or raising max-pods, check both configured IP capacity and the version and features in use.

## 5. Comparing and Choosing a Model by Requirements

| Criterion | OCI VCN-Native | Flannel |
| --- | --- | --- |
| Pod IP space | Belongs to VCN | Separate overlay |
| Direct access from outside the cluster | Routable when conditions are met | Does not provide equivalent direct routing |
| VCN IP budget | Must count addresses serving Pods | Mainly counts OCI resources, while Pods use overlay |
| Cross-worker path | VCN network integration | Has overlay encapsulation layer |
| VCN-layer observability | Can correlate traffic with Pod IPs at suitable observation points | Needs correlation between worker info and overlay layer |
| Notable operational concerns | Subnet capacity, VNICs, IP allocation | Overlay CIDR, inter-worker networking, and encapsulation |
| Virtual node pools | Required network option | Not applicable |

Virtual node prerequisites are described in Oracle's virtual node pool creation workflow. [Source: Creating Virtual Nodes and Virtual Node Pools](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingvirtualnodes_topic.htm).

The following scenarios illustrate how to apply these criteria, not default conclusions for every cluster:

- **Network team needs to monitor and manage Pod flows in OCI architecture:** evaluate VCN-native, and verify how workloads are identified when Pods change addresses.
- **Limited VCN IP space, applications communicate mostly inside the cluster:** evaluate Flannel along with overlay budget and external connectivity needs.
- **System plans to use virtual nodes:** include the VCN-native requirement in the design from the start.
- **Applications with strict throughput or latency requirements:** test with the same workload, same shape, same topology, and same load level. Do not conclude purely from the presence or absence of an overlay.
- **Large clusters or multi-interface networking:** consult dedicated documentation for that scale and feature; this lesson's scope does not replace detailed design.

Oracle also recommends choosing the CNI based on addressing requirements and application characteristics. [Source: Networking Best Practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Networking-best-practices.htm).

## 6. CIDR Planning and IP Capacity

### 6.1. Prevent Overlaps from the Start

With Flannel, the VCN CIDR must not overlap the Pod CIDR or Service CIDR. With VCN-native, Pods use a subnet inside the VCN, while the Service CIDR must remain separate from the VCN. Also avoid conflicts with connected networks such as on-premises. [Source: IPv4 CIDR Blocks and Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengcidrblocks.htm).

Example IPv4 plan:

| Purpose | Illustrative Range | Notes |
| --- | --- | --- |
| VCN | 10.40.0.0/16 | Holds the OCI subnets of the example |
| API endpoint | 10.40.0.0/28 | Separates management addresses |
| Load balancer | 10.40.1.0/24 | Choose private/public per application access |
| Worker | 10.40.16.0/24 | Account for extra nodes added during updates |
| Pod VCN-native | 10.40.32.0/22 | Used only in the VCN-native option |
| Pod Flannel | 10.244.0.0/16 | Used only in the Flannel option |
| Kubernetes Service | 10.96.0.0/16 | Separate from the networks listed above |
| On-premises | 172.20.0.0/16 | Assumed for testing hybrid connectivity |

This table does not prove these ranges are free in your tenancy. Cross-reference against your organization's IP plan and existing connections.

For example, if on-premises already uses 10.244.0.0/16, taking that range as an overlay can cause a Pod to misroute when calling an external host with an overlapping address. An overlay does not eliminate IP conflict problems.

### 6.2. Size for Peak Resources, Not Just Running Pods

With VCN-native, estimate addresses **allocated or reserved** under the current mechanism, rather than just counting Running Pods. A calculation framework:

~~~text
Minimum pod subnet budget =
    Pod addresses allocated to workers at peak time
  + VNIC addresses and shared subnet consumers not yet included above
  + platform-reserved addresses
  + buffer for growth and estimation variance
~~~

Peaks can occur when:

- Cluster Autoscaler adds workers.
- Deployments create new Pods before old Pods terminate.
- Update workflows hold old and new workers concurrently.
- Another pool sharing the same pod subnet scales out.
- Pods or workers take a long time to finish reclaiming resources.

A cluster with free CPU does not guarantee free IPs. Conversely, a subnet with plenty of IPs does not prove the shape or worker configuration permits scheduling more Pods.

### 6.3. VCN-Native Sizing Example

Suppose a compatibility-verified design has:

- Maximum 20 workers at peak load.
- Up to 4 temporary extra workers during updates.
- Verified IP allocation budget for Pods of 32 addresses per worker, on the same pod subnet.

The Pod address portion at peak is:

~~~text
Workers at peak = 20 + 4 = 24
Pod IP budget   = 24 × 32 = 768 addresses
~~~

For a typical single-CIDR IPv4 subnet, OCI reserves three addresses. For example, a /23 has 512 total addresses, leaving 509 before other allocations; a /22 has 1,024 total addresses, leaving 1,021. [Source: Identify VCN Topology and Specifications](https://docs.oracle.com/en-us/solutions/oci-best-practices-networking/identify-vcn-topology-and-specifications1.html).

Under these assumptions:

- /23 is insufficient even for the 768 Pod IP budget alone.
- /22 leaves 253 addresses after the Pod IP portion and the three reserved addresses.
- You must still subtract VNIC addresses, shared consumers, or other uncounted allocations.

This is an illustrative calculation. The number 32 is neither a mandatory OKE default nor a guarantee that every worker always uses exactly 32 addresses. Plug in your actual configuration and measured consumption; if an address is already included in the measured budget, do not count it twice.

For multiple pod subnets or VNIC profiles, budget per subnet and per allocation group. Spare IPs elsewhere in the VCN do not help a profile that has exhausted addresses in its own subnet.

### 6.4. Flannel Also Has Range-Partitioning Limits

Under the IPv4 Flannel model in OKE documentation, each worker is assigned a /25 block from the Pod CIDR. Thus, total overlay IPs do not equal freely usable Pods across arbitrary nodes. [Source: IPv4 CIDR Blocks and Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengcidrblocks.htm).

Self-calculated example:

~~~text
A /20 Pod CIDR has 4,096 addresses
Each /25 block has 128 addresses

Number of /25 blocks in /20 = 4,096 / 128 = 32
~~~

If the plan requires 30 permanent workers and 4 temporary workers, 32 blocks cannot accommodate 34 workers, even if few Pods are running. This is an address-partitioning limit in the example; final supported node counts are also subject to other OKE limits.

Workers also have their own Pod count, CPU, and memory limits. Do not treat the 128 addresses of a /25 as the target operational Pod count on a node.

## 7. Designing Network Paths and Control Layers

### 7.1. Each Layer Answers a Different Question

| Layer | Question |
| --- | --- |
| OCI IAM | Which principal can create or modify OCI resources? |
| Kubernetes RBAC | Which principal can act on Kubernetes resources? |
| Route | Do packets have a path to the destination and back? |
| NSG/security list | Does the OCI network layer allow that flow? |
| Enforced NetworkPolicy | Which Pods may communicate per Kubernetes policy? |
| Application and TLS | Does the connection match the protocol, identity, and business permissions? |

An account with permission to view Pods does not thereby gain access to call a database. An existing route does not replace a rule permitting the connection. A network rule allowing TCP also does not replace user authentication.

In tenancies with networking and clusters in different compartments, identify which principals use subnets, manage network components, and provision resources. Scope permissions properly; do not broaden tenancy-wide permissions just to bypass a permission error without identifying the denied operation.

### 7.2. NSGs and Security Lists Do Not Replace Routes

Security lists apply per subnet; NSGs attach to VNIC groups or supported resources. When using multiple NSGs and security lists together, inspect the union of effective allow rules; a broad rule elsewhere may still permit traffic. Stateful and stateless rules also differ in handling return traffic. [Source: Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

With VCN-native, inspect the exact VNIC or profile serving Pods. Editing the NSG of a worker's primary VNIC may not affect the Pod network path you intend to change.

With Flannel, VCN-layer rules must allow inter-worker networking flows. Do not assume an NSG can inspect Kubernetes labels inside overlay packets and directly enforce frontend/backend policies.

Oracle publishes network requirement sets for API endpoints, workers, and Pods per model. Apply all foundational flows, including API communication, kubelet, path discovery, and service dependencies. A single application rule does not replace complete OKE configuration. [Source: Network Resource Configuration](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm).

### 7.3. Egress to the Internet and Oracle Services

A NAT Gateway lets resources without public IPs initiate outbound internet connections and receive return traffic. It does not provide an arbitrary internet entry point into Pods. [Source: NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm).

A Service Gateway provides a private path to supported Oracle services via the Oracle Services Network. It is not a generic substitute for every internet destination or every private endpoint. [Source: Access to Oracle Services](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm).

A flow-by-flow verification table could look like this:

| Flow | What Must Be Verified |
| --- | --- |
| Worker pulling container images | Network path from worker, DNS, and registry authentication |
| Pod calling public API | Pod egress under CNI model, routes, and network rules |
| Pod calling Oracle service | Specific endpoint and appropriate service access path |
| Pod calling Oracle Database private endpoint | Private name resolution, bidirectional routes, database rules, and TLS |
| Client calling app from outside cluster | Exposed entry point, healthy backends, and return path |

If containers cannot pull images, the application has not started running yet. In that case, check the network path from workers and the registry before blaming application code egress.

### 7.4. NetworkPolicy Requires an Enforcement Engine

Successfully creating a NetworkPolicy resource does not prove traffic is blocked. The cluster needs a compatible enforcement component. Allow policies are additive; also consider other policies selecting the same Pods. [Source: Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Oracle provides instructions for using Calico as a network policy engine for eligible OKE configurations. This adds policy enforcement rather than replacing the cluster's IP-allocating CNI. Do not apply a managed nodes procedure to virtual nodes without checking support. [Source: Installing Calico and Setting Up Network Policies](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupcalico.htm).

The following example is for a lab that already has an active policy engine. It selects Pods carrying label app=order-api in namespace net-lab, allowing TCP/8080 ingress from Pods carrying label app=frontend in the same namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-api-from-frontend
  namespace: net-lab
spec:
  podSelector:
    matchLabels:
      app: order-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

This sample does not configure egress, does not select all Pods in the namespace, and does not cover health check or management flows. Evaluate those flows before using it for a real application.

To verify effect, send the same request from frontend and from another unselected Pod. A negative result is meaningful only when you already know the target app is healthy, connectivity worked before the policy, and no other rule allows it.

## 8. Hands-On: Inspecting Network Configuration on OKE

### 8.1. Prerequisites

Practitioners need OCI CLI authenticated to the right tenancy, profile, and region; permission to read cluster, node pool, and subnet; kubeconfig for the right cluster; and connectivity to the Kubernetes API.

The traffic testing section assumes the lab environment already has namespace net-lab, Pod client-a, a Pod running order-api, and Service order-api. The client needs appropriate testing tools. These are hypothetical lesson resources, not automatically created OKE resources.

### 8.2. Reading Configuration from OCI

The following PowerShell commands only read configuration. Replace placeholder values with resources assigned in your lab.

~~~powershell
$ClusterId = "<CLUSTER_OCID>"
$NodePoolId = "<MANAGED_NODE_POOL_OCID>"
$SubnetId = "<SUBNET_OCID_TO_INSPECT>"

oci ce cluster get --cluster-id $ClusterId
oci ce node-pool get --node-pool-id $NodePoolId
oci network subnet get --subnet-id $SubnetId
~~~

Command sources: [cluster get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/cluster/get.html), [node-pool get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/node-pool/get.html), [subnet get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/subnet/get.html).

Record:

- CNI type in Pod networking config: OCI_VCN_IP_NATIVE or FLANNEL_OVERLAY.
- VCN, worker subnets, and related Pod networking config.
- Shape, Pod limits, and IP allocation per actual configuration.
- Subnet CIDR, route table, and security lists.
- NSGs of the actual VNICs or profiles along the path under inspection.

Do not take a subnet name containing "pod" as proof the cluster uses VCN-native. Names are operator-chosen labels; actual configuration and addresses are the evidence.

### 8.3. Cross-Referencing Kubernetes

~~~powershell
kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -o custom-columns='NAME:.metadata.name,PODCIDR:.spec.podCIDR,PODS:.status.allocatable.pods'
kubectl get pods -A -o wide
kubectl get daemonsets -n kube-system
kubectl get events -n kube-system --sort-by=.metadata.creationTimestamp
~~~

For standard Pods in the example:

- VCN-native: match Pod IPs against pod subnet/profile CIDRs.
- Flannel: match Pod IPs against the overlay Pod CIDR.
- Compare Pods against running nodes to distinguish same-node vs. cross-node.

PodCIDR on a Node may not carry the same meaning across all CNIs. An empty field alone is insufficient to conclude a network error. Likewise, do not infer complete CNI health solely from DaemonSet names; inspect actual add-on configuration and versions.

### 8.4. Testing Along the Path

First confirm backends and Service:

~~~powershell
kubectl get pods -n net-lab -o wide
kubectl get service order-api -n net-lab -o wide
kubectl get endpointslices -n net-lab -l kubernetes.io/service-name=order-api -o wide
kubectl get networkpolicies -n net-lab
~~~

If the client image includes nslookup and wget, you can use:

~~~powershell
kubectl exec -n net-lab client-a -- nslookup order-api.net-lab.svc.cluster.local
kubectl exec -n net-lab client-a -- wget -qO- -T 5 http://order-api:8080/health
~~~

This example assumes the Service listens on 8080 and the app has a /health path. Substitute your actual port, cluster domain, and endpoint. Do not misinterpret missing tools in an image as a CNI failure.

Build a verification checklist:

| Step | Purpose | Reading the Result |
| --- | --- | --- |
| Call app by same-node Pod IP | Test application and local path | Success does not prove cross-node |
| Call cross-node Pod IP | Test inter-worker transport | Compare with same-node to narrow scope |
| Call by ClusterIP | Also test the Service layer | Cross-reference EndpointSlices and port/targetPort |
| Call by Service DNS | Also test name resolution | Separate DNS errors from TCP errors |
| Call database from app environment | Test external-to-cluster connection | Separate timeouts, TCP refusals, TLS, and auth errors |

When testing Pod IP, take the current address from Kubernetes output and call the container port directly. When testing a Service, use the Service port. Those two ports can differ.

Some administrative paths like kubectl port-forward do not traverse the application client's full access path. Success over port-forward does not prove network paths from another Pod, a load balancer, or on-premises are working.

## 9. Symptom-Based Diagnosis

### 9.1. Pod Fails to Initialize Networking

If events show FailedCreatePodSandBox or CNI/IPAM errors:

1. Capture the full message and timestamp.
2. Identify the affected node, pool, and CNI version.
3. With VCN-native, check IP allocation, remaining subnet addresses, VNICs, and related permissions.
4. With Flannel, check network component health, overlay block allocation, and node state.
5. Compare with a newly created Pod succeeding on another node to isolate failure scope.

Increasing CPU requests or replica count does not directly fix address allocation failures. Repeatedly deleting and recreating Pods can also erase event clues without fixing the root cause.

### 9.2. Same-Node Works, Cross-Node Fails

This symptom points toward checking inter-node paths and node-specific configuration on the failing node:

- Flannel: overlay health, forwarding, and packet delivery between workers.
- VCN-native: network path of Pod VNICs/profiles and applied rules.
- Both: workload policies, host firewalls, and configuration differences between nodes.

Do not open all ports to the internet to test. First identify source, destination, protocol, and the denying layer; apply changes scoped appropriately to the lab.

### 9.3. DNS Works, Yet Application Connection Fails

Name resolution only proves part of the DNS path. Check next:

- Does the Service select the right labels?
- Are matching Ready backends present?
- Does the Service port map to the right targetPort?
- Is the process listening on the appropriate address?
- Is TCP blocked before reaching the application?

If Pod IP access succeeds while ClusterIP fails, prioritize inspecting the Service layer and the Service-handling component in your cluster configuration.

### 9.4. Small Connections Work, Large Transfers Hang

This scenario calls for checking MTU, Path MTU Discovery, ICMP, and tunnel layers along the entire path. Overlays have encapsulation overhead; hybrid paths can also add their own transport layers.

Do not change an MTU value cluster-wide from this symptom alone. Measure and inspect the actual path, because stalls can also stem from timeouts, proxies, or the application.

### 9.5. Using Flow Logs Within Their Limits

VCN Flow Logs help correlate network flows with accepted/rejected status at the VCN layer. They do not replace application logs or prove business transactions succeeded. [Source: Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

When records are missing, check the enablement point, capture filter, sampling, and time window. Absence of records does not prove absence of packets. [Source: Enabling Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/vcn-flow-logs-enable.htm).

With VCN-native, correlate Pod IPs with namespaces, workloads, and Pod lifetimes. With Flannel, host-level data may also be needed to link worker flows to Pods inside the overlay. Keep timestamps consistent across log sources.

## 10. Automation, Cost, and Resilience

Put CNI, CIDRs, routes, and related rules into version-controlled infrastructure configuration. When using Terraform or OCI Resource Manager, inspect change plans to identify resources that will be replaced and capacity required during transitions.

An infrastructure variable set should clearly express:

~~~text
pod_network_model
vcn_address_ranges
worker_subnet_ids
pod_subnet_ids_or_profiles
service_cidr
flannel_pod_cidr_if_used
expected_peak_nodes
update_surge_nodes
pod_ip_budget
network_security_groups
~~~

This is a conceptual list for design, not mandatory OCI provider attribute names. Configure only fields applicable to the chosen model; avoid passing both sets of values as if a cluster runs two CNIs simultaneously.

Costs to evaluate include Compute driven by Pod density, idle capacity retention, cross-path traffic, application entry points, logs, and operational effort. Do not conclude one model is always cheaper solely because it reduces VCN IP usage or removes an overlay layer.

For availability, test at least these scenarios:

- Peak load coinciding with worker replacement, increasing IP demand.
- One worker group failing and Pods needing to move to remaining groups.
- Networking to the database failing while Pod-to-Pod remains normal.
- DNS failing while connections to already-known addresses still work.
- Slow Pod/worker reclamation causing address usage to exceed expectations.

When migrating from Flannel to VCN-native or vice versa, plan a target cluster: build suitable network infrastructure, redeploy workloads, verify storage and policies, shift traffic, and only then decommission the source cluster. The rollback plan must preserve required access points and data during the cutover window.

## 11. Decision Example for a Java Application Using Oracle Database

Suppose a system has order-api, order-processing workers, and an Oracle Database private endpoint. The networking team wants to observe application flows in OCI; Pod counts are expected to rise during peak hours.

One option to evaluate is VCN-native with a pod subnet sized with headroom for autoscaling and worker replacement. The database is still accessed by name and appropriate service endpoint rather than storing a fixed Pod IP in partner-side configuration.

The decision record needs the following evidence:

| Decision | Evidence |
| --- | --- |
| Use VCN-native | Meets addressing and flow-management needs in the VCN |
| Allocate sufficient IPs | Includes calculation by peak workers, IP allocation, and shared consumers |
| Private database connection | DNS, bidirectional routes, network rules, TLS, and authentication all verified |
| Workload isolation | Policy engine and policies tested with allowed and blocked cases |
| Network monitoring | Flow logs, Pods, nodes, and error timestamps can be correlated |
| Cost control | Measured load, Pod density, and accompanying infrastructure cost |
| Recovery plan | Clear behavior documented for IP exhaustion, worker loss, or database path failure |

If the organization no longer has sufficient VCN IP space, re-evaluate the IP plan or the Flannel option along with service exposure design. The new decision must uphold all established application, security, and operational targets.

## 12. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| Flannel needs no IP planning | Must still plan overlay, worker, and Service CIDRs |
| VCN-native Pods have public IPs | Pod addresses in this lesson are private VCN IPs |
| Same subnet means all flows are auto-allowed | Network rules, policies, and app state still apply |
| Every Pod always gets its own VNIC | Pod IPs are managed via the VNIC/IP allocation mechanism of the active config |
| One Pod/VNIC limit applies across all versions | Check shape, CNI, profile, and actual max-pods configuration |
| Route to Flannel Pod CIDR suffices for external access | Overlays need proper connectivity/service exposure mechanisms |
| Creating a NetworkPolicy provides isolation | Requires an enforcement engine and checking additive policies |
| DNS answering means the app is reachable | Still must check Service, TCP, TLS, and app permissions |
| Switch CNI by adding a new pool | CNI choice belongs to cluster design; requires migrating to an appropriate cluster |
| A node with free CPU can accept more Pods | IP limits, Pod count limits, and other scheduling constraints still apply |

Networking choices for OKE must be explained through concrete packet paths and address budgets. Once you can trace IP sources, routing layers, traffic-permitting layers, and error observation, your design has a solid basis to scale and operate within OCI infrastructure.
