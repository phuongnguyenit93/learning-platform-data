# Systems Manager Managed Nodes and Connectivity Prerequisites

An operations team has EC2 instances running Java applications in private subnets, servers in an on-premises datacenter, and VMs on another cloud. The team wants to use AWS Systems Manager to check inventory, run commands, patch operating systems, and access servers via Session Manager without opening inbound SSH/RDP. To do that, each machine must become a **managed node** and maintain outbound connectivity to Systems Manager.

An instance in the EC2 `running` state is not guaranteed to appear in Fleet Manager. Systems Manager requires a working SSM Agent on a supported operating system, an IAM credentials source with appropriate permissions, and a network path to the service endpoints. For EC2, you can use an instance profile or Default Host Management Configuration (DHMC). For non-EC2 machines, you typically use a hybrid activation along with an IAM service role.

This lesson belongs to the **Systems Manager Operations** chapter of the **CLOUD_PROVIDERS_AWS** module. It focuses on managed node registration prerequisites, SSM Agent, IAM identity, DHMC, hybrid activation, endpoint connectivity, Session Manager, and the troubleshooting workflow for offline nodes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what a managed node is and which types of machines Systems Manager can manage.
2. State the three foundational conditions for a node to appear and remain in the managed state.
3. Verify supported operating systems and SSM Agent versions.
4. Distinguish between an instance profile, DHMC, and hybrid activation.
5. Choose the appropriate IAM policy for an EC2 managed node.
6. Explain the role of the IAM service role in hybrid/multicloud environments.
7. Recognize how SSM Agent retrieves credentials and errors caused by conflicting credential sources.
8. Identify required SSM endpoints and network ports.
9. Design connectivity via NAT/Internet egress or AWS PrivateLink.
10. Explain DNS, security group, network ACL, and proxy requirements.
11. Distinguish general node management requirements from Session Manager-specific requirements.
12. Check agent status, registration, and connection state.
13. Use `ssm-cli` to diagnose issues.
14. Read SSM Agent logs and resolve common errors.
15. Design secure onboarding, agent updates, and managed-node fleet operations.

## 2. What Is a Managed Node?

A **managed node** is a machine configured so that AWS Systems Manager can identify, communicate with, and execute management operations on it. A managed node is not just an EC2 instance. Machine types can include EC2 instances, physical servers in an on-premises datacenter, VMs on internal virtualization platforms or other clouds, and certain edge devices/AWS IoT Greengrass core devices under supported models.

Non-EC2 machines are typically managed through hybrid and multicloud activations. For macOS, Systems Manager supports EC2 Mac instances; not all non-EC2 macOS hosts are supported.

A managed node can use many Systems Manager capabilities:

| Capability | Example |
|---|---|
| Session Manager | Shell access or port forwarding without opening inbound SSH/RDP |
| Run Command | Run commands or SSM documents across a group of nodes |
| State Manager | Maintain configuration and execute associations on a schedule |
| Patch Manager | Scan and install patches according to a baseline |
| Inventory | Collect OS, software, network, and metadata details |
| Distributor | Distribute packages/agents |
| Fleet Manager | View and manage nodes centrally |

Not every feature supports every operating system or machine type. Before designing a fleet, check the OS support matrix and the specific requirements of each capability.

## 3. Three Foundational Conditions for a Managed Node

For a machine to be recognized by Systems Manager and remain in a managed state, three conditions must be met:

1. **SSM Agent is installed and running** on a supported operating system.
2. **The node has appropriate IAM credentials and permissions** to communicate with Systems Manager.
3. **SSM Agent can connect to the service endpoints** in the correct AWS Region.

    +-----------------------------+
    |  Operating system supported |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | SSM Agent installed/running |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | IAM credentials + permissions|
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | DNS + HTTPS endpoint access |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | Systems Manager managed node|
    +-----------------------------+

Missing any single condition can cause an instance to run normally in EC2 while not appearing in Managed nodes, or appear and then transition to `Connection Lost`. AWS confirms node status using a periodic health signal; troubleshooting documentation describes a roughly five-minute cycle.

## 4. Operating Systems and AMIs

Systems Manager only supports the list of OS versions and CPU architectures published by AWS. Support follows the OS vendor lifecycle:

- Not every OS supported by its vendor is supported by Systems Manager.
- When an OS version reaches vendor end of life (EOL), AWS Systems Manager support for that version also ends per documentation policy.
- Patch Manager has its own support matrix; an OS being managed does not mean all patch operations are supported.
- Check the x86_64/ARM64 architecture and specific OS version before choosing an AMI or building a custom image.

Commonly supported OSes include Amazon Linux 2/2023, Ubuntu Server, RHEL, Debian, SUSE, and Windows Server. The list and minor versions change over time; use the Supported operating systems and machine types page as the authoritative source.

Some AWS-managed AMIs have SSM Agent preinstalled. For a custom AMI:

1. Install the correct SSM Agent package/architecture.
2. Enable the service at boot.
3. Do not bake activation codes or static credentials into the image.
4. Verify that the agent does not retain the registration identity of the source image.
5. Update the agent on a schedule.
6. Test the image in the target account/Region/VPC before releasing it.

## 5. SSM Agent

SSM Agent is the software running on a managed node. The agent receives requests from Systems Manager, executes permitted operations, and sends status/results back to AWS. The agent initiates outbound communication over HTTPS and message channels; there is no need to open inbound management ports for AWS to SSH into the machine.

Main responsibilities:

- Register the node and send status information.
- Receive Run Command, Session Manager, and SSM document operations.
- Execute commands with the OS privileges of the agent/document worker.
- Send execution status, command output, and health information.
- Maintain message channels for session and command orchestration.

On Linux/macOS, the agent usually runs as root. On Windows, the agent runs as a Windows service with corresponding system privileges. Therefore, granting a user permission to run an SSM document can be equivalent to granting administrative access on the machine; IAM and document access must be strictly controlled.

## 6. Checking SSM Agent

Linux with systemd:

    sudo systemctl status amazon-ssm-agent
    sudo systemctl enable amazon-ssm-agent
    sudo systemctl start amazon-ssm-agent

Some Ubuntu images install the agent as a Snap package:

    sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service
    sudo snap start amazon-ssm-agent

Windows Server, PowerShell as Administrator:

    Get-Service AmazonSSMAgent
    Start-Service AmazonSSMAgent

The service name may vary by OS/package. Do not restart the agent in bulk without assessing the impact on active Session Manager sessions or running Run Commands.

### 6.1. Agent Versions and Feature Requirements

| Capability | Minimum SSM Agent Version |
|---|---:|
| Basic Session Manager shell | 2.3.68.0 |
| Encrypt session data with AWS KMS | 2.3.539.0 |
| Shell profiles | 3.0.161.0 |
| Port forwarding or SSH over Session Manager | 3.0.222.0 |
| Stream session data to CloudWatch Logs | 3.0.284.0 |
| DHMC for EC2 | 3.2.582.0 |

These are specific feature thresholds, not a recommendation to keep the agent on old versions. Prefer current AWS-supported agent versions.

## 7. IAM Credentials via EC2 Instance Profile

SSM Agent needs AWS credentials to call Systems Manager APIs. For EC2, the traditional method is attaching an IAM role via an **instance profile**.

    EC2 instance
       |
       | Instance Metadata Service (IMDS)
       v
    IAM instance profile
       |
       | Temporary role credentials
       v
    SSM Agent
       |
       | HTTPS API / message channels
       v
    AWS Systems Manager

The common policy for an EC2 managed node is the AWS managed policy `AmazonSSMManagedInstanceCore`. This policy provides the core set of permissions for SSM Agent to register and communicate with Systems Manager. If you use a custom policy, make sure it includes sufficient actions for the enabled capabilities; a policy that is only enough for registration may not suffice for Session Manager, logging, inventory, or additional integrations.

CloudFormation example creating a role and instance profile:

    Resources:
      ManagedNodeRole:
        Type: AWS::IAM::Role
        Properties:
          AssumeRolePolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          ManagedPolicyArns:
            - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

      ManagedNodeInstanceProfile:
        Type: AWS::IAM::InstanceProfile
        Properties:
          Roles:
            - !Ref ManagedNodeRole

The EC2 instance must reference the instance profile in the `IamInstanceProfile` property. Do not place IAM user access keys in the agent configuration file.

## 8. Default Host Management Configuration (DHMC)

**Default Host Management Configuration** allows Systems Manager to automatically provide an IAM role at the account/Region level to manage EC2 instances. This reduces the need to create and attach a separate instance profile for every EC2 instance.

Key requirements:

- DHMC must be enabled separately in each AWS Region to be managed.
- The EC2 instance must use IMDSv2.
- SSM Agent must be version 3.2.582.0 or later.
- The role selected for DHMC must have an appropriate trust relationship with Systems Manager.
- Enabling the configuration can take up to about 30 minutes before instances start using the role's credentials.

DHMC uses the default role `AWSSystemsManagerDefaultEC2InstanceManagementRole` or a specified custom role. The associated default policy is `AmazonSSMManagedEC2InstanceDefaultPolicy`.

### 8.1. DHMC and Instance Profiles

If an EC2 instance already has an instance profile and its policy allows `ssm:UpdateInstanceInformation`, SSM Agent will try to use credentials from the instance profile first. In that case, the agent will not switch to credentials provided by DHMC.

If you want the node to use DHMC, review the current instance profile and remove the `ssm:UpdateInstanceInformation` permission from that profile per AWS guidance. Do not delete the entire instance profile if applications on the EC2 instance still need other AWS permissions.

### 8.2. IMDSv2

DHMC requires IMDSv2. IMDSv2 uses a session token when accessing the metadata endpoint, reducing the risk of certain types of SSRF and credential exposure.

Check metadata options:

    aws ec2 describe-instances \
      --instance-ids i-0123456789abcdef0 \
      --query 'Reservations[0].Instances[0].MetadataOptions'

To require IMDSv2 in a launch template:

    MetadataOptions:
      HttpTokens: required

Do not block SSM Agent from accessing the metadata endpoint `169.254.169.254`. If using a proxy, configure bypass/`no_proxy` for the metadata address.

## 9. Hybrid Activation for Non-EC2 Machines

For on-premises servers, VMs on other clouds, or supported edge devices, you cannot attach an EC2 instance profile. Instead, create a **hybrid activation** in the account and Region where you want to manage the node.

    Administrator
       |
       | Create activation
       v
    Activation ID + Activation Code
       |
       | Install/configure SSM Agent on non-EC2 host
       v
    SSM Agent registers with Systems Manager
       |
       v
    Managed node ID: mi-xxxxxxxxxxxxxxxxx

An activation includes an Activation ID, Activation Code, IAM service role, registration limit, expiration date, and optional tags/default instance name. After registration, a non-EC2 managed node typically has an ID starting with `mi-`.

### 9.1. IAM Service Role

An IAM service role is used for hybrid managed nodes. Its trust policy must allow the service principal:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "ssm.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }

The role needs a policy allowing the appropriate Systems Manager operations, usually starting from `AmazonSSMManagedInstanceCore` and adding only the permissions actually needed for specific capabilities.

Do not use an EC2 instance profile role in place of a hybrid service role. The two role types have different trust relationships and credential distribution mechanisms.

### 9.2. Protecting the Activation Code

The activation code and activation ID grant the ability to register nodes into the account/Region. Store the code in a secrets manager/protected administrative channel; do not commit it to Git, images, or shared scripts; restrict the registration limit; set a short expiry matching the rollout window; do not print the code to logs; and deregister nodes that are no longer managed.

An expired activation only prevents new nodes from registering with that activation; already-registered nodes remain managed until they are deregistered.

### 9.3. Hybrid Changes in 2026

An activation code has a maximum registration lifetime of 30 days; the default is typically 24 hours if unspecified. If you need to register additional machines after an activation expires, create a new activation.

Per current documentation:

- The legacy Hybrid Activations page in the console is scheduled for deprecation on December 31, 2026; existing activations can still be managed via APIs and the unified Systems Manager console.
- The Advanced-instances tier was removed effective June 30, 2026.
- Session Manager and Run Command on hybrid managed nodes moved to pay-as-you-go pricing effective September 30, 2026.

When designing a hybrid fleet in late 2026, use the unified console/API and check current AWS Systems Manager pricing for the Region and node type.

## 10. Credential Sources and Credential Errors

SSM Agent needs to obtain credentials from the proper source. On Linux/macOS, the agent usually runs as root, so the environment variables or credentials file that the agent sees belong to root, not a regular login user.

Several credential sources may exist in the environment: environment variables, shared credentials files, an ECS task role in certain container environments, an EC2 instance profile, and a DHMC-provided role.

Do not mix static credentials with an instance role. If the agent reads an old credential source by mistake or lacks permissions, the node may fail to register even when the instance profile is correct.

Checklist:

1. Verify the instance profile is properly attached to the instance.
2. Verify the role trust principal is `ec2.amazonaws.com`.
3. Verify the policy contains the required permissions.
4. Verify IMDS is reachable.
5. Verify no proxy is blocking IMDS.
6. Verify root's environment/credentials file does not contain stale credentials.
7. If using DHMC, verify the instance profile does not retain `ssm:UpdateInstanceInformation`, which would cause the wrong source to take precedence.

## 11. Endpoint Connectivity: What Does SSM Agent Call?

SSM Agent initiates outbound HTTPS connections to endpoints in the node's Region. The main endpoints are:

| Endpoint | Role |
|---|---|
| `ssm.<region>.amazonaws.com` | Systems Manager API operations |
| `ssmmessages.<region>.amazonaws.com` | Message Gateway, Session Manager channels, and agent communication |
| `ec2messages.<region>.amazonaws.com` | Message Delivery for certain older agents/Regions |

SSM Agent version 3.3.40.0 and later uses `ssmmessages` instead of `ec2messages` when that endpoint is available. Some newer AWS Regions do not provide `ec2messages`. For older agents or older Regions, `ec2messages` may still be needed.

Do not hardcode an endpoint list copied from one Region across all Regions. Verify service availability and the running agent version.

### 11.1. Ports and Connection Direction

Core network requirements:

- The node must allow outbound TCP 443 to the endpoints.
- The node's security group must allow the corresponding egress.
- If using interface VPC endpoints, the endpoint security group must allow inbound TCP 443 from the node security group or appropriate CIDR.
- Network ACLs must allow both request and response traffic, including ephemeral return ports according to the subnet design.
- DNS must resolve the endpoints to the right addresses.
- The TLS certificate chain must be trusted by the OS/agent.

Normally, there is no need to open inbound TCP 22 (SSH) or 3389 (RDP) to use Session Manager. The operator calls Systems Manager APIs; the agent maintains the outbound channel, and session data flows through the message service.

## 12. Connecting from a Private Subnet

### 12.1. Via NAT Gateway or Internet Egress

A private subnet can use a NAT Gateway to allow outbound HTTPS to public AWS service endpoints. Instances do not need a public IP if the route table, NAT, security group, and NACL permit it.

The advantage is ease of use across many AWS public endpoints. The limitation is that traffic traverses NAT, which can incur costs and create an egress path dependency.

### 12.2. Via AWS PrivateLink

If you do not want nodes to traverse the Internet/NAT, create interface VPC endpoints in the VPC:

    com.amazonaws.<region>.ssm
    com.amazonaws.<region>.ssmmessages
    com.amazonaws.<region>.ec2messages

Only create `ec2messages` when Region/agent compatibility requires it and the endpoint is available.

You must verify Private DNS, VPC DNS support/hostnames, endpoint ENI/subnet/AZ, endpoint security group inbound 443 from managed nodes, node security group egress 443, endpoint policy, and DNS/proxy/firewall rules. PrivateLink endpoints allow private managed nodes to connect to Systems Manager without needing an Internet Gateway or NAT for that traffic.

### 12.3. Additional Endpoints for Optional Features

| Feature | Potentially Required Endpoint/Service |
|---|---|
| Download packages/documents/scripts from S3 | Amazon S3 |
| Write session/command output to CloudWatch Logs | CloudWatch Logs |
| Write session/command output to S3 | Amazon S3 |
| Encrypt session data with a customer managed key | AWS KMS |
| CloudWatch Agent/metrics monitoring | CloudWatch Monitoring |
| Other EC2 operations inside documents | EC2 API |

These are feature/document-dependent requirements. Do not create every endpoint just because SSM Agent needs the core endpoints; match endpoints to actual fleet operations.

## 13. DNS, Proxy, and TLS

If DNS cannot resolve `ssm.<region>.amazonaws.com` or `ssmmessages.<region>.amazonaws.com`, the agent cannot open a channel.

With PrivateLink, check Private DNS, VPC DNS support/hostnames, resolver rules, DNS firewall, and the node's DNS resolver. Use `nslookup`/`dig` or an equivalent tool to verify hostnames.

If nodes go through an HTTP proxy, configure the proxy for SSM Agent; ensure the proxy allows HTTPS CONNECT to SSM endpoints; bypass `169.254.169.254` for IMDS; and check proxy credentials and the TLS trust chain. A TLS inspection proxy, custom CA, or incomplete certificate store can cause handshake failures.

Do not disable certificate verification as a workaround for TLS errors. Fix the trust store or proxy policy according to security standards.

## 14. Session Manager Has Its Own Requirements

An online managed node is not automatically ready for every type of Session Manager session. Beyond node management prerequisites, you need:

- An SSM Agent version compatible with the session type.
- `ssmmessages` connectivity and endpoint permissions.
- An operator IAM policy allowing `ssm:StartSession` on the target/document.
- Session preferences/KMS/S3/CloudWatch Logs if logging/encryption is enabled.
- The Session Manager plugin on the operator's machine if using the AWS CLI.
- An appropriate OS account and shell on the managed node.

Session Manager typically uses the `ssm-user` account. The agent can create this account when the first session starts; the account usually has administrative/root privileges. Organizations must review `ssm-user` privileges, restrict who can call `StartSession`, and log sessions per audit requirements.

Port forwarding or SSH over Session Manager requires agent version 3.0.222.0 or later and does not require opening an inbound SSH port on the node. If session logging to S3/CloudWatch Logs is enabled, the node and/or service need the corresponding network/IAM permissions. Encrypting session data with KMS also has separate agent version and KMS permission requirements.

## 15. Separating Node and Operator IAM Permissions

There are two distinct principals:

| Principal | Main Permissions |
|---|---|
| Managed node IAM role | Allows SSM Agent to register, report status, receive/complete operations, and use configured capabilities |
| Operator IAM identity | Allows viewing nodes, `StartSession`, `SendCommand`, `TerminateSession`, managing documents, and viewing output as permitted |

Attaching `AmazonSSMManagedInstanceCore` to an EC2 instance role does not automatically grant all IAM users access to the machine. Conversely, granting `ssm:StartSession` to an operator does not help a node connect if the agent lacks credentials or network access.

For operators, scope `ssm:StartSession` by instance ARN/tag and allowed session documents; scope `ssm:SendCommand` by document and target; grant `ssm:TerminateSession` for sessions within the appropriate scope; and separately review `ssm:UpdateInstanceInformation`, `ssm:UpdateServiceSetting`, `iam:PassRole`, and activation administration permissions. Use CloudTrail and session logging for auditing.

Do not grant `ssm:*` on all resources merely to simplify onboarding.

## 16. Checking Nodes from the AWS CLI

List managed node information by instance ID:

    aws ssm describe-instance-information \
      --filters "Key=InstanceIds,Values=i-0123456789abcdef0" \
      --region ap-southeast-1

Fields to inspect include `InstanceId`, `PingStatus`, `LastPingDateTime`, `AgentVersion`, `PlatformType`/`PlatformName`/`PlatformVersion`, and `ResourceType`.

Check connection status:

    aws ssm get-connection-status \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

For a non-EC2 hybrid node, use the managed node ID in `mi-...` format as the target.

To start a session once the node is online:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

The AWS CLI requires the Session Manager plugin installed on the operator's machine to open an interactive session. `describe-instance-information` is the inventory/listing check; `get-connection-status` checks the current connection state.

## 17. Using ssm-cli for On-Node Diagnostics

SSM Agent version 3.1.501.0 and later includes `ssm-cli`. This tool checks the prerequisites needed for a node to be managed by Systems Manager.

Linux/macOS:

    ssm-cli get-diagnostics --output table

Windows Server, run from the agent directory:

    cd "C:\Program Files\Amazon\SSM"
    .\ssm-cli.exe get-diagnostics --output table

Diagnostic checks can include EC2 Instance Metadata Service, hybrid instance registration, connectivity to `ssm`, `ec2messages`, `ssmmessages`, and optional endpoints such as S3, KMS, Logs, and Monitoring.

Checks for S3/KMS/Logs/Monitoring apply to optional features; a failure on a secondary endpoint does not necessarily mean managed-node registration failed. Read the notes for each check and compare against the features the node actually uses.

## 18. Inspecting SSM Agent Logs

SSM Agent logs registration, execution, commands, scheduled actions, session workers, and connection errors.

Linux/macOS:

    /var/log/amazon/ssm/amazon-ssm-agent.log
    /var/log/amazon/ssm/errors.log

Windows Server:

    %PROGRAMDATA%\Amazon\SSM\Logs\amazon-ssm-agent.log
    %PROGRAMDATA%\Amazon\SSM\Logs\errors.log

On Linux, agent worker stdout/stderr may be located under `/var/lib/amazon/ssm/`. On Windows, instance/worker data may reside in `%PROGRAMDATA%\Amazon\SSM\InstanceData\`.

When debugging, note the timestamp and Region; look for errors around the time the agent registered or lost connection; classify whether the issue is DNS, TCP, TLS, credentials, `AccessDenied`, or an agent crash; enable debug logging only for as long as needed; and turn debug off after collecting evidence because log volume can grow quickly and contain sensitive metadata.

## 19. Runbook: Node Does Not Appear in Managed Nodes

Follow these steps in order:

1. Confirm the EC2 instance is in the expected account and Region.
2. Confirm the OS/version is on the supported list.
3. Check that SSM Agent is installed, at an appropriate version, and running.
4. Check that the node has the proper identity source: instance profile, DHMC, or hybrid activation.
5. Check the IAM role trust policy and permissions.
6. Check IMDSv2/IMDS connectivity if using EC2.
7. Run `ssm-cli get-diagnostics --output table`.
8. Check DNS resolution for SSM endpoints.
9. Check outbound TCP 443, proxy settings, endpoint security groups, and NACLs.
10. Read the SSM Agent logs.
11. Use `describe-instance-information` to inspect registration/last ping.
12. After fixing, wait for the agent to reconnect and verify `PingStatus=Online`.

If the node returns no result in `describe-instance-information`, registration may not have completed or credentials/endpoints are misconfigured. If the node appears as `ConnectionLost`, prioritize checking the agent process, heartbeat, IAM credential refresh, and network path.

## 20. Runbook: Session Manager Reports TargetNotConnected

`TargetNotConnected` usually means Session Manager cannot establish a channel to the target. Verify whether the node has `PingStatus` Online; whether the SSM Agent version supports the session type; whether the agent can reach `ssmmessages`; whether the endpoint security group allows inbound TCP 443 from the node; whether the node has outbound 443 and working DNS; whether the node IAM role has message channel permissions; whether the operator has `ssm:StartSession` and document permissions; whether Private DNS and endpoint policies are correct; whether a proxy/TLS inspection device permits the TLS channel; and whether the node is starved of CPU, memory, or disk.

Do not open inbound SSH/RDP as a default remediation step. Session Manager is designed to manage nodes over outbound service connections.

## 21. Common Errors and Root Causes

| Symptom | Possible Cause | Remediation |
|---|---|---|
| EC2 running but not listed | Agent not installed/running, unsupported OS | Check agent and OS |
| Instance profile has no effect | Role not attached, wrong trust, missing policy | Review profile and IAM |
| DHMC not working | IMDSv1, outdated agent, profile still has `ssm:UpdateInstanceInformation` | Meet DHMC prerequisites |
| ConnectionLost | Agent stopped, lost egress, expired credentials | Check agent status, logs, endpoints |
| DNS resolution failure | Wrong resolver/Private DNS | Check VPC DNS and endpoints |
| TLS handshake error | Proxy inspection or missing CA | Fix trust chain |
| AccessDenied | Missing IAM policy, endpoint policy, or KMS policy | Identify principal/action/resource |
| Cannot open session | `ssmmessages`, agent version, operator permissions | Check session prerequisites |
| Run Command produces no output | Document permissions, S3/Logs path, or execution error | Check command invocation and agent logs |
| Node alternates online and offline | Proxy/NAT idle timeout, resource pressure, agent crash | Check channel, heartbeat, and host health |

## 22. Security When Onboarding and Operating Managed Nodes

A managed node is a high-privilege administrative channel. Design the following guardrails:

- Use IAM roles/temporary credentials; avoid static access keys.
- Give the EC2 role only the permissions needed for Systems Manager and its workload.
- Separate node roles from operator permissions.
- Restrict Session Manager by tag, account, Region, and document.
- Control `ssm-user` and root/administrator privileges.
- Enable session logging to CloudWatch Logs or S3 when auditing is required.
- Use KMS for session data if required and manage the key policy separately.
- Protect the activation code/ID as a registration credential.
- Do not bake activations or private credentials into AMIs.
- Update SSM Agent in a controlled manner and monitor the rollout.
- Restrict permissions to modify DHMC, hybrid activations, and instance profiles.
- Use VPC endpoints/private connectivity when network isolation is required.
- Monitor CloudTrail for `StartSession`, `SendCommand`, `CreateActivation`, and changes to IAM/service settings.

Do not allow every operator to run every SSM document. A document can execute shells/scripts with high privileges on managed nodes.

## 23. Updating and Maintaining SSM Agent

AWS regularly releases new SSM Agent versions for features and bug fixes. Automate updates, but roll them out safely:

1. Use a State Manager association or Quick Setup to periodically update the agent.
2. Divide the fleet by environment/canary group.
3. Update a small group first.
4. Verify nodes stay Online and Session Manager/Run Command still work.
5. Expand the rollout in batches.
6. Monitor agent errors, CPU/memory usage, and session failures.
7. Maintain a rollback/reinstall procedure for faulty images or packages.

Do not update the entire fleet simultaneously if high availability is required. Newer agent versions can change compatibility requirements or introduce new behavior; test on representative OSes/images.

## 24. Real-World Scenarios

### Scenario A — EC2 in Private Subnet Does Not Appear

EC2 is running and the agent is active, but no node shows up in Fleet Manager.

**Resolution:** Check instance profile/DHMC, `ssm` endpoint DNS, outbound 443, and agent logs. If there is no NAT, create the appropriate interface VPC endpoints.

### Scenario B — Instance Profile Attached but Still AccessDenied

The role has the right name, but its policy lacks the required SSM permissions.

**Resolution:** Verify the actual IAM role ARN on the instance, attach `AmazonSSMManagedInstanceCore` or an equivalent custom policy, and check permission boundaries/SCPs and credential refresh.

### Scenario C — DHMC Enabled but Node Does Not Use Default Role

The EC2 instance has an instance profile containing `ssm:UpdateInstanceInformation`.

**Resolution:** The agent prioritizes instance profile credentials. If you intend to use DHMC, remove that permission from the profile per AWS guidance and verify IMDSv2/agent version.

### Scenario D — Hybrid Node Fails to Register

An activation was created, but the code expired or the registration limit was reached.

**Resolution:** Create a new activation with an appropriate expiry/limit, store the code securely, and configure the agent with the new ID/code. Previously registered nodes are not deregistered just because an activation expires.

### Scenario E — Session Manager Fails to Connect Even Though Node Is Online

The agent meets the version requirement, but the `ssmmessages` endpoint is unreachable.

**Resolution:** Check the PrivateLink endpoint, endpoint SG inbound 443, node egress, Private DNS, and endpoint policy. Do not open inbound SSH.

### Scenario F — ssm-cli Reports IMDS Failure

The agent cannot retrieve EC2 instance identity/credentials.

**Resolution:** Check IMDS options, host firewall, routing/proxy, and `no_proxy` for `169.254.169.254`. If using DHMC, verify IMDSv2 is required.

### Scenario G — EC2 Cannot Be Managed in Only One Region

DHMC was enabled in Region A, while the instance is in Region B.

**Resolution:** Configure DHMC separately in Region B, and verify IAM/service settings and endpoints for Region B.

### Scenario H — Agent Drops to ConnectionLost After a Few Minutes

The host is still running, but the agent stops sending heartbeats.

**Resolution:** Inspect agent logs, proxy/NAT idle timeouts, resource pressure, credential expiration, and TCP 443 reachability. Use VPC Flow Logs to check for `REJECT` traffic if needed.

### Scenario I — Session Logging to CloudWatch Logs Fails

The node can open sessions, but logs are not recorded.

**Resolution:** Check Session Manager preferences, the CloudWatch Logs endpoint/private connectivity, KMS if encrypted, and logging write permissions. This is an optional feature, not the sole condition for successful node registration.

### Scenario J — Activation Code Exposed in CI Logs

A pipeline printed the entire output of `create-activation`.

**Resolution:** Create a new activation if the code was exposed, restrict registrations, purge/control logs per procedure, store the code in a secrets manager, and avoid echoing output in pipelines.

## 25. Scenario Exercises

### Exercise A — Three Managed Node Conditions

An EC2 instance has the agent running, but no instance profile, DHMC, or valid credential source.

**Answer:** The agent cannot authenticate with Systems Manager; attach an instance profile or enable DHMC with all prerequisites met.

### Exercise B — Private Subnet Without NAT

EC2 needs Session Manager without Internet access.

**Answer:** Create interface endpoints for `ssm` and `ssmmessages`, adding `ec2messages` if needed by the agent/Region; configure Private DNS and endpoint security groups.

### Exercise C — Missing Inbound 22

An operator wants to use Session Manager, but the security group does not allow inbound SSH.

**Answer:** Inbound 22 does not need to be opened. The node establishes outbound HTTPS channels to Systems Manager.

### Exercise D — Outdated Agent

A node runs agent 2.3.100.0 but needs port forwarding.

**Answer:** Upgrade to at least 3.0.222.0, and preferably to a current supported version.

### Exercise E — DHMC and Instance Profile

DHMC is enabled, but the instance profile still contains `ssm:UpdateInstanceInformation`.

**Answer:** SSM Agent uses instance profile credentials first; remove that permission from the profile if you want to use DHMC.

### Exercise F — Wrong Hybrid Role Trust

The role does not trust `ssm.amazonaws.com`.

**Answer:** Update the trust relationship for the Systems Manager service and verify the service role has the required permissions.

### Exercise G — Node Online but Session Manager Errors

The node has `PingStatus` Online, but the `ssmmessages` endpoint is blocked.

**Answer:** Allow outbound 443 and endpoint SG inbound 443; check DNS and the endpoint policy.

### Exercise H — Expired Activation

An activation expires after 24 hours, but several nodes have already registered.

**Answer:** Already-registered nodes remain managed; only unregistered nodes cannot use the old activation.

### Exercise I — ssm-cli Reports Secondary S3 Endpoint Failure

Node registration and the SSM endpoint both show Success, but the S3 check fails.

**Answer:** Determine whether documents/features require S3. This may be an optional feature failure and does not necessarily break registration.

### Exercise J — Managed Node in the Wrong Region

The instance is in `ap-southeast-1`, but the operator is viewing Systems Manager in `us-east-1`.

**Answer:** Select the correct Region; managed node registration, endpoints, and DHMC are Region-scoped.

### Exercise K — User Can StartSession to Any Instance

An IAM policy grants `ssm:StartSession` on `*`.

**Answer:** Scope access by instance ARN/tag, session document, and account/Region; audit sessions and manage `ssm-user`.

### Exercise L — Agent Blocked from IMDS by Proxy

The proxy intercepts requests to `169.254.169.254`.

**Answer:** Add a bypass/`no_proxy` entry for IMDS and configure the agent proxy per AWS guidance; verify metadata credential retrieval.

## 26. Review Questions

1. What is a managed node?
2. What are the three foundational conditions for a node to be managed by Systems Manager?
3. Does an EC2 `running` state guarantee the node appears in Fleet Manager?
4. What does SSM Agent do?
5. Why must the operating system be on the supported list?
6. What does an instance profile provide to SSM Agent?
7. Which principal uses `AmazonSSMManagedInstanceCore`?
8. What problem does DHMC solve?
9. What minimum SSM Agent version does DHMC require?
10. Which IMDS type does DHMC require?
11. Why must DHMC be enabled in each Region?
12. How does `ssm:UpdateInstanceInformation` in an instance profile affect DHMC?
13. Which machine types use hybrid activation?
14. Which trust principal does a hybrid node's IAM service role need?
15. Why must the activation code and ID be protected?
16. Does an expired activation deregister already-registered nodes?
17. What prefix does a hybrid managed node ID typically have?
18. Which outbound port does SSM Agent need to reach endpoints?
19. What are the typical core SSM endpoints?
20. When might `ec2messages` not be required?
21. Why is inbound SSH/RDP not needed for Session Manager?
22. Which inbound port must an interface endpoint security group allow?
23. What role does Private DNS play when using PrivateLink?
24. Are S3/KMS/CloudWatch Logs endpoints always required for registration?
25. What does `ssm-cli get-diagnostics` help check?
26. What does `PingStatus=ConnectionLost` indicate?
27. Where are SSM Agent logs located on Linux?
28. Where are SSM Agent logs located on Windows?
29. What minimum agent version does a basic Session Manager shell require?
30. What version does port forwarding/SSH over Session Manager require?
31. What version does Session Manager logging to CloudWatch Logs require?
32. Why must node IAM roles and operator IAM policies be separated?
33. What privileges does `ssm-user` have by default and why must they be reviewed?
34. Why should SSM Agent updates be controlled?
35. What hybrid activation/pricing changes take effect in 2026?

**Quick Answers:** (1) a machine configured for Systems Manager management; (2) agent, IAM credentials/permissions, endpoint connectivity; (3) no; (4) receives commands and sends status; (5) support follows the OS lifecycle; (6) temporary role credentials; (7) EC2 instance role; (8) automatically provides a role at the account/Region level; (9) 3.2.582.0; (10) IMDSv2; (11) service settings are Regional; (12) the agent prioritizes the instance profile and does not use the DHMC role; (13) on-prem/VMs/other clouds/supported edge devices; (14) `ssm.amazonaws.com`; (15) they can register managed nodes; (16) no; (17) `mi-`; (18) TCP 443; (19) `ssm`, `ssmmessages`, and `ec2messages` when needed; (20) agent 3.3.40.0+ uses `ssmmessages` when available and some newer Regions lack `ec2messages`; (21) the agent opens an outbound channel; (22) 443; (23) resolves standard hostnames to endpoint ENIs; (24) no, depends on features; (25) IMDS, registration, endpoint reachability; (26) agent/heartbeat/credential/network disconnection; (27) `/var/log/amazon/ssm/`; (28) `%PROGRAMDATA%/Amazon/SSM/Logs/`; (29) 2.3.68.0; (30) 3.0.222.0; (31) 3.0.284.0; (32) agent permissions differ from operator permissions; (33) administrative/root privileges; (34) prevent feature breakage and security issues; (35) legacy hybrid console deprecated Dec 31, 2026, advanced-instances tier removed Jun 30, 2026, pay-as-you-go Session Manager/Run Command for hybrid from Sep 30, 2026.

## 27. Production Checklist

- [ ] OS, version, and CPU architecture are on the Systems Manager supported list.
- [ ] AMI/custom image has the correct SSM Agent version.
- [ ] Agent service is enabled and running after reboot.
- [ ] EC2 has an instance profile or DHMC configured in the Region.
- [ ] DHMC nodes use IMDSv2 and agent version 3.2.582.0 or later.
- [ ] Instance profile does not unintentionally block DHMC usage.
- [ ] Hybrid nodes have an activation and IAM service role with the right trust policy.
- [ ] Activation code/ID are not stored in Git, images, or CI logs.
- [ ] Node role has only the required permissions.
- [ ] Operator policy is separated and scoped by target/document.
- [ ] Node allows outbound TCP 443 to SSM endpoints.
- [ ] VPC endpoint security group allows inbound 443 from nodes.
- [ ] DNS/Private DNS, routes, NACLs, and proxy settings are verified.
- [ ] `ec2messages` is configured only when Region/agent compatibility requires it.
- [ ] Secondary endpoints (S3/KMS/Logs) are added based on actual features used.
- [ ] IMDS is protected while remaining reachable by SSM Agent.
- [ ] Session Manager does not rely on inbound SSH/RDP.
- [ ] `ssm-user` privileges are reviewed.
- [ ] Session logging/KMS are enabled per audit requirements.
- [ ] Agent auto-updates use canary testing and batched rollouts.
- [ ] `ssm-cli get-diagnostics` is used during onboarding/troubleshooting.
- [ ] Agent logs and CloudTrail have an inspection process.
- [ ] Fleet is monitored by account, Region, and `PingStatus`.
- [ ] Runbooks exist for missing nodes, `ConnectionLost`, and `TargetNotConnected`.
- [ ] 2026 hybrid pricing/console changes are reflected in the operations plan.

## 28. Summary

A machine becomes a Systems Manager managed node only when three conditions are met simultaneously: SSM Agent is running on a supported OS, it has appropriate IAM credentials/permissions, and it can reach Systems Manager endpoints.

- EC2 can use an instance profile or Default Host Management Configuration.
- DHMC requires IMDSv2, SSM Agent 3.2.582.0+, and per-Region activation.
- Non-EC2 machines use hybrid activations and an IAM service role; activation codes/IDs must be protected.
- SSM Agent initiates outbound HTTPS on TCP 443; Session Manager does not require inbound SSH/RDP.
- Private subnets can use NAT egress or PrivateLink interface endpoints such as `ssm` and `ssmmessages`; `ec2messages` depends on agent version and Region.
- Session Manager has specific version, IAM, and endpoint requirements for shell access, port forwarding, KMS, and logging.
- `ssm-cli`, agent logs, and the AWS CLI help isolate OS, agent, IAM, DNS, network, and Region errors.
- Node roles and operator permissions must be kept separate; `ssm-user` and session logging require proper controls.
- Agent updates and hybrid fleet onboarding must follow structured procedures, auditing, and cost planning.

When designing a managed-node fleet, verify OS, agent, identity, and network as a single dependency chain. A stably online node is the foundation for reliable Run Command, Session Manager, Patch Manager, Inventory, and other operational tools.

### Official AWS Documentation

1. Troubleshooting managed node availability: https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-troubleshooting-managed-nodes.html
2. Supported operating systems and machine types: https://docs.aws.amazon.com/systems-manager/latest/userguide/operating-systems-and-machine-types.html
3. Working with SSM Agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html
4. Checking SSM Agent status and starting the agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-status-and-restart.html
5. Viewing SSM Agent logs: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-logs.html
6. Troubleshooting managed node availability using ssm-cli: https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-managed-nodes-using-ssm-cli.html
7. Configure instance permissions required for Systems Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html
8. Managing EC2 instances automatically with Default Host Management Configuration: https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-default-host-management-configuration.html
9. Session Manager prerequisites: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html
10. Troubleshooting Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html
11. Create a hybrid activation: https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-activation-managed-nodes.html
12. Hybrid activation lifecycle and console changes: https://docs.aws.amazon.com/systems-manager/latest/userguide/activations.html
13. IAM service role for hybrid and multicloud: https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-multicloud-service-role.html
14. Systems Manager VPC endpoints and PrivateLink: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html
15. Troubleshooting SSM Agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-ssm-agent.html
16. SSM Agent release notes: https://github.com/aws/amazon-ssm-agent/releases
17. AWS Systems Manager pricing: https://aws.amazon.com/systems-manager/pricing/
