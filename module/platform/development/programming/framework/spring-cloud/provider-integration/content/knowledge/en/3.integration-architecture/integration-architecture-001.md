# Request Flow from Business Code through Spring to SDK and Services

In a Spring Boot application, commands like “save a file to the cloud,” “send a message,” or “read a secret” often appear as a single method call. Behind that call, multiple components participate: business code, Spring Framework, Spring Cloud integration libraries, the provider SDK, authentication mechanisms, and cloud managed services. Understanding this flow accurately helps design applications with low provider coupling, determine the right place to handle errors, and pinpoint root causes when deployments fail.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. Its scope covers practical integration of Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries, from identity/permission configuration to storage, messaging, data, secrets, testing, and system observability.

## 1. Learning Outcomes

After this lesson, you can:

- Draw and explain the path of a request from an API or background task to a cloud service and back to the application.
- Distinguish the responsibilities of **Spring Boot**, **Spring Cloud integration**, **cloud SDK**, **credential provider**, and **managed service**.
- Identify where to place business rules, provider-dependent code, permission configuration, error handling, and retries.
- Apply the same model to AWS S3, Azure Blob Storage, and Google Cloud Storage, and extend it to queues/messaging.
- Read error symptoms to isolate the layer: Spring wiring, endpoint/region configuration, identity, permissions, network connectivity, or the service itself.

## 2. Participating Layers and Responsibilities

| Component | Primary Responsibility | Example |
| --- | --- | --- |
| **Business code (domain/application)** | Defines **when** to read/write data, enforces business rules, and orchestrates use cases | After validating a record, invoke the document storage port |
| **Spring Boot / Spring Framework** | Creates and manages beans, dependency injection, configuration, application lifecycle, web endpoints, local transactions | Inject an implementation of the storage interface into a service |
| **Spring Cloud integration** | Provides starters, auto-configuration, templates/abstractions, listeners, and integration with the Spring ecosystem depending on the library | Spring Cloud AWS S3, Spring Cloud Azure Storage Blob, Spring Cloud GCP Storage |
| **Provider SDK / client library** | Builds API requests, serializes/deserializes data, authenticates or signs requests, performs I/O, and translates API errors into exceptions | AWS SDK for Java v2, Azure SDK for Java, Google Cloud Java client libraries |
| **Credential provider / identity** | Locates and refreshes the identity used to call APIs; does not itself grant permissions to that identity | AWS IAM role, Azure Managed Identity, Google Cloud Application Default Credentials |
| **Managed service** | Handles requests on the cloud side; checks permissions, stores/reads data, receives and distributes messages | Amazon S3/SQS, Azure Blob Storage/Service Bus, Google Cloud Storage/Pub/Sub |

Logical diagram when the application writes an object to object storage:

~~~mermaid
flowchart LR
    U[HTTP / scheduled job] --> C[Controller / job handler]
    C --> B[Business service]
    B --> P[Storage port]
    P --> A[Provider adapter]
    A --> T[Spring Cloud template, if used]
    T --> K[Cloud SDK client]
    A --> K
    K --> N[HTTPS / gRPC depending on API]
    N --> S[Managed cloud service]
    F[Spring Boot + Spring Cloud auto-config] -. creates and injects beans .-> A
    F -. initializes client .-> K
    I[Credential provider] -. supplies identity .-> K
~~~

**This is a responsibility diagram, not a mandatory call chain that must pass through every box.** Spring Boot primarily initializes and wires objects at startup. At runtime, an adapter can call the Spring-injected SDK directly; if a Spring Cloud template is used, the adapter calls the template, and the template uses the SDK. The SDK sends requests over the transport appropriate for the API. For certain services, Spring Cloud provides dedicated listeners or abstractions; the level of support varies by provider and version.

Placing a **port** (an interface owned by the application) between the business service and the adapter is a useful architectural choice when you need independent testing, provider switching, or multi-backend support. For a small application using a single service, calling the client directly from an infrastructure service can still be reasonable; what you must avoid is scattering bucket names, IAM permissions, error codes, and SDK types throughout business logic.

## 3. Distinguishing the Startup Flow from the Request Processing Flow

### 3.1. Startup: Spring Wires the Components

When the application starts up:

1. Dependencies and compatible BOMs determine the versions of Spring Boot, Spring Cloud libraries, and SDKs.
2. Spring Boot reads configuration from YAML, environment variables, and enabled configuration sources.
3. Auto-configuration from the relevant starter may create beans for SDK clients, templates, converters, or listener containers. Bean creation conditions depend on the classpath, configuration, and version.
4. The credential chain is configured or discovered according to the provider's mechanism. Some SDKs only fetch an actual token when making the first request, so **a successful startup does not prove cloud access permissions exist**.
5. Spring injects beans into adapters, services, and controllers; if messaging is configured, listeners may register to receive messages.

There is no need to instantiate a new SDK client on every HTTP request. Popular clients are designed for reuse, with built-in connection pooling and retry/timeout configuration. How a client is instantiated should follow the recommendations of the specific SDK and library version in use.

### 3.2. Runtime: Where Does an Object Write Actually Go?

Suppose a user submits document content over HTTP and the application writes it to object storage:

1. **Controller** receives the request, authenticates the user at the application layer, and validates input constraints (size, content type, document access rights).
2. **Business service** decides the object name/identifier and calls a storage interface. The rule “which documents this user is allowed to upload” belongs here or in an appropriate authorization layer, not in the SDK.
3. **Provider adapter** maps the generic operation to a cloud-specific API, such as bucket + object key for S3.
4. **SDK client** prepares the request; the credential provider supplies identity information, and the SDK adds authentication/request signing according to the corresponding protocol.
5. **Transport** sends HTTP or gRPC to the endpoint. DNS, TLS, proxies, firewalls, private endpoints, and timeouts can affect this step.
6. **Cloud service** verifies the identity and permissions on the resource, applies service policies, and performs the write. A valid identity can still be denied due to missing permissions.
7. **SDK** decodes the result; success returns a response, while failure typically raises an exception containing error code/status information.
8. **Adapter** translates provider-specific errors into application-meaningful errors when needed; **business service** completes the use case, and **controller** builds the HTTP response for the caller.

The return flow travels back toward the application. Receiving an HTTP 200/201 from the application only proves what the application actually waited for and verified: for example, that the adapter received a successful write response. It does not automatically guarantee that all subsequent asynchronous steps or a transaction in another system has also completed.

## 4. End-to-End Example: Saving a Document via Spring Cloud AWS and S3

This example uses **Spring Boot with Spring Cloud AWS 3.x and AWS SDK for Java v2**. Dependency names, configuration styles, and auto-configuration mechanisms must be checked against the compatible BOM version in your project. We decouple business logic from the S3 client, while still using Spring Cloud AWS to configure/create the client and Spring to inject dependencies.

### 4.1. Defining an Application-Owned Interface

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void put(String objectKey, byte[] content, String contentType);
}
~~~

This interface expresses the need to **store content by a key**. It does not force business logic to know about S3 buckets, Azure containers, or GCS buckets. Applications that need downloading, deletion, streaming, or versioning can design additional suitable methods; avoid trying to build a giant abstraction covering every provider-specific feature.

~~~java
// DocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStorage storage;

    public DocumentService(DocumentStorage storage) {
        this.storage = storage;
    }

    public String save(byte[] content, String contentType) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("Document must not be empty");
        }

        String objectKey = "documents/" + UUID.randomUUID();
        storage.put(objectKey, content, contentType);
        return objectKey;
    }
}
~~~

The service only knows the rule for generating object keys and the storage port. In a production system, you also need authorization, size/MIME validation, storage quotas, malicious upload protection where applicable, and request-level idempotency. The example uses a byte array for clarity; for large files, consider streaming or direct uploads via time-limited URLs with scoped permissions.

### 4.2. Adapter Translating Calls to the AWS SDK

~~~java
// S3DocumentStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
@ConditionalOnProperty(
    prefix = "app.storage",
    name = "provider",
    havingValue = "aws"
)
public class S3DocumentStorage implements DocumentStorage {
    private final S3Client s3Client;
    private final String bucket;

    public S3DocumentStorage(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    @Override
    public void put(String objectKey, byte[] content, String contentType) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

        s3Client.putObject(request, RequestBody.fromBytes(content));
    }
}
~~~

With the corresponding S3 starter, Spring Cloud AWS can auto-configure an **S3Client** bean for the adapter; the adapter still calls the AWS SDK's **putObject** API. Spring is responsible for creating/injecting the client, while the SDK executes the request to S3. If you choose **S3Template** provided by Spring Cloud AWS, the adapter calls the template API and the internal flow then reaches the SDK.

Illustrative Maven dependency (version managed via a compatible Spring Cloud AWS BOM):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Example application configuration:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    provider: aws
    bucket: ${APP_STORAGE_BUCKET}
~~~

**APP_STORAGE_BUCKET** is a resource name supplied by the deployment environment, not a credential. For example, do not put access keys/secret keys in YAML. On a developer machine, the SDK can obtain credentials from a profile or a supported login mechanism; in deployment, prefer an IAM role/identity attached to the workload and grant write permissions only to the required bucket/prefix. The region setting must match the resource and client configuration.

### 4.3. Controller and the Path of a Request

~~~java
// DocumentController.java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Map<String, String>> upload(@RequestBody byte[] body) {
        String key = documentService.save(
            body, MediaType.APPLICATION_OCTET_STREAM_VALUE);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("key", key));
    }
}
~~~

For a request with Content-Type **application/octet-stream**, the sequence is:

~~~text
POST /documents
  -> DocumentController.upload(...)
  -> DocumentService.save(...)
  -> DocumentStorage.put(...)
  -> S3DocumentStorage.put(...)
  -> S3Client.putObject(...)
  -> signed HTTPS request -> Amazon S3
  <- result from S3 <- SDK <- adapter <- service
  <- HTTP 201 + object key
~~~

This is a minimal version for observing the architecture: caller authentication/authorization, body size limits, exception mapping, and quotas must be added before production deployment. Do not treat the returned object key as a public URL; download permissions must be checked in a separate flow.

## 5. Same Port, Three Providers: What Changes?

In a port-based architecture, **DocumentService** does not need to know where data is stored. When switching to Azure or Google Cloud, you typically replace the adapter, starter, client, identity/endpoint configuration, and provisioned resources. Service semantics still have to be checked individually; the clouds are not completely equivalent.

| Concern | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Managed object storage | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Common Spring integration | Spring Cloud AWS S3 starter/template | Spring Cloud Azure Storage Blob starter | Spring Cloud GCP Storage starter |
| Typical Java client | **S3Client** (AWS SDK v2) | **BlobServiceClient** (Azure SDK) | **Storage** (Google Cloud client library) |
| Preferred runtime identity | IAM role/workload identity per AWS environment | Managed Identity + Azure RBAC | Workload Identity or appropriate service account + IAM |
| Common credential resolution | AWS default credentials chain | DefaultAzureCredential or starter credential mechanism | Application Default Credentials (ADC) |
| Corresponding messaging example | SQS / SNS | Service Bus | Pub/Sub |

Typical Azure Blob flow: **DocumentService → AzureBlobStorageAdapter → client/template configured by Spring Cloud Azure → Azure SDK → HTTPS → Blob Storage**. The Google Cloud Storage flow is similar: **DocumentService → GcsStorageAdapter → Spring Cloud GCP client/template → Google Cloud Java client → Cloud Storage API**.

When selecting an adapter via configuration, ensure the application has **exactly one DocumentStorage bean** suitable for the environment; for example, the AWS adapter enabled by the property **app.storage.provider=aws**. If two adapters are enabled simultaneously, constructor injection can become ambiguous; if none is enabled, the application fails to start. Artifact names and namespaces for Spring Cloud GCP, AWS, and Azure change across library generations, so always use documentation and BOMs matching the project's version.

Do not equate **buckets**, **containers**, access permissions, versioning, encryption, consistency, metadata, and errors across the three platforms just because all of them have a “put object” operation. The shared port should only contain guarantees that business logic actually needs; provider-specific details belong in the adapter or are explicitly modeled as dedicated capabilities.

## 6. Messaging Flow: Outbound, Inbound, and Asynchronous Processing

Sending a message follows a path similar to writing an object, but the result has a different meaning:

~~~mermaid
flowchart LR
    A[Order service] --> P[EventPublisher port]
    P --> B[Provider publisher adapter]
    B --> K[Spring integration / SDK]
    K --> Q[SQS / Service Bus / Pub/Sub]
    Q --> L[Listener container / subscriber]
    L --> C[Consumer handler]
    C --> D[Event-handling use case]
~~~

**Producer:** Business logic creates an event such as **OrderCreated**, and the adapter uses a Spring Cloud abstraction or SDK to send it to a queue/topic. A successful send response typically confirms that the broker/service accepted the message according to the API contract; it does **not** mean a consumer has already processed it successfully.

**Consumer:** Spring integration or SDK polling/subscriber receives the message, converts the payload into application data, and invokes the handler. After processing, the message is confirmed, deleted, completed, or acked according to the service mechanism. Providers differ in visibility timeout, locks, ack deadlines, ordering, retries, and dead-letter handling.

With many messaging configurations, a message **can be redelivered**: the consumer finishes processing but has not yet acked, hits a timeout, or loses connection. Handlers therefore need idempotency, such as checking whether **eventId** was already processed, enforcing a unique constraint in the database, or designing updates to tolerate repetition. Do not assume every queue/topic guarantees end-to-end exactly-once delivery by default.

If a use case both writes to a database and publishes an event, the two operations across two systems do not automatically participate in the same Spring transaction. **Transactional outbox** is a common pattern to record business state and an event record in the same database transaction, after which another component publishes the event to the cloud. Exact implementation and delivery guarantees depend on the actual system.

## 7. Where Do Identity, Permissions, Networking, and Secrets Enter the Flow?

Three issues are frequently confused:

1. **Identity (authentication):** The SDK determines “under which identity is the application calling?”. On AWS there is the credential chain/role, on Azure there is Managed Identity/DefaultAzureCredential, and on Google Cloud there is ADC/service account/workload identity. Tokens can be automatically refreshed by supporting libraries.
2. **Permissions (authorization):** The cloud service determines whether that identity is allowed to perform the action on the resource. For example, having valid credentials but lacking object-write permission still results in an access error. Permissions must be restricted according to the **least privilege** principle.
3. **Connectivity:** The client must reach the right endpoint/region/project/account over DNS, TLS, proxies, firewalls, or private networks. Timeouts or DNS resolution failures cannot be fixed simply by granting more IAM/RBAC permissions.

**Secrets** are a separate integration branch: when reading values from AWS Secrets Manager, Azure Key Vault, or Google Secret Manager, the code again goes through an adapter/template/SDK with the corresponding credentials and secret-read permissions. Never hard-code secrets or write secrets/tokens to logs; when needed, use workload identity mechanisms and manage secrets using each cloud's capabilities.

A permission check in the **application** (which records a user is allowed to upload) and a permission check in the **cloud** (which bucket a workload is allowed to write to) answer two different questions. Both are necessary; granting cloud permissions to a service does not replace end-user authorization.

## 8. Errors, Retries, and Consistency: The Return Path Is Not Always Simple

| Symptom | Layer to Check First | Remediation Approach |
| --- | --- | --- |
| Cannot create client bean or **DocumentStorage** | Spring dependencies, BOM, auto-configuration conditions, bean config | Check starters, compatible versions, profiles/conditions, and dependency injection |
| Missing credentials / unable to obtain token | Credential chain, environment identity | Determine the workload's actual runtime identity; check login/role/identity config |
| **403 / AccessDenied / PermissionDenied** | Resource permissions, policies, RBAC/IAM | Inspect actions, resource scope, deny policies, and identity; do not assume it is an HTTP caller permission error |
| Bucket/container/topic not found or wrong region/project | Resource and endpoint configuration | Verify resource name, account, project, region, and environment |
| DNS/TLS/connection timeout | Network and transport | Check outbound rules, proxy, TLS, private endpoint, endpoint URL, and timeouts |
| **429 / 503**, throttling, service unavailable | Service limits and health | Retry with backoff + jitter per SDK guidance, limit concurrency, monitor quotas |
| Upload or publish succeeded, yet downstream business logic is incomplete | Asynchronous workflow, consumer, cross-system transaction | Check acks, retries, DLQ, outbox, and idempotency |

Error-handling principles:

- The **adapter** knows SDK-specific exceptions and translates them into meaningful application errors, such as **StorageAccessException** or **StorageUnavailableException**, without losing the root cause in secure internal logs.
- The **business service** decides whether retrying or compensating is permitted. The **controller** maps errors to appropriate HTTP statuses and messages that do not leak buckets, tokens, connection strings, or sensitive data.
- Retries in the SDK and retries in Spring/application code can **stack**, multiplying actual call counts. Only retry likely transient errors, bound total duration, add backoff/jitter, and budget for quotas.
- If a response is lost after a timeout, the write or send **may have already succeeded** on the cloud side. Application APIs need an idempotency key or appropriate deduplication mechanism so retried requests do not create duplicate business effects.
- Writing an object to the cloud and writing metadata to a database involve **two separate systems**; a database transaction does not automatically roll back an uploaded object. Design operation ordering, intermediate states, cleanup/compensation, or synchronization workflows according to business needs.

## 9. Observability and Testing Across Each Boundary

Requests should be tracked end-to-end with a trace/correlation ID, business operation name, provider, resource type, duration, retry count, and normalized error code. Logs must not contain secrets, access tokens, credentials, sensitive payloads, or document contents. SDK instrumentation, trace propagation, and metric support depend on the SDK/library in use; do not assume every cloud call automatically appears in full within distributed traces simply because Spring Actuator is enabled.

A testing strategy can be divided by boundary:

| Level | What to Prove | Example |
| --- | --- | --- |
| **Business unit test** | The service builds the right request and calls the port; no credentials/cloud needed | Mock DocumentStorage, verify put is called with the expected object key and content type |
| **Adapter/contract test** | Data types, requests, responses, and exceptions map properly for the provider | S3 adapter builds the right bucket, key, metadata; handles permission-denied errors |
| **Integration test** | Spring config creates real beans, and the SDK can communicate and read/write data | LocalStack for certain AWS flows; Azurite for Blob; compatible emulator or dedicated test project for Google Cloud |
| **Controlled cloud smoke test** | Identity, IAM/RBAC, region/project, network, and quotas work in a real environment | Workload running with the deployment identity writes, reads, and deletes a test object |

Example unit test for the service without starting a Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;

class DocumentServiceTest {
    @Test
    void delegatesSaveToStoragePort() {
        DocumentStorage storage = mock(DocumentStorage.class);
        DocumentService service = new DocumentService(storage);
        byte[] content = {1, 2, 3};

        String key = service.save(content, "application/octet-stream");

        assertTrue(key.startsWith("documents/"));
        verify(storage).put(
            eq(key), same(content), eq("application/octet-stream"));
    }
}
~~~

Emulators are useful for development and CI, but they typically do not fully simulate IAM, Managed Identity, workload identity, networking, quotas, or all service behaviors. Therefore, integration tests against emulators **do not replace** testing permissions and connectivity against real cloud environments. When testing on the cloud, use isolated test resources, least-privilege permissions, and a data cleanup procedure.

## 10. Practice: Trace a Use Case and Diagnose Errors

**Exercise 1 — Trace the flow.** For an “upload invoice” request, mark where user authentication happens, where size validation happens, where the object key is generated, where the provider is selected, where credentials are obtained, and where the cloud service checks permissions. Explain the return path on success and on **403**.

**Exercise 2 — Swap the adapter.** Keep **DocumentService** and **DocumentStorage** unchanged. Sketch **AzureBlobDocumentStorage** or **GcsDocumentStorage** covering these responsibilities: selecting the container/bucket, calling a Spring-managed SDK client, mapping exceptions, and using the corresponding workload identity. List the configurations that must change when switching environments.

**Exercise 3 — Production error.** The application starts normally, but writing an object returns **AccessDenied**. Check in order: the actual identity in use, the required action/resource, IAM/RBAC and deny policies, and the resource name and region/project. Why does simply changing the connection timeout fail to fix this error?

**Exercise 4 — Duplicate writes.** A client times out and automatically retries the same upload request; the current service generates a **new UUID each time**. Propose an API-level idempotency key and a way to store results by key to avoid creating two business documents, while also handling the case where the object was already written but the database has not been updated yet.

## 11. Key Takeaways

- **Spring Boot** manages lifecycles and dependencies; **Spring Cloud integration** simplifies configuration and wiring; the **SDK** performs API communication; the **cloud service** executes operations and enforces provider-side permissions.
- Auto-configuration happens primarily at **startup**; at runtime, execution can go from the adapter **straight to the SDK** or through a Spring Cloud template.
- Separating **business service → port → provider adapter** isolates change and improves testability, but it does not erase semantic differences across AWS, Azure, and Google Cloud.
- **Identity, permissions, networking, retries, and observability** span the entire flow; a successful send does not mean an entire asynchronous workflow or multi-system operation is complete.
- When an incident occurs, walk each boundary **Spring bean → adapter → SDK/credential → transport → managed service → response/exception** to locate the responsible layer.
