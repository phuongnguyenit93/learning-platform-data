# Distinguishing Stop, Deallocate, and Hibernate Across Service Models

When a virtual machine no longer needs to process load, operations teams can turn it off to reduce costs, free compute capacity, or preserve state to resume work later. However, **stop**, **deallocate**, and **hibernate** do not mean the same thing. They differ in whether the operating system is shut down cleanly, whether CPU/RAM capacity on the host is retained, whether in-memory data is saved and restored, and what types of charges continue to accrue.

For **CLOUD_CORE_SERVICES_COMPUTE**, understanding the VM lifecycle accurately helps you choose how to pause workloads, manage resources, protect data, and optimize operational costs. Even a single term like Stop can result in different states and billing behavior across providers. Therefore, always inspect the machine's actual state and the service's policy rather than relying solely on button names.

## 1. Lifecycle of a Virtual Machine

A virtual machine typically passes through states such as creating, starting, running, pausing, stopping, deallocating, or deleted. State names and transition behaviors depend on the platform.

Common actions:

- **Start:** requests the platform to boot the virtual machine and allocate compute capacity.
- **Stop:** shuts down the operating system or instructs the control plane to stop the machine. Whether host capacity is kept or released may vary.
- **Deallocate:** releases the compute capacity allocated to the virtual machine, while the VM object and certain attached resources continue to exist.
- **Hibernate:** saves memory contents and required state to platform-supported storage, then halts compute capacity so the session can be resumed later.
- **Restart/Reboot:** restarts the operating system within the same machine lifecycle; not equivalent to creating a new machine.
- **Delete/Terminate:** deletes the virtual machine object. Whether disks, IPs, and related resources are deleted alongside it depends on policies and delete-with-VM configuration.

The main transitions can be visualized as follows:

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: Create VM / not yet running
    Stopped --> Running: Start
    Running --> Stopped: Stop
    Running --> Deallocated: Deallocate
    Deallocated --> Running: Start / Allocate
    Running --> Hibernated: Hibernate
    Hibernated --> Running: Resume
    Running --> Deleted: Delete / Terminate
    Stopped --> Deleted: Delete
    Deallocated --> Deleted: Delete
    Hibernated --> Deleted: Delete
~~~

This diagram is a conceptual model. Some platforms combine Stop with deallocate; some use Suspend instead of Hibernate; and some services do not support a hibernation state.

## 2. Stop: Halting the Machine or Shutting Down the OS

Stop is generally understood as requesting the virtual machine to stop running. However, two execution methods must be distinguished:

1. **Shutdown from inside the guest OS:** an administrator or the operating system initiates shutdown via the Linux/Windows shutdown sequence. Services get a chance to finish operations, close files, and flush data.
2. **Stop from the control plane:** a user calls the provider's API, CLI, or management console to stop the machine. The platform may perform a guest shutdown and then retain or release host capacity depending on the service's definition.

These two actions can produce a similar displayed state while differing in resource allocation and billing.

### 2.1. Stop That Retains Compute Capacity

Some platforms have a state where the OS is shut down, yet the machine remains allocated on the host. In this case:

- The machine does not execute workloads and CPU is not used by applications.
- Compute capacity or a host slot remains reserved for the machine.
- The machine may restart faster or retain certain placement constraints.
- The provider may continue charging for compute because capacity remains dedicated.
- Disks, IPs, snapshots, and related resources continue under their own billing policies.

Azure clearly illustrates the difference between **Stopped** (the guest OS is shut down but still allocated) and **Stopped (deallocated)** (host capacity has been released). Shutting down the OS from inside the machine does not automatically guarantee the machine is deallocated.

### 2.2. Stop Where the Platform Releases Compute

In some services, a Stop action from the control plane moves the machine to a stopped state and releases compute capacity. For example, AWS EC2 transitions an instance to the Stopped state; compute usage charges for the instance stop, while EBS volumes and other resources may still incur charges.

Google Compute Engine also has a Stopped state: the machine no longer consumes vCPU/RAM as when running, while persistent disks and retained resources may continue to be billed. Details such as ephemeral IP addresses and local storage depend on resource type.

The key is to check the final state and the service's pricing table. Never assume a machine has stopped incurring charges solely because the operating system is no longer responding.

### 2.3. When Should You Use Stop?

Stop is appropriate when:

- You need to shut down an application gracefully for maintenance or inspection.
- You need to pause a machine temporarily for a short period.
- You want to keep the machine object and disks to start it again later.
- You do not need to preserve the RAM contents of running processes.
- The service offers a Stop state with suitable cost and startup time.

Before stopping, drain requests, stop accepting new tasks, finish or checkpoint jobs, flush data, and verify that services have shut down cleanly.

## 3. Deallocate: Releasing Host Capacity

**Deallocate** is the action of instructing the platform to release the compute capacity assigned to a virtual machine. While Stop may only shut down the guest OS, Deallocate explicitly states that CPU/RAM on the host are no longer reserved for that machine.

Typically, after deallocation:

- The VM is not running and has no vCPU/RAM allocated on a host.
- The platform can reassign the freed capacity to other workloads.
- The VM object and persistent disks may continue to exist.
- Compute billing typically stops while deallocated.
- Charges for disks, snapshots, static IPs, licenses, or related resources may continue.
- Upon starting again, the platform must locate available capacity; the machine may be placed on a different host.

Deallocate does not mean Delete. A deallocated machine can still be started again if configuration and quotas remain valid.

### 3.1. Which Resources Are Retained?

| Component | Typical State After Deallocate | What to Verify |
| --- | --- | --- |
| Virtual machine object | Continues to exist | State, configuration, and management permissions |
| vCPU/RAM on host | Released | Time when deallocation completes |
| Persistent OS disk and data disks | Usually retained | Delete-with-VM policy and storage charges |
| Local/ephemeral disk | Data may be lost | Guarantees of the machine type and disk type |
| Private IP | Usually retained within the same virtual network | Platform addressing policy |
| Dynamic public IP | May be released | Use a static IP if the address must remain stable |
| Static IP or reserved resources | May remain retained and billed | Address retention fees and attachment scope |
| Snapshots, backups, disk encryption keys | Follow their own lifecycles | Retention policy and access permissions |

No single rule applies to every provider and every disk type. Before deallocating, distinguish data on persistent disks from temporary data on local SSDs, temporary disks, or RAM.

### 3.2. When Should You Use Deallocate?

Deallocate is appropriate when:

- Development, testing, or demo environments do not need to run after hours.
- Workloads can stop and restart without preserving in-memory process state.
- You need to release compute to reduce costs during idle periods.
- Re-provisioning wait time on startup is acceptable.
- Data that must be kept is already on persistent storage or backed up.

Deallocate is especially useful for workloads with predictable schedules, such as test environments active only during business hours. For workloads requiring instant responsiveness or persistent connections, account for reallocation and service startup time.

## 4. Hibernate: Saving Memory State to Resume Later

**Hibernate** is a mechanism that saves RAM contents and essential machine state to supported storage, then stops the machine. Upon resume, the platform restores the saved state so the operating system and processes can continue from the previous session.

Hibernate differs from regular Stop or Deallocate in that its goal is preserving memory state:

- RAM contents are written to storage or a platform-managed state store.
- Host CPU/RAM capacity is usually released while the machine is hibernated.
- On resume, the platform reloads the saved memory state.
- Disks and the hibernate state storage area continue occupying space and may incur charges.
- Restoration depends on support from the machine type, OS, RAM size, and disk configuration.

Hibernate typically resumes faster than booting fresh and reloading applications from scratch, though it does not guarantee every resume succeeds or that all external connections remain valid.

### 4.1. What Does Hibernate Save and What Does It Not Guarantee?

Hibernate is designed to save OS and process memory state at the moment of hibernation. However, it does not replace application data backups:

- Data durably written to disk continues to follow the disk's storage guarantees.
- Data residing only in RAM may be preserved in the hibernate snapshot, but recovery depends on the platform and snapshot integrity.
- TCP connections, remote login sessions, leases, tokens, and other server-side state may expire while the machine is asleep.
- Data on ephemeral storage remains subject to that resource's lifecycle risks.
- Active writes or in-progress transactions must be handled safely by the application before hibernating.

After resuming, applications should re-verify database connections, message brokers, DNS, tokens, and time-bound dependencies. Distributed systems must be capable of reconnecting and recovering sessions.

### 4.2. Support Requirements and Limitations

Hibernate is typically supported only on a specific set of machine types, operating systems, and configurations. Requirements may include:

- The instance type or VM size must support hibernate.
- The operating system and kernel/agent must be compatible.
- The OS disk or state storage area must have enough capacity and meet encryption requirements.
- RAM size must not exceed the service's limit.
- The hibernate option may need to be enabled at machine creation time.
- Certain GPU, local disk, confidential computing, or specialized device configurations may not be supported.
- There may be limits on state retention duration or resume counts.

If hibernate fails, the platform may fail to save memory state. Always have a fallback plan to normal shutdown/deallocate and application recovery from durable data.

## 5. Comparing Stop, Deallocate, and Hibernate

| Criterion | Stop | Deallocate | Hibernate |
| --- | --- | --- | --- |
| Guest OS | Shut down or halted per platform behavior | Usually shut down before releasing host | Saves memory state via hibernate mechanism |
| CPU/RAM on host | May remain retained or be released depending on service | Released | Usually released |
| RAM contents | Not guaranteed to be preserved | RAM state not preserved | Saved for restoration if successful |
| Restart behavior | Boots OS from scratch | Allocates host then boots from scratch | Resumes from saved state |
| Persistent disks | Usually retained | Usually retained | Retains disks and hibernate state storage |
| Local/ephemeral data | Depends on platform and disk type | May be lost | Depends on disk type and hibernate implementation |
| Compute cost | Depends on whether host is retained or released | Usually stops | Usually stops once in hibernated state |
| Storage/IP cost | May continue | May continue | May continue, plus hibernate state capacity |
| Best suited for | Short pauses without needing RAM preserved | Longer pauses to save compute costs | Needing to resume an open working session |

The most important distinction is that **Deallocate releases host capacity**, whereas **Hibernate saves RAM state to resume**. Stop is the most easily misunderstood term because its meaning depends on whether it is invoked from the guest OS or the control plane and how the provider implements it.

## 6. How Providers Represent States

Major platforms have different naming and billing models. The table below describes common conventions; details may vary by machine type, region, OS, and product policy.

| Concept | AWS EC2 | Microsoft Azure VM | Google Compute Engine |
| --- | --- | --- | --- |
| Normal stop | Stop instance puts instance into Stopped state; instance compute usage stops | Has Stopped (still allocated) state if shut down from guest; compute charges may continue | Stop VM puts machine into Stopped state; vCPU/RAM stop running |
| Release compute | Stop instance usually releases host capacity; no separate Deallocate operation like Azure | Deallocate releases host capacity and stops compute charges | Stop releases compute capacity; Deallocate term is not commonly used |
| Preserve RAM state | EC2 supports Stop with hibernation for eligible instance types and configurations | Azure supports Hibernate on supported VM sizes and configurations | Suspend/resume is a closely equivalent mechanism for saving memory state; support scope and fees differ from hibernate |
| Remaining billable resources | EBS, IP addresses, and related resources per policy | Managed disks, static IPs, and related resources per policy | Persistent disks, static IPs, and related resources per policy |

A few notes when reading the table:

- AWS EC2 can stop an instance without preserving RAM; if hibernation is enabled and the instance is eligible, RAM contents are saved to the EBS root volume before the instance enters the stopped state.
- Azure distinguishes an in-guest shutdown from a control-plane deallocate. A Stop button in the portal/API may perform deallocation depending on the operation; check whether the displayed state is Stopped or Stopped (deallocated).
- Google Compute Engine uses Suspend/Resume to save machine state while stopping CPU allocation. This is conceptually close to hibernate, though billing for saved memory, limits, and support conditions should be checked in the documentation for the specific VM type.

Never port a procedure from one provider to another merely by swapping API names. Verify post-operation states, retained resource types, when compute billing stops, and resume conditions on the target platform.

## 7. Differences Across IaaS, Managed Platforms, and Containers/Serverless

The operations above primarily describe VM lifecycles in IaaS. Moving up to higher-level managed services, users typically control workloads or replicas instead of directly controlling hosts.

### 7.1. IaaS: User Manages the Virtual Machine

In IaaS, operations teams typically decide when to start, stop, deallocate, or hibernate machines. Users manage the guest OS, disks, agents, applications, and shutdown procedures.

Decisions to evaluate:

- Does the machine need to retain RAM to continue a processing session?
- Which disks must be retained and which hold temporary data?
- Must IPs or network identities persist after deallocation?
- Is reserved host capacity needed to meet startup time targets?
- Can the application recover from checkpoints or queues instead of hibernating?

### 7.2. Managed Instance Groups and Autoscaling

With managed instance groups, autoscaling groups, or machine-group managers, the platform can replace or delete instances according to policies. Scale-in typically terminates a machine without preserving its RAM state.

If a workload must continue after an instance is replaced, the application should store state in a database, object storage, queue, or external checkpoint. Hibernating an instance is not a default strategy for autoscaling because the scheduler needs freedom to replace machines and distribute workloads flexibly.

### 7.3. Containers and Kubernetes

Containers generally do not have deallocate or hibernate operations in the VM sense:

- Stopping a container/pod usually terminates the process and frees node resources.
- Creating a new container from an image starts the process fresh; previous RAM state is not automatically restored.
- Persistent volumes can retain data if configured properly; temporary container filesystems may be lost.
- Kubernetes can scale a workload to zero replicas, though that does not necessarily release nodes if nodes remain in the cluster.
- A cluster autoscaler may shrink the node pool after pods have been evicted or terminated, depending on configuration.

If work must resume, containerized applications should support checkpoints, graceful termination, and recovery from persistent storage.

### 7.4. PaaS and Serverless

In PaaS or serverless, the provider manages the underlying servers. Users typically control instance counts, replica counts, concurrency levels, schedules, or scale-to-zero.

Scale-to-zero means zero application instances are actively serving for a period; it is not the same as hibernating a specific virtual machine. The runtime may be reinitialized on the next invocation, and previous process memory is not guaranteed to persist. Some platforms may keep execution environments warm briefly, but applications should not rely on that for storing business state.

## 8. Cost Impact

Turning off a machine does not mean total machine costs drop to zero. While compute stops, remaining resources can still be billed.

Components to review:

| Component | When Compute Stops |
| --- | --- |
| Instance vCPU/RAM | Usually stops billing when deallocated or in stopped state per provider model |
| OS disk and data disks | Usually continue billing by capacity/performance tier |
| Snapshots and backups | Continue billing by capacity, retention time, and service tier |
| Static public IP | May continue billing while unattached or retained |
| Software licenses | May be billed hourly, per core, or per separate agreement |
| NAT, load balancer, gateway, and managed services | Have independent lifecycles and billing models |
| Hibernate state | May consume additional storage capacity or incur a separate fee |

A simple estimation formula:

\[
\text{Stopped Cost} =
\text{Disk} + \text{Snapshot} + \text{IP} +
\text{License} + \text{Related Resources}
\]

Compute cost savings depend on deallocation duration, hourly machine price, startup time, and automation overhead. For a machine shut down for only a few minutes, savings may be small compared to startup latency and effort. For dev environments shut down overnight or over weekends, deallocate is usually worthwhile.

Hibernate can save compute costs while increasing RAM-state storage costs. If RAM size is large and sleep duration is short, compare state storage cost against the benefit of faster recovery.

## 9. Protecting Data Before Stopping or Hibernating

Before transitioning states, classify data by storage location:

- **Durable data:** databases or files on persistent disks, object storage, and storage services with durability guarantees.
- **Temporary data:** caches, temporary filesystems, local ephemeral disks, and data in RAM.
- **Process state:** heap memory, stack, file descriptors, locks, sockets, and active sessions.

Regular stop or deallocate does not guarantee preserving process state. Hibernate can save RAM, yet you must still ensure the application is not mid-transaction and that dependencies can reconnect.

Safe pre-stop workflow:

1. Stop accepting new requests or tasks.
2. Drain load balancers and queues within the allowed window.
3. Complete transactions or write checkpoints for long-running jobs.
4. Flush data and close files according to application procedures.
5. Persist necessary operational state to durable storage.
6. Execute shutdown or hibernate cleanly.
7. Verify the final state from the control plane.

For database workloads, use the shutdown procedure supported by the database engine. Never force-stop a machine while writing data unless recovery capability has been evaluated and the risk is accepted.

## 10. Choosing Actions by Workload

| Need | Typically Suitable Action | Reason |
| --- | --- | --- |
| Brief maintenance requiring clean shutdown | Stop | Shuts down the OS cleanly |
| Dev/test machine idle for many hours | Deallocate or Stop that releases compute | Saves host costs when not needed |
| Application needing to resume an in-RAM session | Hibernate if supported | Restores process state |
| Batch worker with checkpoints | Deallocate after saving checkpoint | Another worker can start and resume from durable data |
| Stateless web/API in autoscaling group | Scale-in/terminate per policy | Replacement instances can be created as load rises |
| Container with business state | Graceful termination and external state storage | New containers do not restore old container RAM |
| Low-traffic serverless | Scale-to-zero per platform policy | No VM lifecycle management needed |

The final decision should consider downtime tolerance, RTO, RPO, data durability, latency requirements, and total cost.

## 11. Example: Pausing a Test Environment After Hours

A development team runs a VM hosting an integration test environment. The machine is used only during business hours, with an OS disk and a data disk storing configuration and test data. Critical logs are shipped to a centralized system.

The team designs a shutdown schedule as follows:

1. Before stop time, the pipeline notifies users and stops accepting new test runs.
2. Workers complete active jobs or write checkpoints to durable storage.
3. The application closes database connections and performs a clean OS shutdown.
4. Automation invokes deallocate and verifies the machine enters the compute-released state.
5. OS and data disks remain retained; a static IP is kept if fixed-address access is required.
6. Before business hours, automation starts the machine and checks agents, disks, networking, and health endpoints.
7. If the machine is not ready within the defined timeout, the system sends an alert and escalates to an incident workflow.

The team does not need hibernate because the application can restart from durably stored state. If the machine runs long analytical sessions requiring process retention and very long re-initialization times, the team can evaluate hibernate on a supported machine type after testing state integrity and RAM storage cost.

## 12. Automating Stop, Deallocate, and Hibernate

Automated schedules prevent idle machines from running continuously, but must include safeguards for workloads.

A workflow might look like:

~~~mermaid
flowchart TD
    A["Scheduled shutdown time reached"] --> B{"Does the machine have active workloads?"}
    B -- "Yes" --> C["Drain requests and stop accepting jobs"]
    C --> D["Finish jobs or write checkpoints"]
    D --> E{"Need to preserve RAM state?"}
    B -- "No" --> E
    E -- "Yes" --> F{"Does VM support hibernate?"}
    F -- "Yes" --> G["Hibernate and verify state"]
    F -- "No" --> H["Shutdown/Deallocate per recovery plan"]
    E -- "No" --> H
    G --> I["Monitor state and costs"]
    H --> I
~~~

Required control points:

- Only target machines in groups authorized for automated shutdown.
- Exclude machines serving production traffic or running non-interruptible jobs.
- Use tags/labels or managed schedules to identify owners and time windows.
- Log actions, before/after states, and verification results.
- Set timeouts for draining and shutdown; when exceeded, apply an approved fallback policy.
- Prevent two automations from operating on the same machine simultaneously.
- Check whether the machine gets automatically restarted by autoscaling, policies, or another schedule.
- Configure alerts if start or resume fails.

Do not apply a simple deallocate schedule to machines acting as coordinators, quorum members, primary databases, or high-availability workloads without first designing a role-transfer mechanism.

## 13. Common Mistakes

- Assuming an in-guest OS shutdown always releases compute capacity.
- Confusing Deallocate with Delete and accidentally deleting resources meant to be kept.
- Assuming stop/deallocate preserves data across all disk types.
- Failing to check whether dynamic IPs get released after stopping a machine.
- Assuming hibernate guarantees all external connections and sessions continue uninterrupted.
- Failing to verify hibernate support requirements for VM size, OS, and disks.
- Calculating only compute savings while forgetting disks, IPs, snapshots, licenses, and related services.
- Automatically shutting down a machine while jobs are actively writing data or holding critical roles.
- Failing to test start/resume and recovery workflows before enabling schedules in production.
- Treating container/serverless scale-to-zero as if it were VM hibernation.

## 14. Operational Principles

1. **Read actual state:** verify the state from the control plane after every operation.
2. **Separate Stop from Deallocate:** explicitly confirm whether the machine still holds host capacity or has released it.
3. **Use Hibernate conditionally:** enable only when platform, machine type, and OS support it, and resume has been tested.
4. **Keep data durable:** store business data and checkpoints outside RAM, especially for replaceable workloads.
5. **Account for full costs:** compute, disks, snapshots, IPs, licenses, and supporting resources.
6. **Design for recovery:** test reconnection, health checks, start/resume, and fallback plans.
7. **Automate with safeguards:** drain workloads, verify roles, log actions, and restrict the scope of stoppable machines.
8. **Respect the service model:** IaaS allows managing the VM lifecycle; containers and serverless typically require storing state at the application tier.

Stop, deallocate, and hibernate are three ways to manage machine state with different goals. Choosing the right operation requires understanding whether host capacity is kept, which data persists, which costs continue, and how the application recovers. When these factors are built into operational procedures, engineering teams can save compute costs while safeguarding data, resilience, and service experience.
