# Propagating Traces Through RestTemplateBuilder, RestClient.Builder, and WebClient.Builder

## 1. Why Does HTTP Succeed While the Trace Still Breaks?

Suppose the `checkout` service calls the `inventory` service to check stock. The HTTP response returns the right data, yet the tracing system shows two separate traces: one for checkout, one for inventory.

The cause may be that **trace context was not propagated across the HTTP call**. Context propagation means taking the current trace's information, writing it into the outbound request headers, and letting the receiving service read that information to attach its processing to the same trace.

Desired flow:

~~~text
checkout: receive request
└── checkout: HTTP call to inventory
    └── inventory: handle received request
~~~

In a Spring Boot 3.3 application using Micrometer Tracing, the standard approach is creating HTTP clients from **builders auto-configured by Spring Boot**:

- `RestTemplateBuilder` for `RestTemplate`.
- `RestClient.Builder` for `RestClient`.
- `WebClient.Builder` for `WebClient`.

Spring Boot instructs using these builders to obtain network trace propagation integration. If you construct clients manually and bypass the corresponding configuration, automatic propagation is not wired through this integration path. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.propagating-traces).

An HTTP client executing a request and an HTTP client wired into the tracing mechanism are two separate things to verify.

## 2. Mechanism from Observation to HTTP Headers

### 2.1. Role of the Builders

Builders supplied by Boot have already received the required customizers. When building a client, the observation customizers connect the client to the application's `ObservationRegistry` and the corresponding HTTP observation conventions.

Actuator's customizers include:

| Client | Observation Customizer |
| --- | --- |
| RestTemplate | `ObservationRestTemplateCustomizer` |
| RestClient | `ObservationRestClientCustomizer` |
| WebClient | `ObservationWebClientCustomizer` |

These APIs configure client observation recording. [RestTemplate customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/client/ObservationRestTemplateCustomizer.html), [RestClient customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/client/ObservationRestClientCustomizer.html), [WebClient customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/reactive/client/ObservationWebClientCustomizer.html).

When the application has matching tracing configuration, the tracing handler uses the client context to create a span and inject propagation metadata into the HTTP request.

~~~text
Boot-configured builder
        |
        v
HTTP client uses the application's ObservationRegistry
        |
        v
HTTP call creates a client-side observation
        |
        v
Tracing handler creates span and writes context header
        |
        v
Receiving service reads header, creates server-side span
~~~

Builders are not standalone trace generators and senders. The registry, tracing bridge, handlers, and receiver-side configuration must still be active.

### 2.2. Trace ID Stays the Same; Span ID Changes per Unit of Work

A typical structure:

~~~text
Trace T
├── server span S1 at checkout
│   └── client span S2 at checkout
│       └── server span S3 at inventory
~~~

The three spans share trace ID `T` yet have different span IDs.

With W3C Trace Context, the request from checkout to inventory carries a header like:

~~~http
traceparent: 00-11111111111111111111111111111111-2222222222222222-01
~~~

These are **structure-illustrating values**, not a fixed header to put into configuration:

- `1111...` is the trace ID.
- `2222...` is the span ID of the sender propagating context, which in the diagram is client span S2.
- The inventory service creates a new server span S3; it does not reuse S2's span ID as its own span ID.
- Flag `01` has the sampled bit set; it is not confirmation that data was saved in the backend.

Header format and field relationships are defined by W3C Trace Context. [W3C Trace Context](https://www.w3.org/TR/trace-context/).

Do not expect span IDs in both services' logs to be identical. What needs to match are the trace ID and the parent-child relationship.

## 3. Conditions for Trace Propagation to Work

| Condition | Meaning |
| --- | --- |
| Client receives observation configuration | Calls are wired into the appropriate registry |
| Tracing bridge and corresponding handlers exist | Observations can participate in the tracing mechanism |
| Right parent context exists at execution time | Calls attach to the active trace rather than becoming a separate root branch |
| Compatible produce/consume formats | Headers written by the caller are understood by the receiver |
| Receiving service has server-side observation integration | Incoming requests join the trace |
| Working trace export path | Data can be searched on the Collector/backend |

If a call originates from a task with no parent trace, the client can still start a new trace per configuration. That is not automatically an error; compare against the intended processing boundaries.

If HTTP observations exist without a tracing handler, the application can record metrics without writing trace headers. Conversely, outbound headers do not prove data was exported to the backend.

### 3.1. Dependencies and Client Libraries

The integration examples below assume an existing Spring Boot 3.3 application:

- `RestTemplate` and `RestClient` require Spring Web on the classpath.
- `WebClient` requires Spring WebFlux along with an appropriate HTTP client connector.
- Actuator and a compatible tracing setup are already installed.
- The registry and corresponding builders are managed by Spring.

In Boot 3.3, RestTemplate and RestClient auto-configuration is conditional on not being a reactive web application. Therefore, in a WebFlux application, do not assume both blocking builders are present merely because Spring Web was added. Pick the matching client branch and verify which beans are active. [RestTemplateAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestTemplateAutoConfiguration.html), [RestClientAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html).

Example tracing dependency set using OpenTelemetry and exporting to Zipkin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

This is the tracing addition for an existing application; it does not automatically supply all libraries for all three HTTP clients. For WebClient, you can use the WebFlux starter to bring in the library and connector; keep the server architecture choice consistent with the application.

Corresponding test configuration:

~~~properties
spring.application.name=checkout
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
~~~

The endpoint address is resolved from where the JVM runs. This configuration is only one export path example; HTTP context propagation does not require every application to choose Zipkin.

## 4. Creating Three Clients from Injected Builders

### 4.1. Client Configuration

The `InventoryClients.java` example below is a **configuration class integrated into a Boot application**, not a standalone program. The example targets a Servlet application with all required libraries and all three builders available. When using only one client type, keep only the needed part; do not assume this entire class applies as-is to every WebFlux application.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryClients {
    @Bean
    RestTemplate stockTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://inventory:8081").build();
    }

    @Bean
    RestClient stockRestClient(RestClient.Builder builder) {
        return builder.baseUrl("http://inventory:8081").build();
    }

    @Bean
    WebClient stockWebClient(WebClient.Builder builder) {
        return builder.baseUrl("http://inventory:8081").build();
    }
}
~~~

Spring injects the builder parameters into the `@Bean` methods. Adding the base URL still builds upon the Boot-configured builder.

The address `http://inventory:8081` is a deployment-network service name example. When testing on a local machine, replace it with an address reachable by the JVM. In real applications, place target service addresses in environment configuration.

Spring Boot provides `WebClient.Builder` and `RestClient.Builder` with prototype scope so each injection point receives a customizable builder. [Spring Boot 3.3: Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html).

### 4.2. RestTemplate: Synchronous Execution via the Built Client

Method example inside a component injected with the `stockTemplate` bean:

~~~java
String available = stockTemplate.getForObject(
        "/stock/{sku}", String.class, "SKU-1");
~~~

`rootUri` from the builder is used with relative paths starting with `/`. Keep the URI template `/stock/{sku}` rather than concatenating every product ID into one URL string when URI variables can be used.

RestTemplate blocks the calling thread until the operation completes. If the call runs inside the scope of an active HTTP request or business observation, the tracing mechanism can link the client span to that context.

### 4.3. RestClient: Synchronous Call Chain

With the `stockRestClient` bean:

~~~java
String available = stockRestClient.get()
        .uri("/stock/{sku}", "SKU-1")
        .retrieve()
        .body(String.class);
~~~

This is also a blocking call. Complete reading the response in the manner appropriate for the API used; do not leave a response object unfinished and assume the operation was handled completely.

The type `RestClient.Builder` can be confused with `RestClient.builder()`: the Spring-injected parameter carries Boot configuration, whereas calling the static method to create a new builder does not automatically pick up the application's customizers.

### 4.4. WebClient: Returning Mono in Reactive Flows

Method example inside a component injected with the `stockWebClient` bean:

~~~java
import reactor.core.publisher.Mono;

public Mono<String> available(String sku) {
    return stockWebClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(String.class);
}
~~~

This is an integration method snippet, not a standalone executable Java file.

In WebFlux, return `Mono` so the framework performs the subscription within the request processing pipeline. Merely constructing a `Mono` object usually does not execute the network call yet. Thus, chain assembly time and HTTP dispatch time can differ.

Do not call `subscribe()` manually inside a service just to "force sending the trace" when the method can return the reactive chain to the caller. A detached subscription can sever lifecycle, error handling, and context from the active request.

In a blocking environment, there may be an explicitly designed `block()` call site. Never place blocking calls onto WebFlux's non-blocking processing threads.

### 4.5. Customizing from an Existing Builder

`RestTemplateBuilder` has an immutable-style API that returns a new builder. Make sure to use the result of customization calls:

~~~java
RestTemplate client = builder
        .rootUri("http://inventory:8081")
        .build();
~~~

`RestClient.Builder` and `WebClient.Builder` are stateful builders. If you need multiple variants from a retained builder, clone the builder to isolate changes. Do not share a builder being mutated concurrently across threads.

Once a client is built, reuse the client according to the application design; do not construct a new builder/client per request just to get a new trace ID.

## 5. Ways Observation Configuration Gets Lost

The following expressions construct a client/builder outside Boot's configuration:

~~~java
new RestTemplate();
RestClient.builder().build();
WebClient.builder().build();
WebClient.create();
~~~

They do not automatically receive customizers merely because the code runs inside a Spring Boot application.

You can manually configure the registry and related components when building custom infrastructure. However, that is an explicit configuration task, not automatic behavior of the expressions above.

### 5.1. Using @Bean Does Not Automatically Add All Configuration

Example:

~~~java
@Bean
RestTemplate stockTemplate() {
    return new RestTemplate();
}
~~~

Registering an object as a bean does not mean it was built through Boot's `RestTemplateBuilder`. Check how the object is instantiated.

Similarly, declaring a custom builder bean that replaces the default builder can lose customizers unless you apply them. When you only need to add shared configuration, consider the appropriate extension points such as `RestTemplateCustomizer`, `RestClientCustomizer`, or `WebClientCustomizer` instead of rebuilding the entire builder.

### 5.2. Do Not Store a Shared Hardcoded traceparent

Do not place a fixed `traceparent` value into `defaultHeader` on a shared client.

Headers must be generated from each execution's context. A value saved from an earlier request can tie unrelated transactions into the same trace or corrupt span relationships under concurrency.

Also do not simply copy the received `traceparent` header verbatim onto every outbound request and treat that as equivalent to client integration. When a client span exists, the propagated span ID portion must reflect that corresponding client span.

### 5.3. Do Not Re-Wrap HTTP Just to Manually Write Headers

If the client is already observed and tracing is active, do not add a custom interceptor generating trace IDs or a duplicate-purpose observation solely to write headers.

A business observation with its own boundary can be useful, yet it should add domain meaning. The client mechanism still handles HTTP observation and context propagation.

## 6. WebClient and Context When Switching Threads

### 6.1. Execution Time Matters More Than Code Location

Example of a design bug:

~~~text
Open a scope on thread A
    |
    v
Only construct a Mono
    |
    v
Close the scope
    |
    v
Mono is subscribed later on thread B
~~~

You cannot assume thread A's `ThreadLocal` context is still active when HTTP is sent on thread B.

In reactive chains, Reactor Context bound to the subscription is the key context mechanism. When bridging between `ThreadLocal` and Reactor Context, use an appropriate context propagation mechanism. [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/).

### 6.2. Automatic Configuration for ThreadLocal/Reactor Interop

Spring Boot 3.3 provides the property:

~~~properties
spring.reactor.context-propagation=auto
~~~

It enables automatic context restoration via the corresponding Reactor integration. By default, not every `ThreadLocal` value is automatically restored inside reactive operators. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This is not a property that turns every executor, manually spawned thread, or detached subscription into the same trace. Corresponding context propagation components and proper execution boundaries are still required.

Reactor provides `contextCapture` to capture registered `ThreadLocal` values at subscription time and place them into Reactor Context. Do not mistake it for capturing context at code-writing or chain-assembly time. [Reactor: Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).

For services returning `Mono` to WebFlux, prefer keeping the processing chain continuous and verifying trace relationships at subscription time. Do not fix context loss by pre-setting an old trace's header.

### 6.3. RestTemplate/RestClient Can Also Lose Context When Switching Threads

The two synchronous clients do not automatically solve context propagation from outer work when code is dispatched onto a new executor.

If you spawn a thread and call the client there, check whether context is transferred to that thread. A properly configured builder can still create a client span belonging to a new trace if the intended parent context was lost before the call.

## 7. Check Context Propagation Formats on Both Ends

Having the right builder is not enough if the caller's and receiver's header formats are incompatible.

Example configuration for a system consuming multiple formats while producing W3C:

~~~properties
management.tracing.propagation.consume=W3C,B3,B3_MULTI
management.tracing.propagation.produce=W3C
~~~

Actual settings must align with neighboring services. If using the unified `management.tracing.propagation.type` property, remember it can override the corresponding granular consume/produce settings.

Sharing the same Collector or backend does not automatically connect traces whose context was not propagated properly. Sending spans to a backend and transmitting headers on business calls are two separate data paths.

Also separate sampling from context propagation. A trace not selected for full recording can still propagate context; failing to find a trace in the UI does not prove HTTP lacked headers.

## 8. Runnable Experiment: Verifying Clients Receive Observation Configuration

### 8.1. Scope of Evidence

The experiment uses Spring Boot **3.3.0**, Spring Framework **6.1.8**, and Micrometer Observation **1.13.0**. The code was compiled with `javac --release 17` and run on JDK 21.

It directly tests Actuator's two customizers for blocking clients:

- `RestTemplateBuilder` after receiving `ObservationRestTemplateCustomizer`.
- `RestClient.Builder` after receiving `ObservationRestClientCustomizer`.
- A manually constructed `RestTemplate` as a control case.

Requests are answered by `MockRestServiceServer` without opening network ports. This tool supports binding to both `RestTemplate` and `RestClient.Builder`. [MockRestServiceServer 6.1.8 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html).

**The experiment verifies client observation startup and parent observation relationships. It does not install a tracing bridge, does not verify `traceparent` headers, does not test WebClient, and does not send traces to a backend.** The WebClient configuration above is an integration example per API and documentation; full end-to-end verification requires the steps in section 9.

We configure the customizers directly to show their effect clearly. In a normal Boot application, use the injected builders as in section 4.

### 8.2. Dependencies

Create `pom.xml` for the standalone experiment:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>builder-observation-probe</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

`spring-test` is on the program's classpath because `main` itself uses the test utility. In a normal application, test libraries belong in the appropriate test scope.

### 8.3. Complete Java Code

Save `BuilderObservationProbe.java` next to `pom.xml`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.actuate.metrics.web.client.ObservationRestClientCustomizer;
import org.springframework.boot.actuate.metrics.web.client.ObservationRestTemplateCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.observation.ClientRequestObservationContext;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

public class BuilderObservationProbe {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        Recorder recorder = new Recorder();
        registry.observationConfig().observationHandler(recorder);
        var convention = new DefaultClientRequestObservationConvention();

        RestTemplate template = new RestTemplateBuilder(
                new ObservationRestTemplateCustomizer(registry, convention)).build();
        MockRestServiceServer templateServer = MockRestServiceServer.bindTo(template).build();
        expectStock(templateServer);
        measure("RestTemplateBuilder", registry, recorder,
                () -> template.getForObject(
                        "http://inventory.test/stock/{sku}", String.class, "SKU-1"));
        templateServer.verify();

        RestClient.Builder builder = RestClient.builder();
        new ObservationRestClientCustomizer(registry, convention).customize(builder);
        MockRestServiceServer clientServer = MockRestServiceServer.bindTo(builder).build();
        RestClient client = builder.build();
        expectStock(clientServer);
        measure("RestClient.Builder", registry, recorder,
                () -> client.get().uri("http://inventory.test/stock/{sku}", "SKU-1")
                        .retrieve().body(String.class));
        clientServer.verify();

        RestTemplate raw = new RestTemplate();
        MockRestServiceServer rawServer = MockRestServiceServer.bindTo(raw).build();
        expectStock(rawServer);
        measure("new RestTemplate", registry, recorder,
                () -> raw.getForObject(
                        "http://inventory.test/stock/{sku}", String.class, "SKU-1"));
        rawServer.verify();
    }

    private static void expectStock(MockRestServiceServer server) {
        server.expect(request -> {
            if (request.getMethod() != HttpMethod.GET
                    || !"http://inventory.test/stock/SKU-1".equals(request.getURI().toString())) {
                throw new AssertionError("Unexpected request");
            }
        }).andRespond(withSuccess("8", MediaType.TEXT_PLAIN));
    }

    private static void measure(String label, ObservationRegistry registry,
            Recorder recorder, Supplier<String> call) {
        recorder.parents.clear();
        String body = Observation.createNotStarted("business.checkout", registry)
                .observe(call);
        String parent = recorder.parents.isEmpty() ? "none" : recorder.parents.get(0);
        System.out.println(label + " body=" + body + " clientStarted="
                + recorder.parents.size() + " parent=" + parent);
    }

    static class Recorder implements ObservationHandler<Observation.Context> {
        final List<String> parents = new ArrayList<>();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            if (context instanceof ClientRequestObservationContext) {
                parents.add(context.getParentObservation() == null ? "none"
                        : context.getParentObservation().getContextView().getName());
            }
        }
    }
}
~~~

`Recorder` captures the `onStart` callback of the HTTP client context. The `clientStarted` field in stdout is the number of starts recorded per trial, not the number of exported traces.

The calls run synchronously and sequentially. The list inside `Recorder` only serves the experiment, not as a collection structure for concurrent requests in a real environment.

### 8.4. Compile and Run

PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out BuilderObservationProbe.java
java -cp "out;lib/*" BuilderObservationProbe
~~~

Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out BuilderObservationProbe.java
java -cp "out:lib/*" BuilderObservationProbe
~~~

The first run requires downloading dependencies if not already cached locally.

### 8.5. Verified Stdout

~~~text
RestTemplateBuilder body=8 clientStarted=1 parent=business.checkout
RestClient.Builder body=8 clientStarted=1 parent=business.checkout
new RestTemplate body=8 clientStarted=0 parent=none
~~~

The output shows:

- Both customized clients emit HTTP client observations into the designated registry.
- The client observation receives `business.checkout` as its parent during synchronous execution.
- The same response `8` is still returned with `new RestTemplate()`, yet no client observation occurs in the experiment's registry. `parent=none` on this line means there was no client record from which to read a parent, not that the business observation wasn't opened for the trial.
- HTTP data success does not automatically confirm observation/tracing success.

You do not need a running backend to verify this registry-wiring step. However, to conclude that traces propagated over HTTP and were linked into the same trace by the downstream service, the checks below are still required.

## 9. Verifying End-to-End Trace Propagation for All Three Clients

### 9.1. Two-Service Scenario

Prepare a clear flow:

~~~text
Test request
        |
        v
checkout
        |
        | using one of the three clients in turn
        v
inventory
~~~

Run three independent trials with the same business operation:

1. Checkout calls using a `RestTemplate` built from the injected builder.
2. Checkout calls using a `RestClient` built from the injected builder.
3. Checkout calls using a `WebClient` built from the injected builder and executed in an appropriate chain/subscription.

Ensure both checkout and inventory have server-side observation, tracing, and compatible context propagation formats. Do not treat installing tracing only on the caller side as complete configuration for the entire system.

### 9.2. Three Check Levels

| Level | What to Observe | Conclusion That Can Be Drawn |
| --- | --- | --- |
| 1. Client integration | Client-side observation exists in the right registry | Client is wired into the observation mechanism |
| 2. HTTP headers | Request to inventory carries valid context headers in the chosen format | HTTP hop carries context |
| 3. Receiver-side trace | Inventory's server span shares the trace ID and links properly to the client span | Receiving service joined processing into the intended trace |

Only after that should you verify the backend received and stored data for querying. Logs with a trace ID or present headers are not confirmation that the exporter succeeded in sending.

With W3C, compare the trace IDs of S1/S2/S3 and the S1 → S2 → S3 relationship. Do not expect all three span IDs to match.

### 9.3. Additional Scenarios to Test

- A successful call.
- An HTTP error response handled per application design.
- A connection failure or timeout case.
- `WebClient` subscribed on a real reactive flow.
- Cases switching executors/threads if the application does so.
- Concurrent trials to catch stale headers/contexts retained from earlier requests.

If using Spring Boot tests, understand how observability is configured for that test slice/type. Do not assume all export components are enabled identically to running the real application.

### 9.4. URI Templates Aid Metric and Trace Readability

Prefer calls with stable templates:

~~~java
client.get()
        .uri("/stock/{sku}", sku)
        .retrieve()
        .body(String.class);
~~~

Variable parts are passed via URI variables. This keeps operation-type semantics clearer and supports observation conventions that use URI templates.

Do not set observation names or metric tags using trace IDs, order IDs, or URLs containing every identifier. Tracing headers serve context correlation, not tags for splitting metrics per transaction.

## 10. Diagnosing Broken Traces

| Symptom | Check First | Resolution |
| --- | --- | --- |
| HTTP succeeds yet no client observation | How client was created and registry | Use injected builder; verify customizers were not bypassed |
| Client observation exists yet no tracing header | Tracing bridge/handlers and produce format | Check tracing configuration, not just metrics |
| Header reaches inventory yet inventory starts a separate trace | Consume format and server-side integration | Check `consume`, valid headers, and extraction mechanism |
| WebClient has not sent the request yet | Has `Mono` been subscribed? | Keep execution chain intact; do not use detached `subscribe()` to fix context |
| WebClient has client span yet unexpected parent | Context at subscription time | Check Reactor Context, `ThreadLocal`, and thread-switching boundaries |
| RestTemplate/RestClient loses parent after switching executor | Context on the thread executing the call | Use an appropriate context propagation mechanism for the executor |
| Two unrelated requests share a manually set header | Default headers or state held in a singleton | Remove fixed tracing values; let tracing generate per call |
| Declared `@Bean` yet still lacks integration | How the bean was constructed | Distinguish bean registration from building via configured builder |
| Trace missing in UI despite valid context | Sampling, export path, and search filters | Separate header propagation checks from data persistence |
| Duplicate-purpose span layers appear | Overlapping interceptor/annotation/agent wrappers | Identify who owns instrumentation points before adding new wrappers |

An effective diagnostic sequence is: **how the client is built → client observation → parent context → outbound header → how receiver reads header → trace export and search**.

## 11. Self-Check Exercises

1. In an existing Boot application, locate where the three HTTP client types are created. Distinguish injected builders from builders created via static calls.
2. Run the experiment program and explain why all three calls return body `8` yet only two produce client observations in the configured registry.
3. Convert a client from `new RestTemplate()` to an injected builder. Verify observation, headers, and receiver-side trace in order.
4. For `WebClient`, pinpoint the exact place where subscription occurs. Explain what happens if the parent scope already closed before that point.
5. Inspect the W3C header at the receiving service and point out the trace ID field and sender span ID field. Compare with the receiver's new span ID.
6. Execute two concurrent requests and verify no single fixed `traceparent` is shared due to manual configuration.
7. If only logs at checkout have a trace ID, list the remaining steps missing before concluding inventory joined the trace and the backend stored the data.

Creating clients from Boot-configured builders preserves the observation integration path. Complete trace propagation also requires the right context at execution time, compatible headers, and working observation on the receiving service.
