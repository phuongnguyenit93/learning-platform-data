# Session Manager and Access Without Opening Management Ports

An operations team has many EC2 instances in private subnets. Previously, engineers had to open TCP 22 for SSH or TCP 3389 for RDP, maintain bastion hosts, manage key pairs, and maintain IP allowlists. Every time the fleet scaled, the network surface and access provisioning workflows became more complex.

**AWS Systems Manager Session Manager** provides a way to access managed nodes using IAM and SSM Agent. The operator authenticates to AWS and requests a session; SSM Agent on the node maintains an outbound connection to Systems Manager and receives the session data stream. Because the node initiates the outbound HTTPS connection, security groups do not need inbound SSH/RDP rules to use shell sessions or port forwarding.

Session Manager supports interactive shells, running commands via session documents, port forwarding to a node or remote host, and SSH tunneling through Systems Manager. Session types differ in authentication, logging, and agent requirements. Notably, AWS published CVE-2026-89049 affecting remote-host port forwarding; you must use a patched SSM Agent and tightly restrict access to this document.

This lesson belongs to the **Systems Manager Operations** chapter of the **CLOUD_PROVIDERS_AWS** module. We will design Session Manager for EC2/private subnets, configure IAM authorization by node/tag/document, set up logging/KMS, perform shell sessions and port forwarding, distinguish SSH over Session Manager from standard shells, and build production runbooks and guardrails.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Session Manager and why inbound SSH/RDP does not need to be opened.
2. Describe the authentication flow, control channel, and data channel.
3. List managed node, SSM Agent, IAM, and network prerequisites.
4. Distinguish managed node role permissions from operator permissions.
5. Restrict `StartSession` by instance, tag, session document, and session owner.
6. Start shell sessions from the Console and AWS CLI.
7. Use Run As and understand the privileges of the `ssm-user` account.
8. Configure idle timeout, maximum session duration, and shell profiles.
9. Perform port forwarding to a managed node.
10. Perform port forwarding to a remote host such as RDS.
11. Distinguish SSH over Session Manager from a standard shell session.
12. Enable session logging to CloudWatch Logs or S3.
13. Understand logging limitations for SSH and port forwarding.
14. Add KMS encryption and control session data.
15. Design VPC endpoints, DNS, and outbound connectivity.
16. Analyze CVE-2026-89049 and the requirement for a patched SSM Agent.
17. Diagnose `TargetNotConnected`, `AccessDenied`, and disconnected sessions.
18. Build secure auditing and operations procedures for Session Manager.

## 2. What Problem Does Session Manager Solve?

Traditional administrative access typically requires a network path from the engineer's machine to the server:

    Administrator
         |
         | SSH TCP 22 / RDP TCP 3389
         v
      Bastion host
         |
         v
      EC2 private node

This model requires inbound rules, IP allowlists, SSH keys or RDP credentials, bastion patching, network routing, and multi-layer auditing. As the number of nodes grows, key management and access control become difficult to govern.

Session Manager changes the connection flow:

    Administrator / AWS CLI
             |
             | AWS identity + SigV4
             v
       Systems Manager
             |
             | Secure session channel
             v
          SSM Agent
             |
             v
        Managed node

The node initiates an outbound connection to Systems Manager. When an operator requests a session, the service evaluates IAM permissions, checks session configuration, and then transfers data over the established channel.

| Traditional Access | Session Manager |
|---|---|
| Inbound TCP 22/3389 usually must be open | No inbound SSH/RDP needed for shell sessions and tunnels |
| SSH keys or RDP credentials | IAM identity, policies, and session documents |
| Bastion host commonly used | Private nodes can be accessed via Systems Manager |
| Auditing depends on per-host setup | CloudTrail logs API activity; session data can go to CloudWatch Logs/S3 |
| Revoking keys across many hosts | Revoking or adjusting IAM permissions centrally |

Session Manager does not automatically make every access path safe. Operators can still run privileged commands if policies or session documents allow it; targets, documents, OS users, and logging must be restricted.

## 3. Architecture and Connection Flow

A session can be started from the Systems Manager Console, the EC2 Console, or the AWS CLI. When using the CLI, the operator's machine requires the AWS CLI and the Session Manager plugin.

High-level flow:

1. The operator authenticates with an IAM identity (for example, IAM Identity Center/federated role).
2. The operator calls `StartSession` with a managed node and session document.
3. Systems Manager evaluates IAM policies, resource tags, and document permissions.
4. The service sends the request to SSM Agent through the messaging infrastructure.
5. SSM Agent opens or uses an outbound secure channel.
6. Session Manager connects the client and the node via a bidirectional channel.
7. Input from the operator is forwarded to the agent; output is sent back to the client.
8. When finished, the operator or service closes the session; history and logs are saved as configured.

Traffic between the client and the managed node is protected by TLS 1.2. API requests are signed with AWS Signature Version 4. KMS encryption can be enabled to add encryption for session data beyond the default TLS layer.

### 3.1. Control Channel and Data Channel

The control channel is used to establish and coordinate the session. The data channel carries session input/output. Systems Manager message channels are used by SSM Agent to communicate with the service.

This explains why the node needs outbound connectivity to Systems Manager endpoints. The operator does not need a direct network route from their laptop to the node's private IP.

### 3.2. No Inbound Rule Needed Does Not Mean No Network Needed

The node still must reach Systems Manager over HTTPS. If outbound traffic is blocked, DNS cannot resolve the endpoint, or the endpoint policy is wrong, the node may remain EC2 `running` while Session Manager reports `TargetNotConnected`.

## 4. Prerequisites for Using Session Manager

Before starting a session, verify these prerequisites:

- The node is a Systems Manager managed node with `PingStatus` Online.
- SSM Agent is installed, running, and at the minimum version for the session type.
- The node has appropriate IAM credentials/permissions.
- The node can reach Systems Manager endpoints over outbound HTTPS TCP 443.
- The operator has `StartSession` permission for the target and session document.
- If using the CLI, the operator's machine has the AWS CLI and Session Manager plugin.
- Session preferences, KMS, CloudWatch Logs, or S3 are configured if required by the workload.

AWS-documented version thresholds:

| Feature | Minimum SSM Agent |
|---|---:|
| Basic shell session | 2.3.68.0 |
| Encrypt session data with KMS | 2.3.539.0 |
| Shell profiles | 3.0.161.0 |
| SSH session | 2.3.672.0 |
| Port forwarding to managed node | 2.3.672.0 |
| Port forwarding to remote host | 3.1.1374.0 |
| Stream session data to CloudWatch Logs | 3.0.284.0 |

These are minimum feature thresholds, not versions to pin long term. Automate SSM Agent updates on a schedule and prefer current tested versions.

### 4.1. Special Requirement for Remote-Host Forwarding

Effective October 9, 2026, AWS published CVE-2026-89049 affecting SSM Agent's port forwarding to remote host functionality. An SSRF vulnerability could allow an entity with remote-host forwarding permissions to bypass the destination denylist and access link-local endpoints, potentially exposing the managed node's temporary IAM credentials.

- SSM Agent versions earlier than 3.3.4851.0 are affected for remote-host port forwarding.
- The fix was released by AWS in SSM Agent 3.3.4851.0.
- AWS recommends upgrading to the latest version.
- Until updated, strictly restrict access to the `AWS-StartPortForwardingSessionToRemoteHost` document and do not grant it to untrusted principals.

This is an additional security requirement for remote-host forwarding. Reaching the 3.1.1374.0 feature threshold does not mean the agent is patched against the CVE. In current environments, use agent version 3.3.4851.0 or later and update to newer releases as AWS publishes them.

## 5. IAM: Node Permissions vs. Operator Permissions

Session Manager uses two independent permission sets:

| Principal | Role |
|---|---|
| Managed node IAM role | Allows SSM Agent to register, communicate, and open message channels |
| Operator IAM identity | Allows viewing nodes, starting/terminating/resuming sessions, and using session documents |
| Logging/KMS role or resource policy | Allows writing logs, encrypting, or reading data per configuration |

For EC2 managed nodes, the commonly used AWS managed policy is `AmazonSSMManagedInstanceCore`. This policy grants core permissions for the agent. For hybrid managed nodes, use an IAM service role with the proper trust relationship and permissions.

An operator does not need permission to administer the node's IAM role to start a session. Conversely, having `StartSession` permission does not help the agent connect if the node lacks a role or network connectivity.

### 5.1. Common API Permissions

| Action | Purpose |
|---|---|
| `ssm:StartSession` | Start a session to a managed node using a session document |
| `ssm:ResumeSession` | Resume an existing session |
| `ssm:TerminateSession` | Terminate a session |
| `ssm:DescribeSessions` | View session list/status |
| `ssm:GetConnectionStatus` | Check target connectivity |
| `ssm:DescribeInstanceInformation` | View managed-node information |
| `ssmmessages:OpenDataChannel` | Open a data channel for the caller's session |
| `ssm:GetDocument` / `ssm:ListDocuments` | View session documents when selecting a document from the Console |

Exact permissions depend on whether you use the Console, EC2 Console, CLI, session type, and AWS sample policies. Do not copy a broad policy and assign it to every operator; tailor policies to actual workflows.

### 5.2. Restricting Targets by ARN and Tag

You can restrict `StartSession` to a specific set of EC2 instances:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "ssm:StartSession",
          "Resource": [
            "arn:aws:ec2:ap-southeast-1:111122223333:instance/i-0123456789abcdef0",
            "arn:aws:ssm:ap-southeast-1:111122223333:document/SSM-SessionManagerRunShell"
          ]
        }
      ]
    }

This is an example policy for one instance and the default shell document. In practice, use tag conditions to manage access by group—for instance, only allowing Finance operators to access nodes tagged `Finance=WebServers`. Keep the document ARN in `Resource` so operators can only open the intended session type.

### 5.3. Allowing Operators to Terminate Only Their Own Sessions

Session Manager attaches AWS-managed resource tags to sessions. You can use the session-id resource tag and AWS caller identity to restrict `ResumeSession`/`TerminateSession`/`OpenDataChannel` to sessions created by the caller. AWS provides sample policies for IAM users and role sessions; use the exact condition keys and ARN format from the documentation.

Do not grant permission to manage all sessions to regular operators. `TerminateSession` across all sessions can disrupt other engineers' work.

### 5.4. Separating Session Preferences Administration

Anyone permitted to update Session Manager preferences can change logging, KMS encryption, Run As, timeouts, and shell profiles. Separate this permission from normal session-start privileges; preference changes affect many users in the account/Region.

## 6. Starting a Shell Session from the Console

You can use either the Systems Manager Console or the EC2 Console.

In the Systems Manager Console:

1. Select the correct AWS account and Region.
2. Open Systems Manager.
3. Choose Session Manager.
4. Choose Start session.
5. Select a managed node in the Online state.
6. Choose a session document if permitted by policy; otherwise, use the default document.
7. Choose Start session.
8. Once the session opens, run Bash on Linux/macOS or PowerShell on Windows.

In the EC2 Console:

1. Open EC2 → Instances.
2. Select the instance.
3. Choose Connect.
4. Choose Session Manager.
5. Choose Connect.

If the instance does not appear, check managed-node prerequisites and operator permissions. The Console only supports session documents with `sessionType` `Standard_Stream` when a user selects a document from the UI.

## 7. Starting a Session with the AWS CLI

The operator's machine requires:

- AWS CLI installed and configured with a profile/credentials.
- A compatible Session Manager plugin.
- An IAM identity with `StartSession` permission.
- Network access to AWS APIs from the operator's machine.

Command to open a shell session:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

If using a named profile:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1 \
      --profile production-operator

When the session opens, the terminal switches to an interactive stream. End it using the shell exit command or the Session Manager plugin escape sequence displayed in the terminal.

Check active sessions:

    aws ssm describe-sessions \
      --state Active \
      --region ap-southeast-1

Terminate a specific session:

    aws ssm terminate-session \
      --session-id operator-abc123

The Session ID is returned when `StartSession` succeeds. Keep this ID in tickets/incident records if needed for audit correlation.

## 8. OS Privileges: ssm-user and Run As

By default, SSM Agent creates the `ssm-user` OS account on the managed node and grants it administrative/root privileges. Standard shell sessions typically run under this account's credentials.

This is convenient for troubleshooting, but carries major security implications: anyone with `StartSession` access to a node can perform privileged operations based on the session account's OS permissions.

### 8.1. Run As

For Linux managed nodes, you can enable Run As in Session Manager preferences to run sessions as a specified OS user instead of `ssm-user`. The chosen user must exist on the node and have permissions aligned with the task.

Examples:

- A developer who only needs to read logs can use a read-only OS user.
- A DBA who needs to run database diagnostic commands can use a dedicated account.
- A platform administrator needing root can be granted access through a controlled role group with approval.

Run As does not replace IAM. IAM decides who can open a session and to which node; Run As decides which OS identity is used once the session is authorized.

### 8.2. Controlling ssm-user

Review `ssm-user`'s sudo/Administrator privileges. Organizations can disable or modify default administrative privileges per policy, while ensuring session documents and Run As workflows continue to function.

For Windows Server domain controllers, there are specific requirements around `ssm-user`; check AWS documentation before deploying account changes.

## 9. Session Preferences

Session Manager preferences apply at the account/Region level or are configured via an appropriate session document. Common options:

| Preference | Effect |
|---|---|
| CloudWatch Logs | Stream session data to a log group |
| Amazon S3 | Save session logs to a bucket |
| KMS encryption | Further encrypt session data with a customer managed key |
| Idle session timeout | Automatically terminate inactive sessions |
| Maximum session duration | Limit maximum session lifetime |
| Run As | Choose the OS user on Linux managed nodes |
| Shell profiles | Configure shell, environment variables, working directory, and startup commands |

Set a reasonably short idle timeout to avoid unattended sessions. Maximum session duration should match change/incident processes. For production access, require a session reason and record the ticket/change ID in the workflow if the organization requires auditing.

Do not allow every operator to edit preferences. Preferences apply account/Region-wide and can disable logging or weaken protections if misconfigured.

## 10. Port Forwarding to the Managed Node Itself

Port forwarding creates a tunnel from a local port on the operator's machine to a port on the managed node. For example, an engineer needs to open an internal application bound only locally on an EC2 private node.

Command:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --document-name AWS-StartPortForwardingSession \
      --parameters '{"portNumber":["8080"],"localPortNumber":["18080"]}' \
      --region ap-southeast-1

Once the session opens, access from the operator's machine:

    http://localhost:18080

Meaning:

- `portNumber`: the port on the managed node to forward.
- `localPortNumber`: the local port on the operator's laptop/desktop.
- Target: the managed node running SSM Agent.

Traffic is tunneled through Session Manager. There is no need to open inbound port 8080 from the Internet or laptop to the instance; the application can bind solely to an appropriate internal interface.

### 10.1. When to Use Port Forwarding?

- Accessing an admin web UI available only in a private subnet.
- Testing a local service on a managed node.
- Connecting to a database running directly on the managed node.
- Creating a temporary tunnel to debug a service.

Port forwarding does not turn IAM into database authentication. The operator still needs separate application/database credentials if the remote service requires them.

## 11. Port Forwarding to a Remote Host

Remote-host forwarding uses a managed node as an intermediary to reach another host that the managed node can connect to. The remote host does not have to be a Systems Manager managed node.

For example, an operator wants to connect to a private Amazon RDS endpoint via a managed EC2 node in the same VPC.

    Operator laptop
        |
        | localhost:13306
        v
    Session Manager tunnel
        |
        v
    Managed EC2 node
        |
        | TCP 3306 inside VPC
        v
    RDS endpoint:3306

Command:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --document-name AWS-StartPortForwardingSessionToRemoteHost \
      --parameters '{"host":["orders-db.cluster-abc123.ap-southeast-1.rds.amazonaws.com"],"portNumber":["3306"],"localPortNumber":["13306"]}' \
      --region ap-southeast-1

Once the session opens, configure the database client:

    Host: 127.0.0.1
    Port: 13306
    Database: orders
    Username: <database-user>

The remote host must be DNS-resolvable and network-reachable from the managed node. The RDS security group must allow inbound port 3306 from the managed node's security group; the operator's laptop does not need a direct route to RDS.

### 11.1. Permissions and Network Scope

Remote-host forwarding is effectively a TCP proxy from the operator's machine through the managed node. If the node can reach multiple subnets/services, anyone permitted to use this document can reach those destinations within the node's network scope.

Therefore:

- Only grant permission to DBA/operations groups that genuinely need it.
- Scope `StartSession` to specific target nodes.
- Scope permissions to the `AWS-StartPortForwardingSessionToRemoteHost` document.
- Use security groups/network ACLs so the node can connect only to necessary destinations.
- Do not grant remote-host forwarding to untrusted users or public-facing workloads.
- Use an agent patched for CVE-2026-89049 (3.3.4851.0 or later; prefer latest).
- Monitor CloudTrail `StartSession` events and review access regularly.

### 11.2. Security Note on CVE-2026-89049

AWS disclosed an SSRF vulnerability in SSM Agent's remote-host port forwarding. Versions earlier than 3.3.4851.0 are affected; the vulnerability can allow a principal with port-forwarding permissions to reach link-local endpoints and potentially retrieve the managed node's temporary IAM credentials.

Remediation steps:

1. Update SSM Agent to at least 3.3.4851.0, preferably the latest release.
2. If you cannot update immediately, temporarily restrict or remove `StartSession` permissions for the remote-host forwarding document from untrusted principals.
3. Restrict the managed node's IAM role according to least privilege.
4. Restrict network egress from the managed node to required destinations only.
5. Review CloudTrail and suspicious session activity according to incident response procedures.

Do not treat the 3.1.1374.0 feature threshold as a patched security baseline. Remote-host forwarding should only be enabled after the agent meets the security fix level.

## 12. SSH Over Session Manager

SSH over Session Manager is suitable when existing tools require the SSH protocol, such as SCP or IDE remote development. The SSH daemon must still run on the target, and the user must have appropriate SSH authentication. Session Manager establishes a TLS tunnel between the client, the service, and SSM Agent; inbound TCP 22 from external networks does not need to be open.

SSH over Session Manager differs from a standard shell session:

| Shell session | SSH over Session Manager |
|---|---|
| Uses the default session document | Uses an SSH client and the `AWS-StartSSHSession` document |
| Typically uses `ssm-user`/Run As | Uses the host's OS user and SSH key/certificate |
| Session Manager can log commands/output | Session Manager cannot log the SSH payload |
| Does not require `sshd` on the node | Requires the SSH daemon on the target |

Example SSH client configuration with `ProxyCommand`:

    Host i-* mi-*
      ProxyCommand sh -c "aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p'"

Connect:

    ssh -i team-admin.pem ec2-user@i-0123456789abcdef0

Actual configuration may need quoting adjustments depending on shell/OS. The AWS CLI and Session Manager plugin must be installed on the operator's machine. The target needs an SSH daemon, user, and corresponding public key/certificate.

If you only need an interactive terminal, a standard shell session is usually simpler and lets Session Manager record session data. Use SSH when tools or workflows truly require the SSH protocol.

## 13. Session Logging: CloudTrail, CloudWatch Logs, and S3

Distinguish three types of auditing:

| Source | Content |
|---|---|
| AWS CloudTrail | API activity: `StartSession`, `TerminateSession`, preference changes, and management requests |
| Session Manager logging | Shell session input/output as configured |
| OS/application logs | Operating system, service, application, and database activity |

CloudTrail shows who called the API, when, and on which target. It does not automatically record every command typed in the terminal. To capture shell session commands/output, configure Session Manager logging to CloudWatch Logs or S3.

### 13.1. Logging to CloudWatch Logs

In Session Manager preferences:

1. Enable CloudWatch logging.
2. Select a log group with an appropriate retention period.
3. Enable the option to allow only encrypted log groups if required by policy.
4. Ensure logging write permissions and KMS policy if the log group uses a customer managed key.
5. Verify the SSM Agent version meets the log-streaming threshold.
6. Test a session and verify events appear in the log group.

CloudWatch Logs is well suited when you need search, alerts, queries, and CloudWatch dashboard integration.

### 13.2. Logging to Amazon S3

S3 is suitable for long-term storage, retention policies, lifecycle transitions, and audit archives. Configure the bucket/prefix, encryption, bucket policy, and appropriate write permissions.

Do not allow operators to read the entire bucket just because they have `StartSession` permission. Separate session creation permissions from session archive read access.

### 13.3. Logging Limitations for SSH and Port Forwarding

Session Manager does not log session data payloads for sessions using SSH or port forwarding. With SSH, the payload is encrypted inside the tunnel; with port forwarding, Session Manager forwards application bytes rather than interpreting commands.

If you need to audit those workflows, use the appropriate layer:

- CloudTrail to audit who opened/closed sessions and the target/document.
- SSH server logs for SSH authentication activity.
- Database audit logs for SQL statements/DB users.
- Application logs for request/application activity.
- Client-side logs or specialized access tools per policy.

Never claim that enabling CloudWatch Logs in Session Manager records SQL queries sent through a port-forwarding tunnel.

### 13.4. Avoiding Secrets in Session Logs

Shell session logs can capture commands and output. Do not enter passwords/tokens directly in echoed forms or command-line arguments that could be logged. Use secure prompts, secrets managers, and non-echo input mechanisms. Restrict log read access, enable encryption, and set appropriate retention.

On Linux/macOS, AWS notes you can use commands that read passwords with terminal echo disabled; on Windows, use a PowerShell `SecureString` prompt. Specific methods should be tested in your shell profile and session logging setup.

## 14. Encrypting Session Data with AWS KMS

TLS 1.2 is the default encryption layer for Session Manager connections. You can enable KMS encryption to further protect session data.

When enabling KMS:

- Choose an appropriate customer managed key.
- Both the key policy and IAM policies must allow the required principals.
- Operators may need `kms:GenerateDataKey` permissions depending on the workflow.
- The managed node/Systems Manager needs network connectivity to KMS if using VPC endpoints.
- SSM Agent must be version 2.3.539.0 or later.
- Test both session start and session reconnect.

KMS encryption adds an extra encryption layer for session data; it does not replace TLS, IAM authorization, logging, or endpoint security.

## 15. Session Documents

A session document defines the session type and startup behavior. Default shell sessions use the `SSM-SessionManagerRunShell` document. AWS provides other documents such as:

| Document | Purpose |
|---|---|
| `SSM-SessionManagerRunShell` | Standard shell sessions and session preferences |
| `AWS-StartPortForwardingSession` | Forward a port to a managed node |
| `AWS-StartPortForwardingSessionToRemoteHost` | Forward a port to another host from a managed node |
| `AWS-StartSSHSession` | Use the SSH protocol over Session Manager |

Custom session documents can restrict commands, parameters, session type, or shell environment. The Console only supports documents with `sessionType` `Standard_Stream` when users pick a document.

Do not allow users to pick arbitrary documents if they only need a basic shell. A document can define commands or forwarding destinations and significantly alter effective privileges.

## 16. Network: Endpoints and PrivateLink

A managed node needs outbound HTTPS TCP 443 to Systems Manager endpoints in the Region:

- `ssm.<region>.amazonaws.com`
- `ssmmessages.<region>.amazonaws.com`
- `ec2messages.<region>.amazonaws.com` when required by the agent/Region.

SSM Agent 3.3.40.0 and later uses `ssmmessages` instead of `ec2messages` when available; some newer Regions do not offer `ec2messages`. For the Session Manager data channel, `ssmmessages` is the critical endpoint.

Private subnets can use:

1. A NAT Gateway/egress path to public service endpoints.
2. Interface VPC endpoints for Systems Manager/`ssmmessages`.

With PrivateLink, verify:

- Interface endpoints are in the right Region and VPC.
- Private DNS is enabled if using standard hostnames.
- The endpoint security group allows inbound TCP 443 from managed nodes.
- The node security group allows outbound TCP 443 to the endpoints.
- Endpoint policies do not block required actions.
- VPC DNS resolution/hostnames and resolver rules are correct.

If KMS encryption, CloudWatch Logs, or S3 session logging is enabled, additional endpoints and permissions are needed for KMS, Logs, and S3 respectively.

Inbound TCP 22/3389 on the managed node is not required for shell sessions or tunnels. However, if using SSH over Session Manager, `sshd` must still run on the target and local connections from SSM Agent to the SSH service must work.

## 17. VPC Security Groups and Remote Destinations

Session Manager does not automatically modify security groups. When port forwarding to a remote host:

- The managed node needs egress to the remote host/port.
- The remote host's security group/firewall must allow inbound traffic from the managed node.
- The operator only connects to a local port on their laptop.
- Do not open the remote database port to the Internet or the laptop's public IP unless required elsewhere.

RDS MySQL example:

| Component | Rule |
|---|---|
| Operator laptop | Local TCP 13306 |
| Session Manager tunnel | Forwards local 13306 to the managed node |
| Managed node SG | Egress TCP 3306 to RDS SG |
| RDS SG | Inbound TCP 3306 from managed node SG |
| RDS public access | Does not need to be enabled |

This is an appropriate administrative connection pattern for private databases, but IAM permissions for remote-host forwarding must be tightly controlled.

## 18. Auditing, Notifications, and CloudTrail

CloudTrail logs Session Manager API activity. You should monitor:

- `StartSession` and target/document.
- `TerminateSession`/`ResumeSession`.
- Who modifies Session Manager preferences.
- Who modifies related IAM policies or roles.
- Who creates/modifies session documents.
- Toggling of logging and KMS.
- Related activation/managed-node activity if using a hybrid fleet.

You can use EventBridge rules on CloudTrail events to send SNS notifications or trigger workflows when a session starts or ends. Note that event notifications report API activity; they do not replace session command logging.

## 19. Troubleshooting: TargetNotConnected

When `StartSession` returns `TargetNotConnected`, check in order:

1. Does the node appear in Systems Manager Managed nodes?
2. Is `PingStatus` Online?
3. Is the SSM Agent service running?
4. Is the agent version sufficient for the session type?
5. Does the node IAM role have the core policy?
6. Can the agent reach the `ssmmessages` endpoint?
7. Does DNS resolve to the right Region?
8. Does the node have outbound TCP 443?
9. Does the endpoint SG allow inbound TCP 443 from the node?
10. Are NACLs/proxies/TLS inspection blocking traffic?
11. Does the operator have `StartSession` and document permissions?
12. Is the Session Manager plugin installed/compatible on the operator's machine?

A node that is Online yet fails sessions may be suffering from `ssmmessages` channel issues, operator IAM issues, or document authorization failures.

## 20. Troubleshooting: AccessDenied

`AccessDenied` usually comes from one of these layers:

- The operator lacks `ssm:StartSession`.
- The operator is permitted on the target, but not on the session document.
- A tag condition does not match the managed node's tags.
- The operator lacks `ResumeSession`/`TerminateSession` for their own session.
- The KMS key policy does not permit using the key.
- An SCP, permissions boundary, or explicit `Deny` overrides an `Allow`.
- The Console needs `GetDocument`/`ListDocuments` that the policy has not granted.
- The remote-host forwarding document is intentionally blocked by policy.

Inspect the CloudTrail event and IAM policy evaluation to identify the denied principal, action, resource, and condition. Do not resolve this by granting `ssm:*` or `Resource *` to everyone.

## 21. Troubleshooting: Disconnected Sessions or Missing Logs

If a session disconnects:

- Check idle timeout and maximum session duration.
- Check for agent restarts/updates.
- Check network/proxy/NAT idle timeouts.
- Check `ssmmessages` reachability.
- Check node CPU/memory/disk.
- Check whether a user terminated the session.

If a session opens but logs do not appear:

- Verify Session Manager preferences in the right account/Region.
- Check the log group/bucket and encryption settings.
- Check IAM roles/resource policies for Logs/S3.
- Check Logs/S3 endpoints if the node is private.
- Check the agent version.
- Verify whether the session is SSH or port forwarding; those types do not have payloads logged by Session Manager.

## 22. Production Security

Session Manager is an administrative channel capable of providing strong OS privileges. Apply these guardrails:

- Use IAM Identity Center/federation and MFA per organizational policy.
- Scope `StartSession` by tag, instance ARN, Region, and session document.
- Restrict `Resume`/`Terminate` to sessions created by the caller.
- Separate preferences administration from operator session permissions.
- Review `ssm-user` privileges; consider Run As for a lower-privilege OS user.
- Do not grant remote-host port forwarding to untrusted groups.
- Update SSM Agent to the CVE-2026-89049 fix (3.3.4851.0 or later) and stay on current releases.
- Restrict network egress from managed nodes and remote destinations.
- Enable CloudTrail; enable CloudWatch Logs/S3 session logging for shell sessions requiring auditability.
- Encrypt logs, restrict read access, and set retention and lifecycle policies.
- Do not enter secrets into shell commands that may be logged.
- Review session documents and block public sharing if unnecessary.
- Restrict who can modify preferences, IAM roles, KMS keys, and VPC endpoints.
- Use approval/change management for production access when required by the workload.

### 22.1. Do Not Confuse "No Open Ports" with "No Risk"

Session Manager reduces the inbound network surface and removes the need for bastions in many cases. However, a root-privileged session can still alter the system, read data, or reach dependencies from the node. IAM, OS permissions, network egress, logging, and agent patching remain mandatory protective layers.

## 23. Hands-On Lab: Shell Session Without Opening SSH

Assume a private EC2 node is already registered with Systems Manager, has an instance profile, an Online agent, and VPC endpoints.

1. Confirm the security group has no inbound TCP 22 from the operator's network.
2. Confirm the node has outbound TCP 443 to `ssm`/`ssmmessages`.
3. Sign in to AWS using the operator role.
4. Run `StartSession` targeting the instance.
5. Verify the shell prompt appears.
6. Run read-only commands such as `hostname`, `uptime`, and `systemctl status`.
7. Exit the session.
8. Inspect CloudTrail for `StartSession`/`TerminateSession`.
9. If logging is enabled, check CloudWatch Logs or S3.
10. Confirm no inbound SSH rule was added during the lab.

## 24. Hands-On Lab: Port Forwarding to RDS

Assume RDS MySQL is in a private subnet and the managed EC2 node can reach RDS via security groups.

1. Confirm SSM Agent is patched and on a current version.
2. Confirm the operator is allowed to use `AWS-StartPortForwardingSessionToRemoteHost`.
3. Confirm managed node egress TCP 3306 to RDS.
4. Confirm RDS SG inbound TCP 3306 from the managed node SG.
5. Start a remote-host forwarding session with local port 13306.
6. Use a database client to connect to `127.0.0.1:13306`.
7. Authenticate with separate database credentials.
8. Terminate the session and verify the tunnel closes.
9. Check CloudTrail to audit `StartSession`.
10. Check database audit logs if SQL statement tracking is needed.

Session Manager does not record SQL traffic inside a port-forwarding tunnel. Use database audit logs to capture queries as required.

## 25. Real-World Scenarios

### Scenario A — Developer Needs a Shell on a Private EC2 Instance

The instance has no public IP and the security group does not allow SSH.

**Resolution:** Use a Session Manager shell with a node role, agent, `ssmmessages` connectivity, and operator `StartSession` permission. No bastion or inbound 22 is needed.

### Scenario B — DBA Needs Access to Private RDS

The laptop has no route to RDS.

**Resolution:** Use a managed EC2 node as a tunnel endpoint, remote-host forwarding to the RDS endpoint, and grant document access to the DBA group. Restrict network destinations and require a patched agent version.

### Scenario C — Session Opens but Produces No Logs

The operator is using port forwarding.

**Resolution:** This is by design: Session Manager does not log port-forwarding/SSH payloads. Use CloudTrail for session API activity and database/application logs for traffic inside the tunnel.

### Scenario D — TargetNotConnected

The node is in EC2, but not Online in Systems Manager.

**Resolution:** Check the agent, role, DNS, outbound 443, endpoint SG, and `ssmmessages`. EC2 `running` does not guarantee managed node connectivity.

### Scenario E — Operator Can Access Every Instance

The policy allows `StartSession` on all resources.

**Resolution:** Replace with resource ARN/tag conditions and document ARNs; restrict `Resume`/`Terminate` to the session owner.

### Scenario F — Remote-Host Forwarding on an Older Agent

The managed node runs SSM Agent 3.1.1374.0 and has document permission.

**Resolution:** The feature may work, but this version is below the CVE-2026-89049 patch. Upgrade the agent to 3.3.4851.0 or later and narrow document permissions during the upgrade.

### Scenario G — SSH Over Session Manager Does Not Work

The node is Online, but the SSH client reports connection refused.

**Resolution:** Check that `sshd` is running, the OS username, public key/certificate, SSH port, and `ProxyCommand`. Session Manager builds the tunnel, but does not start the SSH daemon or provision SSH keys.

### Scenario H — KMS Encryption Enabled but Session Fails to Open

The node has a misconfigured KMS key policy or an outdated agent.

**Resolution:** Check agent version 2.3.539.0+, key policy, IAM permissions, and the KMS endpoint/private connectivity.

### Scenario I — Session Closes Automatically After Inactivity

Session Manager preferences enforce an idle timeout.

**Resolution:** Check the idle timeout and maximum duration. Choose policy-compliant values; do not disable timeouts globally just to keep sessions open.

### Scenario J — User Enters a Password and It Appears in Logs

Session logging is enabled and the shell echoes input.

**Resolution:** Use secure prompts/no-echo, secrets managers, and restrict log access. Consider handling logs containing exposed secrets under incident/credential rotation procedures.

## 26. Review Questions

1. What is Session Manager?
2. Why is inbound TCP 22/3389 not needed for shell sessions?
3. Which outbound port does a managed node need?
4. What roles do the control channel and data channel play?
5. Which parts of the connection do TLS and SigV4 protect?
6. How do managed node role permissions differ from operator role permissions?
7. Which principal uses `AmazonSSMManagedInstanceCore`?
8. What does `ssm:StartSession` control?
9. Why should session document ARNs be restricted?
10. What is the name of the Session Manager default shell document?
11. Which plugin does the Session Manager CLI require?
12. What is the `ssm-user` account?
13. What does Run As change?
14. Which settings can Session preferences configure?
15. What does `AWS-StartPortForwardingSession` do?
16. How do `portNumber` and `localPortNumber` differ?
17. When is `AWS-StartPortForwardingSessionToRemoteHost` used?
18. Must the remote host be a managed node?
19. Why does the managed node need network reachability to the remote host?
20. Does SSH over Session Manager require `sshd`?
21. Why do SSH/port-forwarding sessions lack Session Manager payload logs?
22. What type of activity does CloudTrail record?
23. What do CloudWatch Logs/S3 session logging record?
24. What does KMS encryption add beyond TLS?
25. What minimum SSM Agent feature version does remote-host forwarding require?
26. Which feature does CVE-2026-89049 affect?
27. Which SSM Agent release fixes CVE-2026-89049?
28. Until updated, which permission must be restricted?
29. What role does the `ssmmessages` endpoint play?
30. Why does port forwarding not replace database authentication?
31. How can an operator be restricted by tag?
32. Why should `ResumeSession`/`TerminateSession` be restricted by session owner?
33. In what order should `TargetNotConnected` be checked?
34. Does Session Manager automatically log SQL statements sent over a tunnel?
35. Why should `ssm:*` not be granted on all resources?

**Quick Answers:** (1) service for accessing managed nodes via Systems Manager; (2) the node opens an outbound channel; (3) TCP 443; (4) coordination and data transport; (5) TLS protects the data channel, SigV4 signs API requests; (6) node agent permissions vs. operator permissions; (7) EC2 managed node role; (8) permission to open a session to a target/document; (9) documents define session type and behavior; (10) `SSM-SessionManagerRunShell`; (11) Session Manager plugin; (12) an OS account usually with administrative privileges; (13) the OS user running the session; (14) logging, KMS, timeouts, Run As, shell profiles; (15) tunnels to a port on the managed node; (16) remote port vs. local port; (17) tunneling from a managed node to another host; (18) no; (19) the node is the connection point to the host; (20) yes; (21) payloads are tunneled/encrypted and the service does not interpret them; (22) API activity; (23) commands/output for supported sessions; (24) an additional encryption layer; (25) 3.1.1374.0; (26) remote-host port forwarding SSRF; (27) 3.3.4851.0; (28) `StartSession` for the remote-host forwarding document; (29) session message/data channels; (30) the database still requires its own credentials; (31) IAM condition `ssm:resourceTag`; (32) avoid managing other users' sessions; (33) agent, node status, `ssmmessages`, DNS, 443, IAM/document; (34) no; (35) overly broad privileges that can grant unintended administrative access.

## 27. Production Checklist

- [ ] Managed node has `PingStatus` Online.
- [ ] SSM Agent is updated and compatible with the session type.
- [ ] Remote-host forwarding uses SSM Agent 3.3.4851.0 or later.
- [ ] CVE-2026-89049 is addressed; the remote-host forwarding document is not granted to untrusted principals.
- [ ] Node role has minimal SSM/`ssmmessages` permissions.
- [ ] Operator `StartSession` is scoped by target ARN/tag.
- [ ] Session document ARNs are scoped by workflow.
- [ ] `ResumeSession`/`TerminateSession` are limited to the session owner or authorized admins.
- [ ] `ssm-user` privileges are reviewed; Run As is considered.
- [ ] Session preferences include idle timeout and maximum duration.
- [ ] CloudTrail records Session Manager API activity.
- [ ] Shell session logging to CloudWatch Logs/S3 is enabled per audit policy.
- [ ] SSH/port-forwarding logging limitations are accounted for in the audit design.
- [ ] Log groups/buckets are encrypted with retention and access controls.
- [ ] KMS key policies and IAM permissions are verified if encryption is enabled.
- [ ] Secrets are not entered into commands/output that could be logged.
- [ ] Nodes have outbound TCP 443 to `ssm`/`ssmmessages`.
- [ ] PrivateLink endpoints and endpoint SGs allow 443 from managed nodes.
- [ ] Inbound 22/3389 is not opened unless required by another use case.
- [ ] Remote-host forwarding is restricted by target, document, and network egress.
- [ ] RDS/database audit logs are used for SQL over tunnels.
- [ ] Session documents use `allowedValues`/`allowedPattern` when accepting parameters.
- [ ] Permission to modify Session Manager preferences is separated.
- [ ] EventBridge/SNS notifications or monitoring exist for session activity if needed.
- [ ] Runbooks exist for `TargetNotConnected`, `AccessDenied`, missing logs, and disconnected sessions.
- [ ] IAM, SSM Agent, and session document permissions are reviewed periodically.

## 28. Summary

Session Manager lets operators access managed nodes using IAM and SSM Agent over outbound connections, enabling many private workloads to operate without inbound SSH/RDP or bastion hosts.

- Shell sessions use `SSM-SessionManagerRunShell`; operators can connect from the Console or AWS CLI/Session Manager plugin.
- Managed nodes need the agent, an IAM role, and outbound TCP 443 to Systems Manager/`ssmmessages` endpoints.
- IAM policies should restrict targets, tags, session documents, and session owners.
- `ssm-user` has strong OS privileges by default; Run As allows selecting a lower-privilege OS identity.
- Port forwarding to a node or remote host tunnels traffic to a local port; the remote host must be reachable from the managed node.
- SSH over Session Manager still requires an SSH daemon, OS user, and SSH authentication.
- CloudTrail logs API activity; CloudWatch Logs/S3 can store shell session data, but do not capture SSH/port-forwarding payloads.
- KMS encryption adds protection beyond TLS; session preferences govern logging, timeouts, Run As, and shell profiles.
- CVE-2026-89049 affects remote-host port forwarding in SSM Agent below 3.3.4851.0; update the agent and restrict document permissions.
- Production access requires least privilege, auditing, network egress controls, and runbooks.

Session Manager reduces the inbound network attack surface, yet remains a powerful administrative channel. Treat IAM policies, OS identity, session documents, agent patch levels, destination reachability, and audit logging as one unified design.

### Official AWS Documentation

1. Session Manager overview: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html
2. Session Manager prerequisites: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html
3. Start a session: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html
4. Control session access to managed nodes: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-restrict-access.html
5. Sample IAM policies for Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html
6. Additional sample IAM policies: https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-examples.html
7. Session Manager SSH connections: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html
8. Configure session preferences: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-configure-preferences.html
9. Enabling and disabling session logging: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging.html
10. Logging session data to CloudWatch Logs: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-cloudwatch-logs.html
11. Logging session data to S3: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-s3.html
12. Use AWS PrivateLink for Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-privatelink.html
13. Systems Manager VPC endpoints: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html
14. Security best practices for Systems Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/security-best-practices.html
15. Troubleshooting Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html
16. AWS Security Bulletin CVE-2026-89049: https://aws.amazon.com/security/security-bulletins/2026-107-aws/
17. SSM Agent releases and fixes: https://github.com/aws/amazon-ssm-agent/releases
