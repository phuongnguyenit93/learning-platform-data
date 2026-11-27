# LocalStack for Supported AWS APIs

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services across **AWS, Azure, and Google Cloud** via Spring Cloud and their corresponding SDKs. On the AWS track, an application might call S3 for file storage, SQS/SNS for messaging, DynamoDB for data persistence, or Secrets Manager for reading sensitive configuration. If every integration test run required an AWS account, real resources, and cloud spend, the feedback loop would be slow and hard to run reliably in CI.

**LocalStack** provides a local simulated environment for many AWS services on a developer machine or inside a container. The application still uses the AWS SDK for Java and Spring Cloud AWS; the client endpoint is pointed to LocalStack. **Testcontainers** starts LocalStack with the JUnit test lifecycle, supplies dynamic endpoints/ports, and cleans up the container once tests finish.

The lesson title highlights an important boundary: LocalStack only simulates the services and API operations supported by the version and edition in use. Seeing a service listed does not mean every operation, semantic detail, IAM behavior, quota, and operational characteristic matches real AWS identically.

After this lesson, you will be able to:

- Identify which AWS operations LocalStack supports before designing tests.
- Connect Spring Boot / AWS SDK for Java 2.x to LocalStack via endpoint overrides.
- Use Testcontainers and JUnit 5 to manage the LocalStack container.
- Test S3, SQS, SNS, DynamoDB, and Secrets Manager flows at the supported API level.
- Separate local test configuration from production AWS configuration.
- Manage resources, data, and containers so tests remain independent and repeatable.
- Recognize what LocalStack cannot prove and add smoke tests on real AWS when needed.

## 2. LocalStack and Testing Scope

LocalStack is a cloud emulator. It accepts requests at AWS API endpoints and simulates the behavior of a set of AWS services so applications can run locally without calling AWS directly.

~~~mermaid
flowchart LR
    T[JUnit 5 integration test] --> A[Spring Boot application]
    A --> B[AWS SDK v2 / Spring Cloud AWS]
    B -->|endpoint override| L[(LocalStack container)]
    L --> S3[S3 API]
    L --> SQS[SQS API]
    L --> SNS[SNS API]
    L --> DDB[DynamoDB API]
    L --> SM[Secrets Manager API]
~~~

During tests, the application executes the exact same AWS SDK code paths. The primary difference is that the client is configured with the LocalStack endpoint, a test region, and dummy credentials. LocalStack handles requests and returns responses according to its implementation.

LocalStack is well-suited for verifying:

- Whether the AWS SDK is configured with the expected endpoint, region, and credentials.
- That the application creates buckets/queues/tables/secrets and invokes supported APIs.
- Request/response mapping, serialization, and error handling.
- Message publish/consume or object upload/download flows.
- Certain cross-service interactions, such as S3 notifications or SNS fan-out to SQS when the integration is supported.

LocalStack does not by itself prove that the application will run cleanly on production AWS. It does not replace testing real networking, real IAM roles, KMS key policies, quotas, service limits, latency, throughput, failure modes, and semantics that exist only on real managed services.

## 3. Checking API Coverage Before Writing Tests

Before choosing LocalStack, identify the exact API operations your code invokes. Do not check service names alone.

For example, a document upload flow might invoke:

- S3: CreateBucket, PutObject, GetObject, HeadObject, DeleteObject.
- SQS: CreateQueue, SendMessage, ReceiveMessage, DeleteMessage.
- SNS: CreateTopic, Subscribe, Publish.
- DynamoDB: CreateTable, PutItem, GetItem, Query, UpdateItem.
- Secrets Manager: CreateSecret, GetSecretValue, PutSecretValue.

Look up each operation in the service's API Coverage page in LocalStack's documentation. Coverage tables indicate which operations are implemented, which are unimplemented, and which plan/edition grants access. Coverage can vary across versions, editions, and licenses; re-check whenever upgrading versions.

<text>Documentation snapshot at the time of writing (24-11-2026):</text>

| Service | Documented Operations | Notes |
|---|---:|---|
| S3 | 100/116 | S3 Control has a separate coverage table, 31/97 |
| SQS | 23/23 | Has specific limitations around changing MessageRetentionPeriod |
| SNS | 36/42 | Filter policies do not support the cidr operator |
| DynamoDB | 47/58 | Some import/export APIs and some global-table operations are unsupported |
| Secrets Manager | 22/23 | StopReplicationToReplica is not yet implemented |

These numbers are a documentation snapshot, not a fixed guarantee. Open the latest coverage page and confirm your environment's plan/license before relying on an operation.

### 3.1. Building an API Matrix for Your Use Cases

Before writing tests, record:

| Use Case | Service | Operations Needed | Coverage | Outcome |
|---|---|---|---|---|
| File upload | S3 | CreateBucket, PutObject, GetObject | Check S3 page | Use LocalStack if sufficient |
| Submit job | SQS | CreateQueue, SendMessage, ReceiveMessage | Check SQS page | Use LocalStack if sufficient |
| Event fan-out | SNS/SQS | CreateTopic, Subscribe, Publish | Check both services | Test end-to-end flow |
| Persist record | DynamoDB | CreateTable, PutItem, Query | Check DynamoDB page | Use LocalStack if sufficient |
| Read secret | Secrets Manager | CreateSecret, GetSecretValue | Check Secrets Manager page | Use LocalStack if sufficient |

If an operation is unimplemented or restricted by your plan, do not write tests assuming that operation works. Pick one of these options: mock the adapter for unit tests, use the real service in a dedicated integration test, or narrow the test scope to supported APIs.

## 4. Where LocalStack Fits in the Testing Strategy

A Spring Boot application should have multiple test layers with distinct goals:

| Test Type | Infrastructure | What It Proves |
|---|---|---|
| Unit test | Mock/fake | Business logic and error-handling branches |
| Slice test | Stripped-down Spring context | Wiring, serialization, or repository boundaries |
| LocalStack integration test | Simulated AWS APIs | AWS SDK/client configuration and supported API flows |
| AWS smoke/contract test | Dedicated test AWS account | IAM, policies, encryption, networking, and real semantics |
| Production monitoring | Production AWS | Runtime behavior, latency, error rates, and quotas |

You do not need to start LocalStack for every unit test. Use it when verifying that the application and AWS APIs exchange data properly. Pure logic such as filename validation, fee calculation, or domain object mapping should be tested quickly with unit tests.

A common pipeline:

~~~text
Pull request
  -> Unit tests
  -> Spring integration tests + LocalStack
  -> Build/package
  -> AWS smoke tests on test account (when cloud contracts change)
  -> Deploy
  -> Production monitoring
~~~

## 5. Dependencies for Spring Boot and Testcontainers

With Spring Cloud AWS, use the BOM compatible with your Spring Boot version. Per the current compatibility matrix, Spring Cloud AWS 3.4.x aligns with Spring Boot 3.5.x; the 4.x line targets Spring Boot 4.0.x. Do not mix arbitrary versions of Spring Boot, Spring Cloud AWS, and the AWS SDK.

Maven example for an application using S3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>3.4.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-localstack</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The example above uses Spring Cloud AWS 3.4.2 for Spring Boot 3.5 and Testcontainers 2.0.5. If your project uses Spring Boot 4, select the compatible Spring Cloud AWS 4.x line. Starting in Testcontainers 2.x, module artifacts have the `testcontainers-` prefix and module Java packages moved into per-module namespaces. If your project still uses Testcontainers 1.x, dependencies and packages may differ.

When testing SQS/SNS/DynamoDB/Secrets Manager, add the corresponding starter or AWS SDK modules. Add only the clients required by the application.

## 6. Running LocalStack Standalone for Development

LocalStack can run via Docker or Docker Compose. The default API gateway typically listens on port 4566. Minimal Compose configuration example:

~~~yaml
services:
  localstack:
    image: localstack/localstack:latest
    ports:
      - "4566:4566"
    environment:
      SERVICES: s3,sqs,sns,dynamodb,secretsmanager
      AWS_DEFAULT_REGION: us-east-1
      LOCALSTACK_AUTH_TOKEN: $LOCALSTACK_AUTH_TOKEN
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
~~~

In real environments, pin the image by tested version or digest instead of relying on the `latest` tag. Keep the auth token in a secret store or local/CI environment variable; never commit tokens into Compose files.

Starting from 23-03-2026, the LocalStack image referenced in Testcontainers documentation requires the `LOCALSTACK_AUTH_TOKEN` environment variable to start. Without the token, the container may exit immediately on startup. Verify the current image authentication requirements and your active license/plan.

To quickly check the endpoint, you can run AWS CLI against the LocalStack endpoint:

~~~bash
aws --endpoint-url=http://localhost:4566 s3api list-buckets
aws --endpoint-url=http://localhost:4566 sqs list-queues
~~~

LocalStack requires AWS credentials and a region for API operations just like the AWS SDK. In local tests, use dummy credentials such as `test/test`; never use production access keys.

## 7. Managing Container Lifecycle with Testcontainers

Testcontainers starts the container before tests and cleans it up afterward. This avoids depending on a pre-started LocalStack server on a developer's machine or a fixed port in CI.

JUnit 5 example with Testcontainers 2.0.5:

~~~java
import org.testcontainers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class LocalStackContainerTest {

    private static String requiredAuthToken() {
        String token = System.getenv("LOCALSTACK_AUTH_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "Set LOCALSTACK_AUTH_TOKEN before running LocalStack tests");
        }
        return token;
    }

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse(
                            System.getProperty(
                                    "localstack.image",
                                    "localstack/localstack:latest")))
                    .withServices("s3", "sqs")
                    .withEnv("LOCALSTACK_AUTH_TOKEN", requiredAuthToken());
}
~~~

Set a fixed image version in build/CI configuration—for example, passing the `localstack.image` system property to a team-approved version. The example above uses `latest` as a fallback solely to illustrate how to pass the image; avoid mutable tags as the default in release pipelines.

Key points to remember:

- Testcontainers requires a running Docker or supported container runtime.
- Ports are mapped dynamically; retrieve the endpoint from the container instead of hardcoding `localhost:4566`.
- `withServices` enables only the services needed for the test, reducing startup time and resource usage.
- A static `@Container` is shared across test methods in the class; service data persists between methods until the container stops.
- An instance `@Container` creates a separate lifecycle per test method at the cost of longer execution time.
- The Testcontainers JUnit 5 extension is primarily tested with sequential execution; if parallel execution is enabled, you must design resource isolation and verify extension limits.

## 8. Connecting Spring Boot to the LocalStack Endpoint

Spring Cloud AWS can auto-configure an `S3Client` from its starter. Use `@DynamicPropertySource` to supply the endpoint, region, and credentials provided by Testcontainers:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void awsProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.cloud.aws.s3.endpoint",
            () -> LOCALSTACK.getEndpoint().toString());
    registry.add(
            "spring.cloud.aws.region.static",
            LOCALSTACK::getRegion);
    registry.add(
            "spring.cloud.aws.credentials.access-key",
            LOCALSTACK::getAccessKey);
    registry.add(
            "spring.cloud.aws.credentials.secret-key",
            LOCALSTACK::getSecretKey);
    registry.add(
            "spring.cloud.aws.s3.path-style-access-enabled",
            () -> true);
}
~~~

For SQS or SNS, configure the corresponding endpoint, such as `spring.cloud.aws.sqs.endpoint` or `spring.cloud.aws.sns.endpoint`. You may use `spring.cloud.aws.endpoint` as a shared endpoint if your Spring Cloud AWS version supports that global property; configuring per-service endpoints avoids accidentally redirecting other clients.

In production `application.yml`, never configure LocalStack endpoints or dummy credentials. Load test configuration from `@DynamicPropertySource` or a test profile so the production app cannot accidentally call a simulated endpoint.

### 8.1. If Building AWS SDK Clients Manually

When not using Spring Cloud AWS starters or when custom client control is needed, build AWS SDK for Java 2.x clients directly:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(
                                LOCALSTACK.getAccessKey(),
                                LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();
~~~

The endpoint override, region, and credentials are all required for requests to be signed and routed properly. The endpoint from `getEndpoint()` works for tests running on the host. If the application also runs inside another Docker container, use a Docker network and internal address; host-mapped endpoints are not guaranteed to be reachable from peer containers.

## 9. Testing S3: Creating a Bucket, Uploading, and Downloading

S3 is a good fit for testing basic file storage flows. With the Spring Cloud AWS S3 starter, the Spring context provides an `S3Client` bean. Tests should create a dedicated bucket, upload an object, download it back, and compare contents.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Testcontainers
@SpringBootTest
class S3LocalStackIT {
    private static String authToken() {
        String token = System.getenv("LOCALSTACK_AUTH_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException("LOCALSTACK_AUTH_TOKEN is required");
        }
        return token;
    }

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse("localstack/localstack:latest"))
                    .withServices("s3")
                    .withEnv("LOCALSTACK_AUTH_TOKEN", authToken());

    @DynamicPropertySource
    static void awsProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.aws.s3.endpoint",
                () -> LOCALSTACK.getEndpoint().toString());
        registry.add("spring.cloud.aws.region.static", LOCALSTACK::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key",
                LOCALSTACK::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key",
                LOCALSTACK::getSecretKey);
        registry.add("spring.cloud.aws.s3.path-style-access-enabled",
                () -> true);
    }

    @Autowired
    S3Client s3Client;

    @Test
    void uploadsAndDownloadsObject() {
        String bucket = "it-" + UUID.randomUUID().toString();
        String key = "documents/example.txt";
        String expected = "LocalStack integration test";

        s3Client.createBucket(CreateBucketRequest.builder()
                .bucket(bucket)
                .build());

        try {
            s3Client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType("text/plain")
                            .build(),
                    RequestBody.fromString(expected));

            String actual = s3Client.getObjectAsBytes(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build())
                    .asUtf8String();

            assertEquals(expected, actual);
        } finally {
            s3Client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
            s3Client.deleteBucket(DeleteBucketRequest.builder()
                    .bucket(bucket)
                    .build());
        }
    }
}
~~~

This example focuses on the `CreateBucket`, `PutObject`, `GetObject`, `DeleteObject`, and `DeleteBucket` APIs; verify each operation in the API Coverage table of your pinned LocalStack version. If your application uses `S3Template` or `S3Resource`, inject that abstraction and test through the corresponding API to verify both Spring Cloud AWS wiring and your business adapter.

## 10. Testing SQS: Sending, Receiving, and Acknowledging Messages

SQS helps test producer/consumer boundaries. You can use Spring Cloud AWS `SqsTemplate` or the AWS SDK `SqsClient`. An SDK-level test can do the following:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.UUID;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.CreateQueueRequest;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.DeleteQueueRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

SqsClient sqs = SqsClient.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                        LOCALSTACK.getAccessKey(),
                        LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();

String queueUrl = sqs.createQueue(CreateQueueRequest.builder()
        .queueName("it-" + UUID.randomUUID())
        .build()).queueUrl();

try {
    sqs.sendMessage(SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody("document-42")
            .build());

    var messages = sqs.receiveMessage(ReceiveMessageRequest.builder()
            .queueUrl(queueUrl)
            .waitTimeSeconds(2)
            .maxNumberOfMessages(1)
            .build()).messages();

    assertEquals("document-42", messages.get(0).body());

    sqs.deleteMessage(DeleteMessageRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(messages.get(0).receiptHandle())
            .build());
} finally {
    sqs.deleteQueue(DeleteQueueRequest.builder()
            .queueUrl(queueUrl)
            .build());
    sqs.close();
}
~~~

This snippet illustrates the API flow; in real tests, handle cases where receive returns an empty list using Awaitility or polling with a timeout, instead of indexing the first element immediately. When testing an asynchronous Spring Cloud AWS listener, assert on the resulting business state with a bounded timeout.

Do not treat a successful `SendMessage` call as proof that the consumer processed the message. Inspect the outcome after the listener finishes and verify acknowledgement/deletion according to the semantics your application uses.

## 11. Testing SNS and SNS → SQS Flows

SNS provides publish/subscribe; SQS buffers messages for downstream consumers. An integration test can:

1. Create an SNS topic.
2. Create an SQS queue.
3. Subscribe the queue to the topic.
4. Configure the queue policy to allow SNS to deliver messages.
5. Publish an event.
6. Receive the message from SQS and verify its body/attributes.

LocalStack supports many SNS APIs, though not all of them. For instance, current documentation notes that some SMS sandbox APIs are unimplemented and the `cidr` operator in filter policies is not supported. If your application relies on those features, verify coverage and test on real AWS.

When testing notification delivery, verify both subscription setup and the queue policy. Checking only that SNS `Publish` returns a `MessageId` does not prove the message reached the subscriber.

## 12. Testing DynamoDB

LocalStack supports a subset of the DynamoDB API, suitable for testing core operations:

- `CreateTable` and `DescribeTable`.
- `PutItem`, `GetItem`, `UpdateItem`, and `DeleteItem`.
- `Query` and `Scan` for supported use cases.
- Certain transactional operations such as `TransactWriteItems` and `TransactGetItems`.

Client example:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                        LOCALSTACK.getAccessKey(),
                        LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();
~~~

In tests, create a table with a unique name and schema matching your application, write an item, and read it back by partition key. After the test, delete the table or use a dedicated namespace/table name per test suite.

Do not conclude that LocalStack verifies all DynamoDB behaviors. Current documentation notes limitations with global tables, replication, and certain import/export APIs. For example, global tables Version 2019 are supported while legacy Version 2017 is not; DynamoDB Streams on replicated tables and some batch operations on replicated tables have restrictions.

If your application depends on transaction isolation, complex conditional writes, TTL timing, global-table conflict resolution, or capacity behavior, add real AWS tests.

## 13. Testing Secrets Manager, Parameter Store, and KMS

LocalStack supports a set of Secrets Manager and Systems Manager Parameter Store APIs. For Secrets Manager, basic flows can create secrets, read `SecretString`, update versions, and delete secrets within supported APIs.

Example reading a secret with AWS SDK v2:

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;

String value = secretsManager.getSecretValue(
        GetSecretValueRequest.builder()
                .secretId("integration-test/database")
                .build())
        .secretString();
~~~

In tests, use only synthetic secrets. Never copy production secrets into LocalStack fixtures or logs. Create secrets with test-specific names, read values, and clean up resources after the test.

KMS and encryption must be evaluated separately. LocalStack can simulate certain KMS APIs and integration flows, but a passing `Encrypt`/`Decrypt` operation does not prove IAM key policies, grants, rotation, HSM-backed security, or production AWS encryption behavior. Critical security requirements must be tested on a dedicated test AWS account with isolated keys and policies.

## 14. Credentials, Region, and Configuration Isolation

The AWS SDK requires credentials and a region to sign requests. With LocalStack, use the dummy credentials supplied by the container:

- Access key: `LOCALSTACK.getAccessKey()`.
- Secret key: `LOCALSTACK.getSecretKey()`.
- Region: `LOCALSTACK.getRegion()`.
- Endpoint: `LOCALSTACK.getEndpoint()`.

Prevent the AWS SDK from accidentally picking up production credentials from a developer machine or CI runner. Configure an explicit endpoint override in tests so requests can never reach real AWS.

In production:

- Use an IAM role, task role, IRSA/EKS Pod Identity, or appropriate workload identity.
- Never use static test credentials.
- Never include LocalStack endpoints in production profiles.
- Never grant real AWS permissions to test containers.

LocalStack supports some IAM and policy features depending on coverage/plan, but testing permission enforcement on an emulator does not replace verifying IAM roles, resource policies, SCPs, permission boundaries, and KMS key policies in real AWS.

## 15. Key Differences Compared to Real AWS

LocalStack simulates APIs and partial service behaviors; real AWS is distributed managed infrastructure with many additional operational conditions.

| Aspect | LocalStack | Real AWS |
|---|---|---|
| API operations | Only operations implemented in coverage | Full AWS service API contract |
| IAM | Support level depends on service/feature/plan | Full AWS IAM, resource policies, SCPs, roles, and policy evaluation |
| Event delivery | Simulates supported integration flows | Real delivery retries, filtering, quotas, and service behavior |
| Consistency | Timing/consistency may differ from production | Follows exact per-service AWS semantics |
| Networking | Local container/network | VPCs, subnets, endpoints, DNS, NAT, firewalls, and routing |
| Quotas/throttling | Does not fully reflect production quotas | Real service quotas and throttling |
| Encryption | Selected APIs/flows simulated | Real KMS, key policies, rotation, grants, and managed services |
| Performance | Depends on container host machine | Depends on region, capacity, and managed service |
| Observability | Emulator logs/container diagnostics | CloudWatch, X-Ray, CloudTrail, and native metrics |

These differences do not make LocalStack less valuable. They simply define the exact scope that a local test can prove.

## 16. Data Management and Cleanup

Testcontainers can share one container across multiple methods. Resources created inside LocalStack do not vanish automatically between methods while the container keeps running.

Isolation principles:

- Create buckets/tables/queues/secrets with a UUID or test run ID suffix.
- Delete objects before deleting buckets.
- Delete messages/queues or purge queues after tests when appropriate.
- Delete subscriptions before topics if required.
- Do not let tests depend on resources created by other tests.
- Use `try/finally` or `@AfterEach` to clean up even when assertions fail.

LocalStack offers persistence and snapshot features depending on configuration/plan. For standard integration tests, prefer a fresh container for clean state. If enabling persistence or reusable containers for speed, enforce clear namespace/cleanup rules and prevent stale state from causing false passes.

For DynamoDB, LocalStack documentation notes that `DYNAMODB_IN_MEMORY` mode can lose data when the container stops even if persistence is enabled. Do not use this mode if tests require data to survive restarts.

## 17. Testing Asynchronous Flows and Eventual Consistency

SQS/SNS and event-driven workflows rarely complete the moment a producer sends a message. Tests should wait for business conditions with a finite timeout.

Example with Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
    .atMost(10, SECONDS)
    .untilAsserted(() -> {
        var result = jobRepository.findById(jobId).orElseThrow();
        assertEquals(JobStatus.COMPLETED, result.status());
    });
~~~

Avoid fixed `Thread.sleep()` calls because they slow tests unnecessarily or become flaky under heavy CI load. Use a reasonable polling interval and a timeout large enough to catch real failures without stalling the pipeline.

For consumers, verify:

- Messages are received and handlers are invoked.
- Business side effects are persisted durably.
- Messages are acknowledged/deleted only after successful processing.
- Failed messages are retried or dead-lettered according to configurations supported by LocalStack.
- Consumers are idempotent when messages are redelivered.

Do not conclude that production retry semantics, visibility timeouts, FIFO ordering, or DLQs work correctly based solely on a single happy-path test.

## 18. Running LocalStack in CI

Testcontainers typically runs LocalStack inside the CI runner's Docker daemon. The pipeline needs:

1. Docker or a Testcontainers-supported container runtime installed.
2. `LOCALSTACK_AUTH_TOKEN` supplied as a CI secret if required by the image.
3. Pinned LocalStack image version/digest and Testcontainers version.
4. Integration tests executed using the endpoint retrieved from Testcontainers.
5. Container logs archived on test failure to aid diagnosis.
6. Testcontainers cleaning up containers and networks after tests finish.

Never hardcode host port 4566 in tests. Testcontainers maps ports dynamically to avoid collisions when multiple CI jobs run concurrently.

Conceptual GitHub Actions example:

~~~yaml
jobs:
  integration-test:
    runs-on: ubuntu-latest
    env:
      LOCALSTACK_AUTH_TOKEN: "inject this value from the CI secret store"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - name: Run integration tests
        run: ./mvnw -B verify -Pintegration
~~~

Replace the illustrative `LOCALSTACK_AUTH_TOKEN` value with your CI platform's secret binding. Never print tokens into the repository, command output, or test reports. Do not grant production AWS credentials to this job. If real AWS testing is needed, create a separate job with a test account, restricted role, and uniquely named resources.

## 19. Troubleshooting and Practice Exercises

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Container fails to start | Missing `LOCALSTACK_AUTH_TOKEN`, Docker unavailable, or incompatible image | Check token, Docker daemon, and container logs |
| SDK calls real AWS by mistake | Missing endpoint override or production profile loaded | Verify endpoint, region, and test profile |
| Signature/region error | Region or credentials mismatch | Pull region/credentials from `LocalStackContainer` |
| S3 bucket request host-style error | Incompatible S3 endpoint/virtual-host routing | Use container endpoint and enable path-style access when needed |
| SQS receive returns empty | Test reads too early or wrong queue URL | Poll with timeout, verify queue and endpoint |
| SNS publish succeeds but queue has no message | Misconfigured subscription or queue policy | Check protocol, subscription confirmation, and policy |
| DynamoDB operation unsupported | API outside coverage or plan restriction | Check operation-level coverage |
| Test passes alone but fails in full suite | Shared data or container state | Use unique resource names and cleanup |
| Parallel tests are flaky | Shared LocalStack/container/resource collisions | Separate namespaces, bound parallelism, or isolate container lifecycle |
| LocalStack passes but AWS fails | Differences in IAM, quotas, consistency, encryption, or networking | Add AWS smoke/contract tests |

### Exercise A — S3

Write an integration test for file upload/download using an `S3Client` auto-configured by Spring Cloud AWS. Create a unique bucket for the test, verify content type and file contents, and clean up objects/bucket afterward.

### Exercise B — SQS

Create a queue, send a message, and verify that the consumer updates job status. Use Awaitility instead of sleep; verify the message is not deleted before the business transaction commits.

### Exercise C — SNS/SQS

Create a topic and queue, subscribe the queue to the topic, publish an event, and verify the message arrives in the queue. Check policies and filter policy limitations against API coverage.

### Exercise D — DynamoDB

Create a table with a partition key, write an item, read it back, and test a conditional update. Document which operations are supported by LocalStack and which require real AWS testing.

### Exercise E — Secrets Manager

Create a test secret, read `SecretString`, and delete the secret. Ensure secret values never appear in logs or test reports.

### Self-Check Questions

1. **What is LocalStack?** A locally running emulator for a subset of AWS services and API operations.
2. **Why check operation-level API coverage?** Because a service may be listed as supported while specific API operations remain unimplemented or restricted by plan.
3. **What does Testcontainers help with?** Managing container lifecycles, dynamic ports, and cleanup tied to test execution.
4. **Which LocalStack artifact does Testcontainers 2.0.5 use?** `org.testcontainers:testcontainers-localstack`.
5. **Which environment variable does the LocalStack container require as of 23-03-2026 per Testcontainers guidance?** `LOCALSTACK_AUTH_TOKEN`.
6. **Why does the AWS SDK need an endpoint override?** So requests are routed to LocalStack instead of real AWS endpoints.
7. **Should AWS production credentials be used in LocalStack tests?** No; use the dummy credentials provided by the container.
8. **Does a successful SQS `SendMessage` prove a job finished?** No; you must verify the consumer processed it and updated business state.
9. **Does LocalStack replace AWS smoke tests?** No; IAM, KMS, quotas, networking, consistency, and managed behavior require separate verification.
10. **How do you prevent tests from depending on stale state?** Unique resource names, cleanup, and isolated container lifecycles.

## 20. Summary

LocalStack is a practical tool for integration testing Spring Boot with the AWS API operations supported by the emulator. Combining AWS SDK for Java 2.x, Spring Cloud AWS, Testcontainers, and JUnit 5 lets tests provision resources, call APIs, validate data, and run in CI without connecting to production AWS.

Before writing tests, check API Coverage per operation and plan. Use endpoints, regions, and credentials from `LocalStackContainer`, never hardcode ports, never use production credentials, and clean up resources after tests. For asynchronous flows, wait for business outcomes with a timeout; never treat publishing a message as completion of the work.

LocalStack catches wiring errors, request mapping bugs, and integration issues early. AWS smoke/contract tests remain essential for IAM, resource policies, KMS, quotas, networking, eventual consistency, performance, and managed-service behavior. Apply each test layer to its proper scope to achieve fast feedback while maintaining confidence for real cloud deployments.

### Official References

- [LocalStack — Getting Started](https://docs.localstack.cloud/aws/getting-started/)
- [LocalStack — AWS API Coverage](https://docs.localstack.cloud/aws/services/)
- [LocalStack — S3 API Coverage and Limitations](https://docs.localstack.cloud/aws/services/s3/)
- [LocalStack — SQS API Coverage and Limitations](https://docs.localstack.cloud/aws/services/sqs/)
- [LocalStack — SNS API Coverage and Limitations](https://docs.localstack.cloud/aws/services/sns/)
- [LocalStack — DynamoDB API Coverage and Limitations](https://docs.localstack.cloud/aws/services/dynamodb/)
- [LocalStack — Secrets Manager API Coverage](https://docs.localstack.cloud/aws/services/secretsmanager/)
- [LocalStack — AWS SDK for Java](https://docs.localstack.cloud/aws/connecting/aws-sdks/java/)
- [LocalStack — Testcontainers Integration](https://docs.localstack.cloud/aws/customization/integrations/testing/testcontainers/)
- [Testcontainers for Java — LocalStack Module](https://java.testcontainers.org/modules/localstack/)
- [Testcontainers for Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Spring Cloud AWS — Compatibility Matrix and Supported Integrations](https://github.com/awspring/spring-cloud-aws)
- [Spring Cloud AWS — S3 Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html#s3-integration)
