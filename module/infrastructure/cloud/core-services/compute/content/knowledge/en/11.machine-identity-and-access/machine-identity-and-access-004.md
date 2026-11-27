# SSH Keys, SSH Certificates, and Linux Account Management

Cloud virtual machines and Linux servers need a mechanism to determine who is allowed to log in, what that account is allowed to do, and how to revoke permissions when a user or workload no longer needs access. SSH is the standard remote administration method. If everyone shares a single password or a single private key, tracking and revoking access becomes very difficult. A sound access system requires an individual identity per person or workload, authentication with public keys or time-limited certificates, group-based authorization, and activity logging.

This lesson covers how to generate and use SSH keys, how to organize SSH certificates with a Certificate Authority (CA), and the Linux account lifecycle. It places these mechanisms in a cloud computing context, where servers may be newly created, replaced, or scaled automatically.

After this lesson, you will be able to:

- Distinguish public keys, private keys, host keys, and SSH certificates.
- Generate, install, protect, verify, and rotate SSH keys.
- Explain how an SSH CA issues time-limited user and host certificates.
- Create Linux accounts, manage groups and sudo privileges, and lock or revoke accounts.
- Configure an SSH server securely and validate configuration before applying changes.
- Troubleshoot login failures and establish workflows for granting, reviewing, and revoking access.

## 1. Machine Identity and Linux Accounts

Linux distinguishes users and groups by numeric identifiers:

- **UID (User ID):** identifies a user account.
- **GID (Group ID):** identifies a user's primary group.
- **Supplementary groups:** additional groups to which the account belongs.
- **Root:** the account with UID 0, holding the highest administrative privileges on the system.

Account information is typically resolved through the Name Service Switch (NSS) mechanism. On a standard Linux machine, **/etc/passwd** holds account details such as username, UID, GID, home directory, and shell; **/etc/shadow** stores protected password authentication data; **/etc/group** describes groups. Enterprise environments may pull identities from LDAP, Active Directory, or a centralized identity management service via NSS/PAM.

Do not assume a single username represents the same identity across every machine. UIDs/GIDs, identity sources, and group policies can vary across machines. When deploying a fleet of servers, establish identity synchronization or centralized access management to prevent the same person from unintentionally having different privileges.

Basic inspection commands:

~~~bash
id alice
getent passwd alice
getent group cloud-operators
whoami
groups
~~~

The **getent** command queries through the system's identity resolution mechanism, making it more useful than reading a local file directly when the machine uses centralized identity.

## 2. How Does SSH Public Key Authentication Work?

SSH key authentication uses a cryptographic key pair:

- **Private key:** kept secret on the user's machine or inside a hardware security device. This key proves the user logging in owns the corresponding identity; never send the private key to the server.
- **Public key:** can be installed on the server so the server can verify signatures created by the corresponding private key.

When connecting, the client requests public-key authentication. The server checks whether the public key is authorized for the target account, then verifies the signature during the SSH handshake. The private key does not leave the client during normal authentication.

A user's public keys are typically placed in **~/.ssh/authorized_keys** under the account on the server. This file lists the keys allowed to log in to that account. If the same person accesses multiple machines, the same public key can be installed into each authorized account, or an SSH CA can be used to manage access at scale.

### Generating a key pair

With modern OpenSSH, Ed25519 is a compact and strong choice for most cases:

~~~bash
ssh-keygen -t ed25519 -a 64 -C "alice@laptop-2026" -f ~/.ssh/id_ed25519
~~~

The command creates two files:

- **~/.ssh/id_ed25519:** private key.
- **~/.ssh/id_ed25519.pub:** public key.

When prompted, set a passphrase for the private key. A passphrase protects the key if the file is copied or the device is lost. If the device has compatible security hardware, consider FIDO keys such as **ed25519-sk**. RSA may still be required for legacy systems, using key sizes and signature algorithms compliant with current organizational policy.

View the fingerprint to identify a key:

~~~bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
~~~

A fingerprint is a short identifier of a public key. When an administrator receives a public key from a user, they can verify the fingerprint over a trusted channel to confirm the authentic key was received.

### Protecting the private key

The private key must be protected like a login credential:

- Never send private keys over email, chat, tickets, or store them in repositories.
- Never copy the same private key for an entire team.
- Set a passphrase and restrict file permissions.
- Use encrypted devices, secret storage, or appropriate security hardware.
- Generate separate keys per person, device, or usage purpose for easy revocation.
- Rotate keys according to policy and immediately if compromise is suspected.

Common file permissions:

~~~bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
~~~

Public keys do not need to be kept secret, but still must be managed so you know who owns each key and whether it remains authorized. On the server, the **.ssh** directory and **authorized_keys** must be owned by the proper account. Overly permissive write access can allow others to add their own keys to the account.

## 3. Installing Public Keys and Connecting via SSH

On systems with **ssh-copy-id**, users can install a public key onto a remote account:

~~~bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub alice@vm-01.example.internal
~~~

If **ssh-copy-id** is unavailable, an administrator can append the public key content to **~/.ssh/authorized_keys** of the target account. Example on the server with administrative privileges:

~~~bash
install -d -m 700 -o alice -g alice /home/alice/.ssh
cat /tmp/alice_id_ed25519.pub >> /home/alice/.ssh/authorized_keys
chown alice:alice /home/alice/.ssh/authorized_keys
chmod 600 /home/alice/.ssh/authorized_keys
~~~

Adjust the home path and group name in the example to match the actual account. Avoid overwriting **authorized_keys** if it already contains other valid keys; append keys carefully and verify the contents afterward.

Connect using a specific key:

~~~bash
ssh -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

You can define configuration for frequently accessed hosts in **~/.ssh/config**:

~~~sshconfig
Host orders-prod
    HostName vm-01.example.internal
    User alice
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
~~~

Then connect using **ssh orders-prod**. **IdentitiesOnly yes** tells SSH to try only the specified identity rather than trying every key in the agent, avoiding failures caused by server authentication attempt limits.

### SSH agent and agent forwarding

An SSH agent holds unlocked keys in memory during a session so the user does not have to re-enter the passphrase every time. Example:

~~~bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-add -l
~~~

Agent forwarding (**ssh -A**) lets an intermediate host use the client's agent to authenticate to the next host. This is convenient when hopping through a bastion, but the intermediate host can ask the agent to sign authentication challenges while forwarding is active. Do not enable forwarding indiscriminately on untrusted hosts. Use **ProxyJump** to traverse a bastion without forwarding the agent:

~~~sshconfig
Host bastion
    HostName bastion.example.internal
    User alice
    IdentityFile ~/.ssh/id_ed25519

Host private-vm
    HostName 10.20.1.15
    User alice
    ProxyJump bastion
    IdentityFile ~/.ssh/id_ed25519
~~~

## 4. Distinguishing User Keys from Host Keys

SSH uses keys on both sides:

- **User key** authenticates a person or workload to the server. The public key is trusted by the server via **authorized_keys** or a CA.
- **Host key** authenticates the server to the client. The client uses the host key or host certificate to confirm it is connecting to the real server and prevent server spoofing.

On first connection, SSH normally asks whether to trust the host key fingerprint and saves it in **~/.ssh/known_hosts**. Administrators should obtain the fingerprint from the console or a trusted management channel and verify it before accepting. **ssh-keyscan** can gather public host keys over the network, but by itself does not prove the responding machine is the genuine server.

When a host key changes because a machine was recreated, the client may warn **REMOTE HOST IDENTIFICATION HAS CHANGED**. Do not blindly delete the warning. Verify the change through a trusted channel first, then update the **known_hosts** entry. The warning may indicate a legitimate rebuild, or it may signal a man-in-the-middle attack.

## 5. SSH Certificates and Certificate Authority

Managing **authorized_keys** manually may work for a few machines, but does not scale across hundreds or thousands of servers. When users change teams, leave, or lose devices, administrators must track down and remove public keys from many machines. SSH certificates solve this distribution problem by having a CA sign and attest a public key along with attributes such as identity, principals, and validity period.

### How do certificates work?

Users still keep their own key pair. They submit their public key to the certificate issuance system. The CA verifies their identity and permissions, then uses the CA private key to sign an SSH certificate. Servers trust the CA's public key and can verify certificates without installing individual public keys into every **authorized_keys**.

A certificate typically carries:

- The certified public key.
- Certificate type: user or host.
- Key ID to identify the issuance event.
- Principals, such as allowed account names or roles.
- Validity start and expiration timestamps.
- Options or extensions granted by the CA.

Short-lived certificates shorten the window during which a compromised credential remains usable. The CA can issue new certificates after the user authenticates via SSO, MFA, or an organizational approval workflow.

### Issuing user certificates with OpenSSH

In this illustrative example, the CA already has a dedicated key pair stored securely. The user generates a personal key pair as before and submits the public key to the certificate issuance system. The administrator or CA service signs the public key:

~~~bash
ssh-keygen -s /secure/ssh-user-ca \
  -I "alice-session-2026-11-22" \
  -n "alice" \
  -V "-5m:+8h" \
  ~/.ssh/id_ed25519.pub
~~~

The command creates a certificate file with the **-cert.pub** suffix, such as **id_ed25519-cert.pub**. **-I** sets the key ID for lookup/auditing; **-n** declares the principals; **-V** sets the validity interval. The principal name must match the policy checked by the SSH server. This is a direct signing example to illustrate the format; in an organization, the CA private key should reside in a dedicated security system and never be distributed to users or application machines.

On the SSH server, install the CA public key and configure **sshd_config**:

~~~sshconfig
PubkeyAuthentication yes
TrustedUserCAKeys /etc/ssh/user_ca.pub
AuthorizedPrincipalsFile .ssh/authorized_principals
~~~

The file **/etc/ssh/user_ca.pub** contains only the CA public key. The file **~/.ssh/authorized_principals** in the target account lists permitted principals, for example:

~~~text
alice
~~~

When a certificate contains the principal **alice**, the server can allow login to the **alice** account if the signature is valid, the certificate is within its validity window, it is not revoked, and all additional policies pass. Without **AuthorizedPrincipalsFile**, OpenSSH uses a default principal rule based on the account name; verify the actual policy before rollout.

The client uses the corresponding private key and certificate:

~~~bash
ssh -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

OpenSSH automatically looks for the **-cert.pub** certificate file alongside the private key in the default configuration. You can specify it explicitly with the **CertificateFile** option when needed.

### Host certificates

A CA can also sign host public keys. When clients trust the host CA, many servers can be authenticated by certificate without distributing individual host keys. In **known_hosts**, an administrator can declare the CA for a hostname scope:

~~~text
@cert-authority *.example.internal ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... host-ca
~~~

Servers are configured with **HostCertificate** pointing to the signed certificate. Host certificates allow clients to verify server identity via the CA, though host key lifecycles, certificates, and domain scopes must be managed carefully. Avoid overly broad wildcards if domain zones belong to different trust levels.

### Protecting the CA and revoking certificates

The CA is a critical trust anchor. If the CA private key is compromised, an attacker can sign certificates for arbitrary identities. Therefore:

- Store the CA private key in an HSM, appropriate KMS, or tightly controlled dedicated signing host.
- Grant signing permissions only to authorized services or personnel.
- Log the requester, principal, key ID, validity period, and approval result.
- Use short-lived certificates, limiting principals and options to what is required.
- Maintain a CA rotation plan to distribute the new CA public key and retire trust in the old CA.
- Maintain a revocation workflow and update revocation lists across all servers.

OpenSSH supports a Key Revocation List (KRL). Administrators can generate a KRL from public keys to revoke:

~~~bash
ssh-keygen -k -f /etc/ssh/revoked_keys.krl revoked_key.pub
~~~

Then configure the server:

~~~sshconfig
RevokedKeys /etc/ssh/revoked_keys.krl
~~~

A KRL can contain revoked keys or certificates. When updating an existing KRL, follow proper update procedures, distribute the updated file to all servers, and verify servers have loaded the list. Revoking a certificate does not replace investigating the compromised device, rotating related keys, and reviewing active login sessions.

## 6. Linux Account Management

Accounts should be created according to roles and job needs. Do not share a single administrative account among multiple people because logs will not show who performed an action.

### Creating accounts and groups

Example of creating account **alice** with a home directory and login shell:

~~~bash
sudo useradd --create-home --shell /bin/bash alice
sudo groupadd cloud-operators
sudo usermod --append --groups cloud-operators alice
id alice
~~~

**--append** (equivalent to **-a**) is critical when adding groups with **usermod -G**: omitting **-a** can replace the current list of supplementary groups. Administrative group names vary by distribution; Ubuntu/Debian typically use **sudo**, while many other distributions use **wheel**.

Home directories, shells, and groups should follow system standards. Service accounts that do not require interactive login typically use a shell such as **/usr/sbin/nologin** or the distribution's equivalent path:

~~~bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin orders-api
~~~

Do not assign SSH keys to service accounts when the workload can use a machine identity or dedicated authentication mechanism.

### Granting least-privilege sudo permissions

Do not grant full root access to everyone simply because they need to restart a service. Grant only the required commands via files in **/etc/sudoers.d/**. Always edit with **visudo** to validate syntax:

~~~bash
sudo visudo -f /etc/sudoers.d/orders-operator
sudo visudo -c
sudo -l -U alice
~~~

Example policy content allowing an operations group to run specific commands:

~~~sudoers
%cloud-operators ALL=(root) /usr/bin/systemctl status orders-api, /usr/bin/systemctl restart orders-api
~~~

Command paths must match the actual machine, and you should evaluate whether permission to restart a service indirectly allows arbitrary command execution through writable configuration files or scripts. Avoid **NOPASSWD: ALL** without an approved requirement and compensating controls.

### Locking, expiring, and deleting accounts

When a user temporarily steps away from duties, an administrator can lock password authentication:

~~~bash
sudo passwd --lock alice
sudo chage -l alice
~~~

Note: locking a password does not necessarily disable public-key login. If the account has **authorized_keys** or is accepted via an SSH CA, the user can still log in using public-key mechanisms depending on PAM configuration and system policy. To revoke SSH access, remove the corresponding keys or certificate trust, revoke principals/groups, set an account expiration date, and check other access paths.

To set an account expiration date:

~~~bash
sudo usermod --expiredate 2026-12-31 alice
~~~

The date format is **YYYY-MM-DD**. For someone leaving the organization, the workflow can include locking or expiring the account, removing them from access groups, revoking SSH keys/certificates, removing sudo privileges, invalidating related tokens and sessions, retaining required data per policy, and only then deleting the account.

Deleting an account:

~~~bash
sudo userdel --remove alice
~~~

**--remove** deletes the account's home directory and mail spool on that machine. Run this only after confirming data retention requirements, file ownership, and service dependencies. In environments using LDAP/AD or centralized identity, revoke access at the authoritative identity source; deleting a local record may not suffice.

## 7. Secure SSH Server Configuration

The SSH daemon typically reads configuration from **/etc/ssh/sshd_config** and included files. A baseline configuration might look like:

~~~sshconfig
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no
AllowGroups cloud-operators
~~~

This is a reference template, not a configuration to copy verbatim to every system. **AllowGroups** restricts SSH login to the specified group; ensure the right users are added to the group before enabling it, otherwise the entire operations team could be locked out. Some environments require keyboard-interactive authentication for MFA; in that case do not disable it without replacing it with an equivalent MFA mechanism. Some services also require port forwarding or X11; disable them only when not needed.

Before applying:

1. Keep your current administrative SSH session open.
2. Open a new session and confirm at least one other administrative account can log in.
3. Validate configuration syntax:

~~~bash
sudo sshd -t
~~~

4. Inspect the effective configuration when needed:

~~~bash
sudo sshd -T | grep -E 'pubkeyauthentication|passwordauthentication|permitrootlogin|allowgroups'
~~~

5. Reload only after checks succeed:

~~~bash
sudo systemctl reload sshd
~~~

Some distributions name the service **ssh** instead of **sshd**. Verify the exact service name on your system. After reloading, test logging in from a new session before closing the original administrative session. If an error occurs, use the still-open session to restore the configuration.

### Restricting access by group or account

**AllowUsers**, **AllowGroups**, **DenyUsers**, and **DenyGroups** can restrict who is allowed to connect. **Match User** or **Match Group** blocks apply dedicated policies to account groups, such as allowing an automation account to run only one specific command or disallowing interactive shells.

A line in **authorized_keys** can also restrict how a key is used, such as limiting source IP addresses or forcing a specific command. Test these options thoroughly so they do not inadvertently grant broader permissions than intended. For automation accounts, **restrict** and **command="..."** can be used when the workflow fits; the forced command must be written safely and must not trust untrusted inputs.

## 8. Applying These Practices in Cloud Environments

In the cloud, VMs may be launched from images or replaced by autoscaling. Manually adding personal keys to each machine easily produces out-of-sync key lists. Common organizational approaches include:

- **Bootstrap key:** the platform injects an initial public key into the VM for administrators to set up the machine. Restrict who has permission to create or modify key metadata.
- **Bastion or access gateway:** users connect through a centralized management point, reducing the number of machines exposing SSH directly to the network.
- **SSH CA:** a system issues certificates after users authenticate via SSO/MFA, with scoped principals and short lifetimes.
- **Machine identity:** workloads use service identities, instance identities, or short-lived tokens to access other services instead of sharing SSH private keys.
- **Configuration management:** configuration management tools synchronize groups, SSH policies, CA public keys, and account states across machines.

Do not expose SSH ports publicly to the entire Internet if access can be restricted via VPN, private networks, bastions, or source-based firewall policies. Security groups/firewalls should allow only the intended sources and ports. Strong SSH authentication does not replace network segmentation.

For auto-replacing instance fleets, identities and access permissions should be provisioned declaratively. When an instance is terminated, access bound to that instance should expire or be revoked automatically. Avoid baking shared private keys into machine images; every VM launched from that image would carry the same secret, expanding the blast radius if one machine is compromised.

## 9. Troubleshooting SSH and Account Errors

| Symptom | Common causes | How to check |
|---|---|---|
| **Permission denied (publickey)** | Wrong user, wrong key, public key not installed, or principal mismatch | **ssh -vvv**, check **authorized_keys**, certificate, and server logs |
| SSH skips the intended key | Agent holds many keys or client selects another identity | Use **-i**, **IdentitiesOnly yes**, check **ssh-add -l** |
| Server rejects due to file permissions | Home, **.ssh**, or **authorized_keys** has incorrect owner/mode | **namei -l /home/alice/.ssh/authorized_keys**, **stat** |
| Host key changed | Machine was recreated or possible host spoofing | Verify fingerprint via trusted channel before updating **known_hosts** |
| Certificate expired/invalid | Expired, not yet valid, untrusted CA, or wrong principal | **ssh-keygen -Lf id_ed25519-cert.pub**, check system clock and CA config |
| Login succeeds but lacks admin rights | Missing sudo/wheel group or invalid sudoers | **id**, **sudo -l**, **visudo -c** |
| Account rejected despite valid key | Account expired, invalid shell, PAM, or AllowGroups block | **getent passwd**, **chage -l**, auth logs, and **sshd -T** |

On the client, enable verbose output to inspect negotiation:

~~~bash
ssh -vvv -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

On the server, logs may reside in the journal:

~~~bash
sudo journalctl -u sshd --since "15 minutes ago"
~~~

Some systems write authentication logs to **/var/log/auth.log** or **/var/log/secure**. Paths and service names depend on the distribution. Logs can contain usernames, IP addresses, and operational details; only authorized personnel should have access.

## 10. Reviewing and Rotating Access Permissions

A key or account should not exist indefinitely simply because it has not caused an incident yet. Maintain an inventory tracking owner, purpose, permitted machines or machine groups, creation timestamp, expiration date, and usage status.

A personal key rotation workflow may include:

1. The user generates a new key pair on a managed device.
2. The new public key is verified and provisioned for the appropriate account/principal.
3. The user tests connecting with the new key while the old key is still active.
4. The administrator removes the old key from **authorized_keys** or stops issuing certificates for the old key.
5. Review logs and inventories to confirm no machines still depend on the old key.

If a private key is compromised, immediately revoke the corresponding public key or certificate, terminate related sessions and tokens where possible, review login logs, inspect account/sudoers modifications, and assess whether an attacker established persistent access. Simply generating a new key without removing the compromised key will not resolve the incident.

For employee accounts, integrate the access lifecycle with onboarding, role change, and offboarding workflows. Access permissions must be reviewed periodically against owners and business needs. Emergency accounts require an assigned owner, approval controls, usage alerts, and post-access reviews.

## 11. Example: Granting SSH Access to an Operations Engineer

Suppose a team runs a VM hosting an ordering API. Engineer Alice needs to check service status and be allowed to restart only **orders-api**. The team does not want to grant full interactive root access.

**Step 1: Create account and access group**

~~~bash
sudo groupadd cloud-operators
sudo useradd --create-home --shell /bin/bash alice
sudo usermod --append --groups cloud-operators alice
~~~

**Step 2: Install verified public key**

Alice generates an Ed25519 key pair on her workstation and sends the **.pub** file via an approved channel. The administrator verifies the fingerprint, then installs the public key into Alice's **authorized_keys** with appropriate owner and mode.

**Step 3: Grant restricted sudo privileges**

The administrator uses **visudo -f /etc/sudoers.d/orders-operator** to add a policy matching the **systemctl** path on the machine:

~~~sudoers
alice ALL=(root) /usr/bin/systemctl status orders-api, /usr/bin/systemctl restart orders-api
~~~

Then verify:

~~~bash
sudo visudo -c
sudo -l -U alice
~~~

**Step 4: Test SSH and permissions**

Alice logs in with her public key, checks **id** and **sudo -l**, and runs the status command. The operations team confirms Alice cannot execute administrative commands outside the granted list.

**Step 5: Revoke upon role change**

When Alice no longer supports the service, the team removes her sudo rules, removes her key from **authorized_keys** or revokes her certificate/principal, removes Alice from the access group, and handles active login sessions per policy. If Alice leaves the company, offboarding must also revoke other related identities and tokens.

This example illustrates permissions tied to a specific person and role. Across many VMs, certificate issuance and group synchronization can be moved to a centralized identity system to reduce manual work.

## 12. SSH and Account Management Checklist

- [ ] Every user or workload has a dedicated identity.
- [ ] Private keys are kept secret, protected with passphrases or appropriate hardware.
- [ ] Public key fingerprints are verified before granting access.
- [ ] Host keys or host certificates are verified to avoid connecting to the wrong server.
- [ ] **.ssh** directories and **authorized_keys** files have proper owner and mode.
- [ ] Private keys are not shared or embedded in images.
- [ ] Accounts have shell, home directory, and groups matching their needs.
- [ ] Sudo privileges are restricted by command and role.
- [ ] The SSH server enables only approved authentication methods.
- [ ] Changes to **sshd_config** are syntax-checked and tested with a new session before closing the old session.
- [ ] SSH certificates have managed principals, expiration, and CA.
- [ ] Revocation lists and compromised-key incident workflows are in place.
- [ ] Logs, key/account inventories, and periodic permission reviews exist.
- [ ] Offboarding workflows revoke keys, certificates, groups, tokens, and related sessions.

## 13. Applied Exercise

An operations team manages 40 Linux servers across two cloud regions. Currently, 5 engineers share a single SSH key installed in **authorized_keys** on all servers. One engineer is transferring to another team, and the team needs to grant temporary access to a contractor for 4 hours.

1. What risks arise when multiple people share a single private key?
2. Propose a plan to migrate to individual identities and short-lived SSH certificates with scoped principals.
3. What must be configured on the servers to trust the user CA and restrict permitted principals?
4. When the contractor finishes work, which permissions must the team revoke? Why is locking only the Linux password insufficient?
5. If one server reports **REMOTE HOST IDENTIFICATION HAS CHANGED**, what must the team verify before modifying **known_hosts**?

Hint: issue an individual key pair per engineer, and use a centralized authentication system to issue certificates valid for at most 4 hours with restricted principals. Servers trust the CA's public key and validate principals per policy. Upon completion, stop issuing certificates, revoke certificates/keys if needed, remove group permissions, and terminate active sessions. For a changed host key, verify the fingerprint via the console or a trusted management channel before updating.

## Conclusion

SSH keys enable authentication without sharing passwords, while SSH certificates enable managing access by identity, principal, and validity period through a CA. Linux accounts and groups define what a user can do after logging in; sudo grants controlled administrative privileges. By combining individual identities, private key protection, host verification, secure server policies, logging, and revocation workflows, operations teams can manage cloud server access consistently and auditably.
