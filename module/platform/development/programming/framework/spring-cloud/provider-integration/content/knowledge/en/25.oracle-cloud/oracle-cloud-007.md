# Distinguishing OCI Queue, Streaming, and Notifications

OCI Queue, OCI Streaming, and OCI Notifications all receive or deliver messages, yet they solve three different problems. Queue distributes work items to workers; Streaming ingests and delivers records by partition/cursor for consumer processing and replay; Notifications broadcasts messages from a topic to multiple subscriptions. Picking the wrong service usually leads to flawed designs around ownership, acknowledgment, checkpointing, ordering, replay, and failure recovery.

Spring Cloud OCI provides service-specific starters for Queue, Streaming, and Notifications, exposing separate bean APIs: `Queue`, `Streaming`, and `Notification`. Those abstractions do not make the three services equivalent: the application must still adhere to each backend's semantics. This lesson focuses on distinguishing these three services by workload, message lifecycle, delivery model, and how to write producers/consumers; other OCI starters are included as comparison examples when choosing APIs.

This lesson presents a workload-driven selection process, compares Queue/Streaming/Notifications in depth, and designs boundaries across Spring APIs, the OCI SDK, database transactions, and managed services. The content belongs to the Oracle Cloud chapter of the `SPRING_CLOUD_PROVIDER_INTEGRATION` module, where learners practice integrating Spring Boot with storage, messaging, data, secrets, and cloud-provider managed services.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish the purpose and message lifecycle of OCI Queue, OCI Streaming, and OCI Notifications.
2. Choose a service based on work distribution, event ingestion/replay, or pub/sub fan-out.
3. Choose the right Spring Cloud OCI starter and `Queue`, `Streaming`, or `Notification` bean API.
4. Design message identity, delivery, settlement, cursors, checkpoints, and retries suited to each service.
5. Distinguish these three OCI services from Oracle TxEventQ and the Spring Cloud Stream binder.
6. Evaluate ordering, retention, consumer progress, fan-out, and failure recovery.
7. Define transaction boundaries, retries, idempotency, and consistency when combining messaging with a database.
8. Design authentication, IAM policies, regions, and compartments by producer/consumer.
9. Evaluate throughput, latency, partitioning, payload size, and operational cost.
10. Test redelivery, replay, subscription delivery, and failure scenarios.
11. Recognize when Oracle TxEventQ or another OCI service is a better fit.
12. Place provider-specific APIs behind an adapter boundary so domain logic stays independent of OCI-specific types.

## 2. Start from the Workload, Not the Service Catalog

A workload describes what work the application must perform, its frequency, its data, and its operational requirements. Even a single phrase like "send a notification" can demand a different service depending on recipients, reliability, and timing.

Examples:

- Storing invoice PDFs: needs object storage, object-key access, metadata, retention, and download.
- Storing database passwords: needs a secret manager, IAM permissions, rotation, and caching.
- Background order processing: needs a queue for work-item distribution, retries, and dead-letter handling.
- High-volume audit event collection: needs a stream, partition keys, cursors, and replay.
- Broadcasting alerts to multiple subscribers: needs pub/sub notifications.
- Sending transactional emails: needs mail protocols and SMTP credentials.
- Running image processing tasks: needs function invocation or a queue-triggered worker.
- Managing a database instance: needs a control-plane API.
- Executing business queries: needs a `DataSource`, connection pool, and transactions.
- Accessing JSON/key-value data: needs a NoSQL repository or suitable API.

### 2.1. Four Service-Selection Questions

**1. What is the workload doing?**

Storing objects, holding secrets, distributing tasks, ingesting events, broadcasting alerts, sending email, writing logs, invoking functions, or querying data?

**2. Which programming model does the workload need?**

- Spring `Resource`/`WritableResource`.
- `Storage`/`Queue`/`Streaming` service beans.
- Spring `MailSender`/`JavaMailSender`.
- Spring Data repository.
- Spring Cloud Stream function bindings.
- OCI SDK/client API.
- Control-plane operations.

**3. What semantics does the workload require?**

- Request/response vs. asynchronous.
- Work items vs. event streams.
- Fan-out vs. single-worker processing.
- Transactional vs. eventual consistency.
- Are ordering, replay, retention, deduplication, or checkpoints needed?

**4. Who operates and authorizes it?**

- Which workload identity calls the API?
- Which region/compartment holds the resource?
- Which IAM policies are granted?
- Who creates the resource vs. who uses the resource?
- Who owns retries, retention, backups, and alerting?

Never choose a service simply because its API is easy to call. Choose based on the semantics the system must guarantee.

## 3. Map of Spring Cloud OCI Starters

The Spring Cloud OCI 2.0.4 catalog provides the following starters:

| Workload / Capability | Starter | Primary API or Abstraction |
| --- | --- | --- |
| Store files/objects | `spring-cloud-oci-starter-storage` | `Storage`, Spring `Resource`, `WritableResource` |
| Secrets/sensitive config | `spring-cloud-oci-starter-vault` | Spring property source, `VaultTemplate` |
| Work-item queue | `spring-cloud-oci-starter-queue` | `Queue` |
| Event/data stream | `spring-cloud-oci-starter-streaming` | `Streaming` |
| Pub/sub notification | `spring-cloud-oci-starter-notification` | `Notification` |
| Application/service logs | `spring-cloud-oci-starter-logging` | `LogService` |
| Transactional email | `spring-cloud-oci-starter-email` | `MailSender`, `JavaMailSender` |
| Function invocation | `spring-cloud-oci-starter-function` | `Function` |
| Autonomous Database management | `spring-cloud-oci-starter-adb` | `AutonomousDb` |
| NoSQL data | `spring-cloud-oci-starter-nosql` | `NosqlDBConfig`, `NosqlRepository` |
| Generative AI | `spring-cloud-oci-starter-gen-ai` | `ChatModel`, `EmbeddingModel` |

Alongside service starters, the core starter provides OCI authentication and shared infrastructure. Service starters normally pull in the required core dependency; inspect the dependency graph before declaring core separately.

The table above maps Spring Cloud OCI integrations. Oracle AI Database starters and the TxEventQ binder belong to other branches in the Spring Cloud Oracle ecosystem and are contrasted in the messaging and database sections below.

## 4. Choose Spring APIs or the Direct OCI SDK?

A service starter may expose Spring abstractions, specialized beans, or APIs close to the OCI SDK. Choose the API layer according to the level of control the application needs.

| API Layer | When It Fits | Examples |
| --- | --- | --- |
| Spring abstraction | Business code manipulates resources via standard contracts | `Resource`, `WritableResource`, `MailSender` |
| Starter service bean | Need OCI-specific operations with auto-configuration | `Storage`, `Queue`, `Streaming`, `VaultTemplate` |
| Spring Data abstraction | Need repository/query access by data model | `NosqlRepository` |
| Spring Cloud Stream | Need `Supplier`/`Function`/`Consumer` and bindings | TxEventQ binder |
| Direct OCI SDK | Starter lacks a needed operation or requires newer/deep APIs | OCI Java SDK clients |

### 4.1. Place Provider APIs at the Adapter Boundary

Domain services should speak in business concepts such as `InvoiceArchive`, `SecretProvider`, `OrderPublisher`, or `NotificationSender`. Only the adapter depends on `Storage`, `Queue`, `VaultTemplate`, or the OCI SDK.

Example:

~~~java
public interface InvoiceFileStore {
    String save(String invoiceId, InputStream content, String contentType);
    InputStream open(String objectKey);
}
~~~

An OCI adapter implements this interface using the `Storage` API or Spring `Resource`. The domain does not need to know namespaces, bucket endpoints, OCI response classes, or SDK request builders.

### 4.2. When to Use Spring `Resource`?

Use `Resource` when reading/writing files is part of a stream flow and code expects a Spring abstraction. Use `Storage` when you need explicit bucket/object operations, metadata, or OCI-specific operations.

Do not force every operation through `Resource` when the business needs conditional writes, metadata, or bucket lifecycles. `Resource` is a content-access abstraction, not the full Object Storage contract.

### 4.3. When to Use the OCI SDK Directly?

Use the SDK directly when:

- The starter does not expose a required operation.
- You need a specific OCI API option.
- You need fine-grained request/response control.
- You need a capability newer than the starter wrapper version.
- You need to optimize a specialized flow after profiling.

If using the SDK directly, reuse the application's authentication provider, region, retry/timeout policies, and client lifecycle. Never instantiate a new client per request.

## 5. Object Storage: Choosing `Storage` API vs. `Resource`

OCI Object Storage stores data as objects inside buckets. The Spring Cloud OCI starter auto-configures a `Storage` bean for bucket/object operations and integrates objects with Spring `Resource`.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
</dependency>
~~~

### 5.1. Using the `Storage` API

Use `Storage` when you need explicit operations on buckets, objects, metadata, or service features.

Example using the starter API:

~~~java
@Service
public class InvoiceObjectService {

    private final Storage storage;

    public InvoiceObjectService(Storage storage) {
        this.storage = storage;
    }

    public void upload(
            String bucketName,
            String objectName,
            InputStream content) {

        storage.upload(
                bucketName,
                objectName,
                content,
                StorageObjectMetadata.builder()
                        .contentType("application/pdf")
                        .build());
    }
}
~~~

This snippet illustrates an upload. Verify `InputStream` ownership/closing contracts per the specific API and close application-opened streams via `try-with-resources`.

### 5.2. Using Spring `Resource`

An Object Storage resource can be resolved by URI matching the Object Storage endpoint. Example:

~~~java
Resource resource = applicationContext.getResource(
    "https://objectstorage.REGION.oraclecloud.com/n/NAMESPACE/b/BUCKET/o/OBJECT_KEY"
);

try (InputStream input = resource.getInputStream()) {
    // Stream object contents
}
~~~

Object Storage resources also implement `WritableResource`. When writing via `getOutputStream()`, content is uploaded when the stream closes:

~~~java
WritableResource target = (WritableResource) applicationContext.getResource(
    "https://objectstorage.REGION.oraclecloud.com/n/NAMESPACE/b/BUCKET/o/OBJECT_KEY"
);

try (OutputStream output = target.getOutputStream()) {
    output.write(pdfBytes);
}
~~~

The URI only locates the object via the resource abstraction. Do not treat that URI as a public URL or credential. Read/write permissions are still enforced via OCI identity/IAM.

### 5.3. Choosing Between the Two

| Need | Choice |
| --- | --- |
| Read file content in Spring APIs accepting `Resource` | `Resource` |
| Write streams from Spring APIs | `WritableResource` |
| Upload with explicit metadata | `Storage` |
| Create buckets or perform bucket/object operations | `Storage` |
| Control OCI-specific operations | `Storage` or SDK |
| Need only an internal file abstraction | Application interface + OCI adapter |

### 5.4. Designing Object Keys and Uploads

- Use stable object keys tied to business IDs/versions.
- Define overwrite and conditional write policies.
- Set content type, metadata, and encryption as required.
- Stream large files instead of always reading everything onto the heap.
- Design multipart uploads and cleanup for large uploads.
- Do not assume object storage has filesystem directories, renames, or locking.
- Use checksums/ETags/version metadata to verify results.
- Handle timeouts as unknown outcomes: the object may already have been written even if the client missed the response.

### 5.5. When Not to Use Object Storage

Do not use Object Storage instead of a database for records requiring multi-attribute queries/updates or relational transactions. Do not use Vault instead of Object Storage for large files. If you need key-value or per-record JSON queries, consider a database or NoSQL.

## 6. Vault: Choosing Property Source vs. `VaultTemplate`

OCI Vault stores secrets and manages versions. The Spring Cloud OCI Vault starter has two primary integration modes:

- Property source: loads secrets into the Spring `Environment` by secret name.
- `VaultTemplate`: reads or manages secrets via a bean API.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
</dependency>
~~~

### 6.1. Property Source for Startup Configuration

Choose a property source when secrets act as application configuration, such as a database password or SMTP credential.

~~~yaml
spring:
  cloud:
    oci:
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_ID}
        property-refresh-interval: 10m
        property-sources:
          - vault-id: ${OCI_VAULT_ID}
~~~

Secrets are added to the Spring `Environment` by name. Beans resolve them via `@Value` or `@ConfigurationProperties`.

Refreshing the property source does not automatically update every singleton bean or connection pool that already injected the old secret. Design client refresh/recreation separately.

### 6.2. `VaultTemplate` for On-Demand Retrieval

Use `VaultTemplate` when secrets must be chosen per tenant/workload or when you want control over read timing:

~~~java
GetSecretBundleByNameResponse bundle =
        vaultTemplate.getSecret(secretName);

String secretValue = vaultTemplate.decodeBundle(bundle);
~~~

Keep `VaultTemplate` inside a `SecretProvider` adapter. Business services should not depend on OCI response types.

### 6.3. Decision Matrix

| Need | Approach |
| --- | --- |
| Password loaded at startup | Property source |
| Dynamically named secret at runtime | `VaultTemplate` via adapter |
| Custom cache/TTL control required | `VaultTemplate` + cache policy |
| Secret rotates periodically | Property refresh + consumer refresh/recreation |
| Create/promote/delete secrets | Separate admin job with management permissions |

### 6.4. IAM and Rotation

Runtime workloads normally only need permission to read secret bundles. Separate read permissions from create, update, promote, or delete permissions. During rotation:

1. Create a new credential on the target system.
2. Create a new secret version.
3. Verify the new credential.
4. Promote the new version to `CURRENT`.
5. Refresh/recreate the `DataSource` or client.
6. Confirm all replicas use the new credential.
7. Revoke the old credential once no consumers remain.

Do not confuse `LATEST` with `CURRENT`; the newest version may still be in `PENDING` state.

## 7. Queue, Streaming, Notifications, and TxEventQ Are Not the Same

This is the most critical decision when selecting messaging.

| Service | Model | Suitable Workload | Progress / Destination |
| --- | --- | --- | --- |
| OCI Queue | Work queue | Independent tasks processed by workers | Message receive/settlement via Queue API |
| OCI Streaming | Stream/partition | Continuous event or data ingestion | Cursor/partition and consumer-managed checkpoints |
| OCI Notifications | Pub/sub fan-out | Broadcasting alerts/events to multiple subscriber types | Topics and subscriptions |
| Oracle TxEventQ | Database-native transactional queue | Messaging tied to Oracle AI Database | JMS, Kafka API, or Spring Cloud Stream binder |

Do not choose simply because a workload mentions the word "event" or "message". Determine whether a message is dispatched to one worker or broadcast to many subscribers; whether replay is required; whether ordering is needed; whether transactions are tied to the database; and who manages acknowledgments/checkpoints.

### 7.1. Comparing by Message Lifecycle

| Criterion | OCI Queue | OCI Streaming | OCI Notifications |
| --- | --- | --- | --- |
| Processing unit | Work item | Record/event in a stream | Notification sent to a topic |
| Consumer model | Workers pull messages to process | Consumers read records by partition/cursor | Subscribers register topics/endpoints |
| Primary goal | Work distribution | Ingesting, retaining, and reading record streams | Fan-out one alert to many targets |
| Progress tracking | Message delivery and settlement | Cursor/checkpoint | Service-tracked publish/subscription/delivery status |
| Replay | Bound by queue message lifecycle/retention | Re-read from cursor within retention | Not intended as a general replayable event log |
| Ordering | Per queue semantics and config | Ordered within a partition | Should not be relied on for business ordering |
| Dead-letter | Built-in queue dead-letter delivery count | Consumer implements quarantine/error flow | Subscribers handle failures per endpoint/delivery model |
| Fan-out | Not its primary purpose | Possible via multiple consumer groups/consumers per stream design | Core purpose |

### 7.2. Decision Tree

~~~mermaid
flowchart TD
    A[Application needs to send messages] --> B{Is each message a work item?}
    B -->|Yes| C[OCI Queue]
    B -->|No| D{Need to retain records and read by cursor/partition?}
    D -->|Yes| E[OCI Streaming]
    D -->|No| F{Need to broadcast the same alert to multiple subscribers?}
    F -->|Yes| G[OCI Notifications]
    F -->|No| H[Evaluate TxEventQ or another API]
~~~

### 7.3. Questions to Answer Before Choosing

1. Who owns the work after publishing: a single worker or multiple subscribers?
2. Does the consumer need to acknowledge/settle individual messages or save a read-position checkpoint?
3. Do you need to replay historical data within a retention window?
4. Is ordering needed system-wide, per partition/key, or not at all?
5. Do failed messages require redelivery, dead-lettering, or subscriber-specific retries?
6. Does the producer need to know the consumer finished business work, or only that the publish request was accepted?
7. Do you need a shared transaction with Oracle AI Database? If yes, evaluate TxEventQ.

### 7.4. Distinguishing Publish Success from Business Completion

An API returning publish success only proves the service accepted the operation per its API contract. It does not prove a worker finished a transaction or all subscribers finished processing. If the business needs final outcome tracking, consumers/subscribers must record processing state and emit results or update a dedicated workflow state.

### 7.5. Designing a Shared Event Contract

Whether you choose Queue, Streaming, or Notifications, payloads should include:

- Unique event ID.
- Event type and schema version.
- Aggregate/business ID.
- Occurred-at timestamp.
- Correlation/causation IDs when tracing workflows.
- Payload sized just right for consumers; avoid embedding large blobs or secrets.
- Schema compatibility rules when producers and consumers deploy at different times.

Never substitute a transport message ID for a business event ID. Transport IDs belong to the service; event IDs belong to the business contract and enable deduplication across providers.

## 8. OCI Queue: Work-Item Distribution

OCI Queue fits messages representing tasks that can be processed independently: generating thumbnails, processing invoices, sending emails, running background jobs, or triggering workflows.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-queue</artifactId>
</dependency>
~~~

The starter auto-configures a `Queue` bean for queue and message operations. The API can create queues with name, compartment, dead-letter delivery count, and retention.

Queue creation example:

~~~java
String queueId = queue.createQueue(
        "invoice-processing",
        compartmentId,
        deadLetterDeliveryCount,
        retentionInSeconds);
~~~

### 8.1. When to Choose Queue

- Each message typically represents a work item.
- Workers pick up work and execute side effects.
- Retries are needed for transient failures.
- Delivery attempts must be capped.
- Dead-letter/quarantine handling is needed for persistently failing messages.
- Queue depth and oldest message age must be monitored.

### 8.2. Consumers Need Idempotency

Messages can be redelivered after timeouts, worker crashes, or failed settlements. Consumers should maintain idempotency keys or inbox records so side effects do not repeat.

Example flow:

~~~text
Receive message
  -> validate message
  -> check inbox/idempotency key
  -> execute business transaction
  -> commit result + inbox marker
  -> settle/ack message
~~~

Never settle a message before business effects are durably persisted. If the commit succeeds but settlement fails, the message may be redelivered; inbox/deduplication handles the redelivery cleanly.

### 8.3. Queue Is Not an Event Log

Queue is designed for distributing work items. If you need to retain events by partition and replay from a cursor, Streaming is a better fit. If you need fan-out to multiple independent subscribers, Notifications is a better fit.

## 9. OCI Streaming: Ingesting and Consuming Records

OCI Streaming fits continuous high-throughput data/events such as audit streams, clickstreams, telemetry, or cross-system integration events.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-streaming</artifactId>
</dependency>
~~~

The starter auto-configures a `Streaming` bean to create streams and send/receive messages.

Record publishing example:

~~~java
PutMessagesResponse response =
        streaming.putMessages(
                streamId,
                "invoice-created".getBytes(StandardCharsets.UTF_8),
                eventPayload.getBytes(StandardCharsets.UTF_8));
~~~

Cursor-based reading example:

~~~java
GetMessagesResponse response =
        streaming.getMessages(streamId, cursor);
~~~

This is an API-level illustration; check how cursors are created, records deserialized, next cursors retrieved, and checkpoints saved in your SDK/starter version.

### 9.1. Partition Keys

Partition keys determine how records are distributed across partitions. Choose keys based on ordering and throughput:

- Key by `customerId` if per-customer ordering is needed.
- Key by `aggregateId` to keep an aggregate's events in the same partition.
- Avoid hot keys that funnel all records into a single partition.
- If entity-level ordering is unnecessary, choose a well-distributed key to utilize partitions evenly.

Ordering is not automatically global across the entire stream; it is scoped to a partition.

### 9.2. Cursors and Checkpoints

Consumers persist their read progress. After a restart, consumers can safely resume reading from a cursor. Ensure you:

- Commit business effects before saving the corresponding checkpoint.
- Never advance a checkpoint past records that haven't finished processing when processing in parallel.
- Store checkpoints durably.
- Maintain a replay and deduplication strategy.
- Monitor consumer lag and retention.

If the checkpoint advances ahead of the business commit, the application can lose events. If business work commits before the checkpoint updates, events may be re-read; idempotency handles duplicates.

### 9.3. When to Choose Streaming Over Queue

Choose Streaming when you need continuous ingestion, partitions, cursors, replay, and stream-based record processing. Choose Queue when messages are work items that workers execute and settle.

## 10. OCI Notifications: Broadcasting One Message to Many Subscribers

OCI Notifications is a pub/sub service for sending alerts/messages to email, SMS, Functions, Slack, PagerDuty, or custom HTTPS endpoints.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-notification</artifactId>
</dependency>
~~~

The starter auto-configures a `Notification` bean for topics, subscriptions, and publish operations.

Topic creation example:

~~~java
CreateTopicResponse response =
        notification.createTopic("invoice-alerts", compartmentOcid);
~~~

### 10.1. When to Choose Notifications?

- The same message must fan out to multiple subscribers.
- Destinations include email, SMS, functions, or HTTPS endpoints.
- The workload is alerting/notification rather than a single task owned by one worker.
- You want to decouple producers from subscribers.

### 10.2. Notifications Does Not Replace Queue

If each message must be processed by a single worker and settled like a work queue, use Queue. Notifications is built for pub/sub fan-out; do not design it as a durable work queue with consumer lock semantics.

If you need an event log replayable by partition, use Streaming.

### 10.3. Payloads and Subscribers

- Keep payloads concise and schema/versioned.
- Never put secrets or sensitive data inside notification bodies.
- Subscribers should authenticate the source and handle duplicates if downstream delivery retries.
- Monitor subscription health and delivery failures.
- Never treat publish success as proof that every subscriber finished processing.

## 11. Oracle TxEventQ: Messaging Tied to Oracle AI Database

TxEventQ stands for Oracle Database Transactional Event Queues. It differs from OCI Queue and OCI Streaming because its backend lives inside Oracle AI Database and can participate in database transactions where supported by the integration.

Choose the programming model matching your codebase:

| API | Starter / Project | When It Fits |
| --- | --- | --- |
| Spring JMS | Oracle AQ/JMS starter | Apps already using `JmsTemplate`/`@JmsListener` |
| Kafka Java API | OKafka starter | Apps using Kafka producer/consumer/admin concepts |
| Spring Cloud Stream | TxEventQ binder | Apps using `Supplier`/`Function`/`Consumer` bindings |

The TxEventQ binder is not a binder for OCI Queue or OCI Streaming. If you require managed OCI Queue, use the Queue starter.

### 11.1. Transaction Boundaries

The AQ/JMS starter can configure the `DataSource` and JMS `ConnectionFactory` to share a database transaction. When properly configured, a single transaction can read a message, update the database, and commit/rollback as one unit of work.

Do not extrapolate this behavior to OCI Queue, OCI Streaming, or Notifications. Those services have separate APIs and transaction boundaries. When pairing a database with OCI managed services, consider outbox, inbox, sagas, or reconciliation.

### 11.2. When Should You Choose TxEventQ?

- The workload already uses Oracle AI Database.
- You need database-native transactional messaging.
- You want to keep message flows within the same database platform.
- Your team prefers JMS, Kafka APIs, or Spring Cloud Stream.

If you do not need transactions tied to Oracle Database, OCI Queue/Streaming may align better with operational requirements.

## 12. Choosing Data Services: Autonomous Database, JDBC/UCP, or Oracle NoSQL

The term "Autonomous Database" can refer to the control plane that manages instances or the data plane used to query data. These two tasks need different APIs.

### 12.1. Autonomous Database Starter: Lifecycle Management

`spring-cloud-oci-starter-adb` auto-configures an `AutonomousDb` bean. This bean supports operations such as create, inspect, start, stop, delete Autonomous Database, and generate wallets.

Choose this starter when applications/platform automation need to manage database resources via OCI control-plane APIs.

Do not use the lifecycle starter as a substitute for `DataSource`/JDBC in business services.

### 12.2. JDBC/UCP/Wallet: Connecting to Run Queries

If the workload needs to read/write records, use the Oracle JDBC driver and `DataSource`. UCP manages connection pools; Wallet provides secure connectivity in environments requiring wallets/mTLS.

A business service typically uses:

- Spring JDBC or Spring Data JPA.
- Oracle JDBC driver.
- UCP `DataSource` where appropriate.
- Wallet/TNS configuration if required by the endpoint.
- A transaction manager for database transactions.

### 12.3. Oracle NoSQL Database

The OCI NoSQL starter fits key-value, table, or JSON workloads with well-defined access patterns and matching transaction semantics.

The starter auto-configures `NosqlDBConfig` and supports repository-based access. Enable repositories per integration guidelines, for example:

~~~java
@SpringBootApplication
@EnableNosqlRepositories
public class CatalogApplication extends AbstractNosqlConfiguration {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Repository:

~~~java
public interface BookRepository extends NosqlRepository<Book, Long> {
    Iterable<Book> findByAuthor(String author);
    Iterable<Book> findByTitle(String title);
}
~~~

Entity:

~~~java
@NosqlTable(tableName = "books")
public class Book {

    @NosqlId(generated = true)
    private long id;

    private String title;
    private String author;
    private double price;
}
~~~

The region must resolve from `spring.cloud.oci.region.static` or credential configuration before `NosqlDBConfig` is created.

### 12.4. Choosing a Data Model

| Workload | Direction |
| --- | --- |
| Relational, joins, multi-table transactions | Oracle AI Database + JDBC/JPA |
| Autonomous Database provisioning | `AutonomousDb` control-plane API |
| Key-value lookups, tables, JSON by access pattern | Oracle NoSQL |
| Large binary files/documents | Object Storage |
| Secrets/sensitive configuration | Vault |

Do not choose NoSQL solely because data contains JSON. Evaluate access patterns, transactions, indexes, consistency, and query needs.

## 13. Email Delivery: Choosing `MailSender` vs. `JavaMailSender`

OCI Email Delivery integrates with Spring Mail. `spring-cloud-oci-starter-email` provides `MailSender` and `JavaMailSender`.

Use `MailSender` for simple plain-text emails. Use `JavaMailSender` when you need MIME, HTML, attachments, or complex message structures.

SMTP configuration uses standard Spring Mail properties:

~~~yaml
spring:
  mail:
    host: ${OCI_SMTP_HOST}
    username: ${OCI_SMTP_USERNAME}
    password: ${OCI_SMTP_PASSWORD}
    port: 587
~~~

SMTP credentials must be generated in OCI Email Delivery and protected like secrets. Never use a database password or developer API key as an SMTP credential.

Simple email example:

~~~java
@Service
public class InvoiceMailService {

    private final MailSender mailSender;

    public InvoiceMailService(
            @Qualifier("ociMailSender") MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);
        mailSender.send(message);
    }
}
~~~

### Synchronous or Asynchronous Email?

Avoid sending emails synchronously inside the invoice creation transaction when slow or failed mail delivery could stall the request. Record an event/outbox entry after the invoice commits and let a worker send the email. Track delivery status, bounded retries, and idempotency per business event.

## 14. Functions: Invoking a Function vs. Building a Dedicated Worker?

The OCI Functions starter provides a client to invoke already-deployed functions. It does not automatically turn your existing Spring Boot application into an OCI Function.

`spring-cloud-oci-starter-function` auto-configures a `Function` bean. The invocation API takes a function OCID, endpoint, mode, and request body per the starter's contract.

Choose Functions when:

- Work is short-lived and cleanly separable into independent invocations.
- You want per-invocation scaling and a serverless runtime.
- Input/output boundaries are clear.
- You do not need a continuously running consumer process.
- Function cold starts, timeouts, and runtime limits are acceptable.

Choose Queue + worker when:

- Work items require backlogs and rate smoothing.
- Processing is long-running or needs steady concurrency.
- Fine-grained retry and dead-letter control are needed.
- Workers should run continuously or keep long-lived local resources.

You can combine Queue with Functions if a trigger/service architecture supports it. Do not assume every queue message automatically invokes a function unless the integration is explicitly configured.

## 15. Logging: Sending Application Logs vs. Using an Observability Stack?

The OCI Logging starter provides a `LogService` bean to send logs to OCI Logging. The destination log is selected via `spring.cloud.oci.logging.logId`.

Example:

~~~java
PutLogsResponse response = logService.putLog("invoice-created");
~~~

Choose OCI Logging integration when the application needs to push logs to OCI Logging or attach logs to a provisioned log resource.

Do not confuse application logs with metrics and distributed tracing:

- Logs record detailed discrete events.
- Metrics aggregate numerical measurements over time.
- Traces follow a request's path across multiple services.
- OCI Logging does not replace Micrometer/OpenTelemetry instrumentation.

Never send secrets, passwords, tokens, or sensitive payloads to logs. Attach correlation IDs and request IDs for cross-referencing; avoid placing high-cardinality IDs into metric labels.

## 16. Generative AI: `ChatModel` and `EmbeddingModel`

The OCI Generative AI starter provides Spring-friendly model abstractions. Current starters in OCI documentation can auto-configure `ChatModel` and `EmbeddingModel`.

Choose `ChatModel` when the workload needs text generation or conversation. Choose `EmbeddingModel` when converting text into vectors for semantic search or retrieval workflows.

Do not treat an embedding model as a replacement for a database or vector index; the model only produces vectors. The application still needs to store and query vectors in an appropriate storage/index.

When choosing a model/API, determine:

- Model ID or dedicated cluster endpoint.
- Region and compartment.
- Input/output token limits.
- Latency and throughput.
- Data sensitivity and logging policies.
- Timeouts, retries, and quotas.
- Cost per request/token.
- Model version and evaluation dataset.

Within the Oracle ecosystem, check the release lines of both the OCI Generative AI starter and the Spring AI Oracle project. Do not add both integrations simply because both mention Generative AI; select the implementation recommended in the documentation for your application baseline.

## 17. Quick Scenario Selection Map

| Scenario | First Choice | Starting API |
| --- | --- | --- |
| Store PDFs, images, archives | OCI Object Storage | `Storage` or `Resource` |
| Load passwords/API tokens | OCI Vault | Property source or `VaultTemplate` |
| Run background tasks with retries | OCI Queue | `Queue` |
| Collect continuous events/telemetry | OCI Streaming | `Streaming` |
| Broadcast alerts to multiple subscribers | OCI Notifications | `Notification` |
| Send transactional emails | OCI Email Delivery | `MailSender`/`JavaMailSender` |
| Invoke serverless processing | OCI Functions | `Function` |
| Create/start/stop Autonomous DB | Autonomous Database | `AutonomousDb` |
| Query Oracle database | Oracle JDBC/UCP/Wallet | `DataSource`, JDBC/JPA |
| Key-value/table/JSON data | Oracle NoSQL | `NosqlRepository` |
| Push logs to OCI Logging | OCI Logging | `LogService` |
| Chat/embeddings | OCI Generative AI/Spring AI Oracle | `ChatModel`, `EmbeddingModel` |
| Transactional messaging inside Oracle DB | TxEventQ | JMS, OKafka, or Stream Binder |

This table is a starting point. Final decisions must rest on delivery semantics, data models, throughput, transactions, and operational capabilities.

## 18. Designing a Multi-Service Workload

Invoice Service example:

~~~mermaid
flowchart TD
    A[Invoice API] --> B[Oracle AI Database]
    A --> C[OCI Object Storage]
    A --> D[OCI Vault]
    B --> E[Outbox event]
    E --> F[OCI Queue]
    F --> G[Invoice worker]
    G --> H[OCI Email Delivery]
    G --> I[OCI Notifications]
    G --> J[OCI Logging]
    G --> K[OCI Function]
~~~

A processing flow might:

1. Receive an invoice creation request.
2. Write invoice metadata to the database.
3. Save the PDF file to Object Storage.
4. Write an outbox event inside the database transaction.
5. Publisher forwards the event to Queue.
6. Worker reads the event and checks idempotency.
7. Worker sends an email via `MailSender`.
8. Worker publishes notifications to subscribers if needed.
9. Worker logs the operation and outcome.
10. A heavy processing step may invoke a Function.

### 18.1. No Single Transaction Spans All Services

A database `@Transactional` does not automatically cover Object Storage, Vault, Queue, Email Delivery, and Functions.

Define failure boundaries:

| Operation | Boundary |
| --- | --- |
| Insert invoice + outbox row | Database transaction |
| Upload PDF | Object Storage API operation |
| Read secret | Vault API operation |
| Publish Queue message | Queue API operation |
| Send email | SMTP operation |
| Publish notification | Notifications API operation |
| Invoke Function | Function invocation |
| Write log | Logging API operation |

Use outbox/inbox, idempotency, sagas, or reconciliation to coordinate side effects. Never hold a database transaction open while waiting on email, functions, or slow external APIs.

### 18.2. Choosing Sync vs. Async

Use synchronous APIs when the client needs an immediate result and the operation is short with clear timeouts. Use async queues/events when operations are long-running, retryable, need load leveling, or do not require an immediate response.

Do not make every call asynchronous. If an operation only reads a cached secret or runs a fast database query, a queue adds unnecessary complexity.

## 19. Identity, IAM, Region, and Compartment per Workload

Each service adapter needs an identity suited to its runtime. Prefer Instance Principal for OCI Compute, Resource Principal for supported resources, and Workload Identity for configured OKE clusters. Local development can use `FILE`/session tokens.

Separate policies by service:

- Storage writers only have write permissions on required objects.
- Vault readers only read required secrets.
- Queue producers only publish.
- Queue consumers only consume/settle per API.
- Logging writers only write logs to designated destinations.
- Function invokers only invoke required functions.
- Autonomous Database provisioning identities hold broader control-plane rights than runtime query identities.

The region must match the resource. Compartments are resource/policy management scopes. `spring.cloud.oci.region.static` can override the region in the auth config file. Never assume the compartment property grants permissions automatically or that every operation uses the default compartment.

Do not share one admin identity across every service just to reduce policy count. Separating identities reduces blast radius and makes auditing clearer.

## 20. Retries, Timeouts, Idempotency, and Backpressure

Each service has distinct semantics. Design retries in adapters per operation and error class.

### Retries

- Retry transient and throttling errors with jittered backoff.
- Do not retry validation, authentication, or authorization errors indefinitely.
- Cap the total retry budget.
- Honor `retry-after` when provided by the service/API.
- Avoid uncoordinated simultaneous retries across client, service, and queue worker without a shared budget.

### Timeouts

- Connect timeouts and read/operation timeouts must match target latency.
- A timeout does not prove an operation did not occur.
- On upload, publish, or invocation timeouts, inspect state or rely on idempotency keys.
- Never let HTTP requests wait indefinitely on a managed service.

### Idempotency

- Object Storage: object keys/versions and conditional writes.
- Queue: business idempotency keys/inbox.
- Streaming: event IDs + checkpoint/replay deduplication.
- Notifications: event identity at subscribers.
- Email: persist send status and business event ID; do not assume SMTP retries are always exactly-once.
- Function: idempotent inputs or invocation keys if supported by application protocol.
- Database: unique constraints/business keys.

### Backpressure

- Cap worker concurrency according to downstream capacity.
- Cap in-flight requests.
- Do not consume messages faster than they can be durably processed.
- Monitor queue depth, stream lag, and retry backlogs.
- Use circuit breakers for outage-prone dependencies when appropriate.
- Separate bulkheads across email, storage, database, and AI workloads.

## 21. Security and Data Handling

- Never commit API keys, private keys, SMTP passwords, or secrets.
- Use Vault/secret injection for credentials.
- Use TLS and least-privilege IAM.
- Encrypt data per service policy.
- Avoid putting PII or secrets in notifications/logs unless strictly required.
- Verify data residency and regions before provisioning resources.
- Set retention/lifecycle rules for objects, queues, streams, and logs.
- Audit resource access and modifications.
- Separate provisioning permissions from runtime permissions.
- Restrict delete and administrative privileges.

For sensitive data, service selection must weigh where data is stored, who can read it, how long it is retained, and how deletion/retention works.

## 22. Performance, Quotas, and Cost

Evaluate services against actual workload characteristics:

| Component | Metrics to Measure |
| --- | --- |
| Object Storage | Object count, size, throughput, request rate, download patterns |
| Vault | Secret count, read frequency, refresh interval, rotation |
| Queue | Queue depth, oldest message age, delivery attempts, worker throughput |
| Streaming | Partition count, ingest rate, consumer lag, retention |
| Notifications | Publish rate, subscriber count, delivery failures |
| Email | SMTP throughput, recipient volume, retries/bounces |
| Functions | Invocation count, duration, memory, cold starts |
| Autonomous Database | Connection pool, CPU/storage, session count, query latency |
| NoSQL | Read/write units, key distribution, index/query patterns |
| Logging | Ingest volume, retention, query frequency |
| Generative AI | Input/output tokens, latency, model quotas |

Do not decide purely on per-request pricing. Calculate total cost: requests, storage, retention, network transfer, compute, retries, log ingestion, and operations.

## 23. Testing Along Service Boundaries

### Unit Tests

Mock internal interfaces such as `InvoiceFileStore`, `SecretProvider`, `OrderPublisher`, and `NotificationSender`. Unit tests focus on business rules, idempotency, and error mapping.

### Context / Auto-Configuration Tests

Verify the right starter creates expected beans and the application context starts cleanly. Use appropriate dummy properties/identities; never use production credentials.

### Integration Tests

- Object Storage: upload/download/checksum/metadata.
- Vault: property source, `VaultTemplate`, secret rotation.
- Queue: publish/consume/redelivery/dead-letter.
- Streaming: partition/cursor/checkpoint/replay.
- Notifications: topic/subscription/publish.
- Email: SMTP authentication, delivery status, and error handling.
- Functions: invoke deployed functions and validate responses.
- Autonomous DB: control-plane operations in a test compartment.
- JDBC/UCP: connection pool, transactions, and queries.
- NoSQL: repository CRUD/queries per access pattern.
- Logging: send logs and verify destination.
- Generative AI: model config, timeouts/quotas, and output validation.

### Failure Injection

- OCI API timeout after the server already received the request.
- 401/403 from identity/policy issues.
- 404 from region/compartment/resource ID mismatches.
- 429 throttling.
- Queue message redelivery.
- Stream consumer restart after business commit but before checkpoint.
- Vault rotation while multiple replicas are running.
- Email timeout with unknown delivery outcome.
- Function invocation timeout.
- Database pool exhaustion or connection reset.

Test in a dedicated test compartment using synthetic data. Never run destructive failure injection on production resources.

## 24. Observability and Runbooks

Monitor metrics/logs per service:

| Service | Signals |
| --- | --- |
| Storage | Upload/download latency, bytes, errors, object not found |
| Vault | Read/refresh failures, cache age, version changes |
| Queue | Depth, oldest message age, delivery count, DLQ |
| Streaming | Ingest rate, partition lag, cursor age, replays |
| Notifications | Publish failures, subscription status |
| Email | SMTP failures, send latency, bounces/retries |
| Functions | Invocation latency, timeouts, errors |
| Database | Pool active/wait, query latency, transaction rollbacks |
| NoSQL | Read/write latency, throttling, hot keys |
| Logging | Ingest failures, log volume |
| Generative AI | Model latency, token usage, quotas/timeouts |

Runbooks should answer:

1. Which principal is the workload using?
2. Which region/compartment holds the resource?
3. What is the API request ID?
4. Is the failure auth, IAM, network, quota, or a service failure?
5. Could the operation have succeeded despite the client timeout?
6. Is it safe to retry?
7. Is reconciliation or manual replay needed?
8. Who owns the policy/resource and who is authorized to change it?

## 25. Lab Exercise: Designing Integrations for Invoice Platform

**Context:** Build an Invoice Platform using Spring Boot. The system receives invoices, stores metadata and PDFs, emits events to send emails, and writes audit logs. Some invoices require image processing or OCR via a function.

### Part A — Choosing Services

1. Use Oracle AI Database/JDBC for invoice metadata.
2. Use OCI Object Storage for PDFs.
3. Use OCI Vault for database/SMTP credentials.
4. Use OCI Queue for email-sending work items.
5. Use OCI Notifications for alert fan-out if multiple subscribers are needed.
6. Use OCI Logging for application/audit logs.
7. Use OCI Functions for image/OCR processing if within execution limits.

### Part B — Choosing APIs

1. Use `Storage` for uploads with metadata.
2. Use `Resource` for file reading flows inside Spring APIs.
3. Use Vault property source or `VaultTemplate` depending on secret lifecycle.
4. Use the `Queue` bean to send/receive work items.
5. Use `MailSender` for simple emails.
6. Use the `Function` bean to invoke deployed functions.
7. Use JDBC/UCP for database transactions.

### Part C — Designing Consistency

1. Write the invoice and outbox row inside the same transaction.
2. Upload the PDF using an idempotent object key.
3. Have the publisher read the outbox and send a Queue message.
4. Have the worker enforce inbox/idempotency keys.
5. Have the worker send the email and persist status.
6. Have the Function process images per the invocation contract.
7. Log operation IDs and request IDs.
8. Reconcile operations with timeouts/unknown outcomes.

### Part D — IAM and Operations

1. Separate identities for API, worker, and function.
2. Grant least-privilege permissions for Storage/Vault/Queue/Logging/Functions.
3. Choose region and compartments.
4. Set retries/timeouts and DLQ policies.
5. Set up alerts for queue backlog and error rates.
6. Test restarts, duplicates, and throttling.

### Deliverables

- Workload-to-service decision matrix.
- Architecture and data flow diagram.
- Starter/API mapping table per service.
- IAM policy matrix per workload.
- Sample adapter code for Storage, Vault, Queue, and Email.
- Outbox/inbox and idempotency design.
- Test matrix for success/failure/retry cases.
- Dashboard for latency, backlog, errors, and cost drivers.
- Runbook for handling timeouts, 403s, DLQs, and replays.

## 26. Self-Check Questions

1. Why should service selection start from the workload?
2. When do you use the `Storage` API vs. Spring `Resource`?
3. Why is Object Storage not a filesystem?
4. How does a property source differ from `VaultTemplate`?
5. Why doesn't refreshing a secret automatically update a `DataSource`?
6. In what semantics do OCI Queue and OCI Streaming differ?
7. Is Notifications suited for fan-out or work queues?
8. Why does TxEventQ differ from OCI Queue?
9. When do you use AQ/JMS, OKafka, or the TxEventQ binder?
10. Does the `AutonomousDb` bean serve the control plane or data plane?
11. When querying an Oracle database, do you need `DataSource`/UCP or the `AutonomousDb` lifecycle API?
12. Which access patterns suit Oracle NoSQL?
13. When do you use `MailSender` vs. `JavaMailSender`?
14. Does the Function starter invoke functions or deploy functions?
15. Does OCI Logging replace metrics/tracing?
16. Why doesn't a single `@Transactional` span Object Storage and Queue?
17. When a Queue message is redelivered, what mechanism does the consumer need?
18. When a Streaming consumer restarts, when should checkpoints be committed?
19. Why doesn't a timeout prove an operation failed to happen?
20. How do you verify the right identity and IAM policy for each workload?

## 27. Key Takeaways

- Choose services based on workload semantics, not merely service names.
- Spring Cloud OCI includes a core starter and service-specific starters; pick the exact starter for each capability.
- `Storage` fits bucket/object operations; `Resource`/`WritableResource` fits Spring-abstracted read/write streams.
- Vault property sources fit startup configuration; `VaultTemplate` fits on-demand secret retrieval.
- OCI Queue distributes work items; OCI Streaming ingests/consumes records by partition/cursor; Notifications fans out pub/sub alerts to multiple subscribers.
- TxEventQ is database-native messaging offering JMS, Kafka-style, or Spring Cloud Stream binder APIs.
- The `AutonomousDb` starter manages Autonomous Database lifecycle; JDBC/UCP/Wallet handle data queries.
- Oracle NoSQL repositories fit key-value/table/JSON models matching explicit access patterns.
- Email Delivery integrates with Spring Mail; the Functions starter invokes deployed functions; the Logging starter pushes logs via `LogService`.
- Generative AI requires picking the right `ChatModel`/`EmbeddingModel` and integration version.
- Never assume one transaction spans multiple managed services; use outbox, inbox, idempotency, and reconciliation.
- IAM, regions, compartments, retries, timeouts, retention, and observability must be designed per workload.

## References

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud OCI — Core starter and service catalog](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [OCI Object Storage integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/)
- [OCI Vault integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [OCI Queue integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/queues/)
- [OCI Streaming integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/streaming/)
- [OCI Notifications integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/notifications/)
- [OCI Logging integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/logging/)
- [OCI Email Delivery integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/email-delivery/)
- [OCI Functions integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/functions/)
- [OCI Autonomous Database integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/autonomous-database/)
- [Oracle NoSQL Database integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/nosql/)
- [OCI Generative AI integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/generative-ai/)
- [Spring Cloud Oracle — Oracle AI Database starters](https://oracle.github.io/spring-cloud-oracle/site/docs/category/oracle-ai-database-starters/)
- [Spring Cloud Oracle — TxEventQ Stream Binder](https://oracle.github.io/spring-cloud-oracle/site/docs/stream-binder/getting-started/)
- [OCI Queue documentation](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm)
- [OCI Streaming documentation](https://docs.oracle.com/en-us/iaas/Content/Streaming/Concepts/streamingoverview.htm)
- [OCI Notifications documentation](https://docs.oracle.com/en-us/iaas/Content/Notification/Concepts/notificationoverview.htm)
