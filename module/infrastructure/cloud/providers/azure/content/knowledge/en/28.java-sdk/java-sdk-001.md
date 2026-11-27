# Azure SDK for Java Structure and Library Version Management

A Java application using Azure may need to read files from Blob Storage, retrieve secrets from Key Vault, send messages into Service Bus, and invoke resource management APIs. Each service has its own Java library. If a project imports incompatible versions, mixes legacy SDK classes with modern ones, or upgrades dependencies without testing, the application can hit compilation errors, runtime missing-method errors, Reactor/Netty conflicts, or hard-to-diagnose authentication failures.

**Azure SDK for Java** is the ecosystem of Java libraries that enable applications to work with Microsoft Azure services. Modern libraries share a relatively consistent structure: **service client**, **client builder**, **authentication credential**, **HTTP pipeline/transport**, **model types**, **synchronous/asynchronous** APIs, and logging/retry mechanisms. Managing library versions, especially via a **Bill of Materials (BOM)**, helps a project control a curated set of dependencies instead of manually combining individual versions that might conflict.

This lesson belongs to the **Azure SDK for Java** chapter of the **CLOUD_PROVIDERS_AZURE** module. It serves as a bridge between knowledge of subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and data, and performing deployment, monitoring, security, and cost-control operations on Azure from Java applications.

> **Lesson Scope:** Examples focus on the modern generation of Azure SDK for Java, commonly referred to as **Track 2**. Artifact names, versions, JDK baselines, and SDK surfaces change by service and over time. Do not treat illustrative version numbers as the latest release: select BOM/SDK versions verified from official release pages, compatibility matrices, and your project's security policy. Code snippets that call Azure in this lesson are clearly marked as read-only or data-mutating.

## Learning Objectives

After this lesson, you will be able to:

1. Describe the roles of **azure-core**, **azure-identity**, service-specific libraries, HTTP transports, and the management SDK.
2. Distinguish between the **data plane SDK** and **management plane SDK**, as well as **Track 1** and **Track 2** libraries.
3. Read the **ClientBuilder → Client → Operation → Model/Response** structure and locate the corresponding packages.
4. Understand synchronous/asynchronous clients, **Reactor Mono/Flux**, **PagedIterable/PagedFlux**, and **SyncPoller/PollerFlux**.
5. Use **DefaultAzureCredential** and managed identities properly without embedding access keys in source code.
6. Manage versions with **com.azure:azure-sdk-bom** in Maven and Gradle.
7. Distinguish between **Azure SDK BOM**, **Spring Cloud Azure BOM**, management library BOMs, and versions not covered by a BOM.
8. Diagnose dependency conflicts, JDK/framework compatibility issues, and **NoSuchMethodError/ClassNotFoundException** errors.
9. Establish workflows for upgrading, testing, recording an SBOM, reviewing CVEs, and rolling back.
10. Build a checklist for SDK selection, security, retries, performance, telemetry, and production deployment.

## 1. What Does the Azure SDK Help With?

There is no single Java JAR containing all Azure features. Instead, developers choose client libraries based on the service and operation type.

~~~text
Java Application
     |
     +-- azure-storage-blob ------------> Blob Storage: GET/PUT/list
     |
     +-- azure-security-keyvault-secrets -> Key Vault: get/set secrets
     |
     +-- azure-messaging-servicebus ----> Service Bus: send/receive
     |
     +-- azure-messaging-eventhubs -----> Event Hubs: produce/consume
     |
     +-- azure-cosmos ------------------> Cosmos DB: items/query
     |
     +-- azure-resourcemanager* --------> Azure Resource Manager operations
     |
     +-- azure-identity ----------------> Microsoft Entra credentials
     |
     +-- azure-core --------------------> common pipeline/models/paging
~~~

The * indicates that the management SDK group has **separate Maven coordinates and version management** compared to many service-client libraries. Do not assume every library belongs to the same BOM.

### Why Use the SDK Instead of Calling REST Manually?

- The client handles authentication headers and token acquisition according to the credential.
- Service models provide strongly typed Java data structures.
- Retry, paging, and polling mechanisms are partially standardized.
- Supports the HTTP pipeline, diagnostics, and tracing per library.
- Reduces manual request URI construction and response status handling.

However, **the SDK does not replace understanding the service**. A method to list blobs can trigger multiple requests, writing a Key Vault secret remains a security-sensitive change, and retrying a non-idempotent command can create duplicate data.

## 2. Data Plane and Management Plane

This is an important distinction right from the start:

| API Type | Purpose | Examples |
|---|---|---|
| **Data plane** | Read/write/consume service data, messages, or secrets | Reading a blob, receiving a Service Bus message, querying Cosmos DB, fetching a Key Vault secret |
| **Management plane** | Create/configure/delete Azure resources via Azure Resource Manager | Creating a storage account, enabling diagnostic settings, configuring a resource group |

~~~text
                  Java application
                         |
                  +------+------+
                  |             |
                  v             v
             Data-plane      Management-plane
             SDK client      SDK/ARM client
                  |             |
                  v             v
             Blob endpoint   management.azure.com
             Key Vault URI   ARM resource providers
             Service Bus     Azure subscription/RG
~~~

### Permissions Differ as Well

A managed identity with the **Storage Blob Data Reader** role can read blobs within its scope, but cannot necessarily create a storage account. Conversely, having an Azure management role at the subscription level does not imply having permission to read all data inside Blob Storage or Key Vault.

Do not grant **Owner** on a resource group just because an application needs to read a file; properly distinguish between actions and Azure data-plane vs. management-plane RBAC.

## 3. Azure SDK for Java Library Groups

| Group | Example Artifact/Package | Role |
|---|---|---|
| **Common core** | com.azure:azure-core | HTTP pipeline structure, logging, paging/polling, shared models |
| **Authentication** | com.azure:azure-identity | DefaultAzureCredential, ManagedIdentityCredential, and credential builders |
| **HTTP transport** | com.azure:azure-core-http-netty | Netty-based HTTP transport for supported SDKs |
| **Alternative transport** | com.azure:azure-core-http-okhttp | OkHttp-based HTTP client when appropriate |
| **Storage** | com.azure:azure-storage-blob | Blob clients and request/response models |
| **Key Vault** | com.azure:azure-security-keyvault-secrets | SecretClient, SecretAsyncClient |
| **Service Bus** | com.azure:azure-messaging-servicebus | Producers, receivers/processors |
| **Event Hubs** | com.azure:azure-messaging-eventhubs | Event producer/consumer |
| **Cosmos** | com.azure:azure-cosmos | CosmosClient/async clients, data operations |
| **Resource management** | com.azure.resourcemanager:* | ARM fluent clients for supported services |
| **Spring integrations** | com.azure.spring:* | Spring Cloud Azure starters and configuration |

**Not every library sharing a groupId is included in azure-sdk-bom**, especially preview libraries, Spring Cloud Azure, and resource-manager libraries. A BOM manages **only the artifacts listed in that BOM**, and does not enforce versions across all of Maven Central.

### Is Core a Service SDK?

No. **azure-core** contains shared primitives, but on its own it does not allow calling **BlobClient** or **SecretClient** without adding the service-specific artifact.

### Does azure-identity Create Azure Resources?

No. It provides ways to acquire tokens/credentials. To read a Blob you need a Blob client; to create a resource group you need the management API and corresponding permissions.

## 4. Typical Dependency Diagram

~~~text
                Java REST API
                     |
       +-------------+----------------+
       |                              |
       v                              v
 azure-storage-blob              azure-identity
       |                              |
       +--------------+---------------+
                      |
                      v
                  azure-core
                      |
               HTTP client interface
                      |
                 +----+----+
                 |         |
                 v         v
              Netty      OkHttp
         (depending on dependency/transport)
                      |
                      v
            Azure service endpoint
~~~

This is a **conceptual diagram**, not an exact dependency graph for every version. SDKs also use supporting libraries such as Reactor, Netty, Jackson, or other components; an artifact can pull in dependencies transitively.

### Why Does the Graph Matter?

An application might add azure-storage-blob without directly declaring azure-core. Maven/Gradle still brings azure-core onto the **runtimeClasspath** via transitive dependencies. If another dependency forces an incompatible version of azure-core, runtime errors can occur even when individual modules compile cleanly.

## 5. Track 1 and Track 2

Azure has had multiple generations of Java SDKs. Many older packages use **com.microsoft.azure** or different API/client patterns. Modern SDKs typically use **com.azure** for data-plane libraries, featuring a more consistent design.

| Aspect | Track 1 / legacy | Track 2 / modern |
|---|---|---|
| Common Maven group/package | com.microsoft.azure or older SDK packages | com.azure and com.azure.resourcemanager depending on type |
| Client construction | Varies by generation | Typically via *ClientBuilder* |
| Authentication | Legacy credential APIs | azure-identity with TokenCredential |
| Async model | Varies by legacy library | Typically Reactor Mono/Flux |
| Common pipeline | Older architecture and inconsistent APIs | azure-core, HTTP policy patterns |
| Release management | Legacy version lines | Azure SDK BOM and modern library release guidance |

**There is no automatic rule that "all com.microsoft.* packages are Track 1"**; it is simply a cue to verify the exact package/docs. Some services have dedicated migration guides.

### Azure Storage Difference Example

- The legacy Blob SDK has different classes and artifacts compared to the modern BlobServiceClient/BlobClient.
- Changing Maven coordinates **is not enough**: you must update imports, authentication, client construction, paging, request models, and error handling.
- Some features or overloads do not have a one-to-one equivalent.

### Upgrade Rule

**Do not mix Track 1 and Track 2 sample code in the same file expecting automatic compatibility.** Inventory legacy classes and review the service-specific migration guide, backed by tests.

## 6. Package Organization of Modern SDKs

Using Blob Storage as an example:

~~~text
com.azure.storage.blob
   BlobServiceClientBuilder
   BlobServiceClient
   BlobServiceAsyncClient
   BlobContainerClient
   BlobContainerAsyncClient
   BlobClient
   BlobAsyncClient

com.azure.storage.blob.models
   BlobItem
   BlobProperties
   BlobStorageException
   ...

com.azure.identity
   DefaultAzureCredentialBuilder
   ManagedIdentityCredentialBuilder

com.azure.core
   credential.TokenCredential (per actual package)
   http/policy, util, exception, ...
~~~

These classes illustrate the library pattern; before writing imports, always verify the **Javadoc of the exact artifact and version**.

### Typically Four Types of Classes

1. **Builder:** configures endpoint, credential, HTTP client, retries, and logging.
2. **Client:** sends operations to the service.
3. **Model/Options:** passes parameters and holds response data.
4. **Exception/Response:** represents errors, status codes, headers, and diagnostics.

An SDK may provide a **specialized client** for a specific service scope; not all methods live on a single "god client."

## 7. Builder Pattern in the Azure SDK

Common usage pattern:

~~~java
SomeServiceClient client = new SomeServiceClientBuilder()
    .endpoint("https://service-endpoint")
    .credential(credential)
    .buildClient();
~~~

This is **pseudocode** to illustrate the Builder pattern, not an actual class name.

### What a Builder Typically Needs

- **Endpoint:** the correct hostname/URI of the Azure resource.
- **Credential:** how to obtain a token or key, depending on the service.
- **HTTP client:** default or custom transport.
- **Client options/policies:** retry, logging, tracing, user agent, or transport tuning where supported by the API.
- **Sync/async choice:** buildClient() or buildAsyncClient() if both are offered.

### Caution with Builder Methods

Method names **are not identical across every SDK**. For example, the Blob builder differs from the Cosmos DB builder and the Service Bus builder. Do not assume `.retryOptions()` or `.endpoint()` shares the same overloads across all libraries.

## 8. Real Example: BlobServiceClientBuilder

This is a **read-only** Java example using Microsoft Entra credentials to check whether a known blob exists. It does not upload or delete data.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobReadOnlyCheck {
    public static void main(String[] args) {
        String endpoint = required("AZURE_BLOB_ENDPOINT");
        String containerName = required("AZURE_BLOB_CONTAINER");
        String blobName = required("AZURE_BLOB_NAME");

        BlobServiceClient serviceClient =
            new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        BlobClient blob = serviceClient
            .getBlobContainerClient(containerName)
            .getBlobClient(blobName);

        // exists() performs a service request to read metadata,
        // requires data permissions, and may incur transaction charges.
        System.out.println("Blob exists: " + blob.exists());
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

### Explanation

1. **AZURE_BLOB_ENDPOINT** is an endpoint such as the HTTPS FQDN of an authorized account; do not append a SAS token in source code.
2. **DefaultAzureCredential** tries identity sources appropriate for the environment; it does not automatically grant Storage Blob Data Reader.
3. **getBlobContainerClient/getBlobClient** construct client objects; **exists()** is what sends the request to Azure.
4. If the blob does not exist, exists() typically returns false; 403 or network errors can still throw an exception.
5. Proper TLS, Private Endpoint, DNS, and RBAC are required for it to work.
6. Create and reuse service clients over the application lifecycle; do not re-instantiate them per HTTP request.
7. **Do not assume read-only means zero cost**: Azure Storage still bills transactions according to its pricing model.

### Prerequisites to Run

- Compatible **azure-storage-blob** and **azure-identity** dependencies.
- A JDK version supported by the libraries.
- The runner is signed in or has a managed identity assigned.
- Minimum required Storage data-plane permissions.
- Valid storage endpoint, container, and blob name.
- Java process can reach the endpoint through network/firewalls.

## 9. Synchronous (sync) and Asynchronous (async)

Modern Azure SDKs typically offer both sync and async clients (depending on the service).

| Aspect | Sync client | Async client |
|---|---|---|
| Result | Returns value or throws exception directly | Mono/Flux or other reactive API |
| Thread model | Calling thread typically blocks on request | Non-blocking flows with subscriptions |
| Best suited for | CLI tools, small batches, thread-per-request apps | Reactive services, high-concurrency I/O |
| Readability | Straightforward | Requires understanding reactive streams and cancellation |
| Common pitfalls | Blocking threads for too long | Forgetting to subscribe, blocking the event loop, missing error handling |

### Sync Example

~~~java
boolean present = blob.exists();
System.out.println(present);
~~~

### Async Example

~~~java
import com.azure.storage.blob.BlobAsyncClient;

BlobAsyncClient asyncBlob = asyncServiceClient
    .getBlobContainerAsyncClient(containerName)
    .getBlobAsyncClient(blobName);

asyncBlob.exists()
    .subscribe(
        exists -> System.out.println("Exists: " + exists),
        error -> System.err.println(
            "Azure Blob read failed: " + error.getClass().getSimpleName()
        )
    );
~~~

The async snippet assumes **asyncServiceClient** was already built via **BlobServiceClientBuilder.buildAsyncClient()**. It does not guarantee the process waits for the subscription to complete: in a short `main` program, you need lifecycle/completion handling rather than just calling `subscribe()` and exiting.

### Mono and Flux

**Mono<T>** represents at most one result or an error; **Flux<T>** represents multiple elements. Reactor is a core component in many async Azure SDKs; handling subscription, cancellation, and backpressure must follow the library's contract.

**Do not call `.block()` on an event-loop thread** of a WebFlux service just to "turn async into sync": it can cause deadlocks or degrade throughput. If your code follows an imperative style, use the appropriate sync client.

## 10. Paging: PagedIterable and PagedFlux

An API listing millions of blobs or secrets does not necessarily return everything in a single HTTP response. The Azure SDK provides shared paging utilities.

~~~text
Java call listItems()
        |
        v
Page 1 (continuation token)
        |
        v
Page 2 (continuation token)
        |
        v
Page 3 ...
~~~

### Sync: PagedIterable

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;

BlobContainerClient container = serviceClient
    .getBlobContainerClient(containerName);

// Only test on a small authorized LAB container.
int count = 0;
for (BlobItem item : container.listBlobs()) {
    System.out.println(item.getName());
    if (++count >= 10) {
        break;
    }
}
~~~

### Cost and Security Warnings

- Iterating over **PagedIterable** may trigger multiple HTTP requests during traversal.
- Printing blob names in production can expose sensitive data.
- Stopping after 10 items does not guarantee the SDK made only one HTTP request.
- To find a specific blob, a **point lookup** is usually better than listing the entire container.
- For large containers, use prefix filters, pagination, and proper telemetry.

### Async: PagedFlux

Many services provide **PagedFlux<T>** for streaming pages and items. Avoid collecting all results into RAM with `collectList()` when data volume is large. Use limits, cancellation, and backpressure according to Reactor patterns.

## 11. Long-Running Operations: Pollers

Some management operations (creating/deleting resources, triggering deployments) do not complete immediately. The SDK may use:

- **SyncPoller** for synchronous flows.
- **PollerFlux** for reactive flows, depending on the library.

~~~text
Client request: create resource
      |
      v
Azure returns Accepted/InProgress status
      |
      v
Poller tracks status
      |
      +-- InProgress
      +-- Succeeded
      +-- Failed / Canceled
~~~

### Why Does This Matter?

- Submitting the command does not mean the resource is ready yet.
- Polling too frequently can create overhead.
- Timeouts, cancellation, and error handling are required.
- You must check the final status and outcome, not just HTTP 202.
- For resource creation/deletion, apply least-privilege, approval, and rollback principles.

Do not write your own infinite `while` polling loop if the SDK already provides an appropriate poller; at the same time, do not assume pollers behave identically across every SDK or operation.

## 12. Azure Core and the HTTP Pipeline

A service request passes through several layers:

~~~text
ServiceClient.method(...)
      |
      v
Serialize request/model
      |
      v
HTTP pipeline
  - authentication / request signing
  - retry policy
  - diagnostics/logging/tracing
  - custom policies when supported
      |
      v
HTTP transport (Netty/OkHttp/...)
      |
      v
Azure service endpoint
      |
      v
HTTP response -> deserialize -> model/error
~~~

**azure-core** provides shared primitives and abstractions for the pipeline, policies, HTTP requests/responses, paging, polling, exceptions, and tracing. Individual service SDKs can add custom policies and their own defaults.

### Does Swapping the HTTP Client Solve Every Error?

No. If the error is 403 due to RBAC, switching from Netty to OkHttp will not grant permissions. If the error is a timeout caused by a firewall, changing the retry policy may only prolong the failure.

## 13. Transport: Netty and OkHttp

Two common transport artifacts:

- **com.azure:azure-core-http-netty**
- **com.azure:azure-core-http-okhttp**

A service library may depend on a default HTTP transport or allow configuring a custom transport.

| Condition | Selection Guidance |
|---|---|
| Using SDK with tested defaults | Keep the default transport when appropriate |
| Application already heavily uses Netty/Reactor | Verify version alignment and lifecycle |
| Organization standardized on OkHttp | Check SDK transport API and compatibility |
| Special proxy or network requirements | Evaluate transport options per SDK documentation |
| TLS/ALPN/connection pool errors | Triage network/JDK/dependencies before changing transport |

### Do Not Add Both "Just in Case"

Having multiple HTTP clients on the classpath can complicate the dependency graph; the SDK locates transports via factory/config mechanisms. If you want a specific client, **configure it explicitly and test the runtime classpath**.

### Connection Pooling and Thread Lifecycle

Service clients are generally designed to be **reused**. Creating new clients on every request can increase socket churn, TLS handshakes, and threads. However, closing clients that share a transport can behave differently from clients owning their own transport: read the exact lifecycle contract for your SDK version.

## 14. Authentication: azure-identity

To integrate with Microsoft Entra ID, the SDK provides credential builders via the **com.azure:azure-identity** artifact.

### Common Options

| Credential | Scenario | Notes |
|---|---|---|
| **DefaultAzureCredential** | Local dev and many Azure workloads | Environment-dependent credential chain; control identity sources |
| **ManagedIdentityCredential** | App Service, VM, Azure Functions, Container Apps, etc. where supported | No stored client secret; must assign proper roles |
| **WorkloadIdentityCredential** | Federated workloads such as AKS Workload Identity | Requires federation/OIDC/service account and roles |
| **AzureCliCredential** | Local development after `az login` | Should not be used as a production auth mechanism |
| **ClientSecretCredential** | Automation when secrets cannot yet be avoided | Requires secret rotation and Key Vault |
| **ClientCertificateCredential** | Automation using certificates | Securely manage certificates and private keys |

The SDK accepts a TokenCredential and calls the service using the scopes/audience required by the client library and service.

### DefaultAzureCredential

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

**Nothing in this code grants permissions to the identity**. Permissions are configured in Entra ID/Azure RBAC and data-plane systems.

### Common Identity Pitfalls

A developer laptop may have multiple tenants or environment variables set for a service principal. DefaultAzureCredential might pick a different credential source than intended. Therefore:

1. Identify the target tenant and subscription.
2. Control authentication environment variables.
3. Verify the actual principal in safe logs and Azure activity/audit logs.
4. Never log raw access tokens.
5. In production, consider explicit managed/workload identity when predictability is required.

## 15. Managed Identity for Java Applications

~~~text
Java app on Azure (managed identity)
      |
      v
Azure Identity SDK acquires token
      |
      v
Azure Blob SDK sends request over TLS
      |
      v
Storage data-plane authorization
      |
      +-- Allowed -> data/metadata response
      +-- Denied  -> 403
~~~

### Example: Selecting a User-Assigned Managed Identity

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalStateException("Missing AZURE_CLIENT_ID");
}
TokenCredential credential =
    new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

The Client ID is an identity identifier, not a secret. **The managed identity must be attached to the compute resource** and granted service data-plane permissions. If the compute platform does not support it or the identity is not attached, the credential cannot work on its own.

### Example Permissions

An API that only needs to view blobs can be assigned **Storage Blob Data Reader** scoped to the required container or resource. If the application needs to upload, permissions must be reviewed carefully; never elevate to subscription Owner as a quick workaround.

## 16. Connecting to Azure: TLS, DNS, and Private Endpoints

~~~text
Java app (AKS/App Service)
          |
          | TLS HTTPS to service FQDN
          v
Private DNS / approved public DNS
          |
          v
Private Endpoint / service route
          |
          v
Azure Blob/Key Vault/Service Bus
~~~

The SDKs do not configure VNets, firewalls, or private DNS for you. When a client API reports **UnknownHostException**, **ConnectTimeoutException**, **SSLHandshakeException**, or 403, diagnose by layer:

| Layer | What to Check |
|---|---|
| DNS | FQDN, private DNS zone, resolver, network namespace |
| TCP/network | NSG, UDR, firewall, routing, allowed ports |
| TLS | JDK truststore, certificate chain, hostname verification |
| Identity | Token/tenant/principal, managed identity assignment |
| Authorization | Data-plane role, ACL, resource scope |
| Service | Quota, request parameters, endpoint version, service state |

**Never disable TLS certificate validation or open public access to the entire Internet to "fix" an SDK error**. Private Endpoints do not replace TLS, and Entra ID does not replace data-plane permissions.

## 17. Client Exceptions and Error Handling

The Azure SDK provides exceptions representing different failure classes:

- **ClientAuthenticationException**: credential/authentication issues depending on the library.
- **HttpResponseException** and its subclasses: the service returned an HTTP error.
- **ResourceNotFoundException**: certain cases where a resource does not exist.
- **ServiceRequestException**: potentially related to network or request transmission.
- **ServiceResponseException**: response or protocol issues, depending on the SDK.
- **Service-specific exceptions**: for example, BlobStorageException carries Blob error code details.

### Do Not Swallow Errors Blindly

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    boolean exists = blob.exists();
    System.out.println("Present: " + exists);
} catch (BlobStorageException ex) {
    // Do not log URIs containing SAS tokens, access tokens, or secrets.
    System.err.println(
        "Blob request failed, HTTP status: " + ex.getStatusCode()
    );
    throw ex;
}
~~~

This snippet is in the context of the **blob** variable built in section 8. For other failures like DNS or auth errors, catch and record telemetry at the appropriate handler layer instead of assuming every exception is a BlobStorageException.

### Common Distinctions

| Code/Error | Typical Meaning | What to Check |
|---|---|---|
| **401** | Invalid or missing auth token/credential | Credential type, audience, tenant |
| **403** | Missing permissions or blocked by service network/firewall policy | Data-plane role/ACL, firewall |
| **404** | Resource/path does not exist or is not visible | Endpoint, container, blob name |
| **409** | Conflict/state mismatch | Resource state, operation semantics |
| **412** | Preconditions/ETag mismatch | Optimistic concurrency |
| **429** | Throttling/rate limit | Retry-after, quota, throughput |
| **5xx** | Server/transient failure | Bounded retry and diagnostics |
| **NoSuchMethodError** | Java runtime linkage/dependency conflict | Version alignment, dependency tree |

Exact HTTP mappings vary by Azure service; **do not rely solely on a status code to infer root cause**—inspect the error code, request ID, and service diagnostics.

## 18. Retries: Useful Defaults, Not Magic

SDKs provide default or configurable retry policies depending on the service. Behavior is affected by:

- Request type and **idempotency**.
- HTTP status and service error code.
- **Retry-After** headers or backoff strategy.
- Total request deadline.
- Throttling and quotas.
- Request cancellation support.

### Two Common Mistakes

1. **Infinite retries** when the service returns 403: permission errors are not fixed by retrying.
2. **Retrying non-idempotent writes** after a timeout: a request may have already been processed by the server even though the response was lost.

Load example:

~~~text
100 instances send requests
  -> Azure service throttles / network times out
  -> each instance retries immediately 10 times
  -> load spikes to 1,000 requests
  -> outage lasts even longer
~~~

### Rules

1. Use the service SDK defaults when suitable.
2. Enforce retry limits, backoff + jitter, and a total request deadline.
3. Do not stack multiple retry layers that exceed the deadline (SDK + Spring Retry + gateway).
4. For writes, define an idempotency key, ETag, or conditional operation when needed.
5. Measure retry counts and end-to-end latency, not just single-attempt duration.

Do not copy **RetryOptions** code from Blob to Cosmos DB without checking the builder and API for the exact SDK and version.

## 19. Why Is Azure SDK Version Management Difficult?

Suppose a Java API uses:

~~~text
azure-storage-blob
azure-identity
azure-security-keyvault-secrets
azure-messaging-servicebus
spring-boot-starter-web
spring-webflux (in part of the system)
~~~

Each library has its own dependencies. A Blob SDK version may depend on azure-core and Netty; Azure Identity has token-acquisition dependencies; Spring Boot has its own BOM managing many common Java libraries.

If a developer picks a set of versions from an outdated blog post:

- **azure-core** may be downgraded to a version missing a method called by a newer SDK.
- **reactor-core** or Netty may be pushed to an incompatible version.
- A security patch may only exist in a newer SDK or transport release.
- **NoSuchMethodError** may only surface at runtime when calling the Azure API.
- Different build/runtime environments can resolve different dependency trees, making bugs hard to reproduce.

### Dependency Management Goals

1. **A single clear source of truth for versions**.
2. **Reproducible dependency resolution**.
3. **Verified compatibility** with the JDK, frameworks, and other libraries.
4. **Controlled application of security patches**.
5. **Defined upgrade schedules and rollback plans**.

## 20. What Is the Azure SDK Bill of Materials (BOM)?

A **BOM (Bill of Materials)** in the Maven ecosystem is a **POM that manages dependency versions** for a group of artifacts. **com.azure:azure-sdk-bom** provides a curated set of versions selected by the Azure SDK team for the libraries **included in that BOM release**.

~~~text
Application POM / Gradle build
           |
           v
Azure SDK BOM (one approved version)
           |
           +--> azure-core                : aligned version
           +--> azure-identity            : aligned version
           +--> azure-storage-blob        : aligned version
           +--> azure-security-keyvault-* : aligned version
           +--> ... artifacts included in the BOM
~~~

### What Does the BOM Do?

- Allows omitting versions in dependency declarations for artifacts covered by the BOM.
- Reduces errors caused by picking mismatched individual versions.
- Lets teams focus on **one BOM version** when upgrading the SDK suite.
- Makes it easier to track release notes and security updates.

### What Does the BOM NOT Do?

- It does **not automatically add** azure-storage-blob to the classpath if the dependency is not declared.
- It does not automatically migrate code when APIs change.
- It does not manage every dependency outside its curated list.
- It does not guarantee compatibility with every Spring or JDK version.
- It does not apply CVE patches if you do not upgrade the BOM or if your config overrides versions.
- It does not guarantee every Azure service preview library is included in the BOM.

### BOM Version and SDK Version Are Two Different Things

A BOM release has its own version, such as **BOM_RELEASE_X**, and manages service SDKs that each have independent versions. Do not assume every artifact carries the **BOM_RELEASE_X** version number.

## 21. Maven: Importing azure-sdk-bom Properly

In a standard Java Maven **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.org</groupId>
  <artifactId>azure-sdk-lab</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-sdk-bom</artifactId>
        <version>REPLACE_WITH_APPROVED_BOM_VERSION</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-identity</artifactId>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-security-keyvault-secrets</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**You must replace** the string **REPLACE_WITH_APPROVED_BOM_VERSION** with an actual verified version. This is an intentional template, not a ready-to-run POM as-is.

### Why Don't the Dependencies Need Versions?

Because **dependencyManagement** sets default versions for matching coordinates. Maven still requires a **dependency entry** under dependencies for the library to be used directly. Importing the BOM alone without declaring azure-storage-blob will not provide the Blob SDK to your Java code.

### Why JDK Release = 17?

This is an **illustrative LTS JDK** for the practice project. The JDK baseline and support matrix for each Azure SDK, framework, build plugin, and runtime image must be verified separately. Do not assume every artifact requires JDK 17 or that all JDK combinations are supported.

### Can You Specify a Direct Version for the Blob SDK?

Yes, though if you declare:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-storage-blob</artifactId>
  <version>MANUALLY_SELECTED_VERSION</version>
</dependency>
~~~

A direct version can override the version managed by the BOM. This reduces alignment benefits and requires justification along with integration tests. **Manual overrides are discouraged if done simply because a blog post showed a higher version**.

## 22. Gradle: Using the BOM with platform

With Gradle Groovy DSL in **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        'com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION'
    )

    implementation 'com.azure:azure-identity'
    implementation 'com.azure:azure-storage-blob'
    implementation 'com.azure:azure-security-keyvault-secrets'
}
~~~

In Gradle Kotlin DSL (**build.gradle.kts**):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(
        platform("com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION")
    )
    implementation("com.azure:azure-identity")
    implementation("com.azure:azure-storage-blob")
    implementation("com.azure:azure-security-keyvault-secrets")
}
~~~

### How Does platform Differ from enforcedPlatform?

**platform** feeds constraints from the Maven BOM into Gradle's dependency resolution; depending on the graph, other version constraints may still influence the outcome. **enforcedPlatform** applies strict constraints that can conflict with other libraries or frameworks, including when dependencies are published to downstream consumers.

Do not default to `enforcedPlatform` just to mask a dependency error. First inspect the graph, version selection reasons, and compatibility.

### Do Maven and Gradle Always Pick the Same Dependency Graph?

**Do not assume so**. Maven dependency mediation and Gradle conflict resolution follow different rules. Even with the same BOM, plugins, dependency constraints, and direct overrides can produce different final classpaths. Always verify resolved versions using your actual build tool.

## 23. Dependency Management vs. Dependency Declaration

~~~text
Import BOM into dependency management
               |
               v
Manages available versions
               |
               +-- Has dependency declaration --> library can enter graph
               |
               +-- No declaration --------------> library is not added automatically
~~~

### Example

A project imports the BOM, and then Java code adds:

~~~java
import com.azure.storage.blob.BlobServiceClientBuilder;
~~~

However, **pom.xml does not declare azure-storage-blob**. The compiler will report a missing package even though the BOM manages the version of azure-storage-blob. The fix is to add the dependency artifact, **not to randomly import another BOM**.

### The Dependency Tree Still Has Transitive Versions

Declaring azure-storage-blob can pull in azure-core and an HTTP transport; if the graph has multiple dependency paths, you must inspect the selected versions. Having a BOM does not eliminate the need to inspect the dependency tree when linkage or runtime errors occur.

## 24. The BOM Does Not Manage All Libraries

A Java project on Azure also uses:

- Spring Boot and Spring Cloud Azure.
- Azure Resource Manager management SDK.
- Micrometer/OpenTelemetry.
- Reactor, Netty, Jackson.
- JDBC drivers for SQL Server/Azure SQL.
- MSAL4J or other auth libraries in specialized integrations.
- Other HTTP clients and utilities.

These libraries **are not necessarily managed by com.azure:azure-sdk-bom**. Specifically:

| Library Family | Management Approach |
|---|---|
| **Azure data-plane SDK** | azure-sdk-bom if the artifact is listed in the BOM |
| **Spring Boot** | Spring Boot dependency management/BOM and compatibility |
| **Spring Cloud Azure** | Spring Cloud Azure BOM/dependencies and compatibility matrix |
| **Azure management SDK** | Manage via its separate release/BOM if available and verified |
| **Reactor/Netty/Jackson** | Inspect resolved graph and framework constraints |
| **Preview/beta service SDK** | Verify whether the artifact is covered by the BOM or must be pinned separately |

### Especially for Beta/Preview

A preview library can introduce breaking API or behavioral changes between releases. Do not assume it is managed by the stable BOM and do not upgrade arbitrarily to a preview release just because its version number looks higher.

## 25. Spring Boot and Spring Cloud Azure BOM

When an application uses Spring Boot, its dependency system already defines version constraints for Spring Framework, Reactor, Netty, logging, and many other libraries. **Spring Cloud Azure** provides starter integrations for accessing Azure using Spring idioms.

Example artifacts:

~~~text
com.azure.spring:spring-cloud-azure-starter-storage-blob
com.azure.spring:spring-cloud-azure-dependencies
~~~

### Choosing by Integration Style

| What are you doing? | Initial Choice |
|---|---|
| Writing a plain Java app with BlobServiceClient | azure-storage-blob + azure-identity, Azure SDK BOM |
| Using Spring property binding/autoconfiguration | Appropriate Spring Cloud Azure starter/BOM |
| Using both Spring starters and direct Azure SDK in one app | Inspect both BOMs and the version graph; avoid conflicting azure-core constraints |
| App only needs one REST endpoint calling Blob | Direct SDK may suffice; adding a starter is not mandatory |

### Example Spring-Oriented Maven Fragment

~~~xml
<!-- Inside a Spring Boot app already configured with an appropriate parent/BOM. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>APPROVED_SPRING_CLOUD_AZURE_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
  </dependency>
</dependencies>
~~~

This is a **fragment for a Spring project that already has dependency management**, not a complete POM. You must select a matching **Spring Boot ↔ Spring Cloud Azure compatibility matrix** combination and verify the resolved Azure SDK versions. Do not paste two separate `dependencyManagement` blocks verbatim if the POM already has one; merge them into valid Maven structure.

### Should You Also Import the Azure SDK BOM?

There is no universal answer. If Spring Cloud Azure BOM already manages several Azure libraries, importing another Azure SDK BOM can cause unintended version mediation. **Choose a clear BOM strategy**, verify import order/rules and the dependency tree, and run integration tests. For modules using the Azure SDK directly without Spring Cloud Azure, the Azure SDK BOM is often easier to manage.

## 26. Azure Resource Manager SDK Is a Separate Branch

Azure Resource Manager is used for operations like creating or configuring storage accounts, virtual machines, or resource groups. Some Java packages:

~~~text
com.azure.resourcemanager
com.azure.resourcemanager.storage
com.azure.resourcemanager.compute
com.azure.resourcemanager.resources
~~~

You should not try to use BlobServiceClient to create an Azure storage account: that is a different management operation. Conversely, a resource-manager client does not replace BlobClient for reading files directly.

### Versioning Must Be Separated

Artifacts in the **com.azure.resourcemanager** group have different release policies, versions, and dependency management mechanisms than many **com.azure** data-plane artifacts. **Verify whether a dedicated BOM exists for the management SDK and check published versions** instead of assuming `azure-sdk-bom` manages everything.

### Permissions and Risks

The Management SDK can create, delete, resize capacity, or alter network configurations. Even if service code runs with a managed identity, it can still make sweeping changes if that identity has broad permissions. Separate runtime data-plane identities from resource-management automation identities whenever possible.

## 27. Semantic Versioning and Version Number Meaning

Many Java artifacts follow the format:

~~~text
major.minor.patch
    |    |     |
    |    |     +--> maintenance/bug/security fixes
    |    +--------> features/compatible evolution per policy
    +-------------> major changes, potentially breaking
~~~

This is a **directional guideline**, not an unbreakable law across all Azure SDKs:

- Release notes and migration guides are the authoritative sources for actual breaking changes.
- Minor or patch releases may still contain behavioral changes tied to bug fixes.
- Preview/beta releases have different stability guarantees than stable releases.
- A new version can raise the minimum JDK baseline or alter transitive dependencies.
- An SDK client version does not equal the service's **REST API version**.

### Two Version Numbers Not to Confuse

**Artifact version:** the Java JAR version downloaded by Maven or Gradle.

**Service API version:** the protocol/API version the client uses when calling Azure, typically chosen or configured by the SDK/service based on capabilities.

Upgrading the service API version can change features and serialization; upgrading the JAR can change implementation details, dependencies, or REST API selection. Do not treat them as the same change.

## 28. JDK, Compiler, and Runtime Compatibility

A system involves three version components:

~~~text
JDK used to compile
       |
       v
Class file bytecode target
       |
       v
JRE/JDK running on Azure
       |
       +-- Spring Boot runtime
       +-- Azure SDK libraries
       +-- Reactor/Netty/HTTP transport
~~~

### Common Errors

- Compiling with a newer JDK and running on an older Java runtime → **UnsupportedClassVersionError**.
- A library raises its minimum JDK, but the build pipeline has not been upgraded → compile/bytecode errors.
- Spring Boot version is incompatible with the Spring Cloud Azure version.
- Runtime container base image contains outdated CA certificates, causing TLS errors.
- Developers run Java 21 locally while the production container still runs Java 17 with an incompatible bytecode target.

### Rules

1. Document the **supported LTS JDK** in the project.
2. Use Maven compiler `release` or Gradle toolchains.
3. Pin the base container image and scan for CVEs.
4. Build and test in CI on the JDK matching production.
5. Check the compatibility matrix for each critical library.
6. Do not pick "the latest SDK version" if your organization's runtime or framework does not support it yet.

## 29. Maven Multi-Module: Where Should the BOM Live?

Suppose a repository has:

~~~text
java-azure-service/
  pom.xml                (parent)
  api/
    pom.xml
  storage-adapter/
    pom.xml
  messaging-adapter/
    pom.xml
~~~

If all modules share the same BOM, Azure SDK versions are usually managed in the **parent pom.xml** inside `dependencyManagement` so individual modules do not specify differing versions.

~~~text
Parent BOM_VERSION
      |
      +-- api                 -> dependency declarations
      +-- storage-adapter     -> azure-storage-blob (no version)
      +-- messaging-adapter   -> azure-messaging-servicebus (no version)
~~~

### Key Points to Remember

- Child modules must actually inherit from the parent or configure the BOM in the right place.
- Placing the BOM in the parent does not automatically add dependencies to each child.
- Importing different BOM versions in different child modules reduces reproducibility.
- When the parent manages both Spring Boot and the Azure SDK, verify import precedence and version mediation.
- Every executable app must inspect its **final runtimeClasspath**, not just the dependencies of a single adapter module.

## 30. Gradle Multi-Module and Version Catalogs

Gradle can manage coordinates using **version catalogs** alongside dependency constraints/platforms. One strategy:

~~~text
settings.gradle(.kts)
  |
  +--> Version catalog: Azure SDK BOM approved version
  |
  +--> Project modules
        +-- api
        +-- storage-adapter
        +-- messaging-adapter
~~~

A version catalog centralizes BOM and artifact identifiers, but **a catalog only stores aliases and versions**; it does not enforce dependency alignment unless modules apply the platform or an appropriate convention plugin.

### When Using Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation(
        platform("com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION")
    )
    implementation("com.azure:azure-storage-blob")
}
~~~

If each module declares `platform` separately, ensure they reference the same version. An organization-approved **convention plugin** can help apply dependency constraints consistently.

## 31. Inspecting the Dependency Tree Before Upgrading

**You cannot determine the runtime Azure SDK versions solely by reading pom.xml or build.gradle**. You must inspect the resolved dependencies.

### Maven

~~~bash
# Run in a hands-on Java project; do NOT run inside the workflow worker.
mvn dependency:tree -Dincludes=com.azure

# View all dependencies if deep investigation is needed:
mvn dependency:tree
~~~

### Gradle

~~~bash
# Groovy/Kotlin Gradle Java project; reference commands only.
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

On Windows you can use **gradlew.bat** instead of the POSIX wrapper. These commands may need to download repository metadata or trigger Gradle plugins, so run them only in permitted environments and scopes; **the worker does not execute builds** for writing this lesson.

### What to Record

| Artifact | Requested Version | Actual Resolved Version | Why Inspect It |
|---|---|---|---|
| azure-storage-blob | BOM or direct | Dependency tree | Service client API |
| azure-identity | BOM or direct | Dependency tree | Authentication |
| azure-core | Transitive/BOM | Dependency tree | Common API compatibility |
| azure-core-http-netty | Transitive/BOM | Dependency tree | HTTP transport |
| reactor-core | Framework/transitive | Dependency tree | Async client runtime |
| netty-handler | Framework/transitive | Dependency tree | TLS/security/performance |
| jackson-databind | Framework/transitive | Dependency tree | JSON/serialization |

**Do not upgrade Netty or Reactor independently** to silence a CVE without checking Azure SDK and Spring Boot compatibility: it may clear a security warning while breaking the application at runtime.

## 32. Diagnosing: NoSuchMethodError, ClassNotFoundException, and Linkage

### NoSuchMethodError

The application compiled against one version of a class/method, but at runtime loaded a different JAR version that lacks that method.

~~~text
Compile-time:
    Azure SDK X -> azure-core version A

Runtime:
    Another dependency selects azure-core version B (missing method)

Result:
    java.lang.NoSuchMethodError
~~~

### ClassNotFoundException/NoClassDefFoundError

Can be caused by a missing artifact, an excluded dependency, incorrect build packaging, or a class removed in the runtime version.

### UnsupportedClassVersionError

The JAR/class was compiled for a newer JDK than the runtime.

### Systematic Investigation Steps

1. Identify the **class, method, and artifact** appearing in the stack trace.
2. Inspect the actual runtime dependency graph and packaging (fat JAR/container).
3. Check the BOM, explicit versions, exclusions, and shaded JARs.
4. Check the JDK baseline and runtime image.
5. Compare against release notes and compatibility matrices.
6. Fix the alignment root cause, then run integration tests.

**Do not add dozens of exclusions blindly**. An exclusion might resolve a conflict temporarily while stripping out an HTTP transport or serializer needed at runtime.

## 33. Dependency Conflicts When Using Spring

Consider a Spring Boot WebFlux application using Reactor/Netty. The Azure Blob SDK also uses an HTTP transport that may be Netty-based.

~~~text
spring-boot-starter-webflux
   -> spring-webflux
   -> reactor-netty
       -> netty-*

azure-storage-blob
   -> azure-core
   -> azure-core-http-netty
       -> netty-*
~~~

### What Can Happen

- Gradle picks a Netty version via its resolution rules; Maven uses different mediation rules.
- The Spring Boot BOM and Azure SDK BOM may recommend different versions.
- Most of the application may run normally, failing only when an Azure call is made.
- A vulnerability scanner may flag a CVE in a transitive Netty dependency.

### How to Handle It

1. Identify the **resolved Netty/Reactor versions**.
2. Verify Spring Boot ↔ Azure SDK/HTTP transport compatibility.
3. If using Spring Cloud Azure, prefer its documented integration and matching BOM.
4. Only override versions when backed by compatibility evidence.
5. Run TLS, integration, and load tests on the production JDK and container image.

Do not assume "the Azure BOM always wins over the Spring BOM" or vice versa; the outcome depends on the build tool, import order, constraints, and direct versions.

## 34. Controlling Alpha/Beta/Preview Dependencies

Sometimes a new Azure feature is only available in a preview SDK:

~~~text
azure-some-service:version-beta.N
~~~

### Risks

- API signatures may change between preview releases.
- Runtime behavior or REST APIs may still be unstable.
- The artifact may not appear in the stable BOM.
- Production support and SLA limits may apply depending on the service.
- Migrating to stable may require code refactoring.

### Recommended Policy

- Document why the preview is needed and which feature depends on it.
- Pin the exact preview artifact version.
- Use a feature flag or adapter to isolate preview APIs.
- Monitor release notes and retirement notices.
- Create dedicated tests to validate upgrades.
- Do not silently switch a stable dependency to a preview version during a BOM update.

If a service API does not have a Java SDK yet, consult the official documentation for REST APIs/HTTP clients or supported libraries; do not pull unverified packages from unknown publishers on Maven Central.

## 35. Reading Release Notes and Selecting Versions Before Upgrading

An Azure SDK upgrade process should answer:

1. **Current artifacts:** which Maven coordinates and actual resolved versions are in use?
2. **Current BOM:** which version, and does it cover those artifacts?
3. **Candidate BOM/SDK:** is it stable or preview?
4. **API changes:** which methods are deprecated or have changed signatures?
5. **Runtime changes:** any changes to JDK, Reactor, Netty, Jackson, or HTTP transport requirements?
6. **Security:** are there critical CVEs, fixes, or retirement notices?
7. **Service contract:** did the REST API, default behavior, retries, or timeouts change?
8. **Testing:** are there adequate tests covering real Azure behavior?

### Official Source Verification Checklist

| Source | What to Look For |
|---|---|
| Azure SDK release notes | Features, fixes, breaking changes, deprecated APIs |
| Maven Central/Maven metadata | Artifact coordinates, published versions |
| Azure SDK BOM release | Versions managed by the BOM |
| Artifact/version Javadoc | Exact API methods, overloads, and imports |
| GitHub changelog/issues | Known problems, security fixes, migration advice |
| Spring Cloud Azure docs | Spring Boot compatibility and starter support |
| Azure service documentation | REST API, security, region/tier constraints |

**Do not treat old blog posts as the sole source** for dependency versions; likewise, do not assume the highest version number is automatically the release supported by your project.

## 36. A Surprise-Free BOM Upgrade Workflow

A safe upgrade flow:

~~~text
Baseline:
  BOM currently approved
  Dependency graph snapshot
  Test results + runtime JDK
          |
          v
Select candidate BOM from official release
          |
          v
Read release notes / API changes / CVEs
          |
          v
Update BOM version in one controlled change
          |
          v
Resolve and compare dependencies
          |
          v
Compile + unit + integration + security tests
          |
          v
Staging/canary on Azure
          |
          v
Production rollout + monitor
          |
          v
Rollback if thresholds breached
~~~

### Phase 1: Establish a Baseline

Record the following details:

- Application commit/tag.
- Current Maven/Gradle versions.
- JDK/toolchain and base image digest.
- Current Azure SDK BOM version.
- Resolved dependency tree or SBOM.
- List of Azure services and API operations actually used.
- Baseline tests, latency, and error rates.

### Phase 2: Update the BOM Separately

Do not bundle too many changes together: upgrading the Azure SDK BOM, doing a major Spring Boot upgrade, changing the JDK, swapping Netty, and refactoring application code in the same PR makes root-cause diagnosis very difficult.

### Phase 3: Diff the Dependency Graph

Changing just one BOM line can still alter many SDKs and artifacts. Inspect the diff to see:

- How azure-core and azure-identity changed.
- Whether HTTP transport, Netty, or Reactor changed.
- Whether new dependencies or exclusions appeared.
- Which artifacts still have explicit version overrides.

### Phase 4: Test Behavior

Successful compilation is not enough. You must test **authentication, TLS, read/write, pagination, retries, timeouts, error mapping, serialization**, and deployment against real services.

### Phase 5: Canary + Observe

Route a small slice of traffic to the new build, comparing p95/p99 latency, error rates, 401/403/429/5xx counts, retries, thread counts, memory, and Azure service charges. If thresholds fail, roll back to the previously approved artifact/binary per plan.

## 37. CVEs, SBOMs, and Supply-Chain Security

Java libraries depend on many different JARs. A vulnerability could reside in:

- An Azure SDK service module.
- azure-core or azure-identity.
- Netty/OpenSSL/JDK TLS stack.
- Jackson or a JSON parser.
- Reactor.
- Spring Framework/Spring Boot.
- Container base images or native libraries.

### What Is an SBOM?

A **Software Bill of Materials** is an inventory of the actual components and versions in a software artifact. It **differs from the Azure SDK BOM**:

| Concept | Definition | Purpose |
|---|---|---|
| **Azure SDK BOM** | A POM managing versions for a group of Azure SDKs | Dependency alignment |
| **SBOM** | Inventory of actual components/dependencies inside software | Auditing, CVE/vulnerability management, supply chain |

An application using the Azure SDK BOM can still have CVEs from transitive dependencies or base images. Therefore:

1. Generate and store an SBOM for each release using organization-approved tooling.
2. Scan both dependencies and container images.
3. Triage based on exploitability and actual runtime paths.
4. Prefer compatible security patches.
5. If an explicit override is needed, record the rationale, expiration, and tests.
6. Inspect both **direct** and **transitive** dependencies.

### Do Not Fix CVEs by Blindly Forcing Versions

For example, a scanner may suggest a newer Netty version, while the Azure SDK HTTP transport relies on an incompatible API. You must verify compatibility and run network tests. A patch that breaks application availability is still a severe risk; sometimes the safer fix is upgrading the **Azure SDK BOM and Spring BOM together** rather than forcing Netty in isolation.

## 38. Version Policies in CI/CD

A sample policy:

| Dependency Group | Policy |
|---|---|
| Azure stable SDKs | Fixed BOM version per release cycle |
| Azure preview SDKs | Pin exact version, requires owner and separate approval |
| Spring Boot/Cloud Azure | Upgrade according to compatibility matrix |
| JDK | Approved LTS, pinned image digest/tag |
| Critical security patches | Prioritized out-of-band review |
| Transitive overrides | Only with documented reason and tests |
| Snapshot dependencies | Restricted or disallowed in production releases |
| Build plugins | Pin versions and test plugin upgrades |

### Lock Files and Dependency Resolution

Gradle supports optional **dependency locking** to preserve resolved versions. Maven reproducibility can be improved through explicit parent/BOM versions, dependency verification, or dedicated management tools.

Locking does not replace a BOM: **the BOM manages constraints**, while lock files/verification lock down a concrete graph for the build tool. Remember to update and review lock state diffs whenever upgrading the BOM.

### Avoid Uncontrolled Version Ranges and Snapshots

Using open version ranges for the Azure SDK or pulling SNAPSHOTs from external repositories can cause two builds to produce different artifacts. Use approved versions and trusted artifact repositories; avoid pulling dependencies from unverified external sources.

## 39. Release and Rollback in Azure Java Projects

~~~text
Release v1
  Azure SDK BOM B1
  JDK image I1
  Dependency/SBOM snapshot S1
       |
       v
Canary release v2
  BOM B2
  JDK image I1
  SBOM S2
       |
       +--> Healthy metrics -> increase traffic
       |
       +--> NoSuchMethodError/5xx -> rollback v1
~~~

### Artifacts to Preserve for Rollback

- Original commit/tag and un-overwritten build artifact.
- Original container image digest.
- Original BOM and resolved dependency graph.
- IaC/Helm/App Service deployment configuration.
- Monitoring dashboards and error budgets.
- Awareness of any data migrations or schema changes.

**Rolling back a Java JAR does not automatically roll back written data**. If an SDK update accompanied schema changes, API version changes, or data mutations in Azure, you need separate backward-compatibility and data recovery plans.

### Two Distinct Phases

**Canary:** observe the application under a small portion of traffic.

**Rollback:** revert to the previously tested artifact, rather than trying to patch the BOM directly on a running pod.

## 40. Observability and Diagnostics for the Azure SDK

When a client fails, you need visibility into:

- Azure service operation and HTTP status.
- Service request/correlation ID when provided in the response.
- Retry count/backoff and total request duration.
- Network/TLS/authentication failure category.
- Endpoint/service region (without exposing secrets).
- Application trace/span ID.
- SDK versions and JDK version in release metadata.

### What Must Never Be Logged

- Access tokens, SAS query strings.
- Storage account keys, connection strings containing secrets.
- Key Vault secret values.
- PII in request/response bodies.
- Full authorization headers.
- Client certificates/private keys.

### HTTP Logging Carries Risk

Some service builders support **HttpLogOptions** or logging policies. Detailed headers or bodies may contain sensitive data. Before enabling detailed logging in production:

1. Identify the operation type.
2. Apply redaction/allowlists per the SDK and logging system.
3. Restrict log read permissions, retention, storage, and export.
4. Set sampling and volume budgets.
5. Test to verify authorization headers and connection strings never appear.

**Debug logging should not be left enabled indefinitely** just to troubleshoot a 403 error.

## 41. Azure SDK and OpenTelemetry

In Java microservices, tracing helps distinguish between:

~~~text
HTTP incoming request
     |
     +--> Spring controller
     |
     +--> Azure Blob SDK call
     |       +--> DNS/network
     |       +--> retries
     |       +--> Azure Storage response
     |
     +--> Azure Service Bus SDK call
     |
     v
HTTP response
~~~

The Azure SDK provides hooks or integrations for telemetry depending on the library and version. Use supported configurations (OpenTelemetry, Azure Monitor, Micrometer, or appropriate tracing options), and never manually record access tokens into spans.

### Essential Metrics

| Metric | Purpose |
|---|---|
| SDK request latency p50/p95/p99 | SLOs and performance |
| HTTP status distribution | Categorize service errors |
| Number of retries | Detect throttling/network issues |
| 401/403 error rate | Credential/authorization issues |
| 429 rate | Capacity/quota/throttling |
| Connection/TLS errors | Transport/network diagnosis |
| Thread/connection pool size | Resource exhaustion |
| Service costs/transactions | Cost management |
| Dependency version | Trace post-release regressions |

Some metrics require manual instrumentation or an agent; do not assume every metric name is available out of the box in Azure Monitor.

## 42. Test Pyramid When Using the Azure SDK

| Test Level | Example | Limitation |
|---|---|---|
| **Unit test** | Mock adapter/interface to verify logic without calling Azure | Does not verify auth/network/API contract |
| **Contract test** | Verify DTOs, serialization, endpoints/options | Does not replace the real service |
| **Integration test** | Call lab Azure resources with real identity/network | Incurs cost, quota, cleanup needs |
| **Performance test** | Verify concurrency, retries, latency, memory | Requires dedicated environment and load policy |
| **Security test** | Least-privilege roles, secret redaction, TLS | Requires real identities/permissions |
| **Release canary** | Route a portion of production traffic through the new SDK | Requires rollback plan and telemetry |

### Wrap the SDK with an Adapter

~~~text
Business service
     |
     v
BlobMetadataReader (interface)
     |
     +--> Fake/Stub implementation for unit tests
     |
     +--> AzureBlobMetadataReader -> BlobClient for integration
~~~

An adapter keeps unit tests independent of cloud credentials and prevents unit tests from accidentally calling production Azure. Still, excessive mocking hides integration failures; both testing levels are necessary.

## 43. Java Adapter Example Decoupling Business Logic from the SDK

Simple interface:

~~~java
public interface BlobMetadataReader {
    boolean exists(String blobName);
}
~~~

Azure Blob implementation:

~~~java
import com.azure.storage.blob.BlobContainerClient;

public final class AzureBlobMetadataReader
        implements BlobMetadataReader {

    private final BlobContainerClient container;

    public AzureBlobMetadataReader(
            BlobContainerClient container) {
        this.container = container;
    }

    @Override
    public boolean exists(String blobName) {
        return container
            .getBlobClient(blobName)
            .exists();
    }
}
~~~

Stub for unit tests:

~~~java
import java.util.Set;

public final class FakeBlobMetadataReader
        implements BlobMetadataReader {

    private final Set<String> existing;

    public FakeBlobMetadataReader(Set<String> existing) {
        this.existing = existing;
    }

    @Override
    public boolean exists(String blobName) {
        return existing.contains(blobName);
    }
}
~~~

### Value of the Adapter

- Business services do not need to import BlobServiceClient directly.
- Unit tests do not require tokens, HTTP, or network access.
- Blob SDK migrations have a bounded surface area for changes.
- Metrics, retries, and error translation can be added in one place.

### Limitations

A stub does not test real behavior when Blob returns 403, 429, or times out. Integration tests against lab Azure resources and real identities are required. Never use unit tests as sole proof that a new BOM is production-compatible.

## 44. Lab A: Building a Maven Version Graph

**Goal:** use the Azure SDK BOM to unify versions without provisioning Azure resources. This exercise is **a guide for learners to run independently** in a lab Java project; the authoring worker does not execute Maven or Gradle.

### Preparation

1. An approved LTS JDK and compatible Maven installation.
2. Maven Central or an organization-trusted proxy repository.
3. Sample POM from section 21 with the BOM version replaced by a verified release.
4. Permissions to download dependencies in the dev environment.

### Steps

1. Create a separate lab Maven project.
2. Add the Azure SDK BOM in `dependencyManagement`.
3. Add **azure-identity** and **azure-storage-blob**.
4. Run the command to inspect dependencies:

~~~bash
mvn dependency:tree -Dincludes=com.azure
~~~

5. Inspect the versions of **azure-core** and the service SDKs.
6. Verify the actual POM has no unjustified direct version overrides.
7. Add **azure-security-keyvault-secrets** without declaring a version.
8. Observe how the graph changes.
9. If a newer approved BOM release is available, change **only the BOM version** and compare the diff.
10. Do not call real Azure services without a lab account and proper permissions.

### Acceptance Criteria

| Question | PASS When |
|---|---|
| BOM imported? | Maven imports it cleanly |
| Service SDK declared? | Required dependencies are present |
| Version source? | Versions come from the BOM or documented overrides |
| azure-core resolved? | Final resolved version is known |
| Build environment? | JDK/runtime target is explicit |
| Security? | No JARs pulled from untrusted repositories |
| Output? | Dependency tree snapshot captured for review |

### Troubleshooting Errors

- **Maven cannot resolve BOM**: placeholder not replaced, repository/offline/network issue.
- **Package not found**: missing service dependency.
- **NoSuchMethodError at runtime**: inspect resolved graph and packaging.
- **403 when calling Azure**: usually related to identity/data-plane rights/network, not a broken BOM.

## 45. Lab B: Gradle dependencyInsight

In a separate Gradle project:

1. Add the Azure SDK BOM platform as shown in section 22.
2. Add azure-identity and azure-storage-blob without specifying versions.
3. Inspect **runtimeClasspath**:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

4. Trace how Gradle selected azure-core:

~~~bash
./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

5. Try adding a library/framework already used by your project and compare version selection.
6. If a conflict appears, do not apply `enforcedPlatform` before evaluating it.
7. Record the dependency graph and a valid BOM upgrade plan.

### Checks to Record

~~~text
Selected azure-core version: <resolved-version>
Selection reason:             <BOM/constraint/conflict-resolution>
Azure Blob SDK version:       <resolved-version>
Azure Identity version:       <resolved-version>
Runtime JDK:                  <tested-jdk>
~~~

Placeholder outputs must be replaced with actual lab results; do not fill in guessed numbers.

## 46. Lab C: Executing a Read-Only Blob Call

**Goal:** verify that once the dependency graph is stable, the Java client can authenticate and read metadata from Azure.

### Prerequisites

- An authorized **lab** storage account/container/blob.
- Environment variables: AZURE_BLOB_ENDPOINT, AZURE_BLOB_CONTAINER, AZURE_BLOB_NAME.
- Developer identity or managed identity with **Storage Blob Data Reader**.
- Valid TLS and network connectivity.
- POM/Gradle configured with compatible libraries.

### Procedure

1. Inspect the resolved dependency graph.
2. Run the Java program from section 8 in the lab project.
3. Observe the output **Blob exists: true/false**.
4. Test with an identity lacking a data-plane role **if approved**, and observe the permission error.
5. Collect request duration and status safely without logging credentials.
6. After upgrading the BOM according to plan, re-run the same test.
7. Compare behavior, errors, and latency—not just version numbers.

### Expected Result

A **technical PASS** is achieved when the client builds successfully, the credential acquires a token for the intended identity, the Blob request returns an authorized result, and logs leak no secrets. **False is not necessarily an error**, as the blob may simply not exist; auth or network errors must be triaged separately.

## 47. Case Study: Spring Boot API Using Four Azure Services

A company runs Java 17/Spring Boot on AKS:

- Azure Blob Storage: stores customer documents.
- Azure Key Vault: supplies unavoidable business secrets.
- Azure Service Bus: publishes order events.
- Azure Cosmos DB: reads and writes shopping carts.
- Microsoft Entra Workload ID: pod authentication.
- Private Endpoints and controlled outbound firewall.
- CI/CD uses Gradle multi-module.
- One team wants to upgrade the Azure SDK for a CVE, while another plans a major Spring Boot upgrade.

### Tasks

1. Categorize artifacts into **data-plane SDK, identity/core, Spring integrations, and management SDK**.
2. Decide between the direct Azure SDK or Spring Cloud Azure starters for each integration and explain why.
3. Design BOM ownership across the Gradle modules.
4. Inspect azure-core, Reactor, and Netty versions on **runtimeClasspath**.
5. Explain why upgrading both the SDK BOM and Spring Boot major version together creates a hard-to-rollback change.
6. Describe how AKS Workload Identity provides a TokenCredential.
7. Assign least-privilege RBAC for Blob/Key Vault/Service Bus/Cosmos.
8. Verify Private DNS/TLS to each Azure endpoint.
9. Contrast safe retries for GET Blob versus publishing/sending business messages.
10. Design adapters/tests so business services are not tightly coupled to SDK classes.
11. Build an integration test checklist for 401, 403, 404, 429, 5xx, and timeouts.
12. Record the SBOM and artifact versions in the release.
13. Distinguish permission to view the Key Vault resource from permission to get a secret.
14. Draft a canary/rollback plan for dependency updates.
15. Explain why the runtime API should not use the management SDK to create storage accounts on every request.

### Suggested Solution

~~~text
Spring Boot Java API
     |
     +-- Business interfaces/adapters
     |      |
     |      +-- Blob SDK
     |      +-- Key Vault SDK
     |      +-- Service Bus SDK
     |      +-- Cosmos SDK
     |
     +-- Managed/Workload Identity -> azure-identity
     |
     +-- Approved BOM(s) + JDK toolchain
     |
     +-- OpenTelemetry/Micrometer instrumentation
     |
     v
AKS runtime with private DNS + approved egress
     |
     v
Azure data-plane services
~~~

Base your BOM strategy on the **compatibility matrix**: if the project relies heavily on Spring Cloud Azure starters, prioritize a supported Spring Boot/Spring Cloud Azure combination and inspect the resulting Azure SDK versions. If using only direct SDKs, the Azure SDK BOM can serve as a convenient baseline. Do not arbitrarily add a second BOM just because the dependency tree looks unexpected.

## 48. Common Mistakes When Using the Azure SDK for Java

| Misconception/Mistake | Why It Is Dangerous | Correct Practice |
|---|---|---|
| "One Azure SDK JAR contains every service" | Missing the required client library | Choose artifacts per service |
| "Importing the BOM makes BlobClient available" | The BOM only manages versions | Declare the azure-storage-blob dependency |
| "All com.azure.* are in azure-sdk-bom" | The BOM manages only a specific set of artifacts | Check the BOM release contents |
| "BOM version equals azure-core version" | Two different versioning schemes | Inspect resolved artifact versions |
| "Having azure-identity grants Azure permissions" | Credentials are distinct from RBAC | Assign the identity and proper roles |
| "Contributor can read every blob" | Data plane differs from management plane | Verify Storage data roles |
| "Client builder calls Azure immediately" | Builder/client creation may not send a request | Verify the actual operation call |
| "Async Mono doesn't need subscribe" | Lazy execution may never run | Manage subscription and lifecycle properly |
| "Calling block() in WebFlux is fine" | Can block the event loop | Use reactive chains or sync APIs on appropriate threads |
| "Listing blobs is free because it's read-only" | Generates service requests and transaction costs | Use paging, filters, and monitoring |
| "HTTP 202 means the resource is ready" | Long-running operation is still in progress | Track via Poller |
| "The BOM fixes all CVEs" | Transitives and base images can still be vulnerable | Generate SBOM + scan |
| "Upgrading SDK and Spring major together is always better" | Hard to isolate regressions | Upgrade one layer at a time with tests |
| "Forcing Netty version fixes everything" | Can break transport compatibility | Review dependency tree and compatibility matrix |
| "ClassNotFound means an Azure outage" | Usually a classpath/packaging issue | Inspect the runtime graph |
| "Keep retrying 403 until it succeeds" | Missing permissions aren't fixed by retries | Fix identity/RBAC |
| "Disable TLS verification to fix PKIX" | Exposes traffic to MITM attacks | Fix DNS/truststore/certificates |
| "Storing service principal secrets in Git is easier" | Credential leakage | Use managed identity / Key Vault |
| "Rolling back the JAR rolls back data" | Data changes persist independently | Plan schema/data rollback |
| "Passing mocked unit tests means production-ready" | Real Azure services haven't been tested | Run integration/canary tests |

## 49. Production Deployment and Upgrade Checklist

| Category | What Must Be Confirmed |
|---|---|
| Service selection | Correct artifact chosen for each Azure service |
| SDK generation | Track 1 and Track 2 are not mixed without a migration plan |
| Data vs management | Runtime identity has only necessary permissions |
| BOM | Single clear version source; BOM-covered artifacts verified |
| Spring integration | Spring Boot/Cloud Azure compatibility matrix verified |
| Build tools | Compatible Maven/Gradle versions and plugins |
| JDK | Toolchain/bytecode/runtime/JDK security updates aligned |
| Dependency graph | Runtime versions of azure-core/Netty/Reactor recorded |
| SBOM/security | Dependency and image scanning enabled, CVE triage in place |
| Preview libraries | Exact version pinned, approval and exit plan documented |
| Identity | Managed identity/Workload ID used, no hard-coded tokens |
| RBAC | Least-privilege data-plane roles/ACLs |
| Network | Private DNS, firewall, TLS certificates, and trusted CAs |
| Client lifecycle | Clients reused, transport/thread ownership clear |
| Retry/timeouts | Bounded retries, deadlines, no retry storms |
| Paging | No unnecessary full data listings |
| Error handling | 401/403/404/409/412/429/5xx classified properly |
| Logging | No exposure of SAS, tokens, secrets, or PII |
| Monitoring | p95/p99 latency, status codes, retries, service charges |
| Test coverage | Unit/integration/performance/security tests |
| Canary | Limited rollout with defined rollback thresholds |
| Backups | Critical data/metadata has a recovery plan |
| Cost | Track transactions, requests, storage, logs, egress |
| Documentation | Record versions, owners, release notes, and rollback steps |

## 50. Self-Check Questions

1. Is the Azure SDK for Java a single JAR or multiple libraries?
2. Distinguish between data plane and management plane SDKs.
3. How do azure-core and azure-identity differ in function?
4. What is BlobServiceClientBuilder used for?
5. Does building a BlobClient automatically send an HTTP request?
6. When should you reuse a service client?
7. How do Track 1 and Track 2 differ?
8. How do sync and async clients differ in how they return results?
9. What types of results do Mono and Flux represent?
10. Why can forgetting to subscribe prevent an async operation from running?
11. Why is calling `block()` on a WebFlux event loop risky?
12. What problem does PagedIterable solve?
13. Why can listing millions of blobs cost money?
14. How are Poller and HTTP 202 related?
15. What policies are typically found in the HTTP pipeline?
16. At which layer do Netty and OkHttp operate?
17. Does DefaultAzureCredential automatically grant Storage Blob Data Reader?
18. How do ManagedIdentityCredential and AzureCliCredential differ in intended environment?
19. Why should 403 errors not be retried infinitely?
20. What is a BOM, and does importing it automatically add a service SDK?
21. How does Maven `dependencyManagement` differ from `dependencies`?
22. Why is Gradle `platform` not always equivalent to `enforcedPlatform`?
23. Is the BOM version equal to the version of every SDK?
24. Does `azure-sdk-bom` manage Spring Cloud Azure?
25. Why should you check the Spring Boot ↔ Spring Cloud Azure compatibility matrix?
26. Might Management SDK artifacts require a separate versioning mechanism?
27. What release risks do Preview SDKs carry?
28. What error occurs when the JDK runtime is older than the bytecode target?
29. How does a dependency tree differ from the dependency declarations in a build file?
30. What can cause NoSuchMethodError and ClassNotFoundException?
31. Why check Reactor/Netty when upgrading the Azure SDK in WebFlux?
32. How does a version lock differ in purpose from a BOM?
33. How do the Azure SDK BOM and an SBOM differ?
34. Why can a CVE in a transitive dependency still exist even when using a BOM?
35. What steps should be taken when changing a BOM version?
36. Why are canary releases and binary image digest rollbacks necessary?
37. Why does rolling back a JAR not automatically roll back data?
38. What must never be logged in HTTP client diagnostics?
39. What does a unit test with a fake BlobMetadataReader verify, and what does it not verify?
40. What criteria prove that an Azure SDK upgrade is safe in a production Java application?

## References

- Microsoft Learn — *Azure SDK for Java overview*: https://learn.microsoft.com/azure/developer/java/sdk/overview
- Microsoft Learn — *Get started with Azure SDK for Java*: https://learn.microsoft.com/azure/developer/java/sdk/get-started
- Microsoft Learn — *Use Azure SDK for Java with Maven*: https://learn.microsoft.com/azure/developer/java/sdk/get-started
- Azure SDK for Java — *SDK release index and packages*: https://azure.github.io/azure-sdk/releases/latest/java.html
- Azure SDK — *Java libraries GitHub repository*: https://github.com/Azure/azure-sdk-for-java
- Azure SDK — *Dependency/BOM guidance in SDK repository*: https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/boms
- Maven Central — *Azure SDK BOM artifact*: https://central.sonatype.com/artifact/com.azure/azure-sdk-bom
- Microsoft Learn — *Authenticate Java apps with Azure Identity*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview
- Microsoft Learn — *DefaultAzureCredential in Java*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/credential-chains
- Microsoft Learn — *Azure Storage Blob Java SDK*: https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java
- Microsoft Learn — *Manage Azure resources with Azure SDK for Java*: https://learn.microsoft.com/azure/developer/java/sdk/management
- Microsoft Learn — *Spring Cloud Azure*: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Spring Cloud Azure — *Reference documentation*: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Microsoft Learn — *Azure SDK design guidelines*: https://azure.github.io/azure-sdk/java_introduction.html
- Maven — *Dependency mechanism*: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — *Platforms and dependency constraints*: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — *Viewing dependencies*: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
