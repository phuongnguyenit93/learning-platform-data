# ECS Service Auto Scaling and Capacity Providers

> **Chapter:** Containers with ECS  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS from Regions/Availability Zones (AZs), IAM, VPCs, compute, and storage to databases, integration, and serverless; build the skill to select services and deploy applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **Amazon ECS Service Auto Scaling** (changing **task counts**) from **capacity providers** (defining and managing **compute capacity to run tasks**).
2. Design **Application Auto Scaling** policies: scalable targets, **`MinCapacity`/`MaxCapacity`**, target tracking, step scaling, scheduled scaling, and appropriate metrics.
3. Understand the components and limits of **`FARGATE`**, **`FARGATE_SPOT`**, **Auto Scaling group capacity providers**, and **Amazon ECS Managed Instances**.
4. Calculate the effect of **`base`**, **`weight`**, and capacity provider strategy rules; explain why actual task ratios do not always match a theoretical split.
5. Describe how **ECS managed scaling** grows/shrinks an EC2 Auto Scaling group via **`CapacityProviderReservation`** and **`targetCapacity`**.
6. Design scaling for HTTP applications behind an ALB or SQS consumer workers, integrating health checks, rolling deployments, multi-AZ, IAM, and VPCs.
7. Diagnose `RUNNING` lower than `desiredCount`, tasks stuck in `PROVISIONING`/`PENDING`, Fargate Spot capacity shortages, premature scale-in, or cost spikes; investigate using read-only AWS CLI commands.

## 1. Two Distinct Auto Scaling Loops in ECS

An ECS system can scale at **two layers**:

- **Application layer (Service Auto Scaling):** "How many application replicas do we need?" → adjusts the ECS Service's **`desiredCount`**.
- **Infrastructure layer (Capacity Provider / Cluster Auto Scaling):** "Where will those tasks run, and is there enough CPU/RAM/capacity to place them?" → provisions appropriate compute capacity.

These two loops are **related but independent**. Increasing `desiredCount` alone does not give a small EC2 instance more memory; adding EC2 instances alone does not cause an ECS Service to launch extra replicas if `desiredCount` stays unchanged.

~~~mermaid
flowchart TB
    L["Traffic / queue / metric"] --> CW["CloudWatch metrics and policies"]
    CW --> AAS["Application Auto Scaling"]
    AAS -->|"Adjusts desiredCount"| S["ECS Service scheduler"]
    S -->|"Places extra tasks"| CP["Capacity provider strategy"]
    CP --> F["Fargate / Fargate Spot"]
    CP --> EC2["EC2 Auto Scaling group capacity provider"]
    CP --> MI["ECS Managed Instances capacity provider"]
    EC2 --> CAS["ECS managed scaling: ASG DesiredCapacity"]
    CAS --> H["Add/remove EC2 container instances"]
    H --> T["Tasks reach RUNNING when resources suffice"]
    F --> T
    MI --> T
~~~

**This is a logical diagram:** the ECS scheduler places tasks according to strategy, constraints, and capacity state. Service Auto Scaling does not directly call the Auto Scaling group to add instances; the capacity provider handles infrastructure capacity provisioning.

### 1.1. A Frequently Misunderstood Scenario

An ECS Service shows:

- **`desiredCount` = 8**.
- **`runningCount` = 4**.
- The remaining four tasks cannot be placed because the EC2 cluster lacks RAM.

The application lacks **compute capacity**, not necessarily working Service Auto Scaling. Raising `desiredCount` from 8 to 12 only increases waiting tasks without fixing the RAM shortage.

Conversely, if an EC2 cluster has 10 idle instances while the ECS Service has **`desiredCount` = 2**, the ECS scheduler does not launch 20 replicas just because spare infrastructure exists.

### 1.2. Concept Mapping

| Component | What It Controls | What It Does Not Control |
| --- | --- | --- |
| **ECS Service** | Desired task count and maintaining tasks during service deployments. | Does not automatically add EC2 instances merely by existing. |
| **Application Auto Scaling** | Changes **`desiredCount`** within policy bounds. | Does not directly manage the cluster's EC2 ASG. |
| **Capacity provider strategy** | How tasks are distributed across capacity types/pools. | Is not a traffic-based scale-out metric. |
| **`FARGATE` / `FARGATE_SPOT`** | Fargate compute per eligible task. | Does not guarantee Spot capacity is always available. |
| **EC2 ASG capacity provider** | Links ECS tasks to an EC2 Auto Scaling group; can enable managed scaling. | Does not replace Service Auto Scaling metrics or thresholds. |
| **ECS Managed Instances** | EC2 infrastructure with more lifecycle steps managed by ECS. | Does not replace IAM permissions, data design, or app logic. |
| **ALB** | Receives requests and balances across healthy targets. | Does not decide task counts without a scaling policy. |

## 2. ECS Foundations Before Auto Scaling

### 2.1. Cluster, Task Definition, Task, and Service

- **ECS Cluster:** logical management boundary for services, tasks, and capacity providers.
- **Task definition:** defines image, CPU, memory, ports, environment, logs, IAM roles, and container runtime settings.
- **Task:** a concrete running instance of a task definition.
- **ECS Service:** maintains tasks at **`desiredCount`**, handling placement and deployments.
- **Capacity provider:** specifies which compute pool can run tasks.
- **Capacity provider strategy:** rules distributing tasks across providers within a compatible capacity family.

ECS Services support different scheduling strategies; Service Auto Scaling here focuses on **`REPLICA`**, as **`DAEMON`** does not scale `desiredCount` the same way. `DAEMON` places one task on each eligible EC2 container instance.

### 2.2. `DesiredCount`, `RunningCount`, and `PendingCount`

Suppose the console shows:

| Property | Value | Meaning |
| --- | ---: | --- |
| **`desiredCount`** | 6 | Service scheduler wants to maintain six tasks. |
| **`runningCount`** | 4 | Four tasks have reached `RUNNING` state. |
| **`pendingCount`** | 2 | Two tasks have not yet reached `RUNNING` per reported status. |

You cannot conclude the application can handle full traffic simply because **`desiredCount` = 6**. Inspect individual task states, **container health**, ALB target health, and app readiness to serve requests.

During a new task definition deployment, old and new tasks may coexist within **`deploymentConfiguration.minimumHealthyPercent`**, **`maximumPercent`**, and the deployment strategy. Inspect deployment details before comparing total task counts to `desiredCount`.

### 2.3. Task Definition CPU and RAM Affect Placement

Example Fargate task requirements:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:release-42",
      "essential": true,
      "portMappings": [{"containerPort": 8080, "protocol": "tcp"}]
    }
  ]
}
~~~

This is an **abbreviated illustrative task definition**, not a full production template. Task-level **`cpu`/`memory`** values must match AWS-supported Fargate combinations. On EC2, requested resources must also fit EC2 instance compute and constraints such as ports, ENIs, GPUs, or CPU architecture.

If a container needs 2 GiB to run but the task definition only allocates 1 GiB, scaling out more tasks **will not cure per-task `OOMKilled` crashes**. Fix resource right-sizing and placement fit first.

## 3. How Does ECS Service Auto Scaling Work?

ECS uses **Application Auto Scaling** to scale an ECS Service's task count up or down. The scalable target is identified by:

~~~text
Service namespace: ecs
Resource ID:       service/<cluster-name>/<service-name>
Scalable dimension: ecs:service:DesiredCount
~~~

`<cluster-name>` and `<service-name>` are placeholders to replace with real names. Application Auto Scaling creates and manages the CloudWatch alarms required by policies.

### 3.1. Three Elements of a Scalable Target

| Element | Function | Example |
| --- | --- | --- |
| **`MinCapacity`** | Minimum task count policies are normally allowed to scale down to. | 2 |
| **`MaxCapacity`** | Maximum task count policies are normally allowed to scale up to. | 20 |
| **Scaling policy** | Metric and condition triggering task count changes. | Target CPU 60%. |

A service with `MinCapacity` 2 and `MaxCapacity` 20 **does not** run 20 tasks ahead of time. It runs at its current `desiredCount` plus scaling adjustments. Raising `MaxCapacity` merely lifts the ceiling; it does not add tasks without a scale-out trigger.

### 3.2. Sample Service Auto Scaling Metrics

AWS provides common predefined metrics:

- **`ECSServiceAverageCPUUtilization`:** average CPU utilization of the ECS Service.
- **`ECSServiceAverageMemoryUtilization`:** average memory utilization of the ECS Service.
- **`ALBRequestCountPerTarget`:** requests per target over the evaluation interval when using an ALB/target group under supported conditions.

You can also use well-designed **custom CloudWatch metrics**, such as **queue backlog per task** for workers. With target tracking, a good metric should react so that **adding capacity causes the metric to drop** under constant load.

Note: `ALBRequestCountPerTarget` has deployment-type limits; AWS documentation notes it is **not supported** for target tracking on services using the corresponding **blue/green deployment type**.

### 3.3. Target Tracking — Keeping a Metric Near a Target

**Target tracking** is usually the first choice because you set a target value (e.g., 60% CPU), and the system automatically calculates scale-out or scale-in steps to keep the metric near that target.

Example:

- An ECS Service has 4 running tasks.
- Average CPU is currently 90%.
- Target CPU is 60%.
- Capacity exists to launch more tasks.

An intuitive estimate:

\[
\text{Tasks needed} \approx
\text{current tasks} \times
\frac{\text{current utilization}}{\text{target}}
=4\times\frac{90}{60}\approx6
\]

The number **6 is only an explanatory estimate**, **not a guarantee that ECS's algorithm will always add exactly two tasks**. Application Auto Scaling weighs CloudWatch sample windows, cooldowns, min/max bounds, actual `RUNNING` task counts, rounding rules, and system state.

### 3.4. Asymmetric Scale-Out and Scale-In

Operational design typically prioritizes **availability**:

- **Scale-out:** adds tasks as load rises. It can respond relatively quickly depending on metric period and cooldown.
- **Scale-in:** removes tasks more cautiously to avoid stripping capacity while requests are still arriving.
- **Scale-out cooldown:** dampens rapid consecutive scale-outs, though larger scaling impulses can override per AWS behavior.
- **Scale-in cooldown:** prevents thrashing by removing tasks too aggressively. During a sudden spike, scale-out can supersede scale-in cooldown per documented behavior.

Align cooldowns with **application startup time**, target group registration, warm-up, and metric lag. If a task needs 2 minutes to load a model before becoming ready and scale-out cooldown is too short, the service can over-provision before seeing the relief from the first scale-out.

### 3.5. Multiple Concurrent Target Tracking Policies

Suppose a service uses two policies:

- CPU target = 60%.
- Memory target = 75%.

Application Auto Scaling's general rule across target tracking policies on different metrics:

- **Scale out whenever any policy triggers scale-out.**
- **Scale in only when all policies with scale-in enabled agree to scale in.**

Thus high CPU scales tasks up even if memory is low. Conversely, low CPU alone will not scale tasks in while memory remains high—prioritizing sufficient capacity.

Never create two target tracking policies on the same metric hoping to "force" faster scaling; documentation requires each target tracking policy on a scalable target to track a distinct metric. Avoid manually editing CloudWatch alarms managed by Application Auto Scaling.

### 3.6. Missing Metrics and Scale-to-Zero

CloudWatch metrics can stop emitting data points when zero tasks are running. Target tracking **does not treat missing data as 0% utilization**.

If you want **`MinCapacity` = 0**:

1. Confirm the application can tolerate cold starts.
2. Pick a metric **that still measures demand when zero tasks exist**, such as SQS visible messages, an external custom backlog metric, or an external trigger.
3. When the metric signals demand from 0 tasks, target tracking waits for valid data points and scales out from minimum per AWS behavior.
4. Test scaling back up from 0—not just scaling down to 0.

**Never assume service CPU utilization can wake up a service from zero tasks**, because with zero tasks running there is no CPU metric indicating incoming work.

## 4. Scaling Modes and When to Choose Each

Through Application Auto Scaling, Amazon ECS supports several scaling approaches:

| Approach | How It Works | Best Suited For | Notes |
| --- | --- | --- | --- |
| **Target tracking** | System steers a metric toward a target value. | Web/APIs with suitable CPU/RPS, workers with backlog/task metrics. | Metric must scale inversely with capacity. |
| **Step scaling** | You define CloudWatch alarms and exact task deltas per breach tier. | Aggressive step jumps or custom threshold responses. | Carefully tune alarms, step adjustments, and cooldowns. |
| **Scheduled scaling** | Updates min/max bounds on a schedule. | Predictable rush hours, sales events, business hours. | Schedules do not replace metrics for unexpected spikes. |
| **Predictive scaling** | Forecasts demand from historical data where options/conditions apply. | Recurring seasonal traffic needing pre-warmed capacity. | Requires suitable history and accuracy/support review. |

### 4.1. Step Scaling

Suppose a service runs 4 tasks with team-defined thresholds:

| Average CPU Detected by Alarm | Illustrative Action |
| --- | --- |
| Above 70% for configured interval | Add 2 tasks. |
| Above 90% for configured interval | Add 5 tasks. |
| Below 25% long enough | Remove 1 task. |

These actions are example **step adjustments**, not AWS defaults. Avoid overlapping alarms that cause capacity oscillation or runaway growth. Watch min/max bounds, evaluation periods, datapoints, and cooldowns.

### 4.2. Scheduled Scaling

Suppose traffic follows a daily curve:

- 07:30–09:30 heavy user logins.
- 12:00 lunchtime spike.
- Low overnight traffic.

You can schedule an action raising **`MinCapacity`** from 2 to 6 ahead of peak hours and lowering min afterward, as real load allows. Scheduled actions typically adjust the **scalable target's min/max bounds** on schedule—do not oversimplify this as "every morning force ECS to run exactly six tasks regardless of policies and demand."

### 4.3. Pick Metrics That Match the System Bottleneck

An API service sitting at 25% CPU while database queries stall and time out will **overload the database even further** if you scale out API tasks without fixing the bottleneck.

Distinguish:

- **CPU-bound:** adding tasks helps if backends scale independently and quotas allow.
- **Memory-bound:** adding tasks eases load for some workloads, though memory leaks require code fixes.
- **I/O-bound:** inspect networking, database connection pools, downstream latency, and retries before adding concurrency.
- **Queue workers:** backlog per task and **`ApproximateAgeOfOldestMessage`** usually reflect responsiveness far better than CPU alone.

## 5. What Is a Capacity Provider?

A **capacity provider** tells ECS **which compute pool** runs tasks and provides pool-specific capacity management features.

Key groups:

1. **AWS Fargate capacity providers:** **`FARGATE`** (on-demand) and **`FARGATE_SPOT`**.
2. **EC2 Auto Scaling group capacity providers:** linked to an EC2 Auto Scaling group, optionally enabling **managed scaling**, managed termination protection, and managed instance draining.
3. **Amazon ECS Managed Instances capacity providers:** ECS manages much of the EC2 instance lifecycle—including provisioning, capacity, and infrastructure management—per current capabilities.

### 5.1. Compute Choice Comparison Table

| Type | Who Manages the Underlying Host? | Scenarios | Watch-Outs |
| --- | --- | --- | --- |
| **`FARGATE`** | AWS provisions matching task compute. | APIs, microservices, batch jobs wanting zero EC2 management. | Billed by task resources/duration and related fees. |
| **`FARGATE_SPOT`** | AWS provisions spare Spot capacity. | Interruption-tolerant batch/workers; cost optimization. | Capacity may be unavailable; tasks stop when AWS reclaims Spot. |
| **EC2 ASG capacity provider** | You manage instance types/AMI/OS/ASG; ECS can manage ASG size. | Workloads needing custom EC2 types, custom AMIs, GPUs, or bin-packing savings. | Requires ECS agent, OS patching, ASG limits, capacity placement. |
| **ECS Managed Instances** | ECS manages much of the EC2 lifecycle. | Want EC2 compute with lower operational overhead. | Verify Region, task compatibility, IAM, quotas, and service pricing. |

**Note:** No single option is "always faster/cheaper" for every workload. Fargate cuts EC2 ops, though pricing and features differ from EC2; ECS Managed Instances is a distinct model, not another name for Fargate.

### 5.2. Fargate and Fargate Spot

- **`FARGATE`:** allocates compute matching task requirements without operating an ASG.
- **`FARGATE_SPOT`:** uses spare AWS compute capacity at discounted rates without guaranteed availability.
- When Fargate Spot is reclaimed, AWS typically sends a **roughly two-minute** warning before stopping the task via an EventBridge task state-change event and a **`SIGTERM`** signal to containers as supported.
- If Spot lacks capacity, tasks may fail to place right away; the ECS service keeps trying to reach `desiredCount` per scheduler behavior.

**Important:** Fargate Spot capacity exhaustion **does not mean ECS automatically falls back to `FARGATE` on-demand**. A capacity provider strategy is not a guaranteed fallback SLA; production apps need an on-demand base, task distribution, multi-AZ, retries, and operational runbooks.

### 5.3. ECS Managed Instances Is Not a Self-Managed EC2 ASG

An organization might want:

- Control to pick suitable EC2 compute capabilities,
- Without manually updating AMIs, editing launch templates, scaling instances, and patching hosts.

ECS Managed Instances addresses several of these needs within its service scope. However, never assume every configuration or management API of an **ASG capacity provider** maps verbatim to a **Managed Instances provider**.

When evaluating it, check **task definition compatibility**, supported instance/hardware families, Regional availability, networking, security, upgrade behavior, and actual pricing.

## 6. Capacity Provider Strategy: `base`, `weight`, and Rules

An ECS Service or standalone task can use:

- An explicitly specified **capacity provider strategy**.
- The cluster's **default capacity provider strategy** when neither launch type nor strategy is specified.
- **`launchType`** (`EC2` or `FARGATE` depending on context), mutually exclusive with `capacityProviderStrategy`.

**Never pass both `launchType` and `capacityProviderStrategy` in the same service request.** Which setting applies depends on the service definition, cluster defaults, and AWS-supported update rules.

### 6.1. Meaning of `base`

**`base`** is the minimum number of tasks ECS tries to place on a specific capacity provider before applying `weight` to the remaining tasks.

Example:

- `FARGATE` **`base` = 2**.
- `desiredCount` = 10.
- Two baseline tasks are placed first onto **`FARGATE`** per `base`.
- The remaining eight tasks are split according to **`weight`**.

Only **one** provider in a strategy may declare `base`. It defaults to 0 if omitted.

### 6.2. Meaning of `weight`

**`weight`** defines the **relative** ratio for distributing tasks after `base` is satisfied.

Example with two providers:

- Provider A `weight` = 1.
- Provider B `weight` = 3.

For eight post-base tasks, the theoretical split A:B ≈ 1:3, or roughly 2:6. With small task counts, placement/rounding, capacity availability, and deployments mean actual distribution will not always match the exact ratio at every instant.

### 6.3. Example: Fargate On-Demand + Spot

~~~json
{
  "capacityProviderStrategy": [
    {
      "capacityProvider": "FARGATE",
      "base": 2,
      "weight": 1
    },
    {
      "capacityProvider": "FARGATE_SPOT",
      "weight": 3
    }
  ]
}
~~~

This is an **illustrative configuration snippet**, not a complete create-service request.

With `desiredCount` **10** and available capacity:

- First, prioritize **2 `FARGATE` tasks** for `base`.
- The **remaining 8 tasks** target a `FARGATE`:Spot ratio of 1:3.
- Expected distribution sits near **4 `FARGATE` and 6 `FARGATE_SPOT` tasks**, not strictly exact at all times.

If `desiredCount` is only **2**, both tasks land on `FARGATE` because `base` consumes the entire count. Never misread a 1:3 weight as **"25% on-demand / 75% Spot of total `desiredCount`"** when `base` is present.

### 6.4. Mandatory Rules to Remember

- Every provider in the strategy must be **associated with the cluster** per usage rules.
- Strategies have an AWS limit on provider count—typically up to **20** per strategy; verify current quotas/docs.
- **At least one `weight` must be greater than 0** in a multi-provider strategy; all weights = 0 is invalid.
- A provider with **`weight` = 0 receives no tasks** from weight-based allocation.
- Over the **API/CLI**, omitting `weight` typically defaults to **0**; in the ECS console, the default may be **1**. **Always specify `weight` explicitly** so IaC stays deterministic.
- A single strategy **cannot mix different capacity provider families**: never combine `FARGATE`/`FARGATE_SPOT` with an ASG-based provider in **one strategy**, nor mix Managed Instances directly with the other two families in the same strategy.
- **One cluster can still contain multiple capacity provider families** serving different ECS services, each with its own compatible strategy.

### 6.5. `weight` Does Not Guarantee Capacity Availability

Suppose you set `FARGATE` 20% and `FARGATE_SPOT` 80% via weights, and Spot runs short on capacity:

- ECS cannot place the full intended share of Spot tasks.
- The service may run with `runningCount` below `desiredCount` for some time.
- Actual traffic share also depends on **ALB target health**, running counts, and capacity skew—not weights alone.

Never use `weight` to claim **"we meet an 80/20 request SLA."** If you need a guaranteed floor of Fargate tasks for availability, set an on-demand **`base`** paired with proper recovery and monitoring.

### 6.6. Switching Between Capacity Models

Whether a service can update from a launch type to a capacity provider strategy or across compute models depends on **ECS documentation at deployment time**, task definition compatibility, and re-deployment rules. Some changes require a fresh deployment and scheduler verification.

Never alter strategy fields in production without a rollback plan, migration path, and verification of task definition, networking, deployment controller, and capacity family compatibility.

## 7. EC2 ASG Capacity Providers and ECS Managed Scaling

With ECS on EC2, an ECS Service may request more tasks, yet **EC2 instances in the cluster must have enough free resources** to host them. An **EC2 Auto Scaling group capacity provider** links ECS task placement to EC2 Auto Scaling group scaling.

~~~mermaid
flowchart TD
    S["ECS Service: desiredCount rises"] --> P["Tasks wait for placement / capacity"]
    P --> C["ASG capacity provider with managed scaling"]
    C --> M["CapacityProviderReservation in CloudWatch"]
    M --> ASG["EC2 Auto Scaling group DesiredCapacity"]
    ASG --> EC2["Add EC2 instances to ECS cluster"]
    EC2 --> R["Scheduler places tasks to run"]
~~~

### 7.1. Distinguishing Three Counts

| Metric | Unit | Adjusted By |
| --- | --- | --- |
| **Service `desiredCount`** | ECS tasks. | ECS Service Auto Scaling or explicit service update. |
| **ASG `DesiredCapacity`** | EC2 instances or ASG capacity units per supported config. | Capacity provider managed scaling or external ASG management. |
| **Service `runningCount`** | Actually running ECS tasks. | Scheduler placement, health, and runtime behavior. |

Example:

- Each task needs 1 vCPU and 2 GiB RAM.
- Each EC2 instance has roughly 4 vCPU and 8 GiB RAM before subtracting OS, agent, and reserved resources.
- In theory multiple tasks fit, though actual fit depends on ports, ENIs, resource reservations, placement, and overhead.

When 20 tasks wait for placement, the capacity provider scales EC2 using ECS heuristics—it does **not** blindly divide 20 by 4 and promise exactly five instances every time.

### 7.2. Managed Scaling

In an ASG capacity provider, **`managedScaling.status = ENABLED`** lets ECS manage ASG scale-out/scale-in based on metrics and configured parameters.

Key parameters:

- **`targetCapacity`**: target reservation percentage within AWS-supported bounds.
- **`minimumScalingStepSize` / `maximumScalingStepSize`**: bounds adjustment sizes to avoid overly tiny or unexpectedly huge scaling jumps.
- **`instanceWarmupPeriod`**: prevents over-scaling while newly launched instances are still booting/registering.
- **Auto Scaling group `MinSize`/`MaxSize`**: hard infrastructure bounds; ECS managed scaling **never raises `MaxSize`** for you.

**Note:** Capacity provider managed scaling manages ASG `DesiredCapacity`, yet you must still configure the **launch template**, cluster association, instance profile, IAM, VPC, subnets, security, and EC2 ECS agent.

### 7.3. What Is `CapacityProviderReservation`?

The ASG capacity provider's **`CapacityProviderReservation`** metric reflects the ratio of **EC2 instances needed to run tasks** to **currently running instances**:

\[
\text{CapacityProviderReservation} =
\frac{\text{instances needed}}{\text{instances running}}\times 100\%
\]

This is an explanatory formula from AWS. The underlying calculation for instances needed accounts for CPU, memory, ENIs, ports, GPUs, placement constraints, and supporting factors—never assume summing vCPUs alone suffices.

Example:

- Estimated need = 8 EC2 instances.
- ASG currently has 10 instances.
- `CapacityProviderReservation` ≈ **80%**.

If **`targetCapacity` = 80%**, the system aims for ~20% headroom under this capacity model. If **`targetCapacity` = 100%**, it targets tighter packing with minimal spare headroom.

**Never interpret `targetCapacity` 80% as keeping EC2 CPU below 80%.** This metric is **not `CPUUtilization`**—it measures instance reservation demand to place ECS tasks on the capacity provider.

### 7.4. `targetCapacity` Below 100% and Placement Strategy

Choosing **`targetCapacity` below 100%** keeps spare capacity so new tasks can start faster. However, **placement strategy** shapes how effectively that headroom works:

- **`binpack`:** packs tasks tightly onto fewer instances, reducing fragmented idle capacity.
- **`spread`:** distributes tasks across attributes like Availability Zones or instances to spread risk.
- **`constraints`:** restricts placement to EC2 instances matching specific rules.

AWS advises evaluating **`binpack` before `spread`** when using `targetCapacity` below 100% in compatible setups so capacity isn't fragmented against scaling goals. Still, where AZ/instance fault tolerance is vital, design intentional HA distribution—never binpack critical workloads onto a single EC2 single point of failure.

### 7.5. When Tasks Cannot Fit Any Instance

If tasks require CPU/RAM/ENIs/GPUs/ports or placement constraints that **no instance type in the ASG can satisfy**, adding more instances of the same type fixes nothing.

For example, a task needs **16 GiB RAM** while the ASG only launches 8 GiB instances. The service will keep waiting tasks even as the ASG scales out idle instances. Fix the **task requirements or the instance type/ASG**.

### 7.6. Managed Termination Protection and Managed Draining

**Managed termination protection** protects EC2 container instances running ECS tasks from certain ASG scale-in terminations. When enabled, configure matching ASG **instance scale-in protection** per AWS guidance.

**Managed instance draining** transitions terminating/reclaimed EC2 instances to **`DRAINING`** so running tasks are stopped/migrated in a controlled manner and services maintain availability within architectural bounds.

The two features differ:

- Protection tries to **avoid picking instances running tasks** for scale-in termination where applicable.
- Draining handles **gracefully emptying an instance** and replacing tasks when termination actually happens.

Spot interruptions or instance refreshes can still terminate an instance even with protection enabled in cases where AWS cannot keep the instance alive. Applications still need **graceful shutdown, deregistration delay, checkpointing, and retries**.

### 7.7. Avoid Conflicts with Manual ASG Scaling Policies

When ECS managed scaling manages an Auto Scaling group:

- **Do not manually edit or delete the scaling policy** managed by the capacity provider.
- Avoid running a competing ASG CPU target tracking policy fighting over **ASG `DesiredCapacity`** unless following a specifically supported design.
- Do not delete management tags like **`AmazonECSManaged`** from the ASG.
- Avoid ad-hoc manual instance/ASG edits when managed termination protection is active.
- Ensure ASG **`MaxSize` > 0** if scaling from 0.

Out-of-band interference can cause scaling oscillation, failed placements, or prevent ECS from estimating capacity accurately.

## 8. Real Scale-Out Sequence on ECS on EC2

Consider a containerized API running on an ASG capacity provider.

**Initial state:**

- `DesiredCount` = 4.
- `RunningCount` = 4.
- ASG has 2 EC2 instances.
- CloudWatch average service `CPUUtilization` = 85%, target = 55%.

### 8.1. Progression

1. **CloudWatch metric** breaches the target per configuration.
2. **Application Auto Scaling** raises `desiredCount` from 4 to a higher count, say 6.
3. The ECS scheduler looks for placement for the new tasks.
4. If the two current EC2 instances lack CPU/RAM/ports/ENIs, new tasks stay in **`PROVISIONING`/`PENDING`**.
5. **ECS capacity provider managed scaling** sees capacity demand for tasks using the provider and increases **ASG `DesiredCapacity`** per scaling logic.
6. The ASG launches a new EC2 instance, which boots, starts the ECS agent, joins the cluster, and becomes ready.
7. The scheduler places the tasks; tasks pull images, start up, and run health checks.
8. Once ALB targets turn healthy and the app is ready, new tasks serve requests.
9. Application Auto Scaling continues monitoring metrics after cooldown to decide next steps.

~~~mermaid
sequenceDiagram
    participant CW as CloudWatch
    participant AAS as Application Auto Scaling
    participant ECS as ECS Service Scheduler
    participant CP as Capacity Provider
    participant ASG as EC2 Auto Scaling Group
    participant ALB as Application Load Balancer
    CW->>AAS: High CPU / target tracking
    AAS->>ECS: Increase desiredCount
    ECS->>CP: Request extra task capacity
    CP->>ASG: Managed scaling updates ASG desired
    ASG-->>ECS: New instance joins cluster
    ECS->>ALB: New tasks pass health checks
    ALB-->>ECS: Targets healthy
~~~

**Total time to serve additional requests** is never just the CloudWatch alarm evaluation period. It includes updating task count, EC2 boot (if needed), image pulls, app startup, cache warming, ALB health checks, and database connections.

### 8.2. Scale-In

When load drops:

1. The service scaling policy lowers `desiredCount` conservatively.
2. The ECS scheduler stops tasks per deployment/termination behavior.
3. Emptied EC2 instances can be scaled in by the capacity provider/ASG.
4. Managed draining/termination protection reduces the risk of killing active tasks prematurely.
5. Metrics, desired/running tasks, and ASG capacity settle back to baseline.

Control **`stopTimeout`**, `SIGTERM` handling, DB connections, session state, and queue checkpoints. If a task is mid-way through a 3-minute payment flow and gets killed after seconds, scale-in causes business failures even when CPU policies worked as configured.

## 9. Designing Service Auto Scaling for an HTTP API Behind an ALB

Suppose **`orders-api`** runs on ECS Fargate behind an ALB:

- Task definition: CPU/memory sized for real load.
- `REPLICA` ECS Service: `desiredCount` = 3.
- Application Auto Scaling: `MinCapacity` = 2, `MaxCapacity` = 20.
- Target tracking CPU = 60% or **`ALBRequestCountPerTarget`** per service/deployment support.
- Capacity strategy: on-demand `FARGATE` baseline for HA, optionally adding Spot for interruption-tolerant capacity.

~~~mermaid
flowchart TB
    USER["Clients"] --> ALB["ALB HTTPS"]
    ALB --> TG["Target group / health"]
    subgraph AZA["AZ A"]
      T1["ECS task 1"]
    end
    subgraph AZB["AZ B"]
      T2["ECS task 2"]
    end
    subgraph AZC["AZ C"]
      T3["ECS task 3"]
    end
    TG --> T1
    TG --> T2
    TG --> T3
    CW["CloudWatch CPU/RPS metrics"] --> AAS["Application Auto Scaling"]
    AAS -->|"desiredCount"| S["ECS Service"]
    S -.->|"add/remove tasks"| TG
~~~

The diagram illustrates tasks spread across AZs; it does not claim the scheduler always places exactly one task per AZ at every moment. Subnets, deployments, placement, Fargate capacity, and load balancers must align with available AZs.

### 9.1. Choosing CPU vs. Request Count

| Metric | Fits Well When | Can Mislead When |
| --- | --- | --- |
| **CPU utilization** | CPU scales roughly linearly with work; CPU-bound APIs. | App mostly waits on DB/network—CPU stays low while latency spikes. |
| **Memory utilization** | Per-task RAM tracks load without memory leaks. | Caches grow until hitting a plateau or memory leaks—scaling doesn't fix leaks. |
| **`ALBRequestCountPerTarget`** | Target group and requests/task reflect load evenly. | Requests vary wildly in cost; blue/green deployment type does not support this metric for target tracking. |
| **Custom latency/backlog** | Reliable demand signal correlated with scale. | Metric doesn't scale inversely with task count or disappears at 0 tasks. |

A DB-dependent API can suffer surging p95 latency while CPU stays low. Adding API tasks then multiplies DB connections and worsens the outage. Pair scaling metrics with **backend health and data store capacity** rather than scaling blindly.

### 9.2. Deployments and Scaling

Per Application Auto Scaling behavior for supported ECS deployment controllers:

- During an **active deployment**, Application Auto Scaling typically **pauses scale-in**.
- **Scale-out remains allowed** unless explicitly suspended.
- Exceptions exist for services using an **external deployment controller**; verify your controller type.
- If a team wants to suspend scale-out too, manage scalable target suspended states cleanly and re-enable afterward.

Also note rolling deployments temporarily need **more capacity than `desiredCount`** per `minimumHealthyPercent`/`maximumPercent`. A nearly full ASG or Fargate Spot shortage can stall a rollout even while scaling policies behave properly.

### 9.3. Health Check Grace Period and Readiness

A newly `RUNNING` task is not automatically ready for requests.

- **ALB health check path** should hit a genuine readiness endpoint.
- **`healthCheckGracePeriodSeconds`** on the ECS Service (when using supported load balancers/health checks) stops the scheduler from declaring tasks unhealthy too early while containers warm up.
- **Container health checks** report internal container health per config.
- Apps should return readiness errors accurately while initializing.
- If DB migrations run at startup, prevent new tasks from receiving production traffic before dependencies are ready.

**Never set a huge health check grace period to hide a crashing image.** Distinguish slow startup from misconfiguration or missing dependencies.

## 10. Designing Auto Scaling for an SQS Worker

An image-processing pipeline:

~~~mermaid
flowchart LR
    S3[("S3 uploads")] --> Q["SQS Standard queue"]
    Q --> W["ECS Service worker tasks"]
    W --> OUT[("S3 results")]
    Q --> M["CloudWatch queue metrics"]
    M --> AAS["Application Auto Scaling"]
    AAS -->|"scale desiredCount"| W
~~~

### 10.1. Why CPU Is Often a Poor Metric Here

Workers may spend most of their time waiting to download images from S3 or write results to a database. Low CPU does not mean the queue isn't backing up.

A useful application metric is:

\[
\text{BacklogPerTask} =
\frac{\text{ApproximateNumberOfMessagesVisible}}{\max(\text{running tasks},1)}
\]

This is a **reference formula** for understanding, not a built-in ECS metric. Pay special attention to in-flight/invisible messages, varying job durations, and the zero-task edge case.

### 10.2. Choosing Target Backlog per Task

Suppose:

- Each task processes **0.5 messages/second** (30 messages/minute) steadily.
- Desired maximum queue wait before processing starts ≈ **120 seconds**.

An initial target backlog scaled to one task's throughput:

\[
\text{Target backlog/task}
\approx
\text{task processing rate} \times
\text{acceptable queue wait}
=0.5\times120 = 60
\]

If the queue holds **600 messages**, this heuristic suggests roughly **10 tasks**. That is an estimate to tune policies—not a guarantee on every message's exact wait time; variable job sizes, retries, and queue semantics all affect actual latency.

Also monitor **`ApproximateAgeOfOldestMessage`**, failures/DLQs, and actual processing duration.

### 10.3. Workers Need Idempotency and Graceful Shutdown

During ECS scale-in or Spot interruptions:

- Workers should stop polling new work on `SIGTERM`.
- Finish in-flight work within the timeout, or checkpoint and let messages return to the queue.
- Tune SQS visibility timeouts and DLQs to match processing duration.
- Process messages idempotently since SQS Standard allows redelivery.
- Record business state conditionally to prevent duplicate processing or double charges.

**Scale-in does not prove the queue is completely empty.** If metrics lag or messages are in-flight (invisible), tasks can scale down while work remains.

### 10.4. Scale to Zero: Test Both Directions

For asynchronous workers not serving synchronous requests:

- `MinCapacity` = 0 saves compute when idle.
- The scale-out trigger metric must **emit even with zero running workers**, such as queue depth or an independent custom alarm/metric.
- When new messages arrive, measure cold-start latency from enqueue to task execution.
- If using Fargate Spot, never assume Spot capacity is always available to boot from zero.

If tight SLAs demand fast response, keeping `MinCapacity` ≥ 1 or an on-demand baseline worker may fit better.

## 11. Security and Networking Affect Scaling Ability

Scaling successfully requires newly launched tasks **to pull images, fetch secrets, accept traffic, and reach dependencies**.

### 11.1. IAM Roles to Distinguish

| Role | Purpose | Example Permissions |
| --- | --- | --- |
| **Task execution role** | Used by ECS agent/Fargate runtime to pull images, ship logs, fetch startup secrets/configs per ECS mechanisms. | ECR image pull, CloudWatch Logs, secrets access if referenced in task definition. |
| **Task role** | AWS API permissions for **application code inside the container**. | `s3:GetObject`, `sqs:ReceiveMessage`, `dynamodb:PutItem`. |
| **EC2 instance profile role** | Infrastructure permissions for ECS EC2 container instances. | ECS agent cluster registration/communication per matching managed policy. |
| **Application Auto Scaling service-linked role** | Allows the service to adjust ECS `desiredCount`. | Internal permissions via **`AWSServiceRoleForApplicationAutoScaling_ECSService`**. |
| **ASG/Capacity provider service roles** | ECS/EC2 Auto Scaling managing capacity and instances. | Feature-specific service-linked roles. |

Never grant **`ecs:UpdateService`**, **`autoscaling:UpdateAutoScalingGroup`**, or IAM admin rights to a task role just to let a container read S3. Workload roles should hold only business permissions.

### 11.2. VPC, Subnets, and Security Groups

- Fargate uses **`awsvpc` network mode** and task ENIs per service limits.
- Tasks in private subnets need paths to **ECR API/DKR, S3, CloudWatch Logs, Secrets Manager**, or other dependencies via **VPC endpoints/NAT** per design.
- ALB target groups, target types, listeners, and Security Groups must allow traffic to container ports.
- EC2 container instances need sufficient subnet IPs, ENIs, ports, and proper cluster registration.
- Spread tasks across **multiple AZs** for availability; watch IP exhaustion and subnet sizing.

If ECS cannot pull images because ECR/S3 endpoints or NAT are missing, raising `desiredCount` **only spawns more failed tasks**.

### 11.3. Secrets and KMS

ECS Task Definitions can reference secrets from Secrets Manager or SSM Parameter Store where supported. When new tasks launch:

- Execution role and network path must reach the secret store.
- KMS permissions must align if using customer managed keys.
- Avoid printing credentials/secrets to logs.
- Remember new tasks pick up the secret version current at startup; rotation needs matching application handling.

### 11.4. Images and Container Sources

Oversized images slow down scale-out. Lean images, multi-stage builds, image scanning, immutable tags/digests, and reliable pull paths cut startup latency and supply-chain risk.

For multi-AZ workloads, images, secrets, and data dependencies must be reachable from every target subnet/Region—not just a single build machine.

## 12. Performance, Cost, and Availability

### 12.1. Cost When Scaling on Fargate

Fargate bills by **vCPU, memory, runtime duration**, OS/architecture/extra storage settings, and Region per current pricing. Scaling out extra tasks for the same traffic increases compute spend if metrics/cooldowns are poorly tuned.

`FARGATE_SPOT` offers lower rates for interruptible capacity, yet factor in costs for:

- Retries and reprocessing after interruptions.
- Longer queue backlog times when Spot capacity tightens.
- Monitoring overhead and on-demand `FARGATE` baseline tasks protecting SLAs.

**Lower unit Spot rates do not automatically mean lower TCO**, especially for latency-sensitive real-time workloads.

### 12.2. Cost on EC2 Capacity Providers

With EC2 ASGs, total cost also includes:

- EC2 instance counts/types/running hours.
- EBS volumes, data transfer, NAT, and networking.
- Operational effort for AMIs, patching, ECS agent updates, and capacity planning.
- Headroom kept by **`targetCapacity` < 100%** for faster task launches.
- EC2 Spot/On-Demand/Savings Plans per purchasing model.

**`targetCapacity` 80%** keeps noticeably more reserve capacity than 100%. That headroom buys faster scale-out response at the price of paying for idle host resources.

### 12.3. Optimizing Around Actually Needed Tasks

An effective plan:

1. **Right-size task definitions:** set CPU/RAM from real consumption.
2. **Profile workloads:** measure RPS, CPU, memory, latency, queue wait, and DB capacity.
3. **Set sensible Min/Max:** never scale below SLA minimums.
4. **Pick demand-aligned metrics:** avoid CPU when bottlenecks sit in DB/IO.
5. **Tune cooldowns to startup/stop times:** prevent thrashing.
6. **Choose capacity providers:** Fargate for lean ops, EC2/Managed Instances for hardware/cost fit, Spot for interruption-tolerant work.
7. **Maintain observability:** track pending tasks, healthy targets, events, and per-service spend.
8. **Run load and failover tests:** measure real post-scale recovery rather than trusting policy configs on paper.

### 12.4. Putting Guardrails on Scale-Out

Never set `MaxCapacity` to infinity just for availability; backends may collapse under hundreds of tasks or DB connections. Constrain via:

- `MaxCapacity` aligned with budget and downstream throughput.
- Rate limiting and throttling at the API edge.
- Database connection pooling and concurrency caps.
- Queue backpressure, DLQs, and exponential backoff retries.
- AWS Budgets, Cost Anomaly Detection, and metric alarms.
- Checking AWS Service Quotas and ASG `MaxSize` ahead of peak events.

Every scale-out should improve throughput or latency. If adding tasks raises the error rate, you are likely **scaling straight into a downstream bottleneck**.

## 13. Which Signals Should You Monitor?

### 13.1. By Layer

| Layer | Metrics / Events | Meaning |
| --- | --- | --- |
| ECS Service | **`desiredCount`, `runningCount`, `pendingCount`**, deployment state, service events. | Is the service meeting its task goal? |
| Application Auto Scaling | Scalable targets, scaling policies/activities, CloudWatch alarms. | Why did `desiredCount` change? |
| ECS task/container | CPU, memory, `exitCode`, `stoppedReason`, container health. | Why are tasks unhealthy or stopping? |
| ALB | `RequestCountPerTarget`, `TargetResponseTime`, HTTP 5xx, `HealthyHostCount`. | Are new tasks actually serving traffic? |
| SQS | `ApproximateNumberOfMessagesVisible`, `AgeOfOldestMessage`, DLQ. | Are workers keeping pace with demand? |
| EC2 capacity provider | **`CapacityProviderReservation`**, provider status, managed scaling/draining. | Is infrastructure keeping up with placement? |
| EC2 ASG | `DesiredCapacity`, `InService`/`Pending` instances, scaling activities. | Is the ASG scaling properly? |
| Cost | Fargate usage, EC2 hours, logs, NAT, data transfer. | Is spend growing proportionally to value? |

### 13.2. Priority Questions During Incidents

- **`desiredCount` rises, `runningCount` does not:** check placement, `stoppedReason`, container image, IAM, networking, and capacity providers.
- **`runningCount` rises, latency stays high:** check ALB health, startup/readiness, DB, rate limiting, and downstream bottlenecks.
- **No new EC2 instances launch:** check capacity provider `managedScaling`, ASG `MaxSize`, `CapacityProviderReservation`, `AmazonECSManaged` tag, task placement, and quotas.
- **Fargate Spot tasks stay Pending:** check Fargate Spot availability and on-demand baseline; never assume automatic fallback.
- **Scale-in causes 5xx:** check container `SIGTERM`/`stopTimeout`, deregistration delay, in-flight requests, readiness, and task protection where applicable.
- **CPU is low, yet tasks don't scale in:** check other target tracking policies, cooldowns, active deployments, `MinCapacity`, and missing metrics.

## 14. AWS CLI — Read-Only Configuration Inspection

These commands **never create, modify, or delete resources**. Ensure your AWS profile has IAM read permissions, select the right account/Region, and replace placeholders with real names.

### 14.1. Confirm Identity and Cluster List

~~~bash
aws sts get-caller-identity

aws ecs list-clusters \
  --region ap-southeast-1

aws ecs describe-clusters \
  --clusters demo-ecs-cluster \
  --include STATISTICS SETTINGS ATTACHMENTS \
  --region ap-southeast-1
~~~

In **`describe-clusters`**, inspect **`capacityProviders`**, **`defaultCapacityProviderStrategy`**, cluster status, registered container instances, and attachments. When a service omits a capacity strategy or launch type, the cluster's default strategy determines placement.

### 14.2. Inspect the ECS Service

~~~bash
aws ecs list-services \
  --cluster demo-ecs-cluster \
  --region ap-southeast-1

aws ecs describe-services \
  --cluster demo-ecs-cluster \
  --services orders-api \
  --region ap-southeast-1 \
  --query "services[].{Name:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Strategy:capacityProviderStrategy,Deployments:deployments,Events:events[:5]}"
~~~

Inspect:

- **`desiredCount`/`runningCount`/`pendingCount`**.
- **`capacityProviderStrategy`** or **`launchType`**.
- **`deploymentController`**, deployment states, and events.
- **Task definition revision**, ALB target group, networking, and health check grace period in the full output.

If events report **`unable to place task`**, the bottleneck is capacity/placement—not a CloudWatch scaling alarm.

### 14.3. Inspect Tasks and Stop Reasons

~~~bash
aws ecs list-tasks \
  --cluster demo-ecs-cluster \
  --service-name orders-api \
  --desired-status RUNNING \
  --region ap-southeast-1

aws ecs list-tasks \
  --cluster demo-ecs-cluster \
  --service-name orders-api \
  --desired-status STOPPED \
  --region ap-southeast-1
~~~

Pick a task ARN from the list and inspect:

~~~bash
aws ecs describe-tasks \
  --cluster demo-ecs-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/demo-ecs-cluster/0123456789abcdef0123456789abcdef \
  --region ap-southeast-1
~~~

Read **`lastStatus`**, **`desiredStatus`**, **`launchType`/`capacityProviderName`**, **`stopCode`**, **`stoppedReason`**, container **`exitCode`/`reason`**, **`healthStatus`**, and ENI attachments.

**Note:** Stopped tasks are only retained for a limited window in the ECS API; rely on CloudWatch logs/EventBridge/task-state history to investigate older incidents.

### 14.4. Inspect Scalable Targets and Policies

~~~bash
aws application-autoscaling describe-scalable-targets \
  --service-namespace ecs \
  --resource-ids service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1

aws application-autoscaling describe-scaling-policies \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1

aws application-autoscaling describe-scaling-activities \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1
~~~

Inspect **`MinCapacity`, `MaxCapacity`**, **`SuspendedState`**, policy types, metric targets, cooldowns, timestamps, and activity reasons. If no scalable target appears, the service is not registered with Application Auto Scaling even if the ECS Service is running.

### 14.5. Inspect Scheduled Actions

~~~bash
aws application-autoscaling describe-scheduled-actions \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1
~~~

Check cron/timezone/start/end, min/max, and scheduled changes. Schedules overlapping target tracking can cause unexpected task count shifts unless both mechanisms are analyzed together.

### 14.6. Inspect Capacity Providers

~~~bash
aws ecs describe-capacity-providers \
  --capacity-providers FARGATE FARGATE_SPOT \
  --region ap-southeast-1

aws ecs describe-capacity-providers \
  --capacity-providers demo-asg-provider \
  --include TAGS \
  --region ap-southeast-1
~~~

For ASG providers, inspect:

- **`autoScalingGroupProvider.autoScalingGroupArn`**.
- **`managedScaling.status` / `targetCapacity`**.
- **`managedTerminationProtection` / `managedDraining`**.
- **`ACTIVE`/`UPDATING`** status and cluster capacity provider associations.

For Managed Instances providers, use **`describe-capacity-providers`** with the schema supported by your current AWS CLI/docs; never assume **`autoScalingGroupProvider`** exists on every provider type.

### 14.7. Inspect the EC2 ASG If Using an ASG Capacity Provider

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names demo-ecs-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Max:MaxSize,Desired:DesiredCapacity,Instances:Instances,Tags:Tags}"

aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name demo-ecs-asg \
  --region ap-southeast-1
~~~

Check ASG `MaxSize`/`DesiredCapacity`, instance lifecycles, health, scaling activities, and the **`AmazonECSManaged`** tag. When managed scaling is enabled, never manually alter ASG policies to test without rollback plans and authorization.

### 14.8. Inspect CloudWatch Metrics

~~~bash
# List ECS Service metrics in CloudWatch.
aws cloudwatch list-metrics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=demo-ecs-cluster Name=ServiceName,Value=orders-api \
  --region ap-southeast-1

# List capacity provider cluster capacity metrics if present.
aws cloudwatch list-metrics \
  --namespace AWS/ECS/ManagedScaling \
  --metric-name CapacityProviderReservation \
  --region ap-southeast-1

# Inspect related CloudWatch alarms.
aws cloudwatch describe-alarms \
  --alarm-name-prefix TargetTracking-service \
  --region ap-southeast-1
~~~

Not all metrics exist when an ECS Service has zero running tasks or when extra monitoring isn't enabled. Verify exact **namespace, dimensions, metric resolution, and time window** when querying history.

### 14.9. Commands Intentionally Omitted Here

Mutating operations such as **`update-service`**, **`register-scalable-target`**, **`put-scaling-policy`**, **`update-capacity-provider`**, **`put-cluster-capacity-providers`**, or editing ASGs **alter live infrastructure and cost** and are excluded from this read-only lab.

In managed environments, production changes should go through peer-reviewed IaC with testing and rollback plans.

## 15. Troubleshooting Table

| Symptom | Possible Causes | How to Verify / Fix |
| --- | --- | --- |
| **High CPU yet `desiredCount` doesn't increase.** | Scalable target not registered, missing policy, alarm missing data, `MaxCapacity` reached, scaling suspended. | Describe scalable targets/policies/activities, CloudWatch metrics/alarms. |
| **Desired 10 but Running 6.** | Compute shortage, `FARGATE_SPOT` unavailable, EC2 lacks placement resources, image pull/startup error. | ECS service events, `stoppedReason`, capacity providers, and ASG. |
| **EC2 ASG fails to scale out.** | Managed scaling disabled, tasks don't use provider strategy, ASG `MaxSize` reached, tasks fit no instance type. | Describe capacity provider/ASG, `CapacityProviderReservation`, placement failures. |
| **ASG grows yet tasks stay `PROVISIONING`/`PENDING`.** | Instances haven't joined ECS, insufficient CPU/RAM/ENIs, wrong AZ/placement, agent/AMI/capacity issue. | ECS container instances, agent logs, task placement, and ASG activities. |
| **No scale-in despite low CPU.** | Memory policy blocking scale-in, `MinCapacity`, cooldown, active deployment, missing metric. | Check all target tracking policies, deployment state, and events. |
| **Excessive repeated scale-outs.** | Slow startup, too-short cooldown, metric lag, DB bottleneck, bad readiness check. | Task launch timeline, metrics, ALB, DB/CloudWatch logs. |
| **Spot tasks get stopped.** | Spot interruption or capacity shortage. | ECS task state change/EventBridge, `stoppedReason`, `FARGATE`/Spot mix. |
| **Fargate Spot isn't replaced by On-Demand Fargate.** | Spot capacity does not auto-fallback; capacity provider strategy defines separate weights. | Check `base`/`weight`, consider an on-demand baseline or separating services. |
| **Task `RUNNING` yet ALB returns 5xx.** | Container not ready, ALB target unhealthy, wrong SG/port, app/DB error. | Target group health, service networking, app logs, DB. |
| **During deployment, task count exceeds `desiredCount`.** | Rolling deployment temporarily keeps old and new tasks per `maximumPercent`. | Describe deployments and deployment configuration. |
| **Fails to scale from zero.** | CPU/memory metrics emit nothing with zero tasks; policy sees no demand signal. | Use queue-depth/independent custom metric; test scaling from 0. |
| **Costs climb while traffic stays flat.** | Over-provisioned tasks, high `MinCapacity`, excess ASG headroom, oversized task CPU/RAM, Spot churn/retries. | Billing, CloudWatch, task counts, capacity reservation, and scaling activities. |

### 15.1. Quick Decision Tree

~~~mermaid
flowchart TD
    A["App needs more capacity"] --> B{"Did DesiredCount increase?"}
    B -->|"No"| C["Check Application Auto Scaling metric / policy / min-max / suspended"]
    B -->|"Yes"| D{"Did RunningCount keep up?"}
    D -->|"No"| E{"Which capacity type is used?"}
    E -->|"Fargate"| F["Check Spot capacity, quotas, networking, image pull, task stoppedReason"]
    E -->|"EC2"| G["Check ASG managed scaling, reservation, resource fit, agent, ASG MaxSize"]
    E -->|"Managed Instances"| H["Check provider status, compatibility, capacity/placement"]
    D -->|"Yes"| I{"Are tasks healthy and latency improving?"}
    I -->|"No"| J["Check ALB/DB/IO, errors, readiness, deployments, downstream"]
    I -->|"Yes"| K["Keep tracking p95, cost, cooldowns, and scale-in"]
~~~

**Diagnostic tip:** Always ask three questions in exact order: (1) **did the service ask for more tasks?** (2) **could ECS launch those tasks?** (3) **once running, did those tasks actually serve business traffic?**

## 16. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Capacity providers scale task counts based on CPU." | Capacity providers manage **where/how compute runs** tasks; Service Auto Scaling changes **`desiredCount`**. |
| "Once Service Auto Scaling exists, EC2 scales automatically." | EC2 requires an ASG capacity provider with managed scaling or another host-scaling mechanism. |
| "Raising `desiredCount` guarantees `runningCount` rises right away." | Requires free capacity, compatible task definitions, working image/network, and passing health checks. |
| "`targetCapacity` 80% keeps EC2 CPU under 80%." | It targets **`CapacityProviderReservation`**, not CPU utilization. |
| "When Fargate Spot runs out, ECS falls back to Fargate." | No guaranteed automatic fallback exists; design an intentional on-demand baseline or switchover. |
| "Weight 1:3 means exactly 25%/75% of all tasks." | **`base`** is allocated first; weights guide the remaining tasks and vary with placement/availability. |
| "You can mix `FARGATE` and EC2 ASG providers in one strategy." | A single strategy cannot mix **different capacity provider families**, though a cluster may host multiple families. |
| "Omitting `weight` in the CLI defaults to 1." | The API/CLI typically defaults `weight` to **0**; specify explicitly, unlike the console. |
| "Scale-to-zero CPU target tracking wakes up on new requests." | At zero tasks, CPU metrics stop emitting; you need an external demand metric or trigger. |
| "Every service should have multiple CPU target policies." | Duplicate-metric policies on one target are invalid/redundant; track distinct meaningful metrics. |
| "Low CPU always triggers scale-in." | `MinCapacity`, cooldowns, active deployments, and other metric policies can block scale-in. |
| "Running two ECS tasks always equals high availability." | Also depends on AZ placement, health checks, load balancing, data stores, and capacity. |
| "ALB target health and ECS task `RUNNING` mean the same thing." | A `RUNNING` task may not be ready or healthy in its ALB target group. |
| "Managed termination protection guarantees no task is ever interrupted." | Spot interruptions, instance refreshes, and hardware failures can still terminate instances. |
| "Bigger `MaxCapacity` is always safer." | Must factor in quotas, backend limits, cost, and downstream bottlenecks. |
| "Auto Scaling solves every performance problem." | It never fixes memory leaks, slow SQL, broken networking, or non-idempotent apps. |

## 17. Real-World Scenarios with Solutions

### Scenario A — API Traffic Spikes During Peak Hours

**Problem:** An ECS Fargate Service running Orders API behind an ALB normally runs 3 tasks, hitting 85% average CPU at peak. The team wants automatic scaling while keeping at least two tasks to survive an AZ failure.

**Approach:**

1. Use `REPLICA` service across multiple subnets/AZs.
2. Register an Application Auto Scaling scalable target with **`MinCapacity` = 2**, **`MaxCapacity` = 20** (example).
3. Start with CPU target tracking around 60%, then refine via load testing.
4. Set cooldowns aligned with startup and ALB target health.
5. Keep an HA-sized `FARGATE` baseline; if adding Spot, use it only for interruption-tolerant margin and monitor availability.
6. Monitor ALB `TargetResponseTime`, 5xx, CPU/memory, DB connections, and cost.

**Explanation:** CPU can be a solid load signal, yet you still must verify extra tasks actually cut latency without overwhelming the database.

### Scenario B — ECS EC2 Reports Insufficient Memory Despite Idle ASG Instances

**Problem:** Service `desiredCount` = 12, `runningCount` = 8. The ASG capacity provider has eight EC2 instances. New tasks request 16 GiB RAM, while each EC2 instance has only 8 GiB total RAM.

**Solution:** No new task can fit the current instance type. Even if managed scaling adds 10 more 8 GiB EC2 instances, none can hold a 16 GiB task. **Select an instance type with enough RAM**, adjust task requests from real measurements, or split workloads/ASGs appropriately.

**Verification:** Inspect ECS service events, task definition resource requests, and EC2 container instance attributes—never look only at ASG `DesiredCapacity`.

### Scenario C — Production Web App Wants 30% of Tasks on Spot

**Problem:** An app runs 10 tasks; it accepts Spot for overflow capacity while keeping at least three tasks on-demand.

**Illustrative design:**

- `FARGATE` `base` = 3, `weight` = 7.
- `FARGATE_SPOT` `weight` = 3.

After `base`, the remaining seven tasks have an expected Spot share of **30% of the remainder**—roughly 2–3 Spot tasks here, **not exact 30% of all 10 tasks**.

To hit a different overall Spot ratio, calculate `base`/weights accordingly and remember AWS does not guarantee Spot capacity is always available. Validate with real load/placement tests.

### Scenario D — SQS Worker Wants to Save Cost When Idle

**Problem:** An ECS Fargate worker consumes SQS; zero messages arrive overnight, so `MinCapacity` = 0 is desired.

**Design:**

- Use a demand metric like **queue depth/backlog per task** published even when `running tasks` = 0.
- Target tracking/step scaling on CloudWatch signals with `MaxCapacity` capped to downstream limits.
- When backlog arrives, measure cold-start duration from 0.
- Maintain idempotency, visibility timeouts, DLQ, and graceful shutdown.

If cold-start latency violates SLAs, retain `MinCapacity` = 1 or a single on-demand baseline worker.

### Scenario E — Scale-In During Deployment Causes HTTP 502

**Problem:** A team runs a rolling update on an ECS Service and several long-running requests break mid-flight.

**Analysis:**

- Check ECS deployment type, `minHealthyPercent`/`maximumPercent`, task health, and service events.
- Application Auto Scaling normally pauses scale-in during supported deployments, yet the ECS scheduler still stops **old tasks as part of the rolling update**. That is not Auto Scaling scale-in.
- Check ALB deregistration delay, `SIGTERM`/`stopTimeout`, connection draining, in-flight requests, and app graceful shutdown.
- For queue tasks, rely on checkpoints, visibility timeouts, and idempotency.

**Lesson:** Distinguish **Application Auto Scaling scale-in** from **task replacement during a rolling deployment**.

## 18. Self-Check Questions

**Q1.** How do Service Auto Scaling and capacity providers differ?  
**Answer:** Service Auto Scaling adjusts `desiredCount`; capacity providers define compute sources and can manage infrastructure capacity for task placement.

**Q2.** Does `desiredCount` = 8 with `runningCount` = 4 prove the CPU scaling metric failed?  
**Answer:** No. The policy likely raised `desiredCount`; inspect task placement, capacity providers, images, networking, and startup errors.

**Q3.** What are the three common predefined target tracking metrics for ECS Services?  
**Answer:** `ECSServiceAverageCPUUtilization`, `ECSServiceAverageMemoryUtilization`, and `ALBRequestCountPerTarget` where supported.

**Q4.** When do two target tracking policies for CPU and Memory scale out?  
**Answer:** Whenever either policy requests scale-out; scale-in happens only when all scale-in-enabled policies qualify.

**Q5.** Could low CPU without scaling in during a deployment be normal behavior?  
**Answer:** Yes. Application Auto Scaling typically suspends scale-in while an ECS deployment is in progress (with exceptions by deployment controller).

**Q6.** With `MinCapacity` = 0 and zero running tasks, can a CPU metric wake the service?  
**Answer:** Never assume it can. You need a demand metric emitted externally from tasks, or another trigger mechanism.

**Q7.** What does `base` = 2 on `FARGATE` mean when `desiredCount` = 10?  
**Answer:** Prioritize placing at least two tasks on `FARGATE` first, then split the remaining eight tasks by `weight`.

**Q8.** In a strategy with `FARGATE` weight 1, `FARGATE_SPOT` weight 3, and no `base`, what is the theoretical split?  
**Answer:** Roughly 25% and 75% of weight-allocated tasks, not a strict guarantee at every instant.

**Q9.** When Fargate Spot lacks capacity, does ECS automatically switch to On-Demand Fargate?  
**Answer:** No. Configure an appropriate baseline/failover strategy; Spot does not guarantee availability.

**Q10.** Can one cluster include EC2, Fargate, and Managed Instances providers?  
**Answer:** Yes within supported features, though **one capacity provider strategy cannot mix different provider families**.

**Q11.** Does `CapacityProviderReservation` measure EC2 `CPUUtilization` or needed/available instance ratio?  
**Answer:** The ratio of required instances to currently running instances; not CPU utilization.

**Q12.** What is `targetCapacity` = 80% used for?  
**Answer:** Guides the ASG provider to preserve capacity headroom via `CapacityProviderReservation`, rather than capping CPU at 80%.

**Q13.** If ASG `MaxSize` = 2 and managed scaling wants six instances, does ECS raise `MaxSize` automatically?  
**Answer:** No. Configure suitable ASG bounds yourself; managed scaling never edits `MaxSize`.

**Q14.** How does managed termination protection differ from managed draining?  
**Answer:** Protection avoids picking instances with running tasks for certain scale-in terminations; draining gracefully empties/replaces tasks when an instance actually terminates.

**Q15.** Why is target tracking on SQS queue depth/worker useful?  
**Answer:** It measures pending work relative to active worker tasks, often far better than CPU for I/O-bound workers.

**Q16.** Does a `RUNNING` task guarantee it is receiving ALB traffic?  
**Answer:** No. Target registration, health checks, networking, and readiness still govern traffic delivery.

**Q17.** Which AWS CLI groups inspect the two scaling loops?  
**Answer:** Application Auto Scaling `describe-scalable-targets`/`policies`/`activities` for task counts; ECS `describe-capacity-providers` and ASG `describe-auto-scaling-groups` for infrastructure.

**Q18.** Why can latency remain poor even after scaling out?  
**Answer:** Bottlenecks may sit in the database/network/IO, ALB targets may not be healthy yet, startup may be slow, or task/app config may be flawed.

## 19. Summary and Deployment Checklist

**ECS Service Auto Scaling** answers **"how many tasks are needed?"**; **capacity providers** answer **"which compute runs the tasks, and does capacity keep up?"**.

When designing:

1. **Start from the workload:** measure CPU, memory, RPS, queue backlog, latency, and HA requirements.
2. **Pick Service Auto Scaling policies:** target tracking for proportional metrics, or step/scheduled/predictive as needed; set Min/Max and cooldowns.
3. **Pick the capacity family:** Fargate for serverless compute; Spot for interruption-tolerant work; EC2 ASG provider for host control; ECS Managed Instances for AWS-assisted EC2 management.
4. **Plan `base`/`weight`:** keep an on-demand baseline if needed; never mix families in one strategy and never expect rigid exact ratios.
5. **For EC2 providers:** enable managed scaling where appropriate and configure ASG `MaxSize`, `targetCapacity`, instance warmup, draining, and termination protection.
6. **Protect the app:** IAM task/execution roles, ECR/images, VPC/SGs, secrets/KMS, health checks, `SIGTERM`, and data backup/resilience.
7. **Observe all three outcomes:** `desiredCount` changes → `runningCount` catches up → healthy tasks genuinely improve business metrics.
8. **Test failure modes:** Spot interruptions, AZ loss, oversized tasks, IP exhaustion, image updates, scale-to/from-zero, DB saturation, and rollbacks.
9. **Control costs:** right-size tasks, set sane min/max, balance EC2 headroom/Spot, manage CloudWatch logs, data transfer, and budget alerts.

Effective autoscaling is never just about spawning tasks fast. It balances **availability, latency, resilience, security, infrastructure utilization, and cost** grounded in real telemetry.

### Official AWS Documentation

- [Automatically scale your Amazon ECS service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) — Service Auto Scaling, cooldowns, deployments, and scale-to-zero.
- [Target tracking scaling policies for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html) — predefined metrics and limitations.
- [Application Auto Scaling and Amazon ECS](https://docs.aws.amazon.com/autoscaling/application/userguide/services-that-can-integrate-ecs.html) — scalable targets, scaling methods, and service-linked roles.
- [Amazon ECS capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html) — families, strategies, and cluster defaults.
- [Amazon ECS Fargate capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html) — `FARGATE`/`FARGATE_SPOT`, `base`/`weight`, and interruptions.
- [Amazon ECS EC2 ASG capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html) — managed scaling and capacity constraints.
- [Amazon ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html) — reservation metric and ASG adjustments.
- [Control instances that ECS terminates](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-termination-protection.html) — managed termination protection.
- [ECS managed instance draining](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-draining.html) — graceful draining of EC2 instances.
- [ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) — CPU, memory, task/execution roles, and container runtime.
