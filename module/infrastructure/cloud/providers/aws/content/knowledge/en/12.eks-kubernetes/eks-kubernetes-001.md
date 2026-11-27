# EKS Control Plane and Data Plane Architecture

> **Chapter:** Kubernetes with EKS  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Region/AZ, IAM, VPC, compute, storage, databases, integration, and serverless; learn how to choose services, design secure systems, monitor, recover, and control costs.

## Learning Objectives

**Amazon Elastic Kubernetes Service (Amazon EKS)** is a managed Kubernetes service provided by AWS. Instead of deploying, patching, and maintaining an entire Kubernetes cluster yourself, development teams can let AWS manage the critical components of the **control plane** and choose how compute resources are provisioned for the **data plane**.

However, “managed Kubernetes” **does not mean AWS operates the entire application for you**. A cluster with a control plane distributed across multiple Availability Zones can still suffer a service outage if Pods run on only a single node, subnets run out of IP addresses, a deployment command leaves all replicas unhealthy, or the application depends on a single database.

After this lesson, you will be able to:

1. Accurately distinguish between the **control plane** and the **data plane**; describe the roles of `kube-apiserver`, `etcd`, the scheduler, the controller manager, kubelet, and the container runtime.
2. Explain what AWS manages in the **EKS-managed control plane** and what operators remain responsible for across different data plane options.
3. Compare **EKS managed node groups**, **self-managed EC2 nodes**, **AWS Fargate**, and **EKS Auto Mode**.
4. Trace a `kubectl apply` operation from the API server to the scheduler, kubelet, Pod, and the application ingress path.
5. Understand the roles of the VPC, subnets/AZs, cluster endpoint, control-plane ENIs, AWS VPC CNI, CoreDNS, kube-proxy, load balancers, and storage.
6. Distinguish between **IAM authentication/access entries**, **Kubernetes RBAC**, and the AWS permissions granted to applications running inside a Pod.
7. Recommend availability, monitoring, autoscaling, security, backup/restore, and cost practices for a production cluster.
8. Use the AWS CLI and `kubectl` with **read-only** commands to inspect an authorized EKS cluster.

## 1. What is EKS, and what layers does Kubernetes require?

Kubernetes manages the **desired state** of workloads: the number of Pods to run, container images, CPU/RAM resources, service ports, update strategies, access permissions, and other objects. Controllers continuously reconcile actual state with declared state and apply changes within the scope of what is possible.

The architecture is commonly separated into:

| Layer | Key Components | Responsibilities |
|---|---|---|
| **Control plane** | API server, etcd, scheduler, controller manager | Receive configuration, store state, make scheduling decisions, manage object lifecycles |
| **Data plane** | Worker nodes, kubelet, container runtime, Pod/containers | Execute workloads and handle application traffic |
| **Networking** | CNI, CoreDNS, Service networking, load balancing | Assign Pod IPs, resolve names, route traffic between services and clients |
| **Storage** | CSI driver, PV/PVC, EBS/EFS, and other services | Attach/detach volumes, provide storage required by Pods |
| **Identity & security** | IAM, access entries/RBAC, Pod Identity/IRSA, security controls | Administrative authentication, Kubernetes authorization, and permissions to call AWS APIs |
| **Operations** | Logs, metrics, autoscaling, upgrades, backup, and IaC | Monitoring, maintenance, recovery, and cost control |

### 1.1. EKS Cluster Diagram

~~~mermaid
flowchart TB
    Dev[Operator / CI-CD] -->|kubectl + AWS IAM auth| EP[EKS Kubernetes API endpoint]
    subgraph CP["EKS-managed Control Plane - AWS-managed environment"]
        API[kube-apiserver]
        ETCD[(etcd - Kubernetes state)]
        SCH[kube-scheduler]
        CM[kube-controller-manager]
        API <--> ETCD
        SCH <--> API
        CM <--> API
    end
    EP --> API
    subgraph VPC["Customer VPC - multi-AZ"]
        subgraph AZA["AZ-A"]
            N1[Worker node A]
            P1[Frontend Pod]
            P2[API Pod]
            N1 --> P1
            N1 --> P2
        end
        subgraph AZB["AZ-B"]
            N2[Worker node B]
            P3[Frontend Pod]
            P4[API Pod]
            N2 --> P3
            N2 --> P4
        end
        LB[ALB / NLB by design] --> N1
        LB --> N2
    end
    API <-->|Kubernetes API / operational connectivity| N1
    API <-->|Kubernetes API / operational connectivity| N2
~~~

The diagram above is a **conceptual model** and does not depict every VPC flow or AWS-internal resource in full detail. AWS maintains the control plane in an AWS-managed environment; the workload components typically reside in subnets of the customer-selected VPC (with exceptions and specifics depending on the data plane mode).

**Key distinction:** the control plane is where **orchestration** happens, not where your Java/Web/API application runs. Workload containers run on the data plane you choose.

### 1.2. How is EKS different from a self-managed Kubernetes cluster?

With a self-managed Kubernetes cluster on EC2, the operations team must design, deploy, replace, patch, back up, and scale the API server, etcd, and all control plane components themselves. With standard EKS:

- AWS provisions and operates the managed **Kubernetes control plane**.
- You still decide the **cluster configuration**, supported version, VPC connectivity, access permissions, and how workloads are operated.
- The data plane has multiple management models; your level of responsibility depends on your choice.
- **Kubernetes version upgrades** still require planning: AWS manages the control plane infrastructure, but applications, admission policies, add-ons, node versions, and API deprecations must be evaluated.

## 2. Control Plane: The Brain of the Cluster

### 2.1. kube-apiserver — the control gateway

`kube-apiserver` exposes the Kubernetes API for:

- `kubectl`, CI/CD pipelines, and administrative tools;
- controllers/scheduler/kubelets according to configured permissions;
- Kubernetes operators and controllers installed by applications.

When you run:

~~~bash
kubectl apply -f deployment.yaml
~~~

the client sends a request to the API server. The server validates authentication/authorization, admission, and object validity before persisting the desired state into the system.

**Common error:** `kubectl get pods` returning `Unauthorized` or `Forbidden` does not necessarily mean the cluster is broken. You need to distinguish between **connectivity to the API endpoint**, **AWS IAM authentication**, **EKS access entries/legacy access mapping**, and **Kubernetes RBAC**.

### 2.2. etcd — storing Kubernetes state

**etcd** is the consistent key-value store used to persist Kubernetes state:

- Deployments, Pods, Services, and related metadata;
- ConfigMaps, Secrets, and many configuration objects;
- state required for controllers to reconcile, orchestrate, and observe the system.

In EKS, AWS manages the control-plane etcd. Operators **do not SSH directly into etcd nodes** as they might in a self-managed cluster. Even though etcd is managed by AWS, you remain responsible for **application configuration**, manifest/IaC sources, application data backup strategies, and recovery procedures for the objects you own.

**A Kubernetes Secret is not automatically a secrets vault suited for every production application**: you must evaluate encryption, RBAC, auditing, rotation, and using AWS Secrets Manager/Parameter Store with appropriate integration mechanisms.

### 2.3. kube-scheduler — selecting nodes for Pods

The scheduler watches Pods that have not yet been assigned to a node and selects a placement that can satisfy constraints:

- CPU and RAM `resources.requests`;
- `nodeSelector`, node affinity/anti-affinity;
- taints and tolerations;
- `topologySpreadConstraints` to distribute across nodes/AZs;
- volume topology, network capabilities, and other constraints.

The scheduler **does not create new CPU or RAM** if all nodes lack capacity. A Pod can remain `Pending` until a suitable node is available, an autoscaler provisions additional nodes, or resource requests are adjusted.

### 2.4. kube-controller-manager — maintaining desired state

The controller manager runs loop-based controllers, such as watching nodes, ReplicaSets, Deployments, or endpoints according to their respective Kubernetes functions. In a typical flow:

1. You declare a Deployment with 3 replicas.
2. Controllers create/adjust the ReplicaSet and Pods.
3. The scheduler assigns Pods to nodes.
4. kubelet on each node creates containers to fulfill the desired state.
5. If a Pod disappears and suitable capacity remains available, controllers create a replacement Pod.

**Note:** a controller can only reach the desired state if real-world conditions allow it—for example, available resources, permissions, images, and networking.

### 2.5. How EKS manages control plane availability

AWS operates control plane components with redundancy across **multiple Availability Zones within a Region**, managing failed component replacement and infrastructure maintenance. The API server and etcd are not placed directly on your EC2 node groups.

However:

- Control plane HA **does not automatically distribute application Pods** across multiple AZs.
- A healthy control plane **does not guarantee all Pods are healthy**, that API services are working properly, or that the database has no errors.
- Upgrade processes, policy edits, quota limits, or API connectivity issues can still affect operations.
- **Control plane logging** must be actively configured; not all Kubernetes logs are stored indefinitely in CloudWatch by default.

## 3. Data Plane: Where Containers Actually Run

### 3.1. What makes up a worker node?

In an EC2 node model, each worker node typically includes:

- Operating system/AMI and kernel;
- **kubelet**: receives assigned PodSpecs, interacts with the container runtime, and reports status;
- **container runtime** such as containerd, depending on the supported AMI/EKS version;
- CNI networking and service routing components such as `kube-proxy`, depending on the cluster model;
- Workload Pods: web/API, workers, ingress controllers, or agents.

~~~mermaid
flowchart TD
    API[EKS kube-apiserver] -->|PodSpec and watch| K[kubelet on EC2 node]
    K --> CR[Container runtime]
    CR --> P1[Pod: api-service]
    CR --> P2[Pod: background-worker]
    CNI[AWS VPC CNI / networking] --> P1
    CNI --> P2
    DNS[CoreDNS service] -. Service resolution .-> P1
    DNS -. Service resolution .-> P2
~~~

**CoreDNS** typically runs as a Kubernetes Deployment/Pods on the data plane rather than inside the AWS-managed control plane. Similarly, many add-ons are installed in namespaces such as `kube-system` and require nodes/compute to run.

### 3.2. Data plane options

| Model | Who provisions/upgrades compute? | When is it suitable? | What you still must manage |
|---|---|---|---|
| **EKS managed node groups** | AWS automates many lifecycle steps for EC2 Auto Scaling nodes | Most EC2 workloads needing simpler node management | Type/size, scaling, AMI/version strategy, workloads, permissions, addons, maintenance |
| **Self-managed EC2 nodes** | Operators orchestrate EC2, bootstrap, updates, and lifecycle themselves | Need specialized host configuration or deep control | Nearly the entire node lifecycle, patching, and bootstrap |
| **AWS Fargate for EKS** | AWS provisions compute to run Pods, no EC2 worker node management required | Certain workloads suited to a serverless Pod model | Fargate profiles, resources, subnet/network, IAM, applications, feature limits |
| **EKS Auto Mode** | AWS automatically manages many compute/network/storage components for workloads under this mode | Want to reduce cluster/EC2 node and autoscaling operations | Intent configuration, workloads, IAM/security, compatibility limits, costs |
| **Hybrid Nodes** (when deployed appropriately) | Nodes can reside on-premises/edge infrastructure per EKS feature | Need to run workloads outside AWS with an EKS control plane | Network connectivity, host/lifecycle, security, latency, service support |

Features and limitations of each mode can change by Region, Kubernetes version, and AWS release. When choosing, check the current **EKS User Guide** and workload prerequisites instead of looking only at the word “managed”.

### 3.3. Managed node groups

**EKS managed node groups** automate the creation and maintenance of EC2 worker node groups, integrating with Auto Scaling groups and supporting node replacement/updates according to service capabilities.

You still need to:

1. Choose appropriate instance family/size, CPU architecture, and AMI.
2. Choose subnets/AZs, security groups, launch templates when used, EBS root volume, and IAM strategy.
3. Set min/desired/max capacity, balancing On-Demand/Spot and redundancy.
4. Ensure compatibility between Kubernetes/control-plane version and node images/add-ons during upgrades.
5. Design resource requests/limits, PDBs, readiness probes, and node draining.
6. Monitor capacity, Pod pending states, image pull errors, disk pressure, and EC2 costs.

**“Managed” does not mean nodes automatically satisfy every scaling requirement**, and a single node group does not automatically run every Pod across multiple AZs. Scaling/controller configurations must be appropriate.

### 3.4. Self-managed nodes

You manage EC2, bootstrap, kubelet, cluster API connectivity, OS configuration, and upgrade workflows yourself. This allows deeper customization, but increases operational overhead and risk:

- Nodes fail to join the cluster even though EC2 is `running`;
- Incorrect AMI/container runtime versions;
- Kubelet missing IAM/network permissions;
- Missing drain procedures before termination;
- Security patches not applied on time.

Choose self-managed nodes only when there is a **clear technical reason** and the operations team has the capability for long-term support.

### 3.5. AWS Fargate for EKS

With **EKS on AWS Fargate**, users define which Pods run on Fargate using **Fargate profiles** and selectors. AWS provisions compute to run Pods without requiring you to directly manage EC2 worker nodes.

Characteristics to consider:

- Fargate Pods in EKS operate under a **distinct networking model** and require suitable subnets; **private subnets** with connectivity to required AWS APIs are commonly used.
- There are limitations with DaemonSets, privileged containers, host/network configurations, and tasks requiring deep host-level permissions.
- Storage differs from EC2/EBS: check support for EFS storage and corresponding volume types.
- Deploying components such as ingress/controllers, logging agents, and monitoring must account for Fargate compatibility.
- Billing is based on provisioned Pod resources per Fargate pricing and related services; it is not identical to EC2 node pricing.

Fargate fits when **both workloads and add-ons are compatible with the Pod-managed model**. It does not eliminate the need to optimize `requests`, authentication, VPC endpoints/NAT, and application troubleshooting.

### 3.6. EKS Auto Mode

**EKS Auto Mode** aims to reduce Kubernetes infrastructure operations by letting AWS automatically manage many aspects such as compute provisioning for Pods, supported networking/load balancing/storage components, and node lifecycles. Core concepts:

- Operators still declare workloads, resource requests, scheduling constraints, and required policies.
- AWS automatically creates/manages compute and integrates certain add-on capabilities according to the Auto Mode design.
- Technical capabilities are not always identical to managed node groups or Fargate; **verify support for DaemonSets, custom AMIs, drivers/controllers, instance types, and networking**.
- Auto Mode has its **own pricing model and limitations** alongside EC2/storage/network components; compare total cost against the operational reduction benefits.

Do not blindly apply manifests to install the AWS Load Balancer Controller or CSI drivers as you would on a traditional cluster without **checking whether Auto Mode already manages the corresponding functionality**.

## 4. Typical Flows: From Deployment to an HTTP Request

### 4.1. A deployment

Suppose you want to run a Java API with 3 replicas:

~~~mermaid
sequenceDiagram
    participant Dev as kubectl / CI-CD
    participant API as EKS API server
    participant ET as etcd
    participant CTR as Kubernetes controllers
    participant SCH as scheduler
    participant K as kubelet on node
    participant RT as container runtime
    Dev->>API: Apply Deployment replicas=3
    API->>API: Authenticate, authorize, validate/admit
    API->>ET: Persist desired state
    CTR->>API: Create ReplicaSet/Pods
    SCH->>API: Read unscheduled Pods and assign node
    K->>API: Watch PodSpecs assigned to node
    K->>RT: Pull image / create containers
    RT-->>K: Container running or failed
    K->>API: Update Pod/Node status
    Dev->>API: kubectl get deploy/pods
~~~

This diagram shows component **roles** rather than modeling every exact API call and watch mechanism. If no node has enough CPU/RAM, the Pod stays `Pending`; if the image is wrong or ECR permissions are missing, the Pod may enter `ImagePullBackOff` even though the control plane is operating normally.

### 4.2. A user request reaching a Pod

A common pattern:

~~~mermaid
flowchart LR
    U[Internet client] --> DNS[Route 53 / DNS]
    DNS --> LB[Application Load Balancer]
    LB --> T[Target group]
    T --> S[Kubernetes Service / Pod targets]
    S --> P1[API Pod - AZ A]
    S --> P2[API Pod - AZ B]
    P1 --> D[(RDS / DynamoDB / S3)]
    P2 --> D
~~~

The exact path depends on the **Service type**, load balancer controller, target mode (instance/IP), CNI, and network configuration. An ALB can route traffic directly to Pod IPs in IP target mode or go through NodePort/instance targets depending on the integration style; not every cluster has an extra NodePort hop in the path.

Key Kubernetes objects:

| Object | Role |
|---|---|
| **Pod** | Common smallest deployable unit of containers |
| **Deployment** | Manages ReplicaSets/rolling updates for stateless Pods |
| **Service (ClusterIP)** | Stable internal DNS/access endpoint inside the cluster |
| **Service (LoadBalancer)** | Can request an external load balancer depending on controller and annotations |
| **Ingress** | HTTP/HTTPS host/path rules, enforced by an Ingress controller |
| **EndpointSlice** | Information about endpoints backing a Service |
| **ConfigMap/Secret** | Configuration and sensitive data with appropriate protections |
| **PVC/PV** | Storage claims and objects with independent lifecycles |

**Note:** simply creating an Ingress/Service does not guarantee the right ALB will be created. You need the **AWS Load Balancer Controller**, EKS Auto Mode integration, or a properly designed controller/provisioner; support depends on cluster configuration.

## 5. Network Boundaries: VPC, Subnets, and EKS Cluster Endpoint

### 5.1. Two different infrastructure scopes

The EKS control plane is managed inside an AWS-operated environment. When creating a cluster, the user provides a VPC and subnets/network settings for the cluster. AWS uses **cross-account network interfaces (ENIs)** in the specified subnets to facilitate communication between the control plane and components inside the customer VPC per EKS design.

~~~mermaid
flowchart TD
    subgraph AWSVPC["AWS-managed VPC / EKS control plane"]
        APISERVER[Kubernetes API servers]
        CP[etcd, scheduler, controller manager]
    end
    subgraph CVPC["Customer VPC"]
        CE[EKS-managed control-plane ENIs]
        SA[Private subnet AZ-A - worker/Pod]
        SB[Private subnet AZ-B - worker/Pod]
        E[Internet/NAT/VPC endpoints as needed]
    end
    APISERVER <-->|EKS managed connectivity| CE
    CE <--> SA
    CE <--> SB
    SA --> E
    SB --> E
~~~

**Do not delete or arbitrarily modify ENIs created by EKS** just because they look like “unowned” resources. They are connectivity components serving EKS. The count and placement of ENIs are managed by the service and may change during cluster operations and upgrades.

### 5.2. Public and private API endpoint access

The Kubernetes API endpoint has access modes tied to the VPC configuration:

| Configuration | Meaning | Security Notes |
|---|---|---|
| **Public endpoint access** | API endpoint has a public access path as configured | Restrict `publicAccessCidrs` where appropriate, enforce strict auth/RBAC |
| **Private endpoint access** | API endpoint is privately reachable from within the VPC by design | Administering from outside the VPC requires appropriate network/DNS paths such as VPN, Direct Connect, or an internal bastion/admin host |
| **Public + private** | Supports both access paths as configured | Still requires CIDR restrictions, IAM, RBAC, and security controls |

**A private API endpoint does not mean workloads are automatically in private subnets**. These are two separate decisions: one governs the **Kubernetes API** access path, while the other governs network connectivity for Pods/EC2 instances and application services.

**Example:** you enable a private-only endpoint, then run `kubectl` from a laptop outside the VPC and hit a timeout. The root cause is likely a **missing network/DNS path**, not missing IAM permissions. Conversely, receiving `Forbidden` means the request likely reached the API but lacks Kubernetes permissions.

### 5.3. Subnets and Availability Zones

A production-ready architecture should:

- Have subnets in **at least two AZs** meeting EKS and workload requirements.
- Distribute nodes and Pods across multiple AZs when the application must tolerate an AZ failure.
- Plan **available IP addresses in subnets**, since AWS VPC CNI allocates Pod addresses per the networking model.
- Review **route tables, NACLs, security groups, NAT Gateways/VPC endpoints** for real dependencies.
- Check quotas and availability for EC2 instance types, EBS, and load balancers in each AZ.

**A multi-AZ EKS control plane does not automatically fix subnet IP exhaustion**. If a subnet runs out of IPs, Pods may fail to initialize networking even if EC2 nodes still have CPU/RAM.

### 5.4. AWS VPC CNI

**Amazon VPC CNI** is the standard networking plugin for EKS running Pods on EC2, allowing Pods to use IP addresses directly associated with the VPC in supported modes. The plugin may require **secondary IPs**, **prefix delegation**, ENIs, and other IP management settings.

Things to monitor:

- Are there enough IP addresses for the desired **Pod density** per node?
- Does the instance type have ENI/IP limits that restrict the number of Pods?
- Are IPv4/IPv6 and custom networking modes configured appropriately?
- Are node security groups and (if supported and enabled) **security groups for Pods** configured accurately?
- Are network policies actually enabled and enforced by the CNI/plugin in use?

**Do not assume Kubernetes NetworkPolicy acts as an active firewall in every EKS cluster.** It requires a supported plugin and configuration; without enforcement enabled, policy manifests may not produce the expected effect.

### 5.5. CoreDNS and kube-proxy

- **CoreDNS:** resolves Kubernetes Service names such as `api.default.svc.cluster.local`, typically run as a Deployment and manageable via an EKS add-on.
- **kube-proxy:** orchestrates part of Service routing on nodes depending on the networking mode; can also be managed via an EKS add-on in supported models.
- **AWS VPC CNI:** implements Pod networking; it does not replace DNS or the Service layer across the entire architecture.

A `DNS lookup failed` symptom can be caused by non-running CoreDNS Pods, upstream resolution failures, network policies, security groups, node networking, or DNS settings; it is not an API server failure by default.

## 6. IAM, Kubernetes RBAC, and Pod Permissions

### 6.1. There are at least three distinct questions

1. **Who can connect to and authenticate with the EKS Kubernetes API?** Involves AWS IAM credentials, EKS cluster authentication/access mechanisms, and the network path.
2. **What is an authenticated identity allowed to do inside Kubernetes?** Involves **Kubernetes RBAC** and Kubernetes authorizers/admission controls.
3. **What AWS APIs is an application running inside a Pod allowed to call?** Involves **IAM roles for workloads** such as EKS Pod Identity or IAM Roles for Service Accounts (IRSA).

You cannot use an IAM policy for `s3:GetObject` to conclude that a user has permission to run `kubectl delete pods`. Conversely, Kubernetes `cluster-admin` permission does not automatically grant Pods permission to call every AWS API.

### 6.2. API Access: IAM + EKS access entries + RBAC

An operator logs in via IAM Identity Center/role; `kubectl` uses the appropriate AWS CLI token flow to authenticate. EKS provides **access entries** and **access policies** to configure access permissions; some older clusters still use the `aws-auth` ConfigMap depending on the selected authentication mode.

~~~text
Operator IAM role
    ↓ AWS token authentication
EKS Kubernetes API
    ↓ EKS access entry / mapping + RBAC or access policy
Allowed Kubernetes API operations
~~~

Secure practices:

- Use temporary **IAM roles** and MFA according to organizational policy.
- Grant only the permissions needed for specific namespaces/administrative groups.
- Check the cluster's authorization mode and access mapping source before making changes.
- Use **Kubernetes Role/RoleBinding** for namespace scope and ClusterRole/ClusterRoleBinding only when truly needed cluster-wide.
- Do not use `system:masters` or `cluster-admin` as a blanket fix for every `Forbidden` error.

Example RBAC in a namespace, granting read-only access to Pods:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: training
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: training
subjects:
  - kind: Group
    name: training-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
~~~

This YAML is for **illustration**; it does not automatically create AWS IAM permissions or add members to the `training-readers` group. You must map identities to the group via the cluster's EKS access mechanism and hold permissions to create RBAC objects to apply it.

### 6.3. Calling AWS APIs from a Pod: IRSA and EKS Pod Identity

For example, a Java API needs to read `s3://school-files/reports/*`. The least-privilege approach is to attach permissions to a **workload identity**, rather than granting `s3:*` on the node IAM role where every Pod would inherit broad permissions.

| Permission Method | High-Level Mechanism | What to Verify |
|---|---|---|
| **IRSA** | Kubernetes service account linked to an IAM role via OIDC and web identity token | OIDC provider, trust policy, service account annotation, SDK, audience, and conditions |
| **EKS Pod Identity** | EKS manages Pod Identity associations; agent and IAM role for Pods in supported modes | Association, IAM trust, agent/permissions, and compute type support |
| **Node IAM role** | Node uses AWS permissions for bootstrap/image pulls/add-ons per configuration | Do not use as general application permissions when dedicated workload IAM options exist |

**Do not mix trust policies between the two methods.** IRSA and EKS Pod Identity use different trust/association mechanisms. Check support across Fargate, EKS Auto Mode, and the current cluster version before choosing; do not assume every method applies uniformly.

A Pod with `serviceAccountName: report-reader` does not automatically have IAM permissions. You must configure the role and identity association per the chosen method.

### 6.4. Additional security responsibilities

- **Pod Security Admission** and security contexts: do not run as root/privileged unnecessarily; restrict capabilities and filesystem writes.
- **Secrets:** never commit passwords to Git; consider AWS Secrets Manager and appropriate CSI/SDK integrations.
- **Image security:** scan images, pin tags/digests per process, and secure ECR.
- **Network:** restrict ingress/egress paths, security groups, and enforced network policies.
- **Encryption:** Kubernetes secrets encryption/KMS per EKS configuration, EBS/EFS/S3 encryption, and standard TLS.
- **Audit:** enable appropriate EKS control plane logs and maintain retention/alerting aligned with compliance requirements.

## 7. Where Do Add-ons and Controllers Sit in the Architecture?

An EKS cluster requires supporting components. Some are **Amazon EKS add-ons** with managed version lifecycles; others are installed by customers via Helm/operators or replaced by managed features in EKS Auto Mode.

| Component | Role | Where does it typically run? | Notes |
|---|---|---|---|
| **Amazon VPC CNI** | Pod IP/networking | Nodes/data plane in supported modes | IAM permissions, IP exhaustion, compatibility |
| **CoreDNS** | DNS for Kubernetes Services | Pods on data plane | Replicas, scheduling, CPU/RAM, health |
| **kube-proxy** | Service traffic routing | On worker nodes in supported models | Version compatibility and datapath |
| **AWS Load Balancer Controller** | Create/manage ALB/NLB for K8s objects | Controller Pods (if self-installed) | IAM, ingress class, tags, subnet discovery |
| **EBS CSI driver** | Provision/mount EBS volumes via CSI | Controller + node components | IAM, AZ binding, PVC, snapshot support |
| **EFS CSI driver** | Access EFS shared file storage | CSI components by design | EFS mount targets, network, permissions |
| **Metrics Server** | Provide resource metrics for HPA when used | Deployment in cluster | HPA metrics, API security, version |
| **Observability agents** | Logs, metrics, tracing | DaemonSet/Deployment or managed features | Cost, retention, compute compatibility |

Add-ons running on EC2 node groups consume their own CPU/RAM capacity; planning capacity solely for application Pods can cause `Pending` or OOM states for system Pods.

### 7.1. Managed add-on does not mean automatic updates at all times

An EKS add-on may have installation/version management supported by AWS, but **do not assume it automatically upgrades alongside the control plane without reviewing configuration**. You must check:

- Cluster/node version compatibility;
- Update mode and preservation policies for custom configurations;
- Appropriate IAM service account/Pod Identity permissions;
- Post-update impact on CNI IP allocation, DNS, and Service routing;
- Rollback or configuration recovery procedures if an update fails.

## 8. Availability: Control Plane HA Differs from Workload HA

### 8.1. Different failure levels

| Incident | Control plane | Data plane/workload | Mitigation |
|---|---|---|---|
| One EC2 node fails | May keep operating | Pods on that node stop running | Replicas, ASG/node replacement, PDB |
| One AZ loses connectivity | Control plane is designed for redundancy | Nodes/Pods/volumes in that AZ may become unavailable | Multi-AZ, topology spread, data replication |
| API endpoint unreachable by operator | May be healthy, but network/auth is misconfigured | Existing workloads may continue running depending on dependencies | Private access, VPN/DNS, check IAM/RBAC |
| All Pods placed on a single node | Not immediately affected | Application outage when node fails | Replicas spread across nodes/AZs, anti-affinity |
| Cluster runs out of Pod IPs | Still accepts API requests | New Pods fail network initialization | VPC/subnet capacity, CNI/IP monitoring |
| Image registry or IAM error | Still accepts desired state | New Pods stuck in `ImagePullBackOff` | ECR/network/permissions/rollout validation |
| Single point of failure database | Keeps operating | API fails even while Pods are `Running` | RDS Multi-AZ or replication and recovery |
| Accidental manifest deletion | Control plane executes the valid request | Workloads deleted or configuration lost | RBAC, GitOps/IaC, backups, reviews |

### 8.2. Distributing Pods across AZs

Kubernetes supports **topology spread constraints** and **pod anti-affinity** to control Pod placement. However, this only works when:

- Nodes are available in the required AZs;
- Sufficient CPU/RAM and IP addresses exist;
- Scheduler constraints do not conflict;
- Storage/volume topology is compatible with Pod placement;
- Autoscalers can provision capacity in the appropriate AZs.

Illustrative Pod template configuration snippet:

~~~yaml
spec:
  replicas: 3
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: api
          image: example.invalid/catalog-api:replace-me
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
~~~

**`ScheduleAnyway` only prefers distribution** and does not strictly guarantee Pods are spread across multiple AZs. If you need a hard constraint, evaluate `DoNotSchedule`, `minDomains`, and the availability impact when an AZ lacks capacity; do not enforce hard constraints if leaving Pods `Pending` harms your SLA more.

### 8.3. Replicas, readiness, and PodDisruptionBudget

For stateless HTTP APIs, you typically need:

1. A Deployment with **multiple replicas** and proper distribution.
2. A **Readiness probe** reflecting actual ability to serve requests, preventing traffic from reaching unready applications.
3. A **Liveness probe** only for conditions that genuinely require a restart; misconfigured liveness probes can trigger continuous Pod restarts.
4. A **Startup probe** if Java applications start slowly.
5. A **PodDisruptionBudget (PDB)** to limit **voluntary disruptions** during drains/upgrades according to controller behavior.
6. Graceful termination, `preStop` or shutdown hooks, and appropriate termination grace periods to reduce errors on in-flight requests.

Example PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-api-pdb
  namespace: training
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: catalog-api
~~~

A PDB **cannot prevent unexpected infrastructure failures**. It can block drain/upgrade operations when insufficient healthy replicas remain, so it must be paired with proper capacity and rollout strategies.

## 9. Scheduling and Auto Scaling: Scaling Pods vs. Scaling Nodes

### 9.1. Three common scaling layers

| Layer | Tools/Mechanisms | What does it adjust? |
|---|---|---|
| **Workload** | Horizontal Pod Autoscaler (HPA), KEDA, or equivalent controller | Number of Pod/controller replicas |
| **Compute capacity** | Cluster Autoscaler, Karpenter, EKS Auto Mode depending on choice | Number/types of nodes and infrastructure capacity |
| **Vertical resources** | Vertical Pod Autoscaler or manual tuning | Pod `requests/limits` per policy |

~~~mermaid
flowchart TD
    M[CPU / custom metrics / queue depth] --> H[HPA or event-driven scaler]
    H --> R[Deployment: increase replicas]
    R --> S{Do Pods have enough node capacity?}
    S -->|Yes| P[Pods Running]
    S -->|No| Q[Pods Pending]
    Q --> N[Node autoscaler / EKS Auto Mode]
    N --> C[Add nodes/compute if quotas and AZ allow]
    C --> P
~~~

**HPA does not automatically provision EC2 nodes**, and a node autoscaler does not automatically increase application replicas without an appropriate demand signal/controller. If `requests.cpu` is too large or subnets lack IPs, increasing node size/count without investigation may still fail to resolve pending Pods.

### 9.2. Resource requests and limits

- **Requests** help the scheduler evaluate capacity for Pod placement.
- **Limits** cap resources via kernel/runtime mechanisms; CPU limits can cause throttling, while memory limits can lead to OOM kills.
- Setting requests too low can overcommit nodes; setting them too high wastes capacity or leaves Pods `Pending`.
- CPU-based HPA typically evaluates utilization relative to **requests**; poorly chosen requests make scaling signals difficult to interpret.

For Java/JVM, consider container memory awareness, JVM heap/non-heap, GC, startup, and readiness. Do not set the memory limit equal to `-Xmx`, because native memory, threads, metaspace, and agents also require memory.

### 9.3. Spot and multiple node types

Use Spot to reduce compute costs for interruptible workloads, combined with:

- Multiple compatible instance families/sizes;
- Node disruption handling and graceful termination;
- Appropriate PDBs, though do not expect PDBs to block all Spot interruptions;
- Replicas and On-Demand capacity for critical components;
- Externalized state or data replication outside nodes.

If a workload requires durable data, consider **RDS/Aurora/DynamoDB/S3/EFS/EBS** based on architecture and AZ scope; never store critical data only on the container filesystem assuming Pods can reschedule without data loss.

## 10. EBS, EFS, and Storage for Pods

### 10.1. A PersistentVolume is not an independent server

Kubernetes manages storage claims through **PersistentVolumeClaim (PVC)**, **PersistentVolume (PV)**, StorageClass, and **CSI drivers**. The actual backend is an AWS service with its own lifecycle, durability, and cost characteristics.

| Storage | Usage Pattern | Key Constraints |
|---|---|---|
| **EBS** | Block storage, suited for a single Pod/stateful app under supported attachment models | Volumes are bound to an AZ; when a Pod moves to another AZ, proper provisioning/recovery design is needed |
| **EFS** | Shared NFS filesystem | Requires network, mount targets, IAM/access points, and performance modes as needed |
| **S3** | Object storage/API | Not a typical block/filesystem PVC; use SDK/API or suitable integration |
| **Ephemeral container storage** | Temporary cache/tmp/build artifacts | Can be lost when Pods/nodes are replaced or terminated |

**An EBS volume in one AZ does not automatically migrate to another AZ when a Pod is rescheduled.** For stateful applications, you must design storage class topology, backups/snapshots, and application-layer replication. A multi-AZ EKS cluster does not make a single EBS volume multi-AZ.

### 10.2. Which layer does a CSI controller belong to?

For example, the EBS CSI driver has controller and node plugin components running on the data plane in supported models. They interact with the Kubernetes API, AWS EBS APIs, and kernel/volume attachments. The driver **is not part of the default AWS-managed Kubernetes control plane in the same sense as etcd/API server**, though it can be managed as an EKS add-on or via corresponding Auto Mode functionality.

## 11. EKS Pricing and Cost Control

### 11.1. Common cost items

| Item | Cost Source | Recommendation |
|---|---|---|
| **EKS cluster/control plane** | Hourly cluster fee and Kubernetes version support tier in effect | Clean up lab clusters, upgrade versions on schedule to avoid extended support if unneeded |
| **EC2 worker nodes** | Instance hours, purchase option, EBS root/data, public IPv4 | Right-sizing, autoscaling, On-Demand/Spot |
| **Fargate** | Pod resources provisioned per configuration/support | Set reasonable requests, shut down unused workloads |
| **EKS Auto Mode** | Compute/infrastructure components plus corresponding Auto Mode fee model | Compare total cost against reduced operational effort |
| **Networking** | NAT Gateway, cross-AZ data transfer, ALB/NLB, VPC endpoints | VPC design, measure traffic, and use endpoints where appropriate |
| **Storage** | EBS, EFS, S3, snapshots/backups | Lifecycle, encryption, retention, and capacity |
| **Logging/monitoring** | CloudWatch Logs, metrics, Container Insights, tracing | Select log types, retention, and sampling |
| **Other** | ECR image storage/data transfer, Route 53, WAF, KMS requests | Tagging, Cost Explorer, budgets, cost allocation |

Pricing **varies by Region, support version, compute type, and time**. Do not treat any hourly rate in a lesson as a financial commitment; consult [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/) and the AWS Pricing Calculator.

### 11.2. Labs still incur costs with no applications running

Even when `kubectl get pods` shows none of your workloads, an **EKS cluster may still incur control plane fees**, and EC2/node groups, NAT, EBS, load balancers, and logs may still be running. A small workload on EKS is not necessarily cheaper than **Lambda**, **ECS Fargate**, or a single EC2 instance; choose EKS when there is a valid reason for Kubernetes orchestration, ecosystem capabilities, or operational requirements.

### 11.3. Cost governance

- Apply consistent tags to clusters, node groups, and related resources per organizational policy.
- Set AWS Budgets and alerts; **a budget does not automatically block all spending by default**.
- Document owner, environment, expected lab cleanup date, and log retention period.
- Use Cost Explorer/Cost and Usage Reports when authorized to analyze compute, EKS, NAT, and storage spend.
- After cleaning up Kubernetes workloads, always verify whether **AWS resources created by controllers** such as ALBs/NLBs/EBS volumes still remain.

## 12. Read-Only Practice: Exploring an Authorized EKS Cluster

> **Prerequisites:** an existing sandbox EKS cluster, AWS CLI v2, a compatible `kubectl`, and least-privilege permissions to view the cluster. This lab **does not create, update, upgrade, or delete an EKS cluster**. If no cluster is provisioned for you, complete the architecture analysis and exercises instead of creating a new cluster yourself.

### 12.1. Step 1 — Verify account and Region

Bash example:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws eks list-clusters --region "$REGION" --profile "$AWS_PROFILE"
~~~

Adjust the profile and Region to match your sandbox. If using AWS CloudShell **without an `aws-lab-dev` profile**, omit the `export AWS_PROFILE=...` line and `--profile` flags to use your current session credentials. Verify `Account`/`Arn` and the cluster list before continuing.

**Permissions note:** an IAM identity with `eks:ListClusters` permission does not necessarily have permission to access the Kubernetes API or run `kubectl get pods`. These are two separate permission levels.

### 12.2. Step 2 — Inspect the control plane and endpoint

~~~bash
CLUSTER_NAME=aws-lab-eks

aws eks describe-cluster \
  --name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --query 'cluster.{Name:name,Status:status,Version:version,Endpoint:endpoint,Platform:platformVersion,Subnets:resourcesVpcConfig.subnetIds,SecurityGroups:resourcesVpcConfig.securityGroupIds,ClusterSecurityGroup:resourcesVpcConfig.clusterSecurityGroupId,PublicAccess:resourcesVpcConfig.endpointPublicAccess,PrivateAccess:resourcesVpcConfig.endpointPrivateAccess,Logging:logging.clusterLogging}' \
  --output json
~~~

The cluster name above is **only an example** and should be replaced with your assigned sandbox cluster. Inspect:

| Field | What to verify |
|---|---|
| `status` | `ACTIVE`, creating/updating, or other status |
| `version` | Cluster Kubernetes version |
| `endpoint` | EKS-provided Kubernetes API server URL |
| `subnetIds` | Subnets declared in the cluster VPC config |
| `endpointPublicAccess` / `endpointPrivateAccess` | Kubernetes API access paths |
| `clusterSecurityGroupId` | Security group created/managed by EKS for the cluster per configuration |
| `clusterLogging` | Log types enabled/disabled on the EKS control plane |

**Do not** attempt to modify the cluster security group or ENIs without understanding the system connections they serve.

### 12.3. Step 3 — Inspect managed node groups, Fargate profiles, and add-ons

~~~bash
aws eks list-nodegroups \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"

aws eks list-fargate-profiles \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"

aws eks list-addons \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"
~~~

An empty node group list **does not mean there is no worker/data plane**: the cluster may use Fargate, self-managed nodes, or other compute modes. With EKS Auto Mode, inspect the **cluster compute configuration** per the supported API version; do not draw absolute conclusions from `list-nodegroups` alone.

If an actual managed node group exists:

~~~bash
NODEGROUP_NAME=aws-lab-workers

aws eks describe-nodegroup \
  --cluster-name "$CLUSTER_NAME" \
  --nodegroup-name "$NODEGROUP_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --query 'nodegroup.{Status:status,InstanceTypes:instanceTypes,CapacityType:capacityType,Subnets:subnets,Scaling:scalingConfig,Version:version,Release:releaseVersion,Health:health}' \
  --output json
~~~

Check instance types, subnets/AZs, min/desired/max capacity, and health issues.

### 12.4. Step 4 — Prepare kubeconfig and perform read-only Kubernetes API inspection

`aws eks update-kubeconfig` **only updates kubeconfig on your local machine**, modifying contexts/entries in your local file. Before running it, back up your current configuration if needed and avoid overwriting a shared kubeconfig. Example:

~~~bash
aws eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --alias aws-lab-eks-readonly
~~~

This command **does not change AWS resources**; it configures local client access. To stay safe, always verify your current context:

~~~bash
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -A -o wide
~~~

If `kubectl` reports `Unauthorized/Forbidden`, inspect your IAM identity, EKS access entries or legacy mapping, Kubernetes RBAC, and access policies; **do not add cluster-admin yourself**.

If the endpoint is private-only, the host running `kubectl` must sit in a network with an appropriate route/DNS path to the cluster endpoint. Updating kubeconfig will not automatically create a VPN or route.

### 12.5. Step 5 — Distinguish control plane vs. data plane components

Inspect permitted system objects:

~~~bash
kubectl get pods -n kube-system -o wide
kubectl get deployments -n kube-system
kubectl get daemonsets -n kube-system
kubectl get services -n kube-system
kubectl get nodes -L topology.kubernetes.io/zone
~~~

For example, you may see `coredns`, `aws-node`, `kube-proxy`, and agents depending on configuration. Compare:

- **CoreDNS Pods:** do they belong to the data plane?
- **VPC CNI components:** which Pods/DaemonSets are used?
- **Control-plane `etcd`:** does it appear as a Pod you manage in `kube-system`?
- Are nodes distributed across multiple AZs?
- Is node readiness healthy?

**Not seeing `etcd` in the namespace** is normal behavior with an AWS-managed control plane; it does not mean EKS lacks etcd.

### 12.6. Step 6 — Inspect Deployments, Services, and Pod placement

If the `training` namespace exists and you have read permissions:

~~~bash
kubectl get deployments -n training
kubectl get pods -n training -o wide
kubectl get services -n training
kubectl get events -n training --sort-by=.lastTimestamp
~~~

Analyze:

1. How many `DESIRED/READY/AVAILABLE` replicas are there?
2. On which nodes/AZs are Pods running?
3. Are any Pods pending due to insufficient resources, scheduling constraints, or lack of IPs?
4. Does the Service have `ClusterIP` or `LoadBalancer`; does an ingress/load balancer exist?
5. What events does `kubectl describe pod <pod-name> -n training` display? **Note** that descriptions may expose metadata or sensitive environment details depending on workload configuration; inspect only within your authorized scope.

### 12.7. Step 7 — Observation questions

From the read-only commands, answer:

- The cluster has an EKS-managed control plane; can you see the API servers/etcd machines as EC2 instances in your account?
- What type are the worker nodes, and in which subnets/AZs are they located?
- What are the node group's min/desired/max limits?
- How is the cluster using public/private API endpoints?
- Which system Pods such as CoreDNS/CNI/kube-proxy run on the data plane?
- If a Pod is `Pending`, what additional information from scheduler events and nodes do you need to determine the cause?

**You do not need to run `kubectl apply` or create an EKS cluster** to complete the core lab.

## 13. Example Manifest: Deployment and Service on the Data Plane

This is a **reference example**, not a mandatory deployment command. The image name `example.invalid` is an intentional placeholder; if applied, it must be replaced with a real image that has been built, scanned, approved, and matches the CPU architecture.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: training
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      serviceAccountName: catalog-api
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: catalog-api
          image: example.invalid/catalog-api:replace-me
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: training
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - port: 80
      targetPort: 8080
~~~

What the manifest **can do** if deployment conditions are valid:

- The Deployment declares **3 Pods** with label `app: catalog-api`.
- The scheduler selects nodes based on capacity/constraints and topology preferences.
- kubelet on the nodes creates containers.
- The `ClusterIP` Service provides an in-cluster access point to ready endpoints.

What the manifest **does not do automatically**:

- Does not create an IAM role/Pod Identity association for the `catalog-api` service account.
- Does not expose the API to the Internet, since `ClusterIP` is only for in-cluster access.
- Does not guarantee 3 Pods distributed across multiple AZs if the cluster lacks capacity.
- Does not create a database, secrets, load balancer, or persistent volume.
- Does not guarantee the real application implements `/ready` or that the image exists.
- Does not replace production PodDisruptionBudgets, policies, or monitoring.

If you want to deploy in a sandbox, you must create the namespace/service account with proper permissions, prepare the image, review resource requests, and confirm other workloads are unaffected. For production, use Helm/IaC/GitOps and an appropriate review pipeline.

## 14. Diagnosing Issues Across the Control Plane and Data Plane

### 14.1. Troubleshooting table

| Symptom | Layer to Check | Suspected Cause | Tools/Observations |
|---|---|---|---|
| `kubectl` times out reaching endpoint | API connectivity | Private endpoint, DNS/VPN/routing/firewall | `describe-cluster`, DNS, and client network path |
| `kubectl` returns `Unauthorized` | Authentication | Incorrect IAM credentials/token or missing mapping | `sts get-caller-identity`, access entries/mode |
| `kubectl` returns `Forbidden` | Kubernetes authorization | Missing RBAC/access policy permissions | `kubectl auth can-i` if permitted |
| EC2 `running` but node fails to join | Data plane bootstrap | Kubelet/AMI/role, cluster endpoint/DNS, networking | EKS node group health, node/bootstrap logs |
| Pod `Pending` with `Insufficient cpu` | Scheduling/capacity | Nodes lack CPU per requests | `kubectl describe pod`, node allocatable |
| Pod `Pending` despite available CPU | Scheduling constraints | AZ/taints/nodeSelector/PVC constraints | Pod events and affinity/volume topology |
| Pod lacks IP or stuck in `ContainerCreating` | Networking/CNI | Subnet IP exhaustion, CNI/ENI permissions, plugin error | CNI logs, subnet addresses, Pod events |
| Pod `ImagePullBackOff` | Runtime/registry | Wrong image tag, ECR credentials, network path | Events, ECR/network/role |
| Pod `CrashLoopBackOff` | Application/startup | App crash, OOM, misconfigured probe, missing config | `kubectl logs --previous`, describe Pod |
| `kubectl get svc` shows ClusterIP but unreachable externally | Exposing traffic | Missing Ingress/LoadBalancer or DNS/network | Service type, controller, ALB/NLB |
| Service DNS does not resolve | Cluster DNS | CoreDNS unhealthy or plugin/network error | `kube-system` Pods, CoreDNS logs |
| ALB healthy but API returns 5xx | Application/dependency | DB/secret/permission/timeout | Logs/traces, downstream metrics |
| Control plane logs missing in CloudWatch | Observability config | Log types not enabled or retention/view permissions | `describe-cluster` logging, CloudWatch |
| HPA scales Pods but they stay `Pending` | Compute autoscaling | Node autoscaler not adding capacity, quotas/AZ | HPA, events, Karpenter/CA logs |
| Many EC2 nodes with high cost, low load | Cost/capacity | Requests too high, node group min too high, idle nodes | CPU/memory usage, AWS billing, autoscaler |
| Workloads fail after control plane upgrade | Version compatibility | Deprecated APIs/add-ons/drivers/node mismatch | EKS upgrade insights, release notes, logs |

### 14.2. Diagnostic sequence

~~~text
1. Verify AWS account, Region, cluster name, and access mode.
2. Is the API server reachable? (DNS / route / endpoint)
3. Is the request failing with Unauthorized or Forbidden? (IAM + RBAC)
4. What is the cluster status / node health / add-on status?
5. Is the Pod Pending, ContainerCreating, Running, or CrashLoopBackOff?
6. Are scheduler events, resources, taints, and topology constraints valid?
7. If containers are running, are readiness and Service endpoints correct?
8. Inspect CoreDNS, VPC CNI, Ingress/LB, and SG/VPC routing.
9. Inspect workload IAM, secrets, storage, and AWS API dependencies.
10. Monitor SLOs and costs, apply the minimal change, and re-test.
~~~

### 14.3. Do not confuse component status with business health

- **Cluster `ACTIVE`:** the cluster is marked active by EKS, which does not prove the application is healthy.
- **Node `Ready`:** kubelet/node is relatively ready, which does not prove all containers are functioning properly.
- **Pod `Running`:** the Pod is scheduled and containers may be running; it does not prove business endpoints return valid responses.
- **Readiness `True`:** a single application check passed; it does not prove every dependency or checkout path works.
- **ALB target healthy:** health check passed; it does not prove all API routes are error-free.

Monitoring should include **metrics, logs, traces, business transactions, and synthetic checks** based on system requirements.

## 15. Case Study: Course Platform Running on EKS

### 15.1. Requirements

An online learning system needs to operate:

- A Java/Spring Boot **Frontend API** with traffic peaking during study hours, requiring HA.
- **Video thumbnail workers** processing a queue, supporting retries.
- **RDS** storing learner data, **S3** storing videos and materials.
- **Secrets Manager** holding centrally managed configuration credentials.
- Tracked costs, centralized logs, and least-privilege IAM.
- A production environment able to tolerate **losing one worker node** and minimize impact when one AZ experiences an outage.

### 15.2. Reference design

~~~mermaid
flowchart TD
    U[Learners] --> CF[CloudFront / DNS]
    CF --> ALB[ALB HTTPS + WAF if needed]
    ALB --> S[Kubernetes Service]
    subgraph EKS["EKS cluster - AWS-managed control plane"]
        CP[Managed K8s API / Scheduler / etcd]
    end
    subgraph VPC["VPC private subnets - 2+ AZs"]
        subgraph A["AZ A"]
            API1[API pods]
            WORK1[Worker pods]
        end
        subgraph B["AZ B"]
            API2[API pods]
            WORK2[Worker pods]
        end
        RDS[(RDS Multi-AZ as required)]
        Q[SQS queue]
    end
    S --> API1
    S --> API2
    API1 --> RDS
    API2 --> RDS
    Q --> WORK1
    Q --> WORK2
    WORK1 --> S3[(S3)]
    WORK2 --> S3
    CP -. Orchestrates .-> API1
    CP -. Orchestrates .-> API2
~~~

**Diagram note:** “EKS cluster - AWS-managed control plane” is drawn separately to emphasize management responsibilities; the Pods/Services in the diagram are actually Kubernetes resources belonging to **the same EKS cluster**, running on the data plane in the customer VPC.

### 15.3. Design decisions

| Area | Recommendation | Rationale |
|---|---|---|
| Control plane | Amazon EKS managed | Avoid managing API/etcd infrastructure yourself |
| API compute | Managed node groups or suitable Auto Mode | Provides nodes/compute for HTTP Pods; measure load and capacity |
| Batch compute | Node groups supporting Spot or suitable compute | Workloads with retry/checkpointing, optimize costs |
| AZs | Worker capacity across multiple AZs | Reduce impact of node/AZ failures |
| Deployment | >= 2 replicas, topology spread, readiness, PDB | Minimize downtime during drains/updates |
| Networking | Private subnets, VPC CNI, ALB ingress via controller | Protect workloads and standardize ingress paths |
| Workload IAM | IRSA or EKS Pod Identity per support | Separate S3/SQS/Secrets permissions from node IAM role |
| Storage | S3, managed RDS; PVC only where required | Durable data outside the Pod lifecycle |
| Scaling | HPA + node autoscaler/Auto Mode | Balance replicas and infrastructure |
| Observability | EKS logs + workload metrics/logs/traces | Separate orchestration errors from application errors |
| Recovery | Backups/snapshots, GitOps, AZ/node failure drills | Meet RTO/RPO and rebuild configuration |
| Cost | Budgets + tags + right-sizing | Avoid idle clusters incurring uncontrolled charges |

### 15.4. Reasoning questions

1. If `kubectl apply` succeeds but there are no nodes, can the Deployment run Pods?
2. Should CoreDNS be considered a machine inside the AWS-managed etcd/control plane?
3. Why does a cluster with an HA control plane still need Deployment replicas distributed across multiple AZs?
4. If all application Pods are `Running` yet the ALB returns 503, which layers should you inspect?
5. How do IRSA/EKS Pod Identity and EKS access entries differ in purpose?
6. Why shouldn't an API Pod rely on a node IAM role with `s3:*`?
7. When HPA increases replicas but Pods remain Pending, what constraints could be involved?
8. Can a PVC backed by an EBS volume in AZ A automatically attach to a node in AZ B?
9. When upgrading the Kubernetes control plane version, why do you still need to check CNI/CoreDNS/kube-proxy/node images?
10. If you stop all Deployments in a lab, why might your EKS bill still increase?
11. Is Fargate suitable for a workload requiring a privileged DaemonSet and host kernel operations?
12. Does `Cluster ACTIVE` mean the system meets p99 latency and business SLOs?

**Brief answer hints:**

1. No, the scheduler still needs capacity to place Pods.
2. No, CoreDNS typically runs as Pods on the data plane.
3. Because control plane HA does not automatically resolve application/node/AZ single points of failure.
4. Listener/target health, Ingress controller, Service endpoints, security groups, and backend.
5. Access entries/RBAC govern **Kubernetes API administration**; IRSA/Pod Identity govern **Pods calling AWS APIs**.
6. To avoid granting broad permissions to every Pod and widening blast radius if a node/container is compromised.
7. Compute capacity, quotas, AZ/subnet IPs, taints/affinity, node autoscaler.
8. No; EBS volumes have AZ affinity and require appropriate data recovery/replication mechanisms.
9. To avoid version/API incompatibilities and network/plugin regressions.
10. Control plane, EC2 nodes, storage, NAT, and ALB/logs may still incur charges.
11. Usually not; review Fargate limitations and choose an appropriate compute model.
12. No; you must monitor application health and metrics.

## 16. Common Misconceptions

**“EKS is completely serverless Kubernetes.”** Inaccurate. EKS manages the control plane, while the data plane can be EC2-managed/self-managed, Fargate, or EKS Auto Mode with differing management levels.

**“Having an EKS cluster means you already have worker nodes.”** Not always true. A cluster may have no compute provisioned yet, no Fargate configured, or nodes failing to join.

**“EKS runs CoreDNS/kube-proxy inside the control plane, so I don't need capacity for them.”** In traditional EC2 data plane models, CoreDNS, CNI/kube-proxy typically run on the data plane or via AWS-supported integrations; always verify the actual configuration.

**“The cluster spans three AZs, so all application Pods will also span three AZs.”** False. The scheduler needs worker capacity and appropriate constraints; it does not automatically replicate Pods and data across control plane AZs.

**“`kubectl Unauthorized` and `Forbidden` both just need IAM `AdministratorAccess` added.”** False. You must distinguish authentication, EKS access configuration, and Kubernetes RBAC; granting overly broad permissions breaks least privilege.

**“A Kubernetes Service of type ClusterIP always creates an ALB.”** False. ClusterIP is for internal services; Internet exposure requires an ingress/load balancer or another appropriate mechanism.

**“If a Pod is `Running`, the application is healthy.”** False. You need readiness probes, health checks, and SLO monitoring.

**“An EBS PVC automatically migrates between two AZs.”** False. EBS volumes are bound to an AZ; storage/replication design must reflect this characteristic.

**“HPA will automatically provision new EC2 instances when scaling up replicas.”** Not automatically; node autoscaling/compute provisioning must be configured appropriately.

**“With no Pods, EKS incurs zero charges.”** False. The control plane and other cloud resources may still be running and accruing charges.

## 17. Pre-Production Checklist for EKS

### Architecture and Operations

- [ ] Distinguish the AWS-managed control plane from the actual data plane.
- [ ] Have a clear compute choice: managed node groups, Fargate, Auto Mode, or self-managed.
- [ ] Verified Kubernetes version, upgrade lifecycle, add-on compatibility, and quotas.
- [ ] VPC/subnets/AZs have sufficient IP addresses, routes, DNS, and appropriate security groups.
- [ ] Kubernetes API endpoint access is restricted per operational/security requirements.
- [ ] Application Deployments have appropriate resource requests/limits and probes.
- [ ] Replicas and scheduling topology meet node/AZ failure requirements.
- [ ] HPA and compute/node autoscaling are configured for demand and tested under capacity exhaustion.
- [ ] PVC/EBS/EFS/S3 strategy and backup/restore plans align with RPO/RTO.
- [ ] Upgrade and rollback plans exist for workloads/add-ons/infrastructure.

### Security and Cost

- [ ] IAM roles for cluster/nodes/controllers/workloads follow least privilege.
- [ ] EKS access entries/legacy mappings and Kubernetes RBAC are reviewed.
- [ ] Applications use workload identity rather than embedding AWS credentials inside Pods.
- [ ] Pod security, image scanning, secrets, TLS, and network policies are verified.
- [ ] EKS control plane logs and workload observability are enabled as needed.
- [ ] Alerts exist for Pod Pending/OOM/CrashLoop, node health, DNS/CNI, and latency/error rates.
- [ ] Tagging, AWS Budgets, Cost Explorer, and retention policies for logs/storage are in place.
- [ ] Runbooks exist to clean up clusters/node groups/load balancers/EBS/NAT in sandboxes.
- [ ] At least node failure and failed rollout scenarios have been rehearsed.

**Expected outcome:** You can describe the **AWS-managed control plane and the data plane provided by compute models**, trace the path from `kubectl apply` to Pod and from client to Service, identify IAM/network/add-on responsibilities, and recommend resilient, observable, and cost-controlled EKS operations.

## Official AWS Documentation

- [What is Amazon EKS?](https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html)
- [Amazon EKS architecture](https://docs.aws.amazon.com/eks/latest/userguide/eks-architecture.html)
- [Amazon EKS cluster endpoint access control](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html)
- [Amazon EKS managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)
- [AWS Fargate for Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html)
- [Amazon EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html)
- [Amazon EKS Hybrid Nodes](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-overview.html)
- [Amazon EKS access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Amazon VPC CNI for Kubernetes](https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html)
- [Amazon EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html)
- [Amazon EKS control plane logging](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/)
- [Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/)
- [Kubernetes Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

> **Implementation note:** Cluster names, ARNs, profiles, example manifests, and commands in this lesson are for training purposes and do not confirm the existence of actual clusters or images. EKS releases, compute models, pricing, add-on compatibility, and network limits vary by Region and version. Before creating or upgrading live systems, consult current AWS/Kubernetes documentation, test in a sandbox, and follow change approval processes.
