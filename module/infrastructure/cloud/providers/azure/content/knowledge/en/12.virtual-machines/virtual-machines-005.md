# Managing SSH, RDP, and Secure Administrative Access

An engineering team operating Azure Virtual Machines (VMs) often needs to sign into Linux machines via SSH or Windows machines via Remote Desktop Protocol (RDP) to update software, inspect logs, and troubleshoot incidents. Opening ports 22 or 3389 directly to the Internet and allowing any IP to attempt sign-in turns a VM into a target for port scanning, password brute-forcing, and vulnerability exploitation. Conversely, locking down all access without preparing a recovery path can lock operations teams out when urgent troubleshooting is needed.

This lesson guides you through designing **secure, controlled, and auditable administrative access paths** for both Linux and Windows VMs on Microsoft Azure. Key topics include SSH keys, RDP, Azure Bastion, private network connectivity, Network Security Groups (NSGs), Just-in-Time (JIT), Microsoft Entra ID, Azure RBAC, recovery procedures when connectivity is lost, and long-term operations.

This lesson belongs to the **Azure Virtual Machines** chapter of the `CLOUD_PROVIDERS_AZURE` module. In this module, you explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data, while learning how to deploy, monitor, protect, and control the cost of an Azure application architecture. VM access decisions must align consistently with networking, identity, monitoring, and system-wide requirements.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **SSH**, **RDP**, **Azure Bastion**, **VPN/ExpressRoute**, and direct public IP access.
- Explain why VMs should use **private IPs**, restrict management paths, and avoid exposing management ports broadly to the Internet.
- Generate **SSH public/private key pairs** and handle private keys securely.
- Identify RDP configurations, Network Level Authentication (NLA), firewalls, and Windows sign-in permissions.
- Apply Azure RBAC and Microsoft Entra ID for VM administration, distinguishing Azure resource permissions from OS-level permissions.
- Design NSGs, JIT, and role assignment workflows for least-privilege, time-bound access.
- Verify SSH/RDP connectivity using the Azure Portal, Azure CLI, and non-destructive diagnostic commands.
- Create runbooks for unreachable VMs and suspected credential compromise.
- Select approaches balanced across risk, availability, and operational cost.

## 2. How Do SSH and RDP Work?

### SSH for Linux and SSH-Enabled Systems

**Secure Shell (SSH)** establishes an encrypted administrative session between a client and a server. On Linux VMs, SSH typically uses TCP **22**. Connections can authenticate with public keys, passwords, or extended server-supported authentication mechanisms.

```text
Admin workstation        SSH connection            Linux VM
SSH client   ===================================> sshd :22
  |                                                  |
  |-- verify server host key                         |
  |-- authenticate user via key/identity             |
  |-- open terminal or permitted forwarding channel  |
```

SSH's strength lies in terminal flexibility and automation. However, an encrypted session **does not automatically ensure security** if the private key leaks, clients skip host key verification, the server allows weak authentication, or the network exposes port 22 to every source.

### RDP for Windows

**Remote Desktop Protocol (RDP)** provides a remote desktop session and Windows administrative tooling. Windows VMs typically use TCP **3389**; some deployments involve additional protocol components depending on configuration.

```text
Admin workstation          RDP connection            Windows VM
Remote Desktop Client  ===========================> RDP service :3389
  |                                                     |
  |-- authenticate and verify certificate/host          |
  |-- check NLA, logon rights                           |
  |-- open Windows session if permitted                 |
```

**Network Level Authentication (NLA)** requires early authentication before establishing a full Remote Desktop session, reducing part of the attack surface. NLA does not replace MFA, OS patching, or source network restrictions.

### Distinguishing VM Sign-In from Azure Resource Management

Someone who can click **Start/Stop VM** in the Azure Portal is not necessarily able to sign into the Linux/Windows guest. Conversely, a local administrator account inside the VM cannot automatically create/delete VMs, edit NSGs, or access Key Vault in Azure. These are **two separate permission boundaries**.

| Layer | Example permissions | Controlling system |
|---|---|---|
| **Azure control plane** | Read VM metadata, start/stop VMs, edit NIC/NSG, attach extensions. | Azure RBAC and Azure Resource Manager. |
| **OS sign-in** | SSH with a Linux account, RDP with a Windows account, sudo/Administrators privileges. | Operating system and configured auth/authorization mechanisms. |
| **Network connectivity** | TCP to private IP on port 22/3389. | VNet, routes, NSGs, firewalls, and VPN/Bastion path. |
| **Application resources** | Read databases, file shares, Azure Storage. | Data-plane RBAC, applications, and separate policies. |

For sign-in to succeed, **identity permissions, network routing, and the guest OS service** must all align.

## 3. Threat Model and Protection Principles

Common risks for VM administrative access:

1. **Internet port scanning:** public IPs with open TCP 22/3389 face continuous automated probing.
2. **Password brute-forcing / credential stuffing:** accounts using weak or reused passwords.
3. **SSH private key leakage:** attackers use stolen keys to sign in.
4. **Abuse of standing high-privilege accounts:** permanent Owner/Contributor or local admin access.
5. **Compromised admin workstations:** SSH/RDP sessions can be hijacked despite encrypted transport.
6. **Lateral movement:** pivoting from one compromised VM to many others via shared passwords/keys or overly broad network rules.
7. **Loss of recovery:** overly strict NSGs, broken sshd, blocking Windows Firewall, or rotated keys without a fallback path.

Apply these principles:

- **Private-first:** prefer VMs without public IPs, accessed over a controlled management channel.
- **Least privilege:** grant only required rights in Azure and inside the guest OS.
- **Strong authentication:** use SSH keys/appropriate identities; enforce MFA and Conditional Access on identity entry points where supported.
- **Just-in-time:** open ports or elevate privileges only for the required window.
- **Defense in depth:** networking, identity, OS hardening, logging, and key management reinforce one another.
- **Auditable access:** record who administered what, when, what changed, and sign-in events.
- **Recoverability:** prepare incident recovery paths without opening all ports to the Internet.

## 4. VM Administrative Access Paths on Azure

| Option | Connection path | Benefits | Limitations / considerations |
|---|---|---|---|
| **Azure Bastion** | Admin via Portal or supported client → Bastion → VM private IP. | No public IP needed on VM; centralized entry point, Azure-integrated. | Bastion cost, RBAC, subnet/SKU setup, and connectivity prerequisites. |
| **Point-to-site VPN** | Admin workstation → VPN → VNet → VM private IP. | Private access for remote engineers using familiar SSH/RDP clients. | Managing VPN clients, identities, routes, and endpoints. |
| **Site-to-site VPN/ExpressRoute** | Corporate network → hybrid connection → VM private IP. | Suits offices/data centers with centralized network controls. | Link cost, routing, DNS, and redundancy. |
| **Jump host / privileged access workstation** | Trusted device → controlled intermediary → VM. | Can integrate session recording workflows and admin tooling. | Jump host itself requires hardening, monitoring, patching, and protection. |
| **Public IP + NSG/JIT** | Approved admin IP → Internet → VM. | Can cover time-limited exceptions. | Exposed to Internet; requires strict source/time limits and should not be the default. |

**Default recommendation for Production VMs:** keep VMs **without public IPs** inside private subnets, managed through **Azure Bastion** or an approved private connection. If a public IP is unavoidable, require business justification, strict source/time/access limits, and a plan to retire direct exposure.

Do not confuse guest VM SSH/RDP ports with application-serving ports. A web server may need HTTPS 443 from Application Gateway, yet **never needs 22/3389 from the Internet**.

## 5. Illustrative Private Administration Architecture

Suppose an application runs in VNet `10.80.0.0/16`:

```text
                               Microsoft Entra ID
                                      |
                               RBAC / MFA / PIM
                                      |
Administrator -- Azure Portal --> Azure Bastion
                                      |
                      VNet: 10.80.0.0/16
                            |
                AzureBastionSubnet: 10.80.0.0/26
                            |
                      Private VM subnets
                    /                      \
            snet-linux                  snet-windows
             10.80.1.0/24                10.80.2.0/24
                 |                           |
           Linux VM                     Windows VM
           10.80.1.10                   10.80.2.10
          SSH TCP:22                    RDP TCP:3389
           no public IP                  no public IP
```

In this diagram:

- Bastion serves as the administrative entry point through Azure infrastructure per supported SKU/features.
- VMs retain private-only IPs; no public NAT/port forwarding is needed for SSH or RDP.
- NSGs on VM subnets/NICs permit management ports only from approved sources, such as the `AzureBastionSubnet` range, rather than `0.0.0.0/0`.
- Application-serving ports and administrative ports are governed by separate rules.
- Both Portal/Bastion permissions and guest OS sign-in permissions must be verified.

**Azure Bastion does not replace authorization inside the VM.** A user permitted to open the connection interface must still authenticate via the configured SSH/RDP method, unless full identity integration is configured.

## 6. Azure Bastion: Administration Without VM Public IPs

**Azure Bastion** is a PaaS service for opening SSH/RDP sessions to VMs over private IPs. Administrators can connect from the Azure Portal via a browser; certain SKUs support **native clients**, tunneling, shareable links, session recording, or additional capabilities. Do not assume every SKU supports all features.

### Components to Prepare

1. **Target VNet** hosting the VMs or connected via a service-supported topology.
2. Dedicated subnet named exactly **`AzureBastionSubnet`**, typically requiring **/26 or larger for current Bastion deployments**, depending on SKU and service limits.
3. Azure Bastion resource with SKU-appropriate frontend and connection configuration.
4. Network path from Bastion to the guest VM's private IP and TCP 22/3389.
5. Azure RBAC permissions to view/use Bastion, the VM, and related network resources per Portal flow.
6. Guest OS sign-in method: SSH key/identity, Windows account, or Microsoft Entra integration if supported.

Different SKUs have different requirements regarding **Bastion's own public IP**. Commonly Bastion uses an Azure-managed frontend public IP, while **target VMs still need no public IP**. Private-only Bastion setups have specific SKU/design requirements; verify before selecting.

### Creating Bastion via the Azure Portal

1. Open **Virtual networks** and select the VNet containing the VMs or appropriate management network.
2. Create a subnet named `AzureBastionSubnet` with a non-overlapping CIDR meeting the SKU minimum size.
3. Open **Bastions** and create the resource in the matching subscription/resource group/region.
4. Choose the SKU, VNet, subnet, and frontend IP per approved design.
5. Configure NSGs on the Bastion subnet and VM subnet per **Bastion's required rules**; do not merely open 22/3389 while ignoring Bastion's control/management traffic requirements.
6. Wait for deployment completion and verify the target VMs need no public IP.

### Connecting to a Linux VM

1. Open Azure Portal → **Virtual machines** → select the Linux VM.
2. Select **Connect → Bastion** or the corresponding option.
3. Choose an environment-supported authentication method, e.g., SSH private key or integrated identity.
4. Confirm the target VM, Linux username, and connection.
5. Document administrative actions and close the session when finished.

### Connecting to a Windows VM

1. Open the Windows VM → **Connect → Bastion**.
2. Choose a supported authentication mode (Windows credentials or Entra-based login if fully configured).
3. Verify the account holds Remote Desktop logon rights in Windows.
4. Perform administrative tasks and sign out cleanly.

**Never share private keys or passwords over chat, tickets, or training docs.** When a connection workflow prompts for credentials, use organization-approved secure interfaces and processes.

### Bastion Is Not a “Turn It On and Forget It” Fix

Failures can still happen:

- NSGs on the Bastion or VM subnet block required traffic.
- Windows Firewall or `sshd` blocks connections inside the guest.
- The VM is stopped, the OS failed to boot, or the NIC is unhealthy.
- The user lacks Azure RBAC rights on Bastion/VM or lacks guest logon rights.
- The selected SKU lacks native client, tunneling, or required features.
- VNet peering/routes or DNS fail prerequisites when VMs live in another network.

**Cost:** Bastion incurs charges by SKU, runtime, and related components. In labs, clean up resources after practice; in Production, consider a centralized Bastion aligned with architecture and connectivity requirements.

## 7. Secure SSH Key Management for Linux VMs

**SSH public-key authentication** is generally the preferred choice for Linux VMs when not using Microsoft Entra login. Each engineer should have an individual key pair—never share one private key across an entire team.

### Generating an SSH Key

Example generating a 4096-bit RSA key pair on an authorized admin workstation:

```bash
ssh-keygen -t rsa -b 4096 \
  -C "azure-admin-workstation" \
  -f ~/.ssh/azure_vm_admin
```

This creates:

- `~/.ssh/azure_vm_admin`: the **private key**—never disclose it.
- `~/.ssh/azure_vm_admin.pub`: the **public key**—safe to register on target systems for authentication.

When prompted, protect the private key with a **strong passphrase** and manage it using an SSH agent or appropriate secret manager. Where hardware-backed keys are supported, consider alternative key types depending on SSH client, OS, and deployment tooling support.

**Never store private keys in Git repositories or unmanaged cloud storage.** Only the public key is provisioned onto VMs through authorized processes.

### Registering a Public Key for a Linux Account

When creating a Linux VM, select SSH public key authentication via Portal/CLI. For existing VMs, adding a new key requires authorization and an active admin path; the public key is placed in `~/.ssh/authorized_keys` for the target user if the SSH server uses that mechanism.

On Linux, wrong permissions can cause `sshd` to ignore keys. Common permissions:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

These run inside the **guest OS**, not in the Azure Portal. Verify file ownership, user context, SELinux/AppArmor, and `sshd` configuration per distro. Never blindly run bulk permission changes without verifying the exact machine and directory.

### Connecting via Private IP

If your workstation **already has private network connectivity to the VNet**, e.g., over VPN:

```bash
ssh -i ~/.ssh/azure_vm_admin azureuser@10.80.1.10
```

Without a VPN, Bastion, native tunnel, or private route, this command **cannot traverse the Internet on its own**. `10.80.1.10` is merely an RFC 1918 example.

When SSH displays a new host fingerprint, **verify the host key over a trusted channel** before accepting. If a host key change warning appears unexpectedly, do not bypass verification blindly; the VM may have been legitimately rebuilt, or you could be reaching the wrong machine or an intercepted endpoint.

### Hardening `sshd` Configuration

Common hardening measures to evaluate:

- Reduce or disable password authentication **after** verifying key-based/Entra login and recovery paths work.
- Restrict direct `root` login; use named accounts with least-privilege `sudo`.
- Revoke keys of personnel who switch teams or leave the organization.
- Keep the OS and OpenSSH patched.
- Restrict source IPs in both **NSGs and the guest firewall**.
- Log successful/failed authentication attempts and alert on anomalies.
- Never copy one shared private key across multiple VMs/engineers when identity-based access or individual keys are feasible.

Avoid editing `sshd_config`, restarting `sshd`, or disabling password auth on Production VMs **before testing a second active session** and ensuring Bastion/Serial Console/Run Command recovery works.

## 8. RDP on Windows VMs: Accounts, NLA, and Access Policies

RDP provides a full desktop convenient for Windows administration, yet introduces risk if port 3389 is exposed or accounts use weak passwords.

### Baseline Configuration Checks

| Factor | Verification |
|---|---|
| Remote Desktop | Enabled only when needed and aligned with organizational policy. |
| **NLA** | Enabled where clients and authentication configuration are compatible. |
| Logon rights | Account belongs to a group/role permitted for Remote Desktop logon; not every Azure user gets it automatically. |
| Windows Firewall | Allows RDP on the appropriate profile without overly broad scopes. |
| NSG | Allows TCP 3389 solely from the Bastion subnet or trusted admin networks. |
| Patching | OS, Remote Desktop Services, and authentication components are up to date. |
| Logging | Windows Security events and Remote Desktop logs are monitored. |
| Certificates/identity | Server verification mechanisms and appropriate auth policies are in place. |

### Connecting via RDP over VPN / Private Network

If your admin workstation has authorized private connectivity to the VNet:

```powershell
mstsc /v:10.80.2.10
```

On Windows, `mstsc` launches Remote Desktop Connection to the private IP. This command does not create a VPN or bypass NSGs/Windows Firewall; routing, permissions, and the RDP service must all be active.

Test TCP connectivity from a Windows client:

```powershell
Test-NetConnection -ComputerName 10.80.2.10 -Port 3389
```

A `True` TCP result only shows the port accepts connections under test conditions; **it does not prove** the account has logon rights or that NLA/certificates are valid.

### Do Not Disable NLA as a “Quick Fix”

If RDP fails with an NLA, certificate, or account error, check:

1. Account type in use (local, domain, or Microsoft Entra).
2. Time sync, name resolution, and domain/identity health if applicable.
3. Remote Desktop logon rights in Windows and local/group policy settings.
4. RDP service status, Windows Firewall, and NSG rules.
5. Availability of Bastion/Serial Console or approved recovery tools.

Disabling NLA or opening port 3389 to the entire Internet to troubleshoot increases exposure; apply only policy-compliant fixes with an approved rollback plan.

## 9. Network Security Groups: Restricting the Right Sources

A **Network Security Group (NSG)** filters network traffic at Azure's subnet or NIC scope. NSG rules evaluate direction, protocol, source/destination, port, and **priority**. Lower priority numbers are evaluated first within the rule set.

Example VM policy:

| Rule logic | Source | Destination | Port | Result |
|---|---|---|---|---|
| Allow SSH from Bastion | `10.80.0.0/26` | `snet-linux` | TCP 22 | Allow |
| Allow RDP from Bastion | `10.80.0.0/26` | `snet-windows` | TCP 3389 | Allow |
| Allow SSH from admin VPN | Approved admin workstation range | Linux VM/subnet | TCP 22 | Allow if needed |
| Allow RDP from admin VPN | Approved admin workstation range | Windows VM/subnet | TCP 3389 | Allow if needed |
| Deny public admin | Unauthorized sources | Managed VMs | TCP 22/3389 | Deny by design |
| App traffic | Valid app/load balancer sources | Application ports | Per service | Allow |

Azure NSGs include default rules covering VirtualNetwork traffic and denying other inbound traffic. When designing explicit allow/deny rules, **inspect effective security rules** on both the subnet and NIC along with actual routing. Never glance at a single rule and assume public sources are blocked.

### Three Common NSG Misconfigurations

**Mistake 1: Opening SSH/RDP to all sources**

```text
Source:      0.0.0.0/0
Destination: VM public IP
Port:        22 or 3389
Action:      Allow
```

Such a rule creates a massive attack surface. With a public IP and valid routing, Internet attackers will probe it continuously. Never use this as a Production default.

**Mistake 2: Overly broad Allow using `VirtualNetwork`**

The `VirtualNetwork` service tag can encompass broad address spaces considered part of the virtual network under Azure's routing model, not just authorized admin machines. For sensitive management ports, specify exact source prefixes and verify paths, especially with peering or hybrid routes.

**Mistake 3: Blocking required Azure Bastion traffic**

An NSG on `AzureBastionSubnet`, if attached, must satisfy the specific rules required by the Bastion service, including control/signaling traffic and connectivity to VMs per current documentation. Do not blindly copy a VM NSG onto the Bastion subnet while omitting platform prerequisites.

### NSGs Do Not Authenticate User Identity

NSGs only inspect network attributes—they do not know who holds an SSH key or who is logging into RDP. Therefore, **NSGs + identity + guest OS policies** must work together. Traffic coming from a valid VPN could still originate from a compromised admin workstation.

## 10. Just-in-Time VM Access (JIT)

**Just-in-Time (JIT) VM access** is a security capability that governs when management ports open for a VM, typically via Microsoft Defender for Cloud with an eligible plan/feature. It reduces port exposure duration, especially when direct network administration is occasionally required.

Example workflow:

1. VM management ports are restricted or closed under baseline policy.
2. An authorized user submits a JIT request specifying the VM, port, source IP/range, and duration.
3. The system applies a temporary rule via the supported mechanism.
4. The administrator connects within the approved time window.
5. Once expired, access through that path reverts to policy restrictions.

JIT requires compatible features and permissions; availability can depend on **Defender for Servers plans**, NSGs/Azure Firewall, and environment setup. Do not assume JIT is included for free in every subscription.

### Does JIT Replace Bastion?

No. JIT primarily **shrinks the open-port time window**; it does not provide a dedicated private channel, re-encrypt RDP, or render a public IP harmless. For VMs with no public IP, Bastion/VPN is usually a cleaner primary access model. JIT can complement appropriate designs, provided conflicts and operational complexity are evaluated.

## 11. Microsoft Entra ID and Azure RBAC for VM Login

Azure supports **Microsoft Entra ID** guest OS login on eligible Linux and Windows VM versions. When properly deployed, users authenticate with organizational identities instead of managing local accounts and SSH keys across every VM.

### Common Login Roles

| Azure RBAC role | Primary purpose |
|---|---|
| **Virtual Machine User Login** | Allows users to sign into VMs via Microsoft Entra with standard user privileges, where supported. |
| **Virtual Machine Administrator Login** | Allows sign-in via Microsoft Entra with administrative privileges, where supported. |
| **Reader** | Reads resource metadata; may be needed alongside login roles in some Portal/Bastion/client flows. |
| **Virtual Machine Contributor** | Manages Azure VM resource properties; **does not grant guest OS sign-in by default**. |

Assign `Virtual Machine Administrator Login` at the narrowest appropriate scope, such as the VM or the owning team's resource group. Never grant it subscription-wide merely for initial setup convenience.

### Prerequisites Before Using Entra Login

Depending on OS and features:

- The VM runs a supported OS/image.
- The appropriate **VM extension** or Entra auth component and required identity settings are configured.
- The VM can reach required identity endpoints or has compatible network paths.
- The user holds the login role at the right scope and is not blocked by Conditional Access/tenant policies.
- Clients and connection commands support Entra authentication.
- On Windows, device join/registration state, RDP/NLA, and client support can affect login behavior.

Example for Linux using Azure CLI with Microsoft Entra SSH support:

```bash
az ssh vm \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<LINUX_VM_NAME>"
```

This works only when Entra SSH prerequisites, CLI/extension setup, permissions, and network reachability align. Installing the Azure CLI SSH extension may be required per environment procedures. **It does not bypass NSGs or turn a private IP into an Internet-routable endpoint.**

### Role of MFA and Conditional Access

When users sign in via Microsoft Entra, MFA and Conditional Access policies can apply per supported flow. However:

- Signing into the **Azure Portal** with MFA **does not automatically enforce MFA** on SSH sessions using local keys or RDP sessions using local passwords.
- Remaining guest OS accounts with weak passwords can still offer a bypass if network rules permit.
- Retire unnecessary local accounts/login paths cleanly while maintaining a documented break-glass plan.

**Privileged Identity Management (PIM)**, when available and licensed, can gate VM login roles with time limits, approvals, and MFA. It adds an identity governance layer rather than replacing network controls.

## 12. Azure Bastion, VPN, and Jump Hosts: Choosing for Operations

Organizations often combine access paths to balance security, cost, and availability:

| Scenario | Preferred option | Rationale |
|---|---|---|
| Few VMs in a VNet, admins use the Portal | Azure Bastion | No VM public IPs and minimal self-managed infrastructure. |
| Many VMs, ops team uses terminal/scripts from standard admin workstations | VPN or Bastion native client if SKU supports | Private connectivity with familiar SSH/RDP tooling. |
| Multiple on-premises sites connecting to Azure | S2S VPN / ExpressRoute with network controls | Centralized on corporate network; requires clear routing/NSGs. |
| Privileged sessions must be recorded via a PAM platform | Jump host/bastion or compatible PAM solution | Ties sessions to identity, approvals, and audit logging. |
| Emergency incident when VPN is down | Azure Bastion or another approved recovery path | Management path independent of office network links. |
| Lab VM using a temporary public IP | NSG source restriction + JIT if available | Strictly time-bound; remove after lab completion. |

For self-managed jump hosts, you must harden the OS, patch regularly, protect identities, and log **the jump host itself**. If compromised, attackers can pivot from that central network position to reach many VMs.

When using VPN/Bastion for private VMs, verify **return routes**, DNS, and firewalls on both ends. A VPN tunnel showing “Connected” does not guarantee SSH/RDP flows end to end.

## 13. Secure Deployment Workflow in the Azure Portal

### Phase A: Design Before Creating VMs

1. Identify whether the VM serves Production, Development, or a test environment.
2. Choose VM subnets and separate administrative subnets/infrastructure.
3. Set a policy of **no default public IP** on VM NICs.
4. Select an approved management path: Bastion, VPN, or hybrid private connectivity.
5. Map user groups needing SSH/RDP and their permitted actions.
6. Choose authentication mechanisms: Linux SSH keys/Entra, Windows RDP/Entra or domain.
7. Plan monitoring, guest patching, backup/restore, and emergency recovery paths.

### Phase B: Create VMs and Networking

1. Open [Azure Portal](https://portal.azure.com/) in the correct tenant/subscription.
2. Create the Linux/Windows VM in the target resource group and region.
3. Choose the VNet/subnet and set **Public IP = None** when using private access.
4. Select approved sign-in methods; prefer SSH keys/Entra for Linux where supported.
5. Create/attach NSGs allowing only required administrative sources—never open 22/3389 to the Internet.
6. Configure patching, monitoring, and identity settings per operational standards.
7. Confirm the VM provisions cleanly and the NIC receives the expected private IP.

### Phase C: Establish the Administrative Channel

1. Deploy Azure Bastion or VPN/ExpressRoute per architecture.
2. For Bastion, create `AzureBastionSubnet` meeting SKU sizing rules and configure access permissions.
3. For VPN/hybrid, verify routes to VM subnets and DNS resolution.
4. Assign Azure RBAC at the narrowest scope, then verify OS-level logon rights.
5. Test SSH/RDP from approved admin sources, recording evidence and any errors.
6. If using JIT/PIM, verify request workflows, expiration, and audit trails.

### Phase D: Acceptance Validation

- Production VMs have no unauthorized administrative public IPs.
- SSH/RDP are unreachable from unauthorized Internet sources.
- Authorized admins can connect through Bastion/VPN with assigned permissions.
- Unauthorized users lacking roles/credentials cannot sign into the guest.
- Guest logs, Azure Activity Log, and Entra logs (where applicable) capture expected activity.
- A recovery plan exists if `sshd` or Windows Remote Desktop stops responding.
- Procedures exist to rotate or revoke keys and access when staff change.
- Costs for Bastion, VPN, monitoring, and licensing are budgeted.

## 14. Inspecting VM, NIC, and NSG State with Azure CLI

The commands below are **read-only**; they open no ports and modify no settings. Replace placeholders with your organization's resources.

### Check Tenant and Subscription

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### Inspect VM and Private/Public IPs

```bash
az vm show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>" \
  --show-details \
  --query "{Name:name,PowerState:powerState,PrivateIps:privateIps,PublicIps:publicIps}" \
  --output json
```

If a VM has an unexpected public IP, inspect the NIC, load balancer, and public endpoint design before removing it. Deleting a public IP without an alternative management path can lock you out.

### List NSG Rules

```bash
az network nsg rule list \
  --resource-group "<RESOURCE_GROUP>" \
  --nsg-name "<NSG_NAME>" \
  --output table
```

### Inspect Effective NSG Rules on a NIC

```bash
az network nic list \
  --resource-group "<RESOURCE_GROUP>" \
  --query "[].{NIC:name,PrivateIp:ipConfigurations[0].privateIPAddress,NSG:networkSecurityGroup.id}" \
  --output table

az network nic list-effective-nsg \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<NIC_NAME>" \
  --output json
```

Command syntax and environment requirements can vary by Azure CLI version. If effective NSG output is unavailable or the VM/NIC state is incompatible, run `az network nic --help` and check **Effective security rules** in the Portal/Network Watcher. Never interpret “unable to read effective NSG” as “no NSG exists.”

### Inspect VM Instance View

```bash
az vm get-instance-view \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>" \
  --output json
```

Instance view shows VM power/provisioning status and runtime/extension details. However, `VM running` **does not guarantee** `sshd` or Remote Desktop Services are listening properly.

### Test Connectivity from an Admin Workstation

On Linux/macOS or a workstation with OpenSSH:

```bash
ssh -v -i ~/.ssh/azure_vm_admin azureuser@10.80.1.10
```

On Windows:

```powershell
Test-NetConnection -ComputerName 10.80.2.10 -Port 3389
```

Run tests only from authorized networks and devices. `ssh -v` prints detailed connection info; redact internal IPs or sensitive identifiers per organizational policy before sharing logs.

## 15. Troubleshooting: Network, Authentication, or OS?

An “unable to access VM” issue must be categorized before changing configurations.

| Symptom | Likely fault layer | Verification steps |
|---|---|---|
| TCP timeout on SSH/RDP | Routing, NSG, firewall, VM/NIC, Bastion/VPN | Check VM running state, private IP, routes, NSGs, and entry point. |
| `Connection refused` | SSH/RDP service not listening, local firewall, or wrong port | Check guest service, listening port, local firewall, and listener config. |
| SSH reports `Permission denied (publickey)` | Wrong user, wrong private/public key, `authorized_keys`, permissions | Check username, key fingerprint, file ownership, `sshd` config, and key source. |
| SSH reports host key changed | VM rebuilt, DNS/IP changed, or spoofing risk | Verify host identity via independent channel; never blindly disable host key checking. |
| RDP reports insufficient privileges | Windows logon rights, account, local/group policy | Check Remote Desktop Users/Administrators groups and logon rights. |
| RDP NLA or certificate error | Identity/domain/time/certificate/client compatibility | Check identity, NLA, CA trust, policy, and client version. |
| Bastion opens yet cannot reach VM | VM NSG, guest firewall, SSH/RDP service, user login | Check Bastion connectivity, target IP/port, and guest logs. |
| VPN Connected yet VM unreachable | Missing return route, NSG, overlapping CIDR, or DNS | Check Effective routes and test private IP before hostname. |
| Entra login reports access denied | Missing login role, broken extension, policy, or unsupported VM | Check Azure RBAC, VM extension, Entra sign-in logs, and OS support. |
| VM running but has no network | Route/NSG, DHCP/NIC, guest firewall, OS network config | Use Network Watcher and an out-of-band recovery channel. |

### Layered Investigation Method

1. **Identify target:** confirm exact subscription, resource group, VM name, NIC, and private IP.
2. **VM state:** verify the VM is running and the OS booted cleanly.
3. **Access origin:** confirm Bastion/VPN or the workstation is on an authorized admin network.
4. **Network path:** check routes, effective NSG rules, firewalls, and ports.
5. **Guest service:** confirm `sshd` or Remote Desktop Services is running and listening on the expected port.
6. **Authentication:** verify username, key/identity, Entra roles, and domain/NLA.
7. **Authorization:** check `sudo` or Windows local admin rights after authentication succeeds.
8. **Record evidence:** UTC timestamp, account, source/destination IPs, status, rules/extensions, and remediation taken.

Change one variable at a time in a controlled way. Changing NSGs, firewalls, and passwords simultaneously obscures root cause and risks leaving an insecure exposure behind.

## 16. Recovering Access When SSH/RDP Completely Fails

If normal login channels fail, do not immediately attach a public IP and open all ports. Azure offers recovery mechanisms with distinct prerequisites.

### Azure VM Run Command

**Run Command** executes tasks inside the guest through the VM/agent management plane when supported conditions are met. It can inspect service state, check configurations, or apply approved fixes without SSH/RDP.

Prerequisites:

- VM Agent and VM state are healthy enough to execute commands.
- User holds required Azure RBAC permissions.
- Compatible guest OS/extensions and management path.
- Commands are reviewed carefully to avoid worsening misconfigurations.

Never use Run Command to set one shared admin password across many VMs or disable all firewalls via an unreviewed script.

### Azure Serial Console

**Serial Console** provides console access to diagnose VMs, especially when guest networking breaks. It requires boot diagnostics, supported OS/VM types, proper permissions, and prerequisite configuration; not every environment is ready unless prepared ahead of time.

This is a **privileged recovery path**: restrict it to authorized operations teams, with logging and proper break-glass accounts.

### Boot Diagnostics and Recovery

Boot diagnostics provides boot status, screenshots, and serial logs when a VM fails to boot its OS. When the OS disk or guest config is severely damaged, recovery/restore from backup may be required per organizational runbook—for example, attaching the disk to an isolated rescue VM for offline repair before restoring. This is a sensitive operation that can cause data loss if performed incorrectly.

### Recommended Break-Glass Procedure

1. Open an incident and confirm the VM/resource genuinely requires recovery.
2. Read VM, NIC, and NSG states alongside recent changes in Activity Log.
3. Pick the least-privileged channel suited to the root cause: Bastion, Run Command, or Serial Console.
4. Obtain owner approval if elevated privileges are needed.
5. Make a single reversible change and retest the service.
6. Confirm temporary rules are closed and break-glass keys/credentials are rotated or disabled per policy.
7. Document the full timeline, operator, and lessons learned to prevent recurrence.

Never write a runbook saying “turn off the NSG and turn it back on” without a safe change plan; doing so can create an immediate breach window during an incident.

## 17. Access Logging and Auditing Administrative Activity

Secure SSH/RDP governance requires knowing **who signed in, from where, when, and what changed**. No single log source answers every question.

| Source | What it records | Common misconception to avoid |
|---|---|---|
| **Azure Activity Log** | Control-plane changes: NSG, NIC, VM, Bastion, extensions, role assignments per resource. | Not a full log of every SSH command or RDP action inside the guest. |
| **Microsoft Entra sign-in logs** | Authentication events via Entra when using Entra-integrated login. | Local SSH key/password logins do not automatically appear as Entra sign-in events. |
| **Linux auth logs / journald** | SSH logins, auth failures, `sshd`, and system events per configuration. | Must be protected, centralized, and governed by retention policies. |
| **Windows Security Event Log** | Windows sign-in successes and failures per audit policy. | Events may be missing if audit policies are not enabled. |
| **Windows TerminalServices logs** | RDP session and Remote Desktop Services events. | Does not replace application logs or system change tracking. |
| **Bastion diagnostics/metrics** | Service/session activity per SKU features and diagnostic settings. | Granularity varies; do not assume every session is video-recorded by default. |
| **Defender for Cloud / Sentinel / SIEM** | Threat detection signals and centralized correlation when deployed. | Depends on service tier, configuration, and response workflows. |

### Example: Viewing SSH Logs on Linux

On systemd-based Linux distributions, the service unit may be named `ssh` or `sshd`:

```bash
sudo journalctl -u ssh --since "2 hours ago"
```

If no records appear, check the actual service name and logging config rather than assuming nobody logged in. Some distros write auth logs to `/var/log/auth.log` or `/var/log/secure`.

### Example: Viewing Windows Sign-In Events

Run in Windows PowerShell with appropriate privileges:

```powershell
Get-WinEvent -FilterHashtable @{
    LogName   = 'Security'
    Id        = 4624,4625
    StartTime = (Get-Date).AddHours(-24)
} | Select-Object TimeCreated, Id, ProviderName, Message
```

Event ID `4624` typically indicates successful logon and `4625` failed logon; to confirm RDP specifically, inspect **logon type**, source IP, and related TerminalServices logs—not just the event ID. Avoid leaking passwords or tokens when exporting logs.

### Recommended Monitoring Policies

- Alert if a Production VM unexpectedly gains a public IP or an inbound rule allowing TCP 22/3389 from `0.0.0.0/0`.
- Detect spikes of failed SSH/RDP login attempts in a short window.
- Monitor VM login role assignments or Entra role/extension modifications outside maintenance windows.
- Alert when Bastion, VPN, or critical management paths become unavailable.
- Track expiring keys/credentials, host patching, guest agents, and Defender alerts per deployed services.
- Periodically review long-lived admin privileges and sessions from anomalous sources.

With Azure Policy, you can audit or block public IPs and overly broad NSG rules where supported by policy definitions. Test policies carefully to avoid blocking valid exceptions, and establish an exception-review process.

## 18. Cost, Administrative Capacity, and Standardization

Secure access carries real costs, though cost comparisons must also weigh operational effort and security risk.

| Component | Cost and operational impact |
|---|---|
| **Azure Bastion** | Priced by SKU/uptime, features, and traffic per current billing model. |
| **VPN/ExpressRoute** | Gateway, circuit/carrier fees, data transfer, and network ops effort. |
| **Jump host** | VM compute, OS license if applicable, patching, monitoring, backup, hardening. |
| **Defender for Cloud / JIT** | Protection plans, licensing, and feature eligibility. |
| **Microsoft Entra / PIM / Conditional Access** | Identity governance policies and required licenses. |
| **Azure Monitor / Log Analytics / SIEM** | Log ingestion, retention, analytics/alerting. |
| **Admin workstations and endpoint security** | Compliant workstations, device protection, MFA, hardware keys if used. |

No single fixed price applies to every design. Estimate with the **Azure Pricing Calculator** using specific SKUs, regions, VM counts, usage hours, and access requirements.

### Recommended Operational Standards

1. IaC VM templates (Bicep/Terraform/ARM) with **no default public IP**.
2. Approved NSG rule sets for administrative subnets and VM subnets.
3. Standards for user identity, Entra/RBAC assignments, PIM, and group separation.
4. Procedures to issue/revoke SSH public keys, rotate credentials, and handle lost devices.
5. Runbooks for Bastion/VPN/JIT, break-glass recovery, and rollbacks.
6. Centralized logging, retention, and alerting for SSH/RDP activity.
7. Testing both authorized access and denied access after every network change.
8. Scheduled reviews of administrator privileges and policy exceptions.
9. Cost tracking for Bastion/Defender/VPN as VMs and subscriptions scale.

## 19. Hands-On Lab: Managing Two Azure VMs Without Public IPs

**Scenario:** A team is deploying an internal application with two VMs in one VNet: one Linux VM running the API and one Windows VM for administrative tooling. Both must be administered externally over an approved channel without accepting direct SSH/RDP connections from the Internet.

| Component | Illustrative value |
|---|---|
| Subscription | `Development` |
| VNet | `vnet-app-dev` – `10.80.0.0/16` |
| Bastion subnet | `AzureBastionSubnet` – `10.80.0.0/26` |
| Linux subnet | `snet-linux` – `10.80.1.0/24` |
| Windows subnet | `snet-windows` – `10.80.2.0/24` |
| Linux VM | `vm-linux-01` – `10.80.1.10` |
| Windows VM | `vm-windows-01` – `10.80.2.10` |
| Public IP on VMs | None |
| Linux auth | Individual admin SSH key or supported Entra SSH |
| Windows auth | Appropriate RDP permissions; NLA enabled |
| Management channel | Azure Bastion or approved VPN |

### Tasks

1. Diagram the access path from administrators to each VM.
2. Select identity models for Linux and Windows; distinguish Azure RBAC from guest permissions.
3. Propose source/destination/port rules for inbound NSGs on the Linux and Windows subnets.
4. Draft a Bastion deployment checklist including subnet and SKU considerations.
5. Explain why the VMs do not need public IPs.
6. Verify two scenarios: an authorized administrator connects successfully, and an unauthorized user is denied.
7. Suppose Linux SSH returns `Permission denied (publickey)`: outline investigation steps.
8. Suppose the Windows VM rejects RDP while the Azure Portal shows the VM running: outline investigation steps.
9. Propose an emergency recovery path if both Bastion and SSH/RDP fail.
10. List three security alerts and two cost items to manage.

### Reference Solution

**Network design:** VMs use private IPs only. Bastion resides in `AzureBastionSubnet` and connects to VMs in the same network or via a service-supported topology. Inbound NSGs on the Linux VM permit SSH only from the Bastion subnet (and from the admin VPN range if explicitly approved); the Windows VM mirrors this for RDP. No Internet-wide rules exist for ports 22/3389.

**Sign-in:** Linux prefers individual user SSH public keys or Entra SSH where supported. Windows uses appropriate Windows/Entra accounts with NLA enabled. Grant Azure RBAC roles to use Bastion plus login roles when using Entra login; never grant Owner merely so a user can SSH.

**SSH publickey error:** verify username, matching private key, public key in `authorized_keys`, file ownership/permissions, key algorithm, `sshd` status, and auth logs. Never enable public password auth as a “quick fix.”

**RDP failure:** verify Bastion reachability to VM port 3389, effective NSGs, Windows Firewall, RDP service, NLA, Windows logon rights, and Windows event logs. If networking fails, inspect routes/NICs; if networking passes yet login fails, inspect identity/policies.

**Recovery:** use Azure Run Command or Serial Console under supported conditions and approved permissions, gather evidence first, and make controlled changes. Monitor Bastion, guest OS health, and privileged accounts.

**Acceptance:** neither VM has a public IP; authorized users connect via the management path; unauthorized sources/identities are blocked; logs record required events; recovery procedures and cost estimates are documented.

## 20. Knowledge Self-Check

**Question 1.** A Production Linux machine only needs administration by the ops team. What is safer than opening TCP 22 from the Internet?

A. Use Azure Bastion or VPN to reach the private IP, with NSG source restrictions.  
B. Open `0.0.0.0/0` to TCP 22 on an arbitrary alternate port.  
C. Share a single root password across the entire team.

**Answer: A.** A private management path combined with source restrictions drastically reduces the attack surface.

**Question 2.** Does the Azure RBAC role `Virtual Machine Contributor` automatically allow Microsoft Entra SSH into a Linux VM?

**Answer:** No. Resource administration and guest sign-in are separate permission scopes; Entra login requires proper configuration and the corresponding login role.

**Question 3.** Why does Bastion allow VMs to have no public IPs?

**Answer:** Bastion terminates the administrative session within Azure's service architecture and connects across the Azure network to the VM's private IP. Any public IP required on certain SKUs belongs to Bastion, not each VM.

**Question 4.** SSH warns that the host key changed. Should you immediately disable `StrictHostKeyChecking`?

**Answer:** No. Check whether the VM was rebuilt or DNS changed, and verify the fingerprint via a trusted channel before accepting the new key.

**Question 5.** Windows RDP over VPN has TCP 3389 reachable, yet login is rejected. Is the error definitely caused by the NSG?

**Answer:** No. The TCP path may already be open; inspect the account, Remote Desktop rights, NLA, domain/identity health, and guest logs.

**Question 6.** Does NLA replace MFA or source network restrictions?

**Answer:** No. NLA is one protective layer within RDP, not a replacement for strong identity controls and NSG/Bastion/VPN boundaries.

**Question 7.** What does JIT VM access provide, and does it replace Bastion?

**Answer:** JIT restricts the time window and sources allowed to reach management ports per supported setup. It does not replace a private management channel or handle SSH/RDP authentication itself.

**Question 8.** Why is `0.0.0.0/0` on port 3389 risky even if the account has a password?

**Answer:** The management port is exposed to the entire Internet, inviting password brute-forcing and protocol exploits; a password alone does not eliminate that risk.

**Question 9.** How should a departing employee's SSH key be handled?

**Answer:** Revoke the public key and related Entra permissions, terminate active sessions/access per policy, audit shared keys and logs, and avoid shared private keys so access can be revoked individually.

**Question 10.** A VM is running yet unreachable via SSH/RDP. Which layer should be checked before resetting the password?

**Answer:** Verify networking, VM/NIC state, routes, NSGs, Bastion/VPN, and guest services first; only then check authentication. Resetting a password does nothing if the network path is broken.

**Question 11.** Does the Azure Activity Log automatically record every Linux command run inside an SSH session?

**Answer:** No. Activity Log records Azure control-plane operations; guest logging, `auditd`/session controls, or dedicated tools are needed to audit in-OS actions.

**Question 12.** When should Run Command or Serial Console be used?

**Answer:** When normal administrative paths fail and prerequisites/authorizations for recovery channels are met. Never use them as an excuse to grant standing elevated access.

**Question 13.** Once Bastion is deployed, can you remove all NSGs and guest firewalls because “Bastion is secure on its own”?

**Answer:** No. Maintain appropriate network and guest OS controls while configuring the rules Bastion requires, avoiding both overly broad exposure and accidental service blocks.

**Question 14.** In VM administration design, what matters more than “changing the SSH port from 22 to 2222”?

**Answer:** Keeping VMs on private networks, restricting sources, strong authentication, least privilege, patching, logging, and recovery paths. Simply changing port numbers is not a fundamental security control.

**In summary:** secure Azure VM administrative access combines **private networking + strong authentication + least privilege + logging + recoverability**. SSH and RDP are the administrative protocols, while Azure Bastion, VPNs, NSGs, JIT, Microsoft Entra ID, and Azure RBAC govern who can reach the VM and under what conditions. A solid design lets authorized operators resolve incidents promptly while minimizing unintended access opportunities.
