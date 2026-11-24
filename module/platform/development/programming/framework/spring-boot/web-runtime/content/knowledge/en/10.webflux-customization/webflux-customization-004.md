# CodecCustomizer and Application-Level Codec Configuration in Spring WebFlux

## Learning Objectives

In Spring WebFlux, HTTP request and response bodies do not turn into Java objects automatically. The framework selects **HTTP message readers/writers** based on Content-Type, Accept, Java types, libraries on the classpath, and codec configurations. Spring Boot provides default configuration for this layer and lets you apply application properties or register **CodecCustomizer** beans to customize it.

After completing this lesson, you will be able to:

- Distinguish codecs, Encoder/Decoder, HttpMessageReader/HttpMessageWriter, and CodecConfigurer.
- Describe how Spring Boot combines default codecs, application properties, and CodecCustomizer beans.
- Choose appropriately among **spring.http.codecs.max-in-memory-size**, **CodecCustomizer**, **WebFluxConfigurer.configureHttpMessageCodecs**, and WebClient-specific configuration.
- Understand in-memory buffer limits, DataBufferLimitException, and limits not controlled by maxInMemorySize.
- Configure codecs without accidentally dropping JSON, text, form, multipart, or Server-Sent Events support.
- Build a Java 17+ WebFlux application with codec customization and test HTTP behavior with WebTestClient.
- Analyze 400, 406, 415 errors, JSON errors, and data-exposure risks when enabling codec logging.

## 1. Why Does WebFlux Need HTTP Codecs?

An HTTP request carries **metadata** such as method, path, and headers, along with a **body** as a stream of bytes. When a controller accepts a Java object from the request body, or returns an object to send as the response, WebFlux must convert the data.

For example, the client sends:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"text":"hello"}
~~~

The controller accepts a Java record Payload and returns a record. WebFlux must:

1. Use **Content-Type: application/json** and the Java type to select the right reader/decoder.
2. Read DataBuffers from the request body via Reactive Streams.
3. Decode JSON into a Payload instance.
4. Invoke the controller/service (which may return a Mono or Flux).
5. Use **Accept: application/json** and the response Java type to select the right writer/encoder.
6. Encode the object into bytes and write the HTTP response.

Diagram:

~~~text
HTTP request                           Spring WebFlux                      HTTP response
headers + Flux<DataBuffer>             request handling                   headers + bytes
         |                                    |                                    ^
         v                                    |                                    |
   HttpMessageReader                         |                             HttpMessageWriter
         |                                    |                                    ^
       Decoder                               |                                  Encoder
         |                                    |                                    ^
         v                                    v                                    |
     Java object ----------------> Controller/Handler -----------------> Java object/Publisher
~~~

Codecs **do not decide controller URLs** and do not replace validation, authentication, or exception handling. They handle body reading/writing, media types, serialization, and buffering when required.

## 2. Distinguishing the Concepts

| Component | Role | Example |
|---|---|---|
| Encoder<T> | Converts objects or sequences into byte data | Encode JSON, String, byte[] |
| Decoder<T> | Converts byte data into objects | Decode JSON, String, protobuf with a custom codec |
| HttpMessageReader<T> | Adapter reading request bodies by HTTP/media type | Reader for JSON, form |
| HttpMessageWriter<T> | Adapter writing response bodies by HTTP/media type | Writer for JSON, text, or SSE |
| CodecConfigurer | Registry and configuration point for codec groups | registerDefaults, defaultCodecs, customCodecs |
| ServerCodecConfigurer | CodecConfigurer for the WebFlux server side | Used in WebFluxConfigurer |
| ClientCodecConfigurer | CodecConfigurer for the WebClient HTTP client | Used with WebClient.Builder.codecs |
| CodecCustomizer | Spring Boot callback applied to CodecConfigurer | Adjust memory limits, register custom codecs |
| Jackson / JSON mapper | JSON serialization/deserialization engine | Convert JSON to Java records and vice versa |
| DataBuffer | Byte chunk abstraction in reactive I/O | Flux<DataBuffer> of a request body |

Simply put, think of **Decoder** as turning bytes into objects on the way in, and **Encoder** as turning objects into bytes on the way out. HttpMessageReader/Writer add HTTP context and choose matching codecs.

Libraries on the classpath affect codec capabilities. For example, lacking a compatible JSON library can prevent application/json requests from being handled as expected. Spring Boot usually manages the required dependencies when using the WebFlux starter.

**Do not confuse with MVC:** Spring MVC uses HttpMessageConverter in the Servlet stack; Spring WebFlux primarily uses HttpMessageReader/Writer and reactive codecs. Therefore, an MVC customizer is not automatically a WebFlux CodecCustomizer.

## 3. How Does Spring Boot Select and Customize Codecs?

For an auto-configured Spring WebFlux application, Spring Boot builds codec configuration from Spring Framework defaults and components on the classpath. Customizations can then be applied via:

- **Application properties** such as spring.http.codecs.max-in-memory-size and spring.http.codecs.log-request-details in supported versions.
- **CodecCustomizer beans** provided by Spring Boot or the application.
- **Jackson configuration** and modules/beans related to serialization/deserialization when the corresponding JSON mapper is used.
- **WebFluxConfigurer.configureHttpMessageCodecs** to customize reader/writer registration on the HTTP server side.
- **WebClient-specific codec configuration** for separately built or customized clients.

Model:

~~~text
Spring Boot WebFlux auto-configuration
            |
            +-- Spring Framework default codecs
            |       JSON, String, byte[], form, SSE ... based on classpath
            |
            +-- spring.http.codecs.* properties
            |
            +-- CodecCustomizer beans
            |       default codecs / custom codecs
            |
            +-- WebFlux server codec configuration
            |       HttpMessageReader / HttpMessageWriter
            |
            +-- WebClient auto-configuration (when applicable)
                    ClientCodecConfigurer / ExchangeStrategies
~~~

Spring Boot may provide its own customizers for the JSON mapper, buffer limits, or logging. If you add another customizer, consider whether multiple callbacks modify the same property; the final effective value depends on how the framework applies them and their order. Do not define conflicting configurations expecting one setting to always "win."

**Keep Boot auto-configuration:** If you only want to extend WebFlux, declare WebFluxConfigurer in a `@Configuration` class **without adding `@EnableWebFlux`**. `@EnableWebFlux` puts WebFlux configuration under direct Spring Framework control and can cause Boot's WebFlux auto-configuration conveniences to stop applying as before.

## 4. What Is CodecCustomizer?

**CodecCustomizer** is a Spring Boot callback that receives a CodecConfigurer and lets application code modify how codecs are configured. It is not a codec itself and does not directly read or write bodies; it **customizes the registry/configuration** when Spring Boot builds HTTP codec configuration.

### Package Differences Across Versions

The package of CodecCustomizer changes across Spring Boot generations. Do not copy imports from random blog posts when upgrading major versions.

| Spring Boot | Typical import | Notes |
|---|---|---|
| Spring Boot 3.5.x | org.springframework.boot.web.codec.CodecCustomizer | Used in the runnable example below |
| Spring Boot 4.x | org.springframework.boot.http.codec.CodecCustomizer | API reorganized by module/package |

Each project must use the import compatible with its version. Examples in this lesson focus on Java 17+ and Spring Boot **3.5.x** to keep code compilation consistent. If your project uses 4.x, check the matching Javadoc/BOM and update the import as shown in the table.

Declaring a bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CodecConfig {

    @Bean
    CodecCustomizer codecCustomizer() {
        return configurer ->
            configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
~~~

This is an abbreviated snippet requiring imports for `@Configuration`, `@Bean`, and `CodecCustomizer` matching your version. The value `1024 * 1024` is **1 MiB = 1,048,576 bytes**, not one million decimal bytes.

### When to Use CodecCustomizer?

Use it when you want Boot-level encoding/decoding configuration, such as:

- Adjusting the buffer aggregation limit for default codecs.
- Registering a specialized decoder/encoder or message reader/writer.
- Replacing default codec behavior when there is a genuine architectural requirement.
- Defining a callback that Boot can apply to the codec configuration it constructs.

Actual scope depends on Boot integration: a WebClient created manually with WebClient.builder() does not automatically receive all beans/configurations Boot applies to the WebFlux server or to Boot's WebClient.Builder. When debugging, identify exactly how the client or server was constructed.

## 5. Configuring via application.properties: The Simplest Way

If the requirement is simply to change the in-memory read/aggregation limit, prefer a **property** rather than writing an unnecessary custom Java bean.

In Spring Boot 3.5 and 4.x versions referenced in official documentation:

~~~properties
spring.http.codecs.max-in-memory-size=1MB
~~~

This property controls how many bytes eligible codecs may retain in memory when data must be aggregated. Boot documentation states that the property applies to **auto-configured WebFlux servers and WebClient instances**, not necessarily to every HTTP client you build manually.

YAML example:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 1MB
~~~

### Older Versions May Use a Different Name

In some Spring Boot 3.0–3.2 versions, documentation used **spring.codec.max-in-memory-size**. In 3.5 and later, use **spring.http.codecs.max-in-memory-size** per the documentation of the version you run. When upgrading, do not assume old property names still bind: read the version-specific application properties and verify binding if needed.

If a system runs multiple services on different Spring Boot versions, standardize properties per each service's BOM rather than copying a single shared configuration file without checking compatibility.

### What Does Max In-Memory Limit?

It limits the bytes a codec may **buffer while aggregating** a piece of data. For a standard JSON body decoded into a single object, reading may have to hold that object's data in memory. For multi-object streams, some codecs apply the limit per buffered object rather than across the entire stream's total bytes.

By default, many codecs have a threshold around **256 KiB**, though the exact default can vary by codec and version. Do not base configurations on the assumption that every codec shares the exact same number.

When exceeded, you typically see:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

**Important:** spring.http.codecs.max-in-memory-size is **not** a general HTTP server upload size limit, not a firewall against large payloads, and does not replace limits at the gateway, reverse proxy, multipart parser, file storage, database, or business validation layers.

If a client uploads a 1 GB file via multipart, setting this property to 1MB will not protect the system. Upload design requires its own limits, streaming, disk quotas, timeouts, authentication, and cancellation handling.

## 6. Configuring CodecCustomizer in Spring Boot 3.5

The following example intentionally **keeps default codecs** and only adjusts the buffer limit. This is safer than calling registerDefaults(false) when you do not want to take responsibility for the entire list of readers/writers.

**File:** src/main/java/com/example/codec/CodecConfig.java

~~~java
package com.example.codec;

import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CodecConfig {

    @Bean
    public CodecCustomizer appCodecCustomizer() {
        return configurer ->
            configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
~~~

In this example, the bean is discovered by Spring Boot's component scan. When Boot applies this bean to its managed CodecConfigurer, default codecs receive a 1 MiB memory limit.

**Do not simultaneously set spring.http.codecs.max-in-memory-size to a different value for the same purpose** unless you intentionally need to control ordering and precedence. To keep this lesson easy to verify, leave max-in-memory-size **unset** when running this example.

If your project uses Spring Boot 4.x, keep the same logic and replace the import with:

~~~java
import org.springframework.boot.http.codec.CodecCustomizer;
~~~

An import change across major versions does not guarantee all underlying APIs remain unchanged indefinitely. Check the Spring Boot migration guide when upgrading.

## 7. Complete Spring WebFlux Application Example

Example using Java 17+, Spring Boot 3.5.x, and the spring-boot-starter-webflux starter. Generate a Maven project from Spring Initializr with Spring Reactive Web. Do not also add the MVC starter if your goal is running a reactive web server.

All three Java files must share the `com.example.codec` package.

### 7.1. CodecApplication.java

~~~java
package com.example.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecApplication.class, args);
    }
}
~~~

### 7.2. Payload.java

~~~java
package com.example.codec;

public record Payload(String text) {
}
~~~

This record illustrates Jackson JSON mapping. A valid JSON body contains a `text` property of type `String`.

### 7.3. EchoController.java

~~~java
package com.example.codec;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
        path = "/api/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Payload> echo(@RequestBody Mono<Payload> input) {
        return input.map(value ->
            new Payload(value.text() == null ? "" : value.text().trim())
        );
    }
}
~~~

### 7.4. CodecConfig.java

Use the complete CodecConfig.java from section 6 to set the codec buffer limit to 1 MiB.

### 7.5. Running and Calling the Endpoint

From a project with the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Example request:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"text":" Hello WebFlux "}'
~~~

With the declared route, the expected result is HTTP 200 with JSON equivalent to:

~~~json
{"text":"Hello WebFlux"}
~~~

Header order and default headers depend on the runtime; the key checks are a matching Content-Type and the trimmed body.

In this pipeline:

1. The JSON reader/decoder reads the body into Payload.
2. The controller receives Mono<Payload>.
3. `map` creates a new Payload once the value arrives.
4. The JSON writer/encoder creates the response.
5. If the body has an incompatible media type or cannot be decoded, WebFlux propagates the error through standard HTTP error handling.

You **do not** call `subscribe()` or `block()` in the controller. The framework manages subscription and response lifecycle.

## 8. When to Use WebFluxConfigurer.configureHttpMessageCodecs?

Besides CodecCustomizer, Spring Framework provides **WebFluxConfigurer** to customize WebFlux infrastructure on the server side:

~~~java
package com.example.codec;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerOnlyCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

This is an **alternative** to CodecConfig in section 6, not a class to add alongside another customizer setting max-in-memory-size=1MiB. It illustrates customizing server codecs using the Spring Framework API.

Key differences:

| Capability | CodecCustomizer | WebFluxConfigurer.configureHttpMessageCodecs | WebClient.Builder.codecs |
|---|---|---|---|
| API layer | Spring Boot | Spring Framework WebFlux | Spring Framework HTTP client |
| Configurer object | CodecConfigurer | ServerCodecConfigurer | ClientCodecConfigurer |
| Primary scope | Codec configurations used by Boot | WebFlux HTTP server | A specific WebClient/builder |
| Requires @EnableWebFlux? | No | No; avoid adding if you want Boot defaults | No |
| Best fit | Boot/application-level customization | Server-side WebFlux only | Outbound clients or manually built clients |

If you only want to change the buffer threshold across the Boot-auto-configured app, a property is usually more concise. If you need server-only configuration, WebFluxConfigurer makes intent clear. If the app uses multiple WebClients with distinct requirements, configure codecs per builder.

### Why Avoid Adding @EnableWebFlux Arbitrarily?

In Spring Boot, a regular WebFluxConfigurer **does not need** `@EnableWebFlux`. Adding `@EnableWebFlux` tells Spring Framework to configure WebFlux directly and can cause Boot's WebFlux auto-configuration to back off. That can change resource handling, integrated codecs, and other conveniences. Use full-control mode only when you have an architectural reason and have checked which defaults must be reconfigured.

## 9. When to Register a Custom Codec?

Custom codecs are needed when:

- The application uses a custom media type unsupported by default codecs.
- Data uses a specialized binary/protocol format requiring a matching Decoder and Encoder.
- Streaming is needed for a specialized message format.
- A reader/writer requires logic that cannot be expressed through standard serializer configuration.

Spring Framework provides the registry:

~~~java
configurer.customCodecs().register(customDecoder);
~~~

Here `customDecoder` must be a real decoder implementing the appropriate Spring contract. This is an illustrative pattern, **not a standalone compilable snippet**; `customDecoder` must be backed by a concrete implementation.

In supported versions, `registerWithDefaultConfig` lets a custom codec inherit default settings such as `maxInMemorySize` and logging details if supported by that codec. Registering a codec does not automatically guarantee it honors every property the way default codecs do.

### The Danger of registerDefaults(false)

The API:

~~~java
configurer.registerDefaults(false);
~~~

**disables registration of default codecs**—it does not mean "give this custom codec slightly higher priority." Used carelessly, the application can lose JSON readers/writers, text readers/writers, form codecs, or SSE support depending on the setup.

Possible consequences:

- `Content-Type: application/json` requests are rejected with 415.
- The server has no matching writer for `Accept`, returning 406.
- Endpoints that previously worked now fail during response serialization.
- HTTP integration tests break unexpectedly.

Use `registerDefaults(false)` only when you **genuinely want to replace the entire codec list** and have registered all readers/writers needed for every media type your application serves. Most memory-limit customizations **do not** require disabling defaults.

### Changing JSON Mapping Does Not Necessarily Require a New Codec

If your goal is formatting `LocalDateTime`, property naming conventions, or custom serialization, prefer Boot-supported Jackson configuration: `spring.jackson.*` properties, Jackson modules, and serializer/deserializer beans. Replacing the JSON codec outright can discard Boot-configured integrations.

Spring Boot 4.x changes the Jackson generation, so when upgrading major versions choose the matching APIs. Do not copy a Jackson2 codec customization from a Boot 3.x app to Boot 4.x without consulting the libraries and migration guide.

## 10. Configuring WebClient: Do Not Confuse Server and Client

The WebFlux server **reads requests** and **writes responses**. WebClient is an HTTP client that **writes requests** and **reads responses**. Both have codec configs, but with separate lifecycles and configurer objects.

When creating a client manually, you can configure codecs:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

WebClient client = WebClient.builder()
    .baseUrl("https://service.example")
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024)
    )
    .build();
~~~

This is an illustrative snippet placed inside a method or `@Bean`; it creates a WebClient with a 2 MiB `maxInMemorySize` for its default client codecs.

In a Boot-auto-configured application, prefer injecting Boot's **WebClient.Builder** to inherit appropriate customizations, then layer on client-specific settings as needed. Do not assume every WebClient created via `WebClient.create()` or `WebClient.builder()` receives all Boot `CodecCustomizer` beans.

A common issue: your app's server decodes a 1 MiB request without trouble, yet WebClient calls a downstream service, decodes a response larger than the default limit, and throws `DataBufferLimitException`. In that case, inspect **the codec settings of the receiving WebClient**, rather than only raising the server's limit.

Setting a large `maxInMemorySize` has memory costs. Under high concurrency, each aggregation can retain significant memory; benchmark under concurrent load and enforce payload size limits at appropriate outer layers.

## 11. Media Types, Content-Type, Accept, and HTTP Status Codes

**Content-Type** on a request declares the format of the body the client sends, whereas **Accept** declares the response format the client wants back. WebFlux selects readers/writers based on media type, Java type, annotations, and registered codecs.

Example:

~~~http
POST /api/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"text":"abc"}
~~~

A handler declaring `consumes` and `produces` as `application/json` accepts matching requests. Sending `text/plain` instead of `application/json` can fail due to a `consumes` mismatch, typically returning `415 Unsupported Media Type`.

If `Accept` only allows a media type unsupported by the handler or codecs, the server can return `406 Not Acceptable`. If the JSON body is syntactically invalid and cannot be deserialized, default behavior typically returns `400 Bad Request`.

Do not blame every HTTP status on "codec not registered"; for example:

| Symptom | Possible cause | How to check |
|---|---|---|
| 400 when sending JSON | Malformed JSON, type mismatch, validation, or binding | Check body, DTO, and message reader error |
| 406 Not Acceptable | Accept/produces mismatch, missing writer | Check response type, produces annotation, registered writers |
| 415 Unsupported Media Type | Content-Type/consumes mismatch, missing reader | Check request media type and registered readers |
| DataBufferLimitException | Aggregation exceeds a specific codec's limit | Check single object/buffer size and config on the reading side |
| 500 when writing response | Encoder/serialization failure, service error, or other exception | Check server logs and stack trace |
| 413 Content Too Large | Possibly reverse proxy or another server/upload limit | Check gateway, server, and multipart configuration |

The final status depends on the framework exception handler, server/gateway, and app configuration. This table gives diagnostic direction, not a guarantee of identical error codes across every deployment.

## 12. Multipart and Streaming: Why Raising maxInMemorySize Isn't Enough

If clients upload images or large files, increasing `spring.http.codecs.max-in-memory-size` may **not** solve the right problem. Multipart has its own in-memory/disk thresholds, part count limits, header size limits, and storage caps.

Relevant properties in Spring Boot 3.5+:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=20
~~~

These are illustrative policy values, not universal defaults; appropriate numbers depend on file types, business requirements, and infrastructure. These properties control multipart handling in Spring WebFlux for matching versions; HTTP server and proxy layers may impose additional limits.

Differences across scenarios:

- **Mono<Payload>** for a JSON body typically decodes a single object and may aggregate data.
- **Flux<Payload>** as a JSON stream/NDJSON can process items one by one; however, codecs may still buffer a single object or prefetch.
- **Flux<DataBuffer>** is low-level byte streaming; using Flux alone is unsafe if downstream code calls `collectList` or joins the entire stream.
- **Multipart PartEvent streaming** has its own processing model; buffer release and read/write errors must be managed properly.

When large payloads can be processed incrementally, design streaming APIs rather than raising aggregation limits to hundreds of MBs. Measure throughput, memory, heap/off-heap usage, and backpressure under realistic load.

## 13. Codec Logging and Sensitive Data

WebFlux/Boot offers an option to log request details; in supported versions:

~~~properties
spring.http.codecs.log-request-details=true
~~~

This feature supports diagnostics in controlled environments. Combined with DEBUG/TRACE logging, it can write form data or sensitive headers into logs.

Do not enable detailed logging indiscriminately in production just to track down a 415 error. Before enabling it, evaluate:

1. Could tokens, personal data, cookies, or secrets appear in logs?
2. Where are logs stored and who can read them?
3. Are proper retention and masking policies in place?
4. Can you debug using metadata, content type, and payload size instead of full contents?

CodecCustomizer also exposes an API to enable request detail logging on default codecs, which carries the same security considerations. By default, prefer logging only necessary metadata.

## 14. Testing Codec Configuration with WebTestClient

**WebTestClient** lets you send HTTP requests and assert WebFlux stack behavior. For the section 7 project, add **spring-boot-starter-test** in test scope.

Spring Boot 3.5.x example:

~~~java
package com.example.codec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CodecApplicationTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        webTestClient.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new Payload("  hello  "))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }
}
~~~

This test verifies both directions: the Java payload is serialized to JSON by the test client, decoded by the server, and encoded back into the response. When testing **the server's own codecs**, keep in mind WebTestClient also uses its own codecs on the client side.

How to design a memory-limit test:

1. Set a small `maxInMemorySize` (for example, 64KB) for a test profile.
2. Send a JSON object with a body exceeding that limit.
3. Assert the request fails; check the cause chain and logs to confirm `DataBufferLimitException`.
4. Send an object below the limit and assert HTTP 200 with the expected body.
5. Also test outbound WebClient if your application uses it.

Do not assert that every over-limit request returns **one fixed HTTP status** unconditionally: responses also depend on runtime exception mapping. What matters is verifying the protective limit triggers and errors are handled consistently without leaking infrastructure details.

In Boot 4.x, packages for several test auto-configure annotations changed; use matching imports and versions rather than copying Boot 3.5 examples verbatim.

## 15. Common Design Mistakes and Fixes

### Calling registerDefaults(false) just to add one codec

If you only want a custom JSON format or higher buffer limit, do not disable default codecs. Keep defaults, configure the appropriate codec group, and run regression tests for JSON, text, multipart, and SSE.

### Assuming CodecCustomizer itself is a Decoder

CodecCustomizer is a registry callback. To support a new format, you must provide and register an actual Encoder/Decoder/reader/writer. A CodecCustomizer bean alone cannot decode any arbitrary protocol.

### Tuning the server when the error is in WebClient

DataBufferLimitException can occur when a client calls another service. Check which side is reading data: server inbound or client inbound. For manually built WebClients, inspect their individual builders.

### Using properties from the wrong version

In older Spring Boot releases, the property prefix was `spring.codec.*`, whereas Boot 3.5/4.x uses `spring.http.codecs.*`. In Boot 4.x, the CodecCustomizer import package also changed. Always verify against the libraries you are running.

### Raising maxInMemorySize indefinitely to silence errors

Raising the threshold may allow a single large valid object, at the cost of a larger memory footprint. Enforce limits at the client/gateway, design streaming when suitable, and account for concurrent requests.

### Confusing codec limits with file upload limits

Multipart files have separate disk-spill mechanisms and quotas; proxies also enforce body size limits. Do not use codec aggregation settings as a substitute for an upload policy.

### Replacing the entire Jackson setup just to format one field

Tune Jackson serializers/deserializers or properties first before writing a new JSON decoder. Replacing the JSON codec can break modules, date/time settings, and Boot integrations.

### Calling block() in a controller thinking codecs must run synchronously

WebFlux accepts Mono/Flux and orchestrates reading/writing automatically. Codecs operate inside the reactive pipeline; calling `block()` during request handling defeats non-blocking behavior and can harm event-loop threads.

### Missing integration tests for Content-Type and Accept

Sending `text/plain` to an endpoint with `consumes = application/json` will fail even if controller logic is valid. Test media-type contracts, DTOs, and response formats.

### Assuming every custom codec automatically honors default settings

Custom codecs must explicitly support those settings. If a custom codec does not enforce buffer limits itself, default codecs' `maxInMemorySize` may not protect it.

## 16. Production Checklist for Codec Changes

Before deploying, verify:

- **Version:** exact Spring Boot/BOM; matching imports and properties.
- **Scope:** server inbound, server outbound, WebClient inbound/outbound — which side needs changes?
- **Defaults:** was `registerDefaults(false)` called accidentally?
- **JSON:** serialization/deserialization and Jackson modules still work.
- **Media types:** test application/json, text/plain, SSE, form/multipart if used.
- **Memory:** limit fits payload size, concurrency, and memory budget; not set arbitrarily high.
- **Streaming:** avoid aggregating large or unbounded streams.
- **Security:** no secrets exposed in request logging.
- **Errors:** 400, 406, 415, and buffer overflows produce appropriate responses and metrics.
- **Regression:** WebTestClient, WebClient integration tests, and load benchmarks.
- **Observability:** track DataBufferLimitException, latency, memory, and upstream errors.
- **Rollback:** if issues occur, can you revert the property or disable the customizer cleanly?

## 17. Self-Check Questions

1. At which stages of WebFlux request/response handling do HttpMessageReader and HttpMessageWriter operate?
2. Does CodecCustomizer belong to Spring Boot or Spring Framework? Does it create a Decoder on its own?
3. Why is spring.http.codecs.max-in-memory-size not a total upload size limit?
4. How do Spring Boot 3.5 and 4.x differ in the CodecCustomizer import?
5. When should you prefer an application property over a CodecCustomizer bean?
6. If you only want to customize server-side codecs, which WebFluxConfigurer extension point do you use?
7. When do you need to configure WebClient.Builder.codecs separately?
8. Which HTTP error statuses can registerDefaults(false) trigger?
9. Why shouldn't a custom JSON converter casually replace the entire Jackson setup?
10. How do you verify a JSON request succeeds without calling block()?
11. For a DataBufferLimitException in an HTTP client calling a downstream service, which side's configuration should you check?
12. Should log-request-details=true be enabled in every production environment?

### Suggested Answers

1. Readers decode request bodies into objects; writers encode response bodies from objects/publishers.
2. Spring Boot; it customizes CodecConfigurer, and an actual codec must still be provided if a new format is required.
3. It caps codec aggregation buffering, not all transport bodies, multipart storage, or gateway policies.
4. Boot 3.5: org.springframework.boot.web.codec.CodecCustomizer; Boot 4.x: org.springframework.boot.http.codec.CodecCustomizer.
5. When the change is only a buffer limit or logging setting already supported by a Boot property.
6. configureHttpMessageCodecs(ServerCodecConfigurer configurer).
7. When WebClient is built manually or needs settings distinct from global auto-configuration.
8. 415 when a matching reader is missing, 406 when a matching writer is missing, depending on the request and configuration.
9. Because you lose Boot's modules/default settings and risk discrepancies in formatting and validation.
10. Use WebTestClient to send a valid request and assert status, Content-Type, and body.
11. Inspect client-side codecs, especially the WebClient.Builder used to create that client.
12. No; consider the risk of exposing sensitive headers/form data and enable it only selectively during controlled debugging.

## 18. Official References

- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): CodecCustomizer, WebFlux auto-configuration, and HTTP codecs.
- [Spring Boot 4.x — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): CodecCustomizer package and current codec management mechanisms.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): spring.http.codecs.max-in-memory-size and multipart properties.
- [Spring Framework — WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): WebFluxConfigurer, ServerCodecConfigurer, default codecs, and custom codecs.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): buffering, DataBufferLimitException, and streaming.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring client codecs.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing requests/responses in the reactive web stack.