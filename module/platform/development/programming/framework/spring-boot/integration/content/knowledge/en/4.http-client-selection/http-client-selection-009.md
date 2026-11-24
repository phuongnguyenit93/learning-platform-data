# Integrating Observability and TLS via Boot Customization Points

## 1. Context: choosing an HTTP client also means choosing operational visibility

In a **Spring Boot Integration** application, the HTTP client is often the gateway to partner systems: fetching data over REST, sending transaction statuses, pulling catalog records, or calling an API after consuming a Kafka/RabbitMQ event. The flow may involve databases, caches, transactions, retries, and idempotency, while the HTTP boundary adds two further requirements:

- **Observability:** measure latency, statuses, and error rates; correlate partner requests with inbound HTTP or message-consumer traces; diagnose timeouts, TLS handshakes, and uncertain outcomes.
- **Trusted connections (TLS):** verify server certificates against an approved CA, use mutual TLS (mTLS) when required by contract, avoid leaking keys, and manage certificate lifecycles.

Spring Boot provides configuration hooks so both requirements apply consistently. How you construct the client determines whether it receives the registered **`ObservationRegistry`**, tracing/propagation, and SSL bundles. Calling `RestClient.create()` or `WebClient.create()` bypasses Boot's auto-configured customizers; when default observability is desired, **inject the Boot-provided builder** and build the client from it.

### Component diagram

~~~mermaid
flowchart TD
    A[HTTP inbound or broker consumer] --> B[Integration service]
    B --> C[RestClient.Builder / WebClient.Builder from Boot]
    D[Actuator + Micrometer ObservationRegistry] --> C
    E[RestClientCustomizer / WebClientCustomizer] --> C
    F[SSL Bundle: CA + client cert/key] --> G[RestClientSsl / WebClientSsl]
    G --> C
    C --> H[HTTP request factory / connector]
    H -->|TLS/mTLS| I[Partner API]
    C -. observations, metrics, trace context .-> J[Monitoring/Tracing exporter]
    I --> K[HTTP result]
    K --> B
    B --> L[DB / cache / broker / outbox]
~~~

Crucial distinction: *inbound TLS* for your web server (`server.ssl.*`) and *outbound TLS* when the client calls a partner are two separate configurations. Setting `server.ssl.bundle=...` does not make HTTP clients automatically trust a partner's certificate.

## 2. Choosing the right Spring Boot customization points

| Integration point | Scope | When to use |
| --- | --- | --- |
| Injected `RestClient.Builder` | One synchronous client, or several using `clone()` | Set per-partner base URL, headers, interceptors, SSL, and observations |
| Injected `WebClient.Builder` | One reactive/non-blocking client, or `clone()` for others | Set filters, connectors, SSL, metadata; preserve Reactor context |
| Injected `RestTemplateBuilder` | Legacy synchronous client using `RestTemplate` | Preserve instrumentation and add timeouts/SSL bundles via builder |
| `RestClientCustomizer` | All Boot-configured `RestClient.Builder`s | App-wide policies like `User-Agent` or consistent conventions |
| `WebClientCustomizer` | All Boot-configured `WebClient.Builder`s | Shared filters/policies for WebClient |
| `RestTemplateCustomizer` | All `RestTemplate`s built via Boot builder | Global adjustments on legacy clients |
| `RestClientSsl` / `WebClientSsl` | Specific selected client | Apply a declared `SslBundle` |
| `SslBundles` | Look up a named SSL bundle | Apply to `RestTemplateBuilder` or custom factories/connectors |
| `ClientHttpRequestFactoryBuilder` / `ClientHttpConnectorBuilder` | Synchronous / reactive transport layer | Need combined control over SSL, timeouts, redirects, and implementation details |
| `ObservationRegistry` + `ObservationConvention` | Measure and tag observations | Intentionally customize naming/tags/observations |

Spring Boot auto-configures builders based on classpath dependencies. A builder **holds state**: if you configure multiple clients from one shared instance, changes to base URL, headers, or SSL can bleed into subsequent builds. Inject separately per bean or call `clone()` when sharing a builder to isolate configurations.

### Choosing RestClient, WebClient, and RestTemplate

| Client | Characteristics | Recommended when |
| --- | --- | --- |
| `RestClient` | Synchronous fluent API, Spring Framework 6.1+, fits blocking Java | Spring MVC apps, scheduled jobs, thread-per-request services; starting point for new synchronous code |
| `WebClient` | Reactive API on `Mono/Flux`, integrates reactive context and non-blocking I/O with matching connector | Spring WebFlux, streaming, or high-concurrency I/O with a clear reactive model |
| `RestTemplate` | Long-standing synchronous API, still active in legacy systems | Maintaining existing code; prefer `RestClient` for new code when unconstrained |

Do not pick `WebClient` thinking it "has better built-in tracing": Boot instruments all three via their respective builders. In reactive flows, never call `block()` on the event loop. In purely synchronous flows, `RestClient` avoids unnecessary reactive complexity.

## 3. Dependencies and baseline configuration

The main code snippets below target **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17+**. In Spring Boot 4.x, several auto-configuration packages, starter names, and APIs have changed; the concepts still apply, yet **always cross-check docs and the BOM for your exact project version**.

For a synchronous Spring MVC application:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

If using `WebClient` without Spring WebFlux already present, add the matching starter:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

You can use `WebClient` inside an MVC application; when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot normally selects a servlet web application. That neither makes `WebClient` calls blocking nor automatically turns your business service reactive.

To export metrics to Prometheus, add `io.micrometer:micrometer-registry-prometheus`. To export traces, add **one** Micrometer Tracing Bridge (e.g., `micrometer-tracing-bridge-otel`) and a Boot-compatible OTLP exporter; adding Actuator alone does not ship traces to a collector. Spring Boot 4.x introduces new telemetry starter packaging, so always consult the tracing guide for your exact version.

~~~yaml
# application.yml — illustrative application properties
integration:
  partner:
    base-url: https://partner.example.internal
    connect-timeout: 2s
    read-timeout: 5s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 0.1
~~~

`management.tracing.sampling.probability=0.1` illustrates a 10% sampling rate once tracing dependencies are configured. In local tests you can set `1.0` for visibility, then tune appropriately in production. Keys under `integration.partner.*` are **application-defined properties** that must be bound via `@ConfigurationProperties` or read via `@Value`; Spring Boot does not auto-configure HTTP clients from this prefix.

## 4. Automatic observability via Boot builders

Micrometer Observation provides a unified API for metrics and tracing. Spring Framework creates observations for HTTP client exchanges under the default name `http.client.requests`; Spring Boot wires builder-created client beans to `ObservationRegistry` and relevant customizers. With a proper tracing bridge and exporter, trace context such as `traceparent` propagates to partner services per the active propagator.

### 4.1. Synchronous RestClient via injected builder

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerRestClientConfig {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Caller-Service", "spring-boot-integration")
                .build();
    }
}
~~~

Because `RestClient.Builder` is Boot-managed, global observation settings still apply. You do not need to construct an `ObservationRegistry` manually or attach a custom interceptor just to obtain basic HTTP metrics.

Business clients should use URI templates to avoid exploding metric cardinality:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerCatalogClient {
    private final RestClient client;

    public PartnerCatalogClient(RestClient partnerRestClient) {
        this.client = partnerRestClient;
    }

    public ProductDto findProduct(String productId) {
        return client.get()
                .uri("/v1/products/{id}", productId)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

`ProductDto` is an application-defined DTO matching the partner's JSON contract. Using `.uri("/v1/products/{id}", productId)` keeps observation URI tags in low-cardinality template form; concatenating `"/v1/products/" + productId` can generate a distinct metric series per ID if the framework cannot recognize the template.

### 4.2. WebClient via auto-configured builder

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfig {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Caller-Service", "spring-boot-integration")
                .build();
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactivePartnerCatalogClient {
    private final WebClient client;

    public ReactivePartnerCatalogClient(WebClient partnerWebClient) {
        this.client = partnerWebClient;
    }

    public Mono<ProductDto> findProduct(String id) {
        return client.get()
                .uri("/v1/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
~~~

In Reactor, trace context travels with the reactive subscriber/context rather than a single `ThreadLocal`. Avoid spawning raw threads or hopping across external callbacks that drop context; when bridging executors, coroutines, or message listeners, configure proper context propagation. When consuming from brokers, verify trace-header extraction and injection on the broker adapter separately.

### 4.3. Legacy RestTemplate via builder

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LegacyPartnerClientConfig {

    @Bean
    RestTemplate legacyPartnerRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://legacy.example.internal")
                .build();
    }
}
~~~

`new RestTemplate()` works, yet does not automatically receive Boot customizers and tracing the way a builder-created `RestTemplate` does. Similarly, `RestClient.create()` and `WebClient.create()` bypass registered Boot customizers.

### 4.4. Application-wide vs. per-partner customization

Spring Boot lets you register customizer beans. Example adding a shared `User-Agent` across `RestClient`s:

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;

@Configuration(proxyBeanMethods = false)
class GlobalHttpClientCustomization {
    @Bean
    RestClientCustomizer integrationUserAgent() {
        return builder -> builder.defaultHeader(
                HttpHeaders.USER_AGENT, "spring-boot-integration");
    }
}
~~~

This is the `RestClientCustomizer` package in **Boot 3.5.x**. For `WebClient`, use `org.springframework.boot.web.reactive.function.client.WebClientCustomizer`, which receives `WebClient.Builder`. For legacy `RestTemplate`, `org.springframework.boot.web.client.RestTemplateCustomizer` mutates the `RestTemplate` instance after the builder creates it. Each has its own scope and is applied by Boot when building from auto-configured builders.

Scoping rules:

- **Application-wide:** common `User-Agent`, non-sensitive conventions, approved logging/tracing policies.
- **Per-partner:** base URL, tokens, mTLS client certificates, timeouts, retries, and error mapping. Never put partner A's `Authorization` header in a global customizer, or it will leak to partner B.
- **Per-request:** correlation/business IDs, idempotency keys, and per-call business parameters.

Customizers should **augment** Boot-supplied configuration. Calling `ObservationRegistry.create()` and overwriting it on the builder strips handlers and tracing bridges registered by Boot. Never build an extra client via `RestClient.create()` inside a customizer expecting framework settings to apply to it.

### 4.5. Replacing ObservationConvention only when truly needed

By default, `http.client.requests` already records metadata like method, URI template, HTTP status, outcome, host, and error type. To add a **low-cardinality** tag, define a `RestClient`-specific convention:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.http.client.observation.ClientRequestObservationContext;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;

public final class PartnerHttpObservationConvention
        extends DefaultClientRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ClientRequestObservationContext context) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("remote.service", "partner-catalog"));
    }
}
~~~

Attach it on the **partner's builder**:

~~~java
return builder
        .baseUrl(baseUrl)
        .observationConvention(new PartnerHttpObservationConvention())
        .build();
~~~

This replaces the client construction inside section 4.1 (placed inside the `@Bean` method, not as a second bean with the same name). Tag with a *stable partner-group name*. Never attach `userId`, `productId`, `requestId`, tokens, query strings, or full URLs as low-cardinality tags; metric series explode with user data and risk leaking sensitive values.

For `WebClient`, `ClientRequestObservationConvention` lives in the reactive package `org.springframework.web.reactive.function.client`, distinct from the synchronous client type. Never try forcing a `RestClient` convention onto `WebClient`.

## 5. Creating and applying SSL bundles for outbound HTTP

TLS on an HTTP client performs two tasks:

1. **Server authentication:** the client validates the server's certificate chain and URL hostname, preventing connections to impersonating servers.
2. **Client authentication (mTLS):** when required by the partner API, the client presents a valid certificate and private key so the server authenticates the client.

Spring Boot defines named **SSL bundles** under `spring.ssl.bundle.pem.*` (PEM) or `spring.ssl.bundle.jks.*` (JKS/PKCS12). A bundle holds trust material, key material, and TLS options, and can be reused by name across clients where appropriate.

### 5.1. Bundle trusting only a partner CA

~~~yaml
# application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: file:/run/secrets/partner-ca.pem
~~~

`partner-ca.pem` should hold the approved CA chain verifying the partner API. When a server uses a public CA already present in the JVM truststore, a custom bundle may be unnecessary; when a partner uses a private CA, configuring a truststore is essential. Never copy a certificate from an unverified server straight into a truststore without verifying its provenance.

### 5.2. Bundle for mutual TLS (mTLS)

When the partner requires a client certificate, add a `keystore` containing the application's own certificate and key:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: file:/run/secrets/partner-ca.pem
          keystore:
            certificate: file:/run/secrets/integration-client.crt
            private-key: file:/run/secrets/integration-client.key
~~~

For PKCS12/JKS, use `spring.ssl.bundle.jks.partner-api.truststore.location` and `keystore.location`, sourcing passwords from secrets/environment variables rather than committing them to Git. Configuring a certificate **without a private key** is insufficient for mTLS. In Kubernetes clusters, mount secrets as files with minimal permissions; never log keys or bake them into container images.

TLS policy: enforce certificate chain and hostname verification, permit only organization-approved TLS versions/ciphers, and account for SNI and DNS across proxies. **Never** install a trust-all `SSLContext` or disable hostname verification to get past handshake errors; that strips server identity verification.

### 5.3. Attaching a bundle to RestClient via RestClientSsl

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class SecurePartnerRestClientConfig {

    @Bean
    RestClient securePartnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`RestClientSsl` lives in `org.springframework.boot.autoconfigure.web.client` in Boot **3.5.x**. Using Boot's builder retains observation/tracing while applying the registered SSL bundle. You do not need to construct an `SSLContext` or load private keys manually here.

**Configuration ordering warning:** `ssl.fromBundle(...)` **replaces any previously configured `ClientHttpRequestFactory`**. If you configured a custom factory with timeouts, proxies, or connection pools and then called `apply(ssl.fromBundle(...))`, the old factory may be overwritten and its settings lost. When combining SSL with advanced transport settings, construct a single factory using the builders in section 6 and pass it once to the builder.

### 5.4. Attaching a bundle to WebClient via WebClientSsl

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class SecurePartnerWebClientConfig {

    @Bean
    WebClient securePartnerWebClient(
            WebClient.Builder builder,
            WebClientSsl ssl,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`WebClientSsl` lives in `org.springframework.boot.autoconfigure.web.reactive.function.client` in Boot 3.5.x. Just like `RestClient`, applying `fromBundle(...)` **replaces any previously assigned `ClientHttpConnector`**. If using a custom Reactor Netty connector for TCP proxies, pooling, wiretaps, or response timeouts, combine TLS into the final connector instead of setting a connector and inadvertently overwriting it with `WebClientSsl`.

### 5.5. RestTemplateBuilder using SslBundles

~~~java
import java.time.Duration;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

@Bean
RestTemplate secureLegacyRestTemplate(
        RestTemplateBuilder builder, SslBundles sslBundles) {
    return builder
            .rootUri("https://legacy.example.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(5))
            .sslBundle(sslBundles.getBundle("partner-api"))
            .build();
}
~~~

This uses `RestTemplateBuilder.sslBundle(SslBundle)` in **Boot 3.4+**. The older methods `setSslBundle`, `setConnectTimeout`, and `setReadTimeout` were deprecated in Boot 3.4 and may be removed in Boot 4. The snippet assumes placement inside a `@Configuration` class with `@Bean` imported.

## 6. Combining timeouts, TLS, and transport without losing instrumentation

### 6.1. Application-wide settings via Boot properties

In **Spring Boot 3.5**, shared HTTP client properties can be declared as:

~~~yaml
spring:
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
      redirects: dont-follow
~~~

These properties apply to **Boot auto-configured HTTP clients**, not `server.tomcat.connection-timeout`, `spring.mvc.async.request-timeout`, or controller timeouts. When partners have differing SLAs, override them on the specific client bean.

**Version difference:** Boot 3.5 uses `spring.http.client.*` (blocking) and `spring.http.reactiveclient.*` (reactive). In **Boot 4.x**, Spring Boot unified these into `spring.http.clients.*`, such as `spring.http.clients.connect-timeout`, `spring.http.clients.read-timeout`, and `spring.http.clients.ssl.bundle`. Read the configuration metadata and migration guide for your exact version before changing properties; never mix the two prefixes.

Distinguish timeouts:

| Timeout | Bounds | Excludes / reminders |
| --- | --- | --- |
| Connect timeout | Time to establish the connection to the server | Body reads, backend processing, retries |
| Read/response timeout | Waiting for data/responses per transport implementation | Not always a deadline for entire large bodies or long streams |
| Pool acquire timeout | Waiting to lease a connection when the pool is saturated | Must be configured separately on the chosen HTTP engine |
| Total task deadline | HTTP + retries/backoff + DB/broker + data processing | Designed at service/worker layer; canceling does not undo remote work |

Never pick a 5-second read timeout and allow 10 consecutive retries inside an HTTP request with a 3-second SLA. Enforce a **retry budget**, circuit breakers, bulkheads, and idempotency keys for side effects.

### 6.2. Factory combining SSL + connect/read timeouts for RestClient

In Boot 3.5, `ClientHttpRequestFactorySettings` and `ClientHttpRequestFactoryBuilder` unify SSL bundles and timeouts into **one factory**:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.ClientHttpRequestFactoryBuilder;
import org.springframework.boot.http.client.ClientHttpRequestFactorySettings;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PartnerTransportConfig {

    @Bean
    RestClient partnerClientWithTransport(
            RestClient.Builder builder,
            SslBundles sslBundles,
            @Value("${integration.partner.base-url}") String baseUrl) {

        ClientHttpRequestFactorySettings settings =
                ClientHttpRequestFactorySettings.defaults()
                        .withTimeouts(
                                Duration.ofSeconds(2),
                                Duration.ofSeconds(5))
                        .withSslBundle(sslBundles.getBundle("partner-api"));

        ClientHttpRequestFactory factory =
                ClientHttpRequestFactoryBuilder.detect().build(settings);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

Here you do **not** call `ssl.fromBundle(...)` because `factory` was already built with the SSL bundle. `ClientHttpRequestFactoryBuilder.detect()` selects an engine from the classpath (e.g., Apache HttpClient, Jetty, Reactor, JDK); precedence depends on the running Boot version, and dependency shifts can swap the detected engine. When deterministic behavior is needed, pick a concrete factory/engine and test in the target deployment environment.

Setting the factory via `builder.requestFactory(factory)` preserves observation customizers already registered on `RestClient.Builder`, whereas replacing the builder with a manual `RestClient.builder()` drops Boot's `ObservationRegistry`.

### 6.3. Connector combining SSL + timeouts for WebClient

Boot 3.5 provides `ClientHttpConnectorBuilder` and `ClientHttpConnectorSettings` for reactive transports, building connectors from the same SSL bundle:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.reactive.ClientHttpConnectorBuilder;
import org.springframework.boot.http.client.reactive.ClientHttpConnectorSettings;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PartnerReactiveTransportConfig {

    @Bean
    WebClient partnerReactiveClientWithTransport(
            WebClient.Builder builder,
            SslBundles sslBundles,
            @Value("${integration.partner.base-url}") String baseUrl) {

        ClientHttpConnectorSettings settings =
                ClientHttpConnectorSettings.defaults()
                        .withTimeouts(
                                Duration.ofSeconds(2),
                                Duration.ofSeconds(5))
                        .withSslBundle(sslBundles.getBundle("partner-api"));

        ClientHttpConnector connector =
                ClientHttpConnectorBuilder.detect().build(settings);

        return builder
                .baseUrl(baseUrl)
                .clientConnector(connector)
                .build();
    }
}
~~~

As with `RestClient`, this is an **alternative** to `WebClientSsl.fromBundle(...)`, not an extra step after `fromBundle`. When advanced Reactor Netty features are required (pool idle/TTL, response timeout, proxy, or wiretap), use the engine's customizer/builder while keeping valid SSL trust material. Never install a custom Netty `SSLContext` with trust-all or disabled hostname verification.

Note that `ClientHttpRequestFactorySettings`, `ClientHttpConnectorSettings`, and the builders above are relatively recent **Boot 3.4/3.5** APIs; Boot 4 restructures these settings classes. The code here is anchored to Boot 3.5; when upgrading major versions, consult the migration guide and API reference.

### 6.4. Avoiding losing instrumentation when customizing transport

Selection workflow:

~~~mermaid
flowchart TD
    A[Need HTTP client?] --> B{Blocking or reactive?}
    B -- Blocking --> C[Inject RestClient.Builder]
    B -- Reactive --> D[Inject WebClient.Builder]
    C --> E{Only need TLS bundle?}
    D --> F{Only need TLS bundle?}
    E -- Yes --> G[RestClientSsl.fromBundle]
    F -- Yes --> H[WebClientSsl.fromBundle]
    E -- TLS + advanced transport --> I[ClientHttpRequestFactoryBuilder + SslBundle]
    F -- TLS + advanced transport --> J[ClientHttpConnectorBuilder + SslBundle]
    G --> K[Build + retain ObservationRegistry]
    H --> K
    I --> K
    J --> K
    K --> L[Test HTTPS, metrics, trace, timeout]
~~~

Timeouts or TLS are configured via a deliberate factory/connector; **observability** remains attached to the builder. Never assume swapping a Netty connector or Apache request factory preserves Spring spans if you also discarded the Boot-managed builder.

## 7. Designing traces and metrics for integration flows

### 7.1. How a trace flows across systems

~~~text
POST /integration/orders              traceId=T
   |
   +-- Spring MVC HTTP server span
          |
          +-- DB: save idempotency key R1
          |
          +-- RestClient HTTP client span
                 |-- traceparent: 00-T-...-01 (when tracing is active)
                 +-- HTTPS / mTLS --> Partner API
          |
          +-- DB: write state + outbox
          |
          +-- Broker publisher / consumer spans
~~~

In synchronous HTTP requests, trace context normally lives on the processing thread; Boot builders paired with Micrometer Tracing propagate context over HTTP headers via the configured propagator. In Kafka/RabbitMQ flows, extracting context from message headers and injecting it into HTTP calls depends on broker instrumentation/adapters. If messages hop onto a custom executor, ensure context propagation so traces do not break.

**Never blindly copy an external `traceparent` header bypassing tracer processing.** Trace headers must be parsed and written according to specifications and sampling/trust rules. Never treat `traceId` as an idempotency key: retries and redeliveries can produce different traces/spans, whereas the business request ID must remain constant.

### 7.2. Choosing low-cardinality tags

HTTP client observations typically capture shared metadata:

| Tag / metadata | Example | Notes |
| --- | --- | --- |
| `method` | `GET`, `POST` | Bounded set |
| `uri` | `/v1/products/{id}` | Use URI templates; never embed real IDs in metrics |
| `client.name` | `partner.example.internal` | Avoid uncontrolled dynamic hosts |
| `status` | `200`, `503`, `IO_ERROR` | Tagged per framework version conventions |
| `outcome` | `SUCCESS`, `SERVER_ERROR` | Separates HTTP errors from I/O failures |
| `error` | `ResourceAccessException` or `none` | Distinct from detailed error messages |
| Custom `remote.service` | `partner-catalog` | Fixed value from a bounded catalog |

The `http.client.requests` metric tracks throughput, latency, and status/error counts. For accurate P95/P99, configure Micrometer histograms/percentiles and keep tag cardinality low. Track **retry attempts**, **circuit breaker state**, **TLS handshake failures**, **pool acquire waits**, **downstream timeouts**, and **message/outbox backlogs** separately when impactful; default HTTP observations do not cover all of those layers.

### 7.3. HTTP 4xx/5xx vs. transport/TLS errors

| Scenario | HTTP response received? | How observed | Integration action |
| --- | --- | --- | --- |
| `404 Not Found` | Yes | HTTP status and URI template | Per contract: absent record vs. wrong endpoint |
| `401/403` | Yes | HTTP status; never log token | Check credentials/authorization; avoid blind retries |
| `429 Too Many Requests` | Yes | HTTP status, `Retry-After` if present | Backoff/rate limit within retry budget |
| `500/503` | Yes | HTTP status, latency, response/traces | Bounded retries if operation is idempotent |
| DNS/connect timeout | No | I/O exception, DNS/connection metrics | Classify unavailable; never map to 404 |
| TLS cert/hostname mismatch | No HTTP response | SSL handshake exception + error trace | Fix trust material or hostname; never disable checks |
| Read timeout after sending POST | Possibly no | Exception + requestId in application logs | Business outcome *uncertain*; verify idempotency before retrying |

Under Spring's `retrieve()` defaults, 4xx/5xx raise exceptions unless custom status handlers are registered; TLS/socket failures occur before or during the exchange and must be handled as infrastructure failures. Never flatten every exception into empty data or a success response.

## 8. Example POST flow with idempotency and end-to-end tracing

Suppose an application receives an order command from an API or broker, saves state via JDBC/MongoDB, and calls a partner API. If a timeout occurs after the partner already created the order, retries must remain safe. One approach is passing a stable **business idempotency key** to the partner, provided the partner API supports that contract.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerOrderGateway {
    private final RestClient partnerRestClient;

    public PartnerOrderGateway(RestClient partnerRestClient) {
        this.partnerRestClient = partnerRestClient;
    }

    public void submit(String requestId, CreateOrderRequest payload) {
        partnerRestClient.post()
                .uri("/v1/orders")
                .header("Idempotency-Key", requestId)
                .body(payload)
                .retrieve()
                .toBodilessEntity();
    }
}
~~~

`CreateOrderRequest` is a DTO matching the partner contract. The request runs through a Boot-configured `RestClient`, gaining default trace spans and metrics while picking up TLS/mTLS from the attached bundle. If the partner returns `202 Accepted` rather than `200`/`201`, follow the response contract: polling or status inquiry may be required before marking business processing complete.

**Design conditions:**

1. `requestId` is generated at the message/command ingress boundary and stays identical across retries, restarts, and message redeliveries. Never mint a fresh UUID per attempt.
2. If the partner lacks idempotency keys, implement status lookup before/after retries plus reconciliation rules. HTTP observations do not give exactly-once delivery.
3. Distinguish `ReadTimeoutException` / socket timeouts (uncertain outcome), `429`, `503`, and auth/TLS failures; never retry them identically.
4. Persist state and emit events via a transactional outbox when DB-to-broker consistency is needed. An HTTP call does not join a DB transaction merely by running inside `@Transactional`.
5. Never log request bodies or `Authorization`/`Cookie`/client private keys. When debugging, log method, URI template, status, latency, remote service, and a safe correlation ID.

**Copy-paste note:** the `partnerRestClient`, `securePartnerRestClient`, and `partnerClientWithTransport` beans above are **three alternative configurations** for the same goal. A real app chooses one per partner; if registering multiple `RestClient` beans, inject with `@Qualifier("partnerRestClient")` to avoid ambiguous dependency errors. Same applies to `WebClient`. Minimal DTO for the GET example:

~~~java
public record ProductDto(String id, String name) {}
~~~

## 9. Meaningful observability and TLS testing

### 9.1. Testing HTTP logic without a real server

For JSON contracts, status mapping, and URI templates, use `@RestClientTest` + `MockRestServiceServer` or appropriate Spring tests to verify:

- Correct HTTP method, path, and business headers.
- URI templates are passed so observations stay templated.
- JSON serializers/deserializers handle required fields and schema errors.
- `404/409/429/5xx` map per contract instead of collapsing into socket failures.
- Retries preserve `Idempotency-Key`.

HTTP-layer mocks **do not verify real TLS handshakes** and may not fully exercise observation/trace export. Never conclude truststores or client certificates work based solely on mocked `RestClient` tests.

### 9.2. HTTPS/mTLS integration tests

Start an HTTPS test server (such as TLS-enabled MockWebServer/WireMock or a test container), generate *test-only* CA/cert/key material, and run the Spring Boot context with SSL bundles pointing to the test material. Test matrix:

| Scenario | Configuration | Expectation |
| --- | --- | --- |
| Standard HTTPS | Test server's CA in truststore | Handshake succeeds, HTTP request transmitted |
| Untrusted private CA | Remove test server's CA from truststore | Handshake rejected; cert verification never bypassed |
| Hostname mismatch | Server cert SAN does not match dialed DNS | Handshake/hostname verification fails |
| Valid mTLS | Server demands client cert; bundle supplies valid cert/key | Handshake and request succeed |
| mTLS missing client cert/key | Server demands client auth; client omits valid bundle | Connection rejected per TLS contract |
| Expired TLS certificate | Test server or client uses expired cert | Rejected, emitting matching error metric/alert |
| Connect timeout | Unreachable/blackholed test server route | Timeout exception fires within configured budget |
| Read timeout | Connected cleanly, server delays response | Matching timeout category; never mapped to 404 |
| 429/503 | Server returns simulated status and headers | Retry/backoff/rate-limit obeys policy |

For `WebClient`, also verify request cancellation, backpressure, and that parent–child span relationships survive `flatMap`/`publishOn` or custom executors.

### 9.3. Verifying live metrics and traces

Verification steps:

1. Enable Actuator and a **test-environment** tracing exporter. Use `1.0` sampling strictly in tests if every request must be traced.
2. Invoke an inbound endpoint so the service fires an outbound HTTP call via Boot's builder. Wait for the response and inspect `/actuator/metrics/http.client.requests` if enabled and recorded.
3. Verify tags: method, URI template, client name, status/outcome; confirm request IDs and access tokens do not appear in tags.
4. Inspect traces in the collector: inbound server span and outbound HTTP client span share `traceId` with proper parent–child hierarchy; `traceparent` arrives at the test server when tracing is active.
5. Inject 503, TLS handshake failure, and timeout to verify exception mapping, result tags, and correlation in logs.
6. Restrict and secure Actuator access; never expose all metrics/tracing endpoints to the Internet just to ease testing.

In Spring Boot 3.5, Actuator also exposes the `ssl.chain.expiry` metric to monitor remaining lifetime until certificates in an SSL bundle expire (reported in seconds); configure alerts well before certificates cause outages. Exact metric names/tags and bundle reload support vary by version and transport; verify against your runtime instead of assuming connection pools automatically pick up rotated secret files immediately.

### 9.4. Verifying customizers remain active

Run an integration test using the exact `RestClient` bean from the application context and check:

- The global customizer added the `User-Agent` header.
- The right SSL bundle took effect (handshake passes with the private CA, fails with another CA).
- Connect/read timeouts survived SSL configuration—a common bug when `apply(ssl.fromBundle(...))` and `requestFactory(...)` are ordered wrong.
- `http.client.requests` metrics and trace context remain intact after customizing the request factory/connector.
- Partner A's `Authorization` header never appears on requests to Partner B in multi-client setups.

You never need a live production endpoint for this. A local test HTTPS server with test-only certificates reproduces TLS failure modes deterministically without touching partner systems.

## 10. Deployment and troubleshooting checklist

### 10.1. Before deploying

| Question | What to verify |
| --- | --- |
| How is the client built? | Injected Boot builder; avoid manual client creation that drops instrumentation |
| Global vs. per-partner config? | Global customizers contain no partner-specific tokens, URLs, or TLS settings |
| Which SSL bundle? | Correct bundle name, trusted CA verified; mTLS has matching cert and private key |
| Finite timeouts configured? | Connect/read/pool wait and overall deadlines aligned with SLA; retries stay within budget |
| Certificates monitored? | Expiry alerts, rotation runbook, post-rotation mTLS verification |
| Reasonable metric cardinality? | URI templates, bounded partner tags, no tokens/PII in logs or tags |
| Cross-system trace intact? | Inbound HTTP → outbound HTTP → broker/DB preserves context |
| Errors classified? | HTTP statuses distinct from TLS/socket errors; POST timeouts marked uncertain |
| Retries idempotent? | Stable business keys, backoff, circuit breakers, outbox or reconciliation |
| TLS genuinely tested? | Handshakes tested with valid and invalid CA/mTLS; not just mocked HTTP responses |

### 10.2. Common issues

**Missing `http.client.requests`:** verify you used an injected `RestClient.Builder`/`WebClient.Builder`/`RestTemplateBuilder`; verify Actuator/`ObservationRegistry` is in the context; ensure the client actually executed a request; verify meter registry/exporters are enabled. If traces are missing while metrics appear, check the tracing bridge, exporter, and sampling probability.

**Outbound span has a different `traceId` from inbound:** check for manual thread creation, custom schedulers, broken subscriber/reactive context, or broker adapters failing to propagate headers. Never "fix" this by copying raw `traceparent` strings manually.

**PKIX path building failed / certificate unknown:** truststore lacks the CA chain, server cert is wrong or expired, or a host/proxy routed to an unexpected server. Verify the server certificate chain and hostname; never disable trust verification.

**mTLS handshake failure:** confirm the server requests client certs, cert/key match, validity dates and Extended Key Usage match, full chain is sent, and SNI/hostname plus TLS protocols/ciphers are compatible.

**Configured timeouts have no effect:** check which engine was auto-detected; check which timeout was set (connect, response, pool acquire, total); check whether `RestClientSsl`/`WebClientSsl` replaced your factory/connector afterward; verify your custom transport honors those settings.

**Old certificate still seen after secret rotation:** connections are being reused, or the SSLContext/connector cached keys at startup. Check reload support for your client/engine and implement controlled pool recreation or rolling restarts; watch certificate expiry metrics post-rotation.

**5xx errors spike after enabling retries:** total request rate can multiply sharply. Track attempt rates, error ratios, concurrency, and circuit breakers; cap retries and apply backoff. For resource-creating POSTs, retry only with clear idempotency/reconciliation contracts.

## 11. Version boundaries and engineering decisions

| Topic | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| RestClient SSL helper | `org.springframework.boot.autoconfigure.web.client.RestClientSsl` | Package moved to REST client auto-configuration module; check current API |
| WebClient SSL helper | `org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl` | `org.springframework.boot.webclient.autoconfigure.WebClientSsl` in Boot 4 API |
| RestClientCustomizer | `org.springframework.boot.web.client.RestClientCustomizer` | Reorganized module/package layout; check IDE and API |
| Global HTTP client settings | `spring.http.client.*` (blocking) and `spring.http.reactiveclient.*` (reactive) | `spring.http.clients.*` |
| Transport settings | `ClientHttpRequestFactorySettings`, `ClientHttpConnectorSettings`, and 3.5 builders | Unified `HttpClientSettings` in the new API |
| Observation | Inject Boot builder + Actuator/Micrometer | Same principle, matching updated packages and starters |
| SSL bundles | `spring.ssl.bundle.pem/jks.*`, inject/apply bundle | Same concept, verify updated APIs before upgrading |

Never copy imports blindly from Boot 3.5 into 4.x where packages moved. When pinned to a specific BOM version, consult Javadocs/reference guides for **that exact release** and watch deprecation warnings. Snippets here are scoped per topic; in real implementations, pick one coherent client configuration per endpoint and test it inside a real Spring context.

### Self-check

1. Why can `RestClient.create()` still call an API yet miss default metrics and tracing provided by a Boot builder?
2. Does configuring `server.ssl.bundle` automatically make `WebClient` trust a partner API's certificate?
3. If you apply `RestClientSsl.fromBundle` after configuring a custom `requestFactory`, what can happen to previously configured timeouts?
4. What is the difference between a CA truststore and a client certificate/private key in mTLS?
5. Why is `.uri("/v1/products/{id}", id)` better for metrics than concatenating the raw ID?
6. When a `POST` times out and the partner may have processed it, why are an idempotency key and reconciliation required?
7. What test setup proves TLS handshakes, metrics/tracing, and timeouts all still work together after customizing a connector?

## References

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5 — SSL Bundles](https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html)
- [Spring Boot 3.5 — Actuator HTTP Client Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Tracing and Propagation](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot 3.5 API — RestClientSsl](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html)
- [Spring Boot 3.5 API — WebClientSsl](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/function/client/WebClientSsl.html)
- [Spring Boot 3.5 API — ClientHttpRequestFactoryBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/ClientHttpRequestFactoryBuilder.html)
- [Spring Boot 3.5 API — ClientHttpConnectorBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/reactive/ClientHttpConnectorBuilder.html)
- [Spring Boot 4 — Calling REST Services](https://docs.spring.io/spring-boot/4.0/reference/io/rest-client.html)
