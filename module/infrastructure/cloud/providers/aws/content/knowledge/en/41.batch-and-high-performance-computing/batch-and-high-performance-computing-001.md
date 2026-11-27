# Choosing EC2, ECS, EKS, or AWS Batch for Batch Processing

Batch processing is a way of executing work over a dataset or a group of tasks and terminating upon completion. Examples include nightly data transformations, report generation, image/video processing, Monte Carlo simulations, rendering, pricing calculations, ETL, log analysis, and model training. Workloads may run for a few seconds, several hours, or many days; they may be a single standalone process, thousands of parallel jobs, or a distributed HPC computation across multiple machines.

On AWS, four options are commonly considered: Amazon EC2, Amazon ECS, Amazon EKS, and AWS Batch. These are not four services at the same layer: EC2 provides compute instances; ECS and EKS orchestrate containers; AWS Batch manages queues and schedules batch jobs, then uses compute environments based on EC2, Fargate, ECS Managed Instances, or EKS. Understanding the exact role of each layer helps avoid building a custom scheduler unnecessarily, while also avoiding choosing an overly complex platform for a simple task.

This lesson progresses from workload classification, model comparison, compute and scheduler selection to storage, networking, IAM, retries, Spot, HPC, cost, and operations. The goal is to select an architecture suited to parallelism, job duration, hardware requirements, interruption tolerance, and the organization's operational capabilities.

## 1. Learning Objectives

After this lesson, learners can:

- Distinguish between batch, scheduled tasks, long-running services, stream processing, and HPC.
- Explain the roles of EC2, ECS, EKS, and AWS Batch in a batch processing architecture.
- Choose EC2 directly when full control over the OS, hardware, networking, or a custom scheduler is needed.
- Run one-off and scheduled container tasks using ECS RunTask and EventBridge Scheduler.
- Choose Kubernetes Job/CronJob on EKS and understand how nodes are provisioned with Karpenter or Cluster Autoscaler.
- Design AWS Batch with job definitions, job queues, compute environments, and scheduling policies.
- Choose EC2 On-Demand/Spot, Fargate/Fargate Spot, or ECS Managed Instances for Batch.
- Understand AWS Batch on EKS as an orchestration overlay model and its compute limitations.
- Use retries, timeouts, dependencies, array jobs, fair-share, resource-aware scheduling, and multi-node parallel jobs.
- Design HPC with MPI, EFA, cluster placement groups, GPUs, and shared storage.
- Secure workloads using IAM roles, VPCs, security groups, KMS, and secret management.
- Monitor queues, jobs, pods, tasks, instances, logs, and costs.
- Design idempotent jobs, checkpoints, recovery, backpressure, and resource cleanup procedures.

## 2. Understanding the Workload Before Choosing a Service

Not every workload running in a container is a batch workload. Before choosing a service, identify how work is triggered, how long it runs, whether it must stay running continuously, and whether there are dependencies between jobs.

### 2.1 Workload Types

| Workload Type | Characteristics | Examples |
|---|---|---|
| One-off task | Runs once and terminates | Converting a file, generating an ad-hoc report |
| Scheduled batch | Runs hourly/daily/monthly or on a business schedule | ETL at 02:00, end-of-day aggregation |
| Queue-driven batch | New work is placed in a queue; workers pick it up | Image resizing, invoice processing |
| Large-scale parallel batch | Many independent jobs running concurrently | Monte Carlo, rendering millions of frames |
| Dependency pipeline | Downstream job runs only when upstream job succeeds | Extract → transform → publish |
| Long-running service | Always maintains a number of instances to serve requests | APIs, continuous worker services |
| Stream processing | Processes continuous events, stateful or stateless | Fraud stream, telemetry |
| HPC tightly coupled | Multiple nodes exchange data continuously with low latency | MPI simulation, computational fluid dynamics |

An ECS service maintains a desired count suitable for long-running services. An ECS standalone task suits a process that finishes and stops. AWS Batch adds queues, dependencies, retries, and capacity scheduling for batch workloads. Kubernetes Job/CronJob provides batch primitives on EKS; if multi-tenant queues/fair-share are needed, an additional scheduler or AWS Batch on EKS is required.

### 2.2 Characteristics to Gather

| Attribute | Question |
|---|---|
| Trigger | Invoked by a user, incoming message, schedule, or pipeline? |
| Arrival rate | How many jobs per minute/hour/day? Are there bursts? |
| Parallelism | Is each job independent, or does it need multiple nodes running concurrently? |
| Duration | What is the P50/P95/P99 runtime? |
| Resource profile | How much CPU, RAM, GPU, disk, network, and accelerator is needed? |
| Interruption tolerance | Can it stop mid-run and be retried? |
| Dependency | Is there ordering or conditions between jobs? |
| Latency/SLA | How quickly must a job start, and before what deadline must it finish? |
| Data locality | Is data in S3, EFS, FSx, EBS, or a database? |
| Isolation | Do tenants require separate kernel, node, network, or IAM isolation? |
| Operations | Does the team have skills in EC2, Docker, ECS, Kubernetes, or HPC schedulers? |
| Cost model | Optimize for runtime, utilization, licensing, or operational overhead? |

### 2.3 How Batch and HPC Differ

Batch describes how work is organized: receive input, run, write output, and terminate. HPC describes a class of computation with high performance requirements, typically using many CPUs/GPUs, high memory bandwidth, high-speed networking, or parallel storage. An HPC workload can be submitted as a batch job.

Two common HPC categories:

- **Loosely coupled/embarrassingly parallel:** each task processes an independent portion of data; hundreds or thousands of containers/instances can run in parallel.
- **Tightly coupled:** nodes must exchange data frequently, such as MPI; requires low network latency/high bandwidth and the ability to start multiple nodes simultaneously (gang scheduling).

The first type suits array jobs or queue-driven workers. The second requires multi-node parallel jobs, placement strategies, and potentially EFA.

## 3. Four Architectural Layers: Compute, Orchestration, Scheduling, and Workflow

A batch architecture can be separated into four layers:

    Event / Schedule / API / Message
                 |
          Workflow / Queue
                 |
          Batch Scheduler
                 |
       Container / Process Runtime
                 |
       Compute Capacity (EC2/Fargate)
                 |
        S3 / EFS / FSx / Database

| Layer | Responsibility | Service or Component |
|---|---|---|
| Trigger | Decides when work exists | EventBridge Scheduler, SQS, API, Step Functions |
| Workflow | Coordinates ordering, timeouts, branching, approvals | Step Functions, MWAA, custom orchestrator |
| Batch scheduler | Queues, priorities, dependencies, retries, capacity allocation | AWS Batch or a Kubernetes batch scheduler |
| Container orchestration | Container placement and lifecycle | ECS or Kubernetes on EKS |
| Compute | CPU, RAM, GPU, network, and disk | EC2, Fargate, ECS Managed Instances |
| Storage | Input, output, checkpoints, and shared data | S3, EBS, EFS, FSx for Lustre |

EC2 is the compute substrate. ECS/EKS orchestrate containers. AWS Batch is the batch scheduler and capacity manager. EventBridge Scheduler triggers tasks on a schedule; Step Functions orchestrates multi-step workflows. A single service can integrate multiple layers, but scheduler responsibilities should not be assigned to EC2 or to the ECS service scheduler.

## 4. Comparing EC2, ECS, EKS, and AWS Batch

| Criterion | Direct EC2 | ECS | EKS | AWS Batch |
|---|---|---|---|---|
| Primary role | Virtual machines / compute | AWS-managed container orchestration | Kubernetes managed control plane | Batch job queues, scheduler, and capacity orchestration |
| Execution unit | Process, VM, self-managed container | Task or service | Pod, Job, CronJob | Job, array job, MNP job, or service job |
| Scheduler | Self-built or install Slurm/engine | ECS task placement; RunTask/Service | Kubernetes scheduler/controller | Batch scheduler: FIFO, fair-share, priority, dependency |
| Compute | EC2 On-Demand/Spot | EC2, Fargate, Fargate Spot | EC2 nodes; other node models possible by workload | EC2, Fargate, ECS Managed Instances; EKS compute environment uses EC2 |
| Queue/retry/dependency | Self-built | Integrate SQS/Step Functions or custom logic | Kubernetes Job retry; advanced queuing needs add-on components | Built-in job queues, retries, dependencies, fair-share |
| Autoscaling | Auto Scaling Group/EC2 Fleet | Capacity providers and Service Auto Scaling | Karpenter/Cluster Autoscaler/HPA by layer | Scheduler scales compute environments based on queue demand |
| HPC/MPI | Highest control | Can run tasks, but requires custom multi-node coordination | Can use MPI operator/queue and EC2 nodes | MNP, GPU, EFA on EC2 compute environments |
| Customizability | Very high | Medium to high | Very high, Kubernetes API/ecosystem | Batch-focused; customizable via compute environments/job definitions |
| Operational complexity | Manage OS, patching, scaling, scheduler | Manage cluster/capacity and tasks | Manage Kubernetes, nodes, CNI, add-ons, scheduler | Manage queues, CEs, job definitions, IAM, and underlying capacity policy |
| Best fit | Legacy, custom OS, HPC, specialized schedulers | One-off/scheduled container tasks or simple services | Shared Kubernetes platform, rich policy and ecosystem | Many batch jobs, queues, dependencies, fair-share, retries, and demand-based scaling |

### 4.1 Quick Selection Rules

- Choose direct EC2 when you need full control over the machine, drivers, kernel, AMI, EFA, license daemons, or a custom HPC scheduler.
- Choose ECS when the application is containerized, task volume is moderate, tasks run once or on a schedule, and no specialized queue scheduler is required.
- Choose EKS when the organization already operates Kubernetes, needs to standardize container workloads on the Kubernetes API, or needs Kubernetes operators/CRDs and ecosystem tools.
- Choose AWS Batch when you need queue management, priorities, dependencies, retries, array jobs, multi-node parallel jobs, and automatic compute provisioning based on demand.

AWS Batch does not replace EC2/ECS/EKS. Batch uses those platforms to run jobs. Similarly, the ECS service scheduler does not replace the Batch scheduler: a service maintains a long-running task count; Batch manages finite units of work.

## 5. Direct EC2 for Batch Processing

EC2 fits when applications require deep control over the operating system, devices, filesystems, networking, daemons, or commercial software. However, EC2 only provides machines; operators must solve job intake, queuing, capacity provisioning, retries, checkpointing, cleanup, and observability.

### 5.1 Simple Architecture

    EventBridge / SQS
          |
       Worker ASG
          |
       EC2 instance
          |
       Process / script / container
          |
       S3 / EFS / FSx / database

A worker can poll SQS, receive a message, download input, run a process, write output, and acknowledge the message. An Auto Scaling Group scales the number of workers up/down based on queue depth or custom metrics. You must handle visibility timeouts, duplicate messages, DLQs, graceful shutdown, and idempotency.

### 5.2 When to Use Direct EC2

- Software requires a custom AMI, kernel modules, drivers, or OS packages.
- Requires GPUs, EFA, local NVMe instance store, or specialized hardware.
- Requires license daemons, long-running processes, or multiple processes sharing memory on the same host.
- Requires an HPC scheduler such as Slurm via AWS ParallelCluster or an internal system.
- Requires placement groups and deep network/storage configuration.
- The team has sufficient capability to manage patching, images, capacity, failures, and lifecycle.

### 5.3 Choosing an Instance Family

| Workload Type | Instances/Resources to Benchmark |
|---|---|
| CPU-bound | Compute optimized (C) |
| Memory-bound | Memory optimized (R/X/U as needed) |
| General-purpose | M |
| GPU training/inference/rendering | Accelerated computing (G/P/Trn/Inf depending on framework) |
| High network throughput | Network-optimized, EFA if MPI/tightly coupled |
| High local I/O | Instance store/NVMe or IOPS/throughput-optimized EBS |

Do not choose by vCPU alone. Measure CPU utilization, memory pressure, page cache, disk queue, network, GPU utilization, runtime, and cost per job.

### 5.4 What Is Needed to Build Your Own Scheduler?

If running on EC2 and building your own batch platform, you need at minimum:

- A job registry and states: QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED.
- A queue and lease/visibility timeout mechanism.
- Resource reservation to avoid overcommitting CPU/RAM/GPU.
- Worker heartbeats and lost-node detection.
- Retry policies, backoff, and dead-letter queues.
- Idempotency keys and output commit mechanisms.
- Priority/fair-share so one tenant cannot consume all capacity.
- Scaling policies and capacity warm-up.
- Auditing, metrics, logs, and cost allocation.
- Cleanup processes for instances, volumes, ENIs, artifacts, and temporary data.

If you have to implement most of this list yourself, evaluate AWS Batch before investing in a custom scheduler.

### 5.5 Spot on EC2

EC2 Spot leverages unused capacity and can significantly reduce costs. AWS can reclaim Spot instances; an interruption notice typically provides about two minutes before stop/terminate, though the event is delivered on a best-effort basis.

Design interruption-tolerant workloads:

- Save checkpoints frequently to S3/EFS/FSx or durable storage.
- Split jobs into retryable chunks.
- Record progress by task ID/partition.
- Commit output by run ID; never overwrite incomplete results.
- Listen to EventBridge interruption/rebalance events.
- Diversify instance types and Availability Zones where possible.
- Use On-Demand for parts requiring stability and Spot for retryable parts.

Do not use Spot for unrecoverable processes or ones with non-idempotent side effects without protective mechanisms.

## 6. Amazon ECS for One-Off and Scheduled Container Tasks

Amazon ECS is an AWS-managed container orchestration service. An ECS task is a single execution of a task definition; an ECS service maintains a desired number of tasks. For simple batch workloads, use standalone tasks via RunTask or EventBridge Scheduler to run tasks on a schedule.

### 6.1 Task Definition, Task, and Service

| Concept | Role |
|---|---|
| Task definition | Blueprint: image, command, CPU, memory, volumes, ports, roles, and logging |
| Task | A single instantiation of a task definition |
| Standalone task | Runs independently and stops when work finishes |
| ECS service | Maintains desired count and replaces stopped/failed tasks |
| Cluster | Logical grouping containing tasks/services and capacity |
| Capacity provider | Links ECS with EC2 Auto Scaling or Fargate/Fargate Spot |

Do not use an ECS service just to run a job and exit. The service scheduler is designed to maintain a desired count; if a task exits after completing work, the service may launch a replacement task and loop. For one-off batch jobs, use RunTask.

### 6.2 ECS Standalone Task

Execution flow:

    Event / SQS / API / EventBridge Scheduler
                   |
                RunTask
                   |
             ECS cluster
                   |
          Capacity provider
             /          \
          Fargate       EC2
             \          /
              ECS task
                  |
          Application exits
                  |
             Task STOPPED

ECS placement is based on CPU/memory in the task definition, placement constraints, and strategies. With Fargate, AWS manages compute for the task. With EC2, you can register instances manually or use capacity providers with cluster auto scaling to add/remove capacity.

### 6.3 Running on a Schedule with EventBridge Scheduler

EventBridge Scheduler supports one-time, rate-based, and cron-based schedules with timezone selection. Scheduler can invoke ECS RunTask as a target. A schedule should configure:

- Target cluster and task definition revision.
- Launch type/capacity provider strategy.
- Network configuration and subnets/security groups.
- Task count and container overrides.
- Scheduler execution role to invoke RunTask.
- Retry policy, maximum event age, and dead-letter queue if needed.
- Flexible time window if exact-second execution is not required.

If a task depends on input data or requires multiple steps, use Step Functions or a workflow engine to manage state and errors. EventBridge Scheduler only issues scheduled invocations; it does not provide a full job dependency graph and fair-share queues like AWS Batch.

### 6.4 Capacity Providers

ECS supports common capacity providers:

- **Fargate:** no EC2 instance management; tasks request CPU/memory per Fargate configurations.
- **Fargate Spot:** lower-cost capacity that can be interrupted; suited for retryable batch jobs.
- **EC2 capacity provider:** links an Auto Scaling Group and supports cluster auto scaling.

A capacity provider strategy can combine On-Demand and Spot using base/weight. Choose a strategy so critical work has stable capacity while interruption-tolerant work leverages Spot.

### 6.5 Task Role and Task Execution Role

The two roles serve different purposes:

- **Task execution role:** used by the ECS/Fargate agent to pull images from ECR, write logs, and retrieve secrets configured in the task definition.
- **Task role:** credentials provided to code inside the container to call S3, DynamoDB, SQS, or other AWS services.

Do not grant application permissions to the execution role unnecessarily. Each workload should have its own task role following least privilege. If tasks run in private subnets, configure VPC endpoints or NAT to reach ECR, CloudWatch, S3, and required services.

### 6.6 ECS Does Not Automatically Replace Standalone Tasks

The ECS service scheduler replaces failed tasks to maintain a desired count. However, a standalone task launched via RunTask or EventBridge Scheduler is not automatically replaced by the service scheduler when it fails. If retries are needed, a workflow must re-invoke RunTask or use AWS Batch.

### 6.7 When ECS Is a Good Fit

- A single task or a few groups of tasks running on a schedule.
- Workloads that do not require complex queues or fair-share.
- Task definitions and an ECS cluster/capacity provider already exist.
- Fargate can be used to reduce compute operational overhead.
- EventBridge Scheduler or Step Functions can orchestrate retries/dependencies.

Once you need to manage thousands of jobs, priorities, queues, dependencies, and exit-reason-based retries, AWS Batch is usually a better fit.

## 7. Amazon EKS with Kubernetes Job and CronJob

Amazon EKS provides a managed Kubernetes control plane. Kubernetes has built-in batch primitives: a Job runs one or more Pods until a target number of completions is reached; a CronJob creates Jobs on a schedule.

### 7.1 Kubernetes Job

A Job manages Pods to execute finite work. Common fields:

| Field | Meaning |
|---|---|
| completions | Number of successful completions required |
| parallelism | Maximum number of Pods running concurrently |
| backoffLimit | Number of retries when Pods fail |
| activeDeadlineSeconds | Time limit for the Job to remain active |
| ttlSecondsAfterFinished | Retention time after completion before cleanup |
| restartPolicy | Typically Never or OnFailure depending on design |

The Kubernetes Job controller watches Pods and creates replacements per policy. This does not mean Jobs include global queues, fair-share, or business quota management across multiple teams.

### 7.2 Kubernetes Job Example

    apiVersion: batch/v1
    kind: Job
    metadata:
      name: image-resize
      namespace: batch
    spec:
      completions: 1
      parallelism: 1
      backoffLimit: 3
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: worker
              image: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/image-worker:1.4.2
              command: ["python", "resize.py"]
              resources:
                requests:
                  cpu: "1"
                  memory: "2Gi"
                limits:
                  cpu: "2"
                  memory: "4Gi"

This manifest is a starting example; image, namespace, resource requests/limits, service account, and volumes must be tailored to the cluster. Containers should handle termination signals and write idempotent output.

### 7.3 Kubernetes CronJob

A CronJob creates Jobs on a cron schedule. Important fields:

- schedule: cron expression.
- timeZone: timezone for the schedule if supported by the Kubernetes version.
- concurrencyPolicy: Allow, Forbid, or Replace.
- startingDeadlineSeconds: maximum allowed delay to start a missed run.
- successfulJobsHistoryLimit/failedJobsHistoryLimit: number of Jobs to retain.
- suspend: pause the schedule.

If a previous job may run longer than the interval between schedules, choose concurrencyPolicy deliberately. Allow permits overlapping runs; Forbid skips the new run while the prior one is still active; Replace terminates the old job to create a new one. Do not use Replace if the job cannot tolerate termination.

### 7.4 Scheduling and Autoscaling

The Kubernetes scheduler places Pods onto nodes based on requests, affinity/anti-affinity, taints/tolerations, topology spread, and other constraints. To scale node capacity for pending Pods, you can use Karpenter or Cluster Autoscaler.

Different scaling layers:

- HPA/KEDA adjusts Pod counts based on metrics or events.
- Karpenter/Cluster Autoscaler adjusts node capacity.
- Kubernetes Job/CronJob controls completion counts and parallel Pods.
- Additional queues/schedulers provide fairness, quotas, and priority at the workload level.

Do not increase parallelism without checking downstream capacity, database connections, API rate limits, and S3 request patterns. Excessive job fan-out can overwhelm downstream systems.

### 7.5 IAM for Pods

Applications inside Pods need IAM roles via EKS Pod Identity or IAM Roles for Service Accounts (IRSA). Bind roles to Kubernetes service accounts and scope permissions by namespace/workload. Do not attach broad permissions to the node instance role and let every Pod inherit them.

### 7.6 When to Choose Native EKS Job/CronJob

- The organization already has a Kubernetes platform and operations team.
- Needs Kubernetes APIs, admission policies, operators, service mesh, or ecosystem tools.
- Jobs can be managed via manifests/GitOps.
- Needs customized pod scheduling, sidecars, init containers, volumes, and network policies.
- Already has an appropriate queue/scheduler layer, or workloads do not need advanced queuing.

If the goal is simply running a few batch jobs with no Kubernetes requirement, operating an EKS cluster may introduce more overhead than value.

## 8. AWS Batch: Managed Batch Scheduler

AWS Batch is a service that manages scheduling, queuing, and compute provisioning for batch jobs. Users describe jobs and resource requirements; Batch finds a suitable compute environment, waits for capacity if needed, runs containers, and tracks job states.

### 8.1 Four Core Components

| Component | Responsibility |
|---|---|
| Job definition | Container/process blueprint: image, command, vCPU, memory, GPU, roles, volumes, logging, and retry/timeout |
| Job queue | Where jobs wait to be evaluated and scheduled by the scheduler |
| Compute environment (CE) | Compute resources to run jobs; managed or unmanaged |
| Job | A single execution submitted to a queue |

Basic flow:

    Producer / Scheduler / Workflow
                  |
               SubmitJob
                  |
               Job queue
                  |
            Batch scheduler
                  |
          Compute environment
           /              \
       ECS platform       EKS platform
       EC2/Fargate/        EC2 nodes
       ECS Managed         and Pods
       Instances
           \              /
             Container job
                  |
              S3 / DB

A queue can be associated with one or more compute environments. The scheduler evaluates CEs in order within the queue; if the first CE is invalid or lacks matching resource types, it can try the next CE per configuration.

### 8.2 Managed and Unmanaged Compute Environments

**Managed compute environment:** AWS Batch manages capacity according to configured min/desired/max vCPUs, instance types, Spot/On-Demand, or Fargate. This is the typical choice because it reduces provisioning and scaling work.

**Unmanaged compute environment:** users manage compute instances and capacity themselves. Use when specialized configurations, dedicated hosts, storage, or infrastructure management outside the managed model are required. Operators must ensure appropriate ECS agent/node capacity and lifecycle.

### 8.3 Queues, Priority, and CE Order

An organization can separate queues by SLA:

| Queue | Priority | Compute Environment | Workload |
|---|---|---|---|
| critical | High | EC2 On-Demand | Jobs that must meet strict deadlines |
| standard | Medium | EC2 On-Demand + Spot | Routine ETL |
| flexible | Low | EC2 Spot or Flex capacity | Simulations that can wait |
| gpu | Per policy | GPU EC2 | Training/rendering |

Queue priority and CE order are two distinct configurations. Queue priority determines which queue the scheduler evaluates first; CE order determines which environment is tried first within a queue.

### 8.4 FIFO and Fair-Share Scheduling

Without a scheduling policy attached, the Batch scheduler defaults to FIFO. FIFO is simple, but large jobs at the head of a queue can delay smaller jobs behind them (head-of-line blocking).

Fair-share scheduling uses share identifiers to allocate capacity across tenants/workloads. For example:

- Team A submits jobs continuously.
- Team B only submits jobs at the end of the day.
- Fair-share prevents Team A from monopolizing all capacity and starving Team B.

Fair-share does not replace queue priority or job dependencies. Choose share decay/window and weights based on fairness goals, SLAs, and agreed utilization targets.

### 8.5 Resource-Aware Scheduling

Batch can manage consumable resources beyond CPU/RAM, such as license tokens, database connection budgets, or API quotas. Jobs declare the required quantity of resources; the scheduler runs jobs only when those consumable resources are available. This prevents launching jobs when compute is free but downstream services have no remaining capacity.

## 9. AWS Batch Compute Environments

AWS Batch currently supports compute environments based on Amazon ECS or Amazon EKS. With ECS orchestration, compute types include EC2, Fargate, Fargate Spot, and ECS Managed Instances. With EKS orchestration, compute environments use EC2 On-Demand/Spot nodes.

### 9.1 ECS Compute Environment: EC2

An EC2 compute environment allows choosing:

- Allowed instance types or instance families.
- Minimum, desired, and maximum vCPUs.
- On-Demand or Spot.
- Allocation strategy.
- Subnets and security groups.
- Launch templates, AMIs, and storage configurations as supported.
- Placement groups, instance profiles, and service roles.

AWS Batch manages EC2 instances in an ECS cluster for a managed CE. The compute environment can scale down to minimum vCPUs after jobs finish; if minvCpus is greater than 0, warm capacity reduces startup latency but still incurs cost.

### 9.2 Allocation Strategy

Allocation strategy determines how Batch selects instance types/pools when additional capacity is needed.

| Strategy | Purpose | When to Consider |
|---|---|---|
| BEST_FIT | Selects a fitting type, prioritizing lowest cost | Want low cost and can tolerate waiting for capacity |
| BEST_FIT_PROGRESSIVE | Selects a type that fits the job, expanding to others as needed | On-Demand CE needing throughput and capacity acquisition |
| BEST_FIT_PROGRESSIVE_ORDERED | Prioritizes the declared instanceTypes order | Need control over instance type ordering |
| SPOT_CAPACITY_OPTIMIZED | Prioritizes Spot pools with deep capacity | Reduce interruption probability |
| SPOT_PRICE_CAPACITY_OPTIMIZED | Balances price and capacity availability | General recommendation for many Spot workloads |
| SPOT_CAPACITY_OPTIMIZED_PRIORITIZED | Prioritizes capacity while respecting instance order on a best-effort basis | Need instance type preference while prioritizing allocation likelihood |

Strategies do not apply identically across all compute types. Fargate and ECS Managed Instances do not use allocationStrategy like EC2. With Spot, diversify instance types and AZs if the workload allows. With some strategies, Batch may exceed maxvCpus by up to one instance to fulfill capacity; review specific behavior before setting hard budget limits.

### 9.3 Fargate and Fargate Spot

Fargate suits container jobs that do not need EC2 instance management, custom AMIs, GPUs, or host-level devices. AWS Batch can create a Fargate compute environment and provision task resources per job.

Limits to note per current documentation:

- Fargate jobs have vCPU/memory limits and supported size combinations; the highest documented size is 32 vCPU and 244 GiB memory.
- GPUs and Elastic Fabric Adapter are not supported.
- EC2 parameters such as instanceTypes, launchTemplate, placementGroup, and minvCpus do not apply.
- Jobs should not be expected to run longer than 14 days on Fargate.
- Fargate Spot can be interrupted; Windows containers are not supported on Fargate Spot.

Fargate is easy to operate for small/medium jobs needing task runtime isolation and fast startup. If you need GPUs, privileged containers, host volumes/devices, more than 32 vCPU, or more than 244 GiB memory, evaluate ECS Managed Instances or EC2.

### 9.4 ECS Managed Instances

Amazon ECS Managed Instances combines a managed operational experience with the compute flexibility of EC2. ECS manages provisioning, scaling, patching, and termination of instances based on job resource requirements. In AWS Batch, this compute environment type is used only with ECS orchestration, not for EKS compute environments.

Choose ECS Managed Instances when jobs need:

- GPUs or specific instance families.
- More CPU/RAM than Fargate limits.
- Privileged access, host-level devices, or volumes.
- ARM64/Graviton instances or specific x86/ARM configurations.
- On-Demand Capacity Reservations, Reserved Instances, or EC2 Instance Savings Plans.
- Flexible vCPU/memory combinations not offered by Fargate.

Fargate remains simpler when jobs fit within its resource limits and do not need GPU/host access. An EC2 managed compute environment fits when you need MNP, custom AMIs/launch templates, fine-grained allocation strategies, or a minvCpus warm pool.

### 9.5 AWS Batch Compute Environment on EKS

AWS Batch can orchestrate jobs on an EKS cluster using an overlay model:

1. Create or select an EKS cluster.
2. Grant Kubernetes RBAC permissions for Batch to access the API server.
3. Connect the cluster and create an EKS compute environment.
4. Create a job queue linked to the CE.
5. Register a job definition based on a pod specification.
6. Submit jobs via the AWS Batch API.

Batch calls the Kubernetes API to create, monitor, and delete Pods/nodes. No Batch operator or custom resource needs to be installed in the cluster. Batch manages the lifecycle of nodes it creates, applying labels/taints so other workloads do not schedule Pods onto them (an exception may be DaemonSets configured to target those nodes). Batch does not place jobs onto nodes managed by other systems.

AWS Batch EKS compute environments use EC2 On-Demand/Spot; Fargate is not supported. When the queue is empty, Batch can scale nodes down to min capacity, which defaults to zero unless set otherwise. Verify EKS Kubernetes version, access entries/authentication, RBAC, node IAM, subnet IPs, and capacity.

### 9.6 Batch on EKS vs. Plain Kubernetes Jobs?

| Need | Plain EKS Job/CronJob | AWS Batch on EKS |
|---|---|---|
| Kubernetes manifest/GitOps | Native | Uses Batch API and job definitions |
| Queues and priority | Must build or install scheduler | Built-in job queues and priority |
| Job dependencies | Separate workflow/scheduler | Built-in job dependencies |
| Retries | Job controller and backoffLimit | Batch retry strategies and exit rules |
| Fair-share | Additional scheduler | Scheduling policies |
| Node scaling | Karpenter/Cluster Autoscaler | Batch manages nodes dedicated to the Batch CE |
| Kubernetes customizations | Full Kubernetes control | Batch manages job/node lifecycle within the CE scope |
| Best fit | Multi-purpose Kubernetes platform, native K8s workloads | Batch-centric platform needing queues, retries, and capacity management |

If the team already runs a queue such as Kueue/Volcano or a custom scheduling system, compare capabilities and operations before adding Batch. Avoid having two schedulers control the same capacity layer.

## 10. Job Definitions and Job Lifecycle in AWS Batch

### 10.1 Job Definition

A job definition describes how to run a container:

- Container image and registry.
- Command/entrypoint.
- vCPU, memory, and GPU resource requirements.
- Execution role and job role.
- Environment variables and parameters.
- Volumes/mount points.
- Logging configuration.
- Retry strategy and timeout.
- Network/security options depending on compute platform.

Job definitions are versioned with revisions. Version images using immutable tags or digests, align job definition revisions with releases, and avoid the latest tag in production.

### 10.2 Job Role and Execution Role

- **Job role:** IAM role assumed by code inside the container to access S3, DynamoDB, SQS, KMS, or AWS APIs.
- **Execution role:** permissions for the ECS/Fargate agent or runtime to pull images, write logs, and retrieve configured secrets.
- **Batch service-linked role:** allows AWS Batch to manage compute resources and integrate with related services.

With an EKS compute environment, additional IAM role/Pod identity or service account configuration appropriate to the cluster is required. Do not confuse the job submitter's permissions with the permissions available to the container runtime.

### 10.3 Submitting a Job

CLI example:

    aws batch submit-job \
      --job-name orders-transform-20261120 \
      --job-queue batch-standard \
      --job-definition orders-transform:4 \
      --parameters input=s3://company-data/raw/orders/ \
      --container-overrides '{"command":["python","main.py","--mode","daily"]}' \
      --region ap-southeast-1

This illustrative command requires an existing job queue, job definition, and registered image. Parameters can be referenced in the command/job definition; container overrides modify the configuration for a single submission. Never pass secrets directly on the command line or in environment variables when Secrets Manager/secret injection can be used.

### 10.4 Job States

A job typically transitions through these states:

    SUBMITTED
        |
    PENDING (waiting on dependencies/resources)
        |
    RUNNABLE (eligible, waiting for compute)
        |
    STARTING
        |
    RUNNING
       / \
 SUCCEEDED FAILED

A job may stay in RUNNABLE for a long time if the CE is invalid, capacity is insufficient, vCPU quotas are reached, instance types are unavailable, job resources do not match, or the queue is blocked. Long RUNNABLE time is not necessarily a container code error; check the scheduler/CE/compute quotas.

### 10.5 Dependencies

SubmitJob can declare dependencies on other jobs. A dependent job transitions to RUNNABLE only after its dependencies succeed; if a dependency fails, the dependent job may also transition to FAILED.

A job can depend on up to 20 jobs under current quotas. For complex pipelines, use Step Functions, MWAA, or an appropriate orchestrator to manage branches, conditions, compensation, and timeouts.

### 10.6 Retry Strategy

AWS Batch supports 1 to 10 attempts. You can use evaluateOnExit to decide whether to retry or exit based on exit code, reason, or status reason.

Example policy:

| Scenario | Action |
|---|---|
| Exit code 137/OOM | Increase memory or route to another queue; do not retry infinitely |
| Exit code 1 due to bad input | EXIT, move record to quarantine |
| Transient throttling/network error | RETRY with backoff |
| EC2 instance failure/Spot interruption | RETRY if job is idempotent/checkpointed |
| AccessDenied/KMS deny | EXIT and fix IAM/policy |
| Missing dependency | Do not submit downstream job until data is ready |

Retries create additional attempts; the application must tolerate re-execution. Do not rely on retries to mask data errors or duplicate side effects.

### 10.7 Timeout and Cancellation

Job timeout limits how long an attempt can run. If an attempt is terminated due to timeout, Batch does not automatically retry that attempt per documented behavior; other failures may be retried if configured. Fargate jobs should not be expected to run longer than 14 days.

When a job is cancelled, the container may receive a termination signal before being stopped. Handle SIGTERM, flush outputs/checkpoints, and release locks/licenses. Do not assume cleanup code always runs if the process is terminated abruptly.

## 11. Array Jobs, GPUs, and Multi-Node Parallel Jobs

### 11.1 Array Jobs

An array job shares a job definition/parameters and creates multiple child jobs that can run in parallel. Array sizes range from 2 to 10,000 child jobs.

Example processing 5,000 files:

    aws batch submit-job \
      --job-name resize-campaign \
      --job-queue batch-standard \
      --job-definition resize-image:2 \
      --array-properties size=5000 \
      --region ap-southeast-1

Inside the container, the AWS_BATCH_JOB_ARRAY_INDEX environment variable identifies the child job index. The application uses this index to select the corresponding partition/file/input. Never let all child jobs read and write to the same output path.

Array jobs suit:

- Monte Carlo parameter sweeps.
- Frame rendering.
- Partitioned ETL.
- Batch document embedding generation.
- Independent image/video processing.

### 11.2 Dependencies Between Array Jobs

Batch supports:

- SEQUENTIAL: child indices run sequentially in order.
- N_TO_N: a child index of the downstream job waits for the corresponding child index of the upstream job to complete.

If the parent array job is cancelled, child jobs may be cancelled as well. If a child job fails, the parent may finish FAILED after the children complete. Design an aggregation/finalization job to verify all partitions before publishing.

### 11.3 GPU Scheduling

A job definition can request the number and type of accelerators. Batch uses this requirement to select matching EC2 accelerated instances and allocate GPUs to containers. Conditions:

- The compute environment must include appropriate GPU instance families.
- The image needs CUDA/drivers/libraries compatible with the host/runtime.
- Resource requests must reflect actual GPU counts.
- Monitor GPU utilization, memory, driver errors, and queue wait times.
- Do not allocate GPUs to CPU-only jobs because GPU instances are expensive.

Fargate does not provide GPUs; choose EC2 or ECS Managed Instances depending on compute environment support.

### 11.4 Multi-Node Parallel Jobs (MNP)

MNP enables a single job to span multiple EC2 instances. This is gang scheduling: nodes are provisioned together for the same job so distributed applications can communicate with each other.

An MNP job has:

- A main node that starts first.
- Child nodes that start after the main node.
- Node groups that can have different container/resource configurations.
- Job completion determined by the main node's state; child nodes are then stopped.
- Single-tenant MNP nodes: only one job container runs per EC2 instance.

MNP suits MPI, distributed training, or frameworks supporting IP-based inter-node communication. MNP requires an EC2 compute environment; Fargate is not supported.

### 11.5 MNP Failure Semantics

If retries are enabled, a main node failure triggers a new attempt. Child node failures do not automatically trigger another attempt in the same way; the application must detect communication failures and report an appropriate status to the main node. Overall job status is determined from the main node.

Do not inspect only a single child process's exit code. Log node index, host, rank, rendezvous endpoint, and network errors for investigation.

## 12. HPC: MPI, EFA, Placement Groups, and Shared Storage

Tightly coupled HPC requires multiple nodes to exchange data frequently. Performance depends on network latency/bandwidth, synchronization, topology, CPU/GPU, and data read/write throughput. A job can use many instances and still run slowly if networking or storage is a bottleneck.

### 12.1 AWS Batch MNP with MPI

An MNP job typically launches a main node and multiple child nodes. The application uses MPI or a similar framework to initialize ranks, discover node addresses, and distribute data.

Design considerations:

- Choose EC2 instance types compatible with the workload and network.
- Use a cluster placement group when nodes must be placed close together in the same AZ.
- Open security groups for internal communication across required nodes/ports.
- Configure hostnames, DNS, MPI transport, and rendezvous.
- Choose shared storage or appropriate input/output partitioning.
- Measure scaling efficiency as node count increases.

### 12.2 Elastic Fabric Adapter (EFA)

EFA is a network device supporting HPC applications with high communication demands. AWS Batch supports EFA-enabled jobs when conditions are met:

- The EC2 instance type supports EFA.
- The AMI and operating system have compatible EFA drivers.
- Instances using EFA are in the same cluster placement group.
- The security group allows inbound/outbound traffic between instances within that same security group.
- The job definition passes the EFA device into the container via hostPath /dev/infiniband/uverbs0; if permissions are declared, READ, WRITE, and MKNOD are required per connector/runtime requirements.

EFA requires coordinated configuration across instances, AMI, security group, placement group, and container. Simply picking an EFA-capable instance is not enough for an MPI application to use EFA.

### 12.3 Placement Groups

| Strategy | Purpose | Workload |
|---|---|---|
| Cluster | Places instances close together in one AZ to reduce latency/increase throughput | Tightly coupled HPC, MPI |
| Partition | Separates instance groups into distinct hardware partitions | Distributed systems needing reduced correlated failures |
| Spread | Distributes a small group of instances across distinct hardware | Workloads needing reduced correlated failures |

Cluster placement groups can hit capacity limits when launching many instances simultaneously. Benchmark and validate allocation feasibility in the target Region/AZ before committing to production SLAs. Placement groups do not guarantee every instance type is always available.

### 12.4 Storage for HPC

| Storage | Pattern |
|---|---|
| Amazon S3 | Durable datasets, checkpoints, results, archives |
| EBS | Block storage for nodes, scratch, and application disks |
| EFS | Shared NFS filesystem for multiple nodes and file-based workflows |
| FSx for Lustre | High-throughput parallel file system for HPC, ML, and analytics |
| Instance store/NVMe | Very fast scratch, but lost when the instance is terminated |

A common pattern is storing durable datasets on S3, mounting FSx for Lustre as scratch/working set, and writing results back to S3. Size FSx capacity/throughput to match read/write patterns and verify data repository associations if using S3 integration.

### 12.5 AWS Batch or AWS ParallelCluster?

AWS Batch fits when an organization wants queues, job definitions, retries, array/MNP jobs, and managed capacity. AWS ParallelCluster fits when you need to build an HPC cluster with a scheduler such as Slurm and manage the cluster environment in a traditional HPC style.

The two options can complement each other at the organization level, but two schedulers should never control the same job. Choose based on how users submit jobs, licenses/toolchains, topology, interactive login needs, queue policies, and operational capability.

## 13. Storage, Networking, and Data Movement

### 13.1 Choosing Storage by Data Lifecycle

| Data Type | Appropriate Storage | Reason |
|---|---|---|
| Durable input/output | S3 | Durable, decoupled from compute, and shared across jobs |
| Recoverable checkpoints | S3/EFS/FSx or suitable database | Persists across instance/task/pod restarts |
| Shared POSIX files | EFS or FSx | Multiple workers read/write the same filesystem |
| Block device/scratch | EBS | Block semantics and configurable throughput |
| High-speed temporary scratch | Instance store/NVMe | Fast I/O; acceptable loss when node terminates |
| HPC working set | FSx for Lustre | High-throughput parallel file system |

Never store the only copy of output in a writable container layer, ephemeral task storage, or local instance store if it must survive job completion.

### 13.2 Network Placement

Place compute close to data and dependent services in the same Region. Choose private subnets for workloads that do not need public inbound access; use NAT or VPC endpoints to reach ECR, S3, CloudWatch, Secrets Manager, and AWS APIs.

Checklist items:

- Subnet IP capacity, especially when ECS awsvpc or EKS VPC CNI allocates ENIs/IPs per task/pod.
- Security group ingress/egress between workers, databases, FSx/EFS, and peer nodes.
- DNS resolution and route tables.
- NAT Gateway throughput and data processing costs.
- Cross-AZ data transfer when compute and storage reside in different AZs.
- MTU/jumbo frames and network interface capabilities for HPC where applicable.

### 13.3 S3 Access Patterns

Many workers reading/writing S3 concurrently should partition data and avoid multiple jobs contending on the same object key or generating excessive small files/metadata. Use multipart uploads for large files, retries with backoff, checksums, and commit markers. When fanning out thousands of jobs, consider concurrency limits and monitor downstream throttling/capacity.

### 13.4 File Systems

EFS suits shared file access and workloads requiring POSIX semantics. FSx for Lustre suits high throughput and parallel I/O. EBS is tied to an instance or volume lifecycle; when an instance terminates, determine whether volumes are retained or deleted. Instance store must always be treated as ephemeral.

## 14. IAM, Secrets, and Workload Security

### 14.1 Roles by Runtime

| Platform | Primary Role | Used For |
|---|---|---|
| Direct EC2 | EC2 instance profile | Credentials for processes on the host |
| ECS | Task execution role | Pull images, logs, secrets |
| ECS | Task role | Permissions for the application inside the container |
| EKS | Pod Identity or IRSA role | AWS permissions for the Pod/service account |
| AWS Batch ECS | Job role and execution role | Application permissions and runtime permissions |
| AWS Batch EKS | Kubernetes RBAC + pod IAM role | Batch API access and workload AWS permissions |
| AWS Batch service | Service-linked role | Batch management of compute/resources |

Do not use an instance role or node role as the default permissions for every workload when per-job/task/pod roles can be assigned. Job submitters should only be allowed to PassRole allowlisted roles.

### 14.2 Secrets

Never embed passwords, API keys, or access keys in Docker images, command lines, logs, or source code. Use Secrets Manager/Systems Manager Parameter Store and inject secrets via the appropriate mechanism for ECS/EKS/Batch. Scope secret read access per workload and rotate according to policy.

### 14.3 Container Hardening

- Use minimal images with immutable tags/digests.
- Scan images and dependencies.
- Run as non-root when possible.
- Use a read-only root filesystem if the application supports it.
- Restrict Linux capabilities and privileges.
- Set CPU/memory requests/limits or Batch resource requirements.
- Do not mount host paths/devices unless truly needed.
- Keep secrets out of images and environment logs.
- Update base images and patch on a schedule.

HPC/EFA may require special device access; grant the exact device/permissions needed rather than enabling full privileged containers unnecessarily.

### 14.4 Encryption and Data Protection

Encrypt S3/EBS/EFS/FSx with appropriate mechanisms, using KMS customer-managed keys when key policy control is needed. Enable TLS for service-to-service and database connections. Verify key policies for runtime roles, service roles, and operators.

### 14.5 Auditing

CloudTrail records control-plane API calls such as SubmitJob, RegisterJobDefinition, CreateComputeEnvironment, RunTask, or EKS changes. Combine Batch job history, ECS task events, Kubernetes audit/logs, and application logs to determine:

- Who submitted the job?
- Which image/definition revision did the job use?
- Which role was granted?
- Which resources did the job read/write?
- In which Region/AZ/compute environment did the job run?
- Who modified queues, CEs, or IAM policies?

## 15. Reliability, Retries, and Idempotency

### 15.1 Batch Is Typically At-Least-Once

A job may be re-executed after a node failure, interruption, timeout, or service error. Therefore, never assume code runs strictly once. Design idempotent outputs:

- Assign a unique job_id/run_id.
- Track state per partition/chunk.
- Use conditional writes/upserts keyed by business key.
- Write outputs to a staging prefix.
- Validate record counts/schemas/checksums.
- Publish only after all parts succeed.
- Clean up old staging data per retention policy.

### 15.2 Checkpointing and Resume

Long jobs should checkpoint progress periodically. Checkpoints must be stored in durable storage and include input/schema/code versions when needed. On resume, verify checkpoint compatibility with new code and confirm input data has not changed.

For MPI/HPC, checkpoints must synchronize state across ranks or use application-level checkpointing. Saving only the main process's checkpoint may be insufficient when state is distributed across nodes.

### 15.3 Spot Interruption

Upon receiving a rebalance/interruption event:

1. Stop accepting new chunks.
2. Save checkpoints or flush results safely.
3. Record completed work state.
4. Close files/sockets and release licenses.
5. Exit before the instance is reclaimed if possible.
6. Let the scheduler retry incomplete work.

The two-minute notice is a window for graceful shutdown, not a guaranteed SLA. Always design jobs to survive abrupt termination.

### 15.4 Retry Policy

Retry only transient or self-recovering failures. For code/data/permission errors, transition to FAILED and trigger remediation. Use exponential backoff, jitter, and attempt limits to prevent retry storms.

### 15.5 Queue Backpressure

If submission rate exceeds processing rate, queues grow. Monitor age of oldest job, queue depth, RUNNABLE duration, arrival/completion rates, and downstream capacity. Cap concurrency and use fair-share and resource-aware scheduling. Do not increase max capacity without verifying that databases/APIs/storage can handle increased traffic.

## 16. Orchestration and Event-Driven Pipelines

AWS Batch often serves as the executor in a multi-step pipeline. Step Functions can coordinate submitting jobs, waiting for results, branching on state, and invoking subsequent steps.

    EventBridge / S3 event / API
                 |
            Step Functions
                 |
          Validate input
                 |
           Submit Batch job
                 |
           Wait / DescribeJob
                 |
         Job SUCCEEDED?
             /       \
           Yes        No
            |          |
      Validate output  Retry / alert
            |
       Publish dataset
            |
       Notify consumers

### 16.1 Choosing an Orchestrator

| Need | Tool |
|---|---|
| One-time/cron/rate schedules | EventBridge Scheduler |
| Multi-step workflows, retries, branching, waits | Step Functions |
| Data DAGs, data engineering schedules | MWAA/Airflow |
| Message buffering and decoupling | SQS |
| Batch compute queuing and scheduling | AWS Batch |
| Simple container tasks | ECS RunTask |
| Kubernetes-native workflows | Job/CronJob or workflow engines on EKS |

### 16.2 Job Dependencies

AWS Batch provides direct dependencies between jobs. Step Functions fits when dependencies involve branching, approvals, compensation, or integration across many AWS services. Do not build large dependency graphs solely from chained scripts if per-step observability and retries are required.

### 16.3 Duplicate Triggers

EventBridge, SQS, and orchestrators can deliver duplicate events under their delivery semantics. Use idempotency keys derived from business event IDs, source object versions, or scheduled execution IDs. Before submitting a job, check whether the corresponding work has already been processed.

## 17. Monitoring and Troubleshooting

### 17.1 Metrics to Monitor

| Layer | Metrics / States |
|---|---|
| Queue | Depth, oldest job age, submitted/runnable/running/failed |
| AWS Batch | Job state, CE state, desired/allocated vCPU, job attempts, scheduling delay |
| EC2 | CPU, memory agent, disk, network, Spot interruptions, instance launch failures |
| ECS | Task state, stopped reason, placement failures, service/task count |
| EKS | Pod pending, restarts, OOMKilled, node pressure, scheduler events, IP capacity |
| Application | Runtime, throughput, error rate, retry count, checkpoints, output counts |
| Storage | S3 requests/latency/errors, EBS throughput/queue, EFS/FSx throughput/capacity |
| Cost | Cost per job, cost per TB, idle capacity, Spot/On-Demand ratio |

### 17.2 AWS Batch Job Stuck in RUNNABLE Too Long

Check in order:

1. Does the job queue have a properly attached compute environment?
2. Is the compute environment status VALID?
3. Does the CE have sufficient maxvCpus and EC2 quotas?
4. Do the instance types satisfy required vCPU/memory/GPU?
5. Do subnets have available IPs and routes to ECR/S3/log endpoints?
6. Is Spot capacity available?
7. Are CE order/queue priorities routing the job to an unsuitable environment?
8. Is the job waiting on an unavailable consumable resource/license?

### 17.3 ECS Task Fails to Start

Check task stopped reason, capacity provider, task definition revision, CPU/memory placement, subnet IPs, security groups, ECR pull permissions, execution role, and log configuration. With an EC2 capacity provider, check ASG managed scaling and instance registration.

### 17.4 EKS Pod Pending

Check Kubernetes events, resource requests, node selectors, affinity, taints/tolerations, node group capacity, Karpenter constraints, subnet IPs, and service quotas. If a Pod is OOMKilled, adjust memory requests/limits and fix memory leaks.

### 17.5 Repeated Job Failures

Inspect exit code, reason, container logs, attempt number, and image digest. Determine whether the error is transient, code, data, IAM, or capacity related. Avoid infinitely retrying a deterministic failure.

### 17.6 Logs and Traces

Log job ID, run ID, tenant, input version, image digest, queue, CE, instance/node, attempt, and output location. Avoid logging PII/secrets or full payloads unnecessarily. Set CloudWatch/S3 retention per policy and use correlation IDs to link logs across workflow, scheduler, and container.

## 18. Cost and Optimization

### 18.1 AWS Batch Has No Separate Orchestration Fee

AWS Batch has no additional service charge for using the scheduler. Users pay for the AWS resources created to run and store jobs, such as EC2, Fargate, ECS Managed Instances, EKS, EBS, S3, EFS, FSx, networking, and CloudWatch.

### 18.2 Cost Components by Model

| Model | Components to Account For |
|---|---|
| Direct EC2 | EC2 On-Demand/Spot, EBS, AMI/storage, networking, load balancer if any, logging |
| ECS on EC2 | EC2, EBS, networking, logs, and idle capacity |
| ECS/Fargate | vCPU/memory over task duration, ephemeral storage, data transfer, and logs |
| Native EKS | EKS cluster control plane, EC2/Fargate nodes, EBS, networking, add-ons, and logs |
| AWS Batch on ECS | Underlying EC2/Fargate/ECS Managed Instances plus storage/networking/logging |
| AWS Batch on EKS | EKS cluster, Batch-managed EC2 nodes, storage/networking/logging |

### 18.3 Common Hidden Costs

- EC2 warm capacity or Batch minvCpus keeping instances idle.
- EKS control plane and node capacity when queues are empty.
- Fargate Spot/EC2 Spot interruptions causing job re-runs.
- NAT Gateway and cross-AZ data transfer.
- S3 requests, orphaned EBS volumes, EFS/FSx capacity.
- Excessive CloudWatch log ingestion/retention.
- License tokens or commercial HPC software.
- Retry storms and job re-runs caused by non-idempotent output.

### 18.4 Optimization

- Use Fargate for jobs that fit within its limits and do not need host-level access.
- Use Spot for interruption-tolerant workloads; diversify instance types/AZs.
- Choose EC2 allocation strategies aligned with capacity/cost goals.
- Set appropriate min/max capacity and scale-down delays.
- Use separate queues for different SLAs.
- Use fair-share to prevent a tenant from consuming all compute.
- Right-size vCPU/memory requests to actual needs; monitor OOMs and CPU throttling.
- Stop ECS tasks/EC2 workers when no work remains.
- On EKS, scale nodes to zero or minimal capacity when appropriate; factor in EKS cluster charges.
- Optimize input partitioning, file sizes, and data locality.
- Track cost per successful job, cost per TB, and queue wait times.

## 19. Case Study: Multi-Tenant Batch Image Processing

### 19.1 Context

An e-commerce platform receives 100,000 product images per day from multiple tenants. Each image must be resized to three dimensions, have a thumbnail generated, have metadata validated, and have results written to S3. Large bursts occur after marketing campaigns; each image is independent, and jobs are retryable.

### 19.2 Options

| Option | Pros | Cons |
|---|---|---|
| EC2 worker + SQS | Deep control, simple if a worker platform exists | Self-managed retries, visibility, scaling, fairness, and job status |
| ECS RunTask | Simple containers, Fargate/EC2 capacity providers | Must build queue/retry/fair-share orchestration |
| EKS Job | Kubernetes-native, can share an existing platform | Kubernetes overhead; queue fairness must be designed |
| AWS Batch array jobs | Large fan-out, retries, queues, capacity scaling, and job status | Requires designing job definitions/queues/CEs and idempotent output |

### 19.3 Proposed Design

- S3 receives original images and emits events.
- SQS/EventBridge or an ingestion service batches requests and deduplicates them.
- AWS Batch array jobs or regular partitioned jobs.
- ECS-managed compute environment using Fargate for small jobs, or EC2 Spot if better throughput/cost is needed.
- Job role permitted only to read the raw prefix and write to the tenant's output prefix.
- Outputs written to a staging path keyed by run ID, followed by publishing a manifest.
- CloudWatch monitors queue age, failures, throughput, and cost.

### 19.4 Tenant Protection

Tenant ID is obtained from a trusted authentication/metadata system, not from arbitrary user-supplied prompts or commands. Job roles/policies restrict S3 prefixes; the application validates object keys and disallows path traversal. Log audit events by tenant and job ID.

### 19.5 Scaling and Retries

Set max concurrency so database/catalog systems are not overwhelmed. Use Spot for retryable processing; persist per-image status and idempotent output. If an image fails due to corrupt input, move it to quarantine rather than retrying indefinitely.

## 20. Lab A: Running Batch Tasks with ECS and EventBridge Scheduler

### Objective

Create an ECS task definition that runs a script reading S3 data, writing results, and running on a schedule.

### Prerequisites

- An ECR image containing the batch script.
- An ECS cluster and Fargate or EC2 capacity provider.
- A task execution role and task role.
- Subnets/security groups and S3 access.
- An EventBridge Scheduler role.

### Step 1: Create the Task Definition

1. Specify an immutable image digest/tag.
2. Set appropriate CPU/memory.
3. Define the command/entrypoint.
4. Attach a task role with permissions only to read input and write output.
5. Attach an execution role to pull images and write logs.
6. Configure awslogs and network mode.

### Step 2: Test a Standalone Task

1. Use ECS RunTask.
2. Select the cluster and capacity provider.
3. Configure subnets/security groups.
4. Monitor task state and stopped reason.
5. Verify output in S3.

### Step 3: Create the Schedule

1. Create a cron or rate EventBridge Scheduler schedule.
2. Choose ECS RunTask as the target.
3. Select the cluster/task definition and network configuration.
4. Attach the Scheduler execution role.
5. Configure retries/dead-letter queue.
6. Run a test execution and verify logs/output.

### Step 4: Test Failures

Have the job return a non-zero exit code. Confirm the ECS task transitions to STOPPED and that the workflow/scheduler detects, re-invokes, or alerts on it. Do not expect ECS to automatically replace a standalone task.

## 21. Lab B: Creating an AWS Batch Queue and Compute Environment

### Objective

Create a managed EC2 compute environment, job queue, and job definition, and submit a job that reads/writes S3.

### Step 1: Prepare the Image

1. Build a container image containing the batch script.
2. Push it to Amazon ECR.
3. Test the image locally.
4. Create S3 input/output prefixes.

### Step 2: Create the Compute Environment

1. Select a managed EC2 compute environment.
2. Choose instance families suited to the workload.
3. Set minvCpus = 0 for a lab that does not need warm capacity.
4. Set maxvCpus to cap cost.
5. Choose On-Demand or Spot.
6. Choose subnets/security groups and service role.
7. Verify the CE status is VALID.

### Step 3: Create the Job Queue

1. Create queue batch-lab.
2. Attach the CE via computeEnvironmentOrder.
3. Set priority.
4. Create a fair-share policy if the lab has multiple tenants.

### Step 4: Register the Job Definition

1. Select the ECR image.
2. Specify vCPU and memory.
3. Attach the job role.
4. Configure command, environment, and log driver.
5. Configure retries/timeout.
6. Register the revision.

### Step 5: Submit and Observe

1. SubmitJob to the queue.
2. Track states SUBMITTED/PENDING/RUNNABLE/STARTING/RUNNING.
3. Inspect CloudWatch logs.
4. Verify S3 output.
5. Verify the CE scales down when the queue is empty.

### Step 6: Test Retries

Have the script return a transient failure on the first attempt and succeed on the next. Verify attempt count, evaluateOnExit, and output idempotency.

## 22. Lab C: Batch on EKS and Kubernetes Jobs

### Objective

Compare plain Kubernetes Jobs with an AWS Batch EKS compute environment on the same cluster.

### Part A: Kubernetes Job

1. Create namespace batch-lab.
2. Create a service account and IAM role via Pod Identity/IRSA.
3. Apply the Job manifest.
4. Monitor Pods with kubectl.
5. Verify backoffLimit, activeDeadlineSeconds, and TTL cleanup.
6. Create a CronJob with an appropriate concurrencyPolicy.

### Part B: AWS Batch EKS

1. Verify the EKS cluster version is supported.
2. Create an access entry/RBAC allowing Batch to call the Kubernetes API.
3. Create an EKS compute environment using EC2 On-Demand or Spot.
4. Create a job queue and EKS job definition.
5. Submit a job via the AWS Batch API.
6. Monitor job state in Batch and Pods/nodes in Kubernetes.
7. Confirm Batch uses only nodes managed by the CE.

### Comparison

Record deployment time, queue wait, node provisioning, job runtime, retry behavior, customizability, and number of operational components. Choose a model based on scheduling needs and team skills.

## 23. Self-Check Questions

**Question 1.** Which layers do EC2, ECS, EKS, and AWS Batch belong to?

**Answer:** EC2 is compute; ECS/EKS are container orchestration; AWS Batch is a batch scheduler and capacity orchestrator built on those compute platforms.

**Question 2.** When should you use direct EC2?

**Answer:** When you need a custom OS/AMI/driver, specialized devices, EFA, license daemons, an HPC scheduler, or deep infrastructure control.

**Question 3.** How does an ECS standalone task differ from an ECS service?

**Answer:** A standalone task runs work and terminates; an ECS service maintains a desired count and replaces tasks to keep an application running.

**Question 4.** Does ECS automatically replace a standalone task when a job fails?

**Answer:** No. You need workflow retries or AWS Batch.

**Question 5.** What is EventBridge Scheduler suited for?

**Answer:** Triggering one-time, rate-based, or cron-based tasks, such as invoking ECS RunTask on a schedule.

**Question 6.** How do Kubernetes Job and CronJob differ?

**Answer:** A Job manages a finite unit of work; a CronJob creates Jobs on a schedule.

**Question 7.** What are the core components of AWS Batch?

**Answer:** Job definition, job queue, compute environment, and job.

**Question 8.** Does AWS Batch charge a separate service fee?

**Answer:** No. Users pay for compute, storage, networking, and other AWS resources consumed.

**Question 9.** Which compute types does an AWS Batch managed compute environment support?

**Answer:** EC2 On-Demand/Spot, Fargate/Fargate Spot, and ECS Managed Instances; EKS compute environments use EC2.

**Question 10.** What model does AWS Batch on EKS use?

**Answer:** Overlay orchestration: Batch calls the Kubernetes API to create/monitor/delete Pods and manages nodes dedicated to Batch; no Batch operator needs to be installed in the cluster.

**Question 11.** Does an AWS Batch EKS compute environment support Fargate?

**Answer:** No. Batch on EKS uses EC2 On-Demand or Spot; to use Fargate, choose an ECS compute environment.

**Question 12.** What problem does fair-share scheduling solve?

**Answer:** Allocating compute across tenants/workloads so one group cannot consume all capacity.

**Question 13.** What is the maximum number of child jobs in an array job?

**Answer:** 10,000 under current limits.

**Question 14.** How many attempts does an AWS Batch retry strategy support?

**Answer:** From 1 to 10 attempts.

**Question 15.** What is an MNP job?

**Answer:** A single job running across multiple EC2 instances using gang scheduling, suited for MPI and distributed HPC.

**Question 16.** What are the main prerequisites for EFA?

**Answer:** Supported instance/OS, EFA driver, same cluster placement group, security group allowing internal traffic, and passing the device into the container.

**Question 17.** Why do Spot workloads require checkpointing and idempotency?

**Answer:** Spot instances can be reclaimed; jobs may re-run, requiring progress persistence and protection against duplicate side effects/outputs.

**Question 18.** How does the task execution role differ from the task role on ECS?

**Answer:** The execution role lets the agent pull images/write logs/fetch secrets; the task role grants AWS permissions to code inside the container.

**Question 19.** Why is a job staying in RUNNABLE for a long time not necessarily a code error?

**Answer:** It may be caused by insufficient compute capacity, quotas, matching instance types, subnet IPs, or an invalid CE.

**Question 20.** When should you choose native EKS Jobs instead of AWS Batch on EKS?

**Answer:** When workloads require Kubernetes-native workflows/APIs and the organization already has a suitable queue/scheduler; Batch fits when queues, dependencies, retries, fair-share, and capacity management are needed.

## 24. Production Readiness Checklist

- [ ] Workload classified: one-off, scheduled, queue-driven, parallel, long-running, or HPC.
- [ ] Resource profile and arrival rate benchmarked.
- [ ] Appropriate compute, orchestration, scheduler, and workflow layers selected.
- [ ] Direct EC2 has plans for patching, capacity, scheduling, and cleanup.
- [ ] ECS standalone tasks have external retry/orchestration when needed.
- [ ] ECS services used only for workloads requiring a maintained desired count.
- [ ] EKS Jobs/CronJobs have requests/limits, backoff, deadlines, and cleanup policies.
- [ ] Karpenter/Cluster Autoscaler and Kubernetes quotas tested.
- [ ] AWS Batch queues, CE order, priority, and fair-share aligned with SLAs.
- [ ] Managed/unmanaged CE and compute types explicitly selected.
- [ ] Fargate limits/GPU/host access/MNP verified.
- [ ] Batch on EKS RBAC/access entries and EC2-only compute verified.
- [ ] Job definition revisions and image digests versioned.
- [ ] Job role/execution role/service role follow least privilege.
- [ ] Subnet IPs, NAT/VPC endpoints, security groups, and DNS verified.
- [ ] Durable storage used for inputs/outputs/checkpoints.
- [ ] Jobs are idempotent and output commits are safe.
- [ ] Retries, timeouts, dependencies, and cancellations have runbooks.
- [ ] Spot interruptions tested.
- [ ] HPC MNP/EFA/placement groups/FSx benchmarked if used.
- [ ] Alarms configured for queue depth, oldest job age, RUNNABLE duration, and job failures.
- [ ] Cost per successful job/TB tracked.
- [ ] Cleanup procedures exist for EC2/EBS/ENIs/logs/temporary data.
- [ ] Rollback plan and incident response owner defined.

## 25. Official References

1. [AWS Batch components](https://docs.aws.amazon.com/batch/latest/userguide/batch_components.html) — compute environments, queues, job definitions, and scheduling.
2. [Compute environments for AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html) — ECS/EKS compute environments.
3. [Managed compute environments](https://docs.aws.amazon.com/batch/latest/userguide/managed_compute_environments.html) — EC2, Fargate, Spot, and ECS Managed Instances.
4. [Amazon EKS compute environments for AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/eks.html) — overlay model, RBAC, node scaling, and EKS limits.
5. [Job queues](https://docs.aws.amazon.com/batch/latest/userguide/job_queues.html) — queue priority and compute environment order.
6. [Fair-share scheduling policies](https://docs.aws.amazon.com/batch/latest/userguide/job_scheduling.html) — FIFO and fair-share.
7. [Job definitions](https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html) — container, resources, roles, volumes, and logging.
8. [Automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html) — retry strategies and evaluateOnExit.
9. [Job dependencies](https://docs.aws.amazon.com/batch/latest/userguide/job_dependencies.html) — dependencies and resource-aware scheduling.
10. [Array jobs](https://docs.aws.amazon.com/batch/latest/userguide/array_jobs.html) — fan-out and child jobs.
11. [Multi-node parallel jobs](https://docs.aws.amazon.com/batch/latest/userguide/multi-node-parallel-jobs.html) — gang scheduling and MPI.
12. [Elastic Fabric Adapter with AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/efa.html) — EFA device, placement groups, and security groups.
13. [Fargate compute environments](https://docs.aws.amazon.com/batch/latest/userguide/fargate-compute-environments.html) — Fargate limits.
14. [Amazon ECS Managed Instances compute environments](https://docs.aws.amazon.com/batch/latest/userguide/ecs_managed_instances.html) — ECS-managed compute lifecycle.
15. [AWS Batch pricing](https://aws.amazon.com/batch/pricing/) — no separate Batch service fee.
16. [Amazon ECS standalone tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/standalone-tasks.html) — running one-off tasks.
17. [Schedule ECS tasks with EventBridge Scheduler](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html) — cron/rate/one-time schedules.
18. [Schedule containers on Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/scheduling_tasks.html) — service, standalone, and scheduled tasks.
19. [Amazon ECS capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-best-practice.html) — EC2, Fargate, and Fargate Spot.
20. [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) — Job controller, completions, parallelism, and retries.
21. [Kubernetes CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) — schedules and concurrency policies.
22. [EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html) — interruptions and diversification.
23. [EC2 placement groups](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/placement-groups.html) — cluster, partition, and spread strategies.
24. [AWS ParallelCluster](https://docs.aws.amazon.com/parallelcluster/latest/ug/what-is-aws-parallelcluster.html) — managing HPC clusters and schedulers.

---

**Conclusion:** EC2 provides compute and deep control; ECS runs container tasks/services with simple operations; EKS provides Kubernetes Jobs/CronJobs and the Kubernetes ecosystem; AWS Batch manages queues, dependencies, retries, fairness, and capacity for batch jobs on ECS or EKS. Choose based on workload, resource profile, interruption tolerance, HPC needs, scheduling complexity, and total cost. Test retries, Spot interruptions, output idempotency, and cleanup before deploying pipelines to production.
