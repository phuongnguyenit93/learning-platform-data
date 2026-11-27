# Serverless Architecture and Choosing the Management Level

## Learning Objectives

After this lesson, you can:

- Explain serverless as an operating model where AWS manages most of the execution infrastructure and scaling.
- Distinguish management levels across serverless services, serverless containers, containers on EC2, Kubernetes, and virtual machines.
- Choose AWS Lambda, Amazon ECS with AWS Fargate, Amazon ECS Express Mode, Amazon EKS, or Amazon EC2 based on duration, runtime, state, load, and operational capability.
- Combine API Gateway, Lambda, SQS, SNS, EventBridge, and Step Functions to build synchronous, asynchronous, and event-driven architectures.
- Select S3, DynamoDB, Aurora Serverless, and other data services based on access patterns.
- Design security, IAM permissions, networking, retries, idempotency, concurrency, and resilience.
- Evaluate latency, cold starts, throughput, quotas, observability, and cost.
- Use AWS SAM, AWS CDK, or CloudFormation to deploy repeatable serverless architectures.
- Build criteria for choosing the management level suited to technical requirements and team capability.

## 1. What Problem Does Serverless Solve?

In traditional models, development or operations teams often have to choose servers, configure operating systems, install runtimes, set up autoscaling, monitor capacity, patch security vulnerabilities, and handle hardware failures. When traffic rises, the system needs more capacity. When traffic drops, idle resources can still incur costs.

Serverless is a model in which the cloud provider manages most of the execution infrastructure. Development teams focus on application code, data, events, APIs, and operational policies. Services can automatically provision or reclaim capacity on demand; many services charge based on requests, execution duration, or actual data used.

On AWS, serverless is not just AWS Lambda. A serverless application typically combines multiple services:

- **Compute:** AWS Lambda or Amazon ECS running on AWS Fargate.
- **API:** Amazon API Gateway, AWS AppSync, or Lambda Function URLs.
- **Messaging:** Amazon SQS, Amazon SNS, and Amazon EventBridge.
- **Orchestration:** AWS Step Functions or Lambda Durable Functions.
- **Data:** Amazon S3, Amazon DynamoDB, Amazon Aurora Serverless.
- **Identity:** Amazon Cognito, IAM, and API authentication mechanisms.
- **Observability:** Amazon CloudWatch, AWS X-Ray, and distributed tracing tools.
- **Infrastructure as Code:** AWS Serverless Application Model (SAM), AWS CDK, CloudFormation, or Terraform.

For example, when a customer places an order on a website, API Gateway receives the request and invokes Lambda. Lambda writes the order to DynamoDB, sends a message to SQS, and returns the order ID to the customer. A worker Lambda reads the queue, processes payment, or sends notifications. Step Functions can orchestrate multi-step workflows, while CloudWatch monitors errors and latency.

Importantly, development teams still must design the architecture and manage IAM, data, networking, retries, observability, and costs. Serverless reduces server administration work, but does not eliminate application operational responsibility.

## 2. Serverless Does Not Mean No Servers

Serverless means customers do not directly provision, patch, or operate the underlying servers for that portion of the service. AWS still runs workloads on physical infrastructure or managed execution environments.

Distinguish three concepts:

| Concept | Meaning |
|---|---|
| Serverless | Provider manages execution infrastructure; customer focuses on workload and service configuration |
| Managed service | AWS manages part or most of the service lifecycle; management scope varies by service |
| Fully managed | Provider operates many underlying platform components, but customers still manage their data, permissions, and configurations |

A service can be managed without being fully serverless. For example, Amazon RDS manages the database engine and infrastructure, yet customers still choose instance classes, capacity, storage, and maintenance windows. Amazon Aurora Serverless automatically adjusts compute capacity based on demand and reduces database capacity management work.

Serverless also does not mean:

- No need to design HA or disaster recovery.
- No need to scope IAM permissions.
- No need to monitor errors and latency.
- No limits on execution duration, payload, concurrency, or throughput.
- Always cheaper than continuously running servers.
- Zero lock-in to service APIs and data models.
- Automatic exactly-once guarantees for every event.

## 3. Spectrum: From Low Management Overhead to Deep Control

You can view management level as a spectrum of choices. At the serverless end, AWS manages more of the infrastructure. At the self-managed EC2 end, the operations team exercises deeper control while also bearing more responsibility.

~~~mermaid
flowchart LR
    A["Managed serverless services"] --> B["Lambda / managed data / API"]
    B --> C["Serverless containers"]
    C --> D["ECS or EKS on managed capacity"]
    D --> E["Containers on EC2"]
    E --> F["Self-managed compute"]
~~~

| Management Level | AWS Services / Options | Customer Primarily Manages |
|---|---|---|
| Serverless function | AWS Lambda | Code, runtime settings, IAM, event sources, concurrency |
| Serverless application services | API Gateway, SQS, EventBridge, DynamoDB, S3 | APIs, schemas, event contracts, access policies, data lifecycle |
| Serverless containers | ECS on Fargate | Container images, task definitions, services, networking, scaling policies |
| Container deployment with automated defaults | Amazon ECS Express Mode | Image, roles, app config, and necessary customizations |
| Managed Kubernetes | Amazon EKS | Kubernetes workloads, add-ons, policies; AWS manages the control plane |
| Kubernetes with deeper managed compute | EKS Auto Mode or EKS Fargate | Workloads and Kubernetes configuration; AWS manages more compute capacity depending on mode |
| Containers on EC2 | ECS/EKS with EC2 capacity | Container platform, node lifecycle, OS, patching, scaling |
| Virtual machines | Amazon EC2 | OS, runtime, patching, scaling, capacity, application |

Not every workload has to sit at one end of the spectrum. A single system can use Lambda for small APIs, Fargate for long-running services, DynamoDB for transactional data, and EC2 for a legacy component requiring a custom kernel module.

### 3.1 Management Level and Control

Higher management levels generally reduce infrastructure maintenance, but may constrain runtimes, execution duration, OS access, or networking control. Deeper control generally increases flexibility, while increasing responsibility for patching, upgrades, scaling, and monitoring.

Evaluate the management level per specific workload, not just by the development team's technology preferences.

## 4. Compute Selection Process

Before choosing a service, answer these questions:

1. Is the workload invoked by request, event, schedule, stream, or running continuously?
2. Does a single execution last a few seconds, a few minutes, or many hours?
3. Is it necessary to keep processes, WebSockets, sessions, or state in memory?
4. Can the application be packaged as a container?
5. Does it require OS, kernel, GPU, device, or specialized network control?
6. Is traffic steady or spiky?
7. Does cold start latency affect user experience?
8. Can the workload safely rerun after a timeout or duplicate event?
9. Does the team have experience operating Kubernetes, container platforms, or EC2?
10. How do idle costs, request costs, and data transfer costs compare?

Quick decision table:

| Workload Characteristic | Option to Evaluate First |
|---|---|
| Short processing function, event-driven, variable traffic | AWS Lambda |
| Simple API or webhook, single function | Lambda Function URL or API Gateway HTTP API |
| API needing API keys, usage plans, private endpoints, or WAF integration | API Gateway REST API |
| Stateless HTTP container, wanting quick deployment with sensible defaults | Amazon ECS Express Mode |
| Long-running container, custom runtime, long jobs, or task resource control | Amazon ECS with Fargate |
| Applications needing Kubernetes APIs and CNCF ecosystem | Amazon EKS |
| Needing GPUs, kernel modules, host access, or specialized workloads | EC2 or EKS/ECS on EC2 |
| Multi-step workflow, retries, waiting for approvals, needing execution history | AWS Step Functions |
| Durable workflow written in a function model with checkpoints | Lambda Durable Functions |
| File/object event processing | S3 + EventBridge/Lambda/SQS |
| High event volume requiring buffering | SQS or Kinesis depending on data model |

This is a starting point. Also check service quotas, Region availability, network topology, compliance, and pricing before deciding.

## 5. AWS Lambda: Request- and Event-Driven Compute

AWS Lambda runs code upon receiving invocations from an API, event source, or AWS service. AWS manages execution environments and automatically scales the number of environments based on concurrency.

Lambda fits:

- Backend APIs and microservices with short requests.
- Processing files when S3 receives new objects.
- Event handlers from EventBridge.
- Workers reading messages from SQS.
- Processing records from Kinesis or DynamoDB Streams.
- Scheduled tasks via EventBridge Scheduler.
- Automation glue code between AWS services.

### 5.1 Invocation Modes

There are two common invocation styles (plus event source mapping):

| Type | Behavior | Example |
|---|---|---|
| Synchronous | Caller waits for the function to finish and receives the response | API Gateway invoking Lambda |
| Asynchronous | Lambda places the event in an internal queue and returns acknowledgment before processing | S3 or EventBridge triggering Lambda |
| Event source mapping | Lambda polls a queue/stream, batches records, and invokes the function | SQS, Kinesis, DynamoDB Streams |

Synchronous fits when the caller needs an immediate result. Asynchronous fits when processing can happen later and producer/consumer decoupling is needed. Event source mapping fits queues/streams because Lambda manages polling and batching.

Do not assume every trigger has the same retry behavior. With synchronous invocation, the caller or source service is typically responsible for handling errors. With asynchronous invocation, Lambda performs retries and can send invocation records to destinations. With SQS event source mapping, messages can become visible again after the visibility timeout.

### 5.2 Time and Resource Limits

Lambda Event Functions have a maximum execution duration of 15 minutes per invocation. Memory is configurable from 128 MB to 10,240 MB; CPU is allocated proportionally with memory. Quotas for concurrency, payloads, deployment packages, and network interfaces must be checked by Region and account.

This is the limit for the standard Event Function model. Certain Lambda Managed Instances functions can run up to 90 minutes for eligible asynchronous invocations or event source mappings, excluding Amazon MQ and Amazon DocumentDB. When workloads need longer durations, check the exact compute form factor and invocation type rather than applying one number to all Lambda types.

An invocation exceeding time limits should be broken down, queued, orchestrated via Step Functions/Durable Functions, or moved to suitable compute like Fargate.

### 5.3 Cold Starts and Concurrency

A cold start occurs when Lambda needs to initialize a new execution environment. Initialization time depends on runtime, package size, VPC configuration, initialization code, and dependencies.

Options:

- Reduce package size and initialization time.
- Initialize SDK clients outside the handler to reuse across execution environments.
- Use Provisioned Concurrency when cold starts must be reduced for latency-sensitive traffic.
- Use Reserved Concurrency to cap maximum concurrency and protect databases/downstream systems.
- Separate functions with different load profiles to manage scaling independently.

Reserved Concurrency incurs no extra charge but reserves/caps concurrency for the function. Provisioned Concurrency keeps execution environments pre-initialized and incurs additional charges.

### 5.4 Lambda Durable Functions

Lambda Durable Functions support multi-step workflows with checkpoints, retries, and waits. A durable execution can span up to one year, while each individual code execution still adheres to Lambda's invocation limits. When an execution is interrupted, the runtime can replay from checkpoints and skip already completed steps.

Durable Functions suit long processes such as order processing, awaiting callbacks, polling external services, or human-in-the-loop flows. If you need visual state machine workflows, broad service integrations, execution history, and multi-system orchestration, compare against Step Functions.

### 5.5 Lambda MicroVMs and Session-Based Workloads

Lambda MicroVMs are a different compute form factor from Lambda Event Functions. MicroVMs provide VM-level isolation, can retain state within a session, support a Dockerfile-based programming model, and support longer session durations. They fit isolated code execution environments, notebooks, sandboxes, or CI executors.

Do not equate MicroVMs with function invocations. The two models differ in lifecycle, concurrency, billing, and application packaging. Check current availability, quotas, and limits before selecting them.

## 6. Serverless Containers: Amazon ECS and AWS Fargate

AWS Fargate is a serverless compute engine for containers on Amazon ECS and Amazon EKS. You provide container images, CPU/memory, task definitions, and required configurations; AWS manages the underlying server capacity.

Fargate fits when:

- The application needs to run continuously.
- Processes must live longer than 15 minutes.
- Custom runtimes, OS packages, or multiple processes in a container are needed.
- Batch jobs or long-running workers exist.
- You want container packaging without managing EC2 instances.
- Control over CPU, memory, and task networking is needed.

### 6.1 ECS Tasks and Services

- **Task definition:** describes container images, CPU, memory, environment, ports, logging, IAM roles, and volumes.
- **Task:** a single running instantiation of a task definition.
- **Service:** maintains desired task counts, replaces failed tasks, and integrates with load balancers.
- **Cluster:** a logical grouping to manage ECS services and tasks.

A Fargate task gets its own ENI with a private IP. Security groups attached to the task ENI control traffic. Containers in the same task can communicate over localhost. Tasks need appropriate routes to pull images and access AWS services.

### 6.2 ECS Express Mode

Amazon ECS Express Mode simplifies deploying containerized applications. To create a service, you provide a container image, task execution role, and infrastructure role. Express Mode automatically configures a Fargate-based ECS service, URL, load balancer with TLS, autoscaling, monitoring, and networking.

Express Mode fits stateless web applications and APIs needing public/private HTTPS, rapid prototyping, or self-service models for developer teams. Created resources remain visible and directly manageable in the AWS account.

There is no separate surcharge for Express Mode; customers pay for underlying resources such as Fargate, load balancers, CloudWatch, and data transfer.

### 6.3 AWS App Runner: Customer Onboarding Availability Notice

AWS App Runner stopped accepting new customers as of April 30, 2026. Existing customers can continue using the service and creating new resources. If designing for new customers needing a simple container deployment experience, evaluate Amazon ECS Express Mode.

This is an availability change that directly impacts service selection. Do not default to older App Runner tutorials for new architectures.

## 7. Amazon EKS, EC2, and Choosing Kubernetes

Amazon EKS provides an AWS-managed Kubernetes control plane. Operations teams still need to understand Kubernetes APIs, deployments, services, ingress, resource requests/limits, network policies, and observability.

Choose EKS when:

- Kubernetes is the organization's standard platform.
- Applications depend on CRDs, operators, or the CNCF ecosystem.
- Cross-environment portability is required.
- A platform engineering team has the capability to operate clusters and a developer platform.
- Workloads require Kubernetes orchestration.

EKS Fargate allows running pods on serverless compute without managing worker nodes for eligible pods. EKS Auto Mode further automates compute, storage, and networking infrastructure according to mode capabilities. Check compatibility, DaemonSet requirements, privileged workloads, storage, and scheduling constraints.

### 7.1 When to Use EC2?

EC2 fits when you need:

- Operating system or kernel-level control.
- GPUs/accelerators or specialized hardware.
- Agents, daemons, or drivers incompatible with serverless compute.
- Continuously running workloads with steady utilization where capacity can be optimized.
- Legacy software requiring dedicated server environments.
- Special network, storage, or host-level tuning.

EC2 can be managed with Auto Scaling Groups, Launch Templates, Systems Manager, and Image Builder. High control comes with responsibility for patching, hardening, monitoring, and capacity planning.

### 7.2 Comparing ECS/Fargate, EKS, and EC2

| Criterion | Lambda | ECS + Fargate | EKS | EC2 |
|---|---|---|---|---|
| Deployment unit | Function | Container task/service | Kubernetes pod/workload | VM or container host |
| Continuous process | Not suited for Event Function | Yes | Yes | Yes |
| Single run duration | Up to 15 minutes for Event Function | Can run long-lived | Can run long-lived | By design |
| OS/host management | AWS | AWS manages host | Depends on Fargate/Auto Mode/EC2 | Customer |
| Kubernetes API | No | Not required | Yes | Can self-install |
| Scale-to-zero | Possible with event-driven invocation | Service can set desired count 0 | Depends on workload/autoscaler | Must be configured |
| Infrastructure control | Low | Moderate | High at Kubernetes layer | High |
| Operational effort | Lower | Moderate | Higher if self-managing cluster | High |

## 8. Choosing the API Layer

The API layer is the gateway between clients and backends. Selection depends on protocols, authentication, traffic control, private networking, and API management capabilities.

| Option | Best Suited For |
|---|---|
| API Gateway HTTP API | Lightweight, lower-cost HTTP APIs integrating with Lambda or HTTP backends |
| API Gateway REST API | Rich API management: API keys, usage plans, request validation, per-client throttling, WAF integration, and private endpoints |
| API Gateway WebSocket API | Long-lived bidirectional connections for chat, real-time dashboards, or games |
| Lambda Function URL | Direct HTTPS endpoint for a single Lambda when full API Gateway features are not needed |
| AWS AppSync | GraphQL APIs, subscriptions, and data source integrations |
| Application Load Balancer | HTTP routing to ECS/EKS/EC2 and supports Lambda targets |

HTTP APIs and REST APIs do not have identical feature sets. Choose HTTP API when requirements are lean and advanced management features are unnecessary. Choose REST API when you need features such as API keys, usage plans, request validation, WAF integration, or private API endpoints.

Function URLs are simple and suit webhooks or single-function endpoints. When per-client quotas/throttling, API lifecycles, caching, or multiple routes are needed, API Gateway is usually a better fit.

## 9. Messaging and Event-Driven Architecture

Event-driven architecture (EDA) allows producers to emit events without knowing all consumers. Components can be deployed and scaled independently.

| Service | Model | Use When |
|---|---|---|
| Amazon SQS | Queue | Buffering, load leveling, asynchronous processing |
| Amazon SNS | Pub/sub fan-out | One event must be delivered to multiple subscribers |
| Amazon EventBridge | Event bus and content-based routing | Routing events from AWS services, SaaS, or custom applications |
| Amazon Kinesis Data Streams | Event stream | Continuous high-volume ingestion and processing, ordered per shard |
| Amazon MSK | Managed Kafka | Workloads requiring Kafka ecosystem or protocol compatibility |

### 9.1 Queues with SQS

Queues decouple producers from consumers. When a consumer slows down, messages wait in the queue instead of prolonging the producer's request. SQS Standard provides at-least-once delivery and best-effort ordering. SQS FIFO supports ordering per message group and exactly-once processing semantics within FIFO feature boundaries.

With SQS + Lambda:

- Lambda polls the queue and passes a batch of messages to the function.
- Messages are hidden during the visibility timeout while being processed.
- If the function processes the batch successfully, Lambda deletes the messages.
- If the batch fails, messages can reappear after the visibility timeout.
- Idempotency is required because messages may be processed more than once.
- Use partial batch response to return only failed messages.
- Use a dead-letter queue (DLQ) to isolate unprocessable messages.

AWS recommends setting the queue visibility timeout to at least six times the function timeout. If using a batching window, add that duration as well per current guidance. Configure the redrive policy and `maxReceiveCount` according to application resilience needs.

### 9.2 Fan-Out with SNS

SNS fits when a single event needs multiple independent consumers. For example, after an order is created, SNS can fan out to:

- Payment processing queue.
- Email sending queue.
- Analytics update queue.
- CRM sync queue.

Each subscriber can process independently. Use subscription filter policies to send only relevant messages to each subscriber.

### 9.3 Event Routing with EventBridge

EventBridge fits event buses requiring content-based routing. Producers send events to the bus; rules filter events by source, detail-type, or payload fields and route them to targets like Lambda, Step Functions, SQS, or SNS.

EventBridge is useful when integrating AWS services, SaaS partners, and custom applications. Define clear event contracts so consumers do not depend on internal producer details.

### 9.4 When to Use Streams?

Kinesis Data Streams fits continuous high-throughput data, ordered processing per partition key, or multiple consumers reading the same stream. SQS fits task queues and independent work items better. EventBridge fits business event routing. Do not use a single service for every messaging need.

## 10. Orchestration: Step Functions and Lambda Durable Functions

A business workflow often involves multiple steps: order validation, inventory reservation, payment, shipping, and notification. If one Lambda sequentially invokes many other Lambdas, orchestration code can become hard to read, retry, and recover.

AWS Step Functions models workflows as state machines. Each state can invoke Lambda, integrate directly with AWS services, branch, run in parallel, retry, catch errors, or wait for callbacks.

### 10.1 Standard Workflow

Standard Workflows suit long-running processes requiring execution history and auditability. A single execution can last up to one year. The default execution model is exactly-once at the workflow state level; if Retry is configured, tasks may re-run according to that policy.

Use Standard for:

- Order or payment workflows.
- Human approvals.
- Multi-service sagas.
- Multi-step ETL.
- Workflows requiring detailed execution history.

### 10.2 Express Workflow

Express Workflows suit high-volume, short-duration event processing up to five minutes. Asynchronous Express uses at-least-once; Synchronous Express uses at-most-once. Because duplicate execution can happen in some cases, steps must be idempotent.

Express does not support certain service integration patterns such as `.sync` and `.waitForTaskToken`. Verify callback, history, and execution semantics requirements before selecting it.

### 10.3 Lambda Durable Functions

Durable Functions provide checkpoint, retry, and wait primitives within the Lambda programming model. They can be used when you want to write multi-step logic in code and let the runtime persist progress across invocations. Individual invocations still have their own limits; durable execution manages longer-running progress.

### 10.4 Comparison

| Criterion | Step Functions Standard | Step Functions Express | Lambda Durable Functions |
|---|---|---|---|
| Goal | Long workflows, clear audit trail | High event volume, short duration | Durable multi-step logic in Lambda |
| Duration | Up to 1 year | Up to 5 minutes | Durable execution up to 1 year |
| Semantics | Default exactly-once, configurable retries | Async at-least-once; sync at-most-once | Checkpoint/replay across durable operations |
| Observability | Detailed execution history | CloudWatch Logs and console | Durable execution state/observability |
| Best suited for | Sagas, approvals, business workflows | Ingestion, transformation, high-volume events | Long processes needing checkpoints but preferring code-first |

Do not choose a workflow type based solely on price. Consider semantics, duration, auditability, callbacks, retries, and step idempotency.

## 11. Data Layer in Serverless Architectures

Serverless compute requires data services with matching operational models. Data remains the most critical part to design carefully: consistency, transactions, partition keys, indexing, backups, retention, and access control.

| Service | Data Model | Best Suited For |
|---|---|---|
| Amazon S3 | Object storage | Files, images, videos, static assets, data lakes |
| Amazon DynamoDB | Key-value/document NoSQL | Well-defined access patterns, high throughput, low latency |
| Amazon Aurora Serverless | Relational SQL | Joins, transactions, and SQL compatibility with auto-adjusting capacity |
| Amazon RDS | Managed relational database | Workloads needing traditional engine/instance models |
| Amazon ElastiCache | In-memory cache | Reducing latency and database load |
| Amazon EFS | Shared file system | Containers/functions needing shared POSIX file storage in suitable designs |

### 11.1 DynamoDB

DynamoDB fits when access patterns are known upfront and data can be modeled around partition keys/sort keys. There is no need to manage database servers or connection pools like relational databases.

Design considerations:

- Uniformly distributed partition keys to avoid hot partitions.
- GSIs/LSIs aligned to actual access patterns.
- Conditional writes or transactions when update control is needed.
- TTL for lifecycle-bound data.
- On-demand or provisioned capacity based on traffic profile.
- Backups, point-in-time recovery, and global tables if DR/multi-Region is required.

### 11.2 Aurora Serverless

Aurora Serverless fits relational workloads needing SQL and transactions while wanting capacity to scale with demand. Do not choose it merely because "Serverless" is in the name. Evaluate minimum/maximum ACUs, scaling behavior, connection counts, failover, RDS Proxy, and costs when the database maintains minimum capacity.

### 11.3 S3 and Event Processing

S3 is often the entry point of file processing pipelines. When an object is created, S3 can send events to Lambda, SQS, or EventBridge depending on the architecture. For large files or long processing, enqueue events to buffer work and avoid processing directly inside the upload request.

## 12. Reference Serverless Architectures

### 12.1 Synchronous API

~~~mermaid
flowchart LR
    C["Web / Mobile client"] --> A["API Gateway HTTP API"]
    A --> L["Lambda"]
    L --> D["DynamoDB"]
    L --> R["API response"]
    R --> C
~~~

Use when clients need immediate responses. Keep the request path short. If business processing takes long, return `202 Accepted` with a job ID and process asynchronously.

### 12.2 Asynchronous Order Processing

~~~mermaid
flowchart TD
    C["Client"] --> A["API Gateway"]
    A --> L["Order API Lambda"]
    L --> D["DynamoDB: order state"]
    L --> Q["SQS: order queue"]
    Q --> W["Worker Lambda"]
    W --> S["Step Functions"]
    S --> P["Payment"]
    S --> I["Inventory"]
    S --> N["Notification"]
    S --> D
    Q -. "Repeated failures" .-> DLQ["Dead-letter queue"]
~~~

The API acknowledges order receipt after saving state and enqueuing a message. Workers process payment/inventory and update order status. The queue absorbs traffic bursts; Step Functions orchestrates steps with retries and compensation.

### 12.3 File Processing Pipeline

~~~mermaid
flowchart LR
    U["User uploads"] --> S3["Amazon S3"]
    S3 --> EB["EventBridge / SQS"]
    EB --> L["Lambda metadata validator"]
    L --> Q["SQS processing queue"]
    Q --> F["Fargate or Lambda worker"]
    F --> O["S3 output"]
    F --> M["DynamoDB job metadata"]
~~~

Use Lambda for short validation steps. Use Fargate when files require long processing, large native dependencies, or sustained CPU/memory. Queues regulate processing rate.

### 12.4 Containerized Web Application

~~~mermaid
flowchart TD
    U["Browser / Mobile"] --> ALB["Application Load Balancer"]
    ALB --> ECS["ECS Express Mode / ECS service"]
    ECS --> F["AWS Fargate tasks"]
    F --> DB["Aurora Serverless or DynamoDB"]
    F --> Q["SQS / EventBridge"]
    Q --> W["Lambda / Fargate workers"]
    ECS --> CW["CloudWatch"]
    W --> CW
~~~

Use containers when applications need continuous server processes, existing frameworks, or custom runtimes. ECS Express Mode reduces initial setup; ECS service/Fargate offers finer control over tasks, networking, load balancing, and scaling.

## 13. Synchronous or Asynchronous?

Choose communication style based on client experience, fault tolerance, and coupling between components.

| Criterion | Synchronous | Asynchronous |
|---|---|---|
| Client needs immediate result | Yes | Usually no |
| Producer depends on consumer | Higher | Lower |
| Buffering when consumer is slow | Limited | Can use queues |
| Retries | Handled by caller or source service | Handled by queue/workflow/service |
| User-facing latency | Includes all downstream calls in request path | Can return ACK early |
| Best suited for | Read APIs, short validations | Emails, image processing, order fulfillment |

Do not hold API requests open waiting on multiple downstream systems. For long tasks, return a job ID and provide a status query endpoint or push notification.

## 14. Idempotency, Retries, and Error Handling

In distributed architectures, events can be redelivered due to timeouts, network errors, or retries. Lambda event source mappings process at-least-once; a message may be processed multiple times.

Idempotency ensures repeated processing does not cause unintended side effects.

For example, when receiving an order creation request, use `orderId` or an idempotency key as the business key. Record the key in DynamoDB using a conditional write. If the same key is sent again, return the stored result instead of deducting inventory or charging payment a second time.

Principles:

- Use idempotency keys for APIs with side effects.
- Record processing state before/after side effects according to transaction design.
- Choose retries with exponential backoff and jitter.
- Distinguish transient errors from unrecoverable data errors.
- Use DLQs to isolate poison messages.
- Design controlled redrive processes and replay tooling.
- Log correlation IDs and business IDs.

### 14.1 SQS with Partial Batch Response

When a batch contains multiple messages and only one fails, the entire batch can be returned to the queue by default. Enable `ReportBatchItemFailures` so the function reports failed messages, avoiding reprocessing of already succeeded messages.

The visibility timeout must be long enough for Lambda to process the batch and retry. AWS recommends at least six times the function timeout; if a batching window is used, add the window duration per SQS event source mapping guidance.

### 14.2 Retries Are Not Always Good

Retries can amplify load on an already failing downstream system. When a database is overloaded, aggressive retries can make things worse. Use backoff, concurrency limits, queue buffers, application-layer circuit breakers, and DLQs to keep load under control.

## 15. Security in Serverless Architectures

Serverless does not remove security responsibilities. Every function, task, state machine, and event source needs properly scoped permissions.

### 15.1 IAM Least Privilege

- Each Lambda function has its own execution role scoped to its business function.
- ECS task execution roles handle image pulls, logs, and secret injection; task roles grant permissions to the application itself.
- Step Functions execution roles only allow invoking needed service integrations.
- Restrict `iam:PassRole` to specific roles and services.
- Use resource-level permissions where supported by APIs.
- Avoid sharing a single `AdministratorAccess` role across the entire workload.

### 15.2 API Authorization

API Gateway can integrate IAM authorization, JWT authorizers, Cognito, or Lambda authorizers depending on API type. Do not treat API keys as a user authentication mechanism; API keys primarily serve usage plans and client identification for traffic management.

Use TLS for public APIs, validate inputs, validate payloads, limit request sizes, and configure throttling. For private APIs, design appropriate VPC endpoints, resource policies, and DNS resolution.

### 15.3 Secrets and Sensitive Data

Never hard-code secrets in source code, container images, or event payloads. Use AWS Secrets Manager or Systems Manager Parameter Store. Use KMS encryption and restrict secret read access by execution role.

Do not log access tokens, passwords, payment data, or PII. Define log retention, redaction, and access permissions upfront.

### 15.4 VPC Networking

By default, Lambda runs in an AWS-managed environment and can reach the Internet. When attaching Lambda to an account VPC, the function uses the VPC's networking to access private resources. If Internet access is required, the VPC must have a NAT or appropriate egress path. Attaching Lambda to a public subnet does not automatically grant Internet access.

Fargate tasks have their own ENIs. Security groups, subnets, routes, DNS, NAT, or VPC endpoints are required for services the task needs to reach. Use private subnets and VPC endpoints where appropriate to reduce Internet dependency.

## 16. Reliability and Resilience

A serverless architecture must account for failures in every service and at every boundary.

### 16.1 Failure Isolation

- Use queues to decouple producers from consumers.
- Use explicit timeouts for downstream calls.
- Limit concurrency to protect databases.
- Separate critical paths from analytics or notification paths.
- Use controlled retries and DLQs.
- Avoid having a single function handle too many unrelated business tasks.

### 16.2 Multi-AZ and Multi-Region

Many serverless services are managed by AWS with high availability within a Region. However, multi-AZ service availability does not automatically give your application multi-Region DR.

DR design must define:

- RTO: maximum acceptable time to restore service.
- RPO: maximum acceptable data loss.
- Data replication strategy.
- DNS/API failover.
- Deployment pipelines in the standby Region.
- IAM, secrets, KMS keys, and network dependencies.
- Runbooks and failover/failback drills.

DynamoDB Global Tables, S3 replication, Aurora Global Database, or backup/restore are different options. Choose based on RPO/RTO, consistency, cost, and how the application handles conflicts.

### 16.3 Dependency Management

If an API Lambda depends on a relational database, burst traffic can open too many database connections. Use RDS Proxy, concurrency limits, and caching where appropriate. If consumers are slow, SQS buffers load instead of letting the request path overwhelm the database.

## 17. Performance and Latency

Serverless can scale rapidly, but latency depends on the entire request path.

Factors:

- Lambda cold starts.
- Runtime initialization and package size.
- API Gateway overhead.
- Number of hops between services.
- Database latency and connection management.
- VPC networking and NAT path.
- Serialization, payload size, and batch size.
- Throttling or concurrency limits.
- Provisioned capacity at the data layer.

Ways to improve:

- Reduce unnecessary service calls.
- Reuse SDK clients and connections inside the Lambda execution environment.
- Choose appropriate memory to get the needed CPU.
- Use Provisioned Concurrency when latency SLOs require it.
- Use caching or tailored DynamoDB access patterns.
- Batch events for high throughput.
- Co-locate services in the same Region and minimize cross-Region calls.
- Use response streaming when progressive responses are needed and supported.

Do not optimize cold starts before measuring. For asynchronous background workloads, cold starts may have no meaningful impact on business outcomes.

## 18. Observability for Serverless Applications

A request can pass through API Gateway, Lambda, DynamoDB, SQS, worker Lambda, and Step Functions. Inspecting logs of a single function makes it hard to understand the entire business transaction.

You need:

- Structured logs with timestamp, severity, service, function, request ID, and correlation ID.
- Metrics for request count, error rate, duration, throttles, queue age/depth, and downstream latency.
- Distributed tracing to follow requests across multiple services.
- Dashboards and alarms aligned with SLOs.
- Business metrics such as order success rate or payment failure rate.
- Log retention and access permissions based on data classification.

Amazon CloudWatch provides logs, metrics, alarms, and dashboards. AWS X-Ray or OpenTelemetry can help trace requests across supported components. AWS Lambda Powertools helps with logging, tracing, metrics, and idempotency across runtimes.

Set the correlation ID at the API boundary and propagate it via event payloads/headers. When events traverse queues, log message IDs and business IDs for traceability.

## 19. Deployment and Infrastructure as Code

Serverless applications often comprise many AWS resources. Creating resources manually easily causes drift between dev, test, and production.

| Tool | Best Suited For |
|---|---|
| AWS SAM | Serverless applications using Lambda/API Gateway/DynamoDB/Step Functions |
| AWS CDK | Complex infrastructure, reusable constructs, and programmatic logic |
| CloudFormation | Native IaC and stack management |
| Terraform | Multi-cloud infrastructure management or organizations standardized on HCL |

Pipelines should include these steps:

1. Unit tests and contract tests.
2. Static analysis and dependency scanning.
3. Build artifacts/container images.
4. IaC and policy validation.
5. Deploy to test environment.
6. Integration tests and smoke tests.
7. Canary or linear deployment.
8. Monitor alarms post-deploy.
9. Roll back if error rate or latency exceeds thresholds.

For Lambda, use versions and aliases to isolate `$LATEST` from production traffic. For ECS services, use deployment circuit breakers, health checks, and suitable rolling/canary strategies. For Step Functions, version state machine definitions and verify event contract compatibility.

## 20. Cost: Is Serverless Always Cheaper?

No. Serverless reduces idle capacity costs for many workloads, but total cost also includes requests, duration, memory, API calls, message operations, data transfer, logs, tracing, and database capacity.

| Component | Common Cost Units |
|---|---|
| Lambda | Request count and GB-seconds |
| API Gateway | API call count, data transfer, and related features |
| SQS/SNS/EventBridge | API operations, event volume, and payload size |
| Step Functions | State transitions or executions/duration/memory depending on workflow type |
| Fargate | vCPU, memory, ephemeral storage, and task run duration |
| DynamoDB | Read/write request units or on-demand requests, storage, and backups |
| Aurora Serverless | ACU capacity, storage, I/O, and backups per configuration |
| CloudWatch | Log ingestion/storage, metrics, and queries |
| NAT Gateway | Active hours and data processing |
| Data transfer | Data transfer by direction, Region, and destination |

A Fargate service running 24/7 can cost close to provisioned capacity, even without managing hosts. A Lambda function running for a few milliseconds under low traffic can be cheaper. Conversely, a continuously CPU-heavy workload may fit right-sized containers or EC2 better.

How to evaluate:

1. Estimate request/event volume.
2. Measure duration and memory/CPU.
3. Calculate concurrency and bursts.
4. Estimate queue operations and workflow steps.
5. Calculate database capacity and connection overhead.
6. Calculate logs, traces, and retention.
7. Calculate data transfer, NAT, and cross-AZ/Region traffic.
8. Compare across low, average, and peak traffic.
9. Factor operational and engineering effort into the decision.

## 21. Risks and Limitations of Serverless Architecture

| Risk | Impact | Mitigation |
|---|---|---|
| Vendor lock-in | Dependency on event schemas and managed APIs | Use clear contracts, adapter layers, and IaC |
| Distributed debugging | Hard to trace requests across many services | Correlation IDs, structured logs, and tracing |
| Duplicate events | Repeated side effects | Idempotency keys and conditional writes |
| Retry storms | Downstream overload | Backoff, concurrency limits, queues, and DLQs |
| Cold starts | Increased latency | Provisioned Concurrency or reduced initialization |
| Quota exhaustion | Throttling or deployment failures | Monitor quotas, set alarms, and request increases |
| Database connection surge | Database runs out of connections | RDS Proxy, pooling, and reserved concurrency |
| Event schema drift | Consumers break when producers change payloads | Versioned schemas and backward compatibility |
| Observability cost | Growing log/trace volume | Sampling, retention, and filtering |
| Cost surprises | Bursts or loops generating huge request volumes | Budgets, alarms, reserved concurrency, and kill switches |

An event-driven system needs replay capability designed upfront. Replays must have bounds, idempotency, and input validation. Do not replay an entire production queue without understanding side effects.

## 22. Case Study: Order Intake Architecture for an Online Store

A store needs to accept orders, update inventory, process payments, and send confirmation emails. Traffic surges heavily during promotional campaigns. Customers need fast feedback confirming their order has been received.

### Requirements

- API responds within a few hundred milliseconds under normal conditions.
- Able to absorb burst traffic.
- Prevent creating duplicate orders when clients retry requests.
- Payments and emails can be processed asynchronously.
- Payment failures must retry and have an investigation process.
- Operations teams can inspect the status of individual orders.

### Design

1. API Gateway HTTP API receives the request.
2. Lambda validates the payload and idempotency key.
3. Lambda writes the order record to DynamoDB using a conditional write.
4. Lambda sends an order event to SQS.
5. Worker Lambda reads the queue and starts Step Functions Standard.
6. Step Functions checks inventory, calls the payment service, updates order state, and emits events.
7. SNS/EventBridge distributes events to email and analytics consumers.
8. DLQ retains messages that fail processing after retries.
9. CloudWatch and X-Ray track latency, errors, and correlation IDs.

### Why Not Handle Everything in One Lambda?

If the request stays open until payment, inventory, and email complete, the API becomes dependent on the latency and availability of all downstream services. Queues and workflows decouple order intake from steps that can take longer.

### When to Use Fargate?

If a processing step requires large native binaries/dependencies, sustained CPU, or long runtimes, that worker can move to ECS/Fargate while keeping short event-driven steps on Lambda.

## 23. Lab: Deploying an Order Intake API and Processing via SQS

This lab illustrates a minimal architecture with API Gateway HTTP API, Lambda, DynamoDB, SQS, and a DLQ. Use a sandbox account and test Region. Resource names can vary by environment.

### Step 1: Prepare AWS SAM

Install AWS SAM CLI, AWS CLI, and configure credentials for the lab account. Create a directory:

~~~bash
mkdir serverless-order-lab
cd serverless-order-lab
~~~

### Step 2: Create the Template

Create `template.yaml`:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Minimal serverless order intake and worker

Globals:
  Function:
    Runtime: python3.12
    Timeout: 20
    MemorySize: 256
    Tracing: Active

Resources:
  OrdersTable:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: orderId
          AttributeType: S
      KeySchema:
        - AttributeName: orderId
          KeyType: HASH
      SSESpecification:
        SSEEnabled: true

  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 130
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
        maxReceiveCount: 5

  OrderApiFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: app.create_order
      Environment:
        Variables:
          ORDERS_TABLE: !Ref OrdersTable
          ORDERS_QUEUE_URL: !Ref OrdersQueue
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref OrdersTable
        - SQSSendMessagePolicy:
            QueueName: !GetAtt OrdersQueue.QueueName
      Events:
        CreateOrder:
          Type: HttpApi
          Properties:
            Path: /orders
            Method: POST

  OrderWorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: app.process_order
      Environment:
        Variables:
          ORDERS_TABLE: !Ref OrdersTable
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref OrdersTable
      Events:
        OrdersQueueEvent:
          Type: SQS
          Properties:
            Queue: !GetAtt OrdersQueue.Arn
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 5
            FunctionResponseTypes:
              - ReportBatchItemFailures

Outputs:
  OrdersApiId:
    Description: HTTP API ID; construct the URL with the API ID and Region
    Value: !Ref ServerlessHttpApi
  OrdersTableName:
    Value: !Ref OrdersTable
  OrdersQueueUrl:
    Value: !Ref OrdersQueue
~~~

The queue visibility timeout is 130 seconds, which is greater than six times the 20-second function timeout plus the 5-second batching window. When changing the timeout or batching window, recalculate according to AWS recommendations. The API URL uses HTTPS with the API ID, Region, and `execute-api` domain; use the `OrdersApiId` output to construct the URL for your deployed Region.

### Step 3: Create Sample Handlers

Create `src/app.py`:

~~~python
import json
import os
import uuid
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
orders = dynamodb.Table(os.environ["ORDERS_TABLE"])
queue_url = os.environ["ORDERS_QUEUE_URL"]


def create_order(event, context):
    body = json.loads(event.get("body") or "{}")
    order_id = body.get("orderId") or str(uuid.uuid4())
    amount = body.get("amount")

    if amount is None or amount <= 0:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "amount must be positive"})
        }

    try:
        orders.put_item(
            Item={
                "orderId": order_id,
                "amount": amount,
                "status": "RECEIVED"
            },
            ConditionExpression="attribute_not_exists(orderId)"
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {
                "statusCode": 200,
                "body": json.dumps({"orderId": order_id, "status": "ALREADY_RECEIVED"})
            }
        raise

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"orderId": order_id})
    )

    return {
        "statusCode": 202,
        "body": json.dumps({"orderId": order_id, "status": "RECEIVED"})
    }


def process_order(event, context):
    failures = []

    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            order_id = message["orderId"]

            orders.update_item(
                Key={"orderId": order_id},
                UpdateExpression="SET #status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "PROCESSING"}
            )
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}
~~~

This is a learning handler. In production, add schema validation, authentication, durable idempotency keys, workflow states, error classification, structured logs, and real payment/inventory logic.

For example, writing to DynamoDB and then sending to SQS are two separate operations. If the database write succeeds but sending the message fails, the order can remain in `RECEIVED` state without being processed. Production systems should consider transactional outbox or DynamoDB Streams to emit events from data changes, paired with idempotent consumers and reconciliation.

### Step 4: Build and Deploy

~~~bash
sam build
sam deploy --guided
~~~

Select a stack name, Region, and confirm deployment capabilities. After deploying, retrieve `OrdersApiId` from CloudFormation outputs and construct the API URL for that Region.

### Step 5: Send a Request

~~~bash
curl -X POST "$ORDERS_API_URL/orders" \
  -H "Content-Type: application/json" \
  -d '{"orderId":"order-lab-001","amount":125000}'
~~~

The expected result is HTTP 202 and JSON containing `orderId` with status `RECEIVED`. The worker Lambda reads the message from SQS and updates the status in DynamoDB.

### Step 6: Inspect Errors and DLQ

- View Lambda logs in CloudWatch.
- Check message counts in the SQS queue.
- Send a test message with an invalid schema to observe retries.
- Verify the message moves to the DLQ after multiple receives.
- Try redriving the message after fixing the bug.
- Verify the DynamoDB record reflects the expected status.

### Step 7: Cleanup

~~~bash
sam delete
~~~

Confirm the lab stack is deleted and no log groups, queues, or out-of-stack resources remain unintentionally. Check the billing dashboard to confirm no resources continue generating charges.

## 24. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Lambda timeout | Slow downstream, timeout too low, or deadlock | Inspect duration, traces, and per-dependency timeouts |
| Lambda throttled | Concurrency exceeded quota or reserved concurrency | Check `ConcurrentExecutions`/`Throttles` and downstream limits |
| Rising cold starts | Large package, heavy init code, or new runtime | Measure init duration, trim package, and consider provisioned concurrency |
| API Gateway returns 5xx | Lambda error, integration timeout, or permissions | Check integration, execution role, and Lambda logs |
| SQS messages processed repeatedly | At-least-once delivery or insufficient visibility timeout | Idempotency, visibility timeout, and partial batch response |
| Rising queue age | Slow consumer or low concurrency | Scale workers, tune batch size, and inspect downstream bottlenecks |
| DLQ growing rapidly | Poison messages or bad data | Classify errors, inspect payloads, fix consumer, then redrive |
| VPC Lambda cannot reach Internet | Missing NAT/egress route or security group | Check route tables, NAT, DNS, and egress rules |
| Fargate task cannot pull image | Missing ECR permissions or network path | Check execution role, NAT/VPC endpoints, and security groups |
| Step Functions execution failed | State input/output, IAM, or service integration error | Inspect execution history and error/cause |
| DynamoDB throttling | Hot partition or capacity pattern | Analyze key distribution and access patterns |
| Sudden cost spike | Retry loop, event storm, log volume, or data transfer | Disable faulty trigger, cap concurrency, and check usage metrics |

## 25. Best Practices

### Architecture

- Choose compute based on workload, not trends.
- Prefer managed services for queues, event buses, APIs, and orchestration instead of building your own.
- Separate short request paths from long-running tasks.
- Use versioned event contracts.
- Do not create too many microservices before the domain needs splitting.
- Keep business logic at clear boundaries and avoid arbitrary Lambda chaining.

### Reliability

- Write idempotent functions and consumers.
- Use queues to buffer when downstream systems cannot handle bursts.
- Configure timeouts, retries, DLQs, and partial batch responses.
- Limit concurrency to protect databases and external systems.
- Test failure paths, duplicate events, timeouts, and redrive.
- Define RTO/RPO and rehearse DR.

### Security

- Each function/task/state machine has its own IAM role.
- Use resource policies and appropriate API authorization.
- Store secrets in Secrets Manager/Parameter Store.
- Encrypt data at rest and in transit.
- Use private networking/VPC endpoints when needed.
- Never log sensitive data.
- Manage dependencies and container images through secure pipelines.

### Performance and Cost

- Measure end-to-end latency, not just function duration.
- Optimize package size and initialization.
- Use Provisioned Concurrency only when SLOs require it.
- Choose batch sizes according to processing time and payload.
- Use caching, connection pooling, and database proxies where appropriate.
- Track queue age, concurrency, throttles, error rate, and cost per transaction.
- Account for APIs, messaging, data transfer, logs, NAT, and databases.

### Operations

- Manage infrastructure with SAM/CDK/CloudFormation/Terraform.
- Use multiple environments and deployment strategies with rollback.
- Standardize logs, metrics, traces, and correlation IDs.
- Set alarms on SLOs and business outcomes.
- Track service quotas and request increases before scaling.
- Build runbooks for DLQs, event replay, and downstream outages.

## 26. Practice Exercises

1. What is serverless and which responsibilities still belong to the development team?
2. Why does serverless not mean zero operations?
3. When should you choose Lambda over Fargate?
4. When should you choose ECS/Fargate over Lambda?
5. What is the difference between ECS Express Mode and a manually configured ECS service?
6. Is AWS App Runner still open to new customers in November 2026? What is the alternative?
7. When should you use EKS instead of ECS?
8. When does a workload need EC2?
9. Distinguish API Gateway HTTP API and REST API.
10. When is a Lambda Function URL sufficient?
11. What messaging patterns do SQS, SNS, and EventBridge solve?
12. When should you use Kinesis instead of SQS?
13. How do Standard and Express Step Functions differ in duration and execution semantics?
14. How do Lambda Durable Functions differ from Step Functions?
15. Why must event-driven consumers be idempotent?
16. What factors should determine an SQS visibility timeout?
17. What kind of retries does partial batch response reduce?
18. How does Reserved Concurrency differ from Provisioned Concurrency?
19. Why might a Lambda attached to a public subnet still lack Internet access?
20. When should you use DynamoDB and when should you use Aurora Serverless?
21. Why should an API return a job ID for long-running tasks?
22. Which components beyond compute can increase serverless costs?
23. How do you trace a business transaction across API Gateway, Lambda, and SQS?
24. When should you choose containers instead of splitting an application into many Lambda functions?
25. Why is it important to test DLQ redrive and event replay?

### Suggested Answers

1. AWS manages most of the execution infrastructure; the development team still manages code, data, IAM, APIs, retries, observability, and costs.
2. Because applications still require deployments, security, monitoring, quotas, incident response, and DR.
3. When the workload is short, event-driven, scales by request, and does not need continuous processes.
4. When containers/custom runtimes, long processes, continuous workers, or steady CPU/memory resources are needed.
5. Express Mode automatically configures much of the supporting infrastructure; standard ECS services allow finer-grained control.
6. No. App Runner stopped accepting new customers on April 30, 2026; evaluate ECS Express Mode.
7. When Kubernetes APIs, CRDs, operators, or the CNCF ecosystem are foundational requirements.
8. When OS/kernel/hardware control, GPUs, or specialized legacy workloads are needed.
9. HTTP API is leaner and cheaper; REST API offers API keys, usage plans, request validation, WAF integration, and private endpoints.
10. When only an HTTPS endpoint for a single function is needed without API management features.
11. SQS is a queue, SNS is pub/sub fan-out, and EventBridge is an event bus with content-based routing.
12. When continuous high-throughput stream ingestion and ordered processing per shard/partition are needed.
13. Standard runs up to one year with default exactly-once semantics; Express runs up to five minutes with async at-least-once and sync at-most-once.
14. Durable Functions provide checkpoint/replay in a code-first Lambda model; Step Functions is a state machine orchestrating service integrations.
15. Because events can be redelivered and consumers can run multiple times.
16. Function timeout, batching window, and retry/throttling buffer time.
17. It returns only failed messages instead of reprocessing the entire batch.
18. Reserved caps concurrency and reserves capacity quota; Provisioned keeps execution environments pre-initialized and incurs charges.
19. Lambda needs VPC egress routes/NAT; a public subnet does not automatically assign a public IP or Internet access.
20. DynamoDB for key-value/document workloads with clear access patterns; Aurora Serverless for SQL, joins, and relational transactions.
21. To avoid holding the request open during long-running work and allow clients to poll status.
22. API Gateway, messaging, Step Functions, databases, logs, traces, NAT, and data transfer.
23. Use correlation IDs, structured logs, and distributed tracing.
24. When continuous processes, specialized runtimes, large dependencies, or long-running workloads are required.
25. To verify events can be replayed safely without duplicate side effects and recover properly after failures.

## 27. Interview Questions

### Is serverless suitable for every workload?

No. Workloads needing kernel access, specialized GPUs, continuous processes, or steady utilization may fit containers on EC2 or EC2 directly. Decisions must weigh duration, runtime, state, networking, and operational capability.

### Should every microservice be moved to Lambda?

Not necessarily. A continuously running service with many endpoints and persistent connections may fit ECS/Fargate better. Lambda suits short requests/events. Hybrid models can be used.

### Why does serverless often need queues?

Queues decouple producers from consumers, absorb bursts, support retries, and prevent slow downstream systems from extending the request path.

### How does EventBridge differ from SNS?

SNS focuses on pub/sub fan-out. EventBridge focuses on event buses and content-based routing across AWS services, SaaS, and custom sources. They can be combined in the same architecture.

### When should you choose Step Functions Standard?

When workflows are long-running, require audit history, callbacks/human approvals, or multi-step orchestration with clear semantics.

### Why should exactly-once not be assumed at every boundary?

A workflow can retry tasks, event sources can deliver at-least-once, and downstream calls can time out after performing side effects. Idempotency remains necessary to protect business logic.

### How does Lambda VPC configuration affect networking?

When attached to a VPC, outbound traffic from the function traverses the VPC configuration. NAT or VPC endpoints are required for corresponding destinations; a public subnet does not grant Internet access automatically.

### How do you protect a database from Lambda bursts?

Use Reserved Concurrency to cap the function, RDS Proxy/connection pooling, queue buffering, and backpressure. Monitor database connection counts and throttling.

### Who is ECS Express Mode suited for?

Teams needing to deploy containerized web applications/APIs quickly with Fargate, URLs, TLS load balancers, autoscaling, and monitoring configured with defaults, while still keeping resources visible in their AWS account.

### Should App Runner be the default choice for new projects?

No for new customers after April 30, 2026. The current AWS Decision Guide recommends ECS Express Mode for a similar container experience without managing underlying infrastructure.

## 28. Pre-Production Checklist

### Workload Fit

- [ ] Workload patterns and execution durations have been measured.
- [ ] Compute is chosen based on runtime, state, concurrency, and networking.
- [ ] Lambda, Fargate, ECS Express Mode, EKS, and EC2 have been evaluated against requirements.
- [ ] Quotas and regional service availability have been verified.

### Architecture

- [ ] API request paths do not include unnecessary long-running work.
- [ ] Queues/event buses are used at boundaries needing decoupling.
- [ ] Multi-step workflows have clear retry/catch logic and states.
- [ ] Data stores match access patterns and consistency needs.
- [ ] Event schemas are versioned and backward compatible.

### Security

- [ ] Dedicated IAM roles per workload with least privilege.
- [ ] API authentication/authorization is configured.
- [ ] Secrets are not in source code or logs.
- [ ] Data encryption and key permissions are verified.
- [ ] VPC routes, security groups, and endpoints are accurate.
- [ ] Logs do not contain PII or credentials.

### Reliability and Performance

- [ ] Function/task timeouts are configured.
- [ ] Idempotency is implemented for side effects.
- [ ] Retries, DLQs, redrive, and partial batch responses are tested.
- [ ] Concurrency protects downstream services.
- [ ] Cold starts and provisioned capacity are evaluated against SLOs.
- [ ] RTO/RPO and DR strategy are defined.

### Observability and Cost

- [ ] Structured logs, metrics, traces, and correlation IDs are available.
- [ ] Alarms are based on SLOs and business outcomes.
- [ ] Queue age/depth, throttles, and error rates are monitored.
- [ ] Dashboards and runbooks have been reviewed.
- [ ] Compute, API, messaging, database, logs, NAT, and data transfer costs are estimated.
- [ ] Service quotas and budgets are established.

### Deployment

- [ ] Infrastructure as Code is under version control.
- [ ] Pipelines include tests, security scans, and IaC validation.
- [ ] Suitable canary/linear/rolling deployment strategies are in place.
- [ ] Rollback and event replay plans exist.
- [ ] Test/staging environments exist before production.

## 29. Official References

- [Choosing an AWS serverless service - AWS Decision Guides](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/choosing-aws-serverless-service.html)
- [Choosing a modern application strategy - AWS Decision Guides](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/modern-apps-strategy-on-aws-how-to-choose.html)
- [AWS Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)
- [The pillars of the Well-Architected Framework - Serverless Applications Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/the-pillars-of-the-well-architected-framework.html)
- [Designing Lambda applications](https://docs.aws.amazon.com/lambda/latest/dg/concepts-application-design.html)
- [Lambda invocation methods](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Lambda Durable Functions](https://docs.aws.amazon.com/lambda/latest/dg/durable-functions.html)
- [Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Lambda VPC configuration](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [Enable internet access for VPC-connected Lambda functions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html)
- [Amazon ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)
- [AWS App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)
- [AWS Fargate documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Fargate task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html)
- [Choose between REST APIs and HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Creating and configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Choosing workflow type in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
- [Step Functions service integrations and IAM policies](https://docs.aws.amazon.com/step-functions/latest/dg/service-integration-iam-templates.html)
- [Amazon DynamoDB documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Amazon Aurora Serverless](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless.html)
- [AWS Serverless Application Model](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
