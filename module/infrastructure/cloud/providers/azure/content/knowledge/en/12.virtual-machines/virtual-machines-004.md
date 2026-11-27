# Initializing Configuration with cloud-init and VM Extensions

An Azure virtual machine freshly created from an Ubuntu image typically contains only the operating system, an admin account, and basic networking. Production applications also need software packages, configuration files, background services, monitoring agents, and operational policies. If configured manually over SSH on every machine, deployment teams easily miss steps, introduce drift between dev/prod environments, and struggle to recover when replacing machines.

On Microsoft Azure, there are two primary ways to automate this work:

- **cloud-init**: initializes Linux machines from configuration data supplied during provisioning, typically on first boot.
- **Azure VM extensions**: install agents or execute configuration tasks on an Azure-managed VM through the **Azure VM Agent**, including after the VM has been created.

Both mechanisms complement each other, yet differ in lifecycle, responsibilities, verification methods, and security risks. This lesson belongs to the **Azure Virtual Machines** chapter, connecting deployment, monitoring, and protection of Azure applications across subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and cost control.

## Learning Objectives

After this lesson, you will be able to:

1. Explain how VM provisioning, bootstrapping, and configuration management differ.
2. Write a **cloud-config** file to install packages, create configuration files, and start services on a Linux VM.
3. Use Azure CLI's **custom data** option and inspect cloud-init logs after VM creation.
4. Distinguish **Azure VM Agent** from cloud-init and identify the role of VM extensions.
5. Configure an illustrative **Custom Script Extension** on Linux and inspect extension status.
6. Design safe idempotent steps handling dependencies, secrets, networking, and software sources.
7. Diagnose failures in cloud-init, extensions, permissions, and application startup.
8. Choose the right mechanism for VM architectures, VM Scale Sets, and Infrastructure as Code workflows.

## 1. Provisioning and Bootstrapping in the VM Lifecycle

**Provisioning** is the process where Azure allocates VM resources: selecting the image, creating the OS disk, NIC, allocating compute, and preparing the operating system. **Bootstrapping** consists of the steps that turn a freshly created machine into a workload-ready node, such as installing Nginx, configuring time sync, creating data directories, and enabling a service.

**Configuration management** spans beyond bootstrapping: ensuring configuration stays accurate as applications evolve, machines are patched, and operational policies change. Systems like Ansible, Chef, Puppet, DSC, or dedicated deployment pipelines can complement cloud-init and VM extensions.

~~~text
ARM / Bicep / Terraform / Azure CLI
             |
             v
       Azure creates VM
             |
             v
   Image + OS disk + NIC + compute
             |
             v
 Linux boot, cloud-init reads custom data
             |
             v
 Install packages / write config / start services
             |
             +--------> Application ready?
             |
             v
 VM Agent manages VM extensions
             |
             v
 Monitoring agents / Custom Script / extra config
             |
             v
 Health checks + logs + monitoring + operations
~~~

The diagram above illustrates responsibilities and **does not guarantee strict ordering across all cloud-init tasks and extensions**. In real deployments, an extension may be declared and executed while the VM is still finishing bootstrap. If an extension depends on cloud-init results, you must implement synchronization or readiness checks rather than assuming “VM provisioning succeeded means all scripts are done.”

## 2. Comparing cloud-init and VM Extensions

| Criterion | cloud-init | Azure VM extension |
|---|---|---|
| Execution context | Inside the guest OS as cloud-init runs initialization stages | Inside the guest OS, coordinated by the VM Agent and extension handler |
| Typical OS | Linux images with supported cloud-init | Linux or Windows depending on the extension |
| Timing | Primarily when creating and booting a new OS instance; per-module frequency depends on cloud-init | When the extension is deployed/updated and as triggered by the extension model |
| How configuration is supplied | Custom data cloud-config, user-data, scripts, or supported datasource config | Extension resource with public settings/protected settings |
| Best used for | Installing packages, writing files, users, base config, first-boot steps | Installing agents, running admin scripts, integrating Azure features |
| Re-execution | Do not rely on rebooting to rerun the entire cloud-config | Can update settings/force-update per extension mechanism |
| Key dependencies | Image supporting cloud-init, DNS/routing/repositories, scripts | Azure VM Agent, extension handler, access to required artifacts/services |
| Monitoring | cloud-init status, logs, and application state | Azure extension status/substatus, extension logs, and application state |
| Secrets management | Never put passwords/tokens in custom data | Use protected settings/identity where supported; still protect logs and host |

**Quick rule of thumb:** initial base setup of a Linux VM on first boot typically fits cloud-init; enabling Azure Monitor Agent, running Custom Script after creation, or managing tasks via ARM calls for VM extensions. A production application may need **both**.

### Cloud-init Is Not the Azure VM Agent Service

On many Azure Linux images, **cloud-init** receives initialization data from the Azure datasource. **Azure Linux Agent (waagent)** may still be present to support Azure VM Agent and extension functionality. Do not disable or remove the VM Agent merely because cloud-init handles provisioning; doing so can break extensions or VM management operations.

For **Windows VMs**, Azure does not use Linux cloud-init as shown in this lesson. Options typically involve image customization, unattend files, PowerShell, Custom Script Extension for Windows, or corresponding configuration management tools.

## 3. What Is cloud-init and cloud-config Syntax?

**cloud-init** is a Linux instance initialization tool capable of creating users, configuring SSH keys, installing packages, writing files, and running commands. On Azure, the Linux image must include a supported cloud-init version and platform integration components.

A **cloud-config** file typically begins with the line:

~~~yaml
#cloud-config
~~~

Followed by YAML containing keys supported by cloud-init. Common keys:

| Key | Role |
|---|---|
| **package_update** | Refreshes package metadata before installation per distro behavior |
| **packages** | List of packages to install via the OS package manager |
| **write_files** | Creates file contents and sets owner/permissions |
| **users** | Declares or modifies users according to supported schema |
| **runcmd** | Declares commands to run at the appropriate cloud-init stage |
| **bootcmd** | Early boot tasks; may run repeatedly depending on module frequency |
| **final_message** | Message logged when cloud-init finishes |

cloud-init runs multiple stages and modules with different **frequencies**: per-instance, per-boot, per-once. Do not assume every key reruns on every reboot. In particular, **runcmd** usually executes during the final stage of initial instance creation, not as a continuous configuration maintenance tool on every VM startup.

### Example cloud-config to Install Nginx

This example targets an **Ubuntu VM using an image with cloud-init support**. Save the file as **cloud-init.yaml** on the machine running Azure CLI:

~~~yaml
#cloud-config
package_update: true

packages:
  - nginx

write_files:
  - path: /opt/bootstrap/site-index.html
    owner: root:root
    permissions: '0644'
    content: |
      <!doctype html>
      <html lang="en">
        <head><meta charset="utf-8"></head>
        <body><h1>Azure VM initialized with cloud-init</h1></body>
      </html>

runcmd:
  - [install, -m, '0644', /opt/bootstrap/site-index.html, /var/www/html/index.html]
  - [systemctl, enable, --now, nginx]

final_message: "cloud-init has completed basic bootstrap."
~~~

How it works:

1. **package_update** refreshes the package index.
2. **packages** installs Nginx using the OS package manager.
3. **write_files** writes a source file outside the document root, avoiding reliance on the package's default HTML file.
4. **runcmd** copies the content to the web directory after package installation and enables/starts Nginx.
5. **final_message** marks completion clearly in the logs.

If repositories are unreachable, a package does not exist in the image, or the service fails to start, cloud-init can fail even though the VM appears created in the Azure portal. You must verify results **from inside the VM**, not only via the ARM resource status.

### Why Use YAML Format and a Separate File?

cloud-config fits naturally into version control and code review, though YAML is sensitive to indentation, data types, and quoting. Even a single indentation mistake can invalidate keys or list schemas.

Never embed passwords, connection strings, SAS tokens, or private keys in cloud-config. **Custom data is not designed to store secrets.** Initialization content and outputs may be persisted by the provisioning system, on the guest disk, or in logs depending on platform behavior; anyone with sufficient VM/guest management access should be assumed able to read this data.

## 4. How Is cloud-init Passed to an Azure VM?

When creating a Linux VM, Azure provides the **custom data** mechanism. Azure CLI offers the **--custom-data** option accepting a file path; the CLI handles encoding when sending the VM creation request. Do not manually base64-encode the file before passing it to standard CLI flags, or it may be double-encoded.

Notes:

- Custom data has an Azure-enforced **size limit**, commonly documented as a maximum of **64 KiB of unencoded content**. Do not use it to embed installers or large binaries.
- The Linux image must support cloud-init properly. Some custom or legacy images do not process cloud-config automatically.
- cloud-init reads initialization data and runs modules per their configured frequencies; editing custom data in management configuration after the VM is provisioned **does not mean cloud-init will automatically rerun** as on creation.
- Rebooting and reimaging behave differently; if the OS disk is recreated, re-initialization behavior must be verified against your image and process.
- Package installation steps require working networking, DNS, proxies, and repository access.

### Related Configuration Layers

| Layer | Examples |
|---|---|
| Azure control plane | Subscription, resource group, VM size, image, NIC, NSG, managed identity |
| Guest initialization data | cloud-config via custom data |
| Guest networking | IP/DNS/routing, proxy, apt repositories, internal endpoints |
| Workload | Nginx, API application, service configuration |
| Post-initialization management | VM extensions, Azure Monitor Agent, updates, configuration changes |

For example, cloud-init can install Nginx, but it **does not assign a Public IP to the VM or open NSG ports**. To let external users reach the website, you must design the ingress layer (Load Balancer/Application Gateway), DNS, NSGs, and network security separately.

## 5. Hands-On: Creating a Linux VM with cloud-init

This is a **lab that creates real resources and can incur costs**. Perform it only in an authorized subscription with verified quota and budget. Commands are illustrative for learning; before running them, verify image aliases, VM sizes, networking, and environment policies.

### Step 1: Prepare CLI and SSH Keys

Sign in and select the target subscription:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{name:name,id:id}" --output table
~~~

Prepare your SSH key pair. Never commit private keys to a repository. The command below assumes your public key is at **~/.ssh/id_ed25519.pub**; substitute your actual path if different.

### Step 2: Save cloud-config

Create **cloud-init.yaml** with the full example from section 3. Verify it is UTF-8, begins with the exact line **#cloud-config**, and uses valid YAML indentation for **packages**, **write_files**, and **runcmd**.

### Step 3: Create the Resource Group

~~~bash
az group create \
  --name rg-vm-init-lab \
  --location southeastasia
~~~

### Step 4: Create a VM from a cloud-init-Enabled Image

~~~bash
az vm create \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --location southeastasia \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/id_ed25519.pub \
  --custom-data ./cloud-init.yaml \
  --public-ip-address ""
~~~

**Operational notes:**

- The image alias **Ubuntu2204** and VM size **Standard_B2s** are illustrative; verify SKU/image availability in your region and subscription.
- **--public-ip-address ""** intentionally avoids assigning a direct Public IP to the machine, requiring a private management path such as Azure Bastion, VPN, or VNet connectivity. Some environments enforce using pre-existing subnets/VNets; pass network parameters matching your architecture.
- Azure CLI may create supporting network resources automatically if you omit explicit VNet/NIC flags. In production, declare VNets, subnets, and NSGs explicitly in controlled IaC.
- **az vm create** returning success does not prove the HTML page or Nginx is working; inspect the guest OS and service.

### Step 5: Verify Inside the VM

Once connected to the VM via an authorized management path, run:

~~~bash
cloud-init status --wait
cloud-init status --long

sudo tail -n 100 /var/log/cloud-init.log
sudo tail -n 100 /var/log/cloud-init-output.log

systemctl is-active nginx
curl -fsS http://127.0.0.1/
~~~

Expected results:

- cloud-init finishes without blocking bootstrap errors.
- Nginx is **active**.
- Local HTTP request to **127.0.0.1** returns the HTML page created by cloud-config.

**If the VM has no Public IP**, do not try to SSH directly from the Internet. The lab intentionally separates guest bootstrapping from exposing application ports publicly.

### Step 6: Verify from the Azure Control Plane

~~~bash
az vm show \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --query "{name:name,state:provisioningState,location:location}" \
  --output json

az vm get-instance-view \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --output json
~~~

These commands inspect VM state from Azure's perspective. They do not replace **cloud-init status**, logs, or application health checks inside the machine.

## 6. Azure VM Agent and the Extension Mechanism

The **Azure VM Agent** is a guest component enabling Azure to manage extensions inside a VM. On Linux, the Azure Linux Agent is commonly called **waagent**. Azure orchestrates extension installation requests from the control plane; the VM Agent receives the configuration, invokes the corresponding **extension handler** inside the OS, tracks status, and reports results back.

Involved components:

~~~text
Azure Resource Manager
        |
        v
VM extension resource
  publisher / type / version
  settings / protectedSettings
        |
        v
Azure VM Agent inside guest
        |
        v
Extension handler
        |
        v
Script / agent install / config task
        |
        v
Status + substatus + logs + app output
~~~

A VM extension is a **child resource** of a VM in Azure Resource Manager. Consequently, extensions can be declared via the Azure portal, Azure CLI, ARM/Bicep, or Terraform depending on your deployment workflow.

### Common Extension Types

| Type | Illustrative purpose |
|---|---|
| **Custom Script Extension (Linux)** | Download/execute custom scripts for configuration or administrative tasks |
| **Custom Script Extension (Windows)** | Execute equivalent scripts on Windows VMs; publisher/type differ from Linux |
| **Azure Monitor Agent extension** | Install telemetry collection agent for Azure Monitor, paired with Data Collection Rules as needed |
| Management and security extensions | Install components for monitoring, authentication, or supported Azure capabilities |

Publisher names, extension types, versions, and OS support **cannot be mixed arbitrarily**. For example, Custom Script for Linux typically uses publisher **Microsoft.Azure.Extensions** and type **CustomScript**, whereas Custom Script for Windows uses a different publisher/type.

### Public Settings vs. Protected Settings

An extension accepts **settings** and optionally **protectedSettings**. Public settings are treated as configuration readable from ARM with appropriate permissions; **never place secrets in public settings**. Protected settings are protected by the extension mechanism, though this does not guarantee script logs, guest processes, or temp files are safe. Prefer managed identities, Azure Key Vault, and least-privilege access whenever possible, and avoid printing secrets to stdout/stderr.

Do not use Custom Script Extension as long-term password storage. If a script needs internal artifacts or packages, design authenticated downloads with integrity verification and scoped repository access.

## 7. Custom Script Extension: Example Configuration on Linux

**Custom Script Extension** (CSE) runs scripts/commands on a VM via the VM Agent. It can install applications, create directory structures, or perform post-creation configuration steps. It is not a continuous state-enforcement tool that guarantees “a machine stays compliant forever” unless paired with broader deployment and validation processes.

### Example Extension Without Downloading External Scripts

Suppose **vm-init-lab** already exists and you want to create a **marker** confirming the extension task executed. Create **cse-settings.json** with:

~~~json
{
  "commandToExecute": "/bin/sh -c 'mkdir -p /opt/bootstrap && touch /opt/bootstrap/extension-ready'"
}
~~~

This illustrative command downloads no artifacts and uses no secrets. It creates a marker at **/opt/bootstrap/extension-ready**; re-running it produces no harmful duplicate state. After confirming VM Agent health, permissions, and environment budget, deploy the extension:

~~~bash
az vm extension set \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --publisher Microsoft.Azure.Extensions \
  --settings @cse-settings.json
~~~

Here the CLI uses **@cse-settings.json** to read JSON from a local file on the CLI workstation. The extension name, publisher, and settings schema must match the Linux handler supported on the image/region. This command **modifies a real VM resource**—run it only in an authorized lab.

### Checking Extension Status

~~~bash
az vm extension show \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --output json

az vm get-instance-view \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --output json
~~~

Inside the guest, verify the marker:

~~~bash
test -f /opt/bootstrap/extension-ready \
  && echo "Extension task completed"
~~~

Check handler logs or status for your installed extension version; Linux logs are commonly located under **/var/log/azure/**. Exact paths and folder names vary by publisher/type/version; never assume the extension succeeded solely because the deployment command returned.

### When Executing Scripts Downloaded from Storage

Another realistic scenario has CSE fetch a versioned script from Azure Blob Storage and execute it. Design checklist:

1. Store **setup.sh** in a trusted, reviewed, versioned artifact source.
2. Configure access using an extension-supported authentication mechanism, avoiding long-lived SAS tokens in public settings.
3. Verify artifact checksums/signatures before execution where possible.
4. Keep the script idempotent, with explicit exit codes and timeouts.
5. Never let the script write secrets to logs.

Avoid patterns that download arbitrary unverified scripts from the Internet and execute them immediately, especially on privileged production VMs. CSE typically runs with system-level privileges; its blast radius is larger than a normal user command.

### Extensions Are Not an Automatic “Rerun” Switch

Custom Script Extension does not necessarily re-execute when you reboot the VM or reapply an identical declaration. Settings updates, handler version changes, or **force update** trigger re-execution according to the extension and Azure rules. To rerun intentionally, use a supported configuration update mechanism and write scripts so repeated execution causes no errors.

If an extension reports provisioning succeeded yet the application is not ready, still verify the real effects: files created, processes running, endpoints returning expected responses, and dependencies reachable.

## 8. Combining cloud-init and Extensions Together

A clean separation of responsibilities:

| Step | Mechanism | Expected outcome |
|---|---|---|
| Create VM/NIC/managed identity | ARM/Bicep/Terraform/Azure CLI | Machine and identity/access foundation provisioned |
| Create users, update packages, install Nginx | cloud-init | Guest OS baseline bootstrapped |
| Install Azure Monitor Agent | VM extension | Agent installed per config and assigned permissions |
| Configure Data Collection Rule | Azure Monitor + ARM/IaC | Telemetry flows to target workspace/destination |
| Deploy application release | Deployment pipeline/suitable extension | Versioned artifact deployed and health-checked |
| Monitor state and rollback | Azure Monitor, logs, release process | Faults detected and recovered per runbook |

In this flow:

- cloud-init handles **bringing the OS to its initial baseline configuration**.
- Custom Script Extension creates a marker or executes supplementary configuration steps.
- Azure Monitor Agent (if deployed) collects telemetry per the DCR.
- Application Gateway/Load Balancer (if present) routes traffic only to instances passing health probes.

### Managing Dependencies Between Steps

Do not assume an extension always runs **after all `runcmd` tasks finish** just because resources appear in the same template. If an extension depends on Nginx or files created by cloud-init:

1. Separate responsibilities cleanly; prefer using the same mechanism for tightly coupled steps.
2. Have the extension script check readiness conditions before executing dependent tasks.
3. Enforce timeouts and fail clearly if prerequisites never appear.
4. Coordinate ordering in pipelines/IaC where supported, while still checking guest-side state.
5. Retest across rebuilds, reimages, and image updates.

Example readiness check inside a script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

for attempt in $(seq 1 30); do
  if systemctl is-active --quiet nginx; then
    echo "Nginx is ready"
    exit 0
  fi
  sleep 10
done

echo "Nginx was not ready before timeout" >&2
exit 1
~~~

This script is illustrative; real checks might wait for a config file, query an HTTP health endpoint, or verify database connectivity. Never use infinite loops because extensions enforce execution timeouts and can stall deployments.

## 9. Writing Idempotent and Recoverable Scripts

**Idempotency** means running a task multiple times does not push the system into an unwanted state. This is essential because VMs may be recreated from images, deployments retried, or extensions updated.

Pattern to avoid:

~~~bash
echo "10.10.10.10 db.internal" >> /etc/hosts
~~~

This command appends a duplicate line on every run. A safer approach manages configuration through dedicated files or state-checked replacements.

Example of writing a configuration file more safely:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /etc/myapp

cat > /etc/myapp/app.conf.tmp <<'EOF'
[app]
environment=lab
listen_port=8080
EOF

install -m 0644 /etc/myapp/app.conf.tmp /etc/myapp/app.conf
rm -f /etc/myapp/app.conf.tmp
~~~

In production, write the temp file on the same filesystem, validate configuration syntax, and perform an **atomic rename** before reloading the service. The illustrative snippet above demonstrates repeatability, though it omits full production validation and rollback logic.

### Checklist for a Solid Bootstrap Script

- Include a **shebang**, clear exit codes, and fail fast when critical steps error.
- Avoid relying on implicit execution ordering across mechanisms.
- Ensure idempotency for files, packages, database migrations, and cloud resources.
- Log enough detail for diagnostics while **never logging secrets**.
- Implement timeouts/backoff when waiting for network calls or services.
- Verify artifact versions and checksums/signatures when pulling external inputs.
- Perform post-configuration health checks separate from script exit status.
- Avoid unexpectedly rebooting the VM while an extension is executing.
- Plan for partial failures and rollback/redeploy procedures.

### Bootstrapping Is Not Data Migration

Do not run irreversible database migrations inside every newly created VM unless guarded by proper orchestration and locking. When VM Scale Sets add three instances, the same cloud-init runs on all three machines; if all three alter database schemas concurrently, race conditions can occur. Global actions like schema migrations belong in a controlled deployment pipeline or dedicated single-runner job.

## 10. Security When Using cloud-init and Extensions

### Never Put Secrets in Custom Data

Insecure example:

~~~yaml
#cloud-config
write_files:
  - path: /etc/myapp/secrets.env
    content: |
      DB_PASSWORD=plaintext-example
~~~

This is an **anti-pattern**, not a configuration to use. Custom data is not a secrets vault. Azure VMs can persist configuration/outputs inside the guest; template copies, pipeline logs, or administrative permissions can expose the data.

A more secure architecture:

1. Create a **managed identity** for the VM via the Azure control plane.
2. Assign minimal RBAC/policies allowing that identity to read only required secrets from **Azure Key Vault**.
3. After initialization, the workload or agent retrieves secrets from Key Vault using the managed identity.
4. Enforce TLS and private networking where required; never log tokens or secrets.
5. Configure secret rotation, expiration, and access auditing per policy.

For extensions, **protectedSettings** helps shield sensitive config inside Azure, but it does not replace managed identities or runtime secret management after the script runs. In high-control environments, avoid designs requiring operators to pass passwords directly on command lines.

### Permissions to Deploy Extensions

Anyone authorized to create VM extensions can execute code inside the guest with very high privileges depending on the handler. Restrict roles at subscription/resource group/VM scope, gate changes through IaC pipelines, review scripts, and treat extension edits as security-critical changes.

### Networking and Outbound Internet Access

A VM without a Public IP may still need access to apt repositories, the Azure control plane, monitoring endpoints, or artifact stores. Design an authorized **outbound** path via NAT Gateway, firewall, or supported alternatives, and verify DNS resolution works.

A sound security posture uses curated package/artifact sources, restricted egress, private mirrors/repositories where appropriate, verified checksums, and clear change logs. Never open unrestricted Internet access or disable firewalls simply because cloud-init failed to install a package.

### Configuration and Log Storage

- Never pass secrets in commands captured by **cloud-init-output.log**.
- Restrict read permissions on config files created by **write_files**.
- Extensions can write logs/arguments on the guest; protect both the host and log files according to sensitivity.
- For downloaded scripts, verify source authenticity and integrity prior to execution.
- Keep images, agents, and extensions patched through a regular update workflow.

## 11. Inspecting and Diagnosing cloud-init

### Where to Check Status

Inside the Linux VM:

~~~bash
cloud-init status
cloud-init status --long

sudo less /var/log/cloud-init.log
sudo less /var/log/cloud-init-output.log
~~~

**cloud-init.log** typically records module activity and error details. **cloud-init-output.log** typically captures stdout/stderr from executed tasks. Treat these files as sensitive if a script accidentally printed tokens or application data.

### Distinguishing Failure Modes

| Symptom | Common causes | Verification steps |
|---|---|---|
| cloud-init ignores content | Unsupported image, missing header, malformed/badly encoded custom data | Check image, `#cloud-config` line, datasource logs, and VM creation parameters |
| Package installation fails | Missing DNS/egress, broken repo, apt lock | Check networking/DNS, apt logs, and `cloud-init-output.log` |
| `write_files` creates no file | Invalid YAML indentation/schema, invalid permissions or path | Inspect `cloud-init.log`, verify permissions and file contents |
| `runcmd` behaves unexpectedly | Syntax error, missing dependency, non-zero exit code | Check `cloud-init-output.log` and module status |
| Reboot does not rerun script | Per-instance module already executed | Check frequency; use configuration management for ongoing changes |
| VM shows Succeeded but web app fails | Azure provisioned resources, guest bootstrap/app failed | Inspect `systemctl`, `curl localhost`, cloud-init status, and logs |
| Custom image VM lacks cloud-init | Image not configured with datasource/agent properly | Review image build steps and cloud-init support |

### What to Do When cloud-init Fails

1. Record the VM name, image, creation timestamp, **sanitized** cloud-config (secrets removed), and error codes.
2. Identify the failing stage via status and logs.
3. Categorize the issue: YAML syntax, networking, packages, permissions, or dependencies.
4. Fix the source configuration in your repository/IaC; spin up a fresh lab VM to test first-boot execution cleanly.
5. Only consider rerunning modules or cleaning cloud-init when you understand its mechanism and impact. Running **cloud-init clean** on a live workload VM can trigger unexpected re-execution; do not treat it as a “safe retry button.”

## 12. Inspecting and Diagnosing VM Extensions

Azure CLI commands:

~~~bash
az vm extension list \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --output table

az vm extension show \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --output json
~~~

Inside the Linux guest, inspect:

~~~bash
systemctl status walinuxagent --no-pager
sudo ls /var/log/azure/
~~~

The VM Agent systemd unit name **varies by distro/image**, so if **walinuxagent** is not found, check the actual service name for your image. Extension logs typically live in corresponding subdirectories under **/var/log/azure/**; extension state data also resides in directories managed by the VM Agent.

| Symptom | Possible causes | How to verify |
|---|---|---|
| Cannot install extension | Missing/broken VM Agent, unsupported OS/region type | Check Agent, publisher/type/version, and instance view |
| Handler cannot download script | DNS/route/firewall block, wrong URL, expired SAS | Check endpoints, artifact permissions, and extension logs |
| Extension reports failed | Command returned non-zero exit code or timed out | Inspect status/substatus, handler logs, and sanitized stderr |
| Extension succeeded but app is down | Script lacked app health check or missed steps | Check markers, `systemctl`, TCP/HTTP endpoints, and config files |
| Reapplying same config has no effect | No trigger change for handler | Check update/force-update rules in extension docs |
| Extension depends on cloud-init but runs early | Missing readiness constraint | Add condition/timeout, coordinate ordering, test repeatedly |
| Task hangs during reboot | Script reboots VM mid-extension or bad timing dependency | Check reboot history, VM Agent logs, and script design |

Never manually delete extension installations or VM Agent directories to “reset” state without understanding the impact. Extensions may enforce monitoring or security controls on the VM.

## 13. VM Scale Sets and Multi-Machine Deployments

With **Virtual Machine Scale Sets (VMSS)**, images, custom data, VM extensions, and related settings can be declared in the scale set model as supported by its features and orchestration mode. When a VMSS scales from 2 to 10 instances, new instances must configure themselves automatically without operators SSHing into each machine.

A scalable design should:

- Use a golden image or cloud-init for baseline configuration.
- Use extensions/agents for telemetry, security, and supported deployment steps.
- Keep scripts **idempotent** so each instance runs independently.
- Prevent global operations (such as database migrations) from running concurrently on every instance.
- Use managed identities and Key Vault to fetch sensitive config rather than baking secrets onto every VM.
- Configure load balancer / application gateway health probes so traffic only reaches ready instances.
- Plan rolling upgrades, health checks, and rollbacks when updating the VMSS model or instances.

**Updating a VMSS model does not necessarily update all running instances immediately**: behavior depends on the upgrade policy and model application rules. Verify instance states and rollout policies before assuming a cloud-init or extension change is active across the entire fleet.

### cloud-init, Extensions, or Golden Images?

For large fleets with heavy software stacks, installing hundreds of packages on every VM startup slows down bootstrapping and increases exposure to repository outages. A prebuilt, pretested **golden image** can hold base software, leaving cloud-init to inject lightweight environment settings. Extensions handle Azure-integrated agents or control-plane-coordinated tasks.

The trade-off is that images require ongoing maintenance and patching. Never embed secrets in images, and do not let stale images become a long-term vulnerability source.

## 14. Monitoring, Operations, and Cost

VM initialization does not end when the create command succeeds. In production, define clear readiness milestones:

| Milestone | Evidence |
|---|---|
| VM provisioned | Azure resource exists; VNet/OS disk configuration matches design |
| Guest bootstrap completed | `cloud-init status` and logs show no blocking errors |
| Baseline configured | Packages, services, and config files verified |
| Extension healthy | VM Agent and extension status/substatus meet requirements |
| Application ready | HTTP/TCP/business health checks pass |
| Observability active | Telemetry, logs, and alerts verified |
| Security controls active | RBAC, NSGs, identity, Key Vault, and policies enforced |

### Tracking Bootstrap Duration

Measure the elapsed time from VM creation until the application becomes genuinely healthy. If it takes too long:

- Check package download speeds, network/proxy latency, and repository responsiveness.
- Identify scripts stalling on external services.
- Move heavy installation tasks into image builds or appropriate pipelines.
- Avoid long chains of complex dependencies without timeouts or logging.
- Verify the VM SKU has adequate CPU/RAM/IO for installation work.

### Cost

cloud-init itself is an in-guest initialization mechanism, but the resources it deploys or downloads can generate charges. **VM extensions** can also install components driving additional fees, such as monitoring ingestion, log retention, security tooling, or data transfer. Cost factors to watch:

- VM runtime hours, VM size, and OS/data disks.
- Public IPs, NAT Gateways, firewalls, data transfer, and related networking services.
- Artifact storage, container registries, proxies, or image galleries.
- Azure Monitor / Log Analytics, Application Insights, and data retention.
- Software licensing or third-party agent fees.
- Idle VM billing time wasted during slow bootstrapping.

Set budgets and owner tags on subscriptions/resource groups and monitor Azure Cost Management. Never hardcode fixed VM or extension prices, as rates vary by region, SKU, plan, and time.

## 15. Scenario Exercise: Deploying an API on Linux VMs

A company is deploying an ordering API across three Ubuntu VMs behind Azure Application Gateway. Every VM must launch with the same configuration:

- Install Nginx as a reverse proxy.
- Create **/opt/orders-api** and a configuration file containing no secrets.
- Use a managed identity to access Azure Key Vault.
- Install Azure Monitor Agent and collect logs.
- Accept traffic exclusively from the Application Gateway subnet; assign no Public IPs to backend VMs.
- Automatically replace unhealthy VMs without manual configuration.

Design the following:

1. Which settings belong in the image, cloud-init, and VM extensions?
2. Draft a sample cloud-config to install Nginx, create the config file, and start the service.
3. Describe how to assign the managed identity and Key Vault secret read permissions.
4. Identify the extension needed for telemetry and how Data Collection Rules attach.
5. Explain what happens if an extension depends on Nginx while cloud-init is still installing packages.
6. Propose health checks and verification steps confirming a VM is ready for traffic.
7. Design idempotency, retries, and rollback if bootstrapping fails.
8. List logs/metrics, network rules, and cost drivers to monitor.

**Suggested solution:** a governed image holds the OS and base packages; cloud-init writes first-boot configuration, starts Nginx, and prepares the app directory; extensions deploy Azure Monitor Agent via IaC; managed identity fetches secrets from Key Vault at runtime; Application Gateway routes traffic only to probe-healthy VMs. All instances share identical setup, while database migrations run from a separate pipeline rather than on each VM.

## 16. Production Checklist

| Area | Verification item |
|---|---|
| Scope | Correct subscription, resource group, region, and owner |
| Image | Supported image with required cloud-init / VM Agent support |
| Cloud-config | Valid YAML with header and zero embedded secrets |
| Custom data | Within size limit, proper encoding, peer-reviewed source |
| Networking | DNS, apt repos, artifacts, Key Vault, routing/egress, and NSGs designed |
| IAM | Least-privilege managed identity/RBAC, no static tokens |
| Bootstrap | Packages/files/services complete and app health checks PASS |
| Extension | OS-matched publisher/type/version, healthy VM Agent, status PASS |
| Dependencies | No reliance on implicit ordering; timeouts and coordination in place |
| Repeatability | Idempotent scripts, no duplicate appends, no per-VM data migrations |
| Recovery | Rebuild, rollback, and partial-failure handling documented |
| Monitoring | cloud-init logs, VM extension status, Azure Monitor, and alerts configured |
| Cost | Budgeted VM/disk/network/log/agent spend; lab resources cleaned up |

## 17. Self-Check Questions

1. What is the difference between VM provisioning, bootstrapping, and configuration management?
2. When should you use cloud-init versus a VM extension?
3. What is the required first line of a valid cloud-config file, and why does YAML indentation matter?
4. What roles do **write_files**, **packages**, and **runcmd** perform?
5. Does **az vm create** succeeding prove Nginx is running? How should you verify it?
6. Why should custom data never contain passwords or tokens even when the VM sits in a private subnet?
7. What role does the Azure Linux Agent play for extensions?
8. Why can you not use Windows extension publisher/type values on Linux?
9. How do public settings and protected settings differ? Do protected settings replace Key Vault?
10. Why is rebooting a VM not a reliable way to force cloud-init to rerun everything?
11. When an extension depends on a file created by cloud-init, how should you handle the timing dependency?
12. Why can commands that append lines to config files break idempotency?
13. In VMSS, why should global database migrations not be placed inside each instance's cloud-init?
14. What causes cloud-init package installation to fail even when the Azure control plane reports no VM error?
15. If a VM extension reports Succeeded yet `/health` returns an error, where should investigation continue?
16. Why should you test bootstrapping, agents, and health checks after updating an image or VMSS model?

## References

- Microsoft Learn — *Use cloud-init to customize a Linux VM in Azure*: https://learn.microsoft.com/azure/virtual-machines/linux/using-cloud-init
- Microsoft Learn — *Cloud-init support for Azure VMs*: https://learn.microsoft.com/azure/virtual-machines/linux/cloudinit-prepare-custom-image
- Microsoft Learn — *Virtual machine extensions and features for Linux*: https://learn.microsoft.com/azure/virtual-machines/extensions/features-linux
- Microsoft Learn — *Custom Script Extension for Linux*: https://learn.microsoft.com/azure/virtual-machines/extensions/custom-script-linux
- Microsoft Learn — *Azure Linux VM Agent overview*: https://learn.microsoft.com/azure/virtual-machines/extensions/agent-linux
- Microsoft Learn — *Custom Script Extension for Windows*: https://learn.microsoft.com/azure/virtual-machines/extensions/custom-script-windows
- cloud-init documentation — *Examples and reference*: https://docs.cloud-init.io/en/latest/reference/examples.html
