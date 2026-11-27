# Setting Up Emulated AWS Connectivity with LocalStack

## 1. Why Emulate AWS When Learning Spring Boot and Spring Cloud AWS?

A Spring Boot service may use Amazon S3 to store files, Amazon SQS to exchange messages, AWS Secrets Manager to read secrets, and DynamoDB to persist data. Calling real AWS on every local run or test introduces extra concerns: accounts and IAM roles, pre-provisioned infrastructure, network connectivity, cost, latency, and the risk of accidentally touching real data.

**LocalStack** runs an environment emulating a set of AWS APIs and services on a developer machine or inside a container. Instead of calling real AWS endpoints, the application configures **LocalStack endpoints** and uses resources created inside the emulated environment. This makes integration flows repeatable.

This lesson belongs to the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module's overall goal is practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries—covering identity/permissions, storage, messaging, data, secrets, integration testing, and differences across cloud providers. This lesson focuses on configuring **Spring Cloud AWS by AWSpring**, **AWS SDK for Java 2.x**, and **LocalStack** in local/test environments.

After this lesson, you will be able to:

1. Explain LocalStack's role in the development workflow and its limitations compared to real AWS.
2. Start LocalStack with Docker Compose and create emulated S3 buckets and SQS queues.
3. Configure **endpoints, regions, credentials, and S3 path-style** for AWS SDK v2 or Spring Cloud AWS.
4. Execute an S3 write/read round-trip and SQS send/receive round-trip to prove connectivity works.
5. Write integration tests using **Testcontainers** with dynamic Spring Boot configuration.
6. Diagnose Docker networking, endpoint, region, DNS, credential, and bean auto-configuration failures.
7. Design guardrails preventing tests/local runs from accidentally sending requests to production AWS.

> **Version scope:** Java examples use AWS SDK for Java **2.x** and Spring Cloud AWS **3.x** configuration style. LocalStack, Testcontainers, AWSpring, and Spring Boot versions must be chosen from your project's actual compatibility documentation. Available services/features and LocalStack licensing or token requirements may differ by **release and edition**; check the LocalStack version you are running before starting.

## 2. Where Does LocalStack Sit in the Architecture?

In real environments, the SDK builds requests targeting AWS service endpoints. Locally, we keep most of the **SDK or AWSpring code** while redirecting endpoints to LocalStack and provisioning fake resources.

~~~mermaid
flowchart TB
    APP["Spring Boot application"] --> SPR["AWSpring S3Template / SqsTemplate<br/>or AWS SDK Java v2"]
    SPR --> CONF{"Environment configuration"}
    CONF -->|local / integration-test| EMU["LocalStack API endpoint<br/>http://localhost:4566"]
    CONF -->|staging / production| AWS["Real AWS service endpoint"]
    EMU --> S3L["Emulated S3"]
    EMU --> SQSL["Emulated SQS"]
    AWS --> S3A["Amazon S3"]
    AWS --> SQSA["Amazon SQS"]
~~~

Key distinctions:

| Concept | Purpose | When using LocalStack |
| --- | --- | --- |
| Service client | `S3Client`, `SqsClient`, or Spring template calling AWS operations | Same familiar SDK/APIs |
| Endpoint | HTTP(S) address receiving requests | Switched to LocalStack's URL |
| Region | Regional context for client and request signing | Set a consistent test region, e.g., `us-east-1` |
| Credentials | Values the SDK uses to sign requests | Use **fake credentials** strictly for the emulator |
| Resource | Bucket, queue, table, secret | Must be created in LocalStack or initialized during tests |
| Identity & policy | IAM principals, trust policies, KMS, SCPs | **Emulation cannot serve as proof of real AWS permissions** |
| Network | DNS, ports, container network, proxies | Must point to the right host/port for where the app runs |

**LocalStack does not replace AWS across all test categories.** A `PutObject`/`GetObject` or `SendMessage`/`ReceiveMessage` flow may succeed in the emulator yet fail on AWS due to IAM, bucket policies, KMS, network/VPC endpoints, queue configuration, quotas, or unemulated service behaviors.

### 2.1. Choosing Appropriate Tests for the Emulator

LocalStack is especially helpful for verifying:

- Whether the Spring context creates S3/SQS beans properly.
- Whether requests/responses use the right SDK, serializers, bucket names, object keys, and queue URLs.
- Whether adapters invoke the expected operations and handle responses and certain service errors.
- Whether producers and consumers communicate over a queue in a controlled environment.
- Whether integration flows run repeatably in CI when provisioning resources from scratch.

For scenarios that **depend strictly on real AWS**—such as IAM role trust on ECS/EKS, cross-account KMS policies, private endpoints, high-load latency, service quotas, or rare failure modes—add integration/smoke tests on an AWS sandbox.

## 3. Preparing Tools and Safety Conventions

Before practicing, prepare:

- Docker Engine or Docker Desktop capable of running Linux containers.
- Docker Compose plugin (`docker compose`).
- AWS CLI v2 or an equivalent tool for calling AWS APIs against the emulator.
- JDK and a Spring Boot project matching your intended AWSpring version.
- A LocalStack image release/edition supporting the S3 and SQS features used in the tests.

Verify you can run these commands:

~~~bash
docker version
docker compose version
aws --version
java -version
~~~

These are hands-on verification commands; this lesson does not assume they have already been run on your machine.

### 3.1. Use Test-Only Resources

Examples in this lesson use:

| Value | Purpose |
| --- | --- |
| `http://localhost:4566` | LocalStack edge endpoint when the app runs **on the host** |
| `http://localstack:4566` | Endpoint when the app runs inside the **same Docker Compose network** as the `localstack` service |
| `us-east-1` | Uniform test region to simplify S3 operations |
| `test` / `test` | Dummy access key and secret key for the emulator |
| `training-documents-local` | Fake S3 bucket |
| `training-events-local` | Fake SQS queue |

These values **do not represent production**. When calling real AWS, use an IAM role or properly authorized profile, real regions, and provisioned resource ARNs.

### 3.2. Always Know Where Requests Are Going

In SDK v2, these settings are **independent**:

- `endpointOverride(...)` selects the URL receiving requests.
- `region(...)` selects the client region and participates in request signing.
- `credentialsProvider(...)` selects the credential source.
- `bucket(...)`, `key(...)`, `queueUrl(...)` select business resources.

Setting a LocalStack endpoint **does not make the SDK ignore region or credentials**. Conversely, passing dummy credentials while forgetting the endpoint override can send requests to real AWS and fail authentication.

## 4. Starting LocalStack with Docker Compose

Create the following Compose example **in a dedicated practice directory**. The YAML below is instructional content, not a pre-created file:

~~~yaml
services:
  localstack:
    image: localstack/localstack:${LOCALSTACK_IMAGE_TAG:-latest}
    ports:
      - "127.0.0.1:4566:4566"
    environment:
      SERVICES: s3,sqs
      AWS_DEFAULT_REGION: us-east-1
~~~

Explanation:

- `4566` is LocalStack's standard edge endpoint port; many services are accessed over this port.
- `127.0.0.1:4566:4566` binds only to the host loopback interface to avoid accidentally exposing the emulator on external networks.
- `SERVICES=s3,sqs` targets the two services needed for the exercises; support depends on version/edition.
- `AWS_DEFAULT_REGION` here is **LocalStack's configuration**, not a replacement for `AWS_REGION` in a Java SDK running in another process.
- `LOCALSTACK_IMAGE_TAG` lets you pin a release. `latest` is convenient for demos but **not reproducibly stable** in CI; pin a team-verified tag or digest for real test suites.

Startup example:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail 100 localstack
~~~

Wait for services to reach ready state before creating resources. You can check the health endpoint where supported by your release:

~~~bash
curl http://localhost:4566/_localstack/health
~~~

If your LocalStack version requires an auth token or specific edition configuration, supply it per that release's official documentation. Never place real tokens inside Dockerfiles or committed Compose files.

### 4.1. Do Not Mount the Docker Socket Unless Needed

Some LocalStack features documented for specific capabilities may use a Docker socket mount. **Basic S3/SQS exercises do not require granting Docker socket access to the emulator container.** The Docker socket grants sensitive host/daemon privileges; consider it only when a feature and release documentation genuinely require it.

### 4.2. How Long Does Emulated Data Persist?

Without persistence configured, data stored by LocalStack can vanish when the container is recreated. For integration tests, **provisioning resources from scratch** is usually an advantage because it avoids stale state.

For manual debugging, you can use persistence supported by your LocalStack release, but CI should never depend on an old volume carrying buckets/queues from a prior run. Each test must control resource setup, cleanup, and naming.

### 4.3. Stopping the Environment

~~~bash
docker compose down
~~~

If using storage volumes, `docker compose down` and `docker compose down -v` behave differently. Delete volumes only when the data is reproducible test data and you know exactly which resources will be removed.

## 5. Pointing the AWS CLI to LocalStack

The AWS CLI defaults to real AWS. With LocalStack, explicitly specify the emulated endpoint and use dummy credentials during local testing.

On Bash:

~~~bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export AWS_PAGER=""
~~~

On PowerShell:

~~~powershell
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_REGION = "us-east-1"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:AWS_PAGER = ""
~~~

Set these variables only in a **terminal dedicated to the emulator**. Never mix that terminal with production commands. Pass `--endpoint-url` explicitly on every LocalStack command so you always know where requests go.

### 5.1. Creating an Emulated S3 Bucket

With test region `us-east-1`:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3api create-bucket \
  --bucket training-documents-local
~~~

In regions other than `us-east-1`, creating a bucket under S3 semantics usually requires a matching location constraint. Using `us-east-1` keeps basic exercises simpler.

Verify:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3api list-buckets
~~~

This command checks only the emulated environment. On real AWS, `ListBuckets` is also governed by IAM policies and service rules; the emulator may not replicate all restrictions.

### 5.2. Creating an Emulated SQS Queue

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  sqs create-queue \
  --queue-name training-events-local
~~~

Retrieve **the queue URL returned by the emulator**:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  sqs get-queue-url \
  --queue-name training-events-local
~~~

The queue URL can vary by LocalStack release and endpoint strategy, and may include a hostname tailored to container vs. host access. Never assume the queue URL is always `http://localhost:4566/000000000000/training-events-local`; obtain it from `CreateQueue` or `GetQueueUrl` and ensure the hostname is reachable from the process using that URL.

### 5.3. Confirm Resources Exist Before Starting Spring

Verify buckets and queues exist in the emulator before starting Spring Boot listeners. This is especially important for `@SqsListener`, because the listener container may resolve queue names **during `ApplicationContext` startup**. If the queue is missing, startup can fail or the library may auto-create queues depending on configuration/version, making tests harder to reproduce.

## 6. AWS SDK Java v2: Connecting to S3 via Endpoint Override

The best sanity check before Spring integration is testing a simple SDK client. Once the client completes a write/read round-trip against LocalStack, you know basics like networking, endpoint, region, credentials, and APIs align.

### 6.1. Dependency

If the project uses Maven and manages SDK versions via a BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
</dependency>
~~~

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("software.amazon.awssdk:s3")
}
~~~

Without a BOM/dependency management, declare a verified specific SDK version. Never put `s3`, `sqs`, and `auth` modules on mismatched versions.

### 6.2. Creating a Local S3Client

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public final class LocalS3ClientFactory {

    public static S3Client create(URI endpoint) {
        return S3Client.builder()
                .endpointOverride(endpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

Configuration breakdown:

- `endpointOverride(endpoint)` directs requests to LocalStack, e.g. `http://localhost:4566` when running on the host.
- `Region.US_EAST_1` provides a consistent test region for the client and request signing.
- `StaticCredentialsProvider` supplies dummy keys for the emulator. **Never carry this configuration into real environments.**
- `pathStyleAccessEnabled(true)` switches S3 URLs to path-style, avoiding DNS failures when the emulator lacks `bucket.localhost` hostname resolution.
- `S3Client` should be reused across the app/test lifecycle and closed when no longer needed.

### 6.3. Write and Read Round-Trip Test

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;

public class LocalS3RoundTrip {
    public static void main(String[] args) {
        try (S3Client s3 = LocalS3ClientFactory.create(
                URI.create("http://localhost:4566"))) {

            String bucket = "training-documents-local";
            String key = "receipts/example-001.txt";
            String content = "Spring Boot and LocalStack";

            s3.putObject(request -> request
                    .bucket(bucket)
                    .key(key),
                    RequestBody.fromString(content, StandardCharsets.UTF_8));

            String stored = s3.getObjectAsBytes(request -> request
                    .bucket(bucket)
                    .key(key))
                    .asUtf8String();

            if (!content.equals(stored)) {
                throw new IllegalStateException("Read-back content differs from original");
            }
            System.out.println("S3 round-trip PASS");
        }
    }
}
~~~

The example assumes bucket `training-documents-local` was already created in the AWS CLI step. Accented or Unicode text works as long as source files and compilation use UTF-8; a short payload keeps the API call clear here.

**Interpreting results:**

- If `PutObject` fails with `Connection refused`, check the port, container, and URL.
- If DNS fails on the bucket hostname, check path-style and endpoint.
- If `NoSuchBucket` occurs, check bucket creation, container state, and region.
- If calling real AWS returns 403, inspect IAM/resource policies rather than assuming LocalStack tests proved permissions.

## 7. AWS SDK Java v2: Connecting to SQS and Sending/Receiving Messages

Add the SDK module:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
</dependency>
~~~

Create a local client:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

public final class LocalSqsClientFactory {

    public static SqsClient create(URI endpoint) {
        return SqsClient.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(endpoint)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .build();
    }
}
~~~

When interacting with SQS, distinguish:

- **Client endpoint:** the SQS API address where the SDK sends requests.
- **Queue URL:** the URL identifying the target queue passed to `SendMessageRequest`/`ReceiveMessageRequest`.
- **Region:** the client/queue region, matching the emulated or real AWS setup.

### 7.1. Sending, Receiving, and Deleting Messages

~~~java
import java.net.URI;
import software.amazon.awssdk.services.sqs.SqsClient;

public class LocalSqsRoundTrip {
    public static void main(String[] args) {
        try (SqsClient sqs = LocalSqsClientFactory.create(
                URI.create("http://localhost:4566"))) {

            String queueUrl = sqs.getQueueUrl(request -> request
                    .queueName("training-events-local"))
                    .queueUrl();

            sqs.sendMessage(request -> request
                    .queueUrl(queueUrl)
                    .messageBody("{\"eventId\":\"evt-001\",\"type\":\"DocumentUploaded\"}"));

            var received = sqs.receiveMessage(request -> request
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(1)
                    .waitTimeSeconds(5))
                    .messages();

            if (received.isEmpty()) {
                throw new IllegalStateException("No message received");
            }

            for (var message : received) {
                System.out.println(message.body());
                sqs.deleteMessage(request -> request
                        .queueUrl(queueUrl)
                        .receiptHandle(message.receiptHandle()));
            }
        }
    }
}
~~~

The example assumes the queue was created beforehand using the AWS CLI. When passing the queue URL returned by the emulator, ensure its hostname/port are reachable from the active JVM.

### 7.2. Why Must Messages Be Deleted After Processing?

`ReceiveMessage` does not permanently consume a message. SQS uses a **visibility timeout**: a message is temporarily hidden while the consumer processes it, then reappears if not deleted. `DeleteMessage` requires the exact **receipt handle** from that receive call.

LocalStack can emulate these behaviors, yet idempotency, FIFO ordering, redrive policies, and network failures still require validation on real AWS for critical flows.

### 7.3. Controlled Failure Testing

To verify code handles more than just the happy path:

- Test a nonexistent queue name and verify the exception.
- Test a duplicate `eventId` payload to validate business idempotency logic.
- Test a handler taking longer than the visibility timeout and observe message redelivery in the emulator.
- Test a mismatched region or endpoint to distinguish connectivity errors from business errors.
- For Spring consumers, test acknowledgement and DLQ behavior per your AWSpring/SQS version.

## 8. Connecting Spring Boot via AWSpring's Spring Cloud AWS

Once the raw SDK works, use AWSpring starters to expose templates/beans so business code follows familiar Spring conventions.

### 8.1. Choosing Starters and BOM

Maven example, **assuming Spring Boot parent/dependency management is already present**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
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

`spring-cloud-aws.version` must be an **actual AWSpring release compatible with your project's Spring Boot/JDK**. Do not assume every AWSpring 3.x release matches every Spring Boot 3.x release. The BOM manages versions, while starters add integration capabilities.

If application code directly imports SDK clients, you can declare direct SDK v2 modules (e.g., `software.amazon.awssdk:s3`) using consistent managed versions. Never mix Java SDK 1.x (`com.amazonaws.*`) examples into an SDK v2 application.

### 8.2. Local-Only Configuration

Example `application-local.yml` using the property style common in AWSpring 3.x:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: us-east-1
      credentials:
        access-key: test
        secret-key: test
      s3:
        endpoint: ${LOCALSTACK_ENDPOINT:http://localhost:4566}
        path-style-access-enabled: true
      sqs:
        endpoint: ${LOCALSTACK_ENDPOINT:http://localhost:4566}

app:
  storage:
    bucket: training-documents-local
  messaging:
    queue: training-events-local
~~~

Explanation:

- `spring.cloud.aws.region.static` assigns the region for AWSpring-created client beans in this configuration.
- `credentials.access-key` and `credentials.secret-key` are **emulator-only dummy credentials** scoped to the `local` Spring profile.
- `s3.endpoint` and `sqs.endpoint` route both services to LocalStack instead of real AWS endpoints.
- `path-style-access-enabled` supports bucket addressing on the emulator; verify exact property names/support against your **exact AWSpring release**.
- `app.storage.bucket` and `app.messaging.queue` are application-defined business properties, not built-in AWSpring keys.

**Never activate the `local` profile in production.** In production configuration, load real regions/resources from deployment config and credentials from IAM workload roles/default provider chains—never dummy credentials or test endpoints.

### 8.3. Writing Files with S3Template

~~~java
import io.awspring.cloud.s3.S3Template;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageAdapter {
    private final S3Template s3;
    private final String bucket;

    public DocumentStorageAdapter(S3Template s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void storeText(String key, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        s3.upload(bucket, key, new ByteArrayInputStream(bytes));
    }
}
~~~

This example handles a small payload. For large files, use streaming/multipart APIs and memory limits. `S3Template` does not need to know whether it talks to LocalStack or real AWS: endpoint and credentials come from the **underlying client** driven by environment configuration.

### 8.4. Sending Messages via SqsTemplate

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

record DocumentUploaded(String eventId, String objectKey) {}

@Service
public class DocumentEventPublisher {
    private final SqsTemplate sqs;
    private final String queue;

    public DocumentEventPublisher(SqsTemplate sqs,
            @Value("${app.messaging.queue}") String queue) {
        this.sqs = sqs;
        this.queue = queue;
    }

    public void publish(DocumentUploaded event) {
        sqs.send(to -> to.queue(queue).payload(event));
    }
}
~~~

`SqsTemplate` relies on SQS integration and the AWSpring-provided SDK client. Verify conversion/serialization for `DocumentUploaded`, as an emulator receiving JSON does not prove every production consumer understands the same schema.

### 8.5. Receiving Messages with @SqsListener

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentEventConsumer {

    @SqsListener("${app.messaging.queue}")
    public void onUploaded(DocumentUploaded event) {
        // Idempotent processing by eventId.
        // If processing fails, let error/ack handling reflect the failure accurately.
    }
}
~~~

The listener can begin polling **as soon as the Spring context starts**. If the queue does not exist yet, provision it prior to startup or use a release-supported queue-creation mechanism under strict control. To test consumer behavior reliably, verify visibility timeout, concurrency, acknowledgement mode, serialization, and retry/DLQ handling.

## 9. When You Need to Create Clients Yourself in Spring

A project may avoid relying on AWSpring auto-configuration properties when adapters need distinct endpoints or regions. In that case, declare explicit SDK client beans:

~~~java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

@Configuration(proxyBeanMethods = false)
@Profile("local")
public class LocalAwsClients {

    @Bean(name = "localS3Client", destroyMethod = "close")
    S3Client localS3Client(
            @Value("${localstack.endpoint:http://localhost:4566}")
            String endpoint) {
        return S3Client.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(URI.create(endpoint))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

**Watch auto-configuration interactions:** declaring a custom `S3Client` bean can cause AWSpring auto-configuration to **back off** or wire differently depending on release and conditions. If you need both a default `S3Template` and multiple `S3Client` instances across regions/endpoints, use qualifiers/factories and inspect the actual `ApplicationContext`. Naming a bean `localS3Client` does not guarantee every template selects it automatically.

For business logic, create an adapter decoupled from connection details. A `DocumentStore` interface backed by S3 in production, LocalStack S3 in integration tests, and a simple fake in unit tests keeps configuration clean.

## 10. Common Issue: Host `localhost` Differs from Container `localhost`

This is the single most common reason Java fails with `Connection refused` even though LocalStack is running.

Suppose two containers share a Docker Compose setup:

~~~mermaid
flowchart LR
    HOST["Host machine"] -->|"http://localhost:4566"| PORT["Docker published port"]
    PORT --> LS["Container localstack:4566"]
    APP["Container spring-app"] -->|"http://localstack:4566"| LS
    APP -. "localhost:4566 points to the app container itself" .-> APP
~~~

| Where the application runs | Typical endpoint | Why |
| --- | --- | --- |
| Java running directly on host | `http://localhost:4566` | Docker publishes port 4566 to host loopback |
| Java running in the same Compose network | `http://localstack:4566` | Compose DNS service name |
| Testcontainers with JVM on host | `container.getEndpointOverride(...)` | Host and mapped port supplied by Testcontainers |
| Docker container on another network | Endpoint/alias reachable via configured network | Cannot reach service names on an unattached network by default |
| CI runner using a remote Docker daemon | Endpoint returned by Testcontainers/network env | Runner's `localhost` may not point to the Docker host |

### 10.1. Why Not Hard-Code `localhost` in Every Test?

When CI runs Docker via a remote daemon, published ports may live on a different host than the JVM. Testcontainers exposes `getHost()`, `getMappedPort(...)`, or `getEndpointOverride(...)` to resolve the endpoint dynamically. With the LocalStack module, prefer its endpoint helper **instead of hand-assembling URLs around port 4566**.

### 10.2. DNS for S3 Virtual-Hosted Style

The S3 SDK can send requests to hostnames like `bucket.endpoint-host`. Inside an emulator, that hostname may fail DNS resolution. That is why many local setups use `pathStyleAccessEnabled(true)` to issue `/bucket/key` URLs.

With other endpoints and DNS setups, virtual-hosted style can also work. The choice depends on emulator and network setup, not a universal rule for all S3 environments.

### 10.3. Queue URLs from the Emulator

A queue URL returned by `GetQueueUrl` may contain a hostname unreachable from the JVM or container. Inspect **the actual value**, LocalStack's endpoint strategy, and DNS/networking; never substitute handcrafted URLs in production. With Spring consumers/publishers, ensure queue names/URLs resolve cleanly under your AWSpring and SDK APIs.

## 11. Automated Integration Tests with Testcontainers

Running LocalStack manually works well for learning and debugging, but CI integration tests need repeatable setup and teardown. **Testcontainers** lets Java tests manage Docker container lifecycles and fetch real runtime endpoints automatically.

### 11.1. Test Dependencies

Structural Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Choose the LocalStack module matching the Testcontainers generation in use. -->
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>localstack</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The `localstack`/`junit-jupiter` artifact names above belong to **Testcontainers 1.x**. With **Testcontainers 2.x**, module coordinates may change to `testcontainers-localstack` and `testcontainers-junit-jupiter`. Select **the exact Testcontainers generation/BOM used by your project**, updating artifacts and imports as required by the release. Never mix both generations in the same project.

In Gradle, declare the corresponding test modules under `testImplementation(...)` with the proper BOM/platform. Testcontainers requires an available Docker runtime; pure unit tests do not require Docker.

### 11.2. Spring Boot Test Connecting Dynamically to LocalStack

The example below demonstrates the **classic Testcontainers API** injecting test endpoints into Spring Boot:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class LocalStackS3IntegrationTest {

    @Container
    static final LocalStackContainer localstack =
            new LocalStackContainer(DockerImageName.parse(
                    "localstack/localstack:latest"))
                    .withServices(
                            LocalStackContainer.Service.S3,
                            LocalStackContainer.Service.SQS);

    @DynamicPropertySource
    static void configureAws(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.aws.region.static",
                localstack::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key",
                localstack::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key",
                localstack::getSecretKey);
        registry.add("spring.cloud.aws.s3.endpoint",
                () -> localstack.getEndpointOverride(
                        LocalStackContainer.Service.S3).toString());
        registry.add("spring.cloud.aws.sqs.endpoint",
                () -> localstack.getEndpointOverride(
                        LocalStackContainer.Service.SQS).toString());
        registry.add("spring.cloud.aws.s3.path-style-access-enabled",
                () -> "true");
    }

    @Autowired
    S3Client s3;

    @Test
    void shouldWriteAndReadS3Object() {
        String bucket = "training-local-" +
                UUID.randomUUID().toString().substring(0, 8);
        String key = "documents/test.txt";
        String content = "Testcontainers with LocalStack";

        s3.createBucket(request -> request.bucket(bucket));
        s3.putObject(request -> request
                .bucket(bucket)
                .key(key),
                RequestBody.fromString(content, StandardCharsets.UTF_8));

        String readBack = s3.getObjectAsBytes(request -> request
                .bucket(bucket)
                .key(key))
                .asUtf8String();

        assertEquals(content, readBack);
    }
}
~~~

**Assumptions of the example:** the AWSpring S3 starter creates an `S3Client` bean in the `ApplicationContext`, properties match your AWSpring release, and the test context **does not start an SQS listener before the queue exists**. If the application has an `@SqsListener`, provision the queue **before the Spring context starts**, e.g. via a LocalStack init hook or test initializer. Creating the queue inside `@BeforeEach` may be too late for listener startup.

Additionally:

- The `latest` image tag is illustrative only. Pin a verified compatible LocalStack tag/digest in CI.
- Testcontainers imports/artifacts depend on major version; if using Testcontainers 2.x, update to that generation's API/docs.
- `@ServiceConnection` can be used in supported Spring Boot/Testcontainers versions, though AWSpring endpoints/properties must still align with your active integration.
- `@DynamicPropertySource` injects endpoints from the **actual running container** into the Spring context; never assume the mapped port is always 4566 on the host.
- `LocalStackContainer` lifecycle is managed by Testcontainers. If you construct extra SDK clients in tests, close them afterward.
- When tests run in parallel, generate unique bucket/queue names per test or isolate containers/contexts to prevent data collisions.

### 11.3. Provisioning Resources Before Context Startup

A specific challenge when testing Spring + SQS listeners is ordering:

~~~mermaid
flowchart TD
    A["Test starts"] --> B["LocalStack container ready"]
    B --> C["Create queues/buckets needed for startup"]
    C --> D["Spring ApplicationContext starts"]
    D --> E["SQS listener resolves queue"]
    E --> F["Run test"]
    F --> G["Cleanup"]
~~~

If testing only an S3 adapter, you can create the bucket inside `@Test`. When `@SqsListener` is active, many AWSpring releases resolve the queue during container startup, requiring queues to exist before the context starts. One approach is **LocalStack initialization hooks** in a compatible release: placing scripts under `/etc/localstack/init/ready.d/` inside the container to create queues before the test application boots.

Example initialization script for an emulated environment:

~~~sh
#!/bin/sh
set -eu

awslocal s3 mb s3://training-documents-local
awslocal sqs create-queue --queue-name training-events-local
~~~

When using init hooks, verify that your LocalStack version supports script mounting/copying, execute permissions, ready timing, and execution logs. Confirm the script completes before Spring context startup. Even if your AWSpring settings support auto-creating queues for listeners, control that policy to avoid divergence between local and production behavior.

### 11.4. What Should Integration Tests Verify?

| Flow | Typical checks |
| --- | --- |
| S3 | Bucket creation, `PutObject`/`GetObject`, content/metadata, missing key |
| SQS producer | Sending events, payload/attributes, queue URL/region |
| SQS consumer | JSON handling, acknowledgement, handler failure, and message redelivery |
| Spring wiring | S3/SQS beans use **test** endpoints and credentials |
| Isolation | Zero real AWS calls; independent of developer's local profile |
| Error handling | Timeouts, missing objects/queues, serialization errors within emulator scope |
| Retry/idempotency | Duplicate messages, slow responses, and safe side-effect handling |
| Startup lifecycle | Required queues exist before listener container starts |

Testcontainers manages **Docker/container lifecycles**. It does not automatically guarantee the Spring context uses the right endpoints if the app defines custom client beans or credential provider overrides. Include tests exercising the exact adapters and beans production uses.

## 12. Preventing Tests from Accidentally Calling Real AWS

This is the top requirement when using emulators in code capable of mutating data.

### 12.1. Configuration by Spring Profile

Clearly separate `local`, `test`, `staging`, and `prod`:

- `local`: LocalStack endpoints, test region, dummy credentials, test resources.
- `test`: dynamic endpoints supplied by Testcontainers; no dependency on manual LocalStack state.
- `staging`: real AWS sandbox or staging, dedicated IAM roles and resources.
- `prod`: standard AWS endpoints, IAM workload identities, production resources.

**Never enable `local` or `test` outside controlled environments.** Inspect `spring.profiles.active` and connection properties at startup; refuse to boot if a production deployment sees `localhost:4566`, `localstack`, or dummy credentials.

### 12.2. Do Not Use Developer Machine Credentials in Tests

If test code simply calls `S3Client.create()` without overriding endpoint and credentials, the default credentials provider chain can pick up the developer's AWS profile or the CI runner's IAM role. Prefer **`StaticCredentialsProvider` with dummy credentials** and **explicit LocalStack endpoints** in tests.

When Spring/AWSpring constructs clients, test configuration must override region, endpoint, and credentials for all test-used beans. Do not change a single property and assume every bean picks it up automatically.

### 12.3. Separating Emulator Tests from AWS Sandbox Tests

A test strategy should have two layers:

1. **LocalStack integration tests:** run frequently on developer laptops and CI, fast and independent of live cloud resources.
2. **AWS sandbox smoke tests:** run with a least-privilege test IAM role and environment-fixed resource ARNs, verifying real IAM/KMS/network/service semantics.

Never make production-account smoke tests the default in `mvn test` or `gradle test` when engineers intend to run local tests.

### 12.4. Practical Guardrails

Useful guardrails:

- In test configuration, endpoints must match a local/test-container allowlist.
- If tests use dummy credentials, require an explicit test endpoint; otherwise fail startup.
- For real AWS tests, verify the account via `GetCallerIdentity` against an allowlist **before** writing or deleting data.
- Test resource names/ARNs must carry dedicated prefixes/tags.
- CI must not inject production credentials into emulator test jobs.
- Never include emulated endpoints, dummy keys, or test init scripts in production images or configs.

## 13. Common LocalStack Connection Errors

### 13.1. Symptom Lookup Table

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Connection refused` to `localhost:4566` | Container not ready, wrong port, Java running in another container | `docker compose ps`, logs, port mapping, network-appropriate endpoint |
| `UnknownHostException` for `localstack` | Java running on host instead of Compose network | Use `localhost:4566` on host or configure matching DNS |
| `UnknownHostException` for `bucket.localhost` | S3 virtual-hosted style incompatible with emulator DNS | Enable path-style in tests or configure proper DNS |
| `NoSuchBucket` | Bucket not created, wrong name/region, or data reset | Call test endpoint with CLI, list buckets |
| `QueueDoesNotExist` | Queue not created; wrong name, queue URL, region, or endpoint | Run `GetQueueUrl` against the emulator itself |
| `Unable to load credentials` | SDK did not receive dummy test credentials; another provider overrides | Inspect Spring properties, beans, and SDK chain |
| `Unable to load region` | Client missing region; confusing CLI/LocalStack `AWS_DEFAULT_REGION` with SDK `AWS_REGION` | Set SDK test region explicitly |
| `SignatureDoesNotMatch` | Region/signing/endpoint/clock mismatch or request hit real AWS | Verify endpoint and client region |
| S3 passes, SQS fails | S3/SQS endpoints configured independently; queue URL unreachable | Inspect the actual client for each service |
| `@SqsListener` fails right at startup | Queue missing before Spring context; incompatible auto-creation/config | Provision before listener starts |
| Passes locally, fails in CI | Host/port changed, remote Docker daemon, unpinned image tag | Use Testcontainers endpoints, check Docker runtime |
| Passes on LocalStack, fails on AWS | IAM, KMS, SCP, VPC/network, throttling, or semantic differences | Sandbox smoke test with real role |

### 13.2. Step-by-Step Diagnostic Order

1. **Container:** Is LocalStack running/ready and are the required services supported in the current image?
2. **Network:** Is the JVM running on the host, in a Compose container, or in CI? Which endpoint is reachable from that exact process?
3. **Endpoint:** Are SDK/AWSpring beans actually targeting LocalStack or real AWS endpoints?
4. **Region/credentials:** Do clients have the test region and dummy credentials?
5. **Resources:** Have buckets, queues, tables, or secrets been created at the right endpoint and region?
6. **Serialization/lifecycle:** Are payload formats, listener containers, queue URLs, acknowledgements, and startup ordering right?
7. **Service semantics:** If errors happen only on real AWS, check IAM/KMS/networking, quotas, retries, and service-specific behavior.

Never "fix" connection issues by granting `AdministratorAccess` or copying real access keys into a local profile. If the emulator works while production fails, isolate which layer diverges first.

### 13.3. Never Log Secrets When Debugging

Enabling SDK HTTP or trace logging risks printing request/response headers, access tokens, or payloads. In tests, use **fake, non-sensitive** data. For Secrets Manager or services handling confidential data, verify log masking and never store real secrets in LocalStack fixtures.

## 14. Where Does LocalStack Differ from Real AWS?

An emulator can support an API while still differing from the cloud provider's full behavior:

| Difference area | Examples | Testing impact |
| --- | --- | --- |
| IAM/identity | Workload roles, STS, trust policies, SCPs, resource-based policies | LocalStack pass does not prove production permissions |
| KMS/encryption | Customer-managed keys, key policies, encryption context | Test on AWS sandbox when flows use real KMS |
| S3 behavior | Bucket addressing, multipart, consistency/edge cases, object versioning | Validate real use cases and large objects separately |
| SQS behavior | Long polling, visibility timeout, FIFO, DLQ/redrive, duplicate delivery | Design idempotency and test critical flows on real AWS |
| Networking | VPC endpoints, private DNS, proxies, TLS, regional latency | Local emulators cannot replace infrastructure tests |
| Quotas/throttling | Rate limits, throughput, and account/region quotas | Run controlled load/performance tests |
| Versions/APIs | Newer features available only on AWS or gated by LocalStack edition | Choose supported versions/editions and check release notes |
| Operations | CloudWatch metrics, CloudTrail, IAM auditing, HA, and recovery | Observe on real sandbox/production |

With SDK/AWSpring, **API surface parity** reduces integration test effort, yet it does not erase differences in permissions, deployment, cost, and managed service semantics.

## 15. A Sound Testing Workflow for a Multi-Cloud Module

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module also covers Azure and Google Cloud services. This LocalStack lesson demonstrates the **adapter → SDK client → test endpoint** pattern, which applies conceptually with other emulators as well.

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Local emulator | LocalStack by service and edition | Azurite for Azure Storage, dedicated emulators where available | Pub/Sub emulator, Firestore emulator, and per-service emulators |
| Spring client | AWSpring + AWS SDK Java v2 | Spring Cloud Azure + Azure SDK | Spring Cloud GCP + Google Cloud Java clients |
| Test configuration | Endpoint override + region + dummy credentials | Storage connection/endpoint + test credentials | Emulator host + appropriate test project/ADC |
| What must be checked on real cloud | IAM roles, resource policies, KMS, region/VPC | Managed Identity/RBAC, resource endpoints | Service accounts/IAM, project/location |

**Do not force a single shared endpoint configuration across every provider.** S3/SQS, Azure Blob Storage, and Google Cloud Storage have distinct APIs, resource models, and authentication mechanisms. Business code can share interfaces like `DocumentStore` or `EventPublisher`, while adapters and integration tests must respect each provider's differences.

### 15.1. Multi-Layered Testing Strategy

~~~mermaid
flowchart TD
    U["Unit tests<br/>Fake/mock adapter"] --> I["Integration tests<br/>LocalStack / emulator"]
    I --> S["Smoke tests<br/>AWS sandbox / Azure / GCP test project"]
    S --> O["Operational tests<br/>IAM, network, load, metrics, recovery"]
~~~

- **Unit tests** verify business logic quickly without Docker or cloud access.
- **Emulator integration tests** verify SDK wiring, serialization, and a realistic subset of operations.
- **Cloud sandbox smoke tests** verify identity, IAM, resources, and networking in the target environment.
- **Operational tests** validate timeouts, retries, concurrency, quotas, observability, and failure recovery.

Each layer answers a different question. Replacing all other layers with LocalStack leaves blind spots around IAM, secret security, and real cloud behavior.

## 16. Comprehensive Hands-On Exercise

**Scenario:** Build a Spring Boot service `document-service` that accepts text content, stores files in bucket `training-documents-local`, and publishes `DocumentUploaded` events to queue `training-events-local`. A consumer receives events to verify the newly created object.

### Task A — Start and Prepare the Environment

1. Write a Docker Compose file running LocalStack with the edge port bound only to loopback.
2. Start the container and verify readiness.
3. Use the AWS CLI with dummy credentials and `--endpoint-url` to create the bucket and queue.
4. Record the right endpoint for an application running **on the host** vs. **inside the Compose network**.
5. Explain why real access keys are unnecessary when running commands against the emulator.

### Task B — Call AWS SDK v2

1. Create an `S3Client` using `endpointOverride`, `Region.US_EAST_1`, test `StaticCredentialsProvider`, and path-style access.
2. Run a `PutObject → GetObject` round-trip, verifying returned bytes/string match the input.
3. Create an `SqsClient` to send a JSON event, receive the message, and call `DeleteMessage` with the receipt handle.
4. Try sending a message to a nonexistent queue; analyze the exception and the order for checking endpoint/region/resource.

### Task C — Integrate Spring Cloud AWS

1. Import a compatible AWSpring BOM and add the S3/SQS starters.
2. Create `application-local.yml` with dummy credentials, region, and per-service endpoints.
3. Implement `DocumentStorageAdapter` with `S3Template` and `DocumentEventPublisher` with `SqsTemplate`.
4. Implement `@SqsListener`, provision the queue before context startup, and process payloads idempotently.
5. Ensure the `local` profile is never activated in staging or production.

### Task D — Automate with Testcontainers

1. Move tests from manual LocalStack to `LocalStackContainer`.
2. Use `@DynamicPropertySource` to obtain live endpoints from Testcontainers instead of hard-coding host/port.
3. Ensure containers and resources are ready before Spring listeners start.
4. Run tests with unique buckets/queues per test run and clean up properly with the lifecycle.
5. Describe the differences between this test and an AWS sandbox smoke test using real IAM roles.

### Task E — Debug Intentional Failures

| Scenario | Questions to answer |
| --- | --- |
| App runs inside a Docker container yet uses `localhost:4566` | Which container does `localhost` point to? |
| S3 throws `UnknownHostException` for `bucket.localhost` | How are S3 addressing style and DNS behaving? |
| SQS listener reports the queue does not exist | Was the queue created before `ApplicationContext` startup? Which endpoint is the client using? |
| JVM has `AWS_PROFILE=prod-readonly` and tests only override region | How do you stop tests from accidentally calling real AWS? |
| LocalStack tests pass yet ECS returns 403 | How should IAM task role, bucket/queue policies, and KMS be checked? |
| CI runs tests against a remote Docker daemon | Why is `localhost:4566` unreliable, and what does Testcontainers provide? |

### Passing Criteria

Your work passes when:

- You can start LocalStack and provision emulated resources from scratch.
- S3 write/read and SQS send/receive/delete succeed via SDK v2.
- Spring Boot uses the intended AWSpring beans and `local`-profile endpoints/credentials.
- Integration tests provision their own endpoints without relying on fixed ports or developer AWS profiles.
- Configuration guardrails prevent test/local requests from affecting production.
- You identify at least three LocalStack limitations and outline a smoke test to run on an AWS sandbox.

## 17. Key Takeaways

**Setting up emulated AWS connectivity with LocalStack** relies on four components working together: **a ready emulator, the network-appropriate endpoint, a consistent region, and test-only dummy credentials**. Only then does verifying S3/SQS resources, AWS SDK clients, and Spring Cloud AWS abstractions make sense.

On the host, the endpoint is typically `http://localhost:4566`; inside a Compose network, `http://localstack:4566` can be used; with Testcontainers, obtain the endpoint from the container runtime. Emulated S3 often needs path-style access when virtual-hosted DNS is unavailable, and SQS needs the actual queue URL returned by the emulator. SQS listeners must have their resources provisioned before Spring context startup.

LocalStack makes integration testing fast and repeatable, yet **does not prove IAM/KMS, networking, quotas, or every production AWS behavior**. A solid engineering workflow combines unit tests, emulator integration tests, and least-privilege AWS sandbox smoke tests—building a strong foundation for upcoming lessons on storage, messaging, data, secrets, and Azure/Google Cloud integration.
