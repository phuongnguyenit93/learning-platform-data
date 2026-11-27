# Designing Virtual Machine Groups and Standardized Machine Images

In **Cloud Architecture**, virtual machines (VMs) are a flexible choice for applications, background services, self-managed databases, and workloads requiring OS-level control. As VM counts grow, creating machines manually causes configuration drift, complicates patching, hinders auditing, and increases operational risk. Two foundational practices solve this: **VM groups** and **standardized/golden images**.

VM groups define machines that share a role, policies, scaling behavior, and lifecycle. Standardized machine images provide a reproducible, tested, versioned OS and base-software foundation. Combining both enables consistent deployments, fast recovery, and scalable fleet management, while supporting trade-off evaluations across **reliability, security, scalability, cost, and operations** under Well-Architected principles.

After this lesson, you will be able to:

- Classify VMs by workload, environment, criticality, and operational requirements.
- Design VM groups using templates, instance groups, scale sets, or equivalent mechanisms.
- Understand the role of golden images, image pipelines, image catalogs, and version management.
- Build a secure pipeline for image creation, testing, approval, publishing, and retirement.
- Combine images with `cloud-init`, startup scripts, configuration management, and secret management.
- Plan patching, rollouts, rollbacks, autoscaling, backups, and recovery for VM groups.
- Translate architectural requirements into measurable, auditable acceptance criteria.

## 1. What Is a Virtual Machine Group?

A **VM group** is a collection of instances managed under a shared purpose. Depending on the cloud platform, it may be called an instance group, virtual machine scale set, autoscaling group, managed instance group, or a set of resources orchestrated via IaC and configuration management. Service names and features differ across providers, but the core idea is standardizing how VMs with similar roles are created, configured, updated, and operated.

For example, a web application might have three groups:

- **Web group:** receives HTTP/HTTPS from a load balancer, runs web/API processes, and scales by request rate or CPU.
- **Worker group:** processes queues and background tasks, scaling by queue depth or processing lag.
- **Admin group:** serves controlled administrative workflows with a small instance count, tight access, and strict auditing.

Each VM in a group may differ in hostname, IP address, zone, or identifying metadata, yet must follow a **shared configuration contract**: OS, image family/version, allowed instance types, security profile, monitoring agents, logging, patching policy, and management method.

### 1.1. Distinguishing Logical Groups from Platform-Managed Groups

| Group Type | Characteristics | Example Use |
| --- | --- | --- |
| **Logical group by inventory/tags** | Uses tags or inventory to group VMs; lifecycles are not necessarily coordinated together | Selecting production VMs to apply a group patch policy |
| **Fixed deployment group** | Uses a template to create a predetermined number of instances; can span multiple zones | An application group with 3 minimum replicas |
| **Autoscaling/managed group** | Platform adjusts VM count based on policies, health checks, and templates | Web tier scaling from 3 to 12 instances under load |
| **Specialized workload group** | Tied to disks, placement, operational schedules, or dedicated node requirements | Database nodes, license-bound workloads, GPU workers |

A logical group helps administration but does not automatically provide autoscaling, unhealthy instance replacement, or load balancing. Conversely, a managed instance group has built-in lifecycle and health check mechanisms. When designing, specify the exact mechanism used rather than calling everything a "VM group."

### 1.2. Do Not Group VMs Simply Because They Share a Size

Two VMs both running 4 vCPUs and 16 GiB RAM do not necessarily belong in the same group. A stateless API server and a database server have different requirements for data, network permissions, backups, restarts, availability, RTO/RPO, scaling behavior, and health checks.

**Workload role and lifecycle** are the primary criteria. Instance type is merely a resource attribute.

## 2. Classifying Workloads Before Creating VM Groups

Good VM groups start from business requirements and workload behavior, not from slicing a server list into equally sized buckets.

| Dimension | Questions | Impact on Grouping |
| --- | --- | --- |
| **Application role** | Web, API, worker, scheduler, database, or admin tool? | Determines image, ports, processes, and dependencies |
| **Environment** | Dev, test, staging, production, or DR? | Separates permissions, data, accounts/projects, and policies |
| **Criticality** | Does the workload directly impact transactions or support functions? | Sets HA, patch windows, monitoring, and recovery priority |
| **Load profile** | CPU-bound, memory-bound, I/O-bound, bursty, or continuous? | Drives instance family, scaling metrics, and limits |
| **Statefulness** | Stateless or stateful? | Determines replaceability, storage, and backup design |
| **Compliance** | Handles personal, payment, or regulated data? | Dictates network, encryption, access, region, and auditing |
| **Hardware** | `x86_64`, `ARM64`, GPU/NPU, or specialized devices? | Selects compatible images and instance types |
| **Lifecycle** | Frequently replaceable or long-lived? | Guides rolling replacement, patching, and maintenance |
| **Operational ownership** | Which team owns and is on-call for it? | Assigns owners, escalation paths, and maintenance windows |

### 2.1. Example VM Group Matrix

An equipment rental platform could organize its groups as follows:

| VM Group | Workload | Characteristics | Scaling Policy | Key Requirements |
| --- | --- | --- | --- | --- |
| `prod-web` | Stateless web/API | High request volume, moderate CPU | Request rate, CPU, or custom metric | Multi-zone, health checks, no local session state |
| `prod-worker` | Message processing | CPU and queue dependent | Queue backlog/processing lag | Idempotent, graceful shutdown |
| `prod-batch` | Scheduled reporting | Scheduled spikes in CPU/RAM and I/O | Scheduled or queue-based | Limit impact on transactional DB |
| `prod-admin` | Internal admin tools | Few instances, elevated privileges | Usually fixed | Private access, MFA, audit logging |
| `staging-web` | Integration testing | Variable load | Small on-demand scaling | Isolated from production, sanitized data |
| `dr-web` | Recovery capacity | Warm or pilot light | Per DR plan | Pre-tested images and configs |

This is a logical example; a system might use containers for web/workers and VMs for databases or legacy components. You do not have to force every workload onto VMs just because you are designing VM groups.

### 2.2. Separating Groups by Blast Radius

A single group should not span machines whose failures or changes carry vastly different impacts. Consider splitting groups when network permissions, data access, maintenance schedules, criticality, scaling metrics, hardware, patch cadences, or owning teams differ.

Avoid over-splitting until every VM sits in its own group with no practical benefit. The goal is balancing **clear administrative boundaries** against **policy maintenance overhead**.

## 3. What Is a Standardized Machine Image?

A **machine image** is a template packaging the initial state of a VM, typically including the OS, boot configuration, and pre-installed software or settings. Depending on the cloud, an image may be called a machine image, AMI, image version, or managed image.

A **standardized image (golden image)** is an image produced through a controlled pipeline with clear provenance, versioning, test evidence, security posture, and explicit approval. It provides a consistent baseline for provisioning VMs in an environment or workload group.

A well-built golden image:

- Shortens provisioning time and reduces manual installation.
- Reduces configuration variance across instances.
- Ensures platform, logging, and security agents are pre-installed.
- Supports auditing and incident investigation by tracking which image/version created each VM.
- Rebuilds machines after failures reproducibly.
- Controls OS and base library versions.

A golden image is **not an ad-hoc snapshot of a running production machine**. If an image contains live data, secrets, tokens, private keys, or dirty machine state, cloning it can leak sensitive material across many instances.

### 3.1. What Goes Into an Image?

| Component | Include in Image? | Notes |
| --- | --- | --- |
| Supported OS and kernel | Yes | Pick versions still receiving security support |
| Security updates and base packages | Yes | Record build timestamp and update sources |
| Standard CA certificates and trust config | Yes, if policy allows | Never embed environment-specific private keys |
| Monitoring/logging agents | Usually yes | Endpoints and identities can be injected at boot |
| Shared runtimes like Java | Depends on role | Record exact version, source, and update path |
| Specialized apps/agents | Possible | Package if version and rollout must align with the image |
| Environment configuration | Immutable, non-sensitive parts | Externalize endpoints or mutable feature settings |
| Secrets, API keys, passwords, tokens | No | Fetch from a secret manager or runtime mechanism |
| User data, database dumps, logs | No | Use durable storage and appropriate data pipelines |
| SSH private keys, shared machine identity | No | Each machine requires its own unique identity |

Some organizations build minimal images and install apps at boot; others bake applications into the image for greater immutability and faster startup. Both work if build pipelines, provenance, testing, and rollouts are sound.

## 4. Designing an Image Pipeline

Reliable machine images are produced as versioned artifacts with a managed lifecycle.

~~~mermaid
flowchart LR
    SRC["Approved OS base image"] --> BUILD["Automated image build"]
    CODE["Recipe / package manifest"] --> BUILD
    BUILD --> HARDEN["Hardening and baseline"]
    HARDEN --> SCAN["Patch, vulnerability, and compliance scan"]
    SCAN --> TEST["Boot, agent, and application smoke tests"]
    TEST --> REVIEW["Review and approval"]
    REVIEW --> SIGN["Provenance / signing if supported"]
    SIGN --> PUBLISH["Publish immutable image version"]
    PUBLISH --> ROLLOUT["Canary / rolling rollout"]
    ROLLOUT --> OBS["Monitor, rollback, or retire"]
~~~

Key stages:

1. **Select base image source:** official or internally approved source; verify publisher, checksum, or signature where available.
2. **Reproducible build:** use Packer, a provider's image builder, or equivalent; store recipes, manifests, and dependency versions.
3. **Hardening:** apply OS baselines, SSH configuration, firewall rules, auditing, permissions, removal of unnecessary services, and host protections.
4. **Security updates:** install vetted patches; record CVEs and approved exceptions.
5. **Install agents/runtimes:** include only necessary components with pinned versions and trusted sources.
6. **Testing:** boot checks, package verification, agent health, config, file permissions, open ports, logs, and smoke tests.
7. **Approval:** automated gate or authorized reviewer checks criteria; archive scan and test results.
8. **Publish:** release an immutable version and update the image catalog.
9. **Rollout:** update via canary, rolling, or blue/green strategies depending on workload.
10. **Monitor and retire:** track VMs running older versions, deprecate, block new launches, and retire obsolete images.

### 4.1. Why Image Versions Must Be Immutable

If an image named `latest` points to different artifacts over time, the exact same deploy script can launch two VMs with different OS states. Troubleshooting becomes guesswork because you cannot tell which packages an instance booted with.

Use immutable versions or IDs, for example:

~~~text
org-linux-web-2026.11.18-build.042
org-linux-worker-2026.11.18-build.042
org-linux-base-lts-2026.11.18-build.017
~~~

These names are merely conventions. The source of truth must link to the **cloud image ID/version**, recipe commit, package manifest, scan results, and approval record. A `latest` tag can help discovery but should never be the sole reference for production deployments.

### 4.2. Packer and Image as Code

Packer is a common option for defining machine image builds as version-controlled configuration. Recipes clearly specify base sources, provisioners, variables, and outputs.

Minimal illustrative HCL example:

~~~hcl
source "amazon-ebs" "app_base" {
  region        = var.region
  source_ami    = var.approved_base_ami
  instance_type = "t3.small"
  ssh_username  = var.ssh_username
  ami_name      = "org-app-base-build"
}

build {
  sources = ["source.amazon-ebs.app_base"]

  provisioner "shell" {
    script = "scripts/install-baseline.sh"
  }

  provisioner "shell" {
    script = "scripts/security-hardening.sh"
  }
}
~~~

This only shows the structure. A real pipeline must define variables, build permissions, regions, accounts, connectivity, outputs, validation, and builder cleanup. Never hardcode credentials or treat placeholders as ready-to-apply production configs. Builder names and attributes must match your Packer/plugin version.

## 5. OS Hardening and Baselines

A golden image is an effective control point for applying uniform baselines, but hardening must align with your threat model, workload, and organizational standards.

**Accounts and authentication.** Disable unnecessary default accounts; restrict `sudo`/admin privileges; manage SSH/RDP via centralized identity or controlled access mechanisms; give every VM a distinct machine identity.

**Services and ports.** Remove or disable unused services; open only ports required by the workload; never expose SSH/RDP to the public internet by default.

**Filesystems and kernel.** Configure file permissions, mount options, and kernel parameters required by the baseline; avoid blanket tweaks that break specific workloads. Test compatibility with drivers, storage, and monitoring.

**Auditing and logs.** Enable auditing as required, recording administrative actions, logins, and critical events; ship logs centrally over protected channels. Never log tokens, passwords, or unnecessary personal data.

**Encryption and keys.** Encrypt volumes/boot disks per policy; fetch keys and secrets via runtime identity; never store shared private keys in the image.

**Software supply chain.** Pull packages only from managed repositories; pin versions for reproducibility; verify signatures/hashes; scan dependencies; track provenance and software licenses.

**Security agents.** EDR, vulnerability agents, host firewalls, or endpoint monitoring must have tracked versions, update policies, health telemetry, and remediation runbooks when agents stop reporting.

### 5.1. Baselines Are Not Rigid One-Size-Fits-All Checklists

Images for stateless web servers and databases may require different baselines. Databases need specific I/O and kernel tuning; GPU worker images need compatible GPU/runtime drivers; legacy workloads may rely on older libraries.

The right approach is maintaining a **shared base image** with core hardening, creating **role-based image families** when package/driver differences justify it, inheriting the baseline, and documenting exceptions with owners, expiration dates, and compensating controls. Do not fork a separate image family for every project if differences are merely parameters injectable at boot.

## 6. Images, Bootstrapping, and Configuration Management

Not every setting belongs inside the image. Distinguish among:

| Category | Examples | Appropriate Location |
| --- | --- | --- |
| **Immutable, shared** | OS packages, runtimes, agent versions, baseline system configs | Golden image |
| **Per-environment/group** | Region endpoints, log destinations, service ports, feature settings | IaC, templates, configuration management, or controlled metadata |
| **Secrets and identity** | Passwords, tokens, private keys, DB credentials | Secret manager, identity service, PKI, or secure provisioning |

### 6.1. `cloud-init` and Startup Scripts

`cloud-init` or startup scripts can set hostnames, register agents, fetch configs, obtain certificates, initialize services, or report readiness to a control plane.

Do not turn startup scripts into sprawling installation frameworks that slow down booting and break reproducibility. If a script pulls packages from mutable repositories, the same image version can yield different VMs across launches.

- Bake base runtimes and version-pinned components into the image.
- Use startup configs for environment parameters, machine identity, and lightweight bootstrapping.
- If installing packages at boot is unavoidable, pin versions, verify checksums, and control repositories.
- Make scripts **idempotent**: re-running must not create duplicate configs or corrupt valid state.
- Enforce timeouts, bounded retries, and clear logging; health checks must report ready only when the workload is genuinely serving.
- Never put secrets in user-data or startup logs; use least-privilege identity to retrieve them from a secret manager.

### 6.2. Configuration Drift

Configuration drift is the divergence between declared/approved configuration and actual running state. An engineer manually installing a package on a production VM makes that machine differ from the image and its peer replicas.

How to control drift: restrict direct edits on production VMs; route changes through code, recipes, and configuration management; monitor packages, agents, and security settings; detect drift via policy scans; and for stateless VMs, prefer replacing instances from a newly tested image. For stateful or legacy VMs, establish a controlled drift workflow since replacement is non-trivial.

## 7. Designing Templates for VM Groups

A VM group typically requires these inputs:

- **Image/version:** standardized image ID aligned with the role.
- **Machine type/size:** vCPU, RAM, CPU architecture, GPU if applicable.
- **Network:** VPC/VNet, subnets, security groups/firewalls, routes, and load balancers.
- **Identity:** service account/managed identity/instance profile with least privilege.
- **Storage:** boot disk, data volumes, encryption, snapshot/backup policies.
- **Metadata/bootstrap:** environment, owner, role, non-secret startup config.
- **Health:** startup, liveness/readiness, application checks, and instance replacement rules.
- **Scaling:** desired/min/max capacity, metrics, and cooldowns.
- **Maintenance:** patch windows, disruption budgets, rollout batches, and rollback settings.

Conceptual group definition example:

~~~yaml
group:
  name: prod-web
  owner: web-platform
  environment: production
  image:
    family: org-linux-web
    version: "2026.11.18-build.042"
  machine:
    architecture: x86_64
    instance_class: general_purpose
    vcpu: 4
    memory_gib: 16
  placement:
    zones: [zone-a, zone-b, zone-c]
    minimum_instances: 3
    maximum_instances: 20
  network:
    ingress: load_balancer_only
    egress_policy: approved_destinations
  identity:
    role: prod-web-runtime
    secret_source: managed_secret_store
  storage:
    boot_disk_encrypted: true
    persistent_user_data: false
  health:
    readiness_check: application_ready
    replace_unhealthy: true
  scaling:
    metric: requests_per_instance
    target: approved_capacity_target
~~~

This is an architectural description, **not a universal schema for Terraform or cloud APIs**. Instance classes, zones, metrics, targets, and policies must be mapped to a specific provider, checked against quotas, and approved before deployment.

### 7.1. Desired State vs. Observed State

- **Desired state:** target instance count, image version, machine size, configuration, and policies.
- **Observed state:** actual running instances, live versions, health, zones, packages, and disk usage.

A VM group is well-managed when you can compare both states, detect drift, and remediate discrepancies. Seeing five VMs in a group never proves they are all running the same image or latest patches.

## 8. Autoscaling and Load Balancing

For stateless workloads, managed instance groups can automatically add or remove VMs based on metrics. Autoscaling must be designed alongside load balancers and application limits.

| Metric | Best Suited When | Risk If Used Alone |
| --- | --- | --- |
| CPU utilization | Workload is primarily CPU-bound | Misses pressure when CPU is idle waiting on DB |
| Memory utilization | Workload memory scales with connections/workers | Memory rarely drops immediately during scale-down |
| Requests per instance | Web/API with measurable traffic | Must account for request cost variance and load distribution |
| Queue depth/backlog | Workers handling async tasks | Message count alone ignores message age |
| Processing lag | Streams/queues needing timely completion | Requires accurate watermarks and consumption rates |
| Scheduled scaling | Predictable peak hours | Reacts too slowly to unexpected surges |

Do not treat 70% CPU as a universal threshold. Targets depend on latency SLOs, traffic ramp rates, boot times, and instance capacity.

### 8.1. Warm-Up and Startup Time

If a VM takes 5–8 minutes to boot, configure agents, and warm up the application, reactive autoscaling after a spike starts may arrive too late. Golden images cut installation time, yet you still must measure true **time-to-ready**, including networking, secrets, dependencies, and health checks.

You may need to hold minimum instances, use scheduled scaling for known patterns, keep capacity buffers, optimize boot speed, and scale on leading indicators like request rate or queue arrival rate rather than lagging CPU saturation.

### 8.2. Safe Scale-Down

Before a worker VM is terminated:

1. Stop accepting new jobs.
2. Finish or checkpoint in-flight work.
3. Acknowledge messages only after durable state is persisted.
4. Close connections and flush required logs/metrics.
5. Signal the health controller that the instance is out of service.
6. Only then allow termination.

Without graceful shutdown and idempotency, scale-down can duplicate work or lose progress. Stateful VMs require dedicated handling for leadership, replication, quorum, and data—never apply stateless replacement mechanics blindly.

## 9. Image Updates and Group Rollouts

Releasing a new image does not mean shutting down every old machine simultaneously. Rollouts must account for availability, capacity, data compatibility, and rollback capability.

| Strategy | Approach | Benefits | Trade-offs |
| --- | --- | --- | --- |
| **Rolling replacement** | Replace old instances in batches | Preserves partial capacity | Old and new versions coexist during transition |
| **Canary** | Replace a small percentage first, observe, then expand | Limits initial blast radius | Needs clear metrics and stop criteria |
| **Blue/green** | Provision new group, verify, then shift traffic | Fast traffic-level rollback | Parallel resource cost; requires session/data control |
| **Replace all** | Stop and recreate all instances | Simple where downtime is acceptable | Unsuitable for high-availability workloads |
| **In-place patching** | Update OS on running instances | Sometimes required for stateful/legacy | Introduces drift and harms reproducibility |

~~~mermaid
flowchart TB
    IMG["Approved new image version"] --> CANARY["Create canary group / replace 1 instance"]
    CANARY --> CHECK{"Health, latency, errors, and security pass?"}
    CHECK -- "No" --> STOP["Halt rollout, isolate, and rollback"]
    CHECK -- "Yes" --> BATCH["Rolling replacement in small batches"]
    BATCH --> WATCH["Monitor metrics and error budget"]
    WATCH --> OK{"Continuation criteria met?"}
    OK -- "No" --> STOP
    OK -- "Yes" --> FULL["Complete rollout"]
    FULL --> RETIRE["Deprecate old image"]
~~~

Canary criteria can include boot/readiness success, CPU/RAM/disk/network within bounds, 5xx rates and p95/p99 latency, security agent health, vulnerability scans, business transaction outcomes, and dependency compatibility.

### 9.1. Rolling Back an Image Is Not Always Enough

If a new image ships alongside incompatible database schema or data format changes, reverting the VM to the old image will not restore data compatibility. Use backward-compatible schema changes, tested backups/restores, feature flags, separate app/image/database rollback decisions, and explicit rollout abort criteria.

## 10. Patch Management and Image Lifespan

Standardized images only stay valuable when updated regularly. An unmaintained golden image becomes a **vulnerability distribution channel** because many VMs launch from the same outdated baseline.

- **Immutable replacement:** build a new image, launch new instances, shift traffic, and retire old instances; ideal for stateless workloads.
- **In-place patching:** update packages on existing VMs; sometimes needed for stateful or legacy systems, but drift must be tracked.
- **Hybrid:** images supply the baseline; agents/package managers apply urgent patches or fast-changing artifacts per policy.

A severe zero-day may require temporary mitigations or immediate patching of running instances before the image pipeline can publish a fresh build.

Image lifespan policies must define update cadences, maximum validity windows, deprecation dates, blocks on launching VMs from expired images, time-bound exception workflows with owners, reporting on VMs running stale versions, and retention for rollback/DR. Exact day counts depend on organizational policy and workload risk—there is no single universal number.

## 11. Backups, Snapshots, and Recovery

**Images, snapshots, and backups serve different purposes.**

| Artifact | Primary Purpose | What Not to Assume |
| --- | --- | --- |
| Golden image | Launch VMs with a vetted OS/software baseline | Not a backup of business data |
| Boot disk snapshot | Restore disk state from a point in time | May be application-inconsistent if not quiesced |
| Data volume backup | Protect workload data | Does not replace restore tests or multi-volume consistency |
| Database/log backup | Recover data and point-in-time state | Cannot rely solely on an image containing DB software |
| IaC/config backup | Recreate configuration and infrastructure | Lacks external state unless exported |

For stateless web/worker tiers, recovery typically rebuilds VMs from golden images and IaC, pulling config/secrets at boot; durable data lives in managed databases, object stores, or appropriate services.

For databases or apps storing data on local disks, use native backups, quiesced snapshots, or supported replication; verify transactional consistency, safeguard decryption keys, align with RPO/RTO, and rehearse restores. Never snapshot a running database VM into a golden image and treat it as a valid backup.

## 12. Image Security and Supply Chain

Images are privileged artifacts: code baked inside can inherit the VM's machine identity permissions. Thus, the image build pipeline is part of your software supply chain.

| Risk | Consequence | Control |
| --- | --- | --- |
| Untrusted base image | Malware or tampered packages | Use only approved sources; verify signatures/hashes |
| Compromised build pipeline | Golden image spreads malware fleet-wide | Isolate build runners, least privilege, short-lived secrets, auditing |
| Secrets baked into image | Credentials exposed across many instances | Secret scanning and stripping before publish |
| Outdated images | Fleet runs vulnerable packages | Scheduled scans, expiry/deprecation, patch SLAs |
| Artifact tampered post-publish | VMs boot unverified code | Immutable versions, hashes/signatures, restricted write access |
| Insecure metadata/user-data | Secrets leak into logs or readable endpoints | Never store secrets in public metadata |
| Image captured from production VM | Carries old data, logs, or identities | Build from clean pipelines; scrub and verify |

### 12.1. Provenance and Signing

For critical images, record base image ID/publisher, recipe commit, build tool, package manifest, dependency sources, scan/test results, pipeline identity, approvals, image ID/checksum/signature, and publish destination.

If your platform supports image signing or policies allowing launches only from approved images, combine them with IAM and auditing. **A signature only proves the artifact matches a signing key**, not that its contents are safe; protecting signing keys and build integrity remains essential.

### 12.2. Image Catalog Access Controls

- Only release pipelines may publish to the production catalog.
- Workload groups may only read/pull authorized image versions.
- Share images across accounts/projects strictly via allowlists.
- Prevent regular users from launching VMs from unapproved images.
- Audit copying, sharing, permission edits, deprecations, and deletions.
- Never assume a public image is safe solely because it sits in a provider's catalog.

## 13. Machine Identity and Secrets at VM Creation

A common mistake is creating a golden image from a domain-joined or certificate-enrolled VM and cloning it across the fleet. Cloning existing identities produces duplicate hostnames, certificates, agent IDs, or keys.

Keep these separate:

- **Machine identity:** provisioned uniquely per instance at boot/enrollment via a trusted workflow; never bake a template machine's private key into the image.
- **Service identity:** grants the VM access to DBs, object stores, secret managers, or queues; use managed identities/instance roles where supported.
- **User identity:** operators connect through centralized access management, MFA, and time-bound permissions; never share local admin accounts across the fleet.
- **Secrets:** fetched at runtime using machine/service identity; stored in a secret manager or PKI with rotation, revocation, and auditing.

After cloning from an image, each VM must establish its own hostname, agent registration, and certificate, and report into inventory. Deprovisioning workflows must revoke identities, certificates, and permissions when a VM is terminated.

## 14. Multi-Region Deployment and Disaster Recovery

Golden images standardize VMs across regions, yet images are not automatically portable. Regions may differ in image catalogs/IDs, instance families, CPU architectures, quotas, subnets, security groups/firewalls, routes, DNS, encryption keys, storage, load balancers, and licenses.

A DR plan must specify which images are replicated or rebuilt in the standby region, who approves them, how checksums/provenance are verified, and how region-specific parameters are injected at launch.

| Model | Description | Trade-offs |
| --- | --- | --- |
| **Backup and restore** | Keep images/configs/backups; launch VMs on disaster | Lower cost, potentially longer RTO |
| **Pilot light** | Keep minimal core components running; scale when needed | Faster startup, but dependencies must be tested |
| **Warm standby** | Small VM group running continuously in standby region | Lower RTO, higher ongoing cost |
| **Active-active** | Multiple regions serve traffic concurrently | High complexity in data, routing, deployments, and cost |

Choose based on business RTO/RPO and fault tolerance. If images live only in the primary region and must be copied during a disaster, recovery time must include artifact copy duration, quotas, disk creation, bootstrapping, identity, health checks, and traffic shifting.

## 15. Cost Optimization for VM Groups

Golden images alone do not make VMs cheaper. TCO must include compute by instance size/CPU/GPU/hours, boot and data disks, snapshots and image storage, licenses, NAT/egress/logs/monitoring/backups, buffer capacity, build pipeline runtime, testing, image catalogs, recipe maintenance, and staffing.

- Use autoscaling for variable workloads while holding minimum capacity for availability.
- Scale down dev/test environments off-hours per policy.
- Pick instance families matched to measured CPU, memory, storage, network, and accelerators.
- Avoid keeping oversized instances year-round just for a rare peak.
- Isolate bursty workloads from latency-sensitive ones when needed.
- Track orphan disks, snapshots, obsolete image versions, and ownerless VMs.
- Evaluate commitments/reservations when baseline load is stable and purchasing models fit.

Retaining old images and snapshots indefinitely inflates storage bills, yet deleting everything right after a release breaks rollbacks and DR. Enforce a retention policy: retain approved versions, time-bound forensic artifacts, purge temporary snapshots, and protect recovery-critical builds.

## 16. Fleet Observability and Operations

Across hundreds or thousands of VMs, operations teams must know **what is running, where, from which image, and whether it is compliant**.

### 16.1. Essential Inventory Attributes

| Attribute | Example |
| --- | --- |
| VM ID/hostname | Unique identifier |
| Group/workload role | `prod-web`, `prod-worker` |
| Environment/region/zone | `production`, `region-a`, `zone-b` |
| Image ID/version | Approved image version |
| OS/kernel/package baseline | Actual installed versions |
| Instance type/architecture | General purpose `x86_64` |
| Owner/service | Responsible team |
| Identity/profile | Assigned service identity |
| Patch/compliance state | `compliant`, `pending`, `exception` |
| Created/updated time | Lifecycle history |
| Health/agent status | `ready`, `degraded`, `offline` |

### 16.2. Key Operational Metrics

- **Fleet compliance:** percentage of VMs running approved images, compliant patch levels, and healthy security agents.
- **Image adoption:** time from publishing a new image until production adopts it.
- **Provisioning latency:** time from VM launch request to application readiness.
- **Replacement success:** percentage of successful instance replacements and rollback frequency.
- **Capacity:** CPU, RAM, disk, network, and instance counts per zone.
- **Application SLOs:** latency, error rates, request rates, queue lag, and transaction success.
- **Lifecycle hygiene:** expired images, ownerless VMs, instances in wrong regions, or overly broad permissions.

Tag logs, metrics, and traces with group and image version to correlate regressions with releases. Avoid sending unnecessary sensitive data into observability pipelines; enforce retention and access controls.

## 17. Complete Example: Production Web Group with a Golden Image

Suppose an equipment rental platform runs a Java API across three availability zones. Hypothetical requirements:

| Attribute | Requirement |
| --- | --- |
| Workload | Stateless web/API |
| Availability | At least 3 healthy instances distributed across 3 zones if supported |
| Scale | 3 to 18 instances based on request rate and CPU |
| Runtime | Approved Java LTS |
| Network | Accepts traffic only from the load balancer |
| Data | No session state or durable business data on boot disks |
| Access | Least-privilege service identity; admin access via controlled bastion/broker |
| Image | Supported OS, tested patches and agents, immutable version |

### 17.1. Image Family and Group Template

The golden image family `org-linux-java-web` contains an approved Linux base version, security patches, OS baseline, specific Java runtime, tested logging/monitoring/security agents, trust store, and startup agent. No private keys or environment secrets are included.

The group template references a pinned image version, load-tested machine type, subnets across three zones, service identity `prod-web-runtime`, encrypted boot disk, load balancer health checks, and scaling policies. Names here are illustrative.

### 17.2. Release Workflow

1. Pipeline pulls the approved base image ID and recipe from Git.
2. Builds the image in an isolated account/project with least privilege; destroys the temporary builder afterward.
3. Installs patches, Java runtime, and agents; applies hardening.
4. Runs package/CVE scans, boot tests, smoke tests, and compliance checks.
5. Records provenance; approves and publishes an immutable image ID/version.
6. Launches a small canary in staging, then production.
7. Observes errors, latency, resources, agent health, and business metrics.
8. Rolling-replaces remaining instances in batches while honoring capacity and disruption limits.
9. Reconciles inventory to confirm instances run the new image or have an approved exception.
10. Deprecates the old image per retention policy, keeping rollback artifacts for the required window.

### 17.3. Hypothetical Post-Canary Incident

After replacing one instance, p99 latency spikes sharply. Investigation reveals the new Java runtime altered default connection pool behavior, surging database connections. A sound process halts rollout when metrics cross thresholds, isolates or rolls back the canary, correlates with the image version, tests pool sizing and DB quotas in staging, publishes a fixed image/recipe, and adds the failure case to the test suite.

Golden images reduce drift but **do not guarantee zero application regressions**. Testing must cover OS, runtime, and workload behavior.

## 18. Criteria for Deciding Image Family Count

Do not create a separate image for every team or VM. Too many families inflate build, scanning, patching, approval, and retention overhead.

Consider a separate family only when there are genuine differences in OS/CPU architecture, driver/kernel dependencies, base runtimes/packages, security baselines, patch lifecycles, or boot modes.

If differences are only endpoints, environments, ports, or feature flags, parameterize at the group/boot layer rather than forking the image. This curbs image sprawl and keeps baselines unified.

## 19. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Using a production VM snapshot as a golden image | Leaks live data, logs, secrets, or old identities | Build cleanly from base images; scan and scrub |
| One image for every workload | Mismatched runtimes, drivers, and baselines | Shared base family, role-specific families when justified |
| Using the `latest` tag in production | Same template produces inconsistent VM states | Pin immutable image IDs/versions |
| Installing unpinned packages at boot | Two VMs from the same image diverge | Bake packages into the image or pin and verify |
| Putting secrets in images/user-data | Leaks credentials across fleet and logs | Secret manager, machine identity, secret scanning |
| Creating identity before cloning | Duplicate certificates/agent IDs/hostnames | Enroll uniquely after boot |
| Updating all VMs simultaneously | Bad image takes down the entire fleet | Canary, rolling batches, stop/rollback criteria |
| Patching VMs manually without updating recipes | Drift returns; new VMs stay vulnerable | Route all changes through the pipeline |
| Treating images as database backups | Fails data consistency guarantees | Native backups, restore tests, DR plans |
| Rolling back app while ignoring schema | Old version breaks on incompatible data | Expand–migrate–contract, test rollbacks |
| Scaling solely on CPU | Reacts late or targets the wrong bottleneck | Tie metrics to SLOs and business load |
| Keeping images only in primary region | DR stalls copying artifacts and hits missing deps | Replicate/build in valid DR regions and rehearse |
| Never retiring obsolete images | Teams keep launching vulnerable VMs | Deprecation, launch-blocking policies, retention |

## 20. Handover and Acceptance Process

A VM group and golden image design should deliver:

1. **Workload classification:** group roles, owners, environments, data sensitivity, and criticality.
2. **Group specification:** image versions, machine families, networking, identity, storage, health, autoscaling, and maintenance.
3. **Image build recipe:** base sources, package manifests, hardening, versioning, and build tooling.
4. **Image verification evidence:** scans, boot/smoke tests, compliance checks, approvals, and provenance.
5. **Rollout/rollback plan:** canaries, batches, capacity floors, abort criteria, and recovery steps.
6. **Patch/lifecycle policy:** image lifespan, exceptions, deprecation, retirement, and stale-VM remediation.
7. **Backup/DR plan:** separation of images from data, RTO/RPO, and rehearsal results.
8. **Operations dashboard/runbook:** inventory, drift, health, scaling, alerts, and on-call owners.

### Acceptance Checklist

- [ ] Every VM group has a clear role, owner, and access boundary.
- [ ] Every group references an immutable image version and tested machine type.
- [ ] Images are built from trusted sources with version-controlled recipes and provenance.
- [ ] No secrets, private keys, user data, or cloned machine identities exist in images.
- [ ] Hardening, patches, agents, and package baselines are verified.
- [ ] Images boot cleanly and workload readiness meets production-like criteria.
- [ ] Each VM receives a unique identity and least-privilege permissions.
- [ ] Autoscaling defines metrics, min/max bounds, cooldowns, and graceful shutdown.
- [ ] Rolling/canary deployments specify stop criteria, rollback paths, and sufficient surviving capacity.
- [ ] Environment config is separated from images; drift is detected and remediated.
- [ ] Data backups, image retention, and DR are designed separately with restore tests.
- [ ] Inventory tracks which image, patch level, and policies apply to every VM.

## 21. Well-Architected Evaluation

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Are groups distributed across zones appropriately? Are failed instances replaced safely? Do image rollouts preserve sufficient capacity? Are databases and stateful data backed up and restore-tested? |
| **Security** | Where do base images come from? Are scanning, hardening, and signing/provenance enforced? Are secrets and machine identities provisioned individually? Are launches from expired images blocked? |
| **Performance Efficiency** | Do machine families match measured CPU/RAM/I/O/network? Do startup latency, autoscaling lag, and resource contention meet targets? |
| **Cost Optimization** | Are over-provisioning, idle VMs, redundant snapshots/images, and licensing controlled? Are minimum capacity and retention tuned? |
| **Operational Excellence** | Are inventory, version adoption, drift detection, rollout automation, logs/metrics, and owners in place? |

Standardizing images and VM groups is not merely about saving provisioning time. It establishes a **repeatable control path from software source to running instances**. When you know which group every VM belongs to, which image it booted, what permissions it holds, and which checks it passed, your organization can handle changes and incidents based on evidence.

## 22. Applied Exercise

An enterprise runs an order management application in the cloud, consisting of an API, order-processing workers, and a reporting VM tier. The API must keep at least three instances; workers scale when queue backlogs grow; reporting runs only at night and needs high RAM. Currently, VMs are provisioned manually and several run OS versions past end-of-support.

Design:

1. Required VM groups, including each group's role and owner.
2. Which image families can be shared, which must be split, and why.
3. The pipeline to build, scan, approve, and publish new images.
4. How environment config, secrets, and machine identities are fetched at boot.
5. Autoscaling metrics for the API and workers; how to run reporting without impacting the API or database.
6. A migration plan to replace end-of-support OS machines, including canaries, rollbacks, data checks, and deprecation schedules.
7. Metrics proving the fleet is standardized and free of non-compliant VMs.

A strong solution explains why workloads belong in separate groups, how far images can be shared, and how VM replacement avoids data loss or breaching availability limits.

**Key takeaway:** VM groups define how workloads are organized and managed; golden images define the reproducible baseline for creating instances. They only deliver full value when integrated with IaC, identity, secret management, patching, testing, controlled rollouts, and observability. In Cloud Architecture, the goal is a VM fleet with consistent configuration, least-privilege permissions, safe replaceability, and reliable recovery under controlled cost and operational risk.
