# Using Regular and Service-Name HTTP Clients Together

> **Chapter:** Service Calls  
> **Module:** SPRING_CLOUD_CORE

A Spring Cloud application often calls several types of destinations. Some requests go to external APIs via fixed hostnames or ordinary DNS; other requests go to internal services whose instance addresses come from service discovery. Using the same HTTP client for both cases can make configuration confusing, especially when the client has load balancing by service ID attached.

Spring Cloud lets you create separate HTTP clients: a **regular client** sends requests to URLs/hostnames using ordinary network resolution; a **service-name client** uses Spring Cloud LoadBalancer to turn a service ID into a concrete instance before sending the request. Both can coexist inside one ApplicationContext. This lesson explains how to declare, inject, use, and test both clients in the **SPRING_CLOUD_CORE** module.

## 1. Two types of target addresses in the same application

Before choosing a client, distinguish physical addresses from logical service names.

- **Direct address:** A URL containing a hostname or IP that the HTTP client can resolve via DNS and network routing, such as `https://api.partner.example` or `http://legacy.internal:8080`.
- **Service ID:** A logical name known to the discovery client, such as `catalog-service`. Spring Cloud LoadBalancer fetches the instance list for this name and picks an instance to send the request to.

For example, an `order-service` application might need:

| Need | Target address | Appropriate mechanism |
| --- | --- | --- |
| Call an external payment API | `https://payments.partner.example` | Regular HTTP client |
| Call a legacy system with fixed DNS | `http://legacy.internal:8080` | Regular HTTP client |
| Call catalog with multiple instances | `http://catalog-service` | Client with Spring Cloud LoadBalancer |
| Call inventory by service ID | `http://inventory-service` | Client with Spring Cloud LoadBalancer |

A regular client does not query `DiscoveryClient` to look up instances. A service-ID client needs load balancing integration; without it, the HTTP client treats the service ID as an ordinary DNS hostname and fails to resolve an address.

## 2. Processing flow of the two clients

~~~mermaid
flowchart TB
    A["order-service application"]
    A --> B["Direct WebClient"]
    A --> C["Load-balanced WebClient"]
    B --> D["Fixed URL / hostname"]
    D --> E["DNS and network routing"]
    E --> F["Partner API or legacy service"]
    C --> G["URI containing service ID"]
    G --> H["Spring Cloud LoadBalancer"]
    H --> I["DiscoveryClient fetches instance list"]
    I --> J["Select one ServiceInstance"]
    J --> K["HTTP request to selected host and port"]
~~~

Both branches use HTTP and can use the same WebClient request/response types. The difference lies in how the target address is resolved before sending the request.

With a regular client, the hostname in the URI is resolved by the HTTP connector and OS via DNS/network routing. With a load-balanced client, the hostname in the URI is interpreted as a service ID for Spring Cloud LoadBalancer to locate an instance. Therefore, do not mix up builders or clients between the two purposes.

## 3. Required dependencies

To use WebClient, the application needs the WebFlux starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

To use a service-ID client, you need a Spring Cloud LoadBalancer compatible with your application's release train:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

The application also needs a discovery instance source. That can be a provider like Eureka/Consul or a static list from SimpleDiscoveryClient in an appropriate environment. LoadBalancer uses discovery data to choose instances.

Adding only the WebFlux starter does not automatically resolve URIs containing service IDs. Likewise, simply having DiscoveryClient does not turn every WebClient into a load-balanced client. You must configure builders and dependencies properly.

## 4. Declaring two separate WebClients

A clean approach is to create two differently named beans:

- `partnerWebClient`: calls direct URLs without a load-balancer filter.
- `catalogWebClient`: built from `@LoadBalanced WebClient.Builder` to call service IDs.

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean("partnerWebClient")
    WebClient partnerWebClient() {
        return WebClient.builder()
                .baseUrl("https://api.partner.example")
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

Here, `@LoadBalanced` is the qualifier marking the builder configured for service-name resolution. The `partnerWebClient` bean is built from a regular builder, so its requests do not go through Spring Cloud LoadBalancer.

### 4.1. Why name the beans?

An application may have multiple `WebClient` or `WebClient.Builder` beans. Bean names and qualifiers make intent explicit during injection:

- `partnerWebClient` is for direct URLs.
- `catalogWebClient` is for service IDs.
- `loadBalancedWebClientBuilder` is the builder wired with load balancing mechanics.

Do not rely on bean declaration order or expect Spring to always guess the right builder when multiple candidates share a type. Nor should you use `@Primary` to hide routing differences; inject with qualifiers so intent is clear right at the injection site.

### 4.2. If the application already has Spring Boot's WebClient.Builder

Spring Boot can provide an auto-configured builder. When both a regular builder and a `@LoadBalanced` builder exist, injecting with qualifiers is especially important. If code needs the regular builder, use the corresponding bean/qualifier; if it needs the service-ID builder, use the `@LoadBalanced` qualifier.

Avoid manually adding a load-balancer filter to a shared WebClient used for all targets. Once the filter is attached to a direct client, partner API hostnames get treated as service IDs and requests fail because no instance exists in the registry.

## 5. Calling external APIs with the regular client

The client calling a partner API uses an ordinary URL or base URL:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PartnerPaymentClient {

    private final WebClient webClient;

    public PartnerPaymentClient(
            @Qualifier("partnerWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<PaymentResponse> createPayment(
            PaymentRequest request) {
        return webClient.post()
                .uri("/v1/payments")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
~~~

The bean's `baseUrl` is `https://api.partner.example`, so the relative URI `/v1/payments` is sent to that hostname. DNS, proxies, TLS, and the HTTP connector's network routing handle connectivity.

### 5.1. When the URL is determined at runtime

If the endpoint comes from configuration, you can read the URL when creating the bean or construct the URI in application logic. For example:

~~~yaml
partner:
  payment:
    base-url: https://payments.partner.example
~~~

This value can be bound via `@ConfigurationProperties` or constructor injection. If the endpoint changes at runtime, design a refresh mechanism for the corresponding client; a WebClient already built from an old base URL does not update itself just because Environment changed.

A regular client can still call internal services using stable DNS or an infrastructure load balancer. The distinction is that it does not use Spring Cloud LoadBalancer service IDs.

## 6. Calling internal services by service ID

The client calling catalog uses `catalogWebClient`, which was configured with `@LoadBalanced`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(
            @Qualifier("catalogWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CatalogItem> findById(String id) {
        return webClient.get()
                .uri("http://catalog-service/api/catalog/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }
}
~~~

In the URI above:

- `http` is the request scheme.
- `catalog-service` is the service ID.
- `/api/catalog/{id}` is the API path on the selected instance.

Spring Cloud LoadBalancer retrieves instances of `catalog-service` through the discovery integration, selects an instance per policy, and replaces the service ID with the instance address before WebClient sends the request.

Do not hardcode a specific instance's host/port into a service-ID client. The purpose of discovery is to allow the instance list to change while service-calling code continues using a stable logical name.

### 6.1. Configuring discovery instances

In local development or integration tests, you can use SimpleDiscoveryClient to declare an instance list:

The configuration prefix is `spring.cloud.discovery.client.simple.instances`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9081
              - uri: http://localhost:9082
~~~

When a dynamic discovery provider is present, the list comes from the corresponding registry. Do not configure multiple providers simultaneously without clearly verifying which instance source LoadBalancer actually uses.

### 6.2. Scheme and URI

The example uses `http://catalog-service` so LoadBalancer recognizes the service ID. The actual instance address is obtained from `ServiceInstance`. Verify that instance schemes, ports, and TLS match the environment.

If the service uses HTTPS, URI configuration and the provider's secure metadata must align. Do not merely change the `http` string to `https` while ignoring truststores, certificates, and hostname verification.

## 7. Using both clients in the same service

A business service may need to call both a partner API and an internal catalog. Inject the two separate beans using qualifiers:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class OrderEnrichmentService {

    private final WebClient partnerWebClient;
    private final WebClient catalogWebClient;

    public OrderEnrichmentService(
            @Qualifier("partnerWebClient") WebClient partnerWebClient,
            @Qualifier("catalogWebClient") WebClient catalogWebClient) {
        this.partnerWebClient = partnerWebClient;
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<OrderView> enrich(String productId) {
        Mono<CatalogItem> catalog =
                catalogWebClient.get()
                        .uri("http://catalog-service/api/catalog/{id}", productId)
                        .retrieve()
                        .bodyToMono(CatalogItem.class);

        Mono<PartnerStatus> partner =
                partnerWebClient.get()
                        .uri("/v1/status")
                        .retrieve()
                        .bodyToMono(PartnerStatus.class);

        return Mono.zip(catalog, partner)
                .map(tuple -> new OrderView(tuple.getT1(), tuple.getT2()));
    }
}
~~~

The two requests become two publishers, and `Mono.zip` combines their results once both complete. The example assumes the DTOs and APIs already exist. In production applications, configure timeouts, per-dependency error handling, and determine whether one API is allowed to fail while still returning a partial result.

You do not need two ApplicationContexts or two applications just to use two HTTP routing styles. Two differently configured WebClient beans can coexist in the same context.

## 8. Differences in errors and observability

Because the two clients use different routing mechanisms, troubleshooting differs as well.

| Symptom | Direct client | Service-ID client |
| --- | --- | --- |
| Cannot resolve hostname | Check DNS, hosts, network namespace | Check which instances DiscoveryClient returns and whether instance hosts resolve |
| Connection refused | Check target port, firewall, and target service | Check selected instance, port, and service status |
| Service not found | Usually a DNS or URL error | Check service ID, DiscoveryClient, and LoadBalancer |
| Calls the wrong instance | Check URL/DNS/infrastructure load balancer | Check instance list and LoadBalancer policy |
| TLS handshake error | Check certificates, truststore, and hostname | Check selected instance TLS and scheme/secure metadata |
| Timeout | Check route and latency to the direct host | Check discovery, instance selection, network, and instance latency |

Logs should record the client type, service ID or target hostname at a safe level, request duration, status code, and correlation ID. Do not log tokens, authorization headers, or sensitive payloads.

With a service-ID client, logging the URI before LoadBalancer replacement may only show the service ID. To observe the final host/instance, use version-appropriate LoadBalancer observations, tracing, or hooks rather than guessing from the input URI.

## 9. Timeouts, retries, and connection pools

The two clients can have different operational requirements:

- Partner APIs may need longer timeouts, dedicated proxies, or retries aligned with partner quotas.
- Internal services may use shorter timeouts and bounded retries for transient errors.
- TLS, connection pools, and concurrency limits may differ per dependency.

Do not apply one blanket retry policy to all requests. Retrying a write operation can create duplicate transactions if the API is not idempotent or lacks idempotency key support. Coordinate timeouts, retries, circuit breakers, and error handling according to each API's semantics.

WebClient is designed for reuse. Create shared beans per purpose rather than instantiating a new client per request. If separate connectors or connection pools are needed, configure each WebClient bean individually.

## 10. Testing both client types

Tests should verify not only the response, but also the chosen routing path.

### 10.1. Testing the direct client

Use a mock HTTP server to verify that `partnerWebClient` requests go to the direct URL without invoking discovery. Check method, path, headers, body, timeouts, and response mapping.

### 10.2. Testing the service-ID client

Configure one or more test instances in SimpleDiscoveryClient or a fake DiscoveryClient. Run stub servers on the corresponding ports, call the URI containing the service ID through the `@LoadBalanced` client, and verify requests arrive at instances picked by LoadBalancer.

Points to verify:

- The service ID in the URI matches the configuration key or registry service ID.
- DiscoveryClient returns the expected instance list.
- LoadBalancer chooses instances according to the configured policy.
- When no instance exists, requests fail in an observable and handled manner.
- When an instance is unreachable, retries/fallbacks occur only if configured by the application.

### 10.3. Testing to prevent mixing the two configurations

Write a test containing both beans and verify:

- Requests to the partner URL do not invoke DiscoveryClient.
- Requests to the service ID do use LoadBalancer.
- Injecting beans by qualifier always picks the right client.
- No load-balanced builder bean is mistakenly used for a direct API.

This test catches configuration errors that often go unnoticed when the two clients are only tested in isolation.

## 11. Common pitfalls

1. **Using a load-balanced client for every URL:** external API hostnames get interpreted as service IDs; create a separate direct client.
2. **Using a regular client for a service ID:** the HTTP connector tries to resolve the service ID via DNS; use a `@LoadBalanced` builder.
3. **Missing Spring Cloud LoadBalancer dependency:** the annotation does not supply an implementation if the dependency is absent.
4. **Injecting the wrong builder:** use qualifiers or bean names that state intent clearly.
5. **Using @Primary to mask ambiguity:** inject by qualifier so routing behavior is never chosen by accident.
6. **No discovery provider or instance list:** the service ID cannot be resolved; check DiscoveryClient.
7. **Wrong service ID:** the name in the URI must match the registered or declared name.
8. **Assuming SimpleDiscoveryClient load-balances by itself:** discovery supplies instances; LoadBalancer picks an instance.
9. **Reusing a WebClient with an inappropriate filter:** separate beans by target type and policy.
10. **Applying the same timeout/retry settings to every dependency:** design per each API's SLA and semantics.
11. **Failing to check TLS on selected instances:** verify scheme, certificates, and hostnames.
12. **Creating a WebClient per request:** reuse beans and connection pools.

## 12. Design workflow in a Spring Cloud application

When a service needs to call both direct endpoints and internal services:

1. List each dependency and determine whether its address is a direct URL/hostname or a service ID.
2. Create a direct WebClient for partner APIs or stable DNS endpoints.
3. Create a `@LoadBalanced` builder for service-ID requests.
4. Name beans clearly and use `@Qualifier` in constructor injection.
5. Configure compatible DiscoveryClient/providers and Spring Cloud LoadBalancer.
6. Set timeouts, TLS, retries, and connection pools per dependency type.
7. Test direct routing and service-name routing separately.
8. Test both no-instance scenarios and unresolvable-hostname scenarios.
9. Record enough logs/traces to distinguish direct DNS errors from discovery/load-balancing errors.
10. Audit that no load-balanced client is used unintentionally for external APIs.

**Key takeaway:** A regular HTTP client sends requests to hostnames/URLs resolved through DNS and network routing. A service-name client uses `@LoadBalanced WebClient.Builder` so Spring Cloud LoadBalancer fetches instances from DiscoveryClient and picks targets for requests. Both clients can coexist in one ApplicationContext; separate beans and inject by qualifier so routing behavior, timeouts, and operational policies for each dependency remain explicit in **SPRING_CLOUD_CORE**.