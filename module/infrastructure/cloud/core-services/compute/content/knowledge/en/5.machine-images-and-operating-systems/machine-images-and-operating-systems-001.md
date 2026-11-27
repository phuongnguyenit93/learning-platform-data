# How Do Boot Images, Custom Images, and Machine Templates Differ?

## Lesson Objectives

When creating a virtual machine on a cloud platform, you typically have to select an image and provide multiple deployment parameters. Some platforms also allow saving the configuration as a template to create multiple identical machines. The three concepts—boot image, custom image, and machine template—are related, but they describe different aspects.

After this lesson, you will be able to:

- Explain how a boot image is used during the virtual machine startup stage.
- Distinguish between provider-supplied prebuilt images and organization-built custom images.
- Describe a machine template and the configurations commonly stored in it.
- Combine images and templates to deploy virtual machines consistently.
- Design a secure lifecycle for building, testing, updating, and releasing images.

## 1. Three Concepts in One Scenario

Suppose an operations team needs to deploy 30 virtual machines running a web service. All machines must use the same Linux version, have the latest security patches, and have pre-installed runtimes, monitoring agents, and tested system configurations. They also need the same CPU type, disk capacity, subnet, firewall, and service access permissions.

There are three separate tasks:

1. Select an operating system source capable of booting the virtual machine, such as a Linux image published by the provider.
2. Create an organization-owned image from that source, install runtimes and agents, and apply patches along with standard configurations.
3. Save the machine creation configuration into a machine template, referencing the custom image along with the machine type, disks, network, identity, and initialization data.

When scaling from 30 to 50 machines, the system can use the same template version to create additional machines with a consistent configuration. When upgrading the runtime version or OS patches, the team builds a new image and updates the template version to reference that image.

## 2. What Is a Boot Image?

A **boot image** is an image used as the source to create the boot disk (or root volume) for a virtual machine. The image typically contains the operating system, partition structure or filesystem, bootloader, and components needed for the operating system to start in the supported virtualization environment.

When creating a virtual machine, the platform typically creates a boot disk from the image or from an associated snapshot, attaches the disk to the machine, and configures the virtual machine so its firmware boots from that disk. The image therefore provides the initial state of the operating system.

Common boot image sources:

- **Provider public images:** popular Linux or Windows distributions prepared for the platform.
- **Marketplace images:** partner-provided images, which may include pre-installed software or licenses.
- **Organization private images:** images created and managed within the organization's account or project.
- **Community-shared images:** should only be used after verifying the publisher, provenance, contents, and usage rights.

A boot image must be compatible with the target environment. Factors to verify include CPU architecture (x86_64 or ARM64), BIOS/UEFI boot mode, virtualization type, storage and network device drivers, disk format, instance type, and deployment region. An image that boots properly on one machine family is not guaranteed to work on every machine family.

A boot image also does not need to contain all application data. Persistent data is typically placed on separate volumes, object storage services, or managed databases. This separation allows virtual machines to be replaced without losing business data.

## 3. What Is a Custom Image?

A **custom image** is an image created by a user or organization, typically based on an existing boot image or from a prepared virtual machine. It packages the operating system along with the software, patches, and configurations required before the machine is placed into service.

A standard custom image may include:

- An approved operating system version and updates.
- Shared runtimes and libraries, such as JRE, .NET runtime, or a web server.
- Monitoring, logging, backup, or security agents.
- Operating system configurations such as timezone, file descriptor limits, SSH configuration, and audit policies.
- Public certificates or required trust configurations, if permitted by governance processes.
- Initialization scripts and guest agent components suitable for the platform.

Custom images reduce configuration time at startup, standardize environments, and limit configuration drift between machines. When every machine installs software through a separate manual process, machine state easily diverges over time. A tested image enables reproducing a software baseline with a defined version.

### Boot Images and Custom Images Are Not Mutually Exclusive

This is the most common point of confusion: **boot image describes the role of an image; custom image describes its origin or how the image was created**. A custom image can certainly be a boot image used to boot a virtual machine.

For example:

- An Ubuntu LTS image published by the provider is a public boot image.
- An Ubuntu LTS image on which the operations team installed Java, applied patches, and added agents is a custom image.
- If that customized Ubuntu image is used to create the root volume for a virtual machine, it is simultaneously the machine's boot image.

Therefore, when designing workflows, distinguish between an image used for booting and an image owned and maintained by the organization. A private image can also be used as the source image for another custom image.

## 4. What Is a Machine Template?

A **machine template** is a configuration blueprint describing how to create a virtual machine or a group of machines with identical characteristics. The template typically references an image and declares the remaining deployment attributes.

Depending on the platform, a template may contain:

- The Image ID or image version to use for the boot disk.
- Machine type, vCPU count, RAM capacity, or performance profile.
- Boot disk and data disk configuration: size, volume type, encryption, IOPS, or throughput.
- Network, subnet, network interface, IP address, and firewall/security group.
- Service account, instance profile, managed identity, or access role.
- Metadata, startup script, or user data.
- Region/zone, placement, termination protection options, and other operational attributes.

A template describes **how to create a machine**. It usually does not contain a copy of the operating system's contents like an image does. Instead, the template holds a reference to a specific image and the parameters the platform needs to provision the machine.

A good template enables configuration reuse, reduces manual effort, and produces interchangeable machines. When using the same template in an autoscaling group or managed instance group, the platform can provision additional machines with the same configuration when load increases.

### Illustrative Template Example

The following YAML snippet is a conceptual configuration illustrating the components, not deployment syntax intended for direct use with a specific provider:

~~~yaml
machineTemplate:
  name: web-prod-v3
  image:
    id: org-linux-web-2026-11
  compute:
    machineType: general-purpose-medium
    vcpu: 4
    memoryGiB: 16
  bootDisk:
    sizeGiB: 40
    encrypted: true
  network:
    subnet: private-app-subnet
    securityGroups:
      - web-service
  identity:
    serviceRole: web-runtime-role
  bootstrap:
    userData: configure-service.yaml
~~~

In the example, image.id points to a tested custom image. The template also declares the machine type, boot disk, network, service permissions, and initialization data. When creating a machine, the platform combines the image with these attributes.

## 5. Direct Comparison

| Criterion | Boot image | Custom image | Machine template |
|---|---|---|---|
| Question answered | Which OS does the machine boot from? | What has the organization pre-packaged in the image? | What configuration is the machine created with? |
| Nature | Source image for the boot disk | Organization- or user-created/customized image | Deployment configuration blueprint |
| Main contents | OS, bootloader, disk layout, and boot components | Boot image plus packaged software, patches, and configurations | Image reference, CPU/RAM, disks, network, identity, and bootstrap |
| Contains an OS? | Usually yes | Usually yes if used as a boot image | Not necessarily; usually references an image |
| Who manages it? | Provider, marketplace, or user | Organization's platform/operations team | Deployment/infrastructure team |
| When does it change? | When choosing an OS or base version | When updating OS, runtimes, agents, or base configuration | When changing machine type, image, network, disks, or deployment policy |
| What is it used for? | Initializing the OS disk | Standardizing software and initial machine state | Creating consistent new machines, scaling, and replacing machines |

You can remember the relationship as follows:

~~~mermaid
flowchart TD
    A["Public boot image"] --> B["Prepare OS, patches, and software"]
    B --> C["Tested custom image"]
    C --> D["Machine template references image"]
    E["CPU, RAM, disks, network, identity"] --> D
    F["Startup script / user data"] --> D
    D --> G["Create virtual machine"]
    G --> H["Runtime configuration and run workload"]
~~~

Images and templates are typically managed on separate lifecycles. One image can be referenced by multiple templates. A template can be updated to point to a new image without recreating the image-building process.

## 6. Image Baking and Startup Bootstrap

When building virtual machines, there are two common ways to deliver software and configuration to a machine.

**Image baking** is installing software, patches, and base configurations during the custom image build process. When the machine starts, most components are already ready. This approach fits software that is relatively stable, requires prior testing, or has long installation times.

**Bootstrap** is the configuration step executed when the machine is created or boots for the first time, typically via cloud-init, user data, a startup script, or a configuration management tool. Bootstrap fits environment-dependent information such as service endpoints, environment names, region-specific runtime configurations, or registering the machine with a management system.

| Criterion | Image baking | Bootstrap |
|---|---|---|
| Timing | Before deploying the machine | When the machine is created or boots |
| Suitable contents | OS, patches, runtimes, agents, and base configuration | Environment parameters, service config, registration, and initialization tasks |
| Advantages | Fast machine startup and easily testable base state | Easy to vary by environment, less need to rebuild images for minor config changes |
| Risks | Image can become stale if not rebuilt regularly | Startup depends on network or external services; script errors can leave the machine unready |

In practice, both are commonly combined. Package stable base components into the image, while environment-specific details and deployment-time tasks are provided via bootstrap. Never embed passwords, private keys, long-lived tokens, or environment secrets in plaintext inside an image or user data. Retrieve secrets from a secret manager using workload identity and least privilege.

## 7. Controlled Custom Image Build Process

A common process consists of the following steps:

1. **Select a base image:** verify the publisher, OS version, CPU architecture, boot mode, licensing, and platform supportability.
2. **Create a build environment:** use a dedicated pipeline, restrict access, pin tool versions, and record inputs.
3. **Install patches and software:** install runtimes, agents, and base configurations according to approved versions.
4. **Clean machine state:** remove temporary data, credentials, build logs, machine identity, and registration details specific to the build machine.
5. **Test the image:** verify boot, network access, disks, agents, logging, monitoring, security policies, and instance compatibility.
6. **Scan and approve:** scan for vulnerabilities, check configuration compliance, record software bill of materials, and verify image provenance.
7. **Publish an immutable version:** create a new image ID or version; record metadata such as OS version, build ID, timestamp, commit, and test results.
8. **Update the template:** create a new template version referencing the new image, then run a trial deployment before rolling out broadly.

Some cleanup tasks depend on the operating system:

- For Linux, reset cloud-init state, machine ID, SSH host keys, and machine registration details according to the OS and platform guidelines. New machines must generate unique identifiers upon boot.
- For Windows, the capture process typically requires generalizing the OS using a tool like Sysprep per platform and image type requirements.
- For management agents, avoid copying a single identity or registration token across every machine created from the image.

Not every image requires the exact same cleanup steps. Follow the supported procedure for the target operating system and image service.

## 8. Image and Template Versioning

Images and templates should be released with versions so you can identify which configuration each machine was created from.

Useful principles:

- Use a naming convention, such as linux-web-2026-11-v3, while still storing the immutable image ID or version assigned by the platform.
- Do not overwrite an image actively used by multiple environments if the platform supports creating new versions.
- Attach metadata about OS version, patches, runtimes, build pipeline, approver, and end-of-support date.
- Production templates should reference a specific image version. Automatically pointing to the latest version can cause subsequent deployments to use a different image without an approved configuration change.
- Record the template and image versions used for every deployment to support auditing and rollback.

When releasing a new image, you do not have to update all running machines at once. You can create a new template version and roll out in stages:

~~~mermaid
flowchart LR
    A["Image v1 + Template v1"] --> B["Current production machines"]
    C["Build and test Image v2"] --> D["Template v2"]
    D --> E["Canary: a small group of machines"]
    E --> F{"Metrics meet requirements?"}
    F -->|Yes| G["Expand rollout"]
    F -->|No| H["Halt rollout, revert to v1"]
    G --> I["Complete release"]
~~~

Phased rollouts help detect compatibility or performance issues before affecting the entire service. Maintain the ability to recreate machines from the previous image/template version throughout the defined rollback window.

## 9. Naming Examples Across Cloud Platforms

Providers use different resource names. Do not assume a single term means the exact same thing on every platform.

| Platform | Boot image / custom image | Machine creation configuration |
|---|---|---|
| AWS | Amazon Machine Image (AMI), which can be a public, Marketplace, or private AMI | EC2 Launch Template referencing an AMI and instance configuration |
| Google Cloud | Public image or custom image used for the boot disk; Machine Image can store the configuration and disk state of a VM | Instance Template describing the configuration to create a VM or VM group |
| Microsoft Azure | Marketplace image or private image in Azure Compute Gallery/Managed Images | VM deployment configuration, VM Scale Set model, or infrastructure template such as ARM/Bicep |

Key distinctions to remember:

- In AWS, an AMI is the image used to initialize an instance; a Launch Template stores the configuration for creating an EC2 instance.
- In Google Cloud, a custom image used as a boot disk source differs from a Machine Image. A Machine Image captures the configuration and disks of a VM, whereas an Instance Template is a configuration blueprint for creating VMs.
- In Azure, an image resource stores the OS/base software contents; a VM or VM Scale Set configuration defines how machines are deployed from that image.

Names and capabilities may change across service versions. In real-world deployments, verify the current documentation for the service in use, especially regarding multi-disk capture, encryption, image sharing, and cross-region replication.

## 10. Image Security and Governance

Custom images are part of the software and infrastructure supply chain. If an image contains malware, vulnerabilities, or exposed credentials, every machine created from it may inherit the issue.

Measures to apply:

- Obtain base images only from verified providers or trusted sources.
- Scan OS and software for vulnerabilities before release.
- Track OS end-of-support dates and schedule replacement image builds.
- Restrict permissions to create, share, copy, and delete images.
- Encrypt snapshots or boot disks according to organizational data policies.
- Control image access across accounts, projects, and regions.
- Retain metadata, build logs, test results, and approval history.
- Do not package secrets, user data, sensitive logs, or private keys inside images.
- Maintain a process to revoke or deprecate images no longer approved for deployment.

Templates also need protection. Templates may contain network information, access roles, user data, or references to internal resources. Manage templates with least privilege, change reviews, and version control just like infrastructure source code.

## 11. Choosing the Right Approach

| Need | Approach |
|---|---|
| Quick test of a single Linux machine | Use a provider-supported public boot image |
| Multiple machines needing the same runtime and agents | Build a tested custom image |
| Creating consistent machines across multiple environments | Use a versioned machine template or infrastructure configuration |
| Machines with region-specific configurations | Package the common baseline in the image; pass regional parameters in template/bootstrap |
| Periodic patch updates needed | Build a new image version, test it, and release via a new template |
| Autoscaling required | Combine a standard image with a template used by the autoscaling service |
| Application data recovery needed | Use appropriate backup/snapshot and data recovery mechanisms; do not rely solely on the boot image |

Not every workload needs a custom image. A short-lived test machine can use a public image and install software at boot. For production systems requiring consistency, auditability, and predictable startup times, a custom image combined with a versioned template is usually easier to manage.

## 12. Common Mistakes

**Confusing a custom image with a machine template:** an image packages OS and software state; a template describes the machine creation configuration and usually references an image. If you only update the image while the template still references the old version, new machines continue using the old baseline.

**Baking environment configuration into the image:** the same image may need to run in dev, staging, and production. If endpoints, environment names, or access permissions are hardcoded in the image, reuse becomes difficult and error-prone. Pass environment parameters via the template or bootstrap.

**Packaging secrets inside the image:** secrets can leak when the image is shared, copied, or downloaded. Use a secret manager and workload identity to fetch secrets at runtime.

**Failing to clean machine identifiers:** multiple VMs may end up sharing the same machine ID, SSH host key, or registration identity. This causes confusion in management, monitoring, and authentication. Clean state according to OS procedures and generate new identifiers at boot.

**Using an image with the wrong architecture or boot mode:** an ARM64 image cannot be used as an x86_64 image; a BIOS-configured image may fail to boot under a required UEFI configuration. Verify compatibility before release.

**Updating images by overwriting in a way that hinders traceability:** without preserving versions and metadata, operations teams struggle to determine what contents a machine was created from. Publish a new image with a new ID/version and update templates in a controlled manner.

**Treating an image as a full data backup:** a boot image typically represents only the boot disk state. Data on separate volumes, databases, and object storage require separate backup/restore strategies. Some machine image types can capture multiple disks, but you must verify capture scope and application consistency.

## 13. Pre-Release Checklist

- [ ] Verified provenance, licensing, and support lifecycle of the base image.
- [ ] Image is compatible with CPU architecture, boot mode, instance type, and deployment region.
- [ ] OS, runtimes, agents, and patches have recorded versions.
- [ ] Removed secrets, build data, and build-machine-specific identifiers.
- [ ] Tested boot, networking, disks, logging, monitoring, and service access.
- [ ] Scanned for vulnerabilities and recorded approval results.
- [ ] Image has an immutable ID/version along with traceability metadata.
- [ ] Template references the exact image version and has appropriate CPU, RAM, disk, network, and identity settings.
- [ ] User data/bootstrap contains no plaintext secrets and is safe for repeated execution (idempotent).
- [ ] Deployed canary, monitored metrics, and prepared a rollback plan.

A boot image provides the foundation for a virtual machine to start. A custom image packages the operating system along with the organization's standard software and configurations; when used as a boot disk source, it is also a boot image. A machine template describes how to create a machine by referencing an image and declaring CPU, memory, disks, network, identity, and initialization parameters. Managing the lifecycles of images and templates separately makes it easier to deploy virtual machines consistently, update in a controlled manner, and scale workloads in the cloud.
