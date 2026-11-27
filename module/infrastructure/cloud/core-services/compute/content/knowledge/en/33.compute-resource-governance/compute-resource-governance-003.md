# Policies for Restricting Allowed Regions, Machine Types, and Image Sources

In a cloud environment, users can create virtual machines across many regions, pick from numerous machine types, and launch from various image sources. Without governance policies, a workload could be deployed in a region that violates data requirements, use a machine type that blows past its budget, or boot from an unvetted image.

Policies restricting allowed regions, machine types, and image sources establish safe boundaries for compute provisioning. Region allowlists dictate where workloads may run; machine type policies limit families, sizes, architectures, and accelerators; image source policies permit only images from trusted publishers or registries. Policies must be centrally managed, checked in Infrastructure as Code (IaC), enforced at the control plane, and continuously monitored.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, chapter **Compute Resource Governance**. It focuses on designing allowlists and deny-by-default rules, applying policies across organizations/projects/subscriptions, controlling regions, machine types, and images, managing exceptions, auditing violations, and safely rolling out policy-as-code.

## 1. Why Restrict Compute Resources?

Permission to create a VM or node typically lets users select multiple attributes that directly impact security, cost, and compliance:

- Region and zone determine data location, latency, resilience, and where costs accrue.
- Machine type determines CPU, RAM, GPU, network performance, architecture, and unit price.
- Image source determines the OS, packages, agents, security settings, and pre-installed software at boot.

A user may hold legitimate VM-creation permissions yet still pick a configuration violating corporate policy—for example, deploying a workload handling sensitive data in an unapproved region, spinning up an expensive GPU instance for a service that needs no accelerator, or booting from an unverified public image.

### 1.1. Three Risk Groups

| Group | Risk | Consequence |
|---|---|---|
| Region | Data or workload in an unapproved location | Residency violations, increased latency, difficulty meeting legal requirements |
| Machine type | Using an unsuitable or disallowed family/size/GPU | Budget overruns, quota exhaustion, expanded attack surface |
| Image source | Unverified, outdated, vulnerable, or tampered image | System compromise, inconsistent configuration, poor traceability |

Policies must block risky selections right before resources are created, while also detecting existing resources that are no longer compliant.

### 1.2. Governance Does Not Replace Workload Design

Policies can constrain allowed options, but they do not automatically pick the optimal configuration for an application. Workload teams still must determine CPU/RAM, storage, networking, HA, and expected cost. Governance sets guardrails so choices stay within the organization's acceptable range.

## 2. Policy Design Principles

A good policy must be understandable, testable, owned, and backed by a clear exception process.

### 2.1. Allowlists and Deny-by-Default

An allowlist explicitly specifies permitted regions, machine types, or image sources. Values outside the list are denied by default or require approval.

Conceptual policy example:

~~~yaml
computeGovernance:
  allowedRegions:
    - ap-southeast-1
    - ap-southeast-2
  allowedMachineTypes:
    - general-purpose.small
    - general-purpose.medium
    - memory-optimized.large
  allowedImageSources:
    - project: platform-golden-images
    - registry: registry.example.internal
~~~

This YAML illustrates an internal policy model, not a direct schema for AWS, Azure, Google Cloud, or Kubernetes. When implementing, translate rules into the policy language and resource fields supported by your actual platform.

Deny-by-default fits high-risk resources, provided allowlists are actively maintained. If an allowlist is too narrow or stale, development teams may be blocked from deploying legitimate workloads.

### 2.2. Least Privilege and Separation of Duties

- Workload users may only create resources within approved boundaries.
- Platform/security teams own organization policies and trusted source lists.
- Application teams propose region, machine type, and image needs.
- Operations teams verify quotas, capacity, backups, and supportability.
- Exception approvers should not self-approve their own changes in high-risk cases.

### 2.3. Policies Must Have Owners and Review Schedules

Each policy should have an owner, objective, scope, effective date, version, rationale, and review schedule. Machine type or image source lists must be updated when platforms deprecate offerings, change pricing, or uncover security risks.

## 3. Policy Layers and Inheritance Scopes

Clouds typically use hierarchical governance structures. Names vary across providers, but models generally comprise an organization, folders/groups, accounts/subscriptions/projects, and resources.

~~~mermaid
flowchart TD
    O["Organization policy baseline"] --> F["Folder / Management group"]
    F --> P["Account / Subscription / Project"]
    P --> R["Resource group / VPC / Cluster"]
    R --> W["VM / Node / Instance"]
    O --> G["Central policy repository"]
    G --> C["CI policy checks"]
    G --> A["Audit and compliance"]
~~~

### 3.1. Organization-Level Baseline

Sets universal boundaries every workload must satisfy:

- Allow only organization-approved regions.
- Prohibit or restrict high-risk machine families.
- Allow only images from trusted sources.
- Require owner, environment, and cost-center tags.
- Prohibit insecure settings such as public IPs or disabled disk encryption when mandated by policy.

Baselines should be stable, clearly scoped, and free of one-off exceptions meant for a single application.

### 3.2. Policies by Workload Group

Workload groups may need distinct profiles:

| Group | Region | Machine type | Image |
|---|---|---|---|
| Production | Only regions approved for the data | Tested production families | Production golden images |
| Development | Approved sandbox regions | Small/general-purpose | Development golden images |
| HPC/AI | Regions with capacity and suitable accelerators | Approved GPU/HPC families | HPC/AI images with verified drivers |
| Regulated | Regions per residency rules | Certified and controlled SKUs | Images with baseline and compliance evidence |

Group-level policies can add stricter limits atop the baseline, but must not widen permissions beyond organizational boundaries unless the provider's policy mechanism explicitly permits it.

### 3.3. Precedence and Conflicts

Some systems enforce that deny always overrides allow; others have specific inheritance, override, or exemption rules. Do not assume all providers resolve policy conflicts identically.

When designing, answer:

- Can organization-level policies be overridden by lower scopes?
- Does deny always override allow?
- Who must approve exemptions?
- Are policies evaluated at create time, update time, or continuously at runtime?
- How are existing resources affected when a new policy is enabled?

Write tests for inheritance and conflict cases before enforcing in production.

## 4. Region Restriction Policies

Region policies specify the geographic locations where compute resources may be created or moved. The region list should reflect data, legal, security, latency, disaster recovery, and service availability requirements.

### 4.1. Region Selection Criteria

- **Data residency:** data must be stored and processed within permitted jurisdictions.
- **Regulatory scope:** legal, contractual, or industry standard mandates.
- **Latency:** proximity to users, databases, and integrated systems.
- **Availability:** zone count, services, and actual capacity.
- **Disaster recovery:** standby regions and cross-region recovery capability.
- **Cost:** compute, storage, network egress, and licensing rates.
- **Service parity:** availability of machine families, GPUs, managed services, and features.

Do not pick regions solely by VM price. Egress, replication, data transfer, and missing machine types can drive total cost higher.

### 4.2. Region Allowlists

Allowlists should use official region codes rather than free-form display names. Region codes must be verified against the provider and deployment environment.

Example:

~~~yaml
policy:
  name: allowed-compute-regions
  effect: deny
  when:
    resource.type: virtual-machine
    resource.region:
      notIn:
        - ap-southeast-1
        - ap-southeast-2
  message: "Compute resource region is not approved"
~~~

This is pseudocode. Syntax like `notIn`, `resource.type`, and `effect` must be translated into the actual policy language of your target platform.

### 4.3. Scope of Application

Region policies must cover related resource types, not just VMs:

- VMs, managed instance groups, and autoscaling groups.
- Disks, snapshots, and images.
- GPU/accelerator instances.
- Kubernetes node pools.
- Backups, replicas, and artifact storage.
- Resources created indirectly by managed services.

If you block VMs yet allow disks or snapshots to be created in another region, data can still leave approved boundaries.

### 4.4. Regions and Zones

A region comprises one or more availability zones. Policies may allow a region while still restricting zones or topologies for workloads with special needs.

For instance, a block volume may be bound to a specific zone; a workload running in another zone cannot attach it directly. Policies must align region, zone, placement, and HA capabilities to avoid configurations that are region-compliant yet unworkable.

### 4.5. Regions for Disaster Recovery

DR regions must be pre-approved before an incident occurs. If only the primary region is permitted, operations teams may be blocked from provisioning compute in a standby region during an emergency.

The DR catalog should specify primary and standby regions, workload types allowed to fail over, which data is replicated, resource-creation permissions during DR, and how emergency permissions are logged and expired.

## 5. Machine Type Restriction Policies

Machine types define virtual hardware profiles or node profiles: CPU, RAM, GPU, local storage, network bandwidth, architecture, and performance characteristics. Policies must constrain both family and size appropriately per environment.

### 5.1. Allowlists by Family and Size

A machine type allowlist may restrict:

- General-purpose for web/API workloads.
- Compute-optimized for CPU-bound workloads.
- Memory-optimized for databases or in-memory analytics.
- Storage-optimized for I/O-intensive workloads.
- GPU/accelerator families for HPC/AI.
- Arm or x86 architectures based on compatibility.

Do not allow an entire family without size limits. A single family can include massive, very expensive sizes.

### 5.2. Policy Example by Environment

~~~yaml
machineProfiles:
  development:
    allowedFamilies:
      - general-purpose
    maxVcpu: 8
    maxMemoryGiB: 32
    accelerators: forbidden
  production:
    allowedFamilies:
      - general-purpose
      - compute-optimized
      - memory-optimized
    allowedSizes:
      - general-purpose.medium
      - compute-optimized.large
      - memory-optimized.large
  hpc:
    allowedFamilies:
      - hpc
      - gpu-accelerated
    requireApproval: true
~~~

This is an illustrative internal schema. Family and size names must map to actual provider machine SKUs. `maxVcpu` and `maxMemoryGiB` are supplemental conditions, not replacements for SKU allowlists.

### 5.3. Attribute-Based Limits

Beyond machine names, policies can check maximum or minimum vCPUs, min/max RAM and RAM-to-vCPU ratios, CPU architecture, GPU count or accelerator model, local NVMe or ephemeral disks, network performance tiers, confidential computing capabilities, and licensing/software requirements.

Attribute-based limits help when providers introduce new SKUs. However, overly broad rules may inadvertently permit untested machine types. Combine family/SKU allowlists with attribute limits.

### 5.4. GPU and Accelerator Limits

GPU instances typically have distinct pricing, quotas, drivers, and image dependencies. Policies should require that the workload/project carry an approved AI/HPC designation, the GPU model be on the allowlist, the region have capacity and driver support, the image include vetted drivers/runtimes, budgets/quotas align, and an accountable owner be assigned.

Never provision GPUs solely on self-declared requests without an owner, workload profile, or cost center.

### 5.5. Quotas vs. Policies

Quotas cap the quantity of resources provisioned within an account/project/region. Policies define which resource types are permitted. A machine type may be on the allowlist yet fail creation due to exhausted quota; conversely, quota may be available while policy denies that SKU.

Track separately:

- Allowed by policy.
- Available by quota.
- Available capacity in region/zone.
- Approved by budget.

## 6. Allowed Image Source Policies

Images contain the OS, packages, agents, runtimes, and initial configuration of a machine. Image sources affect reliability, patchability, traceability, and consistency.

Sources may include golden images built by the platform team, cloud-provider-published images, marketplace images from approved publishers, custom images from internal pipelines, container images from private registries, or images from public registries/external accounts/projects.

Not every public image is malicious, but users should not arbitrarily choose unverified sources in production environments.

### 6.1. Golden Images

A golden image is a standardized image vetted by the organization. It typically includes an OS version and package baseline, applied security patches, endpoint protection/monitoring agents, logging and configuration management agents, hardening settings, CA certificates and trust configuration, and metadata for build and owner traceability.

Golden images must be rebuilt periodically, tested, and replaced when an OS reaches end-of-support or a critical vulnerability emerges.

### 6.2. Allowlists by Publisher, Project, or Registry

For VM images, policies can permit images published by the provider or internal projects, or allow only pre-approved image IDs/versions.

For container images, policies can restrict registries, repositories, namespaces, and digests. Do not rely solely on tags like `latest` or `production` because tags can be moved to different contents.

### 6.3. Image IDs and Immutable Digests

An image ID/version or digest identifies specific image contents. A strong policy may require that the image ID appear on an approved list, the image owner/publisher belong to a trusted list, container images be referenced by digest, image signatures be valid from a trusted issuer, and provenance tie the artifact to its originating pipeline/build identity.

Digests guarantee references to specific contents, but do not prove an image is secure. Scanning, signature verification, and reviews remain necessary.

### 6.4. Public and Marketplace Images

If marketplace images are allowed, approve the publisher, licensing, support lifecycle, and update mechanism. A marketplace image may include hourly-billed software or special licensing; image source policies must coordinate with cost governance.

Public images can be deleted, modified, or stop receiving updates. Mirror or import approved images into an internal repository if the organization requires retention control and reproducible deployments.

### 6.5. VM Images and Container Images Have Different Controls

VM images are typically controlled via image ID, owner/project, publisher, version, or gallery/catalog. Container images are typically controlled via registry, repository, tag/digest, signature, and admission policy.

Do not use a registry allowlist rule as a substitute for VM image controls. Both artifact types have distinct metadata and lifecycles.

## 7. Policy Enforcement Across Cloud Platforms

Providers offer distinct policy services, yet the shared goal is evaluating create or update requests before operations are accepted.

| Platform | Common Mechanisms | Scope Examples |
|---|---|---|
| AWS | Organizations Service Control Policies (SCP), IAM condition keys, AWS Config, and Control Tower controls | Region restrictions, EC2 creation rights, image owner/ID via supported conditions |
| Microsoft Azure | Azure Policy, management groups, policy initiatives, and exemptions | Allowed locations, VM SKUs, image publisher/offer/SKU via policy definitions |
| Google Cloud | Organization Policy, IAM, custom constraints where supported, and Policy Intelligence | Resource locations, restricting compute attributes via appropriate constraints |
| Kubernetes | Admission controllers, ValidatingAdmissionPolicy, Gatekeeper, or Kyverno | Registry/repository, image digest/signature, workload policies, and node placement |

Exact service names and constraints depend on the provider, resource type, API version, and subscription/project type. Before deploying, check current official documentation to verify supported fields, inheritance behavior, and deny/audit/exemption semantics.

### 7.1. AWS

AWS Organizations SCPs can set maximum permission boundaries for member accounts. SCPs do not grant IAM permissions by themselves; IAM identity policies must still allow the action. Region guardrails often rely on request context keys like `aws:RequestedRegion`, though exceptions must be designed for global services or control-plane APIs with special behavior.

For EC2 images, IAM permissions and appropriate conditions can restrict image IDs/owners on APIs/actions that support the corresponding condition keys. Verify each action and condition key before assuming a condition applies across every instance creation path, launch template, or autoscaling flow.

### 7.2. Azure

Azure Policy can be assigned at management groups, subscriptions, or resource groups. Built-in policies can check allowed locations or allowed virtual machine SKUs; custom policies can inspect image properties where corresponding aliases are supported.

Effects such as `Deny`, `Audit`, `Modify`, or `DeployIfNotExists` behave differently. `Deny` blocks non-compliant requests; `Audit` logs violations; `Modify`/`DeployIfNotExists` can alter or deploy supplemental configurations when permissions and resource types align. Never treat `Audit` as if it were blocking resource creation.

### 7.3. Google Cloud

Organization Policy provides constraints at the organization, folder, or project level. Appropriate location constraints can restrict where resources are created. For machine types and images, determine whether managed constraints or custom constraints support the specific resource/API; do not assume every Compute Engine field has a matching built-in constraint.

If a policy cannot inspect an attribute directly, combine IAM, custom pipeline validation, service perimeters, or inventory checks. Do not treat a location rule as sufficient to govern images or machine SKUs.

### 7.4. Kubernetes and Node Images

Kubernetes admission policies can block Pods using container images outside approved registries or lacking digests. However, Pod admission policies do not control the underlying VM node image or images used by cloud autoscaling groups.

Node pools must be governed at the cloud/IaC layer and use approved node images. Workload admission and node image governance are two separate layers.

## 8. Policy-as-Code and Pre-Deployment Checks

Policy-as-code stores rules as versioned, reviewed, and tested source code. This enables platform teams to update allowlists in a controlled way and reuse rules across environments.

### 8.1. Policy-as-Code Workflow

~~~mermaid
flowchart TD
    A["Policy source in Git"] --> B["Pull request review"]
    B --> C["Unit tests / policy tests"]
    C --> D["IaC plan validation"]
    D --> E["Deploy policy in audit mode"]
    E --> F["Review violations and impact"]
    F --> G["Enforce deny"]
    G --> H["Continuous compliance scan"]
    H --> I["Remediate or approved exception"]
~~~

Policies need both positive and negative tests:

- Regions on the allowlist must be accepted.
- Regions off the allowlist must be denied.
- Approved machine SKUs must be accepted.
- Prohibited GPU SKUs in development must be denied.
- Images from trusted registries must pass.
- Images from untrusted registries or mutable tags must be denied when policy requires digests.

### 8.2. Pull Request Checks

IaC plans should be checked before apply. Policy tests can inspect resource plans and verify region, machine type, image source, and mandatory tags.

Pseudocode rule example:

~~~text
deny if vm.region not in approved_regions
deny if vm.machine_type not in approved_machine_types
deny if vm.image_id not in approved_vm_images
deny if container.image_registry not in approved_registries
deny if production and container.image_reference is not digest
~~~

This is illustrative logic, not Rego, CEL, or Azure Policy syntax. When using OPA/Rego, Sentinel, Terraform policy checks, or Azure Policy, write tests matching the exact schema of your chosen tool.

### 8.3. Plan and Runtime May Differ

IaC validation inspects pre-deployment intent. Resources can still be created outside pipelines via console, CLI, or API if the control plane does not enforce policies. Therefore, IaC checks must be paired with organization-level guardrails and inventory scans.

## 9. Enforcing at Create and Update Time

Preventive controls block requests before resources are created. This is the most critical layer for stopping misconfigurations from entering the environment.

Control points:

- Cloud API authorization/policy evaluation.
- Launch template or instance template validation.
- Managed node group/node pool configuration.
- IaC plans and deployment pipelines.
- Kubernetes admission requests.
- Registry pull policies or image verification.

### 9.1. Create and Update

Policies must evaluate both create and update operations. A VM compliant yesterday can have its machine type resized or its image swapped today. An autoscaling template can be updated to launch new instances with non-allowlisted SKUs or images.

Check VM/instance creation, machine size/type updates, image or launch template changes, node pool/autoscaling group creation, snapshot restores or new image creation, image cloning/importing, and container image updates in workload specs.

### 9.2. Indirectly Created Resources

Managed services can create VMs or nodes on a user's behalf. If you only check direct VM creation calls, indirectly provisioned resources can bypass policy.

Identify service principals and API paths capable of creating compute, then verify whether policies apply to the resulting resources. Examples include managed Kubernetes node pools, managed batch, autoscaling, image builders, and deployment services.

## 10. Admission Control for Container Images

In Kubernetes, admission control inspects object create or update requests before the API server persists them. It can restrict registries and enforce immutable image references.

Illustrative `ValidatingAdmissionPolicy` example for a registry allowlist:

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: approved-image-registries
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: "object.spec.containers.all(c, c.image.startsWith('registry.example.internal/'))"
      message: "Container images must come from the approved registry"
~~~

The example above only illustrates checking the main `containers` list. Production policies must also check `initContainers` and `ephemeralContainers`, handle exact registry hostnames/ports, prevent bypasses using equivalent name forms, and create a `ValidatingAdmissionPolicyBinding` for the policy to take effect. Verify that your Kubernetes version supports this API.

### 10.1. Requiring Digests

An image reference using a tag can change contents:

~~~text
registry.example.internal/payments/api:stable
~~~

A digest reference pins specific contents:

~~~text
registry.example.internal/payments/api@sha256:0123456789abcdef...
~~~

The sample digest is an illustrative string, not a valid deployment digest. Production policies should validate digest format and, where needed, verify signatures/provenance via admission integrations.

### 10.2. Checking Init Containers and Sidecars

Do not inspect only `containers`. Pods may contain `initContainers`, sidecars injected by mutating webhooks, or `ephemeralContainers` added for debugging. Policies need strategies for each:

- Init containers must use approved registries and images.
- Sidecar injection must originate from governed controllers/webhooks.
- Ephemeral containers can be restricted or require dedicated debugging permissions.
- Image pull secrets must come from a secret manager or appropriate credential management mechanism.

### 10.3. Signatures and Provenance

A registry allowlist only verifies where an image is stored, not who built it or whether its contents passed checks. For production workloads, you may require valid signatures from a trusted CI identity, provenance linking the image digest to source commits and build workflows, an SBOM attached to the digest, vulnerability scans meeting policy thresholds, and confirmation the image is not revoked or flagged compromised.

Admission controllers or deployment pipelines must verify this evidence. Never trust a self-declared annotation claiming an image was scanned without an underlying verification system.

## 11. Audit, Enforce, and Remediation

Do not enable broad `deny` enforcement right after writing a policy. A rule may be right in intent yet wrong on a field name, miss an API path, or disrupt legitimate running workloads.

### 11.1. Audit Mode Before Enforcement

Roll out in phases:

1. Collect current inventory.
2. Author policies and test allow/deny cases.
3. Enable audit or report-only mode if supported by the platform.
4. Measure how many resources would be impacted.
5. Identify owners and dependent workloads.
6. Remediate resources or grant time-bound exceptions.
7. Enable `deny` on a small scope.
8. Expand gradually after confirming no severe false positives.

Audit mode does not block operations. During this period, restrict who can create resources and monitor violations so an unenforced policy is not mistaken for active protection.

### 11.2. Preventive, Detective, and Corrective Controls

| Control Type | Objective | Example |
|---|---|---|
| Preventive | Block misconfigurations before creation | SCP, Azure Policy Deny, admission policies |
| Detective | Detect non-compliant resources | Cloud inventory, Config, Policy compliance scans |
| Corrective | Bring resources back into compliance | Resize, region migration, image rebuild, quarantine |

A governance system needs all three. Preventive controls alone miss legacy resources or unguarded service paths; detective controls alone allow violations to linger long before remediation.

### 11.3. Handling Violating Resources

When detected:

- Identify resource ID, owner, environment, and dependent workloads.
- Classify risk severity and associated data.
- Block further creation or modification if needed.
- Plan tested migration/resize/rebuild steps.
- Verify backups, snapshots, and rollback paths.
- Confirm post-remediation compliance.
- Record timestamp, handler, and evidence.

Do not auto-delete VMs or disks holding critical data simply because a new policy flagged an unapproved region or machine type. Prioritize safe containment and owner-led remediation.

## 12. Controlled Exception Management

Some workloads have valid needs outside the allowlist—such as a new GPU model for research, a DR region during exercises, or a vendor image not yet added to golden images. Exceptions need a dedicated process that is scoped and time-bound.

### 12.1. Contents of an Exception Request

An exception request should specify the workload, project/account/subscription and owner, requested region/machine SKU/image source, technical/business justification, data involved and sensitivity level, risks and compensating controls, start and expiration dates, platform/security/cost approvers, and a plan to return to the baseline.

### 12.2. Narrowly Scoped Exceptions

Do not widen the organization-wide allowlist just to accommodate one project. Scope exceptions to a specific project, resource group, principal, tag, image digest, or timeframe where supported by the platform.

Example:

~~~yaml
exception:
  id: EXC-2026-041
  scope:
    project: hpc-research
    workload: climate-model
  allow:
    region:
      - approved-dr-region
    machineType:
      - gpu-research-approved
    imageDigest:
      - sha256:approved-digest-placeholder
  owner: research-platform
  approver: cloud-security
  expiresAt: 2026-12-31
  compensatingControls:
    - isolated-network
    - enhanced-monitoring
    - weekly-image-review
~~~

This is an illustrative schema. The placeholder digest is not a deployable value. Exceptions must be checked automatically upon expiration and never expanded beyond the approved request.

### 12.3. Emergency Break-Glass

During an incident, break-glass responders may need to provision compute in regions or machine types outside the baseline. This mechanism must use dedicated identities, MFA, and restricted permissions; require an incident/ticket ID; be short-lived and fully audited; alert security/platform teams; expire automatically or be revoked after the incident; and undergo a post-incident review to bring resources back to baseline.

Break-glass should never become a routine role or a permanent policy exemption.

## 13. Image Lifecycle Management

An image approved today may become insecure within months. Image source policies must tie into the lifecycle from build through deprecation.

### 13.1. Golden Image Workflow

~~~mermaid
flowchart TD
    A["Approved base image"] --> B["Patch and harden"]
    B --> C["Install required agents"]
    C --> D["Scan and test"]
    D --> E["Sign and publish"]
    E --> F["Add to approved catalog"]
    F --> G["Deploy to canary"]
    G --> H["Promote to production"]
    H --> I["Monitor CVE and support lifecycle"]
    I --> J["Rebuild or deprecate"]
~~~

### 13.2. Image Freshness

Policies should define maximum age or refresh cadences for images based on risk. Stale images can contain unsupported packages, vulnerable kernels, or expired certificates.

Signals to track: OS/vendor end-of-support dates, security patch age, critical/high CVEs, agent versions, image build timestamps, signature and provenance status, and active owners and workloads.

Do not check only the image source. An image from a trusted registry can still be outdated or vulnerable.

### 13.3. Deprecation and Revocation

When an image is revoked:

1. Mark the image/digest disallowed for new deployments.
2. Locate all VMs, launch templates, node pools, and workloads using it.
3. Assess exploitability and urgency.
4. Build a replacement image and run compatibility tests.
5. Roll out via groups/canary.
6. Verify no workloads remain on the old image.
7. Revoke pull permissions or delete according to retention policy.

For images suspected of compromise, you may need to quarantine the registry repository or block the digest immediately while planning recovery for running workloads.

### 13.4. Do Not Mutate Deployed Tags

Do not move a `production` tag to a new image without a versioning workflow. Deployment records must capture the actual digest. If a tag is updated, teams must know which workloads still run the old digest and which have moved to the new digest.

## 14. Machine Type Governance and Capacity Planning

Machine type allowlists must balance security, cost, and provisioning feasibility. A SKU allowed by governance that lacks capacity in a region/zone will still cause deployment failures.

### 14.1. Machine Type Catalog

Maintain a catalog containing:

| Field | Meaning |
|---|---|
| Provider/SKU | Exact machine type name |
| Family/profile | General, compute, memory, storage, GPU/HPC |
| vCPU/RAM | CPU and memory capacity |
| Architecture | x86-64, Arm, or other |
| Accelerator | GPU model/count if applicable |
| Network | Bandwidth or tier |
| Region availability | Supported regions/zones |
| Cost tier | Cost group or reference price |
| Approved workload | Permitted workload types |
| Lifecycle | Current, deprecated, or restricted |

Sync the catalog with inventory/provider APIs or review periodically to detect new SKUs, deprecated SKUs, and regional availability differences.

### 14.2. Avoid Overly Broad Wildcards

Rules allowing every machine type matching a family prefix can automatically grant access to new SKUs upon provider release. Before testing, new SKUs may carry high pricing, different architectures, or different networking behavior.

Prefer exact SKU allowlists for production. If wildcards are needed, pair them with vCPU/RAM/accelerator/cost-tier limits and a review process for new SKUs.

### 14.3. Machine Types and Quotas

After policy accepts a SKU, systems still must check quotas and capacity. Track vCPU quotas by region/family, GPU quotas by accelerator, zonal capacity, reservations or committed capacity, subscription/project limits, and per-core/GPU licensing limits.

A policy may permit a SKU without guaranteeing the provider has available capacity at creation time.

### 14.4. Resizing and Migration

Changing machine types may require stopping/deallocating, modifying disks/networks, or restarting. Not every instance can resize directly across families or architectures.

Before remediating a non-allowlisted VM, verify architecture and OS compatibility, driver/accelerator dependencies, disk and network attachments, downtime and HA impact, licensing and quotas, and a rollback plan.

## 15. Region Policies and Associated Data

Region restrictions are not only about where compute runs. Data can be copied or processed across other services during provisioning and operations.

### 15.1. Data Paths to Review

- Boot disks and data disks.
- Snapshots and backups.
- Custom VM images and image replication.
- Object storage holding inputs/outputs.
- Logs, telemetry, and crash dumps.
- Container registries and artifact caches.
- KMS/HSM keys and secret stores.
- Database replicas and message queues.

A VM running in an approved region that writes logs or snapshots to an unapproved region can still violate residency requirements.

### 15.2. Region Pinning and Disaster Recovery

Region pinning keeps workloads inside approved boundaries but can constrain failover options. Pre-approve DR regions and define how data will be replicated.

If a DR region is not permitted for certain data, you may need encrypted backups, tokenization, synthetic data, or recovery procedures executed only after approval. Never replicate sensitive data across borders automatically.

## 16. Inventory and Continuous Compliance

Policies remain effective long-term only when the organization knows what resources exist. Inventory should capture region, zone, machine SKU, image ID/digest, owner, project, status, creation timestamp, and deployment source.

### 16.1. Key Inventory Fields

| Group | Attributes |
|---|---|
| Identity | Resource ID, account/subscription/project, owner, service principal |
| Location | Region, zone, network location |
| Machine | SKU/family, vCPU, RAM, architecture, GPU |
| Image | Image ID, owner/publisher, version, digest, build time |
| Governance | Policy version, compliance state, exception ID |
| Lifecycle | Created time, last update, deprecation status |
| Cost | Cost center, environment, allocated/billable hours |

### 16.2. Drift Detection

Drift occurs when live resources diverge from policy or declared IaC configurations. Causes include manual edits, out-of-band deployments, policy updates, or provider metadata changes.

Continuous compliance should periodically scan all accounts/projects/subscriptions, detect resources outside region/SKU/image allowlists, compare live resources against IaC state where possible, monitor launch templates/autoscaling templates/node pools, detect deprecated or revoked images, and route findings to owners/ticketing systems.

### 16.3. Ownerless Resources

Resources missing owners or cost centers slow down remediation. Require mandatory tags at creation time and detect untagged resources via inventory. If no owner can be identified, route findings to platform operations per default ownership procedures.

## 17. Logging, Audit Trails, and Evidence

When a policy denies a request, logs need enough detail for users to fix the issue and for security to investigate.

Record:

- Principal or service identity making the request.
- Resource type and resource ID if assigned.
- Requested region, machine SKU, and image reference.
- Policy ID, version, and matched rule.
- Decision: `allow`, `deny`, `audit`, or `exemption`.
- Timestamp, request/correlation ID, and API caller source.
- Exception ID and approver if applicable.

Never write secrets, credentials, or sensitive payloads into policy logs.

### 17.1. Clear Denial Messages

~~~text
Request denied by compute-region-policy.
Requested region: region-x
Approved regions: region-a, region-b
Next step: select an approved region or submit a time-bounded exception.
Policy version: compute-baseline-12
~~~

Do not expose sensitive internal information in messages returned to unprivileged users, yet still provide the policy code and sufficient guidance to resolve the block.

### 17.2. Audit Evidence

Retain deployed policy sources and versions, pull requests and reviewers, policy test results, deployment records and effective timestamps, pre- and post-enforcement audit findings, exception approvals and expirations, remediation evidence, and periodic inventory snapshots.

Evidence must have retention aligned with internal/legal mandates and controlled access.

## 18. Treating Policy Violations as an Operational Workflow

Not all violations carry equal severity. A compromised, revoked image has higher urgency than a machine type exceeding a cost tier without security risk signals.

### 18.1. Severity Classification

| Level | Example | Action |
|---|---|---|
| Critical | Confirmed compromised image, data in prohibited region | Contain immediately, block new deployments, incident response |
| High | Image with critical vulnerabilities, non-policy machine SKU in production | Create urgent remediation with owner and short deadline |
| Medium | Deprecated/non-recommended SKU, aging image | Plan migration/rebuild within deadline |
| Low | Missing tags, metadata, or owner | File ticket and complete inventory |

Severity should reflect actual data, workload type, and exploitability; do not infer it mechanically from a single field.

### 18.2. Remediation Workflow

1. Create a finding with resource ID and policy ID.
2. Identify owner and dependencies.
3. Assess security, residency, and downtime risks.
4. Choose action: resize, migrate region, rebuild image, or request exception.
5. Test in an appropriate environment.
6. Execute the change via change management.
7. Re-scan to confirm compliance.
8. Close the finding with evidence.

### 18.3. Never Auto-Delete Resources Without Understanding Impact

A non-allowlisted VM may be running a database or critical service. Deleting it immediately can cause data loss and outages. Automated remediation should only be used for reversible, designed-and-tested actions—such as tagging, blocking new deployments, or quarantining revoked images under incident procedures.

## 19. Practical Example: Standardizing Compute for a Multi-Team Organization

An enterprise has three workload groups: web production, development, and HPC research. Previously, teams picked regions, VM sizes, and images freely. Bills spiked, several VMs ran in unapproved regions, and images were inconsistent.

### 19.1. Baseline Design

- Production regions restricted per residency and DR plans.
- Development limited to sandbox regions.
- Production machine families limited to general-purpose, compute-optimized, and memory-optimized with specific SKUs.
- GPU/HPC SKUs allowed only in research projects with budgets and owners.
- VMs restricted to golden images from the image factory project.
- Container workloads allowed to pull only from private registries using verified digests.

### 19.2. Phased Rollout

1. Inventory all VMs, node pools, images, and launch templates.
2. Build catalogs of approved regions, machine SKUs, and image sources.
3. Author policy-as-code and test allow/deny cases.
4. Run audit mode for two weeks to identify legitimate yet uncataloged resources.
5. Work with owners to migrate old images and change machine SKUs.
6. Enable `deny` for new deployments in development.
7. Enable `deny` for production once remediation completes.
8. Enable admission control for container images.
9. Establish time-bound exceptions for HPC/DR.
10. Review compliance and costs weekly.

### 19.3. Expected Outcomes

- New workloads are provisioned only in approved regions.
- Machine types are constrained by profile and budget.
- VM images have clear provenance and versions.
- Container images carry registries, digests, and evidence.
- Exceptions have owners, approvers, and expiration dates.
- Legacy resources are detected and remediated in a controlled manner.

Actual outcomes should be measured via violation counts, legitimate denial rates, false positives, remediation time, baseline image compliance rate, and spend per group.

## 20. Common Policy Design Mistakes

- **Allowlisting by display name:** names can vary across providers or change; use exact region/SKU/image IDs.
- **Restricting regions only for VMs:** misses disks, snapshots, backups, logs, registries, and managed resources.
- **Restricting only by machine family:** inadvertently permits massive sizes or untested new SKUs.
- **Confusing quotas with allowlists:** available quota does not mean a SKU is policy-approved.
- **Checking only IaC:** console, CLI, or service principals can create resources outside pipelines.
- **Checking only Pod images:** misses VM node images, init containers, sidecars, or ephemeral containers.
- **Allowlisting only the registry:** images may still be unsigned, unscanned, or compromised.
- **Trusting mutable tags:** tags can shift to different contents; store digests in deployment records.
- **Enabling `deny` immediately:** can break legitimate running workloads or dependent deployments.
- **No exception expiration:** temporary exemptions become permanent privileges.
- **Failing to test policy inheritance:** child scopes can be overridden or denied by parents.
- **Neglecting image lifecycle management:** stale images continue spawning new instances even from allowlisted sources.
- **Auto-deleting violating resources:** can cause outages or data loss.
- **Not storing policy versions:** makes it hard to explain why an earlier request passed while a later one was denied.

## 21. Checklist for Implementing Region, Machine Type, and Image Policies

Before enabling enforcement, confirm:

- [ ] Each policy has a clear owner and objective.
- [ ] Region allowlists are based on residency, latency, DR, service availability, and cost.
- [ ] Disks, snapshots, backups, logs, and indirectly created resources are accounted for by region.
- [ ] Machine allowlists specify families and exact SKUs suited to each environment.
- [ ] vCPU, RAM, architecture, GPU, network, and licensing are checked where needed.
- [ ] Quotas/capacity are tracked separately from policy decisions.
- [ ] VM image sources have approved publishers/owners/image IDs.
- [ ] Container images come exclusively from trusted registries/repositories.
- [ ] Production images carry digests, signatures/provenance, and scan evidence per policy.
- [ ] Golden images have patches, owners, build timestamps, and deprecation lifecycles.
- [ ] Policies are tested across allow, deny, inheritance, and exception cases.
- [ ] IaC validation is paired with control-plane enforcement and inventory scans.
- [ ] Audit mode has run and false positives have been resolved.
- [ ] Exceptions specify scope, approver, compensating controls, and expiration.
- [ ] Logging, finding owners, remediation SLAs, and evidence are established.
- [ ] A policy rollback plan exists in case enforcement causes unexpected impact.

## 22. Continuous Governance Process

1. **Discover:** collect compute, machine SKU, and image inventory.
2. **Classify:** tag workloads with data class, environment, owner, and cost center.
3. **Define:** manage region, machine type, and image source allowlists in Git.
4. **Test:** run policy unit tests and IaC validation.
5. **Observe:** enable audit mode and assess impact.
6. **Enforce:** enable `deny` incrementally by scope.
7. **Monitor:** track violations, exceptions, image freshness, and drift.
8. **Remediate:** fix resources with owners and safe plans.
9. **Review:** update catalogs as providers add/remove regions, SKUs, or images.
10. **Retire:** revoke unsupported policy exceptions, images, and machine types.

## 23. Key Takeaways

Policies restricting allowed regions, machine types, and image sources let organizations control where compute runs, what hardware is provisioned, and which base software is trusted. Use explicit allowlists, deny-by-default for high-risk scopes, organization-level baselines, and stricter profiles per workload group.

Region policies must account for data, backups, and indirectly created resources. Machine type policies must constrain families/SKUs along with CPU, RAM, architecture, and accelerator attributes; quotas and capacity are separate checks. Image policies must distinguish VM images from container images, governing publishers/registries, versions/digests, signatures, provenance, scans, and lifecycles.

Roll out policy-as-code with tests, audit mode, phased enforcement, time-bound exceptions, and continuous compliance. When violations occur, evaluate owners and impact before remediation. A strong governance program does more than block bad requests—it ensures workloads deploy consistently, traceably, within residency mandates, and on budget.
