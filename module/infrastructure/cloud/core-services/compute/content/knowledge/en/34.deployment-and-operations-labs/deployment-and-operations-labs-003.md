# Creating a Custom Image and Redeploying Machines from the Image

A custom image is a template prepared from a machine or system disk that can be used to provision new machines with a consistent operating system, runtime, agents, and base software. Instead of configuring each machine manually, operations teams standardize a source machine, create a versioned image, verify the image, and then use it to deploy new machines. This approach shortens compute provisioning time, reduces configuration drift, and establishes a foundation for update or rollback workflows.

An image is only valuable if machines created from it boot properly, receive their own configuration, connect to dependencies, and meet security requirements. If an image contains the source machine's hostname, machine identity, credentials, private keys, or runtime data, newly created machines may share duplicate identities or inadvertently inherit access permissions. Therefore, the image creation process must include preparation, machine state cleanup, capture, verification, test deployment, and lifecycle management.

This lesson belongs to the **Deployment and Operations Labs** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models—from virtual machines and containers to serverless—along with how to choose CPU, memory, networking, and security configurations; deploy applications; scale for load; ensure availability; and optimize operational costs. In compute operations, a custom image is the foundation for creating repeatable virtual machine configurations, deploying in groups, and recovering quickly when an instance needs replacement.

## 1. What Is a Custom Image?

### 1.1. An Image as a Machine Template

A custom image is an artifact describing the contents needed to initialize a new machine. Depending on the platform, an image may include:
- Operating system and boot configuration.
- Partitions or boot disk.
- Kernel, drivers, and system libraries.
- Runtimes such as Java, Python, .NET, or web servers.
- Monitoring, logging, and configuration management agents.
- Base packages and security configurations.
- Certain default configuration files that do not contain secrets.
- Platform-supported metadata or initialization configurations.

When deploying a machine from an image, the platform creates a boot disk or required disks from the image contents, then attaches compute resources and boots the machine according to the requested configuration.

### 1.2. Distinguishing Image, Snapshot, and Backup

| Component | Primary purpose | Typical contents | When to use |
|---|---|---|---|
| Custom image | Create new machines with a standard base configuration | OS, packages, runtime, boot disk, and required metadata | Provisioning new machines, scale-out, replacing machines |
| Disk snapshot | Save the state of a disk at a point in time | Block data of the disk | Restoring a disk or creating a new disk |
| Backup | Protect data and support policy-based recovery | May include multiple disks, databases, files, metadata, and retention | Recovering after accidental deletion, data corruption, or disaster |
| Machine template | Describe machine configuration at deployment | Image reference, machine type, network, identity, disks, and metadata | Consistently creating machines from an image |
| Container image | Package application and dependencies for container runtime | Filesystem/layers and entrypoint | Running containers on VMs or managed container platforms |

A custom image is not inherently a complete backup. An image may exclude detached data disks, managed databases, object storage, secrets, encryption keys, or application state stored in external services. Clearly define the objective: provisioning new machines or protecting data.

### 1.3. Golden Image

A golden image is a standardized image approved by the organization as a deployment baseline. This image typically:
- Uses a supported OS version.
- Has approved patches and base packages installed.
- Is hardened according to a security baseline.
- Includes required logging/monitoring agents and configurations.
- Contains no credentials or machine-specific identity data.
- Is tested and versioned.
- Has an owner, creation date, support expiration, and replacement process.

A golden image can serve as a base for multiple workloads, but you should avoid cramming every application into one monolithic image. Role-specific images such as web, worker, database-client, or gpu-compute help reduce unnecessary packages and limit the attack surface.

## 2. Overall Workflow

The process of creating an image and redeploying machines typically includes these steps:

1. Define the workload, operating system, CPU architecture, and runtime requirements.
2. Create a source machine or temporary build machine from a trusted base image.
3. Install patches, agents, packages, and security configurations.
4. Remove secrets, temporary data, and machine-specific identity.
5. Generalize the machine according to OS/platform requirements.
6. Create the custom image and record metadata/version.
7. Verify image status, disk snapshots, and encryption.
8. Create a new machine from the image with appropriate compute/network/identity configurations.
9. Verify boot, cloud-init, services, logging, and connectivity.
10. Test the application, then shift traffic or workload.
11. Maintain a rollback option and manage the image lifecycle.

~~~mermaid
flowchart TD
    A["Select base image and workload requirements"]
    B["Create source machine"]
    C["Patch, install runtime, agents, and hardening"]
    D["Clean up secrets and machine identity"]
    E["Generalize / prepare for capture"]
    F["Capture custom image and tag version"]
    G["Verify image, disks, and encryption"]
    H["Create new machine from image"]
    I["Boot test and verify configuration"]
    J["Deploy application and run functional checks"]
    K["Cutover or add to pool"]
    L["Monitor, rollback, and manage image"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> K --> L
~~~

Do not skip verification after capture. An image reporting an available or ready state only indicates that the platform finished creating the artifact; it does not prove that machines launched from the image will run the application correctly.

## 3. Planning Before Creating an Image

### 3.1. Defining the Intended Use

First, answer:
- Will the image be used for web VMs, workers, batch, HPC, or administrative hosts?
- Will the machine run a single application or multiple workloads?
- Is local data retention on the boot disk needed?
- Will data disks be created separately from snapshots or backups?
- Does the machine need private network access, internet access, or both?
- Are GPUs, accelerators, or specialized drivers used?
- Does the image need to be used across multiple zones, regions, or accounts/projects?
- Who is permitted to create, share, use, and delete the image?

A single image serving many roles can increase image size, boot time, and unnecessary packages. Keep the base image small, then use cloud-init, startup scripts, configuration management, or deployment pipelines to apply application-specific configurations.

### 3.2. Checking Compatibility

Record the following attributes:
- OS distribution and version.
- CPU architecture: x86_64 or ARM64.
- Boot mode: BIOS/UEFI and Secure Boot requirements if applicable.
- Disk controller and drivers.
- Network drivers.
- GPU/accelerator drivers and runtime.
- Kernel version.
- Filesystem and partition layout.
- Machine management agent and version.
- Supported instance family or machine type constraints.

An x86_64 image cannot run natively on an ARM64 instance. An image with specialized drivers or kernel modules may be incompatible with a different machine family. Check the compatibility matrix of both the platform and the workload.

### 3.3. Choosing a Trusted Image Source

Use a base image that:
- Comes from a verified publisher or repository.
- Has signatures or checksums when provided by the platform.
- Still receives security support.
- Has a clear version and release date.
- Matches the region, architecture, and licensing model.
- Contains no outdated or unnecessary packages.

Do not use an image from an unknown source merely because it already includes the desired runtime. The base image is the root of the software supply chain; any vulnerability or backdoor in it will be replicated to every machine created from it.

### 3.4. Separating Image-Baked Configuration from Deployment-Time Configuration

| Should be packaged in the image | Should be passed at deployment |
|---|---|
| OS and base patches | Hostname or instance name |
| Stable runtimes and packages | Environment and region |
| Agents required on every machine | Environment-specific endpoints |
| Approved public CA bundles | Secrets and credentials |
| Baseline hardening | Workload identity or instance role |
| Generic initialization scripts | Specific user data/cloud-init |
| Application if releasing via image | Per-deployment version/feature flags |

The image should contain relatively stable components. Configurations that vary by environment, identity, and secrets must be provided at runtime via appropriate mechanisms.

## 4. Preparing the Source Machine

### 4.1. Creating a Temporary Build Machine

You can launch a temporary VM from the base image in a dedicated build subnet or project. The source machine should:
- Have access to required package repositories.
- Have controlled network egress.
- Use a dedicated identity with only enough permissions to install packages and download artifacts.
- Have no unnecessary access to production data.
- Have logging enabled to trace changes.
- Be disposable after the image is verified.

Do not use a live production machine serving users as a build machine without proper maintenance procedures and downtime controls.

### 4.2. Updating the Operating System

Perform the following:
- Install approved security updates and bug fixes.
- Remove unused packages.
- Check the kernel and bootloader.
- Configure timezone/locale per workload requirements.
- Verify NTP/time synchronization.
- Check filesystems and disk capacity.
- Reboot if required by patches, then verify the machine operates stably.

Do not rely solely on the package manager reporting success. Verify the running kernel version and required services after rebooting.

### 4.3. Installing Runtimes and Dependencies

Install components required by every machine in this role:
- Exact runtime version.
- System packages and native libraries.
- Monitoring and logging agents.
- Security/endpoint agents per policy.
- Public certificate authority bundles.
- Necessary diagnostic tools without bloat.
- Compatible drivers if the workload requires accelerators.

Record package versions and installation sources. When using external repositories, pin versions or use an internal artifact repository to ensure reproducible builds.

### 4.4. Bake the Application or Only the Platform?

There are two common approaches:

**Image includes the application:** Suitable when deploying an immutable release with strict version control. Each application release produces a new image. Advantages include fast startup and easy rollback by image version. The drawback is that the image must be rebuilt for every release.

**Image includes only OS and runtime:** The application is deployed after boot via a deployment agent or pipeline. This decouples platform lifecycle from application lifecycle, though it makes bootstrapping more complex and can increase provisioning time.

You can combine both: package stable application components into the image while injecting environment configuration and secrets at deployment time.

### 4.5. Hardening the Source Machine

Apply an appropriate baseline:
- Disable unnecessary services and ports.
- Configure the host firewall.
- Restrict SSH/RDP.
- Disable root login or default accounts if required by policy.
- Use a non-privileged user for the application.
- Apply proper file and directory permissions.
- Enable required auditing and logging.
- Configure security updates.
- Keep management and security agents active.
- Do not store private keys or shared credentials.

Hardening must be compatible with how the platform manages machines. For example, disabling a required agent or endpoint can break manageability after new VMs are created.

## 5. Cleaning Up Data and Machine-Specific Identity

### 5.1. Why Generalize?

The source machine may contain unique values:
- Hostname.
- Machine ID.
- SSH host keys.
- Windows SID or domain join information.
- Cloud instance ID and metadata cache.
- DHCP leases and network state.
- Logs, temporary files, and caches.
- Individually issued credentials or tokens.
- Machine-specific certificates.
- Agent registration ID.

If captured as-is, multiple machines created from the same image may share the same identity or send heartbeats with the same machine ID. This causes confusion in monitoring, configuration management, security, and auditing.

### 5.2. Generalizing Does Not Mean Deleting Every Agent

Distinguish between:
- **Machine identity:** Must be regenerated per instance.
- **Agent software:** Typically must be kept so new machines can register with the control plane.
- **Agent registration/token:** May need to be deleted or reset before capture so new machines register independently.
- **Cloud-init or provisioning agent:** Typically must be kept and prepared to run on next boot.

Do not delete binaries for cloud agents, SSM/management agents, or monitoring agents if they are mandatory components. Follow the de-register/reset procedure supported by the provider or agent.

### 5.3. Cleaning Up Linux

Steps commonly considered:
- Clear shell history and temporary files per policy.
- Remove build credentials and tokens.
- Clear unnecessary package caches.
- Reset machine-id following distribution guidelines.
- Remove SSH host keys so the system regenerates them on boot.
- Clean cloud-init state/logs if needed.
- Remove DHCP leases and source-bound network configurations where appropriate.
- Remove agent registration identity if required by the agent.
- Retain cloud-init, cloud agent, and required driver configurations.

On some systemd-based distributions, `/etc/machine-id` may need to be cleared per OS guidance so new machines generate a unique machine ID. Exact steps vary across distributions; do not delete files arbitrarily without verifying the image's boot and systemd behavior.

Cloud-init provides the `cloud-init clean` command to reset state for the next initialization. Depending on the version, options such as cleaning logs or machine-id may differ. Check `cloud-init clean --help` and distribution documentation before running. Do not delete the cloud-init package or datasource config if the platform relies on them to provision hostnames, SSH keys, or user data.

### 5.4. Cleaning Up Windows

For Windows images used to create multiple VMs:
- Install required updates and drivers.
- Verify Windows activation and licensing model.
- Remove user data and build credentials.
- Unjoin from domain or handle per your organization's image process.
- Remove machine-specific certificates/credentials if not shared.
- Prepare agents and drivers for a fresh boot.
- Run Sysprep generalize according to platform and Windows version requirements.

Sysprep is commonly used to generalize Windows prior to capture. Follow the supported procedure strictly; performing certain actions after generalizing can leave the machine in an invalid capture state. Do not reboot the source machine arbitrarily after the shutdown/generalize step.

### 5.5. Secrets and Credentials

Do not leave in the image:
- User or database passwords.
- Cloud access keys.
- API tokens.
- Private SSH keys.
- Private TLS keys.
- Registry credentials.
- Production `.env` files.
- Shared agent registration tokens.
- Service account keys.

If a credential is found to have been packaged into an image or layer, treat that credential as compromised. Revoke/rotate it, audit image and registry history, and build a clean new image. Deleting a file in a new layer does not remove the data from earlier layers.

## 6. Ensuring Consistency During Capture

### 6.1. Boot Disk and Data Disk Images

Determine whether the image will include:
- Boot disk only.
- Boot disk along with supported data disks.
- Linked snapshots of multiple disks.
- A set of disks captured at the same logical point in time.

Do not assume a custom image automatically includes every volume attached to the source machine. Some platforms capture only the boot disk; others support multi-disk capture or allow specifying disk mappings.

Data disks holding databases or user data should have separate backups and appropriate consistency workflows. Machine images do not replace application-consistent backups.

### 6.2. Crash-Consistent vs. Application-Consistent

- **Crash-consistent:** Disk state equivalent to an abrupt power loss. Filesystems or databases may require journal/log recovery at boot.
- **Filesystem-consistent:** Filesystem data has been flushed or frozen using a supported mechanism.
- **Application-consistent:** Applications are coordinated to flush buffers, finish transactions, or pause writes before the snapshot.

If the source machine is running a database or actively processing files, quiesce the application or use native backups. Capturing an image while data is actively changing can produce an inconsistent state.

### 6.3. Stop the Machine or Capture While Running?

Platforms may support capturing while the VM is running, stopped, or after generalization. Exact procedures depend on the provider and disk type.

Principles:
- Read the platform's capture requirements.
- Stop or quiesce stateful applications.
- Flush filesystems if needed.
- Choose reboot/no-reboot mode based on goals and API semantics.
- Record downtime or impact.
- Verify snapshots complete before modifying the source machine.

No-reboot mode can reduce disruption but does not automatically guarantee application consistency. Use it only when allowed by both the workload and the platform.

### 6.4. Post-Capture Verification

Verify:
- The image is in ready/available state.
- All snapshots/disk mappings are complete.
- Architecture and boot mode are correct.
- Encryption and key references are correct.
- The image has the correct owner/project/account.
- Version and source image are recorded.
- The image contains no secrets or temporary data.
- The image can be selected when launching machines in the target region/zone.

## 7. Creating Custom Images on the Cloud

### 7.1. General Workflow

Although API names differ, the workflow usually involves these steps:
1. Select the source VM or disk.
2. Verify permissions to create images and use encryption keys.
3. Generalize or prepare the OS as required.
4. Stop/quiesce the machine if required by the workflow.
5. Invoke the capture/create image operation.
6. Wait for the platform to create the image and associated snapshots.
7. Apply name, version, owner, source, and metadata.
8. Grant image sharing permissions with the right scope.
9. Test creating a VM from the image.

Images are typically immutable or near-immutable resources once created. When packages or patches need updates, create a new version instead of modifying published image contents.

### 7.2. Example with Amazon EC2 AMI

In AWS, an Amazon Machine Image (AMI) serves as the template for launching EC2 instances. An AMI can be created from a prepared instance.

Illustrative command example:

~~~bash
aws ec2 create-image \
  --instance-id i-0123456789abcdef0 \
  --name "compute-api-2026-11-22-v1" \
  --description "Approved compute API image version 1"
~~~

Replace the instance ID and name with values from your actual environment. By default API behavior, EC2 attempts a clean shutdown of the instance before creating the image and then reboots it; evaluate impact and application state before running. The `--no-reboot` parameter can avoid rebooting but increases responsibility for ensuring data consistency.

After creation, inspect the image:

~~~bash
aws ec2 describe-images \
  --owners self \
  --filters "Name=name,Values=compute-api-2026-11-22-v1"
~~~

Do not treat the command returning an image ID as proof that the image is tested. Wait for the image/snapshot status to complete, then launch a test instance.

### 7.3. Example with Azure Compute

In Azure, you can use a managed image or Azure Compute Gallery depending on distribution and versioning goals. General workflow:
- Prepare the source VM.
- Deallocate and generalize if creating a generalized image.
- Capture as a managed image or a Compute Gallery image version.
- Configure replication regions and sharing permissions as needed.
- Create a new VM from the published image/version.

Generalized images and specialized images have different semantics. Generalized images typically require the OS to be generalized; specialized images retain machine state and identity, making them unsuitable for launching fleets of independent machines without handling identity. Choose the image type based on platform documentation and deployment goals.

### 7.4. Example with Google Cloud

In Google Cloud, custom images can be created from a boot disk or supported sources. Typical workflow:
- Prepare the OS and guest environment.
- Stop the instance or disk per capture requirements.
- Create the custom image from the source disk.
- Assign appropriate family/labels/description.
- Create a new instance from the custom image.
- Verify startup scripts, guest agent, and networking.

If creating a Windows image or an image with applications requiring generalization, run the OS-specific preparation before capture. Check image status and bootability on the target machine type/zone.

### 7.5. Differences Across Providers

| Concept | AWS | Azure | Google Cloud |
|---|---|---|---|
| Virtual machine image | AMI | Managed Image / Compute Gallery image version | Custom image |
| Common capture source | EC2 instance and EBS snapshots | Generalized VM or disk depending on image type | Boot disk |
| Distribution | AMI sharing, cross-region/account copy | Gallery replication and sharing | IAM permissions, scoped image availability |
| Launching new machine | EC2 RunInstances | Create VM from image/version | Compute Engine instance from image |
| Key considerations | Reboot behavior, block device mapping, snapshot encryption | Generalized/specialized, Sysprep, gallery version | Guest environment, OS preparation, image family |

Resource names and capture requirements may vary by image type, OS, and platform features. Always verify current cloud documentation before running commands in production.

## 8. Managing Image Versions and Metadata

### 8.1. Naming Conventions

An image name should identify:
- Workload or role.
- OS and major version.
- Architecture.
- Image version.
- Date or release identifier.

Examples:
- compute-api-ubuntu24-x86-v1.4.0
- batch-worker-rocky9-x86-v2026.11
- gpu-training-ubuntu22-arm64-v2.1.0

Do not include secrets, personal data, or sensitive customer names in the image name/description.

### 8.2. Metadata and Tags

Attach metadata:
- owner or owning team.
- workload or role.
- os and os_version.
- architecture.
- image_version.
- source_image.
- build_id or pipeline run.
- created_at.
- security_baseline.
- approval_status.
- support_until or lifecycle date.

Metadata supports auditing, image traceability, identifying versions needing patches, and cleaning up old images. Do not use tags as a substitute for access control; IAM/resource policies must still restrict who can use or delete images.

### 8.3. Immutable Versioning

A published image should be treated as immutable. When making changes:
- Create a new version.
- Record the source image and build inputs.
- Run scans and tests.
- Approve the new version.
- Update deployment templates to the new version.
- Retain the previous version during the rollback window.
- Delete expired versions per policy.

Do not overwrite contents under the same version label if deployments require reproducibility. If a name or alias points to a newer image, explicitly document it as a mutable alias and control changes to it.

### 8.4. Image Families and Channels

Images can be distributed by channel:
- dev: images under experimentation.
- staging: images that passed integration testing.
- stable: images approved for production.
- lts: long-term support images.

Channels help pipelines select appropriate images, but you must keep the ID/version immutable within a single rollout. Do not allow a deployment to pull a moving alias mid-rollout, causing machines in the same group to run different images.

## 9. Protecting Images, Encryption, and Sharing Permissions

### 9.1. Images Can Contain Sensitive Data

Images may accidentally contain:
- Logs with tokens or user data.
- SSH keys or private keys.
- Production configuration files.
- Database dumps.
- Caches containing sensitive data.
- Credentials in shell history.
- Unapproved internal artifacts.

Before publishing, scan the filesystem and check for secrets. Use automated artifact scanning pipelines if available.

### 9.2. Encryption at Rest

Boot snapshots or image backing storage can be encrypted with cloud-managed or customer-managed keys. Check:
- Whether the image and snapshots are encrypted.
- Which account/project owns the key.
- Whether the principal launching VMs has permission to use the key.
- Whether the key is permitted in the target region.
- Whether copying/sharing the image preserves encryption or requires re-encryption.
- Whether the key lifecycle matches image retention.

If the key protecting an image is deleted or disabled, new machines may fail to launch or read disks. Do not delete a key solely because an image is old if that image/backup is still needed for rollback or recovery.

### 9.3. Sharing Images

When sharing images across accounts/projects:
- Share only with necessary principals.
- Prefer private sharing.
- Verify permissions on snapshots backing the image.
- Verify KMS/key permissions.
- Never make an image public without formal approval.
- Revoke sharing permissions once no longer needed.
- Audit launches from the image.

A public image can expose internal software, configurations, or leftover data. The absence of obvious passwords does not mean an image contains no sensitive information.

### 9.4. Supply Chain and Image Provenance

Record:
- Base image and publisher.
- Package manifest or SBOM if supported by the workflow.
- Build pipeline and source revision.
- Vulnerability scan results.
- Release approver.
- Signatures or attestations if available.
- OS/package changes between versions.

When a new vulnerability emerges, provenance metadata helps identify which images and instances are affected.

## 10. Deploying New Machines from a Custom Image

### 10.1. Selecting an Image Version

Before creating a machine:
- Select an approved image ID/version.
- Verify OS, architecture, and boot mode.
- Verify region and zone availability.
- Verify encryption key access.
- Verify compatibility with the planned machine type.
- Verify the image is within its support window.

Do not use generic aliases if they prevent identifying the exact image ID used in a deployment.

### 10.2. Selecting Compute Configuration

The new machine needs configuration for:
- Machine type or instance family.
- vCPU and memory.
- GPU/accelerator if needed.
- Boot disk type and size.
- Data disk mapping.
- Network interface.
- Placement/availability zone.
- Quotas and reservations if needed.

The image does not determine all compute capabilities. The same image can run on different machine types, provided the application is compatible and properly sized.

### 10.3. Networking and Security

Configure:
- VPC/VNet and subnet.
- Security groups or firewall rules.
- Routes and NAT.
- Private endpoints/DNS.
- Load balancer targets.
- Public IP only if truly needed.
- Egress policy and network segmentation.

Do not copy the source machine's exact network identity. New machines need their own NICs, IPs, and hostnames. Do not expose SSH/RDP or application ports to the internet unnecessarily.

### 10.4. Identity and Permissions

Attach identity per workload:
- Instance profile/role.
- Managed identity.
- Service account.
- Platform-provisioned machine identity.
- Permissions to read required secret managers and registries.

Do not place static access keys in user data or images. Grant least-privilege permissions and separate identities across build machines, deployment pipelines, and runtime machines.

### 10.5. User Data and cloud-init

Use user data or cloud-init for values that vary per launch:
- Hostname.
- Environment.
- Endpoints.
- Secret references.
- Agent registration.
- Startup commands.
- Application version or configuration version.

User data may be stored in metadata or visible to principals with appropriate permissions. Never put plaintext passwords, tokens, or private keys in user data. Fetch secrets from a secret manager using workload identity after the machine boots.

### 10.6. Example Launching EC2 from an AMI

Example command:

~~~bash
aws ec2 run-instances \
  --image-id ami-0123456789abcdef0 \
  --instance-type t3.large \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-ids sg-0123456789abcdef0 \
  --iam-instance-profile Name=compute-api-role \
  --min-count 1 \
  --max-count 1
~~~

The IDs above are illustrative placeholders. Before running, select the actual image ID, instance type, subnet, security group, and instance profile for the target account/region. Add tags to instances and volumes to track image version, owner, and environment.

Once the command returns an instance ID, wait for instance state and system checks to pass. Then verify SSH/SSM access, cloud-init, agents, and application health.

## 11. Post-Boot Verification

### 11.1. Infrastructure Layer Checks

- Instance is in running state.
- System/instance status checks pass.
- Boot disk and data disks are attached.
- Filesystems are mounted properly.
- NIC received an IP address.
- Routes, DNS, and security policies are correct.
- Time synchronization is working.
- Encryption and metadata match expectations.

### 11.2. OS and Machine Identity Checks

Verify:
- New hostname, not colliding with the source machine.
- New machine ID.
- New SSH host keys if required by the process.
- Correct Windows identity/SID and domain join.
- Agent registered as a new instance.
- Cloud-init/provisioning reports no errors.
- No leftover credentials or logs from the source machine.
- Timezone, locale, and kernel are correct.

If two machines report the same machine ID or agent ID, halt the rollout and fix generalization before launching more instances.

### 11.3. Service and Dependency Checks

- Application service auto-starts.
- Expected ports are listening.
- Health endpoint returns expected results.
- Database connection succeeds.
- Queue/object storage/API connections work.
- Secrets are retrieved using the proper identity.
- Monitoring and logging emit data.
- Backup agent or policy is applied.
- No unnecessary services are open.

### 11.4. Performance and Repeatability Checks

Create at least one test machine from the image, then:
- Compare boot times.
- Compare packages and versions.
- Inspect runtime configuration.
- Run smoke tests and representative workloads.
- Launch a second machine to verify distinct identities.
- Verify both machines share the same baseline while having distinct hostnames, IPs, and machine identities.

A good image must produce machines with equivalent baselines but distinct instance identities and configurations.

## 12. Replacing Running Machines with New Machines from an Image

### 12.1. In-Place Reinstallation Is Not Always Necessary

With immutable infrastructure, when the OS or base packages need changes, build a new image and deploy new machines. After verification, shift workloads to the new machines and decommission the old ones per procedure.

This approach helps:
- Reproduce machine state reliably.
- Roll back easily to the previous image.
- Reduce drift caused by long-term manual edits.
- Use the same image for scale-out.

### 12.2. Rolling Replacement

Replace machines incrementally:
1. Launch a new machine from the new image.
2. Run health checks and smoke tests.
3. Add the machine to the load balancer or pool.
4. Wait for the machine to become healthy and serve load.
5. Drain an old machine.
6. Confirm active sessions/jobs have finished or been handed off.
7. Terminate the old machine per policy.
8. Repeat until the entire pool runs the new image.

Rolling replacement reduces downtime but requires sufficient capacity while two generations of machines coexist.

### 12.3. Blue-Green Deployment

Create a new group of machines (green) alongside the serving group (blue):
- Deploy the new image to green.
- Test independently.
- Shift traffic partially or completely.
- Monitor errors and latency.
- Keep blue during the rollback window.
- Remove blue after the observation period ends and approval is granted.

Blue-green requires budgeting for running two groups of machines and handling data/state during traffic cutover.

### 12.4. Stateful Workloads

For databases or applications retaining local data, you cannot simply launch a new machine and switch traffic. You must:
- Back up/replicate data.
- Sync final changes.
- Quiesce or transfer write authority.
- Attach/restore data volumes properly.
- Verify consistency.
- Switch leader/endpoint.
- Have a failback plan.

The image contains the OS and application; persistent data must be managed separately.

## 13. Rolling Back When a New Image Fails

### 13.1. Rolling Back by Image Version

If a new image fails:
- Stop launching additional machines from the faulty version.
- Keep deployment templates pointing to the known-good version.
- Launch new machines from the previous image or restore the blue group.
- Shift traffic according to plan.
- Retain logs and the faulty image for investigation if policy permits.
- Revoke the image if there is a severe security issue.

Rollback does not automatically revert database schema changes or data created by a newer application version. Separate compatibility and migration strategies are required.

### 13.2. Rollback Criteria

Thresholds can be set for:
- Boot failures or failed instance checks.
- Application health check failures.
- Elevated error rates.
- p95/p99 latency exceeding SLOs.
- Agent registration failures.
- Database/API connection failures.
- Failed security scans or policy checks.
- Discrepancies in business outcomes.

Criteria must be defined before the rollout to avoid emotional decision-making during an incident.

### 13.3. How Long to Retain Old Images?

Old image retention depends on:
- Post-release observation window.
- Speed of defect detection.
- Required RTO.
- Reproducibility of the image.
- Snapshot/storage costs.
- Audit and retention regulations.

Do not delete an old image immediately after rollout if it still serves as the rollback path or is needed for investigation.

## 14. Lifecycle Management and Image Updates

### 14.1. Patch Cadence

Establish a schedule to:
- Track OS and package updates.
- Assess CVE impact.
- Build a new image from the baseline.
- Scan the image.
- Test boot and workloads.
- Approve.
- Roll out in batches.
- Track instances still running older versions.
- Retire end-of-support images.

Do not let an image live indefinitely merely because it still launches VMs. It may contain unsupported kernels or packages.

### 14.2. Image Drift

Drift occurs when machines launched from the same image diverge over time due to manual modifications.

To reduce drift:
- Use configuration management or IaC.
- Restrict manual changes in production.
- Record packages/versions after provisioning.
- Build new images for platform-level changes.
- Use configuration versions to keep environments synchronized.
- Periodically replace machines or reconcile toward the desired state.

### 14.3. Image Deprecation and Retirement

Before deleting an image:
- Locate instances/templates referencing the image.
- Check autoscaling groups, scale sets, or instance templates.
- Check backup/recovery runbooks.
- Check other accounts/projects using the image.
- Update references to the new version.
- Confirm no dependencies remain.
- Archive required metadata and audit records.
- Delete the image and snapshots per policy.

Deleting an image may not terminate instances already launched from it, but it can prevent launching new machines or rolling back to that version. Verify exact provider semantics.

## 15. Automating the Image Pipeline

### 15.1. Reference Pipeline

A pipeline can include:
1. Select an approved base image.
2. Create a build instance or build environment.
3. Install patches and packages.
4. Configure runtimes and agents.
5. Harden and generalize.
6. Capture the image.
7. Scan for vulnerabilities and secrets.
8. Launch a test instance.
9. Run smoke/integration tests.
10. Apply approval and publish the image version.
11. Update templates or deployment pipelines.
12. Monitor running machines and retire old versions.

### 15.2. Infrastructure as Code

IaC can define:
- Image resources or image pipelines.
- VM build instances.
- Disks and encryption.
- Network and security policies.
- IAM/roles.
- Instance templates/launch templates.
- Autoscaling groups or scale sets.
- Tags and metadata.
- Test environments.

Do not hardcode credentials in IaC. Use secret references and workload identities for pipelines.

### 15.3. Release Controls

An image should only be marked approved when:
- Built from a trusted source.
- Patches and package versions are recorded.
- Scans show no findings exceeding policy thresholds.
- No secrets are detected.
- Boot test succeeds.
- Agents and monitoring operate properly.
- Workload smoke tests pass.
- Owner and approvals are clear.
- A rollback version is available.

### 15.4. Canary Images

Before replacing the entire fleet:
- Launch one or a few machines from the new image.
- Place them into a canary group.
- Route a small portion of traffic or workload.
- Monitor metrics and logs.
- Expand rollout if healthy.
- Roll back if thresholds are breached.

Canary testing catches driver, kernel, boot, dependency, or performance issues that build-only tests miss.

## 16. Optimizing Cost and Deployment Time

### 16.1. Benefits

Custom images can reduce:
- Time spent installing OS and packages on every new machine boot.
- Manual configuration effort.
- Variance between machines.
- Time to replace failed machines.
- Scale-out latency for workloads requiring many base dependencies.

### 16.2. Costs to Account For

- Image storage capacity and backing snapshots.
- Cross-region replication.
- Storage retention across multiple versions.
- Build instance and pipeline runtime.
- Scanning and testing.
- Data transfer.
- Cost of keeping older images for rollback.
- OS/software licensing.
- Operational and maintenance effort.

### 16.3. Reducing Image Size

- Install only necessary packages.
- Clean package caches and temporary files.
- Do not store datasets or runtime logs.
- Use minimal supported base images.
- Separate images by role.
- Move large datasets to separate object/block storage.
- Omit development tools from production images unless required.

Smaller images reduce copy/boot times and storage costs, but mandatory agents or security libraries must never be stripped out.

## 17. Common Troubleshooting

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| Image does not appear when creating VM | Image not ready, wrong region, or missing permissions | Check state, owner, sharing, and region |
| New VM fails to boot | Incompatible boot mode, architecture, drivers, or disk mapping | Check console logs, boot mode, kernel, and machine family |
| New machines share hostname/machine ID | Not generalized or cloud-init state not reset | Check OS identity and sysprep/cloud-init workflow |
| Agent reports the same ID across multiple VMs | Agent registration state was cloned | Reset/de-register per agent docs and build a new image |
| Cannot read encrypted boot disk | Missing KMS/key permissions or key unavailable | Check key policy, region, and principal |
| Cloud-init re-runs incorrectly | Incompatible datasource/state or cloud-init package | Check cloud-init logs and image preparation |
| VM boots but app fails to start | Missing secrets, endpoints, or runtime config | Check identity, secret references, user data, and service logs |
| VM cannot reach private endpoints | Misconfigured subnet, routes, DNS, or firewall | Check network config of the new instance |
| New image runs slowly | Different runtime/packages/drivers or machine type | Compare benchmarks and package manifests |
| Cannot roll back | Old image deleted or key disabled | Check retention and image dependencies |
| New machine missing data disk | Image excludes disk or mapping not declared | Restore/attach data disk per separate plan |
| Multiple VMs share credentials | Secret was baked into image | Revoke credentials, clean up, and publish a new image |

During investigation, preserve image ID, instance ID, build ID, cloud-init logs, and snapshot status for traceability. Never output secrets or sensitive user data into public logs.

## 18. Practical Checklist

### Preparing the Source Machine

- [ ] Define workload, OS, architecture, and target machine family.
- [ ] Select a base image with clear provenance and support.
- [ ] Install required patches, runtimes, agents, and dependencies.
- [ ] Apply hardening and verify services.
- [ ] Store no credentials or unnecessary production data.
- [ ] Determine which disks belong in the image and which are backed up separately.

### Generalize and Capture

- [ ] Clean up hostname, machine ID, and unique identities.
- [ ] Reset agent registration per guidelines.
- [ ] Prepare cloud-init or Sysprep for the OS.
- [ ] Quiesce applications and ensure consistency.
- [ ] Choose capture mode matching downtime and data constraints.
- [ ] Wait for image and snapshots to complete.
- [ ] Verify encryption, owner, region, and architecture.
- [ ] Attach version, tags, source, and build metadata.

### Deploying New Machines

- [ ] Select a specific image ID/version.
- [ ] Choose appropriate machine type, disks, and placement.
- [ ] Configure subnet, routes, firewall, and DNS.
- [ ] Attach workload identity with least privilege.
- [ ] Provide secrets via secret manager or secure mechanism.
- [ ] Pass user data without plaintext credentials.
- [ ] Verify boot, machine identity, agents, and cloud-init.
- [ ] Run smoke tests and workload tests.
- [ ] Launch a second machine to verify non-duplicate identities.

### Rollout and Lifecycle

- [ ] Have a canary, rolling, or blue-green plan.
- [ ] Define rollback criteria beforehand.
- [ ] Retain the previous image version for the required duration.
- [ ] Track instances still using older images.
- [ ] Maintain a schedule for patching, scanning, and releasing new images.
- [ ] Delete images only when no dependencies remain.
- [ ] Store runbooks and metadata for reproducibility.

## 19. Key Takeaways

- A custom image is a template for launching new machines with consistent OS, packages, and runtimes.
- Images differ from snapshots, backups, machine templates, and container images.
- Prepare the source machine, patch, harden, and verify compatibility before capture.
- Generalizing ensures each new machine gets its own hostname, machine ID, and agent identity.
- Do not delete necessary agents; only reset registration state per guidelines.
- Runtime secrets and credentials must be supplied at deployment time, never baked into the image.
- Capture must account for filesystem, database, and multi-disk consistency.
- Image versions should be immutable, with metadata, owner, and provenance.
- When launching a new VM, configure compute, disks, networking, identity, and user data separately.
- Successful boot is not enough; verify apps, dependencies, monitoring, and security.
- Use rolling or blue-green strategies for controlled machine replacement with rollback retained.
- Images require patching, scanning, testing, retention, and retirement across their lifecycle.

## Glossary

| Term | Meaning |
|---|---|
| Custom image | An organization-created image used as a template to deploy new machines. |
| Golden image | A standardized image approved for configuration and security baselines. |
| Base image | The foundational image used to start the build process. |
| Machine image | An artifact describing the OS and disks needed to initialize a virtual machine. |
| Snapshot | A point-in-time capture of a disk or volume state. |
| Backup | A data copy retained under policy for recovery purposes. |
| Generalize | Cleaning or resetting machine-specific info so an image can spawn multiple independent machines. |
| Sysprep | A Windows tool that prepares the OS for image deployment, including generalizing per supported workflows. |
| cloud-init | A tool that initializes Linux machines using platform metadata and user data. |
| Machine ID | The unique system identifier of a machine. |
| User data | Data or scripts passed to a machine at initialization time. |
| Instance profile/role | Identity and permissions attached to a compute instance. |
| Boot disk | The disk containing the OS and data required to boot a machine. |
| Data disk | A disk holding application or persistent data separate from the boot disk. |
| Application-consistent | A capture state coordinated with applications to guarantee valid data. |
| Crash-consistent | A disk state equivalent to an abrupt machine shutdown. |
| Image version | A specific release version of a custom image. |
| Image provenance | Information on image origin, build process, and verification. |
| SBOM | Software Bill of Materials, an inventory of software components inside an artifact. |
| Immutable infrastructure | Operational model replacing machines with versioned artifacts rather than persistent in-place edits. |
| Rolling replacement | Incrementally replacing machines while the system continues serving traffic. |
| Blue-green deployment | Maintaining two environment groups for traffic switching and rollback. |
| Canary deployment | Trial deployment to a small portion of workload before expanding. |
| Image drift | Divergence between actual running machines and the desired baseline image/configuration. |
| Image retirement | The process of deprecating and deleting end-of-life images. |