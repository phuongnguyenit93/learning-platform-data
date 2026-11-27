# Timeouts per HTTP Transport and Differences in Meaning

In a microservices system using **Spring Cloud LoadBalancer**, a request from **order-service** to **inventory-service** may have to wait for **instance discovery**, acquiring a connection from a pool, DNS resolution, TCP setup, TLS negotiation, sending the request, waiting for the backend to process, and reading the body. Each phase can have a **different timeout**. A setting named **readTimeout** in RestTemplate is not necessarily equivalent to Reactor Netty's **responseTimeout** or OpenFeign's **readTimeout**.

Misunderstanding timeouts leads to many incidents: worker threads held too long, reactive requests cancelled before acquiring a connection, retries stretching past the SLA, or clients reporting timeouts even though the server already completed a write transaction. This lesson compares timeouts **by the executing HTTP transport**, not merely by the surface API (**RestTemplate, RestClient, WebClient, OpenFeign**).

**Learning objectives:**

1. Distinguish pool acquire, DNS, TCP connect, TLS handshake, read/response timeout, and **end-to-end deadline**.
2. Know which timeout must be configured on the **actual HTTP engine** (JDK HttpURLConnection, JDK HttpClient, Apache HttpClient 5, Reactor Netty, Feign).
3. Configure and verify RestTemplate/RestClient, WebClient, and OpenFeign when calling through Spring Cloud LoadBalancer.
4. Understand the relationship between timeouts, retries, service discovery, health checks, and error semantics.
5. Design a time budget, test network slowness/pool saturation, and trace timeout root causes.

**Version note:** Spring Framework 6.x/7.x, Spring Cloud, and HTTP engines do not always share identical overloads or defaults. Code snippets follow the APIs of the noted version lines; verify against your running BOM before applying. Numbers in this lesson are **design examples**, not optimal values for every environment.

## 1. The Term “Timeout” Hides Many Different Clocks

Picture a call going through these steps:

~~~mermaid
flowchart LR
    A["Caller: build request"] --> B["Discovery + LoadBalancer"]
    B --> C["Pool: acquire connection"]
    C --> D["DNS"]
    D --> E["TCP connect"]
    E --> F["TLS handshake (HTTPS)"]
    F --> G["Send headers/body"]
    G --> H["Wait for response headers"]
    H --> I["Read response body"]
    I --> J["Decode + return DTO"]
~~~

A specific execution may **skip several steps**: HTTP keep-alive reuses an open connection without needing a new TCP connect or TLS handshake; a cached ServiceInstance avoids querying the registry every time; HTTP/2 can carry multiple streams over one connection. Thus, each instance selection does not necessarily come with a new connection setup.

| Timeout type | What interval does it measure? | Effect when exceeded | Does not automatically protect against |
| --- | --- | --- | --- |
| **Pool acquire / connection request** | Waiting to obtain a connection from the pool | Stops waiting when pool is saturated | Slow backend response after connection is acquired |
| **DNS query / resolve** | Waiting to resolve a hostname to an address | Stops overly long DNS queries | TCP connect/response |
| **Connect** | Establishing a new connection; scope depends on engine | Blocks hung TCP connects | Pool wait and slow responses; may exclude TLS |
| **TLS handshake** | TLS negotiation after TCP connect | Bounds HTTPS handshake | Slow HTTP body/read |
| **Write** | Waiting to send bytes or an interval without write progress | Bounds slow uploads | Slow server processing after receiving request |
| **Response/read/socket** | Waiting for response or an inbound data-inactivity gap, engine-dependent | Cuts the stream when backend goes silent | Usually not a limit on **total** HTTP call duration |
| **Request/overall deadline** | Entire call or single attempt, API-dependent | Stops remaining work when budget runs out | Cannot reverse server-side side effects |
| **Retry backoff** | Pause between attempts | Throttles retries | Not an HTTP timeout, yet adds to latency |

A property name **is not a sufficiently precise contract**. You must ask: when does the clock start, when does it stop, does it measure **the gap between two reads** or **end-to-end duration**, does it reset when a chunk arrives, and does it include retries?

## 2. Which Timeout Belongs to Which Phase?

### 2.1. Waiting for a Connection in the Pool

When more concurrent calls arrive than the pool allows, requests can sit in a queue. **Pool acquire timeout** limits how long a request waits **before** it even gets a socket to use.

For example, a pool has 20 connections, all 20 are occupied by slow requests, and the 21st request must wait. Even if connect timeout is only 200 ms, it can still sit in the queue for 2 seconds if the pool acquire timeout permits. Connect timeout only applies when a **new connection** is actually needed.

In Apache HttpClient 5, this concept is **connection request timeout**; in Reactor Netty, it is typically **pendingAcquireTimeout**.

### 2.2. DNS Resolution

An HTTP client may have to resolve a hostname such as inventory-a.internal. DNS results may be cached by the resolver, JVM, operating system, or HTTP engine. DNS query timeout is usually **independent** of TCP connect timeout.

For a logical URI **http://inventory-service/...** with **@LoadBalanced**, the host inventory-service is a **service ID**. After LoadBalancer chooses a ServiceInstance, the transport connects to the instance's physical host/port. If the instance uses hostname inventory-a.internal, DNS may run for the **actual target hostname**, not for the logical service ID. If the instance uses an IP, DNS may not be needed for that target.

### 2.3. TCP Connect

Connect timeout typically limits opening a new TCP connection. It helps when SYN receives no reply due to dropped packets. However, if the target actively returns connection refused, the error can occur **immediately** without waiting for connect timeout to expire.

When keep-alive reuses a connection, there is **no new TCP connect**, so connect timeout does not constrain requests on that connection.

### 2.4. TLS Handshake

After TCP connect, HTTPS requires a TLS handshake (sometimes preceded by a proxy tunnel). Some transports have a dedicated handshake timeout; some connect timeouts may or may not cover the handshake. Do not guess solely from the name connectTimeout.

The TLS handshake also depends on certificate validation, SNI, proxies, TLS version, and network delay. If a handshake fails due to a bad certificate, increasing the timeout **will not fix** trust/hostname issues.

### 2.5. Response/Read Timeout

A server can connect immediately yet take 10 seconds to run a query. Connect timeout **does not protect** against this. Response/read timeout governs waiting for the reply.

- **Socket read timeout** in some blocking transports typically bounds **the wait time of a single read call**. If the server keeps sending a few bytes before the timeout expires, total request time can become very long.
- **Response timeout** in Apache HttpClient 5 applies during request exchange; Apache documentation warns it is **not a total deadline** and can be exceeded when the HTTP client internally retries a request.
- **Reactor Netty responseTimeout** protects the HTTP response layer, not a guaranteed cap on all preceding phases or multiple retries combined.
- **JDK HttpClient HttpRequest.Builder.timeout** is a *request* timeout, distinct from pure socket read timeout; details of how it covers the response body vary by JDK version.

### 2.6. End-to-End Deadline

An Order Service endpoint with a 2-second SLA cannot simply set readTimeout=2s and consider the SLA met. Total elapsed time also includes:

~~~text
T_call = T_lookup/LB + T_pool + T_DNS + T_connect
       + T_TLS + T_upload + T_response + T_decode
       + T_retry_backoffs + T_additional_attempts
~~~

This is an **additive phase model**, not an exact formula for every engine because some steps overlap or are skipped. Still, it highlights the need for an **independent deadline** on the logical call whenever end-to-end latency must be bounded.

## 3. Spring Cloud LoadBalancer Is Not the HTTP Transport

LoadBalancer accepts a service ID, retrieves the instance list (discovery, cache, health, filters), and picks an instance. The HTTP transport begins its role when calling the physical URI after selection.

~~~text
Order -> GET http://inventory-service/api/stock/BOOK-01
          |
          | Spring Cloud LoadBalancer selects ServiceInstance
          v
        http://10.10.1.22:8080/api/stock/BOOK-01
          |
          | ClientHttpRequestFactory / ClientHttpConnector / Feign client
          v
        TCP, TLS, request, response
~~~

| Scenario | Connected to Inventory? | Does HTTP transport timeout handle it? |
| --- | --- | --- |
| No ServiceInstance | No | Cannot be solved by raising connect/read timeout |
| Slow DiscoveryClient | Possibly not yet | Overall call deadline may apply; transport timeouts do not reliably cover it |
| Waiting on connection pool | Connection not leased yet | Pool acquire timeout |
| TCP SYN dropped | Attempting to connect | Connect timeout |
| TLS handshake hung | TCP connected | TLS/handshake timeout or deadline |
| Backend processing slowly | Connected, waiting for response | Response/read timeout |
| Backend returns HTTP 503 immediately | HTTP response received | Not a timeout |
| Backend finished processing but client timed out | Side effects may already exist | Timeout cannot roll back the backend |

In Spring Cloud LoadBalancer, **ServiceInstanceListSupplier** may use caching and asynchronous health checks. Increasing RestClient or WebClient timeouts **does not make the registry refresh faster**, nor does it remove dead instances from the list on its own.

## 4. High-Level HTTP APIs Differ from the Executing Transport

| Spring/Cloud API | I/O model | Possible HTTP engines | Where timeouts are configured |
| --- | --- | --- | --- |
| RestTemplate | Blocking | HttpURLConnection, Apache HC5, JDK HttpClient via factory | ClientHttpRequestFactory + engine |
| RestClient | Blocking | JDK HttpClient, Apache HC5, Jetty, or Reactor Netty via factory | ClientHttpRequestFactory + engine |
| WebClient | Reactive | Reactor Netty, Jetty reactive, or JDK HttpClient connector | ClientHttpConnector, engine, Reactor operators |
| Spring Cloud OpenFeign | Usually blocking | Feign default client, HC5, OkHttp, or JDK per configuration | Feign Request.Options and underlying HTTP client |

Two applications both calling RestClient.get().retrieve() can use different transports if their classpath or request factory beans differ. Spring Framework also picks a default request factory based on libraries present. Therefore, **never write a single generic YAML timeout block assuming every HTTP client obeys it**.

Operational rule: **verify which HTTP engine and bean are actually injected, then configure timeouts**. The same 2-second value can measure two different intervals across two transports.

## 5. RestTemplate/RestClient with SimpleClientHttpRequestFactory

**SimpleClientHttpRequestFactory** uses JDK HttpURLConnection. It exposes two timeouts:

- **setConnectTimeout**: timeout when opening the URLConnection.
- **setReadTimeout**: timeout when waiting to read data from the URLConnection.

Example for RestTemplate (Spring Framework 6.1+ provides Duration overloads):

~~~java
import java.time.Duration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(500));
    factory.setReadTimeout(Duration.ofSeconds(2));
    return new RestTemplate(factory);
}
~~~

Similar example with RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder inventoryRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(500));
    factory.setReadTimeout(Duration.ofSeconds(2));
    return RestClient.builder().requestFactory(factory);
}
~~~

Once Spring Cloud LoadBalancer configures the builder, the application can use a logical URI:

~~~java
StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**Pitfall:** with HttpURLConnection, read timeout bounds waiting for data during read operations—**not automatically the maximum time from sending GET until finishing deserializing the entire JSON**. A server dripping small chunks of data can stretch the call past 2 seconds.

The SimpleClientHttpRequestFactory Javadoc specifies **0 means no timeout** for both setters and defaults to system settings; never set 0 thinking it means “instant” or assume defaults are safe.

SimpleClientHttpRequestFactory lacks the pool acquisition and reuse configuration suite of Apache HC5 or Reactor Netty. When high throughput and multi-phase control are needed, choose a better-suited transport instead of trying to cram every timeout into two setters.

## 6. RestClient/RestTemplate with JDK HttpClient (Java 11+)

Do not confuse **SimpleClientHttpRequestFactory** (HttpURLConnection) with **JdkClientHttpRequestFactory** (java.net.http.HttpClient). These are two distinct JDK HTTP mechanisms.

JDK HttpClient has:

- **HttpClient.Builder.connectTimeout(Duration)**: bounds creating a **new connection**; has no effect on requests reusing an existing connection.
- **HttpRequest.Builder.timeout(Duration)**: timeout **for a single request**. The JDK Javadoc describes HttpTimeoutException when the response fails to arrive within the limit; body coverage details depend on the JDK version/implementation.
- **JdkClientHttpRequestFactory.setReadTimeout(Duration)**: Spring maps this value to **HttpRequest.Builder.timeout**, not a socket idle read timeout like HttpURLConnection.

Example:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

HttpClient jdkClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(jdkClient);
factory.setReadTimeout(Duration.ofSeconds(2));

RestClient restClient = RestClient.builder()
        .requestFactory(factory)
        .build();
~~~

This is a **direct** RestClient. To use service IDs with Spring Cloud LoadBalancer, attach the factory to a **@LoadBalanced** builder/bean or suitable LoadBalancer integration; setting requestFactory alone does not attach LoadBalancer.

### 6.1. Why Not Call Every readTimeout “Wait Between Two Bytes”?

In JdkClientHttpRequestFactory, the method is named setReadTimeout, yet it operates via the JDK **HTTP request** timeout. You cannot assume it has the exact same start and end points as HttpURLConnection.setReadTimeout.

When running Java 17, 21, or a newer JDK, check the corresponding Javadoc for HttpRequest.Builder.timeout and write an integration test with **fast response headers but a slow body**. Do not copy timeout tables from one transport to another just because setter names look alike.

## 7. Apache HttpClient 5: Separating Pool, Connect, Socket, and Response

For high-traffic blocking RestClient/RestTemplate systems, **Apache HttpClient 5 (HC5)** provides a connection pool and distinct timeouts:

| HC5 configuration | Meaning | Layer |
| --- | --- | --- |
| RequestConfig.connectionRequestTimeout | Waiting to lease a connection from the pool | Connection manager |
| ConnectionConfig.connectTimeout | Waiting to create a connection; TLS details depend on transport | Connection configuration |
| ConnectionConfig.socketTimeout | Waiting for socket I/O activity | Connection/I/O |
| RequestConfig.responseTimeout | Waiting for response during request exchange | Request execution |
| TlsConfig.handshakeTimeout | Waiting for TLS handshake | TLS |
| ConnectionConfig.timeToLive/idleTimeout | Max connection lifetime/idle time for managing reuse | Pool lifecycle, **not an HTTP request deadline** |

### 7.1. Pooled Apache HC5 Example

Illustrative configuration for **Apache HttpClient 5.2+** with Spring Framework using HttpComponentsClientHttpRequestFactory:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

ConnectionConfig connection = ConnectionConfig.custom()
        .setConnectTimeout(Timeout.ofMilliseconds(500))
        .setSocketTimeout(Timeout.ofSeconds(2))
        .build();

PoolingHttpClientConnectionManager manager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(100)
                .setMaxConnPerRoute(30)
                .setDefaultConnectionConfig(connection)
                .build();

RequestConfig request = RequestConfig.custom()
        .setConnectionRequestTimeout(Timeout.ofMilliseconds(300))
        .setResponseTimeout(Timeout.ofSeconds(2))
        .build();

CloseableHttpClient apache = HttpClients.custom()
        .setConnectionManager(manager)
        .setDefaultRequestConfig(request)
        .build();

HttpComponentsClientHttpRequestFactory factory =
        new HttpComponentsClientHttpRequestFactory(apache);

RestClient restClient = RestClient.builder()
        .requestFactory(factory)
        .build();
~~~

**Example scope:** bean/lifecycle wiring, exception mapping, and Spring Cloud LoadBalancer are omitted to focus on timeouts. In a real application, use a shared HTTP client bean, let Spring manage pool shutdown, and attach the factory to a **@LoadBalanced RestClient.Builder/RestTemplate** when calling by service ID.

An important version detail: some Spring Framework 6.x lines have **HttpComponentsClientHttpRequestFactory.setConnectTimeout(...)**; Spring Framework **7.0.10** Javadoc no longer has a connect timeout setter on this factory. Configure connect timeout via **Apache HC5's ConnectionConfig** as shown to avoid assuming the method exists across all versions.

### 7.2. Response Timeout Is Not a Full-Request Deadline

Apache HC5 describes RequestConfig.responseTimeout as a response-wait interval and warns it is **not an absolute deadline**; it can be exceeded when the HTTP client automatically retries a request. In addition, pool acquire wait and connection setup must be measured separately.

~~~text
pool acquire = 300ms
connect      = 500ms
response     = 2s
~~~

You must not conclude “every request is guaranteed to finish within 2 seconds.” A request may wait for the pool, then connect, and then wait for a response; each phase timeout protects **that phase**, without simultaneously establishing an overall deadline.

### 7.3. When the Pool Is Saturated

If the pool allows only 30 connections to inventory-service while 60 concurrent requests arrive, half may have to wait. While a request is waiting on the pool, connect/read timeouts are usually **not the primary clock**; connectionRequestTimeout is the limit to watch.

Raising connectTimeout does not relieve an exhausted pool queue; raising maxConnPerRoute may help in some cases, yet risks overloading the backend. Evaluate concurrency, latency, keep-alive, and server limits before resizing the pool.

## 8. WebClient with Reactor Netty: Timeout Layers to Distinguish

**WebClient** is Spring Framework's reactive API; **Reactor Netty** is a common transport behind WebClient. Timeout configuration should be placed on **HttpClient**, **ConnectionProvider**, and, when needed, **Mono/Flux** operators.

Categories documented by Reactor Netty:

| Category | Representative API | Protects |
| --- | --- | --- |
| Pool acquire | ConnectionProvider.pendingAcquireTimeout | Waiting for pool to grant a connection |
| TCP connect | ChannelOption.CONNECT_TIMEOUT_MILLIS | Creating a new connection |
| HTTP response | HttpClient.responseTimeout | Waiting for HTTP-layer response read progress |
| TLS | SSL provider handshakeTimeout | HTTPS handshake |
| DNS | Resolver queryTimeout | Wait time per DNS query |
| Proxy | ProxyProvider.connectTimeoutMillis | Time to establish connection through proxy |
| Total publisher | Mono.timeout / Flux.timeout | Wait time by reactive signal, operator-dependent |

### 8.1. Configuring Reactor Netty and @LoadBalanced WebClient.Builder

Example for Spring Cloud LoadBalancer:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Bean
ConnectionProvider inventoryConnectionPool() {
    return ConnectionProvider.builder("inventory-http")
            .maxConnections(80)
            .maxIdleTime(Duration.ofSeconds(25))
            .pendingAcquireTimeout(Duration.ofMillis(300))
            .build();
}

@Bean
@LoadBalanced
WebClient.Builder inventoryWebClientBuilder(ConnectionProvider pool) {
    HttpClient netty = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
            .resolver(spec ->
                    spec.queryTimeout(Duration.ofSeconds(1)))
            .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(netty));
}
~~~

Assumes **spring-cloud-starter-loadbalancer** and a discovery source are present. The client can call:

~~~java
Mono<StockResponse> stock = builder.build()
        .get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

**Lifecycle note:** ConnectionProvider and event-loop resources should be shared and cleaned up when ApplicationContext closes; never create a new pool/HttpClient per request. If you build a custom pool separate from default resources, design proper lifecycle/dispose handling. With Spring Boot, avoid losing WebClientCustomizers, tracing, authentication, or preconfigured connector settings by building a disconnected builder from scratch.

### 8.2. pendingAcquireTimeout Is Not connectTimeout

Example:

~~~text
12:00:00.000  subscribe
12:00:00.005  waiting on connection pool; all channels busy
12:00:00.305  pendingAcquireTimeout=300ms -> acquire error
               never even attempted a new TCP connect
~~~

Raising CONNECT_TIMEOUT_MILLIS from 500 to 2000 **will not reduce this error**. Check active/idle/pending connections, concurrency limits, response speed, and whether connections are leaking.

Reactor Netty 1.3.x documentation states a **default pendingAcquireTimeout of 45 seconds**, which should not be relied upon for short SLOs. Even when the pool still has room to create a new connection, connect timeout applies in the TCP setup branch after acquiring; each clock measures a distinct phase.

### 8.3. CONNECT_TIMEOUT_MILLIS Applies Only to New Connections

~~~java
HttpClient netty = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500);
~~~

The value is in **milliseconds**. In Reactor Netty 1.3.x, documentation notes a default connect timeout of 30 seconds; defaults can vary by transport and version, so set it explicitly based on your latency budget.

When reusing a keep-alive socket, there is no new TCP connect for this setting to constrain. If an endpoint responds slowly over an existing connection, rely on response timeout and an appropriate deadline.

### 8.4. responseTimeout and Per-Request Overrides

~~~java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(2));
~~~

This is the default configuration for requests on that HttpClient. For an endpoint needing more time, Spring WebClient can customize per request when the native transport is Reactor Netty:

~~~java
Mono<String> result = webClient.get()
        .uri("http://inventory-service/reports/{id}", reportId)
        .httpRequest(httpRequest -> {
            reactor.netty.http.client.HttpClientRequest nativeRequest =
                    httpRequest.getNativeRequest();
            nativeRequest.responseTimeout(Duration.ofSeconds(5));
        })
        .retrieve()
        .bodyToMono(String.class);
~~~

**This API depends on Reactor Netty**, and is not portable to JdkClientHttpConnector or JettyClientHttpConnector. If you switch connectors, native request customizations must be reviewed or replaced.

Do not read responseTimeout=2s as **every request completes in at most 2 seconds**. Pool wait, DNS, TCP/TLS, request upload, decoding, and retries can add time; responses may stream, and each phase is measured differently.

### 8.5. Data Read/Write Handlers vs. Response Timeout

Spring Framework also allows attaching Netty's **ReadTimeoutHandler** and **WriteTimeoutHandler**:

~~~java
HttpClient netty = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

These are Netty I/O handlers with **no read/write progress** semantics, and the constructor arguments above are in **seconds**. They differ from HttpClient.responseTimeout in scope and lifecycle. Add handlers only when connection-level protection is truly required; attaching them carelessly can interfere with long streaming requests, connection reuse, or TLS.

For typical WebClient usage, **responseTimeout** is usually a better starting point than arbitrarily adding read/write handlers and assuming the two mechanisms are equivalent.

### 8.6. TLS Handshake, DNS, and Proxy Need Separate Bounds When Required

Reactor Netty configures a handshake timeout for HTTPS:

~~~java
HttpClient httpsClient = HttpClient.create()
        .secure(spec ->
                spec.handshakeTimeout(Duration.ofSeconds(4)));
~~~

This snippet enables TLS for an HTTPS client in the example; do not copy an HTTPS configuration verbatim onto a connector meant solely for **plain HTTP** assuming all schemes still behave the same. For complex SSL setups, configure SslContextSpec/truststore and hostname verification according to security policy.

Reactor Netty documentation cites a default SSL handshake timeout of 10 seconds and a default DNS query timeout of 5 seconds for the 1.3.x line. **These are engine-level defaults**, not application SLOs. A DNS resolver can try multiple nameservers/records or caches, so do not conclude total resolution time equals **one DNS query timeout**.

If traffic passes through an HTTP proxy, proxy connect timeout may also be a separate clock. Do not confuse latency connecting to the proxy with backend processing time.

## 9. WebClient + Reactor Timeout: Two Different Ways to Bound

Reactor provides the **timeout(Duration)** operator on Mono/Flux:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofMillis(900));
~~~

With **bodyToMono**, this timeout bounds waiting for a value/completion signal starting from subscription; in a typical cold pipeline it can cover **ServiceInstance selection, pool acquire, connect, sending the request, and body decoding**, making it closer to a deadline for a single subscribe. It does not automatically include **retries placed outside the operator**.

Operator ordering makes a critical difference:

~~~java
// 900ms timeout per subscription to an attempt;
// an outer retry can make total duration exceed 900ms.
Mono<StockResponse> perAttempt = source
        .timeout(Duration.ofMillis(900))
        .retryWhen(Retry.max(1));

// 1500ms timeout wrapping both retries and inner backoff.
Mono<StockResponse> wholeOperation = source
        .retryWhen(Retry.fixedDelay(1, Duration.ofMillis(100)))
        .timeout(Duration.ofMillis(1500));
~~~

In the example, **source** is a cold Mono capable of re-executing the HTTP request on re-subscribe, not an already-completed hot Publisher. Retry.max(1) means at most **one retry after the initial call**, not one total call.

**Flux.timeout(Duration)**, by contrast, is a timeout on the **gap until the next onNext signal**, not inherently an absolute total duration for a stream. For SSE/NDJSON, a continuous stream can run for hours without timing out if each event arrives on time. To limit a stream's lifetime, use an independent deadline/subscription cancellation.

### 9.1. Reactor-Layer Timeouts Do Not Replace Transport Timeouts

If you only set Mono.timeout(2s) while pool acquire still defaults to 45s, the operator can cancel the subscription after 2s, but tearing down physical resources depends on the connector and request phase. Specific operational timeouts at the transport layer are still needed to:

- Identify clear causes: pool timeout, connect timeout, response timeout.
- Prevent a connection/operation from hanging longer than internal policy allows.
- Support cleanup and pool health once the caller cancels.

Conversely, setting only transport timeouts **without a logical deadline** can let multiple retries or sequential downstream calls exceed the SLO.

## 10. OpenFeign: Per-Client-Name connectTimeout/readTimeout

Spring Cloud OpenFeign allows configuring **connectTimeout** and **readTimeout** per Feign client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          default:
            connectTimeout: 500
            readTimeout: 2000
          inventory-service:
            connectTimeout: 300
            readTimeout: 1500
~~~

Both values in this common Feign configuration are interpreted in **milliseconds**. For **@FeignClient(name = "inventory-service")**, settings under inventory-service override defaults for that client.

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Feign's **connect timeout** relates to connection establishment. **Read timeout** relates to waiting for response data after connecting, though execution details are determined by the HTTP client Feign uses. Spring Cloud OpenFeign can use Apache HttpClient 5, OkHttp, or the default client depending on classpath/configuration; therefore **do not equate Feign's config names with one identical timer across all underlying transports**.

### 10.1. Feign Timeouts Do Not Include All Other Costs

Total elapsed time can include:

- Discovery/LoadBalancer picking an instance.
- Connection pool wait when using Apache HC5/OkHttp.
- DNS and TCP/TLS.
- Receiving the HTTP response and decoding the body.
- Retries by Feign or other layers.

Spring Cloud OpenFeign registers **Retryer.NEVER_RETRY** by default, unlike Feign core which may retry certain I/O errors. Even so, an application may configure its own retryer, circuit breaker, or proxy retries: inventory every layer before computing a timeout budget.

### 10.2. HC5's Own Connection Pool and Socket Timeouts Under Feign

Spring Cloud OpenFeign provides engine-specific properties, such as configuring **HC5 connection-request-timeout** and **socket-timeout**. Never apply those mechanically if Feign actually uses OkHttp or the default client: they may **have no effect**.

In a real product, you need to:

1. Identify the Feign Client implementation (HC5, OkHttp, JDK...).
2. Configure Feign connect/readTimeout per client name.
3. Configure pool acquire/socket/TLS on the HTTP engine if the app needs them.
4. Test timeouts per phase and log root causes.

## 11. Jetty and Other Transports: Same API, Potentially Different Timeout Names

Besides Reactor Netty, WebClient has **JettyClientHttpConnector** and **JdkClientHttpConnector**. RestClient can be given **JettyClientHttpRequestFactory** or **ReactorNettyClientRequestFactory**. Each transport keeps its own HTTP engine knobs:

| Transport | Settings to inspect | Do not assume |
| --- | --- | --- |
| Jetty HTTP client | connect timeout, request/idle timeout, connection pool | Same read timeout meaning as Netty |
| JDK HttpClient | client connectTimeout, HttpRequest timeout | Same socket read semantics as URLConnection |
| Reactor Netty used for blocking RestClient | Client request factory wrapping Netty | Same thread/concurrency profile as reactive WebClient |
| OkHttp under Feign | connect/read/write/call timeout, dispatcher/connection pool per config | That Spring Cloud OpenFeign readTimeout is total call timeout |

For example, with **JettyClientHttpRequestFactory** in current Spring Framework lines, the factory provides connect/read timeout setters, but they rely on Jetty HttpClient. If you need Jetty's own overall request timeout or idle timeout, verify the Jetty API and Spring wrapper for your exact version.

**Important:** switching from JDK HttpClient to Apache HC5 or Reactor Netty can change default timeouts, pool sizes, redirects, TLS, and how exceptions are represented even though the **business method** still just calls RestClient.get().retrieve(). Treat switching transports as a change requiring regression tests, not merely a performance tweak.

## 12. Comparison Table of Timeout Semantics

| Transport | Connect timeout | Response/read wait timeout | Pool acquire | Whole-request bound |
| --- | --- | --- | --- | --- |
| HttpURLConnection | URLConnection.connectTimeout | URLConnection.readTimeout: waits per read operation | No HC5-style pool-acquire API | No separate overall deadline via those two setters |
| JDK HttpClient | HttpClient.connectTimeout | HttpRequest.timeout via Spring JdkClientHttpRequestFactory.setReadTimeout | No HC5-style pool-acquire setter | HttpRequest.timeout for one request; check JDK version and body semantics |
| Apache HC5 | ConnectionConfig.connectTimeout | RequestConfig.responseTimeout + ConnectionConfig.socketTimeout | RequestConfig.connectionRequestTimeout | Needs application deadline if wrapping retries too |
| Reactor Netty | CONNECT_TIMEOUT_MILLIS | HttpClient.responseTimeout and optional Netty I/O handlers | ConnectionProvider.pendingAcquireTimeout | Mono/Flux timeout or another deadline placed appropriately |
| Spring Cloud OpenFeign | connectTimeout (Feign options) | readTimeout (Feign options); behavior depends on client | Depends on HC5/OkHttp | Does not inherently cover multiple attempts |
| Jetty | Jetty HttpClient/factory config | Response/request/idle depending on Jetty API | Depends on Jetty connection management | Check request timeout and deadline in specific version |

This is a **conceptual mapping** table, not a guarantee of equivalence. Source/Javadoc and testing at the running transport layer are the authority for when timers run and which exceptions are raised.

## 13. Connect, Response, and Total Deadline: A Worked Numerical Example

Suppose Order Service has at most 2,000 ms to make an Inventory call. One attempt unfolds:

| Phase | Illustrative time |
| --- | ---: |
| LoadBalancer/discovery | 30 ms |
| Pool acquire wait | 180 ms |
| DNS | 60 ms |
| TCP connect | 120 ms |
| TLS handshake | 180 ms |
| Send request | 50 ms |
| Backend processing / wait for headers | 950 ms |
| Read body / deserialize | 90 ms |
| **Total** | **1,660 ms** |

If you only configure responseTimeout=1,000 ms, this attempt can still finish in **1,660 ms**, because time was spent in earlier phases. If the caller also retries a similar attempt, total duration can exceed **3,320 ms**, before even counting backoff.

Conversely, if the whole-call deadline is **2,000 ms**, the first attempt consumed 1,660 ms, leaving only 340 ms. If a retry requires 100 ms backoff and leaves at most 240 ms for the next attempt, retrying a backend that normally takes around 1 second may **no longer be useful**. The policy should stop rather than retry when remaining budget is too small.

### 13.1. Deadline and Smaller Timeouts Must Be Consistent

Illustrative design targets (not defaults):

~~~text
End-to-end budget:              1800ms
Pool acquire per attempt:        150ms
Connect per new connection:      250ms
TLS handshake:                   400ms
Response inactivity per attempt: 900ms
Maximum retry attempts:         1 (1 extra after initial)
Backoff:                         100ms
~~~

Phase timeouts do not have to sum exactly to the end-to-end deadline, because some phases are skipped on connection reuse and some overlap. However, the **overall deadline must be the final limit**, especially when retries exist.

If multiple dependencies are called sequentially within one inbound request, **allocate budgets per dependency** and reserve time for the caller to process responses. If called in parallel, total wait time may track the slowest branch, while connection pools and server load still bear the sum of concurrent requests.

## 14. Retries Multiply Time and Can Switch Instances

When a timeout occurs, Spring Cloud LoadBalancer or the HTTP client may pick a new ServiceInstance according to retry policy. This is especially dangerous for write operations:

~~~text
Attempt 1:
  Order -> Inventory A : POST /reservations
  Inventory A commits transaction successfully
  Response is delayed or lost
  Caller times out

Attempt 2:
  Order -> Inventory B : POST /reservations
  Risk of double reservation if backend does not deduplicate
~~~

**A timeout does not prove the request failed on the server.** Therefore:

- Retrying GET is usually simpler than retrying POST with side effects, yet the backend must still be evaluated.
- For POST creating orders/payments/stock reservations, send the same **Idempotency-Key** across all attempts and enforce deduplication on the server.
- Cap **max attempts**, backoff, total deadline, and retryable statuses/exceptions.
- Distinguish retrying **on the same instance** from retrying **on a different instance**; switching instances does not guarantee the prior transaction never completed.
- Avoid nested retries (HTTP client + LoadBalancer + service mesh + business layer).

Conservative sum example:

~~~text
Total ~ attempt1(900ms) + backoff(100ms) + attempt2(900ms)
      = 1900ms
~~~

If the SLO is only 1,500 ms, this configuration is unsuitable from the start. A **deadline wrapper** placed at the right layer must bound **all retries**; placing a timeout inside a retry operator can grant a fresh clock to every attempt.

## 15. Streaming and “Trickle” Responses Are Important Exceptions

An API returning SSE, NDJSON, or a large download can run for a long time even when the connection is completely healthy:

~~~text
0s:  HTTP 200 + headers
1s:  event 1
2s:  event 2
3s:  event 3
...
60s: event 60
~~~

If the transport uses a **5s read inactivity timeout**, the stream can continue because data arrives every second. If a **5s total Mono timeout** is imposed on a Mono that only completes when the entire body is read, the request will be cancelled even though the stream is working as designed.

With Reactor:

~~~java
Flux<InventoryEvent> events = webClient.get()
        .uri("http://inventory-service/api/events")
        .retrieve()
        .bodyToFlux(InventoryEvent.class)
        .timeout(Duration.ofSeconds(15));
~~~

**Flux.timeout(Duration)** checks the delay between emitted signals, not the absolute total duration of the SSE stream. It helps detect a stream that stays silent too long if the contract requires regular heartbeats/events; however, it will break a healthy stream if valid gaps between two events can exceed 15 seconds.

A solid design typically separates:

1. Connection establishment timeout.
2. Timeout waiting for initial response headers.
3. Idle timeout when no network bytes or application events arrive.
4. Maximum lifetime cap **if** business rules require it.
5. Reconnect/resume policy using event IDs when the stream disconnects.

Depending on the transport, an HTTP chunk may arrive without forming a complete JSON/SSE event to emit onto the Flux. Thus, **network read timeout** and **Flux event timeout** can observe different silence intervals.

## 16. Under Which Exceptions Do Timeout Errors Appear?

There is no single **universal TimeoutException** across all HTTP transports:

| Client/transport | Common exception or root cause | What to distinguish |
| --- | --- | --- |
| RestTemplate/RestClient + HttpURLConnection | ResourceAccessException wrapping SocketTimeoutException, ConnectException... | Could be connect, read, or network |
| RestClient + JDK HttpClient | ResourceAccessException with cause from java.net.http, e.g., HttpTimeoutException/HttpConnectTimeoutException | Request timeout vs. connect timeout per cause |
| RestClient + Apache HC5 | ResourceAccessException or HTTP client wrapper; root cause socket/pool/handshake | Inspect cause chain to find phase |
| WebClient + Reactor Netty | WebClientRequestException; root cause ConnectTimeoutException, pool acquire timeout, SSLException... | I/O error before or during response |
| WebClient + Mono.timeout | java.util.concurrent.TimeoutException emitted by operator | May not be a connector error |
| OpenFeign | RetryableException/FeignException or cause from transport | Varies by Feign Client implementation |
| Any client receiving HTTP 408/504 | HTTP response with status from server/gateway | **Not synonymous** with client-side socket timeout |
| ServiceInstance not found | Error/response produced by LoadBalancer adapter | Possibly no socket connection at all |

Exception names span multiple libraries and versions; this table is a **classification guide**, not a guarantee of exact class names for every stack. When diagnosing:

1. Record the **top-level exception type and root cause**.
2. Verify whether HTTP response status/headers were received.
3. Verify whether a ServiceInstance was selected.
4. Verify whether TCP connected and the backend received the request.
5. Verify whether pool acquisition, DNS, TLS, or read was actually waiting.
6. Verify retry attempts and whether the deadline expired.

### 16.1. HTTP 408 or 504 Is Not Necessarily a Client Timeout

- **HTTP 408 Request Timeout**: the server or an intermediary returned an HTTP code because it did not receive the request on time under its policy.
- **HTTP 504 Gateway Timeout**: a gateway/proxy reports it did not receive a timely response from upstream.
- **Client-side response timeout**: the client stopped waiting on its own; there may be no HTTP response status.

All three contain the word “timeout,” yet their origin, operational response, and retry policy differ. **Never fabricate a fake HTTP 504** for every client timeout and ignore the root cause.

### 16.2. Exception Mapping Should Preserve Cause and Phase

At the adapter layer, you can use a domain taxonomy:

~~~java
sealed interface InventoryFailure
        permits PoolBusy, ConnectFailed, ResponseTimedOut,
                HttpFailure, InvalidResponse {}

record PoolBusy(String serviceId) implements InventoryFailure {}
record ConnectFailed(String serviceId) implements InventoryFailure {}
record ResponseTimedOut(String serviceId) implements InventoryFailure {}
record HttpFailure(String serviceId, int status)
        implements InventoryFailure {}
record InvalidResponse(String serviceId) implements InventoryFailure {}
~~~

This is an **illustrative Java 17+ data model**, not an error Spring creates automatically. In real code, the exception translator should inspect transport-specific causes and preserve trace ID/cause for diagnostics; never catch a **ResourceAccessException** and assume it is always a read timeout.

## 17. Test Timeouts Phase by Phase—Do Not Guess from Elapsed Time

A test reporting only “call failed after 2 seconds” **does not prove read timeout worked**. You must deliberately slow down the **exact phase** under test and verify the exception, root cause, and server-side logs.

### 17.1. MockWebServer: Delayed Response Body for a Blocking Client

JUnit and OkHttp MockWebServer 4.x example:

~~~java
@Test
void blockingClientTimesOutWhenBodyIsDelayed() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.start();
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody("late-response")
                .setBodyDelay(2, TimeUnit.SECONDS));

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(1));
        factory.setReadTimeout(Duration.ofMillis(300));

        RestClient client = RestClient.builder()
                .requestFactory(factory)
                .build();

        assertThrows(ResourceAccessException.class, () ->
                client.get()
                        .uri(server.url("/delayed").toString())
                        .retrieve()
                        .body(String.class));

        RecordedRequest received =
                server.takeRequest(1, TimeUnit.SECONDS);
        assertNotNull(received);
        assertEquals("/delayed", received.getPath());
    }
}
~~~

This example requires JUnit Jupiter, Spring Web, and **MockWebServer 4.x**, with imports such as **java.time.Duration**, **java.util.concurrent.TimeUnit**, **MockResponse**, **RecordedRequest**, and **ResourceAccessException**. It is designed to test **slow body reads** over HttpURLConnection. When using it in a project, check the mock server/lifecycle API of your version and inspect the actual root cause rather than stopping at a broad assertThrows.

**Important:** here the URI is the physical URL of the test server, so this test verifies the HTTP transport, **not Spring Cloud LoadBalancer**. A separate integration test using a service ID and @LoadBalanced is needed to verify target selection.

### 17.2. WebClient: Reactor Operator Timeout

~~~java
@Test
void reactorDeadlineCancelsSlowCall() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.start();
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody("late")
                .setBodyDelay(2, TimeUnit.SECONDS));

        WebClient client = WebClient.create();

        Mono<String> response = client.get()
                .uri(server.url("/slow").toString())
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofMillis(400));

        StepVerifier.create(response)
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(4));
    }
}
~~~

This test uses **Reactor StepVerifier**, without calling block(). This is a **Mono operator** timeout, not proof that Reactor Netty responseTimeout or CONNECT_TIMEOUT_MILLIS fired. To test the Netty layer itself, configure a dedicated connector and inspect the root cause.

With very short test timeouts, the event loop may not finish initializing before the deadline fires. **Warm up the client** or use a safe enough threshold so the test measures the intended scenario rather than fixture startup latency.

### 17.3. Testing Pool Acquire Timeout

To force a request to wait on the pool (Reactor Netty or Apache HC5):

1. Create a pool with at most **1 connection** to a host/route.
2. Have Request A acquire the connection and hold it long enough (e.g., server delays body).
3. Only after confirming Request A holds the connection, start Request B.
4. Set Request B's pool acquire timeout shorter than how long Request A holds the connection.
5. Verify B fails **while waiting on the pool**; the backend never received Request B.
6. Clean up/cancel A, then verify the pool recovers and works again.

Avoid just firing two concurrent requests and assuming A always wins the race. Use a latch/dispatcher/observable lifecycle to control when A has taken the slot. Also disable retries in this test so request counts are not obscured by extra attempts.

### 17.4. Testing Connect Timeout Is Not the Same as Connection Refused

A mock server on a closed port usually triggers **connection refused** very quickly, which **does not prove connect timeout**. Testing unacknowledged TCP SYN requires a controllable network environment (Toxiproxy, network namespaces, or network fault injection), and must avoid relying on random “blackhole” IPs that networks may handle differently.

Cases to separate:

| Test case | Fault-injection method | Assertion |
| --- | --- | --- |
| Connection refused | No listener on known port | Connection error usually arrives fast |
| Connect timeout | Network proxy drops connection in isolated test | Connect timeout in the right phase |
| Slow TLS handshake | Proxy/TLS test endpoint delays handshake | Handshake timeout or deadline |
| Slow response headers | Server receives request then delays headers | Response timeout |
| Slow response body | Server sends headers then delays body | Read/response timeout per engine |
| Trickle response | Server sends bytes at intervals near threshold | Verify idle timeout differs from overall deadline |
| Exhausted pool | Pool=1, Request A holds connection | Pool acquire timeout, not connect |
| Slow DNS | Mock resolver or controlled DNS network test | Resolver timeout, not response |

### 17.5. Testing Timeouts Together with LoadBalancer

A realistic integration test needs:

- Two MockWebServers returning different instance IDs.
- SimpleDiscoveryClient or a mock supplier providing two ServiceInstances.
- RestClient/WebClient with **@LoadBalanced** or OpenFeign integrated with LoadBalancer.
- Client calling **http://inventory-service/...**, not localhost directly.
- Instance A responding slowly, Instance B responding fast.
- Retries disabled or explicitly configured, then counting **RecordedRequest**s on both servers.

Facts to confirm:

~~~text
serviceId = inventory-service
selected  = inventory-a
physical  = localhost:<portA>
transport = Reactor Netty (or JDK/HC5...)
failure   = response timeout
attempt   = 1
~~~

If retries are enabled, also verify whether the second attempt selects Instance B. Seeing the caller receive HTTP 200 after a retry **does not prove LoadBalancer switched instances**.

## 18. Observability: Separating Latency from Timeout Type

A bare warning log:

~~~text
WARN downstream timeout after 2000ms
~~~

is insufficient. Collect these fields where possible:

| Field | Meaning |
| --- | --- |
| traceId / spanId | Links calls across services |
| serviceId | Logical downstream name |
| instanceId / host:port | Actual selected instance |
| transport | Reactor Netty, Apache HC5, JDK... |
| method / path template | Endpoint and retry safety |
| attempt | Attempt number |
| elapsedTotalMs | Duration of entire logical call |
| poolAcquireMs | Connection pool wait time, if measurable by engine |
| connectMs | Time to create new connection |
| tlsHandshakeMs | HTTPS handshake |
| responseWaitMs | Waiting for response/headers/body per engine |
| timeoutType | pool/connect/TLS/read/operator/deadline |
| httpStatus | Record only when a real response arrived |
| rootCause | Lowest useful exception class |

Spring Boot/Micrometer, Reactor Netty, and Apache HC5 offer corresponding hooks/metrics, though metric names and default enablement vary. This is a **recommended observability field set**, not built-in metric names across every connector.

When using Spring Cloud LoadBalancer, also observe:

- ServiceInstance list before/after cache, health, and zone/hint filters.
- Selected instance on initial attempt and retries.
- Cache TTL, health-check poll interval, and no-instance counts.
- Count of 503s from the backend or gateway itself, separate from instance-selection errors.
- Count of requests cancelled after the caller's deadline expired.

### 18.1. Do Not Log Sensitive Content to Debug Timeouts

When errors occur, never enable full logging of Authorization headers, Cookies, query tokens, request bodies containing customer data, or sensitive response bodies in production. Use **path templates**, instance IDs, statuses, error categories, trace IDs, and sanitized timings.

If you enable Netty/HTTP client wire logging in a test environment, disable or restrict its scope before deploying to production. Transport logs can contain sensitive headers or payloads.

## 19. Choosing Timeouts from SLOs, Not Copying Random Numbers

A design workflow applicable to each downstream call:

1. Determine the **inbound SLO**: how fast must Order API respond at P95/P99?
2. Subtract budget reserved for Order Service internal processing and response serialization.
3. Allocate budgets across sequential/concurrent downstream calls.
4. Measure real latency by zone, payload size, cold connections vs. keep-alive, and peak load.
5. Determine pool size, max concurrent requests, and pool acquire timeout.
6. Set connect timeout based on actual/internal network conditions.
7. Set response/read timeout by endpoint type (short GET, long export, SSE).
8. Design retry attempts/backoff within the remaining budget.
9. Place a final deadline on the whole logical call.
10. Test with network fault injection, pool saturation, and real client metrics.

Example: Order API has a 2,500 ms deadline; it needs 300 ms for internal processing and 200 ms for serialization and margin. Remaining downstream budget is roughly **2,000 ms**. If Inventory requires P99 700 ms, two 800 ms attempts with 100 ms backoff might fit, provided you verify overhead/pool behavior and whether the second attempt risks missing the deadline. This is an **allocation illustration**, not a rigid configuration for every system.

### 19.1. Too-Short Timeouts Are Also Dangerous

Setting every connect timeout to 50 ms and response timeout to 100 ms may reduce hung requests, yet causes:

- More TLS/cold-start failures.
- Cross-zone traffic with normal jitter to be cut abruptly.
- Retries amplifying backend load.
- Large but valid work to be cancelled repeatedly.
- Users seeing errors even though the backend could complete within a reasonable SLO.

Do not optimize solely for “fail as fast as humanly possible.” Balance **latency, availability, load, and business correctness**.

### 19.2. Too-Long Timeouts Exhaust Resources

Conversely, setting a 60-second response timeout on a small GET endpoint can hold connections/worker threads for long periods, lengthen pool queues, and spread failures to other downstream dependencies. In WebFlux, non-blocking I/O reduces waiting threads, yet **connections, buffers, pending acquire queues, and backend resources** remain occupied.

An overly long timeout can also let a circuit breaker observe too many slow calls before reacting; timeouts and circuit breakers address related risks, but **do not replace each other**.

## 20. Common Misconceptions and Fixes

| Misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| Connect timeout = cap on entire HTTP call | Only relates to new connections | Add response timeout and deadline |
| Read timeout 2s = response completes in 2s | Some engines measure I/O idle gaps, not total duration | Check exact factory/engine semantics |
| JDK factory and Simple factory are both JDK, so they behave identically | One uses HttpURLConnection, the other uses java.net.http.HttpClient | Read Javadoc and test separately |
| Pool acquire timeout and connect timeout are the same | Pool can wait before TCP connect | Measure pending connections |
| TLS handshake is guaranteed inside connect timeout | Transport-dependent; may have its own timeout | Configure and test TLS separately |
| WebClient.responseTimeout covers retries too | Retries usually run additional attempts outside the response timer | Place deadline outside retries for a total cap |
| Flux.timeout is a deadline for the whole stream | Usually checks the gap between signals | Design stream lifetime separately |
| Feign readTimeout behaves identically on HC5 and OkHttp | Underlying client determines details | Verify the actual Feign Client |
| Server returned 504 = client hit SocketTimeoutException | 504 is an HTTP response from a gateway | Separate HTTP status from I/O errors |
| Stopping the server tests connect timeout | Usually triggers connection refused immediately | Use a controlled fault proxy dropping TCP |
| Increasing timeouts fixes No instances available | No instance exists before sending HTTP | Check discovery/supplier/health |
| Retrying a timed-out POST is always safe | Server may have committed before timeout | Idempotency + operation-status API |
| One global timeout fits all endpoints | Short endpoints, streaming, and file transfers differ | Per-client/per-request policies |
| Raising pool size always cures pendingAcquireTimeout | Can push overload onto the backend | Measure saturation and cap concurrency |

## 21. Practice: Building a Timing Table for a Request

Given this scenario:

~~~text
Caller: order-service, request GET http://inventory-service/api/stock/X
LoadBalancer: selects inventory-a.internal:8443
Transport: Reactor Netty, HTTPS, pool limited to 10 connections

T_lookup = 40ms
T_pool   = 260ms
T_dns    = 20ms
T_tcp    = 100ms
T_tls    = 140ms
T_upload = 10ms
T_wait   = 900ms
T_body   = 100ms
~~~

**Question A:** roughly what is the total elapsed time if all steps occur sequentially?

**Question B:** with pendingAcquireTimeout=200ms, at which stage does it fail? Can ConnectTimeout=500ms save it?

**Question C:** if pool acquire succeeds and responseTimeout=1,000ms, is the caller guaranteed to finish within 1 second?

**Question D:** if the overall deadline is 1,500ms, does retrying the same request after 100ms backoff still make sense?

### Suggested Solutions

- **A:** approximately **1,570 ms** (summing the given numbers; in practice phases may not separate strictly).
- **B:** pool acquire needs 260ms but the limit is 200ms, so the request can fail **before TCP connect**. Raising connect timeout does not change pool wait time.
- **C:** no; response timeout does not cover pool/DNS/connect/TLS and decoding. Total time can exceed 1 second.
- **D:** the first attempt already spent about 1,570ms, so the 1,500ms deadline expired before a retry could start. The right policy is to stop and report/recover per contract rather than starting another attempt.

To extend the exercise, swap the transport to Apache HC5 and identify which properties must be set to bound pool, connect, TLS, and response similarly. Finally, run integration tests with MockWebServer/Toxiproxy to compare root causes.

## 22. Pre-Production Timeout Policy Checklist

- [ ] Verify the **actual HTTP engine** of every RestTemplate/RestClient/WebClient/Feign bean.
- [ ] Know whether that transport pools connections and where pool acquire timeout is configured.
- [ ] Set connect timeout for new connections using real network measurements.
- [ ] Set response/read timeouts appropriate to endpoint type and payload size.
- [ ] Verify TLS handshake and DNS/proxy timeouts if used by your infrastructure.
- [ ] Do not confuse read inactivity timeout with **total deadline**.
- [ ] Enforce a deadline for the entire logical call, covering service lookup, retries, backoff, and decoding as needed.
- [ ] Test timeouts on both **cold connections** and reused connections.
- [ ] When using WebClient, distinguish Mono.timeout, Flux.timeout, and Reactor Netty responseTimeout.
- [ ] When using OpenFeign, verify named client configs and the underlying Feign HTTP client.
- [ ] Never retry validation errors; requests with side effects must have idempotency/duplicate handling.
- [ ] Have tests for pool saturation, slow response headers/body, connection refused, and genuine transport timeouts.
- [ ] Have dedicated LoadBalancer tests to verify which instance gets chosen.
- [ ] Ensure observability separates pool/connect/TLS/response/deadline, HTTP statuses, and no-instance errors.
- [ ] Configure alerts for P95/P99, pool pending counts, timeout rate, retry amplification, and error budget.
- [ ] Never enable logs containing tokens/credentials or sensitive data.
- [ ] Document HTTP library and Spring BOM versions because semantics and defaults can change.

## 23. Conclusion

**Timeout is not a single number, but a set of per-phase limits.** Spring Cloud LoadBalancer selects an instance for a service ID; the HTTP transport governs how connections, responses, and bodies are awaited; the application layer is responsible for the **deadline** and safe retries.

Key points when comparing transports:

- **HttpURLConnection** provides URLConnection connect/read timeouts.
- **JDK HttpClient** provides client connect timeout and request timeout; Spring's JdkClientHttpRequestFactory sets “read timeout” via the request timeout mechanism.
- **Apache HC5** separates pool acquire, connection config, socket, and response timeouts.
- **Reactor Netty** separates pendingAcquireTimeout, CONNECT_TIMEOUT_MILLIS, responseTimeout, and SSL/DNS/proxy; Reactor Mono/Flux also offer signal-based timeout operators.
- **OpenFeign** exposes connectTimeout/readTimeout per client name, while execution depends on the underlying HTTP client.

Only by distinguishing **which clock runs during which phase**, measuring root causes, and testing against real transports can teams design timeout configurations that protect SLOs while avoiding retry storms and data corruption.

## 24. References

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): request factories for RestClient/RestTemplate and choosing an HTTP transport.
- [Spring Framework – SimpleClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): HttpURLConnection connect/read timeouts.
- [Spring Framework – JdkClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): setReadTimeout mapped to HttpRequest timeout.
- [Spring Framework – HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): HC5 connection request and response timeouts.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): Reactor Netty connector, connect/response timeouts, and native request overrides.
- [Reactor Netty – HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#_timeout_configuration): pool, connect, response, TLS, DNS, and proxy timeouts.
- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html): connection request timeout, response timeout, and non-deadline bounds.
- [Apache HttpClient 5 – ConnectionConfig](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.html): socket/connect/idle/TTL settings.
- [Oracle Java – HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connectTimeout and scope when reusing connections.
- [Oracle Java – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout and HttpTimeoutException.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named client connectTimeout/readTimeout, retry behavior, and HTTP engines.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstance selection, retries, and service discovery.
- [Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeout/retry and operator ordering.
