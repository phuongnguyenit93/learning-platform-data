# User data, startup scripts, and cloud-init on first boot

When creating a virtual machine, operations teams often need to install packages, create service accounts, write configurations, register monitoring agents, and start the application. Performing these steps manually after every VM creation makes the process error-prone, inconsistent across instances, and time-consuming. Cloud platforms provide mechanisms to pass initialization data into a virtual machine, commonly referred to as **user data**, **startup scripts**, or **custom data**. On Linux, **cloud-init** is a widely used tool for reading metadata and automating those initialization steps.

This lesson explains how bootstrap mechanisms work on first boot, how to structure scripts so they can run repeatedly and safely, how to protect sensitive information, and how to inspect a machine when initialization fails to complete. The goal is to build a consistent, testable, and observable startup workflow in a VM environment.

## 1. What is bootstrap?

Bootstrap is the process of preparing a virtual machine to run workloads after the platform provisions the machine. Typical steps include:

- Identifying the environment and reading instance metadata.
- Configuring the hostname, network, or environment information.
- Creating users and configuring access permissions.
- Installing required packages, runtimes, and agents.
- Writing configuration files for the application.
- Fetching configuration or secrets from an appropriate management service.
- Registering the machine with monitoring, configuration management, or service discovery systems.
- Starting services and verifying health checks.

Bootstrap takes place after the VM is created and begins booting. It can run during operating system startup or through an agent/extension after the operating system is already up. Therefore, **a VM in the running state does not mean the application is ready**.

### Distinguishing image, user data, and startup script

| Component | Role | Example |
|---|---|---|
| Machine image | Provides the operating system and pre-prepared base software | Linux image with runtime and monitoring agent |
| User data / custom data | Data or instructions passed in when creating the VM | Cloud-config, shell script, PowerShell |
| Startup script | Program executed during the initialization phase or at boot | Install packages, generate configuration, start services |
| Cloud-init | Tool that reads datasource/metadata and orchestrates initialization modules on Linux | Create users, write files, install packages, run commands |
| Configuration management | Long-term configuration management after bootstrap | Ansible, Puppet, Chef, or an internal agent |

The image should contain stable, tested base components. User data typically supplies environment- or instance-specific configuration. The startup script performs the actions needed to connect those two parts.

Do not place full application data or secrets in the image or user data. Values that vary by environment should be supplied via non-sensitive metadata, a configuration system, or a secret manager with restricted access.

## 2. Boot flow and where cloud-init fits

A Linux boot flow on a VM can be summarized as follows:

~~~mermaid
flowchart TD
    A["Cloud provisions VM from image"] --> B["Firmware and bootloader"]
    B --> C["Kernel and init system"]
    C --> D["Network and background services"]
    D --> E["cloud-init detects datasource"]
    E --> F["Reads metadata and user data"]
    F --> G["Runs bootstrap modules"]
    G --> H["Installs packages, writes config, creates users"]
    H --> I["Starts application and agents"]
    I --> J["Health check and readiness"]
    J --> K["VM is placed into traffic rotation"]
~~~

Actual details depend on the image, operating system, provider agent, and network configuration. On many cloud Linux images, cloud-init is built in and runs via systemd services.

### Datasource and metadata

Cloud-init needs to know what environment it is running in and where to obtain initialization data. This source is called a datasource. In the cloud, the datasource usually accesses a metadata service or information provided by the platform to the instance.

Metadata may contain:

- Instance ID and machine identification information.
- Region, zone, or project/account.
- Network interfaces and IP addresses.
- Role or identity information assigned to the machine.
- User data or custom data.
- Attributes used for environment configuration.

Not every datasource provides the same data fields. Scripts should verify that values exist and handle missing metadata gracefully.

### Metadata service as a security boundary

The metadata service should normally only be accessible from inside the VM. If an application has an SSRF (Server-Side Request Forgery) vulnerability, an attacker may try to access metadata to obtain identity details or temporary credentials.

Risk mitigation measures:

- Use platform-provided metadata protection mechanisms, such as required tokens or protected metadata versions.
- Do not allow applications to accept arbitrary URLs and issue server-side requests to them.
- Restrict metadata access within the application and network namespaces if supported by the platform.
- Assign instance roles/service identities with least privilege.
- Do not store long-lived credentials in configuration files.
- Monitor for anomalous metadata access.

On AWS EC2, IMDSv2 uses a token for metadata requests and can be configured as required. This is a specific example of metadata protection; other platforms have their own models and options.

## 3. User data, custom data, and startup scripts

The terminology varies by provider, but the core idea is passing data or instructions into a VM when creating or configuring the machine.

### User data

User data is typically attached to an instance or launch configuration. Its content can be:

- A shell script on Linux.
- Cloud-config for cloud-init.
- MIME multipart containing multiple content types.
- Text or configuration data processed by a platform agent.

User data may be stored in metadata or an equivalent mechanism. Read permissions for user data must be controlled because the content may contain internal configuration details.

### Startup script

A startup script is a program that runs when the machine starts or during a specific phase. Depending on the platform, the script can be provided through metadata, an extension, a guest agent, or the VM configuration.

It is important to distinguish between:

- Scripts that run only during initial creation.
- Scripts that run on every machine boot.
- Scripts triggered by events or extensions initiated by operators.
- Scripts managed as long-running OS services.

A script that runs on every boot must be safe to execute multiple times. If every boot creates duplicate users, installs packages uncontrollably, or overwrites runtime data, the machine can enter an invalid state.

### Cloud-init

Cloud-init is a common initialization tool on Linux cloud images. It reads user data and the datasource, then runs modules by stage. Cloud-init supports multiple input formats such as cloud-config, shell scripts, and MIME multipart.

Cloud-init can:

- Set the hostname and create users.
- Manage SSH authorized keys.
- Install packages.
- Write files.
- Run commands.
- Configure certain system components.
- Emit initialization completion signals.

Cloud-init is not a tool for managing all long-term configuration changes. It is suited for initial provisioning and certain boot-time tasks; configurations that need to continuously converge toward a desired state should be managed with configuration management or an appropriate deployment system.

## 4. Main stages of cloud-init

Cloud-init divides initialization into stages to process data at the right time. Module names and detailed behavior can vary by version.

| Stage | Approximate timing | Typical tasks |
|---|---|---|
| Generator / Detect | When the system prepares to start cloud-init services | Determine which services should run and detect the datasource |
| Local | Early phase, before networking is fully up | Detect local datasource, configure certain base components |
| Network | After networking is ready | Fetch metadata and user data, configure related network/users |
| Config | Configuration phase | Run modules such as writing files and certain system settings |
| Final | Final phase of boot | Install packages, run final commands, complete bootstrap |

### Local stage

In this stage, cloud-init detects the datasource and performs tasks that do not require full networking. Tasks that depend on external endpoints should not be assumed to work here.

### Network stage

Once networking is ready, cloud-init can query the metadata service, retrieve user data, and process configurations that require platform information. If networking is not working or the metadata endpoint is unreachable, the process can be delayed or fail.

### Config stage

Configuration modules such as **write_files** can write files to the system. Ordering between modules matters: configuration files must exist before a service is started.

### Final stage

Package installation and final command execution typically occur in this stage. Downloading large payloads or installing many packages can lengthen boot time.

**runcmd** in cloud-config is recorded during the config stage and executed in the final stage via cloud-init's script mechanism. Therefore, do not assume a command has already finished immediately after the user data file is read.

### First boot and subsequent boots

Cloud-init persists state to determine which modules have run and their execution frequency. Some modules run once per instance; others run on every boot or every configuration change. Standard user-data scripts are processed according to cloud-init's frequency policy, typically once per instance.

Directives such as **bootcmd** can run on every boot, whereas **runcmd** typically runs once per instance. Frequency-based script directories or corresponding modules can be used, but you should verify the cloud-init version and image configuration.

Do not use **cloud-init clean** as a routine troubleshooting fix on production machines. This command clears cloud-init state and can cause initialization steps to re-run on the next boot. It is normally used intentionally when preparing a golden image or reproducing a first-boot state.

## 5. Writing cloud-config with YAML

Cloud-config is a user data format starting with the **#cloud-config** header. Its YAML content describes the desired state or actions to perform.

The following example demonstrates creating a user, installing packages, writing a configuration file, and running an initialization command:

~~~yaml
#cloud-config

package_update: true

packages:
  - nginx
  - curl

users:
  - default
  - name: appops
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...replace-with-approved-public-key

write_files:
  - path: /etc/example-app/bootstrap.conf
    owner: root:root
    permissions: "0640"
    content: |
      APP_ENV=staging
      LOG_LEVEL=info

runcmd:
  - [systemctl, enable, nginx]
  - [systemctl, start, nginx]
~~~

This is an illustrative example. Verify packages, default users, shells, permission groups, and cloud-init modules for the actual image. Do not use a placeholder public key in production; replace it with an organization-approved public key.
The application account in the example is not granted administrative privileges. If an operational account requires elevated privileges, grant them through approved groups and policies, scope allowed commands, and enable audit logging.

### YAML considerations

- Indent with spaces and keep the structure consistent.
- Quote strings containing special characters appropriately.
- File permissions should be written as strings, such as **0640**, to prevent YAML from interpreting them as numbers.
- Use pipe or greater-than block scalars for multi-line content.
- Never place private keys, passwords, or tokens in examples or user data.
- Validate syntax with the cloud-init tool before provisioning many machines.

You can validate configuration on Linux with:

~~~sh
cloud-init schema --config-file user-data.yaml
~~~

Validation capabilities depend on the cloud-init version. Always validate the schema in the target image or an environment closely matching production.

## 6. Writing safe shell startup scripts

Some platforms accept shell scripts starting with a shebang. The script should explicitly declare its shell and handle errors intentionally.

Simple example:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE=/var/log/app-bootstrap.log
exec > >(tee -a "$LOG_FILE") 2>&1

if ! command -v nginx >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y nginx
  else
    echo "Unsupported package manager" >&2
    exit 1
  fi
fi

install -d -o root -g root -m 0755 /opt/example-app

systemctl enable nginx
systemctl start nginx

systemctl is-active --quiet nginx
~~~

This script illustrates the following principles:

- Use a shebang to specify the interpreter.
- Stop on unexpected errors.
- Write logs to support investigation.
- Check whether a package is installed before installing it.
- Create directories and files in a deterministic desired state.
- Enable and start services in a way that can be safely re-run.
- Verify service status at the end.

In production, add timeouts, bounded retries for network dependencies, signature or checksum verification for artifacts, and step-by-step error handling. Do not download and execute scripts directly from unverified sources.

### Idempotency is a critical requirement

Idempotent means running the same operation multiple times brings the system to the same desired state without unintended side effects.

Examples:

- Create directories with **install -d** or **mkdir -p**.
- Check whether a package is already installed before installing.
- Write files with deterministic content rather than appending on every run.
- Use **systemctl enable** and check service state.
- Create users with an existence check.
- Use versioned markers or state tracking when controlling completed tasks.

A simple marker file is not enough to prove the entire bootstrap succeeded. If the script stops partway after creating the marker, a subsequent run may skip incomplete steps. Only write a marker after all required checks pass, or track state per step.

### Do not use startup scripts as a long-term application deployment system

A startup script can download and launch the initial application version, but new releases should not depend on manually editing user data. Use CI/CD, configuration management, or a deployment agent to manage releases and rollbacks.

## 7. Ordering and dependencies between bootstrap steps

Some steps must finish before others. For example:

1. Network is operational.
2. Metadata and identity are read.
3. Access permissions for secrets/artifacts are established.
4. Packages and runtimes are installed.
5. Configuration files are written.
6. Application is installed or downloaded.
7. Service is enabled/started.
8. Health check passes.
9. Load balancer places the machine into service.

If the application starts before configuration files are written, the service may crash. If the script downloads artifacts before DNS or routing is ready, the download will fail.

### Managing network dependencies

Bootstrap often needs access to package repositories, artifact registries, secret managers, or management systems. Ensure:

- DNS is working.
- Routes and firewalls allow the required connections.
- Proxies or private endpoints are configured if used.
- Required CA certificates are present.
- Service endpoints are reachable from the VM's subnet.
- Retries/backoff for transient errors and an overall timeout are in place.

Do not retry infinitely. A wrong endpoint or blocking policy will leave the VM stuck in initialization for too long. Bound the duration, log the failure, and signal failure so the orchestration system can handle it.

### Do not rely on accidental ordering

If multiple scripts or modules modify the same file, install the same package, or start the same service, the outcome can depend on execution order. Organize bootstrap into explicit stages with clear inputs/outputs and checks after each phase.

## 8. Managing secrets and machine identity

User data can be stored in metadata, instance configuration, APIs, or platform logs. Consequently, its contents may be readable by anyone with VM management or corresponding metadata permissions.

Do not place directly into user data:

- Database passwords.
- Private keys.
- Long-lived access keys.
- CI/CD system tokens.
- Private certificates.
- Encryption secrets or connection strings containing credentials.

### Fetching secrets at runtime

A safer pattern:

1. Assign an instance role, managed identity, or service account to the VM.
2. Grant least-privilege permissions to read only the required secrets.
3. During bootstrap, retrieve temporary credentials or secrets from a secret manager.
4. Write secrets to the required location with strict ownership and permissions, or pass them directly through a secure mechanism.
5. Avoid printing secret values to logs, command lines, or world-readable files.
6. Rotate secrets according to policy.

Do not use operator credentials embedded in scripts to call cloud APIs. Use platform-issued workload identities instead.

### Separating configuration from secrets

Standard configuration such as environment name, port, feature flags, or non-sensitive endpoints can be passed via user data or a configuration service. Secrets must go through a secret manager with separate permissions and auditing.

When logging bootstrap progress, record status messages such as "configuration retrieved" or the secret identifier, never the secret value.

## 9. Bootstrap on AWS, Azure, and Google Cloud

Each platform has its own mechanisms. Do not assume user data shares the same size limits, execution timing, or run frequency across clouds.

| Platform | Common mechanism | Points to verify |
|---|---|---|
| AWS EC2 | User data; cloud-init on many Linux AMIs; EC2Launch on Windows | User data scripts typically run on first launch by default; size limits, IMDSv2, logs, and agent behavior |
| Microsoft Azure | Custom data, cloud-init on supported Linux images, VM Agent, and Custom Script Extension | Distinguish custom data from extensions; provisioning state; re-run capability and data limits |
| Google Cloud | Startup scripts via metadata, guest environment/agent; cloud-init on supported images | Scripts run at boot based on metadata key type; service account permissions, logs, and guest agent |

### AWS EC2

On many Linux AMIs, EC2 user data is processed by cloud-init. You can pass a shell script or cloud-config when creating an instance. User data scripts typically run only on initial launch by default depending on the image/configuration; running on every boot requires an appropriate mechanism and understanding its impact.

On Windows, EC2Launch or the corresponding initialization tool handles user data. Behavior depends on the agent version and configuration. Do not apply Linux cloud-init assumptions to Windows.

Checking cloud-init logs on Linux typically includes:

~~~sh
cloud-init status --long
sudo less /var/log/cloud-init.log
sudo less /var/log/cloud-init-output.log
~~~

### Microsoft Azure

Azure Linux VMs can use cloud-init when the image supports it and custom data is passed at provisioning time. The VM Agent and Custom Script Extension are separate mechanisms, commonly used to run scripts or deploy configuration after the machine has been created.

Custom data and extensions do not share the same lifecycle. If you need to re-run a task after the VM has been provisioned, an extension or configuration management tool is usually more appropriate than expecting custom data to re-run automatically.

On Windows, you can use the VM Agent and extensions such as Custom Script Extension to run PowerShell. Check extension status in the Azure Portal/CLI and inspect VM Agent logs.

### Google Cloud

Compute Engine supports startup scripts via project-level or instance-level metadata keys. The guest environment/agent on the VM reads metadata and executes the script according to platform rules. Linux images can use cloud-init if the datasource and image are compatibly configured.

Some startup scripts execute on every VM boot, so they must be idempotent. Distinguish between startup script keys for Linux and Windows, as well as project-level versus instance-level metadata scope.

### Choosing a mechanism

- Use cloud-init when you need modular Linux initialization and the image supports it well.
- Use a startup script when operations are simple and the platform provides a clear execution mechanism.
- Use extensions or configuration management when you need re-runs, status tracking, and change management after first boot.
- Use images with heavy packages pre-baked when you want to reduce bootstrap time and boot-time repository dependencies.

## 10. Bootstrap for Windows

Windows VMs typically use a provider agent or extension to process custom data and startup scripts. Scripts are usually written in PowerShell and may run with system privileges depending on the mechanism.

PowerShell example demonstrating directory checking and creation:

~~~powershell
$ErrorActionPreference = "Stop"

$LogPath = "C:\ProgramData\ExampleApp\bootstrap.log"
$Directory = "C:\ProgramData\ExampleApp"

New-Item -ItemType Directory -Path $Directory -Force | Out-Null

"Bootstrap started at $(Get-Date -Format o)" |
  Out-File -FilePath $LogPath -Append -Encoding utf8

if (-not (Test-Path "C:\Program Files\ExampleApp\app.exe")) {
    # Install an artifact verified through the internal pipeline.
    Write-Output "Application installation is required."
}

"Bootstrap checks completed at $(Get-Date -Format o)" |
  Out-File -FilePath $LogPath -Append -Encoding utf8
~~~

In production, use signed installers, verify checksums, and enforce timeouts and exit codes. Do not disable TLS verification or execute downloaded scripts without verification. If the script can re-run, every step should check state before making changes.

### Checking Windows logs and status

Depending on the agent and image, logs may reside under the provider's ProgramData directory or be written to the Windows Event Log. You can check:

- VM Agent and extension status.
- Script exit codes.
- Event Viewer, especially logs related to provisioning and services.
- Application service status.
- Log files generated by the bootstrap script.

Exact paths vary by agent version. Consult the documentation for the specific image and extension being deployed.

## 11. Bootstrap with systemd

After installing the application, long-running processes should be managed by the OS service manager. On Linux, systemd lets you declare startup ordering, the service user, restart policies, and dependencies.

Example unit file:

~~~ini
[Unit]
Description=Example application
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=appuser
Group=appuser
WorkingDirectory=/opt/example-app
ExecStart=/opt/example-app/bin/server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
~~~

After writing the unit file, bootstrap can run:

~~~sh
systemctl daemon-reload
systemctl enable example-app.service
systemctl start example-app.service
systemctl status example-app.service --no-pager
~~~

**network-online.target** is only useful when the system has an appropriate wait-online service configured. It does not guarantee that all external endpoints are reachable. Applications still need dependency connection retries and timeouts.

### Readiness is different from a running process

An active service does not necessarily mean it is ready to serve requests. Readiness should verify real conditions such as:

- The application has loaded its configuration.
- Connections to the database or required dependencies are working.
- Required caches or data are warmed up.
- The listening port and health check endpoint respond.
- No critical migrations or initialization steps are still running.

The load balancer should send traffic only when readiness passes. If bootstrap fails, the instance must not be added to the pool simply because the VM transitioned to the running state.

## 12. Monitoring bootstrap status

Bootstrap should produce observable state. A VM creation pipeline should distinguish these milestones:

1. VM is provisioned.
2. VM begins booting.
3. Network and metadata are operational.
4. Bootstrap begins.
5. Installation and configuration steps complete.
6. Application starts.
7. Readiness passes.
8. VM is allowed to receive traffic.

Cloud providers may report a VM as running or provisioning succeeded before the application finishes initializing. Use dedicated signals for bootstrap and application readiness.

### cloud-init logs on Linux

Useful commands:

~~~sh
cloud-init status --long
sudo journalctl -u cloud-init-local
sudo journalctl -u cloud-init
sudo journalctl -u cloud-config
sudo journalctl -u cloud-final
sudo tail -n 200 /var/log/cloud-init.log
sudo tail -n 200 /var/log/cloud-init-output.log
~~~

Unit names may differ across distributions. Not every image includes all services or stores logs in the same way.

### Analyzing execution time

Cloud-init can provide tools to analyze stages and modules:

~~~sh
cloud-init analyze show
cloud-init analyze blame
~~~

The output helps identify which steps prolong boot time. If package installation takes several minutes, consider baking packages into the image, using an internal repository, or reducing concurrent tasks.

### Signaling completion

Some platforms support signaling mechanisms or extension statuses to report bootstrap success or failure. If building your own, emit metrics or events to the monitoring system after each stage.

Signals should include the instance ID, image version, bootstrap version, and status, without any secrets. Use an overall timeout so the orchestration system detects machines stuck in initialization.

## 13. Troubleshooting common issues

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| Script does not run | Malformed user data, missing shebang, inactive agent/cloud-init | Inspect user data, cloud-init or VM agent service, and logs |
| Cannot retrieve metadata | Network, routing, firewall, or metadata policy | Check datasource, metadata endpoint, and protection settings |
| Package installation fails | DNS, repository, proxy, TLS, or package lock | Inspect package manager logs, DNS, routing, and wait timeouts |
| YAML cloud-config not applied | Wrong indentation, unsupported key/module, or bad header | Validate schema, cloud-init version, and logs |
| Script runs multiple times | Startup script configured to run on every boot or instance state reset | Verify execution frequency, design idempotently, and use markers properly |
| VM running but application not ready | Bootstrap still running, service error, or dependency not ready | Check readiness, systemd, application logs, and dependencies |
| Bootstrap hangs for a long time | Infinite retries, large download, or unresponsive endpoint | Set timeouts, backoff, deadlines, and per-step logging |
| Secret inaccessible | Role/identity or policy lacks permissions | Check identity attached to VM and secret manager audit logs |
| New instance has duplicate hostname or SSH host key | Image not generalized or template machine state retained | Review image build pipeline and first-boot identity handling |
| Extension reports failure | Outdated VM agent, incompatible handler, or non-zero script exit code | Check agent, extension status, handler logs, and exit code |

### Ordered investigation workflow

1. Determine whether the VM booted to the operating system.
2. Check networking and the metadata service.
3. Verify user data is properly formatted and received by the agent.
4. Read cloud-init/VM agent logs from start to finish.
5. Identify the first module or command that failed.
6. Re-run that isolated command in a test environment to reproduce.
7. Check permissions, package repositories, DNS, and dependencies.
8. Fix the script to be idempotent, with timeouts and logging.
9. Launch a new test instance to confirm first boot.
10. Release the image or configuration only after smoke tests pass.

Do not arbitrarily edit cloud-init internal state or delete state files in production to force a script to re-run. Doing so can cause user creation, SSH key setup, or system configuration modules to re-execute unexpectedly.

## 14. Security and reliable operations

Bootstrap typically runs with root or SYSTEM privileges. A bug in a script can affect the entire machine, so safe design principles must be applied from the start.

### Least privilege

- Scripts only have the permissions needed for their assigned steps.
- Instance roles can read only the exact artifacts, secrets, and configurations required.
- Do not share administrative credentials across environments.
- Configuration files have explicit ownership and permissions.
- Application services run under dedicated users, not root unless necessary.

### Controlling script and artifact sources

- Store scripts in a repository with code review and version control.
- Use an artifact registry or trusted internal source.
- Verify checksums or signatures before installing.
- Pin package or artifact versions when reproducibility is needed.
- Scan for vulnerabilities and verify licenses.
- Record image versions and bootstrap versions in inventory.

### Limiting boot-time dependencies

If every VM must download dozens of packages from the Internet before serving traffic, startup time becomes unpredictable. You can:

- Bake runtimes and base packages into the image.
- Use internal repositories or artifact mirrors.
- Download independent components in parallel with bounded concurrency.
- Cache artifacts in a region close to the VM.
- Download only small configs and necessary secrets at boot.

Do not bake secrets or credentials into the image to shave startup time. Secrets should still be fetched at runtime using workload identity.

### Controlling user data changes

User data is usually tied to machine creation configuration or metadata. Editing its content after a VM is running does not automatically re-run the script. Some platforms allow modifying the data without triggering execution, while others require a reboot or a separate mechanism.

For bootstrap changes, create a new version, test on a fresh instance, and roll out via launch templates/scale sets/instance groups or an appropriate replacement workflow. Record script versions for traceability.

## 15. Example: bootstrapping a web service on Linux

A team deploys a web service across multiple VMs. The base image already includes cloud-init and security agents. User data provides non-sensitive environment configuration, while secrets are retrieved from a secret manager using the instance identity.

Deployment flow:

1. Create VMs from a tested image.
2. cloud-init detects the datasource and reads user data.
3. Configure the hostname and create the application user.
4. Install missing packages and write configuration files.
5. Fetch runtime secrets using the assigned identity.
6. Download the application artifact from the internal registry and verify its checksum.
7. Install the systemd unit and enable the service.
8. Start the application.
9. Check the health endpoint and report bootstrap status.
10. The load balancer adds the VM to the pool once readiness passes.

A portion of the cloud-config might look like this:

~~~yaml
#cloud-config

package_update: true
packages:
  - curl
  - jq

users:
  - default
  - name: appuser
    system: true
    shell: /usr/sbin/nologin
    lock_passwd: true

write_files:
  - path: /etc/example-app/app.env
    owner: root:appuser
    permissions: "0640"
    content: |
      APP_ENV=production
      PORT=8080

runcmd:
  - [install, -d, -o, appuser, -g, appuser, /opt/example-app]
  - [systemctl, daemon-reload]
  - [systemctl, enable, example-app.service]
  - [systemctl, start, example-app.service]
~~~

This example assumes the artifact and systemd unit are provided by the image or another deployment step. Do not place secrets in `app.env` inside user data; the application or a suitably authorized runtime step should retrieve secrets securely.

If the service fails the health check, keep the VM out of the load balancer. The pipeline can collect logs, mark the instance as failed, and launch a replacement after resolving the root cause.

## 16. Bootstrap design and testing workflow

A workflow applicable to production VMs:

1. **Define objectives:** list packages, users, configurations, secrets, and services required before serving traffic.
2. **Choose the mechanism:** cloud-init, user data script, startup script, or extension based on OS and provider.
3. **Separate stages:** split offline tasks, metadata tasks, package installation, configuration, and service startup.
4. **Design for idempotency:** re-running must not create duplicate users, duplicate file appends, or data loss.
5. **Restrict privileges:** use instance identity, secret manager, and least-privilege permissions.
6. **Add observability:** per-step logging, timeouts, exit codes, metrics, and completion signals.
7. **Test on a clean image:** create a new VM from the actual image and verify first boot.
8. **Test failure modes:** simulate DNS failures, unreachable repositories, missing secret permissions, and missing artifacts.
9. **Measure timing:** identify slow steps and set a maximum bootstrap threshold.
10. **Roll out safely:** deploy as canary, monitor readiness, and retain rollback capability.

### Bootstrap completion criteria

A VM should be marked ready only when:

- The operating system has finished booting.
- Bootstrap exits with a successful status.
- Required runtimes and configurations are present.
- Secrets were retrieved using a valid identity.
- The application is running and readiness checks pass.
- Monitoring and security agents are active.
- The VM is registered with the orchestration system.
- No critical errors appear in initialization logs.

## 17. Pre-production checklist for user data

- [ ] Selected the right mechanism for the image, operating system, and cloud provider.
- [ ] Distinguished first-boot tasks from per-boot tasks.
- [ ] Verified datasource and metadata service behavior.
- [ ] Validated cloud-config structure or shell/PowerShell syntax.
- [ ] Script includes timeouts, error handling, and per-step logging.
- [ ] Steps are safe to re-run or have explicit state control.
- [ ] Dependency order across network, packages, files, and services is defined.
- [ ] No passwords, private keys, tokens, or secrets in user data.
- [ ] Instance identity has least-privilege permissions.
- [ ] Artifacts are fetched from trusted sources with integrity verification.
- [ ] Service runs under an appropriate user with a restart policy.
- [ ] Separate readiness check exists independent of the VM running state.
- [ ] Logging, metrics, exit codes, and an overall timeout are configured.
- [ ] Tested on a fresh instance from the production image.
- [ ] Tested failure scenarios and recovery paths.
- [ ] Image, user data, and bootstrap scripts are versioned.
- [ ] Rollout, rollback, and log retention plans are in place.

## Conclusion

User data passes configuration or instructions into a VM; startup scripts execute initialization actions; cloud-init orchestrates many Linux bootstrap steps through datasources and stages. To make startup reliable, you must determine the right execution timing, dependency order, run frequency, and completion criteria. Scripts must be idempotent, have timeouts and logs, use machine identity to fetch secrets, and verify readiness before accepting traffic. Combining standardized images, versioned bootstrap logic, and testing on fresh instances makes VM deployments consistent, easier to debug, and more secure.
