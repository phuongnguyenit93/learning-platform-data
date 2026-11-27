# Network Policy Security and Multi-AZ EKS Operations

An **Amazon Elastic Kubernetes Service (Amazon EKS)** cluster can run hundreds of Pods across multiple namespaces and multiple **Availability Zones (AZs)**. Even though those Pods reside inside VPC subnets, you should never assume they are isolated from one another by default. A compromised application can attempt to reach other internal services; conversely, overly restrictive **NetworkPolicy** rules can break DNS, database connections, or health checks.

On the availability side, creating an EKS cluster with multiple subnets **does not automatically distribute Pods evenly across AZs**. A three-replica Deployment can still land all three Pods on a single node or a single AZ without appropriate scheduling constraints. When that AZ experiences an outage, the application goes down even though the EKS control plane keeps running.

This lesson belongs to the **Kubernetes with EKS** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless so learners can design secure, observable, resilient, and cost-controlled applications.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **Kubernetes NetworkPolicy**, **security groups**, **network ACLs**, **IAM**, and **Kubernetes RBAC** by their exact protection layers.
2. Explain **default allow**, **default deny**, additive policy evaluation, **ingress**, and **egress**.
3. Author policies restricting **frontend → API → backend** traffic while permitting DNS and genuinely needed connections.
4. State prerequisites, limits, and enablement steps for NetworkPolicy with **Amazon VPC CNI**, including **standard/strict enforcement**.
5. Design multi-AZ EKS using **node groups**, **topology spread constraints**, **PodDisruptionBudgets**, health probes, and autoscaling.
6. Explain AZ constraints of **Amazon EBS**, the role of **EFS**, backups, and Multi-AZ database services.
7. Use **kubectl** and **AWS CLI** to inventory and troubleshoot network policies, scheduling failures, Pod IP exhaustion, and AZ outages.
8. Build runbooks for deployments, upgrades, monitoring, recovery, and EKS operational cost estimation.

## 2. Responsibility Model: What EKS Manages vs. What We Manage

Amazon EKS manages the **Kubernetes control plane** for high availability per AWS architecture, deploying control plane components across multiple AZs. Users still manage most of the **data plane** configuration, workloads, Kubernetes add-ons, IAM, networking, data, and deployment workflows. Available compute options include **EC2 managed node groups**, self-managed nodes, Fargate, and managed modes such as **EKS Auto Mode**, each carrying distinct limits and responsibilities.

| Component | Role | What the Organization Remains Responsible For |
|---|---|---|
| **EKS control plane** | AWS-managed Kubernetes API server and orchestration components | Version upgrades, endpoint access, authentication/authorization, and cluster configuration |
| **EC2 worker nodes / node groups** | Supplies CPU, RAM, networking, and storage for Pods | AZ distribution, sizing, node updates, node IAM role, OS/add-ons |
| **Kubernetes scheduler** | Places Pods onto nodes per declared constraints | Replicas, resource requests, affinity, topology spread, tolerations |
| **Amazon VPC CNI** | Allocates Pod IPs and VPC networking | IP/subnet config, network policy enforcement where supported, add-on upgrades |
| **CoreDNS / kube-proxy and network components** | Internal DNS and Service routing per config | Availability, scaling, security, updates, and metrics |
| **Application workloads** | Serve APIs, process jobs, persist data | Health checks, retries, graceful shutdown, durable data, SLOs |

**Distinguish control plane HA from workload HA:** a cluster can still answer **kubectl** commands even after an application loses all its Pods in a failed AZ. Similarly, if all worker nodes sit in one AZ, control plane HA cannot save the service.

### 2.1. Illustrative multi-AZ EKS architecture

~~~mermaid
flowchart TB
    USER["Clients / Route 53"] --> ALB["ALB / Kubernetes Ingress"]
    CP["EKS control plane<br/>AWS-managed multi-AZ"] -. "Kubernetes scheduling / API" .-> NG["EC2 worker node groups"]
    subgraph VPC["VPC within one AWS Region"]
        subgraph AZA["AZ A"]
            NA["Node A"]
            PA["API Pod A"]
        end
        subgraph AZB["AZ B"]
            NB["Node B"]
            PB["API Pod B"]
        end
        subgraph AZC["AZ C"]
            NC["Node C"]
            PC["API Pod C"]
        end
        NA --> PA
        NB --> PB
        NC --> PC
    end
    NG --> NA
    NG --> NB
    NG --> NC
    ALB --> PA
    ALB --> PB
    ALB --> PC
    PA --> DB["RDS / DynamoDB<br/>Data decoupled from Pods"]
    PB --> DB
    PC --> DB
~~~

This diagram shows an architectural goal, **not an automatic guarantee**. Production requires worker capacity across multiple AZs, scheduling constraints, healthy targets, proper networking, and resilient backends.

## 3. Five Easily Confused Security Layers

| Mechanism | Scope and Enforcement | Example |
|---|---|---|
| **Kubernetes NetworkPolicy** | Controls **L3/L4** traffic to/from selected Pods; requires enforcing network plugin | Only **frontend** Pods may call **api** Pods on TCP 8080 |
| **Security group** | Filters traffic at ENIs/VPC resources; attachable to Pods in supported configs | Only authorized workloads may connect to RDS on TCP 5432 |
| **VPC network ACL** | Stateless filtering at subnet boundaries | Allow or deny IP ranges/ports entering or leaving a subnet |
| **AWS IAM / EKS Pod Identity / IRSA** | AWS API permissions, such as S3, SQS, DynamoDB | Pod role may only invoke **s3:GetObject** on a specific bucket |
| **Kubernetes RBAC / EKS access entries** | Who may call the **Kubernetes API** and operate on cluster resources | Ops team can view Pods but cannot create ClusterRoles |

**NetworkPolicy neither grants nor revokes IAM permissions.** Blocking a Pod from talking over TCP to another service does not block **s3:PutObject**. Conversely, a role limited to read-only S3 does not block TCP traffic from that Pod to another Pod.

Comprehensive defense requires evaluating **multiple layers simultaneously**: identity and API permissions, networking, TLS encryption, application configuration, admission control, image security, runtime security, and observability.

## 4. Kubernetes NetworkPolicy: Evaluation Rules

**NetworkPolicy** is a standard Kubernetes API in the **networking.k8s.io/v1** group, scoped to **Pods in a namespace**. A policy uses **podSelector** to select target Pods and declares allowed **ingress/egress** connections.

### 4.1. Default allow when no policy selects a Pod

Under standard Kubernetes semantics:

- A Pod **not selected by any ingress policy** has unrestricted ingress under NetworkPolicy by default.
- A Pod **not selected by any egress policy** has unrestricted egress under NetworkPolicy by default.
- Once a Pod is selected by an **Ingress** policy, only ingress traffic explicitly permitted by policies is allowed.
- Once a Pod is selected by an **Egress** policy, only egress traffic explicitly permitted by policies is allowed.

**Communication between two Pods** must be permitted by both the **source Pod's egress** and the **destination Pod's ingress** if both sides are isolated in their respective directions. Policies selecting the same Pod are **additive (union)**; creation order does not affect precedence.

### 4.2. Ingress differs from egress

~~~mermaid
flowchart LR
    FE["frontend Pod"] -->|"frontend egress + api ingress:<br/>TCP 8080"| API["api Pod"]
    API -->|"api egress + redis ingress:<br/>TCP 6379"| REDIS["redis Pod"]
    API -->|"DNS egress: TCP/UDP 53"| DNS["CoreDNS in kube-system"]
~~~

This illustrates **separate directional controls**; policies only take effect when an enforcing network plugin supports them.

### 4.3. Selector principles

| Element | Meaning |
|---|---|
| **podSelector: {}** in spec | Selects **all Pods** in the policy's namespace |
| **matchLabels: app: api** | Selects Pods carrying label **app=api** |
| **namespaceSelector** | Selects namespaces by label; can combine with podSelector in **the same list item** to select Pods inside that namespace |
| **ipBlock.cidr** | Selects IP/CIDR ranges; check interaction with CNI NAT/service translation |
| **policyTypes: [Ingress, Egress]** | Isolates both directions for selected Pods |
| **ingress / egress rules** | Permitted peers and ports/protocols |

**Common YAML mistake:** two separate list items under **from:** such as **- namespaceSelector: ...** and **- podSelector: ...** are evaluated as **OR**, not requiring a Pod to satisfy both. To select **labeled Pods inside a specific namespace**, put **namespaceSelector and podSelector inside the same list item**.

### 4.4. No explicit Deny in standard NetworkPolicy

Standard Kubernetes NetworkPolicies express **allow rules** only. To deny by default, select Pods with a policy containing empty rule lists, then add separate allow policies. There is no firewall-style rule ordering where **Deny overrides Allow** inside the standard NetworkPolicy API.

**Advanced note on EKS:** supported Amazon VPC CNI/EKS versions may offer **ClusterNetworkPolicy** at the admin/cluster tier with actions such as **Deny** under AWS's extended API. This is **not** the same resource as **networking.k8s.io/v1 NetworkPolicy**. When using advanced policy types, verify exact version, evaluation precedence, and semantics in AWS documentation. The hands-on examples below use **standard NetworkPolicy** so learners master the core model first.

### 4.5. L3/L4 limitations

Standard NetworkPolicies govern **Pods/IPs/ports/protocols**—they do not filter **HTTP paths**, API routes, request bodies, user identities, or AWS IAM rules. To block **GET /admin**, enforce authorization inside the application, API Gateway/WAF, service mesh, or an appropriate Layer 7 security layer. Never treat NetworkPolicy as a general DNS-based firewall; external IPs change over time.

## 5. Amazon VPC CNI Must Enforce Policies for YAML to Take Effect

A **NetworkPolicy YAML accepted by the Kubernetes API** does not mean traffic is actually blocked. The cluster requires a **CNI/network policy engine** with enforcement enabled. On EKS with Amazon VPC CNI, AWS provides NetworkPolicy enforcement via the **network policy controller** and **network policy agent**.

### 5.1. Amazon VPC CNI prerequisites and limits

| Condition | Operational Significance |
|---|---|
| **Amazon VPC CNI network policy feature must be enabled** | Not enabled by default on all clusters; inspect add-on configuration |
| **Supported version** | Consult current VPC CNI/EKS docs; AWS specifies **VPC CNI 1.21.0 or later** for standard and admin policies in current guides |
| **EC2 Linux worker nodes** | VPC CNI network policies do not apply to Pods on **Fargate** or **Windows** nodes |
| **Compatible OS/kernel** | The eBPF network policy agent requires a supported kernel and node OS |
| **`hostNetwork`** | Pods using host networking are not governed by standard VPC CNI network policy enforcement |
| **Primary Pod interface** | VPC CNI policies apply to the primary interface (**eth0**); extra Multus or secondary interfaces may fall outside |
| **IPv4/IPv6** | Rules must match the cluster's IP family; mismatched family rules can be ignored |
| **Controller-managed Pods** | Policy enforcement targets Pods with **`ownerReferences`** (e.g., Deployment/ReplicaSet); standalone Pods created directly may behave inconsistently |

If a cluster uses **Calico**, **Cilium**, or another third-party policy engine, verify which plugin actually enforces rules. Never run two policy engines simultaneously over the same traffic without strict coordination; migrating engines requires node replacement and rule verification.

**Version-specific limitations can evolve.** Before production rollout, verify AWS docs for your exact Kubernetes version, VPC CNI add-on build, node type, OS, connectivity mode, and cluster network mode.

### 5.2. Enabling the feature on the add-on

For the **EKS managed `vpc-cni` add-on**, AWS supports configuring **`enableNetworkPolicy`** and the node agent via configuration values. **Read-only inspection first**:

~~~bash
aws eks describe-addon \
  --region ap-southeast-1 \
  --cluster-name demo-eks \
  --addon-name vpc-cni \
  --query 'addon.{Version:addonVersion,Status:status,Configuration:configurationValues}' \
  --output json
~~~

Before updating the add-on, verify **addon version**, its configuration schema, IAM permissions, node types, existing custom settings, and your rollback plan. Never issue an update command omitting existing custom settings, or you risk overwriting config and disrupting Pod connectivity.

Conceptual configuration example (not a universal command for every version):

~~~json
{
  "enableNetworkPolicy": "true",
  "nodeAgent": {
    "enablePolicyEventLogs": "true"
  }
}
~~~

In environments using **self-managed VPC CNI**, configuration changes happen via Helm or DaemonSets per AWS instructions rather than the managed add-on API. Test all network-layer changes in a representative environment before production.

### 5.3. Standard mode vs. strict mode

Amazon VPC CNI offers two modes affecting **initial Pod startup**:

| Mode | Before NetworkPolicies Fully Programmed | Consequence |
|---|---|---|
| **standard** | Pods can start in **default allow** before rules apply | Brief startup window where Pods are not yet isolated as intended |
| **strict** | Pods start in **default deny** before specific rules apply | Stronger posture, yet requires explicit policies for DNS and all startup dependencies |

Strict mode is configured via **`NETWORK_POLICY_ENFORCING_MODE=strict`** on **`aws-node`** per deployment docs. Strict mode can break **CoreDNS, monitoring agents, webhooks, or Pod bootstrapping** if allow rules are missing. Host-networked Pods behave differently and require separate controls.

**Rollout approach:** prepare policies for CoreDNS and system components, test DNS/service discovery, enable strict mode on a canary group, monitor denied flows, and expand gradually. Never flip an entire cluster from standard to strict without mapping all required connections first.

### 5.4. Network policy logs

The VPC CNI network policy agent can log allow/deny verdicts. AWS docs describe node-level logs, such as **/var/log/aws-routed-eni/network-policy-agent.log**, with options to ship logs to CloudWatch Logs.

**Network policy event logs are not enabled by default in all configurations**; enabling them increases CPU, network traffic, and CloudWatch costs. Collect only what is needed, set retention, and avoid logging sensitive payloads. If policies appear ineffective, inspect **`policyendpoints.networking.k8s.aws`** created by the network policy controller, controller/agent RBAC, and **`aws-node`** Pod health.

## 6. Hands-On Example: Default-Deny Followed by Explicit Flows

Suppose namespace **shop** runs three Deployment-managed Pod groups:

- **app=frontend**: internal web/UI calling API on TCP **8080**.
- **app=api**: Java service calling **redis** cache on TCP **6379** and CoreDNS.
- **app=redis**: internal cache accepting connections only from API.

The apps and namespace already exist; the goal is illustrating **internal connectivity**, excluding ingress from an ALB or external ingress controller. For real-world application ingress, add matching policies per your CNI/ALB design and source restrictions; the examples below **intentionally do not permit Internet traffic to frontend**.

### 6.1. Policy A — default deny in the namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: shop
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

When enforced, every Pod in namespace **shop** is isolated for both ingress and egress, **except** flows permitted by other NetworkPolicies. **This does not mean Kubernetes blocks traffic immediately** if CNI enforcement is not enabled.

### 6.2. Policy B — allow all Pods to query CoreDNS

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: shop
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

This is the common rule for CoreDNS. **Before applying, verify actual CoreDNS Pod labels**, such as with **`kubectl -n kube-system get pods --show-labels`**. With **NodeLocal DNSCache**, DNS proxies, or other plugins, paths/labels/addresses may differ and require tailored policies. Egress from `shop` alone is insufficient if policies in `kube-system` also isolate CoreDNS ingress.

### 6.3. Policy C — frontend may only call API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-egress-to-api
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8080
~~~

If frontend also needs external identity providers, off-cluster APIs, or S3 endpoints, those connections must be **reviewed and explicitly permitted**. Never add **`0.0.0.0/0`** just to “stop timeouts” without security review.

### 6.4. Policy D — API accepts only from frontend, calls only Redis

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-ingress-egress
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
~~~

This policy combines additively with **allow-dns-egress**, so API Pods can resolve DNS and reach Redis. If API also calls RDS, SQS, STS, or AWS services via VPC endpoints, add matching egress rules; IAM and SGs still must align.

### 6.5. Policy E — Redis accepts only from API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-ingress-from-api
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 6379
~~~

Expected behavior for internal traffic:

| Flow | Expected | Why |
|---|---|---|
| Frontend → API TCP 8080 | **ALLOW** | Both frontend egress and API ingress allow it |
| API → Redis TCP 6379 | **ALLOW** | Both API egress and Redis ingress allow it |
| Frontend → Redis TCP 6379 | **DENY** | Redis only allows source **app=api** |
| API → CoreDNS TCP/UDP 53 | **ALLOW** when policy/labels match | Allow DNS egress combines additively |
| Redis → API TCP 8080 new connection | **DENY** | No matching allow rule exists |
| Pod in another namespace → API | **DENY** without explicit policy | API ingress selects only frontend in same namespace |

**Stateful connections:** return packets for an already permitted connection are normally handled by the network plugin; the table above describes **new connections**, not individual return packets.

### 6.6. Lab application order

A low-risk approach is saving each policy to its own manifest, verifying labels, and applying **allow policies first** before applying **default-deny-all**. In a test environment:

~~~bash
# Example only: create manifest files matching the YAML above.
kubectl apply -f allow-dns-egress.yaml
kubectl apply -f frontend-egress-to-api.yaml
kubectl apply -f api-ingress-egress.yaml
kubectl apply -f redis-ingress-from-api.yaml
kubectl apply -f default-deny-all.yaml

kubectl -n shop get networkpolicy
kubectl -n shop describe networkpolicy api-ingress-egress
kubectl -n shop get pods -L app -o wide
~~~

Test connections from **Deployment/ReplicaSet-managed Pods** to avoid VPC CNI policy limits on standalone Pods. When using **`kubectl exec`** for testing, containers need the right utilities; distroless production images typically lack shells/`curl`. Use a controlled **temporary diagnostic Deployment** with scoped permissions and labels.

**Production workflow:** route policies through CI/CD, assess impact, deploy via canary, watch denied flows, and maintain rollback. NetworkPolicy fixes will not resolve SG/NACL, Route 53, DNS, or IAM issues.

## 7. EKS Network Security Beyond NetworkPolicy

### 7.1. Security groups for Pods

In supported **Amazon VPC CNI on EC2** setups, **Security Groups for Pods** attaches SGs directly to Pods via **`SecurityGroupPolicy`** and branch ENIs. This is especially useful for restricting which workloads may talk to **RDS**, ElastiCache, or VPC-attached AWS services.

NetworkPolicy governs **Pod-to-Pod/in-cluster L3/L4**, whereas SG for Pods governs **the VPC ENI layer** and AWS resources. When using both together, **both must permit** the flow; an SG allowing port 5432 cannot bypass a NetworkPolicy blocking egress.

**Cost/limits:** SG for Pods consumes ENIs and per-instance pod-ENI limits; it can slow Pod startup or trigger **`Insufficient vpc.amazonaws.com/pod-eni`**. Check instance types, ENI counts, IPs, and quotas before broad rollout.

### 7.2. IAM for Pods: EKS Pod Identity and IRSA

For Pods calling AWS APIs, prefer an **IAM role bound to a Kubernetes service account** via **EKS Pod Identity** or **IAM Roles for Service Accounts (IRSA)** as supported:

- **EKS Pod Identity** uses EKS associations between service accounts and IAM roles, backed by the Pod Identity Agent on supported nodes.
- **IRSA** uses the cluster's OIDC identity provider, service account annotations, and matching trust policies.

Both issue **temporary AWS credentials** to applications; neither **replaces Kubernetes NetworkPolicy**, opens SGs, or governs Kubernetes API permissions for the service account. Avoid letting Pods fall back to broad EC2 node instance profiles or exposing IMDS unnecessarily.

### 7.3. EKS API endpoint and administrative access

The EKS cluster endpoint can be **public**, **private**, or both per service configuration. With a public endpoint, restrict **public access CIDR ranges**, enforce IAM authentication, EKS access entries/Kubernetes RBAC, and audit logs. With a private endpoint, admin/CI hosts require a valid path into the VPC—such as VPN, Direct Connect, or in-VPC runners.

**Making the endpoint private does not stop an already authorized principal from calling the Kubernetes API from an allowed network.** IAM/RBAC and cluster permissions must still follow least privilege.

### 7.4. TLS, admission, and workload security

- Use HTTPS/TLS via Ingress/ALB or a service mesh as required; NetworkPolicy does not encrypt payloads.
- Restrict privileged containers, `hostPath`, `hostNetwork`, Linux capabilities, and service account permissions.
- Enforce **Pod Security Standards** via admission or policy engines (e.g., Kyverno/Gatekeeper) per cluster capabilities.
- Protect secrets via Kubernetes Secrets with KMS encryption and external secret stores when needed.
- Scan images in ECR or other registries, pin image digests/tags, and enforce resource requests/limits.

## 8. Multi-AZ EKS Operations: Real Design, Not Just Subnets

### 8.1. Subnet and worker node distribution

AWS recommends spanning EKS clusters across **at least two AZs**, and critical systems often use three AZs where Regions support it. Plan subnets carefully for EKS/control-plane ENIs, node groups, private workloads, and public load balancers.

Example network layout:

| AZ | Private Subnet | Illustrative Workload | Capacity to Reserve |
|---|---|---|---|
| AZ A | 10.20.0.0/20 | Node A + API Pod A | EC2 capacity, IP addresses, egress path |
| AZ B | 10.20.16.0/20 | Node B + API Pod B | EC2 capacity, IP addresses, egress path |
| AZ C | 10.20.32.0/20 | Node C + API Pod C | EC2 capacity, IP addresses, egress path |

CIDRs are examples only. Ensure zero overlap with other networks and sufficient IPs for **Pod ENIs, nodes, load balancers, and upgrades**. Amazon VPC CNI allocates VPC IPs to Pods in standard modes; IP exhaustion causes **Pending/ContainerCreating** Pods even while EC2 nodes have free CPU/RAM.

**Internet egress:** private subnets use NAT Gateways or VPC endpoints. A single NAT Gateway in AZ A creates cross-AZ dependency; if AZ A or its route fails, Pods in AZs B/C lose egress. Evaluate per-AZ NAT with per-AZ subnet routes or VPC endpoints, weighing cost vs. fault isolation.

### 8.2. Node placement does not automatically decide Pod placement

A managed node group spanning three AZ subnets supplies multi-AZ worker capacity, yet the scheduler places Pods based on **requests, taints/tolerations, affinity, topology**, and node health. Without scheduling rules, three replicas can still cluster together.

~~~bash
kubectl get nodes -L topology.kubernetes.io/zone
kubectl -n shop get pods -o wide
kubectl -n shop get deployments
~~~

Cross-reference **Pod → Node → `topology.kubernetes.io/zone`**; plain `kubectl get pods` does not show AZs directly in every version, so check node labels or observability tooling.

### 8.3. Topology spread constraints

Example API Deployment with three replicas requiring balanced AZ distribution:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:stable
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
~~~

This is a learning manifest; the image URI must exist, and DNS/secrets/network/node capacity must be ready. **`topologyKey = topology.kubernetes.io/zone`** reads the node label. **`maxSkew: 1`** caps replica imbalance across eligible domains. **`DoNotSchedule`** can leave Pods Pending when the constraint cannot be met.

**Do not guarantee three replicas always land in exactly three AZs.** If only two AZs are eligible or scheduling conditions shift, skew can still occur under scheduler rules. When three AZs are mandatory, verify eligible domains and combine node affinity, **`minDomains`**, or version-matched policies, then test thoroughly. **`ScheduleAnyway`** reduces Pending risk but acts only as a soft preference rather than a strict guarantee.

### 8.4. Pod anti-affinity and per-node spreading

Zone-level topology spread distributes across AZs; to prevent multiple replicas from landing on the same node, add a constraint on **`kubernetes.io/hostname`** or **`podAntiAffinity`**:

- **`preferredDuringSchedulingIgnoredDuringExecution`**: tries to separate across nodes/AZs when possible.
- **`requiredDuringSchedulingIgnoredDuringExecution`**: hard scheduling requirement; can cause Pending Pods when nodes are scarce.

**Trade-off:** hard constraints strengthen HA when capacity is plentiful, yet can stall rollouts or block recovery after an AZ outage if the scheduler cannot consolidate Pods onto surviving AZs. Choose rules based on **SLOs and acceptable degraded capacity**, rather than applying `DoNotSchedule` blindly to every Deployment.

## 9. PodDisruptionBudget, Rollouts, and Health Probes

### 9.1. PodDisruptionBudget (PDB)

A **PDB** caps how many Pods can be disrupted by **voluntary evictions** using the Eviction API, such as during node drains for maintenance. For a three-replica **`orders-api`** Deployment:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: shop
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

The PDB requests keeping **at least two healthy Pods** during supported voluntary evictions. **A PDB cannot stop sudden node/AZ failures, Spot interruptions, hardware faults, or forced delete/terminate calls.** Nor does it replace **Deployment `rollingUpdate.maxUnavailable`/`maxSurge`**; design both coherently.

During an AZ failure, a PDB cannot force two remaining replicas to serve properly if they were both in that AZ or if backends are down.

### 9.2. Probes and graceful termination

| Setting | Purpose | Common Mistake |
|---|---|---|
| **`startupProbe`** | Gives slow-starting apps time before liveness checks begin | Liveness triggers early, causing restart loops |
| **`readinessProbe`** | Controls whether Pod enters Service endpoints for traffic | Reporting ready before DB/configs are initialized |
| **`livenessProbe`** | Detects wedged processes needing restart | Depending on flaky external systems, causing mass restarts |
| **`terminationGracePeriodSeconds`** | Gives Pods time for clean shutdown | Killing active long requests or uncheckpointed jobs |
| **`preStop` hook** | Runs pre-termination cleanup per lifecycle | Overly long hooks causing timeouts/grace exhaustion |
| **PDB** | Limits voluntary disruptions | Setting `minAvailable` too high, stalling drains/upgrades |

With ALB/NLB and AWS Load Balancer Controller, check timing across **Kubernetes EndpointSlice/Service** updates, target group health, deregistration delays, and open connections. A working **`readinessProbe`** alone does not guarantee zero dropped requests if a node shuts down abruptly.

### 9.3. Multi-AZ RTO/RPO

**RTO** is the maximum target time to restore service; **RPO** is the maximum acceptable data loss window. Stateless apps with sufficient replicas across two surviving AZs can achieve low RTO. However, if a stateful component kept its sole data on an EBS volume in the lost AZ, the app cannot recover that data even if a new Pod schedules elsewhere.

Multi-AZ design must therefore span **compute, networking, ingress, DNS, storage, databases, queues, IAM, and observability**—not just the Kubernetes scheduler.

## 10. Multi-AZ Storage: EBS, EFS, and Databases

### 10.1. Amazon EBS is an AZ-level volume

An **EBS volume** is created in one AZ and attaches only to EC2 instances in **that same AZ**. With the **Amazon EBS CSI driver**, PVs/PVCs are bound to that AZ topology. If a StatefulSet/Deployment Pod uses an EBS PVC in AZ A while the scheduler forces the Pod onto a node in AZ B, attachment fails or the Pod stays Pending.

Example StorageClass (using the **traditional EBS CSI driver on EC2 worker nodes**, not Auto Mode):

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3-wait-consumer
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: true
~~~

**`WaitForFirstConsumer`** defers volume provisioning until the scheduler places the Pod on a node, picking the right AZ initially. It **does not let an EBS volume migrate across AZs after creation**. **`Retain`** preserves the PV/data after PVC deletion per reclaim rules, but it is not a backup. Use snapshots/backups to restore into another AZ per runbooks when needed.

**EKS Auto Mode distinction:** Auto Mode StorageClasses use provisioner **`ebs.csi.eks.amazonaws.com`**; do not copy **`ebs.csi.aws.com`** verbatim. EBS volumes normally do not mount on Fargate Pods; always check compute engine and node type.

### 10.2. Amazon EFS for multi-AZ shared files

**Amazon EFS** provides NFS access across VPC mount targets and works when multiple Pods need **`ReadWriteMany`** file storage. With the **EFS CSI driver**, design mount targets, security groups, IAM/access points, latency, and throughput carefully.

EFS simplifies multi-Pod file access across AZs, yet **does not automatically solve concurrency, file locking, or transactional consistency**. Measure latency, cross-AZ network traffic, throughput, and cost.

### 10.3. Keep databases decoupled from Pod lifecycles

For transactional data, evaluate **Amazon RDS/Aurora Multi-AZ**, **DynamoDB**, or appropriate managed database services. Having multiple app replicas does not make the database HA. Implement connection pooling, bounded retries, timeouts, idempotency, backups, and database failover testing.

**Single-AZ EBS stateful storage** must never be confused with multi-AZ data protection. If self-hosting databases on Kubernetes, engineer replication, quorum, storage placement, backup/restore, and matching operational expertise.

## 11. Multi-Layer Autoscaling

| Mechanism | What It Adjusts | What It Does Not Solve Alone |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | Deployment/StatefulSet replicas from metrics | Does not launch nodes when cluster capacity fills up |
| **Cluster Autoscaler** | EC2 worker node counts in node groups/ASGs | Does not fix bad Pod resource requests or HA scheduling |
| **Karpenter** | Provisions/consolidates nodes from scheduling demand and NodePool/NodeClass | Does not replace workload replication or database HA |
| **EKS Auto Mode** | Automates node/network/storage tasks within feature scope | Still requires configuring app scheduling, security, and reliability |

HPA scale-out can leave Pending Pods when **nodes are full**. Cluster Autoscaler/Karpenter watches those Pending Pods and provisions nodes meeting CPU/RAM/IP/zone constraints; provisioning succeeds only if EC2 capacity, quotas, subnet IPs, and topology limits allow.

### 11.1. Multi-AZ and capacity costs

- Multi-AZ node groups spread capacity, yet must keep headroom to **absorb Pods when one AZ fails**.
- For AZ-bound EBS volumes, node autoscalers must provision nodes in the PV's exact AZ.
- When using **Spot**, apply diversification, replacement handling, PDBs/graceful termination, and an appropriate On-Demand baseline.
- Never let **Cluster Autoscaler and Karpenter manage the same node group** without clear ownership boundaries.
- Hard topology constraints combined with subnet IP exhaustion can leave Pods permanently Pending even while other AZs have capacity.

### 11.2. Pod IP planning

Amazon VPC CNI normally assigns **VPC IP addresses** to Pods, so workload scale is bounded by subnet CIDRs, ENI/IP limits, prefix delegation, and IPAM settings. When scaling Pods on EC2, CPU is often not the first bottleneck.

Signs of IP exhaustion:

- Pods stuck in **`ContainerCreating`/`Pending`**.
- Events showing **`aws-node`/IPAM** errors or failure to assign Pod IPs.
- EC2/VPC subnet out of free addresses or instances hitting ENI/IP limits.

Fixes include re-architecting CIDRs, selecting larger subnets, enabling prefix delegation where supported, picking instance types with higher IP limits, or balancing workloads across AZs. Avoid merely adding more nodes when subnets have zero free addresses.

## 12. Upgrades and Safe Operations

### 12.1. Planned upgrade sequence

Kubernetes/EKS have version support calendars and add-on compatibility matrices. A standard upgrade runbook covers:

1. Review current Kubernetes version, support timelines, **deprecated APIs**, CRDs, webhooks, and workloads.
2. Prepare backups/restores for data and configs; export manifests/IaC and define app rollback paths.
3. Verify compatibility of **VPC CNI, CoreDNS, kube-proxy, EBS/EFS CSI, AWS Load Balancer Controller**, and network policy agents with the target version.
4. Upgrade the **control plane** along EKS-supported version hops.
5. Update add-ons and worker node groups per compatibility guides, rolling groups sequentially to preserve capacity.
6. Monitor **PDBs**, target health, DNS, network policy enforcement, EBS attachments, pending Pods, and SLOs.
7. Run API smoke tests and recovery checks, then record the change.

**Never assume a control plane upgrade can be reversed with one click.** Review EKS rollback/upgrade rules and prepare data-plane/application recovery paths.

### 12.2. When draining nodes

**`kubectl drain`** issues evictions and respects PDBs. During a node group upgrade, Pods with overly high **`minAvailable`**, long termination grace periods, or unschedulable placement constraints can stall drains.

Run drains only in authorized environments and maintenance windows. Before draining, verify sufficient surviving nodes, subnet IPs, AZ capacity, replicas, and PV constraints. Monitor **`kubectl get pdb`**, allowed Pod disruptions, events, and replacement scheduling.

### 12.3. Multi-AZ is not Multi-Region

An EKS cluster lives within a single **AWS Region**. Multiple AZs mitigate single-AZ outages, yet do not create a standby cluster in another Region. Regional disaster recovery requires **multi-Region cluster deployments**, DNS failover, data replication, secrets/KMS, image registries, CI/CD, and RTO/RPO drills.

## 13. AWS CLI and kubectl Inventory Commands (Read-Only)

The commands below **only read state/configuration** in authorized environments. Replace cluster, Region, and namespace with real values. For `kubectl`, verify kubeconfig points to the right cluster with appropriate Kubernetes API permissions.

~~~bash
# Cluster metadata, version, and endpoint access.
aws eks describe-cluster \
  --region ap-southeast-1 \
  --name demo-eks \
  --query 'cluster.{Name:name,Version:version,Status:status,Subnets:resourcesVpcConfig.subnetIds,Private:resourcesVpcConfig.endpointPrivateAccess,Public:resourcesVpcConfig.endpointPublicAccess}' \
  --output json

# Inventory managed node groups.
aws eks list-nodegroups \
  --region ap-southeast-1 \
  --cluster-name demo-eks

# Inspect managed VPC CNI add-on.
aws eks describe-addon \
  --region ap-southeast-1 \
  --cluster-name demo-eks \
  --addon-name vpc-cni \
  --query 'addon.{Version:addonVersion,Status:status,Config:configurationValues}' \
  --output json

# List nodes and AZ labels.
kubectl get nodes -L topology.kubernetes.io/zone

# Workloads, Pod placement, and network policies.
kubectl -n shop get deployments,pods -o wide
kubectl -n shop get networkpolicies
kubectl -n shop describe networkpolicy default-deny-all

# PDBs, events, and Pending Pods.
kubectl -n shop get pdb
kubectl -n shop get events --sort-by=.lastTimestamp
kubectl -n shop get pods --field-selector=status.phase=Pending
~~~

**Read and cross-check:** if three replicas sit on the same node/AZ, inspect scheduler constraints and node placement. If NetworkPolicies exist yet traffic still flows, verify the network policy engine/feature. If Pods are Pending, run **`kubectl describe pod`** to check **`FailedScheduling`**, PVC binding, taints, or IPAM.

### 13.1. Inspecting the policy engine (depending on add-on and permissions)

~~~bash
kubectl -n kube-system get daemonset aws-node
kubectl -n kube-system get pods -l k8s-app=aws-node -o wide

# On add-ons with NetworkPolicy enabled:
kubectl get crd policyendpoints.networking.k8s.aws
kubectl -n shop get policyendpoints

# Requires a specific pod name; read logs only if authorized:
kubectl -n kube-system logs POD_AWS_NODE \
  -c aws-network-policy-agent --tail=100
~~~

**Note:** CRDs or agent containers may not exist if the feature is off, the version is unsupported, or another CNI engine is used. Never edit or delete EKS-managed **`PolicyEndpoint`** resources “just to see if errors clear.”

## 14. Common Incident Analysis

| Symptom | Causes to Investigate | Evidence and Remediation |
|---|---|---|
| **NetworkPolicy created, yet traffic still allowed** | VPC CNI feature disabled, Fargate/Windows/hostNetwork Pod, wrong labels, standalone Pod | Check add-on, `aws-network-policy-agent`, `policyendpoints`, labels, node type |
| **Pods fail DNS resolution after default deny** | Missing TCP/UDP 53 allow rule or mismatched CoreDNS labels | Check CoreDNS labels, namespace policies, NodeLocal DNSCache |
| **Frontend calls to API time out** | Missing frontend egress or API ingress, wrong SG/NACL/route/port | Check both NetworkPolicy directions and underlying network path |
| **API cannot reach RDS** | NetworkPolicy egress, SG for Pods, RDS SG, DNS, routes, or IAM/TLS | Check pod-to-RDS path, credentials, and security layers |
| **Pods pass traffic briefly at startup despite strict posture** | Amazon VPC CNI is in standard startup mode | Check enforcing mode and test startup traffic |
| **Enabling strict mode breaks CoreDNS** | Policies do not yet allow system DNS access | Deploy allow rules for CoreDNS and dependencies |
| **Pods Pending after adding spread constraints** | Insufficient eligible AZs/nodes, capacity, taints, strict `maxSkew` | `kubectl describe pod`, `topologyKey`, node labels, autoscaler |
| **StatefulSet Pod Pending on EBS volume** | PV exists only in AZ A, Pod constrained to AZ B | PV `nodeAffinity`, `WaitForFirstConsumer` StorageClass, PV topology |
| **Pods stuck ContainerCreating** | Missing Pod IPs, VPC CNI/IPAM/ENI, image pull, or volume attach | Pod events, `aws-node` logs, subnet free addresses |
| **AZ loss leaves API with 0 healthy replicas** | All replicas in one AZ, unspread node groups, or backend tied to lost AZ | Node/Pod AZ placement, ALB health, data tier |
| **Node drain never finishes** | PDB too strict, no replacement node, bound PVC, or non-evictable Pod | PDB `disruptionsAllowed`, events, node capacity |
| **HPA scales replicas, yet latency stays high** | DB bottleneck, node autoscaler stalled, policies/network blocking backend | HPA metrics, Pending Pods, DB latency, traces |
| **One zone overloaded while global HPA mis-scales** | Uneven load distribution, mismatched per-zone topology/capacity | Per-AZ metrics, ingress routing, scheduler/autoscaler placement |
| **Cross-AZ transfer bill spikes** | Pods talking to DB/cache across AZs, hairpin NAT/traffic, cross-zone flows | VPC Flow Logs, Cost Explorer, traffic metrics, topology |

### 14.1. Network policy troubleshooting workflow

~~~mermaid
flowchart TD
    A["App timeout / connection refused"] --> B["Verify DNS, IP, port,<br/>source and destination Pods"]
    B --> C["Which Pods are selected by NetworkPolicy?<br/>Ingress + egress"]
    C --> D{"Is VPC CNI policy engine<br/>enforcing?"}
    D -->|"No / unsupported"| E["Check add-on, node type,<br/>agent, policyendpoints"]
    D -->|"Yes"| F["Inspect denied flow logs<br/>and rules/labels"]
    E --> G["Cross-check SG, NACL,<br/>routes, VPC endpoints, IAM/TLS"]
    F --> G
    G --> H["Apply minimal rule fix<br/>test both allow and deny"]
~~~

**Never delete all network policies in production just to “test connectivity.”** Use an isolated namespace/staging setup or an approved, rollback-ready change; inspect logs/traces, labels, and routing before altering security layers.

### 14.2. Multi-AZ failure analysis workflow

1. Identify incident class: **node/AZ down, subnet IP exhausted, EBS volume bound, DNS/ALB/DB unavailable**.
2. Inspect actual replicas, ready Pods, and each node's AZ.
3. Check scheduling constraints, tolerations, PDBs, resource requests, HPA/Cluster Autoscaler/Karpenter.
4. Verify available EC2 capacity and free IPs in surviving AZs.
5. Verify backend health and network paths from recovered Pods.
6. Run synthetic transactions, measure recovery time, and document remaining RTO/RPO gaps.

## 15. Design Scenarios

### Scenario A — Single namespace holding app and cache

A team runs frontend, API, and Redis inside namespace **shop**. Currently any Pod can call Redis. Security requires frontend to call only API, and only API to call Redis.

**Task:** design default-deny ingress/egress NetworkPolicies, allow DNS, allow frontend → API TCP 8080, allow API → Redis TCP 6379, and deny frontend → Redis.

**Hint:** apply the policies from section 6; test both egress and ingress directions. Confirm Amazon VPC CNI policy enforcement is active on EC2 Linux nodes before assuming policies work.

### Scenario B — Multi-AZ production yet all Pods sit in one AZ

An EKS cluster has subnets in three AZs. Deployment **checkout-api** runs 3 replicas, yet all Pods sit on nodes in AZ A. When AZ A fails, the service loses all healthy endpoints.

**Task:** explain why “having three subnets” is insufficient and propose a better design.

**Hint:** ensure worker capacity across all three AZs, configure **`topologySpreadConstraints`** by zone, consider hostname spreading, verify replicas/requests/quotas, readiness probes, and PDBs. Verify Pod → node → AZ placement; simulate losing one AZ and measure load on surviving zones.

### Scenario C — Strict mode breaks application DNS

A team enables NetworkPolicy strict mode. New API Pods cannot resolve **`redis.shop.svc.cluster.local`**, while direct IP connections on permitted flows still work.

**Task:** diagnose without opening all egress.

**Hint:** inspect CoreDNS/NodeLocal DNSCache, UDP/TCP 53, Pod/namespace labels, `kube-system` ingress policies, and `aws-network-policy-agent` logs. Add the exact DNS allow policy rather than opening **`ipBlock 0.0.0.0/0`**.

### Scenario D — EBS PVC prevents Pod AZ failover

A StatefulSet has a gp3 PVC provisioned in AZ A. After a node failure in AZ A, the scheduler tries placing the Pod onto a node in AZ B, but the volume fails to attach.

**Task:** explain the EBS constraint and recovery options.

**Hint:** EBS volumes are AZ-bound; **`WaitForFirstConsumer`** only picks the AZ at initial PV creation. When AZ A is unavailable, restore from snapshot/backup into another AZ or use storage/database replication. EFS supports multi-AZ file sharing for fitting workloads, but does not replace database consensus.

### Scenario E — PDB blocks node group upgrade

A Deployment runs two replicas with PDB **`minAvailable: 2`**, and the node group needs an AMI rollout. Kubernetes drain cannot evict Pods because zero spare Pods exist.

**Task:** recommend a change that still protects the SLO.

**Hint:** temporarily scale up replicas/capacity, spread Pods across nodes/AZs, align PDB and Deployment rollout settings, and ensure new nodes launch before old nodes drain. Never force-delete production Pods just to bypass PDBs without evaluating impact.

### Scenario F — RDS connection fails despite NetworkPolicy Allow

An API Pod has NetworkPolicy egress allowed to RDS on TCP 5432, yet connections time out. RDS is protected by a security group and the Pod uses Security Groups for Pods.

**Task:** list all layers to inspect.

**Hint:** egress policy, Pod SG and RDS SG, subnet routes/NACLs, DNS, exact endpoint/port, network path, TLS; once TCP succeeds, check IAM/DB credentials and database grants. A NetworkPolicy Allow cannot override an SG Deny or database auth failure.

## 16. Observability, Security, and Operational Cost

### 16.1. Telemetry sources to maintain

| Source | What It Monitors | Why It Matters |
|---|---|---|
| **CloudWatch Container Insights / Prometheus** | CPU, memory, Pod restarts, cluster/node health | Sizing, HPA, and workload incidents |
| **Kubernetes Events / Pod descriptions** | `FailedScheduling`, evictions, image pulls, volume binding | Separates scheduler, storage, and app failures |
| **Amazon VPC CNI / network policy agent logs** | Rule enforcement, denied flows, and IPAM issues | Investigating network isolation and Pod networking |
| **VPC Flow Logs** | VPC traffic flows within configured log scope | Checking SGs/routes and cross-AZ traffic trends |
| **EKS control plane logs** | API server/audit/authenticator/controller/scheduler per config | Auditing Kubernetes API access and orchestration |
| **ALB/NLB metrics and app tracing** | 4xx/5xx errors, healthy targets, p95 latency | Proving customers still receive service |
| **AWS Cost Explorer / CUR** | EKS, EC2/Fargate, networking, and storage costs | Optimizing TCO and spotting cross-AZ charges |

**VPC Flow Logs and NetworkPolicy logs are not identical.** VPC Flow Logs capture VPC-level network flows per service logging rules; network policy agent logs show verdicts from the policy engine. Never assume VPC Flow Logs alone identify which Kubernetes NetworkPolicy dropped a packet.

### 16.2. Easily overlooked cost drivers

- **EKS cluster/control plane** per active pricing, including version-support tier surcharges if applicable.
- **EC2 managed/self-managed nodes, Fargate**, or matching compute modes.
- **Inter-AZ data transfer**, NAT Gateways, VPC endpoints, load balancers.
- **EBS/EFS**, snapshots, databases, backups, and data replicas.
- **CloudWatch logs/metrics**, Prometheus, network policy flow logs, and security tooling.
- **Failover headroom capacity**, baseline replicas, PDBs slowing scale-in, and Spot churn overhead.

Cost optimization must not trade away resilience blindly: packing all Pods into one AZ to save transfer costs raises outage risk. If choosing **same-zone** traffic routing, verify load balancing behavior, failover across AZs when one fails, and live SLOs.

## 17. Pre-Production Checklist

- [ ] Cluster spans subnets across at least **two AZs** with per-AZ capacity plans.
- [ ] Worker nodes, critical workloads, DNS/ingress, and backends can tolerate a single node/AZ failure.
- [ ] Verified CNI/network plugin enforces NetworkPolicies; never treat accepted YAML as proof of enforcement.
- [ ] Reviewed **EC2 Linux/Fargate/Windows/`hostNetwork`/standalone Pod** limits for your VPC CNI version.
- [ ] Created default-deny and explicit allow rules for real flows, including **DNS TCP/UDP 53** where needed.
- [ ] Verified both source **egress** and destination **ingress**, network policy logs, SGs/NACLs, and routes.
- [ ] Separated Pod AWS IAM via Pod Identity/IRSA from Kubernetes RBAC/network controls.
- [ ] Secured EKS API endpoints, admission, service accounts, secrets, TLS, and node IAM.
- [ ] Configured **`topologySpreadConstraints`** and/or `podAntiAffinity` per SLOs and verified Pod AZ placement.
- [ ] Tuned replicas, **PDBs**, readiness/liveness/startup probes, and graceful shutdown.
- [ ] Verified autoscalers/node provisioning, IP capacity, quotas, and failover paths on AZ loss.
- [ ] Accounted for **EBS AZ binding**; aligned StorageClasses, EFS, or DB HA/DR with data requirements.
- [ ] Tested rollouts/node upgrades and behavior under AZ/capacity shortages without recklessly bypassing PDBs.
- [ ] Monitored denied flows, application SLOs, scheduling errors, storage, logs, and per-AZ load.
- [ ] Measured RTO/RPO, tested restores, and budgeted inter-AZ/NAT/storage/compute costs.

## 18. Key Takeaways

**Kubernetes NetworkPolicy** restricts **L3/L4** traffic to and from Pods, yet only works when an enforcing **network plugin** executes it. On EKS with Amazon VPC CNI, enable the feature on supported versions/nodes and understand **standard** vs. **strict** startup modes. A **default-deny** design is only safe and operational when required flows—especially **DNS** and critical API/backend paths—are explicitly allowed.

**Multi-AZ EKS** requires more than selecting subnets: you need **worker capacity and Pod distribution across AZs**, topology spread/anti-affinity, PDBs, probes, autoscaling, resilient networking, and compatible storage. **EBS binds to one AZ**, whereas **EFS** and Multi-AZ databases provide different storage and recovery models. Combining **least privilege + multi-AZ scheduling + observability + failover drills** builds applications that are secure, recoverable, and cost-predictable.

### Official AWS and Kubernetes References

- [Amazon EKS — Limit Pod traffic with Kubernetes network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html) — capabilities, limits, and NetworkPolicy/admin policies.
- [Configure Network Policies in Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html) — standard/strict enforcement and node agent.
- [Troubleshoot EKS Network Policies](https://docs.aws.amazon.com/eks/latest/userguide/network-policies-troubleshooting.html) — policyendpoints, logs, common issues.
- [Amazon EKS Best Practices — Network Security](https://docs.aws.amazon.com/eks/latest/best-practices/network-security.html) — NetworkPolicies and VPC defense layers.
- [Amazon EKS Best Practices — VPC and Subnets](https://docs.aws.amazon.com/eks/latest/best-practices/subnets.html) — multi-AZ design and IP addressing.
- [Amazon EKS Best Practices — Data Plane](https://docs.aws.amazon.com/eks/latest/best-practices/data-plane.html) — worker nodes, scheduling, autoscaling.
- [Amazon EKS Best Practices — Cluster Upgrades](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html) — PDBs, topology spread, add-on/worker updates.
- [AWS Prescriptive Guidance — Spread workloads across AZs](https://docs.aws.amazon.com/prescriptive-guidance/latest/ha-resiliency-amazon-eks-apps/spread-workloads.html) — topology spread and anti-affinity.
- [Amazon EKS — Use Kubernetes storage with Amazon EBS](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html) — EBS CSI, Auto Mode, and node constraints.
- [Amazon EKS — Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-configure-pods.html) — IAM roles for service accounts.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — standard semantics and YAML.
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — scheduling across failure domains.
- [Kubernetes — Pod Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — PDBs and voluntary disruptions.
- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/) and [AWS Pricing Calculator](https://calculator.aws/) — cluster/compute/network pricing.
