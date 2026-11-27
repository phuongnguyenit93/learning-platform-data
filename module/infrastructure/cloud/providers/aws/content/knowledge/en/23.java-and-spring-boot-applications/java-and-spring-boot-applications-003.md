# Integrating Spring Cloud AWS and Checking Compatibility Matrices

## Learning objectives

After this lesson, you will be able to:

- Explain the role of Spring Cloud AWS in a Spring Boot application and distinguish the Spring integration layer from AWS SDK for Java 2.x.
- Read and apply compatibility matrices across Spring Cloud AWS, Spring Cloud release trains, Spring Boot, Spring Framework, Java, and the AWS SDK.
- Choose the right release line (3.x or 4.x); avoid pairing Spring Cloud AWS 2.x/3.x/4.x with incompatible Spring Boot versions.
- Manage dependencies using the Spring Cloud AWS BOM, Spring Boot dependency management, and the AWS SDK BOM when an override is truly needed.
- Select service-specific starters: S3, SQS, SNS, DynamoDB, Secrets Manager, Parameter Store, SES, CloudWatch, and other available integrations.
- Understand auto-configuration for `AwsCredentialsProvider`, `AwsRegionProvider`, and AWS clients, and how to override them safely.
- Integrate S3 via `S3Client`/`S3Template`, SQS via `SqsTemplate`/`@SqsListener`, and external configuration via `spring.config.import`.
- Design least-privilege IAM permissions, use workload roles, manage endpoints/Regions, and keep real credentials out of application configuration.
- Customize synchronous/asynchronous clients, HTTP timeouts, retries, connection pools, and local-environment endpoints.
- Run integration tests using LocalStack + Testcontainers, and verify compatibility via dependency trees, builds, and startup tests.
- Migrate applications from Spring Cloud AWS 2.x to 3.x/4.x; diagnose version conflicts, auto-configuration, IAM, Region, SQS listener, and Config Data errors.

**Module context:** This lesson belongs to the **Java and Spring Boot Applications** chapter in CLOUD_PROVIDERS_AWS. The module's AWS journey spans Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless. Spring Cloud AWS lets Spring applications consume AWS services using familiar Spring idioms while relying on the AWS SDK for Java to invoke real services.

> **Scope:** Content focuses on Spring Cloud AWS 3.x/4.x and AWS SDK for Java 2.x. The matrix below reflects the release-line matrix published by the project; patch releases change over time. Always verify the current release/reference page and the POM of the exact version you plan to deploy. Never treat a newer version number as proof of compatibility with every Spring Boot version.

## 1. The problem: how many layers does a Spring app need to call AWS?

A Spring Boot service receives a document upload request, stores the file in S3, publishes an event to SQS, and reads connection details from Secrets Manager.

Using only the AWS SDK, developers must manually create clients and configure Regions, credentials providers, HTTP transport, lifecycle, and data mapping. Spring Cloud AWS adds starters and auto-configuration so these clients operate seamlessly inside the Spring `ApplicationContext`.

~~~mermaid
flowchart TB
    API[Spring MVC / WebFlux Controller] --> Service[Business services]
    Service --> S3[S3Template / S3Client]
    Service --> SQS[SqsTemplate / SqsAsyncClient]
    S3 --> AWS[(Amazon S3)]
    SQS --> QUEUE[(Amazon SQS)]
    BOOT[Spring Boot Config Data] --> SM[Secrets Manager]
    BOOT --> PS[Systems Manager Parameter Store]
    CORE[Spring Cloud AWS core] --> CRED[AwsCredentialsProvider]
    CORE --> REGION[AwsRegionProvider]
    CRED --> S3
    CRED --> SQS
    REGION --> S3
    REGION --> SQS
~~~

There are three layers to understand:

| Layer | Responsibility | Examples |
| --- | --- | --- |
| Spring Boot | Application context, dependency injection, configuration, lifecycle, health | `@SpringBootApplication`, `@ConfigurationProperties` |
| Spring Cloud AWS | Spring starters, auto-configuration, templates, listeners, config import | `S3Template`, `SqsTemplate`, `@SqsListener` |
| AWS SDK for Java 2.x | AWS API clients, SigV4 signing, credentials/Region providers, HTTP clients | `S3Client`, `SqsAsyncClient`, `StsClient` |

Spring Cloud AWS does not replace the AWS SDK. It provides the integration and auto-configuration layer; when you need an AWS service or API lacking a dedicated Spring abstraction, the application can still inject the AWS SDK client directly.

## 2. What is Spring Cloud AWS and when should you use it?

Spring Cloud AWS integrates AWS services with Spring/Spring Boot using patterns such as dependency injection, auto-configuration, configuration properties, message listeners, and Spring Config Data.

Key benefits:

- Auto-configures AWS Regions and credentials providers for AWS clients.
- Provides per-service starters so only needed dependencies enter the classpath.
- Integrates S3, SQS, SNS, DynamoDB, SES, Parameter Store, Secrets Manager, and CloudWatch.
- Offers abstractions such as `S3Template`, `SqsTemplate`, and `@SqsListener`.
- Connects AWS SDK clients to Spring lifecycle and configuration.
- Supports testing with LocalStack/Testcontainers.

### When is the AWS SDK alone enough?

Using the AWS SDK directly is a solid choice when:

- The application does not use Spring;
- Only a couple of SDK clients are needed and Spring abstractions add no value;
- You need a new API or service without a Spring Cloud AWS integration yet;
- You want full manual control over client configuration.

### When does Spring Cloud AWS help?

Spring Cloud AWS fits well when an app already uses Spring Boot and wants to:

- Auto-configure Region/credentials;
- Inject S3/SQS/DynamoDB clients;
- Use listener annotations and templates;
- Load configuration from Secrets Manager/Parameter Store;
- Integrate metrics and LocalStack following Spring conventions.

Do not force every AWS API call through a Spring Cloud AWS abstraction. You can use starters for supported services and inject AWS SDK clients directly for the rest.

## 3. Reading the compatibility matrix: do not pick versions by intuition

Spring Cloud AWS depends on core Spring projects. Each release line is tested against specific Spring Cloud, Spring Boot, and Spring Framework lines.

<text color="secondary">Release-line matrix per the Spring Cloud AWS project's compatibility table; cross-check patch versions against release notes before locking dependencies.</text>

| Spring Cloud AWS | Spring Cloud train | Spring Boot | Spring Framework | AWS SDK |
| --- | --- | --- | --- | --- |
| 2.3.x | 2020.0.x (Ilford) | 2.4.x, 2.5.x | 5.3.x | 1.x |
| 2.4.x | 2021.0.x (Jubilee) | 2.6.x, 2.7.x | 5.3.x | 1.x |
| 3.0.x | 2022.0.x (Kilburn) | 3.0.x, 3.1.x | 6.0.x | 2.x |
| 3.1.x | 2023.0.x (Kilburn) | 3.2.x | 6.1.x | 2.x |
| 3.2.x | 2023.0.x | 3.2.x, 3.3.x | 6.1.x | 2.x |
| 3.3.x | 2024.0.x | 3.4.x | 6.2.x | 2.x |
| 3.4.x | 2025.0.x | 3.5.x | 6.2.x | 2.x |
| 4.x | 2025.1.x | 4.0.x | 7.0.x | 2.x |

**How to read the table:**

- Spring Cloud AWS 2.x is tied to AWS SDK for Java 1.x and Spring Boot 2.x.
- Spring Cloud AWS 3.x moved to AWS SDK for Java 2.x, Spring Boot 3.x, and Spring Framework 6.x.
- Spring Cloud AWS 4.x belongs to the Spring Boot 4.x/Spring Framework 7.x generation while continuing on AWS SDK for Java 2.x.
- Spring Cloud AWS 3.4.x is the release line for Spring Boot 3.5.x.
- Spring Cloud AWS 4.x is the release line for Spring Boot 4.0.x in the project's published compatibility table.

**Selection examples:**

| Existing project | Release line to evaluate |
| --- | --- |
| Legacy Spring Boot 2.7.x | Spring Cloud AWS 2.4.x if SDK v1 must be maintained |
| Spring Boot 3.2.x | Spring Cloud AWS 3.1.x/3.2.x per Spring Cloud train and patch |
| Spring Boot 3.4.x | Spring Cloud AWS 3.3.x |
| Spring Boot 3.5.x | Spring Cloud AWS 3.4.x |
| Spring Boot 4.0.x | Spring Cloud AWS 4.x |

Do not pair Spring Cloud AWS 4.x with Boot 3.5.x just because both are newer major versions. Likewise, do not bump Spring Framework or Spring Cloud Commons independently outside the matrix and expect the compatibility verifier to protect the entire runtime.

## 4. Java version and build tool requirements

Modern Spring Boot 3.x and 4.x both require Java 17 or higher per their respective system requirements; specific releases may additionally support newer Java versions.

| Platform | What to verify |
| --- | --- |
| Spring Boot 3.5.x | Java 17+, Spring Framework 6.2.x |
| Spring Boot 4.0.x | Java 17+, Spring Framework 7.0.x |
| Maven | Minimum Maven version per Spring Boot release |
| Gradle | Gradle wrapper within the range supported by the Spring Boot release |
| CI JDK | Should match the JDK used for compile/test and production runtime |
| AWS SDK for Java 2.x | Check the Java baseline of the specific SDK release and dependent libraries |

A project might compile on a newer JDK while the runtime container uses an older JRE. Verify the JDK running Maven/Gradle, `maven.compiler.release` or the Gradle toolchain, the Java version inside the Docker image, and the Java version of the Lambda/ECS/EKS/EC2 runtime.

Maven compiler example:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

If choosing Java 21 or 25, also verify compatibility of Spring Boot, the AWS SDK, native-image tooling, and third-party libraries.

## 5. Selecting the right Spring Cloud AWS BOM

A **Bill of Materials (BOM)** manages the versions of Spring Cloud AWS modules and related dependencies along a release line tested by the project.

Instead of specifying versions on every starter, import the BOM and declare version-less dependencies.

Maven example for a Spring Boot 4.0.x and Spring Cloud AWS 4.2.1 project:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-aws.version>4.2.1</spring-cloud-aws.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.2.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

If your project uses Spring Boot 3.5.x, select the matching Spring Cloud AWS 3.4.x release instead of copying `4.2.1` from the example above.

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:4.2.1"))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")
}
~~~

The BOM version must match your project's Spring Boot/Spring Cloud release line.

## 6. How Spring Boot BOM, Spring Cloud BOM, and AWS SDK BOM work together

The three BOMs govern different scopes:

| BOM | Manages |
| --- | --- |
| Spring Boot dependency management | Spring Boot, Spring Framework, and many foundational dependencies |
| Spring Cloud release BOM | Spring Cloud projects if the app uses release-train modules |
| Spring Cloud AWS dependencies BOM | Spring Cloud AWS modules and dependencies tested by the project |
| AWS SDK for Java BOM | AWS SDK v2 modules such as `s3`, `sqs`, `sts`, `dynamodb` |

By default, let the Spring Cloud AWS BOM choose the AWS SDK version tested with that release.

If you need a newer AWS SDK version than the one managed by the Spring Cloud AWS BOM, Spring Cloud AWS documentation requires declaring the AWS SDK BOM before any other BOM configuring AWS SDK dependencies in `dependencyManagement`. After overriding, run compatibility tests because you have stepped outside the project's default tested dependency set.

Example structure when there is a clear reason to override:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.2.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Do not declare differing versions for `software.amazon.awssdk:s3`, `sqs`, `sts`, `auth`, and `regions`. All SDK modules should be aligned under a single BOM.

## 7. Which starter is for which AWS service?

Spring Cloud AWS offers per-integration starters. Add only starters for services the application actually uses.

| AWS integration | Maven artifact |
| --- | --- |
| Core auto-configuration | `spring-cloud-aws-starter` |
| S3 | `spring-cloud-aws-starter-s3` |
| SQS | `spring-cloud-aws-starter-sqs` |
| SNS | `spring-cloud-aws-starter-sns` |
| SES | `spring-cloud-aws-starter-ses` |
| DynamoDB | `spring-cloud-aws-starter-dynamodb` |
| Parameter Store | `spring-cloud-aws-starter-parameter-store` |
| Secrets Manager | `spring-cloud-aws-starter-secrets-manager` |
| EC2 Instance Metadata | `spring-cloud-aws-starter-imds` |
| AppConfig (supported release lines) | `spring-cloud-aws-starter-app-config` |

Additionally, newer release lines may add integrations such as AppConfig, Spring Integration adapters, Kinesis binders, and others. Check the starter list in the reference docs for your exact release.

### Starters already pull core modules

If you add `spring-cloud-aws-starter-s3`, you do not need to separately add `spring-cloud-aws-s3` just for the basic API. The starter already declares the required module and dependencies.

Do not add every starter to every application. Each starter can activate corresponding auto-configuration, clients, background listeners/pollers, or Config Data imports.

## 8. Package names and major changes across 2.x, 3.x, and 4.x

| Generation | AWS SDK | Spring Cloud AWS package | Spring Boot |
| --- | --- | --- | --- |
| 2.x | AWS SDK v1 | `org.springframework.cloud.aws...` | 2.x |
| 3.x | AWS SDK v2 | `io.awspring.cloud...` | 3.x |
| 4.x | AWS SDK v2 | `io.awspring.cloud...` | 4.x |

Key changes when upgrading from 2.x to 3.x:

- Transitioned from AWS SDK v1 to v2; clients and request/response models changed packages/APIs.
- Legacy configuration namespace `cloud.aws.*` moved to `spring.cloud.aws.*` for corresponding properties.
- Spring Boot 3 uses Jakarta APIs; libraries still depending on `javax.*` can break.
- Parameter Store/Secrets Manager use Config Data imports (`spring.config.import`) instead of the legacy prefix resolution mechanism.
- SQS message collection conversion and acknowledgment behavior changed.
- Some legacy Cognito/RDS/EC2/ElastiCache/CloudFormation integrations were removed in Spring Cloud AWS 3.x/4.x; use the AWS SDK or appropriate Spring projects instead.

Spring Cloud AWS 4.x builds on Spring Boot 4 and Spring Framework 7. When upgrading from 3.x to 4.x, check the Spring Boot 4 migration guide, Jackson version, Jakarta APIs, auto-configuration conditions, and starter changes.

## 9. Auto-configuration: which beans does Spring Cloud AWS create?

When a starter is on the classpath, Spring Cloud AWS auto-configures core AWS components and the corresponding clients.

Core components:

- `AwsCredentialsProvider`: supplies credentials to sign AWS requests.
- `AwsRegionProvider`: supplies the Region for AWS clients.
- AWS SDK service clients: `S3Client`, `SqsAsyncClient`, `SnsClient`, `DynamoDbClient`, etc.
- Spring abstractions: `S3Template`, `SqsTemplate`, listener containers, and configuration property sources.

~~~mermaid
flowchart TD
    CP[Spring Boot Environment] --> AC[Spring Cloud AWS Auto Configuration]
    AC --> Cred[DefaultCredentialsProvider]
    AC --> Reg[DefaultAwsRegionProviderChain]
    AC --> S3C[S3Client]
    AC --> SQSC[SqsAsyncClient]
    AC --> DDB[DynamoDbClient]
    Cred --> S3C
    Cred --> SQSC
    Cred --> DDB
    Reg --> S3C
    Reg --> SQSC
    Reg --> DDB
    S3C --> S3T[S3Template]
    SQSC --> SQT[SqsTemplate / Listener containers]
~~~

If you provide a custom `AwsCredentialsProvider` bean or `AwsRegionProvider` bean, the corresponding default auto-configuration may back off. Only override when explicitly required, and ensure your custom provider handles refresh/lifecycle properly.

## 10. Credentials provider: using the runtime identity

Spring Cloud AWS defaults to the AWS SDK `DefaultCredentialsProvider` chain. Primary sources checked in order:

1. Java system properties;
2. Environment variables;
3. Web identity token;
4. Shared AWS profiles;
5. ECS/container credentials;
6. EC2 Instance Metadata Service (IMDS).

| Environment | Recommended credentials |
| --- | --- |
| Developer laptop | IAM Identity Center SSO profile / AWS profile |
| EC2 | Instance profile / IAM role |
| ECS | ECS task role |
| EKS | Pod Identity or IRSA/web identity |
| CI/CD | OIDC federation or runner-assumed role |
| Cross-account | Source workload role + STS `AssumeRole` |

Do not put static access keys/secrets in `application.yml` or Docker images. Properties `spring.cloud.aws.credentials.access-key` and `secret-key` exist for special/test cases, not for long-lived production credentials.

### Local profile

You can log in with SSO using the AWS CLI and select the profile via environment:

~~~bash
aws sso login --profile dev-sso

# Linux/macOS
export AWS_PROFILE=dev-sso

# Windows PowerShell
$env:AWS_PROFILE = "dev-sso"
~~~

If environment variables contain stale credentials, they can take precedence over the profile. Verify identity with `aws sts get-caller-identity --profile dev-sso` and inspect `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`.

### Web identity on EKS

Spring Cloud AWS supports `StsWebIdentityTokenFileCredentialsProvider` for Kubernetes/EKS environments. The starter can use the token file and role ARN supplied by the environment; when explicit configuration is needed, properties include:

~~~yaml
spring:
  cloud:
    aws:
      credentials:
        sts:
          role-arn: arn:aws:iam::111122223333:role/orders-api
          async-credentials-update: true
~~~

Only declare `role-arn` when overriding the value supplied by the EKS Pod Identity/IRSA setup. The role's trust policy must trust the exact OIDC provider/service account or corresponding identity provider.

## 11. Region provider: do not confuse Identity Center Region with service Region

Spring Cloud AWS uses `DefaultAwsRegionProviderChain` to determine the Region. Common sources:

1. Java system property `aws.region`;
2. Environment variable `AWS_REGION`;
3. Shared AWS profile configuration;
4. EC2 metadata.

You can explicitly set the Region in `application.yml`:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Region is a setting for service clients. If the app calls S3 in Singapore while the IAM Identity Center SSO instance resides in another Region, the SSO Region does not replace the S3 Region.

### Multi-Region applications

If a service must call AWS services across multiple Regions, the auto-configured default Region may not suffice. Create dedicated clients per Region:

~~~java
@Configuration
class AwsClientConfiguration {

    @Bean
    S3Client singaporeS3(AwsCredentialsProvider credentialsProvider) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .credentialsProvider(credentialsProvider)
            .build();
    }

    @Bean
    S3Client tokyoS3(AwsCredentialsProvider credentialsProvider) {
        return S3Client.builder()
            .region(Region.AP_NORTHEAST_1)
            .credentialsProvider(credentialsProvider)
            .build();
    }
}
~~~

Both clients share the same provider if the principal/permissions allow access to both Regions. Manage bean names/qualifiers clearly so the wrong client is never accidentally injected.

## 12. Basic application configuration with application.yml

A common configuration:

~~~yaml
spring:
  application:
    name: orders-api
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: orders-documents
    prefix: orders/
~~~

Separate configuration by profile:

- `application-local.yml`: Region, LocalStack endpoint, or developer profile;
- `application-test.yml`: Testcontainers connection;
- `application-prod.yml`: production Region, no credentials;
- runtime role/identity supplied by EC2/ECS/EKS/CI.

Do not commit account-specific secret values or sensitive private endpoints. Even values that can safely appear in config still require change control through the deployment pipeline.

## 13. S3 integration: using S3Client when the full API is needed

When `spring-cloud-aws-starter-s3` is present, Spring Cloud AWS auto-configures the AWS SDK S3 client. You can inject `S3Client` and invoke the SDK API directly:

~~~java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class DocumentService {

    private final S3Client s3;

    public DocumentService(S3Client s3) {
        this.s3 = s3;
    }

    public void createBucket(String bucketName) {
        s3.createBucket(b -> b.bucket(bucketName));
    }

    public void upload(String bucket, String key, RequestBody body) {
        s3.putObject(
            PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build(),
            body
        );
    }
}
~~~

This snippet only illustrates client injection and API invocation; production code must address bucket ownership, bucket policies, encryption, versioning, object keys, content types, streaming, and retries.

Never instantiate an AWS SDK client per HTTP request. Clients are shared resources and thread-safe per the SDK contract; let Spring manage their lifecycle.

## 14. S3Template: Spring-style abstraction

`S3Template` provides common operations such as uploading/downloading objects, reading/writing Java objects, and generating signed URLs.

Example upload service:

~~~java
import io.awspring.cloud.s3.S3Template;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class DocumentStorage {

    private final S3Template s3Template;

    public DocumentStorage(S3Template s3Template) {
        this.s3Template = s3Template;
    }

    public void upload(String bucket, String key, InputStream content) {
        s3Template.upload(bucket, key, content);
    }
}
~~~

Common use cases:

- Storing user-uploaded files;
- Reading objects back as Spring `Resource`s;
- Persisting Java objects as JSON;
- Generating short-lived presigned GET/PUT URLs.

### Choosing S3Template vs. S3Client

| Requirement | Choice |
| --- | --- |
| Common upload/download | `S3Template` |
| Full control over AWS APIs | `S3Client` |
| Large transfers, multipart/parallel transfer | `S3TransferManager`/CRT when needed |
| Presigned URLs | `S3Template` or SDK presigner |
| Newer S3 APIs without Spring helpers | Direct AWS SDK |

A signed URL is a bearer capability: anyone holding the URL while it remains valid can exercise the permissions it represents. Never log full URLs or set overly long expirations.

## 15. S3 configuration, IAM, and streaming

The application needs permissions matching its actual operations:

| Use case | Typical IAM actions required |
| --- | --- |
| List objects | `s3:ListBucket` on bucket ARN |
| Download | `s3:GetObject` on object ARN |
| Upload | `s3:PutObject` on object ARN |
| Delete | `s3:DeleteObject` on object ARN |
| SSE-KMS | Add required KMS permissions, e.g., `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` per operation |

Bucket-level actions and object-level actions use different ARNs. With KMS encryption, the principal's IAM policy, key policy, and grants all affect authorization outcomes.

### Large file uploads

- Use streams to avoid loading the entire file into the heap;
- Consider multipart/transfer manager;
- Bound concurrency and memory buffers;
- Configure network timeouts and retries;
- Ensure multipart upload cleanup;
- Avoid allocating large byte arrays for every file.

### Object keys

Never trust client-supplied filenames directly. Normalize keys, prevent path traversal in application logic, isolate tenant prefixes, and avoid storing PII in object keys unnecessarily.

## 16. SQS integration: @SqsListener and message listener containers

Spring Cloud AWS supports SQS via `@SqsListener`, `MessageListenerContainer`, `SqsTemplate`, and acknowledgment handling.

Example listener:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @SqsListener("orders-events")
    public void onOrderCreated(OrderCreated event) {
        // Validate event, process idempotently, persist business result.
    }
}
~~~

Spring Boot auto-configuration creates the listener container and message adapter for the annotated method. SQS message payloads are strings at the service boundary; Spring Cloud AWS provides message converters to serialize/deserialize objects.

### Sending messages with SqsTemplate

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final SqsTemplate sqsTemplate;

    public OrderEventPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }

    public void publish(OrderCreated event) {
        sqsTemplate.send("orders-events", event);
    }
}
~~~

With Spring Boot auto-configuration, `SqsTemplate` can be injected unless another template bean already exists in the application context. The template is immutable and thread-safe.

## 17. SQS delivery semantics: duplicates, visibility timeout, and DLQ

SQS Standard queues provide **at-least-once delivery**. A message may be delivered multiple times, so listeners must be idempotent.

A safe consumer should:

1. Validate message/schema/version;
2. Check idempotency key/event ID;
3. Persist business state within a transaction;
4. Acknowledge only after successful processing per the acknowledgment mode;
5. Retry transient errors with backoff;
6. Route poison messages to a DLQ via redrive policy;
7. Monitor queue depth, age of oldest message, and DLQ count.

Visibility timeout must exceed expected processing duration or be properly extended. If processing outlasts the visibility timeout, the message can be redelivered to another consumer while the first consumer is still running.

### Standard vs. FIFO

| Property | Standard | FIFO |
| --- | --- | --- |
| Ordering | Best-effort | Per message group |
| Duplicate delivery | Possible | Deduplication window exists, still design idempotently |
| Throughput | Suitable for high throughput | Subject to message group/deduplication constraints |
| Use case | Event processing, background jobs | Workflows requiring ordering per entity/group |

Do not treat a FIFO queue as a database transaction. Business side effects still require idempotency and transactional design.

## 18. SQS concurrency, acknowledgment, and error handling

The SQS listener container polls messages asynchronously. Increasing `maxConcurrentMessages` can boost throughput, but also increases DB connection usage, API concurrency, memory/CPU, downstream throttling risk, and the number of in-flight invisible messages.

Tune concurrency to downstream capacity, not just queue backlog.

### Acknowledgment

Spring Cloud AWS offers acknowledgment modes and batching behaviors. Choose the mode based on semantics:

- Acknowledge upon successful processing;
- Manual acknowledgment when tied to business transaction decisions;
- Batch acknowledgment when handlers process batches with per-message outcomes.

Never acknowledge before durable side effects commit. If the handler writes to the DB and message acknowledgment fails, redelivery must remain idempotent.

### Retries and DLQ

Distinguish transient errors (timeouts, throttling), data errors (invalid schemas), permission/configuration errors, and poison messages. Use bounded retries with backoff; permission errors require fixing IAM/Region/queue config rather than retrying indefinitely.

`maxReceiveCount` in the redrive policy must align with the retry window and visibility timeout.

## 19. SNS, SQS, and the fan-out pattern

SNS can fan out a single event to multiple SQS queues so each bounded context processes independently.

~~~mermaid
flowchart LR
    Order[Order service] --> SNS[(SNS topic)]
    SNS --> Q1[(Billing queue)]
    SNS --> Q2[(Shipping queue)]
    SNS --> Q3[(Analytics queue)]
    Q1 --> B[Billing consumer]
    Q2 --> S[Shipping consumer]
    Q3 --> A[Analytics consumer]
~~~

Spring Cloud AWS provides `SnsClient`/`SnsTemplate` and SQS listener integrations. When SNS publishes to SQS:

- The queue policy must allow the SNS topic to send messages;
- The subscription must match the right Region/account;
- Filter policies must match message attributes;
- Consumers still require idempotency;
- Dead-letter strategies can be placed on the subscription/queue per architecture.

Do not rely on SNS notifications as a guarantee of atomic commit alongside a database transaction. If an outbox is needed, the transaction boundary belongs inside the application/database.

## 20. Secrets Manager: loading secrets with Spring Config Data

Spring Cloud AWS integrates with Secrets Manager via `spring.config.import`.

Example secret `/secrets/orders-db` containing JSON:

~~~json
{
  "username": "orders_app",
  "password": "REDACTED"
}
~~~

Configuration:

~~~yaml
spring:
  config:
    import: aws-secretsmanager:/secrets/orders-db?prefix=spring.datasource.
~~~

Top-level keys of the JSON secret are added to the Spring Environment with the specified prefix. They can be bound with `@ConfigurationProperties` or injected with `@Value`.

If a mandatory secret is missing or unreadable, application startup should fail to avoid running with incomplete config. If a secret is truly optional, use `optional:aws-secretsmanager:` deliberately.

### Plain-text secrets

If a secret is plain text, import it by secret name and map the value to the appropriate property. For multiple secrets, separate them using the syntax documented in your version's reference docs.

### Prefixing to avoid property collisions

If JSON contains generic keys like `username` and `password`, use `?prefix=db.` or an appropriate prefix to avoid overwriting other properties.

Never print secret values in logs, Actuator `env` endpoints, startup banners, or exception messages. Restrict access to `/actuator/env` and any endpoints that can expose configuration.

## 21. Secret rotation and configuration reload

Secrets Manager supports rotation, yet rotation on AWS does not automatically guarantee that every object inside the JVM now uses the new credential.

Spring Cloud AWS offers configurable property source reloading. Distinguish between:

- Reloading the property source;
- Refreshing `@ConfigurationProperties`/`@RefreshScope` beans;
- Replacing an already constructed connection pool or client;
- Existing DB connections still open with old credentials.

When a database password rotates, an end-to-end strategy is needed so the `DataSource`/connection pool opens new connections with the new credentials and retires old connections. Do not assume that seeing the updated value in the AWS console means HikariCP automatically updates.

Reloading can use a `refresh` or `restart_context` strategy depending on the integration. Reload features require additional dependencies/configuration and must be tested across the application lifecycle.

## 22. Systems Manager Parameter Store: path-based configuration

Parameter Store fits key/value configuration, feature flags, endpoints, and non-secret parameters. Use `SecureString` for data requiring encryption, and manage KMS permissions per key.

Example parameters:

~~~text
/config/orders-api/payment-url = https://payments.example.internal
/config/orders-api/max-retries = 3
/config/orders-api/feature/new-checkout = true
~~~

Import path:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/orders-api/
~~~

Parameters under the path are loaded into the Spring Environment. A prefix can map them into a specific namespace:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/database/?prefix=spring.datasource.
~~~

Common IAM permission for path-based lookup is `ssm:GetParametersByPath`. When reading a `SecureString` encrypted with a customer-managed KMS key, the principal may also need `kms:Decrypt` and the key policy must allow it.

### Secrets Manager vs. Parameter Store?

| Need | Consider |
| --- | --- |
| Passwords, API tokens, database secrets, and rotation | Secrets Manager |
| App config, endpoints, feature flags, non-secret values | Parameter Store |
| Hierarchical path-based config | Parameter Store |
| Secret lifecycle/rotation integration | Secrets Manager |
| Pricing and quotas | Check each service's pricing/limits |

Do not store plaintext secrets in Parameter Store Standard just because importing is convenient.

## 23. CloudWatch metrics and observability

Spring Cloud AWS can integrate the Micrometer CloudWatch registry. Dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-cloudwatch2</artifactId>
</dependency>
~~~

Configure namespace and export interval:

~~~yaml
management:
  cloudwatch:
    metrics:
      export:
        namespace: OrdersApi
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
~~~

Corresponding CloudWatch permissions are needed, typically including `cloudwatch:PutMetricData`. Do not enable the CloudWatch metrics exporter on every local profile unnecessarily.

### Monitoring the application and AWS integrations

| Metric/Signal | Meaning |
| --- | --- |
| HTTP request rate, error rate, p95/p99 | API user experience |
| SQS queue depth/age | Backlog and consumer lag |
| Listener failures/DLQ count | Message processing health |
| S3 request failures/latency | Upload/download health |
| AWS SDK retry count | Throttling/network instability |
| Secrets/Parameter import failures | Application config readiness |
| JVM heap/thread/connection pool | Resource saturation |
| CloudWatch service metrics | AWS-side behavior |

Propagate correlation IDs and event IDs across API → SQS → consumer; avoid placing secrets, sensitive payloads, or PII into metric dimensions.

## 24. Customizing AWS clients: timeouts, HTTP transport, and retries

Spring Cloud AWS supports customizers for synchronous and asynchronous AWS client groups.

| Client type | Example integrations |
| --- | --- |
| Synchronous | DynamoDB, SES, SNS, Parameter Store, Secrets Manager, S3 |
| Asynchronous | SQS, CloudWatch |

You can configure `AwsSyncClientCustomizer` or `AwsAsyncClientCustomizer`, or per-client customizers.

Synchronous customizer example:

~~~java
import io.awspring.cloud.autoconfigure.AwsSyncClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
class AwsHttpConfiguration {

    @Bean
    AwsSyncClientCustomizer syncClientCustomizer() {
        return builder -> builder.overrideConfiguration(config ->
            config.apiCallTimeout(Duration.ofSeconds(20))
        );
    }
}
~~~

This example sets the overall API call timeout; also evaluate per-attempt timeouts, retry strategies, connection acquisition timeouts, and HTTP client pooling under realistic load.

### Retries do not replace business idempotency

The AWS SDK includes a retry strategy for retryable errors. However, a POST may commit on the server and then time out on the response. If the caller retries without business idempotency, the application can create duplicate orders/payments.

For SQS consumers, use event IDs/unique constraints/outbox or an idempotency store. For APIs, enforce an idempotency key per contract.

## 25. Endpoints and LocalStack: isolating test endpoints from production

Spring Cloud AWS supports configuring an endpoint for auto-configured clients:

~~~yaml
spring:
  cloud:
    aws:
      endpoint: http://localhost:4566
      region:
        static: ap-southeast-1
~~~

This endpoint suits AWS-compatible/local test environments. Never include LocalStack endpoints in production profiles, and never use fake credentials against real AWS.

In tests, you can use `spring-cloud-aws-testcontainers` and `@ServiceConnection` with `LocalStackContainer` so Spring Cloud AWS automatically wires Region/credentials to the container.

### LocalStack and cost/tooling

Following LocalStack changes in 2026, the `localstack:latest` community image may require `LOCALSTACK_AUTH_TOKEN`. Pin an appropriate version or configure the token per current terms. Tests should fail explicitly if the container fails to start rather than silently falling back to real AWS.

## 26. Integration testing with Testcontainers

Example test setup using Spring Boot service connections:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class LocalAwsTestConfiguration {

    @Bean
    @ServiceConnection
    LocalStackContainer localStackContainer() {
        return new LocalStackContainer(
            DockerImageName.parse("localstack/localstack:4.12.0")
        );
    }
}
~~~

Requires Testcontainers LocalStack and `spring-cloud-aws-testcontainers` dependencies managed by the BOM. For newer LocalStack versions requiring an auth token, configure the container environment appropriately; the version in the example is merely an illustrative pin from documentation—select a currently supported version.

### What to test

- Application context starts with the intended release line;
- AWS clients are created with the expected Region/credentials;
- S3 upload/download and object keys;
- SQS send/listener/acknowledgment;
- DLQ/redrive behavior;
- Secrets Manager/Parameter Store config imports;
- IAM `AccessDenied` paths if the integration environment allows;
- Consumer retries/idempotency.

LocalStack cannot replace contract tests against real AWS for every feature. Certain IAM, KMS, event delivery, consistency, or service limits behave differently from AWS.

## 27. Compatibility verifier and dependency diagnostics

Spring Cloud includes a compatibility verifier to catch certain Spring Boot versions that are incompatible with the release train. It is a helpful guardrail, though not a substitute for thorough verification:

- It does not prove every transitive dependency is compatible;
- It does not catch every binary/API conflict;
- It does not verify AWS account/Region/IAM permissions;
- It does not replace integration testing.

When startup reports a compatibility error, read the accepted versions and upgrade/downgrade to the matching release train. Do not disable the verifier just to make the app boot without investigating the root cause.

### Maven diagnostics

~~~bash
mvn -q help:effective-pom

mvn dependency:tree \
  -Dincludes=io.awspring.cloud,org.springframework.boot,org.springframework,org.springframework.cloud,software.amazon.awssdk
~~~

### Gradle diagnostics

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-aws \
  --configuration runtimeClasspath
~~~

Look for warning signs:

- Two different versions of `software.amazon.awssdk` modules;
- Both Spring Framework 6.x and 7.x on the runtime classpath;
- Spring Cloud AWS 4.x paired with Boot 3.x;
- Spring Cloud AWS 3.x paired with Spring Framework 7.x;
- A starter version overridden by a different direct module version;
- AWS SDK v1 and v2 coexisting due to legacy dependencies.

## 28. Migrating from Spring Cloud AWS 2.x to 3.x

Migrating 2.x → 3.x is a major change:

| Area | 2.x | 3.x |
| --- | --- | --- |
| AWS SDK | v1 | v2 |
| Spring Boot | 2.x | 3.x |
| Spring Framework | 5.x | 6.x |
| Java namespace | `javax.*` common | Jakarta `jakarta.*` |
| Spring Cloud AWS package | `org.springframework.cloud.aws` | `io.awspring.cloud` |
| Property namespace | Several `cloud.aws.*` / `aws.*` | `spring.cloud.aws.*` |
| Config import | Legacy mechanism | Spring Boot Config Data |

### Sample property migrations

| Old property | New property |
| --- | --- |
| `cloud.aws.credentials.access-key` | `spring.cloud.aws.credentials.access-key` |
| `cloud.aws.credentials.secret-key` | `spring.cloud.aws.credentials.secret-key` |
| `cloud.aws.region.static` | `spring.cloud.aws.region.static` |
| `aws.paramstore.region` | `spring.cloud.aws.parameterstore.region` |
| `aws.secretsmanager.region` | `spring.cloud.aws.secretsmanager.region` |
| `management.metrics.export.cloudwatch.*` | `management.cloudwatch.metrics.export.*` |

Parameter Store 3.x uses `spring.config.import=aws-parameterstore:/path/` instead of assembling prefixes/default context/name under the 2.x mechanism.

### Safe migration process

1. Inventory all legacy Spring Cloud AWS dependencies and properties.
2. Select the target Spring Boot/Spring Cloud release train.
3. Replace AWS SDK v1 clients/models with SDK v2 APIs.
4. Update package imports and Jakarta dependencies.
5. Migrate Parameter Store/Secrets Manager config loading to Config Data imports.
6. Migrate SQS listeners/templates and verify payload conversion/acknowledgment.
7. Run `dependency:tree` to uncover version conflicts.
8. Run unit/integration tests against LocalStack.
9. Test in an AWS non-production account with least-privilege IAM.
10. Canary deploy and monitor errors/latency/DLQ before full rollout.

## 29. Migrating from 3.x to 4.x

Spring Cloud AWS 4.x targets Spring Boot 4.x/Spring Framework 7.x per the compatibility matrix. Boot 3.5.x apps should remain on the 3.4.x release line unless planning a Boot 4 upgrade.

During migration:

- Upgrade Spring Boot first or together with a tested dependency set;
- Verify the matching Spring Cloud train;
- Upgrade the Spring Cloud AWS BOM to 4.x;
- Review Spring Boot 4 migration notes and Jackson version;
- Inspect auto-configuration/classpath condition changes;
- Build all modules, not only the module containing AWS starters;
- Test Config Data imports, SQS message conversion, and service connections.

Do not upgrade only the Spring Cloud AWS BOM to 4.x inside a Boot 3.5.x project. The compatibility table must be respected across Boot/Cloud/Framework/AWSpring.

## 30. Which services lack Spring Cloud AWS integrations?

Not every AWS service has a Spring Cloud AWS starter/abstraction. The compatibility matrix also notes some integrations present in 2.x that were dropped in 3.x/4.x.

| AWS service | Approach |
| --- | --- |
| RDS/Aurora | Spring Boot DataSource/JDBC/JPA + driver; AWS SDK/Secrets Manager/IAM auth as needed |
| EC2 control plane | AWS SDK EC2 client |
| ElastiCache | Redis client/Spring Data Redis; AWS networking/auth per engine |
| CloudFormation | AWS SDK CloudFormation client or IaC pipeline |
| API Gateway | AWS SDK/API Gateway or Spring Web endpoints behind it |
| Lambda | AWS SDK Lambda client, Spring Cloud Function/AWS adapter per architecture |
| Kinesis | Spring Cloud AWS Kinesis binder/integration when supported by the release line, or SDK |
| AppConfig | AppConfig starter on supported release lines; check matrix |

Do not confuse “no Spring Cloud AWS starter” with “cannot use the AWS service in Spring.” You can inject AWS SDK clients via custom configuration.

## 31. IAM, KMS, and networking for Spring Cloud AWS

An application can boot cleanly yet still receive `AccessDenied` when calling a service. Auto-configuration does not grant IAM permissions.

Design permissions per feature:

| Integration | Typical IAM actions |
| --- | --- |
| S3 read | `s3:GetObject`, `s3:ListBucket` |
| S3 write | `s3:PutObject` |
| SQS consumer | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` |
| SQS publisher | `sqs:SendMessage` |
| SNS publisher | `sns:Publish` |
| Secrets Manager | `secretsmanager:GetSecretValue`, `secretsmanager:DescribeSecret` |
| Parameter Store | `ssm:GetParametersByPath`/`ssm:GetParameter` depending on query style |
| CloudWatch metrics | `cloudwatch:PutMetricData` |
| KMS-encrypted resources | `kms:Decrypt`/`kms:Encrypt`/`kms:GenerateDataKey` per operation |

Actual permissions must be scoped to resource ARNs, prefixes, queue/topic ARNs, and key ARNs. Some actions require `Resource *`; consult the IAM Service Authorization Reference.

### Network

Applications in private subnets require routes/DNS/egress to service endpoints or appropriate VPC endpoints—such as S3 gateway endpoints, SQS interface endpoints, Secrets Manager interface endpoints, Systems Manager interface endpoints, STS endpoints, and CloudWatch monitoring endpoints.

Check Security Groups, endpoint policies, DNS private hosted zones, and TLS. Valid credentials cannot push a request across a blocked network path.

## 32. Troubleshooting: common errors and how to isolate them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for `S3Client` | Missing S3 starter, auto-config excluded, or custom bean conflict | Check starter, classpath, and conditions |
| No region provided | Missing region property/env/profile/metadata | Set `spring.cloud.aws.region.static` or `AWS_REGION` |
| Unable to load credentials | No credentials provider succeeded | Verify `AWS_PROFILE`, SSO login, workload role/IMDS |
| `ExpiredToken` | Static/temporary credentials expired or source identity stopped refreshing | Use provider chain/role; avoid static credentials |
| S3 `AccessDenied` | IAM, bucket policy, KMS key policy, or SCP deny | Check action, resource ARN, encryption, and identity ARN |
| SQS listener receives no messages | Wrong queue/Region, missing `ReceiveMessage`, listener container failed to start | Check queue URL/name, IAM, startup logs, and CloudWatch |
| Messages processed multiple times | At-least-once delivery, ack failure, visibility timeout | Idempotency, visibility, acknowledgment, and DLQ |
| App fails at startup importing secret | Secret/path missing or IAM/network/KMS deny | Check secret ARN, role, and optional/required semantics |
| Secret changed yet DB pool uses old password | Config refresh does not update existing connection pool | Design pool refresh/reconnect and test rotation |
| `SdkClientException` timeout | DNS, VPC endpoint, proxy, SG/NACL, or HTTP timeout | Check network path and client timeouts |
| `NoSuchMethodError`/`ClassNotFoundException` | Conflicting SDK/Spring versions | `dependency:tree`, BOM, clean rebuild |
| Compatibility verifier fails | Incompatible Spring Boot/Cloud release train | Align with matrix; do not blindly disable verifier |
| SQS payload conversion error | Jackson/message type header/version mismatch | Check converter, payload schema, and type mapping |
| LocalStack test hits real AWS | Endpoint/`ServiceConnection` not applied | Check test profile, endpoint, and dummy credentials |
| Startup fails on config import | Missing starter for import scheme, required resource missing | Add starter, fix URI, or mark `optional:` when valid |

### Investigation sequence

~~~text
1. Confirm Spring Boot, Spring Cloud train, Spring Cloud AWS, and Java versions.
2. Inspect effective POM/dependency tree for version conflicts.
3. Check auto-configuration conditions and startup logs.
4. Verify Region and endpoint.
5. Verify identity with STS GetCallerIdentity.
6. Check IAM identity/resource policies, KMS, and SCPs.
7. Check VPC endpoints, DNS, TLS, and timeouts.
8. For SQS: inspect queue attributes, listener container, visibility, and DLQ.
9. For Config Data: inspect import URI, resource existence, and IAM.
10. Re-run integration tests before canary deployment.
~~~

Do not enable debug logs that capture request `Authorization` headers, secret values, or the full configuration environment.

## 33. Hands-on exercises and self-check questions

### Exercise 1 — Choosing from the compatibility matrix

A project uses Spring Boot 3.5.x, Spring Framework 6.2.x, and AWS SDK v2. A developer plans to add Spring Cloud AWS 4.x because it is a newer major version.

**Task:** Choose the appropriate release line per the compatibility table; explain why Boot 3.5.x belongs with Spring Cloud AWS 3.4.x and why 4.x targets Boot 4.0.x.

### Exercise 2 — Managing the BOM

A Maven project declares `spring-cloud-aws-starter-s3:3.4.x`, `spring-cloud-aws-sqs:3.3.x`, and `software.amazon.awssdk:s3:2.x` individually.

**Task:** Rewrite `dependencyManagement` using the Spring Cloud AWS BOM, version-less starters, and describe when an AWS SDK BOM override is actually justified.

### Exercise 3 — Local SSO profile

A Spring Boot app running locally ran `aws sso login --profile dev-sso`, yet Java picks up credentials from an old account.

**Task:** Explain provider chain precedence, check `AWS_ACCESS_KEY_ID`/`AWS_SESSION_TOKEN`, set `AWS_PROFILE`, and verify with STS.

### Exercise 4 — ECS production

A service on ECS Fargate has access key/secret credentials in `application.yml`.

**Task:** Migrate to an ECS task role, design least-privilege S3/SQS IAM permissions, and explain why the task execution role differs from the task role.

### Exercise 5 — S3 upload

Write a Spring service injecting `S3Template` to upload files; then describe when `S3Client` or `S3TransferManager` is needed. List IAM actions and how to protect object keys.

### Exercise 6 — SQS consumer

An `@SqsListener` processes payment events, writes to the database, and occasionally sees messages reappear.

**Task:** Explain at-least-once delivery, design an idempotency key, transaction boundary, acknowledgment, visibility timeout, and DLQ.

### Exercise 7 — Secrets Manager

A JSON database secret has keys `username`/`password`. Spring Boot needs to load the secret into `spring.datasource.*` and refuse to start if the mandatory secret is missing.

**Task:** Write `spring.config.import` with a prefix; describe IAM `secretsmanager:GetSecretValue`, KMS Decrypt, and why Actuator `env` must not be exposed.

### Exercise 8 — LocalStack Testcontainers

An integration test accidentally writes objects to a real AWS bucket instead of LocalStack.

**Task:** Configure `@ServiceConnection` with `LocalStackContainer`, verify test endpoints/Region/credentials, pin the image, and prevent fallback to real AWS.

### Short questions

1. **Does Spring Cloud AWS replace the AWS SDK?** No; it adds Spring abstractions/auto-configuration on top of the AWS SDK.
2. **Does Spring Cloud AWS 3.x use AWS SDK v1 or v2?** AWS SDK v2.
3. **Which Spring Boot release line is Spring Cloud AWS 4.x compatible with per the matrix?** Spring Boot 4.0.x.
4. **Which Boot line pairs with Spring Cloud AWS 3.4.x?** Spring Boot 3.5.x.
5. **What is the benefit of a BOM?** Keeps modules on the same release line and tested dependency versions.
6. **Should you specify separate versions per AWS SDK module?** No; use a single SDK BOM when an override is needed.
7. **What is the S3 starter artifact?** `spring-cloud-aws-starter-s3`.
8. **What is the SQS listener annotation?** `@SqsListener`.
9. **What is S3Template used for?** Upload/download, object mapping, and signed URLs for common use cases.
10. **Which sources does the Spring Cloud AWS default credentials provider check?** Java properties, environment, web identity, profile, container, EC2 metadata.
11. **What is the static Region property?** `spring.cloud.aws.region.static`.
12. **What is the Secrets Manager Config Data scheme?** `aws-secretsmanager:`.
13. **What is the Parameter Store Config Data scheme?** `aws-parameterstore:`.
14. **What does an optional import do?** Allows the app to keep starting if the external resource does not exist, when the resource is genuinely optional.
15. **Can an SQS Standard queue deliver duplicates?** Yes; consumers must be idempotent.
16. **Can LocalStack tests fully replace AWS integration tests?** No; some behaviors must be verified in non-production AWS.
17. **Does the compatibility verifier prove runtime AWS permissions are valid?** No; it checks part of framework compatibility.
18. **Should you disable the compatibility verifier to bypass version errors?** No, unless there is a thoroughly evaluated and tested reason.

## 34. Pre-production checklist

- [ ] Spring Cloud AWS release line matches Spring Boot, Spring Cloud train, and Spring Framework.
- [ ] Java version, Maven/Gradle wrapper, and runtime container are verified.
- [ ] Correct Spring Cloud AWS BOM selected; starters do not declare individual patch versions.
- [ ] AWS SDK module versions are aligned; AWS SDK BOM overridden only with clear justification.
- [ ] Spring Cloud AWS 2.x/3.x/4.x APIs and package namespaces are not mixed.
- [ ] Credentials come from local SSO profiles or workload identity/runtime roles.
- [ ] No access keys/secrets/session tokens stored in Git, Docker images, or `application.yml`.
- [ ] Region is explicitly configured; SSO Region is not confused with service Region.
- [ ] S3 bucket/object permissions, KMS policies, and object key rules are verified.
- [ ] SQS queue policies, listener concurrency, visibility timeouts, acknowledgments, and DLQs are designed.
- [ ] Consumers enforce proper idempotency and transaction boundaries.
- [ ] Secrets Manager/Parameter Store imports have clear required/optional semantics.
- [ ] Secret reload/rotation is tested end-to-end against actual connection pools or clients.
- [ ] IAM policies grant only necessary actions/resources.
- [ ] VPC endpoints, DNS, Security Groups, TLS, and timeouts are tested.
- [ ] CloudWatch/Micrometer namespaces and metrics contain no PII/secrets.
- [ ] AWS client customizers do not allocate new clients per request.
- [ ] LocalStack endpoints/credentials exist only in test/local profiles.
- [ ] Testcontainers images are pinned and auth requirements are handled.
- [ ] Dependency tree shows no Spring Framework/AWS SDK version conflicts.
- [ ] Integration tests cover S3/SQS/config imports and failure paths.
- [ ] Non-production AWS tests verify IAM, KMS, event delivery, and Region.
- [ ] Deployment includes canary, dashboards, alerts, rollback, and runbooks.
- [ ] Release notes and compatibility table reviewed for the exact patch version being deployed.

## 35. Summary

Spring Cloud AWS enables Spring Boot to consume AWS services using Spring idioms: per-service starters, auto-configuration for credentials/Region, templates, message listeners, Config Data imports, metrics, and testing utilities. AWS SDK for Java 2.x remains the layer executing API calls; whenever a feature lacks a Spring abstraction, inject the SDK client directly.

**The compatibility matrix is the first prerequisite for a stable integration.** Per the project's compatibility table, Spring Cloud AWS 3.4.x aligns with Spring Boot 3.5.x/Spring Cloud 2025.0.x/Spring Framework 6.2.x; Spring Cloud AWS 4.x aligns with Spring Boot 4.0.x/Spring Cloud 2025.1.x/Spring Framework 7.0.x. Both modern release lines use AWS SDK for Java 2.x. Patch releases and support windows evolve, so verify the exact release docs before locking dependencies.

After selecting versions, use the BOM to keep the dependency graph aligned, pick only the starters needed, rely on workload identity, set Region explicitly, apply least-privilege IAM, and run integration tests using LocalStack/Testcontainers alongside a non-production AWS account. For SQS, design idempotency/acknowledgment; for Secrets Manager, test rotation against stateful connection holders; for S3, govern object permissions and streaming.

### Official documentation

- [Spring Cloud AWS Reference Documentation 4.2.1](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html)
- [Spring Cloud AWS project README and Compatibility Matrix](https://github.com/awspring/spring-cloud-aws/blob/main/README.md)
- [Spring Cloud AWS Bill of Materials](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#bill-of-materials)
- [Spring Cloud AWS Credentials and Region](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#spring-cloud-aws-core)
- [Spring Cloud AWS S3 Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#s3-integration)
- [Spring Cloud AWS SQS Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#sqs-integration)
- [Spring Cloud AWS Secrets Manager](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#secrets-manager-integration)
- [Spring Cloud AWS Parameter Store](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#parameter-store-integration)
- [Spring Cloud AWS Testing with LocalStack](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#testing)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Release 2025.0 Reference](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html)
- [Spring Cloud Release 2025.1 Reference](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html)

**Note:** Patch versions, Java baselines, starter inventories, and support windows change. Rely on the project's compatibility matrix and the reference docs for your exact Spring Cloud AWS artifact version; build and test with the actual dependency tree before promoting to production.
