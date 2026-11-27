# Instance Lifecycle, Stop, Hibernate, and Terminate in Amazon EC2

An Amazon EC2 instance does not remain in the `running` state forever. Throughout application deployment and operations, an instance may be launched, rebooted, temporarily stopped, hibernated to preserve RAM contents, or permanently terminated. Each action affects **data, IP addresses, running processes, attached resources, recovery behavior, and your AWS bill** differently.

This lesson belongs to the **EC2 Instances** chapter of the **CLOUD_PROVIDERS_AWS** module. Managing the EC2 lifecycle properly is foundational for running Java/Spring Boot applications on VPC infrastructure, integrating IAM and EBS, connecting to RDS/S3, monitoring with CloudWatch, building resilient architectures, auto-scaling, and controlling costs.

> **Key takeaway:** Both `stop` and `hibernate` transition an EC2 instance to `stopped`, differing in whether RAM is preserved; `terminate` ends the instance permanently. Stopping compute billing does not mean all AWS charges disappear.

## 1. Learning Outcomes

After completing this lesson, learners will be able to:

1. Explain the six EC2 instance states: `pending`, `running`, `stopping`, `stopped`, `shutting-down`, `terminated`.
2. Compare `reboot`, `stop/start`, `hibernate/start`, and `terminate`.
3. Clearly distinguish **EBS-backed root volumes** from **instance store-backed root volumes** when deciding to stop an instance.
4. Predict what is **preserved or lost**: RAM, EBS volumes, instance store, instance ID, private/public IPs, and Elastic IPs.
5. State the prerequisites for enabling hibernation at launch time: AMI, instance type, RAM, root EBS, encryption, and disk capacity.
6. Inspect `DeleteOnTermination`, stop protection, termination protection, and Auto Scaling impacts.
7. Use the Console/CLI to **observe** states, verify the right account/Region, and troubleshoot common errors.
8. Decide whether to stop, hibernate, or terminate based on the application, recovery time, data safety, cost, and automation readiness.

## 2. Components That Determine What Survives

An EC2 instance comprises several layers whose lifecycles are not identical:

| Component | Role | Remember on State Changes |
|---|---|---|
| **Instance ID** (`i-...`) | Logical identifier of the EC2 instance | Usually preserved across reboot, stop/start, hibernate/start; a terminated instance cannot be restarted |
| **AMI** | Template to launch new instances | AMIs help **create** new instances; not a snapshot of live RAM/running app state |
| **Root volume** | Holds the OS and boot data | Can be EBS or instance store; root type determines stop/hibernate eligibility |
| **EBS data volumes** | Block storage decoupled from the compute host | Data normally persists across stop; on terminate depends on `DeleteOnTermination` |
| **Instance store volumes** | Local disks attached to the physical host | Data is **lost** on stop, hibernate, or terminate; usually preserved across reboot |
| **Elastic Network Interface (ENI)** | VPC connectivity, private IPv4, IPv6, Security Groups | Usually kept on stop/hibernate; after terminate, retention/deletion depends on attachment/lifecycle |
| **Auto-assigned Public IPv4** | Non-static public IP assigned by EC2 | Usually lost on stop/hibernate; a different IP may be assigned on start |
| **Elastic IP** | Separately allocated static IPv4 address | Can remain associated across stop/start; may still incur charges |
| **RAM, processes, sockets** | Instantaneous runtime state | Lost on stop/reboot; hibernate attempts to save RAM to EBS for resume |
| **IAM instance profile** | Role supplying temporary credentials to workloads | Attachment usually persists; issued credentials may expire during long stops |

Do not confuse data on an **EBS filesystem** with data in **RAM**, **instance store**, or an external RDS database. Stopping EC2 does not automatically create snapshots/backups, back up data to S3, or guarantee that an actively writing app flushes cleanly before a sudden shutdown.

## 3. Lifecycle Diagram of an EC2 Instance

AWS publishes six primary states:

~~~mermaid
stateDiagram-v2
    [*] --> pending: Launch instance
    pending --> running: Boot succeeds
    running --> stopping: Stop or Hibernate
    stopping --> stopped: Stop completes
    stopped --> pending: Start instance
    running --> shutting_down: Terminate instance
    stopped --> shutting_down: Terminate instance
    shutting_down --> terminated: Terminate completes
    terminated --> [*]
    state "shutting-down" as shutting_down
~~~

**Important observation:** AWS **has no separate `hibernated` state** in the standard state list. Both stop and hibernate transition through `stopping` to `stopped`. The attribute `HibernationOptions.Configured = true` indicates the instance **was configured with hibernation support at launch**, not that the most recent stop actually saved RAM successfully.

### 3.1. Meaning and Billing by State

| State | What Is Happening? | Compute Instance Usage |
|---|---|---|
| `pending` | Instance is launching or restarting | Compute billing by state not yet active |
| `running` | Instance is running, usable once OS/network are ready | Compute billing active |
| `stopping` | Instance is shutting down or hibernating | Normal stop does not bill compute; **hibernate still incurs compute charges while `stopping`** |
| `stopped` | Instance is stopped, not serving traffic like a running host | No compute billing; **EBS and other resources may still incur charges** |
| `shutting-down` | Instance is being terminated | No compute billing by state |
| `terminated` | Instance is permanently terminated | No compute billing; check for leftover resources |

For On-Demand configurations eligible for per-second billing, each transition from `stopped` to `running` incurs a **one-minute minimum**; afterward, billing accrues per actual usage time. Windows, Spot, Dedicated Hosts, and Savings Plans/Reserved Instances have specific billing terms; consult the applicable pricing and commitment rules.

## 4. Quick Comparison: Reboot, Stop, Hibernate, and Terminate

| Question | Reboot | Stop → Start | Hibernate → Start | Terminate |
|---|---|---|---|---|
| Can the same instance ID be reused? | Yes | Yes | Yes | **No** |
| Intermediate EC2 states | Usually stays `running` | `stopping → stopped → pending` | `stopping → stopped → pending` | `shutting-down → terminated` |
| Preserves RAM contents? | No | No | **Yes**, if hibernation succeeds | No |
| Preserves root EBS data? | Yes | Yes | Yes | Depends on `DeleteOnTermination`, typically deleted by default |
| Preserves other EBS volume data? | Yes | Yes | Yes | **Depends on each volume and how it was attached** |
| Preserves instance store data? | Usually yes | **No** | **No** | **No** |
| Preserves private IPv4/IPv6 on ENI? | Yes | Yes | Yes | Original instance is gone |
| Preserves auto-assigned public IPv4? | Yes | Usually no | Usually no | No |
| Can instance type be changed? | Not while running | Yes in normal stopped state | **Do not arbitrarily change** while hibernated | No |
| Compute billing when inactive | Still billed while running | Not billed while stopped | Not billed while stopped; billed while hibernating/stopping | Not billed once in shutting-down |
| When to choose? | OS maintenance | Pause restartable applications | Preserve environments needing RAM/process state | Permanently retire |

**Reboot is not stop/start.** A reboot typically happens on the same physical host and preserves instance store and public IPv4. Stop/start can move the instance to a different physical host, losing instance store data and auto-assigned public IPv4 addresses. Hibernate behaves similarly to stop at the infrastructure layer, adding the step of writing RAM to EBS.

## 5. Stop and Start: Pausing Compute While Keeping EBS

### 5.1. Prerequisites for Stopping

An instance must use **Amazon EBS as its root volume** to support `StopInstances`/`StartInstances`. Instances with an instance store-backed root volume cannot be stopped/started via standard EC2 stop; you must redesign around AMI/EBS or terminate and redeploy per procedure.

Before stopping, verify:

1. Has the application drained connections, paused traffic, and committed active transactions?
2. Do logs, caches, uploads, or DB transactions hold unpersisted data only in RAM/instance store?
3. Are the EBS volumes to retain present and showing healthy I/O?
4. Does the instance belong to an **Auto Scaling group**, ECS capacity/cluster, or another automated instance manager?
5. Are there uptime/SLA requirements, maintenance windows, or load balancer/DNS dependencies?

### 5.2. What Does EC2 Do When Stopping?

Normally, EC2 sends a shutdown signal to the guest OS so services shut down gracefully. If the OS does not shut down cleanly within a few minutes, EC2 may perform a hard shutdown. Afterward:

- `running → stopping → stopped`.
- Compute capacity is released; when started again, the instance may run on a **different physical host**.
- **RAM is lost**; processes must restart when the OS boots.
- Data on **instance store is lost**.
- Root and data EBS volumes **are preserved** and usually remain logically attached.
- Primary/private IPv4, IPv6, ENIs, and attached Elastic IPs **are preserved**.
- Auto-assigned public IPv4 addresses **are released**; starting again may assign a new IP.
- Certain attributes can be modified while stopped, such as instance type, subject to AWS limits.

### 5.3. What Happens on Start?

`StartInstances` transitions the instance from `stopped → pending → running`. AWS reattaches EBS and ENIs, the OS **boots fresh**, daemons initialize, user data runs per cloud-init/EC2Launch configuration, and services start according to their own setup.

The `running` state only indicates EC2 has booted at the service layer. To assess readiness to serve traffic, distinguish:

- **System status checks:** health of AWS host/network infrastructure.
- **Instance status checks:** health of the guest OS and instance reachability.
- **Application readiness:** whether Spring Boot has opened its port, connected to RDS, handled migrations, warmed caches, and registered with the load balancer.

Route traffic back only after application-level health checks pass. A `running` instance whose Java process is still starting up will return connection errors.

### 5.4. Cost Caveats When Stopping to Save Money

Stopping is a common way to cut compute costs for dev/test environments used only during business hours. However:

- **EBS volumes** still incur charges for provisioned capacity/IOPS/throughput depending on type.
- **Public IPv4 and Elastic IPs** may continue incurring charges under current pricing policies.
- Snapshots, load balancers, NAT gateways, databases, and related services do not stop automatically.
- Long-term Savings Plans/Reserved Instance commitments remain financially binding under their purchase terms.
- With EC2 Auto Scaling, manually stopping an instance can cause the group to mark it unhealthy and **launch a replacement**, defeating the cost savings.

Therefore, to shut down a dev environment for savings, account for the **entire deployment unit**: Auto Scaling desired capacity, databases, load balancers, and supporting resources, managed under a clear start/stop schedule.

## 6. Hibernate: Saving RAM to EBS Before Stopping

### 6.1. How It Works

**EC2 hibernation** works like *suspend-to-disk*:

1. EC2 signals the OS to hibernate.
2. The OS freezes processes and writes **RAM** contents to the **encrypted EBS root volume**.
3. The instance transitions through `stopping` to `stopped`; EBS volumes persist, while instance store data is lost.
4. On start, EC2 provisions the host/instance; the OS reloads saved RAM data and resumes processes from their prior state.

~~~mermaid
flowchart LR
    R["running: OS + JVM + RAM"] --> H["hibernate: write RAM to EBS root"]
    H --> S["stopped: compute not running"]
    S --> P["start: reload RAM from EBS"]
    P --> R2["running: resume process state if resume succeeds"]
~~~

Hibernation helps when software takes a long time to start, load models, warm large datasets in RAM, or initialize workspaces. However, **preserving RAM does not preserve external connections**: TCP sockets, DNS entries, STS session tokens, IAM credentials, database connections, TLS session keys, and timeouts may have expired while the instance slept. Upon resume, applications must **reconnect, refresh credentials, and revalidate health**.

### 6.2. Prerequisites

| Prerequisite | Requirement |
|---|---|
| Enabled at launch | Must **enable hibernation when creating the instance**; cannot be enabled later on an existing instance |
| Root volume | Must be **EBS-backed** |
| Encryption | **Root EBS must be encrypted**, since RAM can hold sensitive data |
| Root volume size | Must be large enough for the OS, application data, **and RAM contents** |
| EBS volume type | Supported types include `gp2`, `gp3`, `io1`, `io2` per AWS documentation |
| AMI and OS | Must use an AMI supporting hibernation; some distros require extra configuration steps |
| Instance type | Only AWS-supported families/types; bare-metal is unsupported |
| RAM | Under current AWS limits: **Linux less than 150 GiB**, **Windows up to 16 GiB** |
| Lifecycle management | Not supported for instances in an **Auto Scaling group** or **used by Amazon ECS** |

You can view hibernation-capable instance types in EC2 Console → Instance Types by filtering **On-Demand Hibernation support**, or via CLI:

~~~bash
aws ec2 describe-instance-types \
  --region ap-southeast-1 \
  --filters Name=hibernation-supported,Values=true \
  --query 'InstanceTypes[].InstanceType' \
  --output text
~~~

The supported list **changes by Region/AMI and over time**, so never assume every EC2 type supports hibernation.

### 6.3. Enabling Hibernate at Launch

In **EC2 Console → Launch instance**, pick an eligible AMI and instance type, configure a sufficiently large encrypted EBS root volume, and set **Advanced details → Stop - Hibernate behavior → Enable** before launching.

For API/CLI, configure hibernation at launch using `--hibernation-options Configured=true` on `run-instances` alongside a qualifying root volume. Do not attempt to alter `HibernationOptions` on an already-created instance, as AWS does not support enabling hibernation post-launch.

### 6.4. Hibernating a Configured Instance

The AWS CLI uses `stop-instances` with `--hibernate`. Example syntax **that affects a real instance**:

~~~bash
# ILLUSTRATIVE ONLY: stop an instance with hibernation enabled
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --hibernate \
  --region ap-southeast-1 \
  --profile dev
~~~

If hibernation **fails**, AWS may fall back to a **normal shutdown**. Thus, seeing the `stopped` state does not prove RAM was successfully saved. Check OS/hibernation logs, post-start app state, and AWS-documented indicators. If a workload **cannot tolerate losing RAM state**, maintain an independent persistence mechanism or verified recovery workflow.

### 6.5. Limitations to Remember

- Leaving an instance hibernated for **more than 60 days** is unsupported. Per AWS guidance, to keep it longer you must start the hibernated instance, stop it, and start again per procedure; usually, evaluate independent application state persistence instead.
- **Do not modify instance attributes while hibernated** as you would on a normally stopped instance, as this can break resume capability.
- Hibernation always **loses instance store data**, just like a stop.
- Hibernation can fail or face issues across hardware, kernel/OS, security, or update changes during sleep.
- Compute charges can continue accruing **during the `stopping` phase of hibernation** until `stopped`; the EBS volume storing RAM continues incurring storage fees.
- Some hibernation-enabled instances may not finish OS hibernation setup immediately after launch; wait and verify prerequisites per hibernation docs.

### 6.6. Hibernate with Spot Instances

AWS supports hibernation for **certain Spot Instances** when conditions are met. Unlike On-Demand, **Spot capacity can be reclaimed by AWS**:

- Spot requests can select an interruption behavior of `terminate` (default), `stop`, or `hibernate` depending on request type/supported configuration.
- When **Spot is hibernated by AWS due to interruption**, only **Amazon EC2** can resume it when capacity/price conditions allow.
- When **Spot is proactively hibernated by the user**, the user can request to start it again under applicable rules.
- Never expect a Spot instance to resume at an exact desired time; capacity may be unavailable. Critical apps must handle Spot interruptions, persist state durably, and plan fallbacks.

## 7. Terminate: Ending an Instance Permanently Without Reusing Its ID

### 7.1. Impact of `TerminateInstances`

`TerminateInstances` transitions an instance from `running` or `stopped` to `shutting-down` and then `terminated`. Afterward:

- You cannot **start** or reconnect to that same instance.
- The **Instance ID** cannot be reused to restore the terminated instance.
- Data on **instance store** is lost.
- EBS volumes with `DeleteOnTermination = true` are **deleted** along with termination.
- EBS volumes with `DeleteOnTermination = false` are **retained**, continue incurring charges, and can be snapshotted or attached to another instance.
- Resources outside the EC2 lifecycle (such as RDS databases, EBS snapshots, S3 buckets) **are not automatically deleted** merely because an instance is terminated.

**A terminated instance cannot be restored.** If you still have the AMI, snapshots, or retained EBS volumes, you can **launch a new instance**, but it is a separate deployment with a different ID, physical host, and attributes. There is no “undo Terminate.”

### 7.2. `DeleteOnTermination` Is a *Per-EBS-Volume* Setting

An easy rule of thumb is that **root EBS volumes typically default to `DeleteOnTermination = true`**. For EBS data volumes, the default depends on **when and how they were attached**, as well as AMI/launch template settings; never assume every data volume is always retained.

| EBS Volume | Typical Default Behavior | What Must Be Checked |
|---|---|---|
| Root volume attached at launch | Usually `true`, deleted on terminate | Actual value in block device mappings |
| Data volume attached after launch | Usually `false`, retained | Was it overridden during attachment? |
| Data volume declared at launch | May vary across Console/CLI/AMI | Always inspect actual `DeleteOnTermination` |
| Volume kept for audit or migration | Set `false`, take snapshots/backups | Verify access/encryption/keys and data consistency |

For example, suppose an instance has root `/dev/xvda` and data volume `/dev/sdf`. If both have `DeleteOnTermination=true`, terminating deletes **both**. If the data volume has `false`, the instance disappears while the EBS volume persists and keeps accruing charges.

In the Console, open **EC2 → Instances → select instance → Storage → Block devices → Delete on termination**. With CLI, inspect `BlockDeviceMappings` (see the lab section).

### 7.3. Termination Protection and Stop Protection

AWS provides safeguards against accidental actions:

- **Termination protection** is the `DisableApiTermination` attribute. When enabled, it blocks termination via EC2 Console/CLI/API in supported cases.
- **Stop protection** is the `DisableApiStop` attribute. When enabled, it blocks unintended stops via Console/CLI/API; per AWS behavior, it also blocks termination through those interfaces while enabled.
- These protections **do not block every scenario**: shutdowns initiated inside the guest OS per `InstanceInitiatedShutdownBehavior`, AWS scheduled events, or Auto Scaling actions follow their own rules.
- Auto Scaling has separate **scale-in protection** at the group level; it is not the same as EC2 instance termination protection.

Even with protection enabled, maintain backups, least-privilege IAM, change approvals, and monitoring. These are guardrails against human error, not a complete data-recovery strategy.

### 7.4. When Is Terminate the Right Choice?

Terminate is appropriate when instances are built via **Infrastructure as Code/AMIs/container images**, all critical state lives on S3/retained EBS/RDS/EFS or backups, and the team wants to retire older instance lifecycles. This is standard **immutable infrastructure** practice: replace instances with tested new versions, then terminate the old ones.

Terminate is inappropriate if operators do not yet know what local data must be preserved, have not checked `DeleteOnTermination`, lack backups, or are terminating the sole instance serving live traffic without a traffic-drain plan.

## 8. Guest OS Shutdowns vs. AWS API Actions

Learners should distinguish three contexts:

1. **Reboot via OS/EC2:** restarts the operating system without entering the `stopped` state.
2. **Stop via EC2 Console/API/CLI:** the API sends a shutdown request to the guest OS and transitions states per the EC2 lifecycle.
3. **OS shutdown/poweroff run from inside EC2:** for EBS-backed instances, `InstanceInitiatedShutdownBehavior` determines whether the instance **stops** or **terminates**; the default is typically `stop`.

For example, if someone changed `InstanceInitiatedShutdownBehavior` to `terminate`, running a shutdown command inside the OS can **destroy the instance**, contrary to expecting a temporary stop. Always check this attribute before running shutdown commands in scripts.

Note: a Linux `halt` using the `HLT` mechanism does not necessarily transition the instance to `stopped`; the instance may remain billed as `running`. For auditable stops, AWS recommends using Console/CLI/API so requests are recorded in CloudTrail.

**Force stop / skip OS shutdown** bypasses clean OS shutdown and can lose unflushed data or cause corruption. Use it only under an incident runbook after assessing filesystem/database impact.

## 9. IP Addresses, VPC Networking, and Application Access

### 9.1. What Happens to IPs?

| Network Attribute | Reboot | Stop/Start or Hibernate/Start | Terminate |
|---|---|---|---|
| Primary private IPv4 on ENI | Kept | Kept | Original instance gone |
| IPv6 on ENI | Kept | Kept | Depends on whether ENI is kept/deleted |
| Auto-assigned public IPv4 | Kept | Usually released and reassigned on start | Released |
| Associated Elastic IP | Kept | Usually remains associated and billed | Check release/disassociate and billing |
| Security Group on ENI | Kept | Kept | Attachment gone if ENI is deleted |
| VPC, subnets, route tables | Unchanged | Unchanged | Independent VPC resources remain |

If an application uses an **auto-assigned public IPv4** in a hardcoded DNS A record or partner allowlist, stop/start will break connectivity. Usually place an Application Load Balancer, Route 53, and a stable domain in front of instances; where a static public IPv4 is genuinely required, use an Elastic IP and account for its cost.

### 9.2. Restarted Does Not Mean Ready to Serve

Consider an EC2 instance running a Spring Boot API on `:8080` after start:

- EC2 may enter `running` before Spring Boot finishes loading dependencies and database connections.
- Load balancer targets may still fail health checks and receive no traffic yet.
- EBS persists, but **local in-memory caches** are gone after a stop; startup may need cache warming.
- STS credentials, database sessions, and TLS connections held in RAM may have expired during hibernation.

The solution is readiness probes/target health checks, connection retries with backoff, and designing apps to treat stop/start as a normal operational event.

### 9.3. Region/AZ and Physical Hosts

An EC2 instance belongs to one AZ within a Region; across stop/start, the instance ID/ENI/subnet remain in that logical AZ, though the instance typically moves to a **different physical host**. Never rely on traits of the old host (instance store, local hardware state, host-tied parameters) after a start. Certain configurations like Dedicated Hosts have exceptions. Starting may also fail if the AZ/instance type lacks capacity.

## 10. Costs Across the Lifecycle

When deciding to pause an EC2 instance, separate cost layers:

| Cost Item | Running | Stopped/Hibernated | Terminated |
|---|---|---|---|
| EC2 On-Demand compute | Yes | No while `stopped`; **hibernate still bills during `stopping`** | No after `shutting-down` |
| Root/data EBS volumes | Yes | **Yes**, EBS still exists | Yes if volumes are retained |
| EBS snapshots | Yes if snapshots exist | Yes | Yes for retained snapshots |
| Public IPv4 / Elastic IP | May be billed | May **still be billed** | May be billed if IP allocation remains |
| RDS, NAT Gateway, ALB, S3... | Billed independently | **Do not auto-stop** | **Do not auto-delete** |
| Savings Plans/Reserved Instances | Per purchase commitment | Commitment remains active | Commitment remains active |

**Hypothetical example:** A dev Spring Boot instance is needed only 8 hours/day. If it is On-Demand EBS-backed EC2, stopping it for the remaining 16 hours reduces compute usage. Still, the team must account for EBS and IPv4 billing, data/ALB services, and verify Auto Scaling will not recreate the instance. This is a **cost-optimization lever**, not a magic formula cutting the entire environment's bill by two-thirds.

Hibernation uses a larger root EBS volume to store RAM, so **EBS costs may rise** compared to normal stop. Weigh faster resume times against extra EBS capacity and the risk of failed resumes.

## 11. EC2 Auto Scaling, Spot, and Self-Healing Infrastructure

### 11.1. Instances in an Auto Scaling Group

With Amazon EC2 Auto Scaling (ASG), the goal is maintaining **desired capacity**. When an instance is stopped or marked unhealthy, the ASG can **terminate it and launch a replacement** to satisfy desired count. Therefore:

- Do not manually stop an ASG-managed instance expecting it to stay `stopped`.
- To reduce instance count, adjust ASG desired/min capacity cleanly, accounting for graceful scale-in and target draining.
- **Instance scale-in protection** guards against certain ASG scale-in events, but does not replace EC2 stop/termination protection or other safeguards.
- **Hibernation is not supported for instances in an ASG or used by ECS** under current EC2 constraints.

### 11.2. Spot Instances Have a Distinct Lifecycle

Spot capacity comes from spare EC2 capacity and **can be interrupted**. Default interruption behavior is terminate, though certain Spot requests support stop/hibernate when configured and eligible.

- Spot instances interrupted with `terminate` are lost like normal terminations.
- Spot instances stopped/hibernated may not restart/resume until capacity and price constraints are met.
- Spot requests have their own lifecycle alongside EC2 instances and can launch replacement instances after events.
- Avoid keeping sole database, queue consumer, or batch job state in Spot RAM or instance store; checkpoint to S3/EBS/RDS or an appropriate durable service.

Critical workloads must recover from **durable data sources** and handle interruptions gracefully rather than treating hibernation as an immediate-resume guarantee.

## 12. Safe Operations Workflow in the AWS Console

### 12.1. Pre-Change Checks

1. Sign in to the **right AWS account/role** and select the right Region; use MFA/Identity Center per policy.
2. Open **EC2 → Instances**, filter by instance ID or `Name` tag; confirm instance type, AZ, owner, and whether it is ASG/Spot or On-Demand.
3. On the **Storage** tab, check root device type and **Delete on termination** for every EBS volume.
4. On the **Details** tab, check hibernation enabled, stop protection, termination protection, and shutdown behavior.
5. Check application health/logs, target groups, snapshots/backups, and RDS/S3/queue dependencies.
6. Clarify the objective: OS maintenance (reboot), pause compute (stop), keep RAM (hibernate), or retire instance (terminate).
7. Execute per runbook/change approval; monitor state transitions and re-verify the application after start.

### 12.2. Console Actions

- **Reboot:** Select instance → **Instance state → Reboot instance**.
- **Stop:** **Instance state → Stop instance**; available only for eligible configurations.
- **Hibernate:** **Instance state → Hibernate instance**, available only when enabled at launch and prerequisites are met.
- **Start:** Select `stopped` instance → **Instance state → Start instance**.
- **Terminate:** **Instance state → Terminate (delete) instance**; double-check instance ID, EBS deletion flags, backups, and approval before executing.

After stop or hibernate, the state displays as `stopped`. That is only the EC2 state; operational logs/records must track **which action was used** and whether RAM was actually saved.

## 13. AWS CLI: Inspecting States and Key Attributes

### 13.1. Verify Identity and Region Before Any Action

These examples use AWS CLI v2, a read-authorized `dev` profile, and Region `ap-southeast-1`. Replace with your lab environment's real account/Region:

~~~bash
aws --version
aws sts get-caller-identity --profile dev --output json

aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,Root:RootDeviceType,HibernateEnabled:HibernationOptions.Configured,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress}' \
  --output table
~~~

`--query` projects the fields to inspect; with `--output table`, the output may be blank if no instances exist in that Region. To filter by the `Name` tag, add `--filters Name=tag:Name,Values=...` with the target value as needed.

### 13.2. Inspect a Specific Instance

~~~bash
# Read-only: does not modify state
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,RootDevice:RootDeviceType,Type:InstanceType,HibernateEnabled:HibernationOptions.Configured,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress}' \
  --output json
~~~

**Illustrative** output:

~~~json
[
  {
    "Id": "i-0123456789abcdef0",
    "State": "stopped",
    "RootDevice": "ebs",
    "Type": "t3.small",
    "HibernateEnabled": true,
    "PrivateIP": "10.0.1.25",
    "PublicIP": null
  }
]
~~~

Here `HibernateEnabled: true` only reflects **configured support**. Do not infer that RAM from the last stop was preserved. To confirm that, check the actual stop/hibernate operation and hibernation logs.

### 13.3. Inspect `DeleteOnTermination`

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].BlockDeviceMappings[].{Device:DeviceName,Volume:Ebs.VolumeId,DeleteOnTermination:Ebs.DeleteOnTermination}' \
  --output table
~~~

This identifies which volumes **will be deleted on termination**. Always inspect every mapping; never assume only the root volume is affected.

### 13.4. Inspect Both Protection Flags and Shutdown Behavior

~~~bash
aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiTermination

aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiStop

aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute instanceInitiatedShutdownBehavior
~~~

These three commands are read-only. Some states/instance types impose restrictions on querying or using these attributes; if you encounter `AccessDenied`, check `ec2:DescribeInstanceAttribute` permissions.

### 13.5. Read-Only Listing of Instances by State

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=instance-state-name,Values=running,stopped \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone}' \
  --output table
~~~

This helps audit resources still incurring EBS charges or long-stopped dev machines. If empty, verify account, Region, and IAM permissions before assuming no instances exist.

## 14. State-Changing Commands: Use Only When Authorized

The commands below **make live changes**, provided so learners understand the syntax. Execute only in an authorized lab environment after verifying account, Region, instance ID, backups, dependencies, and change policies.

~~~bash
# Stop an EBS-backed instance (RAM/instance store will be lost)
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

# Start after the instance is stopped
aws ec2 start-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

# Hibernate an instance enabled at launch (may fall back to stop)
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --hibernate \
  --profile dev \
  --region ap-southeast-1

# Terminate: PERMANENTLY DELETE INSTANCE; EBS deletion per mapping
aws ec2 terminate-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1
~~~

For supported operations, `--dry-run` checks whether the principal has permission to call the API; it returns `DryRunOperation` when permitted, or `UnauthorizedOperation` when denied. `--dry-run` **does not guarantee** the real call will succeed, does not check downstream app impact, and does not substitute for change approval.

The AWS CLI also provides **waiters** to wait for a target state after an authorized operation:

~~~bash
aws ec2 wait instance-stopped \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

aws ec2 wait instance-running \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1
~~~

The `instance-running` waiter checks only the EC2 state; **it does not prove** the application is healthy. Verify EC2 status checks and endpoint/ALB target health before completing maintenance.

## 15. Auditing, Monitoring, and Lifecycle Automation

### 15.1. EventBridge State-Change Notifications

Amazon EC2 emits events with `source = aws.ec2` and `detail-type = EC2 Instance State-change Notification` to **Amazon EventBridge** whenever state changes. Example event:

~~~json
{
  "source": "aws.ec2",
  "detail-type": "EC2 Instance State-change Notification",
  "detail": {
    "instance-id": "i-0123456789abcdef0",
    "state": "stopped"
  }
}
~~~

The snippet above is an **abbreviated illustrative event pattern**, not a full EventBridge event with every metadata field. You can use EventBridge Rules to invoke Lambda/SNS/Step Functions when an instance becomes `stopped` or `terminated`, alerting on-call teams or triggering designed operational workflows.

### 15.2. CloudTrail, CloudWatch, and AWS Systems Manager

- **AWS CloudTrail:** audits API calls such as `StopInstances`, `StartInstances`, `TerminateInstances`, and protection changes per log config; identifies **who** acted, **when**, account, and Region.
- **Amazon CloudWatch:** tracks metrics while running, status checks, alarms, and app logs; distinguish missing metrics due to a stopped machine from monitoring agent failures.
- **AWS Systems Manager:** supports automation/runbooks, maintenance windows, patching, and IAM-governed operations.
- **AWS Backup/EBS snapshots:** enables EBS data recovery as designed; snapshots protect only backed-up data and do not automatically ensure write-consistent database snapshots without quiescing/coordination.
- **IaC and deployment pipelines:** store launch templates, user data, ASGs, volumes, alarms, tags, and policies in source control to rebuild infrastructure reliably.

### 15.3. Dev Server Auto-Shutdown Automation Pattern

A suitable workflow for development EC2 instances **not managed by Auto Scaling**:

1. Apply tags such as `environment=dev`, `schedule=office-hours`, and owner.
2. At end of day, automation checks tags, states, and dependencies, then stops instances on an approved schedule.
3. Next morning, starts them back up; waits for state and health checks, then verifies application readiness.
4. Logs results, alerts on failures, and maintains exclusions for instances that must stay running.
5. Monitors **full-stack costs**, including EBS, IPv4, databases, load balancers, and snapshots.

Do not run this automation against production, ASG/ECS nodes, or critical batch servers without dedicated design.

## 16. Troubleshooting by Symptom

| Symptom | Common Causes | How to Check |
|---|---|---|
| **Stop** button is disabled | Instance store root, unsupported state, stop protection, or IAM deny | Inspect `RootDeviceType`, `State.Name`, `DisableApiStop`, and IAM permissions |
| `IncorrectInstanceState` on start/stop | Instance is transitioning or already in an incompatible state | Run `describe-instances`, wait for transition to finish |
| Hibernate option does not appear | Not enabled at launch, incompatible AMI/instance/RAM/EBS, restricted environment | Check `HibernationOptions.Configured` and prerequisites |
| Hibernate ends in `stopped` yet RAM is lost on start | Hibernation failed and fell back to normal stop; OS/space issue | Inspect system/hibernation logs, root EBS size/encryption, app state |
| Instance stuck in `stopping` too long | OS failed clean shutdown, I/O stall, or hibernation issue | Check EC2 status/system logs; avoid force stop without assessing data |
| `UnauthorizedOperation` / `AccessDenied` | Missing permission in IAM policy/SCP/permission boundary | Check `sts get-caller-identity` and IAM request/action |
| `start-instances` reports insufficient capacity | AZ/type/placement/capacity constraints | Inspect message, capacity reservation/type/AZ, fallback runbook |
| Lost SSH/HTTP via old IP after start | Auto-assigned public IPv4 changed | Check `PublicIpAddress`; consider Elastic IP or DNS/ALB |
| EC2 `running` yet API still fails | App not ready, DB/TLS/credentials expired, SG/NACL | Check app logs, health endpoint, target health, networking |
| Terminate is blocked | Termination protection or stop protection is enabled | Check both `DisableApiTermination` and `DisableApiStop`; verify approval |
| Manually stopped yet a new instance appears | Auto Scaling/ECS/Fleet is enforcing desired capacity | Check ASG/Spot/Fleet before touching individual instances |
| Terminated yet bill keeps rising | Remaining EBS/IPv4/snapshots/ALB/RDS/NAT and commitments | Inspect billing by service/resource and cleanup plan |
| Data files vanish after stop | Files lived on instance store or memory/cache instead of EBS | Inspect mounts/storage layout; use EBS/EFS/S3 for persistent data |
| Cannot restart hibernated Spot | Capacity unavailable or request/price constraints unmet | Check Spot request and interruption behavior |

**In production:** when an instance becomes unresponsive, prioritize inspecting status checks, app logs, networking, and persistent storage. Stop/start often switches physical hosts and clears RAM, which may clear transient OS issues while also erasing in-memory evidence and causing downtime; weigh recovery objectives before acting.

## 17. Read-Only Lab: Choosing the Right Lifecycle Action

### 17.1. Prerequisites

An AWS training account with a `dev` profile and EC2/STS read permissions. **No EC2 instance needs to be created for this exercise**; sample outputs may be used. Examples use the Singapore Region (`ap-southeast-1`).

### 17.2. Part A — Identify Account and State

~~~bash
aws sts get-caller-identity --profile dev

aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Root:RootDeviceType,Type:InstanceType,HibernateEnabled:HibernationOptions.Configured}' \
  --output table
~~~

For each instance, record `Id`, state, root device type, and hibernation capability. Explain why **hibernation enabled** alone does not prove RAM data is intact while the instance is `stopped`.

### 17.3. Part B — Predict What Survives and What Is Lost

Scenario: an EBS-backed EC2 instance running Spring Boot has:
- configuration files on the EBS root volume;
- temporary batch files on local instance store;
- Redis client connections and cache in RAM;
- private IPv4 in the subnet and an auto-assigned public IPv4.

Build a table predicting what survives or is lost after `reboot`, `stop/start`, `hibernate/start`, and `terminate`. Compare with the table in section 4 and explain why sole copies of data should not live on instance store.

### 17.4. Part C — Inspect EBS Deletion Flags

If you have a valid instance ID:

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].BlockDeviceMappings[].{Device:DeviceName,DeleteOnTermination:Ebs.DeleteOnTermination,VolumeId:Ebs.VolumeId}' \
  --output json
~~~

Questions: if terminated, which volumes will be deleted? Which volumes may keep accruing charges? If a volume must be kept, what must the team do **before** executing the termination?

### 17.5. Part D — Choose the Action by Objective

| Scenario | Preliminary Choice | Conditions to Verify |
|---|---|---|
| Maintain Java service and need OS restart | Reboot | Rollout/health checks ready; do not rely on current RAM |
| Dev server unused overnight, data on EBS | Stop | Not in ASG, start schedule configured, EBS/IPv4 costs tracked |
| Heavy compute workstation needing RAM resume | Hibernate | Enabled at launch, RAM/AMI/EBS eligible, reconnect logic ready |
| Replace app instance with new immutable deployment | Terminate old instance | Traffic drained, backups/snapshots and `DeleteOnTermination` checked |
| Production EC2 in ASG is unhealthy | Follow ASG/repair runbook | Check desired capacity/health; avoid ad-hoc manual stops |
| Batch job on Spot with interruption risk | Checkpoint and retry | Check stop/hibernate/terminate behavior; capacity not guaranteed |

### 17.6. Part E — Post-Start Recovery Verification

For a Spring Boot app running on EC2, write a concise post-start / post-hibernate-resume runbook:

1. Verify EC2 state and status checks.
2. Verify EBS mounts, secret/STS credential refresh, and RDS connection pools.
3. Check logs, application health endpoint, and any caches needing warm-up.
4. Confirm target group/ALB receives traffic and monitor 5xx errors.
5. Check CloudTrail/EventBridge events and actual recovery duration.

The lab is complete when learners clearly distinguish **EC2 state** from **application readiness** and identify the data and costs affected by each action.

## 18. Self-Check Questions

1. When `stopped`, does EC2 incur compute charges? Which charges may still apply?
2. Why can an EBS-backed EC2 instance be stopped while an instance store-backed root instance cannot via normal stop?
3. How do `Reboot` and `Stop/Start` differ regarding RAM, public IPv4, and instance store data?
4. Can hibernation be enabled on an instance launched weeks ago?
5. Where does hibernate save RAM, and why must the root EBS volume be encrypted?
6. When hibernation fails, what can happen instead of resuming RAM?
7. If an instance is `stopped` with `HibernationOptions.Configured=true`, is it guaranteed to have hibernated successfully?
8. What differs between `DeleteOnTermination=true` and `false`?
9. Why is enabling termination protection insufficient against all risks in Auto Scaling or OS-initiated shutdowns?
10. Why can stopping an instance in an Auto Scaling group cause a replacement instance to launch?
11. After starting, EC2 is `running`, yet the load balancer target remains unhealthy. What should you inspect?
12. With Spot, who can resume an instance when AWS proactively hibernates it due to interruption?
13. Is hibernating for over 60 days supported under current AWS limits?
14. If a team uses immutable deployments with no unique local data, which approach should be preferred when releasing a new app version?
15. How do you monitor a `running → stopped` transition via EventBridge and investigate who triggered it via CloudTrail?

### Guided Answers

- **Stop:** preserves EBS/instance ID/private IP, but loses RAM, instance store, and usually auto-assigned public IPv4.
- **Hibernate:** identical to stop at the compute layer, plus saves RAM to encrypted root EBS; must be enabled at launch and checked against limits.
- **Terminate:** instance cannot be recovered, EBS data depends on each volume's `DeleteOnTermination`, and many other resources can still incur charges.
- **Safe operations:** verify account/Region/IAM, backup plans, ASG/Spot dependencies, application readiness, and non-compute billing.

## 19. Official AWS Documentation

1. [Amazon EC2 instance state changes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html) — Six states, lifecycle diagram, and reboot/stop/hibernate/terminate comparison.
2. [Stop and start Amazon EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html) — EBS-backed prerequisites and stop/start operations.
3. [How EC2 instance stop and start works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html) — RAM, instance store, EBS, ENIs, private/public IPs, and billing.
4. [Hibernate your Amazon EC2 instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Hibernate.html) — Hibernation overview and resume behavior.
5. [Prerequisites for EC2 instance hibernation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/hibernating-prerequisites.html) — AMI, instance families, RAM, root EBS, encryption.
6. [How EC2 instance hibernation works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-hibernate-overview.html) — Preserved/lost data and the 60-day limit.
7. [Enable hibernation for an instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/enabling-hibernation.html) — Enabling at launch and inspecting `HibernationOptions`.
8. [Terminate Amazon EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/terminating-instances.html) — Permanence of terminate and workflow.
9. [Preserve data when an instance is terminated](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html) — `DeleteOnTermination` and defaults to verify.
10. [Change instance termination protection](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_ChangingDisableAPITermination.html) — `DisableApiTermination` attribute.
11. [Enable stop protection](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-stop-protection.html) — `DisableApiStop` attribute.
12. [State change events for EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-instance-state-changes.html) — EventBridge notifications.
13. [Spot Instance interruption behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/interruption-behavior.html) — Stop/hibernate/terminate when Spot is reclaimed.
14. [Amazon EC2 On-Demand Pricing](https://aws.amazon.com/ec2/pricing/on-demand/) — Compute billing mechanics by configuration.

> **Final takeaway:** Before clicking Stop, Hibernate, or Terminate, verify **identity/account/Region, root volume, where critical data resides, EBS deletion flags, Auto Scaling/Spot dependencies, application recovery, and remaining costs**. Making sound instance-lifecycle decisions keeps AWS systems data-safe, predictably recoverable, and within budget.
