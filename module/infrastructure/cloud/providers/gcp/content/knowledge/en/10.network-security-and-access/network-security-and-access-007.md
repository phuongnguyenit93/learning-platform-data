# OS Login and SSH Access Control on Google Cloud

An operations team manages **Compute Engine** VMs running internal tools, background jobs, and troubleshooting utilities. The team wants developers to access VMs relevant to their work, on-call engineers to perform administrative tasks when assigned, and departing personnel to lose login access immediately. At the same time, the organization wants to restrict public SSH ports and avoid manually copying SSH keys onto individual VMs.

**OS Login** is Google Cloud's mechanism for managing operating system login permissions on Linux VMs through **Identity and Access Management (IAM)**. Rather than relying primarily on SSH public keys stored in project or instance metadata, OS Login binds login to a Google Cloud identity, IAM roles, and POSIX/SSH user profiles managed via OS Login. Truly securing SSH also requires controlling the **network path to port 22**, SSH daemon configuration, key lifecycle, multi-factor verification where supported, monitoring, and emergency recovery procedures.

This lesson belongs to the **Network Security and Access** chapter of the **CLOUD_PROVIDERS_GCP** module. When building systems spanning organizations/projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases, learners must choose appropriate administrative access patterns, protect hosts and data, automate configuration, and monitor both reliability and cost.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how OS Login works and how it differs from metadata-based SSH key management.
2. Distinguish `roles/compute.osLogin`, `roles/compute.osAdminLogin`, service account usage permissions, and IAP TCP tunnel permissions.
3. Determine project- vs. instance-level OS Login enablement scope and understand metadata inheritance/overrides.
4. Combine OS Login with **Identity-Aware Proxy (IAP) TCP forwarding** to connect to VMs without external IPs.
5. Establish workflows for granting/revoking access, managing SSH keys, verifying 2-step verification, and maintaining audit trails.
6. Isolate and diagnose IAM, OS Login, SSH daemon, firewall, routing, and application errors independently.

## 2. Four Layers of an SSH Login Session

A successful login requires satisfying multiple conditions simultaneously:

| Layer | Question | Related components |
| --- | --- | --- |
| **Identity** | Who is requesting access? | Google/Cloud Identity account, IAM group, SSH key, or supported authentication mechanism. |
| **Authorization** | Which VMs may that identity enter, and can it use `sudo`? | OS Login roles, IAM allow/deny policies, access conditions, and extra requirements for service accounts. |
| **Network connectivity** | Can the admin's machine reach the SSH port on the VM? | External IP or IAP tunnel, VPC firewall, routes, ingress policies, SSH port. |
| **Operating system** | Does the VM support OS Login with valid SSH daemon and auth configuration? | Guest environment, NSS/PAM, POSIX username, `sshd`, filesystem, Linux configuration. |

~~~mermaid
flowchart LR
    OP["Operations engineer"] --> AUTH["Google identity / IAM"]
    AUTH --> IAP["IAP TCP tunnel or allowed SSH path"]
    IAP --> FW["VPC firewall: TCP 22"]
    FW --> VM["Compute Engine Linux VM"]
    VM --> OS["OS Login + SSH daemon"]
    OS --> SH["User shell"]
    P["IAM roles and POSIX privileges"] -. "Login / sudo rights" .-> OS
~~~

**OS Login is not a VPN, firewall, or SSH tunnel.** It handles identity and OS login authorization. A user with a valid IAM role still cannot SSH if the VPC firewall blocks port 22. Conversely, an open firewall does not let a user without OS Login permissions log in.

### 2.1. Which Workloads Does OS Login Apply To?

The typical case is a **Compute Engine Linux VM** with a guest environment supporting OS Login. For custom images, verify that OS Login components and compatible SSH/NSS/PAM configurations are installed. Windows VMs use different account management and connection mechanisms and do not follow the Linux SSH login model in this lesson.

When **GKE** nodes run on Compute Engine, SSH access to nodes and node operations carry GKE-specific constraints; do not treat managed cluster nodes identically to standalone self-managed VMs. **Cloud Run** is a serverless environment without direct SSH into service VMs; rely on Cloud Run logs, revisions, and diagnostic tools instead. Nor does SSHing into a VM grant **Cloud SQL** or **Cloud Storage** access permissions.

## 3. OS Login vs. Metadata SSH Keys

### 3.1. Traditional Approach: Metadata-Based SSH Keys

In the metadata SSH key model, public keys can be added to **project** or **instance** metadata. The Compute Engine guest environment on the VM uses supported mechanisms to create/update Linux users and manage `authorized_keys`.

~~~text
Administrator → gcloud/metadata SSH key → VM guest environment
             → Linux user + authorized_keys → sshd
~~~

While convenient for a single test VM, as fleet size grows, tracking who can log in, which keys remain valid, and when access must be revoked becomes fragmented. Setting `block-project-ssh-keys=TRUE` blocks project-level metadata SSH keys on that VM, but **does not mean OS Login is enabled or enforced**.

### 3.2. Approach with OS Login

When OS Login is active:

1. Users are granted an appropriate **IAM role** on the resource or ancestor scope.
2. SSH public keys (when using key-based auth) are attached to the identity's **OS Login profile**, rather than using project/instance metadata SSH key lists as the standard login source.
3. The VM's guest environment integrates with OS Login to resolve POSIX accounts and verify login eligibility.
4. Users log into a shell with corresponding Linux permissions; only users granted appropriate admin roles can use `sudo` via OS Login.

When OS Login is enabled, Compute Engine ignores SSH keys in project/instance metadata for standard metadata-based authentication. Keys stored in metadata are not treated as an OS Login authorization source. However, **never assume OS Login disables every local account or alternate access method on a modified custom image**: audit `sshd`, local accounts, custom authorized keys, and any remaining administrative paths.

| Criterion | Metadata SSH keys | OS Login |
| --- | --- | --- |
| Primary source of access control | Keys in project/instance metadata and guest config. | Identity and IAM roles combined with OS Login profile. |
| Offboarding personnel | Requires cleaning up metadata/keys and ensuring guest sync. | Revoke IAM binding or group membership; check active sessions and other grants. |
| Standard vs. `sudo` access | Depends on user/guest setup and SSH key workflows. | Cleanly separates standard login role from OS admin role. |
| Extra authentication | Requires custom implementation. | Supports OS Login 2-step verification when eligible. |
| Auditing | Track metadata edits and guest logs. | Adds IAM/OS Login API audit trails plus guest logs, per logged event types. |
| Deployment scope | Configured per metadata/VM. | Enabled per project or instance; roles managed via IAM. |

OS Login **centralizes authorization workflows**; it does not mean assigning an IAM role alone makes SSH secure. Network policy, private key hygiene, OS patching, and logging remain mandatory.

## 4. IAM Roles to Understand

### 4.1. Two Primary Roles

| Role | Purpose | Example recipient |
| --- | --- | --- |
| `roles/compute.osLogin` | Grants OS Login access as a non-privileged standard user on eligible VMs. | Developers needing to inspect app files/logs within approved scope. |
| `roles/compute.osAdminLogin` | Grants OS Login access with OS administrative privileges, including `sudo`, within permitted scope. | Operations engineers performing authorized maintenance. |

`roles/compute.osAdminLogin` is sensitive: root privileges on a VM can affect processes, files, application keys, credentials present on disk, and availability. Never grant `osAdminLogin` simply because a user hit a read error on a directory. Adjust **Linux file permissions, ownership**, or the workflow before handing out full machine admin rights.

### 4.2. At Which Level Should Roles Be Bound?

OS Login roles can be bound at the project level and, where supported, at specific VMs or ancestor scopes. Where you place the binding defines the blast radius:

~~~text
Organization
└── Folder: production
    ├── Project: retail-prod
    │   ├── VM: checkout-worker-01
    │   └── VM: reporting-worker-02
    └── Project: analytics-prod
~~~

- Binding a login role on **project `retail-prod`** can grant SSH access across many eligible VMs in the project.
- If only **a single VM** needs maintenance, prefer a narrower instance-level binding where roles and provisioning workflows support it.
- Binding broadly at **folder/organization** scope propagates access across many projects, which is only appropriate for teams explicitly assigned cross-project duties.

IAM allow policies can also be affected by **IAM Conditions**, deny policies, and other constraints. Therefore, never evaluate effective access solely from a direct binding on a single VM.

### 4.3. Additional Permissions Often Overlooked

| Scenario | Permission or mechanism to check | Why? |
| --- | --- | --- |
| SSH via IAP TCP forwarding | `roles/iap.tunnelResourceAccessor` at the appropriate scope. | Authorizes opening an IAP tunnel to the protected resource. |
| VM has an attached service account | May require `roles/iam.serviceAccountUser` on the **VM's attached service account** per SSH flow/OS Login rules. | Access to VMs running as a service account is a separate control that must be respected. |
| Users outside the organization | May require `roles/compute.osLoginExternalUser` granted as needed at the **organization** alongside a regular OS Login role on the VM/project. | Lets organizations govern external identities using OS Login. |
| Listing/reading VM details via gcloud | Permissions such as `compute.instances.get` and `compute.instances.list` per CLI/UI usage. | OS Login roles govern OS login, not all Compute Engine management actions. |
| Editing metadata or IAM policies | Appropriate Compute Engine/IAM admin roles. | Users allowed to SSH should not necessarily be able to toggle OS Login or grant access to others. |

Anyone connecting via IAP needs **both tunnel permission and Linux login permission**. Missing either causes SSH to fail at a different stage. For service accounts or external-to-organization users, check official documentation and your identity model to see which additional bindings apply.

### 4.4. Use Groups Instead of Scattered Individual Bindings

A clean governance pattern:

~~~text
group:vm-readers@example.com
  → roles/compute.osLogin
  → scope: authorized VM group

group:vm-maintainers@example.com
  → roles/compute.osAdminLogin
  → scope: VMs needing controlled maintenance

group:vm-iap-users@example.com
  → roles/iap.tunnelResourceAccessor
  → scope: appropriate tunnel/VMs
~~~

An administrator can belong to multiple groups simultaneously. Define membership, approving owners, and review cadences for every group; for `sudo` access, enforce approvals, time-bound privileged access where supported, and periodic reviews.

## 5. Enabling OS Login on VMs and Projects

### 5.1. Pre-Change Preparation

Before enabling in production:

1. Confirm VMs are **Linux VMs supporting OS Login** with a compatible guest environment. For custom images, verify setup beforehand.
2. Inventory current operators, attached service accounts, OS Login groups, and whether IAP permissions are in place.
3. Verify a test connection still works once metadata keys are ignored.
4. Check `sshd`, firewalls, routes, and fallback access paths per your organization's recovery runbook.
5. Test on a comparable nonproduction VM, verifying both standard users and `sudo`-privileged operators.
6. Assess impact if the project has older VMs, maintenance scripts, or legacy pipelines still relying on metadata SSH keys.

Enabling OS Login before assigning proper IAM roles can **lock operations teams out of SSH**. Prepare a controlled recovery path before modifying metadata or enforcing an Organization Policy.

### 5.2. Enabling at the Project Level

`enable-oslogin=TRUE` is the metadata key used to enable OS Login. Configuring it at the **project** level applies it by default to eligible VMs, barring valid instance overrides or policy constraints.

~~~bash
# Examples use Bash and an illustrative project ID.
PROJECT_ID="retail-prod"

# READ-ONLY: inspect project-wide common metadata.
gcloud compute project-info describe \
  --project="$PROJECT_ID" \
  --format="yaml(commonInstanceMetadata.items)"

# WRITE: enable OS Login via project metadata.
gcloud compute project-info add-metadata \
  --project="$PROJECT_ID" \
  --metadata=enable-oslogin=TRUE
~~~

`add-metadata` **modifies live configuration**. Run it only when authorized and after verifying all affected VMs. If the organization requires OS Login across all VMs, administrators can enforce an Organization Policy constraint such as **`constraints/compute.requireOsLogin`** after evaluating scope and support—a stronger governance control than metadata alone.

### 5.3. Enabling at the Instance Level

~~~bash
PROJECT_ID="retail-prod"
ZONE="asia-southeast1-a"
VM="checkout-worker-01"

# READ-ONLY: inspect VM metadata and service account.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,metadata.items,serviceAccounts)"

# WRITE: enable OS Login on the specific VM.
gcloud compute instances add-metadata "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --metadata=enable-oslogin=TRUE
~~~

Instance-level metadata can **override the corresponding project-level value** when not locked by an organization policy. Therefore, seeing project metadata set to `TRUE` is not enough to conclude every instance has OS Login active: inspect instance metadata and effective constraints too.

Never set `enable-oslogin=FALSE` as a workaround to bypass governance when Organization Policy mandates OS Login. Any access configuration change must go through an approved workflow.

### 5.4. Reading Back State

~~~bash
# READ-ONLY: confirm VM metadata after update.
gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(metadata.items)"
~~~

This confirms **the metadata was saved**, but you still must test logging in with a valid identity to confirm the guest environment works. Do not treat `enable-oslogin=TRUE` as an end-to-end test of SSH, IAM, and networking.

## 6. Managing SSH Public Keys with OS Login

### 6.1. Public Key and Private Key

An SSH key pair consists of:

- **Private key:** stored securely on the user's device or key manager; never sent via email, Git repositories, or shared metadata.
- **Public key:** added to the OS Login profile so the system verifies signatures during login.

Do not confuse an **SSH key for VM login** with a **service account JSON key** for authenticating to Google APIs. They are distinct credential types with separate functions and risks.

### 6.2. Adding a Key to an OS Login Profile

Suppose a user has an SSH public key at `~/.ssh/id_ed25519.pub`:

~~~bash
# Read OS Login profile of the active identity.
gcloud compute os-login describe-profile

# WRITE: add public key to the identity's OS Login profile.
gcloud compute os-login ssh-keys add \
  --key-file="$HOME/.ssh/id_ed25519.pub"

# READ-ONLY: list public keys in the profile.
gcloud compute os-login ssh-keys list
~~~

Depending on CLI version and policy, you can set an **expiration time** on the key instead of storing it indefinitely; check `gcloud compute os-login ssh-keys add --help` for exact flags. Key formats, usernames, and TTLs also depend on the OS Login profile and system support.

`gcloud compute ssh` can handle generating/importing keys and resolving the username via OS Login automatically. Avoid manually hardcoding Linux usernames like `ubuntu` or `root` without checking the profile. POSIX usernames may be derived from the Google Cloud identity following specific rules.

### 6.3. Key Lifecycle and Revoking Access

When a person leaves the team:

1. Revoke the IAM role or group membership granting OS Login access.
2. Check for direct bindings on other projects, instances, or ancestor nodes.
3. Review and delete/expire SSH keys in their OS Login profile as needed per offboarding policy.
4. Terminate **already established** SSH sessions if immediate cutoff is needed, because revoking new login permissions does not always kill active running shell sessions.
5. Check local accounts, manually managed keys, alternate SSH paths, and audit logs if the environment has custom configurations.

Revoking new login access is primary, yet in a credential-compromise incident you must also audit tokens, private keys, data access permissions, and active sessions across the entire environment.

## 7. OS Login 2-Step Verification

### 7.1. Role of 2-Step Verification

**OS Login 2-step verification (OS Login 2FA)** adds a second identity verification step alongside supported SSH authentication. Its purpose is reducing risk if a private key or credential is compromised.

Prerequisites typically include:

- The user and account type support 2-step verification under Google Cloud/Cloud Identity.
- The account has an enrolled 2FA method compliant with organizational policy.
- The Linux VM and guest environment support OS Login 2FA.
- The SSH client flow can complete the interactive challenge; non-interactive/automated workflows face restrictions.

**Enabling 2FA metadata does not automatically make every principal type capable of passing the challenge.** Verify compatibility across identity type, VM image, and SSH tooling. For automation, use proper controlled deployment mechanisms rather than embedding personal private SSH keys in pipelines.

### 7.2. Configuration Example

~~~bash
# WRITE: enable OS Login and require OS Login 2FA at project level.
gcloud compute project-info add-metadata \
  --project=retail-prod \
  --metadata=enable-oslogin=TRUE,enable-oslogin-2fa=TRUE
~~~

To apply to an individual VM, use instance metadata with the same approach:

~~~bash
# WRITE: configure instance after confirming compatibility.
gcloud compute instances add-metadata checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --metadata=enable-oslogin=TRUE,enable-oslogin-2fa=TRUE
~~~

If the organization already enforces specific access policies, align with those rules. In production, test the full authentication flow with real users before rolling out broadly, and never remove approved recovery mechanisms.

## 8. Combining OS Login with IAP: SSH Without External IPs

### 8.1. Why Consider IAP TCP Forwarding?

A VM inside a private VPC can have **no external IPv4 address**. To let administrators SSH from external networks, **IAP TCP forwarding** creates an authorized TCP tunnel through the IAP service to the VM.

~~~mermaid
flowchart LR
    USER["Admin workstation"] --> IAM["IAM: IAP + OS Login roles"]
    USER --> T["IAP TCP forwarding"]
    T --> FW["VPC firewall: TCP 22 from IAP"]
    FW --> VM["Linux VM with internal IP only"]
    IAM -. "OS Login authorization" .-> VM
    VM --> SSH["sshd → Linux shell"]
~~~

IAP adds a **network path protection layer**; OS Login controls **who can log into the operating system**. Deploying both eliminates the need to expose TCP port 22 on VMs to the public Internet.

### 8.2. Prerequisites

| Item | Requirement |
| --- | --- |
| IAP API / config | Service and environment configured for IAP TCP forwarding. |
| IAP permission | Principal has IAP tunnel permission, typically `roles/iap.tunnelResourceAccessor` on the assigned scope. |
| OS Login permission | Principal has the right Linux login role and any applicable extra permissions. |
| Resource read permission | `gcloud` has permission to read VM metadata needed to establish the connection. |
| VPC firewall | TCP 22 allowed from the IAP TCP forwarding source range to the target VMs. |
| VM guest | Linux VM supports OS Login, `sshd` is running, and guest firewall does not block it. |
| User's Internet path | Admin workstation can reach the IAP service over HTTPS. |

For IPv4 IAP TCP forwarding, the firewall source range documented by Google Cloud is **`35.235.240.0/20`**. This range permits traffic from the IAP service to the VM—**it does not allow everyone on the Internet to SSH**: IAP IAM and OS Login checks remain mandatory. For IPv6 or specialized setups, consult current documentation for exact source ranges and mechanics.

### 8.3. Narrow Firewall Example for IAP SSH

Suppose the VM carries network tag `iap-ssh` in VPC `retail-vpc`. The following firewall rule is a **network-mutating example**:

~~~bash
# WRITE: create only when organization approved source, target, and scope.
gcloud compute firewall-rules create allow-iap-ssh \
  --project=retail-prod \
  --network=retail-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=iap-ssh
~~~

If a VM lacks the `iap-ssh` tag, this tag-based rule **does not apply** to that VM. In **Shared VPC** setups, firewalls belong to the host VPC/network and are managed in the right project. Beyond classic VPC firewall rules, hierarchical firewall policies, guest firewalls, or other rules may still block traffic.

Never open `0.0.0.0/0` to TCP 22 simply because the first IAP session failed. Troubleshoot layer by layer to keep the security model intact.

### 8.4. SSH via IAP Example

~~~bash
# READ/CONNECT: starts SSH session, does not grant IAM permissions.
gcloud compute ssh checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --tunnel-through-iap
~~~

The command may prompt interactively to create an SSH key or complete verification. It does not assign an external IP to the VM. With valid permissions and prerequisites, the user enters a VM shell under their OS Login-managed POSIX account.

`gcloud compute ssh` can also connect directly over other network paths when permitted. **Using IAP is a transport choice**, not a replacement for OS Login. If organizational policy requires all SSH to traverse IAP, ensure no unintended direct SSH paths remain open.

## 9. Structured IAM Provisioning Workflow

### 9.1. Read the Allow Policy Before Making Changes

~~~bash
PROJECT_ID="retail-prod"

# READ-ONLY: inspect IAM allow policy attached directly to the project.
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="yaml(bindings)"
~~~

This output does not show every **binding inherited from folders/organization**, instance-specific bindings, IAM deny policies, or other policy conditions. To determine effective permissions accurately, inspect ancestor scopes and active IAM policies too.

### 9.2. Example Granting OS Login to Operations Groups

The following commands modify live policy; run only with approval:

~~~bash
# WRITE: grant standard login at project level.
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-readers@example.com" \
  --role="roles/compute.osLogin"

# WRITE: grant OS administrative login to a controlled group.
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-maintainers@example.com" \
  --role="roles/compute.osAdminLogin"

# WRITE: grant IAP tunnel usage at project level (can be narrowed further).
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-iap-users@example.com" \
  --role="roles/iap.tunnelResourceAccessor"
~~~

This example uses **project scope** for clarity, yet in production consider narrower scopes and IAM Conditions when restricting by VM, IP, or time window. Never grant project-wide admin to a group that only needs SSH to one VM.

If the VM has an attached service account, check permissions required to act as that identity. When granting actAs on a specific service account is genuinely required:

~~~bash
# WRITE: grant on a specific service account, never on all service accounts.
gcloud iam service-accounts add-iam-policy-binding \
  vm-runtime@retail-prod.iam.gserviceaccount.com \
  --project=retail-prod \
  --member="group:vm-maintainers@example.com" \
  --role="roles/iam.serviceAccountUser"
~~~

`roles/iam.serviceAccountUser` is sensitive because it permits acting with the service account's identity across supported operations. Evaluate the permissions held by that service account first; never grant it blindly to fix an SSH error without confirming the resource and root cause.

### 9.3. Revoking and Verifying

~~~bash
# WRITE: revoke standard login binding at project level.
gcloud projects remove-iam-policy-binding retail-prod \
  --member="group:vm-readers@example.com" \
  --role="roles/compute.osLogin"
~~~

Removing one binding does not prove a user has lost all access, as direct bindings, other groups, or ancestor grants may remain. Verify effective permissions and other access paths, and terminate active sessions if immediate revocation is required.

## 10. Deployment Scenario: Production Retail System

Suppose an organization runs:

- An ordering API on **Cloud Run**.
- **Cloud SQL** storing transactional data.
- **Cloud Storage** holding images and static assets.
- Several **Compute Engine Linux VMs** running data-sync jobs and incident-investigation tools.
- **GKE** running other workloads with its own node management procedures.
- A **production VPC** assigning no external IPs to regular administrative VMs.

Security wants users to SSH only into assigned VMs, only operations engineers to have `sudo`, and all maintenance connections to traverse IAP.

### 10.1. Designing Permissions by Responsibility

| Persona | Need | Recommended permissions / approach |
| --- | --- | --- |
| App dev team | Read logs and check service status on relevant VMs. | Standard OS Login scoped to assigned VMs; separate Cloud Logging viewer roles if needed. |
| Sysadmin team | Install patches, restart services, perform approved troubleshooting. | `osAdminLogin` in assigned scope, with approval workflow and auditing. |
| Security team | Audit who can SSH and inspect metadata configs. | Read roles for IAM/policies/assets; root shell access is not required. |
| CI/CD | Deploy apps via managed automation. | Dedicated deployer/workload identity; avoid personal SSH private keys. |
| On-call support | Connect to VMs without external IPs during incidents. | IAP tunnel access + appropriate OS Login + VM view permissions. |

**Never grant a Cloud Run service account `osAdminLogin` merely because the app calls Cloud SQL.** VM OS administration permissions are completely separate from database connectivity or Cloud Storage object access. Separating **machine admin**, **deployment**, and **runtime** identities limits blast radius if credentials leak.

### 10.2. Operator Access Flow

~~~mermaid
sequenceDiagram
    participant E as On-call engineer
    participant I as IAM / IAP
    participant V as Compute Engine VM
    participant O as OS Login / Linux
    E->>I: gcloud compute ssh --tunnel-through-iap
    I->>I: Verify tunnel permissions
    I->>V: Open TCP tunnel to port 22
    E->>O: SSH authentication and OS Login
    O->>O: Verify identity / login privileges
    O-->>E: Standard shell or admin rights per role
~~~

In practice, SSH authentication, OS Login lookups, and tunneling involve multi-step protocol interactions. The diagram highlights the core separation: **IAP governs the network entry path**, while **OS Login governs Linux login and privileges**.

### 10.3. Onboarding and Offboarding Workflows

**Onboarding:**

1. Manager confirms which VMs need access and the specific task.
2. Add user to the standard or admin OS Login group as appropriate.
3. Grant IAP permissions at the proper scope, checking VM read access and any service account requirements.
4. Confirm the user has enrolled a valid 2FA method if required by policy.
5. Test login from an authorized network path and record the granted scope.

**Offboarding or Role Change:**

1. Remove group membership or relevant bindings.
2. Check for remaining bindings at project, instance, and ancestor levels.
3. Handle SSH keys and active sessions per revocation requirements.
4. Audit changes made on VMs if the user previously held `sudo`.
5. Record completion date and verifier.

For sensitive production access, organizations can adopt **time-bound privileged access** with approval workflows instead of leaving `osAdminLogin` active indefinitely.

## 11. Safe SSH Verification and Monitoring

### 11.1. Read-Only Verification Suite

~~~bash
# Inspect project/instance metadata.
gcloud compute project-info describe \
  --project=retail-prod \
  --format="yaml(commonInstanceMetadata.items)"

gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(name,networkInterfaces,metadata.items,serviceAccounts)"

# Inspect OS Login profile of the active gcloud identity.
gcloud compute os-login describe-profile

# Inspect direct IAM bindings on the project.
gcloud projects get-iam-policy retail-prod \
  --format="yaml(bindings)"

# List firewall rules to verify IAP path to the VM.
gcloud compute firewall-rules list \
  --project=retail-prod
~~~

In Shared VPC, firewall rules must be inspected in the **host project owning the network**. These commands only show configurations and permissions visible to the current identity; to confirm live access, still test connecting with the intended principal and analyze all effective policies.

### 11.2. Which Log Answers Which Question?

| Source | Questions it helps answer |
| --- | --- |
| **Cloud Audit Logs** for IAM/Compute Engine metadata changes | Who modified bindings, metadata, or managed resources, and when? |
| **OS Login API logs**, per logged activity types and logging config | Were there profile/SSH key management actions or OS Login API calls? |
| **IAP audit/telemetry** within supported scope | Who used IAP TCP forwarding, and were there tunnel access-control errors? |
| **VM Linux auth logs/journald** | Did `sshd` accept or reject the login? Which Linux account and source address appeared? |
| **VM Cloud Logging/Monitoring**, if configured | Are logs and alerts centralized so troubleshooting doesn't require routine SSH? |

Not every source logs every event automatically or shares identical retention. Verify Audit Logs enablement by log type, storage location, access controls, and retention policies. Investigating a failed SSH session often requires correlating **IAP logs** with **guest OS SSH logs**.

### 11.3. Measuring Administrative Path Reliability

Useful internal metrics:

- Percentage of production Linux VMs with OS Login enabled per baseline.
- Ratio of admin connections using IAP vs. direct SSH when policy mandates IAP.
- Number of users and groups holding `osAdminLogin`; expiration status of elevated grants.
- Time-to-revoke access when personnel change teams or leave the organization.
- SSH failure rates broken down by IAM, IAP, network, or SSH daemon.
- Completeness of audit logs and emergency access procedures.

The goal is **minimizing excess privilege while preserving incident-response capability**. If security controls leave on-call engineers with zero valid recovery paths when IAP or IAM experiences issues, the design has not balanced risk and reliability.

## 12. Layer-by-Layer Troubleshooting

### 12.1. Diagnostic Matrix

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| `Permission denied (publickey)` | SSH key missing from OS Login profile, insufficient OS Login IAM, guest OS misconfigured, or wrong username. | Inspect profile/keys, IAM roles, guest environment, and auth logs. |
| `403` when creating IAP tunnel | Missing tunnel role, IAM Condition failed, or IAP API/policy denied. | Verify principal, target resource, and IAP bindings. |
| IAP tunnel connects but SSH times out | Firewall to TCP 22, guest firewall, `sshd`, or route/network unreachable. | Check IAP source range, network tags, port, and guest logs. |
| Has OS Login role yet denied on VM with service account | Possibly missing extra permission to use the service account per access flow. | Inspect VM `serviceAccounts` and check `iam.serviceAccounts.actAs` requirements. |
| Logs in successfully but cannot `sudo` | Only holds `roles/compute.osLogin`, lacks admin role, or OS policy restricts it. | Check effective IAM roles and sudo policy. |
| Failure after enabling `enable-oslogin=TRUE` | VM previously relied on metadata SSH keys, missing IAM, or incompatible guest environment. | Compare metadata, roles, guest logs; execute recovery plan if needed. |
| User has project role yet VM denies access | Instance metadata, IAM Conditions, deny policies, or unexpected role scope. | Inspect effective policies in ancestors and on the VM. |
| OS Login 2FA fails repeatedly | Account lacks enrolled valid 2FA method, unsupported workflow, or incompatible guest image. | Check support docs for account/image type and test interactively. |
| SSH works directly even though IAP is required | External IP, ingress firewall, or bastion path left open. | Audit IPs, ingress rules, actual access paths, and network policies. |
| Still cannot log in after re-granting role | Network/SSH daemon issue, IAM propagation delay, or key/session issue. | Trace DNS/IP → IAP → TCP 22 → SSH auth → OS Login. |

### 12.2. Short Investigation Procedure

1. **Right VM?** Confirm project ID, zone, instance name, and internal/external IP.
2. **Right principal?** Run `gcloud auth list` for CLI identity; verify the real user/automation identity and granted roles.
3. **Path to TCP 22?** When using IAP, check IAP role, network, firewall, and `--tunnel-through-iap`.
4. **How is OS Login enabled?** Inspect project metadata, instance metadata, and organization policies.
5. **Right OS Login role?** Distinguish standard login, admin login, and any extra conditions.
6. **SSH key/profile valid?** Verify public key, expiration, POSIX username, and which key the client offers.
7. **Guest OS accepting connections?** Check `sshd`, Linux auth logs, and guest environment health.
8. **Retry with minimal scope:** connect from a test identity, recording exact errors and timestamps to correlate logs.

Avoid "quick fixes" like granting `roles/owner`, `roles/editor`, attaching external IPs, or opening `0.0.0.0/0` to TCP 22. Those changes increase risk while masking the original root cause.

### 12.3. Administrative Recovery Plan

When enabling OS Login or 2FA in production, infrastructure teams should maintain a **break-glass runbook**:

- Who is authorized to approve emergency access and how independent verification works.
- Scope of VMs/projects covered, trigger conditions, and expiration of temporary grants.
- How to verify guest environment, metadata, and IAM when standard SSH fails.
- Organization-approved management tools to repair configuration if SSH is unavailable.
- Post-incident audit and review.

Never assume "we can always use the serial console" in every environment: serial access carries its own security constraints, IAM permissions, and policies. Design fallback paths using tools actually enabled and governed by your organization.

## 13. Practice Exercises

### Exercise 1 — Choosing Roles

Three people need access to the same production Linux VM:

1. A developer who only needs to read application logs.
2. An SRE authorized to update OS config and run `sudo`.
3. An auditor who only reviews who has access, without entering a shell.

**Hint:** person (1) starts with `roles/compute.osLogin` and appropriate Linux file read permissions; person (2) considers `roles/compute.osAdminLogin` within approved scope and duration; person (3) uses appropriate IAM/audit viewer roles, without OS Login.

### Exercise 2 — Designing SSH Without External IPs

VM `checkout-worker-01` has no external IPv4 address and runs in VPC `retail-vpc`. List the requirements for an engineer to SSH via IAP.

**Hint:** IAP API/tunnel, `roles/iap.tunnelResourceAccessor`, OS Login role, VM read permissions, OS Login metadata, firewall allowing TCP 22 from IAP's source range to the VM, `sshd`, and a valid identity/SSH key. If the VM has an attached service account, verify additional IAM requirements.

### Exercise 3 — Reading Metadata

Run these **read-only** commands:

~~~bash
gcloud compute project-info describe \
  --project=retail-prod \
  --format="yaml(commonInstanceMetadata.items)"

gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(metadata.items)"
~~~

**Question:** if the project has `enable-oslogin=TRUE` while instance metadata has `enable-oslogin=FALSE`, what else must you check to determine the effective OS Login state? Why should you not rely on changing instance metadata when an organization policy enforces OS Login?

### Exercise 4 — The `publickey` Error

A user has permission to SSH through IAP yet receives `Permission denied (publickey)`. Describe how to separate **IAP succeeding** from **OS Login/SSH key rejection**, including checking profile public keys, username, and guest auth logs.

### Exercise 5 — Revoking Access

An engineer leaves the SRE team after holding `osAdminLogin` via a group and opening an SSH session to a VM. Outline the workflow to revoke access, check remaining bindings, handle active sessions, audit logs, and confirm no alternate access paths remain.

### Exercise 6 — Assessing Impact on CI/CD

A legacy deployment script SSHs into VMs using a key stored in project metadata. The platform team wants to enable OS Login project-wide. Propose a migration plan: inventory scripts, select appropriate deployment identities/mechanisms, test permissions, roll out in nonproduction, check logs/rollback, and constrain automation privileges.

## 14. Production Rollout Checklist

| Item | What to verify |
| --- | --- |
| **Image and guest environment** | Linux image supports OS Login with compatible SSH daemon/PAM/NSS. |
| **Project/instance metadata** | `enable-oslogin`, `enable-oslogin-2fa` values and override behavior properly understood. |
| **Organization Policy** | Presence/absence of OS Login enforcement constraint; policies and exceptions managed. |
| **Principals and roles** | Standard login, OS admin, IAP user, and automation identities clearly separated. |
| **VM service account** | Extra permissions checked if required, avoiding overly broad grants. |
| **SSH keys** | Private keys protected; public keys/profiles and key lifecycle/revocation governed. |
| **2-step verification** | Identity types, images, and workflows compatible; tested end-to-end. |
| **SSH path** | External IP/IAP, ingress TCP 22, exact network target, guest firewall, and routes verified. |
| **Logging/auditing** | IAM, OS Login, IAP, and Linux auth logs monitored with sensible retention. |
| **Automation** | Metadata and IAM managed via IaC/review; no personal SSH keys stored in pipelines. |
| **Recovery** | Break-glass runbook, accountable owners, and tested recovery plan exist. |
| **Cost/reliability** | VMs, logging, connectivity paths, recovery times, and access scope monitored. |

## 15. Official Documentation and Key Takeaways

OS Login, 2-step verification support, IAM roles, IAP, and authentication options may evolve across service and guest image versions. When deploying on Google Cloud, verify current documentation:

- [OS Login overview](https://cloud.google.com/compute/docs/oslogin)
- [Set up OS Login](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin)
- [Set up OS Login with 2-step verification](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin-2fa)
- [Connect to Linux VMs using IAP](https://cloud.google.com/compute/docs/connect/ssh-using-iap)
- [IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [SSH best practices for Compute Engine](https://cloud.google.com/compute/docs/connect/ssh-best-practices)
- [Understanding IAM roles](https://cloud.google.com/iam/docs/understanding-roles)
- [Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [gcloud compute os-login reference](https://cloud.google.com/sdk/gcloud/reference/compute/os-login)

**OS Login places Linux login permissions under the IAM model; IAP provides a controlled SSH tunnel path; VPC firewalls decide whether network traffic passes.** By separating responsibilities cleanly across each layer, you can govern VM access by group, separate `sudo` from standard login, revoke access systematically, and preserve incident-response capabilities without exposing SSH to the entire Internet.
