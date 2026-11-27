# Metadata Server and Startup Scripts

A Compute Engine virtual machine needs to know **which machine it is, which project and zone it belongs to, what application configuration to use, and what tasks to run at startup**. Instead of hard-coding these values into images or logging into every VM manually, Google Cloud provides the **metadata server** and **startup scripts** to retrieve instance context and automate machine bootstrapping.

In the **Compute Engine** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects project, IAM, and VPC fundamentals with application provisioning, identity management, releases, and reliability/cost monitoring. For example, a team running an API on Compute Engine can reuse the same image and startup script across environments while passing `app-env=dev` or `app-env=prod` via metadata. When the VM boots, the script reads the appropriate value to prepare its configuration.

**Learning Outcomes**

1. Distinguish built-in metadata, custom metadata, and short-lived service account credentials.
2. Query metadata **from inside a VM** over HTTP with the required header.
3. Explain metadata scopes at the project, zone, and instance levels; understand when instance-level settings override project-level ones.
4. Use startup scripts on Linux/Windows and understand the role of the Google Guest Environment.
5. Write idempotent startup scripts that log safely, check errors, and never leak secrets.
6. Practice creating a VM with a startup script, verifying results, updating metadata, and cleaning up resources.
7. Diagnose common errors and choose appropriate configuration approaches for single VMs, managed instance groups (MIGs), and deployment pipelines.

## 1. What Is the Metadata Server?

The **metadata server** is a service a Compute Engine VM can query to read data describing itself and its Google Cloud environment. Each VM sees metadata scoped to its own context. Values may be provided automatically by Google Cloud or added by administrators.

VMs reach the metadata server via its internal DNS name or link-local IP address:

~~~text
http://metadata.google.internal/computeMetadata/v1/
http://169.254.169.254/computeMetadata/v1/
~~~

A VM needs no public IP, Cloud NAT, or Internet access to reach this internal HTTP metadata endpoint. Google Cloud also offers an **HTTPS metadata server** for Shielded VMs meeting guest environment and certificate requirements; do not simply change `http` to `https` in a legacy script without configuring the required validation and certificates.

**Core security note:** the metadata server can be queried by processes running inside the VM without another IAM login per metadata request. Consequently, untrusted code running on the VM or a server-side request forgery (SSRF) vulnerability can expose metadata—including tokens for the VM's attached service account. Never use metadata as a secret store.

### 1.1. Common Metadata Tree

Metadata is organized into hierarchical paths/keys. For example:

~~~text
computeMetadata/v1/
├── instance/
│   ├── name
│   ├── id
│   ├── zone
│   ├── attributes/
│   │   ├── app-env
│   │   └── startup-script
│   ├── network-interfaces/
│   └── service-accounts/
│       └── default/
│           ├── email
│           └── token   # Sensitive content; DO NOT log
└── project/
    ├── project-id
    ├── numeric-project-id
    └── attributes/
        └── app-env
~~~

This is an illustrative layout, not a guarantee that every key exists on every VM. `app-env` is **custom metadata** that appears only after an administrator defines it. The live metadata tree also includes system-provided entries that vary by VM configuration.

| Data Category | Examples | Usage |
| --- | --- | --- |
| System instance metadata | `instance/name`, `instance/id`, `instance/zone` | Identify the machine, label logs, or select environment-specific behavior. |
| System project metadata | `project/project-id`, `project/numeric-project-id` | Identify the hosting project; avoid hard-coding Project IDs. |
| Custom metadata | `instance/attributes/app-env` | Pass **non-sensitive** configuration such as `dev` or `production`. |
| Service account details | `instance/service-accounts/default/email` | Identify the workload identity attached to the VM. |
| Service account access token | `instance/service-accounts/default/token` | Used by Google Cloud libraries/ADC to authenticate API calls; never print tokens to logs, web pages, or shared output. |
| Guest agent keys | `startup-script`, `startup-script-url` | Instruct the guest environment how to fetch and run scripts when the VM boots. |

### 1.2. Project, Zone, and Instance Scopes

Google Cloud supports metadata scoped at the **project**, **zone** (for supported features and management modes), and **VM instance** levels.

- **Project metadata** passes shared values to many VMs in a project, such as intentional project-wide defaults. Editing project-wide metadata therefore has broad blast radius.
- **Zonal metadata** supports zone-level values per Compute Engine rules; verify supported key types and configuration syntax.
- **Instance metadata** specifies values for one specific VM. For supported overlapping configuration keys, instance values can take precedence over broader scopes.

For example, the project may set `app-env=dev` while a production VM sets `app-env=prod`. Applications must **query the right path and understand precedence rules**; querying `project/attributes/app-env` directly returns the project-level value rather than automatically resolving to the VM-level override. To customize scripts per VM, pass explicit instance metadata and standardize naming conventions across teams.

**Do not confuse metadata with IAM:** modifying metadata through the Compute Engine API is gated by IAM, whereas reading metadata *from processes inside the VM* follows a different access model. Permissions like `compute.instances.setMetadata` or `compute.projects.setCommonInstanceMetadata` must be tightly restricted because anyone able to modify startup scripts can cause arbitrary code execution with high privileges on the next boot.

### 1.3. The Metadata Server Operates Independently of the Internet

~~~mermaid
flowchart LR
    A["App / script inside VM"] -->|"Metadata-Flavor: Google"| M["Metadata server<br/>metadata.google.internal"]
    M --> C["VM info, project info,<br/>and custom attributes"]
    M --> SA["Service account info<br/>and short-lived tokens"]
    A -. "Google Cloud APIs, when authorized by IAM" .-> G["Cloud Storage / Logging / API"]
~~~

Metadata requests are served within the infrastructure associated with the VM's physical host, not over the public Internet. Even so, brief availability blips can happen, such as right at boot or during maintenance. Scripts should implement timeouts and bounded retries rather than assuming every call succeeds on the first try.

## 2. Querying Metadata from Inside a VM

### 2.1. Required Header

To query the HTTP metadata server, include the header:

~~~http
Metadata-Flavor: Google
~~~

This header distinguishes intentional metadata requests from unintended requests. Without it, the metadata server rejects the request. The header is not a secret or authentication token; **any process permitted to send HTTP requests from the VM can attach it**.

Inside a **Linux VM shell** (via SSH or Console), for example:

~~~bash
MDS="http://metadata.google.internal/computeMetadata/v1"

# Current VM name
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/instance/name"

# Project ID
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/project/project-id"

# VM zone (typically a resource path)
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/instance/zone"
~~~

These are **read-only** commands and create no new resources. You cannot run them from your laptop or Cloud Shell outside the VM expecting live VM metadata, because the metadata endpoint responds relative to the compute instance querying it.

### 2.2. Reading Custom Metadata

Suppose the VM has key `app-env` assigned:

~~~bash
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/app-env"
~~~

If the value is `training`, the output is:

~~~text
training
~~~

If the key is absent, the query returns HTTP 404; scripts should handle that as an error rather than silently falling back to an assumed safe environment value. You can list `instance/attributes/` or `project/attributes/` to inspect available keys, but **never dump all metadata in environments that might hold sensitive fields**.

### 2.3. Using Windows PowerShell

On a **Windows VM**, you can invoke:

~~~powershell
$mds = "http://metadata.google.internal/computeMetadata/v1"
$headers = @{"Metadata-Flavor" = "Google"}

$vmName = Invoke-RestMethod -Uri "$mds/instance/name" -Headers $headers
$projectId = Invoke-RestMethod -Uri "$mds/project/project-id" -Headers $headers
Write-Output "VM=$vmName Project=$projectId"
~~~

Windows VMs use the exact same metadata protocol and header; only the shell and OS commands differ. Token endpoints must still be protected and never sent to `Write-Output` or transcripts.

### 2.4. Reacting to Metadata Changes

The metadata server supports watching a **specific key** for updates using `wait_for_change=true`, useful for applications that reload configuration without rebooting the VM:

~~~bash
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/app-env?wait_for_change=true&timeout_sec=60"
~~~

This waits for a value change; it is **not** a mechanism that automatically re-runs startup scripts. Do not long-poll the access token endpoint; the metadata server enforces restrictions on request types and watched keys. When implementing watch loops, add retry caps, backoff, and timeout handling to avoid unnecessary load.

## 3. Startup Scripts: Automating Tasks at VM Boot

A **startup script** is a script executed by the Compute Engine guest environment during VM boot. Common tasks include:

- Creating directories, configuration files, and setting file permissions.
- Installing or updating required packages when networking and package repositories allow.
- Reading custom metadata to determine environment names, service endpoints, or application profiles.
- Starting systemd services, monitoring agents, or health checks.
- Fetching a pinned release version from a trusted artifact store if the VM identity has appropriate permissions.

**Startup scripts are not a complete release orchestration platform.** When managing hundreds of VMs, multiple variants, or consistent rollbacks, combine golden images, instance templates, managed instance groups, Infrastructure as Code, and CI/CD. Use startup scripts for focused bootstrap steps, and dedicated configuration/deployment tooling for the broader application lifecycle.

### 3.1. Prerequisites for Execution

Google Cloud provides the **Google Guest Environment**, which includes the guest agent and metadata script runners. Standard Compute Engine public images include the guest environment out of the box. With custom images, you must ensure the guest environment is installed, enabled, and properly configured.

~~~mermaid
flowchart TD
    BOOT["VM boot / reboot"] --> G["Google Guest Environment<br/>guest agent / metadata scripts"]
    G --> M["Read instance/project metadata"]
    M --> S{"Valid startup script<br/>present?"}
    S -->|No| END["VM continues booting"]
    S -->|Yes| RUN["Fetch script content<br/>and execute in guest OS"]
    RUN --> STATUS["Write exit status and output<br/>to appropriate logs"]
    STATUS --> END
~~~

On Linux, startup scripts execute with **root privileges**. Thus, permissions to edit startup metadata carry major security risk: anyone able to edit the script can inject commands that execute as root on the next boot. Never run unverified scripts or unreviewed code.

Startup scripts typically run **every time the VM boots**, including subsequent reboots if the guest environment is active. **Updating metadata on a running VM does not immediately re-run the startup script.** Operators must either reboot the VM or explicitly invoke the runner after assessing the impact.

### 3.2. Linux Metadata Keys

| Key | Delivery Method | When Appropriate |
| --- | --- | --- |
| `startup-script` | Script content supplied inline or loaded from a local file by `gcloud`. | Short scripts fitting comfortably within metadata size limits. |
| `startup-script-url` | Path to a script stored in Cloud Storage, such as `gs://bucket/bootstrap.sh` or a supported Cloud Storage URL. | Larger scripts, independent file management, or versioned script release flows. |

For Linux, Compute Engine documentation specifies a **256 KB** limit for directly passed startup script content; larger scripts should live in Cloud Storage per current guidance. Using a Cloud Storage URL requires ensuring the VM has **network connectivity, a service account, and object read permissions**. For instance, grant `roles/storage.objectViewer` to the service account **on that specific bucket**; VM access scopes must also permit the call if applicable.

If both `startup-script` and `startup-script-url` are configured, the guest environment may process **multiple scripts** for the same boot event. Never rely on implicit execution ordering across script types or guest agent versions; instead, consolidate dependent steps into one well-structured script and verify each step's result.

### 3.3. Linux Startup Script Example

Suppose a VM needs to write a self-description file at boot and emit a log entry. This script requires no Internet package downloads and can re-run safely without creating unwanted duplicates:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

MDS="http://metadata.google.internal/computeMetadata/v1"

metadata() {
  curl --fail --silent --show-error \
    --retry 5 --retry-delay 2 \
    -H "Metadata-Flavor: Google" \
    "$MDS/$1"
}

VM_NAME="$(metadata instance/name)"
PROJECT_ID="$(metadata project/project-id)"
APP_ENV="$(metadata instance/attributes/app-env)"

# Use app-env only for non-sensitive configuration
install -d -m 0755 /var/lib/metadata-demo
printf 'vm=%s\nproject=%s\nenvironment=%s\n' \
  "$VM_NAME" "$PROJECT_ID" "$APP_ENV" \
  > /var/lib/metadata-demo/info.txt
chmod 0644 /var/lib/metadata-demo/info.txt

logger -t metadata-demo "Startup completed for $VM_NAME"
~~~

In this example:

1. `set -Eeuo pipefail` catches shell failures early instead of falsely reporting a clean bootstrap.
2. The `metadata` helper always sends the required header and retries transient failures.
3. `VM_NAME` and `PROJECT_ID` are read from the VM environment rather than hard-coded.
4. `APP_ENV` is a required custom key supplied at VM creation; if missing, the script fails loudly instead of running against the wrong environment.
5. `install -d` and overwriting the file yield identical results across re-runs.
6. `logger` emits secret-free status messages to local system logs.

`curl --retry` handles certain transient errors per curl's policy; in production, configure explicit connect/total timeouts, retry only appropriate failure classes, and guard dependencies so startup does not hang indefinitely.

### 3.4. Inline Scripts vs. Scripts from Cloud Storage

**Option A — supplying content from a local file:**

~~~bash
gcloud compute instances create vm-lab \
  --zone=asia-southeast1-b \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --metadata=app-env=training \
  --metadata-from-file=startup-script=./startup.sh
~~~

The CLI **reads the local file and embeds its contents into metadata** when executed. The VM does not need access to files on your laptop.

**Option B — referencing a Cloud Storage object:**

~~~bash
gcloud compute instances create vm-lab \
  --zone=asia-southeast1-b \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --metadata=app-env=training,startup-script-url=gs://EXAMPLE_BUCKET/bootstrap.sh
~~~

VM creation commands are **mutating operations that may incur charges**; `vm-lab` and `EXAMPLE_BUCKET` are placeholders—do not run both commands to create the same VM. With Option B, upload the script to Cloud Storage first, verify object read IAM, access scopes, and network reachability, and restrict write access to the object because the next boot will fetch the updated script.

For strict versioning, use versioned object names or immutable release artifacts and update the URL inside instance templates only after review. Never treat an uncontrolled URL fetched at boot as a safe code source.

### 3.5. Startup Scripts on Windows

Windows VMs use dedicated metadata keys:

| Windows Key | Meaning |
| --- | --- |
| `windows-startup-script-ps1` | PowerShell startup script. |
| `windows-startup-script-cmd` | CMD-style startup script. |
| `windows-startup-script-bat` | Batch-file startup script. |
| `windows-startup-script-url` | Script fetched from a supported location, depending on guest environment setup. |

Minimal PowerShell example running **inside a Windows VM at boot**:

~~~powershell
$mds = "http://metadata.google.internal/computeMetadata/v1"
$headers = @{"Metadata-Flavor" = "Google"}
$vm = Invoke-RestMethod -Uri "$mds/instance/name" -Headers $headers

New-Item -Path "C:\ProgramData\MetadataDemo" -ItemType Directory -Force |
  Out-Null
Set-Content -Path "C:\ProgramData\MetadataDemo\boot.txt" `
  -Value "VM=$vm"
~~~

When creating a Windows VM, pass the PowerShell file via `--metadata-from-file=windows-startup-script-ps1=./startup.ps1` and choose an appropriate Windows image. Windows startup script logs appear in **Windows Event Viewer** under `GCEMetadataScripts` events as well as the serial console per documentation. Do not pass the Linux key `startup-script` expecting it to behave like a Windows key.

## 4. Startup Scripts in the VM Lifecycle

### 4.1. Startup Scripts vs. Ad-Hoc SSH Commands

| Mechanism | Timing and Impact | Best Used For |
| --- | --- | --- |
| **Startup script via metadata** | Guest environment runs it at boot; re-runs on later boots. | Automated bootstrapping for new VMs or template instances. |
| **SSH / PowerShell Remoting** | Operator explicitly runs commands during an admin session. | Incident investigation and approved manual interventions. |
| **systemd service / Windows Service** | OS manages long-running process, restarts, and status. | Running continuous apps or agents after startup prepares the host. |
| **Instance template + MIG** | Multiple VMs created from a standard blueprint with replacement and scaling. | VM fleets and automated rollout/rollback by design. |
| **Custom image / image baking** | Pre-packages software and baseline configuration into the image. | Faster boot times, stronger consistency, and tighter version control. |

Never run a foreground server indefinitely inside a startup script, as bootstrapping may never report completion. Create and enable a **systemd unit** or Windows Service so the OS manages the process lifecycle.

### 4.2. Scripts Must Be Idempotent

**Idempotent** means re-running the script neither corrupts state nor duplicates side effects unintentionally. This matters because VMs reboot for maintenance, host failures, or operational tasks.

| Error-Prone Pattern | Improved Pattern |
| --- | --- |
| Using `>>` on every boot to append repeated config lines. | Render files from exact templates or update conditionally. |
| Creating a new user unconditionally on every boot. | Check if the user exists first; manage state with proper tooling. |
| Running database migrations automatically at VM boot without locking. | Use dedicated migration workflows with coordination and rollback. |
| Downloading releases from a mutable `latest` URL. | Pin an approved artifact version or checksum. |
| Continuing execution after a package install or command fails. | Fail fast on exit codes, log without secrets, and use bounded retries. |
| Printing full environment variables, HTTP responses, or tokens to serial logs. | Log only events, non-sensitive IDs, and necessary error codes. |

Safe bootstrapping is not just "the script worked once." Validate the **initial boot**, **subsequent reboots**, **instance replacement from a template**, and **temporary dependency unavailability**.

### 4.3. Does Updating Metadata Re-Run the Script?

Suppose a VM is running and you update it:

~~~bash
gcloud compute instances add-metadata vm-lab \
  --zone=asia-southeast1-b \
  --metadata=app-env=staging
~~~

The new metadata value becomes queryable inside the VM per metadata propagation, but **the startup script does not re-execute automatically** just because `app-env` changed. Applications needing hot reloads must watch values and reload config cleanly. To manually re-run startup scripts on Linux with a supported guest environment:

~~~bash
# Execute inside the Linux VM after verifying side effects
sudo google_metadata_script_runner startup
~~~

This re-runs root-level commands and mutates VM state; never test it in production unless the script is proven idempotent. **Rebooting the VM** also re-triggers startup scripts, though it requires disruption planning, especially on stateful VMs.

### 4.4. Inspecting Output and Exit Codes

On a Linux VM, inspect startup script logs:

~~~bash
# Execute inside the Linux VM
sudo journalctl -u google-startup-scripts.service --no-pager
sudo journalctl -u google-startup-scripts.service -b --no-pager
~~~

Related output can also be viewed via **serial port 1** in the Cloud Console or:

~~~bash
# From a workstation with gcloud and permission to read instance/serial output
gcloud compute instances get-serial-port-output vm-lab \
  --zone=asia-southeast1-b \
  --port=1
~~~

Exact logging behavior depends on the OS image and guest environment. Not every `echo` written to a local file appears automatically in Cloud Logging; centralized logging requires an appropriate agent or log sink.

## 5. Securing Metadata, Service Accounts, and Startup Scripts

### 5.1. Metadata Is Not a Secret Store

Never place **passwords, API keys, private keys, access tokens, refresh tokens, private certificate material**, or connection strings with credentials into custom metadata. Why:

- Processes on the same VM can query the metadata server.
- Anyone with control-plane permissions to read or edit metadata can view values per their access.
- Startup scripts can inadvertently leak values into serial output, journal logs, application logs, or debug shell output.
- Project-level metadata is visible to multiple VMs, creating wide exposure.

Instead, use **Secret Manager** or an organization-approved secrets system. When a VM needs a secret at runtime, attach a service account granted access solely to the exact required secret/version, read it via official client libraries/ADC, and avoid writing secrets to disk or logs unnecessarily.

### 5.2. Service Account Tokens Are Sensitive Credentials

A VM with an attached service account can obtain short-lived credentials from the metadata server to call Google Cloud APIs. Common paths fall under:

~~~text
instance/service-accounts/default/
instance/service-accounts/default/email
instance/service-accounts/default/token
~~~

Here `default` is an **alias** for the service account attached to the VM by configuration, not necessarily the project's default Compute Engine service account. The `token` endpoint returns a sensitive access token; this lesson names the path for reference only—**never print tokens to a terminal or write them to logs**.

Effective API permissions depend on both the **service account's IAM roles** and the **VM's access scopes** per Compute Engine rules. To reduce risk:

1. Create dedicated service accounts per workload and environment.
2. Grant least-privilege IAM roles on exact target resources instead of project-wide Editor.
3. Restrict who can change service accounts, manage VMs, edit metadata, or impersonate identities.
4. Prefer environment-provided credentials and Google Cloud client libraries/ADC over long-lived JSON service account keys.
5. Isolate untrusted processes and application endpoints that might access metadata.

### 5.3. SSRF and Untrusted Processes

A web app with a feature that "fetches content from a user-supplied URL" without destination restrictions can become a **server-side request forgery (SSRF)** vector against the metadata server. The `Metadata-Flavor: Google` header prevents some accidental hits, yet is **not a complete security boundary** if code on the VM can forge headers.

Therefore:

- Never let users control arbitrary destination URLs for server-side HTTP requests.
- Validate and allowlist hosts, schemes, and ports at the application layer; guard redirects and DNS rebinding.
- Apply sandboxing or process isolation so untrusted code cannot reach the metadata endpoint where feasible.
- Minimize service account privileges to limit blast radius if a token is leaked.
- Evaluate the HTTPS metadata endpoint on Shielded VMs where appropriate; HTTPS protects transport, though it **does not replace process isolation or IAM**.

### 5.4. Users Who Can Edit Startup Scripts Can Escalate Privileges

On Linux, startup scripts can run as root at boot, making `compute.instances.setMetadata` a sensitive permission. Even without SSH access, a user holding this permission can edit the startup script to alter the system on its next boot.

At project level, `compute.projects.setCommonInstanceMetadata` can impact numerous VMs across the project. Protect changes with least-privilege IAM, separation of duties, peer review, and audit logging. If a script points to a Cloud Storage object, anyone able to overwrite that object can likewise control what executes when the VM boots.

~~~mermaid
flowchart LR
    EDIT["User allowed to edit metadata<br/>or bootstrap object"] --> SCRIPT["Startup script"]
    SCRIPT --> ROOT["Commands run inside guest OS<br/>with elevated privileges"]
    ROOT --> SA["Code on VM<br/>can use service account"]
    SA --> API["Google Cloud APIs / data<br/>per IAM and scopes"]
~~~

**Control objective:** minimize who can alter scripts, review artifact changes, restrict service account permissions, and retain audit logs. Never rely solely on VPC firewalls to stop a root startup script already executing inside the VM.

### 5.5. Logging and Costs

Reading metadata from inside a VM incurs no network egress charges and consumes no standard Compute Engine API quota. However, creating VMs, disks, external IPs, storing scripts in Cloud Storage, ingesting logs, and Internet egress can incur charges. Scripts that download packages or large artifacts on every boot also increase boot time and network traffic.

**Never log tokens or secrets.** Configure log retention, log-reading IAM, and storage locations per operational and compliance requirements. For centralized startup logs, record diagnostic fields such as VM name, image version, startup version, elapsed time, and exit status—never personal data or credentials.

## 6. Hands-On Lab: Creating a VM That Reads Metadata at Boot

**Goal:** create a Linux VM with no external IPv4 and no service account, running a startup script that reads the VM name, Project ID, and custom metadata `app-env`. The script writes non-sensitive metadata into a local file and emits a status message for verification.

**Lab context:** a test project with an active Cloud Billing account, permissions to create Compute Engine VMs/VPCs/subnets, permission to read serial output, and sufficient VM quota. Run the commands below in **Bash** via Cloud Shell or a workstation configured with `gcloud`. Never run labs directly in a production project.

### 6.1. Lab Diagram and Safety Rules

~~~mermaid
flowchart LR
    PC["Learner / Cloud Shell"] --> API["Compute Engine API"]
    API --> VM["VM mds-lab-vm<br/>Debian 12, no external IP"]
    VM --> MDS["Metadata server<br/>link-local"]
    MDS --> VM
    VM --> FILE["/var/lib/metadata-demo/info.txt"]
    VM --> LOG["Startup logs / serial output"]
~~~

| Item | Illustrative Value | Rationale |
| --- | --- | --- |
| Project | `YOUR_LAB_PROJECT_ID` | Replace with your authorized lab project ID. |
| VPC | `mds-lab-vpc`, custom mode | Isolates lab networking from production networks. |
| Subnet | `mds-lab-subnet` in `asia-southeast1`, `10.88.0.0/24` | Sample CIDR for private IP allocation. |
| VM | `mds-lab-vm` in `asia-southeast1-b` | Linux VM executing the startup script. |
| Machine type | `e2-micro` | Small shape for testing; verify zonal availability, quota, and pricing. |
| Image | `debian-12` from `debian-cloud` | Standard image with guest environment installed. |
| External IP | None | Lab requires no inbound Internet or NAT. |
| Service account | None attached | Script calls no Google Cloud APIs; minimizes privileges. |
| Custom metadata | `app-env=training` | Non-sensitive environment label. |

Do not assume `10.88.0.0/24` fits every project: if hybrid connectivity exists or overlapping CIDRs are used, select a range approved by your network team. Verify names, zones, and machine types before running.

### 6.2. Selecting Project and Checking Environment

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE="asia-southeast1-b"
export VM_NAME="mds-lab-vm"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud compute machine-types describe e2-micro --zone="$ZONE"
~~~

If the Compute Engine API is not yet enabled, an authorized user in the **lab project** runs:

~~~bash
gcloud services enable compute.googleapis.com
~~~

This mutates project API configuration; verify permissions and org policies first. Enabling the API does not automatically grant VM quota or network creation permissions.

### 6.3. Creating the Lab VPC and Subnet

~~~bash
gcloud compute networks create mds-lab-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create mds-lab-subnet \
  --network=mds-lab-vpc \
  --region="$REGION" \
  --range=10.88.0.0/24
~~~

A VPC has **global** scope, while a subnet has **regional** scope. A VM in zone `asia-southeast1-b` uses the subnet in region `asia-southeast1`. Because the startup script only queries the internal metadata server, this lab **does not require** Cloud NAT, VPN, or default Internet egress.

### 6.4. Creating the Local Startup Script

**On Cloud Shell** or the workstation running `gcloud`, create `startup.sh` to pass into metadata at VM creation:

~~~bash
cat > startup.sh <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

MDS="http://metadata.google.internal/computeMetadata/v1"

metadata() {
  curl --fail --silent --show-error \
    --connect-timeout 3 --max-time 10 \
    --retry 5 --retry-delay 2 \
    -H "Metadata-Flavor: Google" \
    "$MDS/$1"
}

VM_NAME="$(metadata instance/name)"
PROJECT_ID="$(metadata project/project-id)"
APP_ENV="$(metadata instance/attributes/app-env)"

install -d -m 0755 /var/lib/metadata-demo
printf 'vm=%s\nproject=%s\nenvironment=%s\n' \
  "$VM_NAME" "$PROJECT_ID" "$APP_ENV" \
  > /var/lib/metadata-demo/info.txt
chmod 0644 /var/lib/metadata-demo/info.txt

echo "metadata-demo: bootstrap succeeded for $VM_NAME"
logger -t metadata-demo "bootstrap succeeded for $VM_NAME"
SCRIPT
~~~

**Why is this script safe for the lab?** It requires no Internet access to download packages, needs no service account, contains no secrets, and creates one directory/file cleanly overwritten on re-runs. `echo` and `logger` provide completion signals without printing tokens or passwords.

### 6.5. Creating the VM with the Script Attached

~~~bash
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=mds-lab-subnet \
  --no-address \
  --no-service-account \
  --no-scopes \
  --metadata=app-env=training \
  --metadata-from-file=startup-script=./startup.sh
~~~

Key flags:

| Flag | Role |
| --- | --- |
| `--no-address` | Assigns no external IPv4 to the VM. |
| `--no-service-account` and `--no-scopes` | Detaches service account and OAuth scopes; script needs no API tokens. |
| `--metadata=app-env=training` | Adds a custom metadata value to the instance. |
| `--metadata-from-file=startup-script=./startup.sh` | CLI reads the local file and loads its contents into VM metadata; guest environment runs it at boot. |

**Do not try querying an access token** from this VM since no service account is attached. If another exercise needs a script to access Cloud Storage or Secret Manager, create and attach a dedicated service account with least-privilege IAM rather than omitting `--no-service-account` and defaulting to whatever account exists.

### 6.6. Inspecting Status and Startup Logs

After the VM boots, from your external `gcloud` shell:

~~~bash
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,status,zone,networkInterfaces,metadata.items)"

gcloud compute instances get-serial-port-output "$VM_NAME" \
  --zone="$ZONE" \
  --port=1
~~~

In the serial output, look for guest agent startup script execution, exit status, or the line:

~~~text
metadata-demo: bootstrap succeeded for mds-lab-vm
~~~

Serial output can include machine environment details and OS records, so share only necessary excerpts. If the line does not appear yet, verify whether the VM has finished booting and allow logs to flush before declaring failure; if it still fails, check the troubleshooting section below.

**Optional:** if your organization configured SSH over **IAP TCP forwarding** and you have matching IAM/OS Login/SSH keys, log into the VM (still without an external IP) to inspect the file:

~~~bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --tunnel-through-iap \
  --command="sudo cat /var/lib/metadata-demo/info.txt"
~~~

The IAP command only works if the environment permits TCP 22 from IAP to the VM with proper IAM access; this lab **does not open SSH firewalls automatically**. Expected contents on the VM:

~~~text
vm=mds-lab-vm
project=YOUR_LAB_PROJECT_ID
environment=training
~~~

This is illustrative output; the actual Project ID matches the one you selected.

### 6.7. Updating Metadata and Understanding When Scripts Re-Run

**Mutating operation on the lab VM:**

~~~bash
gcloud compute instances add-metadata "$VM_NAME" \
  --zone="$ZONE" \
  --metadata=app-env=staging
~~~

Inspect metadata again via the control plane:

~~~bash
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(metadata.items)"
~~~

`app-env` is now `staging`, yet `/var/lib/metadata-demo/info.txt` **still reflects the previous startup** until the script runs again. To test idempotency in your **lab project**, you can intentionally stop and start the VM:

~~~bash
# Run only when the lab serves no users
gcloud compute instances stop "$VM_NAME" --zone="$ZONE"
gcloud compute instances start "$VM_NAME" --zone="$ZONE"
~~~

When the machine boots again, the guest environment re-runs the startup script and the sample file updates to `environment=staging`. In production, stopping/starting causes service disruption, rotates ephemeral external IPs (if any), and requires prior impact assessment.

### 6.8. Cleaning Up Resources and Checking Costs

After completing the lab, confirm the project and resource names belong to your lab:

~~~bash
gcloud config get-value project
gcloud compute instances list --filter="name=mds-lab-vm"
gcloud compute networks subnets list --filter="name=mds-lab-subnet"
~~~

**Delete only the resources you created in the lab project**:

~~~bash
gcloud compute instances delete "$VM_NAME" \
  --zone="$ZONE" --quiet

gcloud compute networks subnets delete mds-lab-subnet \
  --region="$REGION" --quiet

gcloud compute networks delete mds-lab-vpc --quiet
~~~

The local `startup.sh` file on Cloud Shell or your laptop is not a GCP resource. Store it in a reviewed repository or remove it manually when done. Never delete files or networks of the same name managed by someone else.

**Post-cleanup check:** confirm no lab VM, subnet, or VPC remains in Console/`gcloud`. VMs and disks may incur charges while active; accrued billing can appear with a delay in Cloud Billing. Internal metadata reads incur no Internet egress fees, but that does not make the entire lab free.

## 7. Troubleshooting Metadata Server and Startup Scripts

### 7.1. Outside-In Diagnostic Sequence

When a VM is running yet expected configuration is missing, check in order:

1. **Right VM/project/zone?** Verify `gcloud compute instances describe`, VM name, zone, and attached metadata.
2. **Is the guest environment working?** Supported public images include the guest agent; custom images or guest configs may omit or disable the startup runner.
3. **Does the metadata server respond inside the VM?** Check DNS, HTTP endpoint, required header, proxies, and guest OS firewall.
4. **Do the metadata keys exist?** Confirm exact `startup-script`/`startup-script-url` keys and any custom attributes read by the script.
5. **Did the script run and with what exit code?** Check serial output, `journalctl`, or Windows Event Viewer.
6. **Are external dependencies failing?** Do Cloud Storage downloads, package installs, Google Cloud API calls, or secret fetches have required IAM and network paths?
7. **Which step is non-idempotent?** If initial boot works but reboot fails, inspect file writes, user creation, package managers, and application state.

### 7.2. Common Errors Table

| Symptom | Causes to Check | Verification Steps |
| --- | --- | --- |
| `curl` to metadata returns 403 or rejected | Missing/wrong `Metadata-Flavor` header; endpoint restricted by config; malformed request. | Query benign `instance/name` with the right header; read HTTP status and troubleshooting docs. |
| `curl` returns 404 | Key or path does not exist, e.g., missing `app-env`. | Inspect instance/project metadata and key spelling (case-sensitive). |
| Metadata temporarily returns 429 or 503 | Rate limiting or transient server busy state during boot/maintenance. | Use bounded retries with backoff; avoid aggressive polling, especially on token endpoints. |
| Cannot resolve `metadata.google.internal` | DNS/guest network config, resolver, proxy, or system overrides. | Inspect DNS inside VM; test link-local IP `169.254.169.254` with required header. |
| Requests route through corporate proxy and fail | HTTP proxy or `NO_PROXY` omits metadata endpoints. | Ensure direct access to metadata per network policy; check `NO_PROXY` and proxy config. |
| Startup script does not run | Missing/disabled guest agent, wrong key name, OS mismatch, VM still booting. | Check serial port and guest environment; confirm exact Linux/Windows key names. |
| Script runs but exits non-zero | Command error, missing metadata, broken package repo, or unhandled exit code. | Inspect timestamped logs and exit code; test in a controlled lab VM. |
| `startup-script-url` fails to download | Wrong URL/object, missing egress path, insufficient IAM or VM access scopes. | Check object path, attached service account permissions, scopes, and NAT/Private Google Access. |
| Re-running script breaks the app | Non-idempotent script, duplicate config/migrations, mutable artifact version. | Compare previous vs. current boot logs, check script version; move migrations/deploys out of boot scripts. |
| `gcloud` inside script cannot call APIs | VM lacks service account, missing scopes/IAM, API disabled, or network blocked. | Inspect identity, IAM, OAuth scopes, API enablement, and connectivity; never print access tokens. |
| Startup logs missing in Cloud Logging | Startup script logs only locally/serial without a collection pipeline to Logging. | Check `journalctl` and serial output; configure Ops Agent/sinks if centralized logs are needed. |

### 7.3. Checking the Metadata Server Safely

**Inside a Linux VM**:

~~~bash
# Never query tokens during routine diagnostics
curl --fail --show-error --silent \
  --connect-timeout 3 --max-time 10 \
  --noproxy '*' \
  -H 'Metadata-Flavor: Google' \
  http://169.254.169.254/computeMetadata/v1/instance/name
~~~

If querying by IP succeeds while DNS fails, inspect the guest resolver/DNS. If neither connects, check guest OS network configuration, proxies, routes, and metadata server support docs. Do not tweak VPC firewalls by guesswork: the metadata server uses a special local path, and the issue often lives inside the guest OS.

**Inspecting Linux script logs:**

~~~bash
sudo systemctl status google-startup-scripts.service --no-pager
sudo journalctl -u google-startup-scripts.service -b -n 100 --no-pager
~~~

Depending on the image and guest environment, unit/log names may vary; consult image documentation if that unit is absent. On Windows, inspect the Application Log in Event Viewer for Google Compute Engine metadata script events.

### 7.4. When Scripts Fetch from Cloud Storage Without an External IP

Lacking an external IP **does not prevent** a VM from reaching Google Cloud APIs or Cloud Storage. You can use **Private Google Access**, proper DNS/routes/firewalls, or other supported egress mechanisms. If a script needs packages from the public Internet, **Cloud NAT** or a proxy may be required; Private Google Access does not provide general Internet access.

Beyond networking, IAM must also permit access. For example, to read a script object in a private bucket, the attached service account needs object read permissions and access scopes must not block the required API scope. **IAM without networking—or networking without IAM—will fail.**

## 8. Applying This in Multi-VM Deployments and Operations

### 8.1. Example: Multiple VMs Sharing an Image with Different Configurations

An organization runs an online learning backend:

| Environment | VM/Group Name | Custom Metadata | Goal |
| --- | --- | --- | --- |
| Development | `course-dev-vm` | `app-env=dev` | Connect to test services with verbose diagnostics enabled. |
| Staging | `course-stage-vm` | `app-env=staging` | Run production-like config without production secrets. |
| Production | MIG `course-prod-mig` | `app-env=prod` in template/VM config | Initialize VMs consistently and connect to approved production dependencies. |

Machines can share bootstrap logic, yet **never share service accounts or secrets across environments**. When autoscaling or health checks replace a VM, the new VM executes the startup script from scratch; therefore the script must bootstrap cleanly from an empty state without assuming local state from an old VM.

With a **managed instance group (MIG)**, use an **instance template** pinning the right metadata, image, network, and service account versions. Updating a template does not immediately apply every change to existing VMs; plan rolling replacements and verify differences between old and new VMs.

### 8.2. Separating Configuration, Secrets, and Deployment Code

| Information Type | Preferred Management Location | Rationale |
| --- | --- | --- |
| Environment name, non-sensitive feature flags | Controlled custom metadata | VMs read values at boot without hard-coding. |
| Passwords, API keys, database secrets | Secret Manager or approved secret vaults | Granular permissions, audit trails, and rotation. |
| Application binaries/container images | Artifact Registry or trusted artifact store | Versioning, vulnerability scanning, and verification. |
| OS and baseline packages | Tested base/custom images | Cuts boot install time and configuration drift. |
| Startup scripts | Code-reviewed repo, versioned artifacts, or IaC-managed metadata | Clean versioning and change traceability. |
| IAM and VPC | Policies/bindings and infra managed by platform admins | Prevents scripts from widening permissions or altering networks out of scope. |

A solid rollout strategy:

1. CI/CD tests startup scripts, lints shell code, and scans for embedded secrets.
2. Build reviewed images or artifacts with immutable **versions**.
3. Update the instance template with the vetted script URL or metadata.
4. Roll out to a small canary group; measure bootstrap duration, app health, and startup logs.
5. If criteria pass, expand rollout; if checks fail, roll back using the verified template/artifact.

### 8.3. Do Startup Scripts Replace Cloud Run or GKE?

No. Startup scripts specifically address **Compute Engine VM initialization**. On GKE, you also manage Kubernetes workloads, node images, init containers, DaemonSets, Workload Identity Federation, and cluster rollout mechanisms. On Cloud Run, workloads run in platform-managed containers with their own configuration and startup model; you do not attach a Linux Compute Engine `startup-script` to a Cloud Run service the way you do to a VM.

When choosing Compute Engine for OS control, legacy systems, or specialized software, metadata scripts cut manual toil. When a workload fits GKE or Cloud Run, adopt the configuration and identity model native to that service.

## 9. Practice Scenario and Self-Check Questions

**Scenario:** a backend team inherits three production API VMs. Every time a machine is recreated, the on-call engineer must SSH in, install packages, write a config file containing the Project ID, and start the service. One metadata entry holds a database password, and the script always downloads artifacts from a `latest` URL. During a recent reboot, one VM ended up running a different app version from the other two.

Design an improvement plan covering:

1. Which items belong in custom metadata vs. Secret Manager.
2. An idempotent startup script: create directories, read metadata with error checks, fetch a pinned artifact version, configure systemd, and report exit status.
3. A dedicated workload service account, secret/artifact permissions, and restrictions on who can edit metadata/scripts.
4. How to use instance templates, canary testing, and rollouts so all three VMs stay on the same config version.
5. What logs and checks to collect after VM boot, including transient Cloud Storage/API unavailability.
6. How to test that a second reboot creates no duplicate config, avoids unsafe migrations, and leaks no tokens.

### Review Questions

**1. Is the metadata server only reachable when a VM has a public IP and Cloud NAT?**  
No. The metadata server exposes an internal endpoint scoped to the VM; queries do not require general Internet egress.

**2. Why must `Metadata-Flavor: Google` be sent? Is this header a secret?**  
It is a mandatory header signaling intentional metadata requests; it is not a secret and does not replace process isolation or IAM.

**3. Does adding a new `startup-script` to a running VM's metadata execute it immediately?**  
No. Startup scripts normally run at VM boot; re-running them requires an explicit trigger per guest environment and operational procedure.

**4. What prerequisites are needed when using `startup-script-url`?**  
A valid URL/object, proper network reachability, and object-read IAM permissions on the attached service account (plus compatible access scopes if applicable).

**5. Why are metadata-editing permissions dangerous even if a user cannot SSH into the VM?**  
Because Linux startup scripts can run as root at boot and leverage the permissions of the VM's attached service account.

**6. Should OAuth access tokens retrieved from the metadata server be logged to Cloud Logging for debugging?**  
No. Tokens are sensitive credentials; log only error codes, non-sensitive identifiers, and status information.

**7. Why must startup scripts be idempotent when deployed via a MIG?**  
VMs can be replaced or rebooted repeatedly; scripts must converge to a consistent state without duplicating config or corrupting data.

**8. Why can a VM with no service account still read `instance/name`?**  
Reading system metadata inside a VM is distinct from calling Google Cloud APIs with OAuth credentials. No service account is needed to read the VM name.

## Official Google Cloud Documentation for Deployment Reference

- **About VM metadata:** https://cloud.google.com/compute/docs/metadata/overview — metadata structure, endpoints, and access security.
- **View and query VM metadata:** https://cloud.google.com/compute/docs/metadata/querying-metadata — HTTP syntax, headers, watch queries, and HTTPS requirements.
- **Set and remove custom metadata:** https://cloud.google.com/compute/docs/metadata/setting-custom-metadata — project/VM metadata, permissions, and limits.
- **About startup scripts:** https://cloud.google.com/compute/docs/instances/startup-scripts — lifecycle and guest environment prerequisites.
- **Use startup scripts on Linux VMs:** https://cloud.google.com/compute/docs/instances/startup-scripts/linux — keys, gcloud flags, logs, and re-running.
- **Use startup scripts on Windows VMs:** https://cloud.google.com/compute/docs/instances/startup-scripts/windows — PowerShell/CMD keys and Windows Event Viewer.
- **Guest agent functionality:** https://cloud.google.com/compute/docs/images/guest-agent-functions — responsibilities and metadata script management.
- **Troubleshoot metadata server access:** https://cloud.google.com/compute/docs/troubleshooting/troubleshoot-metadata-server — DNS, proxies, HTTP errors, and token issues.
- **Service accounts on Compute Engine:** https://cloud.google.com/compute/docs/access/service-accounts — identities, IAM roles, and access scopes.
- **Secret Manager:** https://cloud.google.com/secret-manager/docs/overview — managing secrets instead of storing them in metadata.
- **Managed instance groups:** https://cloud.google.com/compute/docs/instance-groups — templates, updates, and automated VM group management.

Flags, IAM permissions, HTTPS metadata endpoint features, and guest agent behavior can evolve across product releases. Verify current official docs, OS image types, and project policies before deploying to production. A system is well prepared when **VMs read properly scoped metadata, boot deterministically, expose zero credentials, emit diagnostic logs, and redeploy cleanly through a tested pipeline**.
