# Troubleshooting SSH, Routing, NSGs, and DNS

## 1. Objectives and Scope

This lesson belongs to the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_ORACLE** module, focusing on Oracle Cloud Infrastructure (OCI). We combine knowledge of tenancy, compartment, IAM, VCN, and Compute to pinpoint the failure point on a connection, then restore it with verifiable and reversible changes.

After this lesson, you can:

- Distinguish between name resolution failures, TCP establishment failures, and SSH authentication failures.
- Trace outbound and return paths across route tables, gateways, NSGs, Security Lists, and the operating system.
- Troubleshoot DNS within a VCN, across VCNs, and between OCI and on-premises networks.
- Use evidence from the client, target host, and OCI tools to choose the right change.
- Record results, update automation configurations, and clean up diagnostic resources to control costs.

The examples primarily target standard Linux Compute instances. For DB Systems or managed database services, IP, route, and DNS checks remain useful; OS access and connection methods must follow the specific service type. A successful TCP connection to a database port does not confirm credentials, TLS, wallet, or database service health.

## 2. Define the Connection to Troubleshoot

### 2.1. Diagram the Path Before Making Changes

A direct SSH session over IPv4 can be pictured as follows:

```text
Client
  | resolves hostname to IP address
  | TCP from ephemeral port to SSH port
  v
Client network / VPN / corporate firewall
  v
VCN Internet Gateway + public IP mapping
  v
Target VNIC: Security Lists and applied NSGs
  v
OS firewall -> sshd -> account and authorized_keys
  ^
  | response requires a return path and permission at every control layer
```

This is a diagram for fault isolation, not an exact representation of OCI's internal packet-processing order. If accessing a private IP over VPN, FastConnect, or Bastion, replace the Internet segment with the actual access path.

Use a consistent address set throughout this lesson:

| Component | Illustrative Value | Role |
| --- | --- | --- |
| VCN | `10.20.0.0/16` | Application network |
| Management subnet | `10.20.10.0/24` | Hosts jump host in self-managed model |
| Jump host | `10.20.10.5` | Forwards SSH to application host |
| Application subnet | `10.20.20.0/24` | Private subnet |
| Application Compute | `10.20.20.10` | Host to troubleshoot |
| Public IP of a public test host | `198.51.100.20` | SSH test target from Internet |
| Client egress public IP | `203.0.113.10` | Source for Internet rules |
| On-premises DNS | `172.16.0.53` | DNS of network connected via DRG |
| Application FQDN | `app01.app.learnvcn.oraclevcn.com` | Illustrative name based on DNS label |

The public addresses in this table are for documentation only and not for real connections. Replace them with verified addresses, hostnames, and ports in your environment. Default SSH port is 22; if changed, update commands and rules consistently.

### 2.2. Record a Reproducible Attempt

Before testing, record:

1. Timestamp and time zone; command executed; verbatim error message.
2. Region, compartment, and OCIDs of the instance, VNIC, subnet, and VCN involved.
3. Actual source IP after NAT/VPN; destination IP; IPv4 or IPv6; protocol and port.
4. Access method: public IP, private IP via corporate network, jump host, or OCI Bastion.
5. Most recent changes: routes, NSGs, DHCP options, image, SSH key, or OS config.
6. Impact scope: one client, one host, one subnet, or multiple applications.

Example of a concrete SSH attempt:

```text
Timestamp: <UTC timestamp of attempt>
Source at OCI edge: 203.0.113.10:<port chosen by client/NAT>
Public destination: 198.51.100.20:22/TCP
Corresponding private IP: <private IP verified on VNIC>
Result: Connection timed out after ~5 seconds
Most recent change: updated admin IP allowlist
```

Permission to view an instance in the Console is an OCI resource permission. SSH login also depends on OS accounts and keys inside the guest. If you encounter `NotAuthorizedOrNotFound` when viewing network resources, verify region, OCID, and IAM with an administrator; do not treat not seeing a resource as proof it was deleted.

## 3. Classify Symptoms from the Client

### 3.1. Use Error Messages to Choose the Layer to Check

| Symptom | Existing Evidence | Check Next |
| --- | --- | --- |
| `Could not resolve hostname` | Client has no address to connect to | Resolver, hostname, search domain, DNS records |
| `Connection timed out` | TCP handshake not completed within timeout | Destination IP, forward/return paths, rules, firewall, host state |
| `No route to host` or `Network is unreachable` | Routing error or network error reply received | Client/OS routes, VPN, gateways; do not assume NSG alone |
| `Connection refused` | Active rejection response received | Wrong IP/port, service not listening, or firewall REJECT |
| `Permission denied (publickey)` | Reached SSH service and authentication phase | Username, key, file permissions, SSH config |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Host key differs from client's cached value | Verify host identity via trusted management channel |
| Handshake completes but data stalls | Basic path works | MTU, packet loss, OS resources, stateful connection tracking |

A single message only helps prioritize hypotheses. For example, a timeout can occur because the target host's OS firewall drops packets even when routes and NSGs are correct. Oracle provides dedicated guidance for common SSH error groups in [Troubleshooting the SSH Connection](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-ssh-connection.htm).

### 3.2. Separate the TCP Test from the SSH Test

On Linux with OpenSSH and an `nc` variant supporting the options below:

```bash
nc -vz -w 5 198.51.100.20 22

ssh -vvv -o ConnectTimeout=5 -o ConnectionAttempts=1 \
  -o IdentitiesOnly=yes -i ~/.ssh/oci_lab_key \
  opc@198.51.100.20
```

On Windows PowerShell:

```powershell
Test-NetConnection -ComputerName 198.51.100.20 -Port 22 -InformationLevel Detailed

ssh -vvv -o ConnectTimeout=5 -o ConnectionAttempts=1 -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\oci_lab_key" opc@198.51.100.20
```

`TcpTestSucceeded: True` only indicates that the TCP connection succeeded; it does not test SSH keys. The source address shown on the client may be a LAN or VPN IP, differing from the post-NAT public IP seen by OCI.

In `ssh -vvv` logs, look for TCP connection establishment, SSH version exchange, key offer, and key acceptance. The `-i` option selects the key file; `IdentitiesOnly=yes` avoids trying unintended identities. Refer to option usage in [OpenSSH ssh(1)](https://man.openbsd.org/ssh).

Test the numeric IP first, then test the hostname over the same access path. If TCP to the IP succeeds while the hostname fails to resolve, prioritize the DNS branch. Do not treat ping as a mandatory prerequisite: ICMP and TCP/22 may be permitted differently.

## 4. Troubleshoot Routing on OCI and in the OS

### 4.1. Direct Connection via Public IPv4

Check simultaneously:

- The right instance and the right VNIC/private IP with the public IP attached are being used.
- The subnet allows public IPs; the "public subnet" label alone does not guarantee an instance has a public IP.
- An Internet Gateway exists and is enabled.
- The effective route table has a path to the client via the Internet Gateway; the common configuration is `0.0.0.0/0 -> Internet Gateway`.
- Security rules and the OS permit the required traffic.

A public IP is an OCI-provided mapping; when running `ip addr` inside the guest, you normally see the VNIC's private IP. Verify the mapping on OCI rather than manually assigning the public IP inside the OS. Direct Internet access requirements are described in [Internet Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingIGs.htm).

A common real-world mistake is editing the right rule in one route table while the subnet uses a different table. In addition to the subnet-attached table, check route tables attached directly to the VNIC or private IP if the environment uses **per-resource routing**.

Routes prioritize longer prefixes. For example, in the effective table:

| Destination | Target | Effect When Destination Is `203.0.113.10` |
| --- | --- | --- |
| `0.0.0.0/0` | Internet Gateway | General default route |
| `203.0.113.0/24` | DRG | Selected route because it is more specific |

The host may receive SYN via the public IP yet send replies toward the DRG according to the second route. Compare configuration against the expected return path rather than checking only for the existence of a default route. See route selection rules and per-resource routing in [VCN Route Tables](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingroutetables.htm).

### 4.2. Private Hosts Require a Private Access Path

A NAT Gateway lets resources without public IPs initiate outbound Internet connections and receive replies. It does not provide port forwarding for Internet clients to initiate SSH into private hosts. Therefore, `0.0.0.0/0 -> NAT Gateway` does not enable SSH from a laptop to a private IP. See [NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm).

Choose the designed access path:

| Access Path | Points to Check |
| --- | --- |
| Self-managed jump host | Client to jump host; then jump host to target private IP |
| VPN/FastConnect | Client-side routes, on-premises network, DRG, and VCN; both directions |
| OCI Bastion | Session, CIDR allowlist, endpoint, and connectivity to target |
| Cloud Shell via private networking | Configured private network and corresponding usage permissions |

Example with a self-managed jump host when both hops use the same identity:

```bash
ssh -J opc@198.51.100.20 \
  -o IdentitiesOnly=yes -i ~/.ssh/oci_lab_key \
  opc@10.20.20.10
```

If the two hops use different keys, configure each host in SSH config. Do not copy private keys onto the jump host. This is the self-managed jump host model; OCI Bastion provides session-specific connection commands.

For OCI Bastion, verify the session is active and the client's egress public IP is in the allowlist. Managed SSH requires OpenSSH, Oracle Cloud Agent, and the Bastion plugin on the target; port forwarding has different requirements. If using port forwarding to reach SSH, the target host must still have a running SSH server. Refer to [Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

For VPN/FastConnect, check advertised CIDRs, DRG attachment route tables, VCN routes, and on-premises routes. Overlapping CIDRs or missing return routes can cause tests to fail even when the tunnel displays UP.

### 4.3. Inspect Routing Decisions Inside the Guest

Run the following commands **inside the instance**, via an active session or authorized console channel:

```bash
ip -br addr
ip route
ip rule show
ip route show table all
ip route get 203.0.113.10
```

`ip route get` helps identify which interface and source IP Linux intends to choose. It does not display the Internet Gateway, NAT Gateway, or full OCI routes. With multiple VNICs, check source IP, policy routing, and whether return traffic traverses the intended interface.

Two subnets in the same VCN normally have local routing built in; you do not need to add an Internet default route for them to communicate via private IPs. If traffic is routed through a firewall appliance or custom routes are configured, inspect that new path.

Do not add random OS routes just because SSH timed out. First determine whether the fault lies in guest routing or infrastructure routing.

## 5. Troubleshoot NSGs and Security Lists

### 5.1. Find the Exact Effective Rule Set

Security Lists attach to a subnet and apply to VNICs in that subnet. Therefore, modifying a shared Security List can affect multiple hosts. See [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm).

NSGs apply to VNICs or resources added to the group. Creating an NSG with the right rules but forgetting to attach it to the target VNIC means the rules neither protect nor allow traffic for that VNIC. Hosts with multiple VNICs must be checked on the exact VNIC receiving traffic. NSGs also allow referencing source/destination NSGs within the same VCN. See [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

For NSGs and Security Lists, allow rules are combined as a union on the VNIC; there is no ordered deny/allow list like numbered ACLs. Removing an SSH rule from an NSG does not revoke SSH if a Security List still permits it.

For a public test host, a minimal stateful ingress rule might look like:

| Attribute | Illustrative Value |
| --- | --- |
| Direction | Ingress |
| Source type | CIDR |
| Source | `203.0.113.10/32` |
| Protocol | TCP |
| Source port | All |
| Destination port | `22` |
| Stateless | No |

Clients normally use ephemeral source ports. Setting source port to 22 will not match most client-initiated SSH sessions.

If using a jump host over private IP, the source observed at the target is typically the jump host's private IP. With OCI Bastion, verify the Bastion private endpoint as the source on the hop to the target; do not assume the laptop's public IP applies at every hop.

### 5.2. Distinguish Stateful and Stateless Rules

Stateful rules track connections and automatically permit matching return traffic; you do not need to open all egress just to reply to a tracked ingress connection. Stateless rules require explicit permission for the return direction. When traffic in the same direction matches both types, stateless takes precedence and does not create stateful tracking.

Example stateless rule pair for SSH to the test host:

| Direction at Server VNIC | Peer CIDR | Source Port | Destination Port |
| --- | --- | --- | --- |
| Ingress TCP | Source `203.0.113.10/32` | All | `22` |
| Egress TCP | Destination `203.0.113.10/32` | `22` | All |

You can narrow the return destination port if the actual port range is verified, including NAT. Rules for combining policies, state tracking, and stateless exceptions are covered in [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Check both source and destination sides: the jump host's egress NSG can also block SYN before it reaches the server. A successful test on an already-open SSH session does not confirm a new session can connect; open a new session after making changes.

If the endpoint uses **Zero Trust Packet Routing (ZPR)** security attributes, check the corresponding ZPR policies alongside NSGs/Security Lists. This is an additional control layer noted in the [NSG documentation](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

## 6. Check SSH and Firewall Inside the Target Host

### 6.1. Is a Process Listening?

On Oracle Linux with systemd:

```bash
sudo ss -lntp
sudo systemctl status sshd --no-pager
sudo journalctl -u sshd --since "15 minutes ago" --no-pager
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T
df -h
df -i
```

On Ubuntu, the service unit is typically `ssh`; check the actual unit and socket activation mechanism of your image. Corresponding examples:

```bash
sudo systemctl status ssh --no-pager
sudo journalctl -u ssh --since "15 minutes ago" --no-pager
```

Read the output against concrete questions:

- Is the right port in LISTEN state? Is it listening on the private IP, all addresses, or only loopback?
- Do logs show syntax errors, missing host keys, user rejections, or connection limits?
- Are filesystems or inodes full, causing service or login failures?
- Is effective configuration altered by included files or `Match` blocks?

`sshd -t` validates configuration before applying; `sshd -T` prints effective configuration and can be combined with `-C` to evaluate connection conditions in Match blocks. See [OpenSSH sshd(8)](https://man.openbsd.org/sshd.8).

If SSH configuration must be changed, keep an administrative session open, back up configuration per operational procedure, test syntax, and apply using OS mechanisms. Test a new login session before closing the existing one.

### 6.2. The OS Firewall Is an Independent Layer

Choose commands matching the firewall managed on the image; do not assume every tool is installed:

```bash
# firewalld: identify the zone attached to the interface first.
sudo firewall-cmd --get-active-zones

# Example only when the interface actually belongs to the public zone:
sudo firewall-cmd --zone=public --list-all

# If the system uses nftables:
sudo nft list ruleset

# If the system uses iptables:
sudo iptables -S
sudo iptables -L -n -v
```

Look for rules applying to the exact interface, source, port, and evaluation order. Do not disable the entire firewall or flush the ruleset just to test connectivity. An incrementing packet counter on a DROP/REJECT rule while testing SSH is much stronger evidence than simply seeing an allow rule in another chain.

Do not mix manual edits across multiple tools if the firewall is owned by a service or configuration management system.

### 6.3. When TCP Succeeds but the Key Is Rejected

On common platform images, Oracle Linux normally uses `opc` and Ubuntu uses `ubuntu`; custom images may differ. The client's private key must match a public key provisioned for the target account. On Windows, check the private key's ACL per OS guidance; `chmod` in Linux examples does not replace checking Windows ACLs. See [Connecting to a Linux Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm).

Example checks on Oracle Linux:

```bash
# Linux client:
chmod 600 ~/.ssh/oci_lab_key

# On target, check default path for the opc account:
sudo namei -l /home/opc/.ssh/authorized_keys
sudo stat -c '%U:%G %a %n' \
  /home/opc /home/opc/.ssh /home/opc/.ssh/authorized_keys
sudo ssh-keygen -lf /home/opc/.ssh/authorized_keys
```

Check ownership of home, `.ssh`, and `authorized_keys`; overly permissive write permissions; wrapped or truncated public key lines; locked accounts; and authentication logs. If SELinux is enabled, check contexts and related logs before modifying. The authorized keys path may also have been changed in SSH config.

You can compare fingerprints without uploading the private key to the server:

```bash
# Client: extract the corresponding public key, then compute fingerprint.
ssh-keygen -y -f ~/.ssh/oci_lab_key | ssh-keygen -lf -
```

If the host key changed, verify the fingerprint via a trusted console, for example with an Ed25519 host key:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Only after confirming the machine was rebuilt or the host key was legitimately rotated should you update the corresponding entry in `known_hosts`. Do not disable host key checking to bypass warnings. Fingerprint options and host key management are described in [OpenSSH ssh-keygen(1)](https://man.openbsd.org/ssh-keygen).

### 6.4. When All SSH Paths Are Lost

Instance Console Connection supports viewing and troubleshooting via serial console or VNC console, with dedicated IAM and connection requirements. Console history can also help identify boot failures. A console connection does not automatically grant a logged-in root session.

Use the appropriate recovery workflow to inspect the OS, firewall, and SSH; prioritize identifying the cause before rebooting. Rebooting loses volatile evidence and can disrupt applications. Refer to [Troubleshooting Instances Using Instance Console Connection](https://docs.oracle.com/en-us/iaas/Content/Compute/References/serialconsole.htm).

## 7. Troubleshoot DNS from Application to Resolver

### 7.1. Identify the Resolver and Queried Name

Run inside the failing host, not just on the administrator's laptop:

```bash
cat /etc/resolv.conf

# Present on many systems using systemd-resolved:
resolvectl status

# Goes through the OS name resolution mechanism:
getent ahostsv4 app01.app.learnvcn.oraclevcn.com

# Query DNS explicitly specifying FQDN and record type:
dig app01.app.learnvcn.oraclevcn.com. A +time=2 +tries=1
dig app01.app.learnvcn.oraclevcn.com. AAAA +time=2 +tries=1

# Compare against OCI's default resolver from inside the instance:
dig @169.254.169.254 app01.app.learnvcn.oraclevcn.com. A +time=2 +tries=1
```

If a tool is missing, use an equivalent built-in utility or install it via an approved workflow; avoid changing DNS just to install tools. On Windows:

```powershell
Resolve-DnsName -Name app01.app.learnvcn.oraclevcn.com -Type A
Resolve-DnsName -Name app01.app.learnvcn.oraclevcn.com -Type A -Server 169.254.169.254
```

Queries targeting `169.254.169.254` must be run from an appropriate OCI environment; a laptop outside OCI has no direct route to this link-local resolver.

`getent` reflects the OS lookup order, which can include `/etc/hosts`; `dig` queries DNS directly and does not fully represent how every application resolves names. If `resolv.conf` points to `127.0.0.53`, that may be a local stub resolver; inspect upstream servers with the resolver management tool. A trailing dot on the FQDN avoids interference from search suffixes.

### 7.2. Distinguish DNS Responses

| Result | Meaning to Understand | Investigation Path |
| --- | --- | --- |
| `NOERROR`, with answer | Query returned an answer | Is the IP correct; test TCP to that IP |
| `NOERROR`, missing requested record type | Name may still exist | Test A/AAAA/CNAME properly; inspect answer and authority |
| `NXDOMAIN` | Resolver reports the name does not exist in queried context | Spelling, zone/view, shadowed names, negative cache |
| `SERVFAIL` | Resolver could not complete processing | Upstream, forwarding, DNSSEC, server failure |
| `REFUSED` | Server refused to process query | Query policy or recursion restriction |
| Timeout, no response | No DNS reply received | Resolver IP, routes, UDP/TCP, firewall |

DNS response codes are defined in [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html). A timeout is not an `NXDOMAIN` code.

Read `SERVER`, status, answer, authority, and TTL together. Looking only at `dig +short` can omit details needed to distinguish the cases above.

### 7.3. DNS Inside a VCN

An instance's system name is formed from its hostname and the subnet/VCN DNS labels; display name is not always that hostname. The Internet and VCN Resolver can resolve public names even when an instance has no Internet path for application traffic. Therefore:

- Resolving a public name does not confirm outbound HTTPS or SSH to the Internet works.
- Changing the hostname inside the OS does not automatically update OCI-managed DNS records.
- Changing DHCP options requires the client to renew/re-read them; inspect active settings inside the guest.

Do not make persistent edits to `/etc/resolv.conf` if DHCP or an OS service regenerates it. Refer to [DNS in a Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns.htm).

For custom private zones, verify the record exists in the right zone and private view, and that the view is attached to the resolver of the VCN from which the client queries. Private DNS resolvers use views, zones, and rules to answer, not merely IP reachability between two hosts. See [Private DNS Resolvers](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-Private-resolver.htm).

To test a case where one host succeeds and another fails, build a comparison table:

| Test Host | Subnet | Actual Resolver | Identical Query | Result |
| --- | --- | --- | --- | --- |
| app01 | app | OCI Resolver | `db.internal.example. A` | Private IP |
| app02 | app | Legacy custom DNS | `db.internal.example. A` | NXDOMAIN |

This illustrative table generates a hypothesis of differing resolver configurations; verify actual state before changing anything. After fixing a record or resolver, account for TTL, negative caching, OS caches, and application-runtime caches.

## 8. DNS Across VCNs and With On-Premises Networks

### 8.1. Distinguish Listening Endpoints and Forwarding Endpoints

- A **listening endpoint** receives queries from other networks into the VCN's resolver.
- A **forwarding endpoint** sends queries from the OCI resolver to target DNS servers according to rules.
- Instances querying `169.254.169.254` do not need a listening endpoint created just for that lookup.

Endpoints have IPs in a subnet and must be evaluated alongside corresponding routing, NSGs, and Security Lists. Do not use a VCN's link-local resolver as a direct target DNS address for on-premises hosts. See [Resolver Endpoints](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_endpoints.htm).

A forwarding flow to an on-premises network:

```text
OCI application
  -> VCN resolver
  -> rule matching corp.example
  -> forwarding endpoint
  -> VCN route / DRG / VPN or FastConnect
  -> DNS 172.16.0.53
  -> response along return path
```

To troubleshoot a typical endpoint DNS hop, check at minimum:

| Control Point | Query to Allow | Response to Allow |
| --- | --- | --- |
| OCI forwarding endpoint | Egress to target DNS, destination port 53 | From target DNS, source port 53 |
| OCI listening endpoint | Ingress from allowed DNS/clients, destination port 53 | To DNS/clients, source port 53 |
| On-premises firewall/DNS | Queries from the endpoint's actual source IP | Replies back to query source |

Check both UDP and TCP. With stateless rules, you must have explicit return rules targeting the requester's ephemeral ports; with stateful rules, check connection state and tracking limits. Oracle provides dedicated guidance for [Private DNS network connectivity issues](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/troubleshooting_network-connectivity.htm).

From a test host with a path to on-premises DNS:

```bash
dig @172.16.0.53 host01.corp.example. A +time=2 +tries=1
dig @172.16.0.53 host01.corp.example. A +tcp +time=2 +tries=1
```

Testing from a Compute host only tests that host's source path. It does not replace testing the forwarding endpoint, because routes, source IPs, and rules can differ.

DNS requires TCP support alongside UDP; blocking TCP/53 can break queries, especially when falling back to TCP for truncated responses. See [RFC 7766 — DNS Transport over TCP](https://www.rfc-editor.org/rfc/rfc7766.html).

### 8.2. Check Views and Forwarding Order

Private DNS evaluates private views first, then resolver rules, then the Internet when no prior match exists. A private zone `example.com` can return `NXDOMAIN` for `host01.corp.example.com` and shadow a forwarding rule for `corp.example.com`.

When using custom DHCP settings, verify the requirement to include `169.254.169.254` in the nameserver list to query private views/rules per OCI guidance. These cases are explained in [Common Private DNS Issues](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/troubleshooting_general.htm).

Resolver rules are evaluated in order; a matching rule forwards the query and does not try subsequent rules simply because the target DNS fails. Two rules with identical conditions do not automatically provide failover. See [Resolver Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_rules.htm).

When troubleshooting, record separately the queried name, views/zones that could match, the first matching rule, and the target DNS. Check for forwarding loops if OCI DNS and on-premises DNS forward the same suffix to each other. Successful network connectivity between two VCNs does not confirm private DNS sharing or forwarding is configured properly.

## 9. Combine OCI Tools with In-Guest Evidence

### 9.1. Network Path Analyzer

Create an analysis specifying exact source, destination, protocol, source/destination ports if needed, and check direction. For TCP/UDP, bidirectional analysis helps detect return-path issues.

Network Path Analyzer analyzes configuration; it does not send real packets and does not inspect the `sshd` process, in-guest firewall, or user keys. Results also depend on permissions to view involved resources. If the tool reports an available path while SSH still fails, switch to runtime evidence. See [Network Path Analyzer](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/path_analyzer.htm).

### 9.2. VCN Flow Logs

Enable capture at the VNIC or appropriate scope, filtering by source, destination, and time range of the test attempt. Flow Logs show traffic accepted or rejected by OCI network security rules; sampling and capture filters affect recorded data. See [Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

- `REJECT` is evidence to inspect rules on the corresponding VNIC.
- `ACCEPT` does not confirm the OS firewall allowed it or the application processed it.
- Missing records do not prove absence of traffic: check log enablement point, filters, sampling, and time window.

Some link-local traffic such as VCN DNS, DHCP, and block storage does not appear in Flow Logs. Do not treat the absence of logs for `169.254.169.254` queries as proof that an NSG blocked DNS. See [Details for VCN Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_vcn_flow_logs.htm).

### 9.3. Scoped Packet Capture

If authorized and tools exist inside the guest, capture packets during the exact test attempt with a bounded packet count:

```bash
# On SSH target:
sudo tcpdump -ni any -c 40 'tcp port 22'

# On host sending DNS query:
sudo tcpdump -ni any -c 40 '(udp port 53 or tcp port 53)'
```

| Observation During New SSH Attempt | Prioritized Hypothesis |
| --- | --- |
| No SYN seen on guest | Wrong target or blocked before capture point; check interfaces/filters |
| Repeated incoming SYN, no SYN-ACK | OS firewall, listener, or return path |
| Incoming SYN, repeated outgoing SYN-ACK, missing ACK | Reply not reaching client or blocked by client |
| Handshake completes, then publickey error | Drill into username, keys, and SSH policies |

These are packet-level inferences at the observation point and must be cross-checked with configuration and logs. If MTU is suspected, check packet sizes, retransmissions, and ICMP notices along the real path; do not change system-wide MTU based solely on one hung session.

## 10. End-to-End Troubleshooting Workflow

1. **Pin the target:** right tenancy, region, compartment, instance, and VNIC; record actual source/destination IPs.
2. **Minimal reproduction:** one time-bounded TCP check and one SSH check; record timestamps.
3. **Isolate DNS:** compare hostname against numeric IP; record resolver and A/AAAA results.
4. **Inspect routing:** client path, OCI effective route tables, gateways, and return path.
5. **Inspect security:** NSG/Security List union on each VNIC, stateful/stateless, ZPR layer if applicable.
6. **Inspect guest:** listener, firewall, OS routes, services, and authentication logs.
7. **Correlate evidence:** Network Path Analyzer, Flow Logs, and packet capture when needed.
8. **Fix one proven cause:** record before/after configuration and rollback steps.
9. **Verify recovery:** new connection over the original access path; check dependent services too.
10. **Close operationally:** revoke test rules/sessions, sync IaC, and record recurrence prevention.

Do not change DNS, NSGs, and routes simultaneously in a single test. If multiple components need fixes, apply them step by step with separate observable checks so you know which change resolved which cause.

## 11. Illustrative Scenarios

### 11.1. Network Change Causes Public SSH Timeout

**Observation:** instance is running; others can still SSH. The client just switched to a new Internet connection.

**Hypothesis:** post-NAT source public IP changed and no longer matches the management CIDR.

**How to verify:** obtain egress IP from the edge device or an organization-approved method; compare against effective rules and a timestamped test attempt. Do not use a LAN IP from `Test-NetConnection` alone against public rules.

**Resolution:** update the permitted source CIDR appropriately or use the designed Bastion/VPN path. Open a new session to verify and revoke any temporary test rule.

### 11.2. Ping Gets No Reply, but SSH Reports Key Error

**Observation:** `ping` times out; `ssh -vvv` reaches authentication and reports `Permission denied (publickey)`.

**Inference:** ICMP does not determine TCP/22 status. There is enough evidence to prioritize username, identity, and authorized keys.

**Resolution:** verify image, account, and key fingerprint; check SSH logs. Do not open ICMP or alter routes to solve this authentication error.

### 11.3. NAT Route Exists, but Cannot SSH to Private Host

**Observation:** the private host can download package updates; a laptop cannot reach `10.20.20.10:22` from the Internet.

**Inference:** a working outbound path does not provide an inbound path to a private IP.

**Resolution:** test via OCI Bastion, a jump host, or an approved private connection. With a jump host, verify each hop and source rules at the target.

### 11.4. DNS Works on Admin Host, Fails in Application

**Observation:** the database name returns a private IP on a test host, but `NXDOMAIN` on the application host.

**How to verify:** query the exact same FQDN and record type; compare actual resolvers, DHCP options, private views, and caches. If the application runs in a container, test from inside the container's network namespace.

**Resolution:** fix resolver/view configuration or records at the exact point handling those queries. Then test connecting to the returned IP and connecting by hostname from the application.

### 11.5. NSG Has an SSH Rule, but SYN Never Reaches Target

**Observation:** an operator just added a rule to NSG `admin-access`; traffic is still rejected.

**How to verify:** verify the target IP's VNIC actually belongs to `admin-access`; check source-side egress NSGs if using a jump host; inspect which VNIC records `REJECT`.

**Resolution:** fix the identified wrong NSG attachment or rule, then open a new connection. Also verify no overly broad Security List rule makes effective configuration differ from intent.

The scenarios above are reasoning examples for learning the workflow, not outputs run on a specific tenancy.

## 12. Controlled Lab Practice

Use a lab environment where you have administrative permissions and recovery channels. For each exercise, record initial config, action, expected outcome, actual evidence, and revert step.

| Exercise | Lab Action | Expected Observation |
| --- | --- | --- |
| Wrong username | SSH with a nonexistent account | TCP may succeed, authentication fails |
| Wrong key | Use a different lab private key | Logs show the key was not accepted |
| Wrong SSH source | Temporarily change lab rule CIDR, keeping a recovery path | New session fails; verify no other rule set still allows it |
| Broken return route | Edit route in a dedicated lab route table | Compare NPA and SYN/SYN-ACK packets before reverting |
| Nonexistent name | Query a test FQDN with no record | Receive NXDOMAIN if matching zone/context answers so |
| Compare UDP vs TCP DNS | Query the same target DNS in both modes | Distinguish transport differences if any |

Do not practice breaking routes or blocking SSH on tables shared with production environments. After each exercise, revert changes and prove a new connection works; do not rely on an already-open session.

Control diagnostic resources through appropriate log scopes, retention aligned with need, and tearing down test hosts or temporary resources after the lab. In real operations, put verified changes into Terraform/Resource Manager or your managed configuration tool so the next deployment does not reintroduce broken settings.

## 13. Incident Closure Criteria

An incident can be closed once the following are documented:

- A new connection succeeds from the required source using the expected hostname or IP.
- DNS returns the right address in the right environment; TCP and authentication are verified separately.
- Root cause is supported by evidence and the remediation change is clearly described.
- Temporary rules, sessions, packet captures, and test resources have been cleaned up as needed.
- Automation configuration is synchronized; no undocumented manual drift remains.
- Recurrence detection is in place: appropriate alerts, connectivity probes, or DNS checks from a representative point.

A concise report can use this structure:

```text
Impact scope:
Start / recovery timestamps with time zone:
Source -> destination / protocol / port:
Symptom and reproduction command:
Evidence from client, OCI, and guest:
Root cause:
Remediation change and rollback procedure:
Verification results for new session / DNS / service:
IaC, monitoring updates, and follow-up actions:
```

The goal of troubleshooting is to explain both why the connection broke and why the change restored it, with access permissions and network configuration aligned to operational needs.
