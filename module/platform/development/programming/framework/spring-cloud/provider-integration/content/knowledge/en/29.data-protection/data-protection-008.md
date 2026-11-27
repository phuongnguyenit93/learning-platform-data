# Access Auditing, Data Residency, and Retention Policies

A system may enforce permissions properly and encrypt data well yet still fail to answer critical questions during an incident: who read this record, which workload sent the request, which region stores the data, where backup copies reside, and when data may be deleted? If audit logs are missing, tampered with, or expired prematurely, operations teams struggle to investigate and the organization struggles to prove its controls operated effectively.

Data protection therefore requires managing **access trails**, **storage/processing locations**, and **retention periods** together. These three domains are related yet distinct:

- **Audit trail** records who did what, to which resource, when, and with what outcome.
- **Data residency** defines the geographic or regional boundaries where data is stored and processed per service commitments and configuration.
- **Retention policy** governs how long data must be kept, when it may be deleted, and when deletion must be suspended.

A policy only takes effect when implemented across actual databases, object storage, log platforms, backups, replicas, search indexes, and cloud services. Selecting a single region for a database does not automatically guarantee that every log, copy, and telemetry signal stays in the same place.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries. The focus of this lesson is designing investigable audits, scoping residency accurately, and enforcing retention/deletion throughout the data lifecycle.

## 1. Learning Objectives and Running Scenario

After this lesson, you will be able to:

1. Distinguish among application audits, control-plane audits, data-plane audits, operational logs, and security events.
2. Design audit events with actor, action, resource, timestamp, outcome, tenant, and correlation ID.
3. Capture read/download accesses, permission changes, exports, deletions, and administrative actions.
4. Integrate Spring Boot auditing with Spring Security, Spring Data JPA, and transactional outboxes.
5. Distinguish among region, geography, data residency, data sovereignty, and cross-region replication.
6. Map storage locations for business data, logs, backups, metadata, keys, and telemetry.
7. Configure AWS CloudTrail, Azure Monitor, and Google Cloud Audit Logs for the right event categories.
8. Design retention, lifecycles, legal holds, immutable storage, and deletion workflows.
9. Test log completeness, audit read permissions, data location, retention, and restore capability.
10. Avoid storing excessive secrets/PII in audit logs and avoid deleting evidence before retention obligations expire.

Running scenario: **document-service** stores customer contracts in object storage, metadata in PostgreSQL, and audit trails in a log platform. The service runs in one region, maintains backups/replicas for disaster recovery, and ships logs to a SIEM. The organization needs to know who viewed/downloaded contracts, whether logs are retained long enough, whether copies exist outside approved geographies, and how to delete data upon retention expiry.

~~~mermaid
flowchart TD
    A["User / service request"] --> B["Spring Boot authorization"]
    B --> C["Business operation"]
    B --> D["Application audit event"]
    C --> E["Database / object storage"]
    E --> F["Cloud data-plane audit"]
    D --> G["Durable audit outbox"]
    F --> H["Cloud audit trail"]
    G --> I["Central log archive / SIEM"]
    H --> I
    E --> J["Backup / replica / index"]
    I --> K["Retention + legal hold + access review"]
    J --> K
~~~

**Auditing tells you what happened; residency tells you where data travels and resides; retention governs how long data and evidence persist.**

## 2. Categories of Audit Trails to Collect

### 2.1. Application audit trail

Application audits are recorded at the business layer, where the application understands the semantic meaning of actions:

- A user views or downloads a customer profile.
- An employee changes a contract's status.
- An administrator grants or revokes permissions.
- A service generates a signed URL or exports a report.
- A user updates payment details.
- A workflow deletes or anonymizes data.

Cloud API logs can tell you a principal invoked `GetObject`, yet cannot necessarily tell which business workflow, ticket, or end user triggered that call. Application audits supply that context.

### 2.2. Control-plane audit

Control-plane audits record configuration and resource administration changes:

- Creating/deleting buckets, databases, keys, or service accounts.
- Modifying IAM/RBAC, bucket policies, or network rules.
- Disabling audit logging or altering log destinations.
- Creating snapshots, replicas, exports, or diagnostic settings.
- Changing retention periods, legal holds, and encryption settings.

These events are typically recorded by the cloud provider. A Spring Boot application cannot replace the cloud's administrative audit source.

### 2.3. Data-plane audit

Data-plane audits record operations directly on data:

- Reading objects, downloading files, writing, or deleting objects.
- Querying tables or reading records.
- Accessing secrets or calling KMS decrypt.
- Reading messages or exporting datasets.
- Modifying ACLs/permissions attached to resources.

These logs often require separate enablement/configuration and can generate high volume and cost. Never assume enabling management events automatically records every object read or data query.

### 2.4. Operational logs and security events

| Category | Purpose | Examples |
| --- | --- | --- |
| Application log | Debugging and operations | Request timeout, DB connection error |
| Access log | Tracking HTTP requests | Method, route, status, latency |
| Application audit | Business evidence | Actor downloaded contract, outcome |
| Cloud audit | Cloud activity evidence | `GetObject`, IAM policy change |
| Security event | Detecting suspicious behavior | Repeated access denied, token reuse |
| Metrics/traces | Performance and execution flows | Latency, spans, error rates |

An access log containing only method, URL, and status may not reveal who the authenticated actor was or which resource was read. Conversely, debug application logs must never be treated as formal audit records.

### 2.5. Questions an audit should answer

Every audit record should help answer:

- **Who:** which user, service principal, workload, or administrator?
- **What:** which action occurred?
- **Which resource:** which object, record, tenant, dataset, or secret?
- **When:** UTC occurrence timestamp and recording timestamp?
- **Where:** which source IP, workload, region, or endpoint?
- **Why:** which purpose, ticket, workflow, or authorizing policy?
- **Result:** allowed, denied, success, failure, or partial?
- **How:** which request ID, trace ID, policy version, and authentication context?

Not every field must appear in every event. Collect only the metadata required for investigation, compliance, and operations.

## 3. Designing an Audit Event Schema

### 3.1. Recommended fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `eventId` | Unique audit event ID | UUID or random ID |
| `occurredAt` | When the operation occurred | UTC/`Instant` |
| `recordedAt` | When the audit store received the event | Distinguish from `occurredAt` |
| `actorType` | `USER`, `SERVICE`, `ADMIN`, `SYSTEM` | Do not rely solely on display name |
| `actorRef` | Pseudonymized subject/service principal | Avoid full emails unless necessary |
| `tenantRef` | Associated tenant | Must be verified from trusted identity/context |
| `action` | `READ`, `DOWNLOAD`, `UPDATE`, `EXPORT`, `DELETE`, `GRANT` | Use a stable vocabulary |
| `resourceType` | `CUSTOMER`, `DOCUMENT`, `SECRET`, `DATASET` | Can use an internal taxonomy |
| `resourceRef` | Resource ID | Never log payloads or document contents |
| `outcome` | `ALLOWED`, `DENIED`, `SUCCESS`, `FAILURE` | Separate authorization decision from execution result |
| `reasonCode` | Reason code or policy decision | Avoid logging exceptions containing secrets |
| `purpose` | Declared business purpose | Never trust arbitrary client strings |
| `classification` | Sensitivity tier of the resource | Aligned with data inventory |
| `source` | Workload, application, API, or cloud service | May include environment |
| `sourceIp` | Source IP when justified to collect | Consider masking/retention |
| `requestId` | Request correlation ID | Validate or generate at the edge |
| `traceId` | Distributed trace ID | Never use as an identity |
| `policyVersion` | Policy/authorization rule version | Helps explain historical decisions |
| `region` | Relevant region/resource location | Do not infer from IP |

### 3.2. Never log sensitive data into audits

Never log directly:

- Passwords, API keys, OAuth tokens, refresh tokens, cookies, private keys.
- Full signed URLs, SAS query strings, or presigned URLs.
- Full request/response bodies.
- National IDs, card numbers, full emails/phones without explicit justification.
- Contract contents or support notes.
- SQL bind parameters containing sensitive data.
- Exception messages containing connection strings or credentials.

Substitute event metadata, opaque resource references, hashed/pseudonymized identifiers, and reason codes. If payloads must be stored for investigation, require an explicit purpose, separate permissions, encryption, and separate retention; never turn audit logs into a second business database by default.

### 3.3. Separating outcome from authorization decision

For example, a user is permitted to download a contract, but object storage transiently fails:

- Authorization decision: `ALLOWED`.
- Operation result: `FAILURE`.

If the user lacks permission:

- Authorization decision: `DENIED`.
- Operation result: `NOT_EXECUTED`.

Separating these two values distinguishes policy denials from infrastructure errors.

### 3.4. Stable event vocabulary

Use a well-defined catalog of action/resource types. Avoid letting each service invent arbitrary strings like `VIEW_DOC`, `DOC_OPENED`, `READ_CONTRACT` for the same behavior. A consistent vocabulary enables querying, alerting, and reporting across services.

## 4. Storing Audits in Spring Boot

### 4.1. Spring Data auditing and access audits are different

Spring Data JPA supports metadata such as created-by, last-modified-by, created-date, and last-modified-date. These are useful for knowing who created or modified an entity and when.

However, Spring Data auditing **does not automatically log every read, download, export, access denial, or permission change**. Those actions require dedicated application audit events.

### 4.2. Enabling JPA auditing

Example auditor configuration extracting the principal from Spring Security:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication())
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
~~~

An entity can capture the metadata:

~~~java
import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class DocumentEntity {

    @Id
    private UUID id;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;
}
~~~

This tracks entity creation/modification history. Never use these fields as a substitute for an access audit trail.

### 4.3. Audit record model

Example Java record:

~~~java
import java.time.Instant;
import java.util.UUID;

public record AccessAuditEvent(
        UUID eventId,
        Instant occurredAt,
        String actorType,
        String actorRef,
        String tenantRef,
        String action,
        String resourceType,
        String resourceRef,
        String authorizationDecision,
        String operationOutcome,
        String reasonCode,
        String purpose,
        String classification,
        String requestId,
        String traceId,
        String region) {
}
~~~

`actorRef`, `tenantRef`, and `resourceRef` should be internal identifiers or pseudonymous references. Never place object bodies inside the record.

### 4.4. Writing audits in the same transaction

For critical operations, audit records should commit alongside business changes or be recorded via a transactional outbox. Example schema:

~~~sql
CREATE TABLE access_audit_outbox (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_type VARCHAR(24) NOT NULL,
    actor_ref VARCHAR(160),
    tenant_ref VARCHAR(160),
    action VARCHAR(48) NOT NULL,
    resource_type VARCHAR(48) NOT NULL,
    resource_ref VARCHAR(200),
    authorization_decision VARCHAR(24) NOT NULL,
    operation_outcome VARCHAR(24) NOT NULL,
    reason_code VARCHAR(80),
    purpose VARCHAR(120),
    classification VARCHAR(32),
    request_id VARCHAR(100),
    trace_id VARCHAR(64),
    region VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

The repositories, actor/context, entity, and exception below represent application domain types. The example focuses on persisting the audit record within the business transaction.

~~~java
import java.time.Clock;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository documents;
    private final AccessAuditOutboxRepository auditOutbox;
    private final Clock clock;

    public DocumentCommandService(
            DocumentRepository documents,
            AccessAuditOutboxRepository auditOutbox,
            Clock clock) {
        this.documents = documents;
        this.auditOutbox = auditOutbox;
        this.clock = clock;
    }

    @PreAuthorize("hasAuthority('document:archive')")
    @Transactional
    public void archive(UUID documentId, AuditActor actor, AuditContext context) {
        DocumentEntity document = documents.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);

        DocumentAccessPolicy.requireArchivePermission(actor, document);
        document.archive();

        auditOutbox.save(AccessAuditOutbox.from(
                UUID.randomUUID(),
                clock.instant(),
                actor,
                "ARCHIVE",
                "DOCUMENT",
                document.getId().toString(),
                "ALLOWED",
                "SUCCESS",
                context));
    }
}
~~~

This example assumes `actor`/`context` were derived from a trusted security context and authorization ran inside the service. Never accept actor or tenant directly from request bodies and trust them.

For denied requests, emit security audits via an authorization failure handler or a separate audit path. Writing inside a business transaction and then throwing `AccessDeniedException` rolls back the transaction and loses the exact `DENIED` event you needed to keep.

The outbox publisher forwards events to the audit store/log platform and marks them published. Publishers may retry on timeouts; downstreams need event IDs to deduplicate. Never delete outbox records before durable publishing confirmation per design.

### 4.5. When must an audit failure fail the operation?

Classify by criticality:

- For permission changes, restricted data downloads, bulk exports, or mandatory-audit actions, inability to record the audit durably may require failing closed or leaving the operation pending.
- For debug/performance telemetry, dropping some events during log backend outages may be acceptable, provided they are not treated as audit evidence.
- When using a same-transaction outbox, business changes and audit intent commit atomically; publishing happens afterward.

Base the decision on risk and business requirements. Never silently drop audits when the sink fails.

### 4.6. Request ID, trace ID, and source IP

- Generate a request ID at the API gateway/edge if the client omits one.
- If accepting `X-Request-ID` from clients, validate charset/length and never treat it as an identity.
- Use W3C trace context to correlate traces across services, yet trace IDs do not prove actors.
- Trust `X-Forwarded-For` only when requests traverse configured trusted proxies/load balancers.
- Never treat the first IP in a raw client-supplied header as proof of origin.
- Avoid logging full URL query strings because they may contain tokens.

### 4.7. Async processing and actor context

`SecurityContext` binds to the current thread execution model by default. When handing work off to executors or message listeners, the principal may not propagate automatically. Pass actor references and request context explicitly in commands/events, or use appropriate context propagation. Never assume background workers run under the original user's identity without verified metadata.

## 5. Audit Logs Must Resist Tampering or Deletion

### 5.1. Separate write, read, and admin permissions

A sound model:

- Applications only hold `INSERT` permission on audit events/outboxes.
- The audit publisher holds append permission to the archive.
- Auditor/security roles hold read and query permissions.
- Platform administrators do not receive default permission to delete evidence.
- Changing retention/immutability requires a separate role and approval.
- Log archive credentials are never shared with the audited workloads.

If the audited principal can alter or delete its own logs, the audit trail loses its value.

### 5.2. Append-only and immutable storage

Protect archives using:

- Database permissions restricted to `INSERT` for writers and `SELECT` for auditors.
- Time-partitioned tables with separate partition-drop policies.
- A centralized log account/project/subscription.
- WORM/object locks or retention locks.
- Hashes/digests to detect tampering.
- Replication to a separate security account or independent SIEM.
- Alerts whenever logging is disabled or destinations/retentions change.

Immutable storage blocks modifications/deletions throughout the retention period. It also makes early deletion difficult or impossible; finalize retention settings before locking.

### 5.3. Tamper-evident is not tamper-proof

Hash chains or signed digests detect modified/deleted records as long as attackers cannot rewrite the entire chain and verification keys. However, if a single administrator holds write, delete, and signing-key control, evidence can still be destroyed.

Cloud providers offer digest/integrity validation features. For example, CloudTrail log file integrity validation creates signed digests to verify log files; enabling validation does not run checks automatically—you must execute validation and protect where digests live.

### 5.4. Protecting the audit archive

- Use a dedicated account/project whenever feasible.
- Require MFA/strong authentication for archive administrative permissions.
- Protect encryption keys and key policies independently.
- Alert on changes to log sinks/trails/diagnostic settings.
- Store copies in approved regions/locations.
- Test restoration and integrity validation.
- Never grant application roles permission to delete archives or shorten retention.

## 6. Data Residency, Geography, and Sovereignty

### 6.1. Key concepts

A **region** is a cloud infrastructure zone offered by a provider. A **geography** can be a group of regions within a geographic or provider-defined data residency boundary. **Data residency** concerns where customer data is stored/processed per configuration and service commitments. **Data sovereignty** is broader, encompassing applicable laws, control, access rights, and data operations.

Picking a region close to users primarily improves latency. Picking regions for residency requires accounting for services, replication, backups, logs, and service terms.

### 6.2. Region alone is not the whole answer

An application can host its database in Singapore yet still send data outside the region via:

- Cross-region database replicas or object replication.
- Backup vaults in another region.
- Log Analytics workspaces or SIEMs in a different geography.
- CDNs/caches or export destinations.
- Data warehouses and BI pipelines.
- Support bundles, crash dumps, or telemetry.
- Identity providers and tenant metadata.
- Developer downloads or administrative access from another country.

Build a complete data-flow map rather than merely specifying a region in deployment manifests.

### 6.3. Data location inventory

| Component | Examples | What to verify |
| --- | --- | --- |
| Primary database | Managed PostgreSQL service | Region, zone, replicas, and PITR |
| Object storage | S3, Blob, Cloud Storage | Bucket/container region, replication, versioning |
| Application audit | Audit DB/outbox | DB location, archive destination |
| Cloud audit | CloudTrail, Activity Log, Cloud Audit Logs | Log destination, region, retention |
| Search/cache | OpenSearch, Redis, managed cache | Replicas, persistence, and exports |
| Backup/DR | Snapshots, vaults, backup copies | Region, account/project, and restore path |
| Key management | KMS, Key Vault, Cloud KMS | Key resource location, replication/availability semantics |
| Analytics | BigQuery, warehouse, SIEM | Dataset/workspace location and cross-region queries |
| Telemetry | Traces, crash dumps, metrics | Backend region, labels, and payload capture |
| Support/exports | Diagnostic bundles, ticket attachments | Recipients, location, retention, and deletion |

### 6.4. Data classification must accompany location

Restricted data may enforce tighter geography, replication, and support-access bounds than Public/Internal data. Not every data category needs identical location constraints. Match controls to classification and contractual/legal obligations.

### 6.5. Region policies and service exceptions

Use organization policies, Azure Policy, SCPs, or policy-as-code to restrict which regions allow resource creation. Policies alone do not prove every service dependency is regional. Some services are global, some metadata/control planes have different scopes, and some features store/replicate data under specific terms.

Before committing to residency guarantees, verify product-specific data residency documentation and service terms. Document exceptions, approvers, and compensating controls.

## 7. Retention Policies and Data Lifecycle

### 7.1. Retention requires explicit ownership

Every data category needs:

- Data owner and storage purpose.
- Classification.
- Business/contractual/legal basis.
- Retention start event.
- Duration and unit.
- Renewal/legal hold conditions.
- Deletion or anonymization method.
- Handling for backups, replicas, indexes, and archives.
- Proof of completed deletion.
- Owner approving exceptions.

Never rely on service defaults alone because default retention may violate organizational obligations.

### 7.2. Retention start times

Timers can start from different milestones:

- Record creation date.
- Contract end date.
- Ticket closure date.
- Account termination date.
- Audit event occurrence date.
- Legal hold release date.

For example, contracts may need retention measured from the end of the customer relationship, whereas access logs run from event occurrence. Never apply the same trigger blindly to every dataset.

### 7.3. Example retention matrix

Values below illustrate policy structure only, not default legal mandates:

| Data class | Example data | Sample retention rule | End-of-life action |
| --- | --- | --- | --- |
| Operational logs | Debug/health/latency | 30–90 days per operational need | Lifecycle delete |
| Security audit | Access denied, privilege changes, exports | Per approved investigation and compliance needs | Archive/immutable then delete |
| Business audit | Who approved contract/payment | Per record lifecycle and recordkeeping obligations | Retain/hold then delete |
| Customer content | Profiles, documents, files | Per purpose and contract | Delete/anonymize |
| Temporary uploads | Quarantined files | Short TTL after scanning/processing | Lifecycle delete |
| Backups | Snapshots/PITR | Per RPO/RTO and backup policy | Backup expiry |
| Legal evidence | Records under legal hold | Until hold release and underlying retention end | Authorized release then delete |

Every figure must be validated by the data owner, security, and legal/compliance in context. Overly long retention inflates risk and cost; overly short retention destroys evidence or violates obligations.

### 7.4. Retention vs. immutability

- Retention policies define how long data is kept.
- Lifecycle rules automatically transition storage classes or delete when conditions match.
- Versioning keeps multiple object versions without setting an expiration by itself.
- Immutable/WORM prevents modification/deletion for a period or while a legal hold applies.
- Backup policies maintain recovery copies per RPO/RTO.

Having a 365-day retention target does not stop an object from being deleted today. Preventing premature deletion requires appropriate immutability/permission controls.

### 7.5. Legal holds and exceptions

A legal hold suspends deletion of data relevant to an investigation or dispute. When placing a hold:

- Record reason, requester, scope, and start date.
- Restrict permissions to place/remove holds.
- Ensure lifecycle jobs never delete held objects.
- Emit audit records whenever holds are added or removed.
- Once released, recalculate deletion eligibility.
- Never extend holds indefinitely once the underlying basis ends.

### 7.6. Cross-system data deletion

When deleting a customer/document, address:

1. Primary database.
2. Object storage and object versions.
3. Read replicas and cross-region replicas.
4. Search indexes and caches.
5. Event/message retention.
6. Export/report files.
7. Analytics warehouses.
8. Backups/snapshots/PITR.
9. Application logs and audit logs.
10. Support bundles or third-party processors.

Not every audit record must be deleted alongside business data; minimal metadata may be required to prove deletion occurred. Design audit records so they omit payloads or direct identifiers beyond necessity.

### 7.7. Backups and crypto-erasure

Backups can outlive deletions from the primary database. Policies must specify:

- Backup expiration on its own schedule.
- Reapplying deletions/tombstones upon restore for records deleted after the backup timestamp.
- With envelope encryption, crypto-erasure is only valid if no copies of the key material or recovery paths remain anywhere.
- Never delete shared KEKs while valid data still needs decryption.
- Test restores and deletion replay in an isolated environment.

## 8. AWS: CloudTrail, S3 Data Events, and Object Lock

### 8.1. CloudTrail management events and data events

CloudTrail records AWS API activity:

- Management events track control-plane changes such as creating resources, policies, and configurations.
- Data events track resource operations such as S3 `GetObject`, `PutObject`, and `DeleteObject`.
- Some services support network activity events or other event types.

**S3 object-level data events are not enabled by default on trails.** Configure advanced event selectors to target specific buckets/objects and read/write actions. Data events can produce high volume and cost; scope them by classification, bucket, and audit goals.

For example, if you only need to audit contract access, enable S3 data events for the contract bucket/prefix rather than every bucket in the account. Cover `GetObject`, `PutObject`, `DeleteObject`, and related actions.

### 8.2. Storing and validating log integrity

CloudTrail can deliver logs to a chosen S3 bucket, ideally in a dedicated log archive account. Enable log file integrity validation to generate signed digests verifying log files were not altered after CloudTrail delivery.

- Protect the archive bucket with a dedicated policy.
- Restrict delete and lifecycle-modification permissions.
- Enable encryption and auditing on the archive bucket.
- Periodically verify digests with the appropriate tool/CLI.
- Alert if trails are stopped, logging is disabled, or destinations change.

Enabling integrity validation only generates digests; you must still run validation checks and protect both logs and digests.

### 8.3. S3 Object Lock

S3 Object Lock provides WORM protection for object versions:

- The bucket must have Versioning enabled.
- Governance mode lets specially privileged principals bypass retention.
- Compliance mode blocks deleting/overwriting object versions before expiry, even by the account root user.
- Legal holds have no fixed expiration date and must be explicitly cleared.
- Object Lock does not prevent creating a new object version under the same key; control versions and access policies.

Enabling Object Lock is a bucket-lifecycle decision; once enabled, you cannot disable Object Lock or suspend versioning on that bucket. Do not turn it on for a log archive merely to "feel safer" without first designing retention, legal hold, and deletion workflows.

### 8.4. AWS residency and replication

Select an AWS Region for S3/databases and check:

- S3 Cross-Region Replication or replication rules.
- Backup copies sent to other regions/accounts.
- CloudTrail destination bucket region.
- KMS key region and key policies.
- Exports to Athena/warehouses/SIEMs.
- Global services and metadata outside regional resource bounds.

A CloudTrail multi-region trail collects events from multiple regions; it does not determine where the archive lives. Include destination buckets and replicas in your data location inventory.

### 8.5. AWS retention and lifecycle

S3 Lifecycle transitions or expires objects/versions. Interactions among Versioning, Object Lock, and legal holds must be tested carefully: locked objects cannot be deleted by lifecycle rules before eligibility. Test lifecycle rules on a test bucket covering noncurrent versions, delete markers, replication, and backups.

## 9. Azure: Activity Log, Resource Logs, and Immutable Blob Storage

### 9.1. Activity Log and resource logs

Azure Monitor captures distinct log sources:

- **Activity Log:** subscription-level administrative/control-plane operations, such as resource creation, role changes, or configuration edits.
- **Resource logs:** operations inside individual resources, which may contain data-plane operations depending on the service.
- **Entra sign-in/audit logs:** authentication and identity changes.
- **Application logs:** business events emitted by Spring Boot.

The Activity Log is built into the platform and retained for 90 days; for longer retention, route it to a Storage account, Log Analytics, or Event Hubs as needed. Resource logs are not collected automatically by default for every resource; create diagnostic settings per resource.

### 9.2. Diagnostic settings

Diagnostic settings define:

- Log/metric categories to collect.
- Destination: Log Analytics workspace, Storage account, Event Hubs, or partner integration.
- Collection mode/schema.
- Retention policies at the destination.

Do not assume enabling a diagnostic setting on one resource covers the entire subscription. Use policy/deployment automation to verify new resources have required diagnostic settings.

Some destinations carry regional constraints; for example, Storage/Event Hubs destinations for regional resources must meet matching location restrictions. Resource logs use store-and-forward delivery without strict transactional guarantees; critical business audits should keep durable records inside the application.

### 9.3. Azure immutable Blob Storage

Azure Blob immutable storage supports:

- Time-based retention: objects cannot be modified/deleted during the interval.
- Legal hold: enforces WORM until the hold is cleared.
- Container-level or version-level WORM depending on configuration.
- Policy auditing and management within supported scopes.

Legal holds and time-based retention can be combined. Before locking a policy, verify retention intervals, versioning, delete semantics, and who can set/clear legal holds. Immutable storage can block data deletion even after business records expire.

### 9.4. Azure residency and location

Azure regions belong to geographies; a geography can serve as a residency boundary for many services. However, commitments and exceptions depend on the specific product, feature, replication option, and service terms.

Verify:

- Regions of Storage accounts, databases, Key Vaults, and Log Analytics workspaces.
- Where diagnostic settings route to workspaces/storage/event hubs.
- Whether geo-redundant storage replicates within the geography or across geographies per SKU.
- Backup vaults and recovery regions.
- Microsoft Entra/identity metadata and service-specific location commitments.
- Where customer exports occur or support accesses data from.

Azure Policy can restrict allowed resource creation locations, yet does not replace checking global services or per-product exceptions.

### 9.5. Azure retention

The 90-day Activity Log retention is not the default for all resource logs. Log Analytics, Storage accounts, Event Hubs consumers, and archives each have their own retention/TTL settings. Design lifecycles and deletions at destinations; verify export pipelines do not keep extra out-of-policy copies.

## 10. Google Cloud: Cloud Audit Logs, Log Buckets, and Bucket Lock

### 10.1. Cloud Audit Logs categories

Google Cloud Audit Logs include major categories:

- **Admin Activity:** administrative operations modifying configurations/resources.
- **Data Access:** reading metadata/data or creating, modifying, or reading user-provided data.
- **System Event:** actions performed by Google Cloud systems.
- **Policy Denied:** requests rejected by policies, depending on service/configuration.

Admin Activity is enabled by default. Data Access is disabled by default for most services, excluding certain services like BigQuery; inspect and enable per service at the project/folder/organization scope. Data Access logs can carry substantial volume and cost.

### 10.2. Cloud Storage audit limitations to know

For Cloud Storage:

- Admin Activity records bucket/IAM configuration changes.
- Data Access records object read/write operations when enabled.
- Public access via `allUsers` or `allAuthenticatedUsers` is not logged by Cloud Audit Logs the same way as standard authenticated access.
- Object Lifecycle Management and Autoclass are not fully tracked in Cloud Audit Logs like user-driven operations.
- When public access or lifecycle logging is needed, evaluate Cloud Storage usage logs; delivery can be delayed and lacks the timeliness/completeness guarantees of audit logs.

Never enable only Admin Activity and conclude you have evidence of every object download.

### 10.3. Cloud Logging log buckets

Cloud Logging stores logs in log buckets:

- Log buckets are regional resources; their location governs where logs are stored/indexed/queried.
- Buckets have independent retention periods and IAM access.
- Logs can route via sinks to log buckets, BigQuery, Cloud Storage, or Pub/Sub.
- Bucket location is chosen at creation time; an existing bucket's location cannot be changed.
- Default `_Required` and `_Default` buckets may be created in `global` unless a default resource location is configured beforehand; organizations/folders can set a default location for new buckets.
- User-defined buckets can specify dedicated regions and retentions.

Never route sensitive logs to a BigQuery dataset or SIEM in another region without reflecting it in your residency map.

### 10.4. Cloud Storage Bucket Lock

A Cloud Storage retention policy dictates the minimum duration objects must be kept. Once a bucket retention policy is locked:

- You cannot remove the policy or shorten the retention period.
- Objects younger than the retention age cannot be deleted/overwritten.
- The bucket cannot be deleted until every object satisfies retention.
- Locking is irreversible.

Always test with a separate bucket, synthetic data, and short durations before locking a production bucket.

### 10.5. BigQuery locations

A BigQuery dataset's location is selected upon creation and cannot be changed directly afterward. Moving requires copying/replicating or creating a new dataset in another location where supported.

All datasets referenced in a single query must have compatible locations. Verify dataset, job, connection, external data source, and log sink locations before deploying analytics.

## 11. Quick Comparison Across the Three Providers

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Control-plane audit | CloudTrail management events | Azure Activity Log | Cloud Audit Logs Admin Activity |
| Data-plane audit | CloudTrail data events; requires configuration | Resource logs/diagnostic settings per resource | Cloud Audit Logs Data Access; must enable for most services |
| Object access | S3 `GetObject`/`PutObject`/`DeleteObject` data events | Storage resource logs | Cloud Storage Data Access; usage logs for certain cases |
| Central log destination | S3 archive, CloudTrail Lake, SIEM | Log Analytics, Storage, Event Hubs | Cloud Logging buckets, BigQuery, Cloud Storage, Pub/Sub |
| Integrity/immutability | CloudTrail digest validation, S3 Object Lock | Immutable Blob Storage | Cloud Logging bucket lock and Cloud Storage Bucket Lock |
| Residency control | AWS Region, buckets, replicas, and destinations | Azure region/geography, workspaces, and storage destinations | Resource location, log bucket region, dataset/bucket location |
| Retention | S3 Lifecycle/Object Lock, CloudTrail archive | Activity Log export, workspace/storage retention, Blob immutability | Log bucket retention, GCS retention/Bucket Lock, dataset policies |
| Common pitfall | S3 data events left disabled | Diagnostic settings not created | Data Access logs left disabled |

## 12. Implementing Retention Policies in Applications

### 12.1. Data retention catalog

An internal policy table can describe:

~~~yaml
retentionPolicies:
  - id: operational-log
    dataClass: INTERNAL
    purpose: application-operations
    retentionDays: 45
    destination: central-log-bucket
    immutable: false
    deleteMethod: lifecycle

  - id: security-access-audit
    dataClass: CONFIDENTIAL
    purpose: security-investigation
    retentionDays: 400
    destination: audit-archive
    immutable: true
    deleteMethod: controlled-expiration

  - id: temporary-upload
    dataClass: CONFIDENTIAL
    purpose: upload-processing
    retentionDays: 7
    destination: quarantine-storage
    immutable: false
    deleteMethod: lifecycle
~~~

This structure is illustrative, not a default legal schedule. Before applying, obtain owner and compliance approval for each policy and verify destinations enforce matching lifecycles/immutability.

### 12.2. Do not enforce retention only in code

If code sets a 365-day constant while a bucket lifecycle retains data for 7 years, the data persists. If an app deletes a record while backups retain it for months, copies still exist. Policies must be enforced in the underlying storage/services and audited periodically.

Use policy-as-code or IaC to enforce:

- Region allowlists.
- Enabled audit logging.
- Diagnostic settings.
- Log destinations.
- Retention periods.
- Object locks/legal holds.
- Backup copy locations.
- IAM permissions on audit archives.

### 12.3. Deletion workflow

A deletion workflow may include:

1. Verify the deletion request and owner.
2. Check legal holds, litigation holds, and retention obligations.
3. Map data lineage: primary, replicas, indexes, exports, events, backups.
4. Record a deletion tombstone or workflow state.
5. Delete/anonymize primary data in a safe order.
6. Purge caches/indexes and exports per policy.
7. Let backups expire or apply deletion replay upon restore.
8. Emit an audit event confirming scope, outcome, and timestamp.
9. Verify remaining copies and report completion.
10. Keep minimal required evidence without copying deleted payloads.

Never log raw personal data in deletion audits. Use pseudonymized references, deletion request IDs, and record counts.

### 12.4. Retention exceptions and legal holds

Each exception requires:

- Request ID and owner.
- Justification.
- Dataset/object scope.
- Duration or termination condition.
- Approver.
- Permissions to place/clear the hold.
- Audit logging for every change.

Never let application workloads set indefinite legal holds automatically just to avoid deletion errors.

## 13. Controlling Audit Read Access and Data Locations

### 13.1. Least privilege for audits

Separate permissions explicitly:

- Application writer: append events only.
- Log pipeline: read outbox and write to archive.
- Security analyst: query audits within assigned scope.
- Auditor: read-only access and audited exports.
- Platform admin: manages infrastructure without default permission to alter evidence.
- Retention operator: executes lifecycle/hold actions upon approval.

Never grant a single super-role to those who generate events, investigate incidents, and manage retention.

### 13.2. Auditing access to audits

Log archives themselves hold sensitive insights into user behavior and infrastructure. Record:

- Who queries the audit archive.
- Who exports/downloads logs.
- Who alters retention or sinks.
- Who modifies IAM/log bucket policies.
- Who clears legal holds or unlocks policies where allowed by the provider.
- Who accesses backups or evidence archives.

### 13.3. Alerting on audit pipeline changes

Configure alerts for:

- CloudTrail trails or data event selectors being disabled.
- Azure diagnostic settings being deleted or destinations changed.
- Google Cloud audit configurations or sinks being altered.
- Log archive retention being shortened.
- Object Lock/Bucket Lock/immutability policies changing.
- Sudden drops or stalls in log ingestion.
- Creation of new service accounts/roles permitted to delete archives.

Place alerts in an independent control plane whenever possible so attackers cannot easily disable both logging and alerts.

### 13.4. Periodic residency verification

On a schedule or upon architecture changes:

- Compare IaC/resource inventories against region policies.
- Verify replication and backup destinations.
- Verify workspace/log bucket/dataset locations.
- Inspect data exports, SIEMs, and third-party integrations.
- Review support access and operational boundaries against product terms.
- Store configuration evidence and owner sign-offs.

Do not treat a single go-live review as sufficient; regions, service features, and data flows evolve over time.

## 14. Testing Audits, Residency, and Retention

### 14.1. Application audit tests

- Successful read/download emits an event with actor/resource/outcome.
- Access denied emits an appropriate event.
- Admin grant/revoke includes actor and policy version.
- Exports emit dedicated events with scope.
- Events contain no raw tokens, signed URLs, passwords, or bodies.
- Request IDs/trace IDs correlate with operational logs.
- Async workers preserve explicitly propagated actor context.

### 14.2. Audit pipeline tests

- Outbox records commit atomically with business transactions.
- Publisher retries do not produce duplicate audit records.
- Transient sink outages do not drop persisted events.
- Application roles cannot update/delete archives.
- Auditors can read but cannot modify records.
- Integrity validation detects tampered log files in a test environment.
- Alerts fire when trails/diagnostic settings are disabled.

### 14.3. Residency tests

- Primary DBs, object storage, and KMS reside in approved locations.
- Replicas/backups target only approved destinations.
- Log workspaces/buckets/SIEMs sit within allowed boundaries.
- BigQuery datasets and job locations are compatible.
- Unapproved cross-region copies are blocked by policy.
- Global resources/service-specific exceptions are documented in the inventory.

### 14.4. Retention tests

- Aged objects are handled by lifecycle rules per policy.
- Objects within retention cannot be deleted when WORM is enabled.
- Legal holds block deletion until cleared.
- Backups expire on schedule.
- Backup restores replay tombstones/deletions occurring after the backup timestamp.
- Log archives are not deleted prematurely.
- Retention locks cannot be shortened or removed per provider semantics.

### 14.5. Restore and evidence tests

- Restore a backup into an isolated environment.
- Verify decryption using the matching key version.
- Confirm an audit event records the restore action.
- Verify data deletion states are replayed.
- Validate hashes/digests of log archives.
- Produce a report with timestamps, scope, results, and operator.

## 15. Troubleshooting Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Management events exist but no object reads | Data-plane auditing not enabled | Enable S3 data events, Azure resource logs, or GCP Data Access |
| Azure Activity Log only keeps 90 days | Not routed to longer-term storage | Add diagnostic settings to Storage/Log Analytics/Event Hubs |
| GCS shows no logs for public objects | Cloud Audit Logs omit public `allUsers`/`allAuthenticatedUsers` access | Evaluate usage logs and tighten access restrictions |
| Logs sit in the wrong geography | Log sink/workspace/bucket is in another region | Check locations of every destination and replica |
| BigQuery query reports location mismatch | Dataset/job/connection in different locations | Align locations or copy/replicate datasets |
| Lifecycle fails to delete objects | Retention lock/legal hold/versioning still active | Inspect object versions and hold states |
| Audit logs vanish after deleting a resource | Destination tied to resource or never archived | Isolate log archives; check diagnostic settings and retention |
| Audit events missing actor in async workers | Security context not propagated | Pass actor metadata explicitly in messages/commands |
| Duplicate audit events | Outbox publisher retries or at-least-once delivery | Deduplicate at the sink using event IDs |
| Cannot prove who read an object | Only app logs exist or data events disabled | Enable provider data-plane audits and correlate request/resource refs |
| Customer data not completely deleted | Copies remain in backups, replicas, caches, indexes, or exports | Follow data lineage and cross-system deletion workflows |
| WORM blocks legitimate data deletion | Misconfigured retention/lock or uncleared legal hold | Review policies/approvals before locking; never bypass arbitrarily |

## 16. Comprehensive Hands-On Exercise

`document-service` stores contracts in object storage, metadata in PostgreSQL, audits in a log platform, and backups in a recovery region. The application integrates with AWS, Azure, or Google Cloud depending on environment.

**Tasks:**

1. Build a data inventory covering primary data, audits, logs, telemetry, backups, keys, exports, and replicas.
2. Design an audit schema capturing actor, action, resource, tenant, purpose, outcome, request ID, and policy version.
3. Emit access audit events for `READ`, `DOWNLOAD`, `EXPORT`, `UPDATE`, `DELETE`, and `GRANT`.
4. Use Spring Data auditing for created/modified metadata and distinguish it from access audits.
5. Persist audits via transaction/outbox so events survive service restarts.
6. Enable data-plane auditing for object storage and document scope/cost.
7. Select log destinations and verify region/geography per provider.
8. Build a retention matrix for operational logs, security audits, business records, temporary files, and backups.
9. Configure WORM/legal holds on the audit archive in a test environment.
10. Write a deletion workflow spanning primary, replicas, indexes, exports, and backups.
11. Test audit read permissions, integrity validation, retention, and restoration.
12. Write a report proving data and logs reside within approved locations.

**Self-assessment questions:**

- How do application audits differ from cloud control-plane audits?
- Why must S3 data events be configured explicitly?
- Why are Azure resource logs not collected automatically?
- Why must GCP Data Access logs be enabled explicitly for many services?
- Why might Cloud Storage public access not appear in Cloud Audit Logs?
- How do region and geography differ?
- Why must log destinations and backups appear in a residency map?
- How does a retention policy differ from WORM/immutability?
- Why must BigQuery dataset locations be chosen prior to creation?
- Why must Cloud Logging log bucket locations be verified?
- Why does S3 Object Lock require Versioning?
- Why must GCS Bucket Lock be carefully evaluated before enabling?
- Why does Spring Data auditing not record every read/download?
- Why does a transactional outbox fit audit events well?
- When deleting a customer, why must replicas, caches, indexes, and backups be addressed?
- Why must reading the audit archive also be audited?

**Guided answers:** application audits capture business context while cloud audits record provider actions; S3 data events are off by default; Azure resource logs require diagnostic settings; GCP Data Access is off by default for most services; public access has audit logging limits; regions are infrastructure zones while geographies can act as boundaries; logs and backups are data copies; retention sets duration while WORM blocks modification/deletion; BigQuery locations cannot be changed directly after creation; Cloud Logging log buckets have fixed locations; S3 Object Lock requires versioning; GCS Bucket Lock irreversibly prevents reducing/removing retention; Spring Data auditing tracks entity creation/modification only; outboxes bind audit intent to transactions; deletion must follow full data lineage; audit readers themselves require governance.

## 17. Official References

### Spring

- [Spring Data JPA – Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html): created/modified metadata and `AuditorAware` integration with Spring Security.

### AWS

- [AWS CloudTrail – Logging data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html): data-plane events, S3 object activity, and advanced event selectors.
- [AWS CloudTrail – S3 data events for governance](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-s3-data-events-governance.html): auditing access, deletion, replication, and cost considerations.
- [AWS CloudTrail – Log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html): digests and verifying log integrity.
- [Amazon S3 – Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html): WORM, governance/compliance modes, retention, and legal holds.
- [Amazon S3 – Configuring Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html): Versioning requirement and bucket/object configuration.
- [AWS – Data privacy FAQ](https://aws.amazon.com/compliance/data-privacy-faq/): Region selection and customer content location.

### Azure

- [Azure Monitor – Activity Log](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log): Activity Log and retaining beyond 90 days.
- [Azure Monitor – Resource logs](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/resource-logs): collecting resource logs and destinations.
- [Azure Monitor – Diagnostic settings](https://learn.microsoft.com/en-us/azure/azure-monitor/platform/diagnostic-settings): routing logs/metrics to workspaces, Storage, and Event Hubs.
- [Azure Storage – Immutable storage overview](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview): WORM, time-based retention, and legal holds.
- [Azure – Data residency](https://azure.microsoft.com/en-us/explore/global-infrastructure/data-residency/): geographies, regional services, and location exceptions.
- [Azure – Regions overview](https://learn.microsoft.com/en-us/azure/reliability/regions-overview): regions, geographies, and resiliency.

### Google Cloud

- [Cloud Audit Logs with Cloud Storage](https://docs.cloud.google.com/storage/docs/audit-logging): Admin Activity, Data Access, public access, and logging limitations.
- [Enable Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access): enabling Data Access and volume/cost considerations.
- [Cloud Logging – Log buckets and retention](https://docs.cloud.google.com/logging/docs/store-log-entries): locations, retention, IAM, and routing.
- [Cloud Logging – Locations](https://docs.cloud.google.com/logging/docs/region-support): regional log buckets and default locations.
- [Cloud Storage – Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock): retention policies and irreversible locking.
- [BigQuery – Dataset locations](https://docs.cloud.google.com/bigquery/docs/datasets): fixed location at dataset creation.
- [Cloud Storage – Usage and storage logs](https://docs.cloud.google.com/storage/docs/access-logs): when usage logs are needed to supplement audits.

### OWASP

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to avoid logging, log integrity, access control, and retention.

**Remember:** to prove data was accessed appropriately, combine application audits with cloud data-plane audits. To satisfy residency, track primaries, replicas, backups, logs, analytics, and telemetry alike. To make retention enforceable, implement lifecycles/immutability in actual storage, handle legal holds, and test restore/deletion across the entire data flow.
