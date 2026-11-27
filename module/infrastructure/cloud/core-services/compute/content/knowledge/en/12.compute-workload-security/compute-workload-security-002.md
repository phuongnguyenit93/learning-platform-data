# Reducing the attack surface with a minimal OS baseline

Virtual machines are often created from an OS image preloaded with many packages, services, accounts, and administrative tools. Every installed or enabled component can introduce additional code to patch, network ports to protect, permissions to govern, and potential exploit paths. A server running a web application does not necessarily need a compiler, print server, file-sharing service, or various other administrative daemons.

A **minimal OS baseline** is an approved set of configurations and foundational components ensuring a machine has only the functionality needed for its workload while still meeting operational, monitoring, and security requirements. A baseline reduces the attack surface, produces consistent servers, and enables automated compliance checks.

In the compute module, the baseline must be considered alongside VM images, network configuration, workload identity, application deployment, and patching processes. Even a well-hardened OS can be compromised if the application is vulnerable, secrets leak, or security groups are overly permissive. Therefore, the baseline is one layer within a defense-in-depth architecture.

## 1. The operating system attack surface

The attack surface is the sum of points where users, applications, or external actors can interact with the system and potentially cause impact. On a VM, these points can include:

- Listening network services such as SSH, RDP, web servers, databases, or management agents.
- Packages, libraries, kernel modules, and runtimes with known vulnerabilities.
- Accounts, groups, sudo/Administrator privileges, SSH keys, and authentication mechanisms.
- Administrative interfaces, local APIs, sockets, and scheduled tasks.
- Firewall rules, routes, DNS configuration, and connection paths from other networks.
- Build tools, compilers, package managers, shells, and scripts that could be abused post-compromise.
- Logs, temporary files, caches, credentials, and sensitive data on disk.

Every additional component increases patching and governance overhead. An unnecessary daemon may contain vulnerabilities, run with elevated privileges, or open a network port the operations team is unaware of. A compiler installed in production can help an attacker compile tools directly on the host. A shared account makes it difficult to attribute actions to an individual.

Reducing the attack surface does not mean stripping out every component. The machine still needs minimal capabilities to boot, be administered, retrieve configuration, write logs, monitor health, enforce endpoint protection, and serve the application. Removing an agent or library that the workload depends on can cause loss of observability or downtime. The goal is to retain only components with a clear need, an assigned owner, and an update path.

## 2. Principles for designing a minimal baseline

A solid baseline typically follows these principles:

1. **Least functionality:** install and enable only the capabilities required by the workload.
2. **Least privilege:** processes and operators hold only the permissions needed for their tasks.
3. **Secure by default:** default configurations restrict access; permissions or services are opened only upon approved request.
4. **Patchable:** the OS, packages, and agents have trusted update sources and a clear support lifecycle.
5. **Observable:** configuration state, logs, metrics, and security events can be collected.
6. **Reproducible:** the baseline is defined as versioned code or policy that can rebuild machines deterministically.
7. **Recoverable:** recovery paths exist if a hardening change prevents booting, locks out access, or breaks the application.

A baseline should distinguish three layers:

| Layer | Scope | Examples |
|---|---|---|
| Common foundation | Applies to all machines in an image family | Patches, default accounts, time sync, auditing, default firewall |
| Workload profile | Applies by server role | Web/API, worker, database, bastion, batch processing host |
| Controlled exceptions | Adjustments required by applications or legacy systems | Specialized kernel modules, legacy ports, compatibility packages |

Avoid maintaining a single baseline for every server type if workloads have different requirements. For instance, a database server needs backup and storage monitoring tools; a web edge server may need a reverse proxy; an internal worker may not need any inbound ports at all. You can share a common foundation and extend it with role-specific profiles.

## 3. Selecting the right OS and source image

Attack surface reduction starts with image selection. Prefer official or vetted internal images with verified provenance and appropriate signatures or verification mechanisms. The OS must remain within its security support window, be compatible with the application, and have an update process maintained by the organization.

On Linux, consider cloud-optimized images or minimal installations of a supported distribution. On Windows Server, consider Server Core when the application is compatible and a full desktop GUI is unnecessary. Choosing a minimal edition reduces packages and services, though you must verify support for agents, runtimes, drivers, and administrative tools.

Image selection criteria:

- Trusted vendor and release channel with documented update procedures.
- OS version supported throughout the planned lifecycle.
- Regular security patches and clear vulnerability advisories.
- Compatibility with instance types, drivers, guest agents, and monitoring tools.
- Ability to inspect package inventory, signatures, and configuration state.
- Free of data, accounts, SSH host keys, tokens, or build-machine state.

Do not pick an image solely because it has the smallest footprint. An image lacking management agents or security updates can increase operational risk. Evaluate overall support cost, observability, boot time, and workload compatibility.

## 4. Inventorying and removing unnecessary components

Before hardening, inventory packages, services, listening ports, accounts, and automated tasks. Know which components are required by the OS, which were added by the image builder, and which are installed by the application during deployment.

On Linux, you can run inspection commands such as:

```bash
# List packages on Debian/Ubuntu
dpkg-query -W -f='${binary:Package}\t${Version}\n'

# List running services
systemctl --type=service --state=running

# List enabled services
systemctl list-unit-files --type=service --state=enabled

# Inspect listening ports
sudo ss -lntup
```

On RPM-based systems, you can inventory packages with `rpm -qa`. Command names and service management tools vary by distribution. On Windows, you can inspect services and installed software with PowerShell:

```powershell
Get-Service | Sort-Object Status, Name
Get-ItemProperty `
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', `
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' `
  -ErrorAction SilentlyContinue |
  Select-Object DisplayName, DisplayVersion, Publisher
```

The registry query above only exemplifies software registered under standard uninstall keys; some portable apps or differently managed packages may not appear. For large fleets, use inventory/endpoint management tooling for consistent data.

For each component, answer:

- Which workload or team needs this component?
- Does it listen on the network or run with elevated privileges?
- Are there vulnerabilities, support lifecycles, or patches to track?
- Can it be replaced by an external managed service or a shared agent?
- If disabled or removed, will it impact booting, administration, logging, backups, or recovery?

Only remove packages or disable services after confirming dependencies. Never disable system services arbitrarily just because their names look unfamiliar. Some services supporting DNS, network configuration, time sync, storage, guest agents, or endpoint protection may be essential for safe operation.

## 5. Minimizing network services and listening ports

Every network-listening service is a point to protect. The baseline should specify which machines may open which ports and from which sources. By default, if inbound traffic from other networks is not needed, do not open inbound ports; when needed, restrict sources via security groups, NSGs, firewalls, or appropriate management CIDR ranges.

On Linux, after inspecting with `ss -lntup`, map each socket back to its service and workload. If FTP, Telnet, print servers, legacy RPC, or file-sharing services are unneeded, remove or disable them per your distribution's guidance. Never use Telnet for remote administration because credentials and data can be transmitted unencrypted.

For SSH, a baseline configuration commonly considers:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowGroups cloud-ops
X11Forwarding no
```

This is an illustrative baseline, not a copy-paste config for every environment. Before disabling password authentication, verify that administrative accounts have working keys or an alternative login method, correct key file permissions, and a console/management recovery path. Validate syntax with `sshd -t`, open a new administrative session to test, and only then reload the service. Never close your active session until the new access path is verified.

On Windows, restrict RDP to management networks or dedicated access services; never expose RDP directly to the Internet. Enforce strong authentication, Network Level Authentication where appropriate, Windows Firewall, and controlled administrative access. If the workload does not need RDP, do not enable remote desktop merely for convenience.

Guest OS firewalls and cloud firewalls complement each other. Security groups/NSGs control traffic at the cloud network layer; the host firewall adds control on the machine itself. Use both layers for defense in depth while avoiding conflicting rules that lock out legitimate administrative access.

## 6. Protecting accounts and administrative privileges

Default accounts, orphaned accounts, and overly broad administrative privileges increase the risk of compromise. The baseline must establish rules for local accounts, administrative groups, sudo, file permissions, and authentication.

Common practices include:

- Create individual administrative accounts or distinct identities for accountability; avoid sharing a single account across a team.
- Use dedicated service accounts for applications rather than running every workload as `root` or `LocalSystem` unnecessarily.
- Grant permissions through centrally managed groups and revoke access when users change roles or leave the organization.
- Require strong authentication and MFA at the administrative access layer or identity-aware access proxy.
- Restrict direct login as root/Administrator; use audited, controlled privilege escalation mechanisms.
- Set least-privilege permissions on configuration files, private keys, data directories, and sockets.
- Review unused accounts and lock or disable them per policy.

On Linux, inspect `/etc/passwd`, `/etc/shadow`, sudo groups, and permissions on sensitive files. On Windows, review local Administrators, service accounts, interactive logon rights, and service logon privileges. Do not delete system accounts arbitrarily, as packages or services may depend on them.

Cloud administrative permissions and guest OS login permissions are two separate layers. Someone authorized to provision a VM does not necessarily need root access inside it; conversely, SSH access to a machine should not automatically grant permission to modify VPCs, security groups, or IAM. Manage the two layers with separate roles and separate auditing.

## 7. Kernel hardening and OS protection mechanisms

The kernel is the privileged component managing processes, memory, devices, and networking. The baseline should use an OS-vendor-supported kernel, apply security patches, and restrict unnecessary modules or features according to a tested profile.

Measures may include:

- Updating the kernel and system libraries from trusted repositories with package signature verification.
- Restricting unused kernel modules per distribution and workload guidance.
- Using SELinux or AppArmor on Linux when supported by the application and image; maintaining tailored policies rather than disabling the mechanism over a permission error.
- Enabling OS-supported memory and execution protections such as ASLR, NX/DEP, and appropriate application control mechanisms.
- Enabling Secure Boot or vTPM when supported by the instance type, image, and boot process, while verifying kernel/driver update compatibility.
- Enabling auditing for administrative actions, configuration changes, and key security events.
- On Windows, maintaining Microsoft Defender Antivirus/Endpoint Protection, Windows Firewall, UAC, and organization-approved security policies.

Do not toggle kernel features blindly from a generic hardening checklist. A module may be needed for storage, networking, filesystems, or agents. An overly strict SELinux/AppArmor policy can prevent an application from starting; inspect denial logs and author narrow policies for legitimate behavior rather than disabling protection system-wide.

## 8. System configuration, time synchronization, and auditing

The baseline must govern settings that affect authentication, logging, and incident investigation. Incorrect system time can break TLS, token validation, log correlation, and event analysis. Machines must synchronize time with trusted sources supported by the organization or platform.

Configurations to manage include:

- Time synchronization and standardized timezone for the operating environment.
- DNS resolvers and search domains matching the workload network.
- Hostnames, machine IDs, and agent identities uniquely generated per instance.
- Audit logs for logins, privilege escalation, account changes, services, and security configuration changes.
- Forwarding system logs to centralized storage with access controls and appropriate retention.
- Restricting log read permissions and protecting logs against modification or deletion by application accounts.
- Log rotation policies and disk space limits so logs do not fill the filesystem.

Never write private keys, tokens, passwords, or sensitive data into logs. If logs contain business data or personal information, apply appropriate filtering, access control, and retention policies.

## 9. Security updates and package management

A minimal baseline must include an update process. Reducing package count lowers the number of components to patch, but does not eliminate the need to update the kernel, runtimes, agents, and libraries still in use.

An update process should define:

1. Permitted package/repository sources and signature verification methods.
2. Scheduled patch review cycles and emergency procedures for critical vulnerabilities.
3. Impact assessment for patches affecting applications, drivers, and agents.
4. Canary testing on images or test instance groups before broad rollout.
5. Reboot procedures or live patching if supported, along with checks confirming the running kernel is updated.
6. Tracking unpatched hosts, end-of-life systems, and overdue exceptions.

Do not simply update the image and assume the entire fleet is patched. Running instances created from older images retain old packages until patched in place or replaced by new instances. Immutable infrastructure models typically build a newly patched image and roll out instance replacements in waves; long-lived workloads can use patch management to update the active fleet.

Avoid adding untrusted repositories or downloading packages directly from unverified URLs. Maintain package and version inventories so you can identify affected machines whenever a new vulnerability is disclosed.

## 10. Workload role-based baselines

A common baseline should be extended by server role. For example:

| Role | Likely required components | Components typically removable if unused |
|---|---|---|
| Web/API server | OS, application runtime, web proxy if needed, monitoring, endpoint protection, log agent | Compilers, desktop GUI, print services, file sharing, unused admin tools |
| Worker/batch | Runtime, queue client, monitoring, log agent, checkpointing mechanism | Unnecessary inbound listeners, web servers, desktop GUI |
| Database server | Database engine, storage tools, backup/monitoring agents, endpoint protection | Unrelated application runtimes, compilers, unnecessary sharing services |
| Bastion/management host | Approved administrative access tools, auditing, endpoint protection | Business applications, build packages, unnecessary public services |
| Data processing host | Compute runtimes/drivers, required libraries, monitoring and data management | Unrelated network services, unapproved experimental packages |

These are classification guidelines, not a rigid uninstall list. For instance, some agents need a local inbound listener, or a database might require a compiler extension in a specific workflow. Every exception must have a rationale and be tested.

## 11. Disk encryption and local data protection

The OS baseline should specify how data on boot and data volumes is protected. Encryption at rest reduces risk if snapshots, volumes, or storage devices are accessed outside normal management paths. Use encryption mechanisms supported by the cloud provider or guest OS, manage keys through the corresponding KMS/Key Vault service, and restrict key usage permissions.

Points to consider:

- Does the boot volume contain configuration files, logs, or sensitive data?
- Are data volumes encrypted by default or must encryption be explicitly enabled?
- Do snapshots and backups inherit encryption, or do they require separate configuration?
- Who has permission to create snapshots, copy volumes, export images, or decrypt data?
- How do you recover if a key is disabled, rotated, or permissions change?
- Do temporary files, swap, crash dumps, or core dumps contain sensitive information?

Encryption does not replace filesystem permissions, snapshot controls, backup security, or data deletion procedures. Encryption keys are themselves critical assets; if KMS permissions are overly broad or key material leaks, data can still be exposed.

## 12. Automating the baseline in golden images and at boot

The baseline should be applied automatically in the image build pipeline and re-verified at boot time. Tools such as Packer, cloud image builders, Ansible, Chef, Puppet, cloud-init, or equivalent configuration management systems can be used. Avoid having multiple tools overwrite the same setting without clear precedence or ownership.

A typical pipeline:

1. Select an approved source image and pin its version.
2. Install patches and minimal packages from trusted repositories.
3. Apply the common OS baseline and workload profile.
4. Disable unnecessary services, ports, and features after confirming dependencies.
5. Configure accounts, permissions, firewall, auditing, time sync, and endpoint protection.
6. Run vulnerability scans and automated configuration compliance checks.
7. Launch a test instance from the image to verify boot, administration, logging, and a sample application.
8. Publish the new image version along with its verification report.

Example baseline data structure managed in a repository:

```yaml
baseline:
  id: linux-compute-baseline
  version: "2.1"
  os_family: linux
  controls:
    automatic_security_updates: true
    root_ssh_login: false
    password_ssh_login: false
    host_firewall: enabled
    time_sync: required
    audit_logging: required
    endpoint_protection: required
  workload_profile: api-server
```

This is a policy description example, not a standard schema for a specific tool. The pipeline must map each control to enforceable configurations and automated checks. Do not simply record `host_firewall: enabled` without verifying actual rules, service status, and required connectivity.

Never embed secrets in images. Accounts, SSH host keys, machine IDs, and agent identities must be freshly generated upon cloning; workload secrets should be provisioned at runtime using a least-privilege identity. Environment-specific configurations should be supplied via bootstrap or configuration management systems.

## 13. Verifying baselines and detecting configuration drift

A baseline is only valuable if it can be verified. Requirements should translate into controls with clear outcomes: pass, fail, not applicable, or exception. For example, "secure SSH" is too vague; convert it into verifiable checks that `PermitRootLogin` is disabled, only the admin group may log in, and password authentication matches the approved profile.

Common verification methods:

- OS-appropriate security benchmarks or compliance scanners.
- Package inventory and vulnerability scanners.
- Checking enabled/running services and listening ports.
- Checking file permissions, accounts, admin groups, and authentication policies.
- Verifying firewall, auditing, logging, time sync, and endpoint protection.
- Configuration management or agents detecting drift between actual state and baseline.
- Cloud security posture management or fleet management systems if used by the organization.

You can reference CIS Benchmarks, Microsoft Security Baselines, or approved internal standards. Select the exact OS version and profile. Do not apply an entire benchmark mechanically: some controls may conflict with cloud guests, agents, or applications. Document exceptions with justification, an approver, compensating controls, and an expiration date.

**Configuration drift** occurs when running machines diverge from the baseline due to manual changes, deployment scripts, package updates, or application modifications. Detect drift via periodic configuration comparisons or continuous agent checks. For critical security changes, alert promptly and establish automated remediation or ticketing workflows.

## 14. Testing hardening changes before rollout

A security change can prevent an application from accessing files, opening ports, or calling dependent services. Baselines must therefore be tested on representative workloads before broad rollout.

A testing workflow should include:

1. Build a test image or instance from the new baseline version.
2. Verify boot, administrative login, guest agents, monitoring, and logging.
3. Install or deploy a sample application matching the profile.
4. Verify connectivity to DNS, secret providers, databases, queues, and required endpoints.
5. Run health checks and functional smoke tests.
6. Run vulnerability scans and mandatory control checks.
7. Test reboot, shutdown, backup/restore, and incident access paths.
8. Perform a canary rollout, monitor metrics, and expand in waves.

Test both normal operations and recovery scenarios. For example, a new firewall rule might permit load balancer traffic while blocking an agent from sending logs to its management endpoint. If you only test the API, that observability failure can go unnoticed.

When hardening locks out access, ensure a tested recovery channel exists such as a serial console, cloud console, management agent, or the ability to recreate the machine from a prior image. For immutable fleets, rollback typically means redeploying from a known-good image version after confirming application data is stored on persistent volumes or external services.

## 15. Example minimal baseline for a Linux API server

Suppose a Java API runs on Linux in a private subnet. The machine only receives requests from a load balancer, accesses an internal database, retrieves secrets from a secret manager, and sends logs/metrics to an observability service.

The baseline can be designed as follows:

| Item | Target configuration | Verification method |
|---|---|---|
| Image | Supported Linux LTS, approved image | Verify image ID, OS version, and release source |
| Packages | OS packages, Java runtime, and required agents | Compare package inventory against allowlist |
| Services | Enable only network, time sync, guest agent, logging, security agent, and application service | `systemctl` and service inventory |
| Network | No public IP; accept API port only from load balancer | Cloud security group/NSG and `ss -lntup` |
| SSH | Root login disabled; authentication via approved administrative method | Inspect SSH config and test login via management channel |
| Identity | Individual admin accounts, `orders` user for the application | Check groups, sudo, and file permissions |
| Host firewall | Allow only defined administrative and application flows | Inspect firewall rules and run connectivity smoke tests |
| Kernel/security | Patches, SELinux/AppArmor per profile, auditing | Scanner and policy status checks |
| Logging | System and application logs forwarded centrally | Verify log events from test instance |
| Storage | Encrypted boot/data volumes; restricted directory permissions | Check encryption metadata and permissions |

A quick post-build verification example on Linux:

```bash
cat /etc/os-release
systemctl --type=service --state=running
sudo ss -lntup
sudo sshd -t
sudo systemctl is-active systemd-timesyncd
sudo aa-status 2>/dev/null || sudo getenforce
```

These commands are illustrative and may require adjustment by distribution. `systemd-timesyncd` is not present on all distributions; some systems use chrony or another time service. `aa-status` applies to AppArmor, whereas `getenforce` applies to SELinux. A "command not found" result does not by itself prove the system lacks protection; you must know which profile is active.

Because the API only accepts traffic from the load balancer, the machine's security group allows the application port solely from the corresponding source security group. The machine needs no public IP. Outbound rules open only required destinations such as the database, secret provider, update repositories, and logging service. Administration flows through a VPN or dedicated access system with auditing and strong authentication.

## 16. Common mistakes when minimizing an OS

- **Removing packages arbitrarily:** can break application or agent dependencies. Inventory and test before removing.
- **Disabling unfamiliar system services:** can break DNS, networking, time sync, storage, or guest management. Verify their role before changing them.
- **Disabling the firewall to troubleshoot connectivity:** widens the attack surface. Inspect rules and routes, then open only the required flows.
- **Disabling SELinux/AppArmor when an app is denied:** removes an important protection layer. Read audit logs and write a narrow policy.
- **Disabling SSH passwords before preparing alternatives:** can lock out administrative access. Test a new session first and keep recovery channels.
- **Using one baseline for all workloads:** can omit required agents/permissions or leave unnecessary packages behind. Use role-based profiles.
- **Hardening only new images:** running machines can still drift or retain vulnerabilities. Combine patching and drift detection across the fleet.
- **Applying benchmarks without testing:** some controls conflict with applications or cloud agents. Test and manage exceptions formally.
- **Having no rollback plan:** a bad change can render an entire group of servers unreachable. Keep known-good image versions and recovery paths.

## 17. Minimal OS baseline checklist

- [ ] Image comes from a trusted source, OS version is supported, and a patching process exists.
- [ ] Package inventory is reconciled against required components.
- [ ] Services and listening ports are inventoried; unnecessary services are removed or controlled-disabled.
- [ ] Default accounts, administrative rights, and service accounts are reviewed.
- [ ] SSH/RDP access is restricted to secure management channels with strong authentication.
- [ ] Host firewall and cloud network policies permit only required flows.
- [ ] Kernel, SELinux/AppArmor, or Windows security controls follow a tested profile.
- [ ] Auditing, centralized logging, time sync, and endpoint protection are operational.
- [ ] Boot volumes, data volumes, snapshots, and backups are protected with appropriate encryption.
- [ ] Machine-specific secrets and identities are provisioned at runtime, never baked into images.
- [ ] Baseline is version-controlled, automatically verified, and monitored for configuration drift.
- [ ] Representative workloads pass smoke tests, health checks, reboots, and recovery tests.
- [ ] Exceptions have documented rationale, approver, compensating controls, and expiration date.

A minimal OS baseline ensures virtual machines run only necessary components, reduces exploitable entry points, and makes security posture easier to verify. When baselines are tailored by workload role, automated in the image pipeline, tested before rollout, and maintained across the fleet, organizations reduce risk while preserving manageability and system recoverability.
