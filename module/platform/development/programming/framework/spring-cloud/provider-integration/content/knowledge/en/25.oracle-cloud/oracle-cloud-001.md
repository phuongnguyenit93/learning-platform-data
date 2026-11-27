# Spring Cloud Oracle, Spring Cloud OCI, and Subproject Boundaries

Oracle has many components serving Spring applications: Oracle AI Database, database-backed queues and event streams, Oracle Cloud Infrastructure (OCI), and the Generative AI service. The names Spring Cloud Oracle and Spring Cloud OCI are closely related but not synonymous. Understanding the project structure helps you choose the right starter, API, dependency, and operational model.

**Spring Cloud Oracle** is a multi-module project that brings together Spring Boot integrations for Oracle technologies. **Spring Cloud OCI** is a subproject within it, focusing on managed services of Oracle Cloud Infrastructure such as Object Storage, Vault, Streaming, Queue, Functions, and Autonomous Database. Starters connecting directly to Oracle AI Database, the binder for TxEventQ, and the Spring AI Oracle integration have their own boundaries.

This lesson defines that structure, shows when to use each branch, and explains how to combine them in a Spring Boot application. The goal is to help learners declare the right dependencies and choose the right programming model before diving deeper into each OCI service.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the relationship between Spring Cloud Oracle, Spring Cloud OCI, and the OCI SDK.
2. Identify the main subprojects in the Spring Cloud Oracle ecosystem.
3. Distinguish between OCI managed service integrations and direct Oracle AI Database integrations.
4. Choose between OCI Queue, OCI Streaming, TxEventQ via JMS/OKafka, and the Spring Cloud Stream binder.
5. Choose the right Maven group/artifact for each type of integration.
6. Understand the role of the core starter, service-specific starter, and auto-configuration.
7. Choose an OCI authentication method suitable for local development, compute, Functions, and OKE.
8. Distinguish Spring-friendly APIs from OCI service-specific semantics.
9. Build configuration, testing, and deployment according to compatible Spring Boot versions.
10. Avoid mixing up dependencies, transaction boundaries, and operational responsibilities across subprojects.

## 2. Why Are There Multiple Names?

Three concepts are often confused:

- **Oracle Cloud Infrastructure (OCI):** Oracle's cloud platform, providing compute, networking, Object Storage, Vault, Queue, Streaming, Functions, Autonomous Database, and many other managed services.
- **Spring Cloud Oracle:** The project that integrates Oracle technologies into the Spring Boot programming model.
- **Spring Cloud OCI:** The branch that integrates OCI services within the Spring Cloud Oracle project.

Spring Cloud Oracle is not a cloud service, nor is it a single client SDK. It is a collection of starters, auto-configuration, templates, resource abstractions, binders, and sample applications. The OCI Java SDK remains the underlying client layer for OCI APIs; Spring starters help configure and use the SDK in a way that feels familiar to Spring developers.

### How Naming Evolved Over Time

Documentation and repositories have evolved over multiple versions. Older documentation streams may refer to the OCI integration as Spring Cloud OCI or Spring Cloud for OCI as the name of a standalone project/library. The newer structure places this under the multi-module Spring Cloud Oracle project.

Therefore, when reading older documentation or dependencies, check:

- Whether the version in use belongs to the 1.x or 2.x line.
- The artifact and package names for that exact version.
- The supported Spring Boot/Spring Framework versions.
- Whether a module has been renamed, relocated, or replaced.

Do not infer the current structure solely from a blog post or an example using older artifacts. The reference documentation and release notes for the exact version are the authoritative source.

## 3. Map of Subprojects

The current structure has four complementary branches:

~~~mermaid
flowchart TD
    A[Spring Cloud Oracle] --> B[Oracle AI Database Spring Boot Starters]
    A --> C[Spring Cloud Stream Binder for TxEventQ]
    A --> D[Spring Cloud OCI]
    A --> E[Spring AI Oracle]
    B --> F[UCP / Wallet / AQ-JMS / OKafka / JSON / Spatial]
    C --> G[Spring Cloud Stream Supplier / Function / Consumer]
    D --> H[Vault / Object Storage / Queue / Streaming / Functions / ADB]
    E --> I[OCI Generative AI via Spring AI APIs]
~~~

| Branch | Scope | When to Choose |
| --- | --- | --- |
| Oracle AI Database Spring Boot Starters | Database connectivity, UCP, Wallet, AQ/JMS, OKafka, JSON, Spatial, and telemetry | Application needs to connect to or use Oracle AI Database features |
| Spring Cloud Stream Binder for TxEventQ | Brings Oracle Transactional Event Queues into Spring Cloud Stream's Supplier/Function/Consumer model | Want to use TxEventQ via Spring Cloud Stream |
| Spring Cloud OCI | Integrates OCI managed services through Spring-idiomatic starters and APIs | Application needs Vault, Object Storage, Queue, Streaming, Functions, Logging, or other OCI services |
| Spring AI Oracle | Integrates OCI Generative AI models through Spring AI abstractions | Application uses OCI chat models or embedding models via Spring AI |

These branches belong to the same Oracle ecosystem but are not a single monolithic module. They can share an application and some configuration foundations, but you should not add every starter in an "all-in-one Oracle suite" fashion.

### Quick Selection Diagram

~~~mermaid
flowchart TD
    A[Spring App Needs Oracle Integration] --> B{What is the integration target?}
    B -->|Oracle Database| C[Oracle AI Database starters]
    B -->|OCI managed service| D[Spring Cloud OCI]
    B -->|TxEventQ via Spring Cloud Stream| E[TxEventQ Stream Binder]
    B -->|OCI Generative AI via Spring AI| F[Spring AI Oracle]
    C --> G[UCP / Wallet / AQ-JMS / OKafka / JSON]
    D --> H[Storage / Vault / Queue / Streaming / Functions]
    E --> I[Supplier / Function / Consumer]
    F --> J[ChatModel / EmbeddingModel]
~~~

## 4. How Do Spring Cloud Oracle and Spring Cloud OCI Differ?

### Spring Cloud Oracle: Overall Scope

Spring Cloud Oracle brings together integrations for the Oracle ecosystem. The scope is not limited to OCI. For example, UCP and Wallet serve database connectivity; AQ/JMS and OKafka serve messaging tied to Oracle AI Database; the TxEventQ binder integrates with Spring Cloud Stream; Spring Cloud OCI connects to cloud services; Spring AI Oracle brings Generative AI into Spring AI applications.

### Spring Cloud OCI: Cloud Services Scope

Spring Cloud OCI focuses on OCI. A core starter configures authentication and shared infrastructure; service-specific starters add beans and APIs for each service.

Typical integrations:

- Object Storage: APIs for bucket/object operations and Spring Resource.
- Vault: property source and API for managing/reading secrets.
- Streaming: producing and consuming records from OCI Streaming.
- Queue: operating on OCI Queue queues and messages.
- Notifications: publishing notifications to topics.
- Logging: sending logs to OCI Logging.
- Email Delivery: Spring Mail integration.
- Functions: invoking OCI Functions.
- Autonomous Database: managing Autonomous Database resource lifecycle operations.
- Oracle NoSQL Database: accessing Oracle NoSQL.
- Generative AI: OCI Generative AI integration; check the current version recommendations since the Spring AI Oracle branch has been split out separately.

### The OCI SDK Remains the Foundation Underneath

Spring Cloud OCI does not eliminate the OCI SDK. It provides auto-configuration, beans, and Spring-friendly usage patterns. When you need a feature not yet covered by a starter, you can use the OCI SDK directly within the same application, but you should keep a single place responsible for authentication, region, retry, timeout, and client lifecycle.

Do not accidentally create two sets of clients with two different credential profiles. If using both a starter and the SDK directly, unify the provider/credential strategy and access permissions.

## 5. Dependency Boundaries and Maven Coordinates

The branches use different groupIds. This is an important signal to avoid picking the wrong artifact.

| Integration Type | Common GroupId | Example Artifact |
| --- | --- | --- |
| Spring Cloud OCI core | com.oracle.cloud.spring | spring-cloud-oci-starter |
| OCI Object Storage | com.oracle.cloud.spring | spring-cloud-oci-starter-storage |
| OCI Vault | com.oracle.cloud.spring | spring-cloud-oci-starter-vault |
| OCI Streaming | com.oracle.cloud.spring | spring-cloud-oci-starter-streaming |
| OCI Queue | com.oracle.cloud.spring | spring-cloud-oci-starter-queue |
| Oracle AI Database UCP | com.oracle.database.spring | oracle-spring-boot-starter-ucp |
| Oracle AI Database Wallet | com.oracle.database.spring | oracle-spring-boot-starter-wallet |
| Oracle AI Database AQ/JMS | com.oracle.database.spring | oracle-spring-boot-starter-aqjms |
| Oracle AI Database OKafka | com.oracle.database.spring | oracle-spring-boot-starter-okafka |
| TxEventQ Spring Cloud Stream binder | com.oracle.database.spring.cloud-stream-binder | spring-cloud-stream-binder-oracle-txeventq |

Artifact names and groupIds may change between major releases. This table helps identify boundaries, not replace checking the documentation for your exact version.

### Core Starter and Service Starters

With Spring Cloud OCI:

- The core starter provides authentication configuration and shared infrastructure.
- A service starter pulls in the implementation needed for a specific integration.
- When a service starter already declares the transitive dependency of the corresponding module, you do not need to declare a separate implementation module unless required by the documentation.

Maven example for an application needing Object Storage:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.oracle.cloud.spring</groupId>
        <artifactId>spring-cloud-oci-starter-storage</artifactId>
        <version>SPRING_CLOUD_ORACLE_VERSION</version>
    </dependency>
</dependencies>
~~~

In many setups, a service starter pulls in the necessary core starter. If the application needs multiple OCI services, check the dependency tree and version guidelines to avoid duplicate declarations or mixed versions.

### Do Not Mix Artifacts Just Because They Are Both Oracle

For example:

- To use Object Storage, choose the starter under Spring Cloud OCI.
- To use JDBC with Oracle AI Database, choose the JDBC driver and the appropriate UCP starter.
- To use TxEventQ via JMS, choose the AQ/JMS starter.
- To use TxEventQ via Spring Cloud Stream, choose the corresponding binder.
- To use Kafka-style APIs on TxEventQ, look at OKafka.
- To use OCI Generative AI via Spring AI, look at Spring AI Oracle.

An artifact from the database branch does not become an OCI service starter simply because Autonomous Database is deployed on OCI.

## 6. Version Alignment: Spring Boot, Spring Cloud Oracle, and OCI SDK

Cloud integration depends on multiple version layers:

1. Java runtime.
2. Spring Boot.
3. Spring Framework.
4. Spring Cloud Oracle subproject.
5. Spring Cloud Stream or Spring AI if used.
6. OCI Java SDK and transitively pulled clients.
7. JDBC driver, UCP, Wallet, or NoSQL driver if using database starters.

Do not upgrade a single transitive dependency on its own to fix a compile error without checking the compatibility matrix.

### Major Versions Can Change the Underlying Platform

The 2.x line of Spring Cloud Oracle moves to Spring Boot 4 and Spring Framework 7. Therefore, you cannot assume a 2.x starter is a drop-in replacement for an application currently running Spring Boot 3 or 2.x.

If your current application uses Spring Boot 3:

- Identify the Spring Cloud Oracle release line compatible with Boot 3.
- Read the migration guide/release notes for that line.
- Do not pull in the 2.x starter just because it is newer.
- Only upgrade the Boot major version after planning for Spring Framework, Jakarta APIs, test libraries, and related dependencies.

If your application uses Spring Boot 4:

- Choose the Spring Cloud Oracle 2.x version supported by the documentation.
- Align versions across the OCI starter, database starter, binder, and Spring AI Oracle.
- Use the project's dependency management according to official guidelines.
- Inspect the dependency tree to detect two different versions of the OCI SDK or Spring libraries appearing together.

### Version Selection Workflow

~~~text
1. Identify the application's Spring Boot version
2. Choose the compatible Spring Cloud Oracle release line
3. Identify the exact subproject and starter
4. Use the version/BOM from the release line documentation
5. Inspect the dependency tree
6. Run compile + integration tests
7. Deploy to staging and observe authentication, connections, and retries
~~~

Do not copy dependency versions from a sample with a different Boot version. A sample may demonstrate an API without directly matching your project's baseline.

## 7. OCI Authentication: What Is the Core Starter Responsible For?

OCI APIs require an identity for authentication and authorization to check permissions. The Spring Cloud OCI core starter auto-configures authentication and shared infrastructure for service starters.

Common authentication types:

| Type | Typical Environment | Characteristics |
| --- | --- | --- |
| FILE | Developer machine or environment with an OCI config profile | Reads configuration from the OCI CLI/SDK file |
| SIMPLE | Cases requiring direct declaration of API key properties | Requires user OCID, tenancy OCID, fingerprint, private key, and region |
| INSTANCE_PRINCIPAL | OCI Compute instance | Uses the instance's identity and dynamic group/policy |
| RESOURCE_PRINCIPAL | OCI Functions or supported resources | Uses the resource's identity instead of embedding a user key |
| SESSION_TOKEN | Temporary working sessions | Suitable for workflows using session tokens |
| WORKLOAD_IDENTITY | Workloads running on OKE in a supported model | Links the workload to an IAM identity |

Choose the method based on where the application runs and the OCI SDK authentication guidelines. Do not treat all types as interchangeable across every environment.

### FILE for Local Development

Example:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: /path/to/oci/config
      region:
        static: YOUR_OCI_REGION
      compartment:
        static: YOUR_COMPARTMENT_OCID
~~~

Property names and defaults must be verified for your starter version. You can let the SDK use the default location if you do not specify a custom file. Do not commit config files or private keys to the repository.

### SIMPLE and API Keys

SIMPLE uses an OCI user's API key information. Sensitive values should not be written literally in `application.yaml`:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: SIMPLE
        user-id: INJECT_USER_OCID_FROM_SECRET_STORE
        tenant-id: INJECT_TENANCY_OCID_FROM_SECRET_STORE
        fingerprint: INJECT_FINGERPRINT_FROM_SECRET_STORE
        private-key: /run/secrets/oci/private-key.pem
        pass-phrase: INJECT_KEY_PASSPHRASE_FROM_SECRET_STORE
        region: YOUR_OCI_REGION
~~~

This is an illustrative structure; verify property binding names in your release. Prefer a secret manager or mounted secret file, grant least-privilege read permissions, and rotate keys according to policy.

### Workload Identity and Principals

In production, avoid attaching a developer's personal API key to workloads. Choose an identity bound to the compute/function/pod according to the environment:

- Compute instance: Instance Principal with dynamic groups and policies.
- OCI Functions: Resource Principal if supported by the runtime/service.
- OKE: Workload Identity when the cluster/workload is properly configured.

Workload identities eliminate the need to distribute personal private keys to containers. However, an identity only provides authentication; policies must still allow the exact operations on the right compartment/resource.

## 8. Region, Compartment, and IAM Policy

### Region

OCI resources belong to a region. Configuring a default region lets starters share the same location unless overridden individually.

~~~yaml
spring:
  cloud:
    oci:
      region:
        static: YOUR_OCI_REGION
~~~

Spring Cloud OCI's static region may take precedence over a region taken from a profile or auth config. Therefore, check property precedence when declaring multiple sources at once.

Do not hardcode a documentation example region into production. Choose a region based on data location, latency, residency, DR, and where resources are actually provisioned.

### Compartment

A compartment is the organizational and access-control boundary for OCI resources. You can configure a default compartment:

~~~yaml
spring:
  cloud:
    oci:
      compartment:
        static: YOUR_COMPARTMENT_OCID
~~~

An application can operate on resources across multiple compartments; a default property does not replace an explicit compartment ID in operations targeting a different compartment.

### IAM Policy

A successful authentication configuration does not guarantee API calls are permitted. Check:

- User/group or dynamic group/workload identity.
- Appropriate policy verb: inspect, read, use, manage.
- Resource type and compartment scope.
- Service-specific or operation-specific permissions.
- Policies for service principals if an OCI service needs to access another resource.
- Separate permissions for reading secrets, writing objects, and publishing/consuming messages.

Start with the minimum permissions required for the use case. Do not grant manage-all at the tenancy level just to quickly work around a 403 error.

## 9. Auto-Configuration and Spring Beans

A Spring Boot starter typically performs:

1. Reading configuration from the Spring Environment.
2. Creating an authentication provider or reusing an existing one.
3. Configuring region/compartment.
4. Creating OCI SDK clients/templates or Spring abstractions.
5. Registering beans in the application context.
6. Applying conditional properties to enable/disable the integration.

The application can inject beans via constructors instead of instantiating clients in every service.

~~~java
@Service
public class DocumentArchiveService {

    private final Storage storage;

    public DocumentArchiveService(Storage storage) {
        this.storage = storage;
    }

    // Upload/download operations using the Storage bean
}
~~~

Specific package names and method imports depend on the module/version. Read the corresponding Javadoc or sample before writing full code.

### When Do You Need the OCI SDK Directly?

Use the SDK directly if:

- The starter does not yet expose a needed operation.
- You need service-specific client configuration.
- You need an API newer than the Spring integration version.
- You need a capability that has no Spring abstraction.

Keep the same principle: reuse the authentication provider, region, retry, timeout, and lifecycle. Do not create a new client per request; SDK clients are generally designed to be reused.

## 10. Object Storage: Spring Resource and Storage API

OCI Object Storage stores objects by namespace, bucket, and object name. Spring Cloud OCI provides the Storage API and integrates with Spring Resource.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

The starter can auto-configure a Storage bean for bucket/object operations.

Illustrative example:

~~~java
@Service
public class InvoiceArchive {

    private final Storage storage;

    public InvoiceArchive(Storage storage) {
        this.storage = storage;
    }

    public void upload(
            String bucket,
            String objectName,
            InputStream content,
            StorageObjectMetadata metadata) {

        storage.upload(bucket, objectName, content, metadata);
    }
}
~~~

Actual APIs and imports must match the release. Clearly define who owns the InputStream and close the stream in the proper place. Do not read an entire large file into a byte array if you can stream it.

### Spring Resource

Objects can be accessed via the Resource abstraction using an Object Storage URI format:

~~~text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object>
~~~

Spring Cloud OCI can resolve an object into a Resource so it can be read like other resources. WritableResource integration allows writing objects via an OutputStream; the upload completes when the stream is closed according to the implementation's contract.

Benefits:

- You can use ResourceLoader/ApplicationContext to resolve resources.
- File-reading code stays close to Spring abstractions.
- You can pass the Resource into Spring APIs that accept a Resource.
- No need to write all the OCI SDK plumbing for common operations.

The Resource abstraction does not turn Object Storage into a POSIX filesystem. Do not assume renames, directories, atomic updates, or filesystem-like locking. An object key is an object name; folders are merely prefix conventions.

### Design Decisions

- Bucket and object naming.
- Namespace and region.
- Content-Type, metadata, and encryption.
- Multipart upload for large files.
- Retention, lifecycle, and versioning.
- Conditional write/overwrite policy.
- Read/write/delete permissions per workload.
- Idempotency on upload retries.
- Pre-authenticated access if the use case allows it and with an expiration time.

Do not put sensitive information in object metadata without corresponding controls. Avoid logging file contents or access URLs containing tokens.
## 11. Vault: Secrets and Spring Environment

OCI Vault can be used in two main ways in the Spring Cloud OCI integration:

- As a property source to bring configuration values from Vault into the Spring Environment.
- As an API bean for the application to query secrets on demand via VaultTemplate.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

### Vault as a Property Source

Configuration example:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
      region:
        static: YOUR_OCI_REGION
      vault:
        enabled: true
        compartment: YOUR_COMPARTMENT_OCID
        property-refresh-interval: 10m
        property-sources:
          - vault-id: YOUR_VAULT_OCID
~~~

A secret can be referenced from the Spring Environment by the name configured in the Vault integration. Property naming, prefixes, and refresh behavior must match the starter version.

Benefits:

- Secrets do not have to be stored in `application.yaml`.
- Secret read permissions can be managed via OCI IAM.
- Versions/rotation can be managed in Vault.
- The application uses Spring property conventions.

However, refreshing a property source does not automatically recreate every singleton bean that already injected the old value. Check binding, refresh scope, and the lifecycle of secret-dependent beans. For credentials requiring rotation, design a reload/refresh mechanism and test it when a secret changes.

### VaultTemplate

The starter can also auto-configure VaultTemplate for API operations:

~~~java
@Service
public class SecretLookupService {

    private final VaultTemplate vaultTemplate;

    public SecretLookupService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readSecret(String secretName) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(secretName);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Class and method names must match the release Javadoc. Do not log secret values, do not include secrets in exception messages, and do not cache indefinitely if rotation is an operational requirement.

### Secrets, Keys, and Permissions

OCI Vault has separate concepts for secrets and keys. An application needing to read secrets does not automatically need permission to manage encryption keys or administer the entire Vault. Grant least-privilege permissions for the appropriate workload identity and compartment.

Do not use Vault to store all kinds of business data or large files. Choose the service based on data type: Vault for sensitive secrets/config; Object Storage for files/objects; a database for database records.

## 12. Messaging: Three Models to Distinguish

In the Oracle ecosystem, there are multiple messaging options. Their names sound similar, but their backends and semantics differ.

| Option | Backend | Programming Model | Best Suited When |
| --- | --- | --- | --- |
| OCI Queue | OCI managed queue service | Queue/message API | Independent jobs processed via a queue |
| OCI Streaming | OCI managed stream service | Stream/partition/cursor API | High-throughput record stream ingestion and consumption |
| TxEventQ via AQ/JMS | Oracle AI Database Transactional Event Queues | JMS, JmsTemplate, listener | Applications using Spring JMS that want a database-tied queue |
| TxEventQ via OKafka | Oracle AI Database Transactional Event Queues | Kafka Java client APIs | Applications already using Kafka-style producers/consumers |
| TxEventQ via Stream Binder | Oracle AI Database Transactional Event Queues | Spring Cloud Stream Supplier/Function/Consumer | Applications following Spring Cloud Stream's function-based messaging model |

Do not choose solely based on the word "queue" or "stream". Determine where messages are stored, transaction boundaries, throughput, ordering, consumer groups, retention, delivery/ack semantics, and operational practices.

## 13. OCI Queue and OCI Streaming

### OCI Queue

OCI Queue is a managed queue service for messages processed independently. Spring Cloud OCI provides the starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-queue</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

The starter auto-configures a Queue bean for queue and message operations.

Items to design:

- Queue creation and retention configuration.
- Delivery count and dead-letter behavior.
- Message visibility/acknowledgment semantics.
- Retry, poison messages, and quarantine.
- Consumer concurrency and flow control.
- Message ID, correlation ID, and idempotency.
- IAM permissions for producers/consumers.

Queue fits tasks that can be processed independently: generating thumbnails, processing invoices, sending notifications, running background workflows. Consumers must handle duplicates safely according to the service's semantics.

### OCI Streaming

OCI Streaming is a service for ingesting and consuming record streams. Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-streaming</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

The starter can auto-configure a Streaming bean to create streams and send/receive messages.

API-level example:

~~~java
@Service
public class AuditStreamPublisher {

    private final Streaming streaming;

    public AuditStreamPublisher(Streaming streaming) {
        this.streaming = streaming;
    }

    public void publish(
            String streamId,
            byte[] key,
            byte[] payload) {
        streaming.putMessages(streamId, key, payload);
    }
}
~~~

This snippet illustrates bean usage; exact method signatures/imports should be verified against your SDK/starter release.

When designing streams:

- Choose an appropriate partition key to distribute load and preserve ordering where needed.
- Persist consumer cursors/checkpoints durably.
- Handle replayed records after restarts.
- Monitor consumer lag and retention windows.
- Design schemas/versioning and event identity.
- Do not treat a stream as a work-item queue with the same settlement semantics.

### Queue and Streaming Are Not Interchangeable

| Criterion | OCI Queue | OCI Streaming |
| --- | --- | --- |
| Model | Message queue | Event/data stream |
| Reading pattern | Receive messages to process and settle via API | Read records by partition/cursor |
| Progress tracking | Message acknowledgment/visibility | Cursor/checkpoint |
| Ordering | Per queue semantics and configuration | Per partition/key and sequence |
| Use case | Work distribution | Event ingestion, stream processing |
| Recovery | Redelivery/retry/DLQ policy | Replay from cursor within retention |

Do not use a single shared consumer abstraction and assume Queue and Streaming have identical semantics. Write separate adapters if the domain needs a common interface, while keeping differences in settlement/checkpointing inside the implementations.

## 14. TxEventQ: AQ/JMS, OKafka, and Spring Cloud Stream Binder

TxEventQ stands for Oracle Database Transactional Event Queues, which resides inside Oracle AI Database. It is database-tied messaging, neither OCI Queue nor OCI Streaming.

### AQ/JMS Starter

AQ/JMS provides support for Oracle Advanced Queuing and TxEventQ as a JMS provider. Spring applications use JMS abstractions like JmsTemplate and listeners.

Common dependency:

~~~xml
<dependency>
    <groupId>com.oracle.database.spring</groupId>
    <artifactId>oracle-spring-boot-starter-aqjms</artifactId>
    <version>ORACLE_DATABASE_STARTER_VERSION</version>
</dependency>
~~~

AQ/JMS depends on database connectivity infrastructure and UCP. You need to configure the datasource, queues/topics, database user, and appropriate AQ privileges.

Notably, the default configuration as described in the documentation can share a transaction between the datasource and the JMS connection factory. This allows a single local database transaction to read a message, update data, and commit/rollback within the same unit of work when configured properly. Do not extrapolate this property to OCI Queue, OCI Streaming, or other brokers.

### OKafka Starter

OKafka provides Kafka-style producer, consumer, and administration APIs, backed by TxEventQ in Oracle AI Database.

~~~xml
<dependency>
    <groupId>com.oracle.database.spring</groupId>
    <artifactId>oracle-spring-boot-starter-okafka</artifactId>
    <version>ORACLE_DATABASE_STARTER_VERSION</version>
</dependency>
~~~

Choose OKafka when the application already uses Kafka client concepts such as producers, consumers, groups, serializers, and topic administration. If you want JMS APIs, use AQ/JMS. If you want Spring Cloud Stream's function model, consider the binder.

### Spring Cloud Stream Binder for TxEventQ

The binder brings TxEventQ into the Spring Cloud Stream model. The application declares a Supplier, Function, or Consumer and configures bindings instead of managing queue APIs directly in each service.

The artifact has its own group:

~~~xml
<dependency>
    <groupId>com.oracle.database.spring.cloud-stream-binder</groupId>
    <artifactId>spring-cloud-stream-binder-oracle-txeventq</artifactId>
    <version>TXEVENTQ_BINDER_VERSION</version>
</dependency>
~~~

Function example:

~~~java
@Configuration
public class OrderEventFunctions {

    @Bean
    public Function<OrderCreated, OrderAccepted> validateOrder() {
        return event -> new OrderAccepted(
                event.orderId(),
                event.customerId());
    }
}
~~~

The binder connects to the Oracle datasource and TxEventQ according to its configuration. Check database permissions, UCP, binding names, consumer groups, retries, error handling, and transaction behavior for your version.

### Choosing Between AQ/JMS, OKafka, and the Binder

| Question | Recommended Choice |
| --- | --- |
| Does the application use Spring JMS/JmsTemplate? | AQ/JMS |
| Do you need Kafka Java client APIs? | OKafka |
| Are you using Spring Cloud Stream function bindings? | TxEventQ binder |
| Must messages live in an OCI managed queue separate from the database? | OCI Queue |
| Do you need record stream ingestion/partitions/cursors? | OCI Streaming |

Do not install all three TxEventQ integrations if you only need one programming model. Combine them only when there is an architectural reason and queue ownership, transaction managers, and consumer identities are clearly defined.

## 15. Autonomous Database: Resource Management and Data Connectivity Are Two Different Things

The name Autonomous Database appears on both sides, so distinguish carefully:

- The Spring Cloud OCI Autonomous Database starter provides OCI resource lifecycle management operations, such as creating, retrieving information for, or generating wallets for an Autonomous Database.
- Oracle AI Database starters such as UCP and Wallet serve application connections to the database to run queries/transactions.

These are two distinct responsibilities.

### Lifecycle Management

When an application or platform automation needs to provision or look up an Autonomous Database, use the appropriate OCI service integration. These operations typically require resource management permissions and should not be granted to every business service.

### Database Connectivity in Applications

A CRUD application typically needs:

- Oracle JDBC driver.
- DataSource.
- UCP if using Oracle Universal Connection Pool.
- Wallet/mTLS if required by the environment.
- Spring Data JDBC or Spring Data JPA depending on the persistence model.

UCP configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//DB_HOST:1521/DB_SERVICE
    username: APP_USER
    password: INJECT_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
    type: oracle.ucp.jdbc.PoolDataSourceImpl
    oracleucp:
      connection-factory-class-name: oracle.jdbc.pool.OracleDataSource
      connection-pool-name: ProviderIntegrationPool
      initial-pool-size: 2
      min-pool-size: 2
      max-pool-size: 20
~~~

Parameters are illustrative; size according to concurrency, database limits, and workload. Do not leave literal passwords in configuration files.

### Wallet

For Autonomous Database or database endpoints requiring mTLS, the Wallet starter can provide secure connection mechanisms. A wallet is sensitive credential/trust material; manage mounting, rotation, permissions, and backups according to policy.

Do not confuse generating a wallet via a resource management API with an application using a wallet to open JDBC connections. Those two steps may belong to different service identities and lifecycles.

## 16. Spring AI Oracle: Separate from Spring Cloud OCI

Spring AI Oracle provides model integrations for OCI Generative AI through Spring AI APIs. This is a separate branch within the Spring Cloud Oracle ecosystem.

Applications can work with abstractions such as:

- ChatModel or ChatClient for conversations.
- EmbeddingModel for embeddings.
- Streaming/tool calling/memory depending on the capabilities of the model integration and version.

Do not mistake Spring AI Oracle for OCI Queue, OCI Streaming, or a Spring Cloud Stream binder. It is an AI model integration.

### Choosing the Right AI Branch

- Application needs to call OCI Generative AI via Spring AI: use Spring AI Oracle.
- Application needs to manage OCI resources or call other service APIs: use the corresponding Spring Cloud OCI starter.
- Application uses another model provider: keep the Spring AI abstraction if an appropriate implementation exists.

Some older documentation/versions had the Generative AI module inside Spring Cloud OCI. Newer release notes reflect changes and recommend moving model integrations to Spring AI Oracle. When upgrading versions, read the release notes rather than keeping old dependencies out of habit.

## 17. Combining Branches in a Real-World Architecture

Example of an invoice processing service:

~~~mermaid
flowchart TD
    A[Spring Boot Invoice API] --> B[Oracle AI Database]
    A --> C[OCI Object Storage]
    A --> D[OCI Vault]
    B --> E[UCP / Wallet]
    C --> F[Spring Cloud OCI Storage]
    D --> G[Spring Cloud OCI Vault]
    B --> H[TxEventQ]
    H --> I[Spring Cloud Stream Binder]
    A --> J[OCI Queue or Streaming]
    A --> K[OCI Generative AI]
    K --> L[Spring AI Oracle]
~~~

A request may:

1. Authenticate the user through the API layer.
2. Write invoice metadata to Oracle AI Database.
3. Write an outbox/TxEventQ event within the appropriate transaction.
4. Store the PDF file in OCI Object Storage.
5. Read needed secrets from Vault.
6. Publish an event to consumers to send emails or continue processing.
7. Use Generative AI to extract/suggest content if the use case requires it.

Not every step should run inside a single synchronous request. File uploads, event publishing, and database transactions have separate failure boundaries. Use outbox/saga or workflow state when multiple side effects are involved.

### Transaction Boundaries

| Operation | Transaction Boundary |
| --- | --- |
| Insert invoice and outbox row in the same Oracle DB | Database transaction |
| TxEventQ consume/update if JMS/binder config supports shared transactions | Oracle AI Database transaction per integration |
| Upload object to OCI Object Storage | Separate OCI API operation |
| Read secret from Vault | Separate OCI API call |
| Publish to OCI Queue/Streaming | Separate OCI broker operation |
| Call OCI Generative AI | Separate external API call |

Do not assume a single `@Transactional` on a service covers the database, Object Storage, Vault, and Generative AI. If a workflow requires multiple steps, define retries, idempotency, compensation, and partial completion states.

## 18. Environment and Profile Configuration

Separate configuration by environment:

| Environment | Suggested Authentication | Configuration |
| --- | --- | --- |
| Local developer | FILE or session token | OCI CLI profile, local config file |
| CI test | Dedicated test identity/service principal or mock | Secret injection, test compartment |
| OCI Compute | Instance Principal | Dynamic group and policy |
| OCI Functions | Resource Principal | Resource identity and policy |
| OKE | Workload Identity if supported/configured | Cluster/workload federation |
| On-premises | Approved API key or federation | Secret store, network route, region |

Do not use a local developer profile as a production credential. Do not put private keys, tokens, passwords, or Vault secrets into source control.

Example of separated profiles:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

In production, use the profile/identity suitable for the runtime and manage secrets through an approved system. Avoid storing two credential types in the same file and toggling between them with comments.

## 19. Security and Least Privilege

Each starter only needs a subset of OCI permissions:

- Storage upload requires object/bucket write permissions per the use case.
- Storage download requires object read permissions.
- Vault integration requires secret bundle read permissions or specific operations.
- Queue producers and consumers require their respective permissions.
- Streaming producers/consumers require permissions for the appropriate stream and stream pool.
- Functions invocation requires permission to invoke the function.
- Logging requires log write permissions.
- Autonomous Database lifecycle APIs may require broader resource management permissions than a JDBC user.

Separate identities per service when risks and ownership differ. An invoice API should not automatically have permission to delete buckets, create databases, and administer Vault just because they share a tenancy.

### Protecting Configuration

- Do not commit OCI config files, API private keys, or wallets.
- Do not log secrets, private keys, wallet contents, or full sensitive payloads.
- Use environment injection or secret mounts with least-privilege read access.
- Rotate credentials and verify workloads pick up the new credentials.
- Restrict Vault access and audit secret retrieval.
- Use TLS and configure network access according to policy.
- Verify region/compartment to avoid writing data to the wrong environment.

## 20. Retry, Timeout, and Idempotency

The OCI SDK and services have their own retry/timeout semantics. Using a starter does not mean every operation is automatically safe to retry.

Distinguish between:

- Transient connection errors.
- Throttling/quotas.
- Permission denied.
- Validation errors.
- Resource not found.
- Conflict/conditional write failures.
- Unknown outcome after a timeout.

### Retry Rules

- Retry transient errors according to policy.
- Respect `retry-after` or backoff if provided by the API.
- Do not retry validation/authorization errors indefinitely.
- Cap the total retry budget.
- Set connect/read/operation timeouts.
- Use idempotency keys or conditional operations for side effects.
- Reconcile state if a timeout leaves the outcome unknown.

For example, an object upload timeout does not necessarily mean the object was not written. Check the object key, ETag/version, or metadata before sending a new operation that could create another side effect.

### Queue and Stream

With Queue, consumers need idempotency and timely settlement. With Streaming, consumers need durable checkpoints/cursors and replay handling. With TxEventQ, understand the transaction and delivery behavior of the database integration. Do not apply the same retry/ack algorithm to all three.

## 21. Testing Along Project Boundaries

Test each integration independently before testing workflows spanning multiple services.

### Unit Tests

- Test business services through internal interfaces.
- Mock Storage, VaultTemplate, Queue, Streaming, or database ports.
- Verify error mapping and idempotency.
- No need to call real OCI services for pure business logic.

### Database Integration Tests

- Use an Oracle database test environment or Testcontainers with a supported image/driver.
- Test UCP and Wallet/mTLS if needed.
- Test AQ/JMS or TxEventQ with proper database privileges.
- Verify rollback/commit and message transaction boundaries.

### OCI Services Integration Tests

- Use a dedicated test compartment and resources.
- Grant least-privilege IAM policies to the test identity.
- Test Object Storage upload/download/delete.
- Test Vault reads and secret rotation.
- Test Queue delivery/ack/redelivery.
- Test Streaming cursor/checkpoint/replay.
- Clean up test resources with a clear lifecycle.

### Contract and Compatibility Tests

- Check starter/version compatibility against the project's Spring Boot version.
- Verify auto-configured beans and conditional properties.
- Check OCI SDK version resolution.
- Verify serialization/schema compatibility.
- Test 401/403, 404, throttling, and timeout errors.
- Test client and listener shutdown/close behavior.

Do not run integration tests against a production tenancy or resources containing real data.

## 22. Observability and Operations

Monitor each layer separately:

| Layer | Signals to Monitor |
| --- | --- |
| OCI authentication | Auth failures, token/key refresh, identity mode |
| IAM | 401/403, policy denials, compartment mismatches |
| Object Storage | Upload/download latency, errors, bytes, object size |
| Vault | Secret read latency, refresh status, permission errors |
| OCI Queue | Queue depth, oldest message age, delivery attempts, DLQ |
| OCI Streaming | Consumer lag, partition throughput, checkpoint age |
| TxEventQ | Queue depth, database sessions/pool, transaction failures |
| UCP | Active/available connections, wait time, acquisition timeouts |
| Spring AI Oracle | Model latency, token usage, timeouts, response errors |

Use Micrometer/Actuator and OpenTelemetry appropriate for the application. Do not assume every starter emits the exact same metrics; verify actual metrics and add instrumentation at the adapter/service layer.

Logs should include request/correlation IDs, operations, service/region, appropriate resource references, and provider request IDs when available. Do not log secrets, private keys, wallet contents, or full sensitive payloads.

## 23. Common Integration Pitfalls

### Using the Wrong Starter

Symptom: expected beans are missing or the wrong SDK is pulled in. Check the groupId/artifact, dependency tree, and correct subproject.

### Authentication Works Locally but Fails in OCI Runtime

The cause is usually misconfigured workload identity, dynamic groups, resource principals, or IAM policies. A local FILE profile does not prove production identity works.

### Identity Exists, Yet the API Returns 403

Verify the policy, verb, resource type, compartment, and scope. Do not fix it by embedding an API key of a higher-privileged user.

### Using Queue Like Streaming

Queue settlement and stream checkpoints are two different models. Choose the service based on required semantics.

### Using the TxEventQ Binder While Configuring OCI Queue

TxEventQ is Oracle AI Database native messaging; OCI Queue is a separate managed service. The TxEventQ binder needs a datasource and database permissions.

### Using the Autonomous Database Lifecycle Starter to Run Queries

A resource lifecycle starter does not replace JDBC DataSource, UCP, or Wallet. Choose the appropriate database starter for queries/transactions.

### Upgrading Spring Cloud Oracle While Manually Pinning an Old SDK Version

This can cause dependency conflicts. Read release notes, use dependency management, and inspect the resolved tree before overriding versions.

### Treating Spring Resource as a Filesystem

Object Storage does not have full filesystem semantics. Design object keys, overwrites, versioning, and concurrency around object storage behavior.

## 24. Lab Exercise: Choosing the Right Oracle Branch for Invoice Service

**Context:** Build an Invoice Service with Spring Boot. The service needs to store invoice metadata in Oracle AI Database, store PDFs in OCI Object Storage, read secrets from OCI Vault, and publish `InvoiceCreated` events to consumers.

### Part A — Requirements Analysis

1. Determine whether the database is Oracle AI Database or Autonomous Database.
2. Confirm that PDF files are stored in OCI Object Storage.
3. Choose TxEventQ or OCI Queue for events based on transaction/ownership requirements.
4. Determine whether a Spring Cloud Stream binder or JMS API is needed.
5. Identify whether the runtime is local, Compute, Functions, or OKE.

### Part B — Dependency Selection

1. Choose UCP and Wallet if the application needs JDBC connections as required.
2. Choose the Spring Cloud OCI Object Storage starter.
3. Choose the Spring Cloud OCI Vault starter.
4. Choose AQ/JMS, OKafka, or the TxEventQ binder if the backend is TxEventQ.
5. Choose the OCI Queue starter if events are sent to OCI Queue.
6. Do not add Spring AI Oracle if the application does not call Generative AI.

### Part C — Configuration and Permissions

1. Configure the region and compartment.
2. Choose runtime-appropriate authentication.
3. Create least-privilege IAM policies for database/Storage/Vault/Queue.
4. Do not store private keys or secrets in the repository.
5. Verify startup and auto-configured beans.

### Part D — Processing and Recovery

1. Write the invoice and event intent within the database transaction if using outbox.
2. Upload the PDF using an idempotent object key.
3. Record upload status and event publication.
4. Handle timeouts/unknown outcomes through reconciliation.
5. Use inbox/idempotency on the consumer side.
6. Test duplicates, retries, and partial failures.

### Deliverables

- Module/dependency diagram and transaction boundaries.
- Starter selection table with rationale.
- Auth/region/compartment configuration per environment.
- IAM policy matrix per workload.
- Sample code connecting to database, Object Storage, Vault, and messaging.
- Integration test results.
- Dashboard for latency/errors/backlog/connection pool.
- Runbook for handling 403s, throttling, timeouts, and duplicates.

### Self-Check Questions

1. Is Spring Cloud Oracle synonymous with Spring Cloud OCI?
2. How does Spring Cloud OCI differ from the OCI Java SDK?
3. Why are database starters a separate branch?
4. Is the TxEventQ binder backed by OCI Streaming?
5. When should you use AQ/JMS, OKafka, or the Spring Cloud Stream binder?
6. In what semantics does OCI Queue differ from OCI Streaming?
7. What is the Spring Cloud OCI core starter responsible for?
8. For which runtimes do Instance Principal and Resource Principal differ?
9. Why shouldn't local FILE authentication be used for production workloads?
10. How do region and compartment affect calling OCI services?
11. Is an Object Storage Spring Resource a filesystem?
12. Does Vault property refresh automatically recreate every singleton bean?
13. Does the Autonomous Database lifecycle API replace UCP/JDBC?
14. Which boundary does Spring AI Oracle belong to?
15. Why must you check Spring Boot compatibility before upgrading a starter major version?
16. Why doesn't a single `@Transactional` span the database, Object Storage, and OCI Queue?
17. What should you check when encountering a 403 even though authentication succeeded?

## 25. Key Takeaways

- Spring Cloud Oracle is a multi-module project for Oracle technologies; Spring Cloud OCI is the branch integrating OCI managed services.
- Oracle AI Database starters, the TxEventQ binder, Spring Cloud OCI, and Spring AI Oracle have distinct responsibilities.
- The OCI SDK is the underlying client layer; Spring starters provide auto-configuration and Spring-friendly APIs.
- Use the right groupId/artifact per branch; do not mix database starters with OCI service starters.
- The Spring Cloud Oracle 2.x line moves to Spring Boot 4/Spring Framework 7; check release compatibility before upgrading.
- The core starter configures OCI authentication and shared infrastructure; service starters add beans for specific services.
- Choose FILE for local development when appropriate; production should use principal/workload identities per runtime and policy.
- Region, compartment, and IAM policies all affect service calls; authentication does not mean authorization.
- OCI Queue, OCI Streaming, and TxEventQ are three distinct messaging models; choose based on delivery, ordering, transaction, and checkpoint semantics.
- Spring Cloud OCI Object Storage provides the Storage API and Spring Resource; object storage is not a filesystem.
- Vault can serve as a property source or be used via VaultTemplate; inspect secret refresh and bean lifecycles.
- Autonomous Database lifecycle integration differs from JDBC/UCP/Wallet used to query data.
- Spring AI Oracle is a separate branch for model APIs; do not confuse it with OCI Queue, Streaming, or Functions.
- Do not assume `@Transactional` spans multiple OCI services; use outbox, idempotency, sagas, and reconciliation along failure boundaries.
- Test each integration, IAM policy, version, retry, duplicate, and observability metric before deploying.

## References

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud Oracle — OCI Core and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud Oracle — OCI Object Storage](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/)
- [Spring Cloud Oracle — OCI Vault](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [Spring Cloud Oracle — OCI Streaming](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/streaming/)
- [Spring Cloud Oracle — OCI Queues](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/queues/)
- [Spring Cloud Oracle — Oracle AI Database starters](https://oracle.github.io/spring-cloud-oracle/site/docs/category/oracle-ai-database-starters/)
- [Spring Cloud Oracle — AQ/JMS](https://oracle.github.io/spring-cloud-oracle/site/docs/database/aq-jms/)
- [Spring Cloud Oracle — OKafka](https://oracle.github.io/spring-cloud-oracle/site/docs/database/okafka/)
- [Spring Cloud Oracle — TxEventQ Stream Binder getting started](https://oracle.github.io/spring-cloud-oracle/site/docs/stream-binder/getting-started/)
- [Spring Cloud Oracle — Spring AI Oracle](https://oracle.github.io/spring-cloud-oracle/site/docs/category/spring-ai-oracle/)
- [Spring Cloud Oracle — Release notes and compatibility changes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [Oracle Cloud Infrastructure Java SDK authentication](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)
