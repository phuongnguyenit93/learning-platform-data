# Migrating Data, Identity, Endpoints, and Operations

When migrating a Spring Boot application from one cloud provider to another, the hardest part is rarely swapping out an SDK. Accumulated data, workload access permissions, service addresses, network policies, and operational processes are all tied to the current platform. If you only change endpoints or swap Spring Cloud libraries, the application might start up cleanly yet still lose data, lack permissions, send messages incorrectly, or be unrecoverable during an incident.

Within the scope of integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, migration must be treated as a controlled change across four layers: data, identity, endpoints, and operations. Spring Cloud AWS, Spring Cloud Azure, and Google Cloud integration libraries help applications use corresponding services in an idiomatic Spring way, but they do not give the three providers' services identical semantics or identical security models.

## Objectives

After this lesson, you will be able to:

- Inventory data and service dependencies before switching providers.
- Choose object, database, and message migration strategies suited to consistency requirements.
- Migrate workload identities to the target cloud's native authorization mechanisms without embedding long-lived keys in the application.
- Configure endpoints, regions, private networking, and TLS via environment-specific configuration.
- Design cutover, verification, rollback, and post-migration monitoring.
- Decouple business logic from individual provider SDKs using adapters with clear boundaries.

## 1. Pre-migration inventory

First, list every resource that the application reads, writes, or depends on at startup. The inventory must cover both resources called directly from Java code and resources accessed indirectly via Spring configuration, secrets, environment variables, or network infrastructure.

| Dependency category | What to record | Migration questions |
|---|---|---|
| Object storage | Buckets/containers, keys, metadata, versions, lifecycles, encryption | Are object names, metadata, and retention policies preserved? |
| Databases | Engine, schemas, indexes, extensions, transactions, replicas | Are data types, sequences, and transaction behaviors compatible? |
| Messaging | Queues/topics, retention, ordering, acknowledgements, DLQs | Does the target provider share the same delivery and retry model? |
| Identity | Roles, service accounts, managed identities, policies | Which workloads may act on which resources? |
| Secrets and keys | Secret stores, encryption keys, rotation, decryption permissions | Who can read secrets and which key decrypts legacy data? |
| Endpoints and network | Regions, DNS, private endpoints, firewalls, proxies, TLS | Can the application reach targets from the right network? |
| Operations | Logs, metrics, traces, alerts, backups, runbooks | Which signals does ops use to detect and resolve failures? |

Next, classify data. Authoritative source data must be migrated and reconciled rigorously. Reproducible data such as caches or search indexes can be rebuilt. In-flight messages require a dedicated plan because acknowledgement state, ordering, and retention limits can differ across brokers.

For each data category, define at least:

- Current volume, rate of new data generation, and allowed migration window.
- RPO (acceptable data loss) and RTO (target recovery time).
- Requirements for storage residency, encryption, retention, deletion, and auditing.
- Measurable acceptance criteria, such as record counts, object counts, total bytes, and checksums.
- How to return to the source if the target fails criteria after cutover.

Do not begin copying before establishing which system is the authoritative writer at each stage. Two places accepting writes without a conflict resolution strategy create an irreconcilable state.

## 2. Migrating data by type

### 2.1. Object storage

AWS S3, Azure Blob Storage, and Google Cloud Storage all store objects, but how they represent permissions, versions, metadata, tags, lifecycles, retention, and encryption differs. An object whose bytes are copied successfully can still lose business attributes if you only copy raw bytes.

A sound workflow usually has four phases:

1. **Initial copy:** use a data transfer tool or migration service suited to the source/target pair and data scale. At large volumes, do not route all objects through Spring Boot application requests to download and re-upload; that wastes application resources and increases timeout risk.
2. **Catch up on changes:** continue transferring newly created, updated, and deleted objects since copying started. Use inventory reports, change logs, or incremental sync mechanisms supported by the source service.
3. **Reconcile:** compare key lists, counts, sizes, required metadata, and content checksums. Retain transfer manifests so failed objects can be investigated and retried.
4. **Switch write authority:** at cutover, pause or lock writes on the source for a defined window, transfer final deltas, re-verify, and point the application to the target.

Do not assume an object's ETag is always the MD5 of its content. With multipart uploads or certain encryption modes, ETags may not represent a content checksum. Use provider-supported checksums or compute SHA-256 during transfer when integrity requirements demand it.

Create a mapping table for non-equivalent attributes. For example, source ACLs may need translation into target IAM policies or role assignments; lifecycle rules may need rewriting; source provider encryption keys do not automatically transfer to the target provider. If data is encrypted with customer-managed keys, define a workflow to decrypt at the source and re-encrypt with target keys while keeping data accessible throughout migration.

### 2.2. Databases

Database migration must address both structure and data. Beyond tables and rows, verify data types, collations, timezones, sequences/identities, indexes, constraints, triggers, stored procedures, extensions, and transaction isolation levels. A schema valid on the source engine may not run verbatim on the target engine.

For large datasets or low-downtime requirements, the workflow typically involves an initial bulk load followed by replication or Change Data Capture (CDC) to stream ongoing changes. Migration tooling must support the actual engines and topology. Spring Boot continues serving business traffic; do not turn every application request into a database replication step.

Before cutover, verify per-table row counts, foreign keys, constraints, business aggregates, and critical queries. If using sequences, confirm the next value at the target is higher than the highest issued value at the source to avoid duplicate keys after switching.

Avoid direct dual-writes to two databases without a distributed transaction resolution mechanism. A request may succeed on the source and fail on the target, or vice versa. If events are needed for synchronization, consider the Transactional Outbox pattern: persist the business change and an outbox record in the same transaction, then let a separate process publish events with retries and idempotency.

### 2.3. Queues, topics, and events

Do not treat migrating a message backlog like copying files. SQS/SNS, Azure Service Bus/Event Grid, and Google Pub/Sub differ in acknowledgements, visibility or ack deadlines, ordering, retention, subscriptions, dead-lettering, and retries. A message acknowledged at the source broker does not mean it has been processed at the target broker.

Before switching brokers, define:

- Which producers stop sending to the source and when.
- Which consumers must finish in-flight messages before shutting down.
- Whether unprocessed messages will be drained, replayed, or moved via migration tooling.
- Which idempotency keys prevent applying an event twice.
- Which event ordering is required by business logic and what scope must be preserved.
- How failing messages and dead-letter queues are migrated so investigation trails are not lost.

Design consumers to be idempotent from the outset. When a message is redelivered, consumers recognize already-processed events and avoid repeating business side effects. If ordering must be preserved, choose partition keys or sessions suited to the target broker; never assume global ordering is preserved after changing providers.

## 3. Migrating workload identity and access control

Applications running in the cloud should obtain identity from their execution environment. Never package long-lived access keys, client secrets, or service account keys inside YAML files, container images, source code, or static pipeline variables.

| Provider | Typical workload identity | How the application obtains credentials |
|---|---|---|
| AWS | IAM role attached to EC2, ECS tasks, or workloads on EKS | AWS SDK credential provider chain reads runtime environment or configured workload identity |
| Azure | Managed Identity on supported services or Workload Identity for AKS | Azure Identity credential chain, typically via `DefaultAzureCredential` |
| Google Cloud | Service account attached to workload or Workload Identity Federation/Workload Identity for GKE | Application Default Credentials (ADC) or corresponding auth libraries |

Mechanism names vary across platforms, but the shared principle is that identity comes from the runtime and permissions are managed outside the application. For instance, an EKS pod can obtain an IAM role via IRSA or EKS Pod Identity; an AKS workload can use Workload Identity; a GKE workload can map a Kubernetes service account to a Google service account. Pick the mechanism supported by your platform version and cluster configuration.

Apply least privilege per workload. A service that only reads objects should have read access solely to the required bucket or container; do not grant admin permissions over the entire storage account. Separate application roles from infrastructure deployment roles. In production environments, restrict resource scope, actions, regions, and access conditions wherever the provider supports them.

In Spring Boot applications, prefer letting provider SDKs and starters discover credentials automatically via standard provider chains. Do not manually read access keys and instantiate clients if the SDK already supports workload identity. For local development, use developer profiles or CLI logins; never copy production credentials to personal machines.

### 3.1. Secrets and encryption keys

Secrets such as database passwords, third-party tokens, and private keys should live in an appropriate secret management service, such as AWS Secrets Manager or Parameter Store, Azure Key Vault, and Google Secret Manager. Applications receive read access only to the specific secrets they need. Secret reads should have audit logs, rotation mechanisms, and handling for expired secrets.

Distinguish secrets from ordinary configuration. Regions, bucket names, and endpoints are typically configuration; passwords, tokens, and private keys are secrets. Never write secrets into logs, exception messages, actuator environment endpoints, or metric labels. When secrets rotate, verify whether connection pools and clients reload new values or require restarts.

Data encryption keys need a separate plan. Keys in KMS, Key Vault, or Cloud KMS have independent policies, versions, and lifecycles. Do not delete source keys merely because copied data has landed on the target; destroy or revoke them only after confirming that data, backups, and archives can all be decrypted according to retention policies.

## 4. Migrating endpoints and connection configuration

Endpoints are part of the deployment contract. Applications may need endpoints for storage, databases, brokers, secret managers, internal APIs, and observability services. When switching providers, these values usually change alongside regions, accounts/projects, networking, and authentication methods.

Externalize environment-varying settings from source code. Example application configuration:

```yaml
app:
  cloud:
    provider: ${CLOUD_PROVIDER:aws}
    region: ${CLOUD_REGION:ap-southeast-1}
  storage:
    container: ${STORAGE_CONTAINER:documents}
    endpoint: ${STORAGE_ENDPOINT:}
```

This is application-owned configuration; each provider adapter maps these values to its own SDK clients and properties. Do not assume a single generic `endpoint` property can replace provider-specific settings such as Azure account URLs, S3 regions/endpoints, or Google Cloud projects and buckets. Configure custom endpoints only for explicit reasons such as private endpoints, proxies, emulators, or test environments.

When establishing connectivity on the target cloud, verify these layers:

1. **Network routing:** does the workload have routes to the subnet or network hosting the service; do security groups, firewalls, route tables, and egress policies permit connections?
2. **DNS:** do endpoint hostnames resolve to expected addresses from inside the application's actual runtime environment? Private endpoints often require private DNS zones linked to the right network.
3. **TLS:** are certificates valid for the hostname; does the JVM trust store trust the required CA; does any proxy alter the certificate chain?
4. **Region and resource scope:** do region, project, subscription, account, bucket/container, and database match deployment settings?
5. **Timeouts and limits:** do connect/read timeouts, connection pools, request sizes, rate limits, and quotas match target service latency and limits?

Never disable hostname verification or TLS validation to bypass certificate errors in production. Fix the trust chain, DNS, or proxy configuration. For private endpoints, test from inside the target subnet or cluster; a successful call from a developer laptop does not prove production workloads have the same network path.

If the endpoint is a public API called by external clients, traffic can be steered via an API gateway, load balancer, or health-checked DNS. Lowering TTL before switching can help some clients update faster, but DNS caches in resolvers and applications may still hold old addresses. Keep the source active during the transition window and verify live connections after shifting routes.

## 5. Keeping business logic stable with per-provider adapters

Business code should not depend directly on S3, Azure Blob, or Google Cloud Storage client classes. Define a port based on business needs, then implement adapters per provider. The port should expose the operations the application actually needs, rather than trying to mimic every API across all clouds.

Example document storage port:

```java
public interface DocumentStorage {
    void upload(String key, InputStream content, long contentLength,
                Map<String, String> metadata);

    InputStream download(String key);

    void delete(String key);
}
```

Adapters such as `S3DocumentStorage`, `AzureBlobDocumentStorage`, and `GcsDocumentStorage` map operations onto their respective SDKs. Adapters also handle differences in metadata, pagination, retries, checksums, and provider errors. If a business flow needs a feature unique to one provider, surface that capability explicitly in the contract or a specialized port; never silently ignore attributes when switching providers.

Adapters can be selected via Spring configuration:

```java
@Configuration
class DocumentStorageConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "app.storage", name = "provider",
                           havingValue = "aws")
    DocumentStorage s3Storage(S3Client client) {
        return new S3DocumentStorage(client);
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.storage", name = "provider",
                           havingValue = "azure")
    DocumentStorage azureStorage(BlobServiceClient client) {
        return new AzureBlobDocumentStorage(client);
    }
}
```

This is an example of adapter wiring; clients must be configured with the starters/SDKs and credential chains suited to your project's Spring Boot, Spring Cloud, and provider library versions. The Google Cloud adapter can be registered using the same pattern. At runtime, the application receives only one implementation per port.

Keep configuration differences inside the integration layer. For example, the AWS adapter uses `S3Client`, the Azure adapter uses `BlobServiceClient`, and the Google Cloud adapter uses the Cloud Storage client. Never pass these types into controllers or business services. As a result, switching providers impacts mainly configuration, adapters, and data workflows.

Still, abstractions do not erase service differences. Spring Cloud helps integrate with provider ecosystems, but does not guarantee queues, storage, databases, or IAM behave identically. Write contract tests for the behaviors business logic depends on: object reads/writes, metadata, error handling, retries, access permissions, and idempotency.

## 6. Planning cutover and rollback

Cutover is the point when authoritative traffic shifts from source to target. A solid plan specifies owners, timing, go/no-go criteria, manual steps, and recovery procedures.

Reference workflow:

1. **Prepare the target:** provision resources, networks, roles, policies, secrets, endpoints, backups, and dashboards. Run smoke tests from the real workload.
2. **Initial data transfer:** copy objects, schemas, and database rows; retain manifests and verification outputs.
3. **Sync ongoing changes:** enable replication/CDC or incremental sync. Monitor lag and verify backlogs shrink below agreed thresholds.
4. **Pre-cutover testing:** run reconciliation queries, verify read/write permissions, process test messages, and confirm SLO metrics.
5. **Freeze writes or switch producers:** put the source in read-only mode, pause producers, or enforce write fences so two authoritative data sources cannot diverge.
6. **Final sync and verification:** transfer remaining deltas, compare counts, and confirm consumer and message states.
7. **Shift traffic:** update configuration, feature flags, gateways, or DNS according to plan; run canary deployments before full rollout.
8. **Observe:** watch authentication errors, latency, throughput, retries, DLQs, quotas, costs, and business metrics throughout the monitoring window.
9. **Close out migration:** decommission source resources only after the rollback window closes, backups are verified, and data owners sign off.

Define abort criteria before starting. For example: do not shift traffic if unexplained row-count discrepancies remain, replication lag exceeds thresholds, workloads cannot read secrets, or target consumers cause abnormal DLQ spikes. Criteria must align with real system data and SLOs.

Rollback is more than flipping DNS back. Once the target accepts writes after cutover, the source becomes stale. Before allowing writes on the target, decide how you would revert: keep the source read-only, configure reverse replication, replay from logs/outbox, or accept a sync downtime window. Without a way to preserve writes committed on the target, reverting to the source is not safe.

Avoid running active-active writes across two clouds for extended periods unless the application has an explicit conflict-resolution model. If parallel runs are needed for comparison, prefer shadow reads or mirrored requests that produce no business side effects. Any test write must carry idempotency keys and safeguards against duplicate side effects.

## 7. Post-migration operations

After cutover, keep dashboards and alerts covering both application and provider perspectives. A failing request may stem from application code, credentials, DNS, networking, quotas, or managed services. Logging only `AccessDenied` is insufficient for troubleshooting; include correlation IDs, operation names, provider, region, and resource type, while strictly excluding tokens and secrets.

Signals to monitor include:

- **Availability:** request success rates, errors by status code, health checks, and connection failures.
- **Latency:** p50/p95/p99 latency for storage, databases, brokers, and downstream APIs.
- **Throughput:** request counts, bytes transferred, messages sent/received, and consumer processing rates.
- **Data reliability:** replication lag, unreconciled records/objects, message retries, and DLQ depth.
- **Security:** authentication errors, authorization denials, role/policy changes, secret accesses, and key management activity.
- **Resources and cost:** quotas, throttling, connection pools, egress, request counts, storage volume, and cross-region transfer charges.

Set explicit client timeouts and use bounded retries with exponential backoff and jitter. Retry only transient failures; authentication or invalid data errors typically require configuration or business fixes. For write operations, guarantee idempotency before enabling retries. Circuit breakers and bulkheads can protect the rest of the application when managed services degrade, provided thresholds reflect observed latencies and SLOs.

Test backups by actually restoring them, not just checking backup job status. Runbooks must cover how to verify identity, inspect DNS/TLS, check quotas, handle DLQs, shift traffic, and restore data. After several days or a peak load cycle, compare actual billing against estimates—especially egress, request fees, replication, and version storage.

## 8. Example: migrating a document store from S3 to Azure Blob

Suppose a Spring Boot service stores customer documents on S3. The goal is to migrate to Azure Blob Storage while keeping the business `upload`, `download`, and `delete` APIs unchanged.

**Step 1 – Isolate the business contract.** Controllers and services call only `DocumentStorage`. The existing S3 adapter accesses the bucket. Add an Azure Blob adapter and run contract tests so both satisfy required behaviors.

**Step 2 – Provision target identity.** Attach a Managed Identity or Workload Identity to the workload on Azure. Grant appropriate data-plane roles scoped to the target storage account or container, such as blob read/write permissions matching the service's responsibilities. Configure the Azure SDK to use the runtime's credential chain; never put account keys in `application.yml`.

**Step 3 – Prepare endpoints.** Configure the Blob Storage account URL, container, region, and private endpoint if required by architecture. From the application pod or host, verify DNS, routing, TLS, and permissions with a test read/write against a test container.

**Step 4 – Migrate data.** Use an appropriate migration tool to copy objects from S3 to Blob. Save manifests containing keys, sizes, checksums, metadata, and status. Map ACLs, tags, versioning, retention, and encryption to target policies; document any attributes that cannot be migrated verbatim.

**Step 5 – Reconcile and cut over.** Compare object counts, total bytes, checksums, and critical metadata. Sync final deltas, freeze writes on S3, then switch `app.storage.provider` to `azure` via deployment configuration. Enable canary traffic and watch authentication errors, latency, retry counts, and business errors before shifting 100% of traffic.

**Step 6 – Preserve recovery options.** During the rollback window, keep S3 read-only and retain backups and manifests. If Azure has accepted new writes, have a plan to sync back or recover those changes before reverting. Delete source buckets only after data owner sign-off and retention rules permit.

This example shows that changes inside Spring Boot can stay focused on adapters and configuration, yet migration work still spans data, permissions, networking, verification, and operations. Skipping any of those areas may leave the application running without a truly safe migration.

## 9. Common errors and troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| Runs locally, fails with permission errors in cloud | Local credentials are overly broad; workload identity or role binding is misconfigured | Verify the workload's actual principal and policies on the target resource |
| Connection timeouts after switching endpoints | Misconfigured private DNS, routes, firewalls, or egress | Test DNS resolution and connectivity from the production runtime itself |
| Objects have exact bytes but missing metadata | Only content copied; metadata/tags/ACLs unmapped | Compare manifests and inspect attributes on the target provider |
| Database divergence after cutover | CDC lag, concurrent writes, or missed final sync | Check replication lag, write fences, and reconciliation counts |
| Messages processed multiple times | Broker redelivery or non-idempotent consumer | Enforce event IDs/idempotency keys and inspect ack/DLQ behavior |
| Rollback loses recent data | Target accepted writes without reverse sync to source | Define authoritative writer and post-cutover write preservation plan |
| Costs spike after migration | Egress, requests, replication, or retaining multiple versions | Break down billing by service, region, and workload |

## 10. Acceptance checklist

- [ ] Inventoried objects, databases, brokers, secrets, identities, endpoints, and operational dependencies.
- [ ] Defined RPO, RTO, cutover window, authoritative data source, and rollback criteria.
- [ ] Migrated data, synced deltas, and reconciled with verifiable counts/metrics.
- [ ] Mapped metadata, versions, retention, encryption, and dead-letter handling or recorded exceptions.
- [ ] Workloads use runtime identity, least privilege, and an appropriate secret manager.
- [ ] Endpoints, DNS, routing, TLS, timeouts, and quotas verified from the target deployment environment.
- [ ] Target provider adapters passed contract tests and required integration tests.
- [ ] Cutover includes write fences, canary rollout, dashboards, owners, and abort criteria.
- [ ] Rollback preserves data created after cutover.
- [ ] Backups, runbooks, alerts, and costs verified post-migration.

A multi-cloud migration succeeds when the application accesses the right data with the right identity, connects to the right endpoints, and operations teams can observe, troubleshoot, and recover the system. Spring Cloud libraries standardize integration within Spring Boot code; your data, permissions, and operations plan determines whether the migration is actually safe.
