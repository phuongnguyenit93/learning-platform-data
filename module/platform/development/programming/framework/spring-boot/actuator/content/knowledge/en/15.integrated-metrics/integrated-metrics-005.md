# Observing HTTP Clients Created From Spring Boot-Managed Builders

## 1. Distinguishing Incoming Requests From Outgoing Requests

Suppose an application receives an order request and then makes an HTTP call to an inventory service. There are two different activities to observe: handling the request in your application and performing the outgoing call to another service.

```text
User -> Order Application -> Inventory Service
        HTTP server side     HTTP client side
        http.server.requests
        for incoming calls   http.client.requests
                             for outgoing calls
```

`http.server.requests` does not replace client measurements. Incoming request duration can include business steps, queue waits, and multiple outbound calls; a client timer measures activity at the client boundary according to its observation lifecycle.

Spring Boot Actuator integrates observation for `RestClient`, `RestTemplate`, and `WebClient`. The critical practical condition is **obtain the builder auto-configured by Boot, then build the client from that builder**. An object typed as `RestClient` or declared as a bean does not by itself prove it uses Boot's observation configuration.

The complete example in this lesson is verified with **Boot 3.3.13, Spring Framework 6.1.21, Micrometer 1.13.15, and Java 17**. This is the version set to reproduce the lab within the Boot 3.3 line, not an instruction to upgrade a single library or pick a deployment patch for every project.

## 2. What Role Does the Builder Play in Observation?

In Boot 3.3, integration is built on Micrometer Observation. Boot provides customizers that attach `ObservationRegistry` and appropriate observation conventions to builders/clients. When a call executes, Spring creates an observation; the metrics handler turns matching observations into meters.

```text
Boot-configured builder
  -> client carries ObservationRegistry + observation convention
  -> HTTP call executes
  -> observation starts / finishes / records error when applicable
  -> metrics handler records into MeterRegistry
  -> read http.client.requests or export to monitoring system
```

`ObservationRegistry` coordinates observations and handlers. `MeterRegistry` manages meters. Simply having some registry bean or a counter variable does not substitute for wiring the client into this flow properly.

| Client | Builder to Inject From Spring | Usage Characteristics |
| --- | --- | --- |
| `RestClient` | `RestClient.Builder` | Fluent synchronous API |
| `RestTemplate` | `RestTemplateBuilder` | Classic synchronous API, builder in Boot package |
| `WebClient` | `WebClient.Builder` | Reactive API; building a pipeline does not send a request |

Boot's corresponding customizers include `ObservationRestClientCustomizer`, `ObservationRestTemplateCustomizer`, and `ObservationWebClientCustomizer`. There is no need to add a manual timing interceptor just to duplicate this built-in integration. [Boot 3.3 HTTP client metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.http-clients), [HttpClientObservationsAutoConfiguration 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/web/client/HttpClientObservationsAutoConfiguration.java).

### 2.1. Having Metrics Does Not Require a Tracing System

Observation can feed metrics, tracing, or other matching handlers. Getting HTTP client timers in an Actuator app does not require configuring a remote trace backend. Conversely, seeing a metric does not prove traces are created, sampled, and exported.

Low-cardinality information can go into metric labels; high-cardinality details are handled by the appropriate observation mechanism and do not automatically become timer tags. Do not push request IDs, order numbers, or constantly varying full URLs into tags to look up individual calls. [Observability, metrics, and traces in Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 2.2. "Spring-Managed Client" Is Not Enough If You Bypass the Configured Builder

The following direct instantiations do not automatically receive Boot's Observation setup:

```java
RestClient directRestClient = RestClient.create();
RestTemplate directRestTemplate = new RestTemplate();
WebClient directWebClient = WebClient.create();
```

Those are valid APIs, yet without applying equivalent configuration yourself, the client may fail to record metrics into the application's registry. Returning a client constructed this way from a `@Bean` method does not retroactively restore customizers skipped at construction time.

Similarly, creating `new RestTemplateBuilder()`, `RestClient.builder()`, or `WebClient.builder()` yourself is not equivalent to the builder injected by Boot. In special cases requiring a custom builder, apply the corresponding configurers/customizers deliberately and verify the outcome; injecting the provided builder usually keeps configuration sources clearer.

## 3. Building Clients From Injected Builders

In a Boot application with the corresponding client dependencies, an illustrative configuration is:

```java
package example.clients;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryClientConfiguration {
    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder.clone()
            .baseUrl("https://inventory.example")
            .build();
    }

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
            .rootUri("https://inventory.example")
            .build();
    }

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder.clone()
            .baseUrl("https://inventory.example")
            .build();
    }
}
```

This is integration configuration for a Boot project, not a standalone program with `main`. `inventory.example` is a sample host; the standalone experiment below uses in-memory mock responses and does not contact that server.

In a real application, you do not need to create all three client types for one task. The configuration above places them side by side to show the builders and how to preserve observation settings for each API.

`RestClient.Builder` and `WebClient.Builder` can hold state as they are configured. `clone()` isolates variants before setting a base URL or extra customizations while keeping existing setup. `RestTemplateBuilder` uses immutable-style methods returning a new builder; be sure to use the return value of configuration calls.

Do not swap out the injected builder for a new builder halfway through a method and expect ObservationRegistry, conventions, codecs, or other customizers to remain intact. Also do not set the observation registry to NOOP when your goal is collecting metrics.

### 3.1. RestClient: Calling With a URI Template

```java
String item = inventoryRestClient.get()
    .uri("/items/{id}", 7)
    .retrieve()
    .body(String.class);
```

This snippet belongs in a component injected with `inventoryRestClient`. The synchronous call completes or throws according to the client's response handling. When the response is read/closed properly via the API, the observation completes its lifecycle and appears in metrics.

### 3.2. RestTemplate: Keeping Template and URI Variables

```java
String item = inventoryRestTemplate.getForObject(
    "/items/{id}", String.class, 7);
```

Do not wrap each call in a manual timer of the same name. If you also time an enclosing business operation, use a distinct name and boundary to keep the semantics of the two measurements separate.

### 3.3. WebClient: An Actual Subscription Is Required

```java
Mono<String> pending = inventoryWebClient.get()
    .uri("/items/{id}", 7)
    .retrieve()
    .bodyToMono(String.class);

// Return pending to the WebFlux layer so the pipeline is subscribed to,
// or execute it at the appropriate boundary of the program.
```

The illustrative snippet requires importing `reactor.core.publisher.Mono`. Creating `pending` alone does not send an HTTP request. Without a subscription, you cannot expect a timer sample for an unexecuted call to appear.

In a reactive controller, typically return the `Mono` to the framework; do not add `subscribe()` just to "turn on metrics," as that can trigger a call detached from request lifecycle and intended error handling. `block()` in the verification program at the end of this lesson is only for `main` of a synchronous program, not advice to block WebFlux reactive threads.

A cold pipeline can re-execute the call when subscribed to again. Subscribing twice or placing retries where they re-trigger execution can therefore produce multiple observations. Understand the execution lifecycle rather than just counting how many times code constructed a `Mono` variable.

## 4. Choosing URI Templates So Metrics Stay Meaningful

Compare two ways of calling:

```java
// Keep a template with variables to group many order IDs:
client.get().uri("/items/{id}", id).retrieve().body(String.class);

// Concatenate variable data into the string before calling:
client.get().uri("/items/" + id).retrieve().body(String.class);
```

This illustrates a `client` configured with a base URL and an `id` variable. The `/items/{id}` template lets the convention keep a stable `uri` dimension across many IDs. Concatenating beforehand turns concrete values into many distinct templates, increasing tag combinations and meter cost.

If you pass a pre-built `URI` or an API overload that discards template metadata, the convention may no longer know the original template; `uri` may then become a fallback like `none`, depending on client and version. Do not assume the client is broken merely because the uri tag lacks a specific path.

Inspect actual labels and prefer string overloads with URI variables when template grouping is needed. Do not assume every `uri(...)` overload or helper function that concatenates URLs preserves the same observation metadata.

Boot has a mechanism limiting the number of HTTP client uri tag values, but that cap is a safeguard; it does not redesign your grouping and can drop meters past the threshold. Fixing how URIs are built makes more sense than raising the limit when identities grow unchecked.

## 5. Reading the http.client.requests Metric

### 5.1. Recording and Exposing the Endpoint Are Separate Things

A client can record metrics inside the application even if the metrics endpoint is not exposed over HTTP. When diagnosing via Actuator in a web app, an example configuration is:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Access permissions and management URL/port still follow the application configuration. Exposing the endpoint does not send an outgoing request and does not fix a client built from an unconfigured builder.

Typically at least one call must execute and reach the recording stage before the corresponding timer appears. Run a controlled test call, wait for it to finish, and then check:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/metrics/http.client.requests
```

These commands apply to a web app exposing the endpoint at that URL, not the portless verification program later in this lesson. In PowerShell, where `curl` is an alias, use `curl.exe` for proper syntax.

The default name is `http.client.requests`; it can be changed via `management.observations.http.client.requests.name`. If a project renamed it, inspect the actual list rather than concluding instrumentation is missing because the old URL returns 404.

### 5.2. Reading the Classification Dimensions

Standard HTTP client conventions usually provide the following dimensions; read `availableTags` to confirm the actual set for your project/version:

| Tag | Meaning to Keep Clear |
| --- | --- |
| `method` | HTTP method, such as GET |
| `uri` | Preserved URI template, or fallback when no template is available |
| `client.name` | Target host name per convention, not automatically the client bean name or business service name |
| `status` | Response status code when available; may have special labels when no response could be read |
| `outcome` | Result group derived from response, or unknown |
| `exception` | Exception type info per observation context/convention, not the full error message |

Other handlers or configurations can add labels such as `error` and common tags. Do not force every app to have only those six tags. `client.name=inventory.example` in the lab is the mock URI's host; it does not automatically become a business name like "warehouse."

Receiving no HTTP response differs from receiving HTTP 503. Special labels such as `CLIENT_ERROR` or `IO_ERROR` are observation-layer conventions, not numeric HTTP codes or proof that the server returned an HTTP 4xx. [Framework 6.1.21 synchronous convention](https://github.com/spring-projects/spring-framework/blob/v6.1.21/spring-web/src/main/java/org/springframework/http/client/observation/DefaultClientRequestObservationConvention.java).

`RestTemplate`/`RestClient` use conventions in `org.springframework.http.client.observation`; `WebClient` uses the convention interface in `org.springframework.web.reactive.function.client`. When customizing, do not register a bean for one side's interface and assume the other side uses it too.

### 5.3. Reading Measurements and Filtering the Right Group

Because this is a timer, COUNT, TOTAL_TIME, and MAX are typically present. COUNT of completed samples is not calls per second; duration fields must be read with the reported unit. Do not use a client timer as the total duration of an entire business transaction.

You can filter by actual tags, for example:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/http.client.requests --data-urlencode "tag=client.name:inventory.example" --data-urlencode "tag=uri:/items/{id}" --data-urlencode "tag=status:200"
```

All three tag parameters apply together. Calling a metric name with multiple tag sets can return aggregated data; without filtering, one COUNT can combine multiple hosts, methods, or outcomes.

A client's bean name or Java type is not automatically a distinguishing tag. Two different clients with the same standard labels can record into the same timer group. During verification, compare before-and-after deltas per phase or use a meaningful low-cardinality convention; do not put Java object IDs into tags.

## 6. Verification Program Testing All Three Builders Without Networking

The experiment creates a Spring application context with Boot auto-configuration and retrieves the builders from the context. `MockRestServiceServer` supplies responses for the two synchronous clients; `exchangeFunction` supplies in-memory responses for WebClient.

There is no real DNS/TLS/server in the experiment. It verifies the wiring builder -> observation -> meter, URI templates, and execution timing; it does not measure network performance, transport-level retries, connection pools, or real inventory service latency.

Create a Gradle project with a wrapper and JDK 17 available:

```text
managed-http-client-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/example/client/ManagedHttpClientDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'managed-http-client-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework:spring-webflux'
    implementation 'org.springframework:spring-test'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    implementation 'org.hamcrest:hamcrest'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.client.ManagedHttpClientDemo'
}
```

Boot 3.3.13's BOM keeps libraries on the verified version set; do not mix older Spring Framework/Micrometer versions with a different BOM and expect identical measurement lifecycle details.

`spring-test` and Hamcrest are in `implementation` **only because this is a verification `main` program** using mock utilities. In a production project, these test utilities belong in test scope; do not add them to runtime just to enable metrics. `httpclient5` provides a request factory for the synchronous client build path in the experiment; actual responses are still replaced by the mock factory before calling.

`src/main/java/example/client/ManagedHttpClientDemo.java`:

```java
package example.client;

import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

public class ManagedHttpClientDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class DemoConfiguration {
        @Bean
        ClientHttpConnector noNetworkConnector() {
            return (method, uri, callback) -> Mono.error(
                new AssertionError("A real connection must not be used in this demo"));
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("demo", Map.of(
                "management.metrics.use-global-registry", false)));
        context.register(DemoConfiguration.class);
        context.refresh();

        try {
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            require(count(registry) == 0, "No client calls yet");

            RestClient.Builder managedBuilder =
                context.getBean(RestClient.Builder.class).clone();
            MockRestServiceServer managedServer =
                MockRestServiceServer.bindTo(managedBuilder).build();
            managedServer.expect(requestTo("https://inventory.example/items/7"))
                .andRespond(withSuccess("item-7", MediaType.TEXT_PLAIN));
            managedServer.expect(requestTo("https://inventory.example/items/8"))
                .andRespond(withSuccess("item-8", MediaType.TEXT_PLAIN));
            managedServer.expect(requestTo("https://inventory.example/items/9"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

            RestClient managed = managedBuilder.build();
            require("item-7".equals(managed.get()
                .uri("https://inventory.example/items/{id}", 7)
                .retrieve().body(String.class)), "First body");
            require("item-8".equals(managed.get()
                .uri("https://inventory.example/items/{id}", 8)
                .retrieve().body(String.class)), "Second body");
            require(count(registry, "status", "200") == 2, "Two successful calls");
            System.out.println("restClient.success=" + count(registry, "status", "200"));

            try {
                managed.get().uri("https://inventory.example/items/{id}", 9)
                    .retrieve().body(String.class);
                throw new AssertionError("Expected HTTP 503");
            }
            catch (RestClientResponseException exception) {
                require(exception.getStatusCode().value() == 503, "Expected 503");
            }
            managedServer.verify();
            require(count(registry, "status", "503") == 1, "503 recorded");
            require(count(registry, "uri", "/items/{id}") == 3,
                "One URI template for all three calls");
            System.out.println("restClient.status503="
                + count(registry, "status", "503"));
            System.out.println("restClient.templateCalls="
                + count(registry, "uri", "/items/{id}"));

            long beforeRaw = count(registry);
            RestClient.Builder rawBuilder = RestClient.builder();
            MockRestServiceServer rawServer =
                MockRestServiceServer.bindTo(rawBuilder).build();
            rawServer.expect(requestTo("https://inventory.example/items/20"))
                .andRespond(withSuccess("raw", MediaType.TEXT_PLAIN));
            require("raw".equals(rawBuilder.build().get()
                .uri("https://inventory.example/items/{id}", 20)
                .retrieve().body(String.class)), "Raw body");
            rawServer.verify();
            require(count(registry) == beforeRaw, "Raw builder has no Boot observation setup");
            System.out.println("raw.added=" + (count(registry) - beforeRaw));

            RestTemplate template = context.getBean(RestTemplateBuilder.class)
                .requestFactory(SimpleClientHttpRequestFactory.class)
                .rootUri("https://inventory.example")
                .build();
            MockRestServiceServer templateServer =
                MockRestServiceServer.bindTo(template).build();
            templateServer.expect(requestTo("https://inventory.example/items/30"))
                .andRespond(withSuccess("template", MediaType.TEXT_PLAIN));
            long beforeTemplate = count(registry);
            require("template".equals(template.getForObject(
                "/items/{id}", String.class, 30)), "RestTemplate body");
            templateServer.verify();
            require(count(registry) == beforeTemplate + 1, "RestTemplate observation");
            System.out.println("restTemplate.added="
                + (count(registry) - beforeTemplate));

            WebClient web = context.getBean(WebClient.Builder.class).clone()
                .baseUrl("https://inventory.example")
                .exchangeFunction(request -> Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header("Content-Type", "text/plain")
                    .body("reactive").build()))
                .build();

            long beforeReactive = count(registry);
            Mono<String> pending = web.get().uri("/items/{id}", 40)
                .retrieve().bodyToMono(String.class);
            require(count(registry) == beforeReactive, "Assembly is not execution");
            System.out.println("webClient.beforeSubscribe="
                + (count(registry) - beforeReactive));

            require("reactive".equals(pending.block()), "First subscription");
            require(count(registry) == beforeReactive + 1, "First observation");
            System.out.println("webClient.afterSubscribe="
                + (count(registry) - beforeReactive));

            require("reactive".equals(pending.block()), "Second subscription");
            require(count(registry) == beforeReactive + 2, "Second observation");
            System.out.println("webClient.afterSecondSubscribe="
                + (count(registry) - beforeReactive));

            require(count(registry) == 6, "Expected six observed exchanges");
            System.out.println("observed.total=" + count(registry));
            System.out.println("OBSERVATION_PASS");
        }
        finally {
            context.close();
        }
    }

    private static long count(MeterRegistry registry, String... tags) {
        return registry.find("http.client.requests").tags(tags).timers()
            .stream().mapToLong(Timer::count).sum();
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run from the project directory:

```bash
./gradlew -q run --console=plain
```

On Windows PowerShell use `.\gradlew.bat -q run --console=plain`. Dependency classes are resolved by Gradle; if using `javac`/`java` directly, the full classpath must be supplied in both steps.

Experiment output on the version set listed at the start:

```text
restClient.success=2
restClient.status503=1
restClient.templateCalls=3
raw.added=0
restTemplate.added=1
webClient.beforeSubscribe=0
webClient.afterSubscribe=1
webClient.afterSecondSubscribe=2
observed.total=6
OBSERVATION_PASS
```

### 6.1. Three RestClient Calls and One URI Template

The first two calls receive HTTP 200; the third receives 503 and goes through `retrieve()`'s error-throwing mechanism. The test catches the exception so the program continues, while confirming the `status=503` group still gets one sample.

All three URLs with IDs 7, 8, and 9 are invoked with template `/items/{id}`, so filtering by that uri counts 3. Catching the exception in caller code does not erase the recorded observation sample. Still, specific exception tags depend on where errors are attached to the observation context; do not use the exception tag alone as a substitute for all error classification.

### 6.2. A Manually Created Client Still Returns Content Yet Adds No Sample

The `rawBuilder` client still receives the mock response and returns `"raw"`, yet it was not built from Boot's builder and did not automatically apply customizers. `raw.added=0` proves that a successful call does not imply metrics are wired to the inspected registry.

This is a controlled baseline comparison, not a rule that directly created APIs can never be observed. They can be configured manually with an equivalent ObservationRegistry/customizer; that configuration would then need to be verified separately.

### 6.3. Customizing RestTemplate Preserves Retained Setup

RestTemplate is obtained from the context's `RestTemplateBuilder` and then given a root URI and request factory. It still adds one sample when called. What matters is keeping the builder source and customizer path, not avoiding all client customization.

### 6.4. WebClient Is Counted by Execution

Before subscription, the delta is 0. Two `block()` calls in `main` trigger two subscriptions to the cold pipeline, yielding deltas of 1 and 2 respectively.

The `noNetworkConnector` bean makes any real network connection in the experiment fail; `exchangeFunction` supplies the mock response. This setup is strictly for verification and does not belong in production client configuration.

### 6.5. Total of 6 Is the Verified Sample Count, Not a Constant for All Apps

```text
RestClient:   2 x 200 samples + 1 x 503 sample = 3
RestTemplate: 1 sample                         = 1
WebClient:    2 subscriptions                  = 2
Raw client:   not wired to measurement         = 0
Total observed                                 = 6
```

`OBSERVATION_PASS` means the experiment's assertions passed on the stated configuration. It does not prove every HTTP call in another application is observed, or that tracing/exporters are configured.

## 7. Boundaries to Understand Before Using the Data

### 7.1. Observation Does Not Configure Timeouts or Retries

Having a timer does not mean the client has suitable time limits. Timeouts, request factories/connectors, pools, retries, and error-handling policies are related but independent configurations.

Execution layers can handle multiple attempts differently. For example, re-subscribing a WebClient pipeline re-executes the observation; a hidden transport-level retry does not automatically correspond to the same counting behavior. To understand sample counts, check which layer retries and what scope the observation wraps.

### 7.2. Client Duration Is Not Every Kind of "Latency"

Timer samples complete according to the client's observation lifecycle and API usage. With streaming responses, body reading/closing and cancellation affect resource lifecycles; do not assume a single figure always covers full business processing or every byte of every body type.

Ordinary calls in this lesson use `body(String.class)`/`getForObject()`/`bodyToMono()` and collect the result for a clear execution flow. If using lower-level APIs like exchange or returning unconsumed responses, manage lifecycles per the API contract and verify the corresponding signals.

### 7.3. Metrics and Traces Are Different Evidence

Missing traces can relate to tracing handlers, sampling, context propagation, or exporters; do not try to fix that by adding more counters. Seeing `http.client.requests` also does not verify that trace context was propagated to the target.

Headers containing credentials, full URLs, and user data should not be turned into tags just to debug individual calls. Keep metric dimensions bounded and use detailed diagnostic sources appropriate to the application's data policy.

## 8. When http.client.requests Is Missing

| Item to Check | Concrete Question |
| --- | --- |
| Client source | Was the client actually built from Boot's injected builder, or created via a static/new API in another branch? |
| Auto-configuration and dependencies | Does the client/builder type actually exist in the current context? Are auto-configuration conditions satisfied? |
| ObservationRegistry and handler | Is the registry active with a metrics handler, or was it replaced by NOOP? |
| Actual execution | For WebClient, has it been subscribed to? Did code only construct a Mono and leave it unused? |
| Call lifecycle | Has the call reached observation completion? Is a response/stream still open? |
| Metric name | Was `management.observations.http.client.requests.name` changed? |
| Filters/predicates | Were observations or meters denied by configuration? Was the URI tag limit exceeded? |
| Inspected registry | Do metrics go to the application registry used by the endpoint, or is a different registry being checked? |
| HTTP endpoint | Is this an authorization/web-exposure path issue rather than a missing meter? |

Do not add `@Timed` to every method or a custom timing interceptor as a first fix. That can create a measurement with a different boundary or make data harder to interpret when the real cause was simply the wrong builder or a missing subscription.

In reactive applications, auto-configuration conditions for synchronous clients can differ from non-reactive applications. Do not assume merely adding a builder type to a constructor signature guarantees Spring provides it in every application type. Verify actual beans and conditions.

## 9. When Sample Count Exceeds Expected Calls

First verify actual executions: a pipeline subscribed multiple times, application retries, a business operation calling multiple downstreams, or the same test executed repeatedly. Then check whether extra instrumentation or duplicate handlers were registered.

Finally, verify the exact Boot/Framework/Micrometer patch versions with a small test having controlled responses. Observation lifecycle details can differ across patch versions; do not divide COUNT by 2 or drop samples with a filter just to match a desired number without finding the cause.

The lesson's example pins the version set and checks deltas after each phase. If changing configuration or versions breaks an assertion, investigate the reason before changing expected counts. Keep Boot's aligned dependency management rather than upgrading or downgrading a single library to bypass a test result.

## 10. Self-Check

1. A `RestClient` is declared as a bean, yet inside the factory method it uses `RestClient.create()`. Why can you not claim it has Boot's observation configuration?
2. Write how to build each client type from its respective builder; state when you must keep the returned builder or create a clone.
3. Replace template `/items/{id}` with string concatenation of the ID and inspect the uri tag. What can happen to label combinations?
4. Construct a WebClient Mono without returning it to the framework, subscribing, or blocking. Should you expect an outbound request sample to appear?
5. In synchronous `main`, subscribe to the same cold pipeline twice. Why can two samples appear even though the Mono variable was created only once?
6. A call receives 503 and caller code catches the exception. Explain why you still need to check status/outcome and should not assume the error sample was deleted.
7. If `http.server.requests` exists but `http.client.requests` does not, which boundaries will you inspect before adding manual instrumentation?
8. Why does a populated client timer not yet prove timeouts, retries, tracing, and exporters are all configured properly?

Reliable HTTP client observation starts from **a properly sourced builder, real execution flow, controlled URI templates, and phase-by-phase sample verification**, before using the data to investigate the system.
