# Server Access via Session Manager and EC2 Instance Connect

> **Chapter:** EC2 Instances  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore AWS from Regions/AZs, IAM, and VPC to compute, storage, data, integration, and serverless; practice designing and operating applications securely with observability, recovery, and cost control.

When operating Amazon EC2, we often need to log in to inspect logs, adjust configuration, diagnose network errors, or resolve incidents. The traditional approach is opening SSH (TCP port 22) from an admin workstation to Linux EC2 instances. In production environments, exposing SSH directly over the Internet increases the attack surface and complicates SSH key management and identity control.

AWS offers two access methods commonly considered:

- **AWS Systems Manager Session Manager**: establishes a session through Systems Manager and the SSM Agent, usually requiring no public IP or inbound SSH port.
- **Amazon EC2 Instance Connect (EIC)**: issues a **temporary SSH public key** to Linux EC2 instances and connects over SSH. With an **EC2 Instance Connect Endpoint (EICE)**, connections can reach instances via private IP without an Internet Gateway, bastion host, or public IP.

Both methods integrate with **IAM**, yet their **connection path, network requirements, OS-level authentication, and session logging capabilities** differ. This lesson guides you on choosing the right option for each scenario and verifying the access path before using it in production.

## 1. Learning Objectives

After completing this lesson, learners will be able to:

1. Distinguish Session Manager, EC2 Instance Connect over public IP, and EC2 Instance Connect Endpoint over private IP.
2. Prepare the right IAM permissions, instance profiles, agents or SSH support packages, Security Groups, and VPC connectivity.
3. Use the AWS Console/AWS CLI to open management sessions, understanding the role of OS users and SSH keys.
4. Design access to EC2 instances in private subnets using VPC interface endpoints or an EIC Endpoint.
5. Explain the limitations of session logging, CloudTrail, and safeguards for privileged access.
6. Troubleshoot `TargetNotConnected`, `AccessDenied`, SSH timeouts, wrong OS user errors, and network connectivity issues.

## 2. A Map of the Three Access Paths

~~~mermaid
flowchart TB
    A["IAM-authenticated Administrator"]
    subgraph AWS["AWS control plane and authorized connectivity"]
        SSM["Systems Manager Session Manager"]
        EIC["EC2 Instance Connect API"]
        EICE["EC2 Instance Connect Endpoint"]
    end
    subgraph VPC["Amazon VPC"]
        Agent["Linux/Windows EC2 with SSM Agent"]
        Public["Linux EC2 with SSH and public IP"]
        Private["Linux EC2 with SSH, private IP"]
    end
    A -->|"StartSession, HTTPS"| SSM
    Agent -->|"Outbound TLS 443 channel"| SSM
    A -->|"SendSSHPublicKey, IAM"| EIC
    EIC -.->|"Temporary SSH key in instance metadata"| Public
    A -->|"SSH TCP 22 over Internet"| Public
    A -->|"OpenTunnel, IAM"| EICE
    EICE -->|"TCP 22 via VPC"| Private
    EIC -.->|"Can push public key for SSH"| Private
~~~

*These branches illustrate typical patterns. EICE is a TCP tunnel and can work with an existing SSH key; pushing a key via the EIC API and opening an EICE tunnel are **two separate operations**. Sessions can also use other setups such as SSH over Session Manager.*

| Criterion | Session Manager | EIC via Public IP | EIC via EIC Endpoint |
| --- | --- | --- | --- |
| Session control technology | Systems Manager and SSM Agent | SSH and EIC API providing public key | SSH/TCP tunnel through EICE, optionally combined with EIC API |
| Does the instance need a public IP? | **No** | Usually **yes** when connecting directly from the Internet | **No** |
| Needs inbound TCP 22 on EC2? | **No** for standard Session Manager shell | **Yes** from allowed SSH sources | **Yes** from the endpoint per network model |
| Requirements on the instance | SSM Agent, instance profile permissions, outbound network to SSM | SSH server, EIC-compatible AMI/OS user, public network path | SSH server; EIC package if using temporary keys; path to EICE |
| User IAM permissions | `ssm:StartSession` and related permissions | `ec2-instance-connect:SendSSHPublicKey` and EC2 describe rights | `ec2-instance-connect:OpenTunnel` and related rights; plus SendSSHPublicKey if using temporary keys |
| Session content logging | Configurable for standard Session Manager shells | Does not automatically record full SSH content via Session Manager | Does not automatically record full SSH/tunnel content |
| Best-fit use case | General administration without public SSH | Linux systems with existing SSH and public IP | Private Linux hosts needing SSH; certain other TCP tunnels |

**Additional distinction:** An EIC Endpoint is not a **VPC interface endpoint for the SSM service**. One is a TCP tunnel to EC2; the other is a private network path from the **SSM Agent** to the Systems Manager APIs.

## 3. How Does Session Manager Work?

**Session Manager** is a capability of **AWS Systems Manager**. When an IAM-authorized user starts a session, the SSM Agent on EC2 establishes a data channel through the AWS service. Because the **channel is initiated outbound from the instance**, you generally do not need to assign a public IP, open inbound TCP 22, or manage SSH private keys for a standard shell.

### 3.1. Connection Flow

~~~mermaid
sequenceDiagram
    participant User as Administrator
    participant IAM as IAM / AWS Systems Manager
    participant Agent as SSM Agent on EC2
    participant OS as Operating System Shell
    User->>IAM: StartSession(target = instance ID)
    IAM-->>User: Validate permissions and session info
    Agent->>IAM: Outbound TLS channel to SSM service
    IAM-->>Agent: Initialize valid session
    Agent->>OS: Spawn shell per Run As config
    User<->>OS: Exchange commands/output over Session Manager channel
~~~

*Conceptual diagram of the control and data flows. Actual connections use the relevant service endpoints/channels; traffic is not sent directly from the admin machine to the instance's private IP.*

### 3.2. Prerequisites on EC2

| Prerequisite | What to Check | Why It Is Needed |
| --- | --- | --- |
| **SSM Agent** | Installed, supported version, and running | The agent connects to Systems Manager and initiates sessions |
| **IAM instance profile** | Has SSM permissions for EC2, typically starting with the AWS managed policy `AmazonSSMManagedInstanceCore` | The instance needs permission to communicate with the service |
| **Network connectivity** | Instance can send outbound HTTPS/TLS 443 to required SSM endpoints, via Internet/NAT or PrivateLink | The agent must reach AWS Systems Manager |
| **DNS** | Can resolve endpoint hostnames; if using interface VPC endpoints, enable matching private DNS/VPC DNS | The agent locates the correct service address |
| **Administrator IAM** | Permitted to start a session against the target managed node and session document | Seeing an EC2 instance does not grant shell access |
| **Client** | AWS Console or AWS CLI with the Session Manager plugin when using local CLI | Renders and streams session I/O |

**Note two-sided permissions:** `AmazonSSMManagedInstanceCore` belongs on the server's **instance profile**, not on an administrator to let them log into any EC2 instance. Conversely, an IAM user with `ssm:StartSession` still cannot connect to an instance that is not online in Systems Manager.

### 3.3. SSM Agent and the Managed Node Role

Many AWS-provided AMIs bundle SSM Agent, but do not assume every custom AMI, older Linux image, or custom Windows image has a healthy running agent. Check status in **AWS Systems Manager → Fleet Manager / Managed nodes** or via the describe CLI command.

On some Linux systems using `systemd`:

~~~bash
# Run directly on the EC2 instance or in an authorized environment
sudo systemctl status amazon-ssm-agent
~~~

With Snap-based installations (such as some Ubuntu releases), the service name may differ, e.g., `snap.amazon-ssm-agent.amazon-ssm-agent.service`. Check your AMI's documentation rather than assuming one `systemctl` command fits every OS. If you cannot reach the machine yet, inspect Systems Manager/EC2 console details, boot logs, EC2 serial console (if eligible), or pre-planned recovery paths.

### 3.4. Using Session Manager Without a Public IP

In a private subnet, there are two main outbound connectivity approaches:

1. **NAT Gateway / Internet egress:** the instance uses a private IP with its default route pointing to a NAT in a public subnet. Security Groups and NACLs allow outbound HTTPS and return traffic; no inbound port 22 is needed.
2. **Interface VPC endpoints (AWS PrivateLink):** create the required SSM endpoints in the VPC, enable private DNS, and configure the endpoint Security Group to accept TCP 443 from managed instances. Instances communicate with the endpoint's private IP without needing NAT for SSM traffic.

Endpoints to evaluate:

~~~text
com.amazonaws.<region>.ssm
com.amazonaws.<region>.ssmmessages
com.amazonaws.<region>.ec2messages  (only when required by Agent version/Region and operational flow)
~~~

`ssmmessages` provides the core Session Manager data channel. `ec2messages` is tied to older SSM Agent/Region flows and is no longer supported in some newer Regions; **do not blindly create or require it in every Region**. Features such as writing CloudWatch Logs, S3, KMS, updating the Agent, or fetching OS packages may require separate endpoints/network paths and permissions.

Example for a private EC2 instance with SG `sg-ec2` and interface endpoints:

- EC2 SG: allow outbound TCP **443** to the endpoints per network policy.
- Interface endpoint SG: allow inbound TCP **443** from SG `sg-ec2`.
- VPC has DNS resolution/hostnames enabled and endpoints use private DNS when needed.
- Route tables permit internal routing to the endpoint ENI subnet; any custom NACL must allow bidirectional request/response traffic.
- EC2 instance profile has appropriate SSM permissions; no endpoint policy blocks required operations.

Placing endpoints across multiple AZs reduces single-location dependency for service connectivity; actual designs must still verify DNS, quotas, endpoint subnets, and service AZ support.

## 4. Hands-On: Opening a Session Manager Session

Suppose a Linux instance has the illustrative ID `i-0123456789abcdef0` in Region `ap-southeast-1`. Learners must hold valid AWS permissions and practice only on authorized resources.

### 4.1. Method 1: AWS Management Console

1. Open **EC2 console → Instances**, select the target Region and EC2 instance.
2. Select the instance and click **Connect**.
3. Open the **Session Manager** tab.
4. If the instance is online and permissions allow, click **Connect** to open a browser shell.
5. Check the active OS user, working directory, and session details; close the session when done.

You can also launch sessions from **Systems Manager → Session Manager → Start session** or Fleet Manager. Exact UI details may vary across console updates.

### 4.2. Method 2: AWS CLI

On the admin workstation, you need **AWS CLI**, credentials configured for the target Region/account, and the **Session Manager plugin** (for starting interactive CLI sessions). Verify identity before connecting:

~~~bash
aws sts get-caller-identity
aws --version
session-manager-plugin
~~~

Depending on the plugin version, running `session-manager-plugin` with no arguments may print usage info or a missing-argument message; the goal is simply confirming the binary is executable. If the shell reports command not found, install the plugin per AWS instructions for your OS.

Check whether EC2 appears as a managed node:

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --filters Key=InstanceIds,Values=i-0123456789abcdef0 \
  --query "InstanceInformationList[].{Id:InstanceId,Status:PingStatus,Agent:AgentVersion,Platform:PlatformType}" \
  --output table
~~~

Then start the session:

~~~bash
aws ssm start-session \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0
~~~

You will drop into an interactive shell once all prerequisites are met. Type `exit` in the shell to end the session. Sessions can also be managed via Systems Manager using `ssm:TerminateSession` or `ssm:ResumeSession` per policy.

**Note:** `describe-instance-information` lists managed nodes and their last observed status; it does not guarantee `StartSession` will succeed. An instance may show “Online” while the user lacks IAM permissions or permission for the session document.

### 4.3. Session Manager OS Account

On Linux, Session Manager uses the `ssm-user` account by default, or another account via **Run As**. In many Linux configurations, `ssm-user` has broad sudo privileges. Therefore:

- Treat `ssm:StartSession` as real administrative access, not harmless read-only log viewing.
- Configure Run As, sudoers, and file permissions appropriately for the job function.
- Separate read-only operations roles, troubleshooting roles, and elevated privileges; never grant production shell access to everyone casually.
- On Windows, OS accounts and shells behave differently; do not assume Linux commands apply to Windows sessions.

### 4.4. Sample IAM Policy for Session Starters

The following **illustrative identity-based policy** allows starting a default session only on **one specific EC2 instance** using the default session document created in the account/Region:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartSessionOnSelectedInstance",
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": [
        "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0",
        "arn:aws:ssm:ap-southeast-1:123456789012:document/SSM-SessionManagerRunShell"
      ]
    }
  ]
}
~~~

This is **only part** of an operator's permission set. In practice, you may also need EC2/SSM describe permissions and session management actions (such as `ssm:ResumeSession`, `ssm:TerminateSession`, `ssmmessages:OpenDataChannel` depending on documentation and client method). Use the [official Session Manager IAM sample policies](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html) to combine appropriate statements, restricting resume/terminate permissions to **sessions created by that same identity**.

Never grant `ssm:StartSession` on `Resource="*"` to all users just to bypass access errors. In production, use IAM Identity Center/federation, group- or tag-scoped permissions, bounded session durations, MFA where needed, and proper logging.

## 5. Administering via Session Manager: Logging, Port Forwarding, and Limits

### 5.1. Session Logs and Auditing

For **standard Session Manager shell sessions**, session preferences can be configured to stream output to **Amazon CloudWatch Logs** or **Amazon S3**, with optional KMS encryption. Both IAM permissions and network paths from the instance/logging component must satisfy requirements.

**AWS CloudTrail** records API calls such as `StartSession`, `TerminateSession`, and IAM configuration changes; CloudTrail **does not record shell command contents**. To meet auditing requirements, distinguish three layers:

| Layer | Information | Configuration Needed |
| --- | --- | --- |
| **CloudTrail** | Who called session start/stop APIs, timestamps, API context | Trail/Event data store and suitable retention policy |
| **Session Manager logs** | Standard shell output content, when session type and config support it | Session preferences to CloudWatch Logs/S3, permissions, and endpoints |
| **OS/application logs** | Commands, file edits, sudo usage, app events via host logging | Configure auditd/journald/syslog/agents and protect logs |

**Crucial limitation:** Session Manager **does not provide session content logging** for connections running **SSH over Session Manager** or **port forwarding sessions**. For those flows, you need auditing at the OS/application and network layers. Never claim “SSM records every command” without verifying the session type.

### 5.2. Port Forwarding via Session Manager

Beyond shells, Session Manager can create a TCP tunnel through a managed node. For example, reaching an internal database `db.internal.example:5432` from an admin workstation without making the DB public:

~~~bash
aws ssm start-session \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["db.internal.example"],"portNumber":["5432"],"localPortNumber":["15432"]}'
~~~

Once the tunnel is active, a PostgreSQL client can connect to `localhost:15432` on the admin machine. The managed node must **resolve the DB hostname and be allowed by Security Groups/NACLs/routes to reach port 5432**. The DB endpoint still requires proper database authentication; the tunnel does not grant DB privileges by itself.

This example illustrates the capability. In real environments, restrict who can use port-forwarding session documents, limit session duration, lock down intermediate hosts, and restrict access to sensitive data.

### 5.3. When Session Manager Fits Best

- EC2 instances in **private subnets** needing administration without inbound SSH.
- Organizations wanting centralized access control via IAM and IAM Identity Center.
- Operations teams needing shell access, session timing visibility, and optional standard-shell logging.
- Windows or Linux servers with a compatible SSM Agent that do not require pure SSH workflows.
- Environments aiming to eliminate issuing, rotating, and storing SSH private keys.

Session Manager still has dependencies: the Agent, IAM instance profile, connectivity to AWS Systems Manager, and related AWS services. If all of those fail, Session Manager access may be unavailable, so maintain controlled recovery options.

## 6. EC2 Instance Connect: SSH with Temporary Public Keys

**EC2 Instance Connect (EIC)** combines **IAM** with traditional **SSH** on Linux EC2 instances. When an authorized user calls the `SendSSHPublicKey` API, AWS places the **public key** in instance metadata for a brief window (**60 seconds**). The EIC package on the OS integrates with SSH to check this public key.

Key points to understand:

- **IAM checks permission to push the public key** to the target instance.
- **SSH still authenticates the OS user** and connects to `sshd`. EIC does not turn the Linux shell into an IAM API.
- The temporary key window limits how long you have to **initiate SSH authentication**, not a 60-second cap on the SSH session itself. An established connection stays open until closed per configuration and operational policy.
- TCP connectivity to the SSH port is still required; a successful `SendSSHPublicKey` call **does not mean port 22 is reachable**.

### 6.1. Prerequisites for Public-IP SSH

| Prerequisite | How to Check |
| --- | --- |
| Instance runs **Linux** with an SSH server | AMI supports EIC and `sshd` is running; check distro-specific guidance |
| **EC2 Instance Connect** package/integration | Built into the AMI or installed and configured compatibly; do not assume every custom AMI has it |
| Correct **OS username** | `ec2-user` (many Amazon Linux AMIs), `ubuntu` (many Ubuntu AMIs), or the AMI's actual username |
| Caller IAM permissions | `ec2-instance-connect:SendSSHPublicKey` on the instance; EC2 describe permissions when using the Console |
| Network path to instance | Supported public IPv4/IPv6, VPC route, and Internet Gateway as needed |
| Security Group and NACL | Inbound TCP 22 from allowed sources; NACL allows request and return traffic |
| SSH key | Matching key pair if using a standalone SSH client; private key stays on the admin machine |

**Do not open SSH `0.0.0.0/0` in production just for quick access.** If using direct SSH, restrict admin sources by IP/VPN or use an EIC Endpoint to avoid public SSH exposure.

### 6.2. Method 1: Using the EC2 Console

1. Open **EC2 → Instances** and select the Linux instance.
2. Choose **Connect → EC2 Instance Connect**.
3. Select **Connect using a Public IP** when the instance has an eligible public address.
4. Confirm the **Username** matches the AMI.
5. Click **Connect**; the EC2 console pushes a temporary key and opens a browser-based SSH connection.

If the machine only has a private IPv4 address, choose **EC2 Instance Connect Endpoint** or another supported access path. Console tabs and labels may change as AWS updates the UI.

### 6.3. Method 2: Pushing the Public Key via AWS CLI, Then SSH

The example below applies to Linux/macOS with OpenSSH; the equivalent works on Windows with OpenSSH and appropriate path syntax.

**Step 1 — Generate a local key pair for the lab:**

~~~bash
ssh-keygen -t ed25519 -f ./ec2-lab-key -C ec2-lab
~~~

`ec2-lab-key` holds the **private key**—keep it secret with strict file permissions; `ec2-lab-key.pub` holds the **public key**. Never commit private keys to Git, paste them into tickets, or upload them to servers.

**Step 2 — Push the public key to instance metadata:**

~~~bash
aws ec2-instance-connect send-ssh-public-key \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --instance-os-user ec2-user \
  --ssh-public-key file://./ec2-lab-key.pub
~~~

The API returns success once AWS accepts the request; **initiate SSH promptly afterward** because the public key remains valid only briefly. Some API/CLI contexts may also require passing the Availability Zone; check the syntax of your AWS CLI version.

**Step 3 — Connect to the allowed public address:**

~~~bash
ssh -i ./ec2-lab-key ec2-user@PUBLIC_IPV4_OF_INSTANCE
~~~

`PUBLIC_IPV4_OF_INSTANCE` is a placeholder—replace it with the real address. SSH will still verify the server's **host key**; before accepting a new fingerprint, verify it against host details published via a trusted channel.

If you get `Permission denied (publickey)`, distinguish among: IAM denied `SendSSHPublicKey`, key sent successfully but more than 60 seconds elapsed, wrong OS user, `sshd`/EIC package unsupported, or private key mismatching the sent public key.

### 6.4. Direct Connection Support in the CLI

With **AWS CLI v2** and a compatible OpenSSH environment, you can use the unified EIC SSH command:

~~~bash
aws ec2-instance-connect ssh \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --os-user ec2-user
~~~

The CLI can auto-select the connection type when supported; to explicitly force the private EIC Endpoint path, pass `--connection-type eice`. Do not treat automatic selection as proof that an instance has no public exposure; still inspect routes and Security Groups.

## 7. EC2 Instance Connect Endpoint: SSH to Private EC2

**EC2 Instance Connect Endpoint (EICE)** is a managed TCP proxy/tunnel service that accepts IAM-authorized connections from an admin workstation and reaches EC2 instances inside a VPC over **private IP**. Administrators do not need a VPN, bastion host, or public IP just to open an SSH path in supported scenarios.

EICE places a **network interface** in a subnet you specify. The tunnel through EICE is an IAM-controlled TCP connection; **EICE itself does not log into Linux instead of SSH**. To reach a shell:

1. IAM must permit opening the EICE tunnel via `ec2-instance-connect:OpenTunnel` and related conditional permissions.
2. EICE must reach the EC2 private IP/port via routes, Security Groups, NACLs, and endpoint IP address settings.
3. The target machine needs an SSH server and valid SSH authentication: either a **temporary public key via EIC** or an **already configured SSH key** on the machine.

### 7.1. Sample Network Configuration

~~~mermaid
flowchart LR
    ADMIN["Admin Laptop / IAM role"] -->|"OpenTunnel via AWS service"| EICE["EIC Endpoint ENI<br/>in VPC subnet"]
    EICE -->|"TCP 22 - private IP"| EC2["Linux EC2<br/>10.50.10.25"]
    EC2 -.->|"Can use temporary EIC key"| EIC["EC2 Instance Connect API"]
~~~

*Logical flow only. Verify endpoint support, quotas, subnets, IP types, and routes in your actual VPC. Do not confuse this SSH flow with Session Manager.*

Example:

- EC2 sits in private subnet `10.50.10.0/24` with no public IP.
- An EIC Endpoint is created in an appropriate subnet in the VPC with its own Security Group.
- The endpoint SG allows **egress TCP 22** to EC2.
- The EC2 SG allows **inbound TCP 22** from the endpoint SG, or from the client source matching preserve-client-IP behavior.
- Custom NACLs must permit bidirectional request/response traffic, including ephemeral ports. VPC routing must be valid.
- Operator IAM is scoped to the allowed endpoint and target instances; do not grant endpoint create/modify rights across the entire account when only SSH access is needed.

**Source IP preservation:** when an EIC Endpoint has client IP preservation enabled, the source IP seen by the target host and Security Group requirements can differ from non-preserved mode. Do not blindly apply “allow EC2 inbound from endpoint SG” to every setup; verify endpoint mode, IP type, and AWS documentation.

### 7.2. Accessing EICE with AWS CLI

To SSH from AWS CLI v2 over EICE using AMI EIC support:

~~~bash
aws ec2-instance-connect ssh \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --os-user ec2-user \
  --connection-type eice
~~~

This is convenient when the instance has no public IP. If multiple endpoints/IP types exist or specific routing is needed, pass the appropriate endpoint/instance IP parameters per CLI documentation.

### 7.3. Opening a Tunnel and Using Standalone OpenSSH

EICE also lets you open a TCP tunnel and connect with an existing key in an SSH client. Example in **terminal 1**:

~~~bash
aws ec2-instance-connect open-tunnel \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --local-port 8888
~~~

Once the status shows it is listening locally, in **terminal 2**:

~~~bash
ssh -i ./existing-ssh-key -p 8888 ec2-user@localhost
~~~

Here `existing-ssh-key` is a private key whose public key is **already accepted by the target OS**. If you want to use a temporary EIC key instead, you still need the step that sends the public key via the EIC API. A tunnel alone does not add public keys to `authorized_keys`.

Beyond SSH, EICE can forward certain other TCP connections when supported, such as RDP to Windows via a separate tunnel. However, **EIC public-key login** as described in section 6 is a **Linux SSH** mechanism and does not apply verbatim to Windows.

### 7.4. Limits and Trade-offs

- EICE relies on the AWS service and IAM permissions to establish tunnels; active connections still have maximum duration limits.
- Quotas on endpoint count, concurrent connections, and max duration can affect operations, so check official quotas in your target Region/account.
- EICE carries no additional per-service fee per AWS pricing published at the time of writing, though **inter-AZ data transfer** and other network resources may incur charges; always check current pricing.
- If the endpoint sits in an AZ that loses availability, remote SSH access can be disrupted even if EC2 instances in another AZ keep running. Incident-response designs must account for the endpoint's own failure domain.

## 8. IAM: Separating Key Sending, Tunnel Opening, and EC2 Management

### 8.1. EIC Public Key Permission Example

The following identity-based policy illustrates allowing SSH key delivery only to **one Linux EC2 instance** for OS user `ec2-user`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendKeyToSelectedLinuxInstance",
      "Effect": "Allow",
      "Action": "ec2-instance-connect:SendSSHPublicKey",
      "Resource": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0",
      "Condition": {
        "StringEquals": {
          "ec2:osuser": "ec2-user"
        }
      }
    },
    {
      "Sid": "ViewEC2ForConnection",
      "Effect": "Allow",
      "Action": "ec2:DescribeInstances",
      "Resource": "*"
    }
  ]
}
~~~

Note:

- `ec2:DescribeInstances` generally requires `Resource="*"` due to how the service supports resource-level permissions.
- `ec2:osuser` only restricts the username passed to the EIC API; it does not replace Linux sudo, file, and user permission settings.
- This policy **does not grant** `OpenTunnel` through EICE; instances without public IPs still require an appropriate network path.
- An IAM Allow permits AWS API actions only within its scope and remains subject to SCPs, permissions boundaries, explicit Denies, and related policies.

### 8.2. EIC Endpoint Permissions

To use EICE, callers need `ec2-instance-connect:OpenTunnel` on the target endpoint; access can be scoped by endpoint ARN and service condition keys such as destination, remote port, or max tunnel duration where supported. `SendSSHPublicKey` is a separate permission if temporary SSH keys are used.

For production, separate:

| Role | AWS Permissions to Evaluate | Rationale |
| --- | --- | --- |
| **Session Manager operator** | `ssm:StartSession` scoped by instance/document; own-session management permissions | Controlled login via SSM |
| **EIC operator** | `ec2-instance-connect:SendSSHPublicKey` on designated instances/OS users | Temporary key injection for SSH |
| **EICE operator** | `ec2-instance-connect:OpenTunnel` on approved endpoints | Private TCP tunnel to instances |
| **Network administrator** | Permissions to create/modify EICE, subnets, routes, SGs | Alters connectivity infrastructure; higher blast radius than usage rights |
| **Access administrator** | IAM roles/policies and related boundaries | Controls who can access resources |

Endpoint creation, tunnel opening, and SSH authentication are **distinct control gates**. If a team can modify IAM policies or Security Groups themselves, restrictions placed on them can be bypassed; protect **permission-management rights** as well.

## 9. Which Method Fits Which Scenario?

| Scenario | Option to Evaluate First | Rationale |
| --- | --- | --- |
| Administering Linux EC2 in a private subnet without opening inbound 22 | **Session Manager** | Only needs SSM Agent and outbound connectivity to SSM; IAM-governed |
| Administering Windows EC2 needing shell access and IAM integration | **Session Manager** if Agent prerequisites are met | Does not depend on OpenSSH/Linux users |
| Public Linux EC2 with SSH and EIC package | **EC2 Instance Connect** | Leverages SSH, temporary public keys, and IAM controls |
| Private Linux EC2 where the team still needs OpenSSH workflows | **EC2 Instance Connect Endpoint** | TCP tunnel over private IP without exposing SSH to the Internet |
| Forwarding an internal TCP connection for investigation | Session Manager **port forwarding** or EICE tunnel per policy | Inspect protocol, network path, and session auditing |
| Capturing shell session contents for auditing | **Standard Session Manager shell** with logging enabled | Can export logs to S3/CloudWatch Logs; check session-type limits |
| Specialized AMI without SSM Agent but with SSH configured | EIC/EICE if AMI supports it, or SSH via EICE with existing keys | Avoids dependency on SSM Agent |
| Troubleshooting when SSM Agent is offline | Approved fallback admin path: EICE/SSH, EC2 Serial Console if supported, recovery procedures | SSM channel may be unusable when Agent/SSM networking fails |

**Design guidance:** for typical AWS workloads, evaluate **Session Manager** as the primary admin path since it eliminates inbound SSH and key management overhead. Use **EICE** when teams require SSH workflows or need an IAM-gated fallback path. Both still require proper OS privilege control, IAM scoping, and recovery planning.

## 10. Real-World Scenario: API EC2 Instances in Private Subnets

Suppose an e-commerce platform runs a public ALB and application EC2 instances across two private subnets in two AZs:

~~~text
VPC 10.60.0.0/16
├── AZ A
│   ├── public-a          : ALB, NAT Gateway A (if needed)
│   └── app-private-a     : EC2 app A, no public IP
└── AZ B
    ├── public-b          : ALB, NAT Gateway B (if needed)
    └── app-private-b     : EC2 app B, no public IP

SSM interface VPC endpoints: ssm, ssmmessages (and additional endpoints if needed)
EIC Endpoint: optional addition if SSH access to private instances is desired
~~~

### 10.1. Option A — Managing via Session Manager

1. Each app EC2 instance has an instance profile with appropriate SSM permissions.
2. SSM Agent is installed, running, and showing online.
3. Private subnets have NAT/egress or interface endpoints supporting HTTPS 443 from instances.
4. Operator IAM roles have `ssm:StartSession` scoped to matching instances and documents.
5. EC2 Security Groups allow inbound **only from the ALB to the application port**; no inbound 22 is needed.
6. Enable CloudTrail, configure standard-shell session logs if required, and enforce log retention and read access controls.

If AZ A fails, app B can keep serving traffic if capacity and dependencies are ready. To keep managing app B, ensure app B's path to SSM **does not depend solely on a NAT/endpoint in AZ A**. If a single shared NAT Gateway sits in AZ A, losing AZ A can sever app B's outbound SSM channel; per-AZ NATs or properly configured multi-AZ VPC endpoints mitigate this risk.

### 10.2. Option B — SSH Through an EIC Endpoint

1. Create an EIC Endpoint in the VPC in a subnet matching IP type and routing requirements.
2. Configure IAM to allow opening tunnels on that endpoint; if using temporary public keys, also grant `SendSSHPublicKey` on target EC2 instances.
3. EC2 runs an SSH server; if using temporary EIC keys, the AMI must include the EIC package/integration.
4. Instance SG allows TCP 22 from the actual tunnel source; endpoint SG allows egress; NACLs allow bidirectional traffic.
5. Operators connect with `aws ec2-instance-connect ssh --connection-type eice`.
6. Monitor CloudTrail and OS-level auditing, since standard Session Manager shell content logging is not present by default.

A single-AZ endpoint can become an operational dependency. In HA designs, document how operators recover if the endpoint fails or needs replacement, rather than confusing endpoint reachability with application availability.

## 11. Security When Opening Production Access

**Server administration is a privileged action.** Whether over Session Manager or SSH, anyone inside a shell can read files, inspect environment variables, or call AWS APIs using the **instance role** within the EC2 instance's permissions.

Key controls:

1. **Individual identity:** prefer federated login/IAM Identity Center and role-based access over shared static access keys.
2. **Least privilege:** scope `StartSession`, `SendSSHPublicKey`, and `OpenTunnel` by instance, endpoint, account, Region, tags, and OS user where condition keys exist.
3. **OS privilege management:** configure sudo/Run As/Linux groups carefully; an IAM-authorized session is not automatically a read-only shell.
4. **Avoid public SSH unless necessary:** keep EC2 on private IPs with inbound 22 closed when using Session Manager, or restrict strictly to EICE sources.
5. **Avoid careless private key storage:** if SSH keys remain in use, protect them, rotate as needed, and never commit them to repositories.
6. **Appropriate auditing:** CloudTrail for APIs, Session Manager shell logs where supported, and OS auditing for SSH/port-forwarding.
7. **Emergency access controls:** time-bound, approved, monitored break-glass roles; rehearse recovery so you do not lose access if the Agent/SSM fails.
8. **Encryption and data handling:** TLS, encrypted logs, strict log read permissions, and prohibiting copying production secrets/DB dumps onto personal laptops.
9. **Monitor privilege changes:** alert on IAM policy edits, SSH security group changes, EICE creation, or anomalous sessions.
10. **Software updates:** patch SSM Agent, SSH server, and AMIs systematically, testing compatibility before rollout.

**A classic least-privilege violation:** a user who only needs to read logs is granted `ssm:StartSession` on EC2 where the session allows `sudo su`. On the host they can read secrets or alter files. In such cases, granting tightly scoped CloudWatch Logs read permissions is far more appropriate than shell access.

## 12. Troubleshooting Access Issues

### 12.1. Session Manager Reports `TargetNotConnected` or Connect Button Unavailable

Check in order:

1. **Right account/Region/instance ID?** The instance must run in the Region targeted by the CLI/Console.
2. **SSM Agent online?** Look for `PingStatus=Online`. If offline, check agent service status, version, and startup logs via a fallback access path.
3. **Instance profile?** Is an IAM role attached as an EC2 instance profile with required SSM permissions?
4. **Networking?** Can the agent reach `ssm`/`ssmmessages` endpoints via NAT or VPC interface endpoints? Are DNS, endpoint SG TCP 443, and NACLs correct?
5. **Private endpoint policy?** Did a restrictive policy accidentally block agent API calls?
6. **User IAM?** Are `StartSession` and the session document allowed without explicit Denies, permission boundaries, or SCP blocks?
7. **Session Manager plugin?** Is the plugin installed on the local machine when using AWS CLI?

A read-only command to inspect connection status:

~~~bash
aws ssm get-connection-status \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0
~~~

This status only reflects connectivity recorded by the service at query time; investigate further if session requests still fail.

### 12.2. Session Manager Reports `AccessDenied`

Distinguish two principals:

- **Operator:** is `ssm:StartSession` permitted on both the instance and the document? Are resume/terminate/`ssmmessages` permissions present where required by the client? Is there an explicit Deny in IAM/SCP?
- **EC2 instance role:** does it have the SSM Agent permissions to register/connect the communication channel? This is a different principal from the operator.

Do not “fix” errors by attaching `AdministratorAccess` or opening all of `ssm:*`. Inspect CloudTrail/API errors and add only the exact required action/resource.

### 12.3. EIC Reports `SendSSHPublicKey AccessDenied`

- Does the caller's IAM policy grant `ec2-instance-connect:SendSSHPublicKey` on the **instance ARN**?
- Does the `ec2:osuser` condition match the username passed?
- Are the instance ID/Region/AZ, SCPs, and boundaries aligned?
- Does the caller have the EC2 view permissions required by the Console?

### 12.4. SSH `Permission denied (publickey)`

The key-push API may have succeeded while SSH authentication failed because:

- More than **60 seconds** elapsed before starting authentication with the temporary key.
- Wrong OS user (for example, using `ec2-user` on an AMI that only has `ubuntu`).
- The EIC package or `sshd` integration is missing or broken on the AMI.
- The SSH client used a different private key from the public key that was pushed.
- Misconfigured `sshd`, home directory permissions, or authorized keys settings.

Inspect authentication with verbose SSH (never share secrets from output):

~~~bash
ssh -v -i ./ec2-lab-key ec2-user@PUBLIC_IPV4_OF_INSTANCE
~~~

### 12.5. SSH Timeout or `Connection refused`

| Symptom | Primary Suspects | How to Check |
| --- | --- | --- |
| **Timeout** | Routes, public IP, IGW, SG inbound 22, NACL, VPN, or EICE path | Trace the TCP path and inspect SGs/NACLs in both directions |
| **Connection refused** | Reached host/address, but no SSH listener on port or rejected by host layer | Check `sshd`, listening port, OS firewall, and instance health |
| **Host key changed** | IP/host changed, instance replaced, or spoofing risk | Verify host key via a trusted channel before editing `known_hosts` |
| **EICE OpenTunnel denied** | Missing `ec2-instance-connect:OpenTunnel` or endpoint/port condition mismatch | Check IAM and CloudTrail for `OpenTunnel` |
| **EICE tunnel opens but SSH fails** | Wrong source IP/SG/port 22/SSH key/OS user | Check endpoint → instance networking and SSH auth separately |

**Avoid dangerous shortcuts:** never disable host key verification, never open port 22 to the entire Internet, and never delete Security Groups/NACLs just to test connectivity.

## 13. Read-Only Observability with AWS CLI

The following examples only read metadata in Region `ap-southeast-1` and require appropriate IAM permissions. Resource names and IDs are placeholders.

### 13.1. Inspect EC2 Instance and Addresses

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query "Reservations[].Instances[].{Id:InstanceId,State:State.Name,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,Subnet:SubnetId,Profile:IamInstanceProfile.Arn}" \
  --output table
~~~

Without a public IP, an instance **is not eligible** for direct SSH over public IPv4. However, it can still be reached via Session Manager or EICE if each method's prerequisites are met.

### 13.2. Inspect Managed Node Status

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --filters Key=InstanceIds,Values=i-0123456789abcdef0 \
  --query "InstanceInformationList[].{Id:InstanceId,Ping:PingStatus,Agent:AgentVersion,LastPing:LastPingDateTime}" \
  --output table
~~~

### 13.3. Inspect EIC Endpoints in the VPC

~~~bash
aws ec2 describe-instance-connect-endpoints \
  --region ap-southeast-1 \
  --query "InstanceConnectEndpoints[].{Id:InstanceConnectEndpointId,State:State,Vpc:VpcId,Subnet:SubnetId}" \
  --output table
~~~

If the account/Region has no endpoints yet, the result may be empty. Having an endpoint does not guarantee IAM and TCP 22 to the instance are properly configured.

### 13.4. Inspect Active Session Manager Sessions

~~~bash
aws ssm describe-sessions \
  --region ap-southeast-1 \
  --state Active \
  --query "Sessions[].{Id:SessionId,Target:Target,Owner:Owner,Start:StartDate}" \
  --output table
~~~

The session list depends on the caller's describe permissions. Session metadata is sensitive administrative data and must be protected, especially in products containing operator details.

## 14. Practice Exercises and Self-Check Questions

### Exercise 1 — Choosing a Connection Method

Given three instances:

| Instance | Status | Goal |
| --- | --- | --- |
| **EC2 A** | Linux, private subnet, online in Systems Manager | Check app logs without opening inbound SSH |
| **EC2 B** | Linux, private subnet, no SSM Agent, SSH configured | Administer with OpenSSH from a laptop |
| **EC2 C** | Public Linux, EIC-capable, user IAM allows only sending public keys | Short-lived key-based SSH access |

**Hints:**

1. EC2 A: **Session Manager** if permissions and network paths are in place.
2. EC2 B: **EIC Endpoint + an SSH key already accepted by the host** or recover by installing the Agent; EICE tunnels do not require SSM Agent.
3. EC2 C: **EC2 Instance Connect over public IP**, with restricted SGs/routes and verified OS username.

### Exercise 2 — Finding the Network Misconfiguration

A private EC2 instance has no NAT, yet two interface endpoints (`ssm` and `ssmmessages`) were created. The endpoint SG allows inbound TCP 443 only from the administrator's Internet IP address. EC2 has the SSM Agent and a valid IAM role, yet `PingStatus=ConnectionLost`.

**Question:** What is wrong with the endpoint SG rule?

**Hint:** The caller reaching the endpoint is the **EC2 instance inside the VPC**. The endpoint SG must allow inbound TCP 443 from the EC2 SG or appropriate private CIDR; allowing the admin's Internet laptop IP does not help the Agent connect to the endpoint. Also verify DNS, endpoint policies, and NACLs.

### Exercise 3 — Explaining Two Different Failures

An operator calls `SendSSHPublicKey` successfully, yet SSH to `10.50.10.25:22` from the Internet times out. Next, they create an EICE and open a tunnel successfully, yet SSH returns `Permission denied (publickey)`.

**Suggested answer:** Direct connection to a private IPv4 address has no Internet route, causing the timeout. EICE resolves the **TCP path**, whereas `publickey` belongs to the **SSH authentication** layer; inspect the pushed/expired public key, OS username, private key, and EIC package.

### Exercise 4 — Reading a Policy and Assessing Risk

Suppose role `SupportReadOnly` is granted:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": "*"
    }
  ]
}
~~~

**Question:** Does the role name accurately reflect the capabilities granted? What is the risk if instances hold database credentials and secret files?

**Hint:** Naming a role “ReadOnly” does not make a shell read-only. `Resource="*"` is overly broad when paired with related permissions/session documents; a session may run as a privileged OS user, reading secrets or modifying files. Scope by instance/document, restrict Run As/sudo, and grant IAM-scoped CloudWatch Logs read access when the actual need is only reading logs.

### Exercise 5 — Designing a Resilient Management Path

An application runs across two AZs with private EC2 instances in both AZs. Normally admins use Session Manager via a single NAT Gateway in AZ A. Analyze what happens if AZ A goes down, and propose how to keep operating EC2 in AZ B.

**Hint:** EC2 B may continue running while its outbound SSM path breaks because NAT-A is down. Use per-AZ NAT Gateways or deploy required SSM interface endpoints across multiple AZs with proper networking/DNS/SGs. Test the fallback path while one zone is isolated.

## 15. Summary

Three core concepts to remember:

1. **Session Manager** brokers sessions via the **SSM Agent and Systems Manager**, typically needing no public IP or inbound port 22. Check IAM for both operator and instance, port 443 connectivity, and session preferences.
2. **EC2 Instance Connect** pushes a **temporary SSH public key** via an IAM-authorized API; afterward you still need an **SSH server, the right OS user, and a TCP path to EC2**. The 60-second window governs using the public key to initiate authentication, not the lifetime of an already-established SSH session.
3. **EC2 Instance Connect Endpoint** provides a **private TCP path to private instances**. It is not SSM Agent, does not install SSH keys on its own, and does not record full SSH session contents automatically.

Good production EC2 access design starts from **operational requirements** before picking a connection mechanism. IAM, networking, OS privileges, auditing, resilience, and cost must all be evaluated together—and verified by testing along the exact intended connection path.

### Official AWS Documentation

- [AWS Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html) — overview and session administration.
- [Set up Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started.html) — preparing IAM, SSM Agent, networking, and clients.
- [Verify or add instance permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html) — `AmazonSSMManagedInstanceCore` and instance profiles.
- [Sample IAM policies for Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html) — permissions for users, managed nodes, sessions, and session documents.
- [VPC endpoints for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html) — `ssm`, `ssmmessages`, related endpoints, and network prerequisites.
- [Session Manager logging](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-auditing.html) — capturing and auditing shell output, session-type limits.
- [EC2 Instance Connect tutorial](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-tutorial.html) — temporary SSH keys and IAM permissions.
- [Connect using EC2 Instance Connect](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-methods.html) — Console, CLI, and OpenSSH.
- [EC2 Instance Connect Endpoint](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-with-ec2-instance-connect-endpoint.html) — tunneling mechanism, permissions, quotas, and pricing.
- [Connect through EIC Endpoint](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-using-eice.html) — private IPv4/IPv6 connections with AWS CLI and OpenSSH.
- [Troubleshooting SSM Agent](https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-ssm-agent.html) — inspecting Agent, DNS, IAM, and network paths.
