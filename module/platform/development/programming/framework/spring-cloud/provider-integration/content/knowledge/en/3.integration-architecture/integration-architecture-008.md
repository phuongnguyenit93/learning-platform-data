# Limits of Portability Across Cloud Providers

A Spring Boot application can use the same interface to write objects to Amazon S3, Azure Blob Storage, or Google Cloud Storage. That makes swapping implementations possible without heavily rewriting business code, yet **it does not mean the three services share identical behavior**. They differ in resource models, conditional writes, versioning, consistency, identity, policies, request limits, retries, event delivery, transactions, observability, and pricing. An overly simple abstraction can hide differences a use case depends on; an overly broad abstraction produces optional parameters everywhere and inconsistent behavior.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries, from identity/permissions, storage, messaging, data, and secrets to integration testing. This lesson focuses on identifying **where portability genuinely lives, where its limits lie, and how to design for controlled provider switching**.

## 1. Learning Outcomes

After this lesson, you can:

- Distinguish portability at the levels of source code, APIs, semantics, data, security, operations, and cost.
- Explain why a shared interface does not guarantee equivalent cloud services.
- Compare object storage, messaging, and managed databases across AWS, Azure, and Google Cloud.
- Design a **common contract + provider capabilities** without turning interfaces into SDK clones.
- Choose among lowest common denominator, provider-specific extensions, and multiple intentional adapters.
- Plan contract tests, cloud tests, and migration rehearsals to uncover differences before cutting over production.

## 2. Portability Has Multiple Layers

When someone says “the app is portable,” clarify **portable at which layer**:

| Layer | How Portable Can It Be? | Example Limit |
| --- | --- | --- |
| **Business logic** | Usually remains intact if use-case contracts stay stable | Invoice issuance rules do not depend on buckets |
| **Application port** | Can share genuinely common semantics | `DocumentStore.put` does not automatically express versioning or create-if-absent |
| **Framework/API** | Can use Spring abstractions if provider integrations support them | Templates/listeners/properties vary across Spring Cloud families |
| **Service semantics** | Often only partially equivalent | S3 version ID, Blob ETag, and GCS generation cannot be swapped mechanically |
| **Identity and authorization** | Only target principles and policies can be unified | IAM roles, Azure Managed Identity/RBAC, and Google ADC/IAM follow different models |
| **Network and deployment** | Some parts shared; topology remains provider-specific | PrivateLink, Private Endpoint, Private Service Connect, and DNS differ |
| **Reliability and operations** | Goals can be standardized; execution differs | Queue visibility, locks, ack deadlines, DLQs, and quotas |
| **Cost and performance** | Cannot be inferred from matching APIs | Request pricing, egress, retrieval tiers, replication, and throughput differ |

~~~mermaid
flowchart TD
    A[Business use case] --> B[Portable application contract]
    B --> C[Provider adapter]
    C --> D[AWS service]
    C --> E[Azure service]
    C --> F[Google Cloud service]
    D --> G[Provider-specific semantics]
    E --> G
    F --> G
    G --> H[Identity / network / reliability / cost]
~~~

The **practical goal** is usually keeping business logic and core contracts stable while isolating differences in adapters, configuration, and deployment. Not every difference is worth abstracting away; some differences should be preserved as explicit capabilities.

## 3. Why the Same Method Does Not Guarantee the Same Behavior

Suppose all three adapters implement:

~~~java
public interface DocumentStore {
    void put(String key, byte[] content, String contentType);
}
~~~

This signature only specifies inputs and when the method returns. It **does not state**:

- If the object already exists, does it overwrite, create a new version, or return a conflict?
- On timeout, might the object already have been stored?
- When the method returns, is the data immediately readable from every location?
- What limits apply to content type and metadata?
- Which version ID, generation, or ETag is returned?
- Are range reads, streaming, or resumable uploads supported?
- Where are encryption keys, retention, legal holds, and lifecycle rules configured?
- Which identity is used, which permissions are checked, and which network path does traffic take?

An interface can make adapters **callable the same way**, yet it does not prove those questions have the same answers. If the application relies on a guarantee the port never specifies, the code implicitly depends on provider behavior.

## 4. Object Storage: S3, Azure Blob, and Cloud Storage

### 4.1. Resource and Operation Models

| Concept | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Resource holding objects | Bucket | Storage account and container | Bucket |
| Object | Object/key | Blob name in container | Object name |
| Typical Java client | AWS SDK v2 `S3Client` / `S3AsyncClient` | Azure SDK `BlobServiceClient`, `BlobContainerClient`, `BlobClient` | Google Cloud Java `Storage` |
| Writing data | `PutObject`, multipart API | Block/blob upload APIs | `Storage.create`, writer/resumable API |
| Versioning/concurrency | Versioning, conditional requests, and API-level ETags | Blob versioning, ETag/access conditions | Object versioning and generation/metageneration preconditions |
| Common identity | IAM role/credential chain | Managed Identity/DefaultAzureCredential + RBAC | ADC/workload identity/service account + IAM |

These names represent typical APIs and concepts; exact configuration and capabilities depend on accounts, APIs, SDKs, and versions. For example, S3 **bucket/key**, Azure **account/container/blob**, and GCS **bucket/object** can map from one application **object key**, yet each adapter must still know the matching resource locator.

### 4.2. Versioning and Conditional Writes Are Not Uniform

Providers have concurrency-protection mechanisms, yet they should not be collapsed into one generic field:

- **Amazon S3:** versioning can generate version IDs; APIs support conditional requests where applicable, such as existence/ETag preconditions on supported operations.
- **Azure Blob:** ETags and access conditions enable conditional updates; Blob versioning is a separate feature.
- **Google Cloud Storage:** generation and metageneration preconditions prevent overwrites when the generation no longer matches; object versioning has its own semantics.

**ETag is not inherently a content checksum** and is not equivalent across providers. Multipart uploads, encryption, and API implementation details change its meaning. Version ID, generation, and ETag are also not the same type of identifier.

If business logic requires “create the document only if it does not already exist,” define the port around **create-if-absent** and use the appropriate atomic precondition in each adapter. Avoid separate **HEAD → PUT** patterns: two concurrent requests can both observe the object missing and both write. Contract tests must exercise race scenarios to verify the guarantee.

### 4.3. Consistency and Read-After-Write Behavior

Do not infer consistency from the method name `put`. Read service and API documentation for your exact usage: immediate reads after writes, prefix listings, metadata/version reads, concurrent writes, and multi-region replication. A system switching providers can break if it previously relied on list-operation ordering or visibility timing.

Safer design practices:

- Use a stable object key/operation ID to locate data.
- If immediate read-after-write is required, test against the real read-after-write API and actual network/replication path.
- Never use prefix listing as the single source of truth for business state; store state metadata in a database when consistent business queries are required.
- For concurrent updates, define versions/preconditions and handle conflicts rather than relying on an unspecified “last write wins.”

### 4.4. Large Uploads, Streaming, and Limits

A generic `put(byte[])` method fits only small, bounded payloads. Services provide dedicated APIs for multipart, block, or resumable uploads; they differ in:

- Maximum sizes, part counts, part sizes, and request limits.
- How upload sessions are initiated, completed, or aborted.
- Retrying individual chunks and recovering after process restarts.
- Checksums, metadata, write conditions, and resumability.
- How the SDK manages buffers, threads, connections, and backpressure.

If business logic only uploads small files, a simple port can suffice. If resume or streaming is required, define an appropriate **upload session/stream contract** or expose a dedicated capability. Do not force multipart and resumable uploads into a `byte[]` method that buffers entire files on the heap.

### 4.5. Metadata, Encryption, Retention, and Lifecycles

All providers support metadata and encryption, yet configurations differ:

| Requirement | What to Compare |
| --- | --- |
| Metadata | User metadata, HTTP headers, custom metadata, size limits, and character rules |
| Encryption at rest | Provider-managed keys, customer-managed keys, key rotation, and key usage permissions |
| Retention/legal hold | Object locks, immutability policies, retention durations, and deletion rules |
| Lifecycle/tiering | Tier transition rules, archive/retrieval, expiration, and restore fees |
| Replication | Regional scope, propagation time, permissions, and egress costs |
| Signed URLs | Signing mechanism, authorized signing identities, expiration, and request constraints |

A shared interface should only carry options with clear semantics that can be verified across all supported providers. If legal hold is mandatory and an adapter cannot guarantee it, never silently ignore the setting; reject the configuration or explicitly represent the capability as unsupported.

## 5. Messaging: Same “Send Message” Idea, Different Semantics

| Aspect | Amazon SQS/SNS | Azure Service Bus | Google Cloud Pub/Sub |
| --- | --- | --- | --- |
| Common model | Queues, topics, and subscriptions depending on service | Queues, topics/subscriptions | Topics and subscriptions |
| Consumer | Receive/delete, visibility timeout | Receive/settle, lock duration | Pull/push, ack deadline |
| Delivery | Redelivery possible; design idempotently | Locks, abandon/dead-letter, and redelivery | Ack deadline, redelivery, and dead-letter policies |
| Ordering/dedup | FIFO queues with dedicated features | Sessions and tier-dependent features | Ordering keys and config-dependent features |
| Retry/dead-letter | Redrive policy/DLQ | Dead-letter queue | Retries and dead-letter topic/policy |
| Typical Java API | `SqsClient`, `SqsAsyncClient`, Spring Cloud AWS listener/template | Azure Service Bus client/processor and Spring Cloud Azure integration | Publisher/Subscriber, `ApiFuture`, Spring Cloud GCP integration |

These semantics cannot be normalized behind a single **send(String queue, Object payload)** method. Determine:

- When publish returns success, did the broker accept the message or did a consumer process it?
- When does the consumer ack? If the handler is async, does the listener truly wait for completion?
- When a message is redelivered, how does the application handle duplicates?
- Over what scope is ordering required: entire queue, session, partition, or ordering key?
- How many times are poison messages retried, and where do they go?
- Are message attributes, size limits, schemas, delays, and scheduling equivalent?

A publisher port can standardize the “broker accepted the event” contract and a stable event ID. Consumer adapters must preserve the broker's ack/lock semantics; application handlers must be idempotent. If a use case requires session ordering or FIFO deduplication, model that capability explicitly instead of assuming every broker supports it identically.

**Transactional outbox** helps write business state and an event record in the same database transaction, after which a publisher worker forwards it to the broker. It does not create a distributed transaction between database and queue, nor does it guarantee the broker/consumer never redelivers; event IDs and idempotency remain necessary.

## 6. Managed Databases: Shared Repositories Have Limits

### 6.1. Protocol-Compatible Databases vs. Provider-Specific Datastores

With managed PostgreSQL on **Amazon RDS**, **Azure Database for PostgreSQL**, or **Google Cloud SQL**, applications can often keep the same JDBC driver, Spring Data JPA/JDBC, and migrations if engine versions/features are compatible. Still, you must configure separately:

- Endpoints, TLS, private network access, and DNS.
- Connection pools, failover, timeouts, and retries.
- Authentication via password, IAM/database identity, or provider-specific mechanisms.
- Engine versions, extensions, collations, parameter groups/flags, and migrations.
- Backups, point-in-time recovery, replicas, failover, and maintenance windows.

With **DynamoDB**, **Azure Cosmos DB**, **Firestore**, or **Spanner**, query models, partition keys, transactions, consistency, and indexing differ. A `Repository.save/findById` interface may compile everywhere while performing and behaving very differently. For instance, full-collection scans, scoped transaction limits, or poorly chosen partition keys can sharply increase cost and latency after migration.

### 6.2. Do Not Assume Transactions Are Identical

JPA/JDBC transactions typically bind to a database connection/engine. NoSQL transactions may be scoped to a document, partition, entity group, or operation count. Never put `@Transactional` on a service and assume object storage, message brokers, and any managed database all roll back together when one step fails.

When migrating databases:

1. Inventory queries, indexes, unique constraints, isolation levels, and active transactions.
2. Verify data types, time zones, numeric precision, collations, and encoding.
3. Test race conditions and concurrent updates.
4. Run migrations/reconciliation on a representative dataset copy.
5. Measure query plans, latency, throughput, and cost under realistic workloads.

## 7. Identity, Authorization, and Networking Are Not Portable by Config Alone

The three platforms grant identity and permissions differently:

| Topic | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Common runtime identity | IAM role, credential chain, workload identity | Managed Identity, service principal, or Azure credential chain | ADC, service account, Workload Identity Federation |
| Authorization | IAM policies, resource policies, bucket/queue policies | Azure RBAC, resource/data-plane roles and policies | Project/resource-level IAM roles/bindings |
| Scope | Principal, action, resource, condition | Principal, role, scope, and data actions | Principal, role, resource hierarchy |
| Private networking | PrivateLink/VPC endpoints and VPC networking | Private Endpoint/VNet/DNS | Private Service Connect/VPC/DNS |
| Secrets/keys | Secrets Manager, KMS | Key Vault, Key Vault Managed HSM | Secret Manager, Cloud KMS |

No port can turn three policy languages into one. You can standardize **permission intent** at the application level (such as “this workload writes only documents belonging to this service”) and implement provider-specific policies accordingly. Verify both service permissions and encryption-key permissions; an object write can still fail if key access is missing.

Keep two decisions separate:

- **Business authorization:** is the caller allowed to view/create the document or issue the invoice? Check in the application/security boundary.
- **Workload authorization:** is the application's service account/role allowed to access the bucket, queue, database, or secret? Check in IAM/RBAC and infrastructure configuration.

When switching clouds, verify DNS, TLS, outbound rules, proxies, private endpoints, certificate trust, egress, and endpoint resolution. A similarly named endpoint setting in YAML does not guarantee identical network topology or trust boundaries.

## 8. Reliability, Retries, and Indeterminate Outcomes

An operation can fail before sending the request, be rejected by the service, or execute while the response is lost. Providers return different error codes and retry guidance. Adapters must classify by **meaning**, not just compare status codes.

| Error Group | Application Behavior to Consider |
| --- | --- |
| Invalid input | Do not retry; return validation error |
| Workload lacks permissions | Do not retry endlessly; fix identity/policy |
| Resource not found | Check names, project/account, region, and provisioning |
| Conflict/precondition | Read state/version or handle business conflict |
| Throttling/quota/transient service error | Retry with backoff, jitter, deadline, and concurrency bounds |
| Timeout after side effect | **Outcome unknown**; reconcile before retrying if needed |

For object storage, a stable key directs retries to the same resource, yet does not by itself prevent overwrites or enforce create-once. For messaging, the broker may have received the event even if the producer lost the response; consumers must deduplicate by event ID. For databases, retrying a transaction may re-run business logic or hit unique constraints differently than the first attempt.

Do not let retries in the SDK, Spring Retry, Reactor, and brokers multiply uncontrollably. Define an overall **retry budget**, timeout budget, retryable error classes, and idempotency rules. When changing providers, run fault-injection tests to verify real error codes and actual request counts sent.

## 9. Capability Model: Share What Is Common, Expose What Differs

A minimal port can fit simple use cases:

~~~java
public interface DocumentStore {
    StoredDocument put(DocumentWrite request);
    Optional<DocumentContent> get(String objectKey);
}
~~~

However, if use cases need create-without-overwrite, returned versions, signed URLs, or multipart sessions, do not pile nullable parameters onto a single method. Represent distinct **capabilities** separately:

~~~java
public interface ConditionalDocumentStore {
    StoredDocument createIfAbsent(DocumentWrite request);
}

public interface VersionedDocumentStore {
    StoredDocument putNewVersion(DocumentWrite request);
}

public interface TemporaryDownloadLinkProvider {
    URI createReadLink(String objectKey, Duration validFor);
}
~~~

These are design examples; not every provider supports every capability with identical guarantees. At adapter startup, the application can:

- Select implementations satisfying required capabilities and **fail fast** if missing.
- Use the core interface for portable use cases and dedicated capability interfaces for specialized ones.
- Return an explicit capability outcome if the application intentionally accepts a fallback.

Avoid `instanceof S3DocumentStore` checks in application services or exposing provider names to business logic. Capabilities should be resolved in wiring/configuration or at application boundaries; adapters invoke provider-specific APIs.

### 9.1. Lowest Common Denominator Can Be Too Low

Keeping only the intersection across services aids portability, yet can strip vital features: versioning, conditional writes, ordered messaging, transactions, retention, queries, or identity. When use cases genuinely require those features, there are three options:

1. **Accept the shared limit:** design the business process around the lowest common guarantee that still meets requirements.
2. **Named capabilities:** the use case requires a capability and deploys only on providers supporting it; incompatible deployments fail fast.
3. **Provider-specific workflows:** keep part of the use case/adapter separate when semantic differences are too wide to hide behind a common interface.

Never claim “multi-cloud” if the app can only run on one provider without capability checks. Nor should you discard valuable features solely to keep an identical interface on paper.

## 10. Example: Choosing a Contract for Object Storage

Suppose the requirement is **saving a new document without overwriting an existing one**. The contract must express an atomic condition:

~~~java
public interface ImmutableDocumentStore {
    StoredDocument createIfAbsent(DocumentWrite request)
        throws DocumentAlreadyExistsException;
}
~~~

The AWS adapter can use conditional writes matching the S3 API and current bucket/versioning setup; the Azure adapter uses appropriate access conditions/ETags; the GCS adapter uses generation preconditions. Each adapter must verify how its SDK expresses the condition, conflict error types, and timeouts after writes. If an API/provider setup cannot satisfy the contract, never fall back to a non-atomic check sequence and still claim “created uniquely.”

The return type should carry only information the application truly needs:

~~~java
public record StoredDocument(
    String objectKey,
    Optional<String> providerVersion
) {}
~~~

Use `providerVersion` only if the application treats it as an **opaque token** passed back to the same adapter that created it. If cross-provider version comparison/semantics are needed, define an application-managed **application revision** rather than assuming S3 version IDs, Azure version IDs, and GCS generations can be compared directly.

## 11. Migration Is a Data and Operations Problem, Not Just Swapping Adapters

A plan to move from S3 to Azure Blob or GCS must consider at least:

1. **Inventory:** bucket/container/object counts, total volume, object sizes, metadata, versions, retention, lifecycles, encryption, access logs, and traffic patterns.
2. **Mapping:** bucket/key → account/container/blob or project/bucket/object; metadata, content types, custom headers, tags, and version semantics.
3. **Identity/network:** new workload identity, IAM/RBAC, key permissions, private endpoints, DNS, TLS, and egress.
4. **Data movement:** copy tooling, throughput, checksums, retries, version/metadata preservation, egress fees, and delta-sync windows.
5. **Application:** adapters, configuration, timeouts, retries, streaming, signed URLs, error mapping, and capability checks.
6. **Verification:** object counts, checksums/sizes, metadata, read/write permissions, conditional writes, and critical use cases.
7. **Cutover:** write freeze or controlled dual-write, routing, rollback, and handling data written during the transition window.
8. **Retirement:** delete the source only once reconciliation, retention, backups, audits, and rollback windows satisfy criteria.

~~~mermaid
flowchart TD
    A[Source inventory] --> B[Map semantics + capabilities]
    B --> C[Copy data / sync deltas]
    C --> D[Verify checksums + metadata + permissions]
    D --> E{Smoke and business tests pass?}
    E -->|No| F[Keep source, fix mapping or rollback]
    F --> C
    E -->|Yes| G[Controlled traffic cutover]
    G --> H[Monitor and preserve rollback window]
    H --> I[Retire source per policy]
~~~

**Dual-write** can cause data divergence if one provider succeeds and the other fails. If used, you need operation IDs, per-target states, retry/reconciliation, and rules establishing the source of truth. Never simply add two adapters and call both inside one method without a compensating workflow.

## 12. Testing Portability with Contracts and Provider Matrices

A shared test suite can verify the **DocumentStore** contract, while each adapter needs additional tests for provider-specific semantics:

| Test Group | Shared Contract | Provider-Specific |
| --- | --- | --- |
| Put/get | Accurate content, content type, and key | Metadata/header limits, encoding, checksums |
| Create-if-absent | Does not overwrite when object exists | S3 conditional requests, Blob access conditions, GCS generation preconditions |
| Versioning | Application receives valid revisions | Version ID, Blob version, generation semantics |
| Concurrent writes | Conflicts detected per contract | Race conditions and real error codes |
| Timeouts | Does not report false success when outcome unknown | SDK retries, request IDs, service behavior |
| Authorization | Workload lacking permissions cannot write | IAM policies, Azure RBAC, Google IAM |
| Large objects | Stays within memory budget | Multipart/block/resumable uploads |
| Delete/retention | Rejects deletes when business policy forbids | Object lock, immutability, retention, and lifecycles |

Testing should cover three levels:

- **Unit tests:** application services using fake ports, needing no cloud credentials.
- **Adapter/contract tests:** mocked SDKs to verify mapping and errors; emulators (LocalStack, Azurite, or suitable GCP environments) for integration flows.
- **Real cloud tests:** identity, policies, networking, quotas, conditional writes, retention, failover, and semantics emulators do not adequately simulate.

Do not merely run one test suite and count “passes” across three clouds. Maintain a **capability × provider × version × configuration** matrix; mark a capability supported only if the real target deployment satisfies its guarantees. Any unsupported capability must be explicitly documented and fail fast when required by a use case.

## 13. Performance and Cost Trade-Offs

A portable adapter can increase API call counts if it must check state before/after operations. Proxying files through the application instead of direct uploads raises bandwidth and compute costs. Switching providers can also alter:

- **Request pricing:** PUT/GET/LIST, transactions, batch operations, message publish/receive/ack.
- **Storage pricing:** hot/cool/archive tiers, minimum storage durations, and retrieval fees.
- **Network pricing:** egress, cross-region traffic, private connectivity, interconnects, and NAT traffic.
- **Performance:** regional latency, throughput, request rates, partition/hot keys, connection pools, and concurrency.
- **Operations:** backups, replication, monitoring, key management, log retention, and support plans.

You cannot conclude one provider is cheaper from per-GB storage rates or a local benchmark alone. Model a representative workload: object sizes, read/write ratios, concurrency, list/query frequency, retention, regions, and egress volume. Measure **p50/p95/p99 latency**, error/throttling rates, per-operation cost, and data migration cost.

## 14. Anti-Patterns That Hurt Portability

| Anti-Pattern | Why It Is Risky | Better Alternative |
| --- | --- | --- |
| `CloudStorage` interface with dozens of nullable parameters | Vague contract; each adapter ignores different fields | Use-case ports + explicit capabilities |
| Shared method names with differing semantics | Methods report success with mismatched guarantees | Define preconditions, versions, acks, and outcomes |
| Exposing SDK requests/exceptions to application logic | Business layer depends on provider | Map in adapter, retain root causes internally |
| Testing only with mocks | Misses IAM, networking, quotas, consistency, and API behavior | Emulators + cloud smoke/contract tests |
| Hard-coding buckets/accounts/projects in business services | Code must change per environment/provider | Configuration and adapters own resource mapping |
| Treating every 403 as a caller error | Workload identity may lack permissions | Separate business authorization from cloud authorization |
| Dual-write without reconciliation | Two providers can diverge in data | Operation states, outbox/reconciliation, controlled cutover |
| Picking lowest common denominator regardless of requirements | Loses needed features or weakens guarantees | Named capabilities and startup support checks |
| Comparing APIs alone while ignoring cost/networking | Migration runs yet violates SLA/budget | Workload benchmarks and regional/tier TCO |

## 15. Decision Checklist for a Use Case

Before picking an adapter or committing to multi-cloud support, document:

1. **Business outcome:** what do users need, and what invariants must always hold?
2. **Required semantics:** create/update, versioning, consistency, ordering, acks, transactions, retention, and idempotency.
3. **Required capabilities:** mandatory features vs. optional ones.
4. **Provider mapping:** APIs, identities, policies, networking, limits, and error mappings per cloud.
5. **Failure model:** timeouts before/after side effects, retries, conflicts, quotas, and reconciliation.
6. **Operational model:** metrics, logs, traces, alerts, backups, restores, and shutdown.
7. **Cost/performance:** workload benchmarks, egress, requests, storage tiers, and migration costs.
8. **Test evidence:** contracts, emulators, cloud smoke tests, and migration rehearsals.

Only after completing this matrix should you claim a use case is **portable across AWS, Azure, and Google Cloud**. If a provider only supports a subset, reflect that in deployment/capability configuration and fail startup when configuration requires capabilities the adapter cannot provide.

## 16. Hands-On Exercises

**Exercise 1 — Object storage portability.** An application needs PDF uploads, range downloads, versioning, and no overwrites. Build an S3/Blob/GCS matrix for each requirement. Indicate what fits in `DocumentStore`, what requires separate capabilities, and what must remain provider-specific.

**Exercise 2 — Messaging semantics.** A payment-processing consumer must apply business effects only once per event ID. Compare SQS visibility timeouts, Service Bus locks, and Pub/Sub ack deadlines. Design database-backed idempotency and a dead-letter workflow; explain why a `receive/ack` interface does not automatically guarantee exactly-once processing.

**Exercise 3 — Managed databases.** An app using PostgreSQL on RDS plans to move to Cloud SQL. List what stays unchanged (JDBC/JPA, entities, repositories) and what must be checked (extensions, versions, networking, IAM auth, TLS, pools, failover, backups, parameter settings).

**Exercise 4 — Conditional creation.** Two instances write the same object key concurrently. Design a `createIfAbsent` contract and precondition mappings for S3, Azure Blob, and GCS. Write a concurrency test confirming only one operation succeeds.

**Exercise 5 — Capability checks.** An application requires signed URLs and retention locks. Design capability interfaces, express which adapters satisfy them in deployment config, and define startup behavior if the selected provider lacks a mandatory capability.

**Exercise 6 — Migration rehearsal.** Plan migrating 10 TB of objects from S3 to Azure Blob or GCS. Include inventory, copying, checksums, metadata/version mapping, dual-write or write freeze, cutover, rollback, egress costs, and criteria for retiring the source.

**Exercise 7 — Evaluating portability claims.** A team claims “just swap the Spring Cloud starter and it runs on all three clouds.” Demand evidence across APIs, semantics, IAM/RBAC, networking, reliability, observability, performance, cost, and integration tests before accepting the claim.

## 17. Key Takeaways

- **Portability is not binary.** Business logic and parts of application contracts can be shared, while service semantics, identity, networking, reliability, and cost remain distinct.
- **Matching method signatures do not guarantee matching semantics.** Versioning, conditional writes, consistency, streaming, message acks, and transactions must be specified and tested explicitly.
- Use **common contracts** for genuinely shared needs; use **capabilities** or provider-specific workflows for specialized features. Never force every cloud into an overly broad or overly weak interface.
- **Identity, IAM/RBAC, networking, retries, and observability** must be configured and verified per provider; never confuse workload permissions with end-user permissions.
- Migration requires inventory, mapping, copying, reconciliation, smoke tests, cutover, and rollback. **Swapping an adapter does not migrate data or policies.**
- Commit to portability only when backed by **contract tests + cloud tests + workload/cost evidence** on the actual target providers and versions.
