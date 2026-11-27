# Customizing Azure Client Builders, HTTP Pipelines, and Proxies

When a Spring Boot application uses Azure Blob Storage, Key Vault, or Service Bus, Spring Cloud Azure's default configuration is often sufficient for basic connections. However, in enterprise environments with **HTTP proxies**, **Private Endpoints**, or requirements around **timeouts**, **retries**, **HTTP logging**, or **observability**, developers need a deeper understanding of how the Azure SDK for Java constructs clients and dispatches requests.

A familiar failure is uploading a Blob successfully from a laptop, yet encountering **407 Proxy Authentication Required**, TLS errors, timeouts, or an inability to acquire an access token when running in CI or a corporate network. To handle this properly, distinguish the configuration of the **Azure service client**, **HTTP transport**, **HTTP pipeline**, and **credential**; each layer can use a different connectivity path.

This lesson belongs to the **Azure Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; focusing on identity/permissions, storage, messaging, data, secrets, integration testing, and comparing differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish **service client builder**, **transport HttpClient**, **HttpPipeline**, **HttpPipelinePolicy**, and **TokenCredential** in the Azure SDK for Java.
2. Create and reuse a **BlobServiceClient** via **BlobServiceClientBuilder** with configured endpoint, identity, HTTP client, and logging.
3. Configure an HTTP proxy for a specific transport, understanding the roles of HTTPS CONNECT, TLS, authentication, and proxy bypass.
4. Explain the limitations of HTTP proxies for services using **AMQP**, WebSockets, and certain database connections.
5. Choose between **Spring Cloud Azure auto-configuration** and defining custom client beans when customization is needed.
6. Build retry/timeout policies, safe logging/tracing, and connectivity tests across local, CI, and Azure runtimes.
7. Diagnose proxy, DNS, TLS, credential, Azure RBAC, and SDK errors without exposing secrets.

## 2. The Connectivity Layers Inside the Azure SDK

~~~mermaid
flowchart TD
    A[Spring Boot service] --> B[Azure service client\nBlobServiceClient / SecretClient]
    B --> C[Azure SDK HTTP pipeline]
    C --> D[Authentication policy\nTokenCredential]
    C --> E[Retry / logging / custom policies]
    C --> F[HTTP transport: Netty / OkHttp / ...]
    F --> G{Proxy on network?}
    G -->|Yes| H[HTTP proxy / HTTPS CONNECT]
    G -->|No| I[DNS / private routing]
    H --> J[Azure data endpoint]
    I --> J
    D --> K[Microsoft Entra token endpoint]
~~~

This diagram is a **conceptual** model: pipeline execution order, where retries are handled, and how the Azure Identity SDK issues HTTP requests depend on the library and version. Token-acquisition requests to Microsoft Entra may use the **credential's own HTTP transport**, separate from the transport calling Blob Storage unless configured uniformly.

| Layer | Responsibility | Example |
| --- | --- | --- |
| **Service client** | Exposes the Azure service's business APIs | **BlobServiceClient**, **BlobClient**, **SecretClient** |
| **Client builder** | Accepts endpoint, credential, transport, and options to construct a client | **BlobServiceClientBuilder** |
| **HTTP pipeline** | Applies policies around HTTP requests/responses | Authentication, retry, telemetry, logging |
| **HttpPipelinePolicy** | Component processing requests/responses inside the pipeline | Header policy, tracing/correlation |
| **HttpClient** (Azure Core) | Executes HTTP requests over the concrete transport | Netty, OkHttp depending on dependencies |
| **Proxy** | Intermediary forwarding connections per network policy | Corporate HTTP CONNECT proxy |
| **TokenCredential** | Supplies an appropriate access token for the service | DefaultAzureCredential, ManagedIdentityCredential |
| **Azure RBAC** | Determines whether the principal may operate on the resource | Storage Blob Data Contributor |

**A client builder is not an open network connection.** Many Azure SDKs construct the client object without yet acquiring a token or contacting Azure; configuration is only truly exercised on the first request.

## 3. Service Client Builder: Where to Customize?

The Azure SDK for Java provides per-service builders. Each builder accepts parameters suited to that service's API.

| Service | Typical Builder | Important Customizations |
| --- | --- | --- |
| Azure Blob Storage | **BlobServiceClientBuilder** | Endpoint/account, TokenCredential, HTTP transport, retry, logging |
| Azure Key Vault Secrets | **SecretClientBuilder** | Vault URL, credential, HTTP transport, policy/logging |
| Azure App Configuration | **ConfigurationClientBuilder** | Store endpoint, credential, transport, and retry |
| Azure Service Bus | **ServiceBusClientBuilder** | Namespace, credential, AMQP transport, processor/producer options |
| Azure Event Hubs | **EventHubClientBuilder** or specialized builders | Namespace/event hub, credential, AMQP transport, and processing |
| Azure Cosmos DB | **CosmosClientBuilder** | Endpoint, credential, consistency, direct/gateway, and connection settings |

Do not assume all builders share the same methods, even within the Azure SDK. For example, one builder takes **endpoint(URL)** while another takes **fullyQualifiedNamespace(hostname)**. Some SDKs use TCP/AMQP transports, so configuring Azure Core's **HttpClient** is not a universal control knob for every connection.

### Creating BlobServiceClient Directly

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class AzureBlobClients {

    private AzureBlobClients() {}

    public static BlobServiceClient create(String endpoint) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Example endpoint in Azure public cloud: **https://stordersdev01.blob.core.windows.net**. Never pass an Azure Resource Manager ID shaped like **/subscriptions/...** as the Blob client's endpoint.

SDK clients are designed to be **reused**. In Spring Boot, keep the client as a **singleton bean** rather than creating a builder/client per HTTP request. Repeatedly constructing clients increases resource overhead, scatters configuration, and complicates connection-pool inspection.

### Synchronous and Asynchronous

Blob Storage provides both synchronous and asynchronous clients within its API surface. From the same builder, you can construct clients using the appropriate methods, such as **buildClient()** or **buildAsyncClient()** where supported by the API. Choose based on architecture:

- Standard Spring MVC handlers typically use the synchronous client.
- Spring WebFlux or high-throughput pipelines can use the async client and manage backpressure.
- Never call thread-blocking synchronous APIs on the WebFlux event loop.
- Never instantiate a new HTTP transport/connection pool per item in a data stream.

## 4. Common HTTP Configuration Categories

| Need | Appropriate Configuration Location | Watch Out For |
| --- | --- | --- |
| Azure target | Builder **endpoint** or **fullyQualifiedNamespace** | Correct DNS/cloud environment and resource |
| Principal/token | **TokenCredential** or builder credential mechanism | Correct tenant, identity, and RBAC |
| HTTP proxy | HTTP transport or SDK-supported transport settings | Do not assume every protocol uses the proxy |
| Connection timeouts | HTTP transport or connection options | Distinguish connect, read, response, and overall operation |
| Retries | Service SDK retry options or HTTP pipeline | Avoid unbounded retries and breaking idempotency |
| Headers/telemetry | Pipeline policies or supported SDK diagnostics | Never log tokens, SAS, or sensitive data |
| Certificates/trust | Runtime/transport trust store and TLS policy | Never disable certificate validation |
| Sockets/concurrency | HTTP client pool, SDK connection settings | Align with load and service limits |
| Private Endpoint | Infrastructure DNS, routes, VNet, firewall | Never replace the service hostname with an arbitrary IP |

**There is no single configuration that applies across the entire Azure SDK.** Each service uses its own transport stack; many applications also run several different HTTP clients: Spring WebClient, the Azure Blob client, and the Azure Identity credential client.

## 5. How Does the HTTP Pipeline Work?

The Azure Core HTTP pipeline composes **HttpPipelinePolicy** instances before and after a request traverses the **HttpClient**. Typical responsibilities include:

1. Adding common headers and request metadata.
2. Authenticating requests using a token or appropriate credential mechanism.
3. Emitting logs, traces, and metrics per configuration.
4. Executing retries/backoff for eligible errors when supported by the SDK.
5. Dispatching requests over the HTTP transport and receiving responses.

Execution order, invocation counts, and which policies re-run during retries depend on the **actual SDK and pipeline configuration**. Do not rely on the ordering in an illustrative diagram to build security-sensitive logic such as request signing or security boundaries.

### Adding a Custom Policy at the Builder Level

Example creating a policy that only adds a header carrying **non-sensitive** technical metadata:

~~~java
import com.azure.core.http.HttpPipelineCallContext;
import com.azure.core.http.HttpPipelineNextPolicy;
import com.azure.core.http.HttpResponse;
import com.azure.core.http.policy.HttpPipelinePolicy;
import reactor.core.publisher.Mono;

public final class ComponentHeaderPolicy implements HttpPipelinePolicy {

    @Override
    public Mono<HttpResponse> process(
            HttpPipelineCallContext context,
            HttpPipelineNextPolicy next) {

        context.getHttpRequest()
                .setHeader("x-app-component", "documents-api");
        return next.process();
    }
}
~~~

Attach the policy to the Blob client builder in versions supporting **addPolicy**:

~~~java
BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .addPolicy(new ComponentHeaderPolicy())
        .buildClient();
~~~

The policy above illustrates the pipeline extension point. Do not use it to inject an **Authorization header**, craft SAS tokens, store access tokens, arbitrarily mutate request payloads, or attempt to bypass security policies.

**Custom headers may be transmitted to Azure and through proxies**, so include only information permitted to be exposed to downstream systems. If you need per-request correlation IDs, use proper trace/context propagation; do not hard-code a static ID and assume each request is distinguished.

### Beware When Policies Execute Multiple Times

Retries can cause a single request to be processed more than once in certain pipeline layers. Therefore, policies must **have no dangerous side effects**; never send extra messages or write to a database directly inside a policy just because it runs on an HTTP request.

## 6. Safe HTTP Logging and Tracing Configuration

The Azure SDK provides version-dependent HTTP logging options, such as **HttpLogOptions** and **HttpLogDetailLevel**.

~~~java
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

HttpLogOptions logOptions = new HttpLogOptions()
        .setLogLevel(HttpLogDetailLevel.BASIC);

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .httpLogOptions(logOptions)
        .buildClient();
~~~

The **BASIC** level illustrates limited HTTP metadata logging. Exact logged fields depend on the SDK/version and logger settings; inspect actual output in tests, especially if endpoints or URLs contain sensitive data.

**Never log:** access tokens, refresh tokens, **Authorization** headers, account keys, SAS query parameters, connection strings, secret values, request/response bodies containing personal data, or proxy credentials.

For production observability:

- Record **request ID/correlation ID**, duration, status, retry count, error rate, and circuit metrics at an appropriate level.
- Integrate tracing/OpenTelemetry as supported by the SDK and your monitoring stack.
- Apply sampling and retention limits to avoid massive log volumes.
- Preserve trace context across HTTP proxies; never manually record or attach tokens to span attributes.

HTTP logging is an investigative tool; it does not replace business-layer error monitoring and Azure service metrics.

## 7. What Is an HTTP Proxy and What Is HTTPS CONNECT For?

An **HTTP forward proxy** is an intermediary server that clients may have to traverse to reach the Internet. For requests to an **HTTPS** service, the client typically uses **CONNECT** to establish a tunnel through the proxy, and then performs TLS verification against the target hostname according to transport and proxy settings.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot / Azure HTTP client
    participant P as Corporate HTTP proxy
    participant S as Azure Blob HTTPS endpoint
    A->>P: CONNECT stexample.blob.core.windows.net:443
    P-->>A: HTTP 200 Connection Established
    A->>S: TLS handshake over tunnel
    S-->>A: TLS certificate for Azure hostname
    A->>S: HTTPS request (token + Blob operation)
    S-->>A: Response per RBAC / service policy
~~~

Depending on corporate policy, the proxy may require authentication or perform TLS inspection. The system must trust valid certificate chains via a managed trust store; **never disable TLS hostname verification or certificate validation** to get past proxy errors.

### HTTP Proxy vs. Private Endpoint

| Mechanism | Purpose | What to Remember |
| --- | --- | --- |
| **HTTP forward proxy** | Routes/controls outbound HTTP(S) traffic | Client/transport must use the proxy per policy |
| **Private Endpoint / Private Link** | Provides private IP access to an Azure service inside a supported network | DNS and routing from the runtime must be correct |
| **Firewall/VNet rules** | Restricts allowed traffic flows | Valid RBAC with wrong network still fails |
| **Corporate TLS inspection** | Intermediary TLS termination per policy | Requires a valid trust chain; never skip validation |

With a Private Endpoint, the application typically still calls the service's **standard hostname** (e.g., **stexample.blob.core.windows.net**), while internal DNS resolves it to a private IP. Sending all requests through a corporate proxy outside the VNet that lacks a path to the private endpoint can inadvertently break the private route. Apply **proxy bypass** rules per your organization's network architecture and verify where DNS actually resolves.

## 8. Configuring the Netty HTTP Transport with a Proxy

The Azure SDK for Java includes HTTP transports such as **azure-core-http-netty** and **azure-core-http-okhttp**. When using Netty, you can build an **HttpClient** and pass it into the Blob builder.

Example using the Netty transport and an internal HTTP proxy:

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import java.net.InetSocketAddress;

public final class ProxyBlobClientFactory {

    private ProxyBlobClientFactory() {}

    public static BlobServiceClient create(
            String endpoint, String proxyHost, int proxyPort) {

        ProxyOptions proxyOptions = new ProxyOptions(
                ProxyOptions.Type.HTTP,
                new InetSocketAddress(proxyHost, proxyPort));

        HttpClient httpClient = new NettyAsyncHttpClientBuilder()
                .proxy(proxyOptions)
                .build();

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .httpClient(httpClient)
                .buildClient();
    }
}
~~~

This example configures a **proxy for the Blob client's HTTP transport**. To compile, the project needs the dependency providing **NettyAsyncHttpClientBuilder**, typically **com.azure:azure-core-http-netty**; manage its version consistently with the Spring Cloud Azure / Azure SDK BOM.

**Important limitation:** the snippet above **does not yet ensure that DefaultAzureCredential's token-acquisition requests also go through the proxy**. Azure Identity may use its own HTTP client. If the environment only permits outbound traffic via the proxy, configure the transport for **credential/token acquisition** using the API of your Azure Identity version; verify connectivity to both **Microsoft Entra** and Blob Storage.

### Things Not to Assume

- Setting **HTTPS_PROXY** can help, yet **not every Java transport/SDK reads it identically by default**.
- JVM properties such as **https.proxyHost**/**https.proxyPort** are not guaranteed to be honored by Netty and every Azure SDK the way a standard JDK HTTP client honors them.
- An HTTP proxy configured on a Blob client **does not automatically configure** a Service Bus AMQP client or Cosmos DB direct TCP transport.
- **NO_PROXY** or bypass lists must also be verified against the specific library and runtime.

Proxy authentication, bypass, timeout, and pooling properties vary by HTTP provider version. If the proxy requires a username/password, use the proxy authentication API supported by the transport and load secrets from a secret store; never put passwords in source code or logs.

## 9. Spring Boot Example: Configuring Clients Directly via Beans

When an application needs conditional proxy settings per environment, you can manage the client in a **@Configuration** class and load parameters from environment variables.

### 9.1. application.yml

~~~yaml
app:
  azure:
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
      container: ${AZURE_BLOB_CONTAINER:documents}
    proxy:
      host: ${APP_HTTP_PROXY_HOST:}
      port: ${APP_HTTP_PROXY_PORT:0}
~~~

On a developer machine, **APP_HTTP_PROXY_HOST** can be left blank if direct internet access is available. In proxied networks, set the managed host and port.

Never store proxy usernames/passwords in configuration files committed to Git. If proxy authentication is required, use a secret store or platform credential injection mechanism.

### 9.2. Spring @Configuration

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.net.InetSocketAddress;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobClientConfiguration {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${app.azure.blob.endpoint}") String endpoint,
            @Value("${app.azure.proxy.host:}") String proxyHost,
            @Value("${app.azure.proxy.port:0}") int proxyPort) {

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        BlobServiceClientBuilder builder =
                new BlobServiceClientBuilder()
                        .endpoint(endpoint)
                        .credential(credential);

        if (!proxyHost.isBlank()) {
            if (proxyPort < 1 || proxyPort > 65535) {
                throw new IllegalArgumentException(
                        "Proxy port must be between 1 and 65535");
            }

            ProxyOptions options = new ProxyOptions(
                    ProxyOptions.Type.HTTP,
                    new InetSocketAddress(proxyHost, proxyPort));

            HttpClient httpClient = new NettyAsyncHttpClientBuilder()
                    .proxy(options)
                    .build();

            builder.httpClient(httpClient);
        }

        return builder.buildClient();
    }
}
~~~

This example conditionally selects a proxy for the **Blob HTTP transport**. If credentials must also traverse the proxy, add matching configuration for **Azure Identity** based on your SDK version; otherwise, the app can fail immediately during token acquisition.

Spring Boot manages **BlobServiceClient** as a reusable bean. Never instantiate it inside individual controller methods. In larger systems, define dedicated configuration properties and validate hostname, port, endpoint, retries, and timeouts.

### 9.3. Business Service

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentBlobStorage {

    private final BlobContainerClient container;

    public DocumentBlobStorage(
            BlobServiceClient client,
            @Value("${app.azure.blob.container}") String containerName) {
        this.container = client.getBlobContainerClient(containerName);
    }

    public void upload(String name, byte[] bytes) {
        container.getBlobClient(name).upload(
                new ByteArrayInputStream(bytes), bytes.length, false);
    }
}
~~~

The method only handles data operations, unaware of proxy host or credential details. **The Blob container must already exist**, the identity needs the appropriate write role, and networking must permit the request. For large payloads, switch to streaming/multipart via the appropriate API; avoid holding entire files in byte arrays in every production scenario.

## 10. Using a Spring Cloud Azure Starter vs. Defining Custom Builders

A project already using **spring-cloud-azure-starter-storage-blob** can inject the **BlobServiceClient** auto-configured by the starter. This works well when you only need endpoint/account, identity, and standard properties supported by your Spring Cloud Azure version.

When specialized proxy/pipeline settings are needed, there are two paths:

| Approach | Advantages | What to Verify |
| --- | --- | --- |
| **Keep auto-configuration, use supported properties or extension points** | Preserves Spring Cloud Azure conventions and starter dependency wiring | Specific properties/customizers **depend on version**; never guess property names |
| **Declare a custom BlobServiceClient bean** | Full control over endpoint, transport, credential, policies, and pools | Avoid duplicate beans, auto-configuration conditions, qualifiers, and dependencies |

Before adding configuration, check **the official documentation for your Spring Cloud Azure version**. Some starters expose dedicated customization hooks; do not assume every starter shares the same property names or that one customizer applies to every Azure client.

### Duplicate Beans and Inconsistent Configuration

If a starter creates a **BlobServiceClient** and the application defines another bean of the same type, constructor injection can become ambiguous or one configuration can shadow another. Depending on auto-configuration conditions:

- Spring Boot may back off its auto-configured bean if an application bean of the same type already exists.
- Multiple clients for multiple Azure accounts can coexist when explicitly defined by the application.
- If multiple clients are needed, use **@Qualifier** and clear bean names.

Do not rely on "whichever bean happens to win" for production client behavior. Check the **condition evaluation report** and integration tests to verify which endpoint/credential is actually used.

## 11. Special Considerations for Service Bus and Event Hubs: AMQP vs. HTTP

Blob Storage, Key Vault Secrets, and several other SDKs use HTTP(S) for the data plane, whereas **Azure Service Bus** and **Azure Event Hubs** primarily use **AMQP** for messaging. Consequently, a Netty HttpClient configured with a proxy for Blob **does not automatically control** a messaging client's AMQP connection.

Typically:

- **AMQP over TCP** uses a dedicated port and protocol, commonly **5671/TLS**.
- Some Azure messaging SDKs provide **AMQP over WebSockets** over **443**, useful in networks blocking direct AMQP ports.
- WebSockets over 443 **do not automatically guarantee** compatibility with every corporate proxy; verify proxy support in the specific SDK transport.
- Event Hubs uses a partition/checkpoint model; read permission for events does not automatically grant Blob permission if the consumer stores checkpoints in Blob Storage.

Example selecting WebSockets transport in a supporting Service Bus Java SDK version:

~~~java
import com.azure.core.amqp.AmqpTransportType;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;

ServiceBusClientBuilder builder = new ServiceBusClientBuilder()
        .fullyQualifiedNamespace("orders-dev.servicebus.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .transportType(AmqpTransportType.AMQP_WEB_SOCKETS);
~~~

This only configures the **builder**; it does not yet create a sender/receiver or send messages. The SDK/version may have separate proxy settings for AMQP transport; consult the service documentation and verify in the real network environment. **Do not speculatively pass a Blob HttpClient into a Service Bus builder**.

### Cosmos DB Also Has Distinct Connection Modes

The Azure Cosmos DB Java SDK can use **direct mode** or **gateway mode** depending on API and configuration. Direct mode involves connections/protocols distinct from the HTTPS gateway. If the network mandates all traffic pass through an HTTP proxy, review the mode selection, connection settings, and actual proxy support in **CosmosClientBuilder**. Do not assume the same Java proxy property automatically routes direct TCP connections.

## 12. Retries, Timeouts, and Idempotency

Azure SDKs typically provide default retries or per-service retry options. When customizing, distinguish:

| Concept | Meaning | Risk When Misconfigured |
| --- | --- | --- |
| **Connect timeout** | Time limit for establishing TCP/TLS/tunnel at the transport layer | Too short causes false failures when network/proxy adds latency |
| **Read/response timeout** | Time limit waiting for data/response | Too long stalls threads; too short triggers unnecessary retries |
| **Operation timeout/budget** | Total time allowed for an operation per SDK/API | No bound lets requests hang indefinitely |
| **Retry count** | Number of retries on errors considered recoverable | Too many retries amplify load and cost |
| **Backoff/jitter** | Increasing and randomized delay between retries | No backoff can trigger a retry storm |
| **Idempotency** | Whether re-executing changes the business outcome | Duplicate uploads/overwrites or duplicate messages |

Do not blindly retry every error. For example, **401/403 from wrong identity or permissions** will not be solved by endless retries; **429 or 503** may require backoff respecting service hints/headers. When sending Service Bus messages, account for cases where a request **was processed by the server but the client lost the response**; retrying can emit duplicate messages and requires business-level deduplication.

### Stacked Retry Layers Can Multiply Load

A single service might have retries at:

1. The HTTP client/SDK.
2. Spring Retry or application service retries.
3. Reverse proxy / service mesh.
4. Queue workers or job schedulers.

If each layer retries three times, actual total requests can multiply far beyond expectations. Choose **one clear retry budget policy**, measure end-to-end latency, and enable retries only where needed.

### Proxy Timeouts Are Not Azure Service Timeouts

A proxy can proactively close a tunnel or idle connection. When that happens, the SDK typically sees a timeout, connection reset, or 502/504 from the proxy—not necessarily an overloaded Azure service. Compare proxy logs against Azure-side request IDs; if a request never reached Azure, there will be no corresponding service request ID.

## 13. Layered Connection Troubleshooting

| Symptom | Suspect | What to Check |
| --- | --- | --- |
| **407 Proxy Authentication Required** | Proxy requires credentials, misconfigured proxy auth | Verify proxy hostname/port and credentials via approved mechanism |
| **502/504 from proxy** | Proxy cannot reach upstream, timeout, or policy block | Compare proxy logs, routing, DNS, and error timestamps |
| **UnknownHostException** | Wrong DNS or proxy resolves DNS differently than expected | Check DNS from both the runtime and where the proxy runs |
| **PKIX path building failed / SSLHandshakeException** | CA trust chain, TLS inspection, hostname mismatch | Inspect certificates/trust store; never disable validation |
| **ConnectTimeoutException** | No TCP route, wrong proxy, or firewall | Check outbound access, VNet, endpoint, and port |
| Blob endpoint resolved yet **credential unavailable** | Azure Identity token request misses the right network path or identity unconfigured | Check token endpoint, managed/workload identity, and credential transport |
| **401/403 from Blob** | Token/audience, RBAC, Shared Key/SAS, or network policy | Verify principal, DataActions, scope, and Azure error code |
| **429/503** | Throttling, load, or service incident | Inspect Retry-After, metrics, backoff, and concurrency |
| Service Bus fails to connect over TCP/5671 | Firewall/proxy blocks direct AMQP | Check AMQP over WebSockets/443 and actual proxy support |
| Blob works, Event Hubs fails | Two clients use different transports/protocols | Check Event Hubs-specific builder, port, and proxy settings |
| Works locally, AKS times out | Pod DNS, VNet, Private Endpoint, or egress policy differs from laptop | Test from the target Pod/runtime, not just from a developer laptop |
| Fails only on large file uploads | Proxy body size/idle timeout, SDK transfer settings, memory | Check proxy logs, chunking, streaming, timeouts, and service limits |

**Do not rush to change RBAC when the error is 407 or a TLS handshake failure.** Conversely, fixing a proxy will not supply a missing **Storage Blob Data Contributor** role. Each layer has its own logs and diagnostics.

### Practical Debugging Workflow

~~~mermaid
flowchart TD
    A[Azure SDK call fails] --> B{Right endpoint/hostname?}
    B -->|No| C[Fix endpoint and cloud environment]
    B -->|Yes| D{Can connect via DNS/proxy/TLS?}
    D -->|No| E[Check proxy, route, trust store]
    D -->|Yes| F{Credential acquires token?}
    F -->|No| G[Check identity source and token network path]
    F -->|Yes| H{Azure returns 401/403?}
    H -->|Yes| I[Check audience, RBAC, scope, service policy]
    H -->|No| J[Check retries, quota, payload, and service response]
~~~

**Diagnostic ordering can vary** because Azure Identity token acquisition also requires network connectivity before calling the resource. The key is splitting failures into two independent tracks: token-acquisition connectivity and data-service connectivity.

## 14. Testing HTTP Pipelines and Proxies

### 14.1. Unit Tests

At the unit test level, no live Azure connection is needed:

- Test that the policy adds the expected header to simulated requests without altering the Authorization header.
- Test selecting the proxied HTTP transport when host/port are configured.
- Test validation of endpoints, proxy ports, and the no-proxy case.
- Mock/stub the Azure access adapter to test business logic when the SDK returns 401, 403, 429, or timeouts.

For detailed HTTP pipeline testing, you can use **Azure Core test utilities** or a fake HTTP transport matching your SDK version's API. Never call production services in unit tests.

### 14.2. Local Integration Tests

A lab environment can use:

1. **Azurite** to test part of Blob Storage HTTP(S) operations supported by the emulator.
2. An **HTTP test proxy** or a real dev-environment proxy to verify CONNECT, logging, and bypass rules.
3. A safe test certificate/trust store if the enterprise performs TLS inspection.
4. An endpoint simulating 429/503/timeout responses to test retry policies.

Azurite does not fully replace **Microsoft Entra**, **Azure RBAC**, Private Endpoints, or live Azure service behavior. Local proxy tests likewise do not prove production network paths will behave identically.

### 14.3. Integration Tests in Azure

Deploy Spring Boot with an identity and network matching the real environment:

- Choose the right managed identity/workload identity and data-plane role on the test resource.
- Verify both token-acquisition requests and Blob requests traverse permitted routes/proxies.
- Test no-proxy, proxy-enabled, proxy-blocked, timeout, and controlled 403 scenarios.
- Inspect request IDs, retry counts, and actual latencies; avoid logging tokens and secrets.
- For Service Bus/Event Hubs, test **AMQP or WebSockets** per the network profile rather than substituting Blob HTTP results.

Checking that the Spring Boot context starts is necessary yet **not sufficient**: many errors only appear when the client actually connects or needs an access token.

## 15. Security When Customizing Networking and Pipelines

Principles to maintain throughout:

1. **Never disable TLS verification** to work around proxy or certificate errors. Install valid CAs per policy and use the service's published hostname.
2. **Never put tokens/secrets into custom headers or HTTP logs**; that information can pass through proxies and observability systems.
3. **Never commit proxy credentials** into **application.yml**, **gradle.properties**, Dockerfiles, or scripts.
4. **Minimize Azure RBAC:** network connectivity does not grant data-plane permissions; the principal still needs roles on the target resource.
5. **Control egress:** permit only required endpoints, including the Microsoft Entra endpoint when credentials need tokens.
6. **Do not broaden proxy bypasses arbitrarily:** cross-check with Private Endpoint, VNet, and DNS architecture.
7. **Reuse HTTP clients/connection pools:** avoid creating a transport per request, which risks resource exhaustion.
8. **Use policies intentionally:** test their impact on retries, observability, and errors when communicating through a proxy.
9. **Monitor resources:** connection counts, retries, timeouts, 407, 429, and 5xx per endpoint.
10. **Version compatibility:** manage **azure-core**, transports, and Azure SDKs with a BOM matching your Spring Cloud Azure / Spring Boot versions.

## 16. Comparing Azure with AWS and Google Cloud

| Concern | Azure SDK for Java | AWS SDK for Java v2 | Google Cloud Java Libraries |
| --- | --- | --- | --- |
| Client construction | **BlobServiceClientBuilder**, **SecretClientBuilder**, per-service builders | Per-service builders, e.g., S3 client builder | Client/settings builders per Google Cloud API |
| HTTP transport | Azure Core HttpClient: Netty/OkHttp depending on module | Apache/Netty/JDK/CRT transport depending on client | HTTP/JSON or gRPC transport depending on service |
| Credential | **TokenCredential**, DefaultAzureCredential | **AwsCredentialsProvider**, provider chain | **GoogleCredentials**, Application Default Credentials |
| Proxy | Configured per HTTP provider or service SDK | Configured per HTTP client/protocol | Configured per corresponding HTTP/gRPC transport |
| Retry/tracing | HTTP pipeline/policies and SDK-specific options | SDK interceptors / per-client retry strategies | Client settings/retries/gRPC interceptors per service |
| Permissions | Microsoft Entra + Azure RBAC or dedicated data authorization | IAM policies/roles and service policies | Cloud IAM and per-service authorization |

The common thread is separating **client settings**, **transport**, **credential**, and **authorization**. The key difference is that you cannot copy a proxy or timeout variable from Azure to AWS/GCP and assume identical effect. For example, AWS S3 and Azure Blob both use HTTP, yet still differ in endpoints, signing/tokens, retries, and data consistency; Google Cloud SDKs may use gRPC.

## 17. Lab Exercise: Blob Client Running Through a Corporate Proxy

**Scenario:** the Spring Boot Documents API runs directly on a laptop, yet the CI environment can only reach Azure through a proxy. The goal is to configure the client safely and test both token acquisition and Blob uploads.

1. **Prepare the lab:** a Storage Account and private **documents** container, a test identity with **Storage Blob Data Contributor**, the Blob endpoint, and an authorized test proxy.
2. **Select dependencies:** compatible Spring Boot, **spring-cloud-azure-dependencies** BOM when using Spring Cloud Azure starters or Azure SDK BOM when using the SDK directly; ensure the Netty HTTP provider is present if using that code.
3. **Create a Spring bean:** use BlobServiceClientBuilder, endpoint from an environment variable, and DefaultAzureCredential or an explicit per-environment credential.
4. **Add proxy:** use NettyAsyncHttpClientBuilder with ProxyOptions; validate proxy host/port. Execute an upload test.
5. **Verify token acquisition:** identify the identity source; if Entra login fails due to the proxy, configure Azure Identity's HTTP path per your SDK version and re-test.
6. **Add BASIC logging:** observe endpoint, status, latency, and request ID; confirm no Authorization header, SAS, or proxy secrets are exposed.
7. **Test controlled failures:** misconfigure the proxy, block upstream test traffic, revoke the data role on the test identity, and document the differences between **407/TLS/timeout/403**.
8. **Test Private Endpoint if supported in the lab:** compare DNS and routing when bypassing the proxy for private endpoints, without arbitrarily altering standard hostnames.
9. **Extend to messaging:** use a Service Bus sender in a restricted network environment, comparing AMQP/TCP with WebSockets/443 and separate proxy settings.
10. **Compile a report:** table of endpoint, principal, transport, proxy mode, TLS, retries, error codes, request IDs, and an explanation of which layer caused each failure.

### Self-Check Questions

1. Why does successfully instantiating **BlobServiceClient** not prove that networking or RBAC works?
2. How does the Azure SDK's **HttpClient** differ in responsibility from **BlobServiceClient**?
3. Why might configuring an HTTP proxy on the Blob client still fail to let DefaultAzureCredential acquire a token?
4. What role does HTTP CONNECT play when a client calls an HTTPS Blob endpoint?
5. Should you disable TLS certificate validation to work around PKIX errors from a corporate proxy? Why or why not?
6. Why must Service Bus AMQP over 5671 and WebSockets over 443 be verified separately from Blob HTTP?
7. At which layer should **407 Proxy Authentication Required** be handled, and how does it differ from a **403 from Azure Blob**?
8. If retries are enabled simultaneously in the SDK, Spring, and the proxy, what happens to the actual request count?
9. How can a Spring Cloud Azure starter be affected when an application manually defines an additional BlobServiceClient bean?
10. What does an Azurite test through a proxy prove, and what evidence regarding managed identity/RBAC is still missing?

## 18. Key Takeaways

- **Service builders** select endpoints, credentials, and client settings; the **HTTP pipeline** applies policies; the **HTTP transport** dispatches requests; the **proxy** is part of the network path.
- **DefaultAzureCredential** may require a network path to acquire tokens independently of data endpoint connections; configuring a proxy for Blob does not automatically configure a proxy for Azure Identity.
- **Spring Cloud Azure starters** reduce Spring Boot wiring. When deep customization is needed, use version-supported extension points or explicit client beans while managing bean conflicts.
- **Service Bus/Event Hubs** use AMQP/WebSockets; **Cosmos DB** may use direct/gateway modes. Never force Blob's HTTP proxy onto every service.
- Manage **retries, timeouts, TLS, logging, and connection pools** deliberately; never log tokens/secrets, never disable certificate verification, and always test real requests with the right identity and network.

## References

- [Azure SDK for Java — Get started](https://learn.microsoft.com/azure/developer/java/sdk/get-started)
- [Azure SDK for Java — HTTP clients](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipelines)
- [Azure Core SDK for Java API](https://learn.microsoft.com/java/api/overview/azure/core-readme)
- [Azure Storage Blob client library for Java](https://learn.microsoft.com/java/api/overview/azure/storage-blob-readme)
- [Azure Identity client library for Java](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [Azure Service Bus client library for Java](https://learn.microsoft.com/java/api/overview/azure/messaging-servicebus-readme)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
