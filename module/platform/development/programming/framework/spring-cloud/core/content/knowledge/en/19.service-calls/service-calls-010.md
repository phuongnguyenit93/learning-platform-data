# Preserving Configuration and Observability of Spring Boot-Provided Builders

When calling services through Spring Cloud LoadBalancer, an application typically declares a builder with the **@LoadBalanced** qualifier to translate logical service names into real instance addresses. If you create a brand-new builder without applying Spring Boot's configuration, the client may still call services, yet lose foundational settings such as message converters/codecs, HTTP request factories/connectors, SSL bundles, timeouts, customizers, and especially HTTP client observability.

Spring Boot provides pre-configured builders for **RestTemplate**, **RestClient**, and **WebClient**. Spring Cloud provides the mechanism to mark a builder as load-balanced. When both mechanisms are used together, you must preserve Boot's configuration while creating the LoadBalancer-enabled builder.

This lesson belongs to the **Service Calls** chapter of the **SPRING_CLOUD_CORE** module. The goal is to understand why Boot's customizers must be preserved, how to combine them with @LoadBalanced, how to distinguish regular and load-balanced builders, and how to verify metrics/traces of requests passing through the client.

## 1. Two configuration layers collaborate to build an HTTP client

An HTTP client in a Spring Cloud application typically receives configuration from two sides:

- **Spring Boot:** foundational HTTP client configuration, message conversion, codecs, request factories/connectors, SSL, ObservationRegistry, and application customizers.
- **Spring Cloud LoadBalancer:** adds service name resolution and ServiceInstance selection before sending requests.

These two layers solve two different tasks. Boot prepares an operable, observable HTTP client; LoadBalancer replaces a logical service name with a selected instance address.

~~~mermaid
flowchart TD
    A["Spring Boot auto-configuration"] --> B["Builder with baseline configuration"]
    A --> C["Builder customizers"]
    C --> B
    D["@LoadBalanced"] --> E["Spring Cloud LoadBalancer customization"]
    B --> F["Load-balanced builder"]
    E --> F
    F --> G["RestTemplate / RestClient / WebClient"]
    G --> H["HTTP request"]
    H --> I["Discovery + select ServiceInstance"]
    I --> J["Actual instance address"]
    H --> K["Micrometer Observation"]
    K --> L["Metrics / Traces"]
~~~

If you only create a builder via the raw API and attach LoadBalancer, requests may route properly but lack configurations Boot would otherwise prepare. Conversely, if you only use a Boot builder without marking it @LoadBalanced, URLs containing a service name like http://catalog-service may be treated as ordinary DNS hostnames.

## 2. What is inside a Spring Boot-provided builder?

Boot auto-configures builders so applications do not have to assemble every HTTP client component manually. Details depend on client type and version, but typically include:

| Builder | Configuration Boot can supply |
| --- | --- |
| RestTemplateBuilder | HttpMessageConverter, ClientHttpRequestFactory, timeouts, SSL, RestTemplateCustomizer, and request customizers |
| RestClient.Builder | HttpMessageConverter, ClientHttpRequestFactory, timeouts, SSL, RestClientCustomizer |
| WebClient.Builder | ClientHttpConnector, codecs, HTTP resources, WebClientCustomizer, SSL, and observability configuration |

These configurations can come from properties, the classpath, customizer beans, or other auto-configurations. For example, adding an HTTP client implementation to the classpath can affect which request factory/connector is chosen; Jackson configuration can affect converters/codecs; an SSL bundle can supply trust/key material; Actuator can supply observation customizers.

Therefore, Boot builders are integration hubs for many parts of the application. Creating a new builder manually can bypass all of those parts.

### 2.1. Builder and client represent two different phases

A builder is a configuration object. Calling build() creates a concrete HTTP client:

~~~java
RestClient client = builder
        .baseUrl("https://catalog.internal")
        .build();
~~~

Customizers and configurations are applied to the builder before build(). Once a client is built, mutating the builder does not necessarily change clients created earlier.

This is why builder configuration should be completed before building the client, and builder scope should be managed carefully when creating multiple different clients.

## 3. Observability depends on builder configuration

Spring Framework uses Micrometer Observation to record HTTP client activity. An observation can produce:
- Timer/counter metrics for tracking duration and error rates.
- Spans in distributed traces if a tracing system is configured.
- Metadata such as HTTP method, URI template, client name, status, and exceptions.

Spring Boot integrates observations into auto-configured builders. If a client lacks an ObservationRegistry or the corresponding observation customizer, observations can become no-ops and emit no data.

The default metric name commonly used for HTTP clients is:

~~~text
http.client.requests
~~~

Metrics help answer:
- Which service is being called heavily?
- Are request response times increasing?
- How are error rates changing by status/outcome?
- Which request sits inside a slow trace?
- Do errors originate in the client, network, or target service?

Do not rely solely on manual logging to measure latency or trace across services when Boot/Micrometer already provides instrumentation.

### 3.1. Metrics and traces are different

| Data | Purpose | Example |
| --- | --- | --- |
| Metric | Aggregated over time, used for dashboards/alerts | request count, latency, error rate |
| Trace | Follows a single request across multiple components | order-service calls catalog-service then inventory-service |
| Log | Records detailed events at a point in time | timeout when calling catalog |

Observation is an integration layer that produces metrics and/or traces from the same operation. Having metrics does not mean a trace exporter is configured; tracing also requires an appropriate bridge/exporter.

### 3.2. HTTP client observability requires an instrumented builder

Spring Boot Actuator supports instrumentation for:
- RestTemplate created from a configured RestTemplateBuilder.
- RestClient created from a configured RestClient.Builder.
- WebClient created from a configured WebClient.Builder.

If you instantiate clients directly via constructors/raw APIs and skip customizers, the application can lose observations. You can configure ObservationRegistry manually, but then take on responsibility for integrating it properly for each client type.

## 4. Creating a load-balanced RestTemplateBuilder while keeping Boot config

Spring Cloud Commons guides creating a RestTemplateBuilder bean annotated with @LoadBalanced. To preserve configurations and customizers supplied by Boot, use **RestTemplateBuilderConfigurer**.

Example for Spring Boot 3.x:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedRestTemplateConfiguration {

    @Bean
    @LoadBalanced
    RestTemplateBuilder loadBalancedRestTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }
}
~~~

Key points:
1. Create a fresh builder as the base.
2. Call configurer.configure(...) to apply Boot's configuration.
3. Mark the bean with @LoadBalanced so Spring Cloud adds load balancing mechanics.
4. Inject the qualified builder when creating RestTemplate.

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Service
public class CatalogGateway {

    private final RestTemplate restTemplate;

    public CatalogGateway(
            @LoadBalanced RestTemplateBuilder builder) {
        this.restTemplate = builder.build();
    }

    public String getCatalog() {
        return restTemplate.getForObject(
                "http://catalog-service/api/catalog",
                String.class
        );
    }
}
~~~

The example uses the logical service name catalog-service. Spring Cloud LoadBalancer selects a suitable instance and routes the request to that instance's physical address.

### 4.1. What does RestTemplateBuilderConfigurer preserve?

The configurer customizes the builder based on settings provided by Boot auto-configuration. These settings can include:
- Default message converters.
- Request factory matching the HTTP client on the classpath.
- Timeouts and SSL bundles.
- RestTemplateCustomizers.
- Boot's observation customizers.
- Request customizers registered in the context.

Do not create a RestTemplateBuilder manually and assume it is equivalent to Boot's builder. The configurer is needed to reuse baseline configuration.

## 5. Creating a load-balanced RestClient.Builder while keeping Boot config

RestClient is an imperative HTTP client with a fluent API. It fits when the application does not need WebClient's reactive model. Spring Boot provides a prototype RestClient.Builder and configures it with message converters, a request factory, and customizers.

Spring Cloud Commons recommends using **RestClientBuilderConfigurer** when creating a @LoadBalanced builder yourself.

Example for Spring Boot 3.2 and later:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }
}
~~~

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient restClient;

    public InventoryGateway(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String getInventory() {
        return restClient.get()
                .uri("http://inventory-service/api/inventory")
                .retrieve()
                .body(String.class);
    }
}
~~~

The configurer applies Boot settings to the builder before the client is built. Spring Cloud LoadBalancer customization is then applied thanks to the @LoadBalanced qualifier.

### 5.1. Why not use RestClient.create()?

RestClient.create() is a direct client creation API. The created client uses API defaults and does not automatically receive Boot's full auto-configuration/customizers.

If you need:
- HttpMessageConverters managed by Boot.
- ClientHttpRequestFactory chosen by Boot.
- Observation instrumentation.
- SSL bundles.
- RestClientCustomizers in the ApplicationContext.

inject Boot's builder or use RestClientBuilderConfigurer when declaring a load-balanced builder.

## 6. Creating a load-balanced WebClient.Builder and applying WebClientCustomizers

WebClient is a reactive HTTP client suited for Spring WebFlux applications or flows needing non-blocking I/O. Spring Boot provides a WebClient.Builder configured with an appropriate connector, codecs, and HTTP resources.

When creating a custom @LoadBalanced builder, Spring Cloud Commons advises applying **WebClientCustomizer** beans provided by Boot. Use ObjectProvider to retrieve customizers in order:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }
}
~~~

The code:
- Creates a builder.
- Retrieves all WebClientCustomizers.
- Applies them in Spring-managed order.
- Returns a builder containing both Boot settings and the LoadBalancer qualifier.

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PricingGateway {

    private final WebClient webClient;

    public PricingGateway(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getPrice() {
        return webClient.get()
                .uri("http://pricing-service/api/price")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

If using Boot 4.x, WebClientCustomizer moves to the org.springframework.boot.webclient.WebClientCustomizer package. Use the import matching your project's Boot version.

### 6.1. Why use orderedStream()?

Customizers can declare ordering to ensure configuration is applied correctly. Using orderedStream() preserves Spring-managed ordering rather than retrieving a list and applying it arbitrarily.

A customizer can configure:
- Codecs and message readers/writers.
- ObservationRegistry.
- Connectors or HTTP resources.
- Global WebClient settings.
- Behavior added by starters or the application.

Do not skip the customizer list when creating a custom builder if you want to preserve Boot behavior.

## 7. When the application has both regular and load-balanced builders

An application often needs two call styles:

- Calling internal services by logical name, such as http://catalog-service.
- Calling fixed external endpoints, such as https://payment-provider.example.

Do not use a single load-balanced builder for all URLs. Regular builders and load-balanced builders should be registered separately to express intent clearly.

### 7.1. Two RestClient.Builders

Example:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }

    @Bean
    @Primary
    RestClient.Builder restClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }
}
~~~

Consumer using the qualifier:

~~~java
@Service
public class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(
            @LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }
}
~~~

Consumers calling external endpoints can inject the unqualified builder:

~~~java
@Service
public class PaymentProviderGateway {

    private final RestClient client;

    public PaymentProviderGateway(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://payment-provider.example")
                .build();
    }
}
~~~

@Primary placed on the regular builder makes Spring select that bean when injection lacks a qualifier. @LoadBalanced selects the builder meant for service discovery.

### 7.2. Two WebClient.Builders

If declaring multiple WebClient.Builder beans, Boot configuration must be applied to each builder. Example:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientBuildersConfiguration {

    private WebClient.Builder createConfiguredBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        return createConfiguredBuilder(customizerProvider);
    }

    @Bean
    @Primary
    WebClient.Builder webClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        return createConfiguredBuilder(customizerProvider);
    }
}
~~~

Both builders receive Boot customizers; only the @LoadBalanced builder receives additional service instance selection behavior.

### 7.3. Two RestTemplateBuilders

Similar organization:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class RestTemplateBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestTemplateBuilder loadBalancedRestTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }

    @Bean
    @Primary
    RestTemplateBuilder restTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }
}
~~~

If there is no need for both client types, do not create extra builder beans. Keep configuration simple and only create a second builder when the application truly needs to distinguish call paths.

## 8. Meaning of @LoadBalanced and service name URIs

@LoadBalanced is a qualifier for Spring Cloud to identify builder/client beans that need LoadBalancer integration. It does not locate a service registry on its own if discovery/load balancer dependencies are absent.

To use it, the application needs a Spring Cloud LoadBalancer implementation, usually added via starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

When calling through a load-balanced builder, the URI uses a logical service name:

~~~text
http://catalog-service/api/catalog
~~~

LoadBalancer fetches the ServiceInstance list for catalog-service, picks an instance, and replaces the logical host/port with the actual endpoint.

If using a fixed URI:

~~~text
https://catalog.internal/api/catalog
~~~

Spring Cloud LoadBalancer's service name resolution is not needed. A regular builder can be used to call fixed endpoints.

Do not attach @LoadBalanced to a builder just to get metrics. Observability comes from Boot configuration; LoadBalancer is a separate routing mechanism.

## 9. Preserving Boot customizers when adding custom settings

Applications often need to add headers, timeouts, base URLs, or filters. Add settings on top of the configured builder instead of replacing the entire baseline configuration.

RestClient example:

~~~java
@Bean
@LoadBalanced
RestClient.Builder catalogRestClientBuilder(
        RestClientBuilderConfigurer configurer) {

    return configurer.configure(RestClient.builder())
            .defaultHeader("X-Client-Application", "order-service");
}
~~~

RestTemplate example:

~~~java
@Bean
@LoadBalanced
RestTemplateBuilder catalogRestTemplateBuilder(
        RestTemplateBuilderConfigurer configurer) {

    return configurer.configure(new RestTemplateBuilder())
            .connectTimeout(java.time.Duration.ofSeconds(2))
            .readTimeout(java.time.Duration.ofSeconds(5));
}
~~~

The connectTimeout and readTimeout methods in the example are available from Spring Boot 3.4 onward. For Boot 3.2 or 3.3, use setConnectTimeout and setReadTimeout per that version's API; when upgrading Boot, check deprecated methods and migrate to the newer API.

WebClient example:

~~~java
@Bean
@LoadBalanced
WebClient.Builder catalogWebClientBuilder(
        ObjectProvider<WebClientCustomizer> customizerProvider) {

    WebClient.Builder builder = WebClient.builder();

    customizerProvider.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.defaultHeader(
            "X-Client-Application",
            "order-service"
    );
}
~~~

Apply custom settings after Boot customizers have run so it is clear what is default and what is an application override.

### 9.1. Avoid operations that replace the entire configuration

Some APIs have replacement semantics rather than additive semantics:
- RestTemplateBuilder.interceptors(...) replaces the existing interceptor list; additionalInterceptors(...) appends interceptors.
- WebClient.Builder.filters(...) allows direct manipulation of the filter list; calling clear() can wipe filters registered by customizers.
- RestClient.Builder has APIs to add or replace interceptors/request initializers depending on version.

To preserve instrumentation, do not remove observation interceptors/filters supplied by Boot. When adding custom processing, prefer additive APIs and verify the customizer list before/after.

## 10. Stateful builders and avoiding cross-configuration

Not all builders share the same mutability semantics:

| Builder | Property | Safe usage |
| --- | --- | --- |
| RestTemplateBuilder | Immutable; configuration methods return a new builder | Store the resulting builder from each call |
| RestClient.Builder | Stateful; mutating the builder affects subsequent clients built from it | Clone when independent configuration branches are needed |
| WebClient.Builder | Stateful; mutating the builder affects subsequent clients built from it | Clone when independent configuration branches are needed |

WebClient example:

~~~java
WebClient.Builder base = configuredBuilder.clone();

WebClient catalogClient = base.clone()
        .baseUrl("http://catalog-service")
        .build();

WebClient inventoryClient = base.clone()
        .baseUrl("http://inventory-service")
        .build();
~~~

RestClient example:

~~~java
RestClient catalogClient = configuredBuilder.clone()
        .baseUrl("http://catalog-service")
        .build();

RestClient inventoryClient = configuredBuilder.clone()
        .baseUrl("http://inventory-service")
        .build();
~~~

Cloning prevents two clients from accidentally sharing base URLs, default headers, filters, or interceptors added in later steps.

With RestTemplateBuilder, methods typically return a new builder instance so each branch can be kept separate:

~~~java
RestTemplateBuilder base = configuredBuilder;

RestTemplate catalogClient = base
        .rootUri("http://catalog-service")
        .build();

RestTemplate inventoryClient = base
        .rootUri("http://inventory-service")
        .build();
~~~

Do not use a single mutable WebClient.Builder or RestClient.Builder as a global object and repeatedly swap its baseUrl across services.

## 11. Configuring observability and where to inspect results

To view HTTP client metrics, an application usually needs Spring Boot Actuator and an appropriate registry/exporter. Example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Configuration to expose required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
          - prometheus
  observations:
    http:
      client:
        requests:
          name: http.client.requests
~~~

The default metric name is http.client.requests. It can be queried via:

~~~text
GET /actuator/metrics/http.client.requests
~~~

If a Prometheus registry is configured, the scrape endpoint is typically:

~~~text
GET /actuator/prometheus
~~~

The exact endpoint depends on management base path, port, and exposure configuration. Do not expose management endpoints to public networks without appropriate access controls.

### 11.1. What can metrics reveal?

HTTP client observations typically record attributes such as:
- HTTP method.
- URI template.
- Client/host name as determined by instrumentation.
- Status code.
- Outcome.
- Exception/error.
- Request/response exchange duration.

Low-cardinality key values are suitable for metrics because the number of distinct values is bounded. Full URIs or high-cardinality data generally belong in traces instead. Avoid putting user IDs, order IDs, tokens, or query strings with sensitive data into metric tags.

### 11.2. Cross-service tracing

If Micrometer Tracing and an exporter are configured, Observation can create spans for HTTP client exchanges. When trace propagation works, trace IDs and span contexts are transmitted to target services via the corresponding instrumentation/protocol.

When a builder loses its ObservationRegistry or customizers, gaps can appear:
- Server spans still exist.
- Client requests fail to create spans.
- Traces break at the service-call boundary.
- Client request metrics do not appear.

Therefore, when investigating broken traces, check the builder used to build the client before investigating collectors or tracing backends.

## 12. SSL bundles and baseline HTTP configuration

Boot can provide SSL bundles and configure request factories/connectors on builders. When creating a builder manually, failing to apply configurers/customizers can cause clients to miss configured truststores, keystores, or TLS settings.

With RestClient in Spring Boot 3.x, you can use RestClientSsl and apply a bundle:

~~~java
RestClient client = builder
        .baseUrl("https://catalog.internal")
        .apply(ssl.fromBundle("internal-services"))
        .build();
~~~

With WebClient, use WebClientSsl matching the Boot version and connector:

~~~java
WebClient client = builder
        .baseUrl("https://catalog.internal")
        .apply(ssl.fromBundle("internal-services"))
        .build();
~~~

If the builder already receives global SSL configuration via customizers, do not instantiate a new connector/request factory arbitrarily. When overriding a connector, understand that you may replace HTTP resources or TLS settings chosen by Boot.

## 13. Distinguishing observability from LoadBalancer instrumentation

Both mechanisms often appear in the same request but serve different goals:

| Mechanism | Responsibility |
| --- | --- |
| Boot HTTP client observation | Measure duration, status, exceptions, and create spans for HTTP exchanges |
| Spring Cloud LoadBalancer | Select ServiceInstance and resolve service names |
| DiscoveryClient | Fetch instance lists from a registry or discovery implementation |
| HTTP connector/request factory | Open connections, handle TLS, timeouts, and I/O |
| Micrometer registry/exporter | Store and export metrics/traces to observability backends |

LoadBalancer selecting the right instance does not mean the request is instrumented. Conversely, metrics can record a request even if the request did not use discovery when the builder lacks @LoadBalanced.

A complete request typically flows through:

~~~mermaid
sequenceDiagram
    participant App as Calling service
    participant Builder as Load-balanced builder
    participant LB as Spring Cloud LoadBalancer
    participant Discovery as DiscoveryClient
    participant HTTP as HTTP client
    participant Target as Target service
    participant Obs as ObservationRegistry

    App->>Builder: Create client and send request
    Builder->>LB: Resolve service name
    LB->>Discovery: Fetch ServiceInstance
    Discovery-->>LB: Instance list
    LB-->>HTTP: Selected instance address
    HTTP->>Obs: Start/record observation
    HTTP->>Target: HTTP request
    Target-->>HTTP: HTTP response
    HTTP->>Obs: Stop observation
    HTTP-->>App: Result
~~~

The diagram illustrates high-level responsibilities; internal ordering of interceptors/filters and observations depends on the client type and integration version.

## 14. Package and API changes between Spring Boot 3.x and 4.x

When upgrading Boot, several builder/configurer packages were reorganized. Do not copy imports from Boot 3 examples to Boot 4 without checking compilation.

| Component | Spring Boot 3.x | Spring Boot 4.x |
| --- | --- | --- |
| RestTemplateBuilder | org.springframework.boot.web.client.RestTemplateBuilder | org.springframework.boot.restclient.RestTemplateBuilder |
| RestTemplateBuilderConfigurer | org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer | org.springframework.boot.restclient.autoconfigure.RestTemplateBuilderConfigurer |
| RestClientBuilderConfigurer | org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer | org.springframework.boot.restclient.autoconfigure.RestClientBuilderConfigurer |
| WebClientCustomizer | org.springframework.boot.web.reactive.function.client.WebClientCustomizer | org.springframework.boot.webclient.WebClientCustomizer |

Version notes to remember:
- RestClient arrived in Spring Boot 3.2.
- Spring Boot 3.2/3.3/3.4/3.5 use the Boot 3 generation packages.
- Spring Boot 4.0 moves several client APIs and customizers into new packages.
- Spring Framework 7 marks RestTemplate deprecated in favor of RestClient; legacy apps still need a suitable migration roadmap.
- The Spring Cloud release train must be compatible with the Spring Boot generation. Use the Spring Cloud BOM to manage versions; do not pin individual modules arbitrarily.

If the project uses Boot 3.1 or earlier, RestClient is absent; choose RestTemplateBuilder or WebClient.Builder. Always check the actual APIs of your Spring Boot/Spring Cloud BOM in use.

## 15. Practices that easily lose Boot configuration

| Practice | Risk | How to fix |
| --- | --- | --- |
| Instantiating RestTemplate directly with new RestTemplate() | Bypasses Boot's RestTemplateBuilder/customizers | Inject RestTemplateBuilder and build |
| Using RestClient.create() | Misses RestClientBuilderConfigurer/customizers | Inject RestClient.Builder or configure the builder |
| Using WebClient.create() | Bypasses WebClientCustomizers and Boot codec/observation config | Inject WebClient.Builder |
| Creating a new RestClient.Builder without configurer | Loses Boot builder settings like converters, request factory, observation | Use RestClientBuilderConfigurer |
| Creating a new RestTemplateBuilder without configurer | Loses Boot customizers/settings | Use RestTemplateBuilderConfigurer |
| Creating a new WebClient.Builder without applying customizers | Can lose codecs, observations, connector customizations | Apply ordered WebClientCustomizers |
| Clearing all interceptors/filters | Can delete instrumentation or LoadBalancer integration | Use additive APIs and verify order |
| Using a load-balanced builder for a fixed endpoint | Adds unnecessary discovery processing | Use a regular builder |
| Injecting multiple builders without qualifiers | Can grab the wrong builder or fail with ambiguity | Use @LoadBalanced and @Primary |
| Sharing one mutable builder across multiple clients | Later client settings can affect subsequent clients | Clone the builder or create separate builders |

## 16. Testing to prove configuration and observability still work

A test that only verifies a request returns HTTP 200 does not prove the builder kept all its configuration. Verify separately:
1. Builder beans are created with the right qualifiers.
2. Requests go through LoadBalancer when URIs use a service name.
3. Converters/codecs still serialize and deserialize properly.
4. Timeout/SSL/header customizers are still applied.
5. Observations are recorded.
6. Regular clients do not go through LoadBalancer unintentionally.

### 16.1. Verifying metrics

In integration tests, you can use SimpleMeterRegistry or a test MeterRegistry to check after a request:
- The http.client.requests meter exists.
- The count increments after the request.
- Basic tags accurately reflect method/status/outcome.
- Request exceptions are also recorded per instrumentation.

If a test only uses a manually created mock builder, the test may lack Boot's observation customizers. Run at least one test with a real ApplicationContext/auto-configuration.

### 16.2. Verifying traces

If tracing is enabled:
- Send a request from the calling service to the target service.
- Verify a client span is created.
- Verify the trace ID propagates to the target service.
- Verify spans finish even on 4xx/5xx responses or connection errors.
- Confirm there are no gaps caused by clients built from builders bypassing ObservationRegistry.

### 16.3. Verifying load balancing

You can use two test instances with the same service ID and record which instance receives requests. Check:
- Logical URIs use the service name.
- LoadBalancer selects instances per the configured policy.
- Requests do not attempt to call the logical hostname directly via DNS.
- Regular builders calling fixed endpoints are not redirected to service instances.

Tests must use the real Spring Cloud LoadBalancer integration if the goal is to verify @LoadBalanced customization.

## 17. Checklist when creating a load-balanced builder

Before promoting a builder to production, verify:

- [ ] Compatible Spring Cloud LoadBalancer starter is added.
- [ ] Builder is annotated with @LoadBalanced.
- [ ] Builder comes from Boot configuration or runs configurer/customizers.
- [ ] RestTemplateBuilder uses RestTemplateBuilderConfigurer.
- [ ] RestClient.Builder uses RestClientBuilderConfigurer.
- [ ] WebClient.Builder applies WebClientCustomizers in order.
- [ ] @Primary is present on the regular builder if both types coexist.
- [ ] Consumers inject the right builder via @LoadBalanced.
- [ ] URIs use service names when discovery/load balancing is needed.
- [ ] Boot's observation interceptors/filters are not removed.
- [ ] ObservationRegistry and exporters are configured.
- [ ] http.client.requests metrics appear after requests.
- [ ] Traces include client spans and context propagation if tracing is enabled.
- [ ] SSL, timeouts, and codecs/converters are tested.
- [ ] Imports match the Spring Boot version and release train.

## Key takeaways

Spring Boot builders carry essential HTTP client baseline configuration, including message converters/codecs, request factories/connectors, SSL, and observability. When you need a load-balanced builder, combine @LoadBalanced with Boot configuration: RestTemplateBuilderConfigurer for RestTemplateBuilder, RestClientBuilderConfigurer for RestClient.Builder, and ordered WebClientCustomizers for WebClient.Builder. When both regular and load-balanced builders exist, use explicit qualifiers and @Primary for the regular builder. Finally, verify requests routed through LoadBalancer, http.client.requests metrics, and actual traces; do not conclude everything works solely because a request returned success.

## References

- Spring Cloud Commons – Common Abstractions: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Boot 3.4 – Calling REST Services: https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html
- Spring Boot – Calling REST Services: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Boot – Metrics and HTTP Client Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Framework – Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html
