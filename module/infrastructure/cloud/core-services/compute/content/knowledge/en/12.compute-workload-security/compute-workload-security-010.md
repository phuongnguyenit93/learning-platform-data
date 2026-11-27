# Collecting evidence and isolating suspected compromised machines

When a virtual machine shows signs of compromise, operations teams must simultaneously limit the attacker's ability to keep operating and preserve sufficiently trustworthy data to determine what happened. Shutting down or deleting resources too early can destroy RAM contents, open network connections, and volatile traces. Leaving the machine normally connected lets the attacker delete logs, steal more data, or pivot to other workloads.

Incident response must therefore coordinate **evidence preservation**, **controlled isolation**, **investigation**, **root-cause eradication**, and **service recovery**. Exact decisions depend on impact severity, business requirements, cloud platform capabilities, and organizational legal procedures. This lesson focuses on virtual machines and compute workloads, applying equally to application instances, workers, and data servers.

## 1. Identifying signs of potential compromise

A single alert rarely proves a machine is compromised. However, certain indicators warrant rapid inspection and correlation:

- Successful logins from unusual accounts, addresses, or times; new administrative accounts or SSH keys appearing.
- Unfamiliar processes, processes running with elevated privileges, new binaries in temporary directories, or commands executed outside deployment schedules.
- CPU, RAM, network throughput, or connection counts spiking without explanation from business traffic.
- Outbound connections to addresses, domains, or ports outside known service allowlists.
- Deleted logs, disabled auditing, stopped security agents, or firewall changes lacking tickets.
- Application files, scheduled tasks, cron jobs, services, or startup scripts modified outside release workflows.
- Alerts from EDR, antivirus, vulnerability detection, cloud security posture, or behavioral detection systems.
- Secrets, access keys, or tokens used from unexpected sources; anomalous cloud control-plane actions.

Inspect both the guest OS and the control plane. A machine may keep serving requests normally while stolen credentials are used to create snapshots, edit security groups, alter IAM roles, or launch additional instances. Conversely, high CPU might simply reflect a batch job or traffic burst. Record the alert, timestamp, resource, and detection source before altering machine state.

## 2. Response objectives and priority order

When compromise is confirmed or reasonably suspected, typical objectives are:

1. Protect people, sensitive data, and critical systems.
2. Stop malicious activity from continuing or spreading to other resources.
3. Preserve evidence valuable for investigation and audit requirements.
4. Scope impacted systems, accounts, and related resources.
5. Remove unauthorized access, vulnerabilities, or persistence mechanisms.
6. Recover services from a trusted state and monitor for re-compromise.

Not every incident follows the exact same sequence. If a machine is encrypting data, spreading malware, or accessing critical systems, immediate isolation can outweigh capturing full volatile data. If the machine is the sole source of evidence for a severe incident and is not currently causing further damage, responders may capture selected RAM data before full isolation. Decisions must be made by accountable incident responders and documented.

A key principle is never deleting, formatting, terminating, or rebuilding a suspected compromised machine before evaluating evidence preservation needs. When emergency action is required to halt damage, document the rationale, decision-maker, timestamp, and potential impact on evidence.

## 3. Preparing before an incident occurs

Evidence collection becomes slow and error-prone if an organization only starts preparing after an alert fires. Every compute environment needs procedures, access rights, and tools prepared in advance.

Items to prepare:

- Contact list covering incident commanders, cloud/platform, security, application, legal, and data owners.
- Controlled emergency permissions to read logs, isolate NICs/security groups, take snapshots, and access consoles.
- Least-privilege temporary elevation procedures; responder accounts require MFA and auditing.
- Cloud audit logs, network flow logs, DNS logs, load balancer logs, EDR, and guest logs enabled, time-synchronized, and shipped centrally.
- Retention rules for logs, snapshots, disk images, memory captures, and legally relevant evidence.
- Dedicated evidence storage area—encrypted, access-restricted, with versioning or immutable retention where appropriate.
- Clean images, replacement provisioning workflows, and verified data restoration procedures.
- Platform-specific isolation runbooks and procedures to check impact on dependent workloads.

Run regular drills to verify responders can genuinely locate the target instance, take snapshots, pull logs, and isolate networking. A permission documented on paper but never tested may fail when needed.

## 4. Identifying resources and opening an incident case

Before making changes, pinpoint the exact suspected resource. An OS hostname may differ from the cloud instance name; IP addresses may have changed or been reused. Cross-check multiple identifiers.

| Information | Why record it |
|---|---|
| Cloud account/subscription/project and region | Identifies governance scope and where resources reside |
| Instance/resource ID | More stable identifier than hostname or IP |
| Hostname, private/public IP, NIC ID, and MAC | Correlates guest traces with network resources |
| Image ID, machine type, zone, and creation time | Establishes origin and initial configuration |
| Disk/volume IDs, snapshots, and encryption keys | Tracks where data lives and how to preserve it |
| IAM role/service identity and security groups/NSGs | Identifies machine permissions and communication paths |
| Application, owner, environment, and criticality | Assesses business impact |
| Alert ID, detection timestamp, and reporter | Links evidence back to detection source |

Open an incident case with a unique identifier. Record times in UTC or explicitly document timezones and clock skew. Guest clocks can drift; preserve both cloud control-plane timestamps and original guest log timestamps, then note offsets when building timelines.

Do not investigate only the machine that triggered the first alert. Identify resources sharing the same IAM role, subnet, security group, image, secrets, deployment pipeline, or network links. The attacker may have used the initial machine as a pivot point to others.

## 5. Preserving volatile evidence before shutting down

**Volatile evidence** is data that disappears when a machine powers off, reboots, or terminates processes. Examples include:

- RAM contents, running processes, and active threads.
- Open TCP/UDP connections, sockets, routing tables, and guest firewall state.
- Process trees, command lines, environment variables, and loaded modules.
- Logged-in users, active sessions, and temporary in-memory credentials.
- In-memory application data, queues, or caches not yet flushed to disk.
- Ephemeral information on open files and system activity.

If the organization has approved, authorized memory-acquisition tooling, consider capturing RAM before powering off or fully isolating the machine. Trained personnel should execute this using tested procedures. Acquisition tools can alter small portions of memory and system state; document the tool, version, command, start/end timestamps, and known side effects.

In cloud VM environments, customers typically lack direct access to physical memory or the hypervisor. Some providers do not support instance memory snapshots or memory dumps. Never assume taking a disk snapshot captures RAM; disk snapshots preserve only volume data per storage service mechanics. When memory acquisition is infeasible, document the limitation and prioritize preserving remaining logs, disks, and control-plane records.

If the machine is causing severe ongoing damage, do not delay isolation just to gather all volatile data. Prioritize stopping harm per playbook, and record which data was lost or uncollectible and why.

## 6. Gathering state information before isolation

If circumstances allow and access does not heighten risk, rapidly capture valuable live state. Use EDR, cloud guest agents, or approved investigative tools.

On Linux, useful information sources include:

```bash
date -u
hostnamectl
who -a
ps auxfww
ss -antup
ip address
ip route
sudo lsof -nP
sudo journalctl --since "2 hours ago" --utc
```

These commands show system time, hostname, sessions, process trees, connections, routes, open files, and recent logs. Depending on distribution, some commands require extra packages or elevated privileges. Avoid installing ad-hoc tools onto a suspected compromised machine when data can be gathered from pre-installed agents or disk images.

On Windows, collect equivalent state using approved tooling, for example:

```powershell
(Get-Date).ToUniversalTime()
hostname
quser
Get-Process | Sort-Object CPU -Descending
Get-NetTCPConnection
Get-NetRoute
Get-NetIPAddress
Get-WinEvent -LogName Security -MaxEvents 200
```

Queries can generate additional logs or lightly alter system state. Save outputs to access-restricted evidence storage without overwriting original logs or storing credentials. If you suspect the attacker is watching interactive sessions or holds deep admin privileges, prefer out-of-band telemetry like EDR or the cloud control plane over interactive logins.

## 7. Preserving disk evidence and snapshots

Disk evidence typically includes boot volumes, data volumes, relevant temporary volumes, and existing snapshots. Before taking snapshots, assess data consistency requirements and operational impact on the workload.

Key principles:

- Record volume IDs, sizes, volume types, encryption keys, attachments, and snapshot timestamps.
- Create snapshots via provider workflows and store them in a controlled forensic account or zone.
- Protect snapshots with encryption, least-privilege access, and appropriate retention policies.
- Note whether snapshots were captured while running or stopped, and whether filesystems/applications were quiesced.
- Never attach originals to an analysis machine in read-write mode without proper preservation procedures.
- Create working copies for analysis and keep originals read-only or protected against modification.

Snapshots of running volumes typically offer only storage-service-dependent consistency. If an application is actively writing, a snapshot resembles crash-consistent state rather than transaction-consistent state. If application-consistent snapshots are required, use supported quiesce mechanisms or backup agents, weighing whether quiescing alters state needed for investigation.

Disk snapshots do not preserve RAM, open network connections, or full process state. If a machine uses ephemeral/instance stores, data there can vanish upon stop, terminate, or certain lifecycle operations. Check instance-type documentation before changing power state.

## 8. Collecting logs from control plane and network services

Guest logs can be deleted or tampered with if an attacker gained high privileges. Collect independent telemetry from the cloud control plane and network services. Valuable sources include:

| Evidence source | What it clarifies |
|---|---|
| Cloud audit/activity logs | Who created, started/stopped, resized, attached disks, or altered NICs, security groups, IAM, or snapshots |
| Identity/IAM logs | Logins, MFA, tokens, role assumptions, permission changes, and unusual credential activity |
| VPC/VNet flow logs | Source/destination flows, ports, protocols, timestamps, and accept/reject status per service capabilities |
| DNS resolver logs | Queried domains, source machines, and timestamps |
| Load balancer/reverse proxy logs | Clients, requests, backends, response codes, and latency |
| WAF/firewall/IDS logs | Inspected requests or connections, allowed vs. blocked |
| EDR/endpoint telemetry | Processes, files, persistence, alerts, and response actions |
| Centralized OS/application logs | Logins, services, application events, errors, and configuration changes |
| CI/CD and artifact registries | Deployed versions, approvers, artifacts, and pipeline modifications |

Query a sufficiently wide window before and after detection. Anomalous activity can begin days before an alert triggers. Preserve data in native format whenever possible, keeping metadata rather than saving screenshots alone.

Flow logs usually omit payloads and may sample rather than log every packet. They aid connection metadata analysis without replacing packet captures or application logs. Also understand ingestion latency, retention limits, and how the platform represents flow states so you avoid drawing wrong conclusions from incomplete data.

## 9. Network-layer isolation of virtual machines

Network isolation stops a suspected compromised machine from communicating with other systems or the Internet while preserving needed investigative access. Implementation varies by platform, with common options including:

- Swapping the security group/NSG for a quarantine policy permitting only investigative traffic.
- Updating firewalls or network ACLs to block traffic to sensitive networks and the Internet.
- Moving the NIC or workload into an isolated subnet if supported by platform and architecture without destroying evidence.
- Applying rules at central firewalls, transit gateways, or network virtual appliances.
- Revoking credentials and cloud permissions that could be abused to open new access paths.

A quarantine policy should explicitly define:

1. Block inbound traffic from regular users and workloads.
2. Block outbound traffic to the Internet, internal networks, and other services, except approved flows.
3. Permit a controlled investigative admin path if needed, such as from a dedicated jump host or forensic workstation.
4. Permit shipping logs or telemetry to evidence storage if safe and necessary.
5. Log blocked connection attempts and policy changes.

Do not mechanically attach a "deny all" security group if doing so severs administrative channels, EDR, or required log collection. Conversely, never leave broad outbound Internet access open for convenience. Design and test quarantine policies beforehand.

Note that security groups, NSGs, ACLs, and firewalls behave differently across platforms. Stateful rules handle existing connections differently from stateless rules; some changes take time to propagate. After isolating, verify from an independent source that unwanted traffic is actually blocked.

## 10. When to stop or shut down a machine

Stopping or shutting down halts malicious processes, yet destroys volatile data. Powering off can also wipe ephemeral storage or disrupt dependent services. Base the decision on containment goals and investigative needs.

| Option | Benefit | Impacts to consider |
|---|---|---|
| Network isolation, keep running | Preserves RAM and process state for investigation; cuts external communication | Malware may continue running locally, destroying data, or awaiting triggers |
| Graceful shutdown after collection | Stops applications cleanly and reduces data corruption | Terminates processes, loses RAM; shutdown scripts may write extra changes |
| Hard stop / force power off | Halts CPU execution rapidly | Loses volatile data; filesystems may become inconsistent |
| Terminate / delete instance | Removes machine from infrastructure rapidly | Can destroy evidence, ephemeral data, and reproducibility |

If a machine is actively spreading malware, encrypting volumes, exfiltrating data, or controlling other resources, network isolation and/or emergency shutdown may be essential. If the goal is forensic investigation without immediate risk of spread, consider collecting volatile data and snapshots per runbook first.

Never delete an instance merely because a snapshot was initiated. Verify snapshot completion, metadata capture, accessible copies, and preservation requirements before changing instance lifecycle state.

## 11. Protecting identities and blocking attacker re-entry

A compromised machine may hold credentials already read or used to access other resources. Network-isolating an instance does not automatically revoke stolen credentials.

Steps commonly requiring assessment:

- Disable, rotate, or revoke potentially exposed access keys, tokens, certificates, and passwords.
- Review IAM roles/service accounts attached to the instance; scope down or temporarily revoke non-essential permissions per emergency procedures.
- Revoke active sessions or tokens where supported by the platform.
- Inspect administrative accounts, SSH authorized keys, Windows credentials, scheduled tasks, and persistence mechanisms.
- Rotate shared secrets accessible to the machine, including database credentials, API tokens, and deployment keys.
- Perform rotations from a clean administrative workstation with MFA; never reuse sessions on the suspected compromised host.
- Inspect audit logs for actions performed using the exposed identities.

IAM changes can disrupt other workloads sharing roles or secrets. Map dependencies before revoking permissions, while prioritizing halting actively abused rights. Record credential identifiers and revocation timestamps; never write actual secret values into incident records.

## 12. Evidence collection and preservation workflow

Evidence is only useful when investigators can establish its provenance, integrity, and handling history. Every artifact requires metadata and chain-of-custody tracking.

For each artifact, record at minimum:

- Unique evidence ID.
- Source resource, account/project, region, and resource ID.
- Data type: memory dump, disk snapshot, log export, packet capture, or specific file.
- Collector, witness if required by procedure, and custodian/recipient.
- Start/end timestamps in UTC, clock source, and known skew.
- Tooling, versions, commands, or operations executed.
- Cryptographic hash, typically SHA-256, of exported files right after collection.
- Storage location, encryption key, access permissions, retention, and every copy/transfer.
- Modifications or limitations that could affect integrity.

Example hashing an exported evidence file:

```bash
sha256sum evidence-disk-image.raw
```

On Windows:

```powershell
Get-FileHash .\evidence-disk-image.raw -Algorithm SHA256
```

Hashing detects file changes after the hash was computed. It does not by itself prove data was collected properly or establish origin; chain of custody and metadata remain essential.

Store originals in an evidence vault with restricted write permissions. Analyze working copies only; record hashes before and after copying. When mounting disk images, prefer read-only mode and avoid executing binaries or scripts from suspected infected images. Analysis environments must sit isolated from production networks with controlled outbound access and monitoring.

## 13. Building a timeline and scoping impact

After collecting data, combine sources to construct a UTC timeline. Never rely on a single log. For example, guest login events can be cross-referenced with identity logs, control-plane security group edits, flow logs, and load balancer requests.

A timeline may include:

1. Last known legitimate activity before anomalies appeared.
2. First suspicious login, command execution, or configuration change.
3. Moments when credentials or permissions were abused.
4. Outbound connections, data accesses, or lateral pivots to other resources.
5. Alert generation and responder acknowledgment times.
6. Start of containment, snapshots, and credential revocation.
7. Confirmation that malicious activity ceased.

Assess blast radius using these questions:

- Which accounts, keys, tokens, or roles were used on the machine?
- Which secrets, databases, object storage, queues, or control-plane APIs did the machine access?
- Were any new instances, NICs, disks, snapshots, security groups, or IAM policies created?
- Are there signs of lateral access within the subnet or across peering/VPNs?
- What data could have been read, modified, deleted, or exfiltrated?
- Do other machines share the same image, credentials, deployment artifacts, or exploitable configuration?
- Which logs are missing, deleted, or disabled during the relevant timeframe?

Separate verified facts from hypotheses. For example, flow logs showing traffic sent to an IP address do not by themselves prove the payload held sensitive data. Record confidence levels and supporting evidence for every conclusion.

## 14. Investigating working copies and fixing root cause

Once originals are preserved, create working copies in a controlled forensic or sandbox environment. Analyze:

- Login logs, `sudo`, SSH, RDP, Windows event logs, and service histories.
- Processes, startup items, cron, scheduled tasks, systemd units, and registry autoruns.
- New or modified binaries, scripts, libraries, packages, and files.
- Web shells, persistence mechanisms, and newly created accounts or keys.
- Browser/application caches, shell history, and temporary data where relevant.
- Network, DNS, proxy, firewall, and routing configurations.
- Potentially accessed secrets or tokens, following secret-handling procedures.

Never run suspicious files directly on a standard analysis workstation. Use sandboxes, appropriate forensic tools, and organizational malware-handling procedures. Engage incident response or digital forensics specialists for deep analysis when needed.

Once root cause is understood, determine eradication steps: patch vulnerabilities, revoke credentials, fix IAM/network misconfigurations, remove persistence, replace images, update applications, or tighten deployment workflows. Never delete only the malware binary while ignoring the initial entry vector; if the flaw or stolen credential remains, replacement machines can be re-compromised.

## 15. Recovering workloads from a trusted state

In many cases, safe recovery means launching fresh machines from vetted golden images, installing patches, and deploying verified application artifacts. Never assume a compromised host returns to a trusted state merely by killing suspicious processes.

A recovery workflow may include:

1. Confirm the root cause is remediated or mitigated against re-exploitation.
2. Build a new image or instance from trusted sources and the current baseline.
3. Assign a new workload identity with least privilege; regenerate host keys and agent identities.
4. Install signature/hash-verified artifacts and clean configuration.
5. Restore data from inspected, scanned backups verified to predate compromise.
6. Rotate secrets and update dependent endpoints.
7. Test health checks, security controls, logging, monitoring, and network connectivity.
8. Gradually reintroduce traffic while watching alerts for re-compromise.
9. Retain evidence and original machines per investigative or legal retention schedules.

Backups may already contain malware, web shells, stolen credentials, or altered data from before detection. Before restoring, check integrity, backup timestamps, contents, and whether the backup reintroduces the vulnerability. Never overwrite original evidence with restored data.

## 16. Scenario example: API server making unusual outbound connections

Suppose EDR detects an unfamiliar process on host `orders-api-07`, and flow logs show outbound connections to an address outside known service allowlists. The API continues serving requests normally.

A controlled response workflow:

1. Open an incident recording resource ID, NIC, IP, IAM role, volume ID, image ID, alert ID, and timestamp.
2. Correlate cloud audit logs and EDR to identify actions near the alert timestamp.
3. If risk permits, capture process trees, network connections, logged-on users, and volatile data per runbook.
4. Export guest logs plus off-host logs including flow logs, DNS, load balancer, identity, and control plane.
5. Take volume snapshots per preservation procedures, recording consistency level and encryption metadata.
6. Apply quarantine policy: block unusual outbound and lateral access; keep only approved forensic channels if needed.
7. Revoke or rotate potentially exposed credentials, and review IAM roles and secrets accessible to the host.
8. Analyze disk copies, correlate timelines, and inspect sibling hosts sharing the same image or credentials.
9. Launch a replacement host from a clean image after addressing root cause; deploy verified artifacts and test readiness.
10. Monitor the replacement host, keep the original isolated, and finalize evidence records.

If the machine is actively exfiltrating data or spreading malware, execute containment immediately according to urgency; volatile collection can be shortened or skipped. Document every decision so investigators understand what data remains intact versus lost.

## 17. Roles, coordination, and incident communication

Compute incident response requires clear role boundaries so multiple responders do not modify the same resource without coordination:

| Role | Typical responsibilities |
|---|---|
| Incident commander | Coordinates priorities, approves containment decisions, and records approvals |
| Cloud/platform engineer | Identifies resources, gathers control-plane evidence, isolates networking, and creates snapshots |
| Security/IR analyst | Analyzes alerts, telemetry, malware, timelines, and blast radius |
| Application owner | Evaluates business impact, dependencies, data exposure, and recovery readiness |
| IAM/security administrator | Revokes credentials, roles, and sessions; audits abused permissions |
| Legal/privacy/compliance | Advises on preservation obligations, notifications, and retention windows when needed |

Designate a dedicated scribe or use a case management system for automatic logging. Share status updates grounded in verified facts, avoiding speculation on root cause or scope before evidence confirms it. Share logs, disk images, or memory dumps only with authorized individuals having a clear need to know.

## 18. Common mistakes

- **Terminating machines immediately upon alert:** destroys RAM, ephemeral data, and evidence. Evaluate containment, collect volatile data if appropriate, then decide.
- **Taking only disk snapshots:** snapshots lack RAM and open connections. Explicitly document which evidence types were captured.
- **Leaving machines online for investigative convenience:** attackers can continue controlling hosts or stealing data. Use pre-built quarantine networks.
- **Blocking all networking without keeping IR channels:** can sever EDR, logging, or administrative control. Keep only approved investigative flows and verify isolation independently.
- **Trusting guest logs completely:** privileged attackers can edit or delete local logs. Cross-check control-plane and off-host telemetry.
- **Mounting original evidence read-write:** alters metadata or contents. Preserve originals and analyze read-only working copies.
- **Skipping hashing or chain of custody:** makes proving file integrity and handling history difficult.
- **Deleting only the malware:** leaves the entry vector or exposed credentials intact. Fix root cause and replace machines from trusted images where appropriate.
- **Restoring backups without inspection:** can reintroduce malware or tampered data to production. Verify backups prior to restore.
- **Overlooking IAM and secrets:** attackers can reuse stolen machine credentials via other paths. Rotate and audit related permissions.

## 19. Evidence collection and isolation checklist

- [ ] Incident opened recording decision-maker, timestamp, alert, and resource IDs.
- [ ] Account/project, region, instance, NIC, volumes, IAM role, and security policies identified.
- [ ] Ongoing damage risk assessed and order of volatile collection vs. containment decided.
- [ ] RAM and process state captured, or inability to collect clearly documented.
- [ ] Guest logs and independent cloud audit, IAM, flow, DNS, load balancer, and WAF/EDR logs exported.
- [ ] Snapshots/copies created per procedure, documenting consistency level and encryption metadata.
- [ ] Evidence tagged with unique IDs, UTC timestamps, source, tools, collector, and cryptographic hashes.
- [ ] Originals protected; analysis performed on copies inside a controlled environment.
- [ ] Machine isolated with IR-required connectivity restricted and verified from an independent source.
- [ ] At-risk credentials, tokens, keys, and IAM roles evaluated and remediated.
- [ ] Timeline and blast radius correlated across multiple data sources.
- [ ] Root cause remediated prior to workload recovery.
- [ ] Replacement machine built from trusted image; backups and artifacts verified before use.
- [ ] Enhanced monitoring, rollback plans, and evidence retention periods established.

Evidence collection and isolating suspected compromised machines are twin activities that must be coordinated together. When operations teams accurately identify resources, preserve necessary volatile and disk/log data, isolate with controlled policies, secure credentials, and maintain chain of custody, organizations contain damage while preserving a trustworthy foundation for investigation and workload recovery.
