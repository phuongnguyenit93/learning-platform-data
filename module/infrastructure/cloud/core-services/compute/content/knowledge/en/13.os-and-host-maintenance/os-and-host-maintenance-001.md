# Building Configuration Baselines and Patch Management

Cloud servers are typically created from an OS image, then installed with runtimes, monitoring agents, security tools, and applications. If each server is configured manually, hosts within the same group can diverge in package versions, accounts, firewall rules, SSH policies, logging, and patches. This divergence increases security risk, makes incident troubleshooting unpredictable, and makes the server fleet difficult to manage.

A **configuration baseline** is the approved standard state defined for an operating system type or workload group. **Patch management** is the process of identifying, testing, deploying, and verifying updates for the operating system, kernel, libraries, and software components. The two activities complement each other: the baseline defines the desired configuration; patch management keeps that foundation up to date and reduces vulnerabilities over time.

This lesson belongs to the **OS and Host Maintenance** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models, from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security configurations; and how to deploy applications, scale under load, ensure availability, and optimize operational costs. In that context, baselines and patches are the foundation for keeping servers consistent, secure, scalable, and recoverable.

## 1. What Is a Configuration Baseline?

### 1.1. Concept and Objectives

A **configuration baseline** is the standard configuration state defined for a system, a group of hosts, or a server role. A baseline describes required settings, prohibited settings, acceptable software versions, and how compliance status is verified.

For example, a baseline for a Linux VM running an API might specify:

- Use an OS distribution and version still supported by the vendor.
- Install only the packages required for the API role.
- Personal admin accounts use SSH keys or a centralized authentication mechanism.
- Disallow direct SSH login with the root account.
- Firewall only opens ports required for the application and administration from trusted sources.
- Synchronize time with approved sources.
- Enable appropriate logging, monitoring, endpoint protection, and backup agents.
- Install security patches within defined timelines.
- Configure encryption, file permissions, and audit policies according to workload sensitivity.

A baseline ensures hosts sharing the same role behave consistently. When a new machine is provisioned, the system can apply the baseline automatically instead of relying on manual steps.

### 1.2. A Baseline Is Not a Static Image

A golden image can contain much of the foundational configuration, but a baseline is broader than an image. A baseline also includes:

- Boot-time configuration and information provided via metadata.
- IAM policies, firewalls, security groups, and network configuration.
- Environment-specific runtime configuration.
- Acceptable package and patch versions.
- Agent, logging, monitoring, and backup configurations.
- Verification rules, exceptions, and compliance evidence.

An image is a way to package and distribute the initial state. Configuration management, policy engines, and compliance tools help maintain that state after the host is created.

### 1.3. Baselines by Role and Criticality

An identical configuration should not be applied to every server. Database servers, web servers, workers, bastions, and build machines have different attack surfaces, performance requirements, and components.

| Role | Commonly Required Components | Key Considerations |
|---|---|---|
| Web/API | Application runtime, reverse proxy, logging agent | Open only necessary ports; restrict process privileges |
| Database | Database engine, backup agent, monitoring | Data protection, encryption, auditing, and maintenance windows |
| Worker/batch | Job runtime, queue client, telemetry | Replaceable or recreatable; manage data access permissions |
| Bastion/management | Administrative access tools, auditing | Strong authentication, source restrictions, session recording |
| Build runner | Toolchain, cache, CI agent | Job isolation, workspace cleanup, secret management |
| GPU host | Drivers, GPU runtime, device plugin/agent | Compatibility across driver, kernel, accelerator, and workload |

You can create a common foundational baseline and extend it per role. Differences must be explicitly declared, with an owner and justification.

## 2. Building Baseline Contents

### 2.1. Operating System and Support Lifecycle

Start by selecting an operating system and version still within the vendor's support window. You need to identify:

- Major version, minor version, and CPU architecture.
- Standard end-of-support date and extended support if available.
- Kernel in use and kernel update policy.
- Allowed package repository sources.
- Mechanism for receiving security patches and critical updates.
- Major version upgrade process.

Do not choose an OS merely because an image is available or the machine boots. An end-of-life version may no longer receive standard security patches, increasing risk over time.

### 2.2. Packages and Services

The baseline should define minimum packages, mandatory packages, and prohibited packages. Removing unnecessary services reduces the attack surface and simplifies operations.

For example:

- Install only the required application runtimes and libraries.
- Do not install compilers or debugging tools in production without a clear operational need.
- Disable or remove unused services such as test daemons, sample servers, or redundant network services.
- Pin versions of components with strict compatibility requirements.
- Record package sources and repository signatures.
- Have an update process for both OS packages and application packages.

Do not remove packages blindly. A package might be a dependency for a security agent, cloud-init, or system service. Before making changes, check dependencies and test on a staging image.

### 2.3. Accounts, Authentication, and Permissions

A server baseline needs to clearly define who can log in and what they are allowed to do.

Common principles:

- Use individual accounts or centralized identities instead of shared accounts.
- Grant least-privilege access by role.
- Restrict sudo/administrator privileges and audit privilege escalation.
- Do not store passwords, private keys, or tokens inside images.
- Use SSH keys, certificates, MFA, or an organization-approved authentication mechanism.
- Disable unnecessary default accounts after verifying no services are affected.
- Have a process to revoke access when personnel leave or workloads end.

For Linux, review permissions on SSH config files, sudoers, system accounts, and login shells. For Windows, manage the local administrators group, Windows LAPS, or an organization-supported administrative password management mechanism.

### 2.4. SSH and Administrative Access

For Linux hosts, a baseline may require:

- Disallowing direct root login over SSH.
- Allowing only approved authentication methods.
- Restricting network sources for SSH access.
- Limiting which groups or accounts are allowed to log in.
- Logging authentication events and monitoring anomalous logins.

Illustrative OpenSSH configuration example:

~~~text
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
AllowGroups ops-admins
~~~

This example must be adapted to your actual access mechanism. Before disabling password authentication, verify that key-based or alternative access works, an approved break-glass account exists, and out-of-band console access is available. Validate syntax using the tool for your OpenSSH version, then reload the service during a controlled change window. Never lock out active administrative access without a recovery plan.

For Windows, the baseline should specify whether Remote Desktop is enabled, allowed access sources, Network Level Authentication, account policies, and remote management mechanisms. Never expose RDP directly to the Internet without an approved protective architecture.

### 2.5. Host Firewall and Network Configuration

A host-level firewall provides an additional layer of defense alongside security groups, network ACLs, and cloud firewall services.

The baseline should define:

- Required inbound ports per role.
- Allowed outbound traffic.
- Administrative and health check sources.
- Default policy when no rule matches.
- Sufficient logging for denied traffic.
- Consistent handling of IPv4 and IPv6.

Do not open up the firewall by "allowing everything so the app runs." If an application does not work, identify the required port, protocol, source, destination, and traffic path before adding a rule. Firewall configuration must also be verified after a reboot and after any network management agent reapplies policies.

### 2.6. Time, Logging, and Monitoring

Incorrect system time can break authentication, certificates, log correlation, and incident investigation. The baseline should specify time sync sources, a standard timezone, and how clock drift is monitored.

Logging should cover relevant events such as:

- Successful/failed logins and privilege escalation.
- Changes to accounts, groups, and policies.
- Changes to network, firewall, and service configurations.
- Kernel, filesystem, and critical service errors.
- Patch installation and reboot results.

Logs should be forwarded to centralized storage with restricted access and appropriate retention. Do not write secrets, tokens, or unnecessary sensitive data into logs.

At a minimum, monitoring should track CPU, memory, disk usage, filesystem, network, service status, patch age, and security agents. Alerts must have clear thresholds and recipients; too many non-actionable alerts reduce incident detection effectiveness.

### 2.7. Encryption and Data Protection

The baseline may require:

- Encrypting boot disks and data disks per policy.
- Using managed keys appropriate for workload requirements.
- Restricting access to snapshots and backups.
- Protecting temporary data and configuration files containing secrets.
- Using appropriate encryption protocols for data in transit.
- Sanitize or wipe data according to procedure when reusing hosts or volumes.

Disk encryption does not replace file permissions, secret management, or application access controls. Combine protective layers suited to the actual data.

## 3. Hardening and Configuration Standards

### 3.1. What Is Hardening?

**System hardening** is the process of reducing the attack surface and limiting exploitability by configuring the operating system and services more securely.

A hardening process may include:

1. Removing unnecessary packages, services, and ports.
2. Enforcing strong authentication and least privilege.
3. Configuring firewalls, auditing, and logging.
4. Protecting system files, secrets, and data.
5. Applying appropriate kernel and system configurations.
6. Installing security and monitoring agents.
7. Re-testing the application to ensure hardening does not break functionality.

Hardening must balance security and operability. Overly strict settings can prevent agents from running, stop applications from binding to ports, or strip backup tools of permissions. Therefore, changes must be tested per server role.

### 3.2. Using Benchmarks as a Starting Point

Organizations can reference CIS Benchmarks, DISA STIG, or hardening guides from OS and cloud vendors. These standards provide configuration control recommendations by platform and protection level.

Keep in mind:

- Choose the exact OS version and profile.
- Review whether each recommendation fits the workload.
- Distinguish mandatory controls, recommendations, and exceptions.
- Test the impact on applications, performance, and agents.
- Record the benchmark version and assessment date.
- Do not apply an entire configuration automatically without checking dependencies.

A benchmark is a reference point for building a baseline. The final policy must be approved based on the environment's risks and requirements.

### 3.3. Controlled Exceptions

Some workloads need configurations that differ from the baseline, such as databases requiring specific kernel parameters or legacy agents not supporting newer TLS versions. Exceptions require:

- The exempted system and setting.
- Technical justification and residual risk.
- Compensating controls.
- Approver and owner.
- Review period or expiration date.
- Verification evidence.

Do not create indefinite exceptions or apply a single broad exception across the entire fleet when only one workload needs it.

## 4. Baselines as Code and Automation

### 4.1. Infrastructure as Code and Configuration Management

You can describe infrastructure using IaC and internal host settings using configuration management tools. The two layers complement each other:

- **IaC:** provisions VMs, NICs, disks, IAM, security groups, and metadata.
- **Image pipeline:** builds patched and hardened base images.
- **Configuration management:** applies packages, services, files, users, and policies inside the guest OS.
- **Policy/compliance:** verifies actual state against the baseline.

When configuration is stored in version control, changes can be reviewed, tested, and traced. Avoid storing secrets directly in repositories or images.

### 4.2. Ansible Example for Linux

The following playbook illustrates how to declare basic settings on Debian/Ubuntu systems. The package and service lists must be adjusted per role and distribution:

~~~yaml
- name: Apply a basic Linux host baseline
  hosts: api_hosts
  become: true
  tasks:
    - name: Install required baseline packages
      ansible.builtin.apt:
        name:
          - chrony
          - unattended-upgrades
          - auditd
        state: present
        update_cache: true
        cache_valid_time: 3600

    - name: Ensure time synchronization is enabled
      ansible.builtin.service:
        name: chrony
        state: started
        enabled: true

    - name: Ensure audit service is enabled
      ansible.builtin.service:
        name: auditd
        state: started
        enabled: true

    - name: Set a managed SSH policy
      ansible.builtin.copy:
        dest: /etc/ssh/sshd_config.d/60-host-baseline.conf
        owner: root
        group: root
        mode: "0600"
        content: |
          PermitRootLogin no
          PubkeyAuthentication yes
      notify:
        - Validate SSH configuration
        - Reload SSH service

  handlers:
    - name: Validate SSH configuration
      ansible.builtin.command: sshd -t
      changed_when: false

    - name: Reload SSH service
      ansible.builtin.service:
        name: ssh
        state: reloaded
~~~

This example must be verified against your Ansible version, OpenSSH include structure, and distribution service name. On some systems, the service is named **sshd** rather than **ssh**. Configuring key authentication must be paired with key provisioning or centralized identity; a playbook does not replace testing access before reloading.

Declarative Ansible modules allow repeated runs without making unnecessary changes when the state is already compliant. However, not all arbitrary commands are idempotent. For shell/command tasks, define check conditions or use dedicated modules.

### 4.3. Baseline Verification Examples on Linux

Several commands help collect system state:

~~~bash
# Operating system and kernel
cat /etc/os-release
uname -r

# Upgradable packages on Debian/Ubuntu
apt list --upgradable

# Available security updates on DNF-based systems
dnf updateinfo list --security

# Failed services and error logs in the current boot
systemctl --failed
journalctl -p err -b

# Listening sockets
ss -lntup

# Time synchronization check
timedatectl status
~~~

Package manager commands differ across distributions. Output only reflects currently configured repositories and updated metadata. Sync the package index before planning patches and verify that repository sources are trusted.

### 4.4. Baseline Verification on Windows

On Windows Server, baselines can be deployed using Group Policy, Local Security Policy, Desired State Configuration, endpoint management tools, or a patch management platform.

Several inspection commands:

~~~powershell
# Operating system information
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

# Installed hotfixes
Get-HotFix | Sort-Object InstalledOn -Descending

# Service status
Get-Service -Name EventLog | Select-Object Name, Status

# Firewall profiles
Get-NetFirewallProfile

# Microsoft Defender status if present
Get-MpComputerStatus
~~~

Not every command or property is available on every Windows Server version or image. Results must be cross-checked against the baseline and management agent in use. Policy deployments should be tested in a pilot OU or test host group before broad rollout.

## 5. Golden Images and Server Lifecycle

### 5.1. What Is a Golden Image?

A **golden image** is a standardized, tested, and approved server image used as the source for provisioning VMs. The image typically includes:

- Operating system and patches as of build time.
- Required foundational packages.
- Basic hardening configuration.
- Monitoring, security, and management agents.
- Required public certificates or trust stores.
- Image version metadata and build details.

Do not embed credentials, private keys, tokens, or host-specific data in a golden image. Those values must be provisioned at deployment time via a secret manager or an appropriate identity mechanism.

### 5.2. Image Build Pipeline

An image pipeline may consist of:

~~~mermaid
flowchart TD
    SRC["Trusted base image"]
    PATCH["Install approved patches and packages"]
    HARDEN["Apply baseline and hardening"]
    TEST["Test functionality, security, and compliance"]
    SCAN["Scan vulnerabilities and inspect artifacts"]
    APPROVE["Review and approve"]
    PUBLISH["Publish versioned image"]
    DEPLOY["Create VMs by workload group"]
    SRC --> PATCH --> HARDEN --> TEST --> SCAN --> APPROVE --> PUBLISH --> DEPLOY
~~~

The pipeline should pin base image, package, and toolchain versions for reproducible builds. Each image needs metadata such as build ID, source, creation date, baseline version, and package list (SBOM if supported by the workflow).

An image should only be published after mandatory checks pass. On failure, the pipeline must save logs and halt at the appropriate step.

### 5.3. Immutable Infrastructure

Under the **immutable infrastructure** model, when a platform change or major update is needed, the team builds a new image and replaces old VMs with new VMs. This keeps machine state reproducible and reduces accumulated manual configuration.

Not every host can be replaced immediately. Databases, stateful workloads, or systems with directly attached devices require dedicated migration, backup, replication, and cutover plans. Rolling replacement or blue/green strategies can reduce disruption.

### 5.4. Configuration Drift

**Configuration drift** is the divergence between a host's actual state and the desired baseline. Drift can occur when:

- Operators edit files directly on the host.
- Packages are installed manually.
- Agents alter configuration.
- A bootstrap script runs inconsistently.
- A host fails to receive new configuration.
- Temporary exceptions are not removed.

Drift must be detected by periodically comparing actual state against declared configuration. For critical settings, automated remediation may be used; for risky changes, generate alerts and require review before fixing.

## 6. What Is Patch Management?

### 6.1. Scope of Patch Management

Patch management is more than running an OS update command. Its scope can include:

- Kernel and bootloader.
- OS packages and shared libraries.
- OpenSSH, OpenSSL, web servers, and middleware.
- Java, .NET, Python, Node.js, or Go toolchains and runtimes.
- Security, monitoring, and backup agents.
- Firmware or drivers if the platform permits management.
- Container base images and dependencies packaged inside images.

With VMs, operations teams generally bear more responsibility for the guest OS. With containers, base images must be updated and application images rebuilt. With managed or serverless services, the provider may manage the underlying host and runtime, while users remain responsible for updating dependencies, runtime versions, and application code within their scope of responsibility.

### 6.2. Update Classifications

| Update Type | Objective | Examples |
|---|---|---|
| Security patch | Fix security vulnerabilities | CVEs in the kernel or libraries |
| Critical update | Fix severe bugs affecting the system | Bugs that could cause crashes or data loss |
| Bug fix | Fix functional defects | Filesystem or network stack bugs |
| Feature update | Add features | Component version upgrades |
| Driver/firmware | Update hardware interaction | NIC, storage, or GPU drivers |
| Runtime/dependency | Update application platform | JVM, .NET, OpenSSL, or npm packages |

Not all updates carry the same risk. Security patches may require emergency deployment; feature updates typically require compatibility testing and a dedicated upgrade plan.

### 6.3. Vulnerabilities and Prioritization

Do not prioritize patches based solely on CVSS scores. Combine multiple factors:

- Vulnerability severity.
- Whether an exploit is actively being used in the wild.
- Whether the host is reachable from the Internet or untrusted networks.
- Whether the affected component is actually installed and in use.
- Privileges a process could gain if exploited.
- Data sensitivity and server role.
- Availability of temporary mitigations.
- Complexity and risk of applying the update.

A medium-severity vulnerability actively exploited on a public-facing server may need remediation before a high-severity vulnerability that is unreachable in the current environment.

Useful sources include vendor security advisories, the CVE database, CISA Known Exploited Vulnerabilities (KEV), and vulnerability management tools. Record the assessment date because exploitation status and exposure levels can change.

### 6.4. Defining Patch SLAs

Organizations should define remediation timelines by risk level and workload classification. Illustrative policy example:

| Priority Level | Typical Conditions | Illustrative Target |
|---|---|---|
| Emergency | Actively exploited vulnerability affecting critical or public-facing assets | Assess immediately, deploy mitigations, and patch via emergency process |
| High | Severe vulnerability with realistic exploitability | Within a few days per organizational SLA |
| Medium | Limited risk or requires specific exploitation conditions | Within the scheduled maintenance cycle |
| Low | Minor impact, minimal exposure | Per regular update schedule |

Specific timeframes must be approved by the organization based on regulatory requirements, criticality, and operational capacity. The table above is not a universal SLA for all systems.

## 7. End-to-End Patch Management Workflow

### 7.1. Step 1: Inventory and Scope Identification

You need to know which hosts exist, which groups they belong to, what OS they run, and who owns them.

Inventory should record:

- Instance ID, hostname, account/project, and region/zone.
- OS, version, kernel, and architecture.
- Workload role, environment, and criticality.
- Technical owner and operations team.
- Package repository source and patch policy.
- Status of agents, backups, monitoring, and configuration management.
- Last patched timestamp and reboot-required state.

Hosts without an owner or inventory record are easily missed in update cycles. Also account for ephemeral hosts, autoscaling hosts, disaster recovery groups, and isolated nodes.

### 7.2. Step 2: Patch Assessment

Gather vendor advisories, affected package lists, and security bulletins. Determine which hosts actually need updates, which dependencies might change, and whether a reboot is required.

Do not deploy a patch just because a package manager shows a newer version. Verify the repository, signatures, publisher source, target version, and compatibility notes.

### 7.3. Step 3: Testing in a Representative Environment

Deploy first to a development or staging environment closely matching production. Verify:

- Application startup and health checks.
- Connectivity to databases, queues, storage, and dependent services.
- Logging, monitoring, backups, and security agents.
- Performance, CPU, memory, and I/O.
- Kernel modules, drivers, and accelerators if present.
- Reboot, self-healing, and rollback capability.

For critical workloads, use automated tests and representative data. Checking only that packages installed cleanly is not enough.

### 7.4. Step 4: Deployment Planning

Define:

- Target host groups and rollout order.
- Maintenance windows and on-call personnel.
- Services needing draining or traffic shifting.
- Remaining replicas/capacity during patching.
- Snapshots, backups, or replacement images.
- Reboot requirements.
- Health checks and rollout stop thresholds.
- Recovery plan if the patch causes failures.

Never patch all nodes in a cluster simultaneously if doing so breaks quorum or leaves insufficient capacity for traffic. For database clusters, follow the DBMS's supported upgrade order and failover mechanism.

### 7.5. Step 5: Ring or Canary Rollout

The fleet can be divided into rings:

1. **Ring 0:** test and staging hosts.
2. **Ring 1:** a small group of low-risk production hosts.
3. **Ring 2:** a representative slice of the fleet across multiple zones or workload groups.
4. **Ring 3:** the remainder of the fleet after prior rings meet criteria.

Monitor errors, latency, throughput, reboots, health checks, and security alerts after each ring. If a threshold is breached, halt the rollout and investigate before continuing.

~~~mermaid
flowchart TD
    TEST["Staging / test"]
    CANARY["Canary production"]
    RING2["Ring 2: representative group"]
    FLEET["Ring 3: remaining fleet"]
    CHECK{"Health checks pass?"}
    STOP["Stop rollout, investigate, and recover"]
    DONE["Verify and close patch cycle"]

    TEST --> CHECK
    CHECK -->|Pass| CANARY
    CHECK -->|Fail| STOP
    CANARY --> CHECK2{"Canary stable?"}
    CHECK2 -->|Pass| RING2
    CHECK2 -->|Fail| STOP
    RING2 --> CHECK3{"Ring 2 pass?"}
    CHECK3 -->|Pass| FLEET
    CHECK3 -->|Fail| STOP
    FLEET --> DONE
~~~

The diagram illustrates the rollout principle. In practice, define health checks and stop thresholds per workload; do not rely solely on package manager status.

### 7.6. Step 6: Reboot and Post-Update Verification

Some patches only take effect after a restart, especially kernel updates, shared libraries held in memory by running processes, or drivers. Distinguish between:

- Package installed while the running kernel remains unchanged.
- Services needing a restart to load updated libraries.
- Full host reboot required.
- Supported live patching mechanisms for specific components.

After updating, verify package versions, running kernel, service status, agents, and application health checks. On Linux, check the kernel with **uname -r**; on Windows, check the build number and hotfix history using administrative tools.

Do not treat "reboot succeeded" as the final result. Confirm the host has re-registered with the load balancer, cluster, or autoscaling group, and that the application is ready to serve traffic.

### 7.7. Step 7: Reconciliation and Evidence Retention

After each patch cycle, record:

- Lists of succeeded, failed, pending, and exempted hosts.
- Package/version before and after.
- Start, completion, and reboot timestamps.
- Health check results.
- Errors encountered and remediation steps.
- Operator or automation run ID.
- Compliance evidence and linked ticket/change records.

Failed hosts must have an owner and remediation deadline. Do not exclude a host from reports simply because it is unresponsive or powered off; determine its status and handle it according to procedure.

## 8. Patching on Linux

### 8.1. Debian and Ubuntu

A common manual workflow involves updating the package index, reviewing available updates, and installing per policy:

~~~bash
sudo apt-get update
apt list --upgradable
sudo apt-get upgrade
~~~

On production systems, inspect changes carefully before confirming. **apt-get upgrade** does not perform all changes that might be needed, such as replacing or removing packages; **full-upgrade** can alter dependencies and remove packages to satisfy upgrades. Do not run broad upgrade commands across a production fleet without testing, backups, and a rollout plan.

You can check which packages need updating and inspect installation history for reconciliation. Log names and tools vary by Debian/Ubuntu version.

### 8.2. RHEL, Rocky Linux, AlmaLinux, and Fedora Server

DNF-based systems can list security advisories and install security updates:

~~~bash
sudo dnf check-update
sudo dnf updateinfo list --security
sudo dnf upgrade --security
~~~

Security advisory filtering and command behavior depend on DNF version, repositories, and plugins. For systems requiring change control, inspect the transaction beforehand, check replaced packages, and record the results.

### 8.3. Checking Reboot Requirements

Some distributions provide tools to detect when a reboot is needed; check methods vary. Ubuntu may use a reboot flag file, while other distributions use dedicated packages or agents. Do not rely on a single generic check file across all distributions.

After a kernel patch, if not yet rebooted, the host may still be running the old kernel. This must be reflected in compliance reports even when the new package is installed.

### 8.4. Live Kernel Patching

Some vendors and distributions support live patching for a subset of kernel patches. This mechanism modifies parts of the running kernel in memory without an immediate reboot.

Live patching reduces disruption but has limitations:

- Not all kernel patches support live patching.
- May require specific subscriptions, agents, or configuration.
- Certain changes still require a reboot.
- The kernel and modules must be within the supported matrix.
- You must verify that the patch has actually been applied.

Live patching does not replace periodic reboot cycles, testing, and full updates per vendor guidance.

## 9. Patching on Windows Server

### 9.1. Update Sources and Policies

Windows Server can receive updates via Windows Update, Windows Server Update Services (WSUS), Microsoft Configuration Manager, or cloud update management services. Choose a single consistent management source to avoid multiple systems competing over update state.

The baseline should define:

- Update channel and target host groups.
- Approved update classifications.
- Download and installation schedules.
- Restart behavior and restart deadlines.
- Deferral or pause policies.
- Logging and compliance reporting methods.

### 9.2. Installation and Reboot

For Windows Server, test updates on a representative host group first. Some updates require restarts and affect running services.

Before patching:

- Verify backups and restore capability.
- Drain the node from load balancers or clusters if needed.
- Verify replication and quorum.
- Check disk space and Windows Update health.
- Announce the maintenance window to stakeholders.

After installation:

- Verify that hotfixes/builds are applied.
- Check pending reboot status.
- Confirm services and event logs.
- Check endpoint protection and monitoring agents.
- Return the host to the cluster or load balancer after health checks pass.

### 9.3. Inspection Tools

PowerShell example to view installed hotfixes:

~~~powershell
Get-HotFix | Sort-Object InstalledOn -Descending
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
Get-Service -Name EventLog | Select-Object Name, Status
~~~

**Get-HotFix** does not necessarily reflect every component or update type completely. Use additional reports from your patch management system and Windows Update history to verify actual state.

## 10. Patch Management for Containers and Serverless

### 10.1. Container Images

Container images package user space and application dependencies. When a base image or package has a vulnerability, you must:

1. Update the base image to a supported version.
2. Update dependencies according to lockfiles and compatibility.
3. Rebuild the image via a trusted pipeline.
4. Scan for vulnerabilities and generate an SBOM if supported by the workflow.
5. Run functional, integration, and security tests.
6. Sign and publish the new image.
7. Roll out pods via canary or rolling update.
8. Verify that running workloads are actually using the new digest.

Do not patch packages inside a running container. When a pod is recreated, manual changes are lost and the vulnerable image remains in the registry. Rebuild and redeploy verified artifacts instead.

### 10.2. Container Hosts

With Kubernetes or self-managed container platforms, you still need to patch the node OS, kernel, container runtime, CNI, CSI, device plugins, and agents. Updating application images does not update the host.

Node patching typically involves cordoning, draining according to disruption budgets, updating or replacing the node, verifying node Ready status, and uncordoning scheduling. Check stateful workloads, local storage, and disruption limits before draining.

With managed Kubernetes services, the provider may manage certain control plane components or node images depending on the service. Teams must still track supported versions, upgrade schedules, and published patch responsibilities.

### 10.3. Serverless and Managed Services

The provider typically handles patching the underlying host and parts of the base runtime. Users remain responsible for updating:

- The runtime version used by the application.
- Packaged libraries and dependencies.
- Layers, extensions, or custom runtimes.
- Container images if using serverless containers.
- Application code and security configuration.

Track runtime deprecation notices and migrate to supported versions before deadlines. Managed does not mean every application dependency is updated automatically.

## 11. Scheduling, Maintenance, and Minimizing Disruption

### 11.1. Maintenance Windows

A maintenance window is a defined period for performing updates that may impact service. Windows should be based on criticality, traffic patterns, dependencies, and recovery capability.

A maintenance plan should specify:

- Start and end times.
- Affected systems and host groups.
- Owners and communication channels.
- Services needing draining or failover.
- Patch, reboot, and verification steps.
- Stop thresholds and completion criteria.
- Recovery plan.

A maintenance window does not replace a safe rollout. Whenever possible, update one node or small batch at a time while the rest continue serving traffic.

### 11.2. Rolling Updates

For multi-host fleets, rolling updates patch small batches at a time instead of stopping everything at once. Maintain sufficient capacity throughout the process and ensure healthy replicas can handle the load.

In Kubernetes, combine rolling updates, readiness probes, PodDisruptionBudgets, and node draining. For VM scale sets or autoscaling groups, replace instances in batches using the updated image. Specific settings depend on the platform.

### 11.3. Quorum and Stateful Services

Database clusters, queuing systems, or control planes may require quorum. Patching too many nodes simultaneously can break quorum and cause downtime or loss of write availability.

Follow product-supported update ordering, verify replica lag, leader/follower states, and failover readiness. Never drain or reboot a node based solely on nominal replica counts; confirm that the remaining replicas are genuinely healthy.

## 12. Rollback and Post-Patch Recovery

### 12.1. Rollback Is Not Always Simple

Not every patch can be safely uninstalled. Packages can alter schemas, data formats, kernel structures, or application state. Removing a newer package might not restore the previous state.

Before patching, identify the appropriate recovery option:

- Restorable snapshots or backups.
- Retained and still-compatible older images.
- Ability to replace failed VMs with new VMs.
- Ability to shift traffic back to an unpatched host group.
- Tested database recovery or failover procedures.
- Ability to restore related configurations and secrets.

### 12.2. Prefer Replacing Hosts from a Known-Good Image

For stateless VMs, spinning up new instances from an approved image is usually easier than bulk-uninstalling packages to revert state. You can deploy the new image to a canary group, retain the old image during the observation period, and shift traffic once health checks pass.

For stateful workloads, decouple compute lifecycle from data. Restoring snapshots or backups must follow application procedures and verify data integrity before returning traffic.

### 12.3. Rollback and Security

If a patch fixes an actively exploited vulnerability, rolling back to a vulnerable version can re-expose the risk. If rollback is required due to compatibility failures, implement temporary mitigations, restrict exposure, and set a clear remediation deadline.

Rollback is a service recovery method; it does not automatically prove the system is back in a secure state. Re-evaluate both functionality and security risk after rolling back.

## 13. Measuring Compliance and Patch Effectiveness

### 13.1. Metrics to Track

| Metric | Meaning |
|---|---|
| Patch compliance rate | Percentage of hosts meeting the patch policy |
| Missing critical patches | Number of hosts missing critical patches |
| Mean time to patch | Average time from patch release/assessment to application |
| Reboot compliance | Percentage of hosts rebooted when required by patches |
| Failed patch rate | Percentage of failed update attempts |
| Configuration drift | Number of hosts diverging from the baseline |
| Unsupported OS count | Number of hosts running an end-of-life OS |
| Exception age | Duration an exception has remained active |
| Image age | Age of the image currently used to provision hosts |
| Coverage | Percentage of hosts with complete inventory, agents, and reporting |

Do not report only an aggregate patch rate. Break metrics down by severity, role, environment, OS, and owner group. A high overall rate can mask critical production hosts that remain unpatched.

### 13.2. Offline and Ephemeral Hosts

Stopped, isolated, or job-only hosts may miss regular patch cycles. Establish policies for:

- Hosts that boot on schedule and self-patch before serving traffic.
- Autoscaling nodes provisioned from updated images.
- Short-lived ephemeral hosts.
- Hosts disconnected from the management system.
- Hosts in recovery or disaster recovery environments.

For autoscaling fleets, the sustainable approach is updating images and launch templates so new instances always launch from a patched foundation, while gradually replacing running older instances.

### 13.3. Reporting and Evidence

A solid patch report should answer:

- How many hosts are in scope?
- How many hosts patched and rebooted successfully?
- Which hosts are still missing critical patches?
- Why have the remaining hosts not been updated?
- Who owns each exception and when does it expire?
- Did the patch cycle cause errors or impact SLAs?
- Is there evidence of testing and recovery readiness?

Data should be pulled from inventory, patch managers, agents, and monitoring systems. Avoid marking compliance solely because an automation job exited with code 0.

## 14. Example Workflow for a VM Fleet

An API service runs across 30 VMs in multiple zones. The operations team uses a golden image and configuration management to maintain the baseline. Each month, the OS vendor releases security updates.

Workflow:

1. Inventory identifies all 30 VMs, OS versions, zones, owners, and current images.
2. The team reviews advisories, identifies affected packages, and determines priority.
3. The pipeline builds a new image from a trusted base image, installs patches, applies hardening, and runs scans.
4. The new image is deployed to staging; API, database, logging, and monitoring are tested.
5. One canary VM in production is replaced with an instance from the new image.
6. Error rate, latency, CPU, memory, and health checks are monitored.
7. If stable, small batches are replaced across zones while maintaining sufficient serving replicas.
8. After each batch, package versions, kernel, agents, and load balancer registration are verified.
9. At the end of the cycle, all 30 VMs are reconciled, failures handled, and compliance reports updated.
10. The previous image and rollback plan are retained for the defined period; expired images are then retired per policy.

Because the API is stateless, the team can replace hosts via rolling replacement. If this were a database, additional replication, quorum, backup, and specific patch ordering plans would be required.

## 15. Common Mistakes

**Using one baseline for every role.** Databases, bastions, and web servers have different requirements. Use a foundational baseline combined with role-based profiles.

**Building an image once and using it forever.** Golden images become stale too. Track versions, build dates, rebuild schedules, and actively deployed images.

**Installing patches directly on individual hosts without tracking.** The fleet will drift and become hard to reproduce. Use a pipeline or patch manager with reporting.

**Disabling services or hardening via checklist without testing.** This can break applications, agents, or administrative access. Test by role and prepare a recovery plan.

**Treating updated packages as an updated kernel.** The new kernel may not be active until reboot, unless live patching is supported and verified.

**Patching the entire fleet at once.** A bad patch can impact every replica. Use rings, canaries, and spare capacity.

**Relying solely on CVSS.** Priority also depends on active exploits, exposure, host role, and protected data.

**Forgetting to patch container base images and dependencies.** Even with patched hosts, application images can still contain vulnerable libraries.

**Assuming managed services automatically update everything.** Providers manage hosts per the service agreement; application dependencies and runtimes may still be the customer's responsibility.

**Rolling back without re-evaluating security.** Older versions can re-open vulnerabilities. Apply compensating controls and set a remediation deadline.

**Marking success when the automation job finishes.** Verify actual versions, reboots, service health, and real host state.

## 16. Baseline and Patch Management Checklist

### Baseline

- [ ] Select a supported OS, version, and architecture.
- [ ] Define a foundational baseline and role-specific profiles.
- [ ] Standardize packages, services, and repository sources.
- [ ] Manage accounts, authentication, sudo/administrator rights, and secrets.
- [ ] Configure SSH/RDP and secure administrative access paths.
- [ ] Define firewall, network, DNS, and time synchronization.
- [ ] Enable logging, auditing, monitoring, backups, and security agents.
- [ ] Define encryption, file permissions, and data retention.
- [ ] Reference appropriate benchmarks and record time-bound exceptions.
- [ ] Store configuration in version control and monitor for drift.

### Golden Images and Automation

- [ ] Use base images from trusted sources.
- [ ] Install approved patches and package versions.
- [ ] Apply hardening and test by role.
- [ ] Scan vulnerabilities, inspect artifacts, and store metadata/SBOM.
- [ ] Never embed credentials or host-specific data in images.
- [ ] Version images and update launch templates/IaC.
- [ ] Maintain a process to replace older instances with new images.

### Patch Management

- [ ] Maintain complete inventory and owners for every host.
- [ ] Track advisories, CVEs, exploits, and exposure levels.
- [ ] Define SLAs by risk and criticality.
- [ ] Test patches in staging or a representative group.
- [ ] Plan maintenance windows, capacity, and rollout order.
- [ ] Use canary/rings and stop thresholds.
- [ ] Verify reboot requirements or live patches.
- [ ] Check services, agents, health checks, and performance after patching.
- [ ] Maintain tested backups, older images, or recovery plans.
- [ ] Reconcile succeeded, failed, and exempted hosts.
- [ ] Report compliance and remediation timelines by risk level.

## 17. Key Takeaways

- A **baseline** defines the approved standard configuration for an operating system or workload role.
- **Hardening** reduces the attack surface by restricting packages, services, privileges, and network flows.
- A **golden image** packages the initial state; the baseline is further maintained via configuration management and policies.
- **Configuration drift** is the gap between actual state and desired state; it must be detected and remediated in a controlled manner.
- **Patch management** covers inventory, assessment, testing, rollout, reboot, verification, and reporting.
- Prioritize patches based on severity, active exploits, exposure, and asset role.
- Ring/canary deployments limit blast radius when a patch causes issues.
- Kernel patches may require a reboot; live patching applies only to vendor-supported subsets.
- Containers require rebuilding and redeploying images; hosts and nodes still have their own patch cycles.
- Rollback must consider both service recovery and the security risks of reverting to an older version.
- Compliance must be based on actual host state, not just automation exit codes.

## Glossary

| Term | Meaning |
|---|---|
| Configuration baseline | Approved set of standard configurations for a system or server role. |
| Hardening | Reducing the attack surface by configuring the OS and services more securely. |
| Patch management | The process of assessing, testing, deploying, and verifying updates. |
| Golden image | Standardized and approved server image used to provision VMs. |
| Configuration drift | Divergence between a host's actual state and its desired baseline. |
| CVE | Common Vulnerabilities and Exposures, public identifiers for security flaws. |
| CVSS | Common Vulnerability Scoring System, a framework for scoring vulnerability severity. |
| KEV | Known Exploited Vulnerabilities, a catalog of vulnerabilities observed being exploited. |
| CIS Benchmark | Security configuration recommendations organized by platform and version. |
| SBOM | Software Bill of Materials, an inventory of software components within an artifact. |
| Maintenance window | Approved time period for performing maintenance activities. |
| Canary deployment | Rolling out a change to a small subset before expanding broadly. |
| Rolling update | Updating instances or nodes sequentially in batches to maintain service availability. |
| Live kernel patching | Applying certain kernel patches to a running kernel without an immediate reboot. |
| Immutable infrastructure | A model of replacing hosts with new artifacts rather than making ongoing in-place edits. |
| Compliance | The degree to which a system meets baselines, policies, and control requirements. |
| Reboot pending | State where updates are installed but a restart is required to finish applying them. |
