# Replacing Unmaintained Libraries or Connectors

A cloud library may still be downloadable from Maven Central, still compile, and even continue running in production after the provider stops maintaining it. That does not mean the library still receives security patches, supports new services, or remains compatible with current JDK and Spring Boot versions. When a dependency is deprecated, archived, or end-of-support, the development team must identify a maintained replacement, plan the migration, and prove that application behavior stays correct.

Replacement is rarely just swapping a Maven coordinate. The new API may change client creation, request/response models, credential chains, retries, async processing, pagination, transactions, or message settlement. A legacy connector might automatically read service bindings in an older environment; the replacement may require explicit configuration. If you only fix imports until the build turns green, these differences often surface after deployment.

This lesson belongs to the **Integration Upgrades** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services via the corresponding Spring Cloud libraries. This lesson focuses on evaluating replacement libraries, migrating connectors and SDKs per provider, verifying compatibility, and deploying changes safely.

## 1. Learning Objectives

After this lesson, you will be able to:

- Identify dependencies that are deprecated, archived, maintenance-only, or end-of-support.
- Distinguish Spring Cloud integration libraries, provider SDKs, and deployment platform connectors.
- Evaluate replacements by support policy, compatibility, security, API fit, and migration cost.
- Replace Spring Cloud Connectors with Java CFEnv when applications run on Cloud Foundry.
- Migrate AWS SDK for Java 1.x to AWS SDK for Java 2.x.
- Migrate legacy Azure Java SDKs to current packages under `com.azure`.
- Replace App Engine legacy bundled APIs with standalone Google Cloud services and Cloud Client Libraries where appropriate.
- Keep dependencies converged using the right ecosystem BOMs.
- Test authentication, authorization, retries, timeouts, payloads, ordering, and resource lifecycles.
- Roll out migrations service by service with observability and rollback.

## 2. Identifying an End-of-Life Library

Do not decide based solely on version numbers or the last release date. Always check the status published by the maintainer.

| Status | Meaning | How to handle |
| --- | --- | --- |
| Active / Supported | Has active maintainers, releases, and bug fixes per policy | Can continue using if compatible |
| Deprecated | Recommended to migrate to another API/package | Plan migration before removal or end of support |
| Maintenance mode | Receives only limited fixes, may not support new features/services | Assess risk and schedule replacement |
| End-of-support | No more updates or official releases | Prioritize migration, especially for data/credential components |
| Archived | Read-only repository or no longer developed | Find another maintainer/replacement and assess self-maintenance cost |
| Unsupported combination | Library is still maintained but does not support the app's Boot/JDK/provider version | Upgrade the whole stack or replace the library |

Signals to check:

- Official support policy page or deprecation list.
- Release notes, changelog, and latest release date.
- Whether the repository is archived and whether issues/pull requests are handled.
- Whether CVEs/advisories have patches for the branch in use.
- Whether compatibility matrices still list the application's Spring Boot, Spring Cloud train, and JDK.
- Whether Maven/Gradle emits deprecation warnings or dependency conflicts.
- Whether the provider publishes a replacement package and official migration guide.

A dependency without releases for several months is not enough to conclude it is EOL. Conversely, a library with a recent release may still be declared deprecated or support only specific branches. Always take the maintainer's support policy as the authoritative source.

### 2.1. Examples of published milestones

The examples below show why status and support dates must be distinguished:

- AWS SDK for Java 1.x entered maintenance mode on 31-07-2024 and reached end-of-support on 31-12-2025. As of 24-11-2026, SDK v1 no longer receives updates or new releases; AWS recommends migrating to SDK v2.
- The Spring Cloud Connectors starter was deprecated in Spring Boot 2.2 in favor of Java CFEnv and removed from Spring Boot 2.3 dependency management.
- Microsoft announced that the legacy Java Service Bus library `com.microsoft.azure:azure-servicebus` retired on 30-09-2026; the replacement package is `com.azure:azure-messaging-servicebus`.
- The Azure SDK deprecation list records that several legacy Storage v8, Event Hubs, and Key Vault packages have reached end of support. Replacement packages and migration guides are listed per service.
- The App Engine Java 8 first-generation runtime was deprecated on 31-01-2026 and no longer allows new deployments. Some legacy bundled APIs can still be used in second-generation runtimes, but Google recommends migrating to standalone services and Cloud Client Libraries where suitable alternatives exist.

These milestones must be re-verified on current support pages before planning for another project. Do not infer one library's EOL date solely from another library's EOL date from the same provider.

## 3. Distinguishing SDKs, Spring Integrations, and Connectors

A Spring Cloud application may use three layers of libraries:

| Layer | Responsibility | Examples |
| --- | --- | --- |
| Provider SDK | Calls cloud service APIs directly | AWS SDK, Google Cloud Java libraries, Azure SDK |
| Spring integration | Provides auto-configuration, Spring abstractions, listeners/templates, and property binding | Spring Cloud AWS, Spring Framework on Google Cloud, Spring Cloud Azure |
| Platform connector | Reads platform service bindings/environment and converts them to application config | Spring Cloud Connectors, Java CFEnv |

These three layers may depend on each other, but they do not completely replace one another. For example:

- AWS SDK v1 → v2 is an SDK migration; Spring Cloud AWS has its own migration/version line.
- Spring Cloud Connectors → Java CFEnv is a connector replacement for Cloud Foundry service bindings; it does not replace the AWS SDK, Azure SDK, or Google Cloud clients.
- `com.microsoft.azure:azure-servicebus` → `com.azure:azure-messaging-servicebus` is an Azure service client replacement; if the application uses the Spring Cloud Azure Service Bus starter, verify which new SDK version the starter manages.

Before replacing a dependency, identify what functionality it provides. If you remove a starter without replacing the auto-configuration or service binding it supplied, the application may compile yet fail to create DataSources, messaging clients, or credential providers at runtime.

## 4. Criteria for Selecting a Replacement

A good replacement must resolve lifecycle issues and satisfy the application's runtime requirements.

| Criterion | Questions to answer | Evidence to record |
| --- | --- | --- |
| Support | Who maintains it? Is there a support policy and security updates? | Support page, repository, release cadence |
| Compatibility | Does it support the chosen JDK, Boot, Cloud train, and SDK BOM? | Compatibility matrix and release notes |
| Security | How are credential chains, TLS, token refresh, and CVEs handled? | Security docs/advisories |
| API fit | Does it cover all operations the application uses? | API reference and feature matrix |
| Behavioral fit | Are retries, timeouts, ordering, ack, pagination, and consistency equivalent? | Migration guide and contract tests |
| Operations | Does it provide metrics, tracing, health, connection pooling, and graceful shutdown? | Observability docs and integration tests |
| Data migration | Does it change formats, schemas, metadata, IDs, or semantics? | Data migration plan |
| Ecosystem | Are Spring starters, test support, emulators, or Testcontainers available? | Starter docs and test modules |
| Licensing | Are the license and support terms suitable? | LICENSE and vendor policy |
| Exit cost | Can it be replaced again if the provider changes policy? | Adapter boundary and domain port |

Do not pick a replacement just because it shares the same service name. A new queue library may not preserve message ordering, visibility timeouts, dead-letter behavior, or message settlement semantics. A new object storage library may change metadata encoding, multipart uploads, checksums, or signed URL generation.

### 4.1. Check compatibility before rewriting code

Build a version table:

```text
JDK:                    21
Spring Boot:            4.x
Spring Cloud train:     2026.x
Provider integration:   release line confirmed by matrix
Provider SDK:           version managed by BOM
Runtime platform:       Cloud Run / ECS / Azure App Service / Cloud Foundry
```

This is an inventory template, not a specific recommended version set. With Spring Cloud providers, always read each project's matrix. Do not assume that because Spring Cloud core supports a Boot version, every provider integration also supports that version.

### 4.2. Inspect the dependency graph and actual APIs

Maven:

```bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aws-java-sdk-s3 --configuration runtimeClasspath
```

Search for both package imports and artifact coordinates. A legacy dependency can still be pulled in transitively even after removing it from the main module's pom.xml.

Example searching for legacy packages in Java:

```bash
rg -n "com\\.amazonaws|com\\.microsoft\\.azure|org\\.springframework\\.cloud\\.connectors" .
rg -n "spring-boot-starter-cloud-connectors|aws-java-sdk-|azure-servicebus|azure-storage-blob" .
```

Also inspect build.gradle, version catalogs, parent POMs, buildSrc, Dockerfiles, Helm, Terraform, CI/CD workflows, samples, and test fixtures. Do not grep only inside src/main/java.

## 5. Replacing Spring Cloud Connectors with Java CFEnv

Spring Cloud Connectors previously helped applications read `VCAP_SERVICES`, discover service bindings, and auto-configure connections in Cloud Foundry. Spring Boot 2.2 deprecated `spring-boot-starter-cloud-connectors` in favor of Java CFEnv; Spring Boot 2.3 removed this starter from managed dependencies.

Java CFEnv reads and parses `VCAP_SERVICES`, exposes service/credential details, and provides a Spring Boot module to map bindings to standard properties such as `spring.datasource.url`.

### 5.1. Choosing CFEnv modules

| Module | Purpose |
| --- | --- |
| `java-cfenv` | Core parser for `VCAP_SERVICES`, usable with any Java application |
| `java-cfenv-jdbc` | Helps locate JDBC services and build JDBC URLs |
| `java-cfenv-boot` | `EnvironmentPostProcessor` mapping bindings into Spring Boot properties |
| `java-cfenv-boot-pivotal-scs` | Supports Spring Cloud Services such as Config Server and Service Registry |
| `java-cfenv-boot-pivotal-sso` | Supports Single Sign-On services |
| `java-cfenv-all` | Bundles multiple modules and activates the `cloud` profile when running on Cloud Foundry |
| `java-cfenv-test-support` | Test helper utilities |

Pick the smallest module that satisfies the application. If Java buildpack v5 injects `java-cfenv-all` automatically, check dependencies before declaring a duplicate module.

Cloud Foundry documentation currently aligns versions with Spring Boot: Java CFEnv 4.x for Boot 4.x (from 4.0.2), 3.x for Boot 3.x (from 3.5.3), and 2.x for EOL Boot 2.x. Check the compatibility matrix before picking a version.

### 5.2. Replacing dependencies

Remove legacy dependencies, for example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cloud-connectors</artifactId>
</dependency>
```

Or Spring Cloud Connectors modules:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-connectors-core</artifactId>
</dependency>
```

Add the CFEnv module for Spring Boot:

```xml
<dependency>
    <groupId>io.pivotal.cfenv</groupId>
    <artifactId>java-cfenv-boot</artifactId>
    <version>4.0.2</version>
</dependency>
```

`4.0.2` is an example version from Cloud Foundry documentation for Spring Boot 4.x; choose the release matching your project's Boot version at migration time.

### 5.3. Leveraging Spring Boot auto-configuration

`java-cfenv-boot` provides `EnvironmentPostProcessor` implementations, such as `CfDataSourceEnvironmentPostProcessor`, to set `spring.datasource.url` from service bindings. Spring Boot continues creating `DataSource` using standard configuration.

If you need to read bindings directly:

```java
import io.pivotal.cfenv.core.CfEnv;
import io.pivotal.cfenv.core.CfService;

public class CloudFoundryBindingReader {

    public String redisHost() {
        CfEnv cfEnv = new CfEnv();
        CfService service = cfEnv.findServiceByTag("redis");
        return service.getHost();
    }
}
```

For JDBC, you can use `CfJdbcEnv` to read the URL, username, password, and driver class. There is no need to parse `VCAP_SERVICES` JSON manually.

### 5.4. Code changes to review

- Remove `@ServiceScan` or `@CloudScan` annotations provided by Spring Cloud Connectors.
- Legacy `cloud.<property>` placeholders may need to change to `vcap.<property>`.
- `java-cfenv-all` activates the `cloud` Spring profile; smaller modules do not automatically activate this profile.
- If multiple service instances of the same type are bound, read credentials with CFEnv and configure each client explicitly. Do not assume the mapper automatically selects the right instance.
- If you had custom Spring Cloud Connector extensions, convert the logic to Spring Boot auto-configuration and write a CFEnv extension to map `VCAP_SERVICES` to properties.

Java CFEnv is a solution for Cloud Foundry service bindings. For applications running directly on ECS, GKE, Cloud Run, or Azure App Service, use the respective platform's identity and configuration mechanisms.

## 6. Migrating AWS SDK for Java 1.x to 2.x

AWS SDK for Java 1.x reached end-of-support on 31-12-2025. AWS recommends migrating to SDK 2.x. Existing SDK v1 releases can continue running, but they no longer receive updates or new releases.

### 6.1. Key differences

| Component | SDK v1 | SDK v2 |
| --- | --- | --- |
| Maven groupId | `com.amazonaws` | `software.amazon.awssdk` |
| Package | `com.amazonaws...` | `software.amazon.awssdk...` |
| Client | `AmazonS3`, `AmazonDynamoDB` | `S3Client`, `DynamoDbClient` |
| Client creation | v1 builder or constructor | v2 builder |
| Model | Setters/mutable requests | Immutable models, builders |
| Getters/setters | `getX`, `setX`, `withX` | `x`, `x(...)` |
| Response class | `*Result` | `*Response` |
| Async | v1-specific APIs | `CompletableFuture` and non-blocking HTTP client |
| Pagination | Many operations require token loops | Paginators provided for supported APIs |

Some v1 packages contain `v2` in their name, such as `com.amazonaws.services.dynamodbv2`, yet still belong to SDK v1. Reliable indicators are the root groupId/package and the dependency tree.

### 6.2. Adding the v2 BOM and migrating artifacts

Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>AWS_SDK_V2_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
</dependencies>
```

The BOM keeps SDK v2 modules aligned. Replace `AWS_SDK_V2_VERSION` with the version selected per support policy at upgrade time. If the application uses Spring Cloud AWS, check Spring Cloud AWS's BOM and compatibility matrix before adding or overriding the AWS SDK BOM. Avoid importing multiple BOMs without checking dependency resolution.

### 6.3. Example migrating the S3 client

SDK v1:

```java
AmazonS3 s3 = AmazonS3ClientBuilder.standard()
    .withRegion(Regions.AP_SOUTHEAST_1)
    .build();

ObjectListing listing = s3.listObjects(bucketName);
String firstKey = listing.getObjectSummaries()
    .get(0)
    .getKey();
```

SDK v2:

```java
try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {

    ListObjectsV2Request request = ListObjectsV2Request.builder()
        .bucket(bucketName)
        .build();

    s3.listObjectsV2Paginator(request)
        .contents()
        .forEach(object -> System.out.println(object.key()));
}
```

SDK v2 uses immutable models and paginators for iterating over all results. Calling only `listObjectsV2` may return just one page; choose the paginator when business logic needs to iterate through all objects.

### 6.4. Credential chains can change behavior

AWS SDK v2 changes several details of credential providers:

- Default credentials provider uses builders or `create()` instead of old constructors.
- Precedence between system properties and environment variables differs from SDK v1; SDK v2 checks system properties before environment variables.
- Profile file formats and some provider classes/methods changed.
- Asynchronous credential refresh is no longer enabled by default in some providers; configure it explicitly when the application needs it.

After migration, verify the actual credential source locally, in CI, ECS task roles, EC2 instance profiles, EKS web identity, and Lambda. An old environment variable can be overridden by a system property, causing the application to use the wrong principal.

### 6.5. Use migration tools, but always review

AWS provides an OpenRewrite-based migration tool to automatically convert many SDK v1 service clients and S3 TransferManager. The tool does not convert all high-level APIs; for example, `DynamoDBMapper` requires manual migration to `DynamoDbEnhancedClient`.

Recommended workflow:

1. Run the migration tool on a separate branch.
2. Review all import, artifact, and model changes.
3. Search for `com.amazonaws` across the entire repository.
4. Manually migrate APIs not supported by the tool.
5. Check credential chains, retries, HTTP clients, and resource closing.
6. Run integration tests with a production-like IAM role.
7. Remove all SDK v1 dependencies once no code or library requires them.

AWS supports running v1 and v2 side by side during a transition period. Apply this along service or module boundaries; do not mix request/response models from both SDKs within a single business flow.

## 7. Migrating Legacy Azure Java SDKs to Current Azure SDKs

Current Azure Java SDKs typically use Maven groupId `com.azure` and packages starting with `com.azure`. Many historical libraries used `com.microsoft.azure`. Azure's deprecated list publishes replacement packages and support end dates per service.

### 7.1. Common package mappings

| Legacy library | Current replacement |
| --- | --- |
| `com.microsoft.azure:azure-servicebus` | `com.azure:azure-messaging-servicebus` |
| `com.microsoft.azure:azure-storage` | `com.azure:azure-storage-blob` |
| Azure Storage Blob v8 (`CloudBlob*`) | Azure Storage Blob v12 (`BlobServiceClient`, `BlobClient`, ...) |
| `com.microsoft.azure:azure-eventhubs` | `com.azure:azure-messaging-eventhubs` |
| `com.microsoft.azure:azure-keyvault` | `azure-security-keyvault-secrets`, `azure-security-keyvault-keys`, `azure-security-keyvault-certificates` |
| `azure-documentdb` | `com.azure:azure-cosmos` |

Mappings are just the starting point. Open each service's specific migration guide because newer APIs often change message handling, async models, paging, retries, or credentials.

### 7.2. Service Bus: QueueClient to builder/processor clients

The `com.microsoft.azure:azure-servicebus` library retired on 30-09-2026. The replacement is `com.azure:azure-messaging-servicebus`.

Example creating a new sender:

```java
ServiceBusSenderClient sender = new ServiceBusClientBuilder()
    .connectionString(connectionString)
    .sender()
    .queueName(queueName)
    .buildClient();

sender.sendMessage(new ServiceBusMessage("invoice-created"));
sender.close();
```

The new SDK uses builders to create clients, with separate sync and async clients. Receiving messages typically uses `ServiceBusProcessorClient` or a receiver client. When replacing a receiver, check:

- Peek-lock and lock duration.
- Auto-complete vs. manual complete/abandon/dead-letter.
- Lock renewal and message processing duration.
- Max concurrent calls and prefetch.
- Session handling and ordering.
- Retries, error handlers, and connection sharing.

Do not treat replacing `QueueClient` with a new receiver as complete until settlement and redelivery have been tested. Completing a message too early or failing to renew locks can cause lost processing or duplicate business operations.

### 7.3. Storage Blob v8 to v12

Azure Blob SDK v8 used `CloudStorageAccount`, `CloudBlobClient`, `CloudBlobContainer`, and `CloudBlockBlob`. V12 moves to builders and resource-oriented clients:

| v8 | v12 |
| --- | --- |
| `CloudStorageAccount` | `BlobServiceClientBuilder` |
| `CloudBlobClient` | `BlobServiceClient` |
| `CloudBlobContainer` | `BlobContainerClient` |
| `CloudBlob` | `BlobClient` |
| `CloudBlockBlob` | `BlockBlobClient` |

V12 example:

```java
BlobServiceClient serviceClient =
    new BlobServiceClientBuilder()
        .connectionString(connectionString)
        .buildClient();

BlobClient blobClient = serviceClient
    .getBlobContainerClient(containerName)
    .getBlobClient(blobName);

blobClient.uploadFromFile(filePath, true);
```

V12 adds Reactor-based async clients. If the application used RxJava or legacy callbacks, update async and backpressure handling. Verify metadata, content types, access tiers, leases, SAS tokens, multipart/block uploads, and checksums before migrating real data.

### 7.4. Authentication and Azure Identity

Newer SDKs integrate with `azure-identity` and the `TokenCredential` model. Prefer `DefaultAzureCredential` or managed identity when supported by the deployment environment, rather than embedding connection strings or account keys in code.

When replacing SDKs:

- Verify role assignments/RBAC for the data plane.
- Check tenant, subscription, endpoint, and cloud environment.
- Test the credential chain on developer workstations, CI, and production.
- Verify token refresh and retries when credential endpoints experience transient failures.
- Ensure Key Vault, Blob, and Service Bus use the intended authorized identity.

## 8. Replacing Legacy Google Cloud / App Engine APIs

Not every older Google Cloud API is unmaintained. Identify whether the application is using a current client library, an App Engine legacy bundled service, or a runtime-specific API.

The App Engine Java 8 first-generation runtime was deprecated on 31-01-2026 and no longer permits new deployments. Some legacy bundled APIs remain accessible in second-generation runtimes via the App Engine API JAR, but only as a transitional path. Where a suitable standalone Google Cloud service exists, migrate to that service and Cloud Client Libraries.

### 8.1. Mapping App Engine legacy services

| Legacy API/service | Replacement direction | Notes |
| --- | --- | --- |
| Blobstore | Cloud Storage | Migrate objects, metadata, URLs, and access control |
| Datastore bundled API | Firestore in Datastore mode / Datastore client libraries | Same underlying service, but requires new clients and permissions |
| Memcache | Memorystore | Choose Redis/Memcached by architecture; do not assume API compatibility |
| Task Queue push | Cloud Tasks | Must migrate queue/task APIs; existing queues can be kept on some paths |
| Task Queue pull | Pub/Sub | Redefine ack, lease, redelivery, and worker models |
| URL Fetch | Java HTTP Client or modern HTTP client | Check timeouts, proxies, TLS, and retries |
| App Identity | OIDC ID token or Identity Platform depending on use case | Review audience, issuer, and trust |
| Mail | SMTP-based provider | Involves provider change, deliverability, and suppression |
| Search | Elasticsearch or suitable search service | Rebuild indexes and verify query semantics |
| Images | Cloud Storage, Cloud Run image service, CDN, or image processing library | No 1:1 replacement for every operation |

Some legacy APIs such as Blobstore, Datastore, or Task Queues may remain available on the Java second-generation runtime. However, migrating to standalone services reduces coupling to the App Engine runtime and makes moving to Cloud Run or other environments easier.

### 8.2. Example Datastore client

If migrating App Engine Datastore to Firestore in Datastore mode, the application uses the Cloud Datastore client library. Example dependencies managed via the Google Cloud Libraries BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>libraries-bom</artifactId>
            <version>GOOGLE_CLOUD_LIBRARIES_BOM_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-datastore</artifactId>
    </dependency>
</dependencies>
```

Replace `GOOGLE_CLOUD_LIBRARIES_BOM_VERSION` with the version selected from the BOM page at upgrade time. The BOM keeps Cloud Client Libraries aligned with foundational libraries such as gRPC, protobuf, Guava, and Google HTTP Client. If the application uses Spring Framework on Google Cloud, check the Spring integration BOM/compatibility matrix before importing an additional standalone BOM.

### 8.3. Example Blobstore to Cloud Storage

Cloud Storage client:

```java
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobId blobId = BlobId.of(bucketName, objectName);
BlobInfo blobInfo = BlobInfo.newBuilder(blobId)
    .setContentType("application/octet-stream")
    .build();

storage.create(blobInfo, Files.readAllBytes(filePath));
```

This example illustrates the object write path. A real migration must also migrate existing data, metadata, ACL/IAM, lifecycles, retention, signed URLs, and URLs stored in databases. Do not switch off the Blobstore API or delete old data before reconciling object counts and checksums.

### 8.4. Not every API has a 1:1 replacement

Some legacy services lack an exact standalone equivalent. In those cases, analyze the use case and choose a third-party solution or redesign. For example, App Engine Search does not automatically convert into Elasticsearch without rebuilding indexes, analyzers, ranking, and query mappings. Moving from Memcache to Memorystore also requires checking eviction, TTLs, serialization, and network latency.

## 9. Avoiding Replacing With Another Dependency Nearing End of Support

A replacement is only good if it has a clear lifecycle. Before selecting one, verify:

- Current release line and support policy.
- Java baseline and Spring Boot compatibility.
- Supported service API version.
- Security update cadence.
- License and support model.
- Test support and local emulators.
- Repository health, issues, maintainers, and release activity.
- Roadmap and migration guidance.

For community libraries, check the number of active maintainers and issue responsiveness. Do not use GitHub stars as the sole criterion. A widely used project with no recent releases or security responses still poses a risk.

If the vendor SDK has an official replacement, evaluate that replacement first. If choosing a third-party option, document who is responsible for patching vulnerabilities, tracking service API updates, and maintaining compatibility with newer JDKs.

## 10. Keeping Dependencies Converged in Spring Boot

When replacing SDKs, the dependency graph often shifts significantly. Do not pin versions for individual modules manually if the provider publishes a BOM.

| Ecosystem | BOM to check |
| --- | --- |
| AWS SDK v2 | `software.amazon.awssdk:bom` |
| Google Cloud Java client libraries | `com.google.cloud:libraries-bom` |
| Direct Azure SDK Java | `com.azure:azure-sdk-bom` |
| Spring Cloud AWS | Spring Cloud AWS dependencies BOM |
| Spring Framework on Google Cloud | Spring Cloud GCP dependencies BOM |
| Spring Cloud Azure | Spring Cloud Azure dependencies BOM |

An application using a Spring Cloud provider starter should prioritize the corresponding integration's BOM and follow provider documentation. Do not add a separate SDK BOM if it overrides versions already managed by the starter, unless you have verified the combination.

After changing dependencies, inspect:

```bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
./gradlew dependencies --configuration runtimeClasspath
```

Search for legacy dependencies still pulled in transitively. Use exclusions only when you know which dependency pulls them in and have tests proving removal does not break classes or runtime behavior.

## 11. Service-by-Service Migration Strategy

You do not need to replace every provider integration at once. Split along service and boundary lines to limit blast radius.

### 11.1. Create business-layer abstractions

Instead of letting business services depend directly on `S3Client`, `BlobClient`, or `Storage`, define business-oriented ports:

```java
public interface DocumentStore {
    void put(String documentId, InputStream content, String contentType);
    InputStream get(String documentId);
    void delete(String documentId);
}
```

AWS, Azure, or Google Cloud adapters implement this interface. When replacing an SDK, business logic stays intact and only the adapter is rewritten.

Similarly, for messaging:

```java
public interface InvoiceEventPublisher {
    void publish(InvoiceCreated event);
}
```

Do not build overly generic abstractions like a `CloudClient` with dozens of methods for every provider. Ports should reflect real use cases and the semantics the application needs.

### 11.2. Use a step-by-step adapter/strangler approach

1. Add the replacement dependency while keeping the old API in the adapter module.
2. Write the new implementation behind the port.
3. Run contract tests against both old and new implementations.
4. Shift a subset of workloads or one resource type to the new adapter.
5. Reconcile results and metrics.
6. Shift primary traffic.
7. Remove the old SDK once no callers or transitive dependencies remain.

For storage, you can copy/backfill objects and compare metadata/checksums before switching the read path. For databases, plan schema changes and dual-reads if formats change. For queues, dual-publishing can create duplicates; establish idempotency keys and deduplication strategies before enabling it.

## 12. Testing Behavior Instead of Only Checking Compilation

A replacement must be verified across multiple layers.

| Test category | What to prove |
| --- | --- |
| Compile/API | Code uses the right new packages, models, and methods |
| Dependency | No legacy SDK remains outside intentionally scoped boundaries |
| Configuration | Endpoint, region, project, subscription, vault, and profiles are right |
| Identity | Principal/token is right, role/RBAC is sufficient and least-privilege |
| Contract | Payloads, metadata, statuses, and error mappings preserve semantics |
| Failure | Timeouts, retries, backoff, circuit breakers, and missing resources |
| Messaging | Ordering, ack, redelivery, DLQ, sessions, and duplicate handling |
| Storage | Content types, metadata, checksums, multipart, ACL/IAM, and signed URLs |
| Data | Queries, transactions, pagination, consistency, and indexes |
| Performance | Latency, throughput, memory, connection pools, and startup |
| Observability | Log correlation, metrics, traces, and health indicators |
| Operations | Shutdown, client close, token refresh, and rollback |

Critical tests must run with production-like identities. Mocks cannot catch missing IAM permissions, wrong endpoints, TLS trust issues, credential chain bugs, or real service differences.

## 13. Deployment and Rollback

Before rollout, record:

- Old and new artifact/image digests.
- Dependency trees and SBOMs for both versions.
- Runtime configuration, endpoints, and identity bindings.
- Schema/data migration versions.
- Queue subscription/consumer configurations.
- Baseline metrics and smoke test results.

Deploy to a canary or small group of instances first. Monitor per-provider API error rates, latency, retries, queue backlogs, DLQs, storage failures, token refresh, and connection pools.

Rollback plans must account for data and messages created by the new SDK. Do not simply revert the container image if metadata formats, schemas, or event payloads changed. If the replacement writes data in an incompatible format, have a backward-compatible reader or separate data migration plan ready.

## 14. Hands-On Exercise: Replacing Legacy Connectors and SDKs in invoice-service

**Context:** `invoice-service` contains these components:

- Spring Cloud Connectors to read Cloud Foundry `VCAP_SERVICES`.
- AWS SDK for Java 1.x to store invoices in S3.
- Legacy Azure Service Bus client to publish events.
- App Engine legacy Task Queue API to run background tasks.
- Spring Boot and Spring Cloud provider integrations needing upgrades to supported branches.

The goal is to replace deprecated/EOL libraries while preserving business contracts.

### Step 1 — Build an inventory

Run:

```bash
./mvnw dependency:tree -Dverbose
rg -n "com\\.amazonaws|com\\.microsoft\\.azure|org\\.springframework\\.cloud\\.connectors" .
rg -n "spring-boot-starter-cloud-connectors|azure-servicebus|aws-java-sdk-|QueueFactory|TaskQueue" .
```

Record all service bindings, S3 operations, message send/receive flows, and Task Queue operations. Classify which parts are SDKs, connectors, and Spring integrations.

### Step 2 — Replace the Cloud Foundry connector

- Remove the Spring Cloud Connectors starter and old connector modules.
- Add `java-cfenv-boot` compatible with your Spring Boot version.
- Remove `@ServiceScan` and `@CloudScan`.
- Verify `VCAP_SERVICES` contains the required bindings.
- Check the `cloud` profile if the application relies on it.
- If there are multiple database/Redis instances, configure each instance explicitly.

### Step 3 — Replace AWS SDK v1

- Import the AWS SDK v2 BOM.
- Add the `s3` module and other modules actually used.
- Migrate `AmazonS3` to `S3Client`.
- Migrate mutable request models to builders.
- Check paginators, multipart transfers, and metadata.
- Verify IAM roles and credential precedence.
- Remove `aws-java-sdk-*` after all code is migrated.

### Step 4 — Replace the legacy Azure Service Bus SDK

- Remove `com.microsoft.azure:azure-servicebus`.
- Add `com.azure:azure-messaging-servicebus`.
- Create senders with `ServiceBusClientBuilder`.
- Migrate consumers to the appropriate processor/receiver API.
- Verify peek-lock, settlement, sessions, retries, and dead-letter handling.
- Test duplicate messages and message lock expiration.

### Step 5 — Replace Task Queue

If the application uses push queues, migrate to Cloud Tasks. If it uses pull queues, evaluate Pub/Sub. Do not merely rename queues and assume identical semantics. Verify retry schedules, target HTTP endpoints, auth tokens, deadlines, acks, redelivery, and rate limits.

### Step 6 — Run contract tests

- Upload an invoice to S3 and compare object metadata/checksums.
- Send `InvoiceCreated` to Service Bus and verify the consumer handles idempotency keys properly.
- Run background tasks covering success, timeout, retry, and dead-letter cases.
- Verify AWS/Azure/GCP principals and least-privilege permissions.
- Compare latency and retry volume against baseline.

### Step 7 — Canary and remove old libraries

Deploy a new revision and observe metrics and logs. Once flows meet expectations, shift traffic and remove old dependencies. Generate a new SBOM to confirm no EOL artifacts remain in the runtime.

## 15. Review Checklist Before Merging

- [ ] Confirmed support/EOL status from maintainers.
- [ ] Documented official replacements and migration guides.
- [ ] Distinguished SDKs, Spring integrations, and platform connectors.
- [ ] Verified JDK, Spring Boot, Spring Cloud, and provider compatibility.
- [ ] Checked dependency trees and package imports repository-wide.
- [ ] Identified which legacy library behaviors the application relies on.
- [ ] Selected appropriate BOMs and checked dependency convergence.
- [ ] Verified credential chains, IAM/RBAC, and token refresh.
- [ ] Verified retries, timeouts, pagination, and client lifecycles.
- [ ] Verified storage metadata, checksums, and data migration.
- [ ] Verified messaging ack, ordering, duplicates, and DLQ behavior.
- [ ] Ran contract tests and provider integration tests.
- [ ] Ran canary deployment and compared against baseline.
- [ ] Prepared rollback plans for images, config, data, and messages.
- [ ] Removed legacy dependencies once no callers/transitive requirements remain.
- [ ] Updated SBOM and dependency inventory.

## 16. Self-Check Questions

1. What are the differences among deprecated, maintenance mode, end-of-support, and archived?
2. Why does a dependency still downloadable from Maven Central not mean it is still supported?
3. How do Spring Cloud Connectors differ in role from Java CFEnv?
4. Why can `java-cfenv-boot` work alongside Spring Boot auto-configuration?
5. How do AWS SDK v1 and v2 differ in packages, models, clients, and credential chains?
6. Which high-level APIs does the AWS migration tool not migrate automatically?
7. Why should you check paginators when migrating the AWS SDK?
8. How does the new Azure Service Bus SDK change how senders and receivers are created?
9. In what client hierarchy do Storage Blob v8 and v12 differ?
10. Which services should replace App Engine Task Queue push and pull queues?
11. Why is the Cloud Client Libraries BOM important for Google Cloud Java?
12. Why might a replacement require IAM/RBAC changes even when the service name stays the same?
13. Why should you not dual-publish messages during migration without idempotency?
14. How does an adapter/domain port reduce the cost of replacing an SDK?
15. Which data points and metrics should be saved before a canary rollout?
16. When rolling back, why must you check schemas, object metadata, and event payloads as well?

## 17. Key Takeaways

Replacing unmaintained libraries starts by verifying support policies and understanding exactly what functionality the dependency provides. Select replacements based on compatibility, security, behavior, and operability. Never swap artifacts or packages alone and treat the migration as complete.

For Cloud Foundry, Java CFEnv replaces most legacy service-binding needs. For AWS, SDK v1 is EOL and must migrate to v2. For Azure, legacy `com.microsoft.azure` packages map to current `com.azure` SDKs. For Google Cloud, migrate legacy bundled APIs to standalone services/Cloud Client Libraries where appropriate and re-verify IAM. **Every migration needs contract tests, dependency convergence, observed rollout, and rollback covering written data.**

## Official References

- [Cloud Foundry — Configuring service connections and migrating to Java CFEnv](https://docs.cloudfoundry.org/buildpacks/java/configuring-service-connections.html)
- [Spring Boot 2.3 — Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes)
- [AWS — AWS SDK for Java 1.x end-of-support](https://github.com/aws/aws-sdk-java)
- [AWS — Migration from SDK for Java 1.x to 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration.html)
- [AWS — Migration tool and limitations](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-tool.html)
- [AWS — Differences between SDK v1 and v2](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-whats-different.html)
- [Azure — Deprecated Java SDK packages and replacements](https://azure.github.io/azure-sdk/releases/deprecated/java.html)
- [Azure — Service Bus Java migration guide](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/servicebus/azure-messaging-servicebus/migration-guide.md)
- [Azure — Storage Blob v8 to v12 migration guide](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/storage/azure-storage-blob/migrationGuides/V8_V12.md)
- [Google Cloud — Java Cloud Client Libraries BOM](https://docs.cloud.google.com/java/docs/bom)
- [Google Cloud — App Engine Java legacy bundled services and alternatives](https://docs.cloud.google.com/appengine/docs/standard/services/overview?tab=java)
- [Google Cloud — Migrate App Engine Java 8 to second-generation runtime](https://docs.cloud.google.com/appengine/migration-center/standard/migrate-to-second-gen/java-differences)
- [Google Cloud — Migrate Java push queues to Cloud Tasks](https://docs.cloud.google.com/appengine/migration-center/standard/java/migrating-push-queues)
- [Google Cloud — Migrate App Engine Datastore to Firestore in Datastore mode](https://docs.cloud.google.com/appengine/migration-center/standard/java/migrate-datastore)
