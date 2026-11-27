# awsvpc Networking, Security Groups, and ALB Connectivity

> **Chapter:** Containers with ECS  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless; practice designing and deploying applications that are secure, observable, resilient, and cost-controlled.

In Amazon Elastic Container Service (**Amazon ECS**), a containerized application cannot serve users merely because its image starts successfully. It also needs network addresses, listening ports, security rules, routing, and a way to direct requests to healthy **tasks**. With the **`awsvpc`** network mode, ECS gives each task a VPC network interface; with an **Application Load Balancer (ALB)**, the system distributes HTTP(S) traffic to tasks through a **target group**.

This lesson focuses on three interconnected questions:

1. **`awsvpc`:** how are IPs, ENIs, and ports assigned to tasks?
2. **Security Groups:** who is allowed to send traffic to tasks, and which systems may tasks call?
3. **ALB:** how do listeners, target groups, and health checks find the right task IP/port, even as tasks get replaced?

Resource names, VPC CIDRs, IDs, and images in this lesson are illustrative. Before production deployment, verify features and quotas for your actual Region, launch type, platform version, and security requirements.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the `awsvpc` **task ENI** model and how it differs from `bridge` and `host` in ECS-supported scenarios.
2. Trace the path **client → ALB listener → target group → task IP:containerPort**, including health checks.
3. Choose **target type `ip`** for ECS tasks using `awsvpc` and distinguish it from `instance`.
4. Configure **least-privilege** Security Groups for the ALB, ECS tasks, databases, and interface VPC endpoints.
5. Understand how private subnets, NAT Gateways, VPC endpoints, DNS, and IAM affect image pulls, log delivery, and AWS API access.
6. Read a sample Task Definition/ECS Service configuration and troubleshoot `Target.Timeout`, `Target.ResponseCodeMismatch`, `CannotPullContainerError`, and `ResourceInitializationError`.
7. Evaluate operational concerns such as multi-AZ resilience, deployments, graceful shutdown, capacity, monitoring, and cost.

## 2. Mental Model: ECS Cluster, Service, Task, and ENI

| Component | Responsibility | Network Impact |
| --- | --- | --- |
| **Cluster** | Logical grouping managing ECS tasks/services | Does not automatically assign public IPs to tasks |
| **Task Definition** | Container template: image, CPU/memory, ports, IAM roles, network mode | `networkMode: awsvpc` defines how the task uses VPC networking |
| **Task** | A single execution of a Task Definition, containing one or more containers | Has its own network interface/IP when using `awsvpc` |
| **Service** | Maintains desired task count, replaces failed tasks, manages deployments | Registers tasks with an ALB target group and places tasks in subnets/SGs |
| **ALB** | Receives HTTP(S), selects targets via listener rules and target-group health | Forwards requests to task **private IP and port** |
| **Security Group** | Stateful firewall at the ENI | Permits only authorized traffic, applied to each task's ENI |

In `awsvpc`, each task gets dedicated **task networking**. Logically, the task is attached to an **Elastic Network Interface (ENI)** with a **private IP** in the selected subnet. Containers within the **same task** share a network namespace and can communicate over `localhost` on non-conflicting ports; **different tasks** have separate IPs/ENIs and cannot communicate via `localhost`.

### 2.1. Task Networking on Fargate vs. EC2

- **AWS Fargate:** `awsvpc` is mandatory. On current supported platform versions, task traffic flows through the task ENI; you manage subnets and Security Groups without managing EC2 host servers.
- **ECS on EC2:** supports `awsvpc` alongside other network modes depending on OS and configuration. With `awsvpc`, tasks use ENIs/task IPs; the container instance's ENI attachment limit and **awsvpcTrunking** support affect task density.
- **Windows containers:** network mode support, versions, and architecture differ from Linux. Never copy Linux network mode configurations directly to Windows without checking documentation.

**A task ENI differs from an EC2 instance ENI in authorization scope.** With `awsvpc`, a **task-level** Security Group isolates each workload instead of opening ports across an entire EC2 host. On Fargate, this is the standard network model.

### 2.2. Comparing `awsvpc` with `bridge` and `host`

| Network Mode | Typical Model | Host Port | ALB Integration |
| --- | --- | --- | --- |
| **`awsvpc`** | Task has a VPC IP and task ENI | `hostPort` equals `containerPort` or is omitted per mode rules | **Target group type `ip`** |
| **`bridge`** | Linux containers share host network via bridge/NAT | Can use dynamic host port mapping on EC2 | Target registration typically uses instance ID and host port |
| **`host`** | Container shares the EC2 host's network namespace | Container ports bind directly on the host | Must manage port collisions when placing tasks on EC2 |

For new Fargate applications, `awsvpc` gives a clean **task IP + application port** mapping and easy per-service Security Groups. In return, you must size subnet IP space and watch ENI/compute limits.

### 2.3. What If One Task Has Two Containers?

Example task containing `api` and `telemetry-sidecar`:

~~~text
Task ENI: 10.30.10.25
├── api               : listens on 0.0.0.0:8080
└── telemetry-sidecar : listens on 127.0.0.1:4317

From api in the same task: call localhost:4317
From ALB outside the task: call 10.30.10.25:8080
~~~

Two containers in the same task **cannot bind conflicting IP/ports**. If `api` only binds `127.0.0.1:8080`, the ALB outside the task cannot connect to `10.30.10.25:8080`. Ensure the application listener binds `0.0.0.0` or the appropriate address whenever it must accept traffic via the ENI.

## 3. Reference Architecture: Public ALB, Private ECS Tasks

Suppose a containerized API is deployed on Fargate across two Availability Zones (**AZ A/B**) in one VPC.

~~~mermaid
flowchart TB
    User["Internet Users"] --> DNS["Route 53 / DNS"]
    DNS -.->|"Returns hostname/IP"| User
    User --> ALB["Internet-facing ALB\nHTTPS listener :443"]
    ALB --> TG["Target group\nTarget type = ip; HTTP :8080"]

    subgraph VPC["VPC 10.30.0.0/16"]
      subgraph AZA["Availability Zone A"]
        PubA["Public subnet A\nALB nodes; NAT-A if needed"]
        AppA["Private app subnet A\nTask ENI 10.30.10.25:8080"]
      end
      subgraph AZB["Availability Zone B"]
        PubB["Public subnet B\nALB nodes; NAT-B if needed"]
        AppB["Private app subnet B\nTask ENI 10.30.11.31:8080"]
      end
      TG --> AppA
      TG --> AppB
      AppA --> DB["RDS / private data service"]
      AppB --> DB
      AppA -.->|"HTTPS egress"| PubA
      AppB -.->|"HTTPS egress"| PubB
    end
    AppA -.->|"Logs / images / secrets via appropriate path"| AWS["ECR, S3, CloudWatch Logs,\nSecrets Manager"]
    AppB -.->|"Logs / images / secrets via appropriate path"| AWS
~~~

*This diagram shows logical relationships, not every network hop. The ALB is a logical resource spanning enabled subnets across AZs; the target group holds dynamic task IPs registered by ECS. Actual paths to AWS services depend on NAT or VPC endpoints and IAM.*

### 3.1. Sample Subnet Plan

| Component | Illustrative CIDR | AZ | Default IPv4 Route |
| --- | --- | --- | --- |
| `public-a` | `10.30.0.0/24` | A | `0.0.0.0/0 → Internet Gateway` |
| `public-b` | `10.30.1.0/24` | B | `0.0.0.0/0 → Internet Gateway` |
| `app-a` | `10.30.10.0/24` | A | `0.0.0.0/0 → NAT-A` if app needs Internet egress |
| `app-b` | `10.30.11.0/24` | B | `0.0.0.0/0 → NAT-B` if app needs Internet egress |
| `db-a` | `10.30.20.0/24` | A | No default Internet route needed if DB has no Internet egress need |
| `db-b` | `10.30.21.0/24` | B | No default Internet route needed if DB has no Internet egress need |

Each **subnet resides in one AZ**. A subnet can host many task ENIs; reserve enough private IPs for desired count, scale-out, **deployment overlap** (old and new tasks coexisting briefly), ALB/endpoint ENIs, and supporting infrastructure.

**Private subnet** does not mean tasks can never connect to the Internet. Tasks receive no public IP, yet can initiate outbound connections through NAT or access AWS services via VPC endpoints when configured.

### 3.2. Path of an HTTPS Request

1. Client resolves `api.example.com` and opens HTTPS to the public ALB on port `443`.
2. **ALB Security Group** evaluates inbound traffic from the client.
3. ALB listener matches host/path rules and selects the ECS service's **target group**.
4. ALB forwards the request (e.g., HTTP to `8080`) to a **task ENI private IP** registered in the target group.
5. **Task Security Group** evaluates inbound `TCP 8080`, allowing it only from authorized sources such as the ALB SG.
6. Container `api` processes and replies; the stateful Security Group automatically permits return traffic for the tracked connection.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant L as ALB :443
    participant T as ECS Task 10.30.10.25:8080
    participant D as Database :5432
    C->>L: HTTPS GET /orders
    L->>T: HTTP GET /orders, target IP:8080
    T->>D: TCP 5432 (if needed)
    D-->>T: Query result
    T-->>L: HTTP 200 + JSON
    L-->>C: HTTPS 200 + JSON
~~~

When the ALB terminates TLS, the **ALB → task** leg can use internal HTTP. If security requirements mandate end-to-end TLS, choose an HTTPS target group and configure certificates/trust inside the container; never assume listener TLS automatically encrypts the backend hop.

## 4. `awsvpc`: IPs, Ports, and Operational Limits

### 4.1. Which IP Does a Task Receive?

In an ECS Service using `awsvpc`, `networkConfiguration.awsvpcConfiguration` specifies:

- A list of **subnet IDs** where tasks may be placed.
- A list of **Security Group IDs** attached to task ENIs.
- `assignPublicIp` as `ENABLED` or `DISABLED` in supported environments; production typically sets **`DISABLED`** when tasks sit behind an ALB in private subnets.

When a service specifies subnets across multiple AZs, ECS distributes tasks across those subnets/AZs according to scheduler mechanics and available capacity. Still, do not treat listing two subnets as a **guarantee** that exactly half the tasks always sit in each AZ; monitor actual placement, capacity, and scaling behavior.

### 4.2. Port Mappings in the Task Definition

Example task definition using `networkMode=awsvpc` with container `api` listening on `8080`:

~~~json
{
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/shop-api:release-2026-11",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ]
    }
  ]
}
~~~

*This is a fragment for analysis, not a complete Task Definition: a real Fargate deployment also needs family, CPU, memory, execution role, and other required fields.*

With `awsvpc`, `hostPort` can be omitted or set equal to `containerPort` per mode rules; do not use `bridge`-style dynamic host port mapping (`hostPort=0`) expecting a random host port. The ALB connects directly to **task IP:8080**, not an EC2 host IP with a translated port.

**Important:** `containerPort` tells ECS how to wire routing/target registration, **it does not start a server inside the image**. Your app must actually listen on that port. Dockerfile `EXPOSE` is also metadata only and does not replace listener configuration.

### 4.3. ENIs, IPs, and Scalability Limits

With Fargate, a task's IP/ENI is allocated at launch and released when the task stops per service mechanics. When ECS replaces a task:

~~~text
Old task  arn:...:task/old  →  10.30.10.25:8080
New task  arn:...:task/new  →  10.30.10.47:8080
~~~

Clients and ALBs must never hardcode old task IPs. **The ECS Service automatically manages target registration/deregistration** for tasks per its load balancer configuration.

Limits to plan for:

- **IP address utilization** in each subnet: scale-out and rolling deployments need more IPs than steady-state task count.
- **EC2 network limits** if running ECS on EC2 with `awsvpc`: ENI/trunking limits, instance types, and resource availability.
- **Fargate quotas / task CPU-memory** and per-AZ capacity.
- **Downstream connections**: not only CPU—RDS connection limits, NAT connection capacity, and downstream throughput can also bottleneck.

## 5. Security Groups by Least Privilege

Security Groups are **stateful**. They evaluate inbound/outbound traffic at the network interface; return packets for a tracked connection are permitted automatically without symmetric rules for ephemeral ports. Subnet **Network ACLs** are stateless, use numbered Allow/Deny rules, and require checking **both directions** when customized.

### 5.1. Four Security Groups

Suppose:

- `sg-alb` is attached to the ALB.
- `sg-api` is attached to ECS task ENIs.
- `sg-db` is attached to RDS.
- `sg-vpce` is attached to interface VPC endpoints (if used).

| Security Group | Inbound to Consider | Outbound to Consider |
| --- | --- | --- |
| **`sg-alb`** | `TCP 443` from valid clients/CIDRs | `TCP 8080` to `sg-api` and health check port if different |
| **`sg-api`** | `TCP 8080` **only from `sg-alb`** | `TCP 5432` to `sg-db`, `TCP 443` to needed endpoints/APIs |
| **`sg-db`** | `TCP 5432` **only from `sg-api`** | Per DB operations and network policy |
| **`sg-vpce`** | `TCP 443` from `sg-api` or allowed private CIDRs | Return traffic on stateful connections; check endpoint policies |

Security Group rules can reference a **Security Group ID** as source/destination where supported by AWS. That way, when old task `10.30.10.25` is replaced by new task `10.30.10.47`, you **never have to update CIDRs/IPs in the ALB or database SGs**.

### 5.2. Illustrative Rules for the ALB Path

~~~text
sg-alb
  IN  TCP 443   Source 0.0.0.0/0    (if API is genuinely public)
  OUT TCP 8080  Destination sg-api

sg-api
  IN  TCP 8080  Source sg-alb
  OUT TCP 5432  Destination sg-db
  OUT TCP 443   Permitted destinations for APIs and AWS endpoints

sg-db
  IN  TCP 5432  Source sg-api
~~~

If only internal staff use the API, the ALB should have **`Scheme: internal`** or restricted ingress rather than public `0.0.0.0/0`. If IPv6 is required, add matching IPv6 rules (`::/0` when genuinely public) and verify ALB IP address type/VPC settings.

**Do not configure `sg-api` inbound rules and forget outbound.** Under strict egress controls, tasks still need access to databases, ECR/S3 for image pulls, CloudWatch Logs, Secrets Manager, or other services depending on lifecycle and app needs. A new SG's default "allow all outbound" helps demos start fast, but is not a final least-privilege policy.

### 5.3. Why Not Open `TCP 8080` from the Whole Internet to Tasks?

Even if tasks in private subnets lack public routes, overly broad SGs expand exposure from **connected networks**—including VPC peering, VPNs, or Transit Gateways if present and routed. The rule "API tasks accept traffic only from `sg-alb`" shrinks the attack surface and blocks unauthorized routed sources.

Security Groups **do not authenticate HTTP users**: the ALB can handle TLS and partial auth, yet the app must still validate tokens, data authorization, and request integrity per business logic.

### 5.4. How Do Network ACLs Affect Traffic?

If using custom NACLs, inspect both **ALB** and **task** subnets:

| Packet | Boundary | Destination Port to Check |
| --- | --- | --- |
| Client → ALB | Public subnet inbound | `443` |
| ALB → client | Public subnet outbound | Client ephemeral port |
| ALB → task | Public subnet outbound and private app subnet inbound | `8080` |
| Task → ALB | App subnet outbound and public subnet inbound | ALB-side connection ephemeral port |

This is a general model of TCP flows, not an exhaustive NACL ruleset for the entire VPC. Ephemeral port ranges depend on platform/path; health checks, egress to AWS APIs, DBs, and other services also have their own flows. A NACL **Deny** blocks traffic even when an SG allows it.

## 6. ALB Integration: Listeners, Target Groups, and Target Types

**ALB** operates at Layer 7; a listener receives HTTP/HTTPS on a **port**, then listener rules select an action, typically **forward to a target group**. The target group holds the targets to which the ALB sends requests, evaluated by health checks.

### 6.1. Why Is `TargetType=ip` Required for `awsvpc`?

For an ECS Service using `awsvpc`, AWS requires a **target group with target type `ip`**, not `instance`. Reason: traffic must reach the **task ENI/private IP**, not an EC2 container instance ID.

~~~text
Correct for awsvpc:
  Target type: ip
  ECS registers: 10.30.10.25:8080, 10.30.11.31:8080

Wrong for awsvpc:
  Target type: instance
  Expects ECS to register: i-0123456789abcdef0:8080
~~~

`instance` fits ECS on EC2 designs with matching host network/port mappings, but **does not apply directly to `awsvpc`**.

### 6.2. How Do Listeners and Target Groups Match Ports?

A common configuration:

| Component | Example | Role |
| --- | --- | --- |
| ALB scheme | `internet-facing` | Accepts public traffic |
| ALB listener | `HTTPS :443` | TLS with ACM certificate |
| Listener rule | `Host: api.example.com` or `Path: /api/*` | Selects backend per request |
| Target group | `HTTP :8080`, `TargetType=ip` | Set of ECS task IPs:ports |
| ECS Service load balancer | `containerName=api`, `containerPort=8080` | Binds the exact container to the target group |
| Container app | Listens on `0.0.0.0:8080` | Serves requests and health checks |

The ALB listener port does not have to equal the container port. The ALB can terminate HTTPS on `443` and forward HTTP on `8080`. When internal traffic requires TLS, the target group can use HTTPS if the container server supports it.

### 6.3. Target Group Health Checks

Example:

~~~text
Protocol: HTTP
Port: traffic-port (8080)
Path: /health/ready
Success code: 200
Interval: 30 seconds (example)
Healthy threshold: 2
Unhealthy threshold: 3
Timeout: per supported config
~~~

Health checks are real network requests from ALB nodes to tasks. They require **Security Groups and NACLs to permit** the path and the container to return the expected status code. If the app only exposes `/health/ready` while the target group defaults to `/` (returning `404`), ECS tasks can show `RUNNING` while targets stay **unhealthy**.

Distinguish:

- **ECS container health check:** command run inside the container (if configured) to report container health.
- **ALB target-group health check:** network request to the target's IP/port/path.
- **ECS Service scheduler:** uses health check results and deployment settings to replace tasks or wait for service stability.

A container reporting `HEALTHY` while the ALB shows `unhealthy` often points to networking/port/HTTP path mismatches. Conversely, an ALB can reach a `200` endpoint before real business dependencies are ready. Design health signals closely around actual readiness.

### 6.4. `RUNNING` Does Not Automatically Mean Serving Traffic

Typical sequence:

~~~mermaid
flowchart LR
    NEW["ECS creates task"] --> ENI["ENI/IP + SG"]
    ENI --> PULL["Pull image + init/logs/secrets"]
    PULL --> START["Container runs, listener starts"]
    START --> REG["Register task IP:port into target group"]
    REG --> HEALTH["ALB health checks"]
    HEALTH --> READY["Target healthy, serving requests"]
    READY --> DRAIN["Deployment/scale-in: deregistration/draining"]
    DRAIN --> STOP["Task stopped"]
~~~

*Actual execution may overlap across stages. This diagram illustrates states operators inspect, not a strict state machine of the entire ECS/ELB API.*

**ALB exhibits "fail-open" behavior** in certain scenarios when all registered targets in a target group across enabled AZs fail health checks: the ALB may still distribute requests to those targets. Therefore, **never rely on ALB health checks as your sole safeguard against bad requests**; implement proper application error handling and DR strategies.

### 6.5. Grace Period and Draining

- **`healthCheckGracePeriodSeconds`** in an ECS Service tells the scheduler to ignore certain unhealthy LB/VPC Lattice/container health checks while the app starts up; base this value on real init time, never to mask chronic failures.
- **Target group deregistration delay** gives in-flight connections/requests time to finish when a target is removed; it does not guarantee every long-running request completes.
- **`SIGTERM` and graceful shutdown**: the app should stop accepting new work, finish active requests, close DB connections, and exit within the timeout granted by ECS/platform.
- **Deployment circuit breaker/rollback** (for supported ECS deployment types) reduces risk from rollouts failing to reach steady state; verify enabled settings and rollback behavior.

A health check should not "wait 15 seconds for the database" when normal requests take a few hundred milliseconds. Align timeouts, thresholds, and readiness with your SLO.

## 7. VPC Egress for ECS Tasks in Private Subnets

A private task typically needs two traffic categories:

1. **Serving traffic:** ALB sends requests to the task; task calls RDS, Redis, internal services.
2. **Startup and operational traffic:** pulling ECR images, fetching secrets, shipping logs, calling AWS APIs, emitting telemetry.

When egress fails, ECS tasks can **fail to start** or fail to emit logs even if the ALB SG and task SG properly allow `TCP 8080`.

### 7.1. NAT Gateway

A straightforward design gives private subnets a `0.0.0.0/0` route to a NAT Gateway in a public subnet, which routes via an Internet Gateway.

~~~text
App subnet A: 0.0.0.0/0 -> NAT-A (public subnet AZ A)
App subnet B: 0.0.0.0/0 -> NAT-B (public subnet AZ B)
~~~

A **per-AZ NAT** pattern prevents AZ-level egress dependency. Sharing one NAT Gateway in AZ A across tasks in AZ B creates a single point of failure if AZ A fails. However, each NAT Gateway incurs hourly and data-processing charges; balance **availability vs. cost**.

NAT **does not expose private tasks publicly**: it only enables outbound connections initiated from private subnets.

### 7.2. VPC Endpoints for Required AWS Services

For Fargate pulling images from **Amazon ECR** and using **`awslogs`**, endpoints commonly evaluated include:

| Service | Typical Endpoint / Connection | Purpose |
| --- | --- | --- |
| **ECR API** | Interface endpoint `com.amazonaws.<region>.ecr.api` | ECR auth/metadata during image pulls |
| **ECR Docker registry** | Interface endpoint `com.amazonaws.<region>.ecr.dkr` | Docker Registry API when fetching images |
| **Amazon S3** | Gateway endpoint for S3 | Access S3-backed image layers via appropriate path |
| **CloudWatch Logs** | Interface endpoint `com.amazonaws.<region>.logs` | Container log delivery via `awslogs` |
| **Secrets Manager** | Interface endpoint `com.amazonaws.<region>.secretsmanager` | Fetch secrets at startup or runtime |
| **SSM Parameter Store** | `ssm` endpoint and related endpoints when needed | Read parameters per app mechanism |

This list is a **needs-based reference**. Exact endpoint requirements depend on Fargate platform version, public vs. private ECR/registry, image layer location, secret types, AWS Regions, and how the app calls APIs. Not every ECS service needs all endpoints; conversely, missing an endpoint for a dependency you actually use can break deployments.

**PrivateLink setup:** interface endpoint ENIs need a Security Group allowing inbound `TCP 443` from the task SG; enable VPC DNS/private DNS, routes/NACLs, and compatible endpoint policies. The S3 gateway endpoint uses route tables and policies differently from interface endpoints; creating an endpoint alone does not guarantee every AWS API call works.

### 7.3. Which Role Needs ECR and Logging Permissions?

Task Definitions typically separate:

- **Task execution role:** used by ECS/Fargate to pull ECR images, send CloudWatch Logs via log drivers, and inject supported secrets.
- **Task role:** used by the containerized application calling AWS SDKs/APIs, such as S3 or DynamoDB.

The two roles are **not interchangeable**. An app whose task role has `s3:GetObject` still cannot pull its image if the execution role lacks ECR permissions; conversely, giving broad permissions to the execution role does not grant those permissions to application code inside the container.

## 8. Sample Deployment Configuration with CloudFormation

The template below illustrates an ECS Fargate service behind an HTTPS ALB, using `awsvpc` with tasks placed in **two private app subnets**. It assumes **VPC, public/private subnets, Security Groups, ECS cluster, ACM certificate, ECR image, and IAM roles already exist**. This is a learning/customization sample, **not a complete production template**: real deployments create billable ALB, task, and supporting resources.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: ECS Fargate awsvpc behind HTTPS ALB (learning example)

Parameters:
  ClusterArn:
    Type: String
  VpcId:
    Type: AWS::EC2::VPC::Id
  PublicSubnetA:
    Type: AWS::EC2::Subnet::Id
  PublicSubnetB:
    Type: AWS::EC2::Subnet::Id
  PrivateAppSubnetA:
    Type: AWS::EC2::Subnet::Id
  PrivateAppSubnetB:
    Type: AWS::EC2::Subnet::Id
  AlbSecurityGroupId:
    Type: AWS::EC2::SecurityGroup::Id
  TaskSecurityGroupId:
    Type: AWS::EC2::SecurityGroup::Id
  CertificateArn:
    Type: String
  ImageUri:
    Type: String
  ExecutionRoleArn:
    Type: String
  TaskRoleArn:
    Type: String

Resources:
  ApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      RetentionInDays: 14

  ApiTask:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: shop-api
      RequiresCompatibilities: [FARGATE]
      NetworkMode: awsvpc
      Cpu: '256'
      Memory: '512'
      ExecutionRoleArn: !Ref ExecutionRoleArn
      TaskRoleArn: !Ref TaskRoleArn
      ContainerDefinitions:
        - Name: api
          Essential: true
          Image: !Ref ImageUri
          PortMappings:
            - ContainerPort: 8080
              Protocol: tcp
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref ApiLogGroup
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: api

  ApiTargetGroup:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      VpcId: !Ref VpcId
      TargetType: ip
      Port: 8080
      Protocol: HTTP
      HealthCheckProtocol: HTTP
      HealthCheckPort: traffic-port
      HealthCheckPath: /health/ready
      Matcher:
        HttpCode: '200'

  PublicAlb:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Type: application
      Scheme: internet-facing
      Subnets:
        - !Ref PublicSubnetA
        - !Ref PublicSubnetB
      SecurityGroups:
        - !Ref AlbSecurityGroupId

  HttpsListener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      LoadBalancerArn: !Ref PublicAlb
      Port: 443
      Protocol: HTTPS
      Certificates:
        - CertificateArn: !Ref CertificateArn
      DefaultActions:
        - Type: forward
          TargetGroupArn: !Ref ApiTargetGroup

  ApiService:
    Type: AWS::ECS::Service
    DependsOn: HttpsListener
    Properties:
      Cluster: !Ref ClusterArn
      ServiceName: shop-api-service
      TaskDefinition: !Ref ApiTask
      LaunchType: FARGATE
      DesiredCount: 4
      HealthCheckGracePeriodSeconds: 60
      DeploymentConfiguration:
        DeploymentCircuitBreaker:
          Enable: true
          Rollback: true
      NetworkConfiguration:
        AwsvpcConfiguration:
          AssignPublicIp: DISABLED
          Subnets:
            - !Ref PrivateAppSubnetA
            - !Ref PrivateAppSubnetB
          SecurityGroups:
            - !Ref TaskSecurityGroupId
      LoadBalancers:
        - TargetGroupArn: !Ref ApiTargetGroup
          ContainerName: api
          ContainerPort: 8080
~~~

### 8.1. Reviewing the Critical Wiring Points

| Config Setting | Must Match |
| --- | --- |
| `ApiTask.NetworkMode: awsvpc` | Tasks use ENIs/IPs in subnets |
| `ApiTask.ContainerDefinitions.Name: api` | `ApiService.LoadBalancers.ContainerName: api` |
| `PortMappings.ContainerPort: 8080` | `LoadBalancers.ContainerPort: 8080` and app listening on `:8080` |
| `ApiTargetGroup.TargetType: ip` | ECS task IPs under `awsvpc` |
| `ApiTargetGroup.HealthCheckPath` | Actual HTTP path returning `200` from the container |
| `PublicAlb.Subnets` | Two **public subnets** in different AZs |
| `ApiService.Subnets` | Two **private app subnets** with sufficient IPs and egress |
| `ApiService.SecurityGroups` | SG on **task ENIs**, permitting inbound `8080` from ALB SG |
| `ExecutionRoleArn` | Permissions to pull ECR, write logs, inject secrets as needed |

This CloudFormation snippet **does not create route tables, NAT Gateways, or VPC endpoints**, does not create SG ingress/egress rules, and does not verify image/tag/certificate validity. Operators must verify those prerequisites alongside IAM/ACM/CloudWatch Logs. Having `DesiredCount: 4` alone also does not guarantee enough capacity remains if an entire AZ fails.

### 8.2. Task Definitions Can Contain Multiple Containers

If a sidecar exists, `LoadBalancers.ContainerName` must point to the container **that actually handles requests from the ALB**. The task ENI and Security Group apply at the task level, not per container. If two services need different network permissions, split them into **separate ECS services/tasks** rather than expecting per-container SGs within one task.

## 9. Inspecting the System via AWS CLI (Read-Only)

The following commands only read state. Replace `my-ecs-cluster`, `shop-api-service`, sample ARNs/IDs, and Region for your authorized environment. No resources need to be created or modified.

### 9.1. Inspect ECS Service, Network Config, and Target Group

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --services shop-api-service \
  --query "services[].{Name:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Network:networkConfiguration,LoadBalancers:loadBalancers,Events:events[0:5].message}" \
  --output json
~~~

Verify subnets/SGs, `assignPublicIp`, and `containerPort`/target group ARN. `RunningCount` matching `DesiredCount` **is not enough**: also verify target health and application errors.

### 9.2. Inspect Task Definition Network Mode

~~~bash
aws ecs describe-task-definition \
  --region ap-southeast-1 \
  --task-definition shop-api \
  --query "taskDefinition.{Family:family,Revision:revision,NetworkMode:networkMode,Ports:containerDefinitions[].portMappings,ExecutionRole:executionRoleArn,TaskRole:taskRoleArn}" \
  --output json
~~~

If the task revision changed, query the exact ARN/revision the service is running; do not assume from the family name alone.

### 9.3. List Tasks and Inspect ENI/IP Details

~~~bash
aws ecs list-tasks \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --service-name shop-api-service

aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --tasks TASK_ARN_1 TASK_ARN_2 \
  --query "tasks[].{Id:taskArn,Status:lastStatus,Desired:desiredStatus,Health:healthStatus,ENI:attachments[].details,Containers:containers[].{Name:name,Status:lastStatus,Reason:reason}}" \
  --output json
~~~

`TASK_ARN_1`/`TASK_ARN_2` are placeholders. Under `attachments[].details`, look for `networkInterfaceId`, `privateIPv4Address`, `subnetId`, and related fields. Returned keys vary by platform/launch type, so do not index blindly by array position.

### 9.4. Read Actual ENI and Security Group Details

~~~bash
aws ec2 describe-network-interfaces \
  --region ap-southeast-1 \
  --network-interface-ids eni-0123456789abcdef0 \
  --query "NetworkInterfaces[].{Id:NetworkInterfaceId,PrivateIP:PrivateIpAddress,Subnet:SubnetId,Groups:Groups[].GroupId,Status:Status}" \
  --output json
~~~

The ENI ID here is illustrative; substitute the ID from `describe-tasks`. Cross-check IP/SG/subnet against your architecture diagram and observe how they change when ECS replaces a task.

### 9.5. Check ALB Target Type and Health Status

~~~bash
aws elbv2 describe-target-groups \
  --region ap-southeast-1 \
  --target-group-arns TARGET_GROUP_ARN \
  --query "TargetGroups[].{Name:TargetGroupName,Type:TargetType,Protocol:Protocol,Port:Port,HealthPath:HealthCheckPath,Matcher:Matcher}" \
  --output json

aws elbv2 describe-target-health \
  --region ap-southeast-1 \
  --target-group-arn TARGET_GROUP_ARN \
  --query "TargetHealthDescriptions[].{Target:Target,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" \
  --output json
~~~

With `awsvpc`, expect `Type=ip` and target IDs to be **task private IPs**. If targets are `unhealthy`, read `Reason` (e.g., timeout or response code mismatch) and inspect networking/path/container rather than blindly bumping CPU.

### 9.6. Inspect Container Logs When `awslogs` Is Enabled

~~~bash
aws logs describe-log-streams \
  --region ap-southeast-1 \
  --log-group-name /ecs/shop-api \
  --order-by LastEventTime \
  --descending \
  --max-items 10
~~~

The example log group `/ecs/shop-api` may not match the auto-named CloudFormation log group in Section 8. Always read `LogConfiguration` on the active task definition to find the exact log group, Region, and stream prefix before querying.

## 10. Diagnosing Connectivity: From DNS to the Container Port

When users see `502`, `503`, `504`, or target-group `unhealthy`, isolate the failing layer in order:

~~~text
Client / DNS
   ↓
ALB public subnet + listener :443 + certificate
   ↓
Listener rule → Target group type ip
   ↓
Task private IP:8080 + task SG + NACL
   ↓
Container listener 0.0.0.0:8080
   ↓
Readiness / business dependencies (RDS, APIs, secrets...)
~~~

### 10.1. Common Error Reference Table

| Symptom | Primary Suspects | How to Verify |
| --- | --- | --- |
| **Cannot create ECS Service after attaching ALB** | Target group not `ip`, wrong `containerName/containerPort`, or listener not attached to TG | `describe-task-definition`, `describe-services`, `describe-target-groups` |
| **`Target.Timeout`** | SG/NACL blocks TCP 8080, app not listening, or request too slow | Check task inbound from ALB SG, port/container logs, health check timeout |
| **`Target.ResponseCodeMismatch`** | Health endpoint returns `404`, `301`, `401`, `500`, or code outside matcher | Hit `/health/ready` directly, inspect logs and matcher |
| **`Target.ConnectionError`** | Nothing listening on task IP/port, task restarting, or connection reset | Verify `0.0.0.0` bind address, container status, ECS events |
| **ECS task `RUNNING` yet ALB returns 503** | No healthy/registered targets, misconfigured ALB listener/TG | `describe-target-health` and listener rules |
| **`CannotPullContainerError`** | Wrong ECR image/tag, execution role lacks permissions, missing NAT/endpoints | ECR URI, role, ECR API/DKR + S3 connectivity |
| **`ResourceInitializationError`** | Cannot access secrets/logging/image metadata or startup config error | Task stopped reason, endpoints/DNS/KMS/IAM, `awslogs` config |
| **New tasks stop repeatedly during deploy** | Container crash, OOM, failed health checks, grace period too short | Stopped reason, logs, target health, rollout events |
| **App calls to DB time out** | Task SG egress, DB SG inbound, routes/NACLs, or DNS | Verify `sg-api → sg-db:5432` and DB connection pool |
| **App AWS SDK calls get `AccessDenied`** | Task role lacks permissions or endpoint/bucket policy denies | Task role, IAM policies, CloudTrail, resource policies |
| **HTTPS client cannot reach ALB** | DNS/IGW route, ALB SG inbound 443, listener/certificate | DNS query, `describe-load-balancers`, ALB logs |

**Never "test-fix" by opening `0.0.0.0/0` on the task SG**: it masks root causes and increases risk. Pinpoint the exact source IP/SG, port, and target state.

### 10.2. Distinguishing ALB 502, 503, and 504

- **502 Bad Gateway** can stem from backend connection errors, resets, or malformed responses.
- **503 Service Unavailable** typically indicates the ALB has no available/registered targets or cannot route the request per rules.
- **504 Gateway Timeout** occurs when connecting to or waiting for a response from a target times out.

Do not treat HTTP status codes as a full diagnosis; inspect **ALB access logs**, metrics, `TargetHealth.Reason`, and application logs. Remember that when all registered targets are unhealthy, ALB **fail-open** behavior may still send traffic to those targets.

### 10.3. Inspecting from Inside a Task

If the environment allows **ECS Exec** with proper IAM/SSM configuration, operators can check listeners/DNS inside a container without opening SSH to hosts:

~~~bash
# Illustrative only when ECS Exec is explicitly enabled and authorized
aws ecs execute-command \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --task TASK_ARN \
  --container api \
  --interactive \
  --command "/bin/sh"
~~~

ECS Exec is **not** enabled automatically. It requires platform support, permissions, and SSM connectivity, and minimal images may lack a shell. Executing into production containers is a privileged action requiring approval and audit logging. If the image lacks `curl`/`sh`, rely on logs, metrics, or approved diagnostic tooling rather than altering production images arbitrarily.

## 11. Multi-AZ, Deployments, and Fault Tolerance

### 11.1. Two-AZ ECS Service Does Not Automatically Equal High Availability

Suppose a service runs **4 tasks**, two in each AZ:

~~~text
AZ A: task 1, task 2
AZ B: task 3, task 4
ALB enabled in A and B, target group holds 4 private IPs
~~~

If AZ A fails, B has two tasks left. If each task safely sustains at most `100 req/s` per benchmarks and peak load is `350 req/s`, B only sustains `200 req/s`—**failing peak demand despite two running tasks**.

To sustain `350 req/s` when one AZ is lost at `100 req/s` per task:

~~~text
Surviving tasks required = ceil(350 / 100) = 4
If balanced across two AZs and losing an entire AZ:
  Illustrative minimum reserve = 4 tasks / AZ
  Total when both AZs are healthy = 8 tasks
~~~

This is an illustrative capacity model. Real capacity also depends on CPU, memory, RDS latency, connection limits, Fargate/EC2 quotas, scale-out speed, and ALB behavior. **Auto Scaling after an outage takes time** and is not an instant guarantee.

### 11.2. Deployment Overlap and Health

During a rollout, ECS may start new tasks while keeping old tasks running temporarily depending on deployment configuration. This requires:

- Enough **subnet IPs** for new task ENIs.
- Enough CPU/memory/quotas and available images/secrets.
- New tasks becoming healthy before old targets are removed.
- Appropriate readiness path and `healthCheckGracePeriodSeconds`.
- Graceful shutdown of old tasks, matching target deregistration delay and in-flight request draining.
- Rollback if the new revision fails to stabilize.

An infrastructure-level deployment success does not guarantee business-level success; monitor `HTTPCode_Target_5XX_Count`, latency, and transaction success rates immediately after rollout.

### 11.3. Stateful Data and Sessions

Avoid keeping sessions or order data solely in a single task's memory. When ECS replaces a task and assigns a new private IP, in-memory state is lost. For HA applications:

- Persist transactional data in RDS/DynamoDB with retries and idempotency.
- Store sessions using stateless tokens or a fault-tolerant external session store.
- Store files/user uploads in S3/EFS or suitable services, never in the container's temporary writable layer.
- Design shutdown and job handling so tasks terminated during scale-in do not drop in-progress work.

## 12. One VPC, Multiple ECS Services: Splitting Traffic

Suppose an e-commerce system has two ECS services:

- **Catalog API**: container port `8080`, path `/catalog/*`, read-only product data.
- **Checkout API**: container port `9090`, path `/checkout/*`, read/write order data.

You can share one ALB with **two separate target groups**, each using `TargetType=ip` and its own health check path:

| Component | Catalog | Checkout |
| --- | --- | --- |
| ECS service | `catalog-service` | `checkout-service` |
| Task SG | `sg-catalog` | `sg-checkout` |
| Container port | `8080` | `9090` |
| Target group | `tg-catalog-ip` | `tg-checkout-ip` |
| Listener rule | `/catalog/*` | `/checkout/*` |
| Health path | `/catalog/health` | `/checkout/health` |
| DB access | Read-only per role/network | Read/write per role/network |

The **ALB Security Group** needs outbound rules to both task SGs on their respective ports. **Catalog task SG** permits inbound 8080 only from the ALB SG; **Checkout task SG** permits inbound 9090 only from the ALB SG. Database and AWS API permissions should also differ per task role.

If Checkout calls Catalog **from the backend**, avoid routing through the public ALB when privacy, latency, or cost requirements argue against it. Consider an **internal ALB**, ECS Service Connect, or supported service discovery; design dedicated routing and SG rules for service-to-service traffic.

## 13. Monitoring, Security, and Cost

### 13.1. Metrics to Monitor

| Layer | Metrics / Signals |
| --- | --- |
| **ALB** | `RequestCount`, `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime` |
| **Target group** | `HealthyHostCount`, `UnHealthyHostCount`, `TargetConnectionErrorCount` |
| **ECS Service** | Desired/Running/Pending task counts, service events, deployment failures |
| **Containers** | CPU/memory utilization, exit codes, OOMs, app logs, and latency |
| **Network** | VPC Flow Logs, NACL/SG `REJECT`s (correlate with config), NAT traffic, and endpoint errors |
| **Data dependencies** | RDS connections/latency, queue backlog, cache hits, DB errors |
| **Cost** | Fargate vCPU/GB-hours, ALB capacity, NAT hours/bytes, PrivateLink endpoints, logs/metrics, data transfer |

`HealthyHostCount > 0` does not prove you can survive losing an AZ. Alert against the **minimum count required to meet SLOs**, not simply whether any target is alive.

### 13.2. CloudTrail, Logs, and Admin Permissions

To audit deployments and infrastructure changes:

- **CloudTrail** for ECS/ELB/EC2/IAM control-plane operations per active configuration.
- **CloudWatch Logs** for container stdout/stderr when `awslogs` is configured and execution role/networking work.
- **ALB access logs** (if enabled) to trace requests, backend status, and latency.
- **VPC Flow Logs** for network connection metadata; note that a `REJECT` record **does not identify the exact SG/NACL rule that blocked it**.
- Maintain separate IAM roles for CI/CD, task execution, and task apps; tightly restrict `iam:PassRole`, `ecs:UpdateService`, and SG/ALB modifications.

Never write secrets, tokens, or sensitive customer data to logs. Enforce log retention and read access controls per policy.

### 13.3. Cost Trade-Offs

- **Fargate** removes EC2 host management while charging per configured/used task resources; evaluate Savings Plans against actual load.
- **ALB** bills hourly plus Load Balancer Capacity Units; sharing one ALB can save money versus one ALB per service, at the expense of listener rule complexity and shared blast radius.
- **Per-AZ NAT** raises availability while adding hourly and data-processing costs; **interface VPC endpoints** charge per ENI/AZ and bytes processed.
- **CloudWatch Logs** and Container Insights carry ingestion/retention/metric fees; configure telemetry intentionally.
- **Cross-AZ traffic** can incur transfer charges along specific flows; map ALB/task/DB/endpoint paths before estimating.

Never pick a network design solely by counting NAT Gateways or ALBs. **Total cost must align with RTO/SLO, security, and operational capability.**

## 14. Production Deployment and Verification Workflow

1. **Prepare networking:** VPC, public/private subnets across at least two AZs, IGW, private egress via NAT/endpoints as needed, DNS, and IP headroom.
2. **Prepare Security Groups:** ALB inbound 443, ALB outbound on app port; task inbound only from ALB SG, task outbound to DB/AWS endpoints as needed.
3. **Prepare image & IAM:** image in registry, task execution role for pull/logs/secrets; task role scoped to AWS APIs used by the app.
4. **Create Task Definition:** `networkMode=awsvpc`, matching container name/port, resources, log config, health/stop behavior.
5. **Create ALB and target group:** multi-AZ ALB, HTTPS listener/certificate, target group **`ip`**, accurate health check.
6. **Create ECS Service:** Fargate or EC2 launch type/capacity provider, private subnets, task SG, `assignPublicIp=DISABLED` where appropriate, bind exact `containerName`/`containerPort` to target group.
7. **Verify steady state:** ECS desired/running, target group healthy, HTTP requests succeeding via ALB/DNS, and DB/API dependencies authorized.
8. **Test rollout/rollback:** deploy a test revision, watch new tasks register and old tasks drain, confirm zero unacceptable SLO disruption.
9. **Test AZ loss:** simulate in staging and verify remaining capacity/egress—never cause unplanned production outages.
10. **Post-deploy monitoring:** metrics, logs, alerts, cost, auditing, and security incident response readiness.

### 14.1. Pre-Production Operations Checklist

- [ ] Task Definition sets `networkMode=awsvpc`; ECS Service uses matching subnets/SGs and launch type.
- [ ] Target group sets **`TargetType=ip`**, wired to the right listener and container name/port.
- [ ] Container listens on an address reachable via the task ENI, not only `127.0.0.1`.
- [ ] ALB resides in public subnets with proper routes/IGW; private tasks have no unnecessary public IPs.
- [ ] ALB SG ↔ task SG permits only app/health ports; task SG ↔ DB/APIs match exact sources and destinations.
- [ ] ECR, S3, CloudWatch Logs, Secrets Manager, and other dependencies have working IAM + NAT/VPC endpoints.
- [ ] Readiness path returns the expected HTTP code, with tuned grace period and deregistration delay.
- [ ] ECS tasks span multiple AZs, and capacity under single-AZ loss has been calculated and tested.
- [ ] Logs/metrics/traces, deployment alerts, and rollback procedures are active with clear owners.
- [ ] Costs for NAT, endpoints, Fargate, ALB, logging, and cross-AZ transfer are estimated.

## 15. Reinforcement Exercises

### Exercise 1 — Choosing Target Type

An ECS Fargate service has task IP `10.30.10.25` and container port `8080`, but the target group was created with `TargetType=instance`. Why does this fail? What must change?

**Hint:** Fargate uses `awsvpc` and task ENIs/private IPs, not EC2 container instance targets. Use **target group type `ip`** and wire the ECS service to container `api`/`8080`.

### Exercise 2 — Security Group Misconfiguration

The ALB HTTPS 443 listener works. The task SG only permits inbound `TCP 8080` from `10.99.0.0/16`, while the ALB lives in `10.30.0.0/16`. The target group reports timeouts.

**Hint:** task SG inbound blocks the actual ALB source. Restrict inbound properly to **source `sg-alb`** (where SG referencing is supported) or the right source CIDR. Also check ALB SG outbound 8080 and NACLs if customized.

### Exercise 3 — App Healthy in Container, ALB Unhealthy

The task is `RUNNING`; the app only returns 200 on `/health/ready`, while `GET /` returns 404. The target group uses default path `/` and matcher 200.

**Hint:** the ALB health check is hitting the wrong path. Configure `/health/ready`, then verify target health, networking, and rollout behavior.

### Exercise 4 — Why Can't the Task Pull Its Image?

A Fargate task is placed in a private subnet with `assignPublicIp=DISABLED` and no NAT. The team created the target group properly and opened ALB → task SG on 8080, yet the task stops with `CannotPullContainerError`.

**Hint:** the failure happens **before the container ever serves traffic**. Check paths to ECR/registry and S3 image layers, required VPC endpoints, endpoint SGs, DNS, and the task **execution role**. Target groups do not fix image pulls.

### Exercise 5 — Losing One AZ

A service runs four tasks, two per AZ; peak traffic is 350 req/s and one task safely handles 100 req/s. When AZ A fails, B has two tasks left. Can the system handle peak traffic?

**Hint:** no—B only has capacity for ~200 req/s. To guarantee at least 350 req/s when one AZ fails, you need roughly **four surviving tasks**, equating to four tasks/AZ in a simple balanced model before safety margins and dependency capacity.

### Exercise 6 — Two Containers in One Task

A task has containers `api` and `metrics`. `metrics` listens on `127.0.0.1:4317`; `api` sends telemetry to `localhost:4317`. Do you need to open inbound SG port 4317 from the ALB?

**Hint:** no—containers **in the same task share a network namespace** under `awsvpc`; `localhost` works internally. The ALB only needs to reach `api:8080`; never expose sidecar ports on the SG.

### Exercise 7 — Multi-Service Design

One ALB must route `/catalog/*` to container port 8080 and `/checkout/*` to port 9090. Sketch the listener rules, two `ip` target groups, and two ECS services with separate task SGs. Verify each service's `containerName`/`containerPort` settings.

**Hint:** never mix two backends with different health endpoints and permissions in one target group. Each ECS service gets its own target group; listener rules forward by path/host to the right group.

## 16. Takeaways

- **`awsvpc`** gives an ECS task a **VPC network identity**: task ENI, private IP, and Security Groups. For Fargate, this mode is mandatory.
- For ECS Services using `awsvpc`, the ALB must use **target group type `ip`**, targeting **private task IP + container port**. The ALB listener can use HTTPS 443 while containers listen on HTTP 8080.
- **ALB SG** permits clients into the listener and ALB out to the task port; **task SG** permits inbound only from the ALB SG while allowing required outbound flows. Custom NACLs still require rules in both directions because they are stateless.
- **A `RUNNING` task does not guarantee a healthy ALB target.** Health paths, HTTP status codes, bind addresses, IAM/image pulls, network egress, and dependencies must all align.
- Production designs require **multiple AZs, spare capacity, graceful shutdown, logging/metrics, least-privilege IAM, and cost control**. Never troubleshoot connectivity by opening every Security Group instead of finding the root cause.

### Official AWS Documentation

- [Task networking with the awsvpc network mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html) — task ENIs, networking, and limits.
- [Amazon ECS task networking for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html) — subnets, public IPs, task ENIs, and platform versions.
- [Use an Application Load Balancer for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb.html) — ALBs and target groups for ECS.
- [Amazon ECS service definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html) — network configuration, load balancers, and health check grace period.
- [Amazon ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) — port mappings, roles, and containers.
- [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html) and [Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — stateful/stateless network controls.
- [ALB target groups](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html) and [Target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — target types and health.
- [Amazon ECR VPC endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) — private image pulls, S3, and endpoint dependencies.
- [VPC endpoints for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html) — ECS APIs, connectivity, and platform differences.
- [Task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) and [Task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — separating ECS runtime and application permissions.
- [Amazon ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) — debugging access to containers when authorized.
- [Troubleshoot ECS service load balancers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshoot-service-load-balancers.html) — analyzing target health and connection errors.
