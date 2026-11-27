# Cannot SSH or RDP: Checking Identity, Network, and Login Services

When you cannot connect via SSH or RDP to a cloud virtual machine, the cause may lie across several layers: invalid identity, an unready server, incorrect DNS or routes, a firewall blocking the port, a stopped login service, or the operating system rejecting the session. Client-side error messages usually reflect only where the connection stopped, not necessarily the root cause.

An effective approach is to determine which stage the connection fails at, then inspect each layer in order from client to server. SSH typically uses TCP port 22; RDP typically uses TCP port 3389 and may use UDP for certain features. Actual ports may have been changed by system policy. Do not widen network access or disable protections just to test connectivity; verify the exact source, destination, identity, and required services.

This lesson guides you through diagnosing SSH failures on Linux and RDP failures on Windows in cloud compute environments. After this lesson, you will be able to:

- Classify failures across identity, name resolution, TCP connection, protocol handshake, and login session creation.
- Check accounts, SSH keys, passwords, MFA, login permissions, and host policies.
- Verify IP addresses, DNS, routes, VPN, bastion, security groups, firewalls, and network ACLs.
- Inspect SSH or Remote Desktop services, OS logs, and virtual machine state.
- Use the console or out-of-band management channels to recover when network login fails.
- Restore connectivity safely and document the root cause to prevent recurrence.

## 1. Pinpoint where the connection fails

A remote login session can be broken down into stages:

1. **Target resolution:** the client resolves the hostname to an IP address and selects the destination IP/port.
2. **Routing:** packets traverse the client network, VPN or bastion, cloud routes, subnet, and the VM's network interface.
3. **TCP setup:** the client opens a connection to the SSH or RDP port; firewalls and security groups must allow the required flow.
4. **Protocol handshake:** both sides negotiate SSH or RDP, verifying the host key/certificate and algorithms.
5. **Identity authentication:** the server validates the public key, password, certificate, MFA, or configured authentication mechanism.
6. **Authorization and session creation:** the account is permitted to log in, and the shell or desktop session initializes successfully.

Distinguishing failures at each stage avoids modifying the wrong layer. For example:

| Symptom | Likely failing stage | First check to perform |
|---|---|---|
| DNS name does not resolve | Target resolution | DNS resolver, records, and search domain |
| Connection timed out | Routing or TCP | Destination IP, routes, VPN, security groups, and firewalls |
| Connection refused | TCP reaches target host but no listener or actively rejected | SSH/RDP service, listening port, and host firewall |
| SSH reports Permission denied | Authentication or account policy | Username, private key, authorized_keys, certificate, AllowUsers/AllowGroups |
| RDP reports invalid credentials | Authentication | Domain/account name, password, NLA, login permissions, and account status |
| Host key or certificate warning | Handshake and server verification | Fingerprint, certificate, DNS, and whether the VM was replaced |
| Login succeeds but session closes | Session creation or workload | Shell/profile, desktop session, resources, and OS logs |

Error messages are clues, not conclusions. A firewall can send a TCP reset causing the client to report refused; a non-listening service produces the same symptom. Combine client output, the cloud console, and server logs.

## 2. Check VM state and cloud access path

Before changing OS configuration, verify the virtual machine and cloud networking:

- The instance is in the running state with no stop, reboot, host maintenance, or provisioning error events.
- System health checks and instance health checks pass, if provided by the cloud platform.
- The network interface is attached to the right VM, subnet, and security group/firewall policy.
- The current IP address matches what the user is connecting to. Dynamic public IPs may have changed after stop/start.
- The route table includes a path between the source network and the target subnet.
- Network ACLs, cloud firewalls, or intermediate network policies permit both outbound and return traffic for the connection.
- If the VM sits in a private subnet, the user has an appropriate VPN, bastion, jump host, or private management channel.

Not every VM needs a public IP. Production servers should generally live in a private network and accept management connections only from a VPN, bastion, or controlled management service. If the target IP changed, update DNS or inventory through an approved change workflow.

### Map the connection path

Trace the path from client to VM:

~~~text
Admin workstation
    |
    +-- VPN or corporate network
            |
            +-- Bastion / access gateway (if present)
                    |
                    +-- Cloud route / firewall / security group
                            |
                            +-- VM network interface
                                    |
                                    +-- OS firewall
                                            |
                                            +-- sshd or Remote Desktop Services
~~~

Each hop can enforce its own policy. A security group permitting port 22 does not mean the Linux firewall allows it. Likewise, Windows Firewall can block RDP even if cloud rules are open.

### Check IP address and DNS

On Linux or macOS:

~~~bash
getent hosts vm-01.example.internal
dig +short vm-01.example.internal
ip route get 10.20.1.15
~~~

On Windows PowerShell:

~~~powershell
Resolve-DnsName vm-01.example.internal
Test-NetConnection vm-01.example.internal -Port 3389
Test-NetConnection vm-01.example.internal -Port 22
~~~

Replace the domain name, address, and port with real values. If DNS returns multiple addresses, verify which address the client attempts. Compare resolution inside the VPN against outside the VPN; split-horizon DNS can return different addresses depending on location.

If connecting by IP works while hostname fails, focus on DNS, search suffixes, resolvers, and caches. If the hostname resolves properly but TCP fails to open, continue checking routes and firewalls.

## 3. Test TCP connectivity from the client

### For SSH

~~~bash
nc -vz -w 5 vm-01.example.internal 22
~~~

Or run SSH in verbose mode:

~~~bash
ssh -vvv -o ConnectTimeout=8 alice@vm-01.example.internal
~~~

Verbose output shows how the client resolved the name, chose an address, opened the socket, received the host key, and which authentication methods it tried. Do not share unfiltered logs if they expose sensitive details such as usernames, internal hostnames, or network addresses.

### For RDP

On Windows:

~~~powershell
Test-NetConnection vm-win-01.example.internal -Port 3389 -InformationLevel Detailed
~~~

The key outputs are whether TCP connect succeeded, the selected destination address, and the source interface/route. This command tests TCP only; it does not verify RDP, NLA, certificates, or login permissions.

### Interpreting TCP results

- **TcpTestSucceeded = True:** the TCP path to the port is open. Proceed to check protocol, authentication, and login policies.
- **Timed out:** packets may be dropped by routes, VPN, firewalls, security groups, or an unresponsive host. Inspect each hop and flow logs if available.
- **Connection refused:** the target may be reachable, but no service is listening, the service uses another port, or a firewall is sending resets.
- **No route to host / Network is unreachable:** check routes, subnets, VPN, gateways, and the client interface.

Ping is not a substitute test for TCP. ICMP may be blocked while SSH/RDP works, or ping may succeed while the TCP port remains blocked.

## 4. Check identity and login permissions

When TCP connects but authentication fails, inspect identity before changing network settings.

### SSH on Linux

Check the following factors:

- Does the username match an account on the VM? Cloud image default usernames vary by distribution and custom organizational images.
- Is the client using the right private key?
- Is the corresponding public key installed on the target account or trusted by an SSH CA?
- Does the private key have a passphrase, and is it loaded into the SSH agent?
- Is the certificate still valid, with the right principal, and signed by a CA the server trusts?
- Is the account locked, expired, missing a valid shell, or excluded by AllowUsers/AllowGroups?
- Do the home directory, `.ssh` directory, and `authorized_keys` have the right owner and permissions?

Specify the identity explicitly:

~~~bash
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes alice@vm-01.example.internal
ssh-add -l
ssh-keygen -lf ~/.ssh/id_ed25519.pub
~~~

On the server, once you have console or alternative admin access:

~~~bash
id alice
getent passwd alice
sudo passwd -S alice
sudo chage -l alice
sudo namei -l /home/alice/.ssh/authorized_keys
sudo sshd -T | grep -Ei 'pubkeyauthentication|passwordauthentication|allowusers|allowgroups|denyusers|denygroups'
~~~

Home directory paths may differ from the example. Verify owner and mode per system policy; typically the `.ssh` directory is accessible only to the owner and `authorized_keys` is not writable by group or others.

Locking a password with `passwd` does not necessarily disable SSH public keys. If the account has `authorized_keys` or authenticates via certificate, revoke that specific mechanism. Conversely, removing a key from `authorized_keys` does not revoke a still-valid certificate if the server still trusts the CA and principal.

### RDP on Windows

Check:

- Does the username belong to the local machine or domain? You may need `DOMAIN\username` or `username@domain` format.
- Is the password still valid, or is the account locked or expired?
- Does the user have permission to log on through Remote Desktop Services?
- Is the user or group in Remote Desktop Users or an authorized administrators group?
- Does domain policy block RDP logins, require MFA, or restrict source machines?
- Is Network Level Authentication (NLA) supported by both the client and authentication path?
- Is the machine domain-joined and able to reach a domain controller?

On Windows PowerShell with appropriate privileges:

~~~powershell
Get-LocalUser
Get-LocalGroupMember -Group "Remote Desktop Users"
Get-Service -Name TermService
Get-NetFirewallRule -DisplayGroup "Remote Desktop"
~~~

If using a domain, inspect domain groups and effective Group Policy settings. Do not add users to the Administrators group just to resolve an RDP failure; grant only the proper Remote Desktop rights and required resource permissions.

### Time and MFA

SSH certificates, Kerberos, TLS, and many MFA systems rely on accurate clocks. If the client, VM, or domain controller clock drifts significantly, certificates may be treated as not yet valid/expired or Kerberos may reject authentication. Check time synchronization and NTP before replacing certificates or resetting passwords.

For MFA, verify the user enrolled the right method, the device is working, and the policy targets the right group. Do not disable MFA system-wide to troubleshoot one account's failure.

## 5. Check the SSH service on Linux

If TCP port 22 is refused or the VM is reachable without an SSH handshake, inspect the service:

~~~bash
sudo systemctl status sshd
sudo systemctl status ssh
sudo ss -lntp | grep ':22'
sudo sshd -t
~~~

The unit name depends on the distribution; it is typically `sshd` on RHEL-family systems and `ssh` on Ubuntu/Debian. Use the exact service name on your machine.

If the service is stopped:

1. Read logs before restarting.
2. Validate configuration with `sshd -t`.
3. Identify the cause, such as a syntax error, missing host key, file permissions, or a port conflict.
4. Fix the identified change and re-validate.
5. Start or reload the service according to procedure.
6. Verify the listening socket and test connecting from an authorized client.

Logs are typically in the journal:

~~~bash
sudo journalctl -u sshd --since "30 minutes ago"
sudo journalctl -u ssh --since "30 minutes ago"
~~~

Check settings that commonly lock out access:

- Was `Port` changed away from 22?
- Does `ListenAddress` restrict listening to an IP/interface that no longer exists?
- Do `AllowUsers` or `AllowGroups` exclude the account?
- Does `AuthenticationMethods` require a combination of key and MFA?
- Does `AuthorizedKeysFile` point to a different path?
- Are `TrustedUserCAKeys`, `AuthorizedPrincipalsFile`, or `RevokedKeys` updated accurately?
- Are PAM, SELinux, or home directory permissions blocking authentication?

Do not overwrite all of `sshd_config` with a template from the Internet. Inspect the effective configuration, included files, and recent changes. If edits are required, keep your current admin session open, validate syntax, and test a new session before closing the old one.

### Check the Linux firewall

Depending on the system, the firewall may be managed by nftables, firewalld, or UFW:

~~~bash
sudo nft list ruleset
sudo firewall-cmd --list-all
sudo ufw status verbose
~~~

Only the commands relevant to each machine apply. Verify that rules allow the exact SSH port from the exact management network. Never flush the entire ruleset or disable the firewall to test connectivity on a production machine; doing so can expose other services.

## 6. Check the RDP service on Windows

RDP typically requires Remote Desktop Services to be running, a listener on the right port, and Windows Firewall allowing connections from valid sources.

On Windows Server, inspect the service:

~~~powershell
Get-Service -Name TermService
Get-NetTCPConnection -LocalPort 3389 -State Listen
Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections
~~~

An `fDenyTSConnections` value of 1 generally indicates Remote Desktop connections are denied in system settings; 0 indicates system settings permit RDP. Group Policy, firewalls, or other policies may still block it.

Inspect firewall rules:

~~~powershell
Get-NetFirewallRule -DisplayGroup "Remote Desktop" |
    Select-Object DisplayName, Enabled, Profile, Direction, Action
~~~

Check the listener and actual port. The default is 3389, though an organization may use a different port. If changed, keep the listener, firewall, security groups, connection documentation, and monitoring in sync.

Relevant logs are usually in Event Viewer:

- Windows Logs → System: service, driver, and startup errors.
- Applications and Services Logs → Microsoft → Windows → TerminalServices-LocalSessionManager.
- Applications and Services Logs → Microsoft → Windows → TerminalServices-RemoteConnectionManager.
- Security: logon success/failure events if enabled by audit policy.

You can quickly inspect recent events via PowerShell:

~~~powershell
Get-WinEvent -LogName "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational" -MaxEvents 50
Get-WinEvent -LogName "Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational" -MaxEvents 50
~~~

If RDP completes the handshake but fails at NLA/CredSSP, check domain connectivity, system time, account status, security updates, and client compatibility. Do not weaken CredSSP security levels or disable NLA system-wide as a general troubleshooting step. If a temporary exception is approved, restrict its scope and duration and plan to restore configuration.

## 7. Check firewalls, security groups, and routes

For management access to work, a matching bidirectional network flow is required. With TCP, the SYN packet travels from client to server; the SYN-ACK reply must be able to return through routes and network policies. Stateless network ACLs may require rules for both the destination port and return ephemeral ports. Stateful security groups usually track connection state automatically, though platform-specific behavior should still be verified.

### Inspection matrix

| Network layer | SSH | RDP | Question to answer |
|---|---|---|---|
| Client | TCP to configured SSH port | TCP to configured RDP port | Does the client have a route and use the right IP/port? |
| VPN/bastion | Allows management source to VM | Allows management source to VM | Are the tunnel, policy, and jump path working? |
| Cloud security group | Allows TCP 22 or custom port from admin CIDR | Allows TCP 3389 or custom port from admin CIDR | Is the rule attached to the right NIC/VM and source? |
| Network ACL/network firewall | Allows outbound and return flow | Allows outbound and return flow | Is a higher-priority deny rule or missing ephemeral return path blocking traffic? |
| OS firewall | Allows sshd to accept connections | Allows Remote Desktop to accept connections | Are the profile, interface, and source scope correct? |
| Service | sshd listening | TermService/listener active | Is the service bound to the right IP and port? |

Prefer source rules restricted to known management IP ranges, VPNs, or bastions. Avoid opening 0.0.0.0/0 or ::/0 for SSH/RDP. If temporary access from a new address is needed, use a narrow, time-bounded rule and remove it once finished.

### Using flow logs and packet captures

If the cloud provides VPC/VNet flow logs or firewall logs, check whether traffic to the target IP/port is ACCEPT or REJECT and on which interface. Flow logs help identify which network layer is blocking traffic, though they do not prove a service is listening.

On Linux, when authorized and deeper analysis is needed, you can observe packets:

~~~bash
sudo tcpdump -ni any 'tcp port 22'
~~~

If SYN arrives with no SYN-ACK, check the host firewall, listener, return routes, and kernel state. If no SYN arrives, the fault likely lies upstream of the VM: client, VPN, routes, security groups, or network ACLs. Packet captures can contain sensitive metadata; store and share them per security policy.

## 8. DNS, IP addresses, and host identity

VMs can be replaced or reassigned IPs after stop/start, scale-in/scale-out, or rebuild operations. An old hostname may point to an IP that no longer belongs to the expected machine. Before editing firewalls or keys, verify:

- Which address does the DNS A/AAAA record currently return?
- Is that IP attached to the right instance/network interface in the console?
- Are DNS TTLs and client caches delaying updates?
- Is the client connecting over a private IP or public IP?
- Is there a NAT, proxy, or load balancer in between?

For SSH, if the host key changes, do not blindly clear the warning. Verify the new fingerprint through the console, configuration management system, or a trusted channel. Once you confirm the VM was legitimately recreated, update `known_hosts` following procedure.

For RDP, the client may warn that the server certificate is untrusted, expired, or mismatched with the hostname. Verify the certificate and hostname; do not ignore warnings on production servers just to force a connection.

## 9. When you cannot log in: use out-of-band management channels

If SSH/RDP does not work, you need a management channel independent of the broken access path. Depending on the platform, you can use:

- The VM's serial console or boot diagnostics.
- Cloud run command/guest agent, if the agent is installed and still connected to the control plane.
- A provider-managed session manager or access gateway.
- Rescue mode, a recovery image, or detaching the boot volume for inspection from a helper machine.
- The hypervisor console or an approved internal management tool.

Out-of-band channels must have tight access controls, logging, and MFA protection. If the guest agent also broke after an update, run command may not work; prepare console or rescue procedures in advance.

### Safe recovery procedure

1. Verify the instance ID and region to ensure you are operating on the right machine.
2. Keep any remaining working admin session open; avoid repeated reboots.
3. Collect console output, boot logs, flow logs, and timestamps of recent changes.
4. Isolate the failing layer: identity, network, firewall, service, or OS.
5. Make the minimal change needed to restore the proper access path; do not disable protections wholesale.
6. Validate configuration and open a new test session from an authorized management network.
7. Confirm account permissions, logs, and service status.
8. Remove temporary rules, revoke unneeded credentials, and document the root cause.

For instance, if SSH is locked out due to a misconfigured `AllowGroups`, use the serial console to restore the config file from a known-good baseline, run `sshd -t`, reload the service, and test connecting with an authorized account. Do not open SSH to the entire Internet to work around an `AllowGroups` mistake.

## 10. Diagnostic decision tree

~~~mermaid
flowchart TD
    A["Cannot SSH or RDP"] --> B["VM running and health checks passing?"]
    B -- "No" --> C["Check cloud status, boot, and console"]
    B -- "Yes" --> D["Hostname resolves to right IP?"]
    D -- "No" --> E["Check DNS, cache, IP, and records"]
    D -- "Yes" --> F["TCP to right port succeeds?"]
    F -- "No" --> G["Check route, VPN, bastion, SG, ACL, and host firewall"]
    F -- "Yes" --> H["SSH/RDP handshake succeeds?"]
    H -- "No" --> I["Check listener, host key/certificate, TLS/NLA, and logs"]
    H -- "Yes" --> J["Identity authentication succeeds?"]
    J -- "No" --> K["Check username, key/password, MFA, account policy"]
    J -- "Yes" --> L["Shell/desktop session created?"]
    L -- "No" --> M["Check login rights, profile, shell, session, and resources"]
    L -- "Yes" --> N["Monitor, document, and close incident"]
~~~

This decision tree is a classification guide. In practice, multiple failures can coexist—for example, DNS pointing to a stale IP while a newly created VM's security group is not yet configured.

## 11. Example 1: SSH timeout after a security group change

An engineer connects to a Linux VM over VPN. SSH worked previously, but after the team changed a security group, SSH hangs and times out.

**Step 1: Verify the VM.** The console shows the VM running and health checks passing. The private IP address has not changed.

**Step 2: Verify DNS and TCP.** The hostname resolves to the right private IP. `Test-NetConnection` or `nc` to port 22 fails.

**Step 3: Check the network path.** The VPN remains connected, and the route to the subnet exists. Flow logs show traffic from the VPN CIDR to TCP 22 being REJECTed.

**Step 4: Scope the rule accurately.** The team confirms the valid management source CIDR and updates the security group to allow TCP 22 from that range. They do not open the port to the entire Internet.

**Step 5: Continue checking the host layer.** TCP opens successfully, and if SSH still refuses access, continue checking `sshd`, host keys, and identity instead of further editing the security group.

Lesson: timeouts usually point to a network path issue or dropped packets. Flow logs and TCP tests help isolate which layer requires attention.

## 12. Example 2: RDP connects but login fails

An administrator can open TCP 3389 to a Windows VM, yet Remote Desktop reports that login fails with the current credentials.

**Step 1: Check TCP.** `Test-NetConnection` returns `TcpTestSucceeded=True`, proving the TCP path to the port works.

**Step 2: Identify account type.** The administrator confirms whether the account is domain or local and uses the proper username format. If it is a domain account, the machine must be able to contact a domain controller.

**Step 3: Check account state and rights.** Verify the account is not locked or expired and belongs to a group permitted to log in over RDP. Check whether a `Deny log on through Remote Desktop Services` policy applies.

**Step 4: Check NLA and logs.** Read `TerminalServices` and `Security` logs to see whether failure happens during authentication or session creation. Check system time and domain connectivity if Kerberos errors appear.

**Step 5: Restore the proper policy.** Fix the misconfigured group or policy through the change process, then retry from an admin workstation. Do not grant Administrator rights or disable NLA broadly just to force login to succeed.

Lesson: once TCP is open, shift focus to authentication, login rights, NLA, and domain health.

## 13. Common mistakes

1. **Opening port 22/3389 to the entire Internet:** widens the attack surface and fails to fix identity or service errors.
2. **Testing only with ping:** ICMP does not verify TCP, SSH, or RDP.
3. **Resetting passwords immediately on error:** may be irrelevant if the connection never reached authentication.
4. **Deleting known_hosts on a host key warning:** can ignore signs of server impersonation.
5. **Disabling firewalls or NLA to test:** reduces security and obscures the root cause.
6. **Using an old IP after VM recreation:** DNS or inventory may not be updated yet.
7. **Editing sshd_config without validating:** syntax errors or wrong `AllowGroups` can lock out all SSH access.
8. **Locking a password while forgetting public keys/certificates:** the account can still authenticate via another method.
9. **Ignoring network ACL return traffic:** the TCP handshake cannot complete even with a valid outbound rule.
10. **Granting overly broad Administrator/root rights:** provides a temporary workaround while creating long-term privilege risks.

## 14. SSH/RDP troubleshooting checklist

- [ ] Confirm the exact VM, instance ID, region, running state, and health checks.
- [ ] Verify the current hostname, IP, port, and DNS records.
- [ ] Check VPN, bastion, routes, security groups, network ACLs, and cloud firewalls.
- [ ] Test TCP to the target port from the right client/source network.
- [ ] Verify the server host key or certificate through a trusted channel.
- [ ] Check the SSH/RDP service, listener, and OS firewall.
- [ ] Check username, account state, public key/certificate, password, and MFA.
- [ ] Check groups, login rights, sudo, or Remote Desktop Users.
- [ ] Read server logs and network logs matching the exact connection attempt timestamp.
- [ ] Use the console or out-of-band management channel if the primary login path fails.
- [ ] Retry from a fresh session after fixing and verify required functionality.
- [ ] Revoke temporary rules, restore security policies, and document the root cause.

## 15. Practice exercise

An operations team manages a Linux VM and a Windows VM in a private subnet. Administrators connect over VPN. This morning, SSH to the Linux VM times out, while RDP to the Windows VM opens TCP 3389 but rejects credentials.

1. Determine the inspection order for each machine and explain why the two failures follow different branches.
2. For the Linux VM, what information should be checked in the cloud console, flow logs, and firewalls before accessing the OS?
3. For the Windows VM, which username/domain formats, account status, login groups, NLA checks, and logs should be inspected?
4. If the Linux VM is unreachable via SSH while the guest agent remains active, which channel can be used to inspect `sshd` and the firewall?
5. After recovery, what should the team do so they do not have to expose SSH/RDP publicly during future incidents?

Hint: the Linux timeout should prioritize checking IP, routes, VPN, security groups, ACLs, and the host firewall before changing keys. Since TCP 3389 is open on Windows, focus on identity, account state, RDP rights, NLA, and domain connectivity. Use run command or session manager if configured and authorized. Maintain VPN/bastion, narrow source rules, MFA, and a fallback console channel.

## Conclusion

Effective SSH/RDP troubleshooting starts by identifying whether the connection stops at DNS, routing, TCP, handshake, authentication, or session creation. Checking VM status, identity, security groups, firewalls, and services in the proper layer limits unnecessary changes and avoids widening access permissions. When the primary login path fails, use a secured console or out-of-band management channel, then verify connectivity and permissions before closing the incident.
