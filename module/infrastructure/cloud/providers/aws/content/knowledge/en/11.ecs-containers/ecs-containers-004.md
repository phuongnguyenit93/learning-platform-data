# ECS Clusters, Task Definitions, and Services

## Learning Objectives

After this lesson, learners will be able to:

- Clearly distinguish **Amazon ECS cluster**, **task definition**, **task**, and **service**; describe the flow from a container image to a running application.
- Choose between **AWS Fargate**, **Amazon EC2**, or ECS-supported managed container capacity based on operational requirements, resources, and cost.
- Author a **task definition JSON** with sensible CPU, memory, image, ports, environment variables, secrets, log driver, and IAM roles.
- Explain why the **task execution role** and **task role** serve two distinct permission sets, and why a service needs proper VPC, subnet, security group, and endpoint configurations.
- Deploy an **ECS service** running multiple tasks across multiple Availability Zones behind an Application Load Balancer, with health checks, rolling deployments, and rollback handling.
- Distinguish one-off **RunTask** executions from a service maintaining `desiredCount`, as well as **ECS Service Auto Scaling** from scaling EC2 container instances.
- Monitor status and troubleshoot `CannotPullContainerError`, `ResourceInitializationError`, `STOPPED` tasks, `unhealthy` targets, and deployments failing to stabilize.
- Evaluate performance, availability, security, durable storage, observability, and cost for containerized applications on AWS.

**Context:** This lesson belongs to the **Containers with ECS** chapter in the **CLOUD_PROVIDERS_AWS** module. When packaging a Java/Spring Boot app or other API as a container, understanding ECS lets you combine **Regions/AZs**, **IAM**, **VPC**, **Elastic Load Balancing**, **S3/EFS/RDS**, integration services like **SQS**, and **CloudWatch** to deploy secure, scalable, and resilient applications. The lesson centers on three core concepts: **cluster, task definition, and service**.

> **Version note:** Console UI, Fargate options, task parameters, and deployment strategies evolve over time. Examples use Linux containers on AWS Fargate with `awsvpc`, ideal for learning the model. ARNs, IDs, and resource names below are illustrative and must be replaced with valid lab resources.

## 1. The Big Picture: From Image to Service

Amazon Elastic Container Service (**Amazon ECS**) is an orchestration service for **running and managing containers**. Instead of logging into each machine to run `docker run`, you declare the desired configuration; ECS coordinates the underlying infrastructure to run tasks, tracks state, and replaces tasks when needed.

Four foundational concepts:

| Concept | Definition | Example |
| --- | --- | --- |
| **Cluster** | Logical namespace holding services/tasks and the capacity configurations used to run them | `orders-prod` |
| **Task definition** | Versioned blueprint (with revisions) describing one or more containers, images, resources, roles, logs, and storage | `orders-api:7` |
| **Task** | A **specific running instance** of a task definition, with its own ARN and state | Task ID `a1b2...`, currently `RUNNING` |
| **Service** | Manager that maintains the desired task count and handles deployments, health/replacement, and ALB/NLB integration | `orders-api-service`, `desiredCount=3` |

~~~mermaid
flowchart TB
    Dev[Developer] --> Image[Container image]
    Image --> ECR[Amazon ECR / registry]
    ECR --> TD[Task definition family:revision]
    Cluster[ECS cluster] --> Service[ECS service: desiredCount = 3]
    TD --> Service
    Service --> T1[Task 1]
    Service --> T2[Task 2]
    Service --> T3[Task 3]
    T1 --> C1[orders-api container]
    T2 --> C2[orders-api container]
    T3 --> C3[orders-api container]
    ALB[Application Load Balancer] --> T1
    ALB --> T2
    ALB --> T3
~~~

**How to read this:** The image holds the program and libraries; the **task definition** specifies how the image runs; a **task** is the running unit; the **service** maintains the set of tasks; and the **cluster** is the organizational boundary where ECS operates these resources. **An ALB does not create tasks on its own**, and **a task definition by itself does not launch containers**.

### Example from a Java Application

Suppose a team has image `orders-api:v1.0.0` running Spring Boot on port 8080:

1. Build and push the image to **Amazon ECR**.
2. Register task definition `orders-api:1` (CPU, RAM, image URI, port 8080, task role, logs).
3. Create an ECS cluster and an ECS service with `desiredCount=2`.
4. The ECS scheduler launches two **tasks** from the task definition.
5. If the service is attached to an ALB target group, the two healthy tasks serve as API backends.
6. When a task stops unexpectedly, the service attempts to launch a **replacement task** to return to `desiredCount`.
7. When image v2 is ready, register a new task definition revision and update the service to deploy it.

Using **RunTask** alone without creating a service means step 6 **does not automatically happen as a desiredCount guarantee**.

## 2. ECS Cluster: Organizational Scope and Container Compute Capacity

A **cluster** is a **Region-level** logical resource—not by default a single server, a VPC, or a Kubernetes cluster. Within a cluster, you can run multiple services and standalone tasks using supported capacity/launch models.

Example:

~~~text
Region ap-southeast-1
└── ECS cluster: commerce-prod
    ├── Service: orders-api       → 3 tasks
    ├── Service: catalog-api      → 2 tasks
    ├── Service: worker           → 4 tasks
    └── Standalone task: data-migration (run once)
~~~

Multiple services can run in the same cluster; sharing a cluster **does not automatically allow** tasks to reach each other over the network or access each other's AWS resources. Access still depends on **VPCs, security groups, IAM, DNS, and application configuration**.

### What Does a Cluster Contain?

Depending on the model, a cluster associates with:

- **Capacity providers** such as `FARGATE`, `FARGATE_SPOT`, or providers backed by an EC2 Auto Scaling group;
- **EC2 container instances** registered by the ECS agent, if using the EC2 model;
- **Container Insights/monitoring** configuration, tags, and related integrations;
- **Services**, **tasks**, and active deployments managed by ECS.

**Do not confuse a cluster with a subnet:** When creating a **service or running a task using `awsvpc`**, you select subnets/security groups for the task. One cluster can span multiple subnets in a VPC according to each service's configuration; never assume every task in a cluster lives in the same subnet or same AZ.

### When Should You Split Clusters?

Consider splitting clusters when separating **environments** (dev/staging/prod), capacity policies, operations, permissions, and cost tracking. However, **a cluster is not a strong security boundary like an AWS account**. Sensitive systems may require separate accounts, VPCs, IAM boundaries, and operational separation rather than merely placing two services in two clusters.

## 3. Choosing Where Tasks Run: Fargate or EC2?

ECS orchestrates tasks; the compute running those tasks can be heavily AWS-managed or self-managed servers.

| Criterion | **ECS on AWS Fargate** | **ECS on Amazon EC2** |
| --- | --- | --- |
| Host servers | AWS manages the underlying host infrastructure | You manage the EC2 fleet (AMI, patching, capacity, agent) |
| Resource allocation | Allocates CPU/RAM per task using supported configurations | Tasks consume available resources on EC2 container instances |
| Task scaling | ECS Service Auto Scaling / service scheduler | ECS Service Auto Scaling **plus** ensuring EC2 fleet headroom |
| Networking | Requires `awsvpc`; tasks get ENIs and security groups per config | Supports `awsvpc`, `bridge`, `host` depending on OS/conditions |
| Host control | Limited kernel/host operations, no SSH to underlying host | Full control over OS settings, instance types, GPUs, host daemons/agents |
| Pricing | Based on vCPU/RAM/task duration and add-ons | Based on EC2/EBS and related resources; optimize host utilization |
| Best fit | APIs, web apps, workers, workloads wanting minimal host operations | Host customization needs, specialized hardware, or leveraging steady baseline load |

**Starting point:** If your priority is running web/API workloads with minimal EC2 management, evaluate **Fargate**. If you need hardware/host control or want to bin-pack many containers onto a long-lived EC2 fleet, evaluate **ECS on EC2**. AWS also offers other managed capacity options depending on service/Region availability; check current ECS documentation before finalizing.

### Capacity Provider Strategy

A capacity provider defines the compute pool ECS uses to run tasks. For Fargate, options commonly include:

- `FARGATE`: tasks run on standard Fargate capacity.
- `FARGATE_SPOT`: uses spare capacity at a discounted rate that **can be interrupted**, suited for workloads that tolerate retries and temporary task loss.

A strategy can set **base** and **weight** values to split task placement across providers as supported. Spot availability is never guaranteed, nor is an exact percentage split guaranteed at every instant.

Conceptual example for an asynchronous worker:

~~~text
Desired tasks: 10
Reference capacity strategy:
  FARGATE       base=2, weight=1
  FARGATE_SPOT  base=0, weight=3

Goal: keep a baseline of regular tasks while using Spot for the rest when available.
Do not use this strategy if every task must remain continuously running.
~~~

**Distinction:** When configuring a service, `launchType` and `capacityProviderStrategy` are two ways to specify capacity; per the AWS API, **do not pass both simultaneously** in the same service creation call.

### EC2 Also Needs a Host Scaling Layer

With ECS on EC2, `desiredCount=10` does not guarantee hosts have enough CPU/RAM/ENIs/ports to place 10 tasks. There are two layers:

1. **Service Auto Scaling:** adjusts the desired number of **tasks**.
2. **Cluster capacity scaling / EC2 Auto Scaling:** maintains enough **EC2 container instances** of the right types to fit the tasks.

You can use a **supported capacity provider with managed scaling** to coordinate the ASG, while still configuring min/max capacity, AZs, quotas, AMIs, instance types, and host security.

## 4. Task Definition: A Versioned Blueprint, Not a Running Task

A **task definition** is a JSON document declaring how ECS runs one or more containers. When registered with ECS, a **family** receives incrementing **revisions**:

~~~text
orders-api:1
orders-api:2
orders-api:3
...
~~~

Each registered revision is a specific configuration; to change the image, CPU, environment variables, roles, or container settings, you normally register a **new revision** and update the service. **Overwriting an image tag in the registry without changing the task definition is not a well-auditable or cleanly rollbackable release process**; prefer image digests or immutable tags.

### Key Field Groups

| Field | Description | Practical Notes |
| --- | --- | --- |
| `family` | Name of the task definition group | `orders-api` |
| `requiresCompatibilities` | Compatibility check for Fargate or target launch environment | `["FARGATE"]` |
| `networkMode` | Networking mode; Fargate requires `awsvpc` | Provides per-task ENI and SG |
| `cpu`, `memory` | Task-level resource allocation | Must select a valid platform combination |
| `runtimePlatform` | OS family and CPU architecture | Linux x86_64/ARM64 matching image support |
| `containerDefinitions` | Image, container name, CPU/memory, env, ports, health, logs | Includes primary and sidecar containers |
| `executionRoleArn` | Permissions for ECS/agent to pull images, send logs, read referenced secrets | Not for app code calling S3 |
| `taskRoleArn` | Permissions for application code inside the container to call AWS APIs | Least privilege per service |
| `volumes`, `mountPoints` | Storage used by the task per supported types | Ephemeral data, EFS, EBS managed per mechanism |
| `ephemeralStorage` | Extra temporary storage for Fargate where supported | Not a backup mechanism |

**Fargate CPU/RAM:** you must pick a **supported combination**—you cannot arbitrarily pair `cpu=256` with `memory=8192`. A valid Linux example is **512 CPU units (0.5 vCPU) + 1024 MiB**; higher tiers depend on OS/platform version/Region and service limits.

### Example JSON: Task Definition for a Spring Boot API

Suppose the team has already created the ECR repository, CloudWatch Logs group, and both IAM roles. `task-definition.json`:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "runtimePlatform": {
    "operatingSystemFamily": "LINUX",
    "cpuArchitecture": "X86_64"
  },
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/ordersAppTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:v1.0.0",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "APP_ENV",
          "value": "lab"
        }
      ],
      "secrets": [
        {
          "name": "DB_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders-db-password-xxxxxx"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/orders-api",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "orders"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -fsS http://localhost:8080/health/ready || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
~~~

**Reading the configuration:**

- `family` creates revisions `orders-api:n`.
- The task requests **0.5 vCPU, 1 GiB RAM**; this budget covers the **entire task**, not each individual container.
- The image comes from ECR; the container listens on `8080`.
- `APP_ENV` holds non-secret config; **DB_PASSWORD** is injected by ECS from Secrets Manager at task launch per supported integration.
- `awslogs` ships container logs to the prepared CloudWatch Logs group. If the log group does not exist or the execution role lacks permissions, task startup can fail.
- The container health check invokes `curl` **inside the image**; the image must actually include `curl` and expose `/health/ready`. If a minimal image lacks `curl`, swap the health command for a tool present in the image.
- `essential=true` marks the container as critical: when it stops, the task cannot continue as a healthy app and terminates per ECS lifecycle rules.

**This is a structurally complete illustrative JSON, not self-provisioning for dependencies.** IAM roles, ECR image, CloudWatch log group, secret, subnets, security groups, and ALB target group must already exist with compatible permissions before running.

### A Task Can Contain Multiple Containers

For example, a web API and a log/telemetry sidecar in the same task:

~~~text
Task: orders-api:3
  ├── container "orders-api"  (essential)
  └── container "telemetry"   (sidecar)
~~~

Containers in the same `awsvpc` task share a network namespace/ENI and can talk over **localhost**, while having separate resource allocations, lifecycles, health checks, and volume mounts per configuration. Do not bundle independent microservices as sidecars just to co-locate them: their scaling, deployments, and failures become coupled to the same task.

## 5. IAM: Task Role vs. Task Execution Role

This is one of the most common sources of ECS errors.

| IAM Role | Who Uses It? | Typical Permissions |
| --- | --- | --- |
| **Task execution role** | ECS container/Fargate agent performing startup and supporting tasks | Pull ECR images, write `awslogs`, read secrets referenced in the **task definition** |
| **Task role** | Application code running inside the container | `s3:GetObject`, `sqs:SendMessage`, `dynamodb:PutItem`, or business AWS APIs |
| **Container instance role** | ECS agent on the EC2 host in ECS on EC2 | Register the EC2 instance to the cluster and perform agent API calls |
| **Service-linked / infrastructure roles** | ECS service itself for specific integrations | Manage ELB targets, EBS/ECS Service Connect infrastructure where applicable |

### Example Permission Split

An API needs:

- **Pull ECR image:** task execution role.
- **Send CloudWatch logs:** task execution role.
- **ECS injecting `DB_PASSWORD` from Secrets Manager into the container:** task execution role needs `secretsmanager:GetSecretValue`; plus KMS permissions if encrypted with a customer managed key.
- **Java app directly calling S3 GetObject:** task role.
- **Java app directly calling Secrets Manager at runtime:** task role (distinct from ECS injecting secrets at task startup).

You can start from the AWS managed policy for the ECS task execution role for standard actions, then add **least-privilege permissions scoped to the actual secrets/logs/images**. Never attach `AdministratorAccess` just to bypass policy troubleshooting.

### Example Identity Policy for a Task Role Reading S3 Reports Only

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-reports-example/reports/*"
    }
  ]
}
~~~

If objects use SSE-KMS with a customer managed key, also verify **`kms:Decrypt`**, IAM/key policy/bucket policy, and Region. Task role permissions **do not replace** security groups or network routes to S3 endpoints.

### ECS Role Trust Policy

For IAM roles assumed by ECS tasks under standard integration, the trust policy must allow the appropriate service principal such as `ecs-tasks.amazonaws.com` and `sts:AssumeRole`. The IAM permissions policy determines **what the role can do**, while the trust policy determines **who/what can assume the role**. You can apply `aws:SourceAccount` and `aws:SourceArn` conditions per ECS IAM guidance to mitigate confused deputy risks.

## 6. Task: A Single Execution with Its Own State and Lifecycle

A task is a **running instance** of a task definition. Calling `RunTask` launches one or more tasks depending on `count` and capacity. Each task has an ID, ARN, last status, desired status, and container/attachment details.

Conceptual lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> PENDING
    PENDING --> ACTIVATING
    ACTIVATING --> RUNNING
    RUNNING --> DEACTIVATING
    DEACTIVATING --> STOPPING
    STOPPING --> DEPROVISIONING
    DEPROVISIONING --> STOPPED
    PENDING --> STOPPED: Initialization failed
~~~

The diagram illustrates common states; not every environment or API displays every intermediate transition or follows identical timing. When troubleshooting, inspect **`lastStatus`**, **`desiredStatus`**, **`stopCode`**, **`stoppedReason`**, and `containers[].reason/exitCode` via `DescribeTasks`.

### Standalone Task

`RunTask` fits:

- One-off data processing jobs;
- Supervised database migrations;
- Tasks triggered by EventBridge Scheduler/Step Functions;
- Separately orchestrated batch workers.

If a standalone task finishes or fails, **ECS does not automatically relaunch it to maintain a desired count** like a service. The job orchestrator must handle retries, idempotency, DLQs, and alerting.

### Service-Managed Task

An ECS service attempts to maintain `desiredCount`; the scheduler replaces stopped tasks and registers new tasks with target groups. However, replacement is not guaranteed to be instantaneous if:

- Fargate/EC2 capacity, IPs, or quotas are exhausted;
- Images cannot be pulled;
- IAM/secrets/logs fail;
- Application health checks fail;
- Networking/ALB configuration is broken.

**A `RUNNING` task does not mean the API is ready for traffic.** Distinguish ECS container health, ALB target health, and application readiness.

## 7. ECS Service: Maintaining Desired State

An **ECS service** declares and tracks:

- Cluster and service name;
- Active task definition revision;
- Launch type or capacity provider strategy;
- `desiredCount` and service scheduling/deployment configuration;
- Network configuration (subnets, security groups, public IP per model);
- Load balancer, target group, and service discovery if used;
- Deployment settings, circuit breaker, alarm/rollback, and autoscaling configuration;
- Tags, security, placement/availability, and lifecycle settings.

### What Does the Service Scheduler Do?

Suppose `desiredCount=3`:

~~~text
Normal state:            RUNNING 3 / desired 3
One task stops:          RUNNING 2 / desired 3
ECS schedules replacement: PENDING 1, RUNNING 2
New task becomes ready:  RUNNING 3 / desired 3
~~~

During a new deployment, ECS can temporarily run **more or fewer tasks than desired** within `minimumHealthyPercent` and `maximumPercent` bounds, depending on strategy and available capacity.

### A Service Can Run Tasks Without a Load Balancer

Example SQS worker:

~~~text
ECS service: invoice-worker
desiredCount=4
Tasks: poll SQS → idempotent processing → write S3/RDS
No ALB required for inbound Internet HTTP.
~~~

Conversely, HTTP-serving web/APIs typically integrate an **ALB**, though an ECS service **does not require** an ALB to be valid.

## 8. Networking with Fargate: awsvpc, ENIs, and AZs

With Fargate, `awsvpc` is mandatory. Each task gets an **elastic network interface (ENI)** and an IP address from the selected subnet; the task uses the security groups attached to its ENI.

### Two-AZ Web API Architecture

~~~mermaid
flowchart TB
    User[Browser / mobile] --> DNS[Route 53 / DNS]
    DNS --> ALB[Internet-facing ALB, HTTPS 443]
    subgraph VPC["VPC: 10.20.0.0/16 in Region"]
      subgraph A["AZ A"]
        PA[Public subnet A: ALB node]
        TA[Private subnet A: Fargate task ENI]
      end
      subgraph B["AZ B"]
        PB[Public subnet B: ALB node]
        TB[Private subnet B: Fargate task ENI]
      end
      ALB --> TG[Target group type ip]
      TG -->|TCP 8080| TA
      TG -->|TCP 8080| TB
    end
    TA --> DB[(RDS Multi-AZ)]
    TB --> DB
    TA --> S3[(S3 / SQS via appropriate endpoints)]
    TB --> S3
    ECS[ECS service / desiredCount 2] -. Maintains tasks .-> TA
    ECS -. Maintains tasks .-> TB
~~~

**Note:** the diagram shows logical relationships; the ALB runs across enabled AZs and routes to targets via ELB mechanisms. Tasks do not need public IPs to receive traffic **from the ALB** when routes and SGs permit.

### Security Groups by Traffic Direction

| Component | Baseline Reference Rules |
| --- | --- |
| **ALB SG** | Inbound TCP/443 from allowed clients; outbound TCP/8080 to task SG |
| **Task SG** | Inbound TCP/8080 from **ALB SG**, not open to the entire Internet |
| **DB SG** | Inbound DB port, e.g., TCP/5432, from **task SG** |
| **Task outbound** | Only to the DB/endpoints/APIs required by the app and task initialization |

**Fargate in private subnets** typically has no public IP (`assignPublicIp=DISABLED`). However, pulling ECR images, fetching secrets, shipping logs, and calling AWS services still require **outbound network paths**:

- Use a **NAT Gateway** to reach public service endpoints over Internet egress;
- Or use **VPC endpoints** for ECR API, ECR Docker registry, S3 (when fetching layers), CloudWatch Logs, Secrets Manager, and related services depending on workload/platform;
- Verify **private DNS**, endpoint security groups, route tables/NACLs, bucket/endpoint policies, and DNS resolvers.

**Missing connectivity to ECR/Secrets Manager/CloudWatch can trigger `ResourceInitializationError`** even when the task definition and IAM roles are valid.

### Target Group Type with awsvpc

Because tasks have their own **ENI/IP**, when attaching an `awsvpc` ECS service to an ALB or NLB, the target group must have **target type = `ip`**, not `instance`.

If you use the EC2 launch type with `bridge` network mode in supported scenarios, target registration and port mappings behave differently. **Never copy an `instance` target group directly from an EC2 ASG setup to Fargate `awsvpc`.**

### DHCP and DNS

New tasks inherit the VPC's DNS configuration at launch. If the VPC's DHCP option set changes, already-running `awsvpc` tasks may not pick up the new settings automatically; plan a deployment/task replacement to apply changes. Successful DNS resolution also does not guarantee connectivity—still verify SGs, routes, endpoints, IAM, and the application.

## 9. ALB Integration, Health Checks, and Service Discovery

### ALB in Front of an API

An HTTP-serving ECS service typically connects as follows:

~~~text
HTTPS listener 443 (ALB)
   └── target group "orders-api-tg", target type = ip
        ├── task ENI 10.20.10.21 : 8080
        └── task ENI 10.20.20.29 : 8080
~~~

When the service scales out or deploys a new task revision, ECS registers and deregisters targets in the corresponding target group. Because task IPs change across lifecycles, **never hardcode private task IPs** in clients.

### Three Levels of Health Checks

| Layer | What It Detects | Notes |
| --- | --- | --- |
| **Container health check** in task definition | Whether the command inside the container succeeds | Requires the tool inside the image; `startPeriod` gives boot time |
| **ALB target group health check** | Whether the target responds over HTTP/gRPC as configured from the ALB | Verify port, path, matcher, and ALB → task SG |
| **Service/deployment health** | Scheduler observes task state, container/LB health, and deployment progress | `RUNNING` alone may not mean the target is healthy |

For example, `/health/ready` should return 200 only once the app is listening, required migrations are done, and essential dependencies are reachable. If readiness depends on every unstable peripheral service, all tasks could go unhealthy simultaneously when replacing tasks cannot fix the issue; design health checks around genuine serving readiness.

### Service-to-Service Communication

Between internal ECS services, you can use:

- **ECS Service Connect** for service discovery/naming and supported observability/routing features;
- **AWS Cloud Map** service discovery with appropriate DNS/registration;
- **Internal ALB/NLB** when a stable HTTP/TCP endpoint with dedicated routing/load balancing is needed.

**Do not assume two services in the same cluster automatically resolve each other by service name** without configuring service discovery or an endpoint. Plan namespaces, DNS, SGs, and internal ports explicitly.

## 10. Rolling Deployment: Replacing Tasks Safely

An ECS service can replace running revisions with a new revision according to its deployment configuration. With a **rolling deployment**, the scheduler gradually swaps old tasks for new ones using these parameters:

| Parameter | Meaning in Rolling Updates | Example |
| --- | --- | --- |
| `desiredCount` | Desired number of tasks after deployment | 4 |
| `minimumHealthyPercent` | Minimum healthy percentage of desired tasks, rounded up | 100% → at least 4 healthy per applicable rules |
| `maximumPercent` | Maximum total task percentage during deployment, rounded down | 200% → up to 8 tasks in counted states |
| `healthCheckGracePeriodSeconds` | Window where the service ignores certain LB/VPC Lattice/container health checks during startup | E.g., 90 seconds after task start |
| `deploymentCircuitBreaker` | Detects rolling deployments failing to reach steady state; can roll back | `enable=true`, `rollback=true` |

A common default for rolling updates is **minimum 100%, maximum 200%**, though do not assume every deployment strategy shares identical defaults; verify in the API/Console.

### Example: Replacing 4 Tasks

Suppose `desiredCount=4`, `minimumHealthyPercent=100`, `maximumPercent=200`, and capacity is available:

~~~mermaid
sequenceDiagram
    participant Dev as CI/CD
    participant ECS as ECS service scheduler
    participant F as Fargate capacity
    participant LB as ALB target group
    Dev->>ECS: Update service to orders-api:8
    ECS->>F: Launch revision 8 tasks
    F-->>ECS: Tasks RUNNING
    ECS->>LB: Register new IPs, wait for healthy
    LB-->>ECS: New targets healthy
    ECS->>LB: Deregister/drain revision 7 tasks
    ECS->>F: Stop revision 7 tasks
    ECS-->>Dev: Deployment reaches steady state
~~~

If the new revision fails due to image, secrets, ports, memory, or health checks, the **circuit breaker** can mark the deployment failed and **roll back to the previously completed deployment** when enabled and an eligible prior deployment exists.

**Not every deployment type shares identical rollback settings**: ECS supports strategies such as rolling, blue/green, linear, and canary depending on controller/support. When using advanced strategies or CodeDeploy/external controllers, health checks, traffic shifting, and rollback settings differ. This lesson focuses on rolling updates.

### Watch Out for `desiredCount = 1` or Tight Capacity

If min healthy = 100%, max percent = 100%, and `desiredCount=1`, the service may have no headroom to launch a new task and no permission to stop the old task, stalling the deployment. Configure bounds that allow at least one task to **be started or stopped** per strategy, with sufficient capacity and quotas.

ALB **deregistration delay**, **container stop timeout**, and application graceful shutdown all affect in-flight requests. Never treat updating a task definition alone as guaranteeing a safe deployment.

## 11. ECS Service Auto Scaling: Scaling Task Counts on Demand

**ECS Service Auto Scaling** builds on **Application Auto Scaling** to automatically adjust an ECS service's **desired task count**. Options include target tracking, step scaling, scheduled scaling, and other supported mechanisms.

### Common Metrics

| Metric | When to Use | Signs of a Poor Choice |
| --- | --- | --- |
| **ECSServiceAverageCPUUtilization** | CPU correlates with API/worker load | CPU is low while latency rises due to DB/network |
| **ECSServiceAverageMemoryUtilization** | RAM reflects task memory pressure | High RAM from normal caching; adding tasks doesn't shrink per-task footprint |
| **ALBRequestCountPerTarget** | Web/API behind ALB with fairly uniform request cost | Long polling, highly uneven requests, or app not behind an ALB |
| **Custom metric** (queue backlog per task, wait time) | SQS workers where load does not arrive over HTTP | Missing metric publishing, or metric doesn't reflect real backlog |

Example:

~~~text
Service orders-api:
  min tasks = 2
  max tasks = 10
  target tracking = 60% target average CPU

When CPU stays high → increase desiredCount if conditions allow.
When CPU stays low  → decrease desiredCount per policy.
~~~

This is a learning example, **not a universal 60% recommendation**. Benchmark CPU, request rate, memory, concurrency, p95/p99 latency, and downstream impact.

### Two Scaling Layers on ECS on EC2

~~~mermaid
flowchart TD
    L[CloudWatch workload metric] --> S[Service Auto Scaling]
    S --> D[Increase desired task count]
    D --> H{Does EC2 cluster have capacity?}
    H -->|Yes| T[New tasks RUNNING]
    H -->|No| P[Tasks wait for placement / capacity]
    P --> C[Capacity provider managed scaling / EC2 ASG]
    C --> T
~~~

Increasing desired tasks when EC2 hosts lack CPU/RAM/ENIs/ports or fail placement constraints leaves tasks unplaced. With Fargate, you do not manage EC2 hosts directly, though capacity availability, IP exhaustion, and quotas/limits still apply.

### Why You Cannot Scale Everything Infinitely

- Adding app tasks still hits **RDS connection pool or database throughput** bottlenecks.
- NAT/ALB/VPC endpoints, S3/SQS/KMS API quotas, and costs rise with traffic.
- Spot interruptions/placement constraints introduce capacity variance.
- APIs storing sessions or files on local disk cannot safely hand off traffic across new tasks.

Before raising `max tasks`, run **load tests** and identify downstream limits.

## 12. Multi-AZ and ECS Service Resilience

Placing tasks across **subnets in at least two AZs** limits blast radius during an AZ impairment. However, **selecting two subnets does not automatically guarantee healthy tasks in both AZs at every moment**.

Consider:

1. **Placement:** the ECS scheduler distributes tasks according to capacity, availability, and supported policies; verify which AZs actually hold running tasks.
2. **Desired count:** with two tasks across two AZs, losing one task/AZ leaves one task—which may become overloaded.
3. **ALB:** enable at least two AZs, use `ip` target groups, and ensure active health checks.
4. **Data:** use RDS Multi-AZ, S3, EFS/backups, or replication aligned with RTO/RPO; never keep sole business state inside one task.
5. **Reserve capacity:** surviving tasks must handle the traffic level the organization expects to sustain during an AZ loss, or accept scale-out delay.
6. **Quotas/IPs:** private subnets need enough IP addresses, ENIs, and service limits to cover deployment surges too.
7. **Graceful failure:** client timeouts, retries/backoff, circuit breakers, and idempotency when tasks stop or swap.

### Simple Capacity Calculation

Suppose an API needs **240 RPS**, and one task sustains **80 RPS** within the p95 latency target.

Normally:

\[
N_{\text{minimum}}=\lceil 240/80\rceil=3\ \text{tasks}
\]

However, three tasks split across two AZs are **not enough** to absorb an AZ outage without losing capacity. If **one surviving AZ** must serve the full 240 RPS immediately, you need **at least 3 healthy tasks per AZ**, i.e., **6 tasks** normally—plus headroom for traffic peaks and rolling deployments per SLO.

This is an **illustrative capacity estimate**, not a guarantee that the service enforces exact per-AZ task counts by itself. Test placement and failure behavior, adjusting for real metrics and cost.

### Do Not Confuse Task Failover with Data Backup

If an API task becomes `STOPPED`, the ECS service can launch a new task. But if an invoice PDF lived only on the old task's ephemeral storage, that file is lost. **ECS services manage compute lifecycles, not application data backups.** Use S3/EFS/databases and a separate data recovery plan.

## 13. Task Storage: Ephemeral, EFS, and EBS

| Storage | Characteristics | Best Suited For |
| --- | --- | --- |
| **Fargate ephemeral storage** | Temporary storage tied to task lifecycle; deleted when task stops | Caches, scratch files, reproducible temporary files |
| **Amazon EFS** | Managed shared NFS filesystem; multiple tasks/instances can mount concurrently under supported setups | Shared files, content, uploads requiring POSIX |
| **Amazon EBS volumes for ECS tasks** | Managed block volumes where supported by ECS, typically tied to task/AZ and deploy configuration | Specialized stateful tasks needing a block device |
| **S3** | Object storage via API, not a mounted POSIX filesystem | Images, invoices, logs, backups, data lakes |
| **RDS/Aurora/DynamoDB** | Managed database services | Transactional/queryable business data with proper consistency and HA |

**Fargate Linux platform 1.4.0 or later** typically includes **20 GiB of default ephemeral storage**, configurable up to **200 GiB** where supported; downloaded and unpacked container images also count against this space. Ephemeral storage is **not a backup** and never carries over to replacement tasks.

**EBS for ECS tasks** differs from an EC2 host's root EBS disk: check ECS-supported deployment/volume types, **ECS infrastructure role** permissions, AZ locality, pricing, and lifecycle. Never assume an arbitrary EBS volume can be mounted simultaneously by multiple Fargate tasks across AZs. When multi-AZ shared files are needed, EFS is usually the clearer choice.

## 14. Security and Configuration for Applications in ECS

### Images and Supply Chain

- Store images in ECR/managed registries; restrict who can push and pull.
- Use **immutable tags or image digests** for repeatable, auditable deployments.
- Scan images, minimize installed packages, and run containers as **non-root** when feasible.
- Match CPU architecture to the image (`X86_64` vs. `ARM64`); patch base images and secret-handling libraries.
- Never bake passwords or AWS access keys into Dockerfiles/images.

### Secrets

- Use **AWS Secrets Manager** or **SSM Parameter Store** as appropriate.
- When ECS injects secrets as container environment variables, the execution role needs read access; **rotating a secret in Secrets Manager does not update environment variables inside already-running tasks**—new tasks must typically be launched.
- Secrets in environment variables can still leak via debug dumps, process introspection, or logging inside the container; enforce strict access control and log hygiene.
- If the app fetches secrets directly at runtime, grant permissions on the **task role**.

### IAM and Networking

- Separate the **task role** from the **execution role**; scope S3/SQS/DB/KMS permissions to least privilege.
- Place API tasks in **private subnets**, allowing backend ports only from the ALB SG as needed.
- Use TLS to the ALB and consider TLS to backends/DBs, protecting certificates and connection strings.
- Combine SGs/VPC endpoint policies with IAM; **having network reachability does not grant API authorization**.
- If using ECS Exec for debugging, tightly govern SSM channel permissions, auditing, encryption, and enable/disable policies; never treat ECS Exec as routine app operations.

### IAM Account Boundaries

An ECS cluster in the same account **does not isolate resources as strongly as separate AWS accounts**. For prod vs. dev or distinct data classification tiers, consider separate accounts, VPCs, roles, and KMS key policies. Distinguishing the task role from the execution role becomes even more critical when teams share an environment.

## 15. Observability: Logs, Metrics, Events, and Task Status

In ECS, troubleshooting should combine **ECS service events**, **`DescribeTasks`**, **CloudWatch Logs/Metrics**, and load balancer logs. Never diagnose a root cause from a single `STOPPED` status alone.

| Source | Useful Information | Pitfalls |
| --- | --- | --- |
| **ECS task status / `stoppedReason`** | Why a task failed to start or stopped | Top-level message may only show the failure layer; also inspect container `reason`/`exitCode` |
| **ECS service events** | Placement failures, unhealthy ALB targets, deployment starts/failures | Not every application-level error appears here |
| **CloudWatch Logs (`awslogs`)** | stdout/stderr, stack traces, Java app output, bootstrap logs | Missing logs may mean the container never started or execution role/networking failed |
| **CloudWatch ECS CPU/Memory** | CPU/RAM usage per cluster/service/task | Low CPU does not prove the app is healthy |
| **Container Insights** | Deeper ECS/task/container telemetry when enabled | Collection cost and metric scope depend on configuration |
| **ALB target health / 5xx / latency** | Whether the API receives traffic and responds properly | Healthy targets do not prove every business endpoint works |
| **CloudTrail** | Who registered task definitions, updated services, changed roles | Does not replace container application logs |
| **VPC Flow Logs / Resolver logs** | Helps debug connectivity and DNS | Network `ACCEPT` does not prove HTTP/DB success |

### Minimum Signals to Monitor

- **`RunningTaskCount` vs. `DesiredTaskCount`**; prolonged deployment instability.
- **CPU/Memory utilization**, OOM/exit codes, error rates, and application p95/p99 latency.
- **ALB `HealthyHostCount`**, 5xx responses, and target connection errors.
- **Deployment failures**, task launch/capacity errors, secrets access errors, and log delivery failures.
- **SQS queue backlog** for workers, DB connection saturation, and downstream dependencies.
- **Fargate/EC2, NAT, ALB, CloudWatch, and data transfer costs** by tags/environment.

Set log retention and restrict access to logs containing business data; separate infrastructure alerts (CPU) from service quality metrics (API errors, latency).

## 16. Hands-On via AWS Console: Deploying a Two-AZ Orders API

> **Lab environment:** Use an authorized lab account, Region, and VPC. You need a real container image, IAM roles, security groups, ECR, and a CloudWatch log group; Fargate, ALB, public IP/NAT/VPC endpoints, and logs may incur charges. Set budgets and clean up resources afterward. Never experiment directly in production without change review.

### Step 1 — Prepare Image and Permissions

1. Build an application returning HTTP 200 on `GET /health/ready` once fully ready.
2. Push image `orders-api:v1.0.0` to **Amazon ECR**; note its URI and architecture.
3. Create `ecsTaskExecutionRole` with permissions to pull images, write logs, and read task-definition secrets.
4. Create `ordersAppTaskRole` with app API permissions (S3/SQS/etc.) scoped to specific resource ARNs.
5. Create CloudWatch Logs group `/ecs/orders-api`; create the secret if used by the task.

### Step 2 — Prepare VPC and ALB

Assume the VPC has:

- `public-a`, `public-b`: two subnets in two AZs for the **internet-facing ALB**.
- `private-app-a`, `private-app-b`: two subnets in two AZs for **Fargate tasks**.
- `sg-alb`: inbound HTTPS 443 from valid clients; outbound TCP 8080 to `sg-orders-tasks`.
- `sg-orders-tasks`: inbound TCP 8080 from `sg-alb`; outbound per API/DB/log needs.
- Proper egress path so tasks can pull ECR images and reach logs/secrets via NAT or supported VPC endpoints.

Create an **ALB** with an HTTPS listener/ACM cert as needed, a **target group of type `ip`**, port 8080, and HTTP health check `/health/ready`.

### Step 3 — Create an ECS Cluster

ECS Console → **Clusters → Create cluster**. Select cluster/capacity settings suitable for **Fargate**. Name it `orders-lab`.

**Important:** Creating a cluster does not launch containers automatically; you still need a task definition and either a service or `RunTask`.

### Step 4 — Register a Task Definition

ECS Console → **Task definitions → Create new task definition**. Configure:

- Fargate, Linux, `awsvpc`;
- `0.5 vCPU`, `1 GiB memory`;
- ECR image URI, container name `orders-api`, port 8080;
- Execution role and task role;
- Environment/secrets/log configuration;
- Container health check using a command that actually exists inside the image.

After creation, note `orders-api:1` (or actual revision) and review the generated JSON.

### Step 5 — Create an ECS Service

Inside cluster `orders-lab` → **Services → Create**:

- Compute: Fargate or matching capacity provider strategy;
- Task definition `orders-api:1`;
- Service name `orders-api`, **desired tasks = 2**;
- Subnets `private-app-a` and `private-app-b`, task SG, public IP disabled;
- Load balancing: prepared ALB/`ip` target group, container name `orders-api`, port 8080;
- Health check grace period matching actual startup duration;
- Rolling deployment, circuit breaker/rollback enabled where supported and appropriate.

Wait for tasks to enter `RUNNING`, containers healthy, and ALB targets healthy; test `https://<alb-dns>/health/ready` from a lab client.

### Step 6 — Deploy a New Version

1. Build/push image `v1.0.1`.
2. Register a **new task definition revision** referencing the new image URI/tag or digest.
3. **Update service** to reference the new revision.
4. Watch deployment progress, task health, ALB targets, logs, and errors.
5. If deployment fails, inspect ECS service events/circuit breaker and the prior revision; never raise `desiredCount` endlessly to mask failures.

### Step 7 — Verify Multi-AZ Availability

Inspect `DescribeTasks` and actual ENIs/subnets/AZs; stop one task in the lab and verify the service launches a replacement task. Observe healthy task counts, latency, and replacement impact. **Do not intentionally break live AZ infrastructure** to simulate an outage; use approved failure-testing methods.

## 17. Hands-On via AWS CLI: Cluster, Task Definition, and Service

IDs, ARNs, and names below are **fictional**. Replace them with your lab account/VPC/Region values. Commands use AWS CLI v2 syntax; on Windows PowerShell, prefer JSON input files over complex inline quoting.

### 17.1. Verify Caller and Create Cluster

~~~bash
aws sts get-caller-identity --profile lab

aws ecs create-cluster \
  --cluster-name orders-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Inspect cluster:

~~~bash
aws ecs describe-clusters \
  --clusters orders-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

### 17.2. Register Task Definition

Save the JSON from Section 4 as `task-definition.json`, ensuring the real image/roles/log group/secret exist:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region ap-southeast-1 \
  --profile lab

aws ecs describe-task-definition \
  --task-definition orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

Check `taskDefinitionArn` and `revision`; in an empty family, the first revision is 1. If the family already existed, the revision number will be higher—**never hardcode revision numbers in real deployments**.

### 17.3. Create Service from JSON

Save the following example as `service.json`; prerequisite: the target group is **already attached to an ALB**, in the right VPC, with `targetType=ip`.

~~~json
{
  "cluster": "orders-lab",
  "serviceName": "orders-api",
  "taskDefinition": "orders-api:1",
  "desiredCount": 2,
  "launchType": "FARGATE",
  "platformVersion": "LATEST",
  "networkConfiguration": {
    "awsvpcConfiguration": {
      "subnets": [
        "subnet-0123456789abcdef0",
        "subnet-0fedcba9876543210"
      ],
      "securityGroups": [
        "sg-0123456789abcdef0"
      ],
      "assignPublicIp": "DISABLED"
    }
  },
  "loadBalancers": [
    {
      "targetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/orders-api-tg/0123456789abcdef",
      "containerName": "orders-api",
      "containerPort": 8080
    }
  ],
  "healthCheckGracePeriodSeconds": 90,
  "deploymentConfiguration": {
    "minimumHealthyPercent": 100,
    "maximumPercent": 200,
    "deploymentCircuitBreaker": {
      "enable": true,
      "rollback": true
    }
  }
}
~~~

Run:

~~~bash
aws ecs create-service \
  --cli-input-json file://service.json \
  --region ap-southeast-1 \
  --profile lab
~~~

**Do not pass both** `launchType` and `capacityProviderStrategy` in this request. If switching to capacity providers, adjust the fields accordingly and verify the provider is associated with the cluster. If the task definition lacks a valid image or subnet egress, the service will be created but tasks will repeatedly fail.

### 17.4. Check Service and Task Status

~~~bash
aws ecs describe-services \
  --cluster orders-lab \
  --services orders-api \
  --region ap-southeast-1 \
  --profile lab

aws ecs list-tasks \
  --cluster orders-lab \
  --service-name orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

Grab a real task ARN and describe it:

~~~bash
aws ecs describe-tasks \
  --cluster orders-lab \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/orders-lab/0123456789abcdef0123456789abcdef \
  --region ap-southeast-1 \
  --profile lab
~~~

Once the service stabilizes, verify:

- `runningCount` and `desiredCount`;
- `deployments`, `events`, and target health;
- task ENIs/subnets/AZs;
- container `lastStatus`, `healthStatus`, and `exitCode` if any.

### 17.5. Update to a New Task Definition Revision

After pushing image v2 and registering revision `orders-api:2` (actual value may differ):

~~~bash
aws ecs update-service \
  --cluster orders-lab \
  --service orders-api \
  --task-definition orders-api:2 \
  --region ap-southeast-1 \
  --profile lab
~~~

If the image uses a mutable tag and the task definition did not change, `--force-new-deployment` can trigger a fresh deployment, though for **reproducible releases** always use digests or a new revision pointing to the exact new artifact.

~~~bash
aws ecs wait services-stable \
  --cluster orders-lab \
  --services orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

The wait command only checks waiter criteria; still **verify live HTTP traffic, metrics, logs, and downstream impact**. Waiters can time out if tasks fail or the service cannot reach steady state; inspect service events rather than blindly increasing sleeps/retries.

### 17.6. Inspect Why a Task Stopped

Stopped tasks may need their ARN fetched from the **ECS Console / task list filtered by desired status** or from prior deployment output; do not look only at `RUNNING` tasks.

~~~bash
aws ecs list-tasks \
  --cluster orders-lab \
  --desired-status STOPPED \
  --region ap-southeast-1 \
  --profile lab

aws ecs describe-tasks \
  --cluster orders-lab \
  --tasks <actual-task-arn> \
  --region ap-southeast-1 \
  --profile lab
~~~

**In the example above**, `<actual-task-arn>` is a placeholder, not valid literal Bash syntax (`<` has special meaning in the shell). Substitute a real ARN before executing. `STOPPED` task status remains visible only for ECS's retention window; configure dedicated storage for long-term logs/metrics.

### 17.7. Lifecycle Management and Lab Cleanup

After collecting results, scale `desiredCount` to 0 and delete the service per lab procedures; clean up the target group/ALB, log group, secret, ECR images, IAM roles, and cluster **only if created for the lab** and no dependencies remain. **Deleting a cluster does not delete external resources** such as ALBs, ECR, CloudWatch Logs, or VPCs.

## 18. Troubleshooting by Symptom

| Symptom | Common Causes | Right Layer to Inspect |
| --- | --- | --- |
| `CannotPullContainerError` | Wrong image URI/tag/digest, missing ECR pull permissions, ECR endpoint/network failure | Image existence, execution role, ECR auth, SGs, NAT/VPC endpoints |
| `ResourceInitializationError` | Cannot fetch secret/SSM param, cannot create log stream, startup service connectivity failure | Execution role, `secretsmanager:GetSecretValue`, KMS, Logs, DNS/egress |
| Task `STOPPED` immediately | Essential container crash, missing env var, wrong CPU architecture, bad startup command | `DescribeTasks`, `stoppedReason`, exit code, CloudWatch Logs |
| Task `RUNNING` but ALB unhealthy | App not listening, wrong port/path/matcher, ALB→task SG blocks traffic | Target health reason, task ENI IP, local endpoint, health check config |
| Task cannot be placed/allocated | Fargate capacity/quotas, subnet IP exhaustion; EC2 host out of CPU/RAM/ENIs/ports | ECS service events, free subnet IPs, service quotas, capacity providers |
| Desired = 4 but Running = 2 persistently | Task startup/placement failures, launch/config/network error | ECS events, stopped tasks, quotas, `executionRole`, egress |
| Service deployment rolls back | New revision unhealthy or circuit breaker triggered | Deployment history, events, container logs, compare task definitions |
| Cannot connect to DB | Wrong DB hostname/port/SG, DNS/VPC route, IAM auth, or credentials | Task→DB SG, resolver, Secrets Manager, DB logs; separate network vs. auth |
| Reading S3 returns `AccessDenied` | Task role lacks S3/KMS, or bucket/key policy denies | Caller task role, IAM policy, bucket policy, KMS key |
| Logs are empty | App hasn't started, bad `awslogs` config, execution role lacks Logs, networking failure | Log group/stream, task initialization logs, and `stoppedReason` |
| Task OOMKilled | Memory too low, JVM heap mismatch with container limit | Exit code/OOM, CloudWatch/Container Insights, JVM container flags |
| Scaling out does not improve p95 | RDS, cache, network, or downstream dependency is the bottleneck | APM/traces, DB connections, queues, downstream latency |
| Only AZ B fails | AZ B SG/NACL/route/endpoint differs from AZ A; capacity shortage | Task subnet/ENI/AZ, per-AZ egress and ALB health |
| Secret rotated, app still uses old value | Secret injected at task launch; existing tasks not yet replaced | Controlled task revision deployment/restart, or runtime refresh mechanism |
| Task IP change breaks clients | Hardcoded task IPs, missing service discovery/load balancer | Use ALB/Service Connect/Cloud Map, proper TTLs, and retries |

### Ordered Diagnostic Procedure

~~~text
1. Confirm account, Region, cluster, service, and task definition revision.
2. Check DescribeServices: desired/running/pending, deployments, events.
3. Check DescribeTasks for both RUNNING and STOPPED tasks: stopCode/stoppedReason,
   container reason/exitCode, ENIs, and health status.
4. If failing before container start: check ECR image,
   execution role, network egress, Secrets Manager, and CloudWatch Logs.
5. If container runs but API fails: check ALB target type ip, port/path,
   task security group, app logs, DB/DNS, and readiness.
6. If scaling/deploy fails: check capacity/quotas, policies, min/max,
   deployment config, AZs, circuit breaker, and rollback.
7. Fix one specific root cause; redeploy in lab, test HTTP/SQS,
   and observe latency/errors after the change.
~~~

**Never fix issues by attaching `AdministratorAccess`, opening SGs to `0.0.0.0/0` on backend ports, or assigning public IPs to every task without evaluation.** Those workarounds hide IAM/egress bugs and introduce serious risk.

## 19. Cost Visibility and Control

### Which Components Drive Fargate Cost?

Depending on configuration and current pricing, Fargate costs typically depend on **vCPU**, **memory**, **task runtime per billing rules**, and **extra ephemeral storage** beyond the default allowance. Different platforms/architectures and Spot capacity carry different rates.

Beyond Fargate itself, account for:

- **ALB** and load balancer capacity unit usage;
- **CloudWatch Logs/metrics/Container Insights**;
- **NAT Gateways**, VPC endpoints, public IPv4 addresses, and cross-AZ/Internet data transfer;
- **ECR storage/scanning/image transfer** per usage;
- **Secrets Manager/KMS**, S3/EFS/EBS, RDS, SQS;
- Multi-AZ reserve capacity and staging/prod environments.

### Example vCPU-Hours and GB-Hours Calculation

A service runs **4 Fargate tasks** continuously for **30 days**, each with **0.5 vCPU, 1 GiB RAM**:

\[
H = 4 \times 24 \times 30 = 2880\ \text{task-hours}
\]

\[
\text{vCPU-hours} = 2880 \times 0.5 = 1440
\]

\[
\text{GB-hours} = 2880 \times 1 = 2880
\]

To convert to currency, multiply by the vCPU-hour/GB-hour rates **for the exact Region, OS/architecture, and On-Demand vs. Spot pricing**, then add supporting service costs. This is a capacity estimate only and does not reflect every billing rounding or minimum increment detail.

### When Can EC2 Be More Cost-Effective?

If many tasks use relatively steady CPU/RAM and an EC2 fleet is well-utilized, ECS on EC2 can reduce raw compute spend compared to Fargate, in exchange for patching/AMI/host security, capacity management, scaling, Spot interruption handling, and instance operations. **Compare total cost of ownership**, not just one task rate vs. one instance rate.

### Cost Guardrails

- Set **AWS Budgets**, cost allocation tags (`application`, `environment`, `team`), and anomaly alerts.
- Justify `min/max tasks`; keeping a high `desiredCount` all month is expensive.
- Size CPU/RAM from benchmarks; over-provisioning Fargate CPU/memory also costs money.
- Apply proper retention to images/logs and tear down unused lab resources.
- Measure NAT/endpoint/data transfer; spreading many chatty tasks across AZs can increase cross-AZ traffic.
- Never put interruption-intolerant workloads on Fargate Spot just for lower pricing.

## 20. Three Design Scenarios

### Scenario A — Always-Available E-Commerce API

**Requirements:** Java/Spring Boot API over HTTPS, managing orders and product images, with campaign traffic spikes.

**Suggested design:**

- Immutable ECR images;
- ECS cluster + **Fargate service** with an appropriate minimum `desiredCount`, tasks across two AZs;
- Public ALB + `ip` target group + `/health/ready` health check;
- RDS Multi-AZ, S3 for images/invoices, SQS for background processing;
- Task role scoped strictly to required S3/SQS actions; execution role for pulling ECR/writing logs/reading secrets;
- Service Auto Scaling on CPU or `ALBRequestCountPerTarget` after benchmarking;
- CloudWatch alarms/Container Insights and deployment circuit breaker;
- Test single-task/AZ loss, DB failover, and peak traffic.

**Lesson:** ECS handles compute scheduling; **data HA, auth, networking, and cost** still require deliberate architecture.

### Scenario B — SQS Event-Consumer Worker

**Requirements:** Generate PDF invoices from orders; long processing time, retryable, scale up workers when backlog grows.

**Suggested design:**

- ECS service running worker tasks, **no ALB required**;
- Task definition with config environment variables and scoped SQS/S3 permissions;
- Scale tasks by **queue backlog per task** or an equivalent real metric;
- **Visibility timeout, DLQ, and idempotency** to handle interrupted tasks;
- Consider `FARGATE_SPOT` for interruption-tolerant capacity alongside baseline standard capacity if needed;
- Persist output files to S3, never solely in ephemeral storage.

### Scenario C — Scheduled Batch Job

**Requirements:** A nightly data aggregation job that runs to completion and exits, serving no HTTP traffic.

**Suggested design:**

- Dedicated task definition for the job;
- **EventBridge Scheduler/Step Functions + `RunTask`** as appropriate;
- Do not keep a 24/7 ECS service running for a once-a-day job;
- Handle exit codes, retries, timeouts, idempotency, and audit logging;
- Choose Fargate/EC2 based on runtime duration, resource profile, and cost.

## 21. Pre-Deployment Checklist

- [ ] Understood **cluster ≠ task definition ≠ task ≠ service** and chose `RunTask` vs. service appropriately.
- [ ] Selected Fargate/EC2 based on resources, platform limits, host operations, and total cost.
- [ ] ECR image exists, tags/digests are well-governed, and CPU architecture matches.
- [ ] Task definition has valid CPU/memory pairing, container name/port, log/health configs, environment vars, and secret references.
- [ ] Task execution role handles ECR pulls, CloudWatch Logs, and startup secrets; task role holds only application API permissions.
- [ ] For `awsvpc`, subnets, security groups, IP capacity/network egress, and DNS are properly configured.
- [ ] If using ALB/NLB with `awsvpc`, target group has **target type = `ip`**, matching port, and working health check.
- [ ] Multi-AZ selected and actual placement verified; sufficient reserve tasks/capacity for SLOs.
- [ ] `desiredCount`, deployment min/max, grace period, circuit breaker/rollback, and graceful shutdown verified.
- [ ] Service Auto Scaling uses realistic metrics, min/max bounds, and accounts for DB/SQS impact and cost.
- [ ] Durable data is never stored only in ephemeral storage; S3/EFS/EBS/DB chosen for the workload.
- [ ] CloudWatch logs/alarms, ECS events, health metrics, tracing, log retention, and auditing are in place.
- [ ] Secrets/KMS/IAM, TLS/VPC endpoints, public/private networking, and image security are reviewed.
- [ ] Tested `STOPPED` tasks, bad images, failing health checks, scale-out/in, and recovery in lab.
- [ ] IaC, change review, rollback plan, cleanup, and budgets exist per Region/workload.

## 22. Self-Check Exercises

### Exercise 1 — Identify the Four Concepts

An operations team has:

~~~text
Cluster: sales-lab
Task definition: product-api:5
Service: product-api-service, desiredCount=3
Tasks: 3 task ARNs, each running 1 product-api container
~~~

Explain which is the **blueprint**, which is the **maintenance controller**, which is the **execution unit**, and why mutating the image behind revision 5 without creating a new revision is poor release hygiene.

### Exercise 2 — Compare Execution Role and Task Role

A Java container involves:

1. ECS pulling the image from ECR.
2. ECS loading a secret from Secrets Manager and injecting it as an environment variable.
3. The Java SDK writing messages to SQS.
4. The Java SDK reading an SSE-KMS object from S3.

Classify the actions/IAM roles for each step, including KMS permissions, key policies, and specific S3/SQS resources. Explain why adding ECR pull permissions to the task role will not fix image pull failures.

### Exercise 3 — Diagnose a Target Group Error

A Fargate service has `RUNNING` tasks in private subnets, yet the ALB returns HTTP 503. The target group was created with **target type `instance`**, backend port 8080.

List at least four checks to perform: target type, ECS service load balancer configuration, task SG, target health, application endpoint/path, and outbound networking for task startup. Propose how to replace the target group properly and verify.

### Exercise 4 — Deployment Rollback

A service runs `orders-api:3` stably. The team creates revision 4, but the image omitted `curl`; the task definition health check still invokes `curl`.

Describe the observable states, ECS service events/logs, how the circuit breaker rollback behaves if enabled, and how to fix the image/health command and deploy revision 5. Explain why `RUNNING` does not equate to healthy.

### Exercise 5 — Sustaining Service When One AZ Fails

Load testing shows 1 task sustains 60 RPS; the system must sustain 180 RPS immediately when one AZ loses capacity.

1. Calculate the minimum healthy tasks that must **remain** in the surviving AZ (`ceil(180/60)=3`).
2. If both AZs are balanced and full capacity is needed immediately without waiting to scale, what is the minimum total task count?
3. If 25% headroom is desired, how many tasks per AZ are needed (`ceil(180×1.25/60)=4`)?
4. Why must scheduler placement, subnet IPs, Fargate capacity, and RDS capacity still be tested?

### Short Questions

**1. Does creating an ECS cluster automatically launch containers?** No. You need a task definition plus `RunTask` or a service with suitable capacity.

**2. Can you directly edit the image of an already-registered task definition revision?** Not under standard revision management; register a new revision.

**3. If a standalone task stops, does ECS automatically replace it to keep one task running?** No; a service maintains `desiredCount`, or an external orchestrator must handle retries.

**4. Does a Fargate task require an EC2 instance you administer?** No, AWS operates the host; you still configure CPU/RAM, networking, IAM, storage, and cost.

**5. Which target group type should an `awsvpc` Fargate API use with an ALB?** `ip`.

**6. Which role receives permission for the app to send SQS messages?** The task role; the execution role serves the ECS agent's tasks.

**7. Does `desiredCount=3` guarantee three healthy tasks?** No. You must inspect running count, health status, placement, and logs.

**8. If a task fails, does the ECS service recover data from the old task's ephemeral storage?** No. Durable data must be stored outside the task.

## 23. Summary

In ECS, **the cluster organizes workloads**, **the task definition is the versioned blueprint**, **the task is a concrete running instance**, and **the service maintains the desired task count and orchestrates deployments**. Understanding these distinctions lets you turn container images into well-governed production applications.

For web/APIs, designs typically begin with a **multi-AZ Fargate service**, a **task definition specifying CPU/RAM, IAM, and logs**, an **ALB target group of type `ip`**, health checks, rolling deployments, and metric-driven autoscaling. For short-lived jobs, consider **`RunTask`**. For specialized workloads, ECS on EC2 is an option with added host capacity management.

**System availability is more than whether ECS restarts tasks.** Combine **least-privilege IAM, VPC routing, AWS Regions/AZs, data on RDS/S3/EFS, CloudWatch, backup/restore, load testing, and AWS Budgets**. A sound design must simultaneously be secure, operable, recoverable, and cost-effective.

### Official AWS Documentation for Deployment Reference

- [Amazon ECS concepts and overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html)
- [Amazon ECS clusters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/clusters.html)
- [Task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Creating an ECS task definition](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-task-definition.html)
- [Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_services.html)
- [Amazon ECS service definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html)
- [Service deployments and rolling updates](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html)
- [Amazon ECS service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Task networking with awsvpc](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [Best practices for IAM roles in ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [Amazon ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [Fargate task ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html)
- [AWS CLI ECS command reference](https://docs.aws.amazon.com/cli/latest/reference/ecs/)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/) and [Amazon ECS pricing](https://aws.amazon.com/ecs/pricing/)

**Going to production:** Verify features and limits for your **actual Region/account, OS/platform, instance/capacity provider, and timeframe**; test deployments, failovers, security, and costs in a controlled environment before opening to users.
