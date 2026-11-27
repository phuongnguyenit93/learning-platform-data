# Customizing the HTTP Pipeline, Timeouts, and Retry Policies

Suppose a Java service running on Azure App Service processes orders, reads configuration from Azure App Configuration, uploads files to Azure Blob Storage, and fetches secrets from Key Vault. Under normal conditions, every Azure SDK call finishes quickly. However, when connectivity slows down, DNS stalls, an Azure service returns HTTP 429, or transient network errors occur, the application can stall for tens of seconds, trigger unexpected retry bursts, or even write duplicate data.

To solve this systematically, you need to understand the **HTTP pipeline** of the Azure SDK for Java: a chain of request/response policies covering telemetry, request IDs, authentication, retries, HTTP logging, and the HTTP transport. From there, developers can **customize the HTTP client, timeouts, retry options, and custom policies** while preserving the SDK's security, observability, and compatibility guarantees.

This lesson belongs to the **Azure SDK for Java** chapter in the **CLOUD_PROVIDERS_AZURE** module. It connects directly to deploying Java applications across Azure subscriptions/resource groups, Microsoft Entra ID, virtual networks, Storage, App Configuration, Key Vault, monitoring, and cost control. Content focuses on **com.azure:azure-core** and modern Azure SDK for Java service clients; it does not apply verbatim to legacy Java libraries or third-party SDKs.

> **Safe Scope:** Examples use placeholder resource names, run only in authorized lab environments, and do not execute resource creation or deletion commands. Builder APIs, retry options, and defaults vary across SDK and service library versions. Check your Maven dependency tree and exact-version Javadoc before deploying to production; time values in this lesson are illustrative tuning examples, not Azure SLAs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the components and execution order in the Azure SDK for Java **HttpPipeline**.
2. Distinguish between **HttpClient transport**, **HttpPipelinePolicy**, and service-specific builders.
3. Distinguish **PER_CALL** and **PER_RETRY**, knowing which policies should run once per operation versus once per attempt.
4. Use **DefaultAzureCredential**, service client builders, `HttpLogOptions`, and custom `HttpClient` instances without breaking authentication.
5. Tune Netty **connect, response, read, and write timeouts**, understanding how transport-level timeouts differ from full-operation deadlines.
6. Use **RetryOptions**, **ExponentialBackoffOptions**, and **FixedDelayOptions** appropriately.
7. Distinguish **maxRetries** and **maxTries** across different APIs.
8. Use Azure Storage's specialized **RequestRetryOptions** when appropriate.
9. Analyze HTTP 408, 429, 5xx, `Retry-After`, network failures, non-idempotent operations, and replayability.
10. Write a **custom HttpPipelinePolicy** for safe metrics/tracing that handles both sync and async pipelines.
11. Avoid nested retries, retry storms, event-loop blocking, and credential leaks in logs.
12. Calculate latency budgets, throughput amplification, and appropriate timeout/retry profiles by workload.
13. Design unit, integration, and fault-injection tests for the HTTP pipeline without touching production.
14. Diagnose timeouts, 429s, 401/403s, proxy/TLS issues, service unavailability, and related symptoms.
15. Operate consistent HTTP policies across App Service, AKS, Azure Functions, and other environments.

## 2. Why Understand the HTTP Pipeline?

### 2.1. A Real-World Problem

A payment API must read feature flags from App Configuration before processing an order:

~~~text
Inbound HTTP request to app
    ↓
Java API handler
    ↓
Azure App Configuration SDK
    ↓
DNS → TLS → network → Azure service
    ↓
Configuration returned
    ↓
Business processing
~~~

When the service returns 429 or hits a network timeout, the SDK may retry automatically. If the application also retries in Spring, an API gateway, or a message processor, total attempts can multiply unexpectedly.

For example: the SDK allows up to three attempts, and the app retries the SDK call up to three times. Under continuous failure, that produces **9 HTTP attempts**, not 3. If many instances retry on identical intervals, the whole system can trigger a **retry storm**.

### 2.2. Three Distinct Configuration Layers

| Layer | Examples | Controls |
|---|---|---|
| Transport | Netty, OkHttp, JDK HTTP client; connect/read/write/response timeouts | Connection establishment and HTTP I/O |
| Pipeline | `RetryPolicy`, logging, authentication, custom policies | Request/response behavior wrapping transport |
| Application | API deadlines, circuit breakers, concurrency limits, idempotency | Business goals and user experience |

Never solve every timeout by bumping a single number to 120 seconds. Identify **which layer** is waiting, whether the request is safe to retry, and whether the business deadline still holds.

### 2.3. What Happens Without Proper Controls?

- App threads or async requests hold resources too long.
- p95/p99 latency climbs even while p50 looks healthy.
- Outbound request volume and logging costs increase.
- 429 throttling worsens due to synchronized retries.
- Backend errors amplify across layers.
- Non-idempotent commands write duplicate data.
- Retries fire after the HTTP client disconnects even though the server committed the change.
- HTTP bodies or Authorization tokens leak into logs if debug logging is over-enabled.

The goal of a sound policy is to **retry only recoverable failures, within strict time and attempt budgets, without corrupting data**.

## 3. Components of the Azure SDK for Java

### 3.1. HttpClient Is the HTTP Transport

In Azure Core, **`com.azure.core.http.HttpClient`** represents the HTTP sending and receiving layer. Common transport implementations include:

- **azure-core-http-netty**: Netty; usually the default in the Azure SDK for Java.
- **azure-core-http-okhttp**: OkHttp integration depending on selected dependencies.
- **azure-core-http-jdk-httpclient**: Java HTTP client-based implementation on supported JDK/runtimes.

The HTTP client handles connections, DNS/TLS, sending request bodies, and receiving responses. It **does not automatically replace** authentication/authorization logic or service-specific retries.

### 3.2. HttpPipeline and Policies

~~~mermaid
flowchart LR
    A["Service client call"] --> P1["PER_CALL policies"]
    P1 --> R["Retry policy"]
    R --> P2["PER_RETRY policies"]
    P2 --> H["HttpClient transport"]
    H --> S["Azure service"]
    S --> H
    H --> P2
    P2 --> R
    R --> P1
    P1 --> A
~~~

- **HttpPipeline** combines the transport and a chain of policies.
- **HttpPipelinePolicy** inspects requests and/or responses, adding headers, metrics, logging, or other controlled behaviors.
- **RetryPolicy** decides whether to resend a request when a failure meets retry criteria.
- **Authentication policy** attaches or refreshes credentials per library and credential type.
- **HttpLoggingPolicy** logs allowed request/response details per configuration.
- **Transport** performs actual network I/O.

When a service client is constructed with its standard builder, it builds a pipeline pre-populated with service-appropriate policies. Developers **should customize via the builder first**, and only assemble a full pipeline manually for specialized requirements while preserving mandatory policies.

### 3.3. Requests Flow Forward, Responses Flow Back

~~~mermaid
sequenceDiagram
    participant C as ServiceClient
    participant P1 as Policy A
    participant R as RetryPolicy
    participant P2 as Policy B
    participant H as HttpClient
    participant S as Azure Service
    C->>P1: Request
    P1->>R: Forward
    R->>P2: Attempt 1
    P2->>H: Send HTTP
    H->>S: Request
    S-->>H: Response 503
    H-->>P2: Response
    P2-->>R: Response 503
    R->>R: Evaluate + backoff
    R->>P2: Attempt 2
    P2->>H: Retry HTTP
    H->>S: Retry
    S-->>H: Response 200
    H-->>P2: Response
    P2-->>R: Response 200
    R-->>P1: Final response
    P1-->>C: Result
~~~

This is a conceptual diagram; the exact ordering of authentication, logging, request IDs, and other policies is defined by each SDK/service client contract. Do not assume logging always precedes or follows retries without inspecting the configured pipeline.

### 3.4. Client Builders Are the Preferred Extension Point

Many service clients offer similar builder methods:

| Method | Purpose | Notes |
|---|---|---|
| `endpoint(...)` | Set service endpoint | Must match service/region/sovereign cloud |
| `credential(...)` | Set `TokenCredential` or appropriate credential | Follow least privilege |
| `httpClient(...)` | Swap HTTP transport | Does not replace pipeline policies |
| `retryOptions(...)` | Configure retry strategy | `RetryOptions` type varies by SDK |
| `addPolicy(...)` | Add custom `HttpPipelinePolicy` | Choose `PER_CALL`/`PER_RETRY` properly |
| `httpLogOptions(...)` | Configure logging detail level | Never log bodies/secrets indiscriminately |
| `pipeline(...)` | Supply an entire custom pipeline | May override other builder settings |
| `buildClient()`/`buildAsyncClient()` | Build sync/async client | Never rebuild per request |

Not all builders expose identical methods. For example, azure-core `RetryOptions` differs from **azure-storage-common `RequestRetryOptions`**. Always check the specific client's API before copying code.

## 4. PER_CALL vs. PER_RETRY

### 4.1. Meaning

The Azure SDK for Java defines the **`HttpPipelinePosition`** enum in **`com.azure.core.http`**:

- **PER_CALL**: policy runs once per operation/service call, outside the retry loop.
- **PER_RETRY**: policy runs inside the retry loop on every HTTP attempt sent.
- If not overridden, `HttpPipelinePolicy` defaults to **PER_RETRY** in current Azure Core versions.

| Use Case | PER_CALL | PER_RETRY |
|---|---|---|
| Operation count | 1 | Up to total HTTP attempts |
| Total elapsed operation duration | Appropriate | Incomplete if measured per attempt |
| Initial request trace/correlation | Usually appropriate | Can share trace and add attempt metadata |
| Attempt-level metrics | Insufficient | Appropriate |
| Authentication/token logic | Per built-in auth policy/contract | Do not relocate manually |
| Custom signed headers | Must understand request mutation and retries | May need re-signing per attempt |
| HTTP request attempt logging | Misses retry attempts | Appropriate |

### 4.2. Three-Attempt Example

~~~text
Client operation
    PER_CALL: start (1 time)
        Retry loop
            PER_RETRY: attempt #1 → 503
            Backoff
            PER_RETRY: attempt #2 → 429
            Backoff per policy/Retry-After if supported
            PER_RETRY: attempt #3 → 200
    PER_CALL: complete (1 time)
~~~

If a custom policy counting HTTP requests runs at `PER_CALL`, the count will **underreport** when retries happen. If a policy measuring total operation duration runs at `PER_RETRY`, individual timings miss cumulative backoff.

### 4.3. Do Not Treat Policies as Arbitrary Free-for-All Interceptors

A policy can inspect requests and responses, yet it must:
- Never corrupt the body or service signature.
- Never overwrite the `Authorization` header.
- Never invoke `next.process()` multiple times unless explicitly implementing retry logic.
- Never block with `Thread.sleep` inside an async pipeline.
- Never consume a response body without returning/restoring it.
- Never store per-request mutable state inside a singleton policy.
- Never log PII, request bodies, tokens, or SAS signatures.
- Never build a custom retry loop nested with the SDK's `RetryPolicy`.

The cleanest custom policy is usually **bounded metrics or safe correlation**, not replacing transports or authentication.

## 5. Timeouts Are Not a Single Number

### 5.1. Types of Timeouts

| Timeout | Approximate Scope | Risk If Set Too Low |
|---|---|---|
| DNS/proxy resolution | Endpoint lookup and selection | Cannot resolve target IP |
| Connect timeout | Establishing TCP connection to server | Remote networks or cold connections fail |
| TLS handshake timeout | TLS negotiation where supported by transport | Slow handshakes or cert/auth failures |
| Write timeout | Sending request body data | Large uploads cut off mid-flight |
| Response timeout | Waiting for server to start responding | Service has not finished processing yet |
| Read timeout | Reading response after bytes begin arriving | Slow streams/responses aborted |
| Per-try/attempt timeout | Single HTTP attempt | Must leave room for retries within budget |
| Total operation deadline | Entire call including retries and backoff | Easy to breach SLAs if omitted |
| Business/API deadline | Time allowed for API or worker execution | Must fail/cancel cleanly on time |
| Long-running operation polling | Multiple status-polling requests | Not a single HTTP request |

**Never sum these timeouts and assume that is the exact worst-case duration**, because layers apply at different phases, some are idle/inactivity timeouts, and SDK/service methods may enforce their own policies.

### 5.2. Connect Timeout

Measures from when the transport initiates a connection until connection establishment completes; it is not total API execution time.

If DNS resolves yet an NSG, proxy, or firewall drops SYN packets, a connect timeout is the symptom. Increasing connect timeout indefinitely **cannot fix a broken route**.

### 5.3. Response Timeout

Caps how long to wait for the server to begin returning a response after the request is sent per transport semantics. A throttled or overloaded backend slows responses down; for large uploads, understand how write and response timeouts operate separately.

### 5.4. Read and Write Timeouts

Transports may implement read/write timeouts as **inactivity timeouts or per-operation timeouts**, not necessarily whole-file download/upload caps. For instance, a stream steadily receiving small chunks can last longer than a single read timeout without failing as long as no idle gap exceeds the threshold.

Never set `writeTimeout = 2 seconds` for large uploads over low-bandwidth links just because a separate GET API needs fast responses.

### 5.5. Total Deadline

If a business HTTP API must respond within 5 seconds, configuring 30-second HTTP attempt timeouts with three retries is clearly contradictory.

A total deadline can be applied at the service-method or application layer—for example via SDK overloads accepting `Duration` where supported, or reactive cancellation/deadlines. Still, **an application-level timeout does not make the server roll back writes it already received**. On timeout, check idempotency and verify server state.



## 6. Configuring the HTTP Transport with Netty

### 6.1. When to Customize Netty?

**azure-core-http-netty** is the common default. Customize Netty when you need:

- Short connect timeouts for Azure regions close to the workload.
- Dedicated response/read/write timeouts for upload vs. download paths.
- Enterprise proxy settings and network constraints.
- Advanced connection pool and transport tuning.
- Sharing one transport across multiple service clients.
- Diagnosing DNS, TLS, or connection reuse in App Service or AKS.

You do not need to construct a custom `HttpClient` merely to get defaults; service client builders automatically pick an available classpath transport.

### 6.2. Java Example: Netty with Four Timeouts

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import java.time.Duration;

public final class AzureTransportFactory {
    private AzureTransportFactory() { }

    public static HttpClient create() {
        return new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(20))
            .readTimeout(Duration.ofSeconds(30))
            .writeTimeout(Duration.ofSeconds(30))
            .build();
    }
}
~~~

**Explanation:**

- `connectTimeout = 5s` caps new connection establishment under normal conditions.
- `responseTimeout = 20s` caps waiting for the response to begin.
- `readTimeout = 30s` governs response reading per transport semantics.
- `writeTimeout = 30s` governs request data writing per transport semantics.

This is **not an 85-second total deadline** and does not guarantee every operation finishes within 85 seconds. Across multiple attempts and backoff, total latency can be much higher.

`NettyAsyncHttpClientBuilder` has specific behavior for zero or negative durations and null/default values; never pass `Duration.ZERO` expecting "immediate timeout." Per Netty documentation, non-positive values can **disable** the corresponding timeout. Always use positive durations and verify runtime behavior.

### 6.3. Controlled Transport Sharing

In long-lived Java backends, create clients at application startup and reuse them:

~~~java
HttpClient transport = AzureTransportFactory.create();

// Transport can be passed to multiple service builders
// when transport and lifecycle are compatible.
~~~

Never create new Netty event loops or connection pools per HTTP request. At the same time, **never blindly reuse a transport configured with sensitive proxy/TLS settings across endpoints with incompatible trust or network policies**.

### 6.4. Proxies and Hybrid Connectivity

Enterprises may require HTTP CONNECT proxies or private egress routes. Use `ProxyOptions` and transport-specific builders per current APIs, keeping credentials in a secure store. Before tweaking timeouts, check:

1. Does the DNS resolver resolve the private endpoint hostname properly?
2. Does the proxy permit traffic to the Azure service hostname and port?
3. Does the TLS certificate chain validate cleanly?
4. Do Network Security Groups, Azure Firewall, and VNet routes allow the flow?
5. Are the Private Endpoint and Private DNS Zone linked to the right VNet?
6. Is the managed identity token endpoint reachable?

If the root cause is broken DNS or a firewall drop, raising timeout from 5 to 120 seconds only delays failure.

### 6.5. Never Disable TLS Validation for Quick Testing

Never use an "accept all certificates" trust manager or disable hostname verification to work around timeouts in real environments. Doing so invites MITM attacks and leaks `TokenCredential` tokens and sensitive data.

## 7. Standard Retry Configuration with Azure Core

### 7.1. RetryOptions and ExponentialBackoffOptions

**`com.azure.core.http.policy.RetryOptions`** supports configuring retries via **`ExponentialBackoffOptions`** or **`FixedDelayOptions`**.

Example:

~~~java
import com.azure.core.http.policy.ExponentialBackoffOptions;
import com.azure.core.http.policy.RetryOptions;
import java.time.Duration;

ExponentialBackoffOptions backoff = new ExponentialBackoffOptions()
    .setMaxRetries(3)
    .setBaseDelay(Duration.ofMillis(500))
    .setMaxDelay(Duration.ofSeconds(8));

RetryOptions retryOptions = new RetryOptions(backoff);
~~~

**`maxRetries = 3`** typically means up to three **retries after the initial send**, or up to **4 total attempts**, provided the error is retryable and the operation is not canceled. Do not confuse this with APIs named **`maxTries`**.

The `baseDelay`, `maxDelay`, and `maxRetries` values are illustrative balances between latency and resilience; they are not universal defaults across all Azure services.

### 7.2. Exponential Backoff

An approximate model:

~~~text
Delay after attempt k ≈
    min(maxDelay, baseDelay × 2^(k-1))

Example baseDelay = 500 ms:
  Retry 1: ~0.5 s
  Retry 2: ~1.0 s
  Retry 3: ~2.0 s
~~~

The SDK may apply jitter, server-directed delays, or other bounds depending on `RetryStrategy` and version; never assert exact 0.5/1/2-second timings in tests when randomization is active.

**Exponential backoff** reduces the chance that many clients retry simultaneously against a busy service. When the server returns **`Retry-After`** or an equivalent header, the policy can honor server guidance per library support; verify behavior for your exact client.

### 7.3. When to Use Fixed Delay?

~~~java
import com.azure.core.http.policy.FixedDelayOptions;
import com.azure.core.http.policy.RetryOptions;
import java.time.Duration;

RetryOptions retryOptions = new RetryOptions(
    new FixedDelayOptions(2, Duration.ofSeconds(1))
);
~~~

Fixed delay fits some test suites, very low-load clients, or protocols with predictable recovery intervals. Across thousands of instances, however, every client waiting exactly one second causes **synchronized retries**, creating periodic overload spikes.

In bursty cloud production systems, prefer exponential backoff with jitter or the retry strategy recommended by the service SDK.

### 7.4. RetryPolicy vs. RetryOptions

**`RetryPolicy`** is an `HttpPipelinePolicy` that can take **`RetryOptions`**. When a service client builder exposes **`retryOptions(...)`**, configure it there first.

Do not confuse:

- **RetryOptions**: retry configuration settings.
- **RetryPolicy**: the pipeline policy executing retry decisions and attempts.
- **RequestRetryOptions**: Azure Storage-specific retry configuration with additional options.
- **Application retry**: retrying the entire SDK method outside the Azure SDK pipeline.

A builder may treat `retryOptions` and `retryPolicy` as mutually exclusive. Never attach an extra `RetryPolicy` via **`addPolicy(...)`** on a builder that already configures default retries, as that can stack two retry loops or alter policy ordering unpredictably.

### 7.5. Nature of Retry Conditions

In Azure Core, default `RetryOptions` conditions typically evaluate responses like **408, 429, and certain 5xx errors** plus exceptions depending on version. Still, individual clients/services may extend or restrict behavior.

| Status/Condition | Typical Handling | Warning |
|---|---|---|
| 200/201/204 | Success | Do not retry |
| 400 Bad Request | Invalid input/schema | Fix request; never retry blindly |
| 401 Unauthorized | Invalid/expired auth | Inspect credential/token flow; not a load issue |
| 403 Forbidden | Missing RBAC, ACL, or network policy | Never fix with infinite retries |
| 404 Not Found | Missing resource/route or eventual consistency | Retry only per operation-specific guidance |
| 408 Request Timeout | Potentially transient | Check semantics and deadline |
| 409 Conflict | Usually a business/state conflict | Do not retry unless service documents it as transient |
| 412 Precondition Failed | Stale ETag/condition | Re-read state and resolve concurrency |
| 429 Too Many Requests | Throttling / rate limit | Honor `Retry-After` and shed load |
| 500/502/503/504 | Potentially transient | Bounded retry; remember server may have committed |
| Network reset/EOF | Potentially transient | Unknown whether server received/committed |
| Timeout after POST | Ambiguous outcome | Use idempotency keys or verify state |

**Not every 5xx is retried by default policies**, nor are 409/404 always non-retryable. Behavior depends on service-specific error codes and operation semantics. Never override default conditions from a generic HTTP table and accidentally disable critical service library logic.

### 7.6. Retry-After Is a Server Signal

When Azure returns HTTP 429 or 503 with **`Retry-After`** or service headers like `x-ms-retry-after-*`, let the SDK honor supported server guidance. Never write a tight `while sleep(100)` loop hammering the service, because it:

- Worsens service throttling.
- Generates extra transaction charges.
- Pins threads, connections, and workers.
- Backs up application queues.
- Inflates overall timeouts.

If `Retry-After` exceeds the business deadline, the app must **fail cleanly or defer work to a queue**, not wait forever.

## 8. Complete Example: Azure App Configuration Client

### 8.1. Goals

A Java application reading configuration from Azure App Configuration needs:

- Authentication via **Microsoft Entra ID** using `DefaultAzureCredential`.
- A reused Netty `HttpClient` with explicit timeouts.
- Exponential retry up to three retries after the initial request.
- HTTP logging at `BASIC` level.
- Operation-level metrics policy without logging secrets.
- Keeping the SDK's built-in pipeline intact without overriding it wholesale.

### 8.2. Preparing Dependencies

In Maven, manage Azure SDK dependencies via an organization-approved **`azure-sdk-bom`** and pin compatible versions. Participating artifacts:

~~~text
com.azure:azure-data-appconfiguration
com.azure:azure-identity
com.azure:azure-core
com.azure:azure-core-http-netty
reactor-core (managed by compatible ecosystem)
~~~

Do not pick an old fixed version from a blog post; verify JDK/Netty/runtime compatibility, Azure SDK BOM, and security updates. Do not include every HTTP transport if you only use Netty.

### 8.3. Java Client Factory

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.http.policy.ExponentialBackoffOptions;
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;
import com.azure.core.http.policy.RetryOptions;
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.time.Duration;

public final class AppConfigClientFactory {
    private AppConfigClientFactory() { }

    public static ConfigurationClient create(String endpoint) {
        if (endpoint == null || !endpoint.startsWith("https://")) {
            throw new IllegalArgumentException(
                "HTTPS Azure App Configuration endpoint is required"
            );
        }

        HttpClient httpClient = new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(15))
            .readTimeout(Duration.ofSeconds(20))
            .writeTimeout(Duration.ofSeconds(20))
            .build();

        RetryOptions retries = new RetryOptions(
            new ExponentialBackoffOptions()
                .setMaxRetries(3)
                .setBaseDelay(Duration.ofMillis(500))
                .setMaxDelay(Duration.ofSeconds(8))
        );

        return new ConfigurationClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .httpClient(httpClient)
            .retryOptions(retries)
            .httpLogOptions(
                new HttpLogOptions()
                    .setLogLevel(HttpLogDetailLevel.BASIC)
            )
            .buildClient();
    }
}
~~~

Use via a service singleton or dependency injection:

~~~java
String endpoint = System.getenv("AZURE_APPCONFIG_ENDPOINT");

ConfigurationClient client =
    AppConfigClientFactory.create(endpoint);

// Read an existing key when the principal holds App Configuration Data Reader:
// ConfigurationSetting setting = client.getConfigurationSetting("app.mode", null);
~~~

Never embed App Configuration connection strings or secrets in source code. **`DefaultAzureCredential` does not grant RBAC automatically**: the runtime identity must hold **App Configuration Data Reader** or an appropriate role at the right scope. During development, `DefaultAzureCredential` may select a developer identity different from production managed identity.

### 8.4. Why Not Build HttpPipeline Manually Above?

**`ConfigurationClientBuilder`** knows its authentication scope and service-specific policies. Calling `.httpClient(...)`, `.retryOptions(...)`, `.httpLogOptions(...)`, and `.credential(...)` individually allows the SDK to assemble all required defaults properly.

If instead you wrote:

~~~java
// Conceptual example only; do not build and use in production
// when auth/service policies are missing:
// HttpPipeline pipeline = new HttpPipelineBuilder()
//     .httpClient(httpClient)
//     .policies(new RetryPolicy(retries))
//     .build();
~~~

and passed it to `builder.pipeline(pipeline)`, you risk **omitting authentication, telemetry, content handling, logging, and service-specific policies**. Moreover, `.pipeline(...)` takes precedence over many other builder settings, so `.retryOptions(...)` or `.httpClient(...)` may be ignored. Always read the builder documentation if you truly need a full custom pipeline.

### 8.5. Sync and Async Clients

`ConfigurationClientBuilder` can build **`buildClient()`** or **`buildAsyncClient()`**.

| Sync | Async |
|---|---|
| Easy to use in blocking apps | Suited for reactive/high-concurrency apps when used right |
| Calling thread may block | `Mono`/`Flux` with backpressure and cancellation |
| Can use policies implementing `processSync` | Requires policies implementing `process` returning `Mono` |
| Prone to thread starvation under heavy I/O | Breaks easily if blocked on the event loop |

Never call **`.block()`** on a Netty event loop or reactive callback. If the application uses a blocking framework, size thread pools and timeouts to capacity; if reactive, use async APIs and consistent cancellation.



## 9. Writing a Custom HttpPipelinePolicy for Metrics

### 9.1. Requirements

A policy measuring duration and response status per operation must:

- Run once at **PER_CALL**.
- Hold zero shared mutable state across requests.
- Never log URL paths or query strings that may contain secrets.
- Never print `Authorization` headers, SAS tokens, or request/response bodies.
- Support both sync and async clients if both paths are used.
- Never block forwarding to the next policy.
- Never retry on its own or swallow exceptions.
- Record status, exception category, and elapsed duration.

### 9.2. Java Code: SafeTimingPolicy

~~~java
import com.azure.core.http.HttpPipelineCallContext;
import com.azure.core.http.HttpPipelineNextPolicy;
import com.azure.core.http.HttpPipelineNextSyncPolicy;
import com.azure.core.http.HttpPipelinePosition;
import com.azure.core.http.HttpResponse;
import com.azure.core.http.policy.HttpPipelinePolicy;

import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

import reactor.core.publisher.Mono;

public final class SafeTimingPolicy implements HttpPipelinePolicy {
    private static final Logger LOG =
        Logger.getLogger(SafeTimingPolicy.class.getName());

    @Override
    public HttpPipelinePosition getPipelinePosition() {
        return HttpPipelinePosition.PER_CALL;
    }

    private static long elapsedMs(long startNanos) {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startNanos
        );
    }

    @Override
    public Mono<HttpResponse> process(
        HttpPipelineCallContext context,
        HttpPipelineNextPolicy next
    ) {
        // defer: timer starts upon subscription;
        // do not log or mutate request state before subscribe.
        return Mono.defer(() -> {
            final long start = System.nanoTime();

            return next.process()
                .doOnNext(response -> LOG.info(
                    "azure_sdk_operation status=" + response.getStatusCode()
                    + " durationMs=" + elapsedMs(start)
                ))
                .doOnError(error -> LOG.warning(
                    "azure_sdk_operation errorType="
                    + error.getClass().getSimpleName()
                    + " durationMs=" + elapsedMs(start)
                ));
        });
    }

    @Override
    public HttpResponse processSync(
        HttpPipelineCallContext context,
        HttpPipelineNextSyncPolicy next
    ) {
        final long start = System.nanoTime();

        try {
            HttpResponse response = next.processSync();

            LOG.info(
                "azure_sdk_operation status=" + response.getStatusCode()
                + " durationMs=" + elapsedMs(start)
            );

            return response;
        } catch (RuntimeException error) {
            LOG.warning(
                "azure_sdk_operation errorType="
                + error.getClass().getSimpleName()
                + " durationMs=" + elapsedMs(start)
            );
            throw error;
        }
    }
}
~~~

**Technical Explanation:**

- **`HttpPipelinePolicy`** defines the asynchronous `process` method returning **`Mono<HttpResponse>`**.
- **`processSync`** handles the synchronous path, forwarding through **`HttpPipelineNextSyncPolicy`**.
- **`getPipelinePosition`** returns **`HttpPipelinePosition.PER_CALL`**.
- **`Mono.defer`** postpones starting the timer until a subscriber triggers execution.
- **`next.process()`** is invoked exactly once; no custom retry loop is created.
- **`doOnNext`** and **`doOnError`** observe signals passively without swallowing exceptions.
- **`System.nanoTime`** is appropriate for measuring elapsed durations, avoiding wall-clock jumps from `System.currentTimeMillis`.
- Logs record **status/error type**, never URLs, bodies, or headers.

Note: a reactive publisher may be subscribed to multiple times in some scenarios; each subscription triggers a new operation. If callers attach `retryWhen` or re-subscribe, `PER_CALL` runs once per **pipeline invocation**, not once per business workflow across re-subscriptions.

### 9.3. Attaching the Policy to the App Configuration Builder

In the factory from section 8, add:

~~~java
return new ConfigurationClientBuilder()
    .endpoint(endpoint)
    .credential(new DefaultAzureCredentialBuilder().build())
    .httpClient(httpClient)
    .retryOptions(retries)
    .httpLogOptions(
        new HttpLogOptions()
            .setLogLevel(HttpLogDetailLevel.BASIC)
    )
    .addPolicy(new SafeTimingPolicy())
    .buildClient();
~~~

This snippet relies on the variables and imports from the section 8 factory. Never create a new client or policy per request. **`HttpPipelinePolicy`** instances can be shared, so any counters or timers must be request-local or backed by thread-safe atomics/metrics registries.

### 9.4. When You Want to Observe Every Attempt

If the goal is counting actual HTTP sends, create a separate policy:

~~~java
@Override
public HttpPipelinePosition getPipelinePosition() {
    return HttpPipelinePosition.PER_RETRY;
}
~~~

`PER_RETRY` runs inside each retry attempt. Check whether the SDK's built-in logging policy already records `retryCount` to avoid duplicate entries. For detailed retry telemetry, inspect the Azure SDK and transport's built-in diagnostic events/metrics before adding custom instrumentation.

### 9.5. When Correlation Headers Are Needed

An HTTP policy can add custom headers, provided the service accepts them and canonical signatures remain valid. In most cases, prefer:

- **`Context`** via supporting method overloads.
- **`x-ms-client-request-id`**/`RequestIdPolicy` or SDK request ID mechanisms where supported.
- **`ClientOptions`** and `AddHeadersFromContextPolicy` per documentation.
- OpenTelemetry tracing/correlation at the application layer.

Never overwrite `Authorization` or modify `x-ms-*` headers already signed by Azure Storage. When adding request IDs, prefer SDK-supported mechanisms placed prior to authentication/signing in the pipeline; injecting headers after signing can break authentication.

## 10. Azure Storage: Specialized RequestRetryOptions

### 10.1. Do Not Confuse the Two Retry Option Types

With the **Azure Blob Storage Java SDK**, builders such as **`BlobServiceClientBuilder`** can accept:

- **`com.azure.core.http.policy.RetryOptions`** — general retry configuration from `azure-core`.
- **`com.azure.storage.common.policy.RequestRetryOptions`** — Azure Storage-specific retry configuration supporting `maxTries`, `tryTimeout`, and `secondaryHost` where appropriate.

The two overloads may be **mutually exclusive**. Do not pass both to a single builder expecting combined features; the SDK follows specific precedence rules.

### 10.2. BlobServiceClient Example with Storage Retries

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.common.policy.RequestRetryOptions;
import com.azure.storage.common.policy.RetryPolicyType;

import java.time.Duration;

public final class StorageClientFactory {
    private StorageClientFactory() { }

    public static BlobServiceClient create(String storageEndpoint) {
        HttpClient transport = new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(25))
            .readTimeout(Duration.ofSeconds(60))
            .writeTimeout(Duration.ofSeconds(60))
            .build();

        RequestRetryOptions storageRetries = new RequestRetryOptions(
            RetryPolicyType.EXPONENTIAL,
            4,                       // maxTries: includes the initial request
            Duration.ofSeconds(30),  // tryTimeout per attempt
            Duration.ofSeconds(1),   // retryDelay
            Duration.ofSeconds(8),   // maxRetryDelay
            null                     // do not fail over to secondary
        );

        return new BlobServiceClientBuilder()
            .endpoint(storageEndpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .httpClient(transport)
            .retryOptions(storageRetries)
            .buildClient();
    }
}
~~~

**Prerequisites:** the app has compatible `azure-storage-blob`, `azure-storage-common`, `azure-identity`, and transport dependencies; the endpoint looks like **`https://storage-account.blob.core.windows.net/`** for an existing Storage account. The managed identity or service principal needs appropriate Azure Storage **data-plane RBAC** (such as Storage Blob Data Reader/Contributor depending on operations). Do not assume subscription `Contributor` grants Blob data read/write access by default.

### 10.3. maxTries Differs from maxRetries

| Option | Practical Meaning | Example |
|---|---|---|
| `ExponentialBackoffOptions.setMaxRetries(3)` | Three **retries after the first send** | Up to 4 attempts |
| Storage `RequestRetryOptions` `maxTries = 4` | **Total attempts**, including the first request | Up to 4 attempts |
| App-level `RetryTemplate` `maxAttempts = 3` | Per framework configuration | May multiply with SDK retries |

**Parameter names and semantics differ**—always check the Javadoc for each API. Never state "`maxRetries = 3` means 3 total sends" across all libraries.

### 10.4. tryTimeout Does Not Equal Total Timeout

In Storage `RequestRetryOptions`, `tryTimeout` typically targets **a single service request attempt**. With 4 total attempts, per-attempt timeouts, inter-attempt backoff, and overhead, the whole operation can exceed `tryTimeout` several times over.

An app requiring API completion under 10 seconds needs a **total operation deadline** or smaller `tryTimeout`/retry values. For large uploads, size per-try timeouts to payload size, bandwidth, and network variability.

### 10.5. Secondary Host and Consistency

Some Storage retry options allow a `secondaryHost` for geo-redundant setups. **Do not enable `secondaryHost` blindly "for higher HA"** without understanding:

- The secondary may not yet have replicated all writes.
- Reads may return stale data.
- Not every operation supports secondary endpoints.
- Failing over writes arbitrarily to secondary is invalid.
- DNS, authorization, region, and compliance affect correctness.

If your app requires strong read-after-write consistency, design for the service's consistency model rather than blindly adding secondary retries.

### 10.6. Storage Chunked Uploads Issue Multiple Requests

A 1 GB upload may be split by the SDK into many HTTP requests/blocks, each retried individually. Total upload duration does not equal a single HTTP request, and actual request count exceeds one. Monitor:

- Block/chunk size.
- Max concurrency.
- Retry count per request.
- Stream replayability.
- Write/read timeouts and total upload duration.
- Staying within the Java service's RAM/heap limits.
- Partial upload/commit semantics per Storage API.

Never assume a client-level retry policy turns every large upload into a single atomic HTTP request.

## 11. Timeout Budgets and Retry Storms

### 11.1. Rough Budget Calculation

Suppose a business API allows **8 seconds** total for reading config, querying SQL, and returning a response. If App Configuration alone has:

~~~text
Initial attempt timeout: 2 seconds
Retries: 2
Backoff between retries: 300 ms, then 600 ms

Upper estimate for this dependency:
  3 × 2s + 0.3s + 0.6s
  = 6.9s (+ overhead)
~~~

That leaves almost no time for business logic and response serialization. Allocate budgets deliberately:

~~~text
API gateway / caller deadline: 8.0s
  ├─ auth + input validation: 0.5s
  ├─ App Configuration/cached config: 0.3s target
  ├─ DB/business work: 3.0s
  ├─ downstream queue or write: 2.0s
  └─ headroom + network/cancellation: 2.2s
~~~

These numbers are budgeting examples. **You cannot prove worst-case latency through simple addition** if SDK transports, connection pools, DNS, retries, stream reads, and app scheduling are unbounded. Always measure empirically.

### 11.2. Retry Amplification

Suppose an application sends 1,000 operations/sec to an Azure service, 30% fail transiently, and all three retries are exhausted:

~~~text
70% succeed on first attempt:
  700 operations × 1 attempt = 700 sends

30% fail repeatedly:
  300 operations × 4 attempts = 1,200 sends

Total:
  1,900 HTTP sends / second (instead of 1,000)
~~~

If **100%** of calls fail and each tries four times total, HTTP traffic spikes to **4,000 attempts/sec** before accounting for delays, concurrency, and rate limits. Retry storms turn brief blips into prolonged outages.

### 11.3. Storm Prevention Measures

- **Exponential backoff + jitter** to stagger retry schedules across instances.
- Clear **max retries** and **total deadlines**.
- Honor **`Retry-After`** from services.
- **Circuit breakers** to fail fast during prolonged downstream overload.
- **Bulkheads/concurrency limits** so one dependency cannot consume all app threads.
- **Rate limiting/queues** to smooth bursts.
- **Caching** for reads with acceptable freshness semantics.
- **System-wide retry budgets** instead of every layer retrying independently.
- **Idempotency** so retries never create duplicate side effects.
- **Observability** tracking retry rates, not just error rates.

Configure circuit breaker thresholds, open durations, and half-open probes carefully; overly sensitive breakers can prevent a recovering dependency from receiving traffic.

### 11.4. Do Not Stack Retries at Every Layer

~~~mermaid
flowchart TD
    G["API gateway retry ×3"] --> APP["Application retry ×3"]
    APP --> SDK["Azure SDK retry ×4 attempts"]
    SDK --> S["Azure service"]
~~~

Under worst-case failures, one business call can generate **3 × 3 × 4 = 36 attempts** against the service if all three layers retry the same operation. This is undesirable.

Assign **one primary retry owner** per failure class; other layers should enforce timeouts, circuit-breaking, queuing, or propagate status. If multiple layers must retry, enforce a shared total deadline, idempotency, and a global attempt cap.

## 12. Idempotency: Is It Safe to Resend?

### 12.1. Retries Are Safe Only When Outcomes Are Repeatable

| Operation | Retry Risk | Design Guidance |
|---|---|---|
| GET Blob / Key Vault secret | Usually a read | Preserve version/freshness semantics, reasonable timeout |
| List resources | Paging and shifting state | Use continuation tokens; avoid unnecessary full scans |
| PUT with stable resource ID | Can be idempotent if semantics match | Use ETag/`If-Match` for concurrent writes |
| POST creating a new order | Can create two orders | Idempotency key and unique constraint |
| Queue send | Can enqueue two messages | Stable message ID / dedup if service supports it |
| Delete | Final state may be safe yet HTTP status differs | Handle 404/409 per business policy |
| Long-running operation kickoff | Can start duplicate jobs | Operation ID and polling/reconciliation |
| Non-replayable upload stream | Request body cannot be re-read | Buffering/replay strategy or disable retries as needed |

**HTTP verbs alone do not guarantee idempotency**. A PUT overwrite can cause lost updates under concurrent writers, and a poorly designed GET can trigger side effects. Verify the actual operation contract.

### 12.2. Ambiguous Outcome After Timeout

~~~text
Client sends create entity
    ↓
Service commits
    ↓
Response lost on network
    ↓
Client sees timeout
    ↓
Client retries creating a new entity
    ↓
Duplicate business record
~~~

How to prevent this:

1. Use stable business IDs or request IDs.
2. Perform conditional creates/upserts per SDK and service support.
3. Re-read state by ID before creating anew where appropriate.
4. Enforce unique constraints in storage/databases—not just check-then-insert.
5. For multi-service workflows, use outbox, saga, or reconciliation patterns.
6. Log request correlation IDs without PII.
7. Never retry unconditionally simply because the exception is a timeout.

### 12.3. ETags and Optimistic Concurrency

Azure services like Blob Storage support **ETag**-based conditional requests. Conceptual pattern:

~~~text
Read resource → ETag = A
Update with If-Match: A

If another writer already updated:
  service returns precondition failure (e.g., 412)
  → must re-read and resolve conflict
  → never blindly retry the exact same write
~~~

Never overwrite or strip the ETag just to force a write through. When computing updates from prior state, a 412 means business state and transaction logic must be re-evaluated.

### 12.4. Cancellation Is Not Rollback

When an app hits a deadline and cancels a publisher/request:

- The network request may have already reached the server.
- The server may have already committed data.
- The SDK may miss the response.
- The caller might retry the entire business operation.

Therefore, **cancellation controls client resources and latency**, yet operations with side effects still require state verification and idempotency.



## 13. Logging, Tracing, and HTTP Pipeline Security

### 13.1. HttpLogOptions and Detail Levels

Modern service client builders typically support **`httpLogOptions(...)`** to control what HTTP details the SDK logs.

| Level | Typical Logged Content | Recommendation |
|---|---|---|
| NONE | No HTTP request/response logs from this policy | Strictly log-restricted environments |
| BASIC | Method, redacted URL, status, duration | Relatively safe starting point |
| HEADERS | Adds allowlisted headers | Controlled diagnostics |
| BODY | Adds body per SDK limits | Avoid in production with PII |
| BODY_AND_HEADERS | Body and headers | Never use as production default |

**Never use `BODY_AND_HEADERS` as a production default.** SDK redaction and allowlists help, yet bodies may carry credentials or personal data, and custom headers/query parameters might not be redacted automatically.

### 13.2. Configuring BASIC Logging

~~~java
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;

HttpLogOptions logOptions = new HttpLogOptions()
    .setLogLevel(HttpLogDetailLevel.BASIC);

// Use with a supporting builder:
// clientBuilder.httpLogOptions(logOptions);
~~~

The SDK can also pick up certain log settings from environment variables such as **`AZURE_HTTP_LOG_DETAIL_LEVEL`** on supporting clients. Never turn on verbose logging globally in production without assessing its impact across all Azure SDK clients.

### 13.3. Allowed Headers and Query Parameters

You can expand the allowlist for safe headers when needed:

~~~java
HttpLogOptions logOptions = new HttpLogOptions()
    .setLogLevel(HttpLogDetailLevel.HEADERS)
    .addAllowedHeaderName("x-safe-business-operation");
~~~

This is a placeholder header; never allowlist fields containing `Authorization`, `Cookie`, SAS signatures, client secrets, PII, or tokens. URLs themselves may contain sensitive Blob names/paths or SAS queries; custom logging policies should avoid logging raw URLs without redaction.

### 13.4. Structured Metrics and Traces

A clean metric set might include:

~~~text
azure_dependency_requests_total
azure_dependency_attempts_total
azure_dependency_retries_total
azure_dependency_duration_ms
azure_dependency_attempt_duration_ms
azure_dependency_errors_total
azure_dependency_throttled_total
azure_dependency_in_flight
~~~

These metric names are **architectural suggestions**, not built-in metrics in every Azure SDK version.

Use tags such as `serviceType`, operation category, `statusClass`, `errorClass`, environment, and region. Never put request IDs, full URLs, user IDs, or arbitrary Blob names into metric labels—that causes high cardinality and data leakage risks. Correlation/trace IDs belong in controlled traces and logs.

### 13.5. OpenTelemetry and Azure Monitor

In Java applications, use approved OpenTelemetry and Azure Monitor/Application Insights instrumentation to:

- Link inbound requests with outbound Azure SDK dependencies.
- Track p50/p95/p99 latency and error rates per dependency.
- Separate 429 throttling, network timeouts, and RBAC errors.
- Compare actual retry counts against initial operations.
- Trace regressions back to specific releases or runtimes.
- Enforce RBAC and appropriate retention on logs and traces.

Do not assume every service client emits a separate span for **each attempt** in every version. When attempt-level telemetry is required, inspect current SDK logging/tracing hooks or add a thoroughly tested `PER_RETRY` policy.

## 14. Reactor Async, Total Timeouts, and Cancellation

### 14.1. Async Clients with Mono

The Azure SDK for Java offers many async clients returning **`Mono`/`Flux`**. Calling a method builds a publisher; network execution begins upon subscription.

~~~java
import com.azure.data.appconfiguration.ConfigurationAsyncClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import reactor.core.publisher.Mono;
import java.time.Duration;

ConfigurationAsyncClient client =
    new ConfigurationClientBuilder()
        .endpoint(System.getenv("AZURE_APPCONFIG_ENDPOINT"))
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildAsyncClient();

Mono<?> operation = client
    .getConfigurationSetting("app.mode", null)
    .timeout(Duration.ofSeconds(4));
~~~

**`Mono.timeout(Duration.ofSeconds(4))`** caps the publisher's total wait time—it does not configure Netty connect/read/write timeouts. Upon timeout, the client may cancel the request, yet the server may have already committed a write.

### 14.2. Reactive Pitfalls

- **Subscribing twice** to a cold publisher can trigger two network operations.
- **`retryWhen(...)`** in application code can create an outer retry loop wrapping SDK retries.
- **`block()`** inside a Reactor/Netty event loop can cause starvation or runtime exceptions.
- **`Thread.sleep`** in a reactive callback blocks the event loop and crushes throughput.
- Publisher timeouts do not equal service-side transaction rollbacks.
- Async clients still need concurrency limits, rate limits, and bounded queues; async does not grant Azure services infinite capacity.

What never to do:

~~~java
// NEVER do this inside a reactive callback/event loop:
// sdkMono.map(value -> {
//     Thread.sleep(2000);
//     return value;
// });
~~~

For multi-step workflows with side effects, use durable state and idempotency—not just `Mono.timeout` followed by re-running the whole workflow.

### 14.3. Enforcing Per-Dependency Deadlines

User-facing APIs need tight total deadlines, whereas batch or long-running jobs can allow more time. Application-level deadlines may need to:
- Cancel dependency calls when the budget expires.
- Cap retries according to remaining time.
- Honor `Retry-After` only if it fits within the deadline.
- Return an error or queue work per business rules.
- Verify server state after timeouts on mutating operations.

Never set an app timeout of 2 seconds while allowing the SDK four attempts of 30 seconds each and expect latency to stay unaffected.

## 15. Authentication, Networking, and Policy Ordering

### 15.1. Do Not Reimplement Authentication Unnecessarily

**`DefaultAzureCredential`** acquires tokens from the appropriate environment, and Azure SDK service builders automatically wire the matching authentication policy for the service's audience/scope.

When assembling an entire `HttpPipeline` manually, it is easy to:
- Omit the token authentication policy.
- Use the wrong scope in a different cloud.
- Fail to refresh tokens properly.
- Add the `Authorization` header too early or too late.
- Log tokens accidentally while debugging.
- Omit a mandatory service-specific policy.

For most applications, use **`builder.credential(...) + builder.httpClient(...) + builder.retryOptions(...) + builder.addPolicy(...)`** instead of manually constructing `Authorization` headers.

### 15.2. Errors That Retries Cannot Fix

| Symptom | Suspected Layer | Remediation |
|---|---|---|
| 401 | Token/credential/audience | Check Entra identity, tenant, scope |
| 403 | RBAC/ACL/firewall/policy | Verify data-plane role and network |
| DNS resolution failure | Private DNS, resolver, hostname | Test DNS from the runtime |
| TLS certificate error | CA trust, hostname, clock | Never disable TLS verification |
| Connect timeout | Proxy/firewall/route/service | Check TCP/NSG paths |
| 429 | Quota/throttling | Backoff, `Retry-After`, shed load |
| Response timeout | Slow/overloaded server or network | Measure latency, queries, workload |
| Read timeout | Slow response/chunk stream | Check payload size and network throughput |
| 412 | Concurrent writer / stale ETag | Re-read and resolve precondition |

Never grant `Owner` to fix a DNS error; never open Storage public networking to fix a 403 caused by a missing ACL.

### 15.3. Distinguishing Management and Data-Plane RBAC

A managed identity holding Azure `Contributor` on a resource group **cannot by default** download Blobs or read Key Vault secrets. It needs matching data-plane roles such as `Storage Blob Data Reader/Contributor` or `Key Vault Secrets User` per feature and permission model.

Before tuning retries, verify:
1. Which identity `DefaultAzureCredential` picked at runtime.
2. Whether the service endpoint, tenant, and cloud match.
3. Whether the role assignment applies at the right scope.
4. Whether VNet, Private Endpoint, and DNS are configured properly.
5. Whether firewalls or trusted-service rules block the workload.
6. Which exact status and SDK exception the service returns.

### 15.4. Azure Deployment Environments

- **App Service**: managed identity, VNet integration, outbound networking, and instance scale-out.
- **AKS**: workload identity, pod DNS/egress, HPA, and HTTP connection pools.
- **Azure Functions**: cold starts, trigger-level retries, host concurrency, and SDK retries interacting together.
- **Azure VM/Batch**: identity/proxy/TLS config, thread pools, and worker lifecycles.

A retry profile suited to a user-facing App Service may be far too short for multi-GB batch uploads, or far too long for an Azure Function under strict execution timeouts. Tailor profiles per workload rather than copying one static template everywhere.

## 16. Choosing Timeouts and Retries by Scenario

### 16.1. Reading Feature Flags in a User-Facing API

Requires low p95 latency; flags are cacheable. Approach:
- Singleton App Configuration client.
- Controlled cache and refresh per freshness policy.
- Short total deadline.
- Few or zero retries if a safe cached fallback exists.
- Circuit breaker during prolonged outages.
- Monitor cache age and refresh failures.

Avoid calling App Configuration on **every single HTTP request** when semantic caching fits.

### 16.2. Large Blob Batch Upload

Uploading a 500 MB file over variable networks:
- Use Azure Storage SDK chunking and bounded concurrency.
- Tune `RequestRetryOptions` and `tryTimeout` to chunk size and bandwidth.
- Avoid overly tight per-try timeouts across all uploads.
- Ensure payloads/streams are replayable on retry.
- Use stable blob names and conditional writes where needed.
- Track total duration, block counts, retries, and cost.
- Verify final state after ambiguous timeouts.

### 16.3. Fetching Secrets from Key Vault

- Proper `TokenCredential` and role.
- Retry 429/5xx per SDK and server hints.
- Never log secret bodies.
- Consider controlled caching and rotation.
- Keep the client a singleton.
- Never retry 403 permission failures.

### 16.4. Azure Resource Manager Long-Running Operations

A long-running operation (LRO) involves an initial HTTP request to start deployment followed by multiple polling requests tracking provisioning. **Polling interval, HTTP retry delay, and total job deadline are three distinct concepts**.

On timeout:
- Read back `provisioningState` and the resource ID.
- Never re-submit resource creation under a new ID without checking state.
- Use SDK polling APIs and retry guidance.
- Record correlation/activity logs and approvals.

### 16.5. Initial Selection Matrix

| Workload | Retry | Key Timeouts | Additional Controls |
|---|---|---|---|
| User-facing read | Few, short | Total API deadline | Cache / circuit breaker |
| Background ETL | Controlled | Per-try + job deadline | Queues / replay |
| Large Blob upload | Storage-specific | Write/read/try + total | Chunking, conditional writes |
| Key Vault lookup | SDK-aware | Connect/response | Caching, secret hygiene |
| ARM resource creation | HTTP retry + LRO polling | Total job deadline | State verification |
| Queue/event send | Service-specific | Attempt/operation | Stable IDs / dedup |
| Reactive high volume | Bounded retry | Per-dependency budget | Backpressure / rate limits |

There is no single "best" timeout/retry set for every app. Base choices on SLOs, p95/p99 latency, service quotas, networking, and side-effect risks.



## 17. Testing Timeouts, Retries, and Custom Policies

### 17.1. Why Fault-Injection Testing?

A client that builds cleanly can still fail at runtime: multi-layer nested retries, non-replayable request bodies, missing auth policies, miscounted per-call metrics, or server commits followed by caller timeouts creating duplicates.

Verify **HTTP attempt counts, final status, elapsed time, idempotency, log redaction, and recovery**.

| Test Case | Simulated Mock Server/Transport | Pass Criteria |
|---|---|---|
| Immediate success | Immediate 200 | One transport send, one `PER_CALL` event |
| 503 then 200 | Transient error then recovery | Retries within cap, returns success |
| 429 + `Retry-After` | Server requests wait | Does not retry early violating contract |
| 400 | Invalid request | No futile retries |
| 403 | Forbidden | Does not mask RBAC errors with retries |
| Network reset | Drop connection mid-read | Fails/retries within bounds |
| Connect stall | TCP fails to establish | Connect timeout triggers |
| Response delay | Slow first byte | Response timeout triggers |
| Read stall | Headers sent, body stalls | Read timeout triggers |
| Write stall | Server reads body slowly | Write timeout triggers |
| Async client | `Mono` subscribed | Does not block event loop |
| Sync client | `buildClient` used | Custom `processSync` forwards cleanly |
| Timeout after commit | Server commits, drops response | Zero duplicate records |
| Nested retries | App retry + SDK retry | Total attempts stay within budget |
| Sensitive logs | Simulated SAS/Authorization/PII | Zero credential leakage |
| Cancellation | Caller cancels mid-request | Write state verified |

### 17.2. Testing PER_CALL vs. PER_RETRY

Simulation:

~~~text
HTTP attempt #1 → 503
HTTP attempt #2 → 503
HTTP attempt #3 → 200

Expected (when these statuses are retried):
  PER_CALL executions = 1
  PER_RETRY executions = 3
  HTTP transport sends = 3
  Final response = 200
~~~

This reflects **one service-client invocation**. If the caller re-subscribes to the publisher or retries at the app layer, `PER_CALL` runs again; distinguish SDK attempts from business attempts.

### 17.3. Testing Tools and Scope

- Use a mock `HttpClient` or local HTTP stub server (WireMock/MockWebServer) matching dependencies.
- Simulate statuses, `Retry-After`, delays, connection resets, and partial bodies.
- Assert durations with reasonable tolerance; jitter makes exact millisecond backoff unpredictable.
- Test both `buildClient()` and `buildAsyncClient()` with custom policies.
- Assert logs contain no `Authorization`, SAS signatures, connection strings, or PII.
- For reactive chains, test timeouts and re-subscriptions.
- On authorized Azure staging, validate real DNS/TLS/managed identity and service quotas.
- Never trigger throttling incidents on shared or production resources.

Mock transports cannot replicate full TLS, private DNS, connection reuse, or service-side throttling. Always run targeted integration tests in staging.

### 17.4. Test Idempotency, Not Just Status Codes

A critical test:
1. Mock server receives POST and creates the object.
2. Before sending the response, the server drops the connection.
3. Client encounters `IOException`/timeout and retries.
4. System uses an idempotency key or conditional create.
5. Final state contains **one** business object, not two.

A test that only asserts the final HTTP status is 200 without counting created records misses double-charge/double-create bugs.

## 18. Production Monitoring and SLOs

### 18.1. Signals to Track

| Signal | Question Answered |
|---|---|
| Logical operations/sec | How many real operations is the app requesting? |
| HTTP attempts/sec | Is retry amplification happening? |
| Retry rate | Are transient errors rising? |
| Throttling 429 | Are quotas or service limits exceeded? |
| Authentication 401/403 | Did a rollout break identity or permissions? |
| Connect timeouts | Are DNS, network, or proxies failing? |
| Response/read timeouts | Is the server or payload transfer slow? |
| Dependency p95/p99 | Is it threatening API SLAs? |
| In-flight requests | Are connection or thread pools saturated? |
| Circuit breaker state | Is a dependency persistently unavailable? |
| SDK/transport version | Did an update introduce a regression? |
| Azure service transactions | Are costs and quotas being amplified? |

### 18.2. Illustrative SLO

~~~text
SLI: percentage of valid API operations completing within 500 ms.
SLO: >= 99.5% over 30 days (example target).
Alert: error budget burn rate or dependency p99 spike.
~~~

This is an **illustrative internal SLO**, not an Azure service SLA. Low p95 on one Azure dependency does not guarantee the overall API meets its SLO if other I/O or CPU stages dominate.

### 18.3. Measuring Retry Effectiveness

~~~text
Logical operations:       10,000
HTTP attempts:            13,000
Retry amplification:      1.30x
Final success rate:       99.2%
First-attempt success:    94.0%
~~~

If retries improve success rates yet push p99 over SLO, reduce retries or offload work to a queue. If retries do not raise success rates while 429s climb, the pipeline is adding harmful load.

### 18.4. Illustrative KQL

If instrumentation writes dependency records into Application Insights' workspace-based **`AppDependencies`** table:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize Total=count(),
            Failed=countif(Success == false),
            P95ms=percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), Target
| order by TimeGenerated asc
~~~

Table/column names and queries vary by telemetry schema. Seeing zero rows does not prove zero errors if data collection or sampling is misconfigured.

### 18.5. Metric Cardinality and Privacy

Never put request IDs, full URIs, Blob names containing PII, user emails, or SAS signatures into metric labels. Use bounded tags: service, operation, environment, status class, error class, and region. Keep correlation IDs in RBAC-protected logs and traces with proper retention.

## 19. Troubleshooting Runbooks

### 19.1. Symptom Table

| Symptom | Cause | Remediation |
|---|---|---|
| Client build fails | Dependency/transport version mismatch | Check `azure-sdk-bom` and Maven tree |
| 401 after custom pipeline | Missing auth policy or wrong scope | Revert to standard builder/credential |
| 403 on Blob | Missing Storage data-plane RBAC/ACL/firewall | Check roles and network |
| DNS failure | Private DNS or resolver issue | Test resolution from App Service/Pod |
| TLS handshake failure | Certificate, clock, or proxy | Inspect trust chain |
| Connect timeout | Route, NSG, or firewall | Test connectivity from runtime |
| Response timeout | Slow/overloaded server | Check metrics, capacity, and budgets |
| Read timeout | Slow stream or chunks | Check payload, network, and read settings |
| Write timeout | Slow upload | Tune chunk size and throughput |
| Continuous 429s | Throttling / retry storm | Honor `Retry-After`, cap concurrency |
| Prolonged 503s | Service incident | Circuit breaker / fallback |
| 409/412 | Conflict / stale ETag | Re-read state, resolve concurrency |
| High p99 | Retry × timeout × backoff | Enforce total deadline and retry ownership |
| Reactive app hangs | `block()`/`sleep()` on event loop | Remove blocking calls |
| Wrong SDK retry count | `PER_CALL`/`PER_RETRY` or nested retries | Count actual sends |
| Ambiguous upload outcome | Response lost after server commit | Verify Blob state/ETag |
| Token leaked in logs | `BODY_AND_HEADERS` or custom policy | Redact, rotate, and audit |
| Duplicate LROs | Retried kickoff without state check | Poll `provisioningState` |

### 19.2. HTTP 429 Runbook

1. Identify which dependency is actually returning 429.
2. Check quotas, throughput, concurrency, and request rates.
3. Audit retry loops across SDK, framework, gateway, and workers.
4. Inspect `Retry-After` and service-specific headers.
5. Measure HTTP attempts per logical operation.
6. Lower concurrency or introduce queuing/backpressure.
7. Adjust backoff, retry caps, and total deadlines.
8. Increase capacity/quotas if supported and approved.
9. Load test on staging.
10. Monitor results: 429s, p95/p99, operation counts, and cost.

### 19.3. Timeout After Enabling Private Endpoint Runbook

1. Identify the exact app runtime (Pod/Function/App Service/VM).
2. Check the endpoint FQDN configured in the builder.
3. Resolve DNS from inside that runtime.
4. Inspect Private DNS Zones, resolvers, and VNet links.
5. Inspect VNet integration, NSGs, routes, and firewalls/proxies.
6. Check TLS hostnames and certificates.
7. Verify reachability of the token/managed identity endpoint.
8. Separate DNS/TCP timeouts from data-plane 403s.
9. Never open broad public networking as a temporary workaround.
10. Document evidence and update the runbook.

### 19.4. Post-Write Timeout Runbook

1. Record the operation ID/resource ID and UTC timestamp.
2. Determine whether the server could have committed.
3. Re-read resource state with an appropriate GET.
4. Check the ETag, version, or idempotency key.
5. If already committed properly, do not write again.
6. If not committed, retry under safe conditions.
7. If state remains ambiguous, route to reconciliation/manual review.
8. Verify no duplicate business side effects occurred.
9. Tune timeouts, rates, or circuit breakers based on root cause.
10. Never treat client cancellation as a transaction rollback.

### 19.5. Post-SDK-Upgrade Regression Runbook

- Inspect `azure-core`, transport, library versions, and dependency convergence.
- Check `retryOptions`, `retryPolicy`, and pipeline precedence.
- Compare per-attempt and per-operation metrics before and after the update.
- Check JDK, TLS, and proxy changes.
- Run mock 429/503/timeout tests.
- Run integration/canary tests on staging.
- Execute controlled rollback if p99, error rate, or cost regresses.
- Update release notes and ADRs for timeout/retry profiles.



## 20. Designing HTTP Configuration by Workload

### 20.1. Do Not Use One Timeout for Every Dependency

- **App Configuration:** small config/feature flag reads, interactive latency, cacheable.
- **Key Vault:** sensitive secrets, rotation, strict request/quota hygiene.
- **Blob Storage:** large upload/download payloads and multi-block requests.
- **Resource Manager:** resource deployments with long-running operations and polling.
- **Queues/Events:** duplicate delivery, message IDs, and lock semantics.
- **Cosmos DB:** dedicated SDK and retry/transport abstractions—do not mechanically apply generic `azure-core` examples.

A Java architecture should define **per-service/operation retry profiles** with validation, empirical measurement, and change approval.

### 20.2. Illustrative Configuration Sample

~~~json
{
  "serviceProfiles": {
    "appConfiguration": {
      "connectTimeoutMs": 3000,
      "responseTimeoutMs": 5000,
      "readTimeoutMs": 5000,
      "writeTimeoutMs": 5000,
      "maxRetries": 2,
      "baseDelayMs": 200,
      "maxDelayMs": 1200
    },
    "blobUpload": {
      "connectTimeoutMs": 5000,
      "responseTimeoutMs": 30000,
      "readTimeoutMs": 60000,
      "writeTimeoutMs": 60000,
      "maxTries": 4,
      "tryTimeoutMs": 30000
    }
  }
}
~~~

This is an **application-defined configuration schema**, not JSON parsed automatically by the SDK. Map it carefully into builders:

1. Validate positive `Duration` values and maximum retry caps.
2. Disallow zero values that silently disable timeouts.
3. Separate total operation deadlines from transport timeouts.
4. Record version/profile metadata in releases.
5. Update test fixtures whenever retry profiles change.
6. Review quota, cost, and latency impacts before rollout.

### 20.3. Client Lifecycle in Java

A long-lived Spring Boot, Micronaut, Quarkus, or Java service should:
- Initialize credentials per identity policy.
- Construct transports and Azure clients at startup via DI.
- Reuse clients across HTTP requests.
- Monitor connection pools and in-flight operations.
- Never create new event loops or `HttpClient` instances per request.
- Handle clean shutdown/closing per transport/client API contracts.

If different Azure services have conflicting network or TLS requirements, do not force them onto a single shared transport with incompatible proxy or certificate settings.

## 21. Case Study: Java Orders API on Azure

### 21.1. Problem Statement

A Java service on Azure App Service/AKS:
- Reads feature flags from App Configuration.
- Fetches secrets from Key Vault at startup/rotation.
- Stores invoice PDFs in Blob Storage.
- Writes order status to Azure SQL Database.
- Targets low p95 latency on its HTTP API.
- Runs longer background invoice uploads.
- Must never create duplicate invoices on timeouts or retries.
- Enforces Private Endpoints and managed identities per security policy.

~~~mermaid
flowchart LR
    C["Client"] --> APP["Java API App Service / AKS"]
    APP --> CFG["App Configuration"]
    APP --> KV["Key Vault"]
    APP --> DB["Azure SQL Database"]
    APP --> BLOB["Blob Storage"]
    APP --> MON["Azure Monitor / Application Insights"]
~~~

### 21.2. Dividing Retry Ownership

| Step | Retry Owner | Correctness Mechanism |
|---|---|---|
| Read App Configuration | SDK within short deadline | Cache/fallback per freshness policy |
| Fetch Key Vault secret | SDK honoring server hints | Secret rotation and least privilege |
| Upload Blob | Storage SDK with per-try timeout | Stable blob name, ETag/conditional write |
| Azure SQL transaction | Dedicated JDBC/DB logic | Unique constraints, transactions, outbox |
| HTTP ingress | Gateway avoids blind POST retries | Idempotency key |
| Background invoice job | Queue/worker scheduler | Stable invoice ID and reconciliation |

**The Azure SDK HTTP RetryPolicy does not govern SQL JDBC transactions**. If a Storage upload succeeds yet the worker loses the response, never generate a new invoice with a random blob name.

### 21.3. 429 Scenario During Scale-Out

A flash sale scales App Service from 5 to 50 instances. Every instance fetches config on every request. App Configuration begins returning 429; all instances retry with identical delays, driving up 429s and p99 latency.

Improvements:
1. Add controlled config caching/refresh.
2. Keep retries low within the API's total deadline.
3. Honor `Retry-After`.
4. Rate-limit refresh operations.
5. Add jitter to desynchronize retries.
6. Add circuit breaker/fallback where business allows.
7. Measure actual HTTP attempts rather than just SDK calls.
8. Load test on staging after tuning.

### 21.4. Upload Timeout Where the Service Committed

~~~text
Worker generates invoice with a stable invoiceId.
Storage receives and commits the upload.
Network drops the response.
Worker observes a timeout.
Retry must verify object state/ETag
or use conditional create with the same blob name.
~~~

Maintain durable processing state and mark jobs complete only after verification; sending invoice emails also needs its own idempotency key to prevent duplicate notifications.

### 21.5. Acceptance Criteria

- Managed identities and data-plane permissions are accurate.
- Zero secrets in logs.
- Azure service clients are reused.
- No unintended nested retries.
- Timeouts distinguish connect/response/read/write/total.
- 429s trigger backpressure instead of retry storms.
- Uploads never produce duplicate invoices.
- p95/p99 latency and costs stay within targets.
- Fault-injection evidence and runbooks exist.
- Rollback plan ready if retry setting changes regress.

## 22. Common Pitfalls

1. **Adding another RetryPolicy via addPolicy:** creates nested retries or breaks policy ordering; prefer builder `retryOptions`/`retryPolicy`.
2. **Confusing `pipeline(...)` with `httpClient(...)`:** `pipeline` replaces all policies, potentially dropping credential, retry, and log defaults.
3. **Assuming `Duration.ZERO` means instant timeout:** on some transports it disables the timeout; use positive durations.
4. **Setting only `connectTimeout`:** leaves response, read, write, and total duration unbounded.
5. **Confusing `maxRetries` with `maxTries`:** triggers more attempts than intended.
6. **Retrying all 4xx responses:** 400/401/403/412 usually require fixing inputs, identity, or concurrency.
7. **Ignoring `Retry-After`:** causes sustained 429s and extra charges.
8. **Assuming POST is idempotent:** creates duplicate entities when responses drop.
9. **Logging `BODY_AND_HEADERS` in production:** leaks secrets/PII and adds overhead.
10. **Calling `block()`/`Thread.sleep` on a reactive event loop:** degrades throughput or causes deadlock-like starvation.
11. **Increasing timeouts to fix DNS/firewalls:** only delays failure.
12. **Creating an `HttpClient` per API request:** adds initialization and pooling overhead.
13. **Skipping tests after a BOM upgrade:** version changes can alter transports and retries.
14. **Optimizing success rate while ignoring p99:** excessive retries violate API SLOs.
15. **Disabling TLS hostname verification:** risks token and data exposure; never an acceptable workaround.
16. **Treating client timeouts as transaction rollbacks:** the server may have already finished the write.



## 23. Pre-Production Checklist

### Dependencies and Client Lifecycle

- [ ] Using the modern Azure SDK for Java without mixing legacy SDKs.
- [ ] `azure-core`, transport, and service SDK versions aligned via BOM.
- [ ] No unintended conflicts among Netty/OkHttp/JDK HTTP transports.
- [ ] Builder actually supports `httpClient`/`retryOptions`/`addPolicy` as coded.
- [ ] Clients instantiated via DI/singletons, never per HTTP request.
- [ ] Java runtime, TLS, and transport carry current security patches.
- [ ] SDK upgrades validated with regression tests and canary rollouts.

### HTTP Pipeline

- [ ] Prefer builder customization over assembling full pipelines manually.
- [ ] `PER_CALL`/`PER_RETRY` chosen based on operation vs. attempt scope.
- [ ] Custom policies support both sync and async paths where required.
- [ ] `next.process` never called multiple times unintentionally.
- [ ] No duplicate `RetryPolicy` added alongside SDK defaults.
- [ ] `Authorization` or signed headers never overwritten.
- [ ] Per-request state never stored in shared mutable fields.
- [ ] If `pipeline(...)` is used, auth and service policies are thoroughly reviewed.
- [ ] Safe correlation, tracing, and metrics are in place.

### Timeouts and Retries

- [ ] Connect/response/read/write timeouts have documented rationale and positive values.
- [ ] Per-try timeout distinguished from total operation deadline.
- [ ] `maxRetries` vs. Storage `maxTries` understood accurately.
- [ ] Max retry counts and total time budgets enforced.
- [ ] `Retry-After` and server hints honored per SDK support.
- [ ] Retries never breach business SLOs.
- [ ] No unintended retry nesting across app, gateway, and SDK.
- [ ] POST/PUT side effects protected by idempotency or conditional writes.
- [ ] Backoff + jitter, concurrency limits, and rate limiters configured as needed.
- [ ] Circuit breakers or queues handle prolonged dependency outages.
- [ ] Cancellation never relied upon as a rollback guarantee.

### Security and Operations

- [ ] `DefaultAzureCredential` selects the intended runtime identity.
- [ ] Data-plane RBAC/ACLs follow least privilege.
- [ ] TLS hostname and certificate validation remain enabled.
- [ ] Private DNS, VNet, and Private Endpoints verified from the real runtime.
- [ ] `HttpLogOptions` set appropriately (`BASIC`/`NONE`) for production.
- [ ] Logs and traces exclude SAS tokens, access tokens, secrets, and unnecessary PII.
- [ ] Metrics maintain low cardinality and proper retention.
- [ ] Dashboards monitor 429, 401/403, timeouts, and p95/p99 latency.
- [ ] Fault-injection tests simulate 429/503/timeouts.
- [ ] Incident runbooks exist for network, auth, and retry storms.
- [ ] Cost/quota monitoring tracks spikes in HTTP attempts.
- [ ] Approval and rollback plans cover timeout/retry profile changes.

## 24. Self-Check Questions

1. **What makes up the Azure SDK for Java HTTP pipeline?** An HTTP transport and a chain of HTTP policies.
2. **What is `HttpClient` responsible for?** Establishing connections and sending/receiving HTTP traffic.
3. **What can an `HttpPipelinePolicy` do?** Inspect/transform requests and responses and forward execution.
4. **How many times does a `PER_CALL` policy execute?** Once per pipeline invocation/service call.
5. **When does a `PER_RETRY` policy execute?** On every HTTP attempt inside the retry loop.
6. **What is the default `HttpPipelinePolicy` position in current SDKs?** `PER_RETRY`.
7. **Why place total operation metrics at `PER_CALL`?** To measure full operation duration including backoff.
8. **Why place attempt counters at `PER_RETRY`?** Each individual attempt needs to be observed.
9. **Should you manually build the full `HttpPipeline` for every service client?** No; usually customize through the builder.
10. **How does `httpClient(...)` differ from `pipeline(...)`?** One swaps the transport; the other replaces the entire pipeline.
11. **Why is `pipeline(...)` risky?** It can bypass builder configuration and mandatory auth/service policies.
12. **Is Netty typically the default transport?** Yes, in many modern Azure SDK for Java libraries.
13. **What does connect timeout measure?** Limits the connection establishment phase.
14. **What does response timeout measure?** Waiting for the server to start responding per transport semantics.
15. **Is read timeout a total download timeout?** Not by default; it depends on read/inactivity semantics.
16. **Does write timeout mean the entire upload must finish in that window?** Not necessarily; it typically governs write operations/inactivity.
17. **Does `Duration.ZERO` always mean instant timeout?** No; many transports treat it as disabling the timeout.
18. **How does a total operation deadline differ from per-try timeout?** It covers retries, backoff, and the application budget.
19. **Which objects work with `RetryOptions`?** `ExponentialBackoffOptions` or `FixedDelayOptions`.
20. **How many total HTTP attempts does `setMaxRetries(3)` typically allow?** Up to 4, including the initial request.
21. **What does Storage `RequestRetryOptions` `maxTries=4` mean?** Up to 4 attempts total, including the initial request.
22. **How does exponential backoff help?** Reduces retry bursts during transient failures.
23. **What risk does fixed delay pose with many clients?** Synchronized retries hitting at the exact same cadence.
24. **What is `Retry-After` for?** Server guidance telling clients how long to wait before retrying.
25. **What does HTTP 429 usually indicate?** Rate limiting / throttling.
26. **Should you retry 403 to fix a missing role?** No.
27. **What does HTTP 412 usually relate to?** Precondition / ETag / optimistic concurrency mismatch.
28. **Does a network timeout prove the server did not commit?** No.
29. **Is POST always idempotent?** No.
30. **What is one way to avoid duplicate order creation?** Stable idempotency keys and unique constraints.
31. **Should you add another `RetryPolicy` via `addPolicy` when the SDK already retries?** Not by default.
32. **Why is app retry × SDK retry dangerous?** Multiplies total attempts and latency.
33. **What is a circuit breaker for?** Failing fast when a dependency is persistently unhealthy.
34. **What is a bulkhead for?** Limiting concurrency and isolating resources.
35. **Why is jitter needed?** To spread retry timing across instances.
36. **What is the risk of enabling `BODY_AND_HEADERS` in production?** Exposing PII/secrets plus cost and performance overhead.
37. **What should metric labels avoid?** Full URIs, user IDs, request IDs, and SAS queries.
38. **Does `Mono.timeout` replace Netty `connectTimeout`?** No.
39. **Should you block on a Reactor event loop?** No.
40. **Can subscribing to a `Mono` twice send two requests?** Yes, depending on the publisher and subscription.
41. **Does `App Configuration Data Reader` differ from Azure `Contributor`?** Yes, it is a dedicated data-plane permission.
42. **Is a 1 GB Blob upload always one HTTP request?** No, the SDK may split it into blocks.
43. **Is retrying uploads against `secondaryHost` always safe?** No; consistency and operation semantics apply.
44. **Is an LRO polling interval the same as an HTTP retry delay?** No.
45. **Can you test 429 behavior against mocks?** Yes, without overloading Azure production.
46. **What should a fault-injection test assert?** Attempts, status, elapsed time, side effects, and log redaction.
47. **What should you check upon 401 after using a custom pipeline?** Authentication policy, token acquisition, and scope.
48. **What should you check on connect timeout after enabling a Private Endpoint?** DNS, VNet routes, and NSGs/firewalls from the runtime.
49. **Why track HTTP attempts separately from logical operations?** To detect retry amplification.
50. **What makes up a strong production HTTP policy?** Safe pipeline, timeout budgets, bounded retries, idempotency, least privilege, observability, testing, and runbooks.

## 25. References

Official sources for verifying exact APIs for your Azure SDK version:

- [HTTP clients and pipelines in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipeline) — transport, pipeline, policy positions, builder customization.
- [Azure SDK for Java overview](https://learn.microsoft.com/azure/developer/java/sdk/overview) — SDK scope and Java documentation.
- [Azure Core HTTP pipeline policy interface](https://learn.microsoft.com/java/api/com.azure.core.http.policy.httppipelinepolicy) — `process`, `processSync`, `getPipelinePosition`.
- [HTTP pipeline package](https://learn.microsoft.com/java/api/com.azure.core.http) — `HttpPipeline`/`HttpClient`/`HttpPipelineBuilder`.
- [HTTP policy package](https://learn.microsoft.com/java/api/com.azure.core.http.policy) — `RetryPolicy`, logging, and policy types.
- [RetryOptions Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.retryoptions) — `RetryOptions`/strategies.
- [ExponentialBackoffOptions Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.exponentialbackoffoptions) — `maxRetries`/`baseDelay`/`maxDelay`.
- [RetryPolicy Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.retrypolicy) — retry behavior.
- [NettyAsyncHttpClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder) — connect, response, read, write timeouts.
- [RequestRetryOptions for Azure Storage](https://learn.microsoft.com/java/api/com.azure.storage.common.policy.requestretryoptions) — storage-specific `maxTries`/`tryTimeout`.
- [Implement a retry policy using Azure Storage for Java](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java) — Blob client retries.
- [BlobServiceClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.storage.blob.blobserviceclientbuilder) — `httpClient`, `addPolicy`, `retryOptions`, and pipeline precedence.
- [ConfigurationClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.data.appconfiguration.configurationclientbuilder) — Azure App Configuration client options.
- [Configure logging in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview) — `HttpLogDetailLevel` and redaction.
- [Troubleshooting Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/troubleshooting-overview) — diagnostics.
- [Azure Core source README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/core/azure-core/README.md) — transport, pipeline, and timeout layers.
- [Azure Well-Architected retry strategy](https://learn.microsoft.com/azure/architecture/patterns/retry) — retry/backoff/idempotency.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — monitoring budgets and costs.

**Conclusion:** in the Azure SDK for Java, the **HTTP transport** governs connections and HTTP I/O; **`HttpPipelinePolicy`** adds processing at **`PER_CALL` or `PER_RETRY`** scope; and **`RetryOptions`/`RetryPolicy`** along with specialized options like **Storage `RequestRetryOptions`** govern retries. To deploy safely, start from the service client builder, configure appropriate **connect/response/read/write timeouts** and **total deadlines**, keep retries **bounded and `Retry-After`-aware**, avoid stacking multiple retry loops, ensure **idempotency** for operations with side effects, protect credentials and logs, and measure **HTTP attempts, p95/p99 latency, throttling, errors, and cost**. Only roll out policy changes to production after fault-injection testing, verifying permissions/networking, and preparing a rollback runbook.
