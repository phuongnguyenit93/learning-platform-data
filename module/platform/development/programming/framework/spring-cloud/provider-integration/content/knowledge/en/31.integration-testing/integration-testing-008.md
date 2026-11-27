# Testing Insufficient Permissions, Expired Tokens, Throttling, and Disconnections

> **Chapter:** Integration Testing  
> **Module:** SPRING_CLOUD_PROVIDER_INTEGRATION  
> **Objective:** Design negative integration tests for authentication and authorization failures; simulate expired tokens, throttling, timeouts, connection resets, and network interruptions; verify retries, backoff, idempotency, and error mapping across AWS, Azure, and Google Cloud.

## 1. Why Must Failure Scenarios Be Tested?

A Spring Boot application integrating managed cloud services often works fine in a developer environment because local accounts have broad permissions, tokens are fresh, and networks are stable. Once deployed, the workload identity may lack an IAM action, a role assignment may not have propagated, an access token may expire, a service may rate-limit requests, or a connection may drop mid-flight.

If only happy paths are tested, these failures tend to surface late in production. They can cause failed requests, duplicate data, lost messages, infinite retries, or mask misconfigured permissions.

A good negative integration test must answer four questions:

1. **How is the error identified?** 401, 403, 429, 5xx, timeout, or transport failure?
2. **How does the application react?** Refresh credentials, return a business error, retry, wait, or stop?
3. **Are side effects safe?** Could duplicate objects/messages or partial side effects occur?
4. **Is it observable and diagnosable?** Do logs include request IDs, service error codes, attempt counts, and correlation IDs?

Never lump every cloud error into a single generic exception and retry. Insufficient permissions and expired tokens require different handling from throttling; a timeout after sending a request can leave an indeterminate outcome.

## 2. Classifying Errors by Root Cause

| Error Category | Examples | Typically Appropriate Response |
| --- | --- | --- |
| Unauthenticated | Expired token, wrong token audience, unable to acquire credentials | Attempt refresh/re-authentication via the credential provider; stop if that fails |
| Insufficient permissions | Denied IAM action, missing Azure RBAC role, missing Google IAM role | Do not retry blindly; fix the identity or role assignment |
| Throttling/quota | HTTP 429, AWS throttling, Google `RESOURCE_EXHAUSTED` | Backoff with jitter, honor `Retry-After`, cap attempts |
| Transient service error | HTTP 500/502/503/504, gRPC `UNAVAILABLE` | May retry if the operation is safe and budget remains |
| Timeout | Connect timeout, read timeout, gRPC `DEADLINE_EXCEEDED` | Distinguish unsent requests from ambiguous post-send outcomes |
| Disconnection | Connection reset, socket closed, proxy timeout | Bounded retry if the operation is idempotent |
| Configuration/permanent error | Invalid endpoint, TLS hostname mismatch, 400 validation failure | Fail fast and surface configuration error |
| Resource not found | 404, `NOT_FOUND` | Do not retry unless the workflow explicitly accounts for eventual consistency |

A status code alone is not enough to determine the cause. For instance, HTTP 401 can indicate an expired token, wrong audience, or invalid credentials; HTTP 403 usually indicates the principal was identified but lacks permission for the action. Read the provider's error code and response metadata, not just the status code.

## 3. Choosing the Right Testing Layer

Not every failure can be verified in the same test environment.

| Layer | How Failure Is Produced | What Can Be Verified |
| --- | --- | --- |
| Unit test | Mock ports, credential providers, or retry collaborators | Exception mapping, retry decisions, business branches |
| Adapter test | Mock SDK clients or provider-shaped HTTP responses | Status/error code mapping and request metadata |
| Component test | Fake identities, fake storage/brokers, or local HTTP stubs | Multi-component coordination, app-managed refresh flows |
| Fault-injection test | Toxiproxy, MockWebServer, or WireMock | Latency, connection cuts/resets, 429/503, timeouts |
| Cloud integration test | Dedicated test identity with real IAM/RBAC | Permissions, token audience, workload identity, and real policies |
| Staging/E2E | Cloud resources and near-production network paths | End-to-end flows, quotas, private endpoints, and service behavior |

Mocking a 403 only proves your code handles the exception properly. It does not prove real IAM policies actually deny the action. Toxiproxy can sever connections to a container or test service; it does not prove production private endpoints work.

A balanced strategy uses unit tests for many error branches, fault injection for retries/timeouts, and a small set of real cloud tests with least-privilege identities.

## 4. Normalizing Errors at the Adapter Boundary

Business services should not depend directly on `AwsServiceException`, `RequestFailedException`, or `ApiException`. Adapters should translate SDK errors into stable application errors.

Example contract:

```java
public enum CloudFailureKind {
    AUTHENTICATION_EXPIRED,
    AUTHENTICATION_INVALID,
    ACCESS_DENIED,
    THROTTLED,
    SERVICE_UNAVAILABLE,
    NETWORK_TIMEOUT,
    CONNECTION_LOST,
    RESOURCE_NOT_FOUND,
    INVALID_REQUEST,
    UNKNOWN
}

public record CloudFailure(
        CloudFailureKind kind,
        String provider,
        String service,
        String operation,
        Integer statusCode,
        String providerCode,
        String requestId,
        boolean retryable) {
}

public class CloudOperationException extends RuntimeException {
    private final CloudFailure failure;

    public CloudOperationException(
            CloudFailure failure,
            Throwable cause) {
        super("Cloud operation failed: " + failure.kind(), cause);
        this.failure = failure;
    }

    public CloudFailure failure() {
        return failure;
    }
}
```

Never place access tokens, secret keys, connection strings, or full request bodies inside `CloudFailure`. Retain only the details needed for classification, diagnosis, and log correlation.

### 4.1. Minimum Classification Rules

- 401 or `UNAUTHENTICATED`: check credentials, expiry, issuer, and audience.
- 403 or `PERMISSION_DENIED`: check principal, action, resource scope, and policy.
- 429 or `RESOURCE_EXHAUSTED`: classify as throttling/quota, read retry hints if present.
- 500/502/503/504 or `UNAVAILABLE`: potentially transient; evaluate operation safety and retry budget.
- Timeout/reset: determine whether the request was sent; write outcome may be indeterminate.
- 400/`INVALID_ARGUMENT`: usually a bad request; do not retry.
- 404/`NOT_FOUND`: handle per resource semantics; do not turn into an infinite retry.

Never rely solely on a rule like `statusCode >= 500`. A provider can return 500 for an error that should not be retried, or 400 with an error code indicating throttling or a transient condition. Favor official provider error codes and SDK retry policies.

## 5. Insufficient Permissions: Verifying Real Denials

### 5.1. Creating a Dedicated Principal for Negative Tests

Use a dedicated workload identity or service principal for integration tests. Grant the exact permissions needed for the happy path, then use a second principal missing one specific action to test denial.

Example with Document Service:

- Identity A can write objects to the bucket/container and publish events.
- Identity B only has read access to objects.
- An upload test using Identity B must be rejected.
- A read test using Identity B must succeed if the resource exists and policy permits.
- The test must never fall back to admin credentials when running assertions.

Separating principals verifies real permission boundaries. Never modify production policies to induce errors; use isolated test accounts, projects, subscriptions, or resources.

### 5.2. AWS IAM

AWS SDK for Java 2.x typically throws `AwsServiceException` or a subclass when an AWS service returns an error; `AccessDenied` is normally non-retryable. For S3, the error code may be `AccessDenied`; for other services, codes and HTTP mappings may vary.

A negative test can invoke a real operation using a read-only test role:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowableOfType;

@Test
void readOnlyRoleCannotUploadObject() {
    S3Client s3 = createClientUsingReadOnlyTestRole();

    S3Exception failure = catchThrowableOfType(
            () -> s3.putObject(
                    PutObjectRequest.builder()
                            .bucket(testBucket)
                            .key("negative/doc-1.pdf")
                            .build(),
                    RequestBody.fromBytes(new byte[] {1, 2, 3})
            ),
            S3Exception.class);

    assertThat(failure.statusCode()).isEqualTo(403);
    assertThat(failure.awsErrorDetails().errorCode())
            .isEqualTo("AccessDenied");
}
```

This is a structural example. The client helper must use a test role granted a read-only policy; the bucket and key must be test resources. Never use an admin account and simulate `AccessDenied` with a mock while claiming IAM has been tested.

### 5.3. Azure RBAC

Azure Storage data-plane permissions are granted via appropriate roles, such as Storage Blob Data Reader or Storage Blob Data Contributor. Role assignments can be scoped at the subscription, resource group, storage account, or container level depending on design. Role assignments may take time to propagate.

Tests should verify:

- The principal authenticated against the right tenant and subscription.
- The token carries the audience for Azure Storage.
- The role is assigned at the intended scope.
- Read/write/delete operations require the expected roles.
- Negative tests return 403 or the corresponding service error when data actions are missing.

The Azure SDK for Java may throw `RequestFailedException` with status and error codes; token acquisition failures may surface as `ClientAuthenticationException` or `CredentialUnavailableException`. Distinguish token acquisition failures from service-side authorization denials.

### 5.4. Google Cloud IAM

Google Cloud distinguishes `UNAUTHENTICATED` and `PERMISSION_DENIED`. `PERMISSION_DENIED` typically maps to HTTP 403; `UNAUTHENTICATED` indicates the caller was not authenticated. `RESOURCE_EXHAUSTED` typically maps to HTTP 429 and relates to quotas/resource exhaustion.

For Cloud Storage, create a test service account holding only the required role—such as object viewer for reads or object creator for creating objects. Upload tests using a read-only principal must fail; reads of permitted objects must succeed.

Never grant Project Editor or Owner to integration tests. Use narrow resource scopes, revoke permissions afterward if the test creates role bindings dynamically, and avoid mutating roles in parallel with other suites.

### 5.5. Writing Meaningful Permission-Denial Tests

A missing-permission test must verify all three points:

1. The SDK uses the expected principal.
2. The provider denies the specific operation/resource.
3. The application maps the error to `AccessDenied`/`PermissionDenied` and does not retry.

If a test merely asserts that any arbitrary exception was thrown, it could pass due to a bad endpoint, malformed token, or network timeout. Assert on status code, provider error code, and request ID to be sure you are testing the intended condition.

## 6. Expired Tokens and Authentication Failures

### 6.1. Distinguishing Expired Tokens from Missing Permissions

| Scenario | Common Signals | Action |
| --- | --- | --- |
| Expired token | 401, `UNAUTHENTICATED`, `ExpiredToken`, or invalid token response | Refresh or acquire new credentials if the credential source supports it |
| Wrong token audience/issuer | 401 or invalid token | Fix identity configuration; do not retry repeatedly |
| Credential source unavailable | Unable to obtain token before sending request | Check metadata endpoint, workload identity, or CLI/SSO session |
| Principal lacks permission | 403, `PERMISSION_DENIED`, `AccessDenied` | Fix IAM/RBAC; refreshing tokens will not resolve this |
| Principal revoked | Token is valid/unexpired but policy denies | Re-assign the right role if needed; refresh cannot grant permissions |

Expired tokens and permission denied are distinct failures. Refreshing a token cannot grant permissions to a principal that lacks the required role.

### 6.2. AWS: Temporary Credentials and IAM Identity Center

AWS SDK for Java 2.x uses credentials providers to obtain credentials and sign requests. Temporary credentials typically consist of an access key, secret key, and session token, and have an expiration time. Refresh-capable providers obtain fresh credentials before the session expires.

With IAM Identity Center (SSO), the SDK can refresh access tokens using a refresh token as long as the access portal session remains valid. Once the portal session expires, re-login is required; the SDK cannot recover a fully expired session on its own.

Scenarios worth testing:

- The credentials provider refreshes successfully before credentials expire.
- When the refresh token or SSO session expires, new requests fail cleanly.
- Static credentials containing stale session tokens are never used long-term.
- When the provider cannot obtain fresh credentials, the application surfaces an authentication failure without retrying the service operation indefinitely.
- Clients and providers are not closed prematurely while the application is still using them.

Never use `StaticCredentialsProvider` to stand in for production workload identity if the application actually uses `AssumeRole`, Web Identity, or IAM Identity Center.

### 6.3. Azure: TokenCredential and Azure Identity

The Azure SDK for Java obtains tokens via `TokenCredential`. Implementations such as `DefaultAzureCredential`, `ManagedIdentityCredential`, or `ClientSecretCredential` manage token acquisition based on environment.

Azure Identity exceptions to distinguish:

- `ClientAuthenticationException`: authentication failed.
- `CredentialUnavailableException`: the current credential cannot be used in this environment; the credential chain may fall through to the next provider.
- `RequestFailedException` 401/403: the service responded and rejected the request; inspect status/error code to distinguish token vs. permission issues.

Credential chain tests should verify the expected credential is selected in CI. For example, a runner with a developer's Azure CLI login or another service account could cause `DefaultAzureCredential` to pick up the wrong identity. Log the selected credential type safely and verify the principal in cloud tests.

### 6.4. Google Cloud: ADC and Refresh Tokens

Google Cloud Client Libraries for Java typically use Application Default Credentials (ADC). ADC supports multiple credential sources and manages token refreshes depending on credential type.

If you manually build credentials from a static access token, that token will not refresh automatically. This is a common pitfall when code caches tokens manually or forwards tokens from another service.

Prefer ADC, service account impersonation, or Workload Identity Federation for your environment. Avoid downloading and storing long-lived service account keys when identity federation is available.

### 6.5. Testing Token Expiration Deterministically

Do not wait for a real token to expire in wall-clock time during automated tests. That makes suites slow and unstable. Use one of these techniques:

- Unit test credential wrappers with a controllable clock.
- Use a fake `TokenCredential` or token source emitting tokens with deterministic expiry.
- Stub the token endpoint to test both successful refresh and refresh failure.
- Mock services returning `401`/`UNAUTHENTICATED` to verify adapter error classification.
- Run a dedicated cloud integration test with a short-lived workload identity/session if the real credential chain needs verification.

Tests should cover both refresh success and refresh failure. When refresh fails, the application must stop issuing requests and emit a diagnosable authentication error rather than looping retries on the service call.

### 6.6. Never Log Tokens

Never write access tokens, refresh tokens, client secrets, private keys, AWS session tokens, or connection strings to logs or test reports. When verifying token refreshes, log only the credential type, expiry timestamp, refresh count, and correlation ID. Mask tokens in debug output.

## 7. Throttling and Quotas

### 7.1. Recognizing Throttling

Throttling occurs when request rate, concurrency, or quota usage exceeds limits. Providers may return 429, 503, or service-specific error codes.

| Provider | Common Signals | Notes |
| --- | --- | --- |
| AWS | `ThrottlingException`, `TooManyRequestsException`, `ProvisionedThroughputExceededException`, `SlowDown`, or 429/5xx status | SDK classifies errors by error code and status |
| Azure Storage | `503 Server Busy`, `500 Operation Timeout`; some Azure services return 429 | Azure Storage generally recommends exponential backoff |
| Azure Resource Manager | `429 Too Many Requests` with `Retry-After` | Must wait at least the duration specified by the server |
| Google Cloud | `RESOURCE_EXHAUSTED`, typically mapped to 429 | Retryable codes depend on the specific RPC/service |

Do not treat every 429 as the same quota type. It may be a per-project, per-user, resource, partition, or transient service limit. Error details and provider metrics identify the scope.

### 7.2. Safe Retry Policies

A retry policy typically includes:

- Exponential backoff: wait duration grows across attempts.
- Jitter: adds randomness so multiple clients do not retry simultaneously.
- Maximum attempts: caps total calls.
- Total deadline/timeout: bounds overall operation duration.
- Retryable error classification: retries only failures identified as transient.
- `Retry-After`: honors server-specified wait intervals when provided by the SDK/service.
- Idempotency: ensures retries do not create duplicate side effects.

Illustrative backoff schedule:

| Retry Attempt | Base Backoff | Jittered Wait Range (Example) |
| ---: | ---: | ---: |
| 1 | 200 ms | 100–300 ms |
| 2 | 400 ms | 200–600 ms |
| 3 | 800 ms | 400–1,200 ms |
| 4 | 1,600 ms | 800–2,400 ms |

These values are illustrative only. Production settings must align with your SDK/provider, latency budget, and service quotas. Never hard-code this table as a universal default across AWS, Azure, and Google Cloud.

### 7.3. AWS SDK for Java 2.x

AWS SDK for Java 2.x provides three retry strategies: standard, legacy, and adaptive. Standard is recommended by AWS for general use cases; default mode and attempt counts can depend on SDK version, service client, or external configuration. When deterministic testing is needed, set the mode explicitly and measure actual request counts.

Example configuring the retry mode explicitly:

```java
import software.amazon.awssdk.core.retry.RetryMode;

S3Client s3 = S3Client.builder()
        .overrideConfiguration(configuration ->
                configuration.retryStrategy(RetryMode.STANDARD))
        .build();
```

To customize attempt counts, use the retry strategy builder matching your SDK version—for example, `retryStrategy(builder -> builder.maxAttempts(3))`. Verify imports and APIs against your exact AWS SDK version. Never increase SDK retries while simultaneously wrapping the same operation in an application retry loop without accounting for total attempts; two nested retry layers multiply request volume.

### 7.4. Azure SDK for Java

The Azure SDK provides retry policies in Azure Core as well as dedicated options on certain service clients such as Azure Storage. Azure Core `RetryOptions` defaults to retrying certain 408, 429, and 5xx responses (excluding 501/505) along with eligible exceptions per policy. Azure Storage provides `RequestRetryOptions` with retry type, max tries, try timeout, retry delay, and max retry delay.

Do not assume a single default applies to all Azure services. Read the specific client's documentation and verify whether the SDK honors `Retry-After`.

With Azure Storage, `503 Server Busy` and `500 Operation Timeout` can indicate throttling or hot partitions. Exponential backoff eases pressure; proper naming/partitioning is equally important. Retries cannot fix a workload that continually funnels traffic onto a single partition.

### 7.5. Google Cloud Java Client Libraries

Google Cloud Java client libraries configure retries per RPC. Each RPC can define its own set of retryable status codes and `RetrySettings`. Never assume all APIs retry `RESOURCE_EXHAUSTED` or `UNAVAILABLE` identically.

Key parameters include initial retry delay, retry delay multiplier, max retry delay, RPC timeout, total timeout, and max attempts. Google Cloud libraries apply jitter during retries. Inspect the generated `StubSettings` of the exact client to see which RPCs retry and which status codes are configured.

### 7.6. Never Retry Permission Errors

`403`/`AccessDenied`/`PERMISSION_DENIED` are normally non-transient. Retrying repeatedly generates wasted requests and masks policy bugs. One possible exception is a newly created role assignment whose propagation has not completed; if testing that case, use a bounded poll with a clear deadline rather than retrying all 403s indefinitely.

## 8. Testing Retries and Throttling Deterministically

### 8.1. Test the Error Classifier Separately

You can unit test the classifier before involving the SDK:

```java
class CloudFailureClassifierTest {

    @Test
    void permissionDeniedIsNotRetryable() {
        CloudFailure failure = new CloudFailure(
                CloudFailureKind.ACCESS_DENIED,
                "azure",
                "blob",
                "upload",
                403,
                "AuthorizationPermissionMismatch",
                "request-123",
                false);

        assertThat(failure.retryable()).isFalse();
    }

    @Test
    void throttlingIsRetryableWithinBudget() {
        CloudFailure failure = new CloudFailure(
                CloudFailureKind.THROTTLED,
                "gcp",
                "storage",
                "write",
                429,
                "RESOURCE_EXHAUSTED",
                "request-456",
                true);

        assertThat(failure.retryable()).isTrue();
    }
}
```

The classifier must inspect both provider error codes and status codes. Do not simply check status 500–599 and mark everything retryable.

### 8.2. Testing a 429 Sequence Followed by Success

Use MockWebServer or WireMock to emit controlled responses. Example testing an application-owned retry layer:

```java
@Test
void retriesThrottledOperationAndStopsAfterSuccess() {
    AtomicInteger calls = new AtomicInteger();

    String result = retryingExecutor.execute(() -> {
        int attempt = calls.incrementAndGet();

        if (attempt == 1) {
            throw new CloudOperationException(
                    throttledFailure(),
                    null);
        }

        return "stored";
    });

    assertThat(result).isEqualTo("stored");
    assertThat(calls).hasValue(2);
}
```

`retryingExecutor` in this example is an application component taking a clock/sleeper/retry policy via constructor so tests avoid real-time waits. If retries happen entirely inside the SDK, verify request counts against an HTTP stub or proxy using real SDK configuration rather than testing an unused wrapper.

### 8.3. Testing No Retry on Denial

```java
@Test
void doesNotRetryAccessDenied() {
    AtomicInteger calls = new AtomicInteger();

    assertThatThrownBy(() ->
            retryingExecutor.execute(() -> {
                calls.incrementAndGet();
                throw new CloudOperationException(
                        accessDeniedFailure(),
                        null);
            }))
            .isInstanceOf(CloudOperationException.class);

    assertThat(calls).hasValue(1);
}
```

This test protects the system against retry storms when policies are misconfigured. Also verify that logs/metrics do not classify `AccessDenied` as transient.

### 8.4. Testing `Retry-After` and Deadlines

For responses containing `Retry-After`:

- Verify the SDK/policy waits no less than the retry hint requested by the service.
- Verify the total deadline still bounds the operation.
- Verify that if `Retry-After` exceeds the remaining budget, the operation stops instead of extending indefinitely.
- Use a fake clock/sleeper to verify timing without slowing the test suite.

Never assert an exact millisecond jitter duration; jitter is randomized. Assert valid ranges, attempt counts, and total deadlines.

## 9. Testing Timeouts and Disconnections

### 9.1. Distinguishing Connect Timeout and Read Timeout

- **Connect timeout:** the client could not establish a TCP connection within the allowed window.
- **Read/response timeout:** the connection was established, but the response did not arrive in time.
- **Connection reset:** the socket closed unexpectedly while exchanging data.
- **DNS failure:** the hostname could not be resolved.
- **TLS handshake/certificate failure:** handshake failed or the certificate/hostname was invalid.

A connect timeout generally indicates the request never reached the service. A read timeout after sending a request leaves uncertainty as to whether the service executed the operation. Never retry a non-idempotent write solely because the client received no response.

### 9.2. Using Testcontainers Toxiproxy

Toxiproxy lets you inject latency, jitter, bandwidth limits, timeouts, and connection cuts between the test JVM and a container or between two containers. This provides deterministic resilience testing locally and in CI.

Maven dependency for Testcontainers 2.x:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-toxiproxy</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
```

Example creating a network, service container, and Toxiproxy:

```java
import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.Proxy;
import eu.rekawek.toxiproxy.model.ToxicDirection;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;

Network network = Network.newNetwork();

GenericContainer<?> target = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379)
        .withNetwork(network)
        .withNetworkAliases("redis");

ToxiproxyContainer toxiproxy =
        new ToxiproxyContainer("ghcr.io/shopify/toxiproxy:2.5.0")
                .withNetwork(network);

target.start();
toxiproxy.start();

ToxiproxyClient client = new ToxiproxyClient(
        toxiproxy.getHost(),
        toxiproxy.getControlPort());

Proxy proxy = client.createProxy(
        "redis",
        "0.0.0.0:8666",
        "redis:6379");

String proxyHost = toxiproxy.getHost();
int proxyPort = toxiproxy.getMappedPort(8666);
```

Code under test must connect through `proxyHost` and `proxyPort`, not directly to `target`. Tests must close `target`, `toxiproxy`, and `network` in teardown; use JUnit lifecycles or the Testcontainers extension to manage resources. With cloud SDKs, apply this pattern to local emulators or test services with endpoint overrides. When proxying an external HTTPS endpoint, preserve the expected hostname/SNI and certificate validation; never disable TLS verification to make a test pass.

### 9.3. Injecting Latency and Cutting Connections

```java
proxy.toxics()
        .latency("slow-downstream", ToxicDirection.DOWNSTREAM, 1_100)
        .setJitter(100);

// After verifying timeout behavior, cut both directions.
proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0);

proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0);

// Verify the request fails within the expected deadline.

// Restore the proxy after assertions.
proxy.toxics().get("cut-downstream").remove();
proxy.toxics().get("cut-upstream").remove();
```

After restoring the proxy, verify the client can open a new connection and subsequent operations succeed. Connection pools may retain broken sockets; depending on the HTTP client, close/recreate the client or wait for the pool to evict bad connections.

Toxiproxy tests should clean up in `finally` or lifecycle helpers so active toxics never leak into subsequent tests.

### 9.4. DNS and TLS Need Separate Tests

Toxiproxy primarily manipulates TCP streams. DNS failures and certificate validation are distinct failure modes. Use a dedicated test DNS resolver/host mapping or an HTTPS test server with test certificates to verify them.

Never deploy self-signed certificates with hostname verification disabled in production code just to make an integration test pass. TLS tests must validate both the trust chain and hostname verification.

## 10. Timeouts Can Produce Ambiguous Outcomes

A write request may have committed on the service before the response was lost. The client observes a timeout, yet the object or message may already exist.

Example:

1. Service receives an upload request.
2. Service stores the object successfully.
3. Response drops before reaching the client.
4. Client retries.
5. The application might overwrite, create a duplicate, or emit a duplicate event.

Therefore, safe retries require one of these mechanisms:

- A stable idempotency key for a business operation.
- Deterministic object keys and appropriate write conditions.
- Conditional requests using ETag/generation/version.
- Message deduplication keys or a consumer inbox.
- Transactional outbox so retrying a business transaction does not publish duplicate events.
- Read-after-timeout/reconciliation before deciding to write again.

Never generate a new UUID on every retry if that UUID serves as the idempotency key. One operation must keep the same key across all attempts.

## 11. Testing Idempotency and Retry Side Effects

### 11.1. Object Storage

With S3/Azure Blob/GCS, tests should clarify whether upload retries reuse the same object key or create new objects. Verify metadata, content checksums, ETag/generation, and versioning per contract.

A fault-injection test should simulate a dropped response after the write already succeeded, then retry with the same operation ID and verify only one logical document exists.

### 11.2. Message Publishing

A publish timeout can leave a message inside the broker even though the producer never received an acknowledgement. Tests must verify:

- Messages carry a stable event ID.
- Consumers deduplicate by event ID if the business flow requires an exactly-once effect.
- Producer retries do not repeat downstream side effects.
- Outbox records are marked published under consistent rules.
- Duplicate deliveries are handled idempotently.

Never confuse broker-level delivery guarantees with exactly-once business processing.

### 11.3. Database and Outbox

When writing to a database and publishing cloud events, test failures between the two steps. Verify the outbox record commits in the same transaction as business state, then verify the publisher retries until the broker accepts it. A fake publisher only tests logic; database integration tests must verify real transactions and unique constraints.

## 12. Provider Error Matrix

| Scenario | AWS | Azure | Google Cloud | Default Retry Consideration |
| --- | --- | --- | --- | --- |
| Insufficient permissions | `AccessDenied` / `AccessDeniedException` | 403, `AuthorizationPermissionMismatch` or RBAC deny | `PERMISSION_DENIED` | No |
| Expired token/session | `ExpiredToken`, SSO session expired | 401 or `ClientAuthenticationException` | `UNAUTHENTICATED` / expired access token | Refresh credentials if provider supports; do not retry service infinitely |
| Throttling | `ThrottlingException`, `SlowDown`, `TooManyRequests` | 429; Storage may return 503/500 | `RESOURCE_EXHAUSTED` | Yes, within policy and quotas |
| Service unavailable | 5xx, `ServiceUnavailable` | 503 | `UNAVAILABLE` | Bounded |
| Deadline/timeout | Socket timeout, request timeout | Timeout / 408 / `500 Operation Timeout` | `DEADLINE_EXCEEDED` | Conditional |
| Network reset | `SdkClientException` with I/O cause | Transport exception | `IOException`/transport error | Conditional, considering idempotency |
| Bad request | `ValidationException`, `InvalidRequest` | 400, `InvalidArgument` | `INVALID_ARGUMENT` | No |

This table summarizes common error groups, not an absolute mapping across every service. Within the same provider, exceptions and error codes can differ across S3, SQS, Blob Storage, Service Bus, Pub/Sub, or Cloud Storage.

## 13. Observability When Testing Failures

Negative tests should also verify the telemetry emitted by the application. Useful fields include:

- Provider and service name.
- Operation name.
- Normalized failure kind.
- HTTP/gRPC status and provider error code.
- Provider request ID/correlation ID.
- Attempt number and total attempts.
- Retry delay or `Retry-After` if present.
- Elapsed time and remaining deadline.
- Sanitized or truncated resource identifier.

Never log access tokens, refresh tokens, secret keys, SAS tokens, private keys, connection strings, or payloads containing sensitive data.

For permission failures, logs should help identify the principal and required action without exposing credentials. For network failures, logs should distinguish DNS, connect timeout, read timeout, TLS, and connection reset. For throttling, log attempt counts and wait durations to spot retry storms.

## 14. Common Anti-Patterns

| Anti-Pattern | Risk | Fix |
| --- | --- | --- |
| Retrying every exception | Retries 403s, validation, and configuration errors | Classify by provider error code and operation |
| Infinite retries | Hanging requests, rising load and cost | Max attempts + total deadline |
| Unbounded SDK retries and app retries together | Request counts multiply across layers | Budget total retries; let one layer own the primary policy |
| Refreshing tokens on missing IAM permissions | Never resolves a 403 | Check principal, action, and resource scope |
| Using admin identity in tests | Fails to catch runtime permission gaps | Least-privilege test principal |
| Mocking 429 alone and assuming SDK retry works | Never validates real SDK policy | Test HTTP attempt counts with real client and provider-shaped responses |
| Using fixed sleep to wait for token expiry | Slow and flaky tests | Fake clock/token source or stub auth endpoint |
| Retrying writes with a new idempotency key | Creates duplicate resources/messages | Keep key stable across all attempts |
| Disabling TLS verification behind proxies | Masks certificate bugs and opens security holes | Use test certificates with matching hostnames |
| Logging full exceptions/requests | May leak tokens or payloads | Redact and log safe metadata only |

## 15. Practice Lab: Testing Document Service Under Cloud Failures

**Context:** Document Service saves PDF files to object storage and publishes `DocumentUploaded` to a message broker. The application runs with workload identity and default SDK retries.

### Part A — Insufficient Permissions

- Create a test principal with read-only object permissions.
- Attempt an upload and verify the provider returns `AccessDenied`/403/`PERMISSION_DENIED`.
- Verify the adapter maps it to `ACCESS_DENIED`.
- Verify the operation does not retry.
- Verify with a write-enabled principal that the happy path still succeeds.

### Part B — Expired Tokens

- Create a fake credential/token source with controllable expiry.
- Verify the token refreshes before expiration when supported by the provider.
- Simulate refresh failure and verify the operation stops with an authentication error.
- Simulate a service returning 401 for a rejected token.
- Distinguish 401 from 403 and prevent infinite retries.

### Part C — Throttling

- Use an HTTP stub that returns 429/503 followed by success.
- Verify attempt counts and total deadline.
- Check `Retry-After` or SDK retry settings.
- Return 403 and verify no retry occurs.
- Use a fake clock to verify backoff/jitter in an application retry wrapper.

### Part D — Disconnections

- Start a test service inside a container.
- Place Toxiproxy between the test JVM and the service.
- Inject latency exceeding the request timeout.
- Cut the connection after the operation starts.
- Restore the proxy and verify the client reconnects cleanly.
- Verify writes do not produce duplicate objects/events.

### Part E — Cloud Identity Tests

- Run dedicated tests in a test AWS account, Azure subscription, or Google Cloud project.
- Use an IAM role, Managed Identity/workload identity, or service account with least-privilege permissions.
- Test one allowed action and one denied action.
- Capture provider request IDs and verify the actual principal.
- Clean up test-created resources and role bindings.

**Completion criteria:** the learner distinguishes authentication, authorization, throttling, and transport failures; writes negative permission tests; tests token refresh/failure; verifies bounded retries; simulates network faults with Toxiproxy; and protects side effects with idempotency.

---

## 16. Pre-Merge/Pre-Release Checklist

| Group | Question |
| --- | --- |
| Identity | Do tests use a dedicated, environment-matched, least-privilege principal? |
| Permissions | Are both positive and negative tests present for each critical action? |
| Authentication | Are expired tokens, invalid audiences, and unavailable credentials distinguished? |
| Error mapping | Do adapters preserve status, provider code, and request ID? |
| Retries | Are retries restricted to identified transient/throttling failures? |
| Backoff | Are exponential backoff, jitter, max attempts, and total deadlines enforced? |
| `Retry-After` | Are service retry hints honored when provided? |
| Idempotency | Do write retries reuse a stable operation ID/idempotency key? |
| Network | Are connect timeouts, read timeouts, resets, and recovery tested? |
| TLS/DNS | Are certificate/hostname and DNS tested separately when the system depends on them? |
| Observability | Are attempt counts, failure kinds, elapsed times, and request IDs captured? |
| Secrets | Are tokens, keys, and connection strings stripped from logs/test reports? |
| CI | Do cloud tests have isolated resources and cleanup on failure? |
| SDK version | Has retry behavior been verified against the project's actual SDK version? |

## Key Takeaways

- 401/`UNAUTHENTICATED` typically relates to authentication; 403/`PERMISSION_DENIED` typically relates to authorization. Refreshing tokens will not fix missing IAM/RBAC permissions.
- AWS, Azure, and Google Cloud have different exceptions, error codes, and retry defaults; verify the exact service client and SDK version.
- Throttling requires backoff with jitter, attempt caps, total deadlines, and honoring `Retry-After` when present.
- Never blindly retry validation or permission failures.
- Timeouts after sending a request can leave side effects; write retries need idempotency keys or reconciliation.
- Use Toxiproxy to simulate latency, timeouts, bandwidth limits, and connection cuts in controlled tests.
- Testing IAM/RBAC, workload identity, and Managed Identity requires dedicated cloud test principals with least-privilege permissions.
- Log request IDs, error codes, and attempt counts; never log tokens or secrets.

Testing cloud failures goes beyond confirming an application throws an exception. It must prove the application identifies the root cause accurately, stops when unauthorized, refreshes credentials when possible, retries transiently within bounded budgets, and keeps side effects safe when outcomes are uncertain. Combining local/CI fault injection with focused cloud identity tests covers critical failure modes while keeping the integration suite stable.

### Official Documentation

- [AWS SDK for Java 2.x — Configure retry behavior](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [AWS SDK for Java 2.x — Handling exceptions](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/handling-exceptions.html)
- [AWS SDKs and Tools — Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [AWS SDKs and Tools — IAM Identity Center session expiration and refresh](https://docs.aws.amazon.com/sdkref/latest/guide/understanding-sso.html)
- [AWS SDK for Java 2.x — Credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [Azure SDK for Java — Troubleshoot authentication](https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-authentication-overview)
- [Azure SDK for Java — RetryOptions](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.policy.retryoptions?view=azure-java-stable)
- [Azure Storage — Retry policy for Java](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-retry-policy-java)
- [Azure Storage — Mitigate hot partitions](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-performance-mitigate-hot-partitions)
- [Google Cloud Java — Configure client-side retries](https://docs.cloud.google.com/java/docs/client-retries)
- [Google Cloud Java — Authenticate requests](https://docs.cloud.google.com/java/docs/authentication)
- [Google Cloud Java — Status code definitions](https://docs.cloud.google.com/java/docs/reference/proto-google-common-protos/latest/com.google.rpc.Code)
- [Testcontainers for Java — Toxiproxy module](https://java.testcontainers.org/modules/toxiproxy/)

Retry defaults, status mappings, and exception types may vary across service clients and SDK versions. Before changing policies, check the documentation for the specific client, set deadlines according to business SLAs, and measure actual request counts in tests.
