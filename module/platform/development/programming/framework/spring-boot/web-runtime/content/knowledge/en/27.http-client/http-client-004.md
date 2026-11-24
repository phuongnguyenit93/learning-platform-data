# RestClientCustomizer, RestTemplateCustomizer, and WebClientCustomizer in Spring Boot

## 1. Goal: Customize HTTP Clients Without Bypassing Spring Boot

A Spring Boot application may call many downstream HTTP APIs: customer profiles, payments, inventory, reporting. Each client requires different choices for base URL, timeouts, TLS, headers, logging, error checking, and tracing. If code in every service creates `new RestTemplate()`, `RestClient.create()`, or `WebClient.create()`, you easily bypass the HTTP client components that Spring Boot auto-configured.

Spring Boot 3.3 provides three callbacks, one per client family:

- **`RestClientCustomizer`:** customizes `RestClient.Builder`, for the **blocking** fluent API client.
- **`RestTemplateCustomizer`:** customizes **the `RestTemplate` instance** after the builder constructs it, for the long-standing blocking API.
- **`WebClientCustomizer`:** customizes `WebClient.Builder`, for the **reactive** HTTP client using `Mono` and `Flux`.

The three mechanisms have similar names, but **they are not interchangeable**. `RestTemplateCustomizer` does not receive a builder; it receives the actual `RestTemplate`. `RestClientCustomizer` does not affect `RestTemplate`. `WebClientCustomizer` does not make `RestClient` non-blocking.

This lesson uses **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, Gradle**. Hands-on objectives include creating three customizer beans, running an HTTP endpoint, writing integration tests proving headers are attached, knowing when to use local vs. global settings, and understanding the risks of creating clients manually or overriding the HTTP transport.

## 2. Comparison Table of the Three Interfaces

| Aspect | `RestClientCustomizer` | `RestTemplateCustomizer` | `WebClientCustomizer` |
|---|---|---|---|
| Client type | `RestClient` | `RestTemplate` | `WebClient` |
| Programming model | Blocking, fluent API | Blocking, classic API | Reactive, Publisher-based |
| Method | `customize(RestClient.Builder)` | `customize(RestTemplate)` | `customize(WebClient.Builder)` |
| Callback runs on | Boot-prepared builder | Template created by `RestTemplateBuilder` | Boot-prepared builder |
| Standard usage | Inject `RestClient.Builder` | Inject `RestTemplateBuilder` | Inject `WebClient.Builder` |
| Common config | `defaultHeader`, interceptor, status handler | Interceptors, error handler, request factory | `defaultHeader`, exchange filter, connector |
| Direct creation bypassing Boot customizers | `RestClient.create()` | `new RestTemplate()` | `WebClient.create()` |
| Special condition | In Boot 3.3, conditional on non-reactive web applications | Boot provides the builder, not a default singleton RestTemplate | Requires WebClient on classpath |

**Exact Spring Boot 3.3 packages:**

```java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;

import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
```

This is a reference imports snippet, not a complete Java file. The client APIs belong to Spring Framework, while the `*Customizer` types above belong to Spring Boot 3.3. When reading Boot 4.x guides, check package names before copying because APIs may have relocated.

## 3. Why Does Spring Boot Recommend Injecting Builders?

### 3.1. Auto-Configuration for RestClient

Under suitable conditions, Spring Boot 3.3 provides a **prototype** `RestClient.Builder` bean. The builder is pre-configured with `HttpMessageConverters`, `ClientHttpRequestFactory`, and registered customizers. Each normal injection point receives a prepared builder; services use it to build a `RestClient` with their own configuration.

```text
@Bean RestClientCustomizer ...
             │
             ▼
Boot RestClientAutoConfiguration
             │
             ▼
RestClient.Builder prototype
             │
       Service injects builder
             │
       baseUrl, headers, ...
             │
             ▼
          build()
             │
             ▼
    RestClient (blocking)
```

**Note specific to Boot 3.3:** `RestClientAutoConfiguration` carries `NotReactiveWebApplicationCondition`. Therefore, **a reactive WebFlux-only application** does not necessarily receive an auto-configured `RestClient.Builder` bean the way an MVC app does. Do not assume every builder exists just because its class is on the classpath.

### 3.2. Auto-Configuration for RestTemplate

Boot **does not automatically provide a default singleton RestTemplate**. Instead, Boot creates `RestTemplateBuilder`. Calling `build()` constructs a `RestTemplate`, applying the appropriate request factory, converters, and customizers:

```text
@Bean RestTemplateCustomizer ...
             │
             ▼
Auto-configured RestTemplateBuilder
             │
       .setReadTimeout(...)
             │
             ▼
           build()
             │
             ▼
RestTemplate created/configured
             │
 RestTemplateCustomizer.customize(template)
             │
             ▼
 Complete RestTemplate
```

This is an important difference in **timing**: the RestTemplate customization callback runs when building/configuring the template, not on every outbound HTTP request.

`RestTemplateBuilder` returns a new builder when configuration methods are called, for example:

```java
RestTemplate template = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(5))
        .build();
```

This snippet assumes a service with an injected `RestTemplateBuilder builder` and imported `Duration`. If you call `builder.setReadTimeout(...)` and **discard the return value**, the original builder is not modified as intended. Always chain calls or assign the returned builder.

### 3.3. Auto-Configuration for WebClient

When `WebClient` is present, Spring Boot provides a **prototype** `WebClient.Builder`, preparing codecs, the HTTP connector, and shared resources appropriately. `WebClientCustomizer` beans are applied to this builder.

```text
@Bean WebClientCustomizer ...
             │
             ▼
Boot WebClientAutoConfiguration
             │
             ▼
WebClient.Builder prototype
             │
             ▼
           build()
             │
             ▼
WebClient request → Mono/Flux
             │
        subscription
             │
             ▼
          HTTP I/O
```

Both `RestClient.Builder` and `WebClient.Builder` are **mutable/stateful**: modifying the same builder affects subsequent clients built from it. When building multiple clients from one builder instance, use `clone()` to keep settings isolated. After building, typically inject the configured client as a singleton rather than mutating a shared builder across threads.

## 4. Customization Scope: Local, Global, or Manual

### Level 1: Single Client Only

```java
RestClient billing = restBuilder.clone()
        .baseUrl("https://billing.example.test")
        .defaultHeader("X-Client-Name", "billing")
        .build();

WebClient inventory = webBuilder.clone()
        .baseUrl("https://inventory.example.test")
        .defaultHeader("X-Client-Name", "inventory")
        .build();

RestTemplate reports = templateBuilder
        .setReadTimeout(Duration.ofSeconds(7))
        .build();
```

This is an **illustrative snippet** inside a class with injected builders and imported `Duration`; the `example.test` domains are not real HTTP systems. Local settings suit per-partner base URLs, credentials, trust bundles, and timeouts.

### Level 2: Shared Policy Across All Clients of the Same Family

```java
@Bean
RestClientCustomizer appTag() {
    return builder -> builder.defaultHeader(
            "X-Application-Name", "order-api");
}
```

This snippet belongs in a `@Configuration` class with matching imports. Boot collects the bean and applies it to **Boot-provided RestClient.Builder** instances. This is application-wide configuration **within the RestClient scope**, not across every outbound HTTP client in the JVM.

### Level 3: Direct Creation, Intentionally Skipping Auto-Configuration

```java
RestClient rawRestClient = RestClient.create();
RestTemplate rawTemplate = new RestTemplate();
WebClient rawWebClient = WebClient.create();
```

These clients carry Spring Framework defaults, but **do not automatically receive Boot customizer beans**. Use them only when you intentionally configure everything yourself; do not use them out of habit and wonder why timeouts, TLS bundles, or observations are missing.

**Practical rule:** prefer Boot's builders; use global customizers for neutral shared policies, and use dedicated client beans for per-partner settings and credentials. Never put partner A's API token or `Authorization` header in a global customizer, because a client calling partner B could leak the secret.

## 5. Java 17+ Example Project Running All Three Clients

The single example below uses **Spring Boot 3.3.13** with a **Spring MVC/Tomcat** server. The WebFlux starter is added to obtain `WebClient` for outbound calls without switching the server to reactive. A `GET /echo` endpoint echoes back the `X-Demo-Client` header value. Each customizer attaches a different value so tests can verify all three families.

### 5.1. Structure

```text
http-client-customizers/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/clients/HttpClientApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/clients/HttpClientCustomizerTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Both starters appear intentionally: MVC provides the Tomcat server, and WebFlux provides `WebClient`. `RestClient` and `RestTemplate` remain **blocking**. A single project includes all three clients for observation; production apps should include only the dependencies actually needed.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=http-client-customizers
```

### 5.2. Application, Customizer Beans, and Endpoint

**`src/main/java/com/example/clients/HttpClientApplication.java`:**

```java
package com.example.clients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpClientApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ClientCustomization {

    @Bean
    RestClientCustomizer restClientCustomizer() {
        // Parameter is RestClient.Builder, not RestClient.
        return builder -> {
            builder.defaultHeader("X-Demo-Client", "rest-client");
        };
    }

    @Bean
    RestTemplateCustomizer restTemplateCustomizer() {
        // Parameter is the RestTemplate created by RestTemplateBuilder.
        return template -> {
            template.getInterceptors().add((request, body, execution) -> {
                request.getHeaders().set(
                        "X-Demo-Client", "rest-template");
                return execution.execute(request, body);
            });
        };
    }

    @Bean
    WebClientCustomizer webClientCustomizer() {
        // Parameter is WebClient.Builder.
        return builder -> {
            builder.defaultHeader("X-Demo-Client", "web-client");
        };
    }
}

@RestController
class EchoController {
    @GetMapping(
            path = "/echo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String echo(
            @RequestHeader(
                    value = "X-Demo-Client",
                    required = false) String source) {
        return source == null ? "missing" : source;
    }
}
```

There is only one top-level `public class` in the file. The remaining two package-private classes are discovered by Spring Boot component scanning because they share the application's package. Here:
- `RestClientCustomizer` adds a default header to the builder.
- `RestTemplateCustomizer` attaches a `ClientHttpRequestInterceptor` to the template. **The callback registering the interceptor runs only at build time**; the inner interceptor lambda runs on each request.
- `WebClientCustomizer` adds a default header to the builder.
- `EchoController` returns the received request header string, or `missing` if absent.

Nothing calls `subscribe()` or sends requests during customizer initialization. Customizers are used to **configure clients**, not to call downstream services directly.

### 5.3. Run and Test with curl

In a project with JDK 17+ and a compatible Gradle version:

```bash
gradle bootRun
```

If you generated the Gradle Wrapper, use `./gradlew bootRun` (macOS/Linux), or `.\gradlew.bat bootRun` in Windows PowerShell.

```bash
curl -s http://localhost:8080/echo
curl -s -H "X-Demo-Client: manually-set" http://localhost:8080/echo
```

Expected bodies are, respectively:

```text
missing
manually-set
```

`curl` is unaffected by Java customizers; the second header is sent explicitly by the command. To observe Spring Boot customizers, use Java clients built from Boot builders, as shown in the integration test below.

## 6. Integration Test Proving All Three Customizers Work

The test starts the server on a random port, injects the Boot auto-configured builders, sends real HTTP requests to `/echo`, and asserts the responses. Because both web and webflux starters are present and the server selects MVC, Boot provides all three builders in this example.

**`src/test/java/com/example/clients/HttpClientCustomizerTest.java`:**

```java
package com.example.clients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpClientCustomizerTest {

    @LocalServerPort
    int port;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Autowired
    RestTemplateBuilder restTemplateBuilder;

    @Autowired
    WebClient.Builder webClientBuilder;

    private String localUrl() {
        return "http://localhost:" + port + "/echo";
    }

    @Test
    void restClientReceivesHeader() {
        String body = restClientBuilder.build()
                .get()
                .uri(localUrl())
                .retrieve()
                .body(String.class);

        assertEquals("rest-client", body);
    }

    @Test
    void restTemplateReceivesHeader() {
        RestTemplate client = restTemplateBuilder.build();
        String body = client.getForObject(
                localUrl(), String.class);

        assertEquals("rest-template", body);
    }

    @Test
    void webClientReceivesHeader() {
        String body = webClientBuilder.build()
                .get()
                .uri(localUrl())
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("web-client", body);
    }

    @Test
    void directFactoryDoesNotSeeBootCustomizers() {
        String a = RestClient.create()
                .get()
                .uri(localUrl())
                .retrieve()
                .body(String.class);

        String b = new RestTemplate()
                .getForObject(localUrl(), String.class);

        String c = WebClient.create()
                .get()
                .uri(localUrl())
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("missing", a);
        assertEquals("missing", b);
        assertEquals("missing", c);
    }
}
```

Run:

```bash
gradle test
```

**Expected outcome when environment and dependencies are right:** all four tests pass. This is the expected behavior inferred from the code and Spring APIs, **not evidence that Gradle was executed here**.

| Test | Where the client was created from | Returned body |
|---|---|---|
| `restClientReceivesHeader` | Boot-injected `RestClient.Builder` | `rest-client` |
| `restTemplateReceivesHeader` | Boot-injected `RestTemplateBuilder` | `rest-template` |
| `webClientReceivesHeader` | Boot-injected `WebClient.Builder` | `web-client` |
| `directFactoryDoesNotSeeBootCustomizers` | `RestClient.create()`, `new RestTemplate()`, `WebClient.create()` | Three `missing` values |

`block(Duration.ofSeconds(5))` is used **only on the JUnit thread** to conveniently assert the result. Do not copy `block()` into a WebFlux event-loop handler. In real WebFlux services, return/compose `Mono` and let the framework subscribe.

A real test on a random port proves the client sent HTTP over the network to the actual controller and that the final header was observed by the server. That is far more valuable than merely checking that a customizer bean exists in the Spring context.

## 7. When Do Customizers Run vs. When Do Interceptors Run?

Some log messages cause confusion:
- Logs inside `RestClientCustomizer.customize` appear when the builder is configured, **not on every outbound request**.
- Logs inside `RestTemplateCustomizer.customize` appear when the template is built/configured.
- Logs inside `WebClientCustomizer.customize` appear when the builder is prepared and do not guarantee a request was subscribed to.
- `ClientHttpRequestInterceptor.intercept` in RestClient/RestTemplate runs **when the request is executed**.
- `ExchangeFilterFunction` in WebClient participates in **the pipeline of a subscribed request**.

### 7.1. RestClient: Builder Callback and Request Interceptor

```java
@Bean
RestClientCustomizer requestTag() {
    return builder -> {
        builder.requestInterceptor((request, body, execution) -> {
            request.getHeaders().set(
                    "X-App-Instance", "orders");
            return execution.execute(request, body);
        });
    };
}
```

This sample belongs in `@Configuration` with imports; it modifies requests via the interceptor attached to the builder. Do not log raw bodies, tokens, or cookies here.

### 7.2. RestTemplate: Template Callback and Interceptor

```java
@Bean
RestTemplateCustomizer requestTag() {
    return template -> template.getInterceptors().add(
            (request, body, execution) -> {
                request.getHeaders().set(
                        "X-App-Instance", "orders");
                return execution.execute(request, body);
            });
}
```

`RestTemplateCustomizer` is invoked when constructing the template, whereas the `intercept(...)` lambda runs for HTTP requests executed by that template. Do not confuse it with `RestTemplateRequestCustomizer`: that interface customizes an individual `ClientHttpRequest` per the builder contract, unlike the callback operating on the template itself.

### 7.3. WebClient: Reactive ExchangeFilterFunction

```java
@Bean
WebClientCustomizer requestTag() {
    return builder -> builder.filter((request, next) -> {
        ClientRequest tagged = ClientRequest.from(request)
                .header("X-App-Instance", "orders")
                .build();
        return next.exchange(tagged);
    });
}
```

This snippet uses Spring WebFlux's `ClientRequest`; import `org.springframework.web.reactive.function.client.ClientRequest`. A filter can inspect metadata and pass the request to the next function; if it consumes the response body itself, it must preserve lifecycle and buffer release. **Never call `subscribe()` inside a filter**, as doing so breaks cancellation and error propagation.

**Best practice:** use customizers to register interceptors/filters once; use interceptors/filters for **per-request** policies.

## 8. Customizer Ordering and Additive vs. Replace Semantics

Multiple beans of the same interface can exist, contributed by the application or a library. Spring supports `@Order`/`Ordered` to control application order when beans are collected in ordered lists. Still, **never rely on accidental ordering** or assume "the last bean wins" for every setter.

Some methods are **additive**, while others **replace** existing configuration:

| API | Meaning |
|---|---|
| `RestClient.Builder.defaultHeader(...)` | Sets a default header, which can be affected by request-level settings or interceptors |
| `WebClient.Builder.filter(...)` | Appends an `ExchangeFilterFunction` to the filter pipeline |
| `RestTemplate.getInterceptors().add(...)` | Appends an interceptor to the list |
| `RestTemplate.setErrorHandler(...)` | Replaces the current error handler |
| `RestTemplate.setRequestFactory(...)` | Replaces the request factory |
| `RestTemplateBuilder.customizers(...)` | **Replaces the list** of existing customizers |
| `RestTemplateBuilder.additionalCustomizers(...)` | Adds customizers without replacing everything |
| `RestTemplateBuilder.messageConverters(...)` | Resets the converters list, potentially dropping defaults |
| `RestTemplateBuilder.additionalMessageConverters(...)` | Appends converters |

Illustrative ordering example:

```java
@Bean
@Order(10)
RestClientCustomizer commonHeader() {
    return builder -> builder.defaultHeader(
            "X-Application", "order-service");
}

@Bean
@Order(20)
RestClientCustomizer commonStatusHandler() {
    return builder -> builder.defaultStatusHandler(
            status -> status.is5xxServerError(),
            (request, response) -> {
                throw new IOException("Downstream 5xx: "
                        + response.getStatusCode());
            });
}
```

This is a **code snippet** requiring imports for `Bean`, `Order`, `RestClientCustomizer`, and `IOException`—not a standalone file. `@Order` helps when callbacks have ordering dependencies, though keeping policies relatively independent is better. `defaultStatusHandler` affects responses when `retrieve()` runs per contract, rather than throwing during Spring builder construction.

If a `RestTemplateCustomizer` adds an interceptor via `add(...)` and later the same template runs the callback again, the interceptor can be registered twice. Never unconditionally re-invoke callbacks on an already-built client. Write tests verifying how many times requests pass through filters when multiple modules register customizers.

## 9. When to Use Dedicated Client Beans Instead of Global Customizers?

With multiple partners, per-partner client beans clarify trust boundaries and settings:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClients {

    @Bean("billingClient")
    RestClient billing(RestClient.Builder builder) {
        return builder
                .baseUrl("https://billing.example.test")
                .defaultHeader("X-Service", "billing")
                .build();
    }

    @Bean("catalogClient")
    WebClient catalog(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Service", "catalog")
                .build();
    }

    @Bean("legacyTemplate")
    RestTemplate legacy(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://legacy.example.test")
                .setReadTimeout(Duration.ofSeconds(7))
                .build();
    }
}
```

This is an **illustrative class** requiring imports and real downstream hosts; `example.test` is only an example domain. Because the builders come from Boot, they still retain their global customizers. `RestTemplateBuilder.rootUri` applies to URIs starting with `/` in matching methods; absolute URIs are handled separately.

When multiple beans of the same type exist, use `@Qualifier("billingClient")` or constructor qualifiers to prevent ambiguity. If a partner needs an API key, Bearer token, mTLS certificate, or dedicated truststore, configure it on that specific bean rather than globally. Use outbound URL allowlists and input validation to prevent SSRF when base URLs/URIs have external inputs.

## 10. Timeouts and HTTP Transports: Not All Clients Are Alike

The three clients differ in both API and transport:

- `RestClient` and `RestTemplate` are blocking. Timeouts typically attach to `ClientHttpRequestFactory` or the underlying HTTP client.
- `WebClient` returns `Mono/Flux` and uses `ClientHttpConnector` (usually Reactor Netty with `starter-webflux`).
- Connect timeout, response timeout, total pipeline timeout, and business timeout are distinct quantities.
- Retrying a non-idempotent POST can cause duplicate side effects if the server already finished processing and the response was lost.

### 10.1. RestTemplateBuilder in Boot 3.3

```java
RestTemplate template = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(5))
        .build();
```

Snippet requiring `RestTemplateBuilder builder` and `Duration`. Remember that this builder returns a new object on each call.

### 10.2. RestClient with a Request Factory

```java
ClientHttpRequestFactorySettings settings =
        ClientHttpRequestFactorySettings.DEFAULTS
                .withConnectTimeout(Duration.ofSeconds(2))
                .withReadTimeout(Duration.ofSeconds(5));

ClientHttpRequestFactory factory =
        ClientHttpRequestFactories.get(settings);

RestClient client = restBuilder.clone()
        .requestFactory(factory)
        .build();
```

Snippet requiring imports `org.springframework.boot.web.client.ClientHttpRequestFactorySettings`, `ClientHttpRequestFactories`, `org.springframework.http.client.ClientHttpRequestFactory`, `Duration`, `RestClient`; `restBuilder` is the injected builder. When replacing the factory, re-verify TLS, proxies, HTTP resource sharing, and instrumentation—do not assume the new factory inherits all prior settings.

### 10.3. WebClient with Reactor Netty

```java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = webBuilder.clone()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
```

Requires imports `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, and `Duration`. `responseTimeout` is not the timeout of the entire request pipeline. `Mono.timeout`/deadlines in services add separate bounds, and cancellation behavior depends on the upstream/driver.

**Caveat:** replacing the connector manually can lose Boot-prepared shared HTTP resources, TLS, and metrics. Never create a new connection pool per request. Customize narrowly per service and measure latency/concurrency before rolling out globally.

## 11. SSL Bundles, Secrets, and Per-Partner Authentication

For HTTPS, clients must **verify certificate chains and hostnames**; use named SSL bundles instead of trust-all. Boot 3.3 offers:

```java
RestClient securedRest = restBuilder.clone()
        .baseUrl("https://partner.example.test")
        .apply(restClientSsl.fromBundle("partner-trust"))
        .build();

WebClient securedWeb = webBuilder.clone()
        .baseUrl("https://partner.example.test")
        .apply(webClientSsl.fromBundle("partner-trust"))
        .build();

RestTemplate securedLegacy = templateBuilder
        .setSslBundle(sslBundles.getBundle("partner-trust"))
        .build();
```

The variables `restClientSsl`, `webClientSsl`, and `sslBundles` must be injected—corresponding to `RestClientSsl` in `org.springframework.boot.autoconfigure.web.client`, `WebClientSsl` in `org.springframework.boot.autoconfigure.web.reactive.function.client`, and `SslBundles` in `org.springframework.boot.ssl`. The bundle must be declared via `spring.ssl.bundle.jks.*` or `spring.ssl.bundle.pem.*` in configuration. This snippet **does not run standalone** without real certificates/truststores and a partner server.

Putting an `Authorization` header in a global customizer for all hosts creates a **credential leakage risk**. Only attach tokens when the URL/trust domain is known or inside individual client beans, and never log secrets in HTTP interceptors/filters. Never disable hostname verification, skip TLS certificates, or use trust-all as a "quick fix" for handshake errors.

## 12. Observability, Errors, and Request Context

When the app includes Spring Boot Actuator/Micrometer Observation, Boot can register customizers to collect metrics/tracing for HTTP clients. Using auto-configured builders preserves this support. Creating clients directly may leave tracing/observations missing.

**Error handling differs:**
- `RestClient.retrieve()` uses default status handlers and supports `defaultStatusHandler`.
- `RestTemplate` uses `ResponseErrorHandler`.
- `WebClient.retrieve()` converts 4xx/5xx into reactive errors per contract; `exchangeToMono` lets you inspect status/body explicitly.

Never write one custom callback assuming all three clients throw the exact same exception for HTTP 404, timeouts, or broken JSON. Write contracts and tests for each client family.

**Request context:** correlation IDs, `traceparent`, and tenant/user context must come from trusted sources and propagate appropriately for the runtime. On WebFlux, `ThreadLocal` or `RequestContextHolder` does not always follow execution hops across operators; use Reactor Context and proper instrumentation. Never use raw URLs, tokens, or user IDs as metric tags with unbounded cardinality.

Never log entire request/response bodies in a default global filter: that risks exposing PII, JWTs, session cookies, passwords, or payment details. Configure masking, sampling, and bounds if logging is truly required.

## 13. Ways Spring Boot Configuration Gets Lost

### 13.1. Defining RestTemplateBuilder Yourself Without a Configurer

An easy way to lose defaults:

```java
@Bean
RestTemplateBuilder replacement() {
    return new RestTemplateBuilder()
            .setConnectTimeout(Duration.ofSeconds(3));
}
```

Because your `RestTemplateBuilder` bean replaces the auto-configured bean, Boot's customizers and settings **are not carried over automatically**.

If you truly need a custom builder bean, Boot 3.3 provides `RestTemplateBuilderConfigurer`:

```java
@Bean
RestTemplateBuilder replacement(
        RestTemplateBuilderConfigurer configurer) {
    return configurer.configure(new RestTemplateBuilder())
            .setConnectTimeout(Duration.ofSeconds(3));
}
```

These two snippets are **mutually exclusive alternatives** and must not both be defined in the same application. `RestTemplateBuilderConfigurer` belongs to `org.springframework.boot.autoconfigure.web.client` in Boot 3.3. The second option preserves Boot's configuration before applying new settings. Still, most applications **do not need to define their own RestTemplateBuilder bean**.

### 13.2. Creating Clients Directly

```java
RestClient rest = RestClient.create();
RestTemplate template = new RestTemplate();
WebClient web = WebClient.create();
```

These clients do not automatically receive Boot's `RestClientCustomizer`/`RestTemplateCustomizer`/`WebClientCustomizer`. The integration test in Section 6 demonstrates this directly.

### 13.3. Customizing One Family and Expecting Another to Change

A `RestClientCustomizer` does not modify `WebClient` or `RestTemplate`. If all three need the same policy header, you need three matching mechanisms or your own client abstraction layer—you **cannot directly share** one callback because their signatures differ.

### 13.4. Mutating a Builder Concurrently or After Build

`RestClient.Builder`/`WebClient.Builder` are stateful. Never cache a singleton builder and let multiple threads mutate base URLs/headers concurrently. Build configured clients at startup and reuse them, or call `clone()` for independent configurations.

## 14. Reactivity: Adding WebClientCustomizer Does Not Make an App Reactive

A Spring MVC app can use `WebClient` outbound; that does not turn `DispatcherServlet` into `DispatcherHandler`. Conversely, in a pure WebFlux app, calling `RestTemplate`/`RestClient` directly on the Netty event loop **blocks the thread**. Never call `block()` casually inside WebFlux handlers or reactive filters.

Choose accordingly:
- **MVC/Servlet + blocking libraries:** `RestClient` (modern fluent API) or `RestTemplate` (legacy) is the natural fit.
- **WebFlux + reactive downstream:** `WebClient` is the right fit.
- **WebFlux forced to call a blocking SDK:** isolate work onto a bounded scheduler/thread pool and cap concurrency; this is a workaround, not baseline performance.

`WebClient` executes requests only when the Publisher is subscribed to. If a service calls `webClient.get()...bodyToMono(...)` and discards the Publisher, no HTTP I/O occurs—even with the right customizer. Return `Mono` to Spring WebFlux or compose the pipeline properly; never call `subscribe()` inside business services in ways that drop error/cancellation propagation.

## 15. Test Strategy: From Callbacks to Real HTTP

| Test type | What it proves | What it does not prove |
|---|---|---|
| Customizer unit test | Callback invokes expected builder/template methods | Whether Boot registers the bean or network effects |
| Spring context test | Bean exists and DI is wired | Actual headers sent or real timeouts |
| `@SpringBootTest(RANDOM_PORT)` like Section 6 | Boot builder + real HTTP request + response | TLS, proxy, high latency, retries |
| MockRestServiceServer | RestClient/RestTemplate request/response mapping | Sockets/TLS/connection pools |
| WebClient mock ExchangeFunction | Filter behavior, status/body handling | Connector networking |
| Local slow server | Timeouts, error handling | Production load/proxy infrastructure |
| Simulated test CA TLS | Truststore/hostname verification | Real CA rotation/production trust |

Never look at a Spring context containing a `RestClientCustomizer` bean and conclude every client receives the policy. Verify **where clients are created** and what actual requests look like. Similarly, `@WebMvcTest`/`@JsonTest` do not guarantee full HTTP client auto-configuration is loaded; use integration tests at the proper scope.

Useful assertions: correct header per family, partner-specific policies do not cross hosts, timeouts are bounded, 4xx/5xx statuses are handled, invalid certificates are rejected, secrets are never logged, tracing works when dependencies are enabled, and blocking/reactive thread models are not mixed.

## 16. Practical Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Missing header from `RestClientCustomizer` | Code calls `RestClient.create()` | Inject Boot's builder and build from it |
| Missing `RestTemplateCustomizer` | Used `new RestTemplate()` or custom bean | Inject `RestTemplateBuilder` and build |
| Missing `WebClientCustomizer` | Used `WebClient.create()` or manual builder | Inject Boot's `WebClient.Builder` |
| `RestTemplate` bean not found | Boot does not provide a default RestTemplate singleton | Build from `RestTemplateBuilder` and register a bean if needed |
| `RestClient.Builder` missing in WebFlux-only app | Boot 3.3 RestClient auto-config is conditional on non-reactive apps | Check app type; choose WebClient or explicit config |
| RestTemplate timeout did not change | Discarded the builder returned by the method | Chain calls and build from the new builder |
| Customizer logs once even though HTTP runs many times | Callback runs at build time, not per request | Use an interceptor/filter for request-time behavior |
| Duplicate headers | Multiple interceptors, append vs. overwrite, or overlapping configs | Audit order and test final headers |
| New request factory broke SSL/proxy/metrics | Replaced Boot-configured transport | Use Boot's builder and override deliberately |
| WebClient `Mono` sends no request | Publisher was never subscribed to | Return/compose `Mono`; do not discard it |
| WebFlux throughput drops after client change | Calling blocking RestClient/RestTemplate on event loop | Use WebClient or offload blocking I/O |
| HTTP 4xx behaves differently across clients | Different error handlers and default status semantics | Design/test contracts separately per client family |
| Partner A receives Partner B's credentials | Global Authorization header | Scope secrets per client/trust domain |
| Disabled hostname verification to "stop errors" | Wrong trust bundle/CA/SAN | Fix certificates and truststore; never trust-all |
| Missing tracing despite Actuator present | Client built outside Boot builder or missing exporter | Check auto-configuration, registry, instrumentation |
| Mock tests pass but production times out | Mocks do not perform real socket I/O | Test with a local slow server, TLS, and pooling |

## 17. Implementation Checklist

- [ ] Import the three correct `*Customizer` interfaces for Spring Boot 3.3.
- [ ] Confirm whether the client is blocking RestClient/RestTemplate or reactive WebClient.
- [ ] Understand callback parameters: builder, template instance, builder.
- [ ] Use Boot-managed builders instead of accidentally creating clients directly.
- [ ] Use global customization only for shared headers/interceptors/policies without secrets.
- [ ] Keep base URLs, OAuth tokens, API keys, SSL bundles, and timeouts isolated per partner.
- [ ] Set customizer ordering deliberately and avoid multiple setters overwriting the same setting.
- [ ] Remember `RestTemplateBuilder` returns a new builder; `RestClient.Builder` and `WebClient.Builder` are mutable.
- [ ] If replacing the `RestTemplateBuilder` bean, use `RestTemplateBuilderConfigurer`.
- [ ] Do not replace connectors/factories without re-verifying connection pools, TLS, and instrumentation.
- [ ] Never block the Reactor event loop; never manually subscribe Publishers inside services.
- [ ] Write integration tests building all three clients from Boot and calling a real test endpoint.
- [ ] Verify resilience (timeouts, retries, HTTP errors), observability, and log privacy.
- [ ] Also test direct creation paths to verify customizer boundaries.
- [ ] Check auto-configuration conditions for WebFlux-only apps or major Boot upgrades.

## 18. Self-Check Questions

**Q1:** Why does `RestTemplateCustomizer` not receive `RestTemplateBuilder`?  
**Answer:** The interface customizes an already-constructed `RestTemplate` instance; the builder registers callbacks and invokes them during `build()`.

**Q2:** Does `RestClientCustomizer` change `RestTemplate`?  
**Answer:** No; the two families use separate callbacks even though both are blocking HTTP clients.

**Q3:** Does `WebClient.create()` receive Spring Boot's `WebClientCustomizer`?  
**Answer:** No. Inject the Boot-auto-configured `WebClient.Builder` and build from it.

**Q4:** Why can a timeout configured on `RestTemplateBuilder` appear to be ignored?  
**Answer:** Configuration methods return a new builder; if you fail to keep and build from the returned object, the setting does not take effect.

**Q5:** Should you place an `Authorization` header containing a secret in a global `RestClientCustomizer`?  
**Answer:** Usually no, because the token could be sent to unintended hosts. Use partner-specific beans and properly scoped authentication policies.

**Q6:** Can you declare multiple customizer beans of the same type?  
**Answer:** Yes, but avoid conflicting settings, use `@Order` when necessary, and test actual outbound requests.

**Q7:** Does an unsubscribed WebClient `Mono` send an HTTP request?  
**Answer:** Not under the standard reactive model; it must be returned/composed and actually subscribed to.

**Q8:** What is a good test to verify Boot applied callbacks to all three clients?  
**Answer:** `@SpringBootTest` with `RANDOM_PORT`, injecting all three Boot builders, calling a local HTTP endpoint, and asserting headers/bodies.

## 19. Official Documentation

1. Spring Boot 3.3.13 — Calling REST Services, RestClient/RestTemplate/WebClient Customization: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
2. Spring Boot 3.3.13 — RestClientCustomizer JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
3. Spring Boot 3.3.13 — RestTemplateBuilder JavaDoc, `additionalCustomizers` and `setReadTimeout`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html
4. Spring Boot 3.3.13 — WebClientCustomizer JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/WebClientCustomizer.html
5. Spring Boot 3.3.13 — RestClientAutoConfiguration and application conditions: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
6. Spring Boot 3.3.13 — HTTP Clients How-to: https://docs.spring.io/spring-boot/3.3/how-to/http-clients.html
7. Spring Framework — WebClient ExchangeFilterFunction: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
8. Spring Framework — REST Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html

**Takeaway:** `RestClientCustomizer` and `WebClientCustomizer` customize **builders**, while `RestTemplateCustomizer` customizes **constructed templates**. Use Spring Boot–managed builders to preserve codecs, connectors, TLS, and observability where available; reserve global customization for shared policies, use local customization per partner, and verify everything with real HTTP integration tests.