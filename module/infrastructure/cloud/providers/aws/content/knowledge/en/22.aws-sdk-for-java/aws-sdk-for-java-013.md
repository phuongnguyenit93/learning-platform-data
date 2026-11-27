# Testing SDK Code with Mocks, Custom Endpoints, and Test Accounts

> **Chapter:** AWS SDK for Java  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem across Region/AZ, IAM, VPC, compute, storage, databases, integration, and serverless; develop skills in selecting services and designing and deploying applications that are secure, observable, resilient, and cost-controlled.

A Java service receives requests to upload product images to **Amazon S3**, writes metadata to **DynamoDB**, and sends messages to **Amazon SQS**. If every unit test run called live AWS, tests would depend on internet connectivity, IAM, account quotas, resource state, and costs. A minor bug in code could create real buckets or messages; repeated test runs could leave orphaned resources behind.

**AWS SDK for Java 2.x** provides clients for AWS services while supporting testing at multiple levels:

- **Mock clients:** verify application logic without making HTTP requests.
- **HTTP stubs + custom endpoints:** verify serialization, protocol requests, SigV4 signing, and response parsing without calling AWS.
- **Local emulators/containers:** test service integrations in a reproducible development environment.
- **AWS sandbox/test accounts:** validate real IAM behavior, networking, quotas, and AWS service semantics.

No single test level completely replaces the others. Mocks confirm your code calls `putObject` with the expected arguments, yet cannot prove the request is signed properly; HTTP stubs inspect wire requests, yet cannot prove an IAM policy allows the action; LocalStack emulates many APIs, yet does not replace an integration run on real AWS.

This lesson uses **AWS SDK for Java 2.x**, JUnit 5, and S3/DynamoDB/SQS examples. Dependency versions are managed centrally per project; select SDK v2, JUnit, Mockito, WireMock, and Testcontainers versions tested against your current build.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose the right test tier: mock, HTTP stub, LocalStack/Testcontainers, or AWS test account.
2. Mock AWS service clients with Mockito and verify request/response/error behavior.
3. Configure clients with `endpointOverride`, Region, and test credentials to target an HTTP stub.
4. Inspect AWS Signature Version 4 (SigV4) at the request level without using real credentials.
5. Run integration tests with LocalStack/Testcontainers and understand emulator limitations.
6. Set up an AWS sandbox account, role, profile, Region, and account guard before running live tests.
7. Provision uniquely named test resources, clean up safely, bound costs, and avoid impacting production.
8. Test retries, timeouts, pagination, async clients, error handling, and client lifecycles.
9. Integrate tests into CI/CD without storing long-lived access keys in repositories.

## 2. Test Pyramid for AWS SDK

~~~mermaid
flowchart TB
    E2E["AWS sandbox integration tests\nFewer, run under strict control"]
    LOCAL["LocalStack / Testcontainers\nService integration locally"]
    HTTP["HTTP stub / WireMock\nEndpoint override + protocol"]
    UNIT["Unit tests / Mockito\nBusiness logic and interactions"]
    E2E --> LOCAL
    LOCAL --> HTTP
    HTTP --> UNIT
~~~

Each layer answers a distinct question:

| Tier | Question | Calls Live AWS? | Cost / Speed |
| --- | --- | --- | --- |
| **Unit + mock client** | Does the service invoke the SDK properly on success/failure? | No | Fast, low cost |
| **HTTP stub** | How does the SDK build HTTP requests, headers, bodies, and parse responses? | No | Fast, high control |
| **LocalStack/Testcontainers** | Do components work together over AWS-like APIs? | No live AWS; runs emulator | Needs Docker / local resources |
| **AWS test account** | Are real IAM, endpoints, quotas, service semantics, and networking right? | Yes | Slower, may incur charges |

**Practical rule:** test most business rules with unit tests; use HTTP stubs when protocol inspection matters; use emulators for suitable integration flows; reserve AWS sandbox tests for behavior only live AWS can confirm.

### 2.1. When Should You Not Mock the SDK?

If a test only asserts `verify(s3Client).putObject(...)`, it does not verify:

- Whether the SDK constructs the right HTTP request.
- Whether the request is signed with the right Region and service name.
- Whether JSON and headers serialize accurately.
- How response or error bodies deserialize into SDK exceptions.
- Whether custom endpoints, TLS, and retry policies behave as intended.

When those details matter, add an HTTP stub or integration test.

### 2.2. When Should You Not Call Live AWS?

Do not use an AWS sandbox for individual unit tests or suites running hundreds of times per commit. Such tests depend on IAM, account quotas, networking, service availability, and eventual consistency, and can generate charges. Run AWS integration tests in a dedicated stage with explicit resource lifecycles.

## 3. Preparing Dependencies for AWS SDK for Java 2.x

Use the **AWS SDK BOM** to align versions across modules. The Maven example below illustrates the dependency layout; replace **`YOUR_APPROVED_SDK_V2_VERSION`** with the v2 release approved and managed in your project's parent/POM.

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>YOUR_APPROVED_SDK_V2_VERSION</version>
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
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
  </dependency>
</dependencies>
~~~

Common test dependencies include:

- `org.junit.jupiter:junit-jupiter`
- `org.mockito:mockito-junit-jupiter`
- `com.github.tomakehurst:wiremock-standalone`
- `org.testcontainers:junit-jupiter`
- `org.testcontainers:localstack`

Include only the libraries you use. If the project already uses Spring Boot dependency management, check parent-managed versions before importing a second BOM to avoid dependency convergence conflicts.

### 3.1. Selecting AWS SDK v2

Examples in this lesson use v2 clients such as:

~~~java
S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

SDK v2 uses immutable request/response models and builder APIs. **Sync clients** such as `S3Client` and `DynamoDbClient` fit synchronous services; **async clients** such as `S3AsyncClient` return `CompletableFuture` and require testing completion and error paths separately.

Never mix `com.amazonaws...` imports from SDK v1 with `software.amazon.awssdk...` imports from SDK v2 in the same example. If a project still carries SDK v1, maintain a separate migration and testing plan for it.

## 4. Mocking Service Clients with Mockito

AWS SDK v2 service clients are interfaces, such as `S3Client`, `DynamoDbClient`, and `SqsClient`. Mockito can replace clients with mocks to test business logic without network calls.

### 4.1. Service Under Test

~~~java
public final class ProductImageService {
    private final S3Client s3;
    private final String bucket;

    public ProductImageService(S3Client s3, String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(String key, byte[] bytes) {
        PutObjectResponse response = s3.putObject(
            PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("image/png")
                .build(),
            RequestBody.fromBytes(bytes)
        );
        return response.eTag();
    }
}
~~~

This minimal service illustrates the pattern. Real applications may validate keys, enforce size limits, set metadata/checksums/encryption, and handle idempotency.

### 4.2. Testing Success and Verifying the Request

~~~java
@ExtendWith(MockitoExtension.class)
class ProductImageServiceTest {
    @Mock
    S3Client s3;

    @Test
    void uploadsImageToExpectedBucketAndKey() {
        when(s3.putObject(
            any(PutObjectRequest.class),
            any(RequestBody.class)
        )).thenReturn(
            PutObjectResponse.builder().eTag("test-etag").build()
        );

        ProductImageService service =
            new ProductImageService(s3, "test-images");

        String etag = service.upload("products/42.png",
            new byte[] {1, 2, 3});

        assertEquals("test-etag", etag);

        ArgumentCaptor<PutObjectRequest> request =
            ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(s3).putObject(request.capture(), any(RequestBody.class));

        assertEquals("test-images", request.getValue().bucket());
        assertEquals("products/42.png", request.getValue().key());
        assertEquals("image/png", request.getValue().contentType());
    }
}
~~~

Mockito/JUnit imports and static matchers/assertions are omitted to keep focus on the test. `RequestBody` is SDK v2's request body abstraction; to verify exact byte payloads, test input preparation in a separate adapter layer or use an HTTP stub to inspect the actual wire body.

### 4.3. Testing Error Paths

~~~java
@Test
void propagatesAccessDeniedFromS3() {
    when(s3.putObject(
        any(PutObjectRequest.class),
        any(RequestBody.class)
    )).thenThrow(
        S3Exception.builder()
            .statusCode(403)
            .message("AccessDenied")
            .build()
    );

    ProductImageService service =
        new ProductImageService(s3, "test-images");

    assertThrows(S3Exception.class,
        () -> service.upload("products/42.png", new byte[] {1}));
}
~~~

This test verifies that the service propagates the exception to its caller. If the application applies exception translation or retry policies, test that behavior at the application boundary—for instance, confirming 403 does not retry, throttling retries per policy, and validation errors map to appropriate domain errors.

### 4.4. Mocks Should Not Over-Verify Implementation Details

Avoid asserting every getter, builder call, or non-contract interaction order. Tests should assert **business outcomes and meaningful contract interactions**. Overly brittle mock verifications break on minor refactors even when behavior stays identical.

## 5. HTTP Stubs: Inspecting SDK Requests Without Calling AWS

Mocking clients bypasses the SDK's HTTP pipeline. **WireMock** spins up a local HTTP server to inspect the actual requests sent by AWS SDK v2.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant SDK as AWS SDK v2 client
    participant W as WireMock server
    T->>W: Start local HTTP server
    T->>SDK: Build client with local endpoint and test credentials
    T->>SDK: putObject(...)
    SDK->>W: Signed HTTP request
    W-->>SDK: Stubbed HTTP response
    SDK-->>T: SDK response model
    T->>W: Verify path, headers and body
~~~

### 5.1. Building an S3 Client with a Custom Endpoint

~~~java
WireMockServer wireMock = new WireMockServer(options().dynamicPort());
wireMock.start();

S3Client s3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create(wireMock.baseUrl()))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key"
            )
        )
    )
    .serviceConfiguration(
        S3Configuration.builder()
            .pathStyleAccessEnabled(true)
            .build()
    )
    .build();
~~~

These credentials are **dummy values solely for signing requests to the local server**. The SDK still requires a Region to construct the SigV4 signing scope even when targeting a non-AWS endpoint. `endpointOverride` changes the destination address; it does not disable signing.

`pathStyleAccessEnabled(true)` helps with certain S3-compatible test servers because requests use `/bucket/key` paths. Keep this setting strictly for test endpoints; never apply it arbitrarily to production S3 endpoints unless service requirements dictate it.

### 5.2. Stubbing PUT and Verifying SigV4 Headers

~~~java
stubFor(put(urlEqualTo("/test-images/products/42.png"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("ETag", "\"wiremock-etag\"")));

try (S3Client s3 = buildS3Client(wireMock.baseUrl())) {
    PutObjectResponse response = s3.putObject(
        PutObjectRequest.builder()
            .bucket("test-images")
            .key("products/42.png")
            .contentType("image/png")
            .build(),
        RequestBody.fromBytes(new byte[] {1, 2, 3})
    );

    assertEquals("\"wiremock-etag\"", response.eTag());
}

verify(putRequestedFor(
    urlEqualTo("/test-images/products/42.png")
).withHeader(
    "Authorization",
    matching("AWS4-HMAC-SHA256.*")
));
~~~

This assumes `buildS3Client` creates the client as in Section 5.1 and WireMock is running. WireMock can assert request paths, headers, query parameters, and bodies; verify critical business headers as well if your application depends on them.

**Never assert the entire `Authorization` signature as a fixed string**, since timestamps, payload hashes, and signing behavior vary. Assert the scheme and credential scope at the right level; verify full cryptographic signatures only when your test harness includes a dedicated SigV4 verifier.

### 5.3. Closing Servers and Clients Properly

~~~java
@AfterEach
void tearDown() {
    if (s3 != null) {
        s3.close();
    }
    if (wireMock != null) {
        wireMock.stop();
    }
}
~~~

In real test suites, use JUnit extensions or `try/finally` so cleanup still runs when assertions fail. If creating servers/clients in `@BeforeAll`, match lifecycle teardown in `@AfterAll`; never leave open ports or threads lingering between test runs.

## 6. Custom Endpoints, Regions, and Credentials

### 6.1. Three Required Settings When Using endpointOverride

A client targeting a test endpoint typically needs:

1. **Endpoint URI:** HTTP/HTTPS address of WireMock, LocalStack, or a service emulator.
2. **Region:** the Region used in the signing scope; a local endpoint does not eliminate the need for a Region.
3. **Credentials provider:** dummy credentials or a test provider; the SDK needs credentials to sign requests whenever signing is enabled.

Example:

~~~java
AwsCredentialsProvider testCredentials =
    StaticCredentialsProvider.create(
        AwsBasicCredentials.create("test-key", "test-secret")
    );

DynamoDbClient dynamo = DynamoDbClient.builder()
    .endpointOverride(URI.create("http://localhost:4566"))
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(testCredentials)
    .build();
~~~

This pattern fits local emulators with a fixed endpoint. With WireMock, bind a dynamic port and pass the live server's URI. **Never use these test credentials against a real AWS endpoint**; they are not valid IAM credentials.

### 6.2. Endpoint Override Does Not Alter All Networking Settings

`endpointOverride` sets the base URI for the service client. Applications must still account for:

- HTTP/HTTPS scheme and TLS truststores.
- Path-style vs. virtual-hosted-style addressing, especially with S3-compatible endpoints.
- The Region/signing Region expected by the mocked endpoint.
- Proxies, DNS, connection timeouts, and socket timeouts.
- Service-specific endpoint rules and client configuration.

Never include local endpoints in production configs. Isolate configuration classes or profiles clearly so a test endpoint can never be accidentally activated in production.

### 6.3. Using Test Credentials Safely

- Use fake credentials in WireMock and LocalStack tests.
- For AWS sandboxes, use IAM roles/SSO/assume-role or CI workload identity.
- Never commit access keys/secret keys into Git, sample `.env` files with live values, test reports, or logs.
- Never put real credentials into `StaticCredentialsProvider` just to make tests "easier to run".
- Avoid printing full `Authorization` request headers since they contain credential scopes and signatures.

## 7. Testing the DynamoDB Protocol with HTTP Stubs

DynamoDB uses a JSON protocol over HTTP POST; the SDK sets a target header identifying the operation. WireMock can verify the payload and return stubbed responses.

~~~java
stubFor(post(urlEqualTo("/"))
    .withHeader("X-Amz-Target",
        equalTo("DynamoDB_20120810.GetItem"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/x-amz-json-1.0")
        .withBody("""
            {
              "Item": {
                "pk": {"S": "PRODUCT#42"},
                "name": {"S": "Keyboard"}
              }
            }
            """)));

try (DynamoDbClient client = DynamoDbClient.builder()
        .endpointOverride(URI.create(wireMock.baseUrl()))
        .region(Region.US_EAST_1)
        .credentialsProvider(testCredentials)
        .build()) {

    GetItemResponse response = client.getItem(GetItemRequest.builder()
        .tableName("catalog-test")
        .key(Map.of("pk", AttributeValue.builder()
            .s("PRODUCT#42")
            .build()))
        .build());

    assertEquals("Keyboard",
        response.item().get("name").s());
}
~~~

Text blocks require Java 15 or newer; on Java 11, replace with concatenated strings or resource files. Stubs must match the exact protocol headers and response format of the target operation; valid JSON shaped for a different API is insufficient.

### 7.1. Testing Service Errors

You can return HTTP 400/500 with matching error headers/bodies to verify the SDK constructs `DynamoDbException`, populates error codes, and executes retries. AWS JSON protocols use specific error response shapes; check real service/API documentation rather than assuming all AWS services emit identical error bodies.

## 8. What HTTP Stubs Can and Cannot Verify

| Can Verify | Cannot Prove with Stubs Alone |
| --- | --- |
| HTTP method, path, query, headers | Real IAM policies permitting the operation |
| Request serialization and response parsing | Service quotas and account limits |
| Whether SigV4 headers are generated | Signature acceptance by AWS for real credentials and clock |
| SDK handling of status/error codes | Full AWS service semantics |
| Request retries under stubbed scenarios | Exact production AWS throttling/retry behavior |
| Endpoint override and Region in client config | Real DNS, VPC, security groups, and PrivateLink |

WireMock is an **HTTP contract test**, not a full AWS simulator. Use LocalStack or a sandbox account when testing deeper service behavior.

## 9. LocalStack and Testcontainers

**LocalStack** emulates many AWS APIs for local and CI integration testing. **Testcontainers** manages container lifecycles per test suite, making test environments reproducible and self-cleaning.

~~~mermaid
flowchart LR
    J["JUnit 5 test"] --> TC["Testcontainers"]
    TC --> LS["LocalStack container"]
    J --> SDK["AWS SDK v2 client"]
    SDK -->|"endpointOverride"| LS
    LS --> S3["S3 API"]
    LS --> DDB["DynamoDB API"]
    LS --> SQS["SQS API"]
~~~

### 9.1. Starting a LocalStack Container

~~~java
@Testcontainers
class S3LocalStackIntegrationTest {
    @Container
    static final LocalStackContainer localStack =
        new LocalStackContainer(
            DockerImageName.parse("localstack/localstack:3.8.1")
        ).withServices(LocalStackContainer.Service.S3);

    @Test
    void uploadsAndReadsObject() {
        AwsCredentialsProvider credentials =
            StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                    localStack.getAccessKey(),
                    localStack.getSecretKey()
                )
            );

        try (S3Client s3 = S3Client.builder()
                .endpointOverride(localStack.getEndpointOverride(
                    LocalStackContainer.Service.S3))
                .region(Region.of(localStack.getRegion()))
                .credentialsProvider(credentials)
                .serviceConfiguration(
                    S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build()
                )
                .build()) {

            String bucket = "it-" +
                UUID.randomUUID().toString().replace("-", "");
            String key = "sample.txt";
            byte[] expected = "hello from test".getBytes(
                StandardCharsets.UTF_8);

            s3.createBucket(CreateBucketRequest.builder()
                .bucket(bucket)
                .build());

            try {
                s3.putObject(PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build(),
                    RequestBody.fromBytes(expected));

                byte[] actual = s3.getObjectAsBytes(
                    GetObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build()
                ).asByteArray();

                assertArrayEquals(expected, actual);
            } `finally` {
                s3.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
                s3.deleteBucket(DeleteBucketRequest.builder()
                    .bucket(bucket)
                    .build());
            }
        }
    }
}
~~~

This illustrates the Testcontainers LocalStack module API; imports are omitted. Pin an organization-tested image tag instead of mutable tags, and verify API calls against your project's Testcontainers version. The bucket is created per test and cleaned up in `finally`.

### 9.2. What Does LocalStack Verify?

- Many service API flows execute without requiring an AWS account.
- SDK endpoint overrides, request serialization, and client wiring work against a simulated endpoint.
- Tests can create, read, update, and delete resources in an isolated container.
- CI runs integration tests without granting production AWS credentials.

### 9.3. LocalStack Does Not Replace Live AWS

LocalStack is an emulator, not an AWS Region. Some APIs, IAM semantics, service limits, eventual consistency, event delivery, networking, KMS/encryption, performance, and edge cases differ from AWS. **Tests passing on LocalStack do not prove production IAM, networking, or service configurations are valid.**

Use an AWS sandbox for behaviors that emulators do not fully reproduce or that impact production decisions.

### 9.4. Disciplined Testcontainers Usage

- Pin image versions and verify image sources.
- Never share container state across tests needing isolation.
- Use dynamic host ports; never hardcode fixed local ports outside container configuration.
- Wait for service health/readiness before constructing clients.
- Close SDK clients and let Testcontainers stop containers after the suite finishes.
- Separate integration tests from default unit test tasks if Docker is not installed on every developer workstation.

## 10. AWS Sandbox/Test Accounts: Verifying Real Behavior

A **sandbox account** is an AWS account dedicated to development and integration testing, isolated from production with scoped permissions and resource limits. It verifies things mocks and emulators cannot prove:

- IAM role/policy and resource-based policies.
- Real Region availability, service endpoints, and networking.
- Quotas, throttling, and service-specific semantics.
- Real eventual consistency, retries, pagination, and lifecycles.
- KMS, encryption, VPC endpoints, DNS, and cross-service permissions.

### 10.1. Account Isolation Principles

Before running tests:

1. Explicitly designate the **AWS test account ID** and allowed Regions.
2. Use a dedicated test role with least privilege scoped by resource/prefix.
3. Configure budgets, billing alerts, and appropriate quotas.
4. Never allow the test role to assume production roles or touch production data.
5. Enable CloudTrail and record change/run IDs for traceability.
6. Use synthetic or approved test data; never copy PII or secrets into a sandbox casually.

Naming an account **sandbox** does not automatically make it safe. **Account IDs, role trust policies, SCPs, IAM policies, network boundaries, and data governance** define real isolation.

### 10.2. Credentials for Local Development

Use an AWS CLI profile configured via SSO or another organization-approved mechanism:

~~~bash
aws sso login --profile aws-sdk-test
aws sts get-caller-identity --profile aws-sdk-test
~~~

Run tests targeting the designated profile:

~~~bash
AWS_PROFILE=aws-sdk-test AWS_REGION=ap-southeast-1 \
  mvn -Paws-integration verify
~~~

This shell example uses POSIX syntax; on Windows PowerShell, set environment variables using PowerShell syntax. Profiles must be configured beforehand in the AWS CLI—never commit credentials inside project files.

In CI, prefer **OIDC/workload identity or short-lived assume-role sessions** over long-lived access keys. Never place access keys or secret keys in repositories, Docker images, or pipeline logs.

### 10.3. Account Guard Using STS

Before creating any resource, verify caller identity and abort if the account does not match:

~~~java
public final class AwsTestAccountGuard {
    private AwsTestAccountGuard() {}

    public static void requireExpectedAccount(
            StsClient sts,
            String expectedAccountId) {

        if (expectedAccountId == null ||
                !expectedAccountId.matches("[0-9]{12}")) {
            throw new IllegalStateException(
                "AWS_TEST_ACCOUNT_ID must be a 12-digit account ID");
        }

        String actualAccountId =
            sts.getCallerIdentity().account();

        if (!expectedAccountId.equals(actualAccountId)) {
            throw new IllegalStateException(
                "Refusing AWS integration test in unexpected account");
        }
    }
}
~~~

Tests should invoke the guard at the very beginning of setup. Never log access keys, secrets, session tokens, or full caller identity objects unnecessarily. An account guard is an **extra safety check**; IAM and SCPs must still block unauthorized actions.

### 10.4. Creating Clients for the Test Account

~~~java
Region region = Region.of(
    System.getenv().getOrDefault("AWS_REGION", "ap-southeast-1")
);

AwsCredentialsProvider credentials =
    ProfileCredentialsProvider.create("aws-sdk-test");

try (StsClient sts = StsClient.builder()
        .region(region)
        .credentialsProvider(credentials)
        .build()) {
    AwsTestAccountGuard.requireExpectedAccount(
        sts, System.getenv("AWS_TEST_ACCOUNT_ID"));
}

S3Client s3 = S3Client.builder()
    .region(region)
    .credentialsProvider(credentials)
    .build();
~~~

In CI, swap the profile provider for a provider matching the pipeline's role/session. Inject SDK clients into test fixtures and close them once the test suite completes.

## 11. Test Resources: Unique Naming, Cleanup, and Cost Control

### 11.1. Every Test Run Needs Its Own Namespace

Never use fixed bucket, table, or queue names across concurrent test jobs. Generate a random suffix or run ID:

~~~java
String runId = UUID.randomUUID()
    .toString()
    .replace("-", "")
    .substring(0, 12);

String bucketName = "sdk-it-" + runId;
String tableName = "sdk-it-catalog-" + runId;
String queueName = "sdk-it-events-" + runId;
~~~

S3 bucket names must follow global naming rules and contain no uppercase letters; verify naming constraints for each service. For DynamoDB and SQS, obey length and allowed-character limits for resource names.

### 11.2. Cleanup with finally

~~~java
String bucket = createTestBucket(s3);
try {
    uploadFixture(s3, bucket);
    assertObjectCanBeRead(s3, bucket);
} finally {
    deleteTestObjects(s3, bucket);
    deleteTestBucket(s3, bucket);
}
~~~

Do not rely solely on `@AfterEach` if a test process might be killed or a runner disconnects. In sandbox accounts, add **resource tags** with run ID, owner, and TTL/expiry, paired with a scheduled janitor to locate and remove orphaned test resources within an allowlist.

### 11.3. Clean Up Resources According to Service Semantics

| Resource | Before Deleting | Notes |
| --- | --- | --- |
| **S3 bucket** | Delete objects and multipart uploads; check versioning | Versioned buckets require deleting object versions and delete markers |
| **DynamoDB table** | Wait for creation to finish; delete table after test | Deletion is asynchronous; use a waiter if subsequent steps require confirmation |
| **SQS queue** | Stop producers/consumers, delete queue | Deleting affects queued messages; use dedicated test queues only |
| **SNS topic** | Remove subscriptions if needed, then delete topic | Check subscription and resource dependencies |
| **Lambda function** | Stop invocations and delete test function/roles if created | Check log groups, layers, and event source mappings |

### 11.4. Budgets and Test Limits

- Keep service quotas low/sufficient and bound concurrency.
- Never run large load tests in a default sandbox.
- Bound resource lifetimes and maximum concurrent test resources.
- Monitor cost allocation tags and budget alerts.
- Use small test payloads; avoid uploading huge files or seeding millions of items unless covered by a dedicated test plan.
- Separate compute/network-heavy tests from routine pull request pipelines.

## 12. Testing SQS and DynamoDB at the Client Level

### 12.1. Mocking SQS sendMessage

~~~java
@Test
void sendsOrderEventToConfiguredQueue() {
    when(sqs.sendMessage(any(SendMessageRequest.class)))
        .thenReturn(SendMessageResponse.builder()
            .messageId("message-test-1")
            .build());

    OrderEventPublisher publisher =
        new OrderEventPublisher(sqs, "https://sqs.test/queue/orders");

    String messageId = publisher.publish(
        new OrderCreatedEvent("order-42"));

    assertEquals("message-test-1", messageId);

    ArgumentCaptor<SendMessageRequest> request =
        ArgumentCaptor.forClass(SendMessageRequest.class);
    verify(sqs).sendMessage(request.capture());
    assertEquals("https://sqs.test/queue/orders",
        request.getValue().queueUrl());
    assertTrue(request.getValue().messageBody().contains("order-42"));
}
~~~

This assumes `OrderEventPublisher` serializes the event to JSON. Tests can verify queue URL, message body, attributes, and FIFO fields (`MessageGroupId`, `MessageDeduplicationId`) when targeting a FIFO queue.

### 12.2. Mocking DynamoDB Conditional Writes

~~~java
when(dynamo.putItem(any(PutItemRequest.class)))
    .thenReturn(PutItemResponse.builder().build());

repository.createIfAbsent("PRODUCT#42", "Keyboard");

ArgumentCaptor<PutItemRequest> request =
    ArgumentCaptor.forClass(PutItemRequest.class);
verify(dynamo).putItem(request.capture());

assertEquals("catalog-test", request.getValue().tableName());
assertEquals("attribute_not_exists(pk)",
    request.getValue().conditionExpression());
~~~

This illustrates a repository contract; attribute maps and expression names must match your real schema. Beyond success, test `ConditionalCheckFailedException` to ensure duplicate items map to business conflicts rather than infinite system retries.

### 12.3. Testing Serialization Independently of AWS Clients

Do not tie cache or serialization tests to mocked SDKs. For events or DynamoDB items:

- Test object → JSON/attribute map.
- Test JSON/attribute map → object.
- Test missing/unknown fields and schema versions.
- Test Unicode, empty values, timestamps, and numeric precision.
- Test compatibility when older and newer app versions run side by side during rolling deployments.

Isolate serialization into plain Java components so unit tests need no AWS clients.

## 13. Pagination, Waiters, and Eventual Consistency

### 13.1. Testing That Paginators Process All Pages

SDK v2 provides paginators for many operations. S3 example:

~~~java
List<S3Object> objects =
    s3.listObjectsV2Paginator(ListObjectsV2Request.builder()
            .bucket("test-images")
            .prefix("products/")
            .build())
        .contents()
        .stream()
        .toList();
~~~

Tests should simulate multi-page datasets and verify the application does not read only page 1. With an HTTP stub, return `IsTruncated=true` and `NextContinuationToken` on page 1, then verify the next request passes that token. With a mock client, stub sequential responses and verify subsequent calls.

### 13.2. Waiters Instead of Fixed Sleeps

Several AWS APIs complete asynchronously: creating tables, updating bucket policies, deploying functions, or deleting resources. SDK **waiters** poll state until the resource matches the desired condition or times out.

Never write:

~~~java
Thread.sleep(30_000);
assertTableExists();
~~~

Fixed sleeps slow down tests and still fail to guarantee readiness. Use a waiter or bounded polling with backoff that inspects real state.

### 13.3. Eventual Consistency in Tests

Some service APIs and workflows propagate state asynchronously. Tests should:

- Poll for an explicit target condition rather than waiting a guessed duration.
- Enforce clear deadlines and report the final observed state on timeout.
- Avoid immediately asserting that a newly published event has already reached every consumer.
- Distinguish service eventual consistency from missing IAM permissions or network failures.

Never add infinite retries to paper over flaky tests; bound attempts and log request IDs/statuses on failure.

## 14. Testing AWS SDK Async Clients

Async clients return `CompletableFuture`; tests must verify completion, exceptions, and timeouts.

### 14.1. Testing Successful Completion

~~~java
CompletableFuture<PutObjectResponse> future =
    s3Async.putObject(
        PutObjectRequest.builder()
            .bucket("test-images")
            .key("async/sample.txt")
            .build(),
        AsyncRequestBody.fromBytes(
            "async test".getBytes(StandardCharsets.UTF_8))
    );

PutObjectResponse response =
    future.get(5, TimeUnit.SECONDS);

assertNotNull(response.eTag());
~~~

In unit tests, mock `S3AsyncClient` and return `CompletableFuture.completedFuture(...)`. In HTTP/LocalStack tests, enforce a finite timeout so suites never hang indefinitely.

### 14.2. Testing Exception Paths

~~~java
CompletableFuture<PutObjectResponse> failed =
    CompletableFuture.failedFuture(
        S3Exception.builder()
            .statusCode(403)
            .message("AccessDenied")
            .build()
    );

when(s3Async.putObject(
    any(PutObjectRequest.class),
    any(AsyncRequestBody.class)
)).thenReturn(failed);

CompletionException error = assertThrows(
    CompletionException.class,
    () -> service.uploadAsync("private/file.txt", new byte[] {1})
        .join()
);
~~~

`join()` wraps async exceptions in `CompletionException`; `get()` throws `ExecutionException`. Tests should verify the **root cause** per API contract rather than coupling tightly to a wrapper if the application unwraps exceptions.

### 14.3. Cancellation and Timeouts

- Use timeouts on `get` or in the test framework so suites cannot hang.
- Test cancellation if the application exposes cancel semantics.
- Never assume a caller-side timeout means the request never reached AWS or never executed.
- For write operations, outcomes may be uncertain; require idempotency keys or reconciliation before retrying.
- Close async clients and event-loop resources cleanly at lifecycle end.

## 15. Testing Retries, Timeouts, and Error Handling

### 15.1. Classify Errors Before Retrying

| Error | Typical Appropriate Behavior |
| --- | --- |
| **Throttling / `TooManyRequests`** | Bounded retry with backoff and jitter |
| **Transient 5xx / service unavailable** | SDK standard retry strategy retries per service/error classification |
| **`AccessDenied` / Invalid credentials** | Do not retry repeatedly; fix IAM/credentials |
| **Validation / malformed request** | Do not retry the same request |
| **`ResourceNotFound`** | Usually do not retry unless deliberately awaiting eventual creation |
| **Timeout after write** | Outcome may be unknown; check idempotency/reconciliation before retrying |

AWS SDK v2 has built-in retry strategies; defaults and tuning options depend on SDK version and client. Check your SDK version's docs and set **max attempts, API call timeout, and attempt timeout** to match your latency budget. Never blindly retry every exception.

### 15.2. Testing Retries with an HTTP Stub

WireMock can return HTTP 503 on the first few calls and HTTP 200 on a later call. Tests verify the SDK/application retries within configured limits and eventually receives the successful response. Keep in mind:

- The SDK only retries errors classified as retryable by its strategy.
- Backoff applies jitter; never assert millisecond-exact timing.
- Assert primarily on total request count and final outcome.
- Keep attempt counts small so tests stay fast and deterministic.
- Never rely on a single stub test to prove every nuance of live AWS retry behavior.

### 15.3. API Call Timeout vs. Attempt Timeout

Distinguish:

- **Attempt timeout:** bounds a single HTTP attempt.
- **API call timeout:** bounds total operation duration, including retries and backoff.

If the caller's overall deadline is 2 seconds while the SDK allows 3 attempts, configure timeouts so the SDK finishes before the deadline or propagates cancellation/timeouts cleanly. Otherwise, the upstream request expires while the SDK keeps working in the background.

### 15.4. Never Retry Side Effects Blindly

A `PutObject` or `SendMessage` timeout does not always prove AWS never executed the action. For business operations such as charging payments or creating orders:

- Use idempotency keys or deterministic resource identifiers where supported by the API.
- Query current state before re-sending.
- Design idempotent message consumers.
- Separate transport/connection errors from committed business outcomes.

## 16. Client Lifecycle, Thread Safety, and Dependency Injection

AWS SDK v2 service clients are designed to be **thread-safe and reusable**. Normally, build a client once per application lifecycle rather than creating one on every request.

~~~mermaid
flowchart TD
    APP["Application startup"] --> CFG["Build SDK clients once"]
    CFG --> S3["Shared S3Client"]
    CFG --> DDB["Shared DynamoDbClient"]
    CFG --> SQS["Shared SqsClient"]
    S3 --> REQ["Concurrent application requests"]
    DDB --> REQ
    SQS --> REQ
    REQ --> SHUT["Application shutdown"]
    SHUT --> CLOSE["Close clients / resources"]
~~~

### 16.1. What to Verify

- Clients are built with the right Region, credentials provider, endpoint, and timeouts.
- The application closes clients and resources on shutdown.
- New clients are not instantiated inside per-request methods.
- Mutable request builders are never shared across threads.
- Async client event loops and HTTP connection pools are managed cleanly.
- Mocked clients in tests are reset/isolated; never share mutable Mockito stubbing across parallel tests.

### 16.2. Dependency Injection

Inject service clients via constructors or factories/providers. That allows:

- Unit tests to pass mocked clients.
- HTTP contract tests to pass clients with endpoint overrides.
- LocalStack tests to pass clients pointing at containers.
- Production wiring to build clients with default credential chains and endpoints.

Never let business services read environment variables or build AWS clients directly inside business methods; doing so makes controlling endpoints, Regions, and credentials in tests difficult.

## 17. Separating Integration Tests in Builds and CI/CD

Unit tests should run on every commit. Tests requiring Docker or an AWS account belong in a **separate test phase or profile** so developers do not accidentally call live AWS during default test runs.

### 17.1. Test Naming Conventions

Simple convention:

| Type | Naming Convention | Environment |
| --- | --- | --- |
| Unit | `*Test.java` | Mocks, no Docker/AWS needed |
| HTTP contract | `*ContractTest.java` | Local WireMock |
| Emulator integration | `*LocalStackIT.java` | Docker / Testcontainers |
| AWS integration | `*AwsIT.java` | Sandbox account / role |

You can also use JUnit tags such as `unit`, `localstack`, and `aws-integration` to select suites. Never let AWS integration tests run inside every developer's default build profile.

### 17.2. Maven Failsafe Profile (Illustrative)

~~~xml
<profiles>
  <profile>
    <id>aws-integration</id>
    <build>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-failsafe-plugin</artifactId>
          <executions>
            <execution>
              <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
              </goals>
              <configuration>
                <includes>
                  <include>**/*AwsIT.java</include>
                </includes>
              </configuration>
            </execution>
          </executions>
        </plugin>
      </plugins>
    </build>
  </profile>
</profiles>
~~~

This merely illustrates profile separation; plugin versions and test filters must match your existing parent build. Unit tests still run separately; `mvn -Paws-integration verify` should run only in pipelines/jobs with proper account guards and credentials.

### 17.3. Pipeline Stages

~~~mermaid
flowchart TD
    PR["Pull request"] --> UNIT["Unit tests / Mockito"]
    UNIT --> HTTP["WireMock contract tests"]
    HTTP --> LOCAL["LocalStack tests (Docker)"]
    LOCAL --> BUILD["Package / static checks"]
    BUILD --> APPROVAL["Protected integration stage"]
    APPROVAL --> ROLE["Assume sandbox role"]
    ROLE --> GUARD["STS account + Region guard"]
    GUARD --> AWSIT["Small AWS integration suite"]
    AWSIT --> CLEAN["Cleanup + report resources"]
~~~

A safe pipeline:

1. Unit and HTTP contract tests run with zero AWS credentials.
2. LocalStack suites run on Docker-enabled runners.
3. AWS integration jobs run in a protected stage using OIDC/assume-role.
4. The STS guard verifies the account ID and Region allowlist before creating resources.
5. Tests tag resources with a run ID, clean up in `finally`, and emit a resource report.
6. A janitor job locates any orphaned sandbox resources by tag/expiry.

### 17.4. Never Let Local Profiles Point to Live AWS by Mistake

For endpoint tests:

- Use fake credentials and an explicitly passed local endpoint.
- Assert the URI host matches `localhost`, loopback, or the expected container hostname.
- Never fall back to the default AWS endpoint if a test endpoint property is missing.
- Isolate test configuration classes/profiles and fail fast when required test properties are absent.

For AWS sandboxes:

- Never enable local endpoint overrides.
- Never use fake credentials.
- Enforce the account guard and an allowlisted Region.
- Never rely on an ambiguous `default` profile on CI runners.

## 18. Troubleshooting Common Test Failures

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| **`Unable to load credentials`** | Missing valid profile/role/credentials provider | Check SSO login, profile, CI identity, and credential chain |
| **`The security token included in the request is invalid`** | Expired session or invalid credentials | Refresh SSO/assume-role; never switch to hardcoded access keys |
| **`SignatureDoesNotMatch`** | Wrong Region, service signing scope, clock skew, or endpoint/path mismatch | Check Region, system clock, path-style, and canonical request |
| **`AccessDenied`** | Missing permissions in IAM identity/resource/KMS policy | Inspect CloudTrail and policies; do not retry infinitely |
| **`Connection refused`** | LocalStack/WireMock not started or wrong port | Wait for container readiness and use the exact dynamic endpoint |
| **`UnknownHost` / timeout** | DNS, VPC route, security group, proxy, or wrong endpoint | Check network path and endpoint host |
| **S3 bucket addressing mismatch** | Path-style vs. virtual-hosted-style mismatch with emulator | Configure S3 addressing on the test client |
| **DynamoDB target mismatch** | WireMock stub expects wrong `X-Amz-Target` | Verify operation name and request protocol |
| **`NoSuchBucket` / `ResourceNotFound`** | Fixture not created yet, wrong Region, or premature cleanup | Create resources before testing, use waiters and unique namespaces |
| **Throttling in sandbox** | Excess parallel test runs or low quotas | Cap concurrency, apply backoff, and narrow test scope |
| **Tests pass locally yet fail on AWS** | Emulator does not fully model IAM/network/service semantics | Run sandbox integration tests and compare CloudTrail/request IDs |
| **Flaky tests caused by sleep** | Eventual consistency or incomplete provisioning | Replace fixed sleeps with waiters/polling with deadlines |
| **Leftover resources after tests** | Process killed before cleanup or async deletion | Use run ID tags, a janitor job, and deletion waiters |
| **Client threads fail to exit** | Client or HTTP transport never closed | Manage client lifecycle with `try-with-resources` or DI shutdown |

### 18.1. Checking SigV4 in Order

When AWS rejects a request for an invalid signature:

1. Confirm the client uses the intended Region.
2. Verify the credentials provider returns an unexpired session.
3. Synchronize the runner's system clock.
4. Check endpoint, `Host` header, path-style settings, and proxy rewrites.
5. Read error code/request ID from the response and CloudTrail if logged.
6. Avoid printing `Authorization` headers or session tokens in CI output.

## 19. Case Study: Testing an S3 → DynamoDB → SQS Flow

### 19.1. Context

A product image upload API:

~~~text
1. Upload image bytes to S3
2. Save product image metadata in DynamoDB
3. Publish ProductImageUploaded event to SQS
4. Return image key and event/message reference
~~~

Steps can partially succeed—for instance, S3 upload finishes while the DynamoDB write fails, or DynamoDB commits while the SQS publish times out. Tests must validate both behavior and the recovery contract.

### 19.2. Layered Test Matrix

| Test | Tool | Primary Assertion |
| --- | --- | --- |
| Service validates file type/size | JUnit | Rejects invalid input before calling SDK |
| S3 upload passes right bucket/key/content type | Mockito | Accurate request model |
| DynamoDB conditional write | Mockito | Condition expression and conflict mapping |
| SQS event body/attributes | Mockito | Payload, queue URL, message group/deduplication |
| S3 path, headers, SigV4 generation | WireMock | HTTP contract and response parsing |
| Local S3 put/get | LocalStack | SDK and emulator interoperate cleanly |
| IAM role and bucket policies | AWS sandbox | Actions allowed/denied as designed |
| Cleanup and resource lifecycle | AWS sandbox | Buckets/tables/queues deleted per policy |

### 19.3. Handling Partial Failures

~~~mermaid
flowchart TD
    START["Upload request"] --> S3["Put object to S3"]
    S3 --> DDB["Write metadata to DynamoDB"]
    DDB --> SQS["Publish event to SQS"]
    SQS --> OK["Return success"]
    S3 -->|"Failure"| FAIL["Return upload error"]
    DDB -->|"Failure"| COMP["Delete object or mark orphan for cleanup"]
    SQS -->|"Timeout / unknown result"| RECON["Idempotency key + reconcile publish"]
    COMP --> FAIL
    RECON --> DECIDE["Determine message state before retry"]
~~~

Never assume three separate services share an ACID transaction. Use an outbox in DynamoDB/RDS or durable workflow state for reliable event publishing; simulate every failure point in tests to confirm no duplicate side effects occur.

### 19.4. Splitting Tests by Risk

- Unit tests verify validation and mapping logic.
- Mock tests verify request models and service exception handling.
- WireMock verifies SDK signing, serialization, and response parsing.
- LocalStack verifies end-to-end API flows against an emulator.
- AWS sandbox verifies IAM, KMS, bucket policies, SQS policies, VPCs, and quotas.

One small end-to-end sandbox test suffices to prove live wiring; never spin up thousands of real resources on every pull request.

## 20. Hands-On Practice: Building a Multi-Tier Test Suite

### 20.1. Completing the S3 Client Helper for WireMock

Tests from Section 5 can share this helper to guarantee every test targets the local endpoint with fake credentials:

~~~java
private S3Client buildS3Client(String endpoint) {
    AwsCredentialsProvider fakeCredentials =
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key"
            )
        );

    return S3Client.builder()
        .endpointOverride(URI.create(endpoint))
        .region(Region.US_EAST_1)
        .credentialsProvider(fakeCredentials)
        .serviceConfiguration(
            S3Configuration.builder()
                .pathStyleAccessEnabled(true)
                .build()
        )
        .build();
}
~~~

Keep this helper strictly inside the test source set. Never share it with production wiring or let user requests supply the endpoint.

### 20.2. Practice Steps

1. Implement `ProductImageService` accepting `S3Client` via constructor injection.
2. Use Mockito to verify bucket, key, content type, and `AccessDenied` handling.
3. Start WireMock on a dynamic port and build the S3 client using the helper above.
4. Stub `PUT /bucket/key`, return an ETag, and verify the `Authorization` header carries the SigV4 scheme.
5. Return HTTP 500 on the first attempt and 200 on the next; verify retry count matches the configured retry strategy.
6. Run the same put/get flow against LocalStack/Testcontainers.
7. Create a dedicated AWS sandbox role and verify the account with STS before creating real resources.
8. Create a bucket with a run ID, upload an object, read it back, and delete the bucket in cleanup.
9. Inspect CloudTrail/IAM policies when a sandbox test hits `AccessDenied`.
10. Run the test suite in parallel to check for race conditions and resource name collisions.

### 20.3. Artifacts to Record

- Separate unit, contract, emulator, and AWS integration test reports.
- SDK version, Region, policy-masked account ID, and run ID.
- Request IDs and error codes whenever live AWS returns errors.
- List of created test resources and cleanup status.
- Test durations, retry counts, and any incurred costs.

Never store access keys, secret keys, session tokens, `Authorization` headers, or sensitive payloads in test artifacts.

## 21. Reinforcement Exercises

### Exercise 1 — Choosing a Test Level

You need to verify `ProductService` calls the repository properly when a product does not exist. Should you use a mock or an AWS sandbox?

**Hint:** Unit test/mock; no AWS resources are needed.

### Exercise 2 — Endpoint Override

A test uses `endpointOverride` pointing to WireMock yet fails with missing credentials. Why does the SDK still need credentials when the server is not AWS?

**Hint:** The SDK still signs requests with SigV4; supply fake credentials and a Region to form the signing scope.

### Exercise 3 — Region Mismatch

A request reaches a local endpoint, yet the signature fails because the signing Region differs from what the stub/emulator expects. What should you check?

**Hint:** Client Region, signing scope, endpoint-specific settings, and canonical request.

### Exercise 4 — Mock or WireMock?

You want to verify that the S3 client constructs `/bucket/key`, sets the `Content-Type` header, and emits a SigV4 `Authorization` header. Which tool should you pick?

**Hint:** HTTP stub/WireMock with a real SDK client and `endpointOverride`; Mockito never exercises the HTTP pipeline.

### Exercise 5 — LocalStack Passes, AWS Fails

A create-bucket test passes on LocalStack yet fails with `AccessDenied` in the sandbox account. Is that a contradiction?

**Hint:** No. Emulators do not prove real AWS IAM or resource policies. Inspect caller identity, policies, SCPs, KMS, and bucket policies.

### Exercise 6 — Sandbox Guard

A pipeline runs under a default profile pointing to an unexpected account ID. Can tests create resources before detecting the mistake?

**Hint:** Run the STS account guard before any create/modify operation; IAM and SCPs must enforce additional boundaries.

### Exercise 7 — Retrying After Timeout

SQS `SendMessage` times out. The application retries and receives two messages. What design prevents duplicate business processing?

**Hint:** Idempotency keys/deduplication strategies, idempotent consumers, and outcome reconciliation; FIFO deduplication helps only within service semantics/windows.

### Exercise 8 — S3 Cleanup

A test creates a versioned bucket, deletes the object key, and then tries to delete the bucket, failing with `BucketNotEmpty`. Why?

**Hint:** You must delete all object versions, delete markers, and incomplete multipart uploads before deleting the bucket.

### Exercise 9 — Hung Async Test

A test calls `join()` on a future that never completes, hanging the suite indefinitely. How do you fix it?

**Hint:** Enforce finite timeouts, verify service/container readiness, and clean up clients/event loops.

### Exercise 10 — Pagination

`ListObjectsV2` returns the first page with `IsTruncated=true`. The code reads `response.contents()` once and stops. What is the bug?

**Hint:** Subsequent pages are dropped; use a paginator or continuation-token loop.

### Exercise 11 — Thread Safety

An application builds a new `S3Client` on every request. What is the impact and how do you improve it?

**Hint:** Increases connection, thread, and resource overhead; reuse a thread-safe client via dependency injection and close it on shutdown.

### Exercise 12 — Test Account Isolation

An AWS integration test runs concurrently across multiple CI jobs using the same DynamoDB table name. What can go wrong?

**Hint:** Collisions, test interference, and premature cleanup of another job's resources; include a run ID in resource names/tags and scope permissions by prefix.

## 22. Production-Ready Test Implementation Checklist

- [ ] AWS SDK BOM aligns versions cleanly; project uses SDK v2 exclusively without mixing SDK v1 imports.
- [ ] Unit tests mock service clients and focus on business behavior.
- [ ] HTTP contract tests use WireMock/local endpoints, Region, and fake credentials.
- [ ] Custom endpoints are enabled only in test configs and cannot silently fall back to live AWS.
- [ ] SigV4 tests assert scheme/scope appropriately without logging full `Authorization` headers.
- [ ] LocalStack image and Testcontainers versions are pinned; container readiness and lifecycles are managed.
- [ ] Emulator limitations are understood; AWS sandbox tests cover IAM, networking, quotas, and service semantics.
- [ ] Sandbox account ID and allowed Region are checked via STS before creating any resource.
- [ ] CI uses OIDC/assume-role or short-lived sessions; no long-lived keys reside in source or pipeline logs.
- [ ] Test IAM roles enforce least privilege and cannot assume production roles.
- [ ] Resources carry run IDs, owner/expiry tags, `finally` cleanup, and a janitor for orphaned resources.
- [ ] S3 versioning/multipart uploads, DynamoDB waiters, and SQS queue lifecycles are cleaned up properly.
- [ ] Retries, timeouts, throttling, `AccessDenied`, and unknown write outcomes are tested.
- [ ] Pagination, async completion/failure, client shutdown, and parallel execution are tested.
- [ ] Unit, contract, LocalStack, and AWS integration suites are separated in build/CI configurations.
- [ ] Reports contain no credentials, tokens, PII, or sensitive payloads.
- [ ] Budget alerts, concurrency limits, and resource quotas are configured for the sandbox.

## 23. Key Takeaways

**Testing AWS SDK for Java requires multiple complementary layers:**

1. **Mockito** tests business logic and how services interact with SDK clients without network calls.
2. **WireMock + endpoint overrides** test HTTP requests/responses, serialization, and SigV4 generation; Region and fake credentials are still required.
3. **LocalStack/Testcontainers** enable reproducible local integration tests, though they do not verify real AWS IAM, networking, or all service semantics.
4. **AWS sandbox accounts** verify live IAM, KMS, quotas, VPCs, service behavior, and lifecycles; require account guards, least privilege, budgets, and cleanup.
5. Reuse AWS SDK v2 clients, inject them via constructors/factories, and close them with the application lifecycle.
6. Bound retries and timeouts; for write operations, timeouts can leave uncertain outcomes requiring idempotency and reconciliation.
7. Isolate test resources with namespaces, run IDs, and cleanup; never expose credentials or sensitive data in test reports.

A strong test suite proves **sound logic, valid wire requests, reliable integrations, and a safe sandbox**. Neither mocks nor emulators can prove all four on their own.

### Official Documentation and References

- [AWS SDK for Java 2.x Developer Guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html) — comprehensive SDK v2 guide.
- [Service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/service-clients.html) — building and reusing service clients.
- [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — credential sources and provider chain.
- [Configure service endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html) — endpoint configuration and overrides.
- [Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — retry behavior in SDK v2.
- [AWS SDK for Java API reference](https://sdk.amazonaws.com/java/api/latest/) — request/response builders and service clients.
- [AWS STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — verifying account and caller identity.
- [Testcontainers LocalStack module](https://java.testcontainers.org/modules/localstack/) — running LocalStack with Testcontainers.
- [LocalStack documentation](https://docs.localstack.cloud/) — service coverage and emulator configuration.
- [WireMock documentation](https://wiremock.org/docs/) — HTTP stubbing and request verification.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — test lifecycles, tags, and extensions.
- [Mockito documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html) — mocks, stubbing, and verification.
