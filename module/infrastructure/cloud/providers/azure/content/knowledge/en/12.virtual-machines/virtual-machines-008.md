# Trusted Launch, Confidential VMs, and Virtual Machine Protection

Azure Virtual Machines let you run operating systems and applications on cloud compute infrastructure. However, VMs remain exposed to risks from compromised admin accounts, untrusted images, tampered boot components, OS vulnerabilities, network misconfigurations, or unintended access to sensitive data.

Azure provides two important technologies with distinct protection goals:

- **Trusted Launch:** strengthens boot chain integrity using UEFI Secure Boot, a virtual Trusted Platform Module (vTPM), and boot measurement/evaluation capabilities.
- **Confidential VMs:** use hardware-based confidential computing to enhance protection of VM memory while **data is being processed (data in use)**, and can provide evidence for attestation mechanisms.

Neither option replaces Azure RBAC, Microsoft Entra ID, firewalls, OS patching, storage encryption, backups, or monitoring. They are additional layers within a defense-in-depth design.

This lesson belongs to the **Azure Virtual Machines** chapter of the `CLOUD_PROVIDERS_AZURE` module, connecting concepts across subscriptions, resource groups, Entra ID identity, virtual networking, compute, storage, monitoring, security, and cost governance.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish VM security risks across boot time, data at rest, data in transit, and data in use inside RAM.
2. Explain Secure Boot, vTPM, measured boot, and the role of Trusted Launch.
3. Explain confidential VMs, hardware-based memory isolation, and attestation.
4. Choose Trusted Launch or confidential VMs based on threat model, image/VM size, capabilities, region, and budget.
5. Deploy a Trusted Launch VM, read its security profile via Azure CLI, and verify status inside the guest.
6. Design complementary protection layers: access governance, private networking, encryption, patching, monitoring, and backups.
7. Build operational checklists, troubleshooting steps, and security verification criteria.

Prerequisites: Azure subscriptions, resource groups, Azure VMs, Generation 2 images, VNets, NSGs, managed disks, Azure CLI, and Azure RBAC. VM creation commands in this lesson are illustrative; running them in Azure creates resources that can incur costs.

## 2. Threat Model for Virtual Machines

Before picking features, answer: **who or what can introduce risk, which assets need protection, and which layers are trusted?**

| Asset / stage | Typical threats | Protection layer |
|---|---|---|
| VM image | Unverified image, embedded malware, or outdated dependencies | Approved images, software supply chain checks |
| Firmware / bootloader | Bootkits, rogue bootloaders, or invalid boot components | UEFI Secure Boot |
| Boot state | Silent modification of the boot chain | Measured boot, vTPM, attestation/monitoring where supported |
| OS and applications | Vulnerabilities, stolen credentials, local privilege escalation | Patching, EDR, OS hardening, least privilege |
| Data on disk | Data extracted from disk copies or misconfigured storage permissions | Storage encryption, key management, RBAC |
| Data on the network | Eavesdropping or tampering in transit | TLS/mTLS, private networks, VPN/ExpressRoute where appropriate |
| Data in RAM | Risk of guest memory access from infrastructure outside the VM under threat model | Confidential VM, hardware-based memory encryption/isolation |
| Admin accounts | Over-privileged users performing out-of-scope actions | Entra ID, Azure RBAC, PIM, logging, and approvals |
| Backups | Accidental deletion, ransomware, unavailable keys | Backups, retention, restore testing, separated permissions |

Distinguish three data states: **data at rest** (stored on disk), **data in transit** (moving over networks), and **data in use** (actively processed). Encrypting one state does not automatically protect the other two.

For instance, a database with disk encryption still holds decrypted data in RAM while executing queries. Secure Boot does not protect full RAM against host-layer access; confidential computing addresses part of that threat model. Conversely, a confidential VM does not prevent an application from being exploited through an API bug.

## 3. How Does Trusted Launch Work?

### 3.1. What Is Trusted Launch?

Trusted Launch is a security deployment option for compatible Azure VMs, built primarily on **Generation 2/UEFI** and a suite of boot-chain protections. Its goal is to make it harder to inject malicious components before the operating system and endpoint defenses start.

Components typically associated together include Secure Boot, vTPM, measured boot, and integrity monitoring when integrated with supported solutions.

### 3.2. UEFI Secure Boot

**Secure Boot** validates signatures and authenticity of boot components against UEFI trust roots and policies. If a bootloader or boot component is untrusted, firmware can refuse to load it.

Secure Boot specifically counters certain early-execution bootkits and rootkits. However, Secure Boot **does not prove every program running after boot is safe**. Properly signed software can still have vulnerabilities; an app with an authentication flaw can still be breached from the Internet.

On Linux, verify that the bootloader, kernel, drivers, and custom kernel modules align with Secure Boot policies. An update or custom image carrying unsigned modules can prevent the VM from booting.

### 3.3. vTPM

A **Virtual Trusted Platform Module (vTPM)** exposes TPM 2.0 capabilities to the guest VM where supported by the platform. The TPM supports key operations and stores measurements of the boot chain inside Platform Configuration Registers (PCRs).

A vTPM is not an automatic vault holding every application secret. Data protection depends on how the guest OS and software use the TPM, manage keys, and enforce authorization policies.

### 3.4. How Measured Boot Differs from Secure Boot

- **Secure Boot:** checks whether boot components are authorized to run.
- **Measured boot:** records cryptographic measurements of boot components and states.
- **Attestation:** a service or verifier evaluates that evidence against policy to assess trustworthiness.

~~~mermaid
flowchart LR
    F["UEFI firmware"] --> S["Secure Boot: verify boot chain"]
    S --> B["Bootloader"]
    B --> O["Kernel / Operating System"]
    F --> M["Measured boot: record measurements"]
    B --> M
    O --> M
    M --> T["vTPM"]
    T --> A["Attestation / integrity monitoring"]
    A --> P["Alert or policy evaluation"]
~~~

This is a conceptual flow; the exact set of measured components, evidence export format, and verification services depend on OS version, SKU, and actual integrations.

**A measurement differing from baseline does not automatically mean malware.** Bootloader or kernel updates naturally alter measurements. Investigators must correlate image versions, change tickets, patches, and other signals.

### 3.5. Trusted Launch Compatibility Requirements

Before deploying, confirm:

1. **Image:** supports Generation 2 and Trusted Launch.
2. **VM size:** supports the security type in the target region/subscription.
3. **OS and boot chain:** Secure Boot compatibility with bootloaders, drivers, and kernel modules.
4. **Extensions/agents:** required monitoring, security, backup, and management tools work cleanly.
5. **Disks:** OS/data disk types and encryption modes are compatible.
6. **Migration:** whether existing VMs qualify for supported in-place upgrades or require fresh VM builds.
7. **Quota, availability, and cost:** capacity and redundancy models meet requirements.

Do not assume every Generation 2 VM gets Trusted Launch enabled automatically, nor that Trusted Launch can always be enabled on Generation 1 VMs.

## 4. Confidential VMs and Protecting Data in Use

### 4.1. Concept

**Azure Confidential VMs** leverage hardware confidential computing features on supported CPUs and VM platforms. Underlying hardware may use technologies such as **AMD SEV-SNP** or **Intel TDX**, depending on the VM family and Azure availability.

This technology strengthens protection of active guest memory against certain forms of access from outside the VM boundary—such as the hypervisor or host system—within the hardware's threat model. This differs from disk encryption because data must be decrypted into RAM for the CPU to process it.

~~~text
        CONFIDENTIAL VM (guest)
  +----------------------------------+
  | Applications and OS              |
  | Data actively processed in RAM   |
  | Hardware-backed protection       |
  +----------------------------------+
                  |
          Isolation boundary
                  |
       Hypervisor / host infra
     (memory access restricted per
      features and protection model)
~~~

Confidential VMs **do not guarantee absolute secrecy**. If an attacker compromises root/administrator inside the guest, or the app sends plaintext to the wrong endpoint, host-level memory encryption will not stop it. Side-channel risks, availability, I/O devices, in-guest software, and misconfigurations still require evaluation.

### 4.2. Attestation

In confidential computing, **attestation** enables a relying party to verify evidence about the compute environment's state and security properties. Supported platforms can issue hardware reports or evidence for external verification.

~~~mermaid
sequenceDiagram
    participant V as Confidential VM
    participant P as Platform / hardware
    participant A as Attestation verifier
    participant K as Key management service
    V->>P: Request evidence
    P-->>V: Hardware report / quote
    V->>A: Submit evidence for evaluation
    A->>A: Verify policy and attributes
    A-->>V: Verification result
    V->>K: Request key per policy
    K-->>V: Release key only if policy passes
~~~

This diagram shows **an architecture you can build**, not a zero-config flow enabled out of the box on every CVM. Attestation-gated key release requires configuring evidence verification, trust policies, identity bindings, and supported key management integrations.

Never accept an environment variable or a self-asserted `"attested=true"` string inside the guest as sufficient proof. Decision points must validate cryptographically authenticated evidence.

### 4.3. Confidential VMs Are Not Enclaves

A Confidential VM generally protects **an entire guest VM** within a hardware boundary. Other confidential computing models use **enclaves** to shrink the trusted execution base to a slice of an application. The two models differ in code requirements, tooling, attestation, and threat models.

If your goal is minimizing trust in **guest administrators** or isolating data from other processes inside the same VM, evaluate enclave architectures or application-level isolation; a CVM alone may not address that threat.

### 4.4. Compatibility Limits to Evaluate

Not every VM image, GPU, driver, OS, networking feature, or disk supports CVMs. Before choosing, assess:

- Regional availability of confidential VM families, quotas, and capacity.
- Dedicated OS/images, kernel/driver versions, and UEFI settings.
- Underlying hardware platform and matching attestation mechanisms.
- OS disk encryption, guest state encryption, key management options, and disk sizes.
- Support for VM extensions, EDR, Azure Monitor Agent, disk snapshots, and Azure Backup.
- Availability Zones, HA/DR models, resizing, and cross-region portability.
- Compatibility of I/O features, Accelerated Networking, nested virtualization, or GPUs if needed.
- Cost and performance impact under realistic load profiles.

Check the feature matrix for the **exact VM family + image + region**. CVM features evolve across hardware generations; never copy settings from another example and assume it works everywhere.

## 5. Comparing Protection Models

| Criterion | Standard Azure VM | Trusted Launch | Confidential VM |
|---|---|---|---|
| Primary goal | Run apps and OS | Stronger boot-chain integrity guarantees | Additional protection of data in RAM against certain non-guest components |
| UEFI Secure Boot | Per supported image/config | Core component | Per supported design/VM family |
| vTPM and measured boot | Not enabled by default | Signature component | May include dedicated trust/attestation mechanisms |
| Hardware confidential memory protection | Not by default | Not the primary goal | Yes, per platform capabilities |
| Disk encryption | Needed based on data | Still needed | Requires matching disk/guest state encryption choices |
| Compatibility breadth | Broadest | Constrained to Gen2/supported images/SKUs | Strictly constrained by family/image/region |
| RBAC, patching, NSGs, backups | Mandatory to address | Still mandatory | Still mandatory |

**Trusted Launch is not the same as a Confidential VM.** Secure Boot and vTPM protect and measure the boot chain; CVMs add hardware memory isolation boundaries according to the threat model.

Decision examples:

- Standard web/app VM with a supported Gen2 image: **Trusted Launch** is a strong candidate to harden boot integrity.
- Worker analyzing sensitive data requiring RAM protection against host-layer risks: **evaluate confidential VMs** and integrate attestation if key release policies require it.
- VM running custom-compiled kernels/drivers or specialized software: verify compatibility and test images before committing.
- Workload needing only data-at-rest encryption: govern disk encryption, key management, and RBAC rather than treating CVM as mandatory.
- Application suited to managed platforms: evaluate App Service, Container Apps, or PaaS options before self-managing VMs.

## 6. Designing Multi-Layered Protection for Azure VMs

Trusted Launch/CVM is only one layer in the system.

### 6.1. Identity and Governance

- Grant Azure RBAC using **least privilege**, preferring resource group or VM scope over subscription scope whenever sufficient.
- Enforce Microsoft Entra ID, MFA, Conditional Access, and Privileged Identity Management (PIM) for admin accounts.
- Separate Azure control-plane roles from guest root/administrator rights.
- Use managed identities for VM apps calling Key Vault, Storage, or Azure services to avoid embedded secrets.
- Separate VM operators, key custodians, and change approvers where organizational scale permits.
- Enable Azure Activity Log and Entra sign-in/audit logs, preserving deployment evidence as required.

Holding Owner on Azure does not replace managing `sudo` groups, local admins, SSH keys, or application permissions.

### 6.2. Network Protection

- Prefer VMs in private subnets with no unnecessary public IPs.
- Use NSGs, Azure Firewall/NVAs, UDRs, and segmentation by app and environment.
- Access SSH/RDP via Azure Bastion, VPN/ExpressRoute, or controlled management paths instead of exposing TCP 22/3389 to the Internet.
- Where eligible plans exist, consider Just-in-Time (JIT) VM access and rule-change alerts.
- Protect application traffic with TLS, Private Endpoints, and controlled outbound paths.
- Monitor network anomalies and configuration changes.

A VM with Secure Boot enabled can still be compromised through an unpatched public web app. Nor does a Confidential VM replace a firewall.

### 6.3. Operating System and Applications

- Use images from trusted sources and governed image build pipelines.
- Apply OS/kernel/driver patches through tested workflows using Azure Update Manager or equivalent tooling.
- Configure EDR/antivirus, auditing, host firewalls, least privilege, and secret protection.
- Enable necessary logging while avoiding writing tokens, passwords, or sensitive data into logs.
- Scan vulnerabilities and software dependencies before building VM images.
- With Secure Boot, verify signatures and boot health after kernel/module updates.
- With CVMs, verify agents/extensions and drivers in the image support confidential computing.

### 6.4. Data and Key Protection

- **Data at rest:** apply appropriate Azure Storage/Managed Disk encryption, key management, and policies.
- **Data in transit:** enforce TLS/mTLS and private networking where needed.
- **Data in use:** consider confidential computing when justified by the threat model.
- Maintain backups independent of disk encryption, govern backup permissions, and test restores.
- Use Key Vault or Managed HSM per integration capabilities and key policies.

**Azure Disk Encryption, encryption at host, SSE, CVM disk security, and CMK modes are not identical.** Never assume every combination works together simultaneously. Verify compatibility for the exact VM type, disk security profile, OS, and region.

## 7. Pre-Deployment Design Checklist

| Item | Question | Example outcome |
|---|---|---|
| Threat model | Protecting boot only, or data in use too? | Trusted Launch for app VMs; CVM for sensitive workers |
| Region and quota | Are family/SKU available? | Organization-approved region |
| OS/image | Gen2 or CVM image supported? | Trusted image, tested release |
| VM size | Supports the chosen security type? | Size meeting CPU/RAM needs and quota |
| Networking | Public IP, Bastion, NSG plan? | Private subnet, controlled management path |
| Identity | Which admin access and managed identity? | Entra RBAC, SSH key, managed identity |
| Disk/keys | Encryption, guest state, and key ownership? | Supported encryption model |
| Backups | Is restore supported with this security type? | Verified and restore-tested |
| Monitoring | How are boot integrity and guest alerts collected? | Azure Monitor + Defender for Cloud if enabled |
| Cost | Total VM, disk, backup, logging, and network spend? | Budget and `CostCenter` tag |
| Migration | Can existing VMs convert? | Rebuild/redeploy cutover runbook with rollback |

Security is measured by real controls and evidence, not merely an “Enabled” toggle in the Azure Portal.

## 8. Hands-On: Creating a Trusted Launch VM with Azure CLI

This example **creates resources that can incur charges**. Run it only in an authorized lab subscription after confirming VM size/image compatibility.

### 8.1. Prerequisites

Assume you have:

- Resource group **rg-vmsecurity-lab**.
- VNet **vnet-security-lab** and subnet **snet-workload** in the same example resource group.
- Appropriate NSGs/routes and a private management path such as Bastion or VPN.
- Approved SSH key or sign-in method.
- Permissions to create VMs, NICs, OS disks, and related resources.

Verify subscription:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

List VM sizes in a region:

~~~bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --all \
  --output table
~~~

Output here does not automatically prove every image/security-type combination works; verify Trusted Launch support for the exact size, image, and region.

### 8.2. Create a VM with Secure Boot and vTPM

Bash example:

~~~bash
az vm create \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --location southeastasia \
  --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
  --size Standard_D2s_v5 \
  --security-type TrustedLaunch \
  --enable-secure-boot true \
  --enable-vtpm true \
  --admin-username azureadmin \
  --generate-ssh-keys \
  --vnet-name vnet-security-lab \
  --subnet snet-workload \
  --public-ip-address ""
~~~

In this command:

- **--security-type TrustedLaunch** requests Trusted Launch security.
- **--enable-secure-boot true** enables UEFI Secure Boot.
- **--enable-vtpm true** enables vTPM.
- **--image** illustrates an Ubuntu Generation 2 image; verify URN availability and compatibility in your region.
- **--size** is an illustrative size; confirm support in your actual subscription.
- **--public-ip-address ""** prevents creating a public IP in this Azure CLI example.
- **--vnet-name / --subnet** expects an existing network, or add the network resource group option if located elsewhere.

If Azure rejects the request because the image/size is incompatible, fix the choice per documentation. **Never disable Secure Boot to bypass errors** when security policy mandates it. If no private management path is ready yet, a VM without a public IP will not be directly reachable—prepare connectivity first.

### 8.3. Read the Security Profile

~~~bash
az vm show \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --query securityProfile \
  --output json
~~~

Example key fields in the response:

~~~json
{
  "securityType": "TrustedLaunch",
  "uefiSettings": {
    "secureBootEnabled": true,
    "vTpmEnabled": true
  }
}
~~~

This shows example fields only, not a guarantee of exact full JSON across all API versions. Configuration values do not prove the guest booted cleanly or that an attestation service verified its state.

Inspect runtime status:

~~~bash
az vm get-instance-view \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --output json
~~~

### 8.4. Verify Inside the Guest

Inside the Linux guest after signing in over an authorized management path:

~~~bash
# Install mokutil if not present in the image.
mokutil --sb-state

# Verify the guest detects the TPM.
ls /sys/class/tpm
ls -l /dev/tpm* 2>/dev/null
~~~

These tools report Secure Boot status and TPM presence, but **do not replace** external attestation from outside the guest.

In a compatible UEFI/TPM Windows guest, check via PowerShell:

~~~powershell
Confirm-SecureBootUEFI
Get-Tpm
~~~

If either command fails, check OS privileges, Windows edition, firmware mode, and feature support before assuming an Azure platform fault.

## 9. Deploying a Confidential VM

Do not take a Trusted Launch template and merely swap the security type string to `ConfidentialVM`. Select a fully supported combination of image, size, disks, and guest-security profile.

### 9.1. Confirm Protection Requirements

Example: an internal analytics worker processes decrypted sensitive data in RAM, and the organization wants to reduce the ability of the host/hypervisor layer to read memory contents under its threat model.

That justifies evaluating confidential VMs. However, if the goal is shielding data from a compromised process **inside the same guest**, you need application isolation or a different architecture.

### 9.2. Selecting Configuration in the Azure Portal

Conceptual sequence:

1. Select subscription, resource group, and region.
2. Select a **Confidential VM** family and compatible size from Azure's current catalog.
3. Choose a specialized OS/image supported for that confidential VM family.
4. Set security type and UEFI/vTPM/Secure Boot options per image and platform rules.
5. Pick a supported **OS disk / guest state encryption** mode, deciding between platform-managed or customer-managed keys if offered.
6. Configure private networking, sign-in method, managed identity, and logging.
7. Review Azure Backup, extensions, availability, guest agent, and quota support.
8. Deploy in a lab first; verify guest health, apps, and attestation if required.

VM families built on AMD SEV-SNP vs. Intel TDX carry differing deployment prerequisites. Never assume all CVMs share identical configs, disk encryption modes, or attestation formats.

### 9.3. Inspect VM State with CLI

After deploying a CVM:

~~~bash
az vm show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<CONFIDENTIAL_VM_NAME>" \
  --query "{name:name,size:hardwareProfile.vmSize,security:securityProfile}" \
  --output json
~~~

This is an Azure resource read operation. It verifies **declared configuration**, not proof that hardware attestation passed. Real verification requires the attestation mechanism, SDK, or service supported for that VM family and platform.

### 9.4. Releasing Keys or Secrets Conditionally on Trust

Reference architecture:

~~~text
Encrypted dataset on Azure Storage
               |
               v
        Confidential VM
               |
               +--> Hardware/platform evidence
                          |
                          v
                 Attestation verifier
                          |
                          v
                  Policy decision
                          |
                          v
             Key Vault / key release system
                          |
                          v
                  App decrypts data
                          |
                          v
                 Process inside guest
                          |
                          v
                Encrypt output results
~~~

Only claim “keys are released upon passing attestation” when the real system enforces policies, a verifier, and a supported key-release mechanism. If keys are still handed out via an overly permissive identity without checking attestation, CVM configuration alone does not enforce conditional key release.

Never place plaintext keys into images, customData/userData, boot logs, or Git repositories. Govern key lifecycles and attestation evidence access by policy.

## 10. Disk Encryption and Guest State

### 10.1. Distinguishing Mechanisms

| Mechanism | Typical scope | Limitations |
|---|---|---|
| Storage Service Encryption (SSE) | Encrypts data at rest in the storage service | Does not protect RAM once the guest decrypts data |
| Encryption at host (where supported) | Adds host-layer storage encryption per Azure capability | Not equivalent to confidential VM memory isolation |
| Guest OS disk encryption / Azure Disk Encryption (in supported scenarios) | Encrypts volumes via OS mechanisms and key management | Constrained by Gen2, security profiles, and CVM compatibility |
| Confidential VM disk / guest state security | Protects OS disk/guest state via CVM-specific options | May not support every key mode or backup feature |
| TLS/mTLS | Protects data in transit | Does not replace disk or RAM protection |
| CVM hardware memory protection | Enhances guest RAM protection against certain host components | Does not stop leaks caused by the guest or app itself |

**Never assume Azure Disk Encryption, SSE with CMK, encryption at host, CVM OS disk protection modes, and backups all work together across every SKU.** Verify exact documentation before adopting them in an architecture.

### 10.2. Key Management and Data Loss Risks

- Define who owns keys, who can use them, and who approves policies.
- Use Azure Key Vault or Managed HSM where supported integrations exist.
- Block unauthorized access with Azure RBAC, network controls, and logging.
- Configure rotation, recovery, soft delete, and key protections where supported.
- Test scenarios where a key is revoked or the key management system is temporarily unreachable.

Never delete or disable an encryption key actively protecting VMs without assessing impact. Even with backups, losing the required key can make data unrecoverable.

## 11. Monitoring and Auditing Protected VMs

### 11.1. Multi-Layer Verification

| Check layer | Source | Question |
|---|---|---|
| Azure Resource Manager | VM security profile, image, size, disks | Does declared config comply with policy? |
| Azure Activity Log | VM and related resource create/modify/delete events | Who changed settings and when? |
| Guest OS | Security logs, Secure Boot/TPM state, patch level | What state is the OS in? |
| Boot integrity / attestation | Services supported for the image/VM type | Does evidence satisfy policy? |
| Defender for Cloud | Recommendations and security alerts when plan/features enabled | Are there new risks or weak configs? |
| Azure Monitor | CPU, disk, network, availability, log agent if installed | Is the workload healthy? |
| Backup | Job history, retention, and restore tests | Can we recover during an incident? |
| SIEM / ticketing | Microsoft Sentinel or equivalent system | Are investigations and decisions documented? |

Enabling Trusted Launch with vTPM does not automatically surface all guest attestation signals. Depending on image/OS/VM, you need matching agents, extensions, protection plans, diagnostic settings, or attestation services. Inspect actual telemetry rather than trusting an “enabled” checkbox.

### 11.2. Read-Only Verification Commands

~~~bash
# VM security profile
az vm show -g rg-vmsecurity-lab -n vm-tl-lab01 \
  --query securityProfile -o json

# VM status and instance view
az vm get-instance-view -g rg-vmsecurity-lab -n vm-tl-lab01 \
  -o json

# Activity Log over the past 24 hours
az monitor activity-log list --offset 24h --output json
~~~

These commands assist inventory and investigations, yet do not replace attestation outputs or audit evidence from trusted verifiers. When archiving evidence, record resource ID, UTC timestamp, image version, collector, and data scope.

### 11.3. Azure Policy and Deployment Standards

Across multi-subscription organizations, Azure Policy can audit or enforce security profile attributes on supported resource types and policy definitions. Rollout sequence:

1. Inventory Gen1/Gen2 VMs, images, security types, sizes, and regions.
2. Classify workloads requiring Trusted Launch, confidential VMs, or approved exceptions.
3. Start with Audit policies to measure non-compliance scope.
4. Add validation into Bicep/Terraform and CI/CD pipelines.
5. Switch to Deny only after understanding impacts across images and VM families.
6. Track exemptions, owners, and review expiration dates.

Never force confidential VMs onto every workload simply because they protect memory; doing so can break deployments or inflate costs unnecessarily when the threat model does not call for it.

## 12. Patching, Backups, and Rollback

### 12.1. Safe Image Updates

A kernel, driver, or bootloader change can break Secure Boot or alter boot measurements. Workflow:

1. Build a new image version in a controlled pipeline.
2. Deploy a staging VM matching production's security type and extensions.
3. Verify boot, Secure Boot/vTPM, permissions, networking, disks, and the app.
4. Verify attestation outputs if used to gate key release.
5. Record the new baseline and change ticket; roll out gradually where supported.
6. Retain previous images/backups for controlled rollback.
7. Monitor post-release and update baselines deliberately.

If boot fails due to an unsigned module, never disable Secure Boot indefinitely as a quick fix. Resolve signing, check compatibility, or revert to a valid image.

### 12.2. Realistic Backup and DR Capabilities

Before committing to RPO/RTO targets, confirm:

- Does Azure Backup support the exact **security type, VM generation, OS disk mode, and VM family**?
- Are snapshots, restoring a new VM, or cross-region restores supported in this setup?
- Do data disks, guest state, or keys require special recovery steps?
- Does the target DR region offer matching confidential VM families and quotas?
- After restore, do permissions, private endpoints, networking, and key policies still align?

**Disk encryption does not replace backups, and a successful backup does not guarantee the app restores cleanly.** Test restores into an isolated environment and verify data integrity and business functionality.

### 12.3. Migrating Legacy VMs to Trusted Launch / CVM

Do not assume Generation 1 VMs or legacy images can convert in-place directly to Trusted Launch or CVMs. Conversion support depends on the VM, OS, image, disks, and service capabilities at the time. When no in-place upgrade path exists, deploy fresh VMs from supported images and migrate apps/data using a cutover plan.

Required steps: inventory, staging tests, backups, compatibility checks, downtime planning, DNS/IP/managed identity validation, monitored cutover, and rollback.

## 13. Real-World Scenario: Financial Data Processing

Suppose an enterprise runs a financial analytics platform:

- An API receives requests and authenticates users via Entra ID.
- Worker VMs process encrypted data stored in Azure Storage.
- Azure Key Vault manages encryption keys.
- Azure Monitor and Defender for Cloud provide risk visibility.
- CI/CD builds images and deploys infrastructure under change control.

### 13.1. Choosing Controls by Role

| Component | Protection need | Reference design |
|---|---|---|
| Web/API VMs | Prevent boot tampering; protect OS and network | Trusted Launch + RBAC/NSG/EDR/TLS |
| Sensitive analytics workers | Reduce risk of host components reading guest RAM | Evaluate confidential VMs and attestation |
| Azure Storage | Protect data at rest and control access | Encryption, RBAC, private endpoints, backups |
| Azure Key Vault | Restrict who uses keys | Policies, logging, and conditional key release where supported |
| Pipeline | No hardcoded secrets; governed images | Managed identity/WIF, approvals, artifact validation |
| Administration | Prevent unauthorized access | Bastion/VPN, Entra, PIM, auditing |

### 13.2. Processing Flow

~~~mermaid
flowchart TD
    U["Authenticated user"] --> A["Orchestrator API"]
    A --> W["Worker in Confidential VM"]
    S["Storage: encrypted data"] --> W
    W --> T["Attestation verifier if deployed"]
    T --> K["Key Vault / policy"]
    K --> W
    W --> E["Encrypted output"]
    E --> S
    M["Monitor / Defender / logs"] -.-> W
~~~

This diagram illustrates the concept: only when a key-release policy actively enforces attestation verification can an organization claim keys are withheld from non-compliant environments. Merely running the worker on a CVM does not enforce that gate by itself.

### 13.3. Acceptance Criteria

1. VMs use supported images, security types, sizes, and disk configurations.
2. VM and Key Vault permissions follow least privilege, with zero plaintext secrets in images/logs.
3. Networking exposes no unintended public management ports.
4. Attestation/policies genuinely enforce gates if mandated.
5. Guest patches/agents/EDR operate with telemetry and alerts where supported.
6. Backup and restore compatibility is verified.
7. Latency, cost, and stability are benchmarked under representative load.
8. Threat model, configuration docs, approvers, and recovery plans are recorded.

## 14. Common Errors

| Symptom | Possible causes | Investigation steps |
|---|---|---|
| Cannot create Trusted Launch VM | Gen1 image, unsupported size/region, missing quota | Check image generation and SKU availability |
| Secure Boot prevents VM boot | Unsigned bootloader, kernel module, or driver | Check boot diagnostics, image, and patch history |
| Wrong security profile | Missing flags, stale template, or deployment drift | Inspect `securityProfile` and deployment history |
| vTPM missing inside guest | Not enabled, OS unaware, or unsupported feature | Cross-check Azure config, `Get-Tpm`, or `/sys/class/tpm` |
| Integrity signal shifts after update | Legitimate baseline shift or tampering indicator | Compare against change ticket, kernel, boot logs, and verify |
| Cannot pick CVM size | Unsupported region, quota, OS image, or VM family | Check availability and feature matrix |
| CVM boots yet attestation fails | Policy mismatch, faulty evidence, or incompatible SDK | Inspect report/policy per platform docs |
| VM runs slowly | Suboptimal VM family, drivers, I/O, or app code | Benchmark realistically and measure p95 |
| Backup/restore fails | Incompatible security profile or disk encryption mode | Check support matrix and test restore in lab |
| SSH/RDP fails | NSG, Bastion, DNS, guest firewall, or identity | Inspect approved management path |
| Key Vault denies secret access | RBAC, network, or attestation policy failure | Inspect policies, audit logs, and auth errors |

Never fix failures by disabling Secure Boot, opening ports 22/3389 to the Internet, or granting subscription-wide Owner. Investigate sequentially: **image/SKU → Azure config → boot/guest → network/identity → app → attestation → backup**.

### 14.1. If a Boot Integrity Alert Fires

1. Record alert ID, VM resource ID, UTC timestamp, and application impact.
2. Check alert source, measurement/attestation state, and observed telemetry scope.
3. Correlate recent kernel/image/driver updates against change tickets.
4. Preserve logs and evidence per policy; avoid unnecessary scene tampering.
5. If compromise is suspected, isolate per approved runbook and investigate permissions and access origins.
6. Verify image/boot/OS integrity before restoring traffic.
7. Document root cause, conclusion limits, remediation, and incident sign-off.

A legitimate update incompatible with Secure Boot can look identical to a security incident from a user's perspective. Never conclude malware is present without concrete evidence.

## 15. Performance, Availability, and Cost

Confidential VMs can carry constraints on VM families, I/O features, agents, and certain availability/DR methods; pricing also differs from standard VMs. No single fixed overhead percentage applies across all applications.

Benchmarks should measure:

- Boot and post-update restart duration.
- CPU/memory throughput and latency.
- Disk IOPS, throughput, `fsync`, and data disk compatibility.
- Network RTT, TLS overhead, and calls to dependent services.
- Attestation and key-release latency if on the critical path.
- Business p95/p99 latency and error rates.
- Backup/restore duration and actual RTO.

**Confidential VMs do not automatically provide multi-zone resilience or prevent downtime.** You still need HA, Availability Zones, load balancers, multi-region designs, or DR within the capabilities of the selected family/region.

Budget for more than VM compute: include managed disks, backups, networking, Bastion, Azure Monitor, Log Analytics, Defender for Cloud, Key Vault, and test infrastructure. Apply `Application`, `Owner`, `Environment`, and `CostCenter` tags; track Cost Management and budget alerts without confusing budget alerts with hard spending caps.

## 16. Production Readiness Checklist

### Pre-Deployment

- [ ] Threat model clearly defines boot integrity vs. data-in-use protection needs.
- [ ] Selected Trusted Launch/CVM or documented an approved exception.
- [ ] Image, OS, VM size, region, quota, and extensions are compatible.
- [ ] Designed VNet, NSGs, Bastion/VPN admin access, and required connectivity paths.
- [ ] RBAC, Entra identities, and managed identities follow least privilege.
- [ ] Disk encryption, key management, and recovery policies are defined.
- [ ] Verified backup/restore compatibility for the exact security type.
- [ ] Established performance baselines, monitoring, and cost estimates.

### Post-Deployment

- [ ] Security profile reports the intended security type and UEFI settings.
- [ ] Guest OS detects expected Secure Boot/vTPM status.
- [ ] Application operates cleanly with zero unintended public access.
- [ ] Attestation and conditional key release are verified if part of the design.
- [ ] Monitoring/Defender alerts actively receive telemetry where supported.
- [ ] Backup jobs and restore tests meet agreed criteria.
- [ ] Owner, tags, runbooks, change records, and approvers are documented.

### Ongoing Operations

- [ ] OS/kernel/driver patches are tested before rollout.
- [ ] Images, extensions, and security profiles are checked for drift.
- [ ] RBAC and guest OS privileges are audited periodically.
- [ ] Boot integrity alerts and software incidents follow playbooks.
- [ ] Backup/restore outcomes are re-verified periodically.
- [ ] Feature support, cost, quotas, and roadmaps are reviewed prior to resizing/migration.

## 17. Knowledge Self-Check

1. **What does Trusted Launch primarily protect?** The boot chain, using Secure Boot, vTPM, and related measurement/verification capabilities.
2. **Does Secure Boot block all malware after the OS finishes booting?** No. Patching, EDR, network protection, and application security are still required.
3. **How does measured boot differ from Secure Boot?** Measured boot records measurements as evidence; Secure Boot enforces which components are permitted to load.
4. **What is vTPM used for?** Providing TPM 2.0 functionality in the guest, including storing boot measurements and supporting application key operations.
5. **Does enabling vTPM automatically generate complete attestation alerts?** No. Supported monitoring integrations or attestation services are required.
6. **Which data state do Confidential VMs add protection for?** Data in use in RAM, within the corresponding hardware threat model.
7. **Does a CVM provide absolute protection against a compromised guest root/admin account?** No.
8. **Does a CVM replace disk encryption and TLS?** No. Each data state requires dedicated controls.
9. **Does attestation alone ensure Key Vault releases secrets only to compliant VMs?** No; actual policies and key-release integrations must be configured.
10. **Why do Gen2 images matter for Trusted Launch?** UEFI/Secure Boot and compatibility prerequisites depend on Generation 2.
11. **Does enabling Trusted Launch make it safe to open RDP to the entire Internet?** No. NSGs, strong identity, and protected management channels remain necessary.
12. **Is SSE equivalent to confidential memory protection?** No. SSE protects data at rest in storage.
13. **Why must you test backup/restore specifically for CVMs?** Restrictions can apply depending on security profile, disk mode, and VM family.
14. **When an image update alters attestation measurements, can you immediately conclude an attack occurred?** No. Correlate against baselines, authorized changes, and additional evidence.
15. **Should every VM be deployed as a CVM?** No. Base the choice on threat model, compatibility, performance, availability, and total cost.

## 18. References

- [Trusted Launch for Azure virtual machines](https://learn.microsoft.com/azure/virtual-machines/trusted-launch) — Trusted Launch mechanisms and requirements.
- [Deploy Trusted Launch VMs](https://learn.microsoft.com/azure/virtual-machines/trusted-launch-portal) — Portal deployment workflow.
- [Azure confidential virtual machines](https://learn.microsoft.com/azure/confidential-computing/confidential-vm-overview) — CVM protection model and capabilities.
- [Azure confidential computing](https://learn.microsoft.com/azure/confidential-computing/) — data-in-use protection and attestation.
- [Azure security benchmark: Virtual Machines](https://learn.microsoft.com/security/benchmark/azure/baselines/virtual-machines-security-baseline) — VM security baseline controls.
- [Azure virtual machine disk encryption](https://learn.microsoft.com/azure/virtual-machines/disk-encryption-overview) — disk encryption options and prerequisites.
- [Azure Backup for virtual machines](https://learn.microsoft.com/azure/backup/backup-azure-vms-introduction) — VM data protection and recovery.
- [Microsoft Defender for Cloud](https://learn.microsoft.com/azure/defender-for-cloud/) — security posture and alerting.
- [Azure Update Manager](https://learn.microsoft.com/azure/update-manager/overview) — OS patch management.
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/) — governance auditing and enforcement.

**Conclusion:** Trusted Launch strengthens confidence in the boot process; confidential VMs add hardware-backed protection for memory in use per your threat model. Complete VM security still depends on identity, networking, image supply chains, patching, encryption, backups, monitoring, and testing. For production deployments, validate support across the **exact image, VM family, disk security mode, region, and operational services** rather than inferring behavior from feature names.
