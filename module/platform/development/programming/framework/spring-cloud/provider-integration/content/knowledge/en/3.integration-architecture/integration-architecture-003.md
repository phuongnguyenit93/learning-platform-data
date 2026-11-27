# Choosing Starter, Template, Repository, or Direct SDK Based on Need

When integrating Spring Boot with a managed service, the first question is often: “Should I use a Spring Cloud starter, a template, a Spring Data repository, or call the AWS, Azure, or Google Cloud SDK directly?” These four choices **do not sit at the same level**. A **starter** primarily brings dependencies and auto-configuration into the application; a **template** and a **repository** are two styles of higher-level programming APIs; and an **SDK client** is the service-facing API published by the cloud provider. An application can completely **install a starter and still call the SDK directly**, or use a repository for business data and a template for messaging within the same use case.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practical integration of Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries: identity and permission configuration, storage, messaging, data, secret protection, integration testing, and comparing differences across cloud providers. This lesson focuses on establishing **criteria for choosing the integration layer by need**, rather than defaulting to a single API style for every service.

## 1. Learning Outcomes

After studying this lesson, you can:

- Explain the purpose and boundaries of a starter, template, repository, and SDK client.
- Analyze business requirements, cloud capabilities, number of providers, synchronous/asynchronous models, and testability to choose an integration approach.
- Choose an appropriate API for object storage, messaging, managed databases, and secret management.
- Organize code into services, ports, and provider adapters when business logic needs to remain provider-independent.
- Recognize trade-off costs: code volume, access to specialized features, library lifecycle, observability, security, and upgrade difficulty.
- Plan testing from unit tests up to integration tests against real cloud environments.

## 2. Four Concepts: How Do They Relate?

| Component | Nature | What It Typically Provides | What It Does Not Solve on Its Own |
| --- | --- | --- | --- |
| **Starter** | Dependency bundle and Spring Boot/Spring Cloud configuration | Brings SDK/integration libraries onto the classpath, registers beans, binds properties, configures listeners/templates when supported | Not a business API; does not guarantee IAM/RBAC permissions or network connectivity |
| **Template** | Framework-provided operational API | Simplifies send/receive operations, serialization, message/resource conversion, and Spring integration | Not guaranteed to cover all provider-specific APIs and features |
| **Repository** | API oriented around data collections/aggregates, typically from Spring Data | CRUD, derived queries, paging/sorting, and datastore-specific persistence integration | Not a default abstraction for object storage, queues, or secrets |
| **Direct SDK** | Provider's official client library | Close-to-service API access, request/response models, granular tuning, new features | Does not automatically isolate provider dependencies from business logic |

Several valid ways to combine them:

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Application service]
    B --> C[Repository: business data]
    B --> D[Storage / Messaging port]
    D --> E[Provider adapter]
    E --> F[Spring Cloud Template]
    E --> G[Direct SDK client]
    F --> G
    H[Cloud starter] -. provides dependencies and auto-config .-> F
    H -. may create bean .-> G
    C --> I[(Managed database)]
    G --> J[Managed cloud API]
~~~

**Key point:** Choosing a starter and choosing a programming API are **two separate decisions**. For example, add **spring-cloud-aws-starter-s3** so Spring Cloud AWS configures **S3Client**, then inject **S3Client** into your adapter and call the AWS SDK's **putObject**. You do not have to use **S3Template** just because you used the starter. Similarly, a Spring Data repository may use an underlying driver or SDK while the application programs against a data model.

## 3. Start with the Characteristics of the Use Case

Before choosing a library, answer six questions:

1. **What is the primary operation?** Writing an object, publishing a message, reading/writing an aggregate, querying data, or reading a secret?
2. **Are generic or specialized features needed?** Simple CRUD differs from multipart uploads, batch writes, object version control, message sessions/locks, or administrative operations.
3. **Is the API synchronous, async, or reactive?** An HTTP request waiting for a result, background message processing, or a reactive stream with backpressure?
4. **Is the application tied to one cloud or does it need to run on multiple clouds?** How much portability is genuinely needed, and which service differences must be preserved?
5. **What guarantees matter?** Transactions, idempotency, message ordering, retries, latency bounds, consistency, access control, auditing.
6. **Can the engineering team test and operate that integration?** Are there emulators, test resources, observability, and a plan for BOM and SDK upgrades?

First-level approach selection diagram:

~~~mermaid
flowchart TD
    A[Use case needs managed service] --> B{Store and query data aggregates?}
    B -->|Yes| C{Suitable Spring Data module exists?}
    C -->|Yes| D[Evaluate Repository]
    C -->|No| E[Evaluate driver / SDK]
    B -->|No| F{Template supports required functionality?}
    F -->|Yes| G{Need specialized API features?}
    G -->|No| H[Evaluate Template]
    G -->|Yes| I[Evaluate SDK client]
    F -->|No| I
    D --> J[Check abstraction limits]
    E --> J
    H --> J
    I --> J
    J --> K[Select starter / client config / identity / tests]
~~~

This is a **heuristic**, not a rigid law. For instance, Cloud Storage is an object storage service, not a relational database where Spring Data JPA automatically applies. An SDK may still fit better than a template when only a small set of APIs is used but fine-grained control is required. Conversely, a repository is a great fit if Spring Data's query model matches the need and the module is compatible.

## 4. Starter: When Should You Add One?

### 4.1. Role

A Spring Cloud starter typically bundles dependencies and enables conditional auto-configuration for components such as clients, properties, converters, templates, or listener containers. It lets Spring manage configuration, dependency injection, and lifecycles. Specific artifact names, properties, and features depend on the **provider and version**.

For example, with **Spring Boot 3 and Spring Cloud AWS 3.x**, a Maven dependency for S3 looks like:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

The application can declare the region and bucket as follows:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${APP_STORAGE_BUCKET}
~~~

In this example, **spring.cloud.aws.region.static** is a Spring Cloud AWS property; **app.storage.bucket** is defined by the application itself. There is no default mechanism that automatically understands application properties unless we bind or inject them. Versions are managed via a **compatible BOM**; a starter does not guarantee Spring Boot, Spring Cloud, and the SDK will work properly if versions are mixed arbitrarily.

### 4.2. When to Use or Skip a Starter

**Prefer a starter** when:

- The project already uses Spring Boot and the corresponding Spring Cloud library well supports the target service.
- You want client beans, property binding, listeners, or templates ready out of the box for that version.
- The team wants consistent configuration across local/test/production and less boilerplate client initialization code.

**Using only the SDK/driver may make sense** when:

- No starter exists or it does not support your required Boot/SDK versions and target service.
- You need only a very small API subset, need early SDK updates, or do not want extra integration layers.
- You require specialized client configuration that the integration library does not allow customizing safely.

However, defining an SDK client manually via **@Bean** can also be combined with a starter: many auto-configurations use **@ConditionalOnMissingBean** to yield to an application-declared bean. **You must verify the condition report and bean graph**; never assume every starter exhibits the exact same back-off behavior.

## 5. Template: Reducing Boilerplate for Task-Oriented Operations

A **Template** typically represents actions like **send**, **receive**, **upload**, or **download**, while encapsulating part of the data conversion and Spring integration. It is a good choice when application operations fall within the API surface provided by the template.

For example, with **Spring Cloud AWS SQS 3.x**, a service can use **SqsTemplate** to publish events:

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Service;

record OrderPlaced(String orderId, long occurredAtEpochMs) {}

@Service
public class OrderEventPublisher {
    private final SqsTemplate sqsTemplate;

    public OrderEventPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }

    public void publish(OrderPlaced event) {
        sqsTemplate.send("order-events", event);
    }
}
~~~

Corresponding dependency in the Spring Cloud AWS family:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
</dependency>
~~~

The example assumes the application already configured the queue name, permissions, and a message converter supporting the **OrderPlaced** payload for the library version used. **A successful send** usually only confirms that the queue/broker accepted the message per the API; it does **not** confirm that a consumer finished processing it. Options such as FIFO, ordering, deduplication, visibility timeout, dead-letter handling, and processing acknowledgments must be designed explicitly.

Templates are especially useful when:

- Most calls are common operations already supported by the template.
- You want integration with converters, listeners, lifecycles, or Spring conventions.
- You want to reduce repetitive request/response transformation code.

Switch to the **direct SDK** inside a specific adapter if you need new provider features, special control parameters, or low-level operations that the template does not yet support. Do not wrap a template API in multiple layers that merely rename methods without adding a business contract or testing benefit.

**Note:** There is no single unified **CloudTemplate** interface across AWS, Azure, and Google Cloud. For instance, SQS, Azure Service Bus, and Google Pub/Sub differ in queue/topic models, acknowledgments, subscriptions, retries, and ordering. Check exact template/listener names and capabilities in the official documentation for your version.

## 6. Repository: When the Use Case Truly Involves Structured Data

A **Spring Data repository** expresses operations on aggregates and data queries. It makes sense when the datastore and Spring Data module provide a model aligned with the application. For example, when using **managed PostgreSQL** on **Amazon RDS**, **Azure Database for PostgreSQL**, or **Google Cloud SQL**, you can use **Spring Data JPA** and the PostgreSQL driver; application CRUD logic barely needs to know which cloud hosts the database.

Minimal entity and repository example:

~~~java
// InvoiceEntity.java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "invoices")
public class InvoiceEntity {
    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String externalId;

    protected InvoiceEntity() {}

    public InvoiceEntity(UUID id, String externalId) {
        this.id = id;
        this.externalId = externalId;
    }

    public UUID getId() { return id; }
    public String getExternalId() { return externalId; }
}
~~~

~~~java
// InvoiceRepository.java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository
        extends JpaRepository<InvoiceEntity, UUID> {
    Optional<InvoiceEntity> findByExternalId(String externalId);
}
~~~

~~~java
// InvoiceService.java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository invoices;

    public InvoiceService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional
    public UUID register(String externalId) {
        return invoices.save(
            new InvoiceEntity(UUID.randomUUID(), externalId)).getId();
    }
}
~~~

The example assumes the project already has **spring-boot-starter-data-jpa**, the PostgreSQL JDBC driver, a datasource, table migrations, and uniqueness/idempotency rules. In practice, check for duplicate `externalId` values and handle unique constraint violations under race conditions.

**Repositories fit** structured queries, database transactions, and entity lifecycles. They do **not** magically turn an S3 upload into a persisted entity or turn a queue into a database; look at the nature of the service.

For provider-specific datastores such as **Azure Cosmos DB**, **Google Cloud Firestore**, or **Google Cloud Spanner**, a corresponding Spring Data module or template may exist in specific versions. When evaluating one, check:

- Is the module actively maintained and compatible with your project's Spring Boot/JDK versions?
- Do the module's derived queries/paging/transactions match the datastore's actual capabilities?
- Are there critical features supported only by the direct SDK?
- Are there discrepancies in data modeling, indexing, consistency, query cost, or partition keys?

Do not assume JPA repository annotations behave identically on Cosmos DB, Firestore, or Spanner. **Repository transactions** also typically cover only that datastore; they do not automatically encompass object storage calls or message publishing.

## 7. Direct SDK: Explicit Control Over Provider APIs

Official SDKs are often the right choice when you need specialized features, full request/response models, performance tuning, or custom timeouts, HTTP clients, credentials, and retries. **Direct** here means the adapter calls the SDK API; it does not mean abandoning Spring or instantiating a new client per request.

Example adapter writing an object using **AWS SDK for Java v2** with a Spring-injected client:

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void save(String objectKey, byte[] content, String contentType);
}
~~~

~~~java
// S3DocumentStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3DocumentStorage implements DocumentStorage {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public void save(
            String objectKey, byte[] content, String contentType) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

        s3.putObject(request, RequestBody.fromBytes(content));
    }
}
~~~

**Notable point:** Even when using the **direct SDK**, the **S3Client** bean can still be auto-configured by the Spring Cloud AWS starter. The adapter owns the mapping between application semantics and AWS APIs; the business service only knows **DocumentStorage**. The example uses a byte array for simplicity; large files should consider streaming, multipart uploads, or direct uploads depending on each cloud's characteristics. Validation, authorization, and exception mapping must be added in real applications.

Cases where the direct SDK often has a clear advantage:

- **Object storage:** multipart/resumable uploads, signing time-limited URLs, versioning control, or conditional writes via ETag/preconditions.
- **Messaging:** FIFO setup, specialized message attributes, batch operations, dead-letter/redrive APIs, and custom ordering requirements.
- **Data:** specialized query APIs, bulk/batch writes, consistency levels, or transaction models not fully captured by abstractions.
- **Security/administration:** secret rotation, key management, policies, or administrative actions difficult to express with a template.

These cases increase provider coupling. Place SDK code inside an **infrastructure adapter** and expose only the needed capabilities through the port. If a business requirement genuinely depends on a feature absent in other clouds, it is better to express that capability explicitly than to hide differences and cause incorrect behavior.

## 8. Applying This to AWS, Azure, and Google Cloud

### 8.1. Object Storage

| Use case | AWS | Azure | Google Cloud | Selection Guidance |
| --- | --- | --- | --- | --- |
| Standard upload/download | Amazon S3 | Azure Blob Storage | Cloud Storage | Starter + template if API suffices; or starter + SDK client |
| Time-limited access URL | S3 presigned URL | Blob SAS or appropriate grant mechanism | Signed URL | SDK/client supports URL signing; verify signing permissions and expiration |
| Large / chunked upload | Multipart upload | Block blob / chunk upload | Resumable upload | Use the provider's appropriate API/builder |
| Metadata, versioning, conditional writes | S3 features | Blob features | GCS features | Inspect request models and real semantics before abstracting |

S3 uses **bucket/key**, Azure Blob uses **container/blob**, and GCS uses **bucket/object**. These models are close, yet differ in authentication, ACL/IAM/RBAC, write preconditions, storage tiers, and pricing. Never pick a JPA repository for object storage operations just because you want a **save** method.

### 8.2. Messaging

| Need | AWS | Azure | Google Cloud | Selection Guidance |
| --- | --- | --- | --- | --- |
| Common message publishing | SQS/SNS | Service Bus | Pub/Sub | Template/publisher abstraction if it meets the contract |
| Spring-managed consumer | SQS listener | Service Bus consumer/integration | Pub/Sub subscriber/integration | Version-matched listener/container with ack control |
| Specialized ordering/dedup/retry | SQS FIFO, visibility, DLQ | Sessions/locks, dead-letter | Ordering keys, ack deadline, dead-letter | SDK or specialized config when template falls short |

**Do not use a repository to simulate a queue** if the use case requires broker delivery semantics. A successful **publish** call also does not mean a consumer has finished processing. Handlers must account for redelivery, idempotency, poison messages, and retry/dead-letter observability. If a service writes to a database and emits an event, consider the **transactional outbox** pattern to avoid losing events between two systems; JPA transactions do not automatically span queues.

### 8.3. Managed Databases

For **managed PostgreSQL/MySQL** on RDS, Azure Database, or Cloud SQL, **Spring Data JPA/JDBC** can be suitable because access goes over standard database protocols. Driver choice, connection pooling, networking, TLS, IAM database authentication/identity (if used), schema migrations, and transactions must be configured separately.

For **DynamoDB, Cosmos DB, Firestore, or Spanner**, first verify whether a Spring Data module or template is actively maintained and understand its limits. If no suitable abstraction exists, call the client/SDK directly inside an adapter tailored to the real partition/query model. Do not force disparate datastores into a fake **JpaRepository** mold.

### 8.4. Secret Management

Reading secrets from **AWS Secrets Manager**, **Azure Key Vault**, or **Google Secret Manager** typically uses supported config integrations, Spring Cloud integrations, or the respective SDKs. **Repository** is usually not a suitable abstraction for secrets. Choose the secret-fetching approach based on when it must be read (startup vs. runtime), caching/refresh, rotation, policies, and auditing. Avoid copying secrets into source code, committed config files, or logs; prefer workload identity and read-only permissions scoped strictly to required secrets.

### 8.5. What Is Similar and What Differs

| Aspect | Can Be Standardized in the App | Must Be Verified per Provider |
| --- | --- | --- |
| Business logic | Use cases, ports, inputs, and outputs | Features unsupported by other clouds |
| Spring | Bean lifecycle, dependency injection, validation, conditional config | Starters, template/repository APIs, property namespaces, version compatibility |
| Security | Least privilege principle, avoiding hard-coded credentials | IAM roles, Managed Identity/RBAC, ADC/service accounts/workload identity |
| Reliability | Timeout budgets, bounded retries, idempotency, logging | Error codes, quotas, consistency, acknowledgment/locking |
| Testing | Port-based unit tests, use-case smoke tests | Emulators, credentials, endpoints, and real service behavior |

## 9. Designing Boundaries: Stable Business Logic, Swappable Adapters

For a requirement to “create an invoice, save a PDF, and publish an event,” the architecture can combine three different API styles without letting business logic know cloud service names:

~~~mermaid
flowchart LR
    A[InvoiceApplicationService] --> B[InvoiceRepository]
    A --> C[DocumentStorage port]
    A --> D[EventPublisher port]
    B --> E[(Managed PostgreSQL)]
    C --> F[S3 / Blob / GCS adapter]
    F --> G[SDK client or template]
    G --> H[Object storage]
    D --> I[SQS / Service Bus / PubSub adapter]
    I --> J[Messaging template / SDK]
    J --> K[Messaging service]
~~~

**InvoiceRepository** represents persistence and database transactions. **DocumentStorage** represents the need to store documents, while **EventPublisher** represents emitting event notifications. Behind each port you may use a starter, template, or SDK depending on functionality. Even with a single cloud, ports remain valuable for unit testing and keeping authorization/idempotency logic in the right layer; with multiple clouds, they provide clean adapter swap points.

However, separating ports **does not create a distributed transaction**: DB writes, object uploads, and event publishes can succeed or fail independently. Define execution order, intermediate states, compensation, retries, and transactional outbox when consistency demands it. For re-generable PDFs, a workflow that saves **PENDING** metadata first, uploads the file, and then marks it **READY** can be safer than assuming all steps are atomic.

A good port expresses the application's real semantics:

~~~java
public interface DocumentStorage {
    void save(String objectKey, byte[] content, String contentType);
}

public interface EventPublisher {
    void publishInvoiceCreated(String invoiceId);
}
~~~

A poor port often exposes raw SDK request classes directly, such as forcing a business service to accept **PutObjectRequest** or **BlobUploadOptions**. That makes swapping providers harder while offering no clarity of responsibility.

## 10. Performance, Synchronous, Asynchronous, and Reactive Models

The convenience of a template or repository **does not inherently mean faster or slower**. Performance usually depends on networking, payloads, connection pooling, batching, serialization, pagination, retries, and execution models.

- With **blocking SDK/JDBC**, calls wait on I/O and occupy a thread while waiting. Bound concurrency, connection pools, timeouts, and processing queue capacities.
- With **async SDKs** or asynchronous listeners, throughput can improve under heavy I/O, but you must manage backpressure, retries, shutdown, and completion outcomes.
- With **reactive repositories/clients**, gains depend on true non-blocking behavior across the entire pipeline; calling a blocking SDK inside a reactive chain still causes blocking without proper isolation.
- A template may use a sync or async SDK underneath depending on version. Read the template's exact contract before assuming a call is non-blocking.
- Features like streaming uploads, batch writes, bulk inserts, or consumer concurrency should be chosen based on real load and the specific service.

For messaging, distinguish **message publish latency** from **consumer business processing completion time**. For repositories, pagination and indexed queries usually govern cost far more than whether a Spring Data abstraction is used.

## 11. Security and Permissions: Abstractions Do Not Replace Identity

Whether using a starter, template, repository, or SDK, the application still needs an appropriate identity and access permissions:

| Provider | Preferred Cloud Identity | Permissions to Verify |
| --- | --- | --- |
| AWS | Workload IAM role, appropriate credential chain | IAM policies, resource/bucket policies, and specific actions |
| Azure | Managed Identity or appropriate identity via Azure SDK | Azure RBAC, policies, and resource network settings |
| Google Cloud | Workload Identity / service account + ADC | IAM roles/permissions on projects, buckets, topics, or secrets |

Managed databases also involve database-level authentication/authorization, network/private endpoints, TLS, and sometimes cloud-specific identity mechanisms. **Spring Boot starting successfully does not prove cloud permissions are valid**; many SDKs only acquire tokens or hit endpoints on the first request.

Keep the two authorization layers distinct: whether the **end user** is permitted to run the use case and whether the **workload identity** is permitted to access the cloud resource. A client running with a high-privilege role cannot replace business authorization. Never log tokens, access keys, or sensitive connection strings; use secret management and proper rotation policies.

## 12. Testing Plan by Abstraction Level

| Testing Level | What to Verify | Appropriate Technique |
| --- | --- | --- |
| **Service unit test** | Business rules, port selection, errors, and idempotency | Mock/fake **DocumentStorage**, **EventPublisher**, repositories |
| **Unit/adapter test** | Request/response/exception mapping of template or SDK | Mock client, verify bucket/key, queue, converters, error codes |
| **Spring context test** | Starters, properties, conditional beans, qualifiers, bean wiring | ApplicationContextRunner or configured context tests |
| **Emulator integration test** | Real SDK communication, serialization, listeners, read/write flows | LocalStack for supported AWS parts, Azurite for Azure Blob, appropriate GCP emulators if provided |
| **Cloud smoke test** | Identity/roles, permissions, networking, endpoints, quotas, policies, cloud traits | Isolated test resources, real workload identity, cleaned-up test data |

Example **DocumentUploadService** validates payload, builds an object key from an invoice ID, and calls the port. Unit tests verify that exact behavior without needing AWS credentials:

~~~java
// DocumentUploadService.java
public class DocumentUploadService {
    private final DocumentStorage storage;

    public DocumentUploadService(DocumentStorage storage) {
        this.storage = storage;
    }

    public void uploadInvoice(String invoiceId, byte[] pdf) {
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException("PDF is empty");
        }
        storage.save("invoices/" + invoiceId + ".pdf",
            pdf, "application/pdf");
    }
}
~~~

~~~java
// DocumentUploadServiceTest.java
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;

class DocumentUploadServiceTest {
    @Test
    void delegatesValidInvoiceToStoragePort() {
        DocumentStorage storage = mock(DocumentStorage.class);
        DocumentUploadService service = new DocumentUploadService(storage);
        byte[] bytes = {10, 20};

        service.uploadInvoice("123", bytes);

        verify(storage).save(
            eq("invoices/123.pdf"), same(bytes), eq("application/pdf"));
    }
}
~~~

This test confirms the **service** selects the right key and content type and delegates the data to **DocumentStorage**. You can add an empty-PDF test to verify the service throws without calling the port. During integration, separately test the SDK adapter, Spring configuration, and cloud permissions; unit tests do not prove an object was actually persisted in a bucket.

Emulators may not fully support IAM/RBAC, rotation, consistency, dead-letter handling, or networking/private endpoints. Combining context tests, emulators, and cloud smoke tests yields a much more reliable picture than running only unit tests or clicking through the cloud UI.

## 13. Common Abstraction-Selection Mistakes

| Situation | Why It Is Unsound | How to Fix It |
| --- | --- | --- |
| Using a JPA repository to model S3 objects or message queues | Does not reflect storage/messaging semantics | Use a storage port + template/SDK or messaging adapter |
| Using SDK clients inside controllers and business services | Leaks SDK request/exception types; hard to test and swap providers | Put SDK calls in an adapter; expose only required contracts via ports |
| Adding a starter yet instantiating SDK clients per request | Duplicates config, wastes connections, breaks lifecycle | Inject the Spring-managed singleton client |
| Using a template for a provider API it does not support | Loses control over specialized features | Call the direct SDK in the adapter needing that capability |
| Declaring custom client beans without checking auto-config | Unexpected back-off, duplicate beans, or wrong client used | Inspect condition report, bean types/names/qualifiers |
| Assuming repository transactions include message publishing | Databases and queues do not share a transaction automatically | Outbox, idempotency, or compensating workflows |
| Pursuing multi-cloud by unifying providers via method names alone | Hides real differences in guarantees and permissions | Standardize shared contracts; express real differences in adapters |
| Treating 403 errors as template/repository bugs | Error likely stems from identity, policy, or resource permissions | Trace SDK response, credentials, and IAM/RBAC |

When deployment fails, inspect along exact boundaries: **dependency/starter → bean creation conditions → properties → adapter/template/repository → SDK/driver → credentials/network → service**. A missing bean at startup is fundamentally different from a runtime **PermissionDenied** error; increasing retries will never fix broken IAM configuration.

## 14. Decision-Making Exercises

**Exercise 1 — Storing profile images.** A REST API must upload images up to 5 MB into a bucket; the app runs on AWS in year one and may move to Azure later. Choose **starter**, **template or SDK**, whether a port is needed, and what must be tested. Hint: prioritize verifying upload permissions, file size limits, object keys, and lifecycle; use a port if you want unit tests and to avoid leaking S3 request classes.

**Exercise 2 — Order synchronization.** After saving an order to managed PostgreSQL, an event must be published to SQS or Pub/Sub; consumers may reprocess messages. Choose **Spring Data repository**, **messaging template/listener**, or **SDK**, then propose a transactional outbox and consumer idempotency. Explain why publishing a message successfully does not mean downstream business processing is complete.

**Exercise 3 — Specialized API.** A system needs multipart uploads, conditional writes, error classification, and custom retries. A template only supports basic uploads. Should you wrap the template in multiple layers or use the SDK? Propose an adapter, metrics, and test cases for duplicate writes, timeouts after a successful write, and permission-denied errors.

**Exercise 4 — Choosing a datastore.** An application has relational data, join queries, and multi-table transactions; the team is weighing RDS PostgreSQL, Cloud SQL PostgreSQL, and a NoSQL service. When can you keep the same **JpaRepository**? When must you change the data model and use a different repository/SDK?

**Exercise 5 — Secrets.** A system running on Azure has Managed Identity and reads an API key from Key Vault. Decide between config integration and runtime SDK based on secret lifecycle and rotation requirements; describe which permissions to verify and how to prevent leaking keys in logs.

## 15. Key Takeaways

- **Starters** bring dependencies and auto-configuration into Spring Boot; **templates**, **repositories**, and **direct SDKs** are the programming APIs. They can be combined.
- **Repositories** excel for aggregates and data queries when a Spring Data module fits; **templates** are convenient for repetitive framework-covered operations; **SDKs** fit when full provider capabilities or specialized configuration are needed.
- Choose based on **business contracts, API features, delivery/transaction semantics, sync/async behavior, security, testability, and operational complexity**, not code snippet brevity.
- For multi-cloud, use **ports and provider adapters** to keep business boundaries clean; never assume AWS, Azure, and Google Cloud share identical permissions, errors, or data guarantees.
- Separate **API selection decisions** from **identity, IAM/RBAC, timeout/retry, and connection management**: no matter how convenient an abstraction is, these still require verification.
