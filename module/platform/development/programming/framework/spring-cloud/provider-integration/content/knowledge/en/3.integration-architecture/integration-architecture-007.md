# Data, Exception, and Request-Context Mapping at Integration Boundaries

In Spring Boot, a call to **save a document**, **publish an event**, or **read a secret** typically travels from business code to an adapter, through Spring Cloud integration/SDK, and on to a managed service. Each layer represents data, errors, and tracing information differently. For example: the application service says “save the invoice PDF”; AWS S3 expects a **PutObjectRequest** with bucket, key, content type, and request body; Azure Blob Storage expects container/blob names and upload options; Google Cloud Storage expects bucket/object details via its Java client. If SDK requests/responses and provider exceptions leak into business logic, a single SDK or provider change forces updates across many services and tests.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secret protection, integration testing, and cloud provider comparisons. This lesson focuses on designing three intentional transformations at integration boundaries: **data**, **exceptions/results**, and **request context**.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish HTTP/message DTOs, application data types, SDK requests/responses, and cloud resources.
- Design bidirectional mapping without making application services depend on provider types.
- Classify **business errors**, **cloud config/auth errors**, **transient errors**, and cases where **whether the operation completed is unknown**.
- Explain the differences between **business operation ID**, **correlation/trace ID**, **cloud request ID**, **idempotency key**, and **message ID**.
- Map an object-save operation with Spring Boot + Spring Cloud AWS/S3, then apply the same thinking to Azure and Google Cloud.
- Test mappings, errors, and metadata at each boundary without needing a live cloud for unit tests.

## 2. Three Transformation Flows on a Single Request

~~~mermaid
flowchart LR
    H[HTTP DTO / message payload] --> A[Application command]
    A --> P[Outbound port]
    P --> AD[Provider adapter]
    AD --> S[SDK request + transport]
    S --> C[Managed service]
    C --> R[SDK response or SDK exception]
    R --> AD
    AD --> O[Application result or storage error]
    O --> H2[HTTP response / workflow result]
    X[Operation ID / correlation context] -. application .-> P
    X -. safe metadata .-> AD
    Y[Cloud request ID] -. diagnostics .-> AD
~~~

Three information flows must be designed explicitly:

1. **Data:** controllers/listeners convert inputs into commands; application services translate business needs into outbound port requests; adapters map those into SDK models. When receiving responses, extract only what matters to the application contract.
2. **Results and errors:** the SDK reports success, API errors, network errors, or timeouts; the adapter maps them into **errors with stable meaning**. The application/controller decides HTTP responses, retries, or compensating steps based on that meaning.
3. **Request context:** operation IDs, authenticated tenant or principal, correlation/trace IDs, timeout budgets, and cloud request IDs serve authorization, observability, and recovery. Each value has a distinct source of trust and lifecycle.

Spring Cloud starters can configure SDK clients, templates, converters, or listeners for the application. **Spring does not automatically turn AWS, Azure, and Google Cloud semantics into one unified contract**; adapters still must account for what is truly equivalent and what differs.

## 3. Placing Data in the Right Layer

| Layer | Typical Data Seen | Should Own | Should Not Depend On |
| --- | --- | --- | --- |
| **Inbound adapter** | HTTP multipart, JSON DTOs, HTTP headers; queue payloads and attributes | Syntax, size, and format checks; transport mapping | Cloud SDK request bodies inside controllers |
| **Application service** | Invoice ID, DocumentId, validated content, use-case permissions, operation ID | Business rules, business-level resource naming, orchestration | Bucket policies, **PutObjectRequest**, **BlobInfo** |
| **Outbound port** | **DocumentWrite**, **StoredDocument**, application errors | Minimal technical contract sufficient for the use case | SDK-specific exception/metadata types |
| **Provider adapter** | Bucket/container, object key, SDK requests/responses, error codes | Mapping, provider traits, suitable retries, error translation | Deciding whether an end user may view an invoice |
| **SDK and cloud** | HTTP/gRPC, tokens/credentials, API status, and request IDs | Service access and IAM/RBAC enforcement | Application business-rule authorization |

For instance, an HTTP client sends **Content-Type**, filename, and PDF bytes. The HTTP controller validates upload formatting; the application service decides which invoice receives the document and the valid object key; only then does the adapter fill in bucket/region names and build the SDK request. Never let callers specify **buckets**, **storage accounts**, **projects**, **service accounts**, or sensitive headers and pass them straight into the SDK.

**Abstraction ownership:** outbound ports typically live in application/core; provider adapters depend on ports and SDKs. At the source-code level, dependency direction is **application → port ← adapter → SDK**, even though runtime requests flow from application through adapter to SDK.

## 4. Designing the Data Contract Before Mapping

Suppose business logic needs to save a PDF into object storage and receive back an identifier for reference:

~~~java
// DocumentWrite.java - part of application model
import java.util.Objects;

public record DocumentWrite(
        String objectKey,
        byte[] content,
        String contentType,
        String operationId) {

    public DocumentWrite {
        Objects.requireNonNull(objectKey, "objectKey");
        Objects.requireNonNull(content, "content");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(operationId, "operationId");
        if (objectKey.isBlank() || operationId.isBlank() ||
                content.length == 0) {
            throw new IllegalArgumentException("Invalid document write");
        }
    }
}
~~~

~~~java
// StoredDocument.java - result understood by the application
public record StoredDocument(String objectKey) {}

// DocumentStore.java - outbound port
public interface DocumentStore {
    StoredDocument put(DocumentWrite request);
}
~~~

These types import no AWS, Azure, or Google Cloud SDK classes. **operationId** represents a durable identifier for the business operation; it can support idempotency and tracing. Placing an operation ID into object metadata **does not automatically make writes idempotent**; that guarantee must be designed explicitly in the application and/or via provider conditional writes.

**Example limitations:** a record holding **byte[]** is used solely for readability. Byte arrays can be mutated by external code and hold the entire file in memory; production apps must bound size, validate MIME/content, and consider streaming or permission-scoped direct uploads. If a record containing an array belongs to a model requiring immutability, defensively copy it in the constructor and accessor or pick a different data representation.

### 4.1. Pass Only Genuinely Needed Data Across the Port

| Needed by Use Case? | Data | Design Suggestion |
| --- | --- | --- |
| Yes | Document key, content type, content, operation ID | Include in **DocumentWrite** |
| Yes in certain use cases | Version ID, checksum, generation, write condition | Define a capability/option with precise semantics |
| Usually no | AWS request ID, Azure response headers, endpoint address | Keep in diagnostics or observability infrastructure |
| No | AWS **PutObjectResponse**, Azure **BlobUploadOptions**, Google **BlobInfo** in application service | Use only inside the provider adapter |
| Never in public DTOs | Access keys, OAuth tokens, SAS/connection strings | Keep inside credential/config infrastructure |

If the system requires **write once, never overwrite**, the port must declare that condition explicitly, such as **createIfAbsent**. A **put** method that omits write semantics while silently overwriting is a contract bug, even though all three SDKs support writing objects.

## 5. Mapping HTTP or Message Payloads into Application Commands

At the inbound boundary, data arrives from an external source and cannot be trusted yet:

~~~text
POST /invoices/{invoiceId}/document
  HTTP body / Content-Type / authenticated principal
    -> Controller: validate size and format
    -> Application service: verify invoice ownership
    -> Generate trusted objectKey and operationId
    -> DocumentStore.put(DocumentWrite)
~~~

Separate **format validation** from **business authorization**. The controller can check that the file is non-empty and within a maximum MB limit; the application service verifies the invoice belongs to the tenant/caller, computes the key by invoice and version, and calls the port. Never trust an arbitrary client-sent **X-Tenant-Id** or bucket name unless verified against authenticated identity and application data.

For JSON/event payloads, also verify:

- **Schema/version:** adding fields or changing semantics in an event can break older consumers; maintain versioning and compatibility policies.
- **Timestamps:** use explicit instants/UTC (such as ISO 8601) and avoid mixing time zones or epoch milliseconds vs. seconds.
- **Numeric types:** handle money using decimal or smallest integer units rather than floats; watch out for large numbers traversing JavaScript/JSON.
- **Null/missing/empty:** distinguish absent, null, and empty fields per contract; never let a mapper silently drop critical data.
- **Encoding:** use UTF-8 and accurate metadata/content types; never pass binary files through arbitrary `String` conversions.
- **Size:** JSON payloads, metadata, and message attributes have service-specific limits; never stuff large files onto a queue merely to simplify a call.

## 6. Spring Cloud AWS S3 Adapter Example: Mapping Requests and Responses

This example uses **Spring Boot 3, Spring Cloud AWS 3.x, and AWS SDK for Java v2**. With a compatible starter, Spring Cloud AWS can create the **S3Client** bean injected into the adapter; with custom SDK configuration, the application can declare the client bean itself. Artifact names, BOMs, and properties must match your project's exact versions.

Illustrative Maven dependency:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Configuration:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  document-store:
    provider: aws
    bucket: ${APP_DOCUMENT_BUCKET}
~~~

**spring.cloud.aws.region.static** is an AWS integration property; **app.document-store.provider** and **app.document-store.bucket** are defined by the application. The bucket name is supplied by the environment; credentials are resolved by the SDK using a mechanism suited to the workload (such as an IAM role) and must be granted specific resource permissions. Never hard-code access keys/secret keys in YAML.

### 6.1. Defining Shared Errors for Adapters

~~~java
// StorageFailureCode.java
public enum StorageFailureCode {
    ACCESS_DENIED,
    CONFLICT,
    TEMPORARY_UNAVAILABLE,
    OUTCOME_UNKNOWN,
    PROVIDER_FAILURE
}
~~~

~~~java
// StorageFailure.java
public final class StorageFailure extends RuntimeException {
    private final StorageFailureCode code;
    private final String providerRequestId;

    public StorageFailure(
            StorageFailureCode code,
            String safeMessage,
            String providerRequestId,
            Throwable cause) {
        super(safeMessage, cause);
        this.code = code;
        this.providerRequestId = providerRequestId;
    }

    public StorageFailureCode code() {
        return code;
    }

    // Internal use only for correlating with cloud logs/audits.
    public String providerRequestId() {
        return providerRequestId;
    }
}
~~~

The enum is an **application-chosen error taxonomy**, not a claim that AWS/Azure/GCP share identical error codes. Extend it per use case (for example `NOT_FOUND`, `INVALID_REQUEST`, `QUOTA_EXCEEDED`, `PRECONDITION_FAILED`) when justified. **safeMessage** must never expose tokens, connection strings, sensitive bucket names, or bodies in public responses.

### 6.2. Adapter Mapping DocumentWrite to PutObjectRequest

~~~java
// S3DocumentStore.java
import java.util.Map;
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
public final class S3DocumentStore implements DocumentStore {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStore(
            S3Client s3,
            @Value("${app.document-store.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public StoredDocument put(DocumentWrite doc) {
        PutObjectRequest sdkRequest = PutObjectRequest.builder()
            .bucket(bucket)
            .key(doc.objectKey())
            .contentType(doc.contentType())
            .metadata(Map.of("operation-id", doc.operationId()))
            .build();

        try {
            s3.putObject(sdkRequest, RequestBody.fromBytes(doc.content()));
            return new StoredDocument(doc.objectKey());
        } catch (S3Exception ex) {
            throw translateServiceError(ex);
        } catch (SdkClientException ex) {
            throw new StorageFailure(
                StorageFailureCode.OUTCOME_UNKNOWN,
                "Cannot confirm object write",
                null,
                ex);
        }
    }

    private StorageFailure translateServiceError(S3Exception ex) {
        int status = ex.statusCode();
        StorageFailureCode code;
        if (status == 403) {
            code = StorageFailureCode.ACCESS_DENIED;
        } else if (status == 409 || status == 412) {
            code = StorageFailureCode.CONFLICT;
        } else if (status == 429 || status >= 500) {
            code = StorageFailureCode.TEMPORARY_UNAVAILABLE;
        } else {
            code = StorageFailureCode.PROVIDER_FAILURE;
        }

        return new StorageFailure(
            code,
            "Object storage request failed",
            ex.requestId(),
            ex);
    }
}
~~~

**Data flow:** **DocumentWrite.objectKey → PutObjectRequest.key**, **contentType → contentType**, **content → RequestBody**, **operationId → user metadata**. Returns **StoredDocument** with the key, as the current contract does not need to expose the entire **PutObjectResponse**. **S3Client** is a bean reused across calls; the adapter does not construct a new client per request.

**Notes on the semantics of this example:**

- This is a **minimal** error-mapping sample. HTTP **403** from S3 usually indicates a workload identity/policy problem—do not conclude the end user lacks invoice permission. **409/412** must be interpreted per actual operation and precondition; **5xx/429** codes may be transient errors.
- **SdkClientException** can occur before or after the request is sent. For a side-effecting write, if there is no solid evidence of state, conservatively classify it as **OUTCOME_UNKNOWN**. Never claim every client exception succeeded or definitely failed to write.
- **operation-id** metadata only aids tracing and reconciliation when read permissions exist. It does not replace an application-protected idempotency key, conditional writes, or service deduplication mechanisms.
- The SDK exception is kept as an **internal cause**. Never serialize full causes/stack traces into HTTP bodies; log only safe attributes under secure logging settings.
- For large files, **RequestBody.fromBytes** buffers the entire content in RAM; design appropriate streaming/multipart or direct-upload flows.

### 6.3. If Object Versioning or Checksums Are Needed

S3 can provide **versionId**, **ETag**, or checksum details depending on configuration/features. Azure Blob and Google Cloud Storage have **ETag/version/generation** with differing semantics and scopes. Never treat **ETag** as a consistent SHA-256 or MD5 across clouds; multipart uploads, encryption, or provider mechanisms can make ETags differ from a plain content digest.

If a use case genuinely needs **conditional writes** or optimistic concurrency, define a contract with an explicit condition field (such as **expectedVersion** or **createIfAbsent**), implement it with matching preconditions, and test races. Do not add a **String etag** field to a port without specifying how it is generated, validated, and used on each provider.

## 7. At Which Boundary Should Exceptions Be Translated?

Not every exception belongs to the same layer of responsibility:

| Error Type | Where Detected | How Represented in the Application |
| --- | --- | --- |
| Empty PDF, wrong data type, invalid invoice | Inbound/application validation | Use-case input/validation error |
| Caller not allowed to access another tenant's invoice | Business authorization | **Caller** authorization error, typically mapped to HTTP 403 |
| Workload lacks bucket/container write permission | Cloud SDK/managed service | Infrastructure **ACCESS_DENIED** error for operators; do not leak cloud resources |
| Misconfigured endpoint, region, or project | Client/config or managed service | Config/infrastructure error, typically requiring deployment fix |
| Quotas, throttling, 429/503, transient errors | Cloud service/transport | **TEMPORARY_UNAVAILABLE** with bounded retries |
| Request timed out and may already be processed | SDK/transport | **OUTCOME_UNKNOWN**, check state before repeating side effects |
| Conditional write failed | Provider precondition | **CONFLICT** or **ALREADY_EXISTS** per use-case contract |
| Object does not exist on read/delete | Provider response for that operation | **NOT_FOUND** if defined and verified by the contract |

The **adapter** knows codes like **S3Exception.statusCode()**, **BlobStorageException.getStatusCode()**, and **StorageException.getCode()**. It produces neutral infrastructure errors. The **application service** knows whether to report a conflict, keep a pending state, or retry. The **HTTP exception handler** turns application errors into safe responses.

For example, HTTP **502/503** may fit when the **cloud workload lacks permissions** or the managed service is down; HTTP **403** fits when the **caller is unauthorized** to run the use case. Both error sources may carry status 403 at some layer, yet their meanings differ; never copy cloud HTTP statuses mechanically to the caller.

### 7.1. Preserve Root Causes Without Leaking Sensitive Data

When diagnostics are needed, record:

- Normalized error code and operation ID.
- Provider, operation name, log-safe region/project, status code, and cloud request ID if present.
- Internal **cause** handled through appropriate logging/telemetry.

Never log credentials, auth headers, SAS tokens, connection strings, secret values, sensitive PDF/message payloads, or raw full SDK HTTP requests/responses. A cloud request ID helps support search provider logs, but a public API does not need to expose it.

## 8. Retries: Classifying Errors Is Not Enough—Consider the Operation Type

An error that looks transient may still be unsafe to retry blindly. You must know **what side effects the operation has** and **what idempotency guarantees exist**.

~~~mermaid
flowchart TD
    E[Error from SDK] --> A{Verified unrecoverable error?}
    A -->|Yes: e.g. missing permissions| STOP[Return config / authorization error]
    A -->|No| B{Likely already executed side effect?}
    B -->|Yes or unclear| C[Reconcile state / operation ID]
    B -->|No, evidence request not sent| D{Operation safe to retry?}
    C --> D
    D -->|No| F[Report unknown outcome and run compensation]
    D -->|Yes| G[Bounded retry, backoff, jitter, deadline]
~~~

For example, a **PUT object** times out after the server already wrote the data: retrying with a newly generated key can create **two objects**. Using a stable key tied to document ID/operation ID directs retries to the same resource, yet you still must choose between overwriting and create-if-absent. For **message publishing**, the broker may have accepted the message even though the producer lost the response; consumers must implement idempotency by event ID.

The SDK, Spring Retry, Reactor, and message brokers can all retry simultaneously. If each layer tries three times, total calls escalate sharply. Maintain an overall **timeout budget and retry budget**, avoid retrying permission or validation errors, and record retry counts in observability.

## 9. Four Request Identifiers Frequently Confused

| Value | Created By | Purpose | System-Wide Uniqueness Guaranteed? |
| --- | --- | --- | --- |
| **Business operation ID / idempotency key** | Application or authenticated caller controlled by application | Identifies a business operation, prevents duplicates per contract | Governed by application storage/constraint design |
| **Correlation ID** | API gateway or app, possibly accepted from trusted upstream | Groups logs across steps of a request/workflow | Only with a reliable issuance/normalization rule |
| **Trace ID / span ID** | Distributed tracing/instrumentation system | Tracks timing and span relationships across systems | Belongs to tracing context; does not replace business IDs |
| **Provider request ID** | AWS/Azure/Google Cloud for one specific API call, if provided | Investigates one cloud call | Follows provider semantics; may change on each retry |

For example, a single HTTP request may carry **operationId=invoice-123-v2**, an HTTP **traceId**, and three distinct **cloud request IDs** if the SDK retried three times. Never use a provider request ID as a business idempotency key; it does not exist before calling the cloud and changes across retries.

**Trustworthiness:** correlation headers from the internet can be forged or overly long. At the boundary, validate format/size and decide whether to trust upstream trace context or issue a new ID. Tenant IDs and principals must come from an authenticated/authorized security context, never solely from a self-declared user HTTP header.

### 9.1. Which Fields Can Be Sent to the Provider?

Pass only fields that are **safe and supported by the API**:

| Information | S3 object metadata | Azure Blob metadata / headers | GCS object metadata | Notes |
| --- | --- | --- | --- | --- |
| Content type | Request contentType | Blob HTTP headers/content type | BlobInfo/content type | Helps clients serve the right type; does not replace content validation |
| Short, non-sensitive operation ID | Appropriate user metadata | Appropriate metadata key/value | Appropriate custom metadata | Size and format limits vary by provider |
| Trace/correlation ID | Only when useful and permitted | Same | Same | Do not assume cloud providers propagate W3C trace through SDK calls |
| Access tokens, cookies, PII | **No** | **No** | **No** | Metadata may be read or appear in logs or object ACLs |

For metadata, the SDK maps key/value pairs to headers or API fields per provider. Never inject arbitrary headers starting with **Authorization**, never forward full controller request headers to the cloud, and never let callers choose endpoints or roles.

## 10. Comparing AWS, Azure, and Google Cloud

| Aspect | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Typical Java Storage API | **S3Client**, **PutObjectRequest** | **BlobClient/BlobServiceClient**, upload options | **Storage**, **BlobInfo** |
| Typical service exception | **S3Exception** / AWS service exceptions | **BlobStorageException** / Azure HTTP exceptions | **StorageException**, some GAX APIs throw **ApiException** |
| Transport/client exception | **SdkClientException** | HTTP/client exceptions per Azure SDK | IOException/ApiException or library-specific exceptions |
| HTTP code on service error | **statusCode()** on service exception | **getStatusCode()** on appropriate HTTP exception | **getCode()** on StorageException; depends on API |
| Request ID for support | AWS request ID from exception/response when present | e.g. **x-ms-request-id** from response metadata when present | HTTP/gRPC request identifiers when provided by API |
| Metadata and conditional writes | S3 user metadata + operation preconditions | Blob metadata/HTTP headers + ETag conditions | GCS custom metadata + generation/metageneration preconditions |
| Workload identity | IAM role/credential chain | Managed Identity/DefaultAzureCredential | ADC/workload identity/service account |

Exception names and accessors in this table are **directional**; exact APIs vary by service, SDK, and version. Never assume a mapping mechanism can rely solely on **HTTP status**. For instance, 404 on an object read may mean the object does not exist; 404 on another call may mean the wrong account, container, endpoint, or resource. Some gRPC-based APIs return canonical status codes instead of direct HTTP responses.

### 10.1. Azure Blob: What Does the Adapter Do?

An **AzureBlobDocumentStore** uses a client/template configured by Spring Cloud Azure (or a custom Spring-managed Azure SDK client), maps **DocumentWrite.objectKey** to blob name and **contentType** to blob HTTP headers or upload options, and invokes upload on the target container. On failure, the adapter inspects **BlobStorageException**, appropriate status/error codes, and request IDs/headers to produce a **StorageFailure**. Never return raw **BlobStorageException** to the application service.

When using Managed Identity, the Azure SDK acquires tokens from the appropriate credential chain; **Azure RBAC/resource configuration** governs write permissions. A valid token lacking permissions on the storage account/container still triggers a workload authorization error. Retries and conditional writes must follow Azure Blob's contract rather than mechanically copying AWS status enums.

### 10.2. Google Cloud Storage: What Does the Adapter Do?

A **GcsDocumentStore** uses a **Storage** client (or suitable abstraction) to build **BlobInfo** from bucket/object name/content type/metadata and sends bytes/streams to the Cloud Storage API. The adapter translates **StorageException** into application errors by operation and code; if another service uses gRPC/GAX, inspect **ApiException** and RPC metadata. **ADC** determines identity, while IAM on the project/bucket determines permissions.

In GCS, **generation preconditions** are key when the contract requires preventing overwrites; **generation** is not strictly equivalent to **S3 version ID** or ETag. The shared contract should define the intended capability, and each adapter implements it with semantically matching provider APIs.

## 11. Mapping Message Payloads, Headers, and Acknowledgments

Storage is only one case. With messaging (Amazon SQS/SNS, Azure Service Bus, Google Cloud Pub/Sub), there are at least **two boundaries**:

~~~mermaid
flowchart LR
    A[Business service] --> P[EventPublisher port]
    P --> B[Publisher adapter]
    B --> Q[SQS / Service Bus / PubSub]
    Q --> L[Listener / subscriber adapter]
    L --> H[Business event handler]
~~~

**On the publisher side**, the application builds a domain-meaningful event: **eventId**, **eventType**, **schemaVersion**, **occurredAt**, **aggregateId**, and payload. The adapter serializes it to JSON or an appropriate format, attaches supported message attributes, and calls the template/SDK. If publishing succeeds, the result usually confirms only that the broker accepted/acknowledged the API call; it does **not** confirm the consumer finished business processing.

**On the consumer side**, the listener adapter parses the message body and attributes into a validated event DTO, verifies schema version and trusted source, and invokes the business handler. The handler uses **eventId** or a suitable business key for idempotent handling of duplicates. The adapter/listener performs **ack/delete/complete/nack** after the handler reaches the state required by the broker contract.

Example application event model:

~~~java
import java.time.Instant;

public record InvoiceIssuedEvent(
    String eventId,
    int schemaVersion,
    String invoiceId,
    Instant occurredAt
) {}
~~~

**Do not equate the broker's message ID with the application's event ID.** The broker may assign a fresh ID on resend, whereas the event ID must remain stable across republish attempts so consumers can deduplicate. SQS visibility timeouts, Service Bus locks/settlement, Pub/Sub ack deadlines, and dead-lettering differ; error/ack mapping must follow the provider. Supported tracing headers must be propagated intentionally and must never contain tokens, unverified tenant claims, or sensitive PII.

If a use case writes to a database and publishes an event, JPA's **@Transactional** does not automatically include the message broker. **Transactional outbox** is one option to store state and an event record in the same database transaction, after which a worker publishes the event and records the outcome by operation ID.

## 12. Data Boundaries with Databases and Secrets

### 12.1. Managed Databases

With Spring Data JPA/JDBC on managed PostgreSQL (AWS RDS, Azure Database, or Google Cloud SQL), application entities/repositories need not contain cloud provider names. Yet the persistence layer still maps between **domain entities** and **database rows/entities**, including nullability, unique constraints, time zones, transactions, optimistic-locking versions, and SQL error codes.

When using DynamoDB, Cosmos DB, Firestore, or Spanner, data has distinct partition keys, consistency, indexing, transactions, and query models; adapters/repositories must reflect differences that impact business guarantees. Never assume all datastores support identical **save()** semantics merely because they implement the same interface.

A database **unique constraint violation** may correspond to an “already exists” business error when the constraint enforces a business invariant. However, a database connection failure or deadlock must be classified differently; never turn every persistence exception into HTTP 409.

### 12.2. Secret Management

When reading AWS Secrets Manager, Azure Key Vault, or Google Secret Manager, application services usually only need a secret value by a clear name/capability. The adapter translates that name into a provider resource identifier, invokes the client, handles rotation/versioning, and maps errors such as missing secret, permission denied, or temporary unavailable.

**Never let secret values enter generic exceptions, structured logs, URL query strings, message attributes, or object metadata.** If secrets are loaded into Spring config at startup, check refresh lifecycles and how the system handles rotation. If secrets are read at runtime, consider caching/TTL and workload identity to avoid hitting the secret manager on every HTTP request.

## 13. Using Request Context for Observability and Incident Support

A safe adapter log entry should follow a structure similar to:

~~~text
operation=object.put
provider=aws
operationId=invoice-123-revision-2
correlationId=7cde...         # validated ID
providerRequestId=...          # only when provided by SDK
outcome=TEMPORARY_UNAVAILABLE
durationMs=217
attempt=2
~~~

Never put high-cardinality bucket/tenant/document keys into metric labels. Choose carefully:

| Observability Data | Logs/Traces | Metric Labels |
| --- | --- | --- |
| Provider, operation, result category | Yes | Yes, low cardinality |
| Duration, retry count, HTTP status/error category | Yes | Appropriate histogram/counter |
| Operation ID / correlation ID | Yes, per security policy | Typically **no** due to very high cardinality |
| Cloud request ID | Yes, when provided by provider | No |
| Full object key, user email, payload | Only under explicit security rules; avoid by default | No |
| Tokens, secrets, credentials | No | No |

**Context propagation:** with Spring MVC, MDC/ThreadLocal works within the same thread, but with **CompletableFuture**, executors, listeners, or WebFlux/Reactor, context does not automatically travel accurately across threads. Use context propagation supported by Spring/Micrometer/Reactor and your SDK version, or pass a validated **OperationContext** explicitly through application APIs. Never log under the wrong tenant because a ThreadLocal was copied improperly.

**Traceparent/W3C Trace Context** links distributed traces when supported by client/server instrumentation. Do not assume cloud providers preserve full traces across every API. An SDK request ID belongs to the **provider call**, a trace ID belongs to the **tracing system**, and an operation ID belongs to **business logic**; they complement one another.

## 14. Async/Reactive: Exceptions and Metadata Still Need Mapping

When switching from a synchronous to an asynchronous SDK, the application still needs the same error contract, yet errors arrive inside a **future** or **publisher** rather than being thrown directly from the method call:

| Execution Model | Success Result | Error |
| --- | --- | --- |
| Sync SDK | Value returned from method | Exception thrown during call |
| Async SDK | **CompletableFuture** completes | Future completes **exceptionally**, possibly wrapped in `CompletionException` |
| Reactor | **Mono/Flux** emits signals | **onError**; adapter uses conditional `onErrorMap`/`onErrorResume` |

Example bridging a future returned by **AsyncDocumentStore** into a Mono in Spring WebFlux:

~~~java
import reactor.core.publisher.Mono;

public Mono<StoredDocument> saveReactive(
        AsyncDocumentStore asyncStore,
        DocumentWrite doc) {
    return Mono.defer(() ->
        Mono.fromFuture(asyncStore.put(doc)));
}
~~~

This example assumes **AsyncDocumentStore.put** returns **CompletableFuture<StoredDocument>**. **Mono.defer** defers invoking the async client until subscription; an already-created future may have already started I/O. If exception mapping occurs inside the adapter, **Mono** receives normalized application errors; if the adapter surfaces raw SDK exceptions, apply conditional **onErrorMap** preserving root causes rather than swallowing all errors with **onErrorResume**.

**Retrying a publisher** can resubscribe and execute a fresh write; keep stable operation IDs/object keys and idempotency contracts. **Cancellation** is not a cloud rollback. If a controller returns before the future/Mono completes, the HTTP client may receive a misleading success response. For messaging listeners, verify processing/acks await completion per the actual listener API.

## 15. Testing Mapping and Errors at Each Boundary

| Level | What Is Verified | Technique |
| --- | --- | --- |
| Application service unit test | Correct **DocumentWrite** built, permissions checked, no SDK used | Mock/fake **DocumentStore** |
| Adapter request unit test | Bucket/key/content type/metadata mapped accurately | Mock SDK client, **ArgumentCaptor** |
| Adapter error unit test | S3 403/503 and transport errors map to proper **StorageFailure** | Mock SDK exceptions, assert error code |
| Context test | Only the matching provider adapter is created, right client injected | Spring context / `ApplicationContextRunner` |
| Emulator integration | Real SDK upload/download, correct metadata, serialization | LocalStack for AWS, Azurite for Blob, suitable GCP emulator/test environment |
| Cloud smoke test | Identity, IAM/RBAC, endpoints, request IDs, timeouts/retries | Dedicated test resources with least privilege |

### 15.1. Unit Testing That the Adapter Builds the Right Request

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

class S3DocumentStoreTest {
    @Test
    void mapsApplicationDataToS3Request() {
        S3Client client = mock(S3Client.class);
        when(client.putObject(
                any(PutObjectRequest.class), any(RequestBody.class)))
            .thenReturn(PutObjectResponse.builder().build());

        S3DocumentStore adapter = new S3DocumentStore(client, "test-bucket");
        DocumentWrite doc = new DocumentWrite(
            "invoices/42.pdf",
            new byte[] {1, 2, 3},
            "application/pdf",
            "operation-42");

        StoredDocument receipt = adapter.put(doc);

        ArgumentCaptor<PutObjectRequest> captor =
            ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(client).putObject(captor.capture(), any(RequestBody.class));

        PutObjectRequest sdkRequest = captor.getValue();
        assertEquals("test-bucket", sdkRequest.bucket());
        assertEquals("invoices/42.pdf", sdkRequest.key());
        assertEquals("application/pdf", sdkRequest.contentType());
        assertEquals("operation-42",
            sdkRequest.metadata().get("operation-id"));
        assertEquals(doc.objectKey(), receipt.objectKey());
    }
}
~~~

This test checks **adapter mapping** without calling S3. Add tests simulating **S3Exception.builder().statusCode(403).build()** to confirm **StorageFailure.code()==ACCESS_DENIED**, and **503** mapping to **TEMPORARY_UNAVAILABLE**. Add a test mapping **SdkClientException** to **OUTCOME_UNKNOWN** for write operations. To verify actual bytes and stream lifecycles, write separate request-body or integration tests; capturing **PutObjectRequest** does not verify file contents automatically.

### 15.2. Multi-Provider Contract Tests

A contract test suite for **DocumentStore** can include:

1. Write an object and read back matching content/content type; no SDK types leaked.
2. Send the same operation ID twice per the defined idempotency contract; check whether it overwrites, conflicts, or returns the same result.
3. Access with insufficient permissions, missing resource, transient errors, or failed preconditions; verify mapped application errors.
4. Create keys containing Unicode/special characters per defined policy; check encoding and ensure keys are not silently altered.
5. Run two concurrent create-if-absent operations to detect races if the contract mandates unique creation.
6. Verify safe provider request ID/trace info appears in internal logs, never in public error bodies.

Emulators aid technical testing yet rarely simulate IAM/RBAC, quotas, networking, encryption, and all cloud behaviors completely. Therefore, dedicated cloud smoke tests are needed for guarantees the adapter claims to support, using cleaned-up resources with no production data.

## 16. Integration Error Troubleshooting Procedure

When a use case fails, trace boundaries in order:

1. **Input:** are the HTTP/message payload, content type, and schema version valid?
2. **Use case:** were identity/tenant authenticated? Are business authorization and object keys right?
3. **Port:** does the contract specify overwrite or create-if-absent? Is there a stable operation ID on retries?
4. **Adapter:** are bucket/container/project mappings, content metadata, SDK requests, and timeouts correct?
5. **SDK/client:** which credential chain, endpoint, and region/project are used? Were there transport errors before or after sending?
6. **Managed service:** what do IAM/RBAC, quotas, preconditions, error codes, and provider request IDs show?
7. **Return path:** was the SDK exception obscured by a wrapper? Did the adapter map errors accurately, or did the controller return a misleading message?
8. **Re-execution:** might the cloud have already processed the operation? Must state be reconciled before retrying?

For example, the app gets **S3 AccessDenied** while writing a PDF: verify the workload role, **s3:PutObject** action, resource ARN/bucket policy, and deny conditions. Never turn the HTTP response into “user not allowed to view invoice” if application authorization already succeeded. Conversely, an unauthorized user must be rejected **before** the adapter calls S3, regardless of how broad the workload role's permissions are.

## 17. Hands-On Exercises

**Exercise 1 — Separate data boundaries.** A controller accepts JSON containing `invoiceId`, `tenantId`, `bucketName`, `accessToken`, and `rawS3Request`. Redesign the DTO so callers supply only necessary fields; identify which layer verifies the tenant, generates the object key, and selects the bucket/credentials from trusted config.

**Exercise 2 — Exception mapping.** An S3 adapter throws raw **S3Exception** to a REST controller. Write an application error enum and map **403**, **409/412**, **503**, and SDK timeouts. Explain which case should be **OUTCOME_UNKNOWN** and why not every error can be retried.

**Exercise 3 — Three providers.** Keep **DocumentWrite** and **StoredDocument**, then sketch adapters for Azure Blob and Google Cloud Storage. Describe how content type, object key, operation ID, preconditions, and error codes map; propose at least three shared contract tests.

**Exercise 4 — Correlation and operation IDs.** An upload request fails twice and succeeds on the third attempt. Distinguish the business operation ID, trace ID, correlation ID, and the three cloud request IDs; specify which fields appear in audit logs, metric labels, and public responses.

**Exercise 5 — Schema evolution.** A publisher sends **InvoiceIssuedEvent** over SQS/Service Bus/Pub/Sub; older consumers do not yet know a new **currency** field. Design schema versioning, validation, and backward compatibility; explain which `eventId` must remain stable when the producer retries.

**Exercise 6 — Transaction boundaries.** An application writes an invoice to PostgreSQL, uploads a PDF, and publishes an event. If the upload times out after the object was already written, propose a stable key, **PENDING/READY** states, an outbox, and a reconciliation flow that avoids duplicate documents/events.

**Exercise 7 — Layered testing.** Write an application service unit test that imports no AWS SDK; write an adapter test using **ArgumentCaptor** on **PutObjectRequest**; finally, design a cloud smoke test verifying workload permissions and stored content.

## 18. Key Takeaways

- **Inbound DTOs, application commands, outbound port requests, and SDK requests/responses live at distinct boundaries.** Pass only needed business information through ports; keep provider details in adapters.
- **Adapters translate SDK exceptions into application errors with clear semantics**, preserving causes and provider request IDs for internal diagnostics. Never copy cloud statuses mechanically into caller HTTP responses.
- **Business operation IDs, correlation IDs, trace IDs, and cloud request IDs** have different origins, scopes, and purposes; they are not interchangeable.
- **Metadata, Content-Type, and message attributes** must be validated, encoding-normalized, and scrubbed of sensitive data. Never blindly forward caller-supplied tokens/headers into SDKs.
- **Timeouts/cancellations can leave ambiguous outcomes.** Retrying side-effecting operations requires stable object keys or event IDs, idempotency, preconditions, or state reconciliation.
- The same principles apply across **AWS, Azure, and Google Cloud**, yet status/error codes, versioning, metadata, IAM/RBAC, and acknowledgments differ; contract tests and real-cloud tests must enforce every promised guarantee.
