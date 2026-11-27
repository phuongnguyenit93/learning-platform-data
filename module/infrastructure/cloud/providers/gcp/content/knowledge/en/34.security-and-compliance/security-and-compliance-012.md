# Security Incident Response and Evidence Preservation on GCP

When a compromised account is detected, a VM generates anomalous traffic, or data shows signs of unauthorized access, operations teams must simultaneously contain damage and preserve reliable information to determine what happened. On Google Cloud, evidence can be scattered across Cloud Audit Logs, Cloud Logging, Security Command Center, IAM, resource configurations, container images, disk snapshots, and business systems.

Security incident response is therefore a coordinated process across engineering, operations, risk management, and legal teams. Actions such as stopping a VM, deleting a Pod, revoking a key, changing IAM, or redeploying a service can alter traces. Responders must order actions carefully, log decisions, and preserve verifiable evidence.

This lesson covers how to prepare, detect, triage, contain, collect, and preserve evidence in a Google Cloud environment, with examples for Compute Engine, GKE, Cloud Run, Cloud SQL, Cloud Storage, and IAM identities.

## 1. Objectives and Response Principles

An incident response workflow must achieve four objectives:

1. **Protect people, services, and data.** Limit unauthorized access, data leaks, and customer impact.
2. **Understand scope and cause.** Identify affected accounts, projects, workloads, data, regions, and timeframes.
3. **Preserve evidence.** Retain raw data, metadata, timestamps, and operation history sufficient to reconstruct events.
4. **Recover with control.** Eliminate root causes, restore services safely, and monitor for recurrence risk.

During handling, apply these principles:

- **Prioritize safety and damage containment.** If active data exfiltration is underway, immediate containment may matter more than collecting every trace beforehand. Document the rationale and timestamp of that decision.
- **Capture state before making changes.** Whenever possible, snapshot resource states, IAM, networking, deployment revisions, and logs before running operations that alter the system.
- **Keep originals and work on copies.** Never edit, filter-overwrite, or directly open original evidence files with tools that could modify contents.
- **Use consistent UTC timestamps.** Record event time, collection time, and source timezone. Never assume every server clock is accurately synchronized.
- **Restrict access.** Only authorized personnel may read evidence, especially when data includes personal details, trade secrets, or credentials.
- **Log every action.** Actor, timestamp, purpose, commands or changes applied, and outcomes must all appear in the handling log.

Not every alert event is a confirmed incident. Monitoring detections require verification, yet teams must not delay containment when active intrusion indicators are present.

## 2. Preparation Before an Incident Occurs

The ability to preserve evidence depends heavily on pre-configured foundations. If audit logs were not enabled, logs already expired, or no centralized log store exists, teams may be unable to reconstruct the full sequence after an incident.

### Establishing Responsibilities and Coordination Channels

A response plan should predefine:

- Incident commander responsible for coordination and prioritizing actions.
- Cloud/SRE team managing projects, networks, VMs, GKE, Cloud Run, and databases.
- Security team analyzing alerts, identities, vulnerabilities, and intrusion scope.
- Legal, privacy, or compliance team assessing notification obligations, record preservation, and legal requirements.
- Application owners determining business impact, data integrity, and recovery criteria.

Maintain an emergency contact list, controlled break-glass access, approval procedures for isolating production, and an out-of-band communication channel independent of systems that may have been compromised.

### Enabling and Centralizing Audit Logs

Cloud Audit Logs record administrative activity and resource access. Primary log categories include:

| Log Type | Typical Contents | Notes |
|---|---|---|
| Admin Activity | Configuration changes and administrative operations | Recorded automatically; cannot be disabled |
| System Event | System events performed by Google Cloud | Useful when investigating platform-initiated changes |
| Policy Denied | Requests denied by policy | Helps detect blocked activity or permission probing |
| Data Access | Reading or writing data, accessing services | Many services require explicit opt-in; can incur log costs |

Default logs reside in Cloud Logging log buckets with varying retention. For instance, logs in `_Required` have a default retention of 400 days; `_Default` typically has a default retention of 30 days. Actual settings may have been modified. Check each bucket's retention, collected log scope, and organizational retention mandates.

For critical environments:

- Enable Data Access audit logs for services and data types requiring investigation.
- Centralize logs in a dedicated security or logging project with IAM separated from workloads.
- Create log sinks to Cloud Storage or BigQuery for analytics and long-term retention.
- Protect permissions to modify sinks, delete logs, change retention, and grant log reads.
- Audit log routing, exclusion filters, and projects outside collection scope.
- Run drills querying and exporting logs to confirm data is actually retrievable.

Log sinks only forward new logs matching the filter after the sink becomes active; they do not automatically backfill historical logs. When investigating prior timeframes, query and export logs already stored in Cloud Logging.

### Preparing an Evidence Repository

Create a dedicated project or bucket for evidence with least-privilege access and separate audit logs. Organize data by incident ID, source project, resource type, and collection timestamp.

Prepare:

- An evidence bucket with encryption, appropriate retention, and restricted delete permissions.
- A process to generate manifests containing filenames, sources, collection timestamps, collector identity, and SHA-256 hashes.
- A dedicated collector account having only permissions to read necessary data and write to the evidence repository.
- Independent backup or replication mechanisms to reduce the risk of deletion alongside the source environment.
- Legal hold procedures when legal or formal investigation mandates arise.

Cloud Storage Bucket Lock can irreversibly lock a retention policy once confirmed. Apply it only when retention duration, ownership, and legal mandates have been approved. Never enable irreversible locks impulsively during active incident response.

### Maintaining Baseline State

Record inventories of projects, folders, organizations, service accounts, critical resources, network configs, IAM policies, and deployed images. Cloud Asset Inventory can export resource states and policies for comparison at the time of an incident.

A timestamped baseline helps answer which resources newly appeared, who granted new permissions, which firewall rules recently changed, and which workloads were recently deployed.

## 3. Detection, Verification, and Incident Triage

Detection sources can include Security Command Center, Event Threat Detection, alerting logs, EDR systems, user reports, service providers, or billing anomalies.

Signals requiring investigation include:

- A service account used in an unusual region, timeframe, or workload.
- New service account keys created or anomalous key usage.
- Broad IAM permissions granted, role modifications, or unfamiliar members added.
- VMs with unexpected public IPs, processes, or network connections.
- GKE Pods running unfamiliar images, holding elevated privileges, or making unauthorized metadata server requests.
- New Cloud Run revisions using unapproved image digests.
- Cloud Storage showing bulk reads, ACL changes, or object deletions.
- Cloud SQL showing unusual connections, queries, or administrative actions.
- Changes to logging sinks, retention, audit configurations, or Security Command Center.

### Initial Triage

Immediately upon receiving an alert, open an incident record and document:

| Field | Details to Record |
|---|---|
| Incident ID | Unique identifier |
| Detection time | UTC timestamp and detection source |
| Reporter | Team or system submitting the alert |
| Project and resource | Project ID, project number, resource name, region/zone |
| Involved principal | Service account email, user, or federated identity |
| Initial indicators | Log entry, finding ID, IP, image digest, or anomalous behavior |
| Impact level | Affected services, data, customers, and regions |
| Actions taken | Timestamp, actor, justification, and outcome |

Classify severity by impact and scope, for example:

- **Low:** anomalous activity blocked, no evidence of unauthorized access.
- **Medium:** one account or workload shows compromise indicators with bounded scope.
- **High:** potential unauthorized access to sensitive data, administrative privileges, or multiple workloads.
- **Critical:** active exfiltration, spreading malware, data destruction, or severe impact on mission-critical services.

Severity can escalate or decrease as new evidence emerges. Never determine severity solely by alert count; factor in data sensitivity, principal privileges, and lateral spread potential.

### Building a Timeline

A timeline should combine:

1. First event showing anomalous signs.
2. Authentication activity and IAM changes.
3. Network or resource configuration changes.
4. Workload and data activity.
5. Detection, alert, and response timestamps.
6. Containment, collection, and recovery actions.

Use log timestamps alongside metadata such as `principalEmail`, `callerIp`, `userAgent`, `resourceName`, `methodName`, and `requestMetadata` when available. Not all fields appear in every log type or service.

## 4. Response Sequence and Containment Decisions

A response lifecycle typically spans preparation, detection and analysis, containment, eradication, recovery, and lessons learned.

~~~mermaid
flowchart TD
    A[Alert or report] --> B[Create incident record]
    B --> C[Validate and assess impact]
    C --> D{Active harm or exfiltration?}
    D -->|Yes| E[Contain immediately and record actions]
    D -->|No| F[Capture volatile evidence first]
    E --> G[Preserve logs and resource state]
    F --> G
    G --> H[Scope identities, workloads and data]
    H --> I[Eradicate root cause]
    I --> J[Recover with verified configuration]
    J --> K[Monitor and close incident]
~~~

### When Is Immediate Containment Needed?

If active data theft, destruction, or malware propagation is underway, teams must prioritize containment. For example: block outbound paths, tighten firewall rules, isolate a VM from the application network, or disable a compromised credential.

When circumstances permit, quickly capture volatile data before containment: timestamps, network connections, running processes, login sessions, active Pods/VMs, and recent logs. Never delay containment solely to collect every single detail.

### Layered Containment

| Layer | Measures to Consider | What to Evaluate |
|---|---|---|
| Identity | Disable keys, narrow IAM, block principals or credentials | May disrupt legitimate workloads; already-issued tokens may stay valid until expiration |
| Network | Restrict ingress/egress, firewall policies, routes, or endpoint access | Avoid severing administrative and evidence collection paths |
| Compute Engine | Isolate NICs or apply restrictive network rules | VM can still write to disk; stopping the instance destroys volatile memory data |
| GKE | Isolate workloads or namespaces, restrict network policies and service account permissions | Deleting Pods or draining nodes can destroy ephemeral data and runtime state |
| Cloud Run | Adjust traffic, roll back revisions, or restrict service identity permissions | Record revision config, image digest, and traffic split before changing |
| Storage/Database | Narrow read/write permissions, lock accounts, or restrict connections | Can impact active transactions and recoverability |

Never delete VMs, disks, Pods, revisions, service accounts, keys, or buckets just to "clean up" the system. Deleting resources can destroy evidence and prevent root-cause determination. If stopping a service is necessary to protect data, document prior state and justification.

## 5. Collecting Cloud Audit Logs and Cloud Logging

Cloud Audit Logs are often the primary source for determining who called an API, what operation ran, and on which resource. Start with a sufficiently wide time window around the event and expand across related principals or resources.

Example querying logs in a project by timeframe:

~~~bash
gcloud logging read 'timestamp >= "2026-11-19T00:00:00Z" AND timestamp <= "2026-11-19T06:00:00Z"' \
  --project="PROJECT_ID" \
  --format=json > incident-audit-logs.json
~~~

Filter by principal inside the audit log payload:

~~~bash
gcloud logging read 'protoPayload.authenticationInfo.principalEmail="suspicious-sa@PROJECT_ID.iam.gserviceaccount.com" AND timestamp >= "2026-11-19T00:00:00Z"' \
  --project="PROJECT_ID" \
  --format=json > principal-activity.json
~~~

Query by resource or `methodName` once the suspect service and operation are known. Do not assume a single filter will catch every trace: each service has its own resource types, method names, and payload structures.

After exporting:

- Keep the original JSON file intact; never edit it directly to sanitize data.
- Record the filter, project, timeframe, execution timestamp, and collector identity.
- Compute SHA-256 and record it in the manifest.
- If analysis or normalization is needed, create a separate working copy.
- Check record counts, query errors, pagination limits, and the retrieved time range.

The examples above read logs and write to local files. For production environments, use a controlled collection host, protect the output directory, and transfer evidence into an approved vault. Never post logs containing personal data or sensitive details into unauthorized communication channels.

### Log Types to Inspect

- **Cloud Audit Logs:** principal, API method, caller IP, user agent, resource, and status.
- **VPC Flow Logs:** network flows recorded per subnet configuration; not full packet capture.
- **Firewall Rules Logging:** connections matching rules with logging enabled.
- **Cloud DNS logs:** DNS queries if logging is enabled.
- **Load Balancer logs:** requests, status codes, latency, backends, and client addresses per configuration.
- **GKE audit/control-plane logs:** Kubernetes API operations and configured control plane events.
- **Application and OS logs:** authentication, processes, packages, endpoints, errors, and business operations.

VPC Flow Logs and load balancer logs may use sampling or omit fields. They aid flow investigation but do not replace packet captures or application logs.

## 6. Preserving Evidence by Resource Type

Evidence can include logs, configurations, metadata, snapshots, data copies, image digests, findings, and deployment history. Each type requires its own collection method.

### IAM and Service Identities

Collect current IAM policies, service account details, key metadata, project-level permissions, and related change logs.

~~~bash
gcloud projects get-iam-policy "PROJECT_ID" \
  --format=json > project-iam-policy.json

gcloud iam service-accounts keys list \
  --iam-account="SUSPICIOUS_SA@PROJECT_ID.iam.gserviceaccount.com" \
  --project="PROJECT_ID" \
  --format=json > service-account-key-metadata.json
~~~

The key listing command retrieves metadata only; it does not export private keys. Record key IDs, states, creation timestamps, and associated principals if available. Also check inherited IAM policies at the organization and folder levels, service account impersonation, workload identity federation, and group-based grants.

Never download private keys to "inspect" them. Do not place secret payloads, access tokens, or private keys into evidence files. For Secret Manager, collect version metadata, IAM policies, and access audit logs; avoid reading secret values without approved investigative authorization.

### Cloud Asset Inventory

Cloud Asset Inventory supports capturing resource state or IAM policies at a specific point in time. Example exporting a project's resources to an evidence bucket:

~~~bash
gcloud asset export \
  --project="PROJECT_ID" \
  --content-type=resource \
  --output-path="gs://EVIDENCE_BUCKET/INCIDENT_ID/assets.json" \
  --snapshot-time="2026-11-19T06:00:00Z"
~~~

Ensure the collector has permissions to read assets and write to the destination. Record snapshot time, project scope, and exported content type. When change history is needed, pair snapshots with Cloud Audit Logs; a single snapshot does not show who modified resources.

### Compute Engine

For a suspected compromised VM, collect:

- Instance metadata, zone, machine type, network interfaces, IPs, tags, and service account.
- Boot disk, attached disks, snapshots, and related firewall configurations.
- Serial port output, system logs, OS Login, or SSH metadata where available.
- Security agent, OS, application, and VPC Flow Logs.
- Image, startup script, metadata, and deployment history.

Example recording instance metadata:

~~~bash
gcloud compute instances describe "VM_NAME" \
  --zone="ZONE" \
  --project="PROJECT_ID" \
  --format=json > instance-description.json
~~~

You can create a persistent disk snapshot to preserve disk state at a point in time:

~~~bash
gcloud compute disks snapshot "DISK_NAME" \
  --zone="ZONE" \
  --snapshot-names="INCIDENT_ID-DISK-SNAPSHOT" \
  --project="PROJECT_ID"
~~~

Snapshotting a running VM typically yields crash-consistent state and does not guarantee applications or databases flushed data consistently. For databases, prefer backups or proper quiescing procedures and document the collection method. Never attach an original disk directly to an analysis machine if mounting could write to the disk; create a working clone and mount read-only when appropriate.

If memory contents or process state are needed, disk snapshots do not replace memory acquisition. Cloud memory acquisition may be constrained by the platform and require specialized tools, permissions, or support. Document this limitation in the report.

### Google Kubernetes Engine

In GKE, critical evidence can vanish when Pods are deleted or nodes are replaced. Before restarting, draining, or redeploying, consider collecting:

- Cluster, node pools, nodes, namespaces, Pods, owner references, and workload status.
- Image names and digests, commands/args, service accounts, and security contexts.
- Deployments, StatefulSets, DaemonSets, Jobs, CronJobs, Services, Ingresses, and NetworkPolicies.
- Kubernetes events, audit logs, and control-plane logs.
- Node disks, container runtime logs, and application logs.
- RBAC permissions, Workload Identity mappings, and network configurations.

Selected commands to capture Kubernetes state:

~~~bash
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl get deployments,statefulsets,daemonsets,jobs,cronjobs -A -o yaml
kubectl get nodes -o wide
~~~

YAML outputs can contain sensitive configurations. Review storage permissions and strip secret payloads from shared copies; protect originals under evidence procedures. Never run commands exporting all Kubernetes Secrets solely for general investigation. If a specific secret is needed, obtain approval, document justification, and restrict access.

Avoid deleting Pods or draining nodes before assessing runtime state collection needs. When containment is necessary, apply network or permission restrictions and document the exact changes made.

### Cloud Run

For Cloud Run, capture the service, revisions, traffic splits, image digests, runtime service account, region, network configuration, environment variables, and Secret Manager references. Distinguish plain configuration values from secret references; exclude secret payloads from exports.

Collect Cloud Audit Logs for deploy/update operations, revision Cloud Logging, request logs, application logs, Artifact Registry metadata, and image provenance if available. Record the revision currently receiving traffic and prior revisions. Rollbacks alter traffic and active runtime state, so capture configurations beforehand.

### Cloud SQL and Databases

Collect instance metadata, network configuration, authorized networks, private IP, IAM database authentication, DB accounts, backups, PITR windows, and available logs. Inspect Cloud Audit Logs, database engine logs, connections, queries, exports, and backup activity.

If data preservation is needed, use backups or clones via approved procedures. For systems with active transactions, consider consistency and snapshot timing. Never run investigative queries that modify business data or erase traces. Keep original backups intact, analyze clones, and document recovery points.

### Cloud Storage

For affected buckets, record bucket metadata, location, IAM policy, uniform bucket-level access, public access prevention, retention policy, object versioning, and lifecycle rules. Collect Cloud Audit Logs Data Access if enabled, plus access logs from other systems.

Never delete suspect objects or overwrite original objects. If versioning is enabled, preserve relevant object generations. If versioning is disabled, overwritten or deleted objects may be unrecoverable; explicitly document that limitation. When copying objects to an evidence bucket, preserve necessary metadata, generations, checksums, and provenance. A copy does not replace the original and does not by itself prove data was unaltered prior to collection.

## 7. Preserving Integrity and Chain of Custody

Evidence is only credible when you can account for its origin, collection process, who accessed it, and whether contents remained unaltered.

### Generating Manifests and Hashes

After exporting an evidence file, compute its SHA-256 hash. On Linux:

~~~bash
sha256sum incident-audit-logs.json
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\incident-audit-logs.json -Algorithm SHA256
~~~

Record the output in a dedicated manifest. Example:

| Field | Sample Content |
|---|---|
| Evidence ID | EV-0001 |
| File | incident-audit-logs.json |
| Source | Cloud Logging, project payments-prod |
| Query/filter | Full filter or query reference ID |
| Time range | 2026-11-19T00:00:00Z to 2026-11-19T06:00:00Z |
| Collection time | 2026-11-19T06:20:00Z |
| Collector | analyst@example.com |
| SHA-256 | Hash of collected file |
| Storage | Bucket, object path, and generation |
| Custody history | Handover party, recipient, timestamp, purpose |

Hashes detect modifications after hash calculation; they do not prove source data was complete or accurate prior to collection. Therefore, also document source, query method, and context.

### Chain of Custody

Every time evidence is copied, transferred, opened, or analyzed, record:

- Evidence ID and content description.
- Collector, custodian, recipient, and roles.
- UTC date/time and access purpose.
- Storage location, access permissions, and seal status.
- Pre- and post-transfer hashes whenever copied.
- Tools, tool versions, and operations performed.

Keep originals read-only or equivalent; analyze copies. If format conversion, filtering, or decompression is required, preserve originals untouched and document conversion steps.

### Controlling the Evidence Repository

An evidence repository needs:

- Dedicated IAM, separated read and write permissions, and no broad delete permissions.
- Encryption at rest and in transit.
- Appropriate retention, plus legal hold when mandated.
- Audit logging for reads, writes, IAM changes, and deletions.
- Independent backups or protections against compromised source admin accounts.
- Data classification and retention periods aligned with privacy policies.

Never use a bucket suspected of compromise as the sole evidence repository. If source admin accounts may be compromised, store copies in a security project with independent principals and governance boundaries.

## 8. Security Command Center and Investigating Blast Radius

Security Command Center (SCC) aggregates findings on misconfigurations, vulnerabilities, and threats depending on enabled tier, services, and configuration. Findings are investigative leads, not final conclusions.

When reviewing a finding, record:

- Finding ID, category, severity, state, and detection timestamp.
- Resource name, project, folder, or organization.
- Source, detector, and technical description.
- Event time, create time, update time, and external URIs if present.
- Handling status, assignee, and links to related evidence.

Correlate findings with Cloud Audit Logs, Cloud Asset Inventory, network logs, application logs, and live resource states. A finding may already be remediated or closed while historical logs still require preservation. Never delete or clear findings just to tidy dashboards before capturing necessary records.

## 9. Eradicating Root Causes and Restoring Services

After scoping the incident, teams must eliminate entry vectors and recover from a trusted state.

Typical steps include:

1. Identify the principal, credential, workload, image, or configuration causing the incident.
2. Revoke or replace compromised credentials; check impersonation rights and associated keys.
3. Remove unauthorized IAM bindings, unfamiliar resources, firewall rules, or backdoor access paths.
4. Rebuild workloads from verified images and artifacts; never reuse images suspected of malware tampering.
5. Restore data from backups verified for integrity and a clean point in time.
6. Test functionality, access permissions, network flows, audit logs, and monitoring visibility.
7. Restore traffic incrementally and monitor for signs of re-compromise.

Never simply change a password and close the incident. Attackers may have created new service accounts, added SSH keys, altered startup scripts, deployed hidden workloads, or modified log sinks. Check for persistence across IAM, Compute Engine metadata, GKE RBAC, Cloud Run revisions, Cloud Scheduler, Pub/Sub, Cloud Functions/Workflows, firewalls, DNS, and CI/CD.

When revoking a service account key, preserve metadata and logs first if circumstances allow. Disabling a key stops new signatures with that key, yet already-issued access tokens can remain valid until expiration. Also evaluate IAM permissions, active sessions/tokens, and related identities.

## 10. Hands-On Example: Suspected Compromised Service Account Key

Suppose Security Command Center detects a production project service account used from an unfamiliar IP address. Audit logs reveal that principal calling data-read APIs and modifying IAM within the same timeframe.

Sample handling workflow:

**Step 1 — Open record and verify.** Log incident ID, UTC timestamps, project, service account email, IP, method names, resources, and finding ID. Determine the service account's permissions across projects, folders, and the organization.

**Step 2 — Preserve initial data.** Export audit logs across a window wider than the event, save current IAM policies, key metadata lists, asset inventories, and workload states. Compute hashes and update the manifest.

**Step 3 — Expand scope.** Search for service account key creations, role grants, impersonations, VM creations, revision deployments, bucket creations, sink edits, and data accesses. Check other projects where the principal holds permissions.

**Step 4 — Contain.** If key compromise is confirmed, disable the suspect key and narrow the principal's permissions. If active exfiltration is indicated, apply appropriate data-access or network blocks. Record timestamps and impact of every action.

**Step 5 — Remove persistence.** Inspect other keys on the service account, unfamiliar IAM principals, impersonation bindings, new workloads, scheduled jobs, and anomalous sinks. Delete or disable unauthorized components after preserving necessary evidence and obtaining approval.

**Step 6 — Recover and monitor.** Provision replacement credentials via secure workflows, re-apply least-privilege permissions, deploy clean workloads, and monitor audit logs. Verify legitimate consumers operate normally before closing the incident.

Conclusions must never say merely "key disabled." The report must answer when the key was created, who could access it, where it was used, which data may have been read or altered, which permissions were abused, and whether any remaining access paths persist.

## 11. Incident Reporting and Lessons Learned

The final report must be clear enough for engineering, management, and compliance teams to understand the same sequence of events.

A report typically includes:

- Incident summary and impact level.
- Scope across organization, folders, projects, regions, resources, and data.
- UTC timeline from first indicator to full recovery.
- Principals, IPs, API methods, image digests, and affected resources.
- Collected evidence, Evidence IDs, hashes, and storage locations.
- Containment actions, IAM changes, credential revocations, and business decisions.
- Confirmed root cause and unconfirmed hypotheses.
- Data potentially accessed, modified, deleted, or leaked.
- Recovery status, testing, and post-recovery monitoring.
- Notification obligations, legal holds, and approvers if applicable.
- Remediation follow-up items, owners, and deadlines.

Post-incident, update playbooks, break-glass permissions, logging coverage, retention, alerts, resource baselines, and tabletop drills. Re-check whether any projects fail to ship logs, whether required Data Access audit logs remain disabled, whether workloads can alter sinks, and which accounts hold evidence deletion permissions.

## 12. Incident Response and Evidence Preservation Checklist

### Upon Detection

- [ ] Created incident ID and designated incident commander.
- [ ] Recorded UTC timestamps, alert source, project, resource, and involved principals.
- [ ] Assessed impact on data, services, and customers.
- [ ] Ensured reliable coordination channels and emergency access.

### Before and During Containment

- [ ] Captured IAM, network, workload, and revision state where feasible.
- [ ] Collected necessary volatile data when doing so does not increase harm.
- [ ] Logged exact containment actions, actors, timestamps, and justifications.
- [ ] Avoided deleting resources, Pods, disks, revisions, logs, or credentials before assessing evidence needs.

### Collection and Preservation

- [ ] Exported relevant Cloud Audit Logs, application logs, and network logs.
- [ ] Saved IAM policies, key metadata, and resource states.
- [ ] Collected appropriate snapshots/backups for VMs, GKE, Cloud SQL, or Storage.
- [ ] Generated SHA-256 manifests for every evidence file.
- [ ] Stored originals in a separate, restricted vault with appropriate retention.
- [ ] Documented full chain of custody and access history.

### Recovery and Incident Closure

- [ ] Removed persistence mechanisms and revoked compromised credentials.
- [ ] Recovered from verified artifacts or backups.
- [ ] Verified IAM, networking, data, workloads, and logging post-recovery.
- [ ] Monitored for signs of re-compromise.
- [ ] Completed reports, notification obligations, and preventive follow-up actions.

Incident response on Google Cloud requires balancing containment speed against event reconstruction capability. Cloud Audit Logs, Cloud Logging, Security Command Center, Cloud Asset Inventory, and resource snapshots provide distinct pieces of evidence. When teams log every change, protect originals, verify hashes, and maintain chain of custody, investigative findings become reliable and recovery remains tightly controlled.
