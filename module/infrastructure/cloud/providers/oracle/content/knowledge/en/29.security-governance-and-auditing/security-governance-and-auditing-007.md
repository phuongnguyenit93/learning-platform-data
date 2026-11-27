# Incident response and evidence preservation on OCI

## 1. Objectives and scope

In the **Security, Governance, and Auditing** chapter of the Oracle Cloud Infrastructure (OCI) module, this lesson guides organizing incident response from initial signal intake through service recovery and completing the evidence record.

The scope covers tenancy, compartments, IAM, VCN, Compute, Object Storage, and Oracle Database services. The focus is coordinating technical actions with explainability: who made the decision, what was changed, where data was collected from, and what limitations remain in the conclusions.

After this lesson, learners will be able to:

- Classify signals, define scope, and assign handlers.
- Choose containment actions appropriate to the resource and credential type.
- Collect logs, configurations, and volume copies while documenting impact on the system.
- Create manifests, compute SHA-256 hashes, and maintain an evidence chain of custody.
- Design evidence storage with access controls, retention, and decryption availability.
- Practice exporting Audit via OCI CLI on PowerShell and verifying stored copies.
- Define recovery criteria alongside post-incident improvement metrics.

The templates, roles, priority levels, and criteria in this lesson are recommended operational practices. They must be adapted to your organization's actual structure and requirements.

## 2. Concepts to distinguish

| Concept | Meaning in the workflow | Example |
| --- | --- | --- |
| Event | A single recorded occurrence | An API call |
| Alert or finding | A signal requiring review | Cloud Guard reports a notable configuration |
| Incident | An event assessed as needing response procedures | Credential used without authorization |
| Artifact | Data collected during investigation | Log file, NSG config, volume backup |
| Evidence | An artifact managed with provenance and custody records | Audit export with scope, hash, and collector |
| Containment | Limiting ongoing harm | Revoking credentials or blocking access paths |
| Eradication | Removing root cause and persistence mechanisms | Removing unauthorized permissions, redeploying from trusted source |
| Recovery | Restoring service with verification | Shifting traffic to a clean system |

An alert does not prove an intrusion occurred. Conversely, the absence of alerts is insufficient to prove no unauthorized activity took place.

In records, separate three types of statements:

~~~text
Fact: An API configuration update was recorded at 02:12Z.
Hypothesis: The pipeline credential may have been compromised.
Provisional conclusion: Inspect the credential and calling source before attributing blame.
~~~

A principal identifier indicates which technical identity was used; identifying the human actor requires cross-referencing authentication systems, pipelines, admin hosts, and access permission context.

## 3. Preparing before an incident

### 3.1. Roles and decision authority

Oracle recommends having an incident response plan, communication procedures, escalation mechanisms, and stakeholder coordination. Evidence preservation should be embedded within that workflow. [Oracle: Risk and Compliance](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/risk-and-compliance.htm).

One usable role assignment model:

| Role | Responsibilities |
| --- | --- |
| Incident commander | Finalize priority, assign tasks, and decide trade-offs |
| Investigator | Collect, analyze, and document data limitations |
| Evidence custodian | Manage stored copies, manifests, read permissions, and handovers |
| Service owner | Assess application impact, RTO, and recovery criteria |
| IAM/network/DB admin | Execute changes within expertise and authorized scope |
| Legal, compliance, comms lead | Determine notification obligations and shareable content |
| Oracle Support liaison | Escalate service-side details requiring vendor assistance |

In small teams, one person may wear multiple hats, though a second person should verify high-impact decisions or critical evidence intake.

Runbooks must specify in advance who is authorized to revoke credentials, isolate Compute, modify routing, restrict databases, or fail services over to a recovery environment.

### 3.2. Preparing tools and repositories

Prepare the following components ahead of time:

- Response accounts independent of regular workload credentials.
- Trusted acquisition host, OCI CLI, and verified investigation tools.
- Dedicated evidence compartment, separate permission groups, and private buckets.
- Permissions to read Audit, logs, and configurations in relevant compartments and regions.
- Logging for critical sources; export mechanisms and transfer-failure monitoring.
- Capacity, quotas, and standby budget for backups, analysis copies, and recovery services.
- Contact lists and coordination channels that remain usable if IAM or email is impacted.

Drill the scenario where on-call engineers cannot use their everyday administrative accounts. Response permissions must suffice for the task, be logged, and be reviewed after every use.

### 3.3. Timestamp and identifier conventions

Every incident should have its own ID, such as `IR-2026-0042`. Every artifact has an evidence ID, such as `E-001`.

Use UTC as the baseline reference and keep original timestamps inside artifacts untouched. If displaying Vietnam time, state UTC+07:00 explicitly; never alter timestamps inside raw files just to make a report easier to read.

Record concurrently:

- Tenancy OCID, compartment OCID, and region.
- Resource OCIDs, principals, and credential identifiers if provided by the source.
- Event time, ingestion time, and collection time.
- Time zone, clock sync status, and known drift of the acquisition host.
- Exact commands, tool versions, and query scope.

Do not use display names as unique identifiers because names can change or collide.

## 4. Response workflow and evidence to produce

~~~mermaid
flowchart TD
    A["Signal from Cloud Guard, logs, or users"] --> B["Triage and open ticket"]
    B --> C{"Ongoing harm?"}
    C -->|"Yes"| D["Prioritize containment per authority"]
    C -->|"Undetermined"| E["Collect initial facts and verify"]
    D --> F["Collect evidence during and after containment"]
    E --> F
    F --> G["Analyze scope and root cause"]
    G --> H["Eradicate cause and recover"]
    H --> I["Verify, monitor, and post-incident review"]
    F --> J["Manifest and chain of custody"]
    J --> G
~~~

Collection and containment often happen in parallel. When ongoing data loss or lateral movement is a risk, authorized personnel may prioritize halting harm and explicitly document which evidence might be lost due to that decision.

| Phase | Core question | Output record |
| --- | --- | --- |
| Intake | Is the signal credible and does it require escalation? | Reporting source, timestamp, intake handler |
| Assessment | Which resources, identities, and data are involved? | Initial scope, facts, and hypotheses |
| Containment | How to limit harm with proportionate impact? | Decision, before/after configs, and check results |
| Collection & analysis | Does data allow reconstructing the sequence? | Artifacts, manifest, timeline, limitations |
| Eradication & recovery | Have root cause and access paths been resolved? | Fixes, clean deployment source, and verification |
| Post-incident review | Which controls need to change? | Root cause, lessons learned, owner, and due date |

A phase can be reopened when new findings change the scope. For instance, finding a credential used in another region requires expanding the investigation rather than keeping conclusions from the first region.

## 5. Initial assessment: prioritizing the right issue

### 5.1. Collecting minimum information

Immediately upon opening a case, record:

1. Signal source, detection time, and problem/alert ID if any.
2. Referenced resources and accounts.
3. Environment: production, development, or lab.
4. Signs of loss of confidentiality, integrity, or availability.
5. Recent authorized changes that might explain the signal.
6. Actions already taken, including automation and operator steps.

An internal priority scale can be based on scenarios:

| Scenario | Suggested priority | Initial focus |
| --- | --- | --- |
| Active unauthorized access to critical data | Urgent | Restrict access and preserve trails |
| Suspected compromise of admin-level credential | High | Check permission scope and all auth paths |
| Public configuration with no access evidence yet | By data sensitivity | Verify exposed objects |
| Unusual admin action matching an approved change | Needs verification | Cross-check identity, time, and request |

This is not an Oracle default classification. Even a small resource can lead to a major incident if it holds credentials accessing critical systems.

### 5.2. Building a scope matrix

Mark each compartment and region combination as **collected**, **collecting**, **no source**, or **not yet checked**.

Expand from the initial resource to:

- IAM policies, group memberships, dynamic groups, and related credentials.
- Compute instances, VNICs, volumes, buckets, or databases accessible to the principal.
- Pipelines, secrets, registries, and application systems sharing the same identity.
- Other subscribed regions and other compartments within permission scope.

Document reasons for excluding any branch from scope. Do not treat an empty query in one compartment as proof for the entire tenancy.

## 6. Selecting evidence sources on OCI

### 6.1. Source map and limitations

| Source | Question it helps answer | Limitations to note |
| --- | --- | --- |
| OCI Audit | Which API was called, by which identity, on which resource? | Does not replace in-OS logs or SQL audit |
| Cloud Guard | Which problem appeared and what response ran? | Findings are investigation starting points |
| IAM and IdP | How did auth, credentials, and permissions change? | Must cross-check account types and login sources |
| VCN Flow Logs | What traffic was recorded on a VNIC? | Subject to capture filters and sampling config |
| Object Storage service logs | Which object read/write actions were logged? | Must verify categories and log enablement status |
| OS, EDR, application logs | What signs appear in processes and workloads? | Compromised hosts can reduce log trustworthiness |
| Boot/block volume backups | Point-in-time disk data state | Does not capture volatile memory |
| Database audit and Data Safe | Which inside-database activities were logged? | Depends on audit policies and collected sources |
| Infra config, IaC, pipelines | Which configuration was deployed and by whom? | Current state may differ from incident time |

### 6.2. OCI Audit and data access logs

OCI Audit automatically records calls to supported public APIs, including operations via Console, CLI, and SDK. Per Oracle documentation, for Object Storage, Audit records bucket-level events but not per-object events. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Therefore, seeing a bucket configuration change event does not prove objects were downloaded. Cross-check object access log sources.

Object Storage service logs have separate read and write categories. For example, read logs can contain GET/LIST/HEAD; write logs contain PUT/POST/DELETE. Oracle describes delivery of these logs as best effort, so the absence of a log record cannot be taken as absolute proof that access did not occur. [Oracle: Details for Object Storage](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_object_storage.htm).

In investigations, record when logs were enabled, categories, retention, interruptions, and actual data ranges retained. Enabling logs after an incident does not retroactively create records that were never captured.

Audit currently has a 365-day retention period; this setting applies at the tenancy level and is non-configurable. Do not extrapolate that duration to every other log type on OCI. [Oracle: Audit Log Retention Period](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm).

### 6.3. VCN Flow Logs

Flow logs record traffic accepted or rejected according to relevant rules. Capture filters and sampling rates affect which flows enter the logs. When exporting data, also collect the active filter configuration. [Oracle: Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

Use this source to cross-check endpoints, traffic direction, and timestamps, then combine with application logs. Do not treat flow logs as full packet captures or complete payloads transmitted.

### 6.4. Database evidence

API calls managing database resources and SQL operations inside the database are two different layers. Database investigations require coordinating with DBAs to identify audit policies, audit trails, and collection status.

Oracle Data Safe can collect audit records from audit trails of registered databases, such as `UNIFIED_AUDIT_TRAIL`, when collection is enabled. Record the target database, trail, time window, and collection gaps. [Oracle: Audit Trails](https://docs.oracle.com/en-us/iaas/data-safe/doc/audit-trails.html).

For managed services such as Autonomous Database, use diagnostic and audit sources provided by the service; do not apply Compute SSH and disk imaging procedures to every database type.

## 7. Containing incidents while preserving investigability

### 7.1. Before every change

The operator should record beforehand:

~~~text
Objective: Which access path is being restricted?
Scope: Which specific resources and identities?
Current state: Where are existing configs and evidence saved?
Impact: Which services, sessions, or data may be affected?
Decision: Who approved it and at what time?
Verification: Which test confirms containment succeeded?
Rollback: Which conditions permit reversing the change?
~~~

If ongoing harm makes capturing full pre-change state impossible, explicitly log the decision to prioritize containment and which data could not be collected.

### 7.2. When credential compromise is suspected

Use a trusted response identity to check:

- Which principal and credential types were used.
- Whether the credential is shared across multiple pipelines or services.
- Whether new credentials, login sessions, or permissions were created after the suspected time.
- Which accounts need revocation, key rotation, permission restriction, or disabling.
- Which dependent systems must be updated with replacement credentials.

OCI has multiple credential types such as Console passwords, API signing keys, auth tokens, and customer secret keys. Handling one type does not mean the remaining types are handled. [Oracle: Managing User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm).

For federated logins, coordinate with the IdP to handle related sessions and auth factors. For instance/resource principals, inspect the workload itself, dynamic groups, and effective policies—not just a user API key.

Retain fingerprints or credential identifiers needed for correlation; never include private keys, tokens, or passwords in manifests or notification messages.

### 7.3. When Compute compromise is suspected

The goal is usually restricting malicious connections while maintaining controlled investigation paths.

**Do not treat an empty NSG as a mechanism that overrides other permissive rules.** For a VNIC, subnet security lists and associated NSGs combine into the effective set of permissive rules. Traffic may also belong to existing tracked stateful connections. [Oracle: Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Recommended sequence:

1. Record the instance OCID, all VNICs, IP addresses, subnets, NSGs, and volume attachments.
2. Capture rule and routing configurations before changing them.
3. Identify actual ingress/egress paths, including secondary VNICs and internal connections.
4. Apply the prepared containment plan, accounting for all effective rules.
5. Verify from an independent source that the blocked traffic truly ceases functioning.
6. Document service impact and remaining authorized investigation channels.

Do not delete a shared security list solely to isolate one machine. That can disrupt other VNICs in the subnet.

Stopping or rebooting an instance destroys running memory state. Weigh this decision against the risk of ongoing data loss; no single ordering fits every incident.

### 7.4. With Object Storage and databases

For a bucket suspected of unauthorized access, save its configuration and related identities, then review public access, IAM, pre-authenticated requests, and active credentials. A resource remaining private is not enough to prove every access path is controlled.

For databases, work with DBAs to restrict relevant accounts or connection paths, preserve audit trails, and plan recovery. Avoid bulk-changing audit policies or purging trails mid-investigation.

In both cases, document which action addresses current exposure and which action fixes the configuration source that could reintroduce that exposure.

## 8. Collecting volatile data and disk state

### 8.1. Prioritizing by volatility

A possible order of consideration:

| Data | Why decide early? | How to document |
| --- | --- | --- |
| RAM, processes, open connections | Changes rapidly, lost on shutdown | Tool, timestamp, and collection impact |
| Temp files and rotating logs | May be overwritten or deleted | Paths, scope, and collection time |
| Network/IAM configurations | May be altered during containment | Before/after copies and operator |
| Boot/block volumes | Workload continues writing to disk | Backup/copy OCID and timestamps |
| Logs in central services | Have separate retention and latency | Query, source, and data range |

For live collection on a host suspected of compromise, use verified tools and log every change caused by the tool. Data returned by that OS must be cross-checked against independent sources.

Do not bulk-install new tools or run multiple scanners before deciding on a collection strategy. Those activities alter files, logs, and memory and can obscure initial indicators.

### 8.2. Boot volume and data volume backups

OCI allows creating a boot volume backup while attached to a running instance; the copy is crash-consistent, reflecting disk state similar to a sudden power-off. It is not a RAM capture. [Oracle: Boot Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bootvolumebackups.htm).

A disk-state preservation workflow:

1. List the boot volume and each associated block volume.
2. Record source volume OCIDs, sizes, attachments, and encryption keys.
3. Choose an appropriate backup or copy method, documenting the rationale.
4. Record request timestamp, copy identifier, and completion state.
5. Verify all volumes are covered; a boot backup does not automatically include data volumes.
6. Restrict delete permissions, adjust retention, and protect copies to preserve.
7. Restore to a separate analysis copy in an isolated investigation environment.

Volume group backups support consistency across multiple volumes. Application-consistent backups require application coordination such as quiescing or flushing, so document those operations and their impact. [Oracle: Block Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

If application consistency cannot be achieved without significantly altering live state, document the capture's limitations rather than calling it an ideal application-consistent copy.

### 8.3. Preservation copies and working copies

Keep original backups or captures under controlled access. Create separate copies for analysis.

Never boot directly from a preservation copy. When analyzing filesystems, use platform-appropriate read-only attachment and mounting mechanisms; consider whether mounting might automatically write metadata or replay filesystem journals.

Backups managed by the Block Volume service and objects in a team's evidence bucket are two different resource types. Do not assume a log bucket's retention rule protects volume backups.

For Block Volume backup retention, deletion prevention, or indefinite holds, inspect configurations and permissions specific to those features. [Oracle: Block Volume Backups — retention permissions](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

Nor does a volume backup OCID replace the hash of an exported disk image file. Without a file-based disk image, record the exact artifact type with its identifier and service record—never fabricate a SHA-256 hash for uncollected content.

## 9. Designing evidence storage

### 9.1. Separating collectors, analysts, and retention custodians

A dedicated compartment helps organize resources and delegate permissions, but does not automatically create independence from accounts with tenancy-wide admin privileges.

Permissions can be split as:

| Role | Role-based permissions |
| --- | --- |
| Collector | Read sources and create artifacts in intake location |
| Investigator | Read assigned evidence, write separate analysis outputs |
| Retention custodian | Manage retention periods and handovers |
| Auditor | Read manifests, access history, and decisions |
| Key administrator | Ensure decryption availability under separate workflow |

The evidence repository should be private, with access tracking and controlled transfer paths. Never use public access links for handovers.

If the threat model includes a compromised tenancy administrator, evaluate a more independent store, such as another organization-managed collection system. Choosing another tenancy or region must include checking permissions, transfer paths, and data residency rules.

### 9.2. Retention is not versioning

Object Storage retention rules protect objects during the active period. Time-bound rule durations are calculated from each object's Last Modified timestamp. Locking a rule is irreversible, with a mandatory 14-day delay; once locked, retention duration can only be increased. [Oracle: Object Storage Data Retention Rules](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

An active rule protecting data differs from the locked configuration state of the rule itself. Therefore, record both when protection starts applying and when the lock actually takes effect.

Do not design a bucket with both versioning enabled and active retention rules: OCI has constraints between these two features. [Oracle: Object Storage Data Retention Rules — interactions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

Versioning keeps versions, yet versions can still be permanently deleted given corresponding operations and permissions. It does not substitute for retention protection against deletion. [Oracle: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

For indefinite retention needs, OCI offers indefinite retention rules; these rules cannot be locked. Retention duration and rule removal authority must be finalized by the organization before use. [Oracle: Creating an Object Storage Data Retention Rule](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules_topic-To_create_a_retention_rule.htm).

In the lab, use the prepared retention policy; do not test long-term retention locks on data or resources that need cleanup after class.

### 9.3. Preserving decryption capability

Record Vault/key OCIDs and encryption dependencies of artifacts. Never respond to a compromised credential by deleting an encryption key protecting evidence.

Oracle states that data encrypted with a key in Pending Deletion state becomes inaccessible. Response procedures must protect both data and the ability to use valid decryption keys. [Oracle: Deleting a Key](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/managingkeys_topic-To_delete_a_key.htm).

## 10. Manifests and evidence chain of custody

### 10.1. Manifest describing an artifact

A manifest is a record describing a collection run, not proof of every hypothesis. Recommended template:

| Field | Information to record |
| --- | --- |
| Incident ID, evidence ID | Case and artifact identifiers |
| Source | Service, tenancy, compartment, region, and resource OCID |
| Scope | Time window, filters, and query scope |
| Acquisition | Command, tool version, collecting principal |
| Times | Collection start/end timestamps in UTC |
| Artifact | Filename or backup OCID, size if applicable |
| Integrity | Algorithm and hash of collected file |
| Storage | Bucket, object name, version ID if applicable |
| Limitations | Missing data, latency, sampling, or collection-induced changes |
| Custody | Recipient, purpose, and handover instance |

For file-based artifacts, compute hashes immediately after writing finishes and re-verify when copying. NIST describes integrity verification and custody tracking as parts of the digital forensics process. [NIST SP 800-86](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-86.pdf).

### 10.2. What does a hash prove?

In the lab, use SHA-256 to compare exact bytes of the same file between two checks.

A matching hash helps confirm the file has not changed relative to the recorded trusted hash. It does not prove on its own that:

- The original source was untampered.
- The collection window covered every event.
- The collector did not alter data before hashing.
- An incident or an individual's culpability has been established.

Do not use an Object Storage ETag as a default SHA-256 value. Store the artifact hash, object identifier, and service metadata separately.

If both the artifact and manifest can be altered by the same person, both files could be modified together. Store manifests in a change-controlled system; optionally digitally sign manifests per organizational process.

### 10.3. Logging every handover

Each transfer of an artifact or access grant should record:

~~~text
Evidence ID: E-001
Giver / recipient: authenticated identities
UTC timestamp: handover time
Purpose: timeline verification
Source / destination location: storage identifiers
Hash before / after: file SHA-256
Verification result: match or discrepancy description
Confirmer: identity and approval evidence
~~~

To share a redacted report masking sensitive data, create a derived copy, assign a separate evidence ID or artifact ID, and record the transformation and new hash. Never edit the preserved raw original directly.

## 11. Hands-on lab: exporting OCI Audit with PowerShell

This section is a hands-on guide for learners, not an execution report from a live tenancy. Use a lab compartment and a time range containing valid test activity.

### 11.1. Preparing permissions and scope

An Audit read policy might be:

~~~text
Allow group IncidentAuditReaders to read audit-events in compartment SecurityLab
~~~

Replace group and compartment names with actual values. Audit read permission does not automatically grant access to view all log sources or create backups. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Prepare an OCI CLI profile dedicated to collection, such as `IR_READONLY`, and a directory on a trusted acquisition host. Strings in `<...>` below are placeholders to replace.

### 11.2. Exporting a time window

~~~powershell
$ErrorActionPreference = 'Stop'

$incidentId = 'IR-LAB-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$caseDir = Join-Path 'C:/IR-Lab' $incidentId
if (Test-Path -LiteralPath $caseDir) {
    throw 'Directory already exists; choose a new collection case.'
}
New-Item -ItemType Directory -Path $caseDir -Force | Out-Null

$readProfile = 'IR_READONLY'
$sourceRegion = '<SOURCE_REGION>'
$compartmentOcid = '<SOURCE_COMPARTMENT_OCID>'
$collectorPrincipalOcid = '<TRUSTED_COLLECTOR_PRINCIPAL_OCID>'

# Illustrative time range; replace with the window to collect.
$startUtc = '2026-11-21T02:00:00Z'
$endUtc = '2026-11-21T03:00:00Z'

$cliVersionLines = & oci --version
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read OCI CLI version.'
}
$cliVersion = $cliVersionLines -join ' '

$auditFile = Join-Path $caseDir 'E-001-audit-export.json'
$collectionStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')

$auditArgs = @(
    'audit', 'event', 'list',
    '--profile', $readProfile,
    '--compartment-id', $compartmentOcid,
    '--region', $sourceRegion,
    '--start-time', $startUtc,
    '--end-time', $endUtc,
    '--all',
    '--output', 'json'
)

$auditLines = & oci @auditArgs
$auditExitCode = $LASTEXITCODE
$collectionCompletedUtc = [DateTimeOffset]::UtcNow.ToString('o')

if ($auditExitCode -ne 0) {
    throw 'Audit export failed; do not mark collection as successful.'
}

$auditText = ($auditLines -join [Environment]::NewLine) + [Environment]::NewLine
$null = ConvertFrom-Json -InputObject $auditText -ErrorAction Stop

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($auditFile, $auditText, $utf8NoBom)

$artifactSha256 = (Get-FileHash -LiteralPath $auditFile -Algorithm SHA256).Hash
Write-Output ('Evidence file: ' + $auditFile)
Write-Output ('SHA256: ' + $artifactSha256)
~~~

`--all` fetches all result pages for that query; it does not automatically query all compartments or regions. The CLI requires timestamps with minute precision, with seconds and fractional seconds set to 0. [Oracle CLI: audit event list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

The resulting file is a **CLI-serialized JSON export**, not raw bytes of the original HTTP response. Do not use `--query` to strip fields before saving an export intended for preservation.

Audit has processing latency. Distinguish the query window per service mechanics from event timestamps; capture adjacent windows and run supplemental collections if needed. Record each export as a separate artifact. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

### 11.3. Generating a manifest for the exported file

Continue in the same PowerShell session:

~~~powershell
$manifest = [ordered]@{
    IncidentId = $incidentId
    EvidenceId = 'E-001'
    ArtifactType = 'OCI_AUDIT_CLI_EXPORT'
    SourceRegion = $sourceRegion
    SourceCompartmentOcid = $compartmentOcid
    QueryStartUtc = $startUtc
    QueryEndUtc = $endUtc
    CollectionStartedUtc = $collectionStartedUtc
    CollectionCompletedUtc = $collectionCompletedUtc
    CollectorPrincipalOcid = $collectorPrincipalOcid
    CliProfile = $readProfile
    CliVersion = $cliVersion
    CommandArguments = $auditArgs
    FileName = [System.IO.Path]::GetFileName($auditFile)
    LengthBytes = (Get-Item -LiteralPath $auditFile).Length
    HashAlgorithm = 'SHA256'
    Sha256 = $artifactSha256
    Limitations = @(
        'Single compartment and region'
        'Service processing delay must be considered'
        'CLI serialized JSON, not raw HTTP bytes'
    )
}

$manifestFile = Join-Path $caseDir 'E-001-manifest.json'
$manifestText = $manifest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($manifestFile, $manifestText, $utf8NoBom)

$manifestSha256 = (Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash
Write-Output ('Manifest SHA256: ' + $manifestSha256)
~~~

This template contains no private keys or tokens. Record the manifest hash and intake decision in a protected evidence management log.

If the query returns an empty event list, still save the artifact along with scope and success status. Then verify compartment, region, time, permissions, and latency before interpreting the result.

## 12. Uploading evidence to Object Storage and re-verifying

Use the private evidence bucket prepared by the administrator. The evidence-writing profile may differ from the source-reading profile.

### 12.1. Uploading with unique names per case

~~~powershell
$writeProfile = 'IR_EVIDENCE_WRITER'
$storageRegion = '<EVIDENCE_BUCKET_REGION>'
$namespaceName = '<OBJECT_STORAGE_NAMESPACE>'
$bucketName = '<PRIVATE_EVIDENCE_BUCKET>'

foreach ($sourceFile in @($auditFile, $manifestFile)) {
    $objectName = $incidentId + '/' + [System.IO.Path]::GetFileName($sourceFile)

    & oci os object put --profile $writeProfile --region $storageRegion --namespace-name $namespaceName --bucket-name $bucketName --name $objectName --file $sourceFile --no-overwrite

    if ($LASTEXITCODE -ne 0) {
        throw ('Upload failed: ' + $sourceFile)
    }
}
~~~

`--no-overwrite` prevents overwriting an existing object. Record upload result, object name, and response metadata in the intake log; still re-verify contents after transfer. [Oracle CLI: os object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

Unique object names, restricted write permissions, and retention serve different control layers. Do not treat a single CLI flag as a replacement for the entire retention design.

### 12.2. Downloading a separate verification copy

The evidence-reading profile needs bucket/object read permissions per design:

~~~powershell
$verifyProfile = 'IR_EVIDENCE_READER'
$verifyDir = Join-Path $caseDir 'verification'
New-Item -ItemType Directory -Path $verifyDir -ErrorAction Stop | Out-Null

foreach ($sourceFile in @($auditFile, $manifestFile)) {
    $fileName = [System.IO.Path]::GetFileName($sourceFile)
    $objectName = $incidentId + '/' + $fileName
    $downloadFile = Join-Path $verifyDir $fileName
    $expectedHash = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash

    & oci os object get --profile $verifyProfile --region $storageRegion --namespace-name $namespaceName --bucket-name $bucketName --name $objectName --file $downloadFile

    if ($LASTEXITCODE -ne 0) {
        throw ('Verification download failed: ' + $objectName)
    }

    $actualHash = (Get-FileHash -LiteralPath $downloadFile -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw ('Hash mismatch: ' + $objectName)
    }

    Write-Output ('HASH_MATCH: ' + $objectName)
}
~~~

The `object get` command downloads object contents to a file. If collecting a source object with versioning, record the version ID and download that exact version to avoid grabbing a newer one. [Oracle CLI: os object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html).

Record the verification hash alongside the trusted reference source identifier. If hashes mismatch, preserve both copies and investigate the discrepancy—never edit the manifest to make them match.

## 13. Building timelines and evaluating hypotheses

### 13.1. Joining data by identifiers

Audit includes groups of fields for time, identity, request, response, and state change. Fields such as `data.identity.principalId`, `data.request.id`, `data.resourceId`, and `data.eventGroupingId` support activity correlation. [Oracle: Contents of an Audit Log Event](https://docs.oracle.com/en-us/iaas/Content/Audit/Reference/logeventreference.htm).

Field names in exports may depend on how tools render schemas. Keep collected files intact and create working copies for normalization.

A recommended timeline table:

| UTC timestamp | Source/evidence ID | Fact | Confidence level | Point to verify |
| --- | --- | --- | --- | --- |
| T0 | Auth logs | A session was established | Per source quality | Was this an approved activity? |
| T1 | Audit/E-001 | Config change API recorded | Correlated request and response | Are before/after configs complete? |
| T2 | App logs | Unusual activity appeared | Needs independent check | Is the host compromised? |
| T3 | Response log | Team executed containment | Confirmed by operator | Do other access paths remain? |
| T4 | Independent check | Blocked flow no longer works | Within test scope | Were other VNICs and regions checked? |

This is a documentation template, not the sequence of a real incident.

Distinguish API start time, completion time, and log collection time. One request can produce multiple events; do not count each line as an independent action without checking correlation identifiers.

### 13.2. Analyzing with incomplete evidence

When data is insufficient, describe the exact limitations:

~~~text
Collected:
    Audit in two compartments, within the recorded windows.

Missing:
    Object read logs prior to when logging was enabled.

Can conclude:
    A bucket configuration change occurred within the collected data scope.

Cannot yet conclude:
    Whether any objects were downloaded during the unlogged gap.
~~~

Similarly, traffic to a notable IP address is insufficient to prove sensitive data was exfiltrated. Cross-check applications, volume, access permissions, and other data sources.

Every conclusion should reference an evidence ID, describe the reasoning, and state confidence levels. Disproven hypotheses should also be kept in notes to avoid repeating investigations.

## 14. Eradicating root cause and recovering services

### 14.1. Fixing the root cause at the source

Once scope is determined, plan concrete changes:

- Revoke or rotate affected credentials and update dependent systems.
- Remove unauthorized permissions, accounts, or configurations.
- Patch entry points and fix configurations in IaC, pipelines, or source images.
- Rebuild workloads from trusted sources when host integrity cannot be proven.
- Reconcile databases, objects, and application data to identify what needs recovery.

Keep resources under investigation separate from the recovery environment. Never re-attach a disk suspected of tampering to production just because the application can boot.

The most recent backup is not guaranteed to be clean: identify the suspected intrusion time and inspect recovery artifacts. In records, explain why a recovery point was chosen and how much data may require supplemental restoration.

### 14.2. Return-to-service criteria

A recommended set of criteria:

| Verification group | Criterion |
| --- | --- |
| Identity | Affected credentials, permissions, and sessions handled |
| Configuration | Compared against trusted baseline; deployment source fixed |
| Data | Integrity verified per business requirements |
| Application | Read/write flows and critical dependencies operational |
| Observability | Logs and alerting paths verified |
| Availability | Service levels and traffic cutover plan met |
| Investigation | Evidence to preserve is not overwritten by recovery |
| Sign-off | Service owner and incident response lead confirm |

Measure RTO by actual time to restore service to required levels; determine RPO by recoverable data. Do not treat a `RUNNING` instance state as representing full application readiness.

After shifting traffic, keep monitoring the indicators used to detect the incident and the remediated access paths. Document the monitoring duration and responsible owner.

## 15. Automation, cost, and lab wrap-up

### 15.1. Automating by impact

Verified steps such as opening tickets, tagging identifiers, reading configurations, exporting logs, and verifying hashes can be automated.

For actions that modify resources, set explicit boundaries on principals, compartments, resource types, and impact. If automation or responders can stop/delete resources, log execution as part of the timeline and assess impact on evidence.

An automation workflow should have:

- Clear inputs and execution preconditions.
- Idempotency to avoid duplicate runs for the same artifact or resource.
- Error logs, step statuses, and controlled resume mechanisms.
- Escalation to a human owner when permissions are lacking or scope is unclear.

Never mark collection successful just because a file was created; verify source commands, contents, manifest, and preservation outcomes.

### 15.2. Managing cost while retaining necessary data

Separately track log volume, volume backups, analysis volumes, evidence buckets, investigation hosts, and recovery environments.

When selecting storage tiers, consider retrieval time. Objects in Archive must be restored before reading; therefore, do not immediately move data under active investigation to this tier just for lower storage cost. [Oracle: Object Storage Storage Tiers](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/understandingstoragetiers.htm).

Reducing cost by deleting artifacts must follow approved retention decisions. Monitor quotas and remaining capacity so a critical collection does not fail mid-run.

### 15.3. Lab completion milestones

In the lab compartment, learners should have:

1. One valid administrative action with recorded timestamp and actor.
2. An Audit export matching the compartment, region, and query window.
3. A manifest with source, tool, UTC timestamps, and SHA-256 hash.
4. Two objects corresponding to the export and manifest in a private bucket.
5. A verification download whose hash matches the reference source.
6. A handover table and notes on latency and missing data.
7. A decision to retain or clean up lab resources.

To test understanding of integrity, create a separate copy purely for testing, modify that copy's contents, and re-compare hashes. Label it as a test artifact—do not alter the preserved copy.

Clean up analysis volumes and hosts no longer needed, revoke temporary permissions, and verify monitoring sources remain active. Do not delete artifacts subject to an active evidence hold decision.

## 16. Incident closure record and continuous improvement

The closure record should state the issue, verified scope, impact, timeline, root cause, remediation actions, and questions lacking sufficient data to answer.

Store the catalog of evidence IDs along with storage locations, custodians, retention durations, and conditions permitting future disposal. Closing an incident does not automatically end evidence retention requirements.

Internal metrics can include:

| Metric | How it is used |
| --- | --- |
| Time from detection to intake | Evaluate on-call coverage and alerting paths |
| Time to effective containment | Evaluate runbooks and response permissions |
| Time to first verified artifact | Evaluate collection readiness |
| Ratio of log sources with in-scope data | Identify visibility gaps |
| Handover omissions or hash mismatches | Improve evidence management |
| Recovery time and recovered data | Compare against RTO/RPO targets |
| Completion rate of improvement items | Track post-incident follow-ups |

Every improvement item needs an owner, deadline, and verification method. Examples: enabling read logs for critical buckets, fixing missing response permissions, drilling secondary VNIC isolation, or test-restoring volumes in an investigation environment.

A solid record allows someone who was not involved in the incident to read back and understand why the team acted, which evidence supports the conclusions, and which limitations remain.
