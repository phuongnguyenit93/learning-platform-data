# VPC Lattice and Service Connectivity Across Multiple VPCs

> **Chapter:** Advanced Network Connectivity  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem from Regions/Availability Zones (AZs), IAM, and VPCs to compute, storage, databases, integration, and serverless; build skills in selecting services and designing applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

After this lesson, you will be able to:

1. Explain how **Amazon VPC Lattice** solves connectivity between distributed applications and services across multiple VPCs or AWS accounts.
2. Distinguish **service network**, **service**, **listener**, **rule**, **target group**, **VPC association**, and **service-network VPC endpoint**.
3. Describe the path of a request from an application in VPC A to a service in VPC B through VPC Lattice.
4. Design multi-VPC and multi-account connectivity architectures with **AWS Resource Access Manager (AWS RAM)**, IAM, authentication/authorization policies, and Security Groups.
5. Distinguish between **VPC Lattice services** and **resource configurations/resource gateways** and know when each applies.
6. Understand how to use domain names, HTTPS/TLS, metrics, access logs, health checks, and AWS tools for observability and troubleshooting.
7. Evaluate when to choose VPC Lattice over VPC peering, Transit Gateway, PrivateLink, or other connectivity solutions based on technical requirements and cost.

## 1. Problem: Many VPCs, Many Services, Many Development Teams

Suppose an e-commerce platform on AWS is split into separate applications:

- **Orders API** handles orders, running on EC2 or ECS in **VPC Orders**.
- **Payments API** processes payments, running on ECS or EKS in **VPC Payments**.
- **Notifications API** sends notifications, running on AWS Lambda in another operational account.
- Each application may be deployed in its own AWS account to isolate permissions, costs, and release lifecycles.

Orders API needs to call Payments API over HTTPS, yet the two teams do not want to maintain direct access configurations to each other's entire IP ranges. As service counts grow, self-managing numerous VPC connections, routes, and network policies becomes complex.

**Amazon VPC Lattice** is an AWS-managed application networking service. It provides a way to organize, route, secure, and observe communication between **services** deployed across multiple VPCs or AWS accounts without requiring the calling application to maintain direct VPC-peering-style network connectivity to the entire service network.

VPC Lattice is especially well-suited when teams need to manage connectivity at the **service boundary**: which application can call which API, over which port/protocol, with what permissions, and how requests are observed.

### 1.1. Difference in Mental Model

With traditional networking, the question is usually:

> "How does a machine in VPC A reach the IP address of a machine in VPC B?"

With a VPC Lattice service, the question becomes:

> "How is a client in VPC A authorized to call the registered **Payments Service**, and how is that request routed to valid targets?"

VPC Lattice abstracts service identity/access points while providing appropriate routing, authentication, and observability. Even so, customers must still ensure **associations, DNS, policies, Security Groups, target health, and related networking conditions** are configured accurately.

### 1.2. VPC Lattice Is Not a VPC Network Connecting Everything

VPC Lattice does not automatically turn two VPCs into a network where every IP address can route freely to every other. Reachability depends on which services or resource configurations are **published**, which service network participants belong to, and security layers.

For example, allowing Orders API to access Payments Service via VPC Lattice **does not** mean Orders API can SSH into every EC2 instance in VPC Payments or arbitrarily query databases inside that VPC.

## 2. Core Components of VPC Lattice

Distinguish two major concepts:

- **VPC Lattice service:** a logical access point representing an application/endpoint, complete with listeners, routing rules, and target groups.
- **Service network:** a logical boundary grouping multiple services (and resource configurations in applicable scenarios), allowing connected VPCs to consume the components they are authorized for.

### 2.1. Conceptual Diagram

~~~mermaid
flowchart LR
    subgraph A["VPC A — Clients"]
        ORD["Orders API"]
    end
    subgraph C["VPC C — Clients"]
        BATCH["Batch / Backoffice"]
    end
    subgraph SN["VPC Lattice — Service network"]
        S1["Payments Service"]
        S2["Notifications Service"]
    end
    subgraph B["VPC B — Targets"]
        P1["Payments target 1"]
        P2["Payments target 2"]
    end
    L["AWS Lambda function"]
    ORD -->|"VPC association or service-network endpoint"| SN
    BATCH -->|"VPC association or service-network endpoint"| SN
    S1 -->|"Listener / rules / target group"| P1
    S1 -->|"Listener / rules / target group"| P2
    S2 --> L
~~~

This is a **logical diagram**, not a detailed packet map. Client requests must reach the VPC Lattice endpoint and then be forwarded by Lattice to targets; each leg must satisfy networking and authorization requirements.

### 2.2. Component Reference Table

| Component | Role | Design question |
| --- | --- | --- |
| **Service network** | Logical collection of associable services and resource configurations, with shared access/observability boundaries. | Which applications belong to the same connectivity domain? |
| **Service** | Represents an application exposed through Lattice, with a domain name and listeners. | Which API needs to be published to clients? |
| **Listener** | Accepts connections by protocol/port, then evaluates rules. | Use HTTPS/443, HTTP, or TLS passthrough? |
| **Rule** | Selects action/target group based on supported conditions and priority order. | Which backend should receive the request? |
| **Target group** | Set of compute targets executing the service; includes protocol, port, and health check settings where supported. | Does the service run on EC2, IP, ALB, or Lambda? |
| **Service-network service association** | Connects a service to a service network. | Which services appear inside the service network? |
| **Service-network VPC association** | Connects a VPC to a service network so clients in that VPC can use eligible services. | Which VPCs participate as clients? |
| **Service-network VPC endpoint** | Alternative way to connect a VPC to a service network via a service-network type VPC endpoint. | Do we want a dedicated endpoint, chosen subnets, and endpoint SG? |
| **Auth policy** | Policy at the service network and/or service level controlling who can invoke services. | Which principals are permitted to invoke? |
| **AWS RAM** | Shares supported Lattice resources across AWS accounts. | Which accounts own/consume the service network? |

**Key point:** A service that has been created but not yet **associated** with a service network cannot yet be called by clients in that service network under this architecture. Similarly, a client VPC not connected to the service network cannot reach the service merely by knowing the service name.

### 2.3. Service Network: The Connectivity Boundary

A service network can represent a business domain, an environment, or an intentional sharing boundary.

Example:

- **commerce-prod-network** contains production Payments, Orders Backend, and Notifications.
- **commerce-dev-network** contains the corresponding development services.
- **analytics-network** serves data and reporting applications with distinct access requirements.

The service network owner typically decides which VPCs and services are associated, shares the network with required accounts, and defines shared policies at the network scope. The service owner manages listeners, routing, target groups, and service-specific controls.

You do not have to cram every application into one giant service network. Separating by environment and trust boundary makes permissions and change blast radius easier to manage.

### 2.4. Services, Listeners, and Rules

Suppose Payments Service has an HTTPS endpoint:

- Listener accepts **HTTPS/443**.
- Rules evaluate requests by supported path/header/method conditions matching the protocol and config.
- Requests to **/payments/** are forwarded to the Payments target group.
- A default action handles requests that do not match specific rules, per listener configuration.

VPC Lattice supports **HTTP**, **HTTPS**, and **TLS** listeners. HTTPS listeners generally support HTTP-layer request handling, whereas **TLS passthrough** lets target applications terminate TLS themselves and has different limitations compared to HTTP routing. Do not assume all protocols are equivalent in header inspection, auth, or routing capabilities.

### 2.5. Target Groups: Where Requests Are Executed

A target group defines the backend for a service. Common target group types include:

| Target type | Backend identifier | Example |
| --- | --- | --- |
| **INSTANCE** | EC2 instance ID. | API service running directly on EC2. |
| **IP** | IP of a target in a VPC configured for the target group, within service limits. | ECS task or EKS Pod registered via an appropriate integration mechanism. |
| **LAMBDA** | AWS Lambda function. | Serverless Notification API. |
| **ALB** | Internal Application Load Balancer, under supported conditions. | Application already fronted by its own ALB. |

ECS tasks and Kubernetes Pods are typically registered into target groups via **IP**-based integration/registration mechanisms, rather than expecting "ECS" or "Pod" to be separate target-group API types. For EKS, **AWS Gateway API Controller** can be used where supported by architecture and versions. For ALB backends, check listener, port, ALB type, and applicable constraints.

For traffic requiring gRPC/HTTP/2 or TCP/TLS passthrough, verify **compatibility between listener, target protocol version, and target type**. For instance, a TCP target group attached to a TLS listener has different restrictions than a standard HTTPS listener.

## 3. How Does a Request Traverse VPC Lattice?

Consider a call from **Orders API in VPC A** to **Payments Service** backed by **VPC B**.

~~~mermaid
sequenceDiagram
    participant O as Orders API (VPC A)
    participant D as Service DNS
    participant L as VPC Lattice
    participant P as Payments target (VPC B)
    O->>D: Resolve Payments Service domain
    D-->>O: Appropriate VPC Lattice endpoint address
    O->>L: HTTPS request to Payments Service
    Note over L: Evaluate network association, auth, and routing
    L->>P: Forward request to target
    P-->>L: Response from backend
    L-->>O: HTTPS response to client
~~~

Logical steps:

1. **Service owner** creates Payments Service, configuring listeners and target groups.
2. The service is **associated** with the service network. VPC A connects to the service network via a **VPC association or service-network VPC endpoint**.
3. Orders API uses **service DNS** (Lattice-assigned or properly configured custom domain) to resolve the endpoint.
4. The client initiates a connection to Lattice. Security Groups, network paths, endpoints, and applicable policies must permit the flow.
5. If IAM authorization is enabled, the request must satisfy **SigV4** signing and relevant policies.
6. Lattice selects the listener/rule/target group, then routes the request to a serving target per routing logic.
7. The target executes business logic; the response returns through Lattice.

This enables development teams to call services by **service name** rather than tracking EC2/ECS IP lists that change during Auto Scaling. However, VPC Lattice **does not fix application bugs, restrict business-level data access, or guarantee targets are always healthy**.

### 3.1. How Do VPC Association and VPC Endpoint Differ?

| Criterion | VPC association with service network | Service-network VPC endpoint |
| --- | --- | --- |
| How it connects | Creates an association between a VPC and a service network. | Creates a **service network** type VPC endpoint inside the VPC pointing to the network. |
| Network control | Can specify Security Groups on the association as supported by the service. | Choose subnets and Security Groups on the endpoint per configuration. |
| Use case | Accessing services in the service network from clients in the associated VPC. | Connecting through endpoint ENIs placed in specific subnets or aligning with PrivateLink/VPC endpoint models. |
| DNS and deployment | Uses Lattice DNS/association mechanics; verify private DNS by resource type. | Verify endpoint DNS options and access conditions. |

In both models, **clients still need a path to the endpoint and permission to access it**. Details around DNS and resource configurations can differ between the two mechanisms, so inspect actual association properties.

### 3.2. Clients Only Need Network Access to Published Services

If VPC A joins a service network containing Payments, that does not require VPC peering for VPC A to see every subnet in VPC B. Lattice's goal is providing access paths to published, authorized services.

For **TCP database flows**, distinguish two options:

- Use a **VPC Lattice service with a TLS listener/TCP target group** when protocols and system requirements fall within supported scope.
- Use a **VPC Lattice resource configuration/resource gateway** when the goal is exposing access to a resource such as RDS, an IP, or a domain via the resource connectivity model.

Do not assume all HTTP routing/auth features of VPC Lattice services apply to resource configuration flows.

## 4. Two Publishing Layers: VPC Lattice Service vs. Resource Configuration

Amazon VPC Lattice also supports **resource configurations**. This component enables clients to access resources such as RDS, IP-based endpoints, or domain names where supported by the service, via a **resource gateway** and appropriate associations.

### 4.1. Differences in Purpose

| Question | VPC Lattice service | Resource configuration / resource gateway |
| --- | --- | --- |
| What is being published? | An **application service** with listeners, rules, and target groups. | A **resource** or endpoint configured for resource connectivity. |
| Rule-based HTTP routing? | Yes, with supported listeners and protocols. | Does not use the service listener/rule/target-group model in the same way. |
| Service/service-network auth policy? | Applicable to **VPC Lattice services**. | **Service-network auth policies do not apply to resource configurations**; resource configurations have separate controls per documentation. |
| Typical use case | Orders/payments APIs, microservices, Lambda. | Letting clients consume resources in another VPC like a database or IP endpoint. |
| Provider-side config | Service, listener, target group, targets, and associations. | Resource gateway, resource configuration, associations/shares per architecture. |

A **Resource gateway** is the entry point in the VPC hosting the exposed resource. A **Resource configuration** describes the resource permitted to be published, while associations and permissions determine which clients can access it.

In RDS access architectures, **network reachability** alone is not enough for queries to succeed: applications still need DB credentials, TLS, and appropriate database permissions. IAM/Lattice network access does not automatically grant read permissions on database tables.

### 4.2. Do Not Share Security Assumptions

A dangerous mistake is setting an auth policy on a service network and assuming all resource configurations are protected by it. Per AWS documentation, **service-network auth policies do not apply to resource configurations**. Therefore, when publishing a database or other resource, review the controls that actually govern that object: resource sharing/associations, resource policies, Security Groups, database credentials, and related protections.

This lesson focuses on **service connectivity across multiple VPCs**; the resource configuration section prevents applying the wrong model when the real requirement is resource connectivity rather than calling an application API.

## 5. Multi-VPC and Multi-AWS Account Design

Suppose an enterprise separates applications by account:

- **Account A — 111122223333:** VPC Orders, hosting the Orders API client.
- **Account B — 444455556666:** VPC Payments, hosting Payments API targets.
- **Service network:** commerce-prod-network, managed by the infrastructure team and shared with participating parties.

Both account IDs are **illustrative values**. Replace them with appropriate IDs from your actual environment.

### 5.1. Overall Diagram

~~~mermaid
flowchart LR
    subgraph ACCA["Account A — VPC Orders"]
        O1["Orders API / ECS task"]
    end
    subgraph NETWORK["commerce-prod-network"]
        S["Payments Service HTTPS/443"]
    end
    subgraph ACCB["Account B — VPC Payments"]
        TG["Payments target group"]
        P1["Payments EC2/ECS 1"]
        P2["Payments EC2/ECS 2"]
    end
    RAM["AWS RAM: shares appropriate network/service permissions"]
    O1 -->|"VPC association + valid request"| S
    S --> TG
    TG --> P1
    TG --> P2
    RAM -.-> NETWORK
~~~

### 5.2. Deployment Steps by Ownership

**Step 1 — Define network scope.** Identify environments, AWS Regions, account owners, service owners, and consumer VPCs. Name resources clearly by business unit/environment.

**Step 2 — Prepare the Payments backend.** Ensure targets can handle requests, pass health checks, and use the right protocols/ports and Security Groups.

**Step 3 — Create target group, service, and listener.** The service owner creates a target group supporting the workload type, creates Payments Service, and configures HTTPS/443 and routing.

**Step 4 — Create or select the service network.** The network owner establishes the logical boundary for production and defines shared access policies.

**Step 5 — Share resources cross-account when needed.** Use **AWS RAM** to share the service network and/or supported Lattice resources with other accounts; check IAM permissions of managing principals and share acceptance status if applicable.

**Step 6 — Associate services and VPCs.** Payments Service is associated with the service network; VPC Orders is associated or connected via a service-network VPC endpoint. Associations must be active before testing.

**Step 7 — Configure security/auth.** Verify IAM permissions for administrative actions, service network/service auth policies, Security Groups on client/association/target sides, TLS, and domain names.

**Step 8 — Test paths and observability.** Call Payments from Orders using an authorized principal, verifying responses, health, logs, metrics, and behavior when access is denied or targets fail.

Actual execution order may vary by IaC tooling and ownership, but ultimately **service network associations, service associations, caller sources, permissions, listeners, targets, and DNS must all be in place**.

### 5.3. Why Does Cross-Account Require an Extra Sharing Step?

A VPC in account A does not automatically see or have permission to associate with a service network owned by account B. AWS RAM shares AWS-supported resources, but **share acceptance permissions** and **data-plane access permissions** are two separate concerns:

- **AWS RAM + administrative IAM:** which principals can create associations, manage, or use Lattice resources.
- **VPC Lattice network association:** which client VPCs are connected to the network.
- **Auth policy + identity permissions (when `AWS_IAM` is enabled):** which workloads can send requests to a service.
- **Application authorization:** whether end users are permitted to perform business actions like issuing refunds or viewing data.

If you share the service network yet forget to create the VPC association, clients still have no access path. If the network path works yet the service requires SigV4 and the client does not sign requests, requests will still be rejected.

### 5.4. Overlapping CIDRs and Geographic Scope

VPC Lattice reduces the need to establish direct IP routing across every VPC just to call published services; this benefits organizations with hard-to-coordinate CIDR ranges. However, **do not automatically assume every overlapping IP pattern is supported across all target types, resource connectivity modes, protocols, endpoints, and intermediate networks**.

In production, verify constraints of the chosen connectivity mode, Region, VPC, account, IPv4/IPv6 addressing, and current quotas. Examples in this lesson use same-Region VPCs to clarify core principles.

## 6. Layered Security

VPC Lattice provides complementary control layers. No single layer should be treated as a complete substitute for the others.

| Layer | Question to answer | Typical controls |
| --- | --- | --- |
| **Membership** | Does the VPC have a path into the service network? Is the service published into the network? | Service/VPC associations, service-network endpoints, AWS RAM. |
| **Network** | Can clients and Lattice reach service targets over the right protocol/port? | Security Groups on clients, associations/endpoints, and targets; relevant routes and NACLs. |
| **VPC Lattice auth** | Which principals are permitted to invoke the service? | Auth type **`AWS_IAM`**, service network/service auth policies, SigV4, identity policies. |
| **Transport** | Does data require encryption and endpoint authentication? | HTTPS/TLS, certificates, custom domains, backend protocols. |
| **Application** | Is the caller allowed to view/modify this business data? | Access tokens, sessions, RBAC/ABAC, validation, and application auditing. |
| **Observability** | Can errors, denied requests, and configuration changes be detected? | Metrics, access logs, CloudTrail, backend tracing/logs. |

### 6.1. Auth Types `NONE` and `AWS_IAM`

VPC Lattice services/service networks support choosing an appropriate auth mechanism, commonly:

- **`NONE`:** disables VPC Lattice's IAM authentication/authorization layer at that component. Access is still governed by membership, networking, auth at other layers if present, and the application.
- **`AWS_IAM`:** requires evaluating **VPC Lattice auth policies**. Requests are authenticated via AWS Signature Version 4 (**SigV4**) when the policy requires authenticated principals.

Enabling `AWS_IAM` **without a matching Allow** in relevant policies causes requests to be denied by default. For signed requests, the caller must also possess matching **IAM identity-based permissions**; both service network and service auth policies (if enabled) must permit the call. **Explicit Deny** takes precedence per standard policy evaluation rules.

### 6.2. Distinguishing Two Families of IAM Actions

Implementers commonly encounter two action groups serving different purposes:

1. **`vpc-lattice:*`** — **control plane** APIs to create, read, or modify service networks, services, associations, target groups, or policies (depending on the action).
2. **`vpc-lattice-svcs:Invoke`** — **data plane** action used in auth policies/identity policies to permit calling a service through VPC Lattice. Related actions are also listed in the service's IAM reference.

For example, granting **`vpc-lattice:GetService`** so an operator can view a service's configuration **does not grant `vpc-lattice-svcs:Invoke`** for an application to call that service. Conversely, workloads that only need to invoke an API should never be granted permissions to administer the entire service network.

### 6.3. Service-Level Auth Policy Example

Suppose Payments Service belongs to account B, and only role **OrdersClientRole** in account A may invoke it:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersClientInvokePayments",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/OrdersClientRole"
      },
      "Action": "vpc-lattice-svcs:Invoke",
      "Resource": "arn:aws:vpc-lattice:ap-southeast-1:444455556666:service/svc-0123456789abcdef0/*"
    }
  ]
}
~~~

This illustrates an **auth policy attached to Payments Service** with auth type **`AWS_IAM`**. It is not a complete standalone config: verify actual ARNs, resource structure per IAM Service Authorization Reference, service-network policies if enabled, and other access conditions.

The caller role also needs an **identity-based policy** allowing it to invoke the service:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokePaymentsService",
      "Effect": "Allow",
      "Action": "vpc-lattice-svcs:Invoke",
      "Resource": "arn:aws:vpc-lattice:ap-southeast-1:444455556666:service/svc-0123456789abcdef0/*"
    }
  ]
}
~~~

**Do not include `Principal` in a role's identity-based policy.** `Principal` appears in the auth policy because it is a resource-based policy.

A **service-network-level** auth policy can grant broad organization/group-level access, while service owners use service-level auth policies to restrict sensitive APIs more tightly. When both use auth type `AWS_IAM`, permissions must align across the relevant layers.

### 6.4. Signing Requests with SigV4

When IAM auth requires an authenticated caller, standard HTTP/HTTPS requests from applications must be signed using **AWS Signature Version 4** per VPC Lattice requirements. Use AWS SDKs or a service-compatible SigV4 signer to avoid manually mishandling keys or canonical strings.

Applications should obtain **temporary credentials from an IAM role** attached to EC2/ECS/EKS/Lambda or an appropriate identity federation mechanism. Avoid hardcoding access keys and secret keys in source code, uncontrolled environment variables, or pipeline logs.

**Note:** VPC Lattice auth policies do not replace end-user authentication/authorization. If Orders API calls Payments on behalf of a customer, Payments must still validate business permissions, prevent duplicate operations, and record business audits.

### 6.5. Security Groups in VPC Lattice

Security Groups control network traffic, while auth policies control invocation permissions at the IAM application layer.

With a **VPC association**, you can attach a Security Group to restrict which clients inside the VPC may connect to the service network. With a **service-network VPC endpoint**, the endpoint's Security Group controls traffic through the endpoint. On the backend side, the **target's Security Group** must allow traffic arriving from VPC Lattice infrastructure using the AWS-supported source model.

Specifically, **do not assume targets can specify source = the client's Security Group in another VPC**. Traffic traversing Lattice originates from Lattice's data plane; for certain targets such as EC2, AWS provides **AWS-managed prefix lists** for VPC Lattice, for example:

- **`com.amazonaws.ap-southeast-1.vpc-lattice`**
- **`com.amazonaws.ap-southeast-1.ipv6.vpc-lattice`** when IPv6 applies.

When needed, use the managed prefix list as the **source in the target's inbound SG** for backend and health check ports, or as the **destination** in the client's outbound SG if egress is restricted and connectivity uses a VPC association. Select the exact prefix list ID/Region and check SG guidance for the endpoint/target type in use.

Illustrative logical rules:

| Location | Direction | Illustrative rule |
| --- | --- | --- |
| Client SG | Outbound | TCP/443 to the appropriate Lattice path (prefix list or endpoint depending on connection mode). |
| VPC association / endpoint SG | Inbound | Allow only required client sources and listener ports per association mode. |
| Target SG | Inbound | Allow target/health check ports from the AWS-documented Lattice source. |
| Payments application | Authorization | Only the Orders service is authorized to invoke business operations. |

If a client receives **403** from Lattice, inspect **auth type, signatures, and policies** rather than merely opening more inbound SG rules. If connections **time out**, inspect DNS, associations, endpoints, SGs, network paths, and backend health.

## 7. DNS, HTTP/HTTPS, and TLS

### 7.1. VPC Lattice-Assigned Domain Names

When creating a VPC Lattice service, AWS provides a dedicated **DNS name** for the service. A service domain name may follow an illustrative pattern like:

~~~text
payments-svc-0123456789abcdef0.<generated-id>.vpc-lattice-svcs.ap-southeast-1.on.aws
~~~

Always retrieve the exact string from the service's DNS attribute returned by AWS; never guess exact DNS strings from sample names/IDs.

Clients inside a VPC connected to the service network can use this DNS name to call the service if networking and permissions are valid.

### 7.2. Custom Domains

Enterprises may prefer applications to call **`payments.internal.example.com`**. VPC Lattice lets you configure a **custom domain name** on a service under supported conditions, paired with DNS records pointing to the service's domain name.

For **HTTPS on a custom domain**, you must supply a matching certificate in **AWS Certificate Manager (ACM)**. VPC Lattice does not automatically provide valid default certificates for arbitrary custom domains; without a matching certificate, HTTPS over the custom domain may fail.

Example:

~~~text
Client Orders API
    -> https://payments.internal.example.com
    -> DNS points to Lattice service
    -> HTTPS/443 listener
    -> Payments target
~~~

You must configure DNS zones/records so clients resolve the name, supply the right certificate, and ensure proper network association. Adding a DNS record alone never grants access permissions.

### 7.3. HTTPS Listeners and TLS Passthrough

| Ingress mode | What happens in Lattice | Scenario |
| --- | --- | --- |
| **HTTP listener** | Accepts HTTP and routes per supported capabilities. | Internal/testing or cases with appropriate protections where encryption requirements are assessed. |
| **HTTPS listener** | Lattice handles client connection TLS using an appropriately managed/supplied certificate and can perform HTTP routing. | Service-to-service HTTPS APIs. |
| **TLS listener (passthrough)** | Lattice forwards the TLS stream directly to targets for backend TLS termination; HTTP inspection/routing capabilities are limited. | Applications needing end-to-end TLS termination themselves or protocols suited to TLS passthrough. |

**Inbound TLS and Lattice-to-target TLS are two separate segments to evaluate.** Encryption up to Lattice does not automatically ensure targets receive HTTPS connections; target groups have their own protocol/configuration. For sensitive data or compliance requirements, verify the entire path.

### 7.4. DNS Is Not an Authentication Mechanism

Knowing the Payments Service hostname **does not automatically grant invocation permissions**. Conversely, even with valid IAM policies, if DNS fails to resolve or the client is not connected to the service network, the application still cannot call the service.

Evaluating DNS, networking, IAM, and application layers independently avoids fixing the wrong root cause.

## 8. Routing, Target Health, and Resilience

### 8.1. Listener Rules

Listener rules determine which target group receives a request based on conditions supported for the active protocol. Listeners can have a default action and prioritized rules.

Example on Payments Service:

| Illustrative condition | Target group | Meaning |
| --- | --- | --- |
| Path matches **`/payments/v1/*`** | **`payments-v1-tg`** | API v1. |
| Path matches **`/payments/v2/*`** | **`payments-v2-tg`** | API v2. |
| Default | **`fallback-tg`** or appropriate supported response. | Handles remaining requests. |

Check path-matching syntax and listener action/rule limits before applying IaC. Some listener types (especially TLS passthrough) have stricter limitations than HTTPS listeners.

### 8.2. Health Checks and Target Availability

VPC Lattice can monitor target health using supported protocols, ports, and health checks. When designing:

1. Expose a health check endpoint reflecting actual serving readiness (not merely that the process is running).
2. Ensure SGs and network layers permit required health check traffic.
3. Register multiple targets distributed across AZs if SLA/RTO requires it.
4. Monitor target status, error rates, and latency, and test target-failure scenarios.

**Important detail:** In certain target group models, if **all targets become unhealthy**, VPC Lattice may **fail open** and continue routing requests to unhealthy targets as documented. Never assume Lattice always halts all backend traffic when health checks fail. Verify behavior for your target/protocol type and design client timeouts, retries, and circuit breakers.

### 8.3. Regions and AZs

AWS supports running applications across multi-AZ infrastructure. In VPC Lattice, **AZ affinity** and selecting paths to appropriate endpoints/targets improve access efficiency, yet **application availability still depends on targets and architecture**.

Never assume simply creating a service network provides HA. If Payments runs on a single EC2 instance in one AZ, Lattice cannot substitute for deploying redundant targets or proper recovery mechanisms.

### 8.4. Timeouts, Retries, and Idempotency

Stable network connectivity does not guarantee every individual request succeeds. Distributed applications must still handle:

- **Timeouts** on clients and server layers.
- **Retries with backoff/jitter** and bounded attempt counts.
- **Idempotency keys** for payments or non-idempotent business operations.
- **Circuit breakers** or load shedding when downstreams degrade.
- **Observability** to distinguish failures in Lattice, backends, and business logic.

For example, if Orders API times out right after calling Payments, Orders cannot tell whether Payments processed the request. Retrying without idempotency risks creating duplicate transactions.

## 9. Monitoring and Troubleshooting

### 9.1. Signals to Observe

| Layer | Signals | Observability tools/sources |
| --- | --- | --- |
| Client | DNS lookup, TLS handshake, timeouts, HTTP status, retries. | Application logs/tracing. |
| VPC Lattice | Request count, errors, latency, and service/target status where applicable. | Amazon CloudWatch metrics and VPC Lattice console. |
| Requests via Lattice | Client VPC, service, path, response code, duration, bytes per supported fields. | **VPC Lattice access logs** (when enabled). |
| Backend infrastructure | CPU/memory, container restarts, RDS status, app exceptions. | CloudWatch, application logs, service-specific metrics. |
| Configuration changes | Who created/deleted/edited services, associations, auth policies. | AWS CloudTrail and change governance workflows. |

**VPC Lattice access logs are opt-in—never assume they are enabled by default.** Depending on resource type and configuration, logs can be delivered to CloudWatch Logs, Amazon S3, or Amazon Data Firehose. Collecting/storing/analyzing logs incurs costs.

Note that VPC Lattice **service access logs** and **resource access logs** may have different formats/fields; do not assume an HTTP service log parser can parse resource TCP logs.

### 9.2. Triage by Symptom

| Symptom | Possibilities to check | Next step |
| --- | --- | --- |
| DNS fails to resolve | Wrong Lattice-assigned DNS or custom domain, VPC resolver, missing association/endpoint. | Check service DNS attributes, records, DNS resolver, and VPC connection state. |
| Connection times out | Client/association/endpoint/target SGs, network paths, listener/port, unresponsive targets. | Check both ends, health checks, NACLs/routes, and endpoints. |
| HTTP **403** | Missing/invalid SigV4, `AWS_IAM` auth type, service network/service policy, or identity deny. | Inspect auth policies, actual runtime role, signature, and `Invoke` action. |
| HTTP **404** | Wrong hostname/path, service missing/not associated with network, unmatched rule, or backend 404. | Determine from logs whether 404 came from Lattice or the backend. |
| HTTP **5xx** | Backend error, unhealthy targets, target connection failure, or service network fault. | Inspect metrics, access logs, target status, and app logs. |
| Only account A fails | RAM share, VPC association, auth principal/role, SG, or DNS specific to account A. | Compare associations/permissions of a working account against account A. |
| Service runs yet costs spike | Long-lived provisioned services, rising traffic/requests, data processing, or logging volume. | Inspect service inventory, CloudWatch, billing/Cost Explorer, and Regional pricing. |

### 9.3. Diagnostic Decision Tree

~~~mermaid
flowchart TD
    A["Client cannot call VPC Lattice service"] --> B{"Is service associated with network?"}
    B -->|"No"| B1["Create/fix appropriate service association"]
    B -->|"Yes"| C{"Is client VPC connected to network?"}
    C -->|"No"| C1["Check VPC association or service-network endpoint"]
    C -->|"Yes"| D{"Do DNS and HTTPS/TLS work?"}
    D -->|"No"| D1["Check hostname, records, certificate, listener, SG, and network path"]
    D -->|"Yes"| E{"Is request returning 403?"}
    E -->|"Yes"| E1["Check AWS_IAM, SigV4, identity policy, and auth policy"]
    E -->|"No"| F{"Are targets healthy and app responding?"}
    F -->|"No"| F1["Check target group, health check, backend SG, app logs"]
    F -->|"Yes"| G["Inspect response/status, logs, and business logic"]
~~~

This is a suggested evaluation order, not a rigid rule. Multiple faults can coexist; always record **source VPC, target service, hostname, Region, role, request ID, and error timestamp** for investigation.

## 10. Hands-On: Reading Configurations with AWS CLI

Examples use AWS CLI v2 and are **read-only**, creating or modifying no resources. Replace illustrative IDs with real values from an environment you are authorized to access. Commands require matching IAM permissions and must run in the right AWS account/Region.

### 10.1. Verify Account and Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

If resources were created in a different Region than your CLI profile's default, queries may return empty lists even though the service exists in the target Region.

### 10.2. List Service Networks and Services

~~~bash
aws vpc-lattice list-service-networks \
  --region ap-southeast-1

aws vpc-lattice list-services \
  --region ap-southeast-1
~~~

Identify service network IDs (`sn-...`) and service IDs (`svc-...`), distinct from VPC IDs (`vpc-...`). For resources shared via RAM, verify visibility permissions and active account.

### 10.3. View Which Services Are in a Network

~~~bash
aws vpc-lattice list-service-network-service-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1
~~~

If Payments Service is not associated with the network Orders uses, requests from Orders cannot reach that service as designed.

### 10.4. View VPCs Connected to a Network

~~~bash
aws vpc-lattice list-service-network-vpc-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-service-network-vpc-endpoint-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1
~~~

The two lists correspond to **VPC associations** and **service-network VPC endpoints**; if your environment uses only one mode, the other list may be empty. Check association status along with VPC ID, SGs, and account IDs.

### 10.5. View Listeners, Target Groups, and Targets

~~~bash
aws vpc-lattice get-service \
  --service-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-listeners \
  --service-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-target-groups \
  --region ap-southeast-1

aws vpc-lattice list-targets \
  --target-group-identifier tg-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Inspect **service DNS**, listener protocol/port, target group type/protocol, target counts, and health status. **`list-target-groups`** may require pagination handling and permissions in the target group's owning account, especially for shared resources.

### 10.6. View Auth Policies and Access Log Subscriptions

~~~bash
# Applicable to a service network or service with IAM auth enabled.
aws vpc-lattice get-auth-policy \
  --resource-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice get-auth-policy \
  --resource-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1

# Check access log delivery configuration for the service.
aws vpc-lattice list-access-log-subscriptions \
  --resource-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Having no auth policy configured or auth type **`NONE`** does not mean an application is automatically secure. Conversely, with **`AWS_IAM`**, missing an Allow in a required policy can trigger 403 errors.

### 10.7. Inspect the VPC Lattice Managed Prefix List

~~~bash
aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.ap-southeast-1.vpc-lattice \
  --region ap-southeast-1
~~~

If client SGs restrict outbound traffic or target SGs need to allow traffic from Lattice, verify the **managed prefix list ID** for the active Region against rules in **`describe-security-groups`** or **`describe-security-group-rules`**. Never copy raw IP ranges found online into permanent SG rules when AWS provides a managed prefix list.

### 10.8. Test Requests from the Right Environment

To verify connectivity, call the Payments hostname from **the actual container/EC2/Lambda** inside the client VPC per policy. For example, against a service without `AWS_IAM` enabled across relevant layers, an HTTPS probe might look like:

~~~bash
curl --verbose --max-time 10 \
  https://payments.internal.example.com/health
~~~

**Only run this sample command if the domain exists and you are authorized to test.** When a service requires `AWS_IAM`, requests must be **SigV4-signed**; plain `curl` does not sign requests and may receive **403**. Never "fix" it by disabling IAM auth when the design requires authentication. Use a client/SDK that supports request signing and keeps credentials secure.

Thorough testing should also include **intentional negative tests**: unauthorized principals, unassociated VPCs, and invalid endpoints must be rejected as designed.

## 11. Comparing VPC Lattice with Other AWS Connectivity Options

Choose tools based on the **problem**, not the assumption that one service always beats every alternative.

| Criterion | **VPC Lattice service** | **VPC peering** | **Transit Gateway** | **AWS PrivateLink** |
| --- | --- | --- | --- | --- |
| Primary focus | Connecting, routing, securing, and observing **services/applications**. | Routed IP connectivity between **two VPCs**. | Connecting and managing **many VPCs/networks** in a hub model. | Publishing and consuming **specific services/resources** via endpoints per supported features. |
| Abstraction level | Services, listeners, rules, target groups, network associations. | CIDRs, route tables, SGs/NACLs. | Attachments, route tables, CIDRs, and network policies. | Endpoint services, interface endpoints, endpoint policies/SGs where applicable. |
| Broad inter-VPC reachability | Only services/resources published under the Lattice model. | Network connectivity per routes and permissions. | Network connectivity per routes and attachments. | Access points to published services/resources. |
| Application-layer controls | HTTP/HTTPS routing and IAM auth policies where supported. | Not built into VPC peering layer. | Not built into Transit Gateway layer. | Depends on endpoint type and service provider; no Lattice-style HTTP routing by default. |
| Typical use case | Multi-team/multi-account microservices, east-west APIs. | Few VPCs, simple IP connectivity. | Many VPCs/on-prem, general network routing. | Private access to AWS services, SaaS, or specific endpoints. |
| Costs to evaluate | Service hours, data processed, requests/connections, and logs per pricing. | Data transfer and related charges. | Attachments, data processing, and related charges. | Endpoint hours, data processing, and related charges. |

VPC Lattice can complement other solutions. For example, an enterprise can still use Transit Gateway for on-premises connectivity while using Lattice for well-scoped internal service-to-service communication.

**Do not pick Lattice merely to arbitrarily connect every private IP between two VPCs** when general network routing is what you need. Conversely, maintaining a complex peering/Transit Gateway mesh to govern hundreds of independent APIs makes service-level security hard to manage without additional layers.

### 11.1. When Does VPC Lattice Have a Clear Advantage?

- Many applications distributed across **VPCs/accounts** need to call APIs by service identity.
- You want to separate the **service network** administration team from backend service owners.
- You want managed routing to EC2/ECS/EKS/Lambda targets.
- You need IAM-principal **auth policies** for API calls alongside metrics and access logs.
- You want to avoid having every dev team coordinate VPC-to-VPC routing just to call internal APIs.

### 11.2. When to Consider Other Tools?

- General IP routing between two networks or arbitrary ports/protocols needed → evaluate **peering/Transit Gateway**.
- Consuming a single service via a private endpoint in a publisher/consumer model → evaluate **PrivateLink**.
- Hybrid on-premises connectivity to AWS over VPN/Direct Connect → design the appropriate hybrid networking components.
- Public APIs for Internet users with edge auth/throttling and API product management → evaluate **Amazon API Gateway**, ALB, CloudFront, and WAF as appropriate.

## 12. Costs and Operations

VPC Lattice carries not only backend EC2/ECS/Lambda costs, but also its own service and data-plane charges.

Service cost categories to evaluate against current Regional pricing:

1. **Service provisioning:** hourly charges per provisioned service.
2. **Data processing:** volume of request/response data processed by Lattice.
3. **HTTP requests or TCP connections:** billed depending on listener/traffic type.
4. **Access log delivery/storage/analysis:** depends on log destinations like CloudWatch Logs, S3, or Firehose.
5. **Supporting backend and network infrastructure:** EC2, ECS, Lambda, NAT, endpoints, databases, and other architectural data flows.

If you have only a few low-traffic services left provisioned all month, hourly service fees still matter. At high traffic volumes, data processing and request/connection fees can dominate.

Never hardcode a fixed USD rate across all environments: pricing, Regions, features, and billing rules can change. When budgeting, consult the **official Pricing page** and AWS Pricing Calculator where appropriate; verify pricing separately for **resource configurations/resource endpoints** as billing mechanics can differ from VPC Lattice services.

### 12.1. Lifecycle Operations

- Associate only necessary services/VPCs with the network.
- Review IAM/RAM shares whenever personnel or applications change.
- Manage listeners/rules/target groups and policies via IaC wherever possible.
- Tag by team, environment, cost center, and service owner.
- Audit stale associations, unused services, unhealthy targets, log retention, and quotas.
- Monitor request counts, error rates, and latency per service.
- Periodically rehearse target/AZ loss or dependency outages.

Centralized service network governance establishes shared connectivity standards, without absolving development teams of responsibility for application bugs and business data integrity.

## 13. Applied Scenarios

### Scenario A — Orders Calling Payments in Another AWS Account

**Requirement:** Orders in account A needs to call Payments in account B, allowing only authorized runtime principals.

**Design:**

1. Payments Service has an HTTPS/443 listener and a target group backed by healthy instances/tasks.
2. Network owner shares the service network and sets up service/VPC associations with proper permissions.
3. VPC Orders connects to the service network; clients have proper DNS and egress.
4. The service uses auth type `AWS_IAM` with a policy allowing only **OrdersClientRole**.
5. OrdersClientRole has an identity-based Allow Invoke; the app signs requests with SigV4.
6. Payments enforces business authorization, idempotency, and audit logging.

**Verification:** OrdersClientRole succeeds, other roles are denied by policy, and unassociated VPCs cannot reach the service. Confirm access logs, target health, and that transactions are not duplicated on retries.

### Scenario B — Adding Notifications Lambda

**Requirement:** After payment, Orders must send notifications via a Lambda function managed in another account.

**Design:** Publish Notification Service via VPC Lattice with a Lambda target using supported integration, with an invoke policy restricting callers. Ensure the Lambda execution role only calls services or reads data strictly needed. Do not confuse **permission to invoke Notification Service via Lattice** with direct **`lambda:InvokeFunction`** permissions for every client.

**Verification:** Clients authorized only for Payments do not automatically gain permission to invoke Notifications when auth policies are properly separated.

### Scenario C — Applications in Multiple VPCs Accessing RDS

**Requirement:** Several systems need to connect to a centrally managed database.

**Analysis:** This is a **resource connectivity** problem using SQL/TCP protocols, unlike HTTPS APIs with path routing. Consider resource configurations/resource gateways or another networking solution within supported limits. Evaluate data isolation, credentials, Security Groups, TLS, connection pooling, load impact, and database auditing.

**Verification:** Both network connectivity and database authentication are valid; do not assume service-network auth policies protect resource configurations.

### Scenario D — 403 After Enabling `AWS_IAM`

**Symptom:** Previously working HTTPS requests now return 403.

**Common causes:** Client is not signing with SigV4, using the wrong IAM role, identity policy lacks Invoke, or service/service-network auth policy lacks an Allow.

**Remediation:** Check auth type at every layer, verify the runtime's effective identity, and check the Resource ARN for the Invoke action, policies, and logs. Never disable `AWS_IAM` just to silence the error when principal-level control is required.

### Scenario E — Connectivity Works, Yet Errors Spike During a Single-AZ Outage

**Symptom:** Targets in one AZ become unavailable, and many requests time out.

**Analysis:** Inspect target distribution and health, potential fail-open behavior if all targets go unhealthy, client timeouts/retries, healthy target counts in surviving AZs, and whether the app depends on a single-AZ database or service.

**Remediation:** Add HA aligned with RTO/RPO, tune health checks, run load/failover tests, and bound retries to prevent retry storms.

## 14. Common Mistakes

| Misconception | Accurate understanding |
| --- | --- |
| "Attaching VPCs to a service network lets them see all private IPs of each other." | Lattice provides access to **published services/resources**, not general routing across all addresses. |
| "Once a service is created, clients in other accounts can call it immediately." | Proper service-network associations, client VPC/endpoint connections, permissions/shares, and service settings are required. |
| "Knowing the DNS name grants permission to call the service." | DNS only locates the endpoint; IAM auth, networking, and the application can still reject calls. |
| "An AWS RAM share automatically grants Invoke permissions." | Sharing manages resource visibility/association rights; data-plane Invoke has its own policy and connectivity layers. |
| "Adding the client's SG as source in the target SG always works." | Traffic traverses Lattice; many setups require the AWS-managed prefix list or other documented sources depending on target/endpoint type. |
| "`vpc-lattice:GetService` policy is enough for an app to call the API." | Control-plane permissions differ from **`vpc-lattice-svcs:Invoke`**. |
| "With `AWS_IAM` enabled on a service, clients can send plain `curl` requests." | Requests may need SigV4 signing and explicit Allows across applicable policies. |
| "A service-network auth policy protects all resource configurations." | Service-network auth policies **do not apply** to resource configurations. |
| "HTTPS on a custom domain doesn't need certificate setup." | A matching ACM certificate is required for HTTPS to work on a custom domain. |
| "A service network guarantees high availability by itself." | You still need healthy targets, multiple AZs, failover, and application recovery design. |
| "If health checks fail, Lattice always stops sending traffic to all failed targets." | Some target group modes **fail open** when all targets are unhealthy. |
| "Lattice is free within the same Region." | Account for service hours, data processing, requests/connections, and related charges. |
| "Lattice replaces every Transit Gateway or peering use case." | Lattice optimizes service/resource connectivity; general IP routing uses other models. |

## 15. Practice Exercises and Self-Check Questions

### Design Exercise 1 — Selecting Components

A system has an **Inventory API** running on ECS in VPC B and two clients in VPC A and VPC C. Both clients need to call **`GET /inventory/`** over HTTPS.

**Task:** Outline the minimal components and protection layers.

**Suggested answer:** An Inventory Service with an HTTPS listener, a target group suitable for ECS tasks, service association to the service network, connecting both client VPCs via associations/endpoints, DNS, SGs, IAM auth if required, logging, and health checks. Verify policies between consumers and the service, and enforce business permissions in the application.

### Design Exercise 2 — Isolating a Fault

Inventory Service works when called from VPC A but fails from VPC C. What should be checked first?

**Suggested answer:** Check whether VPC C is connected to the right service network, association/endpoint status, and SGs/routes/DNS. If traffic reaches Lattice yet returns 403, inspect the role and auth policies for requests from VPC C. Avoid modifying the backend when VPC A still succeeds unless there is evidence of a backend fault.

### Design Exercise 3 — Pipeline vs. Runtime Permissions

A deployment pipeline for Payments needs to create target groups and edit listeners, while Orders runtime should only call the Payments API.

**Suggested answer:** The pipeline role gets scoped **control plane** permissions under change control. The Orders runtime role receives only the required **`vpc-lattice-svcs:Invoke`** permission and sends SigV4-signed requests when IAM auth is enabled. Never grant service-network admin rights to the Orders runtime.

### Quick Questions

**Question 1.** How do a service network and a service differ?  
**Answer:** A service network is a logical connectivity/observability boundary holding services and resource configurations; a service represents a single application with listeners, rules, and target groups.

**Question 2.** Through which connection modes can a VPC access services in a service network?  
**Answer:** Via a **VPC association** or a **service-network type VPC endpoint**, depending on support and configuration.

**Question 3.** Is VPC peering required between client VPC and target VPC when calling a service via Lattice?  
**Answer:** No, direct VPC peering is not needed solely to call a service published via VPC Lattice in supported architectures.

**Question 4.** What does auth type `AWS_IAM` typically require?  
**Answer:** Callers need valid identity/temporary credentials and SigV4 signing; identity permissions and enabled auth policies must allow the request with no applicable explicit Deny.

**Question 5.** Why might allowing the client VPC's CIDR in the target SG be insufficient?  
**Answer:** Traffic passes through VPC Lattice and originates from Lattice's data plane; rules must reference the AWS-documented source, such as the managed prefix list where applicable.

**Question 6.** Do Lattice service auth policies automatically apply to resource configurations?  
**Answer:** No. Specifically, service-network auth policies do not apply to resource configurations; inspect the separate permission model.

**Question 7.** What key component is needed when using a custom domain with HTTPS?  
**Answer:** Proper DNS mapping and an **ACM** certificate matching the domain name.

**Question 8.** When an ECS backend auto-scales, do clients need to track individual task IPs?  
**Answer:** Normally no; clients call the service name while VPC Lattice target groups/ECS integration handle target registration/routing via supported mechanisms.

**Question 9.** Why can't access logs and metrics replace application logs?  
**Answer:** Lattice describes requests/responses at the service-networking layer; application logs are still required to understand business logic errors, data issues, and application-level authorization decisions.

**Question 10.** What are two core VPC Lattice costs that are easy to overlook?  
**Answer:** Provisioned service hours and data processing; plus request/connection and logging fees depending on traffic and configuration.

## 16. Summary

**Amazon VPC Lattice** connects distributed application services across multiple VPCs and AWS accounts using the **service network → service → listener/rule → target group → backend** model. Clients join the service network via a **VPC association** or **service-network VPC endpoint**, then call services using DNS and appropriate permissions.

When deploying to production, verify every dimension:

- **Connectivity:** service associations, client VPC associations/endpoints, DNS, and Security Groups.
- **Authorization:** IAM/RAM admin permissions, IAM identity permissions, and VPC Lattice auth policies/SigV4 when enabled.
- **Application:** listeners, routing, target health, business authorization, timeouts/retries, and data integrity.
- **Operations:** metrics, access logs, CloudTrail, multi-AZ coverage, failover testing, and cost forecasting.

Lattice delivers strong value when enterprises want to govern **service-to-service** communication along intentional boundaries. However, it does not replace all inter-VPC IP connectivity, does not grant arbitrary resource access automatically, and does not remove customer responsibility for protecting and monitoring applications.

### Official AWS Reference Documentation

- [What is Amazon VPC Lattice?](https://docs.aws.amazon.com/vpc-lattice/latest/ug/what-is-vpc-lattice.html) — overview and components.
- [How VPC Lattice works](https://docs.aws.amazon.com/vpc-lattice/latest/ug/how-it-works.html) — service networks, associations, and connectivity paths.
- [Service networks in VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/service-networks.html) — organizing service networks.
- [Target groups](https://docs.aws.amazon.com/vpc-lattice/latest/ug/target-groups.html) — target types and routing.
- [Listeners for your VPC Lattice service](https://docs.aws.amazon.com/vpc-lattice/latest/ug/listeners.html) — HTTP, HTTPS, and TLS.
- [Manage access to VPC Lattice services](https://docs.aws.amazon.com/vpc-lattice/latest/ug/access-management-overview.html) — access control layers.
- [VPC Lattice auth policies](https://docs.aws.amazon.com/vpc-lattice/latest/ug/auth-policies.html) — service/network-level IAM policies.
- [Security groups for VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/security-groups.html) — traffic sources and managed prefix lists.
- [Access logs for VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/monitoring-access-logs.html) — request observability and analysis.
- [VPC Lattice pricing](https://aws.amazon.com/vpc/lattice/pricing/) — billing by service/data/traffic.
