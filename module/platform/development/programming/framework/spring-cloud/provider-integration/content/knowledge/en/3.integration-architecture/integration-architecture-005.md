# Placing Business Interfaces and Provider Adapters at the Right Boundary

A Spring Boot application can call **S3Client**, **BlobServiceClient**, **Storage**, or a messaging client directly from a business service. This is fast early on, but if all business services know about buckets, containers, SDK request types, and provider error codes, every cloud change ripples into business logic. Conversely, creating an interface for every single SDK method does not produce better architecture either: it merely adds pass-through layers while still bringing the provider's model directly into the application.

The solution is to define **responsibility boundaries** before placing interfaces. The business layer describes **what the application needs**; an outbound port (an interface owned by the application) expresses a contract meaningful to the use case; the provider adapter resolves **which cloud API accomplishes it**. Real differences in permissions, consistency, retries, idempotency, and transactions must be represented explicitly—they cannot be erased simply by naming a shared interface.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries, including identity/permissions, storage, messaging, data, secrets, integration testing, and provider comparisons. This lesson focuses on **designing ports and adapters**, placing each decision at the right layer, and organizing Spring beans so the layers collaborate cleanly in real applications.

## 1. Learning Outcomes

After this lesson, you can:

- Distinguish **inbound adapter**, **application service**, **outbound port**, **provider adapter**, **Spring Cloud integration**, and **SDK client**.
- Determine who owns interfaces and data types; keep SDK requests/responses/exceptions at the proper boundary.
- Design ports narrow enough to reflect business semantics and the guarantees a use case actually needs.
- Write a **DocumentStore** implementation using Spring Boot, Spring Cloud AWS, and S3; outline Azure Blob and Google Cloud Storage adapters with the same contract.
- Organize multi-provider configuration, identity, retries, logging, and error handling without letting adapters decide business permissions.
- Identify transaction boundaries across databases, storage, and message brokers; unit-test business services independently of the cloud and test adapters by contract.

## 2. Define Boundaries Before Writing Code

| Layer / component | Question Answered | Example Responsibilities | Should Not Contain |
| --- | --- | --- | --- |
| **Inbound adapter** | Over what protocol do users or external systems call the app? | REST controller receiving a PDF, validating HTTP format, mapping results to status codes | S3 PutObject calls or IAM permissions |
| **Application service (use case)** | When is the operation allowed, and which steps must coordinate? | Verify invoice allows attaching a PDF, decide object key and metadata to save | Types like **PutObjectRequest**, **BlobClient**, endpoints, or tokens |
| **Outbound port** | What commitment does the app require from an external service? | **DocumentStore.put(DocumentWrite)**, **DomainEventPublisher.publish(...)** | S3/Service Bus specifics unless business logic requires them |
| **Provider adapter** | How is the application contract translated to the provider? | Map document to bucket/key, call SDK, translate error codes, respect API limits | Deciding which user may view an invoice or billing rules |
| **Spring Boot / Spring Cloud** | Who creates, configures, and injects beans? | Auto-configure SDK clients, templates, listeners, properties, and lifecycles per starter | Document/invoice business rules |
| **SDK + managed service** | How is the request sent and executed? | Credentials, HTTP/gRPC, Cloud Storage, IAM/RBAC, API errors | End-user authorization rules inside the application |

In the **ports and adapters (hexagonal architecture)** model, the application service depends on the outbound port; the provider adapter **implements** the port. The port is a contract decided by the application side needing the service, while the adapter depends on both the port and the SDK. At runtime, calls flow from the service through the adapter bean, and then to the cloud client.

~~~mermaid
flowchart LR
    U[HTTP Client] --> C[REST controller: inbound adapter]
    C --> A[InvoiceDocumentService: use case]
    A --> P[DocumentStore: outbound port]
    P --> D[S3DocumentStore: provider adapter]
    D --> SDK[S3Client: AWS SDK]
    SDK --> CLOUD[Amazon S3]
    AUTO[Spring Cloud AWS starter] -. auto-config / inject .-> SDK
    ID[Credential provider] -. supplies identity .-> SDK
~~~

The diagram depicts the **runtime call flow**. Source-code dependency direction is different: **InvoiceDocumentService → DocumentStore ← S3DocumentStore → S3Client**. This lets you swap the S3 adapter for Azure/GCP or a fake during testing without touching business code.

A small project using a single cloud can still place the SDK directly in an **infrastructure service** and inject that service into the use case if the abstraction overhead is not yet worthwhile. A dedicated port becomes valuable when a well-defined contract aids testing, backend switching, provider error isolation, or reusing the same use case. There is no need to put a port around every utility method.

## 3. Where Do Ports Live and Who Owns Them?

**Ports typically live in the application/core package** or in the module defining use cases. They must be readable and understandable without importing any SDK. Example logical structure:

~~~text
com.example.invoice
├── application
│   ├── InvoiceDocumentService.java
│   ├── port
│   │   └── DocumentStore.java
│   └── model
│       ├── DocumentWrite.java
│       └── StoredDocument.java
├── adapter
│   ├── in
│   │   └── InvoiceDocumentController.java
│   └── out
│       ├── aws
│       │   └── S3DocumentStore.java
│       ├── azure
│       │   └── AzureBlobDocumentStore.java
│       └── gcp
│           └── GcsDocumentStore.java
└── configuration
    └── ProviderWiring.java
~~~

These directories are an **example code organization**, not a mandatory Spring Boot rule. In multi-module Java, you can place **application/core** in a module with no SDK dependencies so the **infrastructure** module imports core and the SDKs. In a single Spring Boot module, you can use the same package layout and enforce dependencies via code review or architecture tests.

**The right place for a port** is where a request already carries business meaning without yet turning into provider terminology:

- **Too early:** creating a generic **CloudClient** with **execute**, **send**, **read** methods and **Object** parameters. The contract is vague and fails to reflect the use case.
- **Too late:** defining **S3Port.putObject(PutObjectRequest)**. It has “port” in the name, yet the business layer still imports the AWS SDK and knows about specific buckets/keys.
- **Just right:** **DocumentStore.put(DocumentWrite)** with the document ID, key, content type, and result the application genuinely needs. The adapter decides how to convert these fields into **PutObjectRequest**, **BlobUploadOptions**, or **BlobInfo**.

Do not turn a port into a mirror of the entire SDK. Methods and data types should grow according to **use cases**, not the catalog of available cloud features.

## 4. Start from the Contract and Required Guarantees

Suppose the use case is: “When a user has permission on an invoice, the app receives a PDF file and stores it in object storage; then it saves a file reference for later download.” Before writing the port, determine:

1. **Identity:** which invoice ID does the document belong to? Is the object key stable across retries?
2. **Input:** PDF contents, content type, allowed size, and owning tenant.
3. **Output:** does the use case only need the key, or also a version ID, checksum, or time-limited URL?
4. **Write semantics:** overwrite allowed, create-once unique, versioning, or conditional writes?
5. **Errors:** how are permission denied, resource not found, transient errors, and invalid data categorized?
6. **Completion expectations:** when the method returns successfully, has the cloud confirmed the write? Are there subsequent database updates or event publishes?

If the application only needs to save the file and return the key, the port can be small:

~~~java
// DocumentWrite.java - application model
public record DocumentWrite(
    String objectKey,
    byte[] content,
    String contentType
) {}
~~~

~~~java
// StoredDocument.java - application model
public record StoredDocument(String objectKey) {}
~~~

~~~java
// DocumentStore.java - outbound port
public interface DocumentStore {
    StoredDocument put(DocumentWrite document);
}
~~~

This is a **synchronous** sample suited to a simple use case. The **byte[]** field is for illustration; real systems must bound file size and avoid assuming a record holding a byte array is immutable (arrays can be mutated externally). For large files, a streaming contract or direct upload flow is more appropriate. This port **does not promise** a database transaction or “exactly once.” If overwrites must be prevented, add an explicit create-if-absent/conditional-write guarantee to the contract and implement it using each provider's supported mechanism.

**The return contract should contain only information business logic needs.** Do not return **PutObjectResponse**, **BlobProperties**, or raw SDK objects to the service. If you genuinely need a version or checksum, define a value type with shared semantics and explicitly document which providers satisfy it; never assume **ETag** means the exact same checksum across every cloud.

## 5. Application Service Knows Only Business Logic and Ports

The following code deliberately omits AWS, Azure, and GCP names and cloud configuration details from the application service. The example assumes user permission checks on the invoice have already been handled by the use case's authorization step; production code must enforce that check before calling **put**.

~~~java
// InvoiceDocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InvoiceDocumentService {
    private final DocumentStore documentStore;

    public InvoiceDocumentService(DocumentStore documentStore) {
        this.documentStore = documentStore;
    }

    public StoredDocument saveInvoicePdf(UUID invoiceId, byte[] pdf) {
        if (invoiceId == null) {
            throw new IllegalArgumentException("Invoice ID is required");
        }
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException("PDF cannot be empty");
        }

        String objectKey = "invoice-documents/" + invoiceId + ".pdf";
        return documentStore.put(
            new DocumentWrite(objectKey, pdf, "application/pdf"));
    }
}
~~~

Here the service decides a **key meaningful to the invoice**. Use a validated UUID instead of concatenating a user-supplied path string directly into the key; in multi-tenant applications, include the tenant ID in the model and verify ownership before creating or accessing objects. Simply partitioning objects by tenant **does not replace authorization**.

**A stable key directs retries to the same resource**; it does not by itself make requests idempotent or unique-create. If two different PDFs use the same invoice ID, re-writing can overwrite the older object; versioning, preconditions, or versioned identifiers must be decided by business logic. The rule “only one final PDF may be submitted” belongs to the use case, not the S3 adapter.

## 6. Spring Cloud AWS Adapter Translates the Contract to the SDK

With **Spring Boot 3 + Spring Cloud AWS 3.x** and AWS SDK for Java v2, one approach is adding the S3 starter so Spring provides an **S3Client** bean. The adapter uses the injected client and translates **DocumentWrite** into an AWS request.

Illustrative Maven dependency, with versions managed via a compatible BOM:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Adapter:

~~~java
// S3DocumentStore.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

@Component
@ConditionalOnProperty(
    prefix = "app.document-store",
    name = "provider",
    havingValue = "aws"
)
public class S3DocumentStore implements DocumentStore {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStore(
            S3Client s3,
            @Value("${app.document-store.aws.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public StoredDocument put(DocumentWrite document) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(document.objectKey())
            .contentType(document.contentType())
            .build();

        try {
            s3.putObject(request, RequestBody.fromBytes(document.content()));
            return new StoredDocument(document.objectKey());
        } catch (S3Exception ex) {
            throw new DocumentStoreException(
                "Storage service rejected the request", ex);
        } catch (SdkClientException ex) {
            throw new DocumentStoreException(
                "Storage client could not complete the request", ex);
        }
    }
}
~~~

~~~java
// DocumentStoreException.java - exception at the port boundary
public class DocumentStoreException extends RuntimeException {
    public DocumentStoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  document-store:
    provider: aws
    aws:
      bucket: ${APP_DOCUMENT_BUCKET}
~~~

**spring.cloud.aws.region.static** configures the AWS client in Spring Cloud AWS. **app.document-store.provider** and **app.document-store.aws.bucket** are **application-defined** properties to choose the adapter and supply the bucket. **APP_DOCUMENT_BUCKET** is a resource name from the environment; do not put access keys/secret keys in YAML. The SDK should receive identity from the credential chain/role attached to the workload and be granted least-privilege permissions to write only to the right bucket/prefix.

In this example the adapter uses **S3Client** directly; if the application prefers a supported template API, the adapter can call **S3Template**, which in turn calls the SDK. Choosing between template and SDK is an adapter detail and does not force changes to **DocumentStore** as long as the contract holds.

In production, classify errors more finely: **AccessDenied/403** is usually not worth retrying, **throttling/5xx/timeouts** may be transient, and **invalid request** errors should return appropriate feedback to the caller. The simple code above retains the cause for diagnostics; retries, HTTP mapping, and user-facing messages require explicit policies that avoid exposing sensitive tokens/bucket details in responses.

## 7. Switching Providers: Keep the Port, Swap the Adapter and Configuration

For the same **DocumentStore.put** need, adapter shapes differ:

| Role | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Service | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Common Java client | AWS SDK v2 **S3Client** | Azure SDK **BlobServiceClient/BlobClient** | Google Cloud Java **Storage** |
| Target resource | Bucket + object key | Storage account + container + blob name | Project + bucket + object name |
| Typical SDK call | **putObject** | **BlobClient.upload(...)** or appropriate upload options | **Storage.create(...)** / writer API |
| Common runtime identity | IAM role/default credentials chain | Managed Identity/DefaultAzureCredential | ADC/workload identity/service account |
| Access control | IAM and bucket policies | Azure RBAC and storage policies | IAM on project/bucket |
| Things to watch | Versioning, preconditions, object ownership | Block blobs, ETag conditions, SAS | Generation preconditions, object versioning, signed URLs |

The Azure adapter is designed to receive **BlobServiceClient** or an appropriate client/template via Spring Cloud Azure, locate the container/blob, and upload bytes/content type via the Azure SDK. The GCP adapter uses a **Storage** client/template configured via Spring Cloud GCP, builds **BlobInfo** for the bucket/object, and calls the Cloud Storage API. Both return **StoredDocument** and translate SDK exceptions into port-level errors.

~~~mermaid
flowchart TD
    A[InvoiceDocumentService] --> P[DocumentStore port]
    P -->|provider=aws| W[S3DocumentStore]
    P -->|provider=azure| Z[AzureBlobDocumentStore]
    P -->|provider=gcp| G[GcsDocumentStore]
    W --> C1[S3Client]
    Z --> C2[Azure Blob client]
    G --> C3[Google Cloud Storage client]
    C1 --> S1[Amazon S3]
    C2 --> S2[Azure Blob Storage]
    C3 --> S3[Google Cloud Storage]
~~~

The diagram shows **deployment options**; it does not mean all three adapters must be active in a single environment. When using **@ConditionalOnProperty** to pick a provider, ensure exactly one **DocumentStore** bean exists. If no valid provider matches, the service can fail with a missing bean; if multiple adapters are active, injection by type becomes ambiguous. For systems intentionally using multiple providers in the same runtime, use **@Qualifier** or an explicit business router rather than relying on Spring auto-selection.

Never claim “switching providers is just changing one property” when underlying versioning, size limits, streaming capabilities, consistency, encryption, permissions, and billing models differ. A port stays stable **only within the scope of genuinely shared contracts**; if a use case needs a provider-specific feature, extend the contract intentionally or model a dedicated capability for that provider.

## 8. Designing Contracts: Narrow Enough, Not Over-Abstracted

### 8.1. Avoid Interfaces That Mirror the SDK

Unsuitable example:

~~~java
// DO NOT place in the application layer:
public interface StoragePort {
    software.amazon.awssdk.services.s3.model.PutObjectResponse put(
        software.amazon.awssdk.services.s3.model.PutObjectRequest request);
}
~~~

The business service still has to construct **PutObjectRequest**, know about buckets, and process **PutObjectResponse**; the interface only relocates the call without creating a **dependency boundary**. Moving to Azure still forces changing the service's API and data types.

An overly broad abstraction is also hard to maintain:

~~~java
// DO NOT design merely to cover every SDK:
public interface CloudEverything {
    Object execute(String provider, String operation, Object payload);
}
~~~

Code ends up full of runtime casts, hard to verify inputs/outputs, and unclear about side-effect guarantees. If the shared operation is simply reading/writing PDFs, **DocumentStore** is far clearer.

### 8.2. Do Not Hide Differences Business Logic Actually Needs

Suppose business logic requires “create the document once only, never overwrite.” A port with only **put** and no write semantics will fall short: S3, Blob, and GCS implement conditional writes differently. An explicit operation may be needed:

~~~java
public interface ImmutableDocumentStore {
    // Throws DocumentAlreadyExists if the object already exists.
    StoredDocument createIfAbsent(DocumentWrite document);
}
~~~

**DocumentAlreadyExists** must be an application-defined common error; each adapter maps the corresponding status/precondition. Simply doing separate “HEAD then PUT” calls leaves a race condition between concurrent requests. For unique creation, use the atomic conditional request mechanism supported by each provider and test real race conditions; if a provider cannot satisfy it, never claim the contract is guaranteed.

Similarly, if the application needs **version IDs**, **ETag** conditions, signed URLs, or TTL-based deletion, determine whether it is a core requirement across all providers or a dedicated capability. Do not bundle dozens of optional parameters into one generic request where each adapter silently ignores unsupported parameters.

### 8.3. When Do You Not Need a Custom Port?

There is no rule forcing every service to have an interface. For example, an internal batch job dedicated to AWS S3 with three SDK calls and little business logic can simply use a Spring **S3ArchiveService** in the infrastructure module. Or if **Spring Data JpaRepository** already models the data operations accurately, a service can inject the Spring Data repository directly instead of creating a redundant interface mirroring every CRUD method.

Add a port when it **clearly names an application capability**, isolates dependencies, creates a testing seam, or expresses a contract needing multiple implementations. Do not add one merely to obey a “every class needs an interface” rule.

## 9. Separate Ports by Service Kind and Semantics

An application may use storage, messaging, data, and secrets simultaneously; do not create a single **CloudProviderPort** managing all four:

| Use Case Need | Potentially Suitable Port | Provider Adapter |
| --- | --- | --- |
| Save invoice PDF | **DocumentStore.put/get** by document key | S3 / Azure Blob / GCS |
| Notify that invoice was issued | **InvoiceEventPublisher.publish** | SQS/SNS / Service Bus / Pub/Sub |
| Persist invoice data | **InvoiceRepository** or appropriate Spring Data repository | PostgreSQL on RDS/Azure Database/Cloud SQL; datastore-specific repository/SDK when needed |
| Read partner token | **PartnerCredentialReader.get** if needed at runtime | AWS Secrets Manager / Azure Key Vault / Google Secret Manager |

**A port describes business intent**, not an overly generic technical action. **InvoiceEventPublisher** is more concrete and testable than **CloudMessaging.execute(action)**. Yet if multiple modules need to publish events, a stable infrastructure-meaningful port like **DomainEventPublisher** can be reasonable; abstraction boundaries are governed by real contracts and ownership.

### 9.1. Messaging: Publisher and Consumer Boundaries

~~~mermaid
flowchart LR
    A[Invoice service] --> P[InvoiceEventPublisher]
    P --> B[Messaging publisher adapter]
    B --> Q[SQS / Service Bus / PubSub]
    Q --> L[Listener / subscriber adapter]
    L --> U[InvoiceEventHandler]
~~~

**Successful publish** generally means only that the broker accepted the message; it does not prove a consumer completed processing. The port can return a publish result or async completion reflecting this meaning, avoiding promises of “already processed” when the broker gives no such guarantee.

The inbound listener adapter is responsible for converting provider payloads and metadata into a valid command/event for the handler and acknowledging messages per the broker's rules. The business handler owns idempotency, state transitions, and business validation. SQS visibility timeouts, Service Bus locks, and Pub/Sub ack deadlines differ; the adapter must track handler completion before acking/completing if that is the required contract.

### 9.2. Data Access: Do Not Force Every Datastore into JPA

For managed PostgreSQL on AWS RDS, Azure Database, or Google Cloud SQL, applications can use Spring Data JPA/JDBC and standard drivers; repository boundaries stay relatively stable. For DynamoDB, Cosmos DB, Firestore, or Spanner, partition/query models, transactions, and consistency differ substantially. Define a shared repository port only when **required queries and guarantees can genuinely be met**; never copy **JpaRepository** onto every datastore under a new name.

### 9.3. Secrets: Config and Runtime Boundaries

Secrets needed only at startup can be supplied via config integration; secrets read or rotated at runtime may need a dedicated client/adapter. Application ports should never return raw cloud SDK secret responses or log secret values. Decide caching, TTL, refresh, read permissions, and secret lifetimes. Having the same secret name across three clouds does not mean permissions or rotation flows are identical.

## 10. Proper Placement for Identity and Authorization

There are **two independent security questions**:

1. **Is the end user allowed to perform this use case?** This belongs to application/domain authorization and inbound security. For example, user A must not download user B's invoice PDF even though the backend service has permission to read the entire bucket.
2. **Is the workload allowed to call the cloud resource?** This belongs to cloud identity and resource policy configuration. AWS uses IAM roles/credentials chain, Azure typically uses Managed Identity and RBAC, and Google Cloud uses ADC/workload identity/service accounts with IAM.

Adapters must not read credentials from source code or write credentials to logs. Spring Cloud starters and SDK clients are configured to acquire identity from the runtime environment; the adapter receives the **already-configured client bean** and then calls the service. Valid credentials do not imply sufficient permissions; **403/AccessDenied/PermissionDenied** errors typically require checking the active identity, action, resource, and policies.

| Location | What to Do | Example |
| --- | --- | --- |
| Controller / security boundary | Authenticate caller, validate request size/content type | Reject unauthenticated requests before reading large bodies |
| Application service | Verify ownership and use-case permissions | Invoice ID belongs to the acting tenant |
| Provider adapter | Select resource/key, prevent data leaks in errors and logs | Never expose connection strings or secrets in public exceptions |
| Infrastructure/client config | Bind workload identity, endpoint, region/project, and timeouts | Role may only write to the application's bucket/prefix |
| Managed service | Enforce workload IAM/RBAC/resource policies | Deny actions when resource permissions are missing |

Never treat an **object key prefix** as the sole access-control measure: the application must authenticate/authorize requests, and IAM/RBAC must restrict which resources the workload can actually access.

## 11. Errors, Retries, and Decisions: At Which Boundary?

Not every cloud error should pass straight through to a controller as a raw SDK exception. Distinguish **technical error classification** from **business decisions**:

| Situation | What the Adapter Knows | What Application/Controller Must Decide |
| --- | --- | --- |
| S3 returns **AccessDenied** | Provider code, status 403, request ID | Report an operational error appropriately; do not assume the end caller lacks invoice permission |
| Blob/GCS returns precondition failure | Write precondition violated | Is this a conflict (document exists), should a new version be created, or reject? |
| SDK timeout after PUT | No final response received; cloud **may have written** | Check state, apply idempotency, and follow retry policy |
| Throttling/429/5xx | Service temporarily unavailable or quota hit | Should we retry, how many times, overall deadline, or report temporary failure? |
| Invalid input / business rule violation | Adapter should not decide user permissions | Validate at application/inbound; return proper client error to caller |

The adapter can map exceptions to **DocumentStoreUnavailable**, **DocumentAlreadyExists**, **DocumentStoreForbidden**, or a categorized **DocumentStoreException**. Exact naming is chosen by the application. Preserve the root cause internally so request IDs/cloud error codes are available for debugging, but never let HTTP responses leak tokens, secrets, connection strings, or sensitive resource names.

Retries in the SDK, Spring Retry, Reactor, or messaging frameworks **can stack**, causing unintended bursts of calls. Limit retries to transient errors, add exponential backoff/jitter, overall deadlines, quotas, and idempotency. In particular, an adapter should only auto-retry side-effecting operations when the request's idempotency contract is well understood.

The **application service** decides the business outcome when saving a PDF fails: stay pending, report an error, retry under an operation ID, or run cleanup. The **adapter** should only know how to turn that decision into safe provider API calls.

## 12. Transaction Boundaries: A Port Does Not Create a Distributed Transaction

Suppose a use case performs three steps:

~~~text
InvoiceApplicationService
  1. InvoiceRepository.save(metadata)      -> managed PostgreSQL
  2. DocumentStore.put(pdf)                -> S3/Blob/GCS
  3. InvoiceEventPublisher.publish(event)  -> SQS/Service Bus/PubSub
~~~

**@Transactional** on Spring Data JPA/JDBC usually manages only the database transaction and does not encompass object storage or message brokers. If step 2 succeeds and step 3 fails, rolling back the database does not delete the uploaded PDF. If publish succeeded and the app lost connectivity before receiving the response, resending can produce duplicate events.

One possible design:

- Write **invoice state** and an **outbox event** record in the same database transaction.
- Have a worker read the outbox and publish messages; when consumers receive them, use event IDs for idempotent handling.
- Store PDFs under a stable key, track **PENDING/READY/FAILED** states, and define retry/cleanup if a step fails.
- Use appropriate preconditions/versioning when two concurrent requests store the same document.

Exact solutions depend on latency and consistency requirements. **Transactional outbox** helps synchronize the database with events under an eventual delivery model; it does not make object storage join the SQL transaction. Adapters should not simulate two-phase commit when cloud services offer no such guarantee.

## 13. Do Synchronous, Asynchronous, and Streaming Change the Port?

**Potentially yes**, if the completion model is part of the contract. For example, a synchronous port:

~~~java
public interface DocumentStore {
    StoredDocument put(DocumentWrite document);
}
~~~

When the application genuinely needs non-blocking I/O, you can define:

~~~java
import java.util.concurrent.CompletionStage;

public interface AsyncDocumentStore {
    CompletionStage<StoredDocument> put(DocumentWrite document);
}
~~~

Or for an application built end-to-end on Reactor/WebFlux:

~~~java
import reactor.core.publisher.Mono;

public interface ReactiveDocumentStore {
    Mono<StoredDocument> put(DocumentWrite document);
}
~~~

**CompletionStage** is a standard Java abstraction, whereas **Mono** introduces a Reactor dependency into the application port. Either can be reasonable, provided you define a clear contract around **when the request starts**, completion, cancellation, and retries; never alter signatures just because a provider happens to have an async client. Wrapping a blocking SDK in **Mono** does not make network I/O non-blocking. For large files, **byte[]** still consumes memory; you need an appropriate stream/chunk or direct-upload contract with backpressure and buffer bounds.

A single port should not simultaneously expose sync/async/reactive variants if the use case only uses one model. Choose based on inbound APIs, expected load, SDK/driver capabilities, transactions, and operations. Nor should you replace all of JPA/JDBC with `Mono` when the system still uses a blocking database.

## 14. Selecting and Wiring Implementations in Spring

Spring Boot can auto-configure SDK clients via starters, while **DocumentStore** is an application bean. Options include:

| Context | Suggested Wiring | What to Verify |
| --- | --- | --- |
| One provider per environment | Each adapter has **@ConditionalOnProperty(provider=...)** | Exactly one **DocumentStore** matches; valid config |
| Multiple fixed providers running together | Named beans and explicit **@Qualifier** | Use cases pick the right adapter, avoiding **NoUniqueBeanDefinitionException** |
| Provider chosen per tenant/request | A router implementing **DocumentStore** holding a map of configured adapters | Never trust caller-supplied provider strings blindly; verify permissions and tenant isolation |
| Running unit tests | Fake/mock **DocumentStore** | Tests require no SDK or cloud credentials |
| Integration tests | Real adapter bean against emulator/test resources | Client endpoints, bean graph, and security config are correct |

When building a **routing adapter**, the business service still calls a single port. The router uses a trusted selection source (such as validated tenant config) to delegate to the corresponding adapter. If routing could change between retries, record the chosen **provider + resource + object ID** to prevent a document from being saved across two backends unintentionally.

**There is no need** to manually define three client beans just to have three adapters if starters already auto-configure what is needed. When defining custom clients, inspect **@ConditionalOnMissingBean**, the condition evaluation report, and how templates/listeners acquire clients. Never blindly enable **allow-bean-definition-overriding** to hide wiring conflicts.

## 15. Testing Along Boundaries Without Cloud Dependencies in Unit Tests

### 15.1. Application Service Unit Tests

Verify that the service constructs the right key and calls the port with expected data. Example with Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class InvoiceDocumentServiceTest {
    @Test
    void savesPdfUsingBusinessKeyWithoutCloudSdk() {
        DocumentStore store = mock(DocumentStore.class);
        when(store.put(any(DocumentWrite.class))).thenAnswer(call -> {
            DocumentWrite request = call.getArgument(0);
            return new StoredDocument(request.objectKey());
        });

        InvoiceDocumentService service = new InvoiceDocumentService(store);
        UUID invoiceId = UUID.randomUUID();
        byte[] pdf = {1, 2, 3};

        StoredDocument result = service.saveInvoicePdf(invoiceId, pdf);

        ArgumentCaptor<DocumentWrite> captor =
            ArgumentCaptor.forClass(DocumentWrite.class);
        verify(store).put(captor.capture());
        DocumentWrite saved = captor.getValue();
        assertEquals("invoice-documents/" + invoiceId + ".pdf",
            saved.objectKey());
        assertArrayEquals(pdf, saved.content());
        assertEquals("application/pdf", saved.contentType());
        assertEquals(saved.objectKey(), result.objectKey());
    }
}
~~~

This test verifies **service behavior**, not just mocking for its own sake. Add tests for empty PDFs/null IDs, permission checks, retries by operation ID, and validation before the port is called. Unit tests require no credentials and do not prove the adapter actually uploaded anything.

### 15.2. Provider Adapter Unit/Contract Tests

For S3, you can mock **S3Client** to verify the adapter builds a **PutObjectRequest** with the right bucket/key/content type, and simulate **S3Exception** to verify translation to **DocumentStoreException**. Similarly, the Azure adapter verifies container/blob selection, and the GCP adapter verifies bucket/object, metadata, and exception mapping.

A **contract test suite** is valuable for running shared cases against each **DocumentStore** implementation: put then get, overwriting the same key, permission denied, invalid input, missing object, timeouts/retries if defined by the contract, and race conditions on create-if-absent. If an adapter cannot satisfy a guarantee, revise the contract or state the capability explicitly; do not pretend behaviors match merely because method signatures do.

### 15.3. Integration Tests and Cloud Smoke Tests

| Level | Tools/Conditions | What Is Verified |
| --- | --- | --- |
| Spring context | **ApplicationContextRunner**, context tests | Correct adapter per provider property, bean dependencies injected |
| Emulator | LocalStack for supported AWS parts; Azurite for Blob; appropriate emulator or test project for GCP | Serialization, requests/responses, read/write flows, and basic errors |
| Cloud test environment | Dedicated test bucket/container/project, real workload identity, least privilege | IAM/RBAC, endpoints/regions, TLS/networking, quotas, and provider traits |
| Resilience tests | Timeouts, throttling, errors returned after side effects occur | Idempotency, bounded retries, cleanup, and observability |

Emulators do not fully simulate IAM/RBAC, private endpoints, quotas, retries, consistency, or real cloud behavior. Test data must be isolated, cleaned up, and free of production secrets. Never turn on debug logging to print access keys/tokens, request bodies, or sensitive files.

## 16. Evaluating Whether a Boundary Is Sound

Ask yourself:

1. If **S3Client** is replaced with **BlobClient**, do **InvoiceDocumentService** and its use-case unit tests need to import the new SDK?
2. Does the port clearly specify what **put** guarantees regarding overwrites, completion, and errors?
3. Can the adapter change authentication, endpoints, or retries without modifying business rules?
4. Are end-user permissions checked before calling the cloud, and is the workload identity restricted via IAM/RBAC?
5. Can a request that times out after reaching the cloud be handled safely using a stable key/operation ID?
6. Do business unit tests run without network access, credentials, Spring beans, or cloud emulators?
7. If a use case needs a provider-specific feature, does the contract model that difference explicitly rather than having the adapter silently ignore it?

If you cannot answer these, revisit **port ownership**, contract semantics, or adapter responsibilities before adding another wrapper layer.

## 17. Hands-On Exercises

**Exercise 1 — Spot the leaking boundary.** An **InvoiceService** builds a **PutObjectRequest**, calls **S3Client**, catches **S3Exception**, and returns **PutObjectResponse**. Refactor it into **InvoiceDocumentService → DocumentStore → S3DocumentStore**. Indicate which files are allowed to import the AWS SDK and which tests run without starting Spring.

**Exercise 2 — Move to Azure/GCP.** Keep **DocumentWrite**, **StoredDocument**, and **DocumentStore** intact. Sketch two adapters for Azure Blob Storage and Google Cloud Storage. Specify how container/bucket, key, content type, identity, and provider errors map; list three storage characteristics to verify before claiming they are equivalent.

**Exercise 3 — Unique write.** Two concurrent requests attempt to save the final PDF for one invoice. The current **put** port can overwrite. Design **createIfAbsent** returning **AlreadyExists** and explain why **HEAD → PUT** is insufficient to prevent races. Propose contract tests for each provider.

**Exercise 4 — Post-upload events.** A use case saves invoice metadata in PostgreSQL, uploads a PDF, and publishes an event. Mark the boundaries of **InvoiceRepository**, **DocumentStore**, and **InvoiceEventPublisher**; describe three failure windows and a workflow using **PENDING/READY/FAILED** states, an outbox, and idempotency.

**Exercise 5 — Multi-tenant.** A service shares one bucket across multiple tenants, and callers supply invoice ID and tenant ID. Distinguish where tenant permissions are verified, where the object key is constructed, where workload IAM permissions are granted, and where multi-provider routing happens if one tenant is on Azure. Why is simply prefixing the key with the tenant ID not secure enough?

**Exercise 6 — Choosing the right abstraction.** An AWS-only batch job uploads 10 files per day; a SaaS product with thousands of customers must switch object storage across multiple providers. Weigh adapter count, contract stability, unit testing, and maintenance cost. When is an infrastructure service calling the SDK directly good enough, and when does a port deliver clear value?

## 18. Key Takeaways

- **Application services depend on application-owned ports; provider adapters implement ports and depend on SDKs.** Spring Cloud mainly handles bean configuration/wiring and managed service integration.
- **Ports express use-case capabilities** using the data types and guarantees business logic needs; do not copy SDK requests/responses/exceptions or try to paper over real differences between AWS, Azure, and Google Cloud.
- **Place business authorization at the application/security boundary; place workload identity, endpoints, and resource permissions in infrastructure/cloud.** The two permission checks do not replace each other.
- A successful call to object storage **does not** form a transaction with a database or message broker; design idempotency, state tracking, and outbox/compensation when a use case has multiple side effects.
- Choose the right level of abstraction: **service → port → adapter** when it provides clear contracts and testability; calling the SDK directly inside an infrastructure service remains reasonable for small, stable, single-provider workloads.
- Test at the right boundary: **business unit tests without cloud**, **adapter/contract tests for mapping and semantics**, and **cloud smoke tests for identity, permissions, networking, and real guarantees**.
