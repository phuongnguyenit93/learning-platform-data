# Creating a Virtual Machine in a Private Subnet and Setting Up Administrative Access

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish between public and private subnets through route tables and public IP address assignment.
- Design a network so that virtual machines do not accept direct administrative connections from the Internet.
- Create a virtual machine in a private subnet and grant administrative permissions following the principle of least privilege.
- Set up administrative access via a session management service or an intermediary host.
- Verify network paths, IAM permissions, virtual machine status, and accessibility; troubleshoot common issues.

## 1. Architecture to Deploy

Virtual machines in a private subnet typically run applications, databases, or internal components. They do not need a public IP address and have no direct routing path from the Internet to their network interfaces. Administrators still need an access channel with authentication, authorization, and activity logging.

The examples in this lesson use Amazon VPC and EC2. Equivalent concepts apply to Azure Virtual Network and Google Cloud VPC.

Sample architecture:

~~~text
                         Internet
                            |
                     Internet Gateway
                            |
                  Public subnet 10.20.1.0/24
                     |              |
                 NAT Gateway    Bastion (optional)
                     |              |
              Private route table   | SSH only from VPN/admin IP
                     |              |
              Private subnet 10.20.11.0/24
                     |
                Private EC2 VM
                     |
          SSM Agent / internal app
                     |
       Interface VPC endpoints for SSM
       or egress via NAT Gateway
~~~

In the preferred approach, administrators use AWS Systems Manager Session Manager to open a session to the virtual machine. The connection is initiated from the SSM Agent on the virtual machine outbound to the Systems Manager service over HTTPS; no inbound SSH or RDP ports need to be opened. A bastion host is an alternative when compatibility requirements or specific operational workflows demand it.

## 2. Distinguishing Public and Private Subnets

A subnet does not become a public subnet simply because its name contains the word "public". What determines it is the route table and IP address configuration:

- A public subnet typically has a default IPv4 route to an Internet Gateway. Resources that need direct access from the Internet must also have a public IPv4 address or appropriate public addressing mechanism and security rules allowing traffic.
- A private subnet has no direct route to an Internet Gateway. Virtual machines typically have only private IPs. If outbound Internet connectivity is required, the default route can point to a NAT Gateway placed in a public subnet.
- A private subnet may also have no default route to the Internet. In that case, only internal networks and services via VPC endpoints are accessible according to the configured routes.

A NAT Gateway allows resources in a private subnet to initiate outbound connections; it does not provide new inbound connections from the Internet to the virtual machine. If a virtual machine needs to download packages or update its OS, a NAT Gateway is an option. If it only needs to access supported AWS services, VPC endpoints can reduce dependence on the Internet and NAT.

A private subnet should not be treated as the sole security boundary. Security groups, network ACLs, IAM, encryption, patch management, and appropriate outbound controls are still required.

## 3. Planning VPC, Subnets, and Routing

For the lab, the following addressing scheme can be used:

| Component | Example CIDR | Role |
|---|---|---|
| VPC | 10.20.0.0/16 | Private address space for workloads |
| Public subnet | 10.20.1.0/24 | Hosts NAT Gateway or bastion if needed |
| Private subnet | 10.20.11.0/24 | Hosts virtual machines without public IP |
| VPC endpoint subnet | Use private subnet or application subnet per design | Hosts network interfaces of interface endpoints |

The CIDRs are examples only. Before creating the network, cross-check against office networks, VPNs, other VPCs/VNets, and partner-connected networks to avoid address space overlap.

Sample route table:

| Route table | Destination | Target |
|---|---|---|
| Public route table | 10.20.0.0/16 | local |
| Public route table | 0.0.0.0/0 | Internet Gateway |
| Private route table | 10.20.0.0/16 | local |
| Private route table | 0.0.0.0/0 | NAT Gateway, if outbound Internet is needed |

In production environments, a NAT Gateway is typically placed in each Availability Zone, and the private subnet in that AZ routes to the NAT Gateway in the same AZ to increase availability, reduce cross-AZ dependencies, and control data transfer costs. For a single-AZ lab, one NAT Gateway may suffice for demonstration, but it introduces a single point of failure and still incurs hourly and data processing charges.

If not using NAT, create interface VPC endpoints for the required Systems Manager services. Typically, you need endpoints for Systems Manager and the agent messaging channel; the specific endpoints depend on the agent version, region, and services used. Enable private DNS where appropriate, and allow HTTPS 443 from the virtual machine's security group to the endpoint's security group. If S3, CloudWatch Logs, KMS, or other services are needed, add corresponding endpoints based on actual traffic flows.

## 4. Creating Security Groups for the Virtual Machine

A security group is a stateful firewall attached to a network interface. With the Session Manager approach, the virtual machine does not need inbound rules for TCP 22 or TCP 3389.

A minimal configuration could be:

| Direction | Protocol/port | Source or destination | Purpose |
|---|---|---|---|
| Inbound | No administrative rules | — | Do not accept direct SSH/RDP |
| Outbound | TCP 443 | Security group of SSM interface endpoints | Allows SSM Agent to connect to management service |
| Outbound | Per application needs | Approved target security group or CIDR | Connects to databases, APIs, or internal services |

If using NAT to update the OS or download dependencies, design outbound rules suitable for the required repositories and services. Avoid overly broad outbound rules if the organization requires egress filtering.

The endpoint's security group must allow inbound TCP 443 from the virtual machine's security group. DNS within the VPC must function so the virtual machine resolves endpoint names to private IPs. Security groups are stateful, so return traffic for allowed connections is permitted automatically; network ACLs are stateless and require rules for both inbound and outbound directions, including ephemeral ports when needed.

## 5. Preparing Administrative Permissions with Systems Manager

To manage EC2 with Session Manager, both the virtual machine's permissions and the operator's permissions must be prepared.

**Virtual machine permissions:**

1. Create an IAM role for EC2.
2. Attach an instance profile containing that role.
3. Grant the AWS-supported policy for Systems Manager, typically using `AmazonSSMManagedInstanceCore` as a starting point.
4. Ensure SSM Agent is installed and running. Many common Amazon Machine Images include the agent pre-installed, but you must verify based on the selected OS and image.
5. Ensure the virtual machine has outbound HTTPS connectivity to the Systems Manager endpoints via NAT or interface VPC endpoints.

**Administrator permissions:**

- Administrative users or roles must be granted permissions to start, resume, and terminate sessions scoped to permitted instances and session documents.
- Use IAM Identity Center or a centralized identity mechanism, MFA, and role-based permission groups.
- Scope permissions by tag, account, environment, or resource ARN to prevent everyone from accessing every machine.
- Enable session logging to CloudWatch Logs or S3 if required by operational policy; consider KMS encryption and separate log-reading permissions.

Do not attach broad administrative permissions to the instance role just to troubleshoot connectivity issues. The instance role is the identity of the workload; the user permission to start a session is the identity of the operator. These two permission sets must be managed separately.

## 6. Creating the Virtual Machine in a Private Subnet

Before running the command, prepare the following values:

- An AMI ID compatible with the region and architecture.
- The private subnet ID.
- A security group without inbound SSH/RDP rules.
- An instance profile with Systems Manager permissions.
- An instance type appropriate for the workload and budget.

AWS CLI example:

~~~bash
aws ec2 run-instances   --image-id ami-xxxxxxxxxxxxxxxxx   --instance-type t3.small   --subnet-id subnet-private-xxxxxxxx   --security-group-ids sg-private-xxxxxxxx   --iam-instance-profile Name=ec2-ssm-instance-profile   --no-associate-public-ip-address   --metadata-options HttpTokens=required   --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=private-admin-vm},{Key=Environment,Value=lab}]'
~~~

Replace the placeholders with actual IDs in your lab account and region. The command requests no public IPv4 address for the instance and enforces IMDSv2 for instance metadata access. The AMI must have a compatible SSM Agent and a network configuration that reaches the Systems Manager endpoints.

After creation, retrieve the instance ID from the command output. Wait for the instance state to become `running` and verify that status checks have passed before opening an administrative session.

## 7. Opening an Administrative Session via Session Manager

From an administrative workstation logged into AWS CLI with an authorized IAM role or profile:

~~~bash
aws ssm describe-instance-information   --filters Key=InstanceIds,Values=i-0123456789abcdef0
~~~

The output should indicate that the instance is recognized by Systems Manager as a managed node and its connection status is online. Then open a session:

~~~bash
aws ssm start-session --target i-0123456789abcdef0
~~~

The administrative workstation needs the AWS CLI and the Session Manager plugin as required by the environment. Once the session opens successfully, the administrator gets a shell on the virtual machine with the configured OS permissions. On Linux, you can verify:

~~~bash
hostname
whoami
ip addr
ip route
systemctl status amazon-ssm-agent
~~~

The agent status command may vary depending on the distribution or installation method. On Windows, Session Manager or Fleet Manager can be used depending on service capabilities. If RDP access to a private Windows machine is needed, port forwarding over a session can be used per permitted policy instead of opening port 3389 to the Internet.

Session Manager does not automatically grant root or Administrator privileges to everyone opening a session. Define OS accounts, elevated privileges, sudo/UAC procedures, and command controls according to organizational policy.

## 8. Bastion Host Approach When SSH/RDP Is Required

Some legacy systems or operational tools require direct SSH/RDP protocols. In those cases, a bastion host can be used as an intermediary:

1. Place the bastion in a public subnet or in a private management network with a VPN.
2. If the bastion has a public IP, allow SSH/RDP only from approved VPN IP ranges or administrative IPs. Do not open administrative ports to 0.0.0.0/0.
3. The private virtual machine's security group must allow the administrative port only from the bastion's security group, not from the entire Internet.
4. Use short-lived keys or certificates, MFA at the access layer, individual accounts, and session logging.
5. Keep the bastion OS patched, monitor logins, restrict outbound traffic, and deploy redundantly if the bastion is a critical component.

The advantage of a bastion is compatibility with SSH/RDP and existing administrative tools. In return, the operations team must patch, protect credentials, monitor, and maintain the availability of the bastion. A single bastion can become a single point of failure and a concentrated attack target.

With Session Manager, the administrative path does not require inbound SSH/RDP to the virtual machine. With a bastion, the virtual machine remains in a private subnet but requires an inbound rule from the bastion. Do not keep multiple administrative paths open simultaneously without a clear need and explicit controls.

## 9. Mapping to Azure and Google Cloud

| Platform | Private virtual machine | Common administrative channel | Outbound connectivity |
|---|---|---|---|
| AWS | EC2 in private subnet, no public IP | Systems Manager Session Manager; bastion when needed | NAT Gateway or VPC endpoints |
| Azure | VM in VNet subnet, no public IP attached | Azure Bastion, or private management solution per policy | NAT Gateway, Azure Firewall, or private endpoints depending on service |
| Google Cloud | Compute Engine VM without external IP | IAP TCP forwarding combined with IAM and OS Login | Cloud NAT or Private Google Access/private connectivity depending on destination |

Service names and configuration steps differ, but the principles are the same: virtual machines use private IPs, administrative permissions are granted via centralized identity, firewalls open only necessary flows, and outbound traffic is controlled. Refer to each platform's documentation to verify IAM roles, firewall source ranges, agents, endpoints, and logging.

## 10. Verification and Troubleshooting

After creating the virtual machine, check both the network configuration and management status.

**Verify subnet placement and absence of public IP:**

~~~bash
aws ec2 describe-instances   --instance-ids i-0123456789abcdef0   --query 'Reservations[].Instances[].{State:State.Name,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,Subnet:SubnetId,Vpc:VpcId,Profile:IamInstanceProfile.Arn}'
~~~

`PublicIP` should be empty or not returned. The subnet and VPC must match the design. Continue checking the route table associated with the subnet to confirm there is no direct route to an Internet Gateway.

**Verify permissions and agent:**

- The instance has the correct instance profile.
- The IAM role contains the required policy.
- SSM Agent is running and the instance appears in the managed nodes list.
- DNS resolves endpoints properly; routes and security groups allow HTTPS 443.
- The administrator has permission to start sessions and sessions are logged as required.

**Common errors:**

| Symptom | Possible cause | How to check |
|---|---|---|
| Instance does not appear in Systems Manager | Missing instance profile, policy, or agent not running | Check IAM role, agent status, and agent logs |
| Managed node offline | No route to endpoint, DNS failure, or outbound 443 blocked | Check NAT/VPC endpoint, private DNS, security group, and network ACL |
| User cannot open session | IAM caller lacks permissions or restricted by session policy | Check `StartSession` permission, resource scope, and document |
| SSH to private VM fails | No VPN/bastion path or security group does not allow source | Check routes, peering/VPN, and rule from bastion security group |
| VM cannot update packages | No outbound path to repositories or missing DNS/NAT/egress rule | Check routes, NAT, DNS, and egress policy |
| Administrative session opens but lacks elevated privileges | OS account is not granted sudo/Administrator | Check OS groups and privilege escalation policy |

Do not remediate by opening SSH/RDP from the Internet or granting unrestricted Administrator/root access. Identify the exact layer causing the issue: identity, agent, DNS, routing, firewall, or OS permissions.

## 11. Handover Checklist

- [ ] VPC/VNet CIDR does not conflict with connected networks.
- [ ] Private subnet has no direct route to an Internet Gateway.
- [ ] Virtual machine has a private IP and no public IP.
- [ ] Security group does not open inbound SSH/RDP from the Internet.
- [ ] Outbound routes meet only update and service access requirements.
- [ ] Instance profile and IAM role are granted the proper Systems Manager permissions.
- [ ] SSM Agent is active and can reach the required endpoints.
- [ ] Administrators use individual identities, MFA, and least-privilege permissions.
- [ ] Sessions are logged and retained per policy.
- [ ] Tested administrative access, verified IP/routes, and checked common failure modes.
- [ ] Recorded AMI, instance type, subnet, security group, IAM role, and operational owner.

## Conclusion

A virtual machine in a private subnet reduces the attack surface by not accepting direct administrative connections from the Internet. A complete design must coordinate subnets and route tables, private IPs, security groups, outbound access via NAT or endpoints, IAM identities, and a logged administrative channel. Session Manager is a convenient choice when supported by the platform; a bastion can still satisfy SSH/RDP requirements but must be hardened and operated as a critical infrastructure component.