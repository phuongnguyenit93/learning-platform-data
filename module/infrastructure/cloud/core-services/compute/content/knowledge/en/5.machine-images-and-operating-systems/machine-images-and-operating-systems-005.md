# Building Images via Pipelines and Managing Versions

A machine image is a prepared template used to launch virtual machines with an operating system, boot configuration, base software, and required components. When multiple virtual machines are created from the same tested image, operations teams can deploy consistent environments, shorten provisioning time, and maintain better control over what goes into each machine.

For **CLOUD_CORE_SERVICES_COMPUTE**, images are part of the compute provisioning workflow: an image must be compatible with the machine type, CPU architecture, operating system, platform agents, security requirements, and application deployment model. Building images through a pipeline makes this process repeatable, creates an audit trail, and delivers new versions to environments in a controlled way.

## 1. What Is a Machine Image?

A machine image is an artifact used to create virtual machines. Depending on the platform, an image may contain:

- The operating system and system packages.
- The kernel, bootloader, and boot configuration.
- Drivers or support components for virtualized devices.
- Cloud agents, guest agents, or provider management tools.
- Runtimes, system libraries, and base dependencies.
- Default configurations, initialization scripts, and baseline security policies.
- Applications or application components if the organization chooses that packaging model.

Images are typically stored as platform-managed artifacts or in the organization's private image registry. When creating a virtual machine from an image, the provider creates a boot disk and configures the machine according to the format and settings supported by the image.

### 1.1. Distinguishing Machine Images and Container Images

These two image types serve different purposes:

| Criterion | Machine image | Container image |
| --- | --- | --- |
| Deployment unit | Virtual machine or complete compute instance | Process/application inside a container |
| Operating system | Usually contains a bootable guest OS | Usually contains user space; shares the host kernel |
| Main contents | OS, boot components, agents, drivers, base packages, and optionally apps | Application, runtime, libraries, and required filesystem |
| Lifecycle | Typically changes when releasing a new image or replacing VMs | Can be released independently of the host VM |
| Purpose | Standardizes the compute machine foundation | Standardizes the application runtime environment |

A system can use both: the machine image provides the OS and container runtime; the container image provides the application. In that case, versions and vulnerabilities must be managed across both layers.

### 1.2. Base Images and Golden Images

A **base image** is the initial image supplied by a provider or community, usually containing a minimal operating system. A **golden image** is a standard image built and approved by the organization, containing the baseline configuration, patches, and authorized tooling.

A golden image lets teams share a vetted foundation. However, it only delivers value when updated regularly, given clear ownership, backed by clear provenance, and tested before use. An outdated standard image can become a source of risk if it continues carrying obsolete packages or misaligned configurations.

## 2. Why Build Images via a Pipeline?

If every virtual machine is configured manually after creation, machines diverge over time: packages end up on different versions, one machine misses a patch, another accumulates undocumented manual edits. These differences complicate troubleshooting, scaling out machine counts, and incident recovery.

An image pipeline solves this by codifying and automating artifact creation steps. Identical inputs and identical tool versions produce an image with controlled contents. The output is tested, tagged with metadata, and published as a referenceable version.

Key benefits:

- **Consistency:** new machines created from the same image version share an equivalent foundation.
- **Reproducibility:** you can trace back the source code, base image, installed packages, and configurations used.
- **Security:** patching, hardening, and vulnerability scanning become mandatory gates in the workflow.
- **Deployment speed:** reduces manual post-boot configuration tasks.
- **Scalability:** autoscaling can launch additional machines from a tested image.
- **Recovery:** machines can be recreated from a published version or rolled back to a previous image when needed.
- **Auditability:** provides build history, test results, and the approver or approving system.

A pipeline does not eliminate startup configuration. Values that vary by environment such as service addresses, regions, cluster names, or application settings still need to be supplied via runtime configuration mechanisms.

## 3. Designing an Image Build Pipeline

A practical pipeline typically has the following stages:

~~~mermaid
flowchart TD
    A["Inputs<br/>Base image, config code, package versions"] --> B["Build image in isolated environment"]
    B --> C["Update and harden the OS"]
    C --> D["Boot and functional testing"]
    D --> E["Security scanning and compliance checks"]
    E --> F["Package metadata, SBOM, and provenance"]
    F --> G["Approve and publish immutable image"]
    G --> H["Distribute to regions/environments"]
    H --> I["Roll out new machines and monitor"]
    I --> J["Retire old versions per policy"]
~~~

### 3.1. Declaring Controlled Inputs

The pipeline should pull inputs from versioned sources:

- Explicitly selected base image by ID or digest if supported by the platform.
- OS configuration code and installation tooling managed in Git.
- Package lists or repositories from trusted sources.
- Pinned versions of Packer, image builders, plugins, and testing tools.
- Build configurations per environment or CPU architecture.

Never reference a base image label that always floats to the latest version without recording the exact ID used. Floating labels change over time, causing separate pipeline runs to produce different results.

### 3.2. Building in Ephemeral Environments

An image builder typically provisions a temporary VM or build environment, installs packages and applies configurations, and then captures the result into a new image. Tools like Packer can define build steps as code; several cloud providers also offer dedicated image builder services.

The build environment must operate under least privilege. The build account should only have permissions to read base images, create temporary resources, write artifacts to the target image registry, and emit necessary logs. Do not grant full cloud-account administrative rights if the pipeline only needs to build images within a specific scope.

Builds should run in an isolated environment with controlled networking and repositories. Temporary resources must be cleaned up whether the build succeeds or fails to avoid ongoing costs and orphaned unmanaged machines.

### 3.3. Installing and Configuring the Operating System

Configuration steps typically include:

1. Installing OS patches and package updates according to policy.
2. Installing cloud/guest agents, drivers, and required monitoring tools.
3. Installing base runtimes or dependencies if the organization manages them at the machine image layer.
4. Applying security configurations such as file permissions, allowed services, SSH/RDP policies, and host firewall rules.
5. Setting timezone, locale, logging, and time synchronization per organizational standards.
6. Clearing package caches, temporary files, shell history, and unnecessary build artifacts.
7. Preparing the image for first boot, such as allowing cloud-init or agents to apply per-instance configuration.

Never bake private keys, passwords, tokens, personal certificates, or production credentials into an image. Images can be copied, shared, or used to launch many machines; any secret baked into an image propagates to every copy. Provision secrets at runtime via a secret manager or an appropriately scoped workload identity mechanism.

### 3.4. Testing the Image

A build that merely succeeds is not automatically production-ready. Both bootability and post-provisioning machine behavior must be verified:

- The VM boots with the expected machine type and CPU architecture.
- The OS recognizes filesystems, network interfaces, and required devices correctly.
- Cloud/guest agents operate properly and the machine receives metadata configuration via the platform mechanism.
- SSH or RDP complies with policy; default accounts and access rights are verified.
- Background services start properly; no unnecessary daemons or open ports exist.
- Logging, monitoring, time synchronization, and update mechanisms function properly.
- Sample applications or management agents can be installed and run.
- Machines launched from the image do not retain build-machine state such as host keys, machine IDs, or credentials that should be uniquely generated.

Test across every OS, CPU architecture, and instance type the image will support. An x86-64 image will not automatically boot on Arm; an image for one OS line is not guaranteed compatible with every driver or machine type.

## 4. Security in the Image Creation Workflow

An image is the starting point for every machine launched from it. A security flaw in an image can be replicated across hundreds or thousands of instances, so security must be built into the pipeline.

### 4.1. Reducing the Attack Surface

- Choose a minimal base image with clear provenance and update cadence.
- Install only genuinely required packages, services, and ports.
- Remove unused packages, sample accounts, and unnecessary admin tools.
- Apply the principle of least privilege for users, service accounts, and files.
- Disable remote logins via unauthorized accounts or authentication methods.
- Configure logging, time synchronization, and event collection mechanisms.
- Configure the host firewall and protection policies suited to the machine's role.

Hardening must rely on an organization-approved baseline. Do not mechanically apply a single generic configuration to every workload type if it disables services needed by agents or applications. Exceptions must be documented and carry an expiration review date.

### 4.2. Vulnerability Scanning and Component Management

The pipeline can scan OS packages, libraries, kernels, and tools installed in the image. Findings should be evaluated by severity, exploitability, exposure, and available mitigations.

An **SBOM (Software Bill of Materials)** is an inventory of software components present in an artifact. An SBOM helps identify which images are affected when a new vulnerability is disclosed in a library or package. Store the SBOM alongside the image version and make it queryable during incident response.

Not all scan alerts carry equal risk. The pipeline needs clear policies defining which vulnerabilities block release, which require exception approval, and who owns remediation. Exceptions should document rationale, scope, approver, and expiration date.

### 4.3. Signing and Verifying Image Provenance

For systems with software supply chain assurance requirements, organizations can sign artifacts or release metadata and store build provenance. Provenance records source inputs, tooling, steps, and the pipeline identity that produced the artifact.

Before deployment, systems can verify signatures, release source, and trust policies. This helps detect tampered images or images produced by unauthorized pipelines. Exact signing and verification mechanisms depend on the artifact registry and cloud platform in use.

### 4.4. Preventing Secret Leakage in Logs and Images

The pipeline must avoid introducing credentials into:

- Configuration code or environment variable files committed to the repository.
- Build commands, command lines, or output logs.
- Temporary configuration files, shell history, and package caches.
- Snapshots, image metadata, or initialization scripts.

If a secret appears in an image or log, treat it as compromised: revoke or rotate the secret, assess the scope of affected artifacts, and build a new image after removing the data. Deleting a file in one filesystem layer does not guarantee the data has vanished from every layer or snapshot.

## 5. Declarative YAML Pipeline Example

The example below illustrates a provider-agnostic pipeline structure. Job names and commands are placeholders; replace them with the image builder, scanners, and APIs of the platform in use.

~~~yaml
stages:
  - validate
  - build
  - test
  - security
  - publish

variables:
  IMAGE_FAMILY: "linux-app-base"
  IMAGE_VERSION: "2026.11.22-1"

validate-definition:
  stage: validate
  script:
    - validate-image-definition
    - verify-pinned-base-image
    - check-no-secrets-in-source

build-image:
  stage: build
  needs: ["validate-definition"]
  script:
    - image-builder build --definition image.pkr.hcl
    - record-build-metadata
  artifacts:
    paths:
      - build-metadata.json

test-image:
  stage: test
  needs: ["build-image"]
  script:
    - launch-test-instance
    - verify-boot-and-agents
    - run-os-and-service-tests
    - destroy-test-instance

scan-image:
  stage: security
  needs: ["test-image"]
  script:
    - scan-image-vulnerabilities
    - generate-sbom
    - verify-hardening-policy

publish-image:
  stage: publish
  needs: ["scan-image"]
  rules:
    - if: '$RELEASE_APPROVED == "true"'
  script:
    - sign-image-and-metadata
    - publish-immutable-image
    - record-image-id-and-digest
~~~

In a real pipeline, build metadata should record at least the base image ID/digest, OS version, build tool versions, configuration commit, package manifest, build timestamp, test results, SBOM, and published image ID.

The pipeline must halt if input checks, build, boot tests, or security policies fail. Only the publish stage should have write permissions to the shared image registry; test environments should use ephemeral artifacts or an isolated registry.

## 6. Image Version Management

Every published image must have a unique, traceable identifier. Do not rely solely on human-friendly names like latest or stable because labels can be reassigned to a different artifact.

### 6.1. Versioning Conventions

A convention can combine image family, operating system, architecture, base version, and build date:

~~~text
linux-app-base-ubuntu24-arm64-2026.11.22-1
~~~

The segments can denote:

- Role or image family: linux-app-base.
- Operating system and version: ubuntu24.
- Architecture: arm64.
- Release date: 2026.11.22.
- Build sequence number for that day: 1.

The convention must be consistent and must never contain secrets or sensitive data. Human-readable names aid people; deployment systems should record the platform-assigned immutable ID or digest.

### 6.2. Distinguishing Version, ID, and Alias

| Identifier | Purpose | How It Is Used |
| --- | --- | --- |
| Version | Organization-assigned release version | Tracking releases and communicating across teams |
| Image ID | Platform artifact identifier | Referencing the exact image when creating machines |
| Digest/checksum | Content verification fingerprint if supported | Verifying the artifact has not been altered |
| Alias/channel | Labels like stable, candidate, or production | Resolving versions by release channel |

Aliases are convenient for users, but their targets can change. Reproducible deployments should record the exact Image ID or digest alongside deployment configuration.

### 6.3. Immutable Images

Once published, image contents should be treated as immutable. If packages, patches, or base settings need changes, build a new version. Modifying an image already referenced in place makes it impossible to know exactly what contents new machines are built from.

This model supports change control: older versions remain usable for reproducing environments during the retention period, while new versions pass through the full pipeline and approval gates.

## 7. Image Distribution and Deployment

After publication, an image may need to be copied across different regions, accounts, or environments. The distribution process should verify that destination artifacts match the source, sharing permissions have the right scope, and replication has completed before deployment.

A controlled rollout typically includes:

1. Deploying the new image into a test environment or a small group of machines.
2. Checking boot time, health checks, logs, network connectivity, and application behavior.
3. Expanding to a canary group or a fraction of traffic.
4. Monitoring startup errors, latency, CPU/RAM, agents, and OS events.
5. Gradually expanding to the entire machine group once metrics meet criteria.
6. Halting the rollout and reverting to the previous version if error thresholds are exceeded.

For autoscaling groups or managed instance groups, update the template or launch configuration to reference the new image ID. Existing machines can continue running the old image until replaced via a rolling replacement strategy or maintenance schedule.

Do not delete older images immediately after releasing a new version. Retain enough versions to support rollbacks, incident investigation, and audit compliance.

## 8. Updating and Patching Images

Operating systems and packages continuously receive security patches, bug fixes, and compatibility updates. Images therefore need a periodic rebuild schedule as well as an emergency patching workflow.

### 8.1. Rebuilding Instead of Patching Individual Machines

Under the immutable image model, when a patch is available:

1. Update the base image or approved package list.
2. Run the pipeline to build a new image version.
3. Scan for vulnerabilities and verify configuration.
4. Test boot, agents, and applications.
5. Approve, publish, and roll out.
6. Replace machines running the older version according to policy.

Patching a running machine directly is sometimes necessary in emergencies, but that state must be fed back into configuration code and the pipeline. Otherwise, the machine drifts from the standard image and risks losing the fix when replaced.

### 8.2. Update Policy

Organizations should define:

- Periodic rebuild cadence by OS and criticality.
- Vulnerability remediation deadlines by severity and exploitability.
- Handling of kernel patches requiring reboots.
- Testing and approval timelines for emergency cases.
- Notification and replacement procedures for images approaching end of support.
- Handling of applications requiring specific OS or runtime versions.

Do not enforce one rigid cadence across all images if risk profiles differ. Internet-facing images or those processing sensitive data may need stricter update and validation schedules.

## 9. Lifecycle Management and Version Cleanup

Image registries can accumulate numerous versions, failed builds, test images, and unused images. Without a lifecycle policy, finding trusted versions becomes difficult and storage costs grow.

A lifecycle policy should define:

- **Status:** draft, candidate, approved, deprecated, or retired.
- **Owner:** team responsible for updates and vulnerability remediation.
- **Creation date and review expiration date:** establishes artifact age and review schedule.
- **Usage scope:** permitted environments, accounts, regions, and architectures.
- **Replacement version:** explicitly indicates which new image supersedes an older one.
- **Retention period:** sufficient for rollback and auditing per organizational policy.
- **Deletion criteria:** no workloads referencing it, retention period elapsed, and required approvals obtained.

Before deleting an image, check whether launch templates, autoscaling groups, pipelines, recovery environments, or other accounts still reference it. Deleting an image can break new machine creation or environment recovery even if existing machines launched from it continue running.

## 10. Example: Releasing a New Linux Image

An operations team maintains a standard image for virtual machines running Java services. The current image includes Linux, cloud agent, JDK, and monitoring agent. The team needs to apply security patches and upgrade the JDK on a scheduled release.

The team executes the following steps:

1. Selects an approved base image and records its exact ID.
2. Updates configuration code for OS packages, JDK, and agents.
3. Runs the pipeline inside a least-privilege build account.
4. Scans packages, generates an SBOM, and verifies no credentials exist in the image.
5. Launches a test machine from the new image, verifying boot, SSH, logging, agents, and a sample application.
6. Records the version, Image ID, digest, configuration commit, and test results.
7. Publishes the new version to the candidate channel, rolls out a canary, and then expands.
8. Monitors boot errors, readiness time, p95/p99 latency, and OS logs.
9. Switches the production alias to the approved version while retaining the prior image throughout the rollback window.

If the canary exhibits compatibility errors, the team halts the rollout and reverts machine launch configs back to the previous Image ID. The new image remains in candidate status for investigation; after fixing, the pipeline must build and test a fresh artifact.

## 11. Points to Watch for Windows and Linux

The general workflow applies to both operating systems, though image preparation steps differ.

| Aspect | Linux | Windows |
| --- | --- | --- |
| Initialization tools | cloud-init or guest agent depending on platform | Sysprep and provider guest agent/tools depending on platform |
| Machine identity | Must handle machine ID, host keys, and init state | Must handle SID, hostname, and specialize state via supported process |
| Updates | Package manager and kernel updates | Windows Update, servicing stack, and driver updates |
| Administrative access | SSH and sudo per policy | RDP, administrative accounts, and domain policies |
| Testing | systemd/services, filesystems, networking, agents | Boot, Windows services, drivers, activation, and agents |

Do not clone an already-initialized Windows image while skipping the appropriate generalize/specialize process. On Linux, ensure unique identifiers are regenerated at the right time and build-machine host keys or machine IDs are never carried over to new machines.

Licensing, activation, and OS usage rights requirements must also be verified according to image type and provider agreements.

## 12. Common Mistakes

- Installing an image manually on one machine and capturing it without saving the procedure.
- Using floating base image or package tags without recording input IDs.
- Baking credentials, SSH private keys, or tokens into the image.
- Checking only that the build succeeded without booting a machine from the image.
- Failing to verify compatibility across CPU architectures or instance types.
- Updating production machines directly without updating configuration code.
- Using a mutable alias as the sole identifier in deployments requiring reproducibility.
- Failing to retain SBOMs, metadata, scan results, and build history.
- Deleting old images before verifying no workloads reference them.
- Lacking a rollback procedure or failing to test images before broad rollout.
- Leaving standard images unupdated for long periods, accumulating patch debt.

## 13. Recommended Operating Workflow

1. **Manage configuration as code:** store image definitions, install scripts, and hardening policies in version control.
2. **Pin inputs:** fix base images, packages, builders, and plugins to specific versions or IDs.
3. **Controlled builds:** run in ephemeral environments with least privilege and traceable logs.
4. **Multi-layer testing:** verify boot, OS, agents, networking, security, and sample applications.
5. **Supply chain governance:** generate SBOMs, record provenance, and sign and verify artifacts if required by policy.
6. **Immutable releases:** assign unique versions and Image IDs; never modify published image contents.
7. **Phased rollouts:** canary, monitor health, and expand when criteria are satisfied.
8. **Maintain and retire:** rebuild when patches arrive, mark deprecated, and delete versions per policy.
9. **Test recovery capability:** periodically test launching machines from both the active image and the rollback version.

Building images via pipelines transforms virtual machine configuration into a testable, traceable, and releasable artifact. Combining immutable images with version management, security checks, and controlled rollouts enables engineering teams to deliver consistent compute capacity, reduce configuration drift, and recover faster when changes cause faults.
