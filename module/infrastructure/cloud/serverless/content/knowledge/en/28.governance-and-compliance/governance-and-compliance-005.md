# Storing Audit Logs and Configuration Change Evidence

In a serverless system, configurations can change in many places: IaC code, CI/CD pipelines, cloud consoles, administrative APIs, runtime settings, IAM policies, API gateways, event source mappings, queues, workflows, and secret managers. A small change such as broadening a function's permissions, modifying an endpoint, raising concurrency, or altering retention can affect security, cost, and resilience. During an incident or audit, the team must prove who changed what, when, through which process, whether the change was approved, and what configuration the live system actually received.

Audit logs record security- and governance-relevant events. Configuration change evidence gathers the related artifacts to reconstruct a change's full lifecycle: request, commit, plan, policy checks, approval, deployment, post-deploy verification, and actual live state. These two sources complement each other. Audit logs show what action occurred; change evidence explains how that action was proposed, reviewed, and deployed through a governed process.

In the **CLOUD_SERVERLESS** module, learners build and deploy Java functions triggered by HTTP, messages, or events while handling access permissions, state, retries, idempotency, cold starts, scaling, and cost. This lesson focuses on collecting, protecting, retaining, and querying audit logs alongside configuration change evidence across the entire serverless application lifecycle.

## 1. How Do Audit Logs Differ from Application Logs?

Application logs describe application runtime behavior: a request was processed, a dependency timed out, a message was retried, or a workflow step completed. Audit logs record actions requiring accountability, authorization, or significant state transitions.

| Log Type | Purpose | Example |
|---|---|---|
| Application log | Diagnosing runtime behavior | Order-processing function took 250 ms |
| Security log | Detecting and investigating security events | Failed sign-in, rejected token |
| Audit log | Recording who performed a significant action | Principal modified an IAM policy |
| Platform/control-plane log | Recording cloud resource administration actions | Creating a function, editing an API route, deleting a queue |
| Data-plane audit | Recording data access or modification | Reading an object, editing a record, or querying controlled data |
| Change evidence | Proving which workflow a change passed through | PR, IaC plan, approval, and deployment record |

An application log line like `"configuration updated"` is insufficient as audit evidence without the actor, resource, timestamp, change source, and outcome. Conversely, a cloud provider's audit log may show that an administrative API was called without explaining why the change was approved or which commit produced it.

Never use application logs in place of a provider audit trail. Applications can crash, be modified, or be compromised; platform-recorded control-plane audits provide a more independent source of evidence for administrative actions.

## 2. Two Planes to Observe: Control Plane and Data Plane

The **control plane** is where resources and configurations are managed: creating functions, changing runtimes, updating IAM, editing gateways, changing queue mappings, or configuring workflows.

The **data plane** is where data and requests are processed: calling APIs, reading/writing objects, receiving messages, querying databases, or executing business operations.

A system that enables auditing only on the control plane can tell who changed a policy, but not which principal accessed the data. Auditing only the data plane may miss who altered permissions to allow that access. Scope both layers according to risk and compliance requirements.

~~~mermaid
flowchart TD
    A[Human / CI identity] --> B[Cloud control plane]
    B --> C[Function, API, IAM, queue, workflow config]
    D[Client / event producer] --> E[Serverless data plane]
    E --> F[Function and data services]
    B --> G[Control-plane audit]
    E --> H[Data-plane audit]
    C --> I[Change evidence]
    F --> J[Application audit events]
    G --> K[Central audit archive]
    H --> K
    J --> K
    I --> L[Evidence repository]
    K --> M[Search, alert and investigation]
    L --> M
~~~

Not every service provides the same level of data-plane auditing. You may need to separately enable data access logging, database audit extensions, object-level events, or application-level audit events. Verify coverage per resource and service tier.

## 3. Objectives of a Trustworthy Audit Trail

An audit trail should support the following objectives:

- **Accountability:** identify the principal or service identity that performed the action.
- **Traceability:** link actions to requests, tickets, commits, deployments, or workflows.
- **Integrity:** detect or prevent unauthorized modification or deletion of logs.
- **Completeness:** capture all significant events within the defined scope.
- **Availability:** retrieve evidence reliably when needed for investigations.
- **Confidentiality:** restrict who can read audit logs and sensitive fields.
- **Time accuracy:** timestamps can be correlated across multiple systems.
- **Retention:** retain logs long enough per policy and applicable obligations.
- **Non-repudiation support:** use independent logging sources, signatures, or appropriate protections to strengthen provenance assurance.

No single logging setting guarantees every objective. Audit quality depends on coverage, identity fidelity, write/delete permissions, clock synchronization, archive protection, and operational procedures.

## 4. Required Fields in an Audit Event

An audit event generally needs to answer: who acted, what they did, on which resource, when, from where, why, and with what outcome.

| Field | Meaning | Example |
|---|---|---|
| `event.id` | Unique audit event ID | `aud-7f12` |
| `event.time` | Timestamp when the event occurred in UTC | `2026-11-17T10:15:30Z` |
| `event.type` | Event category | `config.change` |
| `action` | Specific operation | `UpdateFunctionConfiguration` |
| `actor.id` | Principal/user/service identity | `ci-deployer-prod` |
| `actor.type` | Actor category | `human`, `service`, `workload` |
| `actor.session` | Session / assumed role reference | `session-82` |
| `source.ip` | Source IP if available and permitted to store | `203.0.113.10` |
| `source.user_agent` | Client/tool that invoked the API | `terraform/1.x` |
| `resource.id` | Resource ID/ARN/URI | `function/orders-api` |
| `resource.type` | Resource type | `serverless.function` |
| `environment` | Environment | `production` |
| `region` | Region | `ap-southeast-1` |
| `change.id` | Change request ID | `CHG-2048` |
| `request.id` | Provider-assigned request ID | `req-91a` |
| `correlation.id` | Change workflow correlation ID | `corr-31` |
| `outcome` | Outcome | `success`, `denied`, `failure` |
| `reason` | Reason/ticket/reference | `approved release` |
| `before/after` | Filtered configuration values or digests | `timeout 20 → 30` |
| `source` | Originating source | `cloud.audit`, `pipeline`, `app` |

Not every provider returns every field. Document which fields come from the provider, which are enriched by pipelines, and which are unavailable. Never infer an actor solely from an IP address or user agent.

### Example Audit Event JSON

~~~json
{
  "schema_version": 1,
  "event": {
    "id": "aud-7f12",
    "time": "2026-11-17T10:15:30.123Z",
    "type": "configuration.change",
    "action": "UpdateFunctionConfiguration",
    "outcome": "success"
  },
  "actor": {
    "id": "ci-deployer-prod",
    "type": "workload",
    "session": "deploy-run-581"
  },
  "resource": {
    "id": "function/orders-api",
    "type": "serverless.function",
    "environment": "production",
    "region": "ap-southeast-1"
  },
  "change": {
    "id": "CHG-2048",
    "commit": "9c31e4a",
    "before_digest": "sha256:abc...",
    "after_digest": "sha256:def..."
  },
  "source": {
    "system": "cloud-control-plane",
    "request_id": "req-91a"
  },
  "correlation_id": "corr-31"
}
~~~

This example illustrates a normalized schema, not a raw format from any specific cloud provider. When ingesting, preserve the original record or store a source event reference so investigative details are not lost.

## 5. Identity: Record the True Actor, Not Just a Human Name

An actor can be:

- A user signed in via SSO.
- A role assumed by a human.
- A CI/CD service account or workload identity.
- A cloud service principal acting on behalf of an application.
- Automation or a controller.
- A break-glass identity used during an incident.

For assumed roles or federated identities, preserve the chain linking the session back to the originating principal where the provider supplies it. An event recording only a role name may not distinguish which human or pipeline assumed that role.

Best practices:

- Use SSO/federation and dedicated identities per pipeline.
- Never share access keys or service accounts across multiple teams.
- Retain session names/run IDs linkable to CI jobs.
- Distinguish whether an actor is a human, workload, or provider service.
- Record the authentication source and session reference when available.
- Enforce least privilege; auditing does not replace authorization.
- Monitor credential creation, trust policy edits, and assume-role grants.

Never put access tokens, refresh tokens, private keys, or secrets into audit events. Actor IDs must be specific enough for investigation without exposing authentication material.

## 6. Audit Sources from Cloud Providers

Cloud providers offer their own audit/control-plane services. Naming, scope, and default enablement vary; verify exact event types, regions, resources, and data access coverage.

| Platform | Common Audit Sources | Key Points |
|---|---|---|
| AWS | CloudTrail management events and data events | Choose trails, Regions, accounts, resource-level data events, and storage destination |
| Azure | Azure Activity Log and resource-specific diagnostic logs | Activity Log focuses on control plane; data-plane logs typically require separate configuration |
| Google Cloud | Cloud Audit Logs: Admin Activity, Data Access, System Event, Policy Denied | Check Data Access logging, supported services, and project/folder/org configuration |

### AWS CloudTrail

CloudTrail records AWS account API activity. Management events cover administrative operations such as creating, modifying, or deleting resources. Data events record certain data access operations, such as object-level access or function invocations depending on service and configuration.

Do not assume every data event is logged for free or enabled for all resources. Configure appropriate event selectors, evaluate cost, and verify events actually arrive in the trail. With multiple accounts, consider an organization trail or central logging account aligned with your governance architecture.

### Azure Activity Log

Azure Activity Log records subscription control-plane operations, such as creating or updating resources and changing administrative settings. Auditing the data plane typically requires diagnostic settings or service-specific logs for storage, databases, or APIs.

Activity Logs can be routed to a Log Analytics workspace, storage account, or event hub depending on retention and analysis needs. Retention scope and exports must be explicitly configured; never assume a single sink satisfies every requirement.

### Google Cloud Audit Logs

Google Cloud categorizes audit logs into Admin Activity, Data Access, System Event, and Policy Denied. Data Access logs must be enabled and verified per service and policy; do not assume all data reads are captured in every project by default. Sinks can be configured at the project, folder, or organization level to centralize logs into an appropriate destination.

Category names and support levels vary by service. Inventory critical resources and verify real events through testing rather than relying solely on configuration state.

## 7. Building an Audit Coverage Inventory for Serverless

To prevent blind spots, list the resources and actions requiring auditing.

| Component | Changes to Track | Accesses to Track |
|---|---|---|
| Java function | Runtime, handler, memory, timeout, environment, concurrency, code version | Invocations or data access where required |
| IAM role/policy | Policy attach/detach, trust policies, permission boundaries | AssumeRole calls, denied actions |
| API gateway | Routes, authorizers, stages, throttling, custom domains | Request/access logs per policy |
| Queue/topic | Policies, encryption, retention, DLQ, redrive config | Send/receive/delete or publish/subscribe |
| Event source mapping | Batch size, retries, filters, enabled state, concurrency | Poll/consume where supported by the service |
| Workflow | Definition, role, timeout, retries, state machine version | Start/stop/approve/execute and business audits |
| Storage | Bucket/container policies, encryption, lifecycle, public access | Read/write/delete/list per data classification |
| Database | Network, parameters, backups, roles, audit config | Queries/writes or privileged access |
| KMS/secret manager | Key policies, rotation, grants, secret versions | Decrypt, secret reads, rotations |
| Network | VPC, subnets, routes, security groups, endpoints | Flow logs or network security events |
| Logging platform | Trail config, sinks, retention, access policies | Searches, exports, deletions, retention changes |

You do not need to enable every data access log on every resource. Select coverage based on sensitivity, risk, and legal requirements; data-plane logging can generate high volume and cost.

### Auditing the Audit Configuration Itself

A crucial control is recording changes to the audit pipeline itself:

- Disabling or deleting a trail/log sink.
- Modifying event selectors to exclude data events.
- Lowering retention or disabling archiving.
- Changing bucket/container policies.
- Altering Object Lock/retention settings or attempting to delete locked objects.
- Changing KMS keys/policies or revoking decrypt permissions.
- Granting read/delete permissions on the audit archive.
- Modifying alerts or export destinations.

If an attacker can turn off auditing undetected, the remaining logs will not prove the existence of the gap.

## 8. Recording Configuration Changes in Java Serverless

Cloud audits capture control-plane actions. Applications may still need business audit events for domain-level changes executed through functions, such as:

- A user updating account details.
- Staff approving a refund.
- A workflow changing order state.
- An administrator altering tenant settings inside the application.
- A service changing business policies or feature flags.

Business audit events require an authenticated actor, action, target, outcome, and reference to the request/change. Do not treat an arbitrary log statement as an audit event; audit events need a stable schema and a durable storage path.

### Example Java Audit Record

~~~java
public record AuditEvent(
        String eventId,
        Instant occurredAt,
        String actorId,
        String actorType,
        String action,
        String resourceType,
        String resourceId,
        String outcome,
        String requestId,
        String correlationId,
        String changeReference) {
}
~~~

A service can construct events from the authenticated identity context:

~~~java
public void updateTenantLimit(
        AuthenticatedPrincipal principal,
        String tenantId,
        int newLimit,
        String requestId) {

    transaction(() -> {
        tenantRepository.updateLimit(tenantId, newLimit);

        auditOutboxRepository.insert(new AuditEvent(
            UUID.randomUUID().toString(),
            Instant.now(),
            principal.subject(),
            "human",
            "tenant.limit.updated",
            "tenant",
            tenantId,
            "success",
            requestId,
            currentCorrelationId(),
            currentChangeReference()
        ));
    });
}
~~~

This is pseudocode; the tenant update and outbox insert must share the same database transaction so a committed business state never lacks an audit event. A dispatcher reads the outbox and delivers events to the archive, retrying safely and deduplicating by `eventId`. Identity must come from a verified token/session rather than trusting `actorId` directly from the request body. When before/after values are needed, record only non-sensitive values or normalized digests per policy.

### Preventing Lost Audit Events on Function Crashes

If a business update succeeds and the function crashes before emitting the audit event, the system loses evidence. If the audit is written first and the business transaction rolls back, logs falsely report a change that never happened.

With transactional databases, write the business update and the audit/outbox record inside the same transaction. A dispatcher delivers outbox records to the audit archive afterward. The dispatcher needs retries and idempotency; the archive must retain event IDs to deduplicate on ingestion.

If an audit event must sit outside the business transaction, define clear delivery guarantees, retries, dead-letter handling, and reconciliation. Never fire off an HTTP logging call and assume the event was durably persisted.

## 9. Configuration Change Evidence Is a Package, Not a Single Log Line

Each production change should have an evidence package tied to its change ID. This package may include:

- Change request or ticket and business rationale.
- Requester, owner, and reviewers.
- Pull request, commit SHA, and branch/tag.
- Modified IaC or application configuration files.
- Saved plan or diff prior to apply.
- Policy and security scan results.
- Approval records and approval timestamps.
- CI/CD run ID, runner identity, and target environment.
- Artifact digest, image digest, or package checksum.
- Deployment record and provider request/operation ID.
- Secret-redacted before/after configuration snapshots.
- Post-deploy verification, smoke test, and health results.
- Post-deployment drift scan or reconciliation.
- Rollback record if the deployment was reverted.

The provider's audit log proves an administrative API was called. The evidence package connects that event to the commit, plan, and approval so reviewers can explain why the change happened.

## 10. Change Management Workflow for IaC

An infrastructure change pipeline should have traceable stages:

~~~mermaid
flowchart TD
    A[Change request] --> B[Pull request / commit]
    B --> C[Format, validate and scan]
    C --> D[Generate IaC plan]
    D --> E[Policy and security checks]
    E --> F[Human approval]
    F --> G[Apply reviewed plan]
    G --> H[Provider control-plane audit]
    G --> I[Deployment evidence]
    H --> J[Central audit archive]
    I --> K[Evidence repository]
    K --> L[Post-deploy verification]
    L --> M[Drift / reconciliation]
~~~

Each stage should emit a record containing the change ID, commit SHA, pipeline run ID, and affected resources/environment. Approvals must bind to the exact plan or commit being applied. If a plan is regenerated after approval, its contents may differ and require re-review per policy.

### Plan Evidence

With Terraform/OpenTofu, a saved plan helps ensure you apply exactly what was reviewed. However, plan files can contain sensitive data. Never publish plans to public artifacts or repositories. Store them in an artifact store with restricted access, short retention, and download auditing.

Also record the plan digest, commit SHA, backend/workspace, provider versions, timestamp, and reviewer reference. A digest proves the compared file was not altered after creation; it does not prove the plan itself is safe or correct.

## 11. Capturing Before/After Configuration

Configuration snapshots enable comparing pre- and post-change states. Normalize payloads before computing digests to avoid meaningless diffs from key ordering or formatting.

An evidence record might store:

~~~json
{
  "change_id": "CHG-2048",
  "resource": "function/orders-api",
  "config_version_before": "cfg-104",
  "config_version_after": "cfg-105",
  "before_digest": "sha256:abc123...",
  "after_digest": "sha256:def456...",
  "changed_fields": [
    "timeout",
    "memory_size"
  ],
  "secret_values_included": false,
  "captured_at": "2026-11-17T10:15:30Z"
}
~~~

Never store secret values in snapshots. For environment variables holding credentials, record only the variable name, whether it changed, and the secret version/reference if policy permits. Never simply hash a low-entropy secret and publish its digest; digests can expose values to dictionary attacks.

### Provider-Normalized Configuration

Providers may return configurations shaped differently from IaC due to defaults, computed fields, or normalization. Snapshots should distinguish desired config, submitted request, and observed post-deploy config. Merging these three can mislead reviewers into thinking a provider default was a manual edit.

## 12. Proving Artifact and Deployment Provenance

For Java functions, link the deployed artifact back to source code and the build pipeline:

- Repository and commit SHA.
- Build job/run ID.
- Java version, build tool, and dependency lock/versions.
- Artifact filename and SHA-256 digest.
- Container image digest if using an image.
- SBOM and vulnerability scan results if required by process.
- Signing/attestation metadata if adopted by the organization.
- Function version, alias, or deployment revision.
- Provider deployment/request ID.

Tags like `latest` do not prove which artifact is running. Use immutable digests or version IDs. When a function alias shifts to a new version, record both the alias update event and the version digest.

An artifact signature or provenance attestation proves an artifact was produced by the declared pipeline/identity. It does not by itself prove source code is safe or approvals are valid; combine it with build isolation, reviews, and policies.

## 13. Approvals and Separation of Duties

For sensitive changes, the requester should not self-approve and self-deploy when policy mandates separation of duties.

A simple matrix:

| Role | Typical Permissions | Evidence |
|---|---|---|
| Requester | Create change request | Ticket/PR author |
| Developer | Modify code/IaC | Commit, PR diff |
| Reviewer | Review contents and risk | Review decision |
| Approver | Approve production change | Approval event |
| CI deployer | Execute plan/artifact | Workload identity, run ID |
| Auditor | Read evidence | Access audit |
| Security/admin | Administer policies and audit system | Privileged action audit |

Do not share a single credential between developers and CI deployers. Production pipelines should use dedicated workload identities, short-lived credentials, and narrowly scoped permissions.

Approvals must bind to the exact resource, environment, artifact/plan, and expiration window. A blanket approval across all commits or an unattributed approve button is insufficient evidence.

## 14. Centralized Audit Log Storage and Permission Separation

Audit logs should not reside solely in the same account/project where workloads are managed. If a production account is compromised, an attacker could wipe both resources and evidence.

A common pattern:

- Each account/project/subscription emits audit events.
- Events are shipped to a central logging account/project or isolated storage.
- Producers have write-only access to the designated destination.
- Investigation teams have read/search access.
- Permissions to delete, alter retention, or manage keys belong to a separate role.
- Backups/archives maintain copies in another failure domain.
- Alerts detect policy changes or delivery stoppages.

~~~mermaid
flowchart LR
    A[Production accounts] --> B[Audit trail / diagnostic export]
    C[CI/CD systems] --> D[Change evidence]
    E[Identity provider] --> F[Sign-in audit]
    B --> G[Central logging account]
    D --> H[Evidence repository]
    F --> G
    G --> I[Immutable archive]
    G --> J[Search and SIEM]
    H --> K[Change review]
    I --> L[Investigation / audit]
    J --> L
    K --> L
~~~

The central archive must separate administrative privileges from workload privileges. One role can write logs without reading or deleting them; investigators can read without changing retention; archive administrators require separate approvals and auditing.

## 15. Protecting Integrity: Append-Only, WORM, and Hashing

Audit logs are trustworthy only when privileged administrators cannot silently edit or delete evidence.

Common mechanisms:

- **Append-only access:** producers can only append records, never overwrite or delete.
- **WORM/immutable retention:** objects or logs are locked against modification/deletion for the configured duration, per service capabilities.
- **Versioning:** retains object versions for recovery and investigation.
- **Hash/digest:** creates fingerprints to detect content tampering.
- **Digital signatures:** signs events or manifests with controlled keys.
- **Hash chains:** each record/segment references the previous segment's digest to detect reordering or content tampering.
- **Independent copies:** replicates to another account or security boundary.

A standalone hash does not prevent an attacker from altering both the file and the digest. If using hash chains, anchors or manifests must be signed/stored in an independent trust boundary. WORM also requires proper policies, retention, and key management; if an admin can delete the entire archive or key, evidence can still be lost.

### WORM and Legal Holds

WORM/immutable storage typically supports time-based retention and legal holds. Retention locks may be irreversible once enabled. Choose durations per approved policy and legal obligations; avoid setting infinite retention by default.

Legal holds prevent deletion of evidence tied to investigations or disputes. Establish procedures defining who can place/release holds, justification, scope, and auditing of the hold operation itself.

## 16. Encryption and Key Management

Audit logs typically contain actors, resource IDs, IPs, request metadata, and change details. Even without secrets, this remains sensitive data.

Protect it with:

- TLS in transit between producers, collectors, and archives.
- Encryption at rest for log stores and evidence repositories.
- KMS/customer-managed keys where independent key control is required.
- Key policies separated from log-writing permissions.
- Key rotation and auditing of key operations.
- Backing up key metadata and testing decryption during DR.
- Limiting export/decrypt permissions to investigators per assignment.

If a key is disabled or deleted, the archive may become unreadable. DR plans must cover keys, policies, grants, and procedures to restore decryption access.

## 17. Retention, Legal Holds, and Privacy

Retention must balance investigative needs, compliance mandates, cost, and privacy. No single retention period fits every log type.

Suggested categorization:

| Category | Examples | Retention Policy to Define |
|---|---|---|
| Security audit | Privileged actions, denied access | Per security/compliance policy |
| Control-plane audit | Resource create/update/delete | Per governance and investigative needs |
| Data access audit | Reads/writes of sensitive data | Per classification and applicable obligations |
| Application audit | Critical business state changes | Per business lifecycle and dispute windows |
| Operational logs | Debug output, durations, dependency errors | Usually shorter than audit evidence |
| Change evidence | PRs, approvals, plan digests, deployments | Per change policy and audit window |

Do not invent a single universal statutory period. Legal/compliance owners must establish requirements by industry, jurisdiction, and data category.

### Data Minimization

Auditing is not an excuse to store entire request bodies or secrets. Retain only the data required to prove the action:

- Actor ID and role/session reference.
- Resource ID and action.
- Timestamp and outcome.
- Change/ticket/commit reference.
- Non-sensitive before/after fields or digests.
- Request/trace IDs needed for correlation.

IP addresses, user agents, and tenant identifiers may also constitute personal or sensitive data. Define purpose, access permissions, and retention for these fields.

### Deletion and Legal Holds

When retention expires, delete according to an approved lifecycle and record the outcome. If data is under a legal hold, deletion must pause within the hold's scope. Account for copies, indexes, exports, archives, and backups; deleting a dashboard does not delete underlying data from the system.

## 18. Time Synchronization and Event Ordering

Investigating changes across multiple systems requires reliable timestamps. Use UTC and maintain adequate precision. Synchronize clocks via the platform's time synchronization service or managed NTP.

Details to track:

- Event time: when the action occurred at the source.
- Ingest time: when the collector received the event.
- Archive time: when it was written to the archive.
- Provider request ID: helps locate the original event.
- Sequence/version: helps establish order when timestamps collide or clocks skew.

Do not sort all events solely by ingest timestamp, as events can arrive late or be retried. Preserve both event time and ingest time; use sequence numbers or request IDs where provided.

If clocks skew, a deployment may appear before an approval in logs even though it happened afterward. Monitor clock skew and record timezones explicitly.

## 19. Delivery Reliability and Detecting Audit Gaps

Audit events can fail to reach the archive due to network issues, quotas, collector failures, permissions, or misconfiguration. Monitor the audit pipeline itself:

- Trail/diagnostic exports remain enabled.
- Last successful delivery timestamp.
- Delivery errors and throttling.
- Destination buckets/containers/topics still exist.
- Storage quotas and encryption keys remain healthy.
- Collector backlogs and dead-letter queues.
- Unexpected drops in event volume to zero.
- Discrepancies between provider event counts and archive ingest counts where reconciliation metrics exist.

Not all audit sources guarantee instantaneous delivery. Define SLAs/latency expectations and handling for delayed events. During quiet periods, distinguish "no activity" from "audit pipeline stopped" using heartbeats or independent health signals where appropriate.

### Reconciliation

Periodically reconcile:

1. Control-plane event sources.
2. Central collectors/streams.
3. Archive objects/indexes.
4. Change/deployment records.
5. Resource inventories or drift scans.

The goal is to uncover missing events, duplicates, unmanaged resources, or changes lacking change references. Reconciliation does not replace raw audit sources, but it surfaces blind spots.

## 20. Alerting on High-Risk Configuration Changes

You do not need to alert on every minor update. Focus on actions that alter security boundaries, availability, or evidence integrity.

Example rules:

- IAM policies granting wildcard or administrative permissions.
- Trust policies allowing a new principal to assume a role.
- Public access enabled on a bucket, API, or database.
- Function runtime or artifact modified outside the pipeline.
- Function environment/config gaining new variables or modified outside a change window.
- Event source mappings disabled or having retry/batch settings altered.
- Queue policies, DLQs, or retention altered.
- Workflow definitions, roles, or timeouts modified.
- KMS keys disabled, key policies altered, or new grants issued.
- Audit trails, sinks, retention, Object Lock, or lifecycles modified.
- Users granted read/delete permissions on the audit archive.
- Production resources modified without a corresponding change ID, commit, or approval.

Alerts should include actor, action, resource, environment, Region, request ID, and a link to evidence. Never send secrets or raw payloads inside notifications.

### Correlating with Change Windows

When a control-plane event arrives, look up the matching change ID or deployment run. If no approval or commit reference exists, raise an alert for investigation. An out-of-pipeline action is not necessarily malicious; it could be break-glass or an emergency fix, but it still requires a ticket and post-incident review.

## 21. Detecting Drift and Out-of-Process Changes

Audit trails show that an operation occurred; drift detection compares desired configuration against live state.

Example:

- IaC specifies a 30-second function timeout.
- Someone edits it in the console to 60 seconds.
- Cloud audit logs record the API update and actor.
- Plan/refresh detects observed config differs from desired config.
- Change evidence lacks a PR or approval.
- Security alerts classify this as an out-of-process change.

Handling workflow:

1. Identify resource, Region, actor, and timestamp.
2. Retrieve the request ID and original event from the provider.
3. Cross-check PRs, commits, plans, approvals, and deployments.
4. Determine whether the change was an authorized hotfix, valid automation, or unauthorized action.
5. Choose whether to roll back or update IaC to codify an approved change.
6. Run plan/reconciliation after remediation.
7. Retain the incident/change record and related evidence.

Do not automatically revert every piece of drift the moment it is detected. A manual hotfix might be protecting live traffic; assess impact and obtain approval before reverting.

## 22. Break-Glass and Emergency Changes

Break-glass access is emergency privilege used when normal workflows cannot resolve an active incident. Because these privileges are elevated, auditing must be especially strict.

Recommended requirements:

- Dedicated identities, never shared accounts.
- MFA or strong authentication.
- Just-in-time access with short expiration.
- Mandatory justification and incident/change reference.
- Immediate alerts whenever break-glass is activated.
- Recording commands/API operations and modified resources.
- Independent post-incident review.
- Revoking access once the window expires.
- Reconciling manual changes back into IaC and baselines.

Do not block all emergency actions solely because no prior PR exists. Instead, enforce post-hoc review, record incident-based approvers, and backfill evidence once the system stabilizes.

## 23. Querying Audits and Assembling Evidence Packages

An investigation typically needs to answer:

- Who modified resource X in production during time window T?
- Which IAM policy was edited and by which actor?
- Which function version ran after the deployment?
- Does the change have a matching PR, approval, and plan?
- Who read or exported the audit archive?
- Was the audit trail disabled or retention reduced?
- Which secrets/keys were rotated and which workloads were affected?
- Did the change introduce drift or an incident?

An evidence package might look like:

~~~text
CHG-2048/
  request-and-risk.md
  pull-request-reference.json
  commit-and-build.json
  artifact-digest.json
  iac-plan-digest.json
  policy-results.json
  approval-record.json
  deployment-record.json
  provider-audit-events/
  before-after-config.json
  post-deploy-verification.json
  drift-reconciliation.json
  incident-or-rollback.json
  manifest.sha256
~~~

This is an illustrative structure. You do not need to store raw plan files inside the same package if they contain secrets. Store references, digests, and controlled pointers to a secure artifact store.

### Manifests and Digests

A manifest records artifact filenames, digests, sources, timestamps, and the change ID. Digests detect whether files were modified after collection. When high assurance is required, sign the manifest and store signatures in an independent trust boundary. Document the hash algorithm, signing key/identity, and verification procedure.

## 24. Protecting Access to the Audit Archive

The audit archive is a high-value target. Segregate permissions:

| Role | Recommended Permissions | Disallowed Permissions |
|---|---|---|
| Audit writer | Write/append events | Delete, edit, shorten retention |
| Collector | Read sources, write to archive | Manage archive keys and policies |
| Investigator | Scoped search/read/export | Edit/delete logs |
| Compliance reviewer | Read granted evidence | Modify sources or retention |
| Archive administrator | Manage retention/keys per approval | Unaudited deletion of evidence |
| Workload developer | Read application logs per policy | Read all control-plane/security audits |

Use separate roles and approvals for sensitive operations. Audit archive access itself: searches, exports, downloads, permission changes, retention edits, and deletion attempts.

## 25. Testing Audit Coverage and Integrity

Do not check merely that log files exist. Verify that the right events are generated with complete fields, delivered to the archive, and protected from unauthorized edits or deletions.

Test matrix:

| Scenario | Check | Expected Outcome |
|---|---|---|
| Function creation | Control-plane event | Includes actor, resource, action, and timestamp |
| IAM policy edit | Audit event and alert | Captures policy change, actor, and request ID |
| API route change | Event linked to change ID | Includes PR/approval/deployment references |
| Data-plane call | Data access event if enabled | Includes principal/resource/action per coverage |
| Out-of-IaC change | Audit + drift scan | Detected and actor identified |
| CI deployment | Workload identity and run ID | Links commit, artifact digest, and provider event |
| Break-glass | Privileged audit | Triggers alert, incident reference, and post-review |
| Trail disabled | Audit config event | Alerts outside the modified pipeline itself |
| Archive deletion | Retention/Object Lock test | Denied or triggers policy alert |
| Collector outage | Delivery health | Gap detected with replay/reconciliation |
| Clock skew | Timestamp comparison | Time discrepancy detected |
| Evidence restore | Archive restore | Readable and digests/signatures verify |

Test in safe environments with synthetic data. Never attempt to delete production archives or alter live audit trails without explicit scope and authorization.

## 26. Incident Response When the Audit Trail Is Disrupted

If audit logs stop writing or the archive stops receiving events:

1. Determine the start time and scope across accounts, projects, Regions, and services.
2. Preserve log sources, collector states, queue backlogs, and error diagnostics.
3. Inspect permissions, destinations, keys, quotas, networking, and trail configurations.
4. Restore delivery via an approved change.
5. Replay buffered/streamed events if the source supports it.
6. Reconcile control-plane events against provider history, deployment records, and resource inventories.
7. Identify any unrecoverable gap window.
8. Log an incident, impact assessment, and risk acceptance if needed.
9. Add alerts/health checks for earlier detection.
10. Verify changes that occurred during the audit gap using independent sources.

Never fabricate events to fill gaps. When reconstructing a timeline from secondary sources, clearly label sources, confidence levels, and inferred elements.

## 27. Common Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Storing only application logs | Misses cloud administrative actions | Enable control-plane auditing |
| Enabling only control-plane audits | Unknown who accessed sensitive data | Define required data-plane auditing |
| Sharing log write and delete roles | Attackers can erase evidence | Separate writer, reader, and archive admin roles |
| Storing audits in the workload account | Account compromise destroys evidence too | Central archive in a separate security boundary |
| Not auditing trail disablement | Audit gaps go unnoticed | Alert on audit configuration changes |
| Storing events without change IDs | Hard to trace back to tickets/approvals | Correlate with change requests and deployments |
| Not keeping artifact digests | Unknown which package actually deployed | Record immutable digests/versions |
| Unbound approvals | Different plan applied than reviewed | Bind approvals to commit/plan digests |
| Storing raw secrets in before/after | Evidence becomes a credential leak vector | Redact or store secret version references |
| Relying on a standalone hash for integrity | Attacker replaces both file and hash | Sign/anchor digests in another trust boundary |
| Arbitrary retention | Missing evidence or over-retained data | Set retention by classification and policy |
| Unsynchronized clocks | Out-of-order investigative timelines | Use UTC, time sync, and ingest timestamps |
| Not monitoring delivery | Silent event loss | Track health metrics, gap alerts, and reconciliation |
| Alerting on every tiny edit | Alert fatigue | Prioritize high-risk actions |
| Unaudited failovers | Cannot reconstruct emergency decisions | Log incident, actor, fencing, and route changes |

## 28. Process for Designing Auditing and Change Evidence

1. **Classify resources and data:** identify critical resources, data sensitivity, and auditable actions.
2. **Build a coverage matrix:** cover control plane, data plane, identity, application, and CI/CD.
3. **Standardize schema:** actor, action, resource, time, source, outcome, request/change IDs.
4. **Select independent sources:** cloud audit services, identity providers, application audits, and pipelines.
5. **Centralize logs:** dedicated central account/project, isolated archive, and restricted writer permissions.
6. **Protect integrity:** append-only/WORM, versioning, digests/signatures, and archive access auditing.
7. **Design change packages:** request, PR, plan, policies, approvals, artifacts, deployments, and verification.
8. **Protect data:** encryption, redaction, access controls, and retention.
9. **Configure alerts:** IAM changes, public exposure, trail disablement, retention edits, and manual production changes.
10. **Verify delivery:** heartbeats, collector health, gap detection, and reconciliation.
11. **Drill investigations:** query actors/resources/changes and verify digests.
12. **Review periodically:** coverage, retention, role access, costs, and provider updates.

## 29. Production Checklist

- **Coverage:** control-plane, data-plane, identity, application, and CI/CD audits are defined.
- **Identity:** human/workload/service actors are identified; sessions and sources are linked where available.
- **Schema:** conventions exist for event ID, UTC timestamp, action, resource, outcome, and request/change references.
- **Provider audit:** trails / Activity Logs / Audit Logs are enabled with the right scope and Regions.
- **Data access:** sensitive data access logging is enabled aligned with risk and cost.
- **Serverless resources:** functions, IAM, APIs, queues, event mappings, workflows, storage, KMS, and secrets are covered.
- **Change evidence:** PRs, commits, plans/diffs, policies, approvals, artifact digests, deployments, and post-checks are linked.
- **Approvals:** decisions bind to the exact commit/plan/artifact with separation of duties.
- **Integrity:** central archive enforces append-only/WORM or equivalent protection.
- **Access:** writers, investigators, reviewers, and archive admins have separated permissions.
- **Encryption:** transport, storage, and key policies are controlled; DR can decrypt.
- **Retention:** durations align with classification, legal holds, and deletion procedures.
- **Privacy:** no secrets or raw payloads stored; IPs and identifiers follow policy.
- **Time:** UTC, time synchronization, event time, and ingest time are distinguished.
- **Delivery:** health monitoring, gap alerts, backlog tracking, and reconciliation are active.
- **High-risk alerts:** IAM escalation, public exposure, trail disablement, retention/key edits, and manual production changes.
- **Testing:** audit coverage, tamper resistance, restores, break-glass, and evidence retrieval are tested.
- **Cost:** budgets account for data events, ingestion, retention, queries, and cross-Region archives.

## 30. Conclusion

Audit logs and configuration change evidence form two complementary layers proving how a system is governed. Audit logs reveal actor, action, resource, timestamp, source, and outcome. Change evidence connects those events to requests, commits, plans, policy checks, approvals, artifacts, and deployment results. When linked via change IDs, request IDs, and deployment run IDs, teams can reconstruct any change from proposal to live state.

In serverless, audit both the control plane and the data plane: function configuration, IAM, API gateways, queues, event source mappings, workflows, storage, databases, KMS, and secrets. Protect the archive with separated permissions, encryption, append-only/WORM controls, retention, and delivery checks. Audit the audit pipeline itself to catch disabled trails, altered destinations, or shortened retention.

Never store secrets or full payloads just for the sake of evidence. Use stable schemas, sanitized snapshots, artifact digests, and verifiable manifests. Drill queries, restores, break-glass workflows, and audit-gap detection to ensure evidence is truly usable when an incident or audit arrives.
