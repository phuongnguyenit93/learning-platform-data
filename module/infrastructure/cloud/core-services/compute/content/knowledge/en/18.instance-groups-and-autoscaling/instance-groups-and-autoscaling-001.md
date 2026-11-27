# Managed Instance Groups and Member Configuration Templates

When an application needs multiple virtual machines to serve load, creating and managing individual VMs separately quickly becomes difficult to control. A managed instance group (or scale set depending on the platform) lets you declare a desired number of machines along with a standard configuration, after which the platform automatically creates, health-checks, replaces, and updates member machines according to policy.

An **instance template (or machine model)** describes how to create a VM: image, machine type, disks, network, identity, metadata, startup configuration, and related attributes. A **managed instance group** uses this template as its configuration source to maintain a set of VMs sharing the same role. When a member fails or capacity needs to scale, the platform controller creates or removes VMs to bring the group back to its desired state.

In **CLOUD_CORE_SERVICES_COMPUTE**, managed instance groups are the foundation for operating a consistent VM fleet, supporting autoscaling, multi-zone distribution, and batched updates. Good design requires clearly defining the configuration template, lifecycle policies, health checks, load distribution, update mechanics, and which data is allowed to exist independently of each VM.

## 1. What is a managed instance group?

A managed instance group is a resource that controls a collection of VMs instead of managing each machine individually. Operators declare the desired state; the platform continuously compares the actual state against that desired state and takes action to converge them.

A group typically includes the following components:

- **Group/controller:** the resource that manages the VM set and lifecycle policies.
- **Instance template/model:** the configuration used to create member VMs.
- **Desired capacity:** the number of VMs or capacity level the group needs to maintain.
- **Minimum/maximum capacity:** lower and upper bounds if the group supports autoscaling.
- **Health check/autohealing:** how unhealthy members are identified and replaced.
- **Update policy:** how older VMs are replaced with VMs from a new template.
- **Placement/distribution policy:** how members are distributed across zones, subnets, or failure domains.
- **Lifecycle controls:** scale-in protection, draining, hooks, or standby modes depending on the platform.

The group is managed using a **declarative model**: the operator describes the desired outcome, and the controller is responsible for executing the necessary changes. If a VM is unexpectedly deleted while desired capacity remains unchanged, the group can create a replacement VM.

### 1.1. Comparing individual VM management and group management

| Criterion | Individually managed VMs | Managed instance group |
| --- | --- | --- |
| Machine creation | Create each VM via console/API/IaC | Create members from a template/model |
| Maintaining count | Operators monitor and recreate | Controller maintains desired capacity |
| Detecting failed machines | Monitoring and manual intervention | Can integrate health checks and autohealing |
| Image updates | Performed per VM or via scripts | Has update policy/instance refresh |
| Scaling | Create additional VMs and register backends | Change desired capacity or use an autoscaler |
| Consistency | Prone to drift between machines | Template and rollout process enforce a shared baseline |
| Lifecycle | Typically tied to each individual VM | Members can be replaced automatically |

Managed groups reduce repetitive operations, but they do not automatically solve every application problem. The application still needs a stateless design or external state storage, support for shutdown/draining, and proper handling of VM replacement.

## 2. Instance template as the standard configuration source

An instance template describes the configuration used when the group creates a new member. The clearer and more properly versioned the template is, the easier it becomes to control provisioning, scaling, and updates.

A template typically contains the following attribute groups:

| Configuration group | Common contents | Impact |
| --- | --- | --- |
| Compute | Machine type, vCPU, RAM, accelerator, architecture | Processing capacity and cost per VM |
| Boot image | Image ID, image family, or image version | Operating system, kernel, agents, and base software |
| Storage | Boot disk, data disk, type, size, encryption, delete policy | Capacity, performance, and data durability |
| Network | VPC/VNet, subnet, NIC, security group, IP mode | Connectivity, network segmentation, and attack surface |
| Identity | Instance role, managed identity, service account | Workload permissions when calling APIs |
| Metadata/bootstrap | User data, cloud-init, startup script, custom metadata | Configuration when the machine boots |
| Placement | Zone, placement group, tenancy, or host affinity | Latency, fault isolation, and performance |
| Operations | Monitoring, logging, shutdown behavior, tags/labels | Observability, management, and automation |

Templates should contain non-sensitive, reproducible configuration. Do not put passwords, private keys, or long-lived access keys into user data, startup scripts, or metadata. Workloads should use a managed identity/instance role or retrieve secrets from a secret manager using a least-privilege identity.

### 2.1. Compute and machine architecture

Choose a machine type suited to the workload's characteristics:

- Compute-optimized for CPU-bound tasks.
- Memory-optimized for large working sets or in-memory caches.
- General-purpose for mixed workloads.
- Storage-optimized for local I/O or high storage throughput.
- GPU/accelerator for tasks that can leverage hardware acceleration.

Members in the same group are usually created using a consistent machine model. Some platforms support multiple instance types or group-level overrides; if used, verify differences in CPU, RAM, networking, and architecture so the application continues to operate reliably.

Do not change machine types based solely on CPU utilization. Look at memory pressure, network throughput, I/O wait, queues, latency, and cost per request.

### 2.2. Image and in-machine software

The image is the most critical input for creating a consistent fleet. You should:

- Use tested images with an explicit ID/version.
- Pin a specific image in the template rather than referencing an uncontrolled mutable tag.
- Update OS packages, kernel, runtime, and agents inside the image build pipeline.
- Scan for vulnerabilities and verify the baseline before releasing an image.
- Record the image ID, build provenance, and creation timestamp.
- Have a strategy to replace older VMs when a new image is released.

An image family or dynamic alias can be convenient in development environments, but in production you should explicitly control which version each rollout uses. If a template points to a self-updating image alias, a subsequent scale-out may create machines running a different version than existing members.

### 2.3. Boot disk and data disk

The template should clearly specify:

- Boot disk type and size.
- Volume type and IOPS/throughput if configurable.
- Encryption and the key used.
- Policy to retain or delete the boot disk when the VM is terminated.
- Whether data volumes are persistently attached, created per instance, or managed independently.
- Mount points and filesystem initialization steps.

Boot disks can usually be recreated from the image. Business data should live in a database, object storage, shared file service, or a persistent volume with an independent lifecycle. If a data disk is created per VM, define what happens when the group replaces a member.

Do not enable automatic deletion of all disks on termination if any disk might hold data that must be retained. Conversely, do not retain temporary boot disks indefinitely after VMs are replaced, as this incurs costs and can leave sensitive data behind.

### 2.4. Network and security

Members must be created in the appropriate network/subnet and under the right security policies. A template can define:

- VPC/VNet and subnet or subnet selection.
- Network interfaces and public/private IP mode.
- Security group/firewall policy.
- DNS, routes, and required endpoints.
- Network acceleration or bandwidth configuration if supported.

For internal application fleets, prefer private addresses and open only the required ports from the load balancer or trusted sources. Avoid assigning public IPs to individual members unless necessary. Never hardcode an individual IP address into the application; use service discovery, a load balancer, or DNS.

### 2.5. Identity, metadata, and startup

The template can attach an instance role, managed identity, or service account so the workload authenticates with cloud services. Grant least-privilege permissions scoped to the group's responsibilities.

Startup scripts should:

- Be idempotent so re-running them does not cause duplicate configuration or corrupt state.
- Have explicit timeouts and clear logging.
- Check dependencies before starting the application.
- Retrieve secrets from a secret manager using workload identity.
- Never write credentials to logs or world-readable files.
- Report readiness status after completing required configuration.

Startup scripts should not download arbitrary software from uncontrolled sources on every VM boot. It is better to bake software into a tested image; bootstrap should only handle environment configuration and minimal initialization tasks.

## 3. How a group maintains desired capacity

Suppose a group is configured with a desired capacity of 4. If a member is deleted or marked unhealthy, the controller can create a replacement VM to restore the active member count to 4, provided quota, capacity, and other conditions allow.

Capacity settings typically include:

- **Minimum:** the minimum number of members allowed to be maintained.
- **Desired:** the number of members the controller is currently targeting.
- **Maximum:** the upper limit of the group.

For groups using autoscaling, desired capacity can change based on a policy or schedule. For static groups, desired capacity is usually set by an operator.

Example:

| Attribute | Value |
| --- | ---: |
| Minimum | 2 |
| Desired | 4 |
| Maximum | 10 |

If load increases and the autoscaler decides 7 VMs are needed, desired capacity can be raised to 7. When load drops, desired capacity can decrease to 4 or 2 depending on policies and limits.

The controller does not guarantee reaching desired capacity instantaneously. Quotas, zone capacity shortages, bad images, failed startup scripts, subnet IP exhaustion, or insufficient policy permissions can leave the group short of members. Monitor both desired capacity and the actual number of healthy/in-service instances.

## 4. Health checks and automatic replacement of failed machines

Managed groups can typically integrate health checks to detect members that are no longer fit to serve. Depending on the platform, health signals may come from VM status, OS-level checks, load balancer health checks, or user-configured signals.

### 4.1. Health layers

- **Infrastructure health:** does the hypervisor/provider consider the VM operational?
- **Guest health:** have the OS, agents, and basic networking booted properly?
- **Application health:** is the application accepting requests and returning valid responses?
- **Load balancer health:** does the backend pass probes on the configured port/path/protocol?
- **Dependency health:** can the application connect to essential databases, caches, or queues?

A VM can be in a running state while the application itself is dead. If only infrastructure health is used, the group will not detect application-layer failures. Conversely, health checks that are too deep or depend on non-essential auxiliary services can mark all instances unhealthy during a temporary dependency disruption.

### 4.2. Readiness and liveness

Readiness answers the question "is the instance ready to receive traffic?". Liveness answers "is the process still alive or does it need to be restarted?". These two signals serve different purposes.

In a VM fleet, load balancer health checks typically remove unready backends from traffic. Group health/autohealing can use health signals to replace unhealthy VMs. Configure a grace period long enough for booting and bootstrapping, yet not so long that failed machines linger unnecessarily.

### 4.3. Avoiding continuous replacement loops

If an image or startup script has a bug, the group can repeatedly launch new VMs only to mark them unhealthy again. The consequences include:

- Wasted cost from continuously launching VMs.
- Increased load on quotas, APIs, and image registries.
- Fluctuating backend capacity.
- Masking the root cause because failing instances are replaced too quickly.

Ensure bootstrap logs are preserved, set alarms on launch/terminate counts, limit replacement rates, or configure rollout halts on widespread failures. When multiple VMs become unhealthy together after a change, consider rolling back the template/image instead of letting the controller keep looping.

## 5. Distributing instances across multiple zones

A group can distribute members across multiple availability zones or failure domains to reduce reliance on a single point of failure. Exact distribution behavior depends on the provider and group configuration.

For example, a group of 6 VMs across 3 zones can target 2 VMs per zone. When a zone lacks capacity, the provider may distribute unevenly or fail to provision the full count depending on policy.

Benefits:

- Increases fault tolerance when a zone experiences an outage.
- Can reduce the risk of localized maintenance or infrastructure failures.
- Enables load balancers to distribute traffic across multiple failure domains.

Trade-offs:

- Requests and replication may traverse cross-zone networks.
- Cross-zone data transfer charges may apply.
- Databases/caches need a topology that supports multi-zone access.
- Scale-in and rolling updates must avoid removing too much capacity from a single zone.

Do not assume placing VMs across multiple zones alone achieves high availability. Load balancers, databases, caches, DNS, identity, and other dependencies must also have appropriate fault-tolerant designs.

## 6. Updating templates and rolling out members

When changing an image, machine type, disk, network, or startup configuration, you need to determine how existing members receive the new configuration.

Many platforms do not automatically modify all running VMs simply because a template changed. An update/refresh operation is often required to replace old instances with new ones.

### 6.1. Versioning templates

Each significant change should produce a traceable version or model revision. Example:

| Revision | Image | Machine type | Purpose |
| --- | --- | --- | --- |
| v12 | app-image-2026-10 | general-4 | Currently serving version |
| v13 | app-image-2026-11 | general-4 | OS and dependency patching |
| v14 | app-image-2026-11 | compute-8 | Testing increased CPU for workload |

Do not mutate historical versions already used in production if the platform supports immutable versions. Creating new revisions lets you trace which configuration created each VM and roll back to a known working revision.

### 6.2. Rolling updates

A rolling update replaces members in batches rather than stopping the entire group at once. Parameters that typically need to be decided:

- Maximum number of instances replaced simultaneously.
- Minimum number of instances that must remain healthy during the update.
- How much temporary capacity can exceed desired capacity.
- Wait time for health checks after creating a new VM.
- Stop conditions when launches or health checks fail.
- How to roll back to the previous template revision.

If a group must always maintain at least 4 healthy VMs, the update policy must ensure not too many members are taken out simultaneously. For workloads with slow startup times, smaller batches and adequate wait times reduce disruption risk.

### 6.3. Blue-green or batched replacement

For major changes such as switching the OS, runtime, or machine architecture, you can create a new group in parallel, test it, and then shift traffic via the load balancer. This requires extra temporary capacity but enables faster fallback to the old group.

Not every workload needs blue-green. For stateless fleets, rolling updates are usually more cost-effective. For high-risk changes or those requiring broad compatibility testing, blue-green can be worth the cost.

### 6.4. Handling failures during an update

When a rollout fails:

1. Halt the next batch.
2. Preserve logs, image IDs, template revisions, and health results.
3. Check whether new members fail uniformly or only in a specific zone.
4. Determine whether traffic has already been routed to the new instances.
5. Roll back the template or shift traffic back to the stable group.
6. Clean up temporary VMs/disks only after verifying they contain no data that must be retained.
7. Fix the image/bootstrap and retry with a new revision.

## 7. Scale-in and member lifecycle

Scale-out typically creates additional VMs. Scale-in removes VMs when desired capacity decreases. Selecting the right member to remove is critical to avoid dropping requests or losing state.

### 7.1. Graceful shutdown and connection draining

Before termination, the application should be given time to:

- Stop accepting new requests.
- Finish in-flight requests.
- Commit transactions or write checkpoints.
- Process held messages and ack/nack properly.
- Close database/cache connections.
- Flush required logs and metrics.
- Release locks or leases.

Load balancers can support connection draining/deregistration delays. Lifecycle hooks or shutdown hooks can give the application additional time to finish. Configure appropriate timeouts; if too long, scale-in slows down and may exceed platform shutdown limits.

### 7.2. Selecting instances for scale-in

Some groups support policies to select members for termination based on age, zone, template version, or utilization. Verify whether that selection fits your workload.

Do not assume the group will choose the least loaded VM. If a VM is processing a long-running task or holding sessions, the application needs draining and work recovery mechanisms when the VM is removed.

### 7.3. Scale-in protection

Scale-in protection or equivalent mechanisms can prevent a specific instance from being removed while processing critical work. However, protection should not be enabled indefinitely; if all members are protected, the group may fail to reduce capacity and continue incurring costs.

Use time-bounded protection tied to lifecycle events, with a mechanism to remove protection once work completes. For batch-processing workloads, checkpoints and queues are generally more resilient than keeping a VM un-terminable.

## 8. Stateful and stateless workloads in managed groups

Managed groups work best with replaceable members. If each VM holds unique state on local disk or in RAM, autohealing and scale-in can cause data loss.

### 8.1. Stateless design

A stateless instance holds no unique business state that must survive the machine's lifecycle. Sessions, uploaded files, job states, and transactional data are stored in shared services or durable storage.

With this design, a VM can be replaced while the application continues operating on remaining members. This is the ideal model for autoscaling and rolling updates.

### 8.2. If the workload requires state

If local state cannot be avoided:

- Clearly identify which data must be preserved when a VM terminates.
- Use persistent volumes with independent lifecycles and appropriate attachment mechanisms.
- Use databases, shared storage, or replication instead of relying solely on ephemeral disks.
- Implement checkpointing and resume mechanisms.
- Ensure only one instance holds write ownership when using a shared volume.
- Configure time-bounded scale-in protection or lifecycle hooks.

Do not attach a single persistent disk to every member VM unless the storage safely supports multi-attach. Multi-attach block storage requires a cluster-aware filesystem or application-level locking.

## 9. Comparing cloud provider models

Cloud providers have different naming and capabilities, yet all offer models for managing a set of VMs from a standard configuration.

| General concept | AWS | Microsoft Azure | Google Cloud |
| --- | --- | --- | --- |
| Managed VM group | EC2 Auto Scaling Group | Virtual Machine Scale Sets (VMSS) | Managed Instance Group (MIG) |
| Configuration template | EC2 Launch Template | VMSS VM profile/model | Instance Template |
| Desired count | Desired capacity | Scale set capacity | Target size |
| Health check | EC2/ELB health checks | VM health extension and configured health monitoring | Health check and autohealing policy |
| Updates | Instance refresh or configured rolling replacement | Rolling upgrades or update policy | MIG rolling update/recreate |
| Zone distribution | AZ/subnet and group settings | Availability zones | Regional/zonal MIG |

Feature names, limits, and default behaviors vary by API version, group type, and region. When implementing, consult the documentation for the specific service and check constraints such as quotas, disk types, networking, health integration, and update policies.

### 9.1. AWS EC2 Auto Scaling Group

EC2 Auto Scaling Group (ASG) manages a collection of EC2 instances. An ASG typically references a Launch Template and a specific version. A Launch Template describes the image, instance type, key pair if used, network interface, security group, IAM instance profile, storage mapping, user data, and supporting attributes.

Key considerations:

- Specify an explicit Launch Template version; avoid using `$Latest` or `$Default` if changes are not tightly controlled.
- Use appropriate health checks, potentially combining EC2 status and load balancer health.
- Use instance refresh to replace members in batches when updating the template.
- Define lifecycle hooks, connection draining, and termination policies.
- If using multiple instance types, verify application compatibility and capacity across AZs.

### 9.2. Azure Virtual Machine Scale Sets

VM Scale Sets manage a collection of VMs with a uniform configuration or according to supported orchestration modes. The VMSS model describes the image, VM size, storage profile, network profile, identity, extensions, and related attributes.

Key considerations:

- Understand the scale set's orchestration mode and update mode.
- Determine how instances receive a new model and when a rolling upgrade or reimage is required.
- Use health extensions or appropriate health integration to detect unhealthy applications.
- Check zone distribution, upgrade policy, instance protection, and rolling limits.
- Verify that extensions and startup scripts complete successfully before an instance receives traffic.

### 9.3. Google Cloud Managed Instance Groups

Google Cloud Managed Instance Groups create and manage VMs from an Instance Template. A MIG can be zonal or regional and supports autoscaling, autohealing, rolling updates, and distribution policies depending on the group type's capabilities.

Key considerations:

- An Instance Template is the configuration used to create VMs; create a new template revision when changes are needed.
- Update the MIG to a new template using an appropriate update policy.
- Use health checks and autohealing policies to replace unhealthy VMs.
- Regional MIGs help distribute members across multiple zones within a region.
- Check surge/unavailable limits, capacity, and replacement behavior under the update policy.

## 10. Conceptual configuration template example

The YAML example below illustrates a stateless VM group running an API service. This is a vendor-neutral model, not a direct schema for AWS, Azure, or Google Cloud.

~~~yaml
instance_template:
  name: orders-api-v17
  image: orders-api-image-2026-11
  machine:
    type: general-purpose-4
    architecture: x86_64
  boot_disk:
    type: balanced-ssd
    size_gib: 40
    encrypted: true
    delete_on_termination: true
  network:
    subnet: private-app-subnet
    public_ip: false
    security_policy: orders-api-backend
  identity:
    workload_role: orders-api-read-runtime
  bootstrap:
    source: baked-image
    startup_script: configure-environment
  metadata:
    application: orders-api
    environment: production
    template_revision: v17

managed_group:
  name: orders-api-fleet
  template_revision: v17
  min_size: 3
  desired_size: 6
  max_size: 20
  zones:
    - zone-a
    - zone-b
    - zone-c
  health_check:
    type: application
    path: /health/ready
    grace_period_seconds: 180
  update_policy:
    strategy: rolling
    max_surge: 1
    max_unavailable: 1
  scale_in:
    connection_draining_seconds: 60
~~~

When translating into provider configurations, map each field to the provider API and verify its semantics. For example, `max_surge` may be expressed using a different parameter or restricted by group type. The health path must genuinely check application readiness and not depend on a non-essential external system.

### 10.1. Group deployment sequence

1. Build and test the image.
2. Create a new template revision.
3. Create the group with min/desired/max capacity and zone distribution.
4. Verify member VMs are created with the right image, size, disk, network, and identity.
5. Wait for bootstrap to complete and health checks to pass.
6. Register backends with the load balancer or verify automatic integration.
7. Run smoke tests and inspect metrics.
8. Enable autoscaling after confirming the group operates stably.

Do not enable scale-out before verifying that the subnet has enough available IPs, quotas are sufficient, and bootstrap can succeed when multiple VMs are launched simultaneously.

## 11. Drift control and configuration consistency

Drift occurs when the actual VM configuration diverges from the managed template or baseline. For example, someone logs into a VM and manually installs a package, opens a port, modifies a config file, or attaches a disk.

In a managed group, new members may be recreated from a clean template while older members still retain manual edits. This produces a heterogeneous fleet.

Control measures:

- Use immutable images and repeatable bootstrap scripts.
- Manage templates via IaC and review changes through version control.
- Restrict SSH/RDP logins and manual edits in production.
- Scan inventory and compare runtime configuration against the baseline.
- Use instance refresh to replace drifted VMs with fresh members from the standard template.
- Document necessary exceptions along with an expiration timeline for removal.
- Never update a template while skipping the rollout of existing members.

A template is the configuration source for newly created VMs, but it is not always a mechanism that automatically fixes drift inside running VMs. A clear process for updating or replacing members is essential.

## 12. Observing and operating managed groups

Monitor the group at both the group level and the instance level.

| Metric/status | Operational question |
| --- | --- |
| Desired vs actual capacity | Does the group have the target number of VMs? |
| Healthy/in-service instances | How many VMs are actually ready to receive traffic? |
| Pending/launching instances | How long do new VMs take to boot and bootstrap? |
| Launch/terminate failure | Are there quota, IP, image, KMS, permission, or capacity errors? |
| Replacement rate | Are VMs being replaced continuously due to bad health checks or app errors? |
| Template revision per VM | Is the fleet unexpectedly running multiple revisions? |
| Zone distribution | Are members distributed properly, and is capacity sufficient if one zone fails? |
| Scale-in events | Are requests or jobs interrupted when capacity decreases? |
| Cost and utilization | Are VMs over-provisioned or starved of resources? |

Configure alerts for:

- Actual capacity staying below desired capacity for an extended period.
- Healthy capacity dropping below serving thresholds.
- Spikes in launch failures.
- Multiple instances being terminated or replaced consecutively.
- A zone losing capacity or prolonged distribution skew across the group.
- A rollout stalling or halting due to health checks.
- Members running outdated template revisions past the allowed window.

## 13. Common configuration issues

### 13.1. Group fails to launch enough instances

Causes may include quotas, zone capacity, subnet IP exhaustion, missing images, inaccessible KMS keys, insufficient IAM permissions, or invalid startup configurations.

Troubleshooting steps:

1. Check group activity/events and specific launch error messages.
2. Check quotas, zone capacity, and instance types.
3. Verify the image/template version still exists.
4. Check subnet IP address capacity and security policies.
5. Verify permissions to read the image, use encryption keys, and attach to the network.
6. Inspect the bootstrap logs of a test instance.

### 13.2. VMs are created but unhealthy

This can happen due to an overly short grace period, a wrong health endpoint, slow application startup, unready dependencies, or security groups blocking probes.

Do not increase the grace period indefinitely to mask failures. Measure boot/bootstrap time, fix the readiness endpoint, and verify the probe path from the load balancer/health service.

### 13.3. New template does not apply to existing members

Template updates may only affect newly launched VMs. Check whether an update policy, instance refresh, or rolling upgrade has been triggered, and which revision the group references.

### 13.4. Scale-in disrupts the application

If requests or jobs are cut off, check connection draining, lifecycle hooks, shutdown timeouts, and checkpointing mechanisms. For queue workers, ensure in-flight messages can be safely retried.

### 13.5. Fleet has inconsistent configurations

Inspect template revisions, user data, image digests, runtime packages, and manual changes. Standardize with a new image and controlled rollout; do not rely on manually patching individual VMs.

## 14. Common mistakes

- Using templates that point to mutable image aliases without version control.
- Putting long-lived secrets into user data or metadata.
- Treating a running VM state as an indicator of a healthy application.
- Configuring health checks that are too shallow or depend on too many auxiliary services.
- Failing to configure a grace period for slow startups.
- Updating a template without rolling out existing members.
- Using local disks to store unique business data.
- Skipping connection draining before scale-in.
- Enabling scale-in protection indefinitely on all instances.
- Failing to verify subnet IPs, quotas, and capacity before enabling autoscaling.
- Placing all VMs in a single zone despite multi-zone fault tolerance requirements.
- Allowing manual drift that causes members in the same group to diverge in configuration.
- Letting the group continuously create and delete VMs when the image or bootstrap has a systemic error.

## 15. Managed instance group design checklist

**Template**

- [ ] Image ID/version is pinned and tested.
- [ ] Machine type, architecture, and accelerators match the workload.
- [ ] Boot/data disks have clear type, size, encryption, and delete policies.
- [ ] Network, subnet, firewall/security group, and IP mode match the design.
- [ ] Workload identity follows least-privilege principles.
- [ ] Startup/bootstrap is idempotent, has timeouts, and contains no long-lived secrets.
- [ ] Tags/labels, monitoring, and logging are configured.

**Group**

- [ ] Min, desired, and max capacity are appropriate.
- [ ] Health checks validate readiness at the right layer.
- [ ] Grace period is sufficient for boot/bootstrap.
- [ ] Zone distribution and reserve capacity meet requirements.
- [ ] Update/refresh policy defines clear batch, surge, and unavailable limits.
- [ ] Scale-in has draining, shutdown hooks, and checkpointing.
- [ ] Instance protection and lifecycle handling are defined.

**Operations**

- [ ] Alarms exist for launch failures and healthy capacity.
- [ ] Template revision is tracked per member.
- [ ] Rollback procedure is documented for failed rollouts.
- [ ] Inventory tracking and drift detection are in place.
- [ ] Business data exists independently of replaceable VMs.
- [ ] Scale-out, scale-in, autohealing, and zone failures have been tested in non-production environments.

## 16. Safe template change procedure

1. Define the change objective: OS patching, runtime upgrade, resizing, network, or identity changes.
2. Create a new image/template revision without ambiguously mutating the active configuration.
3. Scan the image, test bootstrap, and verify permissions.
4. Create a test group or deploy a canary with a small number of members.
5. Verify boot, readiness, networking, storage, logging, and application metrics.
6. Begin a rolling update with appropriate surge/unavailable limits.
7. Monitor healthy capacity, errors, latency, throughput, and cost.
8. Halt the rollout if health or SLOs degrade; roll back the template or traffic.
9. Verify the entire fleet is running the expected revision.
10. Mark the old revision deprecated and retain metadata for audit/rollback per retention policies.

## 17. Operational principles

1. **Single clear configuration source:** use versioned templates as the standard for creating member VMs.
2. **Design replaceable members:** store business state outside the VM lifecycle.
3. **Maintain observable desired capacity:** monitor desired, actual, and healthy capacity together.
4. **Layer-appropriate health checks:** distinguish infrastructure, guest, and application readiness.
5. **Distribute across failure domains:** balance zone placement, latency, transfer costs, and availability.
6. **Version and roll out:** template changes must have an update strategy and rollback capability.
7. **Controlled shutdown:** drain requests, finish jobs, and checkpoint before scale-in.
8. **Least privilege:** attach dedicated workload identities and avoid long-lived credentials in templates.
9. **Control drift:** restrict manual edits and reconcile runtime state against the baseline.
10. **Test the full lifecycle:** test launch, replacement, scaling, updates, and zone failures before production.

A managed instance group combines a controller that maintains machine count with a template describing each member's configuration. When templates are versioned, health checks accurately reflect serving readiness, and applications tolerate VM replacement, the fleet can scale and recover much more consistently. Careful management of disks, identity, networking, bootstrap, rollouts, and scale-in helps the group meet demand while keeping data, availability, and costs within target bounds.
