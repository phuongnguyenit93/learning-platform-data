# AWS Load Balancer Controller and Exposing Services

> **Chapter:** Kubernetes with EKS  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; practice designing secure, observable, resilient, and cost-controlled systems.

On **Amazon Elastic Kubernetes Service (Amazon EKS)**, an application in `Running` state is not automatically reachable by external users. **Pods** can be replaced and receive new IP addresses; a **Service** provides a stable in-cluster access point; and public applications typically need an **AWS Application Load Balancer (ALB)** or **Network Load Balancer (NLB)** to receive traffic and forward it to the right backends. The **AWS Load Balancer Controller** is the Kubernetes controller that translates those declarative configurations into Elastic Load Balancing resources in AWS.

This lesson explains how the AWS Load Balancer Controller works with **Ingress**, **Service type `LoadBalancer`**, **Security Groups**, subnets, and health checks, as well as how to troubleshoot when users receive `502`, `503`, or cannot connect. YAML manifests, ARNs, and IP addresses in this lesson are illustrative and **must not be applied verbatim to production**.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of the **AWS Load Balancer Controller** and the **reconciliation** mechanism between the Kubernetes API and Elastic Load Balancing.
2. Distinguish `Service ClusterIP`, `NodePort`, `LoadBalancer`, and `Ingress`; choose **Layer 7 ALB** or **Layer 4 NLB** based on requirements.
3. Analyze the two ELB target types: **`instance`** and **`ip`**, including traffic flow via NodePort versus directly to Pod IPs.
4. Design public/internal load balancers with proper subnets, IAM, Security Groups, Kubernetes Services, and health checks.
5. Read and adapt sample `Deployment + Service + Ingress` manifests for HTTPS ALBs; recognize `Service type LoadBalancer` manifests for NLBs.
6. Verify controller permissions via **IRSA or EKS Pod Identity**, along with VPC CNI, subnet discovery, quotas, and DNS prerequisites.
7. Troubleshoot unhealthy targets, empty target groups, missing IAM permissions, improper subnet tags, image pull errors, and unsafe rollout procedures.

## 2. A Kubernetes Service Is Not Automatically a Public Endpoint

Kubernetes has distinct networking abstractions:

| Resource | Purpose | Does it automatically create an AWS load balancer? |
|---|---|---|
| **Pod** | Runs one or more containers sharing a network inside the Pod | No |
| **Service `ClusterIP`** | Provides an internal virtual IP/DNS for matching Pods by selector | No |
| **Service `NodePort`** | Opens a specific port on Nodes to forward traffic to Pods | Not by NodePort alone |
| **Service `LoadBalancer`** | Requests a cloud controller to provision a matching load balancer | Yes, when a compatible controller and class/annotations exist |
| **Ingress** | Declares HTTP(S) host/path routing to Kubernetes backend Services | Only when an appropriate **Ingress controller** runs, such as AWS Load Balancer Controller |
| **IngressClass** | Specifies which controller owns the Ingress | Does not create an ALB without an active controller |

**Key distinction:** a `Service` is not an AWS ELB instance; an `Ingress` is not the ALB itself. They are Kubernetes resources, while the controller reads them, calls AWS APIs to create/update, and reconciles the infrastructure.

Example:

~~~text
Pod IP:            10.20.11.31:8080      (changes when Pod is recreated)
Service ClusterIP: 172.20.105.10:80      (logical access point inside cluster)
Ingress host:      api.example.com       (HTTP routing declaration)
AWS ALB DNS:       k8s-shop-api-xyz.elb.amazonaws.com
~~~

These addresses are examples only; EKS uses your actual Kubernetes Service CIDR and VPC subnet CIDRs. `api.example.com` only resolves on the Internet after creating a matching public DNS record; **the controller does not automatically create all Route 53 records from Ingress hostnames**.

## 3. What Does the AWS Load Balancer Controller Do?

The **AWS Load Balancer Controller (LBC)** runs inside the Kubernetes cluster (typically deployed in the `kube-system` namespace). It watches the Kubernetes resources it manages and **reconciles** actual AWS state toward the declared desired state.

~~~mermaid
flowchart TB
    DEV["DevOps declares YAML"] --> API["Kubernetes API Server"]
    API --> ING["Ingress + IngressClass"]
    API --> SVC["Service type LoadBalancer"]
    ING --> LBC["AWS Load Balancer Controller"]
    SVC --> LBC
    LBC -->|"AWS API + IAM role"| ELB["Elastic Load Balancing"]
    ELB --> ALB["ALB + listeners + rules + target groups"]
    ELB --> NLB["NLB + listeners + target groups"]
    LBC -->|"Target registration"| POD["Pod IP or EC2 NodePort"]
    ALB --> POD
    NLB --> POD
~~~

In a typical flow:

1. An engineer creates/updates an `Ingress` or `Service`.
2. The Kubernetes API stores the desired state.
3. The controller watches resources, validates configuration, and discovers relevant subnets, Security Groups, and endpoints.
4. The controller calls AWS ELBv2/EC2 APIs to create or update the ALB/NLB, listeners, rules, and target groups, then registers targets.
5. The controller updates status fields like `status.loadBalancer.ingress` and keeps reconciling as Pods change.

**Reconciliation is not a one-time “fire and forget” action.** After a Pod is replaced, HPA scales out, or you edit an Ingress, the controller updates target lists, rules, and AWS resources. If you manually edit the AWS ELB directly, manual changes may be overwritten during the next reconciliation loop.

### 3.1. How does the controller handle ALB and NLB?

| Kubernetes Entrypoint | AWS Resource Typically Created | Primary Traffic Model |
|---|---|---|
| **Ingress** with `alb` IngressClass/controller | **Application Load Balancer** | HTTP/HTTPS to host/path and Kubernetes backend Services |
| **Service type `LoadBalancer`** managed by LBC | **Network Load Balancer** | TCP/UDP/TLS per supported configurations |

When using **EKS Auto Mode**, AWS automatically manages certain load balancers, **differing from the self-managed controller deployment path**. Additionally, legacy Kubernetes cloud providers/controllers can also provision load balancers for Services. Therefore, **identify which controller owns each resource via `IngressClass` / `loadBalancerClass` / annotations and the active cluster setup**, preventing two controllers from fighting over one Service.

> **Principle:** before creating a `type: LoadBalancer` Service, verify which controller/`loadBalancerClass` matches your EKS and LBC versions. Annotations for self-managed LBC do not automatically behave identically in EKS Auto Mode.

## 4. Choosing ALB or NLB

### 4.1. Protocol layer differences

| Criterion | ALB | NLB |
|---|---|---|
| Primary layer | **Layer 7** (HTTP/HTTPS/gRPC as supported) | **Layer 4** (TCP/UDP/TLS as supported) |
| Routing rules | Host, path, HTTP headers, and supported listener conditions | Listener/protocol/port selection; no ALB-style HTTP path routing |
| Common Kubernetes resource | `Ingress` | `Service type LoadBalancer` |
| Certificates/TLS | HTTPS listener with ACM certificate | TLS listener for TLS termination, or TCP passthrough |
| Backends | Target groups with `instance` or `ip` per config | Target groups with `instance` or `ip` per config |
| HTTP features | Redirects, fixed responses, auth/WAF integrations | Does not offer ALB's full Layer 7 HTTP feature set |
| Example workloads | Web/API, multiple services under one domain | TCP services, Layer 4 gRPC, workloads requiring NLB characteristics |

**Choose by protocol, not just the word “LoadBalancer.”** An HTTP API routing `/catalog/*` and `/checkout/*` to two services usually fits ALB; a non-HTTP TCP service usually chooses NLB.

### 4.2. Multi-backend routing through ALB

~~~mermaid
flowchart LR
    C["HTTPS Client"] --> L["ALB listener :443"]
    L -->|"Host api.example.com + /catalog/*"| TC["Target group catalog"]
    L -->|"Host api.example.com + /checkout/*"| TP["Target group checkout"]
    TC --> PCS["Catalog Pod IPs :8080"]
    TP --> PPS["Checkout Pod IPs :9090"]
~~~

ALB listeners and target groups distribute traffic, while Kubernetes Deployments manage Pod counts. **Target group health checks** determine whether a target meets criteria to receive traffic, but they do not replace Kubernetes readiness/liveness probes or guarantee valid backend data.

### 4.3. Public or internal?

- **Internet-facing ALB/NLB:** accepts connections from external networks over the designed public path, still subject to Security Groups/WAF/TLS/network controls.
- **Internal ALB/NLB:** serves clients in networks with routing to the load balancer's private addresses (inside the VPC or via private links), **not exposed to the public Internet**.

A system can have a **public ALB** for customer requests and an **internal ALB/NLB** for internal APIs, though you should evaluate cost and failure scope for each LB.

## 5. Target Groups: `instance` or `ip`?

This is the single most important choice when connecting Kubernetes workloads to AWS ELBs.

### 5.1. Target type `instance`

When a target group uses `instance`, ELB registers **EC2 worker nodes** and sends traffic to the corresponding **NodePort** of the Kubernetes Service. The node then forwards requests to Pods via the dataplane/kube-proxy/CNI.

~~~text
ALB/NLB
  → EC2 node (instance ID + NodePort)
    → Kubernetes Service
      → Pod IP:containerPort
~~~

Requirements:

- Supported EC2 worker nodes exist as targets.
- The Service usually requires `NodePort` or controller-supported node-level routing.
- Security Groups and NACLs permit LB → node on the **NodePort** and return traffic.
- Check `externalTrafficPolicy`, topology, and target health per LB type as they affect traffic forwarding.

`instance` is not a direct option for **EKS Fargate-only Pods**, since Fargate does not expose EC2 worker nodes for instance target registration.

### 5.2. Target type `ip`

With `ip`, the controller registers **Pod IP addresses** into the target group; the load balancer sends traffic directly to **Pod IP:port**.

~~~text
ALB/NLB
  → Pod 10.20.11.31:8080
  → Pod 10.20.12.47:8080
~~~

Advantages:

- Eliminates the extra NodePort hop in many EKS setups using Amazon VPC CNI.
- Works with **EKS Fargate** or workloads preferring direct Pod IP targeting.
- Lets the target group track endpoints directly as Kubernetes replaces Pods.

Requirements:

- Pod IPs must be **routable from the load balancer** across VPC/CNI networking.
- Security Groups/network policies/NACLs must allow LB → Pod on the target port.
- Must account for the active CNI, pod readiness, IP capacity, and Security Groups for Pods if used.

**Never assume every Pod IP is directly reachable by AWS ELB**: if using overlay CNIs, multi-cluster networks, unsupported IP ranges, or custom routing, verify connectivity. With standard Amazon VPC CNI, Pods receive VPC IPs per configuration, fitting the `ip` model when other conditions hold.

### 5.3. Quick comparison table

| Scenario | Typical Target Type to Consider |
|---|---|
| EKS running on Fargate | **`ip`** |
| EKS EC2, LB routing directly to Pod IPs | **`ip`** |
| EKS EC2, traffic via worker node NodePort | **`instance`** |
| Pod IPs not routable from the LB | Simply setting `ip` will not work; redesign networking |

For ALB Ingress, the common annotation is:

~~~yaml
alb.ingress.kubernetes.io/target-type: ip
~~~

For an LBC-managed NLB Service, the annotation is:

~~~yaml
service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
~~~

**These two annotations belong to different resource types**—never copy an Ingress annotation onto a Service expecting the controller to interpret them identically.

## 6. Prerequisites Before Deploying the AWS Load Balancer Controller

### 6.1. Cluster and Kubernetes APIs

You need an operational EKS cluster, worker nodes/Fargate profiles per design, proper Kubernetes networking, and Kubernetes API permissions for the deployer. Standard resources include `Ingress` (`networking.k8s.io/v1` API), `Service`, and `Deployment`; the controller also creates and uses custom resources like `TargetGroupBinding` when needed.

If the cluster already runs another automated load balancer mechanism, verify ownership and compatibility before installing the AWS Load Balancer Controller. Legacy resource names or annotations may change support levels across versions.

### 6.2. Installing the controller and IAM

The controller is commonly installed via **Helm** or an AWS/EKS-supported method, running as a Deployment with a Kubernetes ServiceAccount attached to an **IAM role** authorized to manage Elastic Load Balancing, EC2 networking resources, tagging, and required APIs.

Two standard ways to supply AWS credentials:

1. **IAM Roles for Service Accounts (IRSA):** uses an OIDC provider linked to the EKS cluster, an IAM role trusting the exact ServiceAccount/namespace, and a Kubernetes projected token.
2. **EKS Pod Identity:** uses the Pod Identity Agent/add-on and an association binding the IAM role to the ServiceAccount where supported.

**Never attach `AdministratorAccess` to the controller just to fix deployment errors.** Use the official IAM policy provided by the AWS Load Balancer Controller docs for your exact version, scoping trust/roles and cluster permissions appropriately.

Example read-only check that the controller is running:

~~~bash
kubectl -n kube-system get deployment aws-load-balancer-controller
kubectl -n kube-system get pods \
  -l app.kubernetes.io/name=aws-load-balancer-controller -o wide
kubectl -n kube-system get serviceaccount aws-load-balancer-controller -o yaml
~~~

These are **read-only** commands. Label/ServiceAccount names may differ if the Helm release customized them; inspect the actual deployment and Helm release rather than assuming defaults.

### 6.3. Quotas and AWS API access

The controller calls EC2 and ELB APIs to discover VPCs/subnets/SGs, create target groups/listeners, and register targets. Common issues:

- Missing IAM actions for ELBv2, EC2 Describe, Security Groups, or tagging.
- Missing **outbound connectivity to AWS APIs** when the controller runs in a private cluster without NAT or compatible VPC endpoints.
- API throttling, quotas on ALBs/NLBs/target groups/listeners, or subnet IP limits.
- Security Group rule/quota exhaustion for backend traffic.

**Kubernetes RBAC and AWS IAM are separate layers:** a ServiceAccount might have Kubernetes RBAC to read Ingresses yet lack IAM to create an ALB; conversely, full IAM permissions do not grant Kubernetes API access if RBAC forbids it.

### 6.4. VPC CNI and Pod IP addresses

The `ip` target type requires network reachability from the load balancer to available Pod IPs. On EKS with **Amazon VPC CNI**, Pods normally receive VPC subnet addresses; reserve enough IPs for running Pods plus rollout bursts.

Look beyond EC2 node counts: Pod IPs, ENIs, prefix delegation, network policies, SG for Pods, and compute types all affect Pod density and network stability. Installing the controller **does not automatically fix** CNI, subnet routing, or IP exhaustion.

## 7. Subnet Discovery and Placement for ALB/NLB

AWS load balancers must be placed in appropriate subnets for ENIs/nodes and traffic handling. The controller discovers subnets via **tags and controller config**, or you can specify explicit subnet IDs per resource when needed.

### 7.1. Common subnet tags

| Subnet Type | Common Tag | Meaning |
|---|---|---|
| **Public** | `kubernetes.io/role/elb = 1` | Subnet intended for internet-facing load balancers |
| **Private** | `kubernetes.io/role/internal-elb = 1` | Subnet intended for internal load balancers |
| **Cluster association** (when used) | `kubernetes.io/cluster/<cluster-name> = shared` or `owned` | Indicates subnet association with a cluster and avoids ambiguity in shared VPCs |

Requirements around the **cluster association tag** have evolved across controller versions; newer versions may not require it in standard setups, yet in shared VPCs explicit subnet governance remains valuable. Never apply documentation from an older controller version to a newer one blindly.

### 7.2. Public/private subnets are more than names

A public subnet requires a default route to an **Internet Gateway** when hosting an internet-facing LB. An internal load balancer requires private routing to clients and backends. Security Groups, NACLs, and VPC route tables must still permit the traffic.

Example:

~~~text
VPC: 10.20.0.0/16

AZ A:
  public-a   10.20.0.0/24   (kubernetes.io/role/elb=1)
  private-a  10.20.11.0/24  (kubernetes.io/role/internal-elb=1)
  Pods       10.20.11.31, ...

AZ B:
  public-b   10.20.1.0/24   (kubernetes.io/role/elb=1)
  private-b  10.20.12.0/24  (kubernetes.io/role/internal-elb=1)
  Pods       10.20.12.47, ...
~~~

An **ALB** is typically configured across **at least two subnets in two different AZs**; ensure free IPs meet ALB and LBC requirements. If one AZ runs out of IPs or lacks a tagged subnet, the controller may fail to provision the ALB or struggle during scaling.

### 7.3. Explicitly specifying subnets on Ingress

To control exact ALB placement, use the annotation:

~~~yaml
alb.ingress.kubernetes.io/subnets: subnet-0a111111111111111,subnet-0b222222222222222
~~~

Both subnet IDs must belong to the cluster's VPC, span appropriate AZs, and match the scheme's routes/roles. These values are examples only, not live AWS resources. Explicit subnets prevent the controller from picking wrong subnets in shared VPCs, at the cost of higher maintenance when topology changes.

### 7.4. Subnet IPs and per-AZ considerations

Subnets need sufficient IPs for **load balancer ENIs/nodes**, Pods, VPC endpoints, and other resources. Changing AZs/subnets or creating multiple LBs increases IP demand. For true high availability, verify **routing and capacity in every AZ**, not merely two subnet IDs in an annotation.

## 8. Sample Architecture: Exposing an HTTPS API via ALB

Suppose the shop API runs on EKS in **private subnets across two AZs**, while an ALB receives HTTPS traffic from the Internet.

~~~mermaid
flowchart TB
    U["Internet client"] --> DNS["Route 53: api.example.com"]
    DNS -.->|"DNS resolves to ALB"| U
    U --> ALB["Internet-facing ALB\nHTTPS listener :443\nSG: sg-alb"]
    ALB --> TG["Target group: target-type ip\nHTTP backend :8080"]
    subgraph VPC["Amazon VPC, EKS cluster"]
      subgraph A["AZ A"]
        PUBA["Public subnet A"]
        PODA["Pod A private IP :8080"]
      end
      subgraph B["AZ B"]
        PUBB["Public subnet B"]
        PODB["Pod B private IP :8080"]
      end
      TG --> PODA
      TG --> PODB
      PODA --> DB["RDS / private downstream"]
      PODB --> DB
    end
~~~

Request path:

1. Client resolves `api.example.com` to the ALB DNS name (via a Route 53 alias or matching CNAME).
2. Client connects on `HTTPS :443` to the public ALB.
3. The ALB listener evaluates host/path and selects the matching target group.
4. With `target-type: ip`, the ALB forwards the request over the VPC to the registered **Pod IP:8080**.
5. The Pod must listen on an address reachable from outside the Pod (`0.0.0.0:8080` where appropriate), permitted by Security Groups/network policies.
6. The Pod connects to databases/backends as needed and returns the HTTP response to the ALB and client.

**Individual Pods do not need public IPs.** The ALB holds the public endpoint; Pods stay in private subnets. When a Pod is replaced, the controller updates target group IPs.

## 9. Sample Manifests: Deployment, ClusterIP Service, and ALB Ingress

The following YAML is **unapplied** and solely explains how components fit together. It assumes the cluster already has the AWS Load Balancer Controller, matching `IngressClass`, public/private subnets, and sufficient IAM permissions.

### 9.1. IngressClass for the AWS Load Balancer Controller

~~~yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
spec:
  controller: ingress.k8s.aws/alb
~~~

Create this `IngressClass` only if no matching class exists and cluster policy permits it. Some charts/clusters pre-create it; **do not duplicate resources** or overwrite a class used by other workloads without checking.

### 9.2. API Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
  namespace: shop
spec:
  replicas: 4
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: api
          image: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/shop-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 3
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
~~~

**Note:** the `shop` namespace must exist. The image URI is illustrative and not guaranteed to exist; proper ImagePull/authentication, IAM/node role, or Fargate execution role are required. Readiness/liveness endpoints must actually be **served by the application**; a wrong probe path leaves Pods unready even while containers are running.

### 9.3. ClusterIP Service behind Ingress

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: shop-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: shop-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

The Service selects Pods with label `app: shop-api` and exposes port **80** inside Kubernetes. When the Ingress backend references `shop-api:80`, LBC resolves Pods/EndpointSlices and registers **Pod IP:8080** in `ip` mode. Note the distinction between **Service port 80** and **container target port 8080**.

### 9.4. HTTPS Ingress provisioning an ALB

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-api
  namespace: shop
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP":80},{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-southeast-1:123456789012:certificate/00000000-1111-2222-3333-444444444444
    alb.ingress.kubernetes.io/healthcheck-path: /health/ready
    alb.ingress.kubernetes.io/healthcheck-port: traffic-port
    alb.ingress.kubernetes.io/success-codes: "200"
spec:
  ingressClassName: alb
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: shop-api
                port:
                  number: 80
~~~

Explanation:

| Field | Meaning |
|---|---|
| `spec.ingressClassName: alb` | Assigns the Ingress to the controller managing class `alb` |
| `scheme: internet-facing` | Creates an ALB with an internet-facing scheme in appropriate subnets |
| `target-type: ip` | Registers Pod IPs into the target group |
| `listen-ports` | Listens on HTTP 80 and HTTPS 443 on the ALB as configured |
| `ssl-redirect` | Redirects HTTP clients to HTTPS 443 via listener rule |
| `certificate-arn` | Valid ACM certificate for `api.example.com` in the ALB's Region |
| `healthcheck-path` | ALB probes `/health/ready` on targets |
| `spec.rules[*].http.paths` | Selects Kubernetes Service backends by host/path |

**Prerequisites still missing before production:** subnet tags/routes, Security Groups, ALB access logs/WAF if needed, controller permissions, Route 53 DNS, domain ownership, real ACM certificate, application container image, observability, rollback, and cost plan. Never use placeholder ARNs in live environments.

### 9.5. Status after creating the Ingress

Once the controller reconciles successfully:

~~~bash
kubectl -n shop get ingress shop-api
~~~

displays the **AWS ALB DNS name** in the `ADDRESS` column. For clients to reach `api.example.com`, create a **Route 53 A/AAAA alias** or appropriate DNS record pointing to the ALB. Many teams run **ExternalDNS** to sync DNS from Kubernetes annotations/rules; that is a **separate controller**, not the AWS Load Balancer Controller creating Route 53 records on its own.

## 10. Service Type LoadBalancer Provisioning an NLB

Not every service belongs behind an HTTP Ingress. For TCP apps, internal services, or cases needing an NLB, `Service type: LoadBalancer` is the standard declaration.

### 10.1. NLB via LBC and `loadBalancerClass`

On AWS Load Balancer Controller versions supporting class `service.k8s.aws/nlb`, you can define:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: tcp-gateway
  namespace: shop
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-scheme: internal
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
spec:
  type: LoadBalancer
  loadBalancerClass: service.k8s.aws/nlb
  selector:
    app: tcp-gateway
  ports:
    - name: tcp
      port: 8443
      targetPort: 8443
      protocol: TCP
~~~

This example assumes Pods carry label `app: tcp-gateway` and listen on TCP `8443`. Expected outcome: an **internal NLB** forwarding traffic to Pod IPs on port 8443, with no public IPs on Pods.

**Version note:** `loadBalancerClass` and annotations depend on controller/Kubernetes versions and load balancer management modes. Older setups used annotation `service.beta.kubernetes.io/aws-load-balancer-type: external`; in **EKS Auto Mode**, classes/annotations may differ. Before applying, confirm **which controller will handle the Service** rather than mixing guides from two controllers.

### 10.2. When an internet-facing NLB is needed

Changing scheme to `internet-facing` is only one step. You still need properly chosen public subnets, routes, TLS/certificates if using TLS listeners, client reachability, Security Groups/NACLs, and source restrictions. NLB operates at Layer 4 and **cannot route `/catalog` vs. `/checkout` by HTTP path**.

### 10.3. NLB health checks and source IP

NLB target groups also perform health checks. With `ip` targets, verify NLB reachability to **Pod IP:port**. With `instance` targets, verify the path to nodes/NodePorts.

Design points to check:

- Health check protocol/port/path must match the service.
- **Source IP seen by backends** depends on target type, protocol, client-IP preservation, and deployment details; never assume every NLB preserves source IP identically.
- Kubernetes `externalTrafficPolicy` affects routing/health when using target type `instance`.
- If attaching Security Groups to an NLB or backends, verify controller SG management capabilities and active network model.

## 11. Security Groups and VPC Networking for ALB/NLB

AWS Security Groups provide **stateful** filtering at ENIs. For an internet-facing ALB with Pod IP targets, three zones are typically involved:

~~~text
Client HTTPS :443
  → ALB Security Group
    → Target group (Pod IP :8080)
      → Node/Pod networking + Security Groups / NetworkPolicy
        → Container listener :8080
~~~

### 11.1. ALB and backend rules

| Resource | Typical Inbound | Outbound to Check |
|---|---|---|
| **ALB SG** | TCP 443 from valid clients/CIDRs; TCP 80 if redirecting HTTP | TCP 8080 to backend IP/SG group and health check port |
| **Node / Pod SG** (by network design) | TCP 8080 from ALB SG or approved source group | Calls to databases, AWS APIs, DNS, and real dependencies |
| **Database SG** | DB port only from authorized app Pod/Node SGs | As required by service |
| **Interface VPC endpoint SG** | TCP 443 from authorized Pod/Node sources | Stateful return |

Kubernetes **NetworkPolicy** (when supported and enabled by the CNI/network policy engine) adds another layer. Do not assume NetworkPolicies are enforced by default in every EKS cluster; verify the Amazon VPC CNI Network Policy feature or active policy engine.

### 11.2. Automatic vs. manual Security Group management by the controller

AWS LBC can create/attach frontend Security Groups for load balancers and **manage backend security group rules** when conditions/versions align.

When manually specifying an SG for an ALB:

~~~yaml
alb.ingress.kubernetes.io/security-groups: sg-0123456789abcdef0
~~~

Verify whether the controller will **automatically update backend security group rules** or whether you must manage them yourself. An annotation exists:

~~~yaml
alb.ingress.kubernetes.io/manage-backend-security-group-rules: "true"
~~~

However, do not add it mechanically to every environment; it carries IAM permissions, SG topology constraints, and specific controller rules. A controller-created SG and a manually attached SG **are not necessarily managed identically**.

### 11.3. NACLs and ephemeral ports

**Stateless** subnet Network ACLs can block traffic even when Security Groups allow it:

- Client → ALB needs inbound on public subnet port 443; ALB → client needs outbound to the client's ephemeral ports.
- ALB → Pod IP needs outbound from the ALB subnet and inbound to the Pod subnet on port 8080; Pod → ALB responses return to ALB ephemeral ports.
- Custom NACLs need explicit rules in both directions plus flows for DB, DNS, and image pulls.

Trace **source IP:source port → destination IP:destination port** pairs and their reverse paths for responses. Never open only TCP 443 in both directions expecting return packets to pass a stateless NACL.

### 11.4. Egress and image pulls

Pods in private subnets may need outbound connectivity to pull images from **Amazon ECR**, or call Secrets Manager, CloudWatch Logs, STS, and other APIs. Depending on platform, image pulls are performed by the node/container runtime or Fargate; verify permissions and networking for the responsible role.

Egress options:

- **NAT Gateway** for reaching public AWS APIs/endpoints and required Internet destinations.
- **VPC endpoints** for supported services (e.g., ECR API/DKR, S3 gateway, CloudWatch Logs, STS), with proper SGs, DNS, and endpoint policies.
- **Kubernetes API Server** access path matching the cluster's public/private endpoint configuration.

Failures in image pulls, STS, WebIdentity/Pod Identity, or log delivery can keep Pods unready even after the ALB itself was created successfully.

## 12. Health Checks, Readiness, and Rollouts

### 12.1. Two kinds of “healthy”

**Kubernetes `readinessProbe`** decides whether a Pod is ready to receive traffic via a Kubernetes Service. **ALB/NLB target health** is evaluated by AWS ELB against registered targets. They are related but **not identical**:

| Signal | Who Checks? | Common Criteria |
|---|---|---|
| `readinessProbe` | Kubelet | HTTP/TCP/exec/gRPC probe inside Pod |
| `livenessProbe` | Kubelet | Whether container needs restart |
| **ALB target group health** | ELB health checks | HTTP/HTTPS path/status or protocol per target group |
| **EKS controller reconciliation** | AWS Load Balancer Controller | Target group/target registration and resource state |

For example, a Deployment specifies readiness `GET /health/ready`, and the Ingress annotation sets target health path `/health/ready`. If the app binds a different port, an SG blocks 8080, or the response is not 200, targets become **unhealthy** even while Pods show `Running`.

### 12.2. Pod readiness gates for ALB targets

The AWS Load Balancer Controller can use **Pod readiness gates** via an appropriate webhook/configuration so Kubernetes checks target group registration health before marking a Pod ready. A common namespace label enables injection:

~~~yaml
metadata:
  labels:
    elbv2.k8s.aws/pod-readiness-gate-inject: enabled
~~~

**Do not treat the label alone as a guarantee of success.** Pod readiness gates are injected at Pod creation time by the webhook when matching a Service/target group; apply the namespace label **before creating Pods**, and verify controller/webhook and target type support. During strict rollouts, readiness gates help prevent terminating old Pods before new targets are healthy on the ALB.

### 12.3. Graceful termination and draining

During a Deployment update:

1. Kubernetes creates new Pods (per `maxSurge`, `maxUnavailable`, and available capacity).
2. The controller detects endpoint/target changes and registers new targets.
3. ALB/NLB evaluates target health.
4. Old Pods enter termination/deregistration; ELB enforces a **deregistration delay** to drain in-flight connections/requests.
5. Containers receive `SIGTERM` and should finish in-flight requests within an appropriate `terminationGracePeriodSeconds`.

**Do not equate** Pod `Ready`, ELB target `healthy`, and successful business requests. Minimize 5xx errors during rollouts by coordinating readiness gates, deployment strategies, connection draining, shutdown handlers, capacity, and metrics.

### 12.4. When all targets are unhealthy

In certain scenarios, an ALB exhibits **fail-open** behavior when all registered targets in a target group across enabled AZs fail health checks: it may still route traffic to them. Thus, health checks never replace in-app authN/authZ or data protection controls, nor act as a “firewall” blocking traffic when backends fail.

## 13. IngressGroup, Multiple Services, and Security Boundaries

AWS LBC provides **IngressGroup** to let multiple Ingresses share **a single ALB**, reusing listeners/rules and reducing LB count.

Example annotations:

~~~yaml
alb.ingress.kubernetes.io/group.name: shop-public
alb.ingress.kubernetes.io/group.order: "10"
~~~

Key considerations:

- Multiple Ingresses sharing `group.name` share one ALB.
- Rules merge onto the ALB and are ordered per controller logic, where `group.order` sets priority.
- **Trust boundary:** anyone permitted to create/edit an Ingress with the same group name can affect routing for other apps in the group. Never share an IngressGroup across **mutually untrusted teams** without proper admission/RBAC controls.
- Reusing a single ALB improves cost efficiency while increasing the **blast radius** of listener, security group, or WAF changes.

**Example:** checkout and catalog both specify IngressGroup `shop-public`. Someone on the catalog team permitted to create Ingresses should not be able to hijack `/checkout/*`. Without restricting group membership and namespace authorization, they could declare competing rules. Kubernetes namespaces **do not automatically isolate** shared AWS resources inside an IngressGroup.

## 14. Linking DNS, TLS, WAF, and Traffic Sources

### 14.1. Route 53 records do not appear automatically from `Ingress.host`

After an Ingress provisions an ALB:

~~~text
Ingress host: api.example.com
ALB DNS name: k8s-shop-shopapi-123456789.ap-southeast-1.elb.amazonaws.com
~~~

You still need a Route 53 alias or matching DNS record pointing `api.example.com` to the ALB. If using **ExternalDNS**, it reads Kubernetes resources under its granted permissions to manage Route 53 records; that is a **separate operational component** requiring its own IAM policy.

### 14.2. HTTPS with ACM

For an ALB HTTPS listener:

- The ACM certificate must be valid for the served hostnames and reside in the **same Region as the ALB**.
- `certificate-arn` specifies the certificate for ALB TLS termination.
- If redirecting HTTP → HTTPS, listener port 80 must also be intentionally designed and scoped.
- ALB → Pod **HTTP** backend differs from end-to-end TLS; if internal hop encryption is required, configure target-group/backend protocols and server TLS.

Never hardcode certificate secrets or private keys inside Kubernetes manifests when ACM can manage TLS on the ALB.

### 14.3. WAF, authentication, and access control

An ALB can integrate with **AWS WAF** to filter HTTP requests when configured; OIDC/Cognito authentication, header rules/redirects, and app protections also depend on specific annotations and requirements. **WAF does not replace authorization inside the application** or IAM governing AWS API calls.

For internal apps, never expose `internet-facing` just for a “quick test.” Use the `internal` scheme and authorized client networks (VPN, Direct Connect, VPC peering/TGW as appropriate), verifying routes and SGs.

## 15. Diagnostics with kubectl and AWS CLI (Read-Only)

These commands only read state and do not deploy resources. Assume namespace `shop`, Ingress `shop-api`, and Service `shop-api`. Proper kubeconfig/context and AWS account/Region permissions are required.

### 15.1. Check kubeconfig and Ingress

~~~bash
kubectl config current-context
kubectl get ingressclass
kubectl -n shop get ingress shop-api -o wide
kubectl -n shop describe ingress shop-api
kubectl -n shop get events --sort-by=.lastTimestamp
~~~

Inspect **Events**:

- Unable to find valid subnets.
- Missing IAM API permissions.
- Unable to resolve Security Groups or VPC.
- Unsupported annotation/IngressClass configuration.
- Listener/target group creation blocked by quotas or misconfiguration.

If `ADDRESS` remains empty, do not assume you just need to wait for DNS TTL; first verify **whether the controller reconciled the Ingress and created the ALB**.

### 15.2. Check Service, Pods, and EndpointSlices

~~~bash
kubectl -n shop get svc shop-api -o yaml
kubectl -n shop get pods -l app=shop-api -o wide
kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=shop-api
kubectl -n shop describe deployment shop-api
~~~

If the `app: shop-api` selector fails to match Pod labels, the Service has no endpoints and the target group stays empty or unhealthy. If Pods are not Ready, inspect image pulls, readiness probes, resource requests, IAM for ECR/secrets, and application logs.

### 15.3. Check controller and logs

~~~bash
kubectl -n kube-system get deployment aws-load-balancer-controller
kubectl -n kube-system logs \
  deployment/aws-load-balancer-controller \
  --tail=200
kubectl get targetgroupbindings -A
~~~

`TargetGroupBinding` is a CRD provided by LBC; resource names and listing availability depend on controller version and installation. Logs are diagnostic data—never paste tokens or secrets into public tickets.

### 15.4. Inspect ALB, target groups, and target health

~~~bash
aws elbv2 describe-load-balancers \
  --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Type:Type,Scheme:Scheme,State:State.Code,DNS:DNSName}" \
  --output table

aws elbv2 describe-target-groups \
  --region ap-southeast-1 \
  --target-group-arns TARGET_GROUP_ARN \
  --query "TargetGroups[].{Name:TargetGroupName,Type:TargetType,Protocol:Protocol,Port:Port,HealthPath:HealthCheckPath}" \
  --output json

aws elbv2 describe-target-health \
  --region ap-southeast-1 \
  --target-group-arn TARGET_GROUP_ARN \
  --query "TargetHealthDescriptions[].{Target:Target,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" \
  --output json
~~~

Replace `TARGET_GROUP_ARN` with the real target group ARN found via AWS Console/API or controller-created resources. For `ip` target type, `Target.Id` is usually the **Pod IP**; for `instance`, it is the EC2 instance ID.

### 15.5. Inspect subnet tags and Security Groups

~~~bash
aws ec2 describe-subnets \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "Subnets[].{Id:SubnetId,AZ:AvailabilityZone,AvailableIPs:AvailableIpAddressCount,Tags:Tags}" \
  --output json

aws ec2 describe-security-groups \
  --region ap-southeast-1 \
  --group-ids sg-0123456789abcdef0 \
  --query "SecurityGroups[].{Id:GroupId,Ingress:IpPermissions,Egress:IpPermissionsEgress}" \
  --output json
~~~

IDs are placeholders only. Inspect the actual subnets selected by the LB, plus ingress/egress rules on both the ALB SG and backend SGs rather than guessing from resource names.

### 15.6. Test the website once DNS is ready

~~~bash
dig api.example.com A
curl -I https://api.example.com/health/ready
~~~

`dig` and `curl` must be installed, and the domain and TLS certificate must be real. If TLS is not configured or DNS does not yet point to the ALB, these tests fail; never work around failures by disabling TLS verification or opening SGs to the entire Internet.

## 16. Common Failure Table and Troubleshooting

| Symptom | Common Causes | Priority Checks |
|---|---|---|
| **Ingress has no ADDRESS** | Controller not running, wrong IngressClass, missing IAM, subnet discovery error | Controller logs, `kubectl describe ingress`, IAM, and tags |
| **Controller AccessDenied** | Bad IRSA/Pod Identity association/trust or IAM policy missing actions | ServiceAccount, IAM role, OIDC/Pod Identity Agent, CloudTrail |
| **Failed build model / no subnets found** | Wrong tags, insufficient subnets/AZs, low free IPs | Subnet tags, AZs, routes, controller version |
| **ALB created, domain does not resolve** | Missing Route 53 record/ExternalDNS or broken DNS delegation | Ingress ADDRESS, authoritative DNS |
| **HTTPS cert error** | ACM cert in wrong Region/hostname/status, misconfigured ALB listener | Certificate ARN, validation, listener 443 |
| **Target group empty** | Wrong Service selector, no EndpointSlices/Ready Pods, LBC reconcile error | Service, Pod labels, controller logs |
| **Target.Timeout** | SG/NACL blocking Pod port, Pod bound to localhost only, routing/CNI error | ALB SG, Pod IP, port, routes, and listener |
| **Target.ResponseCodeMismatch** | Wrong health path, app returns 301/401/404/500 instead of 200 | `/health/ready`, matcher, app logs |
| **Pod Running yet ALB unhealthy** | ALB health check is independent of Kubernetes readiness | Target group health, SG/port/path |
| **ImagePullBackOff** | ECR credentials/network, nonexistent image/tag, node/Fargate role missing perms | Pod events, ECR/S3/NAT/endpoints, IAM |
| **LoadBalancer Service lacks EXTERNAL-IP/hostname** | Wrong class/controller, IAM, subnets, or quotas | `kubectl describe svc` and controller logs |
| **IngressGroup routing changed unexpectedly** | Multiple teams sharing a group, `group.order`/rule conflict | RBAC, namespaces, IngressGroup annotations |
| **502/503/504 from ALB** | Backend errors, missing/unhealthy targets, timeouts, malformed responses | ALB metrics/access logs + target health + Pod logs |
| **Exposed fine, yet loses service on AZ outage** | Pods/backends/capacity in a single AZ; multi-AZ ALB subnets alone aren't enough | Pod distribution, PDBs, HPA/ASG, RDS/egress |

**Never fix issues by opening all Security Groups or granting `AdministratorAccess` to the controller.** Identify the exact failing layer and add only the tightly scoped permission/route/port required.

## 17. Multi-AZ, Scaling, Readiness, and Resilience

### 17.1. A two-AZ ALB does not make the application HA

Suppose the ALB spans AZs A and B, yet all four Pods sit on EC2 nodes in AZ A. If AZ A fails, the ALB in AZ B may still answer DNS, yet **zero healthy Pods** remain to serve requests.

Production design requires:

- **Worker nodes/Pools** or Fargate placement across multiple AZs.
- **Pod topology spread constraints** or suitable scheduling rules; never let all replicas land in one AZ.
- **PodDisruptionBudgets (PDBs)** to limit voluntary disruptions; PDBs **do not prevent AZ outages**.
- **HPA/Karpenter/Cluster Autoscaler or capacity managers**, with spare quotas and IP headroom.
- Fault-tolerant data and dependencies such as RDS, ElastiCache, EFS, S3, and egress/NAT per requirements.

### 17.2. Calculating capacity when one AZ is unavailable

Suppose an app must serve **300 requests/second** at peak. Benchmarks show each Pod reliably serves **100 requests/second** within the target latency SLO.

~~~text
Capacity needed after losing 1 AZ = 300 req/s
Benchmarked capacity per Pod = 100 req/s
Surviving Pods required = ceil(300 / 100) = 3

Split evenly across 2 AZs, each AZ must maintain at least 3 Pods
Total Pods in normal operation = 6 Pods
~~~

This is a minimal model. Real systems need margin for traffic spikes, CPU/memory, connection pools, data-store limits, HPA reaction time, quotas, node disruptions, and time for new targets to pass health checks. **Never rely purely on autoscaling after an AZ is already lost** if your SLO cannot tolerate the delay.

### 17.3. Private networking and per-AZ NAT

The controller can place a public ALB across two AZs while private Pods still need **egress** to ECR, STS, AWS APIs/telemetry, and dependencies. If all private subnets route through a single NAT Gateway in AZ A, an AZ A outage cuts off egress for Pods in AZ B. Consider per-AZ NAT or multi-AZ VPC endpoints with proper DNS/SGs, balancing cost against resilience.

### 17.4. Deployment and rollback

During a rolling update, new Pods must pull images, schedule, become Ready, register as targets, and pass ELB health checks before taking load. Combine appropriate `maxSurge/maxUnavailable`, readiness gates, grace periods, target deregistration delays, and application graceful shutdown. A Kubernetes rollback does not necessarily revert all separately edited ELB resources when multiple Ingresses share an ALB; maintain IaC/config reviews and change-control permissions.

## 18. Monitoring, Security, and Operational Cost

### 18.1. Metrics to watch

| Component | Suggested Metrics / State |
|---|---|
| **ALB** | `RequestCount`, `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime` |
| **Target group** | `HealthyHostCount`, `UnHealthyHostCount`, `TargetConnectionErrorCount` |
| **Kubernetes** | Pod Ready/Restarts, Deployment available replicas, events, `EndpointSlices` |
| **Controller** | Reconciliation errors, leader/controller logs, crashes/restarts |
| **Nodes/Pods** | CPU, memory, IP exhaustion, network drops, CNI health |
| **Networking** | VPC Flow Logs, ALB access logs, SG/NACL config changes |
| **Costs** | LB hours/LCUs or NLCUs, public IPv4, cross-AZ data transfer, NAT/PrivateLink endpoints, CloudWatch logs |

**`HealthyHostCount > 0` does not prove enough capacity remains after losing an AZ.** Alerts should check minimum target counts required to meet SLOs across multiple AZs.

### 18.2. Security responsibilities

- **RBAC and admission policies:** restrict who can create/modify Ingresses, `LoadBalancer` Services, IngressGroups, Security Group annotations, and hostnames.
- **Controller IAM:** scope AWS API access, trust only the controller ServiceAccount in its namespace, and avoid sharing that role with workloads.
- **Application IAM:** use IRSA/Pod Identity scoped to app needs; never reuse controller permissions for applications.
- **Network:** public/internal schemes, ALB/Pod SGs, NetworkPolicies (if enforced), NACLs, TLS, and WAF.
- **Infrastructure changes:** GitOps/IaC reviews, CloudTrail, log retention, alerts on public LB creation or SG changes.
- **Data:** in-app authN/authZ, secrets management, DB least privilege, encryption, and backups.

Allowing a developer to create unrestricted public Ingresses effectively lets them provision **Internet-facing AWS endpoints**. Permission to create those Kubernetes resources should therefore be governed like network infrastructure permissions, not merely “YAML deploy access.”

### 18.3. Cost control

Each standalone Ingress can provision a dedicated ALB, increasing hourly and usage charges. IngressGroups share an ALB at the cost of a larger shared blast radius across teams. NLBs have a different pricing model from ALBs. Beyond LB fees, account for:

- Cross-AZ data transfer, LB-to-target traffic, and cross-Region/VPC traffic along actual paths.
- EC2/Fargate, public IPv4 addresses, and subnet/IP planning.
- NAT Gateways, interface VPC endpoints, WAF, CloudWatch Logs/metrics, and request volumes.
- Staging, blue/green, or canary environments requiring extra LBs/target groups.

No single model is “always cheapest.” Choose based on protocol, security, availability, service count, traffic volume, and team isolation policies.

## 19. Safe Deployment Procedure

1. **Choose the exposure path:** multi-path/host HTTP(S) → Ingress/ALB; Layer 4 TCP/UDP/TLS → Service/NLB; internal or internet-facing?
2. **Verify ownership:** self-managed LBC, EKS Auto Mode, or another controller? Select matching `IngressClass`/`loadBalancerClass`.
3. **Prepare cluster networking:** subnets with right routes/tags/AZs, VPC CNI, Pod IP space, SGs/NACLs, egress, and DNS.
4. **Configure controller permissions:** IRSA/Pod Identity, version-matched IAM policy, Kubernetes RBAC, and AWS API connectivity.
5. **Deploy the app first:** Pod/Deployment with readiness/liveness probes, resource requests, image access, and matching Service selectors/ports.
6. **Declare the ALB/NLB:** target type, scheme, subnets, listeners, certificates, health checks, Security Groups, and annotations.
7. **Observe reconciliation:** Ingress/Service events, controller logs, and AWS ELB/target group state.
8. **Test end-to-end:** DNS → HTTPS/TCP → LB → Pod → database; verify status codes, source IP, auth, and TLS.
9. **Test rollouts and AZ loss:** verify target draining, readiness, capacity headroom, and surviving egress paths.
10. **Post-deploy monitoring:** alerts, logs, AWS cost, IAM/SG change auditing, and a tested rollback plan.

### 19.1. Production checklist

- [ ] Identified the controller and `IngressClass` / `loadBalancerClass`; no conflicting controllers.
- [ ] Controller is healthy, with accurate ServiceAccount/IRSA/Pod Identity role and AWS API networking.
- [ ] Public/private subnets have accurate routes, tags, multi-AZ coverage, and sufficient IPs.
- [ ] Target type `ip`/`instance` aligns with Fargate/EC2, CNI, and Pod networking.
- [ ] Kubernetes Service selectors, port/targetPort, readiness probes, and container listeners match.
- [ ] ALB/NLB health checks, listeners, target groups, and SGs/NACLs allow intended traffic.
- [ ] Route 53 DNS and ACM/TLS are configured; no internal service accidentally exposed publicly.
- [ ] IngressGroups and shared LBs align with team trust boundaries.
- [ ] Logs/metrics/CloudTrail and alerts on target health/reconcile errors are verified.
- [ ] Pod replication, AZ capacity, rollout/draining, and downstream data tiers meet SLOs.
- [ ] ALB/NLB, public IP, NAT/endpoints, transfer, and WAF costs are budgeted.

## 20. Reinforcement Exercises

### Exercise 1 — ALB or NLB?

A website needs to route `/catalog/*` and `/checkout/*` to two differently named Kubernetes Services. Another app uses raw TCP on port 5432.

**Hint:** the website needs Layer 7 routing → **ALB + Ingress**; the TCP app can evaluate **NLB + Service type LoadBalancer** if an LB is needed. For databases, never expose `5432` publicly by default; assess internal access and auth first.

### Exercise 2 — Wrong target type chosen

EKS Fargate runs Pods at `10.20.11.31:8080`, yet the Ingress annotation specifies `target-type: instance`. Why is this unsuitable?

**Hint:** `instance` registers EC2 worker instances/NodePorts; Fargate Pods do not have EC2 worker nodes in that model. Choose **`ip`** and ensure ELB can reach Pod IPs.

### Exercise 3 — Pod Running but target unhealthy

A Deployment container listens on `127.0.0.1:8080`. Service port 80 → targetPort 8080. ALB health checks hit Pod IP:8080 and time out.

**Hint:** the listener only binds loopback inside the Pod, so external traffic to the Pod IP cannot connect. Update the app to listen on `0.0.0.0:8080` where appropriate and verify SGs/NACLs.

### Exercise 4 — Ingress still lacks an ADDRESS

`kubectl describe ingress` reports no matching subnets found. The cluster has two private subnets, yet lacks public subnet tags. Requirements call for an internet-facing ALB.

**Hint:** you need public subnets with routes/an Internet Gateway, matching `kubernetes.io/role/elb` tags or valid explicit subnet IDs, across multiple AZs with enough IPs.

### Exercise 5 — Service has endpoints but no target group exists

You created a `ClusterIP` Service whose selector matches Pods, without creating an Ingress or controller-managed `Service type LoadBalancer`. Why is there no AWS ELB?

**Hint:** `ClusterIP` is an internal Kubernetes service only; it does not provision an ALB/NLB. Declare a matching Ingress or a `LoadBalancer` Service with the right class/controller.

### Exercise 6 — Shared IngressGroup between two teams

Two independent teams share `alb.ingress.kubernetes.io/group.name=shared-prod`. Team A can create Ingresses with arbitrary hosts/paths. Identify the risk and mitigations.

**Hint:** Team A can define routing rules impacting Team B on the shared ALB. Separate groups along trust boundaries, enforce RBAC/admission policies, review annotations/hostnames, and restrict who can create public ALBs.

### Exercise 7 — RTO during an AZ outage

Six Pods are spread evenly across two AZs, each safely handling 100 req/s. Peak traffic is 320 req/s. If one AZ fails, does sufficient capacity remain?

**Hint:** three remaining Pods = 300 req/s, **insufficient** for 320 req/s peak. You need at least four surviving Pods (e.g., four Pods/AZ in a two-AZ setup) and must verify DB/egress/node capacity.

### Exercise 8 — Comparing NetworkPolicy and SG

A cluster restricts the ALB SG to reach Pod port 8080. Is that enough to block another Pod inside the cluster from calling that API?

**Hint:** depends on CNI, SG for Pods/nodes, and inter-Pod networking. To control **east–west** traffic, examine NetworkPolicies or explicit Security Group topology; never assume the ALB SG governs all Pod→Pod traffic.

## 21. Key Takeaways

The **AWS Load Balancer Controller** bridges **Kubernetes desired state** and **AWS ELB resources**. It reconciles `Ingress` objects into **ALBs** and eligible `Service type LoadBalancer` objects into **NLBs**, continuously tracking target registration as Pods change.

Always verify the five links in the serving path:

1. Is the **Ingress/Service class** owned by the intended controller?
2. Is the **load balancer** placed in the right subnets, scheme, AZs, and listeners?
3. Does **target type** (`ip` vs. `instance`) match your Pod networking/Fargate/EC2 setup?
4. Do **Security Groups/NACLs** permit LB-to-Pod IP/NodePort traffic and return responses?
5. Do **Kubernetes readiness + ELB health checks** accurately reflect a backend ready to serve?

Production readiness also demands **least-privilege IAM, DNS/TLS, AZ capacity, safe rollouts/draining, monitoring, and cost control**. An Ingress creating an ALB does not prove the system is secure or resilient; verify the full traffic path and realistic failure scenarios.

### Official AWS and Kubernetes Documentation

- [AWS Load Balancer Controller documentation](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/) — overview, installation, and versions.
- [AWS Load Balancer Controller: Ingress annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/annotations/) — target type, listeners, SGs, health checks, and IngressGroup.
- [AWS Load Balancer Controller: Service annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/service/annotations/) — NLB Service, target type, internal/public, and class.
- [Subnet discovery](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/subnet_discovery/) — subnet roles, tags, and auto-discovery.
- [IngressClass and IngressClassParams](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/ingress_class/) — selecting the right controller.
- [EKS: Route application and HTTP traffic with Application Load Balancers](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html) — ALBs in EKS.
- [EKS: Route TCP and UDP traffic with Network Load Balancers](https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html) — NLBs with EKS.
- [EKS: Install AWS Load Balancer Controller](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html) — installing controller and IAM.
- [EKS: Assign IAM roles to Kubernetes service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — IRSA.
- [EKS: Pod Identities](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — IAM roles for ServiceAccounts via Pod Identity.
- [EKS: EKS Auto Mode load balancing](https://docs.aws.amazon.com/eks/latest/userguide/auto-configure-nlb.html) — differences between automated management and self-installed LBC.
- [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) and [Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/) — Kubernetes APIs and terminology.
- [Elastic Load Balancing: Target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — health, states, and failure reasons.
