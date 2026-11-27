# Launch Templates and Auto Scaling Groups

A website might need only two EC2 instances during off-peak hours yet require extra capacity when user traffic surges. Creating instances manually leads to inconsistent deployments, slow replacement of failed hosts, and error-prone version upgrades. An **EC2 Launch Template** defines the configuration used to launch new instances; an **Amazon EC2 Auto Scaling Group (ASG)** maintains and adjusts capacity across a fleet according to defined rules. When paired with an **Application Load Balancer (ALB)**, multiple instances can serve requests together, span multiple Availability Zones (AZs), and limit the blast radius of a single instance failure.

This lesson belongs to the **Load Balancing and Scaling** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects Regions/AZs, IAM, VPC, EC2, storage, databases, integration, and serverless so learners can select services, deploy applications safely, monitor performance, recover from incidents, and control costs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the roles of a **launch template**, **Auto Scaling Group**, **scaling policy**, and **load balancer/target group**.
2. Explain **minimum**, **desired**, and **maximum capacity** along with how a healthy fleet is maintained.
3. Configure a launch template with an **AMI**, instance type, security groups, IAM instance profile, user data, EBS, and **IMDSv2**.
4. Design a multi-AZ ASG attached to an ALB, configuring health checks and application startup windows.
5. Choose between **target tracking**, **step scaling**, **scheduled scaling**, and **predictive scaling** based on real workload patterns.
6. Understand how to apply **launch template versions**, **instance refreshes**, lifecycle hooks, scale-in protection, warm pools, and Spot Instances.
7. Inventory, monitor, test scale-out/scale-in, roll out new versions, and calculate total cost.

## 2. Launch Templates and ASGs Solve Two Different Problems

| Component | Question Answered | Primary Function |
|---|---|---|
| **Launch template (LT)** | **How should a new instance be launched?** | Defines EC2 configuration: AMI, instance type, network, SGs, instance profile, storage, user data, metadata options, etc. |
| **Auto Scaling Group (ASG)** | **How much capacity should run and where?** | Launches/terminates/replaces EC2 instances by min/desired/max, AZs, health, scaling policies, and capacity options |
| **Scaling policy** | **When should capacity increase or decrease?** | Decides desired capacity adjustments from metrics or schedules |
| **Target group + load balancer** | **Which healthy instance receives each request?** | Balances traffic and performs health checks at the ingress layer |
| **CloudWatch / scaling activities** | **Is the system behaving as expected?** | Metrics, alarms, scaling history, performance verification, and cost visibility |

~~~mermaid
flowchart TB
    U["Users"] --> ALB["Application Load Balancer"]
    ALB --> TG["Target group<br/>Health checks / routing"]
    LT["Launch template<br/>AMI, type, IAM, SG, EBS, IMDSv2"] -. "Configuration for new instances" .-> ASG["Auto Scaling Group<br/>Min / Desired / Max"]
    CW["CloudWatch metrics"] --> POL["Scaling policy"]
    POL --> ASG
    ASG --> A["EC2 instance<br/>AZ A"]
    ASG --> B["EC2 instance<br/>AZ B"]
    TG --> A
    TG --> B
~~~

For example, an ASG has **min = 2, desired = 2, max = 6**. When a load metric exceeds its target, a policy can raise desired capacity to 3 or 4 (depending on load and calculation); the ASG uses the launch template to launch new instances. When demand stays low long enough, the policy can trigger scale-in; the ASG terminates instances per its termination policies and settings. If an instance becomes unhealthy, the ASG can **replace** it to restore desired capacity even without any scaling policy.

**Avoid a common misconception:** A launch template by itself **neither launches** nor maintains instance counts. Likewise, an ASG does not deliver a complete application on its own: you still must design bootstrapping, networking, data persistence, security, request handling, and application state.

## 3. Designing a Launch Template

### 3.1. Properties to Define

| Property | Example | Design Decisions to Clarify |
|---|---|---|
| **AMI ID** | Pre-baked Linux app AMI | Patched AMI, matching architecture, reproducible build |
| **Instance type** | EC2 type sized for CPU/RAM | Compute, memory, network load, x86/ARM architecture |
| **Security groups** | Web/app SG | Required ports from ALB, management network, outbound rules |
| **IAM instance profile** | Role limited to reading config and writing logs | Least privilege using temporary credentials |
| **Storage** | Encrypted EBS gp3 | Size, throughput, IOPS, EBS encryption, durable data separation |
| **User data** | cloud-init script to configure/start app | Idempotency, bootstrap time, secret-fetching mechanism |
| **Metadata options** | **HttpTokens = required** | Enforce IMDSv2; review hop limit for containers |
| **Tags** | Environment, Owner, Application | Cost allocation, operations, tag-based access control |
| **Network interfaces** | SG, public IP, NIC settings where applicable | Must match ASG-selected subnets; avoid network constraints blocking launches |

The **AMI** can be a pre-built image (**golden AMI**) or a base OS image paired with **user data** to install the app. A golden AMI reduces instance readiness time and bootstrap variance. If every scale-out downloads gigabytes, compiles code, and updates OS packages over the Internet, scaling speed and reliability become heavily dependent on external networks and repositories.

### 3.2. Launch Templates Support Multiple Versions

Launch templates use **immutable versions**: modifying an AMI or setting creates a **new version** without altering prior versions. You can designate a version as **Default** or reference **Latest**, though production typically pins a **specific version number** to control exactly what the ASG launches.

| Reference | Meaning | Risks to Watch |
|---|---|---|
| **Version = 3** | ASG launches instances using version 3 | Easy traceability and controlled rollback |
| **Version = $Default** | ASG uses whichever version is marked Default at launch time | Changing Default silently alters future launches |
| **Version = $Latest** | ASG uses the newest existing version at launch time | Creating a new draft version could cause replacements/scale-outs to use unapproved config |

**Updating a launch template does not automatically replace running EC2 instances.** The ASG uses the referenced template only when launching **new instances**. To roll updates across the whole fleet, use **Instance Refresh**, a rolling deployment, or another controlled release workflow. To roll back, point the ASG back to a verified version and execute the update/verification workflow again.

### 3.3. Security Configuration at the Source

- Never embed **access keys**, passwords, or tokens in AMIs, user data, or Git. Use an instance profile and Secrets Manager or Systems Manager Parameter Store with least privilege.
- Enforce **IMDSv2** via **HttpTokens = required**; evaluate **HttpPutResponseHopLimit** for your topology, especially when running containers on EC2.
- Encrypt EBS volumes with appropriate KMS policies; lock down SGs so app instances accept traffic only from required components.
- Run applications with minimal OS privileges, apply patches regularly, and ship logs/metrics off-host.
- Write idempotent bootstrap scripts: any newly launched instance at any time must converge to the exact same healthy application state.

**Durable state:** business data must never live solely on the root EBS volume of an ASG instance. Instance replacement or termination can destroy local data. Store state in RDS, DynamoDB, S3, EFS, or another managed store, with separate backup and retention policies for persistent data.

## 4. Auto Scaling Groups: Min, Desired, Max, and Instance Lifecycle

### 4.1. The Three Capacity Bounds

| Parameter | Description | Example |
|---|---|---|
| **MinSize** | Minimum capacity the ASG maintains | 2 |
| **DesiredCapacity** | Target capacity the ASG works to achieve | 2 |
| **MaxSize** | Upper limit for capacity adjustments | 6 |

In homogeneous groups, these numbers usually represent instance counts. With **instance weighting / mixed instances**, capacity is measured in **capacity units** per configuration rather than physical host counts. Thus, a **desired capacity of 8** could be satisfied by four instances with weight 2.

An ASG operates via a **reconciliation loop**: comparing actual state against desired capacity, launching instances when short, terminating instances when in excess, and replacing unhealthy instances. If EC2 quotas or instance-type/AZ capacity are exhausted, reaching desired capacity can fail or stall, producing failed scaling activities that require investigation.

### 4.2. Multi-AZ and the Limits of HA

An ASG can span subnets across **multiple Availability Zones within the same Region**. The ASG attempts to balance capacity evenly across AZs within its constraints and available supply. When one AZ suffers an outage, continued availability depends on whether the ASG can launch capacity in surviving AZs, quotas/capacity, networking, ALB, and backend dependencies.

**A dual-AZ ASG + ALB** reduces the risk of a single EC2 or AZ failure; however, it does not guarantee application HA if the database, cache, sessions, DNS, or external dependencies live in only one AZ. Nor does an ASG provide **cross-Region DR** on its own.

Set **desired >= 2** for systems that must keep serving if one instance fails, and verify each surviving AZ can absorb the required load. Setting **min = 0** lets batch jobs or test environments scale down to zero to save cost, but live user-facing apps will be unavailable until capacity boots back up.

### 4.3. Basic Lifecycle

~~~mermaid
flowchart LR
    L["Policy or ASG requests launch"] --> P["Pending"]
    P --> H["Bootstrap + health checks"]
    H --> S["InService"]
    S -->|"Scale-in / unhealthy / refresh"| T["Terminating"]
    T --> X["Terminated"]
    H -->|"Launch fails"| F["Failed / retry launch"]
~~~

ASGs include finer-grained states for **lifecycle hooks**, **warm pools**, and other workflows. The diagram above shows only the simplified lifecycle of an instance.

## 5. Integrating ASG with Application Load Balancer

### 5.1. Role of the Target Group

ALB receives HTTP/HTTPS requests at its listener and routes them to a **target group**. An ASG can attach to an instance target group to automatically register new instances and deregister removed ones. ALB probes the configured **health check path** (such as **/health**) to determine which targets can accept traffic.

~~~mermaid
flowchart LR
    CLIENT["HTTPS Client"] --> ALB["ALB<br/>Public subnets AZ A/B"]
    ALB --> TG["Target group<br/>GET /health"]
    subgraph PRIVATE["Private application subnets"]
        A["EC2 AZ A"]
        B["EC2 AZ B"]
    end
    TG --> A
    TG --> B
    A --> DB["RDS / DynamoDB / S3<br/>data services"]
    B --> DB
~~~

In this diagram, the ALB resides in public subnets, EC2 instances reside in private subnets, and the EC2 security group accepts application-port traffic only from the ALB security group. If EC2 instances need to download packages or call AWS APIs during bootstrap, provision NAT gateways, VPC endpoints, or appropriate private routes.

### 5.2. EC2 Health Checks vs. ELB Health Checks

An ASG defaults to checking **EC2 status checks**, and can be configured to incorporate **Elastic Load Balancing (ELB)** health checks. If you attach a target group without configuring the ELB health check type, the ASG may not replace targets based on ALB unhealthy states the way you expect.

| Mechanism | What It Evaluates | Example |
|---|---|---|
| **EC2 status checks** | Underlying host/instance health | Instance fails hardware or OS status checks |
| **ALB target group health checks** | Whether the target responds on configured protocol, port, and path | HTTP 200 from **/health** |
| **ASG HealthCheckType = ELB** | Lets ASG factor ELB target health into replacement decisions | Persistently unhealthy targets get replaced |
| **Health check grace period** | Waiting window for newly launched instances to avoid premature unhealthy termination | Wait for application bootstrap to finish |
| **Default instance warmup** | Time for a new instance's metrics to stabilize during scaling | Prevent over-aggressive scaling while new hosts warm up |

**Grace period and instance warmup are two different parameters.** Grace period governs health-based replacement decisions, whereas instance warmup governs scaling calculations and metric stabilization for newly added capacity. Appropriate values depend on bootstrap duration, backend connection startup, and application behavior.

### 5.3. What Should a Good Health Endpoint Check?

A **/health** endpoint should reflect whether the application is genuinely ready to serve traffic, avoiding returning 200 merely because an HTTP listener process is alive. Systems distinguishing readiness levels often expose **/live** and **/ready**:

- **Liveness**: whether the process is running and capable of self-recovery.
- **Readiness**: whether the app has loaded configuration, bound listeners, and completed essential initialization to serve requests.

Do not tie health endpoints tightly to optional subsystems, or a slowdown in a secondary service could knock every target out of service simultaneously. Define precisely which failures truly prevent a target from serving.

### 5.4. In-Flight Connections and Graceful Draining on Scale-In

When an instance scales in, the ALB target group's **deregistration delay** gives in-flight requests/connections time to finish. Applications should also trap termination signals, stop accepting new work, and flush checkpoints when needed. For long-running background jobs, prefer lifecycle hooks and queues instead of relying solely on deregistration delay.

## 6. Scaling Policies

### 6.1. Target Tracking Scaling

**Target tracking** keeps a chosen metric near a target value by increasing or decreasing desired capacity; it is usually the best starting point for stateless web/app tiers. Examples:

- **ASGAverageCPUUtilization** targeting roughly **50%**.
- **ALBRequestCountPerTarget** reflecting request load per target when paired with an eligible ALB.
- A custom metric representing **queued messages / worker capacity**, when directly tied to throughput.

| Metric | When Appropriate | When Misleading |
|---|---|---|
| Average CPU | CPU-bound workloads | Apps bottlenecked on RAM, I/O, or external APIs |
| ALB requests per target | Cost per request is fairly uniform | Request complexity varies wildly |
| Queue backlog per instance | Queue-driven workers | Missing per-capacity normalization or highly variable task durations |
| Custom metric | Direct measure of real capacity utilization | Metric does not correlate with scaling efficiency or lags/gaps exist |

**Mental check:** if request volume doubles while each request is very lightweight, CPU may stay low so CPU-based tracking will not scale out as expected. Pick a metric correlated with actual capacity demand. Conversely, a slow database query stretches response times, yet launching more EC2 instances only opens more database connections and worsens the bottleneck.

Target tracking automatically computes both scale-out and scale-in actions. You can **disable scale-in** if the policy should only scale out while another mechanism handles scale-in; that choice directly affects cost.

### 6.2. Step Scaling and Simple Scaling

**Step scaling** adjusts capacity in tiered increments based on CloudWatch alarm breach magnitude—for example, adding a small increment slightly above threshold and a larger increment far above threshold. Configure alarms, step adjustments, and warmup times carefully.

**Simple scaling** also relies on alarms, using a traditional single cooldown window. For most modern workloads, AWS recommends evaluating target tracking or step scaling first for clearer response curves and warmup handling.

### 6.3. Scheduled Scaling

**Scheduled scaling** fits predictable cyclic loads: 8:00 AM business open, planned marketing campaigns, or 11:00 PM batch reporting. Policies adjust min/max/desired at scheduled timestamps. For recurring schedules, verify **timezones**, daylight saving transitions where applicable, and interaction with active capacity.

Example: raise desired to 4 every weekday ahead of peak hours, then return to 2 afterward. If demand spikes beyond forecasts, dynamic scaling can add capacity within configured bounds; avoid schedules that force capacity down while the app is still under heavy load.

### 6.4. Predictive Scaling

**Predictive scaling** forecasts load from historical metric data and can pre-provision capacity ahead of anticipated peaks in supported configurations. Ensure representative historical metrics exist and monitor forecast error—especially for new campaigns or shifting traffic patterns without history. Run in forecast-only mode to validate accuracy before enabling automatic scaling actions.

### 6.5. Warmup, Cooldown, and Avoiding Oscillation

When new instances launch, they need time to install dependencies, run any needed local initialization, connect to downstream services, and enter the target group. If scaling policies look only at overloaded old instances, they may keep scaling out repeatedly before new instances finish booting. Configure **default instance warmup** and observe real scaling behavior.

Do not set warmup too high for fast-booting apps (slowing down scaling response), nor too low for apps needing several minutes to boot (causing over-scaling or routing traffic to unready instances).

## 7. Mixed Instances, On-Demand, and Spot

An ASG can use a **Mixed Instances Policy** to combine multiple EC2 instance types and blend **On-Demand Instances** with **Spot Instances**. Goals include cost optimization, broader capacity availability, and handling traffic bursts.

### 7.1. When Should You Use Spot?

**Spot Instances** offer lower prices than On-Demand, but AWS can reclaim capacity when needed. Under standard EC2 Spot behavior, an interruption notice may be delivered roughly **two minutes** before the instance is terminated, stopped, or hibernated depending on configuration and support—though two minutes should never be treated as a guaranteed data-rescue window.

Workloads suited for Spot typically share these traits:

- Stateless APIs backed by redundant targets.
- Queue-processing workers with retries, checkpoints, and idempotent tasks.
- CI/build runners, batch analytics, or distributed jobs tolerant of losing a node.

Never rely on Spot as the sole compute tier for stateful data or non-interruptible tasks without an explicit recovery design.

### 7.2. Mixed Instances Policy

A mixed instances policy can configure:

| Component | Meaning |
|---|---|
| **Instance requirements / overrides** | List of instance types or attribute constraints like vCPU/RAM |
| **On-Demand base capacity** | Baseline capacity maintained strictly with On-Demand instances |
| **On-Demand percentage above base** | Share of capacity above the base kept as On-Demand |
| **Spot allocation strategy** | How Spot pools are selected by capacity availability or price/risk balance |
| **Instance weighting** | Capacity units assigned across different instance types |
| **Capacity Rebalancing** | Proactively launches replacements when Spot emits a rebalance recommendation |

Diversifying across multiple instance types and AZs improves capacity attainment. However, **do not mix CPU architectures (such as x86 and Arm) unless AMIs, binaries, or container images support both**. When using instance weighting, evaluate metrics like average CPU and requests/target alongside real capacity differences across instance sizes.

**Capacity Rebalancing** can launch replacement instances early when Spot signals elevated interruption risk; it does not guarantee new Spot capacity is always available or preserve in-flight app sessions. Pair it with request draining, checkpoints, retries, and an On-Demand base.

## 8. Lifecycle Hooks, Warm Pools, and Scale-In Protection

### 8.1. When Are Lifecycle Hooks Used?

**Lifecycle hooks** pause an ASG transition during launch or termination so an external workflow can run extra steps. Examples:

- **Launch hook:** install certificates, configure agents, register with a service catalog, warm caches, or verify readiness.
- **Terminate hook:** stop polling new jobs, drain queues, flush state, or ship logs/checkpoints.

Hooks use configured **heartbeat timeouts**, **global timeouts**, and **default results**. Failing to complete a hook properly leaves instances waiting too long or triggers unexpected terminations. Upon completion, signal **CONTINUE** or **ABANDON** as appropriate; effects differ between launch and terminate hooks. Test the full event flow with EventBridge, Lambda, SQS, or your chosen handler.

### 8.2. Warm Pools

A **warm pool** keeps a set of pre-initialized or stopped instances ready under supported modes to shorten scale-out latency for slow-bootstrapping apps. When capacity is needed, the ASG moves an instance from the warm pool into service.

Evaluate **EBS/storage costs and other ongoing billable resources**, resume latency, cache/credential staleness, and application logic after resume/start. Warm pools **do not eliminate warmup time entirely**, and not all workloads behave identically across stopped/hibernated/running pool states.

### 8.3. Instance Scale-In Protection

**Scale-in protection** shields a specific instance from termination during **scale-in events**. It helps when a worker is processing a batch job that cannot be interrupted cleanly. However, it is **not** absolute immunity from every termination cause: evaluate unhealthy instance replacement, Spot interruptions, instance refreshes, and manual/admin actions separately.

Do not enable protection permanently across the entire fleet, or the ASG cannot scale in, driving up costs and breaking scaling policies. Workers should clear protection once their task finishes or adopt queue/checkpoint patterns instead.

## 9. Application Updates and Instance Refresh

### 9.1. Why Do You Need Instance Refresh?

Suppose an ASG runs launch template **version 1** with an older AMI. You release a new AMI and publish **version 2**; existing instances from version 1 **are not automatically upgraded**. To roll out consistently, **Instance Refresh** replaces instances in controlled batches toward your desired launch template/version and preferences.

~~~mermaid
flowchart LR
    LT1["Launch template v1"] --> OLD["ASG running EC2 v1"]
    NEW["New AMI / config"] --> LT2["Launch template v2"]
    LT2 --> REF["Instance Refresh<br/>Healthy percentage limits"]
    OLD --> REF
    REF --> CAN["Replace instances in batches"]
    CAN --> HEALTH["Health checks + metrics"]
    HEALTH --> DONE["Entire ASG reaches target config"]
~~~

### 9.2. Controlled Release Workflow

1. Build a new AMI/application artifact, test booting it, and verify IAM, SGs, EBS, user data, and IMDSv2.
2. Create a new launch template version and diff it against the running version.
3. Select the ASG and define **desired configuration**, min/max healthy percentages, **instance warmup**, checkpoints, and readiness bake times.
4. Start the rolling refresh; monitor ASG status, target group health, HTTP 5xx, latency, and capacity.
5. On errors, cancel/roll back using supported mechanisms; verify **the old version can still boot cleanly** and schemas/data remain compatible.
6. Upon completion, audit all running instances/AMIs/LT versions and record the deployed release.

**Pick sensible healthy percentages:** if desired capacity is only 2 instances, small percentage differences dramatically affect how many instances remain in service. Factor in **MaxSize/quota headroom** and capacity to launch replacements before terminating old instances—especially for zero-downtime goals.

**Data and schemas:** instance refresh manages EC2 instances, not safe database migrations. When deployments include schema changes, apply backward-compatible changes, phased migrations, and independent rollback validation.

## 10. AWS CLI Lab: Illustrative Launch Template and ASG Creation

The commands below are **study templates**, not auto-executed scripts. Run them only in an authorized lab/account after checking IAM permissions, quotas, subnets, target groups, AMIs, and costs. Replace all placeholders with real values. The example assumes a Linux app with a pre-bootstrapped AMI, an ALB target group with working health checks, and two subnets across two AZs.

### 10.1. Create a Launch Template

Example lab input file **launch-template-data.json**:

~~~json
{
  "ImageId": "ami-REPLACE_WITH_VALID_AMI",
  "InstanceType": "t3.small",
  "SecurityGroupIds": [
    "sg-REPLACE_WITH_APP_SG"
  ],
  "IamInstanceProfile": {
    "Name": "app-instance-profile"
  },
  "MetadataOptions": {
    "HttpEndpoint": "enabled",
    "HttpTokens": "required",
    "HttpPutResponseHopLimit": 1
  },
  "BlockDeviceMappings": [
    {
      "DeviceName": "/dev/xvda",
      "Ebs": {
        "VolumeType": "gp3",
        "Encrypted": true,
        "DeleteOnTermination": true
      }
    }
  ]
}
~~~

AMI, security group, profile name, and **DeviceName** must match your chosen image and infrastructure; notably, different AMIs use different root device names. If running containers, check the hop limit instead of blindly copying `1` across environments.

~~~bash
aws ec2 create-launch-template \
  --region ap-southeast-1 \
  --launch-template-name web-app-lt \
  --version-description "web-app-v1" \
  --launch-template-data file://launch-template-data.json
~~~

Creating an LT stores only the template—it **does not launch any EC2 instances**. Verify the template and version afterward:

~~~bash
aws ec2 describe-launch-template-versions \
  --region ap-southeast-1 \
  --launch-template-name web-app-lt \
  --versions 1 \
  --query 'LaunchTemplateVersions[].[VersionNumber,VersionDescription,LaunchTemplateData.ImageId]' \
  --output table
~~~

### 10.2. Create a Dual-AZ ASG and Attach a Target Group

~~~bash
aws autoscaling create-auto-scaling-group \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --launch-template "LaunchTemplateName=web-app-lt,Version=1" \
  --min-size 2 \
  --max-size 6 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-REPLACE_A,subnet-REPLACE_B" \
  --target-group-arns "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/REPLACE_NAME/REPLACE_ID" \
  --health-check-type ELB \
  --health-check-grace-period 300 \
  --default-instance-warmup 180
~~~

Both subnets must be in **two distinct AZs** matching your network design. The target group must exist in the same VPC with a compatible target type and be referenced by an ALB listener. Values like **300 seconds** and **180 seconds** are illustrative: measure real bootstrap times to tune them. Your account must also have sufficient EC2 quotas and capacity.

### 10.3. Add Target Tracking Scaling

Example targeting roughly **50%** average CPU utilization:

~~~bash
aws autoscaling put-scaling-policy \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --policy-name cpu-target-50 \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":50.0}'
~~~

This policy helps only when CPU correlates with application capacity demand. It does not magically scale your database or downstream dependencies.

### 10.4. Inspect ASG Status and Scaling History

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --region ap-southeast-1 \
  --auto-scaling-group-names web-app-asg \
  --query 'AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Desired:DesiredCapacity,Max:MaxSize,Instances:Instances[].[InstanceId,LifecycleState,HealthStatus]}' \
  --output json

aws autoscaling describe-scaling-activities \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --max-items 20 \
  --output json
~~~

Also inspect **ALB target health** and application metrics to confirm instances actually serve requests—not merely that ASG marks them **InService**.

### 10.5. Create a New Version and Start Instance Refresh

After creating version 2 of the launch template through an approved workflow, an example refresh command:

~~~bash
aws autoscaling start-instance-refresh \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --desired-configuration '{"LaunchTemplate":{"LaunchTemplateName":"web-app-lt","Version":"2"}}' \
  --preferences '{"MinHealthyPercentage":90,"InstanceWarmup":180}'
~~~

This command **replaces running EC2 instances**, so evaluate healthy counts, capacity/quotas, termination policies, and rollback first. For very small groups, check how healthy percentages round and how long replacement instances take to become ready. Monitor progress with:

~~~bash
aws autoscaling describe-instance-refreshes \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --output table
~~~

## 11. Monitoring Health, Scaling, and Cost

### 11.1. Metrics to Track

| Group | Metrics / Signals | Decision Impact |
|---|---|---|
| **ASG capacity** | **GroupDesiredCapacity**, **GroupInServiceInstances**, **GroupPendingInstances**, **GroupTerminatingInstances** | Is desired met, or are instances stuck launching/terminating? |
| **ASG scaling activities** | StatusCode, StatusMessage, scaling failure reasons | Missing quotas, capacity, AMI, IAM, or network config errors |
| **EC2** | CPUUtilization, StatusCheckFailed, custom memory/disk metrics if needed | Locate bottlenecks, host failures, and right-sizing opportunities |
| **ALB target group** | HealthyHostCount, UnHealthyHostCount, TargetResponseTime, HTTPCode_Target_5XX_Count | Are targets ready and meeting SLOs? |
| **Traffic** | RequestCount, RequestCountPerTarget, app-layer p95/p99 latency | Scale to demand and catch error spikes |
| **Cost** | EC2 hours, EBS, ALB LCUs, data transfer, CloudWatch, NAT, Spot | Evaluate cost efficiency after enabling scaling |

Some **ASG group metrics** require explicitly enabling metric collection. EC2 memory utilization is not a default built-in metric for every instance and often requires the **CloudWatch Agent / custom metrics**. Design alarms to distinguish **insufficient capacity**, **unhealthy resources**, **application bugs**, and **ineffective scaling**.

### 11.2. How to Test Scaling Properly

1. Capture a baseline: desired count, healthy target count, CPU/requests, latency, and hourly cost.
2. Apply controlled load in a lab and watch the target metric, scaling activities, Pending/InService EC2 counts, and time until targets turn healthy.
3. Verify the system meets SLOs after scale-out and confirm downstream backends hold up.
4. Stop the load and confirm graceful scale-in without killing in-flight worker tasks.
5. Verify ASG replaces an unhealthy instance; drill a simulated AZ outage using an approved procedure.
6. Measure total recovery time, dropped requests, error rates, and cost deltas, then tune policies accordingly.

### 11.3. Estimating Realistic Costs

**EC2 Auto Scaling adds no separate fee merely for creating an ASG under standard service pricing**, but you pay for **On-Demand/Spot EC2 instances, EBS, ALB, CloudWatch, network/data transfer, NAT gateways, KMS, log storage**, and supporting services per applicable pricing. To estimate:

- Determine the **baseline fleet size** and hours kept running even during low traffic.
- Estimate hours spent at elevated load tiers and added instance counts.
- Factor in **instance warmup**, warm pools, scale-in protection, and policies that disable scale-in.
- Include spare capacity for surviving an AZ outage, Spot usage potential, and replacement overhead.
- Compare against serverless or container options like ECS Fargate or Lambda if suitable, without deciding solely on hourly EC2 rates.

## 12. Common Failures and Diagnostics

| Symptom | Possible Causes | Where to Check |
|---|---|---|
| ASG cannot launch instances | Invalid AMI/instance type, quota, insufficient capacity, bad permissions/launch template | **Scaling activities**, EC2 quotas, launch template version, IAM instance profile |
| Instances join ASG and get replaced repeatedly | Failing health checks, slow bootstrap, grace period too short | **ALB target health reason**, EC2 status, app logs, startup timing |
| ALB returns 503 | No healthy targets or misconfigured routing/target group | Listeners, target registration, health path, SGs, ports |
| EC2 `InService`, yet requests fail | App not ready yet or ASG ignoring ALB target state | `HealthCheckType`, target group health, logs |
| High CPU, yet no scale-out | Missing scaling policy, hit MaxSize, wrong metric, suspended process, or missing data | Scaling policy, group limits, CloudWatch metrics, suspended processes |
| Heavy scale-out, yet latency stays high | Bottleneck in DB, I/O, downstream service, or sticky sessions | Tracing, DB connections, app metrics, load tests |
| Scale-in cuts off jobs mid-flight | Missing graceful shutdown, lifecycle hooks, or checkpoints | Termination handling, queue retries, targeted protection |
| New LT version created, yet ASG still runs old AMI | ASG pinned to old version; no instance refresh executed | ASG launch template version, running instance AMIs |
| ASG unexpectedly runs mixed versions | Using **$Latest/$Default** or incomplete rollout | Launch template version per instance, scaling activities, refresh status |
| Spot instances vanish | Spot interruption or depleted capacity pool | Spot events, Capacity Rebalancing, On-Demand base |
| Costs stay high after traffic drops | Long warmup/cooldown, high MinSize, stuck protection, scale-in disabled | Desired vs. Min/Max, group metrics, warm pool, and billing |
| Scale-out fails in private subnets | User data needs Internet without NAT/endpoints, or wrong secret policy | Cloud-init logs, routes, VPC endpoints, IAM, and DNS |

## 13. Practical Scenarios

### Scenario A — Web API with Variable Traffic

A Java app runs on EC2 and scales horizontally across multiple instances. Sessions and persistent data live outside EC2. Traffic surges during midday hours; currently only a single instance runs.

**Question:** what is an appropriate scaling architecture?

**Hint:** create a launch template with a tested AMI, least-privilege role, IMDSv2, security groups, and encrypted EBS. Create a dual-AZ ASG with min/desired starting at 2, attach an ALB target group with a **/ready** health check, and configure target tracking on CPU or request count as appropriate. Load-test both the app and backend dependencies during scale-out.

### Scenario B — New AMI Built, Yet Zero Instances Updated

The team builds AMI v2 and adds launch template version 2, yet every instance in the ASG is still running the old version.

**Question:** why, and what needs to be done?

**Hint:** creating a new launch template version does not replace existing instances. Check which version the ASG references, update the desired configuration, and run a batched **instance refresh**. Verify target health, warmup duration, capacity headroom, and rollback readiness.

### Scenario C — Using Spot to Reduce Cost

An image-processing worker pulls tasks from SQS and supports retries. The team wants lower compute costs without losing jobs when Spot instances are interrupted.

**Question:** how should the design change?

**Hint:** configure a mixed instances policy with an appropriate On-Demand base, multiple Spot pools/AZs, and Capacity Rebalancing where helpful. Ensure workers consume messages idempotently with proper visibility timeouts, checkpoints, and graceful shutdown so reclaimed jobs retry cleanly. Scale on queue backlog per instance, measuring capacity by real throughput rather than raw host count.

### Scenario D — Scaling Out, Yet the App Remains Slow

ASG scales from 2 to 6 EC2 instances; CPU per host stays low, yet p95 latency does not improve. The database shows rising connection counts and long query times.

**Question:** should you raise MaxSize to 20?

**Hint:** not yet. Investigate database bottlenecks, queries/indexes, connection pooling, caching, and traces. Adding more EC2 instances can overwhelm the database further; optimize or scale the bottleneck tier before changing scaling bounds.

### Scenario E — Scale-In Drops Active Tasks

An application processes a file for 15 minutes per EC2 instance. When CPU drops, the ASG scales in and terminates a busy host before results are saved.

**Question:** should you fix this by raising MinSize?

**Hint:** raising MinSize does not solve the root architectural issue. Use queues, checkpoints, idempotent retries, lifecycle hooks, or per-instance scale-in protection while a task is active, paired with graceful shutdown and adequate wait windows. Account for timeouts, costs, and sudden Spot/instance failures.

## 14. Production Readiness Checklist for Launch Templates and ASGs

- [ ] Reproducible, change-controlled **AMI and launch template versions**.
- [ ] Properly configured IAM instance profile, SGs, EBS encryption, IMDSv2, and secret retrieval.
- [ ] Verified idempotent user data/bootstrap with zero unique business state kept on root disks.
- [ ] Chosen **MinSize, DesiredCapacity, and MaxSize** grounded in load profiles, SLOs, and recovery needs.
- [ ] Deployed ASG across multiple AZs as required and tested single-AZ / single-instance failures.
- [ ] Attached ALB/target group in the matching VPC with proper health check path, grace period, and warmup.
- [ ] Selected scaling metrics genuinely correlated with capacity rather than defaulting blindly to CPU.
- [ ] Verified lifecycle hooks, graceful shutdown, connection draining, scale-in protection, and warm pools if used.
- [ ] Validated mixed instances/Spot support, interruption handling, and On-Demand fallback capacity if applicable.
- [ ] Defined a release workflow for **new versions + instance refresh + rollback**.
- [ ] Set up CloudWatch metrics/alarms, scaling activities, and logs for troubleshooting.
- [ ] Benchmarked scale-out/scale-in, health replacement, and TCO across load scenarios.

## 15. Summary

A **launch template** defines how an EC2 instance is built; an **Auto Scaling Group** maintains and adjusts capacity; **scaling policies** decide when to scale out or in; and **ALB with target groups** routes traffic to healthy instances. Safe scaling requires coordinating **Multi-AZ placement, stateless design, health checks, warmup, least-privilege IAM, version pinning, instance refresh, clean shutdowns, and monitoring**. Simply adding more EC2 instances will not fix bottlenecks in databases or downstream dependencies.

### Official AWS Documentation for Reference During Implementation

- [EC2 Launch Templates](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-templates.html) — configuring and managing template versions.
- [Create an Auto Scaling Group using a launch template](https://docs.aws.amazon.com/autoscaling/ec2/userguide/create-asg-launch-template.html) — linking templates to ASGs.
- [How Amazon EC2 Auto Scaling works](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html) — desired capacity, instance replacement, and AZ balancing.
- [Health checks for Auto Scaling instances](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-checks-overview.html) — health check sources.
- [Attach a load balancer to an Auto Scaling Group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/attach-load-balancer-asg.html) — target groups, ELB health, and ALB integration.
- [Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html) — target metrics and instance warmup.
- [Step scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-simple-step.html) — alarms and step adjustments.
- [Auto Scaling groups with multiple instance types](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-mixed-instances-groups.html) — mixed instances, On-Demand, and Spot.
- [Instance refresh](https://docs.aws.amazon.com/autoscaling/ec2/userguide/asg-instance-refresh.html) — updating and replacing fleets.
- [Lifecycle hooks](https://docs.aws.amazon.com/autoscaling/ec2/userguide/lifecycle-hooks.html) — custom actions during launch and termination.
- [Monitor Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/monitoring-overview.html) — metrics, events, and activity logs.
- [AWS Pricing Calculator](https://calculator.aws/) — estimating EC2, EBS, ALB, and related service costs.
