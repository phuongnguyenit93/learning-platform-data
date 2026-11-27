# Lab: Deploying Compute and Accessing via Bastion

## 1. Objectives and Lab Scenario

Within the **OCI Fundamentals Labs** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lab connects concepts of compartments, IAM, VCN, Compute, and storage into a verifiable deployment workflow: create an Oracle Linux VM with only a private IP address, then administer it via Oracle Cloud Infrastructure Bastion.

Suppose a development team needs a test host for a Java application. Operators need SSH access to inspect the OS and prepare the environment, but the team does not want to assign a public IP to the host or maintain a separate jump-host VM for sign-in.

Upon completing this lab, you will be able to:

- Deploy a Compute instance into a private subnet and verify that it has no public IP.
- Distinguish between IAM permissions, network connectivity rules, and OS login authentication.
- Create a Bastion with an allowlist restricted to your lab workstation's public IPv4 address.
- Create an SSH port forwarding session, establish a tunnel, and sign in using the target VM's key.
- Optionally test Managed SSH once Oracle Cloud Agent and the Bastion plugin are ready.
- Collect operational evidence, troubleshoot hop by hop, and clean up resources after the lab.

This lab uses the Console to provision infrastructure and OpenSSH on your local machine to connect. The CLI section at the end is optional; no extra tools are required to complete the main workflow.

## 2. Architecture and Independent Control Layers

### 2.1. Deployed architecture

~~~mermaid
flowchart LR
    Client["Local machine<br/>Public IPv4 in allowlist"]
    PublicEndpoint["OCI Bastion service endpoint<br/>TCP 22, session key"]
    subgraph VCN["VCN 10.38.0.0/16"]
        subgraph PrivateSubnet["Private subnet 10.38.10.0/24"]
            BastionPE["Bastion private endpoint<br/>BastionPrivateIP"]
            VM["Oracle Linux Compute<br/>Private IP, no public IP<br/>sshd TCP 22"]
        end
        SGW["Service Gateway"]
    end
    OSN["Oracle Services Network<br/>Supported regional services"]
    Client -->|"SSH tunnel"| PublicEndpoint
    PublicEndpoint -->|"Service-managed connection"| BastionPE
    BastionPE -->|"TCP 22, NSG allows /32 source"| VM
    VM -->|"Route via service CIDR label"| SGW
    SGW --> OSN
~~~

The Bastion in this lab is the **OCI Bastion service**, not a self-managed Compute VM acting as a jump host. You create the Bastion resource, access sessions, and network rules; you do not have to patch the OS of an intermediate VM.

The VCN contains a private subnet shared by the Compute instance and the Bastion's private endpoint. The lab creates a Service Gateway with a route to the Oracle Services Network from the start, aligning with Bastion creation guidance and supporting the Managed SSH extension. The Service Gateway does not assign a public IP to the Compute instance. See [Creating a Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-bastion.htm).

### 2.2. Do not confuse the three authentication and authorization layers

| Layer | Question to answer | Configuration in this lab |
| --- | --- | --- |
| IAM | Who is allowed to create Compute, Bastion, or sessions? | Group and policies in the lab compartment |
| Network | Which source packets may reach the endpoint and target host? | Client CIDR allowlist, security list, NSG, and OS firewall |
| SSH | How does the connecting user prove their identity? | Session key and Linux user login key |

Having permission to create a session does not automatically allow TCP 22 traffic through. Having the tunnel running also does not mean the Linux login key is valid.

In particular, you must distinguish two source addresses:

- **Client public IPv4**: the address the Bastion endpoint sees when your local machine connects over the Internet; used in the client CIDR allowlist.
- **Bastion private endpoint IPv4**: the source address inside the VCN when Bastion reaches the Compute instance; used in the ingress rule for the target host.

Do not use your laptop's LAN address such as `192.168.1.10` for the Internet allowlist, and do not use your laptop's public IPv4 as the NSG source for the Bastion-to-Compute hop.

### 2.3. Choose the session type

| Criterion | SSH port forwarding — main flow | Managed SSH — extension |
| --- | --- | --- |
| Session target | Private IP and specific TCP port | Linux Compute instance, OS user, and SSH port |
| Agent on target host | Does not depend on Oracle Cloud Agent | Requires Oracle Cloud Agent and Bastion plugin to be active |
| Linux login in this lab | Uses the VM key provided at instance creation | Uses the key declared for the Managed SSH session |
| Operation flow | Keep tunnel in terminal A, SSH from terminal B | Use the SSH command provided by the Console |

Port forwarding forwards TCP traffic to the target service. By itself, this session type does not require the target service to be SSH; however, **because this lab forwards to TCP 22 for Linux login, the target host must still run an SSH server**. Managed SSH prerequisites are described by Oracle in [Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

## 3. Environment, Permissions, and Cost Preparation

### 3.1. Prerequisites before starting

Prepare an OCI tenancy, an authorized region, and a dedicated lab compartment, such as `OCILab`. Your account must be placed by an administrator in a group with appropriate permissions. If your organization enforces Security Zones or additional network policies, use a lab configuration permitted by the organization.

On your local machine, you need:

- An OpenSSH client with the `ssh` and `ssh-keygen` commands.
- Outbound TCP 22 connectivity to the regional Bastion endpoint.
- Two terminals in the same execution environment.
- A reliable way to determine your current public IPv4 address, such as an organization-provided connection info page or egress information from your network administrator.

The local examples below use **Bash on Linux, macOS, or WSL**. If you choose WSL, open both terminals in WSL and store keys in your WSL home directory. If using OpenSSH in PowerShell, replace the key paths with actual Windows paths and write commands on one line; the Linux commands executed after SSHing into the VM remain unchanged.

A VPN, proxy, or switching from Wi-Fi to mobile data can change your egress address. Determine your public IPv4 on the exact network path that will open the SSH tunnel. Do not assume browser egress and terminal egress are always identical.

### 3.2. Choose resources within budget limits

Before creating the VM, check the shape, OCPU count, RAM, boot volume size, quota, and estimated cost in the selected region. Pick a small VM with an Oracle Linux image compatible with the CPU architecture and within tenancy limits. This lab does not depend on a single fixed shape name.

According to the [Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/), the Bastion service is listed as free at the time of writing. Compute, boot volumes, backups, and additional resources must still be evaluated for cost separately. Do not assume the entire lab is free just because Bastion is free.

Set aside about 60–90 minutes for your first run; a Bastion session may need to be recreated if it expires before you finish. Apply free-form tags such as `purpose=oci-compute-bastion-lab` and `owner=<your-name>` to locate resources easily after the session.

### 3.3. Policy for the lab builder

The example below assumes an administrator has created compartment `OCILab` and group `OCILabBuilders` in the `Default` identity domain. Replace with actual names. Learners do not need to grant permissions to themselves.

~~~text
Allow group 'Default'/'OCILabBuilders' to manage instance-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage volume-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage virtual-network-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage bastion-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to read instance-agent-plugins in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to inspect work-requests in compartment OCILab
~~~

This is a permission set for **someone building and cleaning up the entire lab within a dedicated compartment**. Network management permissions allow creating VCNs, subnets, gateways, and NSGs; Compute and volume permissions cover VM lifecycle and storage; Bastion permissions cover Bastion resources and sessions.

If the environment uses custom images in another compartment, defined tags, dedicated encryption keys, or shared resources, an administrator must grant corresponding permissions for those actual resources. The lab chooses an Oracle Linux platform image to avoid dependencies on Marketplace or internal images.

This permission set is broader than what someone needs merely to sign in to an existing VM. In real operations, separate network administrators, VM creators, and session creators; scope permissions by compartment and role. Cross-check [Compute IAM Policies](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/instances.htm) and [Bastion IAM Policies](https://docs.oracle.com/en-us/iaas/Content/Bastion/Reference/bastionpolicyreference.htm) when designing production policies.

## 4. Finalize Parameters and Prepare Two SSH Key Pairs

### 4.1. Parameter table

| Parameter | Lab value or how to obtain |
| --- | --- |
| Compartment | `OCILab` |
| Region | One chosen region, used consistently in Console and CLI |
| VCN | `vcn-oci-lab`, CIDR `10.38.0.0/16` |
| Subnet | `subnet-private-lab`, regional private subnet, CIDR `10.38.10.0/24` |
| Route table | `rt-private-lab` |
| Service Gateway | `sgw-oci-lab` |
| Security list | `sl-private-lab` |
| NSG for VM | `nsg-compute-ssh` |
| Compute | `vm-oci-lab`, Oracle Linux platform image |
| Bastion | `BastionLab` |
| Local TCP port | `2222`, change if already in use by another process |
| Linux user | `opc` for Oracle Linux in this lab |
| Session TTL | 30 minutes per connectivity practice run |

The VCN, subnet, and instance names here are sample resource names. The Bastion name specifically uses alphanumeric characters to comply with service naming requirements.

In addition to display names, record the OCIDs of the compartment, instance, Bastion, and session. Also record the VM's private IP and the Bastion's private endpoint IP after creation. OCIDs help identify the exact resource when duplicate names exist.

### 4.2. Generate keys on your local machine

In local Bash:

~~~bash
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh/oci-lab-vm" -C "oci-lab-vm"
ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh/oci-lab-session" -C "oci-lab-session"

chmod 600 "$HOME/.ssh/oci-lab-vm" "$HOME/.ssh/oci-lab-session"
~~~

Set a passphrase when prompted. If those filenames already exist, choose new names and update all subsequent commands rather than overwriting keys already in use.

| File | Where to place | Purpose |
| --- | --- | --- |
| `oci-lab-vm.pub` | SSH public key field when creating Compute | Enables Linux authentication for the VM key holder |
| `oci-lab-vm` | Keep on local machine only | SSH to `opc` through the tunnel |
| `oci-lab-session.pub` | SSH public key field when creating session | Declares the key authorized for the session |
| `oci-lab-session` | Keep on local machine only | Authenticates the connection to the Bastion session |

Upload only `.pub` files. Never copy private keys onto the VM, paste them into the Console, user data, Git, or lab reports. SSH agent forwarding does not need to be enabled for this lab.

## 5. Create the Private Network and Path to Oracle Services Network

### 5.1. Create the VCN and network components

In the Console, select the right region and compartment `OCILab`. Open **Networking → Virtual cloud networks** and create VCN `vcn-oci-lab` with CIDR `10.38.0.0/16`.

Use the manual VCN creation flow to explicitly choose resources. Enable DNS resolution for the VCN; keep DHCP options using the VCN-provided resolver.

Create in order:

1. Route table `rt-private-lab`.
2. Security list `sl-private-lab`.
3. Regional subnet `subnet-private-lab`, CIDR `10.38.10.0/24`.
4. Set the subnet to **private**, disallowing public IPv4 addresses on VNICs.
5. Associate the subnet with `rt-private-lab`, the VCN's DHCP options, and `sl-private-lab`.

In the dedicated lab security list:

- Have no ingress rule for TCP 22.
- If there is an ingress rule allowing all protocols or all ports from the VCN/subnet, remove that rule from the lab configuration.
- You may keep ICMP diagnostic and Path MTU rules if pre-configured.
- For the main workflow, keep stateful egress for all protocols to `0.0.0.0/0` so SSH learning is not mixed with outbound filtering exercises.

An egress rule only permits traffic at the network security layer; it does not create a route on its own. This lab creates no Internet Gateway, NAT Gateway, or Internet default route. The VM still has no general Internet access path. For production, design egress per required service and test separately.

If the subnet automatically attaches the default security list as well, inspect the applied security lists and remove the extra association or remove broad ingress rules in your dedicated lab resources. The goal is to have no SSH allow path other than the NSG rule added later.

### 5.2. Create the Service Gateway and route

Inside the VCN, create Service Gateway `sgw-oci-lab`, choosing the service CIDR label **All <region> Services in Oracle Services Network** for the current region.

In `rt-private-lab`, add a route:

| Field | Value |
| --- | --- |
| Destination type | Service |
| Destination service | All <region> Services in Oracle Services Network |
| Target type | Service Gateway |
| Target | `sgw-oci-lab` |

Do not replace the service CIDR label with `0.0.0.0/0`. Do not manually enter a fixed public IP of an Oracle service.

The Service Gateway provides access to supported Oracle services in the region and does not replace NAT for arbitrary downloads from the Internet. The lab verification commands do not require `dnf install`, downloading a JDK, or fetching packages from public repositories. See [Access to Oracle Services: Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm).

### 5.3. Create the NSG for Compute

Create `nsg-compute-ssh` in `vcn-oci-lab`. Hold off on adding the SSH ingress rule for now because the Bastion's private endpoint IP is not yet known.

Keep the NSG free of broad ingress rules. During VM creation, attach this NSG to the primary VNIC.

Security lists and NSGs take effect as the **union of allow rules**. A narrow NSG does not revoke a broad SSH rule in a security list; therefore, the security list check above is mandatory for this lab configuration. This behavior is explained in [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

**Checkpoint:** the subnet is private; the route table has a route to the Service Gateway; the subnet has no broad TCP 22 ingress; the NSG is created in the right VCN.

## 6. Deploy Oracle Linux Compute

Navigate to **Compute → Instances → Create instance**. Configure:

| Configuration group | Selection |
| --- | --- |
| Name and compartment | `vm-oci-lab`, `OCILab` |
| Image | Supported Oracle Linux platform image |
| Shape | Small VM fitting budget, quota, and image architecture |
| Availability domain | An AD with capacity for the chosen shape |
| VCN/subnet | `vcn-oci-lab` / `subnet-private-lab` |
| Primary VNIC | Attach `nsg-compute-ssh` |
| Public IPv4 | Do not assign |
| SSH key | Upload or paste contents of `oci-lab-vm.pub` |
| Boot volume | Size required for the image, within budget |
| User data | Leave blank; no package downloads needed for this lab |

Keep Oracle Cloud Agent enabled if supported by the image. The port-forwarding flow does not depend on the Bastion plugin, so you can complete basic connectivity before practicing Managed SSH.

Review the summary screen before creation, especially public IP, shape, and boot volume. Once the instance enters **Running**:

1. Open primary VNIC details.
2. Record the assigned private IPv4; later examples use `10.38.10.25`, which you must replace with your real value.
3. Confirm public IP is blank.
4. Confirm the VNIC belongs to `nsg-compute-ssh`.
5. Record the OCIDs of the instance and boot volume.

Do not force the example private IP if that address is already assigned to another resource. The Running state only confirms VM lifecycle status; the SSH server may take a bit longer to become ready.

Workflow and field names may vary by Console version; consult [Creating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm) if labels differ.

**Checkpoint:** exactly one lab VM is Running in the private subnet, with a boot volume and private IP, and no public IP.

## 7. Create Bastion and Open the Exact Path to Compute

### 7.1. Create the Bastion resource

In the Console, locate the **Bastion** service, typically under **Identity & Security**. Select compartment `OCILab` and create a Bastion with:

- Name: `BastionLab`.
- Target VCN: `vcn-oci-lab`.
- Target subnet: `subnet-private-lab`.
- Client CIDR allowlist: current public IPv4 of your lab workstation, formatted as `<real-IP>/32`.
- Maximum session time-to-live: 30 minutes for the lab.
- No need to enable FQDN or SOCKS5 features.

An address like `203.0.113.25/32` only illustrates syntax; it is not an address to use verbatim. If accessing through a corporate network with multiple egress addresses, use the CIDR list confirmed by your administrator.

Wait for the Bastion to become active, then record its **Private endpoint IP address**. Examples assume `10.38.10.10`; replace with your actual address.

Do not open the allowlist to `0.0.0.0/0` to troubleshoot errors. Maximum session TTL is currently configurable in the 30–180 minute range; this lab picks the lower end of that range. See [Creating a Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-bastion.htm).

### 7.2. Add SSH ingress to the VM's NSG

In `nsg-compute-ssh`, add one rule:

| Field | Value |
| --- | --- |
| Direction | Ingress |
| Stateless | Unchecked, use stateful |
| Source type | CIDR |
| Source CIDR | `<BastionPrivateIP>/32` |
| IP protocol | TCP |
| Source port | All |
| Destination port | `22` |
| Description | SSH from OCI Bastion private endpoint |

With the example above, the source is `10.38.10.10/32`. Do not use the VM's private IP as the source, and do not restrict source port to 22: the connecting client normally uses an ephemeral source port.

A stateful rule tracks connection state and allows corresponding return traffic. The subnet's egress rules in this lab also permit the necessary path.

Because the Bastion endpoint and VM reside in the same VCN, they communicate internally; do not add an Internet route for this SSH hop. If using a Bastion in another subnet within the same VCN, check security rules and routing for both subnets.

Oracle documents using the Bastion's private endpoint IP to allow access to target hosts in [Allowing Network Access From the Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connectingtosessions.htm).

**Checkpoint:** the allowlist contains the client's public IP; the VM's TCP 22 ingress allows only the Bastion's private endpoint IP. These two values serve different roles.

## 8. Create a Port Forwarding Session and Sign In

### 8.1. Create the session

Open `BastionLab` → **Sessions → Create session**:

1. Select **SSH port forwarding session**.
2. Give the session an identifiable name, e.g., `ssh-vm-lab`.
3. Select the target instance or enter the actual private IP of `vm-oci-lab`.
4. Set target port to `22`.
5. Supply public key `oci-lab-session.pub`.
6. Set TTL to 30 minutes, not exceeding the Bastion's maximum.
7. Create the session and wait for status **Active**.

Record the OCID, target private IP, target port, and expiration time. Select **Copy SSH command** from the exact session just created. Do not copy a command from an expired session or a session for another host.

Refer to session creation fields in [Creating a Port Forwarding Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-session-port-forwarding.htm).

### 8.2. Terminal A: hold the SSH tunnel open

Prefer the command generated by the Console, replacing the private key and local port placeholders. The pattern below illustrates binding the listener strictly to loopback; replace the session OCID, hostname, and private IP with real values:

~~~bash
ssh -i "$HOME/.ssh/oci-lab-session" -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -N -L 127.0.0.1:2222:10.38.10.25:22 -p 22 ocid1.bastionsession.oc1.REGION.REPLACE_ME@host.bastion.REGION.oci.oraclecloud.com
~~~

Do not guess the hostname from the region display name. Copy the exact `<session_OCID>@<host>` user string provided by the Console.

Meaning of each component:

| Component | Meaning |
| --- | --- |
| `-i oci-lab-session` | Key authenticating to the Bastion session |
| `-N` | Do not open a remote shell on the Bastion endpoint |
| `-L 127.0.0.1:2222:<VM_IP>:22` | Forward TCP from local loopback to the VM's SSH port |
| `IdentitiesOnly=yes` | Prefer the explicitly specified identity |
| `ExitOnForwardFailure=yes` | Exit if forwarding cannot be established, e.g., local port already in use |
| `ServerAliveInterval` | Send keepalives; does not extend session TTL |

If prompted to confirm the host key on first connection, verify the hostname and cross-check the fingerprint via a trusted environment source when available. Do not disable `StrictHostKeyChecking` to bypass warnings.

After authentication, the terminal may appear idle without showing a prompt. This is normal for a tunnel using `-N`; keep this terminal open. Successfully creating the local listener does not yet prove the target SSH server is reachable, because the connection to the target is opened when a client traverses the tunnel.

### 8.3. Terminal B: SSH into Oracle Linux

In a second local terminal:

~~~bash
ssh -i "$HOME/.ssh/oci-lab-vm" -o IdentitiesOnly=yes -o HostKeyAlias=oci-lab-vm -p 2222 opc@127.0.0.1
~~~

This time use the **VM key**, not the session key. `127.0.0.1:2222` is the local end of the tunnel; it is not a public Compute endpoint.

`HostKeyAlias=oci-lab-vm` stores the host key under a logical VM name rather than only by local port. For multiple VMs, use distinct aliases. If you recreate the VM, verify the host key change before updating the stored entry.

Before trusting the target host's key in high-assurance environments, verify the fingerprint over a trusted administrative channel, such as a separately authorized console connection. When connected via a trusted administrative channel, you can inspect the fingerprint with `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` if that key exists and matches the algorithm the client uses. Reading the fingerprint over the unverified connection itself does not provide independent proof.

This two-terminal flow corresponds to [Connecting to a Port Forwarding Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connect-port-forwarding.htm). Do not use `-A` or expose the local listener to the entire network with `0.0.0.0`.

## 9. Verify Results and Test Access Boundaries

### 9.1. Verify inside the VM

After signing in successfully, run on the **Oracle Linux VM**:

~~~bash
whoami
hostname
cat /etc/os-release
ip -brief address
ip route
sudo systemctl is-active sshd
sudo ss -lntp '( sport = :22 )'
~~~

Expected output:

- `whoami` returns `opc`.
- OS information matches the chosen Oracle Linux image.
- The primary interface has the private IP matching the primary VNIC in the Console.
- `sshd` is active and listening on TCP 22.

`ip route` inside the guest typically shows a default route to the subnet's virtual router. That does not prove the subnet has an Internet Gateway or NAT Gateway: outbound forwarding decisions reside in OCI route tables.

Similarly, do not rely solely on `ip address` inside the guest to conclude whether an OCI public IP exists. Checking the public IP field of the primary VNIC in the Console is direct evidence for this lab requirement.

### 9.2. Controlled tests

| Test | How to perform | Expected result |
| --- | --- | --- |
| Correct VM key | SSH in terminal B using `oci-lab-vm` | Logs in as `opc` |
| Wrong key at Linux layer | Exit shell, test terminal B with `oci-lab-session` instead of `oci-lab-vm` | Denied if session key has not been authorized on the VM |
| Close tunnel | Exit shell, press Ctrl+C in terminal A, then SSH again from terminal B | Cannot connect to local port 2222 |
| Revoke session | Reopen tunnel with an active session, then delete the session in Console | Session is revoked; new connections cannot be established with the old session |
| TTL expiration | Observe an expired session or check expiration timestamp | Must create a new active session to regain access |

Perform the wrong-key test **before the Managed SSH section** so the session key has not yet been authorized for `opc` by the plugin. Keep `IdentitiesOnly=yes` and avoid local SSH configs that automatically try multiple IdentityFiles, otherwise the test may silently fall back to another valid key.

Do not modify an NSG while watching an already-open SSH connection as a decisive revocation test: connection tracking can affect existing flows. To retest network rules, close existing connections and open a new one. To terminate lab access immediately, delete the session and recheck status.

After the revocation test, create a new session if continuing to the next section. Do not widen CIDRs just to make a test "succeed".

## 10. Extension: Connect Using Managed SSH

This section reuses the VM and network infrastructure just created; no extra Compute instance is needed.

### 10.1. Prepare the plugin

Open `vm-oci-lab` details and locate **Oracle Cloud Agent** or the agent plugins list under instance management:

1. Confirm plugins are not globally disabled.
2. Enable the **Bastion** plugin.
3. Wait for status **Running**, rather than relying solely on the Enabled toggle.
4. If the plugin does not reach Running, check DNS, the route to Service Gateway, HTTPS egress, and image agent status.

Plugin state changes can take several minutes; Oracle's documentation notes it may take up to 10 minutes. See [Managing Plugins with Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/manage-plugins.htm).

You can check services from an active shell with:

~~~bash
sudo systemctl status oracle-cloud-agent --no-pager
sudo systemctl status sshd --no-pager
~~~

Do not disable the OS firewall or open Internet ingress to fix plugin status. The plugin needs service connectivity; the SSH flow to the target host still requires the TCP 22 rule from the Bastion private endpoint.

### 10.2. Create and use a Managed SSH session

In `BastionLab`, create a new session:

- Session type: **Managed SSH session**.
- Target instance: `vm-oci-lab`.
- Operating system username: `opc`.
- Port: `22`.
- Public key: `oci-lab-session.pub`.
- TTL: 30 minutes.

Wait for the session to become Active, choose **Copy SSH command**, and replace `<privateKey>` with the path to `oci-lab-session` everywhere required by the command. The command typically includes a proxy step through the Bastion endpoint; preserve the structure generated by the Console.

With Managed SSH, the key declared for the session participates in host authorization via the plugin. Do not mechanically apply the port-forwarding rule "the VM SSH step must use the VM key" to this session type.

After signing in, re-run `whoami` and `hostname`, confirming it is the same VM. Follow [Creating a Managed SSH Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-session-managed-ssh.htm) and [Connecting to a Managed SSH Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connect-managed-ssh.htm).

## 11. Optional: Inspect Resources Using the OCI CLI

This section assumes the OCI CLI is configured and authenticated against the right tenancy, region, and lab permissions. Do not use an SSH private key in place of an API signing key.

The variables and commands below run in **local Bash with the OCI CLI**, not by default on the VM:

~~~bash
export OCI_CLI_REGION="REPLACE_WITH_REGION_ID"
export INSTANCE_OCID="REPLACE_WITH_INSTANCE_OCID"
export BASTION_OCID="REPLACE_WITH_BASTION_OCID"

oci compute instance get --instance-id "$INSTANCE_OCID"
oci bastion bastion get --bastion-id "$BASTION_OCID"
oci bastion session list --bastion-id "$BASTION_OCID" --all
~~~

Cross-check lifecycle states, OCIDs, and session target details against the Console. Do not infer names or IPs from list ordering.

You can create a **new port forwarding session** via CLI:

~~~bash
export VM_PRIVATE_IP="10.38.10.25"

oci bastion session create-port-forwarding --bastion-id "$BASTION_OCID" --display-name "ssh-vm-cli" --target-private-ip "$VM_PRIVATE_IP" --target-port 22 --ssh-public-key-file "$HOME/.ssh/oci-lab-session.pub" --session-ttl 1800 --wait-for-state ACTIVE
~~~

Replace the private IP before running. This command creates an actual additional session; do not run it repeatedly without understanding prior session states. CLI TTL is measured in seconds, so `1800` corresponds to 30 minutes. Retrieve the service-provided SSH command from the session details or from the Console.

The CLI separates session creation from opening the SSH connection. When automating full infrastructure, manage input OCIDs and resource dependencies explicitly; never commit private keys into Terraform code or Git. Session parameters are documented at [OCI CLI: create-port-forwarding](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/bastion/session/create-port-forwarding.html).

## 12. Operational Observation and Troubleshooting

### 12.1. Save useful evidence

Before cleaning up resources, record the necessary values or screenshots:

| Evidence | What it proves |
| --- | --- |
| Instance and primary VNIC | VM resides in the private subnet, public IP is blank |
| NSG and subnet security lists | No SSH rule broader than the chosen Bastion source |
| Bastion | Correct target VCN, subnet, and client allowlist |
| Session | Correct target private IP, port 22, TTL, and state |
| Linux command outputs | Logged in as the right user on the right machine |
| Revocation test results | Old session can no longer reopen connections |
| Post-cleanup resource list | No forgotten boot volumes or lab resources remain |

Do not include private keys, passphrases, tokens, or API credentials in evidence. When sharing publicly, mask unnecessary identifiers and addresses.

If granted Audit permissions, search for Bastion session create/delete events in the right compartment and time window. Audit answers who called the API and when; by default it does not record individual shell commands executed over SSH. To log activity inside Linux, design a separate OS-level logging mechanism. See [Securing Bastion — Auditing](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/bastion_security.htm).

### 12.2. Hop-by-hop diagnostics

The verification path is: **IAM and resource state → local machine to Bastion endpoint → private endpoint to VM TCP 22 → Linux authentication**.

| Symptom | Likely layer involved | How to check and resolve |
| --- | --- | --- |
| Instance or Bastion not visible | Wrong region, compartment, or permissions | Check filters first, then policies and groups |
| `NotAuthorizedOrNotFound` | Permissions or identifiers | Cross-check OCID, region, compartment, and IAM; do not immediately assume deletion |
| Cannot create VM | Quota, capacity, image/shape, or policy | Read work request; pick compatible shape/AD after checking budget |
| Terminal A times out before auth | Client network or endpoint | Check DNS, outbound TCP 22, hostname, and VPN path |
| Bastion closes connection early | Allowlist or invalid session | Check egress IP, Active session, TTL, and OCID in command |
| Terminal A shows `Permission denied (publickey)` | Session authentication | Check session key, declared public key, and SSH client algorithm policy |
| Terminal A runs but terminal B times out | Bastion-to-VM hop | Check target private IP, NSG attached to right VNIC, /32 source, TCP 22, and Linux firewall |
| Terminal B shows `Permission denied (publickey)` | Linux login | Check `opc` user, VM key, and authorized keys |
| `Address already in use` locally | Port 2222 is busy | Stop old tunnel or change both local port and terminal B SSH command |
| Managed SSH creation fails | Plugin, agent, or service path | Confirm plugin Running, DNS, SGW route, HTTPS egress, and valid user |
| Disconnected mid-session | TTL, network drop, or idle | Check session expiration and network; keepalive does not extend TTL |

To gather more detail, add `-v` to the **failing SSH command**. Per Oracle's Bastion guidance, do not use `-vv` or `-vvv`. Distinguish messages from terminal A versus terminal B before changing keys.

If your public IPv4 changes, update the Bastion allowlist and then **create a new session**; updating the allowlist does not update existing sessions. This detail is noted in [Problems Connecting to a Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/troubleshooting_connect_session_failed.htm).

If port forwarding SSH works while Managed SSH still fails, that narrows the issue down to the agent, plugin, or Managed SSH-specific prerequisites. See [Managed SSH Session Creation Failed](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/troubleshooting_managed_ssh_session_creation_failed.htm).

## 13. Clean Up Resources and Control Residual Costs

Delete only the resources created for this lab, verifying names, OCIDs, compartment, and tags beforehand. If shared resources exist, leave them intact and ask their owner to handle dependencies.

Proceed in order:

1. Exit all shells on the VM with `exit`.
2. Stop local tunnels with Ctrl+C.
3. Delete all remaining lab sessions, including sessions created via CLI or Managed SSH.
4. Delete `BastionLab`, waiting for the service-managed private endpoint to be released.
5. Terminate `vm-oci-lab`. If you do not need to retain lab data, explicitly select **delete the attached boot volume** in the dialog.
6. Check Boot Volumes, Block Volumes, and Backups to delete any leftover lab items, if present.
7. Delete `nsg-compute-ssh` once no VNICs remain attached.
8. Delete the private subnet once no dependent resources or private endpoints remain.
9. Delete the Service Gateway route, then delete the Service Gateway and the lab's custom route table and security list once unattached.
10. Delete the VCN after dependent components are cleaned up. Default VCN objects are handled as part of VCN deletion.
11. If groups or policies were created solely for this lab session, have an administrator revoke them after confirming no dependent users remain.

If the Console refuses to delete the subnet because VNICs/private endpoints still exist, inspect the dependent resources rather than deleting other items at random. Confirm the Bastion is fully deleted and the Compute instance has finished terminating.

Do not treat Stopping an instance as complete cleanup. Retained boot volumes, backups, or other resources still require separate attention. [Terminating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/terminatinginstance.htm) lets you explicitly delete the boot volume with the VM; check the actual option rather than relying on defaults.

Cost data in the Console may update with a delay. Cross-check the resource list to confirm cleanup first, then review cost reports once data appears.

## 14. Completion Criteria and Model Limitations

The lab is complete when all of the following evidence is captured:

- An Oracle Linux Compute instance running in a private subnet with no public IP.
- Bastion accepting clients only from the identified egress CIDR.
- VM SSH ingress allowed only from the Bastion's private endpoint; both NSG and security list verified.
- Port forwarding working with two distinct key layers matching their roles.
- User, hostname, and SSH server verified on the target host.
- Tunnel closure or session revocation tested, confirming the old session cannot reopen connections.
- If the extension is completed, Managed SSH works after the Bastion plugin reaches Running.
- Lab resources, especially boot volumes and generated sessions, inventoried and cleaned up.

This model has a single VM and one boot volume tied to the machine's lifecycle; it does not yet provide high availability for applications. Bastion is an administrative access path and does not replace a load balancer, VM recovery mechanism, or backup strategy. When evolving into an environment for a Java application or Oracle database, you must additionally design resource distribution, data recovery, monitoring, and role-based access control.

The key takeaway from this lab is a clear verification chain: the right user creates the session, the right source traverses the network, the right key signs in to the machine, access expires as designed, and resources are cleaned up when no longer needed.
