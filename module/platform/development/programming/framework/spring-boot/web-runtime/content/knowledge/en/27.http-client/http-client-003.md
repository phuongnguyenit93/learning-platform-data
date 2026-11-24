# Spring Boot–Managed Builders and the Customizations They Apply

**Module:** Spring Boot - web-runtime  
**Parent topic:** HTTP client

## 1. The Problem: Why Does the Same HTTP Client Have Different Configurations?

A Spring Boot service calls external APIs over HTTP. The team wants every outbound request to include tracing/metrics, sensible timeouts, consistent message converters/codecs, and an identifying header. Yet the observed behavior can be contradictory:

- One component receives **RestClient.Builder** from Spring, builds a client, and gets every system-added header.
- Another component calls **RestClient.create(...)**, sends requests fine, but lacks the headers or instrumentation the app configured.
- One place injects **WebClient.Builder**, another calls **WebClient.create()**; the two clients can end up using different connectors, codecs, or customizers.
- One service uses **RestTemplateBuilder** and sees changes from **RestTemplateCustomizer**, while **new RestTemplate()** has none of those customizations.
- A **@Bean RestTemplateBuilder** configuration is written to add a timeout, but accidentally replaces Spring Boot's builder and loses default customizers.

The core issue is not that Spring Boot automatically enforces policies on **every HTTP client object in the JVM**. Spring Boot provides **auto-configured builders**; only clients built **through the right builder** receive the corresponding configuration. **Customizer registration**, **builder scope**, **customization order**, and **how the client is created** determine the final configuration.

This lesson focuses on three key Spring Boot **3.3.x** groups with Spring Framework 6.1 and Java 17+:

1. **RestClient.Builder** → imperative/synchronous **RestClient**; typically the choice for new blocking flows.
2. **RestTemplateBuilder** → imperative/synchronous **RestTemplate**, useful when maintaining apps that already use RestTemplate.
3. **WebClient.Builder** → reactive **WebClient**, non-blocking I/O when used properly in a Reactor pipeline.

Understand what Spring Boot manages, what customizations get applied, what gets lost when creating a builder yourself, how to test, and the boundary with the HTTP server.

## 2. Spring Boot Manages Builders, Not Every Client

The official **Spring Boot 3.3 – Calling REST Services** documentation states:

| Client API | What does Spring Boot auto-create when dependencies match? | Builder characteristics | Corresponding customizer |
| --- | --- | --- | --- |
| **RestClient** | Configured **RestClient.Builder**, **prototype** scope | **Stateful**: mutating a builder affects subsequent clients built from that same builder | **RestClientCustomizer** |
| **RestTemplate** | **RestTemplateBuilder**, no default shared **RestTemplate** bean | **Immutable/functional** style: each configuration method returns a new builder | **RestTemplateCustomizer** |
| **WebClient** | Configured **WebClient.Builder**, **prototype** scope | **Stateful**: mutating a builder affects subsequent clients built from that same builder | **WebClientCustomizer** |

**Spring Boot does not automatically create a singleton RestTemplate for all services to share.** You inject **RestTemplateBuilder** and build a RestTemplate configured for the consuming component. Likewise, Boot creates builders for RestClient/WebClient; if a project wants a dedicated client with a specific base URL and authentication, create that client in **@Configuration** using the injected builder.

**Prototype builder** does not mean calling **build()** resets the builder each time. It means Spring can supply **a fresh builder instance whenever the bean is requested from the container**, such as at different injection points. If a singleton holds one `WebClient.Builder` and changes `baseUrl` repeatedly, subsequent builds from that builder still retain earlier mutations. Conversely, `RestTemplateBuilder` returns a new builder object for each configuration step, reducing shared-mutation risk.

**The final client is not necessarily a Boot-managed bean.** You can create:

~~~java
RestClient client = injectedRestClientBuilder
        .baseUrl("https://service.example.test")
        .build();
~~~

This client is a Java object built by your code. If you want to inject **RestClient** via `@Autowired` elsewhere, register it as a **@Bean RestClient** or wrap it in a dedicated service. Do not assume that because Spring Boot provides a `RestClient.Builder` bean, there is automatically a single `RestClient` bean.

## 3. Auto-Configuration Pipeline and Where Customizers Intervene

A practical mental model:

~~~text
Dependencies + Spring Boot auto-configuration
     |
     +--> HTTP client/request factory/connector detection
     +--> HttpMessageConverters / Codec configuration
     +--> SSL bundle, resource factories if configured
     +--> Observation/metrics/tracing hooks if present
     |
     v
Spring-managed Builder
     |
     +--> RestClientCustomizer / WebClientCustomizer (on the builder)
     +--> RestTemplateCustomizer (on RestTemplate when built)
     |
     v
Local customizations in service/@Bean
     |  baseUrl, default headers, filters, timeouts...
     v
.build()
     |
     v
Outbound HTTP client -> Request -> Response
~~~

**Which layer configures what?**

- **Spring Framework** defines the RestClient, RestTemplate, and WebClient APIs along with their HTTP transports.
- **Spring Boot auto-configuration** picks sensible defaults based on the classpath and existing beans and wires them into the builder—especially converters/codecs and the appropriate HTTP transport.
- **Customizer beans** let internal modules or libraries apply shared rules to Boot-created builders/clients.
- **Local builder calls** let each upstream service set its own base URL, authentication, timeouts, or headers.
- **The built client object** is used to execute requests; mutating a builder after a client is built **is not** a mechanism for reconfiguring all existing clients.

The design goal is **configuring once at the right scope**, rather than duplicating interceptors and timeouts in every service. Still, avoid placing a single upstream's secrets in a global customizer, because it can apply to **every client** in the same API family.

## 4. Boot-Managed RestClient.Builder

**RestClient** was introduced in Spring Framework 6.1 as a fluent **imperative** API. In Spring Boot 3.3, when REST client support is present, Boot creates a **prototype RestClient.Builder bean** configured with **HttpMessageConverters** and an appropriate **ClientHttpRequestFactory**.

Common usage inside a service:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Caller", "orders")
                .build();
    }

    public ProductView findById(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductView.class);
    }

    public record ProductView(long id, String name) {}
}
~~~

This is an **illustrative service** and does not run standalone because **catalog.example.test** is an example domain and requires a Spring Boot project with a matching endpoint. In the runnable example in Section 9, we call a localhost endpoint to inspect actual headers.

Key points:

- **RestClient.Builder** is constructor-injected by Spring. You add the **local** `baseUrl` and header for this client.
- **.build()** creates a reusable RestClient; do not build a new client per request.
- **.retrieve().body(ProductView.class)** decodes JSON using appropriate converters when the server returns a valid body.
- Error HTTP statuses (4xx/5xx) throw exceptions under `retrieve` semantics; for custom error mapping, use **onStatus(...)** or handle exceptions per your API contract.
- The example URL must be replaced by real environment configuration in production; never hardcode secrets or uncontrolled hosts.

### RestClientCustomizer for Application-Wide Customization

A bean:

~~~java
package com.example.catalog;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogRestClientCustomization {

    @Bean
    RestClientCustomizer addClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Platform-Client", "spring-boot-service");
    }
}
~~~

Spring Boot discovers **RestClientCustomizer** beans and applies them to **Boot's auto-configured RestClient.Builder**. As a result, RestClients built from those builders carry the default header above unless overridden by a specific request or configuration.

**Not every RestClient on the classpath receives the customizer.** For example:

~~~java
// Creating a client via Spring Framework's static factory:
RestClient raw = RestClient.create("https://example.test");
~~~

This path **bypasses Spring Boot's auto-configured builder**, so it does not inherit **RestClientCustomizer** or Boot auto-configuration/observation. It is still a valid Spring Framework RestClient with its own defaults; the issue is that **it diverges from your application's expected setup**.

**RestClient.Builder is stateful.** If a singleton holds one builder and calls **baseUrl(A).build()**, then **baseUrl(B).build()**, it may inadvertently carry over settings onto client B. When creating multiple distinct clients in the same scope, call **builder.clone()** before applying separate settings:

~~~java
RestClient first = builder.clone()
        .baseUrl("https://service-a.example.test").build();
RestClient second = builder.clone()
        .baseUrl("https://service-b.example.test").build();
~~~

This snippet belongs **inside a constructor or factory that has already received a builder**, not as a standalone Java class. Cloning isolates mutations while preserving the builder's original/Boot defaults at the moment of cloning.

## 5. Boot-Managed WebClient.Builder

**WebClient** uses a fluent reactive API with **Mono**/**Flux**, typically backed by Reactor Netty when the WebFlux starter is present. Spring Boot 3.3 creates a configured **prototype WebClient.Builder**, supporting **ClientHttpConnector** selection, HTTP codec alignment, and sharing HTTP resources appropriately with a reactive server.

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogClient {

    private final WebClient client;

    public ReactiveCatalogClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Caller", "reactive-orders")
                .build();
    }

    public Mono<ProductView> findById(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductView.class);
    }

    public record ProductView(long id, String name) {}
}
~~~

This is also an **API illustration**, not a complete application. Using WebClient requires **spring-webflux** or **spring-boot-starter-webflux**, even when the primary server runs Servlet Spring MVC. Adding WebFlux just to use WebClient **does not by default switch an MVC server to Reactive WebFlux**; Boot generally chooses Servlet when both `spring-webmvc` and `spring-webflux` are present.

### WebClientCustomizer

~~~java
package com.example.catalog;

import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientCustomization {

    @Bean
    WebClientCustomizer clientHeader() {
        return builder -> builder.defaultHeader(
                "X-Platform-Client", "reactive-service");
    }
}
~~~

Just like RestClient, **WebClientCustomizer** applies to **Boot-configured WebClient.Builder** instances and does not automatically modify a WebClient created manually via **WebClient.create()** or **WebClient.builder()**.

**WebClient.Builder is also stateful.** Inject it into components that need distinct setup; when building multiple clients from the same builder, clone it:

~~~java
WebClient blue = builder.clone()
        .baseUrl("https://blue.example.test").build();
WebClient green = builder.clone()
        .baseUrl("https://green.example.test").build();
~~~

Important note: **a reactive API does not guarantee all processing is fully non-blocking**. Calling **.block()** on a Netty event loop or running heavy blocking work inside a reactive pipeline can stall threads; avoid that in WebFlux apps. In MVC apps, WebClient can be used for async calls and controllers can return **Mono** because MVC supports reactive return types; do not mistake having WebClient for making an MVC server end-to-end non-blocking.

## 6. RestTemplateBuilder and RestTemplateCustomizer

Spring Boot **does not auto-provide a shared RestTemplate bean**, because instances typically need different settings per upstream. Instead, it creates **RestTemplateBuilder** with appropriate converters and **ClientHttpRequestFactory**.

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyCatalogClient {
    private final RestTemplate template;

    public LegacyCatalogClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("https://catalog.example.test")
                .setConnectTimeout(Duration.ofSeconds(2))
                .setReadTimeout(Duration.ofSeconds(5))
                .build();
    }

    public ProductView findById(long id) {
        return template.getForObject(
                "/products/{id}", ProductView.class, id);
    }

    public record ProductView(long id, String name) {}
}
~~~

This snippet is meant for an app with a Spring-injected builder and a real upstream. **rootUri** applies only to matching URI templates, typically URI paths starting with **/**; it does not share identical semantics with `baseUrl` on RestClient/WebClient in every case.

**Key difference:** each call such as **builder.rootUri(...)** or **setReadTimeout(...)** returns **a new RestTemplateBuilder**; the original builder is not mutated. Therefore:

~~~java
RestTemplateBuilder configured = builder.setReadTimeout(
        Duration.ofSeconds(5));

// builder != configured as object instances.
// Building from the original builder does not automatically inherit readTimeout=5s.
RestTemplate oldPolicy = builder.build();
RestTemplate newPolicy = configured.build();
~~~

This code snippet belongs inside a component that already received **builder**, not as a standalone program. It highlights the difference between a **functional builder** and a **stateful builder**.

### RestTemplateCustomizer Runs at a Different Time

**RestTemplateCustomizer** receives the **RestTemplate object** after the builder configures it—for example, to add an interceptor:

~~~java
package com.example.catalog;

import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyClientCustomization {

    @Bean
    RestTemplateCustomizer identifyOutgoingCalls() {
        return template -> template.getInterceptors().add(
                (request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Platform-Client", "legacy-template");
                    return execution.execute(request, body);
                });
    }
}
~~~

The customizer is registered on the **auto-configured RestTemplateBuilder**, then applied when **build()** constructs the RestTemplate. A RestTemplate created with **new RestTemplate()** does not automatically receive it. You can also customize **message converters, error handlers, request factories, and interceptors**, but understand each step's impact; do not replace the entire converter list when you only need to add one converter.

**Be careful with replace vs. additive methods:**

- **RestTemplateBuilder.customizers(...)** replaces the list of customizers already configured on the builder.
- **RestTemplateBuilder.additionalCustomizers(...)** adds customizers without clearing earlier ones.
- **RestTemplateBuilder.messageConverters(...)** replaces the converter list; **additionalMessageConverters(...)** appends to it.
- Likewise, **interceptors(...)** and **additionalInterceptors(...)** have different semantics.

A **replace** call can strip away Boot/Actuator customizers even when you only meant to add an interceptor. When adding behavior, prefer **additional...** methods or register a customizer bean at the appropriate scope.

## 7. Local vs. Global Customization: Where Does Each Setting Belong?

| Policy type | Where to configure | Reason |
| --- | --- | --- |
| Upstream catalog base URL | Builder in **@Bean CatalogRestClient** or dedicated service | Specific to catalog; must not apply to billing/payments. |
| Shared **X-Service-Name** header | **RestClientCustomizer**, **WebClientCustomizer**, or RestTemplateCustomizer by API | Safe to share across all outgoing requests needing caller identity. |
| Authorization header for one upstream | Dedicated client, dedicated request filter, or per-upstream credential provider | Prevents leaking tokens to other hostnames. |
| Upstream-specific connect/read/response timeouts | Per-client builder/request factory/connector | Depends on upstream SLA and retry policy. |
| HTTP client metrics/tracing | Use Boot-configured builders with Actuator/observation enabled | Avoids missing instrumentation caused by static factories. |
| Shared JSON converters/codecs | Auto-configuration and controlled customizers | Standardizes serialization without breaking defaults. |
| Proxy for one upstream only | Dedicated client request factory/connector | Avoids routing all outbound traffic through a proxy. |
| mTLS SSL trust bundle for internal upstream | Per-client SSL bundle; never disable certificate verification | Keys/certs and trust policies differ per target. |
| Outbound header logging | Filter/interceptor with redaction and allowlist | Never log Authorization/Cookie/PII or sensitive payloads. |

**Global customizers are not "more is always better".** Adding a default `Authorization` header globally can send that token to any host called by clients sharing that builder. That is a serious credential-leakage flaw; keep credentials inside clients scoped to **a single target/trust boundary**.

**Local customization** does not erase global customizers as long as you keep using the Boot-managed builder. However, if a local call replaces the entire connector, converters, or filters, it may inadvertently override part of the platform baseline. Write integration tests to verify the effective behavior.

### Customizer Ordering

Multiple customizer beans can coexist. Spring supports **@Order** or **Ordered** for certain bean collections; exact impact depends on the auto-configuration mechanism and the API the customizer invokes.

If two customizers both call **defaultHeader("X-Flag", ...)**, do not guess "customizer B always wins", as builder **merge/replace semantics** and order precedence can vary. Instead of fighting over the same setting, assign **one clear owner**; when ordering is needed, use explicit ordering and integration-test actual requests.

## 8. What Happens When You Create a Builder or Client Manually?

This is one of the easiest areas to get wrong.

| Creation approach | Receives Boot auto-configuration/customizers? | Notes |
| --- | --- | --- |
| Inject **RestClient.Builder** and build | **Yes**, when corresponding auto-configuration is active | Preferred approach for RestClient. |
| Call **RestClient.create()** or **RestClient.builder()** manually | **Not automatically** | Spring Framework builds a builder/client with its own defaults, skipping Boot-managed customizers. |
| Inject **WebClient.Builder** and build | **Yes** | Preferred approach for WebClient. |
| Call **WebClient.create()** or **WebClient.builder()** manually | **Not automatically** | May bypass Boot codec/resource/observability customizers. |
| Inject **RestTemplateBuilder** and build | **Yes** | Runs RestTemplateCustomizers from Boot's builder. |
| Call **new RestTemplate()** or **new RestTemplateBuilder()** manually | **Not automatically** | Does not inherit Boot customizers unless applied manually. |
| Define a custom **@Bean RestTemplateBuilder** without configurer | **Can cause Boot to back off** and drop Boot customizers | Use `RestTemplateBuilderConfigurer` when replacing the builder is truly necessary. |
| Define a custom **@Bean RestClient.Builder** without configurer | **Can replace** the auto-configured prototype builder and lose Boot defaults | Use `RestClientBuilderConfigurer` per Spring Boot 3.3 when needed. |
| Define a completely new **@Bean WebClient.Builder** | **Can cause auto-config to back off**, lacking customizers automatically | Prefer injecting Boot's builder; or intentionally apply `WebClientCustomizer`s. |

**Boot auto-configuration is conditional**: which beans exist depends on the classpath, properties, and user-defined beans. Do not assume every project has all three builders. For example, **WebClient.Builder** requires the corresponding WebFlux/HTTP client modules on the classpath.

### When You Must Replace the RestTemplateBuilder Bean

The snippet below is an **advanced alternative**—do not place it inside the Section 9 demo (which uses the default builder). It belongs in **a separate Java @Configuration class** with proper imports:

~~~java
package com.example.alternative;

import java.time.Duration;

import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomRestTemplateBuilderConfiguration {
    @Bean
    RestTemplateBuilder restTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {
        return configurer.configure(new RestTemplateBuilder())
                .setConnectTimeout(Duration.ofSeconds(3))
                .setReadTimeout(Duration.ofSeconds(5));
    }
}
~~~

**RestTemplateBuilderConfigurer** is how Spring Boot 3.3 lets you **preserve compatible defaults/customizers** before adding timeout policies, instead of returning an empty `new RestTemplateBuilder()` that inherits nothing. In Boot 3.3, `setConnectTimeout`/`setReadTimeout` use the **set** prefix; do not copy syntax from other Boot versions without checking the API.

### When You Must Replace the RestClient.Builder Bean

Spring Boot 3.3's **RestClientBuilderConfigurer** exposes **configure(RestClient.Builder)** to apply Boot defaults. Alternative prototype configuration example (place in **a separate project**, not alongside the demo):

~~~java
package com.example.alternative;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CustomRestClientBuilderConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    RestClient.Builder restClientBuilder(
            RestClientBuilderConfigurer configurer) {
        return configurer.configure(RestClient.builder())
                .defaultHeader("X-Platform", "learning");
    }
}
~~~

Set **@Scope(PROTOTYPE)** to preserve isolation across injection points like Boot's default builder. Creating a singleton stateful builder and mutating `baseUrl` in multiple places can cross-contaminate upstream configs.

**There is no identical WebClientBuilderConfigurer** with the exact same API across all versions by default. If you replace the auto-configured `WebClient.Builder`, you must manually review and preserve **WebClientCustomizer** beans, codec/connector/resource setup, and observations; injecting Boot's builder remains the safer option.

## 9. Runnable Demo: Three Clients Calling the Same Endpoint

This demo verifies the difference between **global customizers** and **local customization** across **RestClient**, **RestTemplate**, and **WebClient**.

### 9.1. Project and Dependencies

Uses Spring Boot **3.3.13**, Java 17+, and Maven. Both **spring-boot-starter-web** and **spring-boot-starter-webflux** are included so all APIs are available; when both are on the classpath, Boot defaults to **Servlet Spring MVC/Tomcat**, and WebFlux provides `WebClient`.

**spring-boot-starter-actuator** is also included so HTTP client metrics can be observed when the endpoint is exposed. This is **optional** for HTTP client builder mechanics and not required in every project.

Structure:

~~~text
managed-http-clients/
  pom.xml
  src/main/
    java/com/example/clients/
      ManagedClientsApplication.java
      OutboundClientConfiguration.java
    resources/
      application.properties
  src/test/
    java/com/example/clients/
      ManagedClientBuilderTests.java
~~~

Create **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>managed-http-clients</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=managed-http-clients

# Only for observing metrics on a learning machine.
management.endpoints.web.exposure.include=health,metrics
~~~

**Important:** in the demo, the HTTP clients call back to the same server on `localhost:8080` to avoid external API dependencies. In production, replace localhost with URLs from environment configuration, set up DNS/TLS, and isolate access permissions.

Never expose all Actuator endpoints to the public internet. If enabling the **metrics** endpoint in production, protect access or restrict it to an internal monitoring channel.

### 9.3. Main Class, Remote Endpoint, and Gateway Endpoints

Create **src/main/java/com/example/clients/ManagedClientsApplication.java**:

~~~java
package com.example.clients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ManagedClientsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagedClientsApplication.class, args);
    }
}

// DTO handled by JSON serializer/deserializer for all three clients.
record EchoResponse(String global, String local) {}

@RestController
class DownstreamEchoController {

    @GetMapping("/remote/echo")
    EchoResponse echo(
            @RequestHeader(value = "X-Global", defaultValue = "missing")
                    String global,
            @RequestHeader(value = "X-Local", defaultValue = "missing")
                    String local) {
        return new EchoResponse(global, local);
    }
}

@RestController
class GatewayController {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;

    GatewayController(RestClient restClient,
            RestTemplate restTemplate,
            WebClient webClient) {
        this.restClient = restClient;
        this.restTemplate = restTemplate;
        this.webClient = webClient;
    }

    @GetMapping("/gateway/restclient")
    EchoResponse restClientEcho() {
        return restClient.get()
                .uri("/remote/echo")
                .retrieve()
                .body(EchoResponse.class);
    }

    @GetMapping("/gateway/resttemplate")
    EchoResponse restTemplateEcho() {
        return restTemplate.getForObject(
                "/remote/echo", EchoResponse.class);
    }

    @GetMapping("/gateway/webclient")
    Mono<EchoResponse> webClientEcho() {
        return webClient.get()
                .uri("/remote/echo")
                .retrieve()
                .bodyToMono(EchoResponse.class);
    }
}
~~~

**Runnable notes:**

- Only **ManagedClientsApplication** is a public top-level class, matching the filename. Package-private controllers and records in the same package are scanned/read by Boot on Java 17.
- **DownstreamEchoController** returns the exact header values **actually received** by the server. This is an observable check, not guessing at builder config.
- **GatewayController** uses the clients built from Boot-managed builders. The RestClient and RestTemplate endpoints run synchronously. The WebClient endpoint returns **Mono<EchoResponse>**, which MVC handles with a matching `ReactiveAdapterRegistry`; this does not turn the MVC server into WebFlux.
- The demo calls an endpoint **on the same Tomcat :8080** for easy testing. Under high concurrency, calling the same server consumes extra worker threads; **never use this loopback topology in production**.
- If a real upstream returns 404/500 or times out, `retrieve`/`getForObject` will throw exceptions; production systems need explicit error handling.

### 9.4. Configuration: Three Global Customizers and Three Local Clients

Create **src/main/java/com/example/clients/OutboundClientConfiguration.java**:

~~~java
package com.example.clients;

import java.time.Duration;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfiguration {

    // GLOBAL: applies to Spring Boot-managed RestClient.Builder.
    @Bean
    RestClientCustomizer restClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Global", "restclient-global");
    }

    // GLOBAL: applies to RestTemplate built via RestTemplateBuilder.
    @Bean
    RestTemplateCustomizer restTemplateHeader() {
        return template -> template.getInterceptors().add(
                (request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Global", "resttemplate-global");
                    return execution.execute(request, body);
                });
    }

    // GLOBAL: applies to Spring Boot-managed WebClient.Builder.
    @Bean
    WebClientCustomizer webClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Global", "webclient-global");
    }

    // LOCAL: only this RestClient gets this baseUrl/X-Local.
    @Bean
    RestClient restClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8080")
                .defaultHeader("X-Local", "restclient-local")
                .build();
    }

    // LOCAL: timeout, rootUri, X-Local for this RestTemplate.
    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://localhost:8080")
                .setConnectTimeout(Duration.ofSeconds(2))
                .setReadTimeout(Duration.ofSeconds(5))
                .defaultHeader("X-Local", "resttemplate-local")
                .build();
    }

    // LOCAL: baseUrl and X-Local only for this WebClient.
    @Bean
    WebClient webClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8080")
                .defaultHeader("X-Local", "webclient-local")
                .build();
    }
}
~~~

**This configuration demonstrates two real layers:**

- **X-Global** belongs to the respective customizers; Boot applies it to clients built from Boot-managed builders.
- **X-Local** belongs only to the specific gateway client and does not leak to other RestClient/WebClient/RestTemplate beans.
- RestTemplate uses an interceptor because **RestTemplateCustomizer** operates on the RestTemplate after builder configuration, rather than having the same `RestClient.Builder` API.
- RestTemplate's timeout is local and does not alter WebClient or RestClient. **HTTP client timeouts are not the same property as server connection timeout.**
- For WebClient, Boot's builder can share Reactor Netty HTTP resources and apply appropriate codecs/observation; calling **WebClient.create()** manually misses those customizations.

### 9.5. Run and Inspect the Output

From the directory containing **pom.xml**:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Once the server is listening on port 8080, call from another terminal:

~~~bash
curl -fsS http://localhost:8080/gateway/restclient
curl -fsS http://localhost:8080/gateway/resttemplate
curl -fsS http://localhost:8080/gateway/webclient
~~~

Expected logical JSON bodies (JSON field order may vary):

~~~json
{"global":"restclient-global","local":"restclient-local"}
~~~

~~~json
{"global":"resttemplate-global","local":"resttemplate-local"}
~~~

~~~json
{"global":"webclient-global","local":"webclient-local"}
~~~

When all three responses match their respective values, we have confirmed:

1. RestClient receives its own **RestClientCustomizer**.
2. RestTemplate built from the builder receives its own **RestTemplateCustomizer**.
3. WebClient receives its own **WebClientCustomizer**.
4. **Local settings** apply independently per client.

Do not assume a successful header test proves observation, retries, TLS, or pooling are all properly configured: the header test proves only **the customizations actually tested**.

### 9.6. Observing Actuator HTTP Client Metrics

Because the demo includes Actuator and exposes **metrics** on localhost, after a few HTTP calls you can run:

~~~bash
curl -fsS http://localhost:8080/actuator/metrics/http.client.requests
~~~

In Spring Boot 3.3, **HTTP client observation/metrics** for RestClient, RestTemplate, and WebClient are supported when clients are built through the **auto-configured builders**. With matching Actuator/Micrometer setup, the metric is typically named **http.client.requests**.

Measurement counts and tags depend on executed requests, auto-configuration, metric registry, and tracing/observation context. If the metric name does not appear, check the Actuator dependency, endpoint exposure, builder source, and observation settings; do not assume the metric is guaranteed in every setup.

**HTTP client metrics do not replace error logs, distributed tracing, or request header verification.** The goal here is simply to highlight one benefit of building clients from Boot-managed builders instead of static factories.

## 10. Integration Testing Without Calling External Services

Rather than merely checking that the context contains beans, you can verify the **actual request each client intends to send**. Spring test provides **MockRestServiceServer** to mock HTTP requests for RestClient/RestTemplate; WebClient can be tested via an **ExchangeFunction stub**.

Create **src/test/java/com/example/clients/ManagedClientBuilderTests.java**:

~~~java
package com.example.clients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@SpringBootTest
class ManagedClientBuilderTests {

    @Autowired
    ApplicationContext context;

    @Test
    void restClientAndWebClientBuildersArePrototype() {
        RestClient.Builder firstRest =
                context.getBean(RestClient.Builder.class);
        RestClient.Builder secondRest =
                context.getBean(RestClient.Builder.class);
        assertNotSame(firstRest, secondRest);

        WebClient.Builder firstWeb =
                context.getBean(WebClient.Builder.class);
        WebClient.Builder secondWeb =
                context.getBean(WebClient.Builder.class);
        assertNotSame(firstWeb, secondWeb);
    }

    @Test
    void restTemplateBuilderChangesReturnNewBuilder() {
        RestTemplateBuilder original =
                context.getBean(RestTemplateBuilder.class);
        RestTemplateBuilder changed =
                original.setReadTimeout(Duration.ofSeconds(3));
        assertNotSame(original, changed);
    }

    @Test
    void restClientCustomizerIsApplied() {
        RestClient.Builder builder =
                context.getBean(RestClient.Builder.class);

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();
        RestClient client = builder
                .baseUrl("https://upstream.example.test")
                .build();

        server.expect(requestTo("https://upstream.example.test/ping"))
                .andExpect(header("X-Global", "restclient-global"))
                .andRespond(withSuccess(
                        "{\"global\":\"ok\",\"local\":\"test\"}",
                        MediaType.APPLICATION_JSON));

        EchoResponse body = client.get()
                .uri("/ping")
                .retrieve()
                .body(EchoResponse.class);

        assertEquals("ok", body.global());
        server.verify();
    }

    @Test
    void restTemplateCustomizerIsApplied() {
        RestTemplate template = context
                .getBean(RestTemplateBuilder.class)
                .rootUri("https://upstream.example.test")
                .build();

        MockRestServiceServer server =
                MockRestServiceServer.createServer(template);

        server.expect(requestTo("https://upstream.example.test/ping"))
                .andExpect(header("X-Global", "resttemplate-global"))
                .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

        String result = template.getForObject("/ping", String.class);
        assertEquals("ok", result);
        server.verify();
    }

    @Test
    void webClientCustomizerIsApplied() {
        WebClient.Builder builder =
                context.getBean(WebClient.Builder.class);

        WebClient client = builder
                .exchangeFunction(request -> {
                    assertEquals("webclient-global",
                            request.headers().getFirst("X-Global"));
                    return Mono.just(ClientResponse.create(HttpStatus.OK)
                            .header(HttpHeaders.CONTENT_TYPE,
                                    MediaType.TEXT_PLAIN_VALUE)
                            .body("ok")
                            .build());
                })
                .build();

        String body = client.get()
                .uri("https://upstream.example.test/ping")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        assertEquals("ok", body);
    }
}
~~~

**Test explanation:**

- **@SpringBootTest** starts the application context with the active builder/customizer beans; because no real HTTP server is started, these tests do not call the gateway beans built for localhost 8080.
- **RestClient.Builder/WebClient.Builder** are fetched twice from the Spring context to verify prototype scope. A singleton that already injected a builder keeps its own instance; prototype scope **does not** automatically reset an injected field after injection.
- **RestTemplateBuilder** returns a distinct instance when setting a read timeout.
- **MockRestServiceServer.bindTo(RestClient.Builder)** and **createServer(RestTemplate)** use a mock request factory to assert outbound headers without sending requests to the example hostname.
- **WebClient.Builder.exchangeFunction(...)** creates a stub receiving **ClientRequest**, directly verifying the customizer-added header without network I/O.
- **block(Duration...)** is used only in the **JUnit test** to retrieve the result; in reactive production paths, avoid blocking the Netty event loop.
- You can extend tests to verify **local config** and error handling, while the global header already has a dedicated check per API.

If you need to test **timeouts, DNS, TLS, pooling, proxies, or real streaming**, mock tests are insufficient: use a real test server with appropriate latency/failure injection rather than guessing connector behavior from mock responses.

## 11. SSL Bundles, Timeouts, Connectors, and Request Factories

Spring Boot 3.3 provides **SSL bundles** to separate trust material and client certificate config from code. For Boot-auto-configured RestClient or WebClient, inject **RestClientSsl** or **WebClientSsl** and call **builder.apply(ssl.fromBundle("..."))** once the bundle is configured.

Local example for RestClient 3.3 (placed in a service receiving both dependencies, **not a standalone program**):

~~~java
RestClient secureClient = restClientBuilder
        .baseUrl("https://internal.example.test")
        .apply(restClientSsl.fromBundle("internal"))
        .build();
~~~

In Spring Boot 3.3, **RestClientSsl** resides in **org.springframework.boot.autoconfigure.web.client**, and **WebClientSsl** in **org.springframework.boot.autoconfigure.web.reactive.function.client**. Use real SSL bundles from application config/secret stores; never disable certificate or hostname verification to "fix SSL".

**Timeouts differ across the APIs:**

- **RestTemplateBuilder.setConnectTimeout(...)** and **setReadTimeout(...)** in Boot 3.3 apply to the underlying request factory.
- Spring Framework's **RestClient.Builder** needs a request factory configured with timeouts/HTTP client settings; do not assume it has all the exact same convenience methods as RestTemplateBuilder in the same version.
- **WebClient** typically uses a **ClientHttpConnector** (such as Reactor Netty) with its own connect/response timeouts, pool, and event-loop semantics. Overriding the connector requires checking whether Boot-shared HTTP resources are bypassed or changed.
- **Read timeout**, **response timeout**, **connect timeout**, **TLS handshake timeout**, **connection pool acquire timeout**, and overall request deadline are distinct concepts. Never claim a single timeout guarantees every call finishes in X seconds.

For RestClient on Boot 3.3 you can use **ClientHttpRequestFactorySettings** and **ClientHttpRequestFactories**:

~~~java
// Example inside a constructor with injected dependencies.
ClientHttpRequestFactorySettings settings =
        ClientHttpRequestFactorySettings.DEFAULTS
                .withConnectTimeout(Duration.ofSeconds(2))
                .withReadTimeout(Duration.ofSeconds(5));
ClientHttpRequestFactory factory =
        ClientHttpRequestFactories.get(settings);

RestClient client = builder
        .baseUrl("https://internal.example.test")
        .requestFactory(factory)
        .build();
~~~

This snippet requires imports for **org.springframework.boot.web.client.ClientHttpRequestFactorySettings**, **ClientHttpRequestFactories**, **org.springframework.http.client.ClientHttpRequestFactory**, and **java.time.Duration**. It shows that **a custom factory is passed into the builder before build**, rather than setting a server property and expecting the client to pick it up.

**Version branch note:** APIs for organizing HTTP client settings and request factories change across Spring Boot **3.3**, **3.4**, **3.5**, and **4.x**. Check the Javadoc for your target project version before applying. Do not copy examples using **spring.http.clients.\*** or **ClientHttpRequestFactoryBuilder** from newer Boot releases assuming those properties/classes exist in Boot 3.3.

## 12. Selecting the HTTP Transport: Classpath-Dependent

A Boot-managed builder does not mean an immutable, single transport. In Spring Boot 3.3:

**RestClient and RestTemplate** select a request factory based on the classpath and configuration conditions, prioritizing **Apache HttpClient**, **Jetty HttpClient**, **OkHttp (deprecated)**, and then **simple JDK HttpURLConnection** per the official 3.3 documentation.

**WebClient** selects a reactive connector based on the classpath, documented in 3.3 in the order **Reactor Netty**, **Jetty RS Client**, **Apache HttpClient**, and **JDK HttpClient**.

**Never judge the HTTP library from the class name RestClient alone.** Changing dependencies can swap the default transport, affecting pooling, proxies, timeouts, TLS, and performance. Do not benchmark only on a laptop while ignoring different dependencies in container deployments.

With WebClient/reactor-netty, Boot can manage shared resource factories. If you manually instantiate **new ReactorClientHttpConnector(HttpClient.create())** for each client, you may lose the expected resource sharing. When tuning is needed, create **one managed connector** and control its lifecycle/disposal rather than spawning unbounded event loops and pools.

Outbound **HTTP/2** is also a property of the client transport and peer—it is **not enabled automatically for every outbound request** just because the Spring Boot server has **server.http2.enabled=true**. HTTP server configuration and HTTP client configuration belong to two separate connections.

## 13. Observability, Metrics/Tracing, and Filters

Spring Boot Actuator 3.3 documentation notes that HTTP client instrumentation for **RestTemplate**, **WebClient**, and **RestClient** is applied when you **inject the auto-configured builder and create the client**. Using static factories without applying the corresponding customizers can leave requests missing expected **Observation/metrics/tracing**.

With matching Actuator/Micrometer setup, the metric is typically **http.client.requests**. Valid tags may include method, URI template, status, and outcome. Avoid putting **user IDs, raw URLs with sensitive data, tokens, or high-cardinality inputs** into low-cardinality metric tags.

### Filters and Interceptors Behave Differently

- **RestClient** supports **ClientHttpRequestInterceptor** or request interceptors via its API; when added to the builder by a customizer, they affect instances built afterward.
- **RestTemplate** holds **ClientHttpRequestInterceptor** instances on the template object; customizers run at build time. How interceptors are added or replaced affects execution order.
- **WebClient** uses **ExchangeFilterFunction** filters in the reactive pipeline; they must honor **Mono/Flux** semantics and never block the event loop.

Standalone illustration of a WebClient filter (do not paste directly into the same configuration name in the demo):

~~~java
WebClient client = builder
        .filter((request, next) -> {
            // Do not log Authorization/Cookie or sensitive bodies.
            System.out.println("calling " + request.method());
            return next.exchange(request);
        })
        .build();
~~~

This snippet assumes **WebClient.Builder builder** is in scope. Filters should emit structured logs, redact sensitive data, and perform no blocking I/O in reactive chains. In production, avoid logging full URLs or raw headers indiscriminately.

### Difference Between Customizers and Request-Time Customization

A global customizer typically runs **when the builder is created/prepared**, whereas an interceptor/filter runs **on each request**. For example:

~~~text
Start application / inject builder:
  RestClientCustomizer -> add default header
  WebClientCustomizer  -> add filter
  RestTemplateCustomizer -> attach interceptor after build

At request time:
  Client -> interceptor/filter -> HTTP transport -> upstream
~~~

Do not write a customizer that mints a short-lived token once and freezes it into a permanent default header. For rotating tokens, use a credential provider or request filter that obtains a valid token **at request time**, handling refresh/expiration and host restrictions.

## 14. Stateful Builder Traps and How to Prevent Config Leakage

### 14.1. RestClient.Builder and WebClient.Builder Are Stateful

Bad example inside a singleton:

~~~java
// builder is a shared field of a singleton.
RestClient a = builder.baseUrl("https://a.example.test")
        .defaultHeader("Authorization", "Bearer token-a")
        .build();

RestClient b = builder.baseUrl("https://b.example.test").build();
// Builder b may still retain default Authorization from a.
~~~

If the same builder is mutated across multiple upstreams, previously added default headers, filters, or error handlers can persist. **This is a credential leakage risk**, not merely a wrong URL.

Reasonable approach:

~~~java
RestClient a = builder.clone()
        .baseUrl("https://a.example.test")
        .defaultHeader("X-Caller", "A").build();

RestClient b = builder.clone()
        .baseUrl("https://b.example.test")
        .defaultHeader("X-Caller", "B").build();
~~~

Note that both still carry the builder's **base** configuration; cloning **does not remove** any sensitive global header already added earlier. Therefore, specific tokens should be attached via per-client requests or filters, never via a global builder shared across hosts.

### 14.2. RestTemplateBuilder Is Immutable

With RestTemplateBuilder:

~~~java
RestTemplateBuilder first = builder
        .rootUri("https://a.example.test");

RestTemplateBuilder second = builder
        .rootUri("https://b.example.test");
// first and second are configured independently from the original builder.
~~~

New builders can create distinct RestTemplates without mutating the **original builder**. However, the built RestTemplate **client object** exposes setters and mutable state; avoid mutating a RestTemplate that is actively shared across threads.

### 14.3. Prototype Scope and Singleton Injection

Suppose you have:

~~~java
@Service
class SharedClientFactory {
    private final WebClient.Builder builder;

    SharedClientFactory(WebClient.Builder builder) {
        this.builder = builder;
    }
}
~~~

This singleton holds **one** prototype builder injected when the singleton was created. Reusing `builder` inside the factory **does not yield a fresh prototype instance** each time. To obtain a new builder instance from the container each time, inject **ObjectProvider<WebClient.Builder>** and request it when needed, or clone the stored builder.

**You do not need a fresh builder for every HTTP request.** Typically, build clients **once at service startup** and reuse those objects. Spawning unbounded clients and connection pools wastes resources and degrades observability.

## 15. SSL, Proxies, Authentication, and Production Correctness

Practical takeaways from this lesson:

1. **Supply secrets only to the client targeting the upstream that needs them.** Never create a global `RestClientCustomizer` attaching the same `Authorization` header to all services.
2. **Never disable TLS certificate verification or hostname checking** to work around trust errors; configure an **SSL bundle** with the appropriate CA/truststore and client certificate.
3. **Proxy configuration** belongs to the HTTP transport; scope the policy per client instead of routing the entire JVM through a sensitive proxy unnecessarily.
4. **Connect/read/response timeouts** must be bounded by SLOs and request budgets; when retrying, cap attempts, backoff, idempotency, and total deadline.
5. **Retries do not come automatically from the builder**: if adding Resilience4j, Spring Retry, or retry filters, design them at the proper layer and never blindly retry non-idempotent POSTs.
6. **CORS is not an issue for server-to-server RestClient/WebClient** in the sense of browser CORS enforcement. If an external API returns 403, check authentication/authorization, WAF rules, and the API contract rather than assuming CORS headers are needed.
7. **Pick explicit HTTP client dependencies**; classpath changes can alter the Boot-selected connector/factory and change metrics, performance, and TLS behavior.
8. **Propagate correlation/trace context** via framework observability integrations rather than inventing one custom global header and assuming distributed tracing is complete.
9. **Organize client configuration by upstream name**, avoiding a single mutable builder being altered in rotation across hosts.
10. **Test behavior rather than just bean existence.** Having a `RestClient.Builder` bean does not prove requests actually apply timeouts, headers, or tracing.

## 16. Diagnosing Common Failures

| Symptom | Typical cause | Remediation |
| --- | --- | --- |
| Cannot find **RestTemplate** bean to `@Autowired` | Boot supplies `RestTemplateBuilder`, not a default singleton RestTemplate | Build a RestTemplate from the builder in the service or declare `@Bean RestTemplate`. |
| Cannot inject `WebClient.Builder` | Missing WebFlux client dependency or auto-config inactive | Add `spring-webflux`/`starter-webflux` and inspect the condition report. |
| Client sends requests but lacks global headers | Used `RestClient.create`/`WebClient.create`/`new RestTemplate` or custom builder skipping customizers | Inject Boot's builder, build from it, and test actual requests. |
| `RestClientCustomizer` has no effect on `WebClient` | Wrong customizer family | Use `WebClientCustomizer` for `WebClient.Builder`. |
| `RestTemplateCustomizer` has no effect on `RestClient` | Customizer targets `RestTemplate` only | Use `RestClientCustomizer`. |
| One client sends another upstream's token | Reused stateful builder and mutated `Authorization`/`baseUrl` | Clone or separate builders/clients per upstream; no global secrets. |
| Metrics disappeared after refactor | Replaced auto-configured builder with static factory | Check client creation path, Actuator/observation, and customizers. |
| Lost customizers after declaring a `RestTemplateBuilder` bean | Auto-configuration backed off and `RestTemplateBuilderConfigurer` was skipped | Use the configurer or inject the auto-configured builder instead of replacing it. |
| `RestTemplateBuilder` config changes had no effect | Ignored the new builder object returned by setters | Assign/chain the returned builder and call `build()` on it. |
| `WebClient` still uses old `baseUrl` | Same stateful builder mutated repeatedly in a singleton | Clone before per-client config and build stable clients. |
| Timeouts set in `server.*` do not bound outbound calls | Server timeouts are not HTTP client timeouts | Configure the client's request factory/connector. |
| Running MVC yet `WebClient` is present | Adding WebFlux for the client does not switch the server stack by default | Verify web application type, actual server, and connector. |
| Code from Boot 4.x fails to compile on 3.3 | APIs/properties changed across versions | Check version-matched Javadoc and use Boot 3.3 APIs. |
| Mock test passes but TLS/proxy fails in production | Mocks bypass network, SSL, DNS, and pooling | Add integration/network tests on realistic topology. |
| Calling `RestClient` in Netty event loop slows app | `RestClient` is a blocking client | Use reactive `WebClient` or offload blocking work appropriately. |

## 17. Applied Questions and Answers

**Q1.** Does Spring Boot 3.3 auto-create a singleton RestTemplate bean for all services?  
**No.** It auto-configures **RestTemplateBuilder** so you can build RestTemplates as needed.

**Q2.** Which Boot 3.3 builders are prototype and stateful?  
**RestClient.Builder** and **WebClient.Builder**. `RestTemplateBuilder` behaves functionally, returning a new object on each configuration call.

**Q3.** Why can `RestClient.create()` lack metrics/headers even when a `@Bean RestClientCustomizer` exists?  
Because static factories do not go through **Boot-managed RestClient.Builder**, so they do not automatically receive customizers and instrumentation.

**Q4.** When does `RestTemplateCustomizer` run?  
It is invoked by the **auto-configured RestTemplateBuilder** when building/configuring a RestTemplate, and does not retroactively alter already-constructed RestTemplates.

**Q5.** A singleton injects a prototype `WebClient.Builder`, then mutates `baseUrl` repeatedly. Does each `build()` call get a fresh builder?  
**No.** The singleton holds the single injected instance; build dedicated clients cleanly or clone the builder.

**Q6.** Is adding `Authorization` for upstream A in a global `WebClientCustomizer` and using that builder for B dangerous?  
**Yes.** Sensitive headers can leak to the wrong upstream. Configure credentials locally per trust boundary.

**Q7.** Why use `RestTemplateBuilderConfigurer` when overriding `@Bean RestTemplateBuilder`?  
To preserve Boot's defaults and customizers instead of starting with an unconfigured empty builder.

**Q8.** Why is testing bean existence not enough?  
A bean may exist while actual outbound requests lack headers, timeouts, or instrumentation; test real outbound requests or the HTTP client boundary.

**Q9.** Can `WebClient` be used in Spring MVC?  
**Yes**, with the WebFlux client dependency; that does not turn the MVC server into a reactive server by default.

**Q10.** Do global customizers apply to every client object in the JVM?  
**No.** They apply only to Boot-configured builders of that matching type and clients built from them.

**Q11.** Can changing a transport library in `pom.xml` change HTTP client behavior?  
**Yes.** Boot auto-detects connectors and request factories from the classpath, which can change pooling, timeouts, and TLS.

**Q12.** If mTLS/SSL is needed for service A but not B, where should it be configured?  
On **service A's own builder/client** using the appropriate SSL bundle, without weakening global TLS validation.

## 18. Production Adoption Checklist

- [ ] Identify which HTTP client is used: RestClient, RestTemplate, or WebClient, and verify matching dependencies.
- [ ] Use **constructor injection** with Spring Boot's auto-configured builders whenever possible.
- [ ] Build stable clients per upstream rather than building/mutating a shared builder on every request.
- [ ] Put **global cross-cutting defaults** in the matching customizer; keep **base URLs, tokens, TLS, and per-upstream timeouts** local.
- [ ] Distinguish **prototype stateful builders** from the **functional RestTemplateBuilder**.
- [ ] Never accidentally call **RestClient.create/WebClient.create/new RestTemplate** when Boot customizers are expected.
- [ ] Do not define a custom builder `@Bean` overriding auto-config unless necessary; if required, preserve configurers/customizers.
- [ ] Avoid replacing entire lists of converters, interceptors, or connectors when you only want to add one piece.
- [ ] Verify **observation/metrics/tracing** works using instrumented clients and observable signals.
- [ ] Test outbound request headers, serialization, HTTP error handling, timeouts, and SSL on the actual client path.
- [ ] Audit for token leakage via global `defaultHeader` or shared stateful builders.
- [ ] Inspect the classpath-selected HTTP transport and connection pool/event-loop lifecycles.
- [ ] Verify APIs/properties against your Spring Boot version (especially 3.3 vs. 3.4/4.x).
- [ ] Test real network failures, proxies, TLS, and redirects in production-like environments; mock tests do not cover everything.
- [ ] Review code so every upstream has explicit configuration and trust boundaries.

## 19. Authoritative References

- **Spring Boot 3.3.13 – Calling REST Services:** https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html — `RestClient.Builder` prototype, `WebClient.Builder` prototype, `RestTemplateBuilder`, the three customizers, and avoiding auto-configuration bypass.
- **Spring Boot 3.3.13 – RestTemplateBuilder Javadoc:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html — `setReadTimeout`, `setConnectTimeout`, `rootUri`, `additionalCustomizers`, converters, interceptors.
- **Spring Boot 3.3.13 – RestClientBuilderConfigurer Javadoc:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientBuilderConfigurer.html — configuring a replacement builder on top of Boot defaults.
- **Spring Boot 3.3.13 – WebClientCustomizer package:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/package-summary.html
- **Spring Boot 3.3 – Metrics / HTTP Client Metrics:** https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html — instrumentation via auto-configured builders and the `http.client.requests` metric.
- **Spring Framework 6.1 – REST Clients:** https://docs.spring.io/spring-framework/reference/integration/rest-clients.html — `RestClient`, `WebClient`, `RestTemplate`, transport, conversion.
- **Spring Framework 6.1 – MockRestServiceServer API:** https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html — `bindTo(RestClient.Builder)`, `createServer(RestTemplate)`.