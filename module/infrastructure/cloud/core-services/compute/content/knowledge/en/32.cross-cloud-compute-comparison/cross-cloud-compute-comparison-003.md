# Comparing Images, Metadata, Workload Identity, and Startup Scripts

## 1. Why Compare These Four Components?

When deploying a VM on the cloud, the image determines the operating system and base software; metadata provides information about the instance and runtime environment; workload identity defines which resources the machine is allowed to access; and the startup script automates initialization steps after boot. Together, these four components turn a newly provisioned VM into an operational workload.

Cloud providers offer similar concepts, yet image formats, metadata APIs, credential-issuing mechanisms, and startup script lifecycles differ. An image that works on one platform is not guaranteed to boot as-is on another. A script fetching instance details from one cloud's metadata endpoint may fail on another cloud. Nor can a role or service account be copied directly across accounts or providers.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, comparing these elements helps you select and deploy compute across multiple clouds while understanding differences in CPU, memory, networking, security, and operations. The goal is to design workloads that are portable when needed while still leveraging each platform's native mechanisms properly.

After this lesson, learners will be able to:

- Distinguish between machine images, boot disk images, snapshots, and image galleries.
- Compare image concepts across AWS, Microsoft Azure, and Google Cloud.
- Identify differences that affect portability, such as firmware, drivers, architecture, disk mapping, and licensing.
- Distinguish instance metadata from user data and startup scripts.
- Compare metadata services and how to protect metadata access on each cloud.
- Map instance roles, managed identities, service accounts, and workload identity federation.
- Design startup automation that is idempotent, logged, and free of embedded secrets.
- Establish a workflow for packaging, importing, testing, and migrating images across clouds.

## 2. The Big Picture

### 2.1. Role of Each Component

| Component | Question to Answer | Example Information/Configuration |
|---|---|---|
| Image | What OS and base software does the machine boot from? | OS, packages, agents, bootloader, drivers, filesystem |
| Metadata | Where is the machine running and what attributes does it have? | Instance ID, zone, region, network interfaces, user data |
| Workload identity | What is the machine or application permitted to do? | Role, managed identity, service account, token |
| Startup script | What must run when the machine starts? | Install agents, fetch config, mount volumes, start services |

The image is the starting foundation; metadata describes the runtime context; identity grants permissions; startup automation wires the components into a boot sequence. If a design depends heavily on one provider, an equivalent configuration layer is needed when switching clouds.

### 2.2. Distinguishing Images, Snapshots, and Machine Configuration

- **Image:** a template used to create a boot disk or VM; may contain the OS and pre-installed software.
- **Disk snapshot:** a point-in-time capture of a volume; typically used for backup or creating new disks.
- **Machine image:** may include multiple disks and part of the machine configuration depending on the provider.
- **Instance template/launch template:** describes how to create a VM, such as machine type, image reference, network, metadata, and identity; does not necessarily contain disk data.
- **Infrastructure as Code:** describes the resources to create and their relationships; does not replace images or data backups.

Do not treat these concepts as interchangeable. During migration, identify exactly which artifact holds the OS, data disks, NICs, security policies, identity, and initialization configuration.

### 2.3. Control Plane vs. Guest Operating System

The cloud control plane creates the VM and attaches disks, NICs, security policies, and identity. The guest operating system boots, detects devices, reads metadata, and executes startup automation. A VM can be created successfully in the control plane yet fail to become healthy because the image is incompatible, the cloud agent fails, the script errors out, or the identity cannot obtain a token.

Troubleshooting requires checking both sides: cloud resource status and logs inside the guest OS.

## 3. Comparing Machine Images Across Clouds

### 3.1. AWS: AMIs and EBS Snapshots

An Amazon Machine Image (AMI) is a template used to launch EC2 instances. An AMI references a block device mapping configuration and snapshots for EBS-backed volumes; it can specify the boot volume and additional volumes depending on how it was built. Details such as instance store, architecture, virtualization mode, boot mode, and sharing permissions affect which instance types can be launched.

When operating AMIs, manage:

- Region and architecture of the AMI.
- Root device type and block device mapping.
- Snapshot encryption and KMS key policies.
- Boot mode, kernel/drivers, and instance family requirements.
- Image ownership, sharing permissions, and lifecycle.
- Versioning, tagging, and base image update workflows.

An AMI is an EC2-specific artifact. You cannot take an AMI ID and pass it directly as an image reference on Azure or Google Cloud. To migrate, export/import the disk in a supported format and workflow, then create a native image on the target platform.

### 3.2. Azure: Managed Images and Azure Compute Gallery

Azure supports managed images and Azure Compute Gallery to manage, version, and distribute images. Galleries suit standardizing images across multiple VMs, subscriptions, or regions according to configured sharing permissions.

When working with Azure images, check:

- OS type, OS state, and generation (Gen1/Gen2) compatible with the VM.
- Hyper-V generation, boot mode, and Secure Boot/Trusted Launch support if used.
- How OS disks and data disks are defined in the image version.
- Regional replication, target regions, and quotas.
- Disk encryption, disk encryption sets, and access permissions.
- Publisher/offer/SKU if using Marketplace images.
- Required agents and extensions inside the guest OS.

Azure Compute Gallery distributes image versions, but it does not automatically migrate managed identities, NICs, subnets, NSGs, role assignments, or full VM configurations to another cloud.

### 3.3. Google Cloud: Custom Images and Machine Images

Google Compute Engine provides custom images to create boot disks and machine images to store machine state along with configuration and disks within service-supported scope. Instance templates describe the configuration used to create an instance or instance group.

When working with Google Cloud images, check:

- Source disk and boot disk image.
- Guest OS support, architecture, and boot mode.
- Which configurations/disks a machine image includes and its restore limits.
- Image family, image project, and usage permissions.
- Encryption keys, Cloud KMS, and service agent permissions.
- Guest environment/agent, startup scripts, and metadata.
- Region/zone, machine type, and network interface compatibility.

Custom images and machine images serve different purposes. When migrating to another cloud, recreate networks, service accounts, firewall rules, and related resources rather than assuming a machine image carries the entire environment.

### 3.4. Concept Comparison Table

| Capability | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| VM boot image | EC2 AMI | Managed Image / Compute Gallery image version | Compute Engine custom image |
| Disk capture | EBS snapshot | Managed disk snapshot | Persistent Disk snapshot |
| Broader machine/config capture | AMI with block device mapping; separate backup mechanisms | Image/backup solution per scope | Machine image |
| Image distribution | AMI sharing, cross-region/account copy | Azure Compute Gallery replication/sharing | Image project, image family, and IAM permissions |
| Multi-VM creation config | Launch Template / Auto Scaling | VM Scale Set model | Instance Template / Managed Instance Group |
| In-guest initialization | User data, cloud-init, EC2Launch | Custom Data, cloud-init, VM extensions | Metadata startup scripts, guest environment |
| VM identity | EC2 instance profile / IAM role | System-assigned or user-assigned managed identity | Attached service account |

This table maps equivalent concepts at an architectural level; it does not imply identical formats or features. Service names and limits vary by VM type, region, and version.

### 3.5. Intermediate Image Formats

When moving images across hypervisors or clouds, you may encounter formats such as RAW, VHD/VHDX, VMDK, QCOW2, or OVA. Each platform supports only a specific set of formats, variants, and import conditions.

Before converting, determine:

- Whether the image is a single disk, multiple disks, or an appliance package.
- Virtual size vs. actual size.
- Fixed-size vs. dynamic disk.
- Partition table (MBR/GPT), filesystem, and bootloader.
- BIOS vs. UEFI, Secure Boot, and firmware requirements.
- Storage/network drivers and guest tools.
- Sparse allocation, alignment, and checksums.

Format conversion alone does not resolve differences in drivers, boot firmware, licensing, or cloud agents. After importing, test-boot on a target VM and verify devices, networking, storage, and identity.

## 4. Factors Affecting Image Portability

### 4.1. CPU Architecture

An `x86_64` image cannot run natively on an `Arm64` VM by default, and vice versa. Applications with native binaries, kernel modules, or architecture-dependent packages are especially sensitive to this difference.

When switching clouds:

- Check the architecture of both the image and the target machine type.
- Verify that package repositories provide builds for that architecture.
- Rebuild native binaries if needed.
- Check instruction sets, SIMD, and dependent libraries.
- Re-benchmark, as identical vCPU counts do not guarantee equivalent performance.

### 4.2. Boot Mode and Firmware

VMs may use BIOS/Legacy or UEFI. An image built for one boot mode may fail to boot on an instance that only supports the other. Azure Gen1/Gen2, EC2 boot modes, and Compute Engine firmware settings must be mapped to the specific machine type.

Check partition tables, EFI System Partition, bootloader, Secure Boot, and drivers before importing. Do not arbitrarily change firmware mode on production images, as it can render the OS unbootable.

### 4.3. Storage Drivers and Device Mapping

Block device names and drivers vary across platforms. Applications should not assume volumes always appear at the exact same `/dev/...` path. Use UUIDs, filesystem labels, or verified metadata-based mounts.

On Windows, verify storage drivers, boot-critical drivers, drive letters, volume GUIDs, and domain policies. On Linux, check initramfs, udev, `/etc/fstab`, and appropriate NVMe/SCSI drivers.

### 4.4. Network Drivers and Interface Naming

Virtual NICs can use different drivers and models. Interface names may change; static network configs bound to an old MAC address can leave the machine without an IP after migration.

Prefer DHCP or network configuration managed by cloud-init/NetworkManager/systemd-networkd per platform. After booting, verify routes, DNS, MTU, security policies, and throughput.

### 4.5. Cloud Agents and Guest Tools

Each provider has its own agent or guest environment to support metadata, shutdown, disks, networking, telemetry, or extensions. An image might contain the source cloud's agent while lacking the target cloud's agent.

Before migrating:

- Identify mandatory and optional agents.
- Install the target platform's guest agent according to official documentation.
- Avoid having two agents manage the same configuration and conflict.
- Verify service startup, logs, and required permissions.
- Remove the old agent only after confirming no dependencies remain.

### 4.6. Licensing and Activation

Some images carry licenses tied to the instance, host, subscription, or Marketplace. Copying a disk does not mean the license transfers validly. Windows activation, commercial software licenses, and subscription repositories may require re-registration.

Check licensing terms and each provider's bring-your-own-license (BYOL) mechanisms before migration. Do not bake license keys or activation secrets into shared images.

### 4.7. Encryption and Key Management

Snapshots or images may be encrypted with keys from the source provider. The target cloud usually has its own KMS and policies. Determine whether encrypted data can be exported, re-encrypted, and granted permissions for the target service identity.

Do not assume raw key material can be moved across clouds unchanged. Usually you must decrypt via an authorized workflow at the source and re-encrypt with a target key, or use a key-import mechanism supported by both platforms and approved by your organization.

## 5. Metadata Service: VM Runtime Information

### 5.1. Metadata vs. User Data

The metadata service provides information about the instance, project/account, zone, network, identity, or platform-published configuration. User data/custom data is data passed by the operator at VM creation time, typically for initialization configuration.

Startup scripts may read either metadata or user data, but the two sources differ. Metadata usually describes the cloud environment; user data usually contains parameters or scripts supplied by the VM creator.

Never store passwords, private keys, or long-lived credentials in user data. Metadata can be read by processes inside the VM depending on configuration and access permissions; treat it as unsuitable for storing secrets.

### 5.2. AWS EC2 Instance Metadata Service

EC2 Instance Metadata Service (IMDS) serves metadata via the link-local address `169.254.169.254`. IMDSv2 uses session tokens: the client sends a PUT request to obtain a token, then passes that token in a header when querying metadata. You can require IMDSv2 and restrict the hop limit to reduce exposure to unwanted workloads.

Example querying instance ID using IMDSv2:

```bash
TOKEN=$(curl -sS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -sS \
  -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  "http://169.254.169.254/latest/meta-data/instance-id"
```

This is a Linux shell example. In applications, use the SDK/provider library where appropriate, handle errors, and never log tokens. IMDSv2 mitigates certain SSRF vectors, but it does not replace application and network protections.

### 5.3. Azure Instance Metadata Service

Azure Instance Metadata Service (IMDS) provides VM information via the link-local endpoint `169.254.169.254`. Requests require the `Metadata: true` header; the API requires specifying an `api-version`. The endpoint is also used to retrieve managed identity tokens for the requested resource/audience.

Example reading instance information:

```bash
curl -H "Metadata: true" \
  "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
```

Verify the API version in the example against current documentation and the features used. Do not omit the required header. When requesting a managed identity token, scope the resource/audience strictly to the target service and never log access tokens.

### 5.4. Google Compute Engine Metadata Server

Google Compute Engine provides a metadata server, typically accessed via the hostname `metadata.google.internal` or the link-local metadata address. Requests require the `Metadata-Flavor: Google` header.

Example reading instance ID:

```bash
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/id"
```

The metadata server can also issue access tokens for the service account attached to the VM. Applications must use the proper scope/audience for the target auth mechanism and API, and avoid caching tokens longer than necessary.

### 5.5. Metadata Comparison Table

| Aspect | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Metadata endpoint | `169.254.169.254` | `169.254.169.254` | `metadata.google.internal` / link-local endpoint |
| Primary header/requirement | IMDSv2 token header when IMDSv2 is required | `Metadata: true` | `Metadata-Flavor: Google` |
| Instance information | Instance ID, type, AZ, network, and other metadata | VM ID, location, size, NIC, and other metadata | Instance ID, zone, machine type, network, and other metadata |
| User-supplied data | EC2 user data | Custom data | Instance/project metadata startup scripts or custom metadata |
| Workload credentials | Temporary credentials from instance profile role | Token from managed identity | Token from attached service account |
| Protection notes | Prefer IMDSv2, limit hop count, and control SSRF | Require header, restrict access, and protect against SSRF | Require flavor header, control SSRF, and scope service account/IAM |

These endpoints and APIs are platform-specific interfaces. Do not write a single shared script by hardcoding one metadata URL.

### 5.6. Protecting Metadata Against SSRF

Server-Side Request Forgery (SSRF) can trick an application into sending requests to the metadata endpoint. If metadata exposes credentials, an attacker could attempt to steal the VM's token.

Mitigations:

- Enforce provider-recommended secure metadata mechanisms such as IMDSv2 and mandatory headers.
- Validate and restrict which URLs server-side applications are allowed to fetch.
- Never allow user input to control internal request destination URLs without validation.
- Use appropriate network policies/host firewalls to restrict metadata access from unnecessary workloads.
- Scope roles/managed identities/service accounts to least privilege.
- Never return metadata contents or tokens in error messages.
- Keep frameworks and libraries updated with SSRF protections.

The metadata service must not be treated as a secret store. Credentials obtained from metadata are typically short-lived, yet if leaked they can still be abused while valid.

## 6. Comparing Workload Identities

### 6.1. Why Do VMs Need Workload Identity?

VMs often need to read secrets, write logs, download objects, decrypt volumes, or call cloud APIs. The legacy approach is placing long-lived access keys or passwords in config files. That makes rotation hard and increases exposure via images, backups, logs, or process listings.

Workload identity lets machines or applications obtain short-lived credentials based on an identity attached to the resource. The application requests a token/credential on demand, and the provider evaluates permissions via IAM policies.

### 6.2. AWS: IAM Roles and Instance Profiles

With EC2, an IAM role is attached to an instance via an instance profile. Instance metadata provides temporary security credentials for the role; SDKs automatically fetch and refresh them.

Design practices:

- Create dedicated roles per workload or service class.
- Attach the role via an instance profile.
- Grant only required actions and resources.
- Use conditions and resource policies where appropriate.
- Monitor CloudTrail and credential usage.
- Avoid placing long-lived access keys in AMIs or user data.

If one instance must host multiple distinct application identities, consider a credential broker mechanism or separating workloads onto distinct resources rather than granting one broad role to every process.

### 6.3. Azure: Managed Identity

Azure Managed Identity comes in two common forms:

- **System-assigned:** lifecycle is tied to the resource; when the resource is deleted, the corresponding identity is managed along with that lifecycle.
- **User-assigned:** the identity is a standalone resource that can be attached to multiple permitted resources with an independent lifecycle.

Applications can use the Azure Identity SDK or the appropriate endpoint to obtain tokens. Assign roles at the exact resource scope needed rather than granting broad subscription-level access when only one storage account or secret vault is needed.

During migration, an Azure managed identity ID/principal cannot be carried directly into AWS or Google Cloud. Create a corresponding identity in the target cloud and map permissions by function.

### 6.4. Google Cloud: Attached Service Accounts

Compute Engine VMs can have a service account attached. The metadata server issues access tokens for that service account; IAM policies determine which resources and APIs can be accessed.

Use a dedicated service account per workload, restrict IAM roles, and avoid using the default service account with broad permissions. Check OAuth scopes and IAM roles; scopes do not replace IAM policies and can constrain tokens in ways that must be understood clearly.

During migration, service account emails and IAM bindings are specific to Google Cloud. Create an equivalent workload identity in the target provider.

### 6.5. Workload Identity Comparison Table

| Purpose | AWS | Azure | Google Cloud |
|---|---|---|---|
| VM identity | IAM role attached via instance profile | Managed Identity | Attached service account |
| Credential issuance | Temporary credentials via IMDS/SDK | Token via managed identity endpoint/SDK | OAuth access token via metadata server/SDK |
| Authorization | IAM identity/resource policies | Azure RBAC and resource access policies | IAM roles and resource policies |
| Kubernetes workload identity | IRSA or EKS Pod Identity per configuration | Microsoft Entra Workload ID | Workload Identity Federation for GKE |
| Migration replacement | Create new role and policies | Create new managed identity and role assignments | Create new service account and IAM bindings |

Mechanism names and support depend on the service, cluster version, and configuration. Map permissions by actual actions rather than translating role names literally across providers.

### 6.6. Least Privilege and Permission Mapping

A role in the source cloud may contain many policy statements. When moving to a target cloud, do not simply pick a similarly named role and assign it. Build an action-based permission table:

| Workload Action | Resource | Condition/Scope | Target Permission to Map |
|---|---|---|---|
| Read config | Secret/config store | Only the service's secrets | Read specific secret |
| Read input | Object storage | Job's prefix or bucket | Read object/prefix |
| Write output | Object storage | Workload's output path | Write object/prefix |
| Write telemetry | Logging/monitoring | Service's project/resource | Publish logs/metrics |
| Decrypt disk/data | KMS | Specific key | Conditional decrypt |

Test both allowed actions and actions that must be denied. Permission mapping is not complete just because the happy path works; verify the workload holds no unintended permissions.

## 7. Startup Scripts and Initialization Mechanisms

### 7.1. What Do Startup Scripts Do?

A startup script is code executed inside the guest OS when a VM boots or at a platform-supported lifecycle stage. It can:

- Install or configure agents.
- Fetch configuration from service discovery/secret managers.
- Mount volumes or prepare filesystems.
- Create users/groups and application directories.
- Configure services and start processes.
- Register the node with a management system.
- Emit readiness signals or report bootstrap status.

Startup scripts should be short, safely repeatable, and logged. Long or complex steps should move into configuration management, image baking, or separate orchestration.

### 7.2. AWS: EC2 User Data and cloud-init/EC2Launch

EC2 user data passes scripts or cloud-config when launching an instance. Linux AMIs typically integrate cloud-init; Windows uses EC2Launch or an equivalent mechanism depending on generation/AMI. Execution behavior depends on the OS, agent, and user data configuration.

Some default configurations only run user data on the first boot, while cloud-init has multiple modules/stages and can be configured to run on subsequent boots. Do not assume every script runs strictly once or on every reboot; inspect the cloud-init config and logs on the image.

General cloud-config example:

```yaml
#cloud-config
package_update: true
packages:
  - curl
  - jq
runcmd:
  - [ sh, -c, "systemctl enable app-agent" ]
  - [ sh, -c, "systemctl start app-agent" ]
```

This is a cloud-init example, not EC2-specific syntax. The image must have cloud-init and a suitable package manager. In production, pin package versions where needed, check errors at each step, and never put credentials in user data.

### 7.3. Azure: Custom Data, cloud-init, and VM Extensions

Azure supports Custom Data at VM creation and cloud-init on many Linux images. VM extensions like Custom Script Extension can run installation or configuration scripts after the VM is provisioned. Windows has corresponding extensions and provisioning mechanisms.

Distinctions:

- Custom Data is payload passed at VM creation; not every image executes it automatically if cloud-init or a suitable agent is missing.
- cloud-init handles Linux configuration across stages.
- VM extensions have their own lifecycle, provisioning state, and retry behavior.

Do not place secrets in Custom Data because the payload may be stored in resource configuration or appear in logs. Use Managed Identity to retrieve secrets at runtime when needed.

### 7.4. Google Cloud: Startup Scripts and Guest Environment

Compute Engine supports startup scripts via instance/project metadata; the guest environment/agent inside the VM reads metadata and runs the script per platform rules. You can supply an inline startup script or reference a script file from an accessible location.

Verify that the guest environment is installed and running. If a custom image strips out the required agent, metadata startup scripts may not run. Startup scripts may execute across boots per guest agent behavior; make scripts idempotent and avoid duplicate side effects on VM reboot.

### 7.5. Startup Automation Comparison Table

| Aspect | AWS | Azure | Google Cloud |
|---|---|---|---|
| Initialization payload | EC2 user data | Custom Data | Instance/project metadata |
| Common Linux bootstrap | cloud-init | cloud-init | Startup script via guest environment; cloud-init also usable depending on image |
| Windows bootstrap | EC2Launch/agent and user data per image | VM extensions and Windows provisioning mechanisms | Windows guest environment/startup scripts per image |
| Extension mechanisms | SSM/agent, configuration management | VM extensions, Run Command, and automation | Guest agent, OS Config, and configuration tooling |
| Failure visibility | cloud-init/EC2Launch logs, instance status | Extension status, provisioning state, guest logs | Serial port output, guest agent/startup script logs |

These options are not mutually exclusive. You can use image baking for stable software installation and startup scripts for environment-dependent configuration.

## 8. Designing Portable and Secure Startup Scripts

### 8.1. Separating Common Logic from Provider-Specific Logic

Common logic can include installing the app, creating directories, configuring services, and running health checks. Provider-specific logic includes reading metadata, fetching tokens, registering identity, configuring networking, or calling cloud APIs.

Separating the two keeps application logic consistent and isolates provider-dependent code. Use per-cloud adapters/scripts rather than writing one huge shell script full of hard-to-test branches.

### 8.2. Idempotency

Startup scripts may be re-executed due to reboots, extension retries, or operational actions. An idempotent script can run multiple times without creating invalid state.

Example:

```bash
#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /opt/example-app

if ! id -u appuser >/dev/null 2>&1; then
  useradd --system --home-dir /opt/example-app --shell /usr/sbin/nologin appuser
fi

install -d -o appuser -g appuser -m 0750 /var/lib/example-app
systemctl enable example-app.service
```

Adapt this example to your actual Linux distribution and service. Avoid commands with cumulative side effects like creating new cloud resources on every boot without checking existing state.

### 8.3. Never Embed Secrets

Never place API keys, passwords, private keys, or access tokens in:

- AMIs/managed images/custom images.
- User data or Custom Data.
- Instance/project metadata.
- Startup scripts, long-lived environment variables, or logs.
- Source repositories or build artifacts.

Instead, attach a least-privilege workload identity and retrieve secrets from a secret manager when needed. If a script requires bootstrap credentials, use short-lived, narrowly scoped, rotatable mechanisms.

### 8.4. Preventing Metadata Exposure and SSRF

Web applications can be exploited via SSRF to reach the metadata service. Protect with IMDSv2, required headers, network controls, and input validation per provider. Startup scripts should read only required metadata fields and never dump all metadata into logs.

### 8.5. Retries and Timeouts for Bootstrapping

Package repositories, secret managers, or configuration APIs can be temporarily unavailable right after a VM boots. Startup scripts should use timeouts and bounded backoff retries with an overall time cap. If bootstrapping fails, log a clear error state and let orchestration decide whether to retry or replace.

Avoid infinite loops that leave the VM stuck in provisioning forever. You can split bootstrapping into stateful steps so it resumes safely from checkpoints.

### 8.6. Logging and Exit Status

Log to journald, cloud-init output, or the platform logging agent. Never log secrets or tokens. Scripts must exit with appropriate status codes; masking errors with `|| true` on every command causes the control plane to report success even when the machine is not ready.

### 8.7. Post-Bootstrap Readiness

A VM should only join a load balancer or serve traffic in an instance group when:

- OS boot is complete.
- Required disks and filesystems are mounted.
- Workload identity can obtain a token.
- Necessary configurations and secrets are loaded.
- Application processes are running.
- Health endpoints or smoke tests pass.

Startup script completion does not mean the application is ready. Use health and readiness checks at the orchestration layer to confirm serving readiness.

## 9. Packaging Standard Images and Runtime Configuration

### 9.1. Golden Images

A golden image is a vetted, standardized image typically containing the OS, security patches, agents, runtimes, and baseline configuration. It shortens boot time and ensures VM consistency.

A golden image should have:

- Clear ownership and version.
- Supported base OS and patching schedule.
- Package inventory/SBOM if required by policy.
- Required agents for monitoring, security, and cloud integration.
- No embedded secrets, tokens, or shared machine identities.
- Reproducible build, scanning, and approval pipelines.
- Testing on target instance types and regions.

### 9.2. Image Baking vs. Boot-Time Configuration

**Image baking** installs software and stable configuration before publishing the image. **Boot-time configuration** applies environment-dependent values when the VM starts, such as region, endpoints, roles, or service settings.

Putting too much work into startup scripts slows down booting and introduces failures from repositories/networks. Putting too much dynamic config into images hurts reusability and risks carrying stale environment data. Partition responsibilities based on how static the data is.

### 9.3. Never Blindly Clone Machine Identity

Cloning an image or disk can carry over machine IDs, SSH host keys, certificates, monitoring agent IDs, or domain state. If multiple VMs share the same identity, management and audit systems can confuse machines.

Golden images should be generalized following OS/provider guidance; generate unique host keys or machine identities at provisioning time. For domain-joined Windows or Linux enrolled in management systems, use proper generalize/specialize workflows.

### 9.4. Versioning and Rollback

Never overwrite a published image version. Create a new version, store its digest/checksum, build source, and test results. Retain several rollback versions during the support window.

When releasing a new image, roll out via canary or a subset of the fleet, checking boot success, startup duration, health checks, agents, and metrics before replacing all instances.

## 10. Architecturally Mapping Startup Parameters and Metadata

### 10.1. Avoid Depending on Provider Field Names

A portable script should not assume every cloud uses identical field names such as `instance_id`, `zone`, or `region`. Normalize them into an internal schema:

```json
{
  "provider": "example-cloud",
  "instance_id": "vm-123",
  "region": "region-a",
  "zone": "zone-a",
  "machine_type": "compute-medium",
  "network": {
    "private_ip": "10.0.1.10"
  }
}
```

This is an illustrative internal schema, not a provider metadata response. A dedicated adapter reads native metadata and maps it into the common schema; fields absent on a cloud should be null/omitted rather than fabricated.

### 10.2. Per-Provider Adapters

A clean design can include:

- `metadata/aws`: reads IMDSv2 and handles tokens.
- `metadata/azure`: calls IMDS with required headers and API version.
- `metadata/gcp`: calls the metadata server with the flavor header.
- `identity/aws`: uses the SDK credential chain/instance profile.
- `identity/azure`: uses the Managed Identity SDK.
- `identity/gcp`: uses Application Default Credentials/attached service account.

Applications call internal interfaces such as `get_instance_context()` or `get_secret()` instead of building metadata URLs inside business modules.

### 10.3. Provider Detection

Do not detect the cloud purely from a user-modifiable environment variable. Use controlled metadata endpoints, agents, or deployment configuration. If the provider cannot be identified, fail explicitly or fall back to an approved static configuration; do not probe every cloud's metadata endpoint indiscriminately.

### 10.4. Local Development and Testing

On developer workstations, metadata services may not exist. Design adapters to support mocks or developer credential chains. Never simulate production metadata by writing real credentials into config files.

Test these scenarios:

- Metadata endpoint timeouts or 401/403 responses.
- Expired tokens or clock skew.
- Missing optional fields.
- Blocked network routes to metadata.
- Insufficient workload identity permissions.
- Unrecognized provider.

## 11. Cross-Cloud Image Migration Workflow

### 11.1. Step 1 – Source Inventory

Record:

- Image ID, version, source OS, and architecture.
- Boot mode, partition table, filesystem, and disk size.
- Packages/agents/drivers and licenses.
- Machine identity, host keys, and domain state.
- Startup scripts/user data and metadata dependencies.
- IAM role/managed identity/service account and effective permissions.
- NICs, IPs, routes, firewalls, DNS, and endpoint dependencies.
- Encryption keys, backups, and RTO/RPO.

Do not read or export secrets into the inventory. Record only secret names, storage locations, and authorized identities.

### 11.2. Step 2 – Define the Portability Boundary

Classify components into three groups:

- **Portable:** application code, packages, standard shell scripts, provider-agnostic config files.
- **Adaptable:** cloud-init, service configs, agents, disk mapping, network configs, and metadata adapters.
- **Provider-specific:** AMI IDs, Azure resource IDs, GCP image/project IDs, roles/managed identities/service accounts, KMS keys, NICs/subnets, and metadata APIs.

Preserve portable parts, build adapters for adaptable parts, and recreate provider-specific parts at the destination.

### 11.3. Step 3 – Prepare the Target Image

Select an image format and import path supported by the target cloud. Convert disks if necessary, verify checksums and sizes. Update bootloaders/drivers/agents, strip source static network configurations, and publish a new image version.

If the image contains sensitive data or credentials, handle according to security procedures. Rotate credentials and generate fresh machine identities as required.

### 11.4. Step 4 – Create Networking and Workload Identity

Create VPC/VNet, subnets, routes, firewalls/security groups, DNS, and private endpoints in the target cloud. Create the workload identity and map permissions by action, resource, and scope.

Test both allowed and denied actions. Do not grant broad administrative roles just to make bootstrapping succeed.

### 11.5. Step 5 – Rewrite Metadata Adapters and Startup Scripts

Update metadata endpoints, headers, API versions, and identity SDKs for the target provider. Keep startup scripts idempotent, secret-free, and equipped with timeouts/retries. Separate common configuration from provider-specific configuration.

### 11.6. Step 6 – Boot Test in an Isolated Environment

Launch a test VM isolated from production traffic. Verify:

- OS boot, firmware, drivers, and disk mapping.
- Metadata endpoint and user data.
- Workload identity tokens and access permissions.
- Startup script status, logs, and reboot idempotency.
- NIC, IP, routes, DNS, and dependency connectivity.
- Monitoring/security agents and health checks.

### 11.7. Step 7 – Performance and Security Validation

Benchmark CPU, memory, storage, and networking on the target machine type. Verify image scanning, patch levels, firewalls, IAM scope, metadata protections, and logging. Equal vCPU counts do not guarantee equal throughput across providers or instance families.

### 11.8. Step 8 – Cutover and Rollback

Execute canary or blue/green deployment. Synchronize data, shift traffic incrementally, and monitor error rates and latency. Maintain a data-consistent rollback plan; if the workload writes data, clearly define freeze points, replication lag, and write authority at every stage.

## 12. Hands-On Example: Standardizing a Startup Contract

### 12.1. Common Configuration Structure

An application can read a normalized configuration produced by an adapter:

```yaml
runtime:
  provider: aws
  region: ap-southeast-1
  zone: ap-southeast-1a
  instance_id: i-example
identity:
  mechanism: instance-role
  secret_source: managed-secret-store
application:
  environment: production
  config_ref: orders-api/prod
```

This is an illustrative internal structure. Never store access tokens or secret values in this file. Runtime information should be generated from metadata/identity adapters and managed configuration rather than hardcoded into golden images.

### 12.2. Bootstrap Pseudocode

```text
function bootstrap():
    context = provider_adapter.get_instance_context()
    identity = provider_adapter.get_workload_identity()

    assert context.instance_id is present
    assert identity.can_read("orders-api/prod")

    config = secret_store.read_config("orders-api/prod", identity)
    validate(config)
    ensure_required_volumes_mounted()
    ensure_application_version_installed()
    write_runtime_config_atomically(config)
    start_application_service()
    wait_until_health_check_passes(deadline=bootstrap_deadline)
    report_bootstrap_success(context.instance_id)
```

Pseudocode illustrates sequence, not an executable language. `ensure_*` steps must be idempotent; `write_runtime_config_atomically` prevents services from reading partially written files; the identity is granted only required permissions.

### 12.3. Success Criteria

Bootstrap is considered successful only when:

- Metadata adapter returns a valid context.
- Workload identity obtains a token and reads the intended secret/config.
- Required volumes are mounted properly.
- The application runs the expected version.
- Health checks pass within the deadline.
- Logs contain zero credentials.
- Reboot tests produce no duplicate resources or side effects.

## 13. Troubleshooting

### 13.1. VM Boots Successfully but Has No Network

Check NIC attachment, drivers, interface names, DHCP/static configs, route tables, security policies, and DNS. If the image was cloned from another cloud, check for network configs tied to old MACs/interfaces and which cloud agent manages networking.

### 13.2. Startup Script Does Not Run

Check whether user data/custom data/metadata was passed at VM creation; whether the image includes cloud-init or the guest agent; whether the script has the proper format and execute permissions; and whether bootstrap logs show syntax, package repository, or network errors.

Do not run the script manually and conclude automated provisioning works. Re-test by launching a fresh VM from the published image.

### 13.3. Workload Cannot Obtain Credentials

Check whether the identity is attached to the VM, whether the token endpoint is reachable, whether role assignments/IAM bindings target the right resource scope, whether audience/scope are correct, and whether system clocks are synchronized.

On `AccessDenied`/`Forbidden`, inspect audit logs to pinpoint the exact action and resource. Do not grant project-wide owner/admin permissions as a workaround.

### 13.4. Application Cannot Read Metadata

Verify the provider's endpoint, headers, and token flow. AWS requires a token when IMDSv2 is enforced; Azure requires `Metadata: true`; Google Cloud requires `Metadata-Flavor: Google`. Ensure firewalls, proxy environment variables, and SSRF mitigations are not inadvertently blocking legitimate agent requests.

### 13.5. Image Fails to Boot on Target Cloud

Check architecture, BIOS/UEFI, partitions, bootloader, storage drivers, initramfs, Secure Boot, and image format. Inspect serial/console logs. Create a copy to troubleshoot, preserve the original artifact, and record checksums.

### 13.6. VM Boots but Identity or Monitoring Agent Is Duplicated

Cloned images may retain host keys, machine IDs, or agent IDs. Use generalize/specialize procedures, generate unique identities, and re-register agents. Do not delete random identity files without understanding their impact on domain joins, cloud agents, or management systems.

## 14. Common Pitfalls

- **Treating image IDs as portable:** AMI IDs, Azure image versions, and GCP image IDs belong to separate provider namespaces.
- **Treating a machine image as a full-environment backup:** NICs, IAM, DNS, firewalls, and secrets may live outside the image.
- **Ignoring boot mode/architecture:** the image imports successfully, yet the VM refuses to boot.
- **Keeping old network configs:** interface names, MACs, or static IPs no longer apply.
- **Copying machine identity:** host keys, machine IDs, and agent IDs collide.
- **Baking credentials into images or user data:** secrets can be read from metadata, logs, or artifacts.
- **Using the wrong metadata endpoint:** headers/tokens/API versions do not match the provider.
- **Disabling metadata protections to fix errors:** increases exposure to SSRF and credential theft.
- **Granting overly broad roles:** bootstrap succeeds, but the workload holds excessive permissions.
- **Assuming startup scripts run only once:** reboots or extension retries cause duplicate side effects.
- **Installing everything at boot:** slows provisioning and creates network/repository fragility.
- **Skipping guest agent checks:** metadata or extensions silently fail to execute.
- **Ignoring licensing:** migration breaches license terms or fails activation.
- **Not re-testing on a fresh VM:** manual script runs succeed while automated provisioning still fails.
- **Testing only the happy path:** failing to observe behavior when metadata, token, or secret services are disrupted.

## 15. Comparison and Migration Checklist

### Image

- [ ] Clarified differences between image, snapshot, machine image, and template.
- [ ] Documented architecture, firmware/boot mode, partitions, and filesystems.
- [ ] Verified storage/network drivers, guest agents, and licensing.
- [ ] Confirmed image format and import path supported by the target cloud.
- [ ] Preserved checksums, versions, ownership, and rollback procedures.
- [ ] Confirmed image contains no secrets or shared machine identities.

### Metadata and Startup

- [ ] Identified metadata endpoints and header/token flows for each provider.
- [ ] Confirmed applications do not hardcode one metadata URL across all clouds.
- [ ] Confirmed user data/custom data contains no secrets.
- [ ] Confirmed startup scripts are idempotent with timeouts, retries, and logging.
- [ ] Installed and verified required guest agents/cloud-init/extensions.
- [ ] Configured health checks to confirm application readiness post-bootstrap.

### Identity and Security

- [ ] Mapped instance roles/managed identities/service accounts by actual permissions.
- [ ] Confirmed credentials are short-lived and obtained via workload identity.
- [ ] Applied least-privilege IAM policies and tested denied actions.
- [ ] Confirmed secrets are fetched from secret managers, not baked into images.
- [ ] Protected metadata endpoints against SSRF.
- [ ] Verified key/encryption policies and audit logging in the target cloud.

### Migration Validation

- [ ] Test-booted a VM in an isolated environment.
- [ ] Verified disks, NICs, routes, DNS, and dependencies.
- [ ] Tested startup scripts on both initial boot and reboot.
- [ ] Verified workload identity accesses intended resources only.
- [ ] Verified monitoring/security agents operate with unique identities.
- [ ] Validated performance benchmarks against workload requirements.
- [ ] Prepared canary/cutover, rollback plan, and clear ownership.

## 16. Conclusion

AWS AMIs, Azure Managed Images/Compute Galleries, and Google Cloud custom/machine images all standardize VM creation, yet they are not directly interchangeable formats. Image portability depends on architecture, boot mode, drivers, disk mapping, encryption, licensing, and guest agents. During migration, import or build native images at the destination and test them on actual target VM types.

Metadata services provide runtime context and can issue short-lived credentials; each provider enforces its own endpoints, headers, and token flows. Workload identities also differ: IAM roles/instance profiles, Azure Managed Identities, and Google service accounts must be mapped by actual permissions rather than copying role names. Startup scripts should stay short, idempotent, logged, timed out properly, free of secrets, and cleanly split between portable logic and provider-specific adapters.

A reliable cross-cloud process starts with inventorying images and permissions, defining the portability boundary, preparing target networking and identities, converting images, updating metadata adapters and startup automation, and test-booting in an isolated environment before cutover. Testing failure cases across metadata, tokens, agents, and reboots ensures workloads migrate smoothly while preserving security, operability, and compute performance.
