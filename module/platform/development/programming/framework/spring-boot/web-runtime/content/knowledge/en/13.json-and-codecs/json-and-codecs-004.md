# Spring MVC HttpMessageConverter and Spring WebFlux Codecs

Spring Boot provides two web stacks: **Spring MVC (Servlet)** and **Spring WebFlux (reactive)**. Both can receive JSON via `@RequestBody` and return JSON from `@RestController`, yet they use **two different infrastructure layers** to convert between HTTP bodies and Java objects:

- **Spring MVC:** uses a list of `HttpMessageConverter<?>`. Converters read the HTTP body according to the Java type and media type, or write Java values into the HTTP response.
- **Spring WebFlux:** uses `HttpMessageReader<?>` and `HttpMessageWriter<?>`, typically built from `Decoder<?>`/`Encoder<?>` and appropriate adapters. They integrate with reactive streams (`Publisher`, `Mono`, `Flux`) and `DataBuffer`.
- **Jackson:** is the popular JSON library that Spring Boot integrates into both models when the required dependencies are present. Jackson processes JSON; it is **not** synonymous with the entire MVC converter mechanism or WebFlux codecs.

The same Java DTO type and HTTP `Content-Type: application/json` can behave identically at the API surface, while stream handling, buffering, backpressure, threading, and configuration points are **not the same**.

## 1. At What Stage Is the HTTP Body Converted?

Suppose a client sends:

~~~http
POST /people/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Lan","age":24}
~~~

Spring performs two directions:

1. **Read (decode):** receives JSON bytes and converts them into `Person("Lan", 24)` to pass to the controller.
2. **Write (encode):** converts the Java object returned by the controller into JSON bytes sent to the client.

A conceptually shared DTO:

~~~java
record Person(String name, int age) {}
~~~

This is a Java record (Java 17+). When used with a compatible JSON mapper, it can be serialized/deserialized through its record components.

**Not every controller argument uses a body converter.** `@PathVariable` and `@RequestParam` go through mapping/binding mechanisms; `@RequestBody` and `@ResponseBody`/`@RestController` are the typical locations for body conversion. With `@RequestPart`, a converter/codec can participate in decoding the content of a multipart part.

## 2. Flow in Spring MVC: HttpMessageConverter

With `spring-boot-starter-web`, the typical default web server is embedded Tomcat. An HTTP request follows this path:

~~~text
HTTP client
  -> Servlet container
  -> Servlet FilterChain
  -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter
  -> @RequestBody argument resolver
       -> HttpMessageConverter.canRead(Java type, Content-Type)
       -> converter.read(...) -> Person
  -> Controller / Service
  -> @ResponseBody return-value handler
       -> HttpMessageConverter.canWrite(Java type, response media type)
       -> converter.write(...) -> HTTP bytes
  -> Servlet container -> HTTP response
~~~

Related framework classes/components:

| MVC Component | Role |
|---|---|
| `HttpMessageConverter<T>` | Contract for reading/writing bodies between HTTP and Java types |
| `MappingJackson2HttpMessageConverter` | JSON via Jackson 2 in Spring Boot 3.x when appropriate dependencies exist |
| `StringHttpMessageConverter` | `String` bodies, e.g., text/plain |
| `ByteArrayHttpMessageConverter` | `byte[]` bodies |
| `ResourceHttpMessageConverter` | Bodies involving `Resource` |
| `AllEncompassingFormHttpMessageConverter` | Form and supported multipart cases |
| `RequestResponseBodyMethodProcessor` | Reads `@RequestBody` and handles `@ResponseBody` for annotated MVC |

The actual list of converters depends on the **Spring Framework/Spring Boot version**, classpath, and user configuration. Do not assume all converters for JSON, XML, Protobuf, Smile, CBOR, etc., are present in every application.

### 2.1. canRead and canWrite Select Based on Two Conditions

A converter is considered based on at least:

- The Java type the controller wants to receive or return.
- The matching HTTP media type: `Content-Type` when reading the body, or the negotiated content type when writing the body.
- For converters and adapters supporting generic types, Spring also inspects `Type`, generic type/context, and related extensions.

For instance, a JSON converter can read `Person` with `application/json`, whereas `StringHttpMessageConverter` is typically used to write a `String` response as plain text.

**List order can matter** when multiple converters report support for the same type + media type combination. Do not insert a custom converter supporting `Object.class` and `*/*` at the front of the list when your goal is only to add a narrow wire format: it can hijack work meant for the default JSON/String converters.

### 2.2. Servlet Bodies Are Typically Read/Written Synchronously

A typical `HttpMessageConverter` receives `HttpInputMessage` and `HttpOutputMessage` whose bodies are tied to Servlet HTTP streams. In a standard synchronous Servlet request, reading/writing via the converter runs on the worker thread handling the request.

Spring MVC also supports asynchronous request processing. Therefore, do not claim "every MVC request must stay on a single thread from start to finish," though the **HttpMessageConverter contract is primarily synchronous body conversion** rather than a Reactive Streams reader/writer.

## 3. Flow in WebFlux: Readers/Writers and Encoders/Decoders

With `spring-boot-starter-webflux` and no Servlet starter causing Boot to infer a different stack, the default embedded HTTP server is typically **Reactor Netty**.

~~~text
HTTP client
  -> Reactor Netty HTTP events / DataBuffer
  -> WebFilter chain
  -> DispatcherHandler
  -> HandlerMapping / HandlerAdapter
  -> @RequestBody resolution
       -> HttpMessageReader.canRead(element type, media type)
       -> Decoder reads DataBuffers / Publisher
       -> Mono<Person> or Person supplied to handler
  -> Reactive controller / Service
  -> Response body result handler
       -> HttpMessageWriter.canWrite(element type, media type)
       -> Encoder produces DataBuffers
       -> writes HTTP response with non-blocking I/O
~~~

Classes to know:

| WebFlux Component | Role |
|---|---|
| `HttpMessageReader<T>` | Reads bodies and emits Java data through reactive APIs |
| `HttpMessageWriter<T>` | Writes Java data/publishers to the HTTP response |
| `Decoder<T>` | Converts `DataBuffer`s into Java data |
| `Encoder<T>` | Converts Java data into `DataBuffer`s |
| `DecoderHttpMessageReader<T>` | Adapter from decoder to HTTP message reader |
| `EncoderHttpMessageWriter<T>` | Adapter from encoder to HTTP message writer |
| `Jackson2JsonDecoder` | Decodes JSON using Jackson 2 in Spring Framework 6.x |
| `Jackson2JsonEncoder` | Encodes JSON using Jackson 2 in Spring Framework 6.x |
| `ServerCodecConfigurer` | Configures default and custom codecs/readers/writers for the server |

`HttpMessageReader`/`Writer` is the layer aware of HTTP headers/media types, while `Decoder`/`Encoder` focuses on content conversion. Some writers/readers are not merely adapters around an encoder/decoder—for example, multipart/resource handling has its own specifics. Hence, do not treat `HttpMessageReader` as an absolute synonym for `Decoder`.

### 3.1. Why Does WebFlux Use Publisher and DataBuffer?

`DataBuffer` represents a byte region in the I/O pipeline. Instead of forcing the entire body to be buffered before processing, many WebFlux components can receive/write data as a `Flux<DataBuffer>` stream. Decoders and encoders transform those data chunks into Java objects and back.

Examples:

- A JSON request representing a single `Person`: many decoders **collect/read enough data** to construct the complete object.
- A JSON stream over a streaming media type such as `application/x-ndjson`: the corresponding encoder/decoder can process individual items on a stream without having to accumulate everything into a single JSON array first.
- File downloads or streaming binary responses: can use specialized `DataBuffer`/Resource APIs without necessarily passing through Jackson.

**Reactive does not always mean zero-copy streaming or zero memory use.** When a codec must aggregate data into an object, buffering and memory limits apply; when working with pooled DataBuffers, buffer lifecycle management is a critical responsibility of the framework and custom codecs.

## 4. Quick Comparison of the Two Pipelines

| Property | Spring MVC | Spring WebFlux |
|---|---|---|
| Common server | Servlet: Tomcat/Jetty/Undertow | Reactive: Reactor Netty |
| Front Controller | `DispatcherServlet` | `DispatcherHandler` |
| HTTP body abstraction | `HttpInputMessage` / `HttpOutputMessage` | `ReactiveHttpInputMessage` / `ReactiveHttpOutputMessage` |
| Body conversion | `HttpMessageConverter` | `HttpMessageReader` / `HttpMessageWriter` |
| Byte ↔ object conversion | Typically read/written directly by the converter | `Decoder` / `Encoder` and codec adapters |
| Request body Java API | `@RequestBody Person` | `@RequestBody Person` or `@RequestBody Mono<Person>` |
| Response body API | DTO, `ResponseEntity`, `@ResponseBody` | DTO, `Mono<DTO>`, `Flux<DTO>`, and reactive response types |
| Primary I/O | Servlet request/response, typically synchronous | Reactive non-blocking I/O |
| Common extension point | `WebMvcConfigurer` | `WebFluxConfigurer` / `ServerCodecConfigurer` |
| Preserving Boot defaults | `extendMessageConverters` | `configureHttpMessageCodecs` with appropriate default/custom codec APIs |
| Common pitfalls | Losing default converters when replacing the list | Overlapping custom decoders/encoders, exceeding buffer limits, blocking the event loop |

## 5. Runnable Example with Spring MVC

The first standalone example uses **Spring Boot 3.x**, **Java 17+**, with the Gradle plugin/Boot dependency management configured. `build.gradle` dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

File **src/main/java/demo/mvc/MvcJsonApplication.java**:

~~~java
package demo.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcJsonApplication.class, args);
    }
}

record Person(String name, int age) {
}

@RestController
class MvcPeopleController {

    @PostMapping(
            path = "/people/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Person echo(@RequestBody Person input) {
        return input;
    }

    @GetMapping(
            path = "/people/example",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Person example() {
        return new Person("Lan", 24);
    }
}
~~~

At the POST endpoint, Spring MVC selects the JSON `HttpMessageConverter` to read the body into `Person`. The controller returns the record; Spring MVC then uses the matching converter to write the JSON response.

Run using the project's Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows can use `gradlew.bat bootRun`. Test (Bash syntax):

~~~bash
curl -i http://localhost:8080/people/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Lan","age":24}'
~~~

In the demo project without other Security/filters altering behavior, the HTTP response has status **200 OK** and a JSON body with `name=Lan` and `age=24`, for example:

~~~json
{"name":"Lan","age":24}
~~~

JSON field order is not guaranteed across all Jackson configurations. Do not write tests requiring fixed key ordering if the API contract only specifies values.

## 6. Runnable Example with Spring WebFlux

The second standalone example uses **a separate project** with the same Java 17+ and Spring Boot 3.x, but only the WebFlux dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

File **src/main/java/demo/webflux/WebFluxJsonApplication.java**:

~~~java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxJsonApplication.class, args);
    }
}

record Person(String name, int age) {
}

@RestController
class WebFluxPeopleController {

    @PostMapping(
            path = "/people/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Person> echo(@RequestBody Mono<Person> input) {
        return input;
    }

    @GetMapping(
            path = "/people/example",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Person> example() {
        return Mono.just(new Person("Lan", 24));
    }
}
~~~

In WebFlux, `@RequestBody Mono<Person>` is decoded through `HttpMessageReader`/decoder, supplying the resulting publisher for the handler to process. The controller returns `Mono<Person>`; the response writer/encoder writes JSON once the publisher emits data.

Try it:

~~~bash
./gradlew bootRun
~~~

~~~bash
curl -i http://localhost:8080/people/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Lan","age":24}'
~~~

With the sample configuration, the resulting body carries the same data:

~~~json
{"name":"Lan","age":24}
~~~

**The difference from MVC is not in the JSON shape**, but in how WebFlux operates with publishers, reactive readers/writers, and server I/O. The controller **does not need to and must not** call `subscribe()` or `block()` to return the body. The web runtime manages subscription and completes the HTTP response.

**Do not copy both `Person` classes, both `@SpringBootApplication` classes, and both starters into the same package/module** assuming both stacks will run side by side. The two examples are separate projects. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically defaults to **Servlet MVC**.

## 7. Content-Type, Accept, and Selecting the Converter

Two HTTP headers play distinct roles:

- **Content-Type:** declares the format of data **the client is sending**. When reading `@RequestBody`, the framework finds a converter/reader supporting the combination of Java type and request media type.
- **Accept:** declares which response formats **the client is willing to receive**. When writing the response, the framework negotiates the media type based on `produces` mappings, `Accept`, and converter/writer capabilities.

Example:

~~~http
POST /people/echo
Content-Type: application/json
Accept: application/json
~~~

Changing the request `Content-Type` to `text/plain` while the controller only declares `consumes=application/json` typically returns **HTTP 415 Unsupported Media Type**. If the client only sends `Accept: text/plain` while the endpoint declares `produces=application/json`, it typically returns **HTTP 406 Not Acceptable**. These are media type/mapping selection issues; **they do not prove Jackson is missing**.

| Status | Common Cause |
|---|---|
| 400 Bad Request | Malformed JSON, undecodable body, binding/validation error |
| 404 Not Found | No matching URL/handler found |
| 405 Method Not Allowed | Route exists for URL, but HTTP method does not match |
| 406 Not Acceptable | Response media type cannot satisfy `Accept`/`produces` |
| 415 Unsupported Media Type | Request `Content-Type` does not match `consumes`/reader |
| 413 Content Too Large | HTTP body size limit exceeded at server/proxy |
| 500 or other error handler | Encoding error, processing failure, or unhandled exception |

For body errors, **MVC** typically throws exceptions such as `HttpMessageNotReadableException`; **WebFlux** typically raises `ServerWebInputException` or a related codec exception. The final response depends on error handling and Spring Boot configuration, so do not assume a single exception class across all error scenarios.

## 8. Customizing in MVC Without Losing Default Converters

In Spring MVC, when you want to **add to or adjust** the existing list, the safe approach is usually `WebMvcConfigurer#extendMessageConverters`:

~~~java
package demo.mvc;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConverterConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters
    ) {
        // Here the default converter list has already been prepared.
        // To add a custom format: converters.add(customConverter);
        // Do not call converters.clear() just to add one converter.
    }
}
~~~

This class can be added to the sample MVC project, though it **does not register a new converter on its own** since the snippet illustrates a non-destructive hook. To add a new wire format, write a converter with genuinely narrow `canRead`/`canWrite` matching the Java type and media type, then intentionally call `converters.add(...)`. Avoid registering duplicate converters via both `@Bean` and `extendMessageConverters`.

### Warning About configureMessageConverters

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(customConverter);
}
~~~

This is a **risk-illustration fragment**, missing the `customConverter` declaration and not compiling standalone. In Spring MVC, populating the list inside `configureMessageConverters` can skip registration of default converters; JSON/String/bytes handling can be affected. Do not use this hook if your goal is only to add one item.

`@EnableWebMvc` is also a major change: it delegates more MVC configuration control manually and causes Boot's MVC auto-configuration to back off. Do not add it just to tweak one converter.

If your goal is simply JSON naming/serialization, prefer `spring.jackson.*` or an appropriate `ObjectMapper` customizer rather than replacing the entire Jackson converter.

## 9. Customizing in WebFlux: ServerCodecConfigurer

WebFlux does not use `WebMvcConfigurer#extendMessageConverters` to configure WebFlux codecs. The corresponding extension point is `WebFluxConfigurer#configureHttpMessageCodecs(ServerCodecConfigurer)`.

Example customizing only the buffer memory limit while preserving all remaining default readers/writers:

~~~java
package demo.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

This configuration class can be placed in the same package as the WebFlux example. It sets a maximum buffering limit of **256 KiB** for default codecs that support this limit, **without replacing the entire default list**.

Depending on the version, a Spring Boot 3.x property for the same purpose is:

~~~yaml
spring:
  codec:
    max-in-memory-size: 256KB
~~~

When a property satisfies the requirement, prefer the property since it is easy to vary per environment. Do not configure both the property and custom code with conflicting goals without verifying precedence.

If you genuinely need a custom codec, `ServerCodecConfigurer` provides `customCodecs()` to register additional codecs/readers/writers. Normally **you should not call `registerDefaults(false)`** just to add a codec: disabling defaults can break JSON, text, and resource codecs unexpectedly. When modifying the JSON decoder/encoder directly, verify both read and write directions and check which `ObjectMapper` is used.

### 9.1. MVC and WebFlux Do Not Share Extension Points

| Goal | Spring MVC | Spring WebFlux |
|---|---|---|
| Add custom body format | `HttpMessageConverter` and `extendMessageConverters` | `HttpMessageReader/Writer` or `Encoder/Decoder` via `ServerCodecConfigurer.customCodecs()` |
| Keep default configuration | Do not clear converter list; use extend hook | Keep `defaultCodecs()`; register custom codecs selectively |
| Simple JSON customization | Boot Jackson config/`ObjectMapper` | Boot Jackson config/`ObjectMapper` with default Jackson codecs |
| Body buffer limits | Servlet/container and related settings | `maxInMemorySize` on default codecs or matching Boot property |
| Asynchronous body handling | Servlet async has its own mechanisms | `Publisher`, `DataBuffer`, and reactive codecs |

Do not register an MVC `HttpMessageConverter` expecting WebFlux on Reactor Netty to pick it up automatically. Similarly, do not use `WebFluxConfigurer` to configure Servlet converters in an application actually running MVC.

## 10. Jackson: Shared Point, Yet Not Identical Across Stacks

When an application uses Jackson 2 with Spring Boot 3.x, common JSON classes are:

- MVC: `MappingJackson2HttpMessageConverter`.
- WebFlux: `Jackson2JsonDecoder` and `Jackson2JsonEncoder`.

Both can honor Jackson rules for annotations, serialization/deserialization, modules, naming strategies, and date/time. However, WebFlux codecs are also responsible for handling `Publisher`/`DataBuffer` and certain streaming media types; MVC converters do not inherently share those semantics.

### 10.1. Configuring JSON via application.yml

For example, to omit properties with null values:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
~~~

This is a Boot 3.x property for Jackson integration. When JSON is produced using the Spring Boot-managed `ObjectMapper`, the change can apply to both MVC and WebFlux in their respective projects without replacing entire converters/codecs.

Distinguish clearly:
- Omitting null properties happens during **serialization**; it does not mean requests with missing fields are automatically validated.
- Java record components, Bean Validation, Kotlin nullability, and primitive values have distinct rules.
- An `ObjectMapper` instantiated manually with `new ObjectMapper()` may miss modules/settings registered by Boot.

If a requirement applies to only one DTO, use Jackson annotations on that DTO instead of changing application-wide JSON rules.

### 10.2. Jackson2ObjectMapperBuilderCustomizer

Spring Boot 3.x, Jackson 2 example:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer omitNullFields() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

This configuration class can be package-scanned in an application with Jackson and appropriate Spring Boot auto-configuration. Its goal is to configure **how ObjectMapper is built**, not to clear converters/codecs and recreate them with an empty mapper.

Do not assume every `ObjectMapper` on the classpath goes through Boot's builder; third-party libraries may instantiate their own mappers. When upgrading major versions of Spring Boot/Spring Framework or switching JSON libraries, verify API names and actual auto-configuration behavior.

## 11. Streaming JSON: WebFlux Offers Additional Options

In APIs returning multiple elements, there is a difference between:

- A complete JSON array:
  
~~~json
[{"id":1},{"id":2},{"id":3}]
~~~

- One JSON line per element, NDJSON style:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

In WebFlux, you can return `Flux<Event>` and specify a streaming media type like `application/x-ndjson` when supported by the encoder:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<Event> streamEvents() {
    return eventService.events();
}
~~~

This is a **WebFlux fragment**, requiring definitions for `Event`, `eventService`, and imports. The endpoint can encode each item as a JSON line as the producer emits signals, rather than having to collect everything into a single JSON array in memory.

However, streaming is still affected by HTTP/proxy buffering, flush behavior, downstream consumption rate, serialization cost, and backpressure. Do not promise that each `onNext` corresponds to one TCP packet to the client.

In MVC, applications can also stream responses using appropriate Servlet APIs such as `StreamingResponseBody` or `ResponseBodyEmitter`. Thus, the difference is not "MVC absolutely cannot stream," but that **WebFlux uses reactive publisher/codec integration as its primary model**.

## 12. Buffer Limits, DataBufferLimitException, and Large Requests

An important concern in WebFlux is **memory used to buffer bodies**. If a JSON object must be aggregated for deserialization and its size exceeds the codec threshold, the application can encounter `DataBufferLimitException` or related errors. Depending on error handling, the HTTP response may vary; do not assume it is always 413 or 500.

Good practices:

1. Identify which bodies genuinely need aggregation and which should stream.
2. Set buffer limits matching business requirements and container memory.
3. Configure request size limits at proxy/ingress/server layers if needed.
4. For large uploads, consider streaming/multipart and bounded storage mechanisms.
5. Monitor latency, heap/direct memory, GC, and codec errors.
6. Do not raise `maxInMemorySize` unboundedly just to silence errors without analyzing root causes.

**DataBuffer requires lifecycle management:** when writing custom decoders/readers that manipulate pooled buffers directly, follow the proper retain/release APIs. Do not hold `DataBuffer` references long-term or skip releasing after taking ownership. Use framework codecs whenever possible to reduce memory leak risks.

In MVC, body size concerns also exist, though configuration points may live in the Servlet container, multipart settings, HTTP client/proxy, or custom converters; you cannot use a WebFlux property like `spring.codec.max-in-memory-size` as a substitute for all Servlet limits.

## 13. Blocking I/O: Why WebFlux Codecs Do Not Automatically Make Everything Non-Blocking

WebFlux uses non-blocking I/O where supported by the runtime/client and pipeline. However, if a JSON encoder performs heavy computation or a custom decoder executes synchronous JDBC, that code **still blocks the thread** it runs on.

Do not place this in a WebFlux controller:

~~~java
@PostMapping("/bad")
Person bad(@RequestBody Person input) {
    blockingLegacyRepository.save(input);
    return input;
}
~~~

This is an **anti-pattern fragment** if run directly on the event loop, and will not compile standalone due to missing repository/class definitions. An HTTP codec with a reactive API does not turn JDBC into non-blocking I/O.

If a blocking API must be kept, isolate it with a deferred source:

~~~java
Mono<Person> result = Mono.fromCallable(() ->
        blockingLegacyRepository.saveAndReturn(input)
).subscribeOn(Schedulers.boundedElastic());
~~~

This fragment requires `blockingLegacyRepository`, `input`, and imports; `boundedElastic` has bounded threads/queues and is not true non-blocking I/O. When most business logic relies on blocking JDBC/JPA, **Spring MVC may be simpler and more appropriate**. Do not pick WebFlux just to write `Mono` in code.

For end-to-end reactive flows, consider `WebClient` for HTTP and reactive data drivers like R2DBC when supported by your stack. Continue bounding connection pools, concurrency, timeouts, and retries; reactive I/O does not give downstream dependencies infinite throughput.

## 14. Testing to Catch Converter/Codec Errors

A valuable test checks **both directions**: request JSON enters the controller as the expected type, and response JSON has the expected media type/body. Do not just test that an endpoint starts up.

### 14.1. MVC with MockMvc

In the **sample MVC project**, add:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Create **src/test/java/demo/mvc/MvcJsonApplicationTest.java**:

~~~java
package demo.mvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcJsonApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonIsReadAndWritten() throws Exception {
        String payload = """
                {"name":"Lan","age":24}
                """;

        mvc.perform(post("/people/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(payload))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.name").value("Lan"))
           .andExpect(jsonPath("$.age").value(24));
    }
}
~~~

With Java 17, the `"""` text block above forms a valid JSON string with a trailing newline; Jackson accepts trailing whitespace in JSON requests. Using text blocks avoids quote-escaping errors. `MockMvc` exercises the MVC model without opening a TCP server; to test connector/network behavior, write separate integration tests.

### 14.2. WebFlux with WebTestClient

In the **separate WebFlux project**, add the test starter:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Create **src/test/java/demo/webflux/WebFluxJsonApplicationTest.java**:

~~~java
package demo.webflux;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxJsonApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonIsReadAndWritten() {
        client.post()
              .uri("/people/echo")
              .bodyValue(Map.of("name", "Lan", "age", 24))
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      org.springframework.http.MediaType.APPLICATION_JSON)
              .expectBody()
              .jsonPath("$.name").isEqualTo("Lan")
              .jsonPath("$.age").isEqualTo(24);
    }
}
~~~

In `RANDOM_PORT` mode with a reactive web application, Spring Boot Test can provide a `WebTestClient` configured to call the real HTTP server according to the active version's test mechanism. If the project customizes test clients, adjust injection accordingly. Using a `Map` in `bodyValue` lets Spring WebFlux pick the JSON writer without hand-writing escaped JSON strings.

Test command for both projects:

~~~bash
./gradlew test
~~~

If MVC JSON tests fail after registering a custom `HttpMessageConverter`, check whether `configureMessageConverters` accidentally replaced defaults. If WebFlux fails after configuring custom codecs, check `ServerCodecConfigurer`, `registerDefaults`, Jackson dependencies, and media types.

**Recommended negative tests:** `Content-Type: text/plain` sent to an endpoint consuming only JSON (typically 415), `Accept: text/plain` when an endpoint produces only JSON (typically 406), structurally invalid JSON or DTO mismatch (typically 400), and oversized bodies exceeding configured limits.

## 15. Common Pitfalls and How to Diagnose Them

**Pitfall 1 — Assuming HttpMessageConverter is used for WebFlux Reactor Netty too.** That is the MVC Servlet stack mechanism. For WebFlux, configure `HttpMessageReader`/`HttpMessageWriter` and encoders/decoders.

**Pitfall 2 — Having Mono in a controller and assuming the server is reactive.** When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot usually infers MVC. Check dependencies and the actual `ApplicationContext` type.

**Pitfall 3 — Using configureMessageConverters just to add one simple converter.** The default list may be skipped. Prefer `extendMessageConverters` or appropriate Boot bean mechanisms, and test JSON/String/bytes.

**Pitfall 4 — Disabling default codecs to register a custom one.** Calling `registerDefaults(false)` can break JSON, text, and resource handling. Only disable when intentionally managing the full list.

**Pitfall 5 — Converter/codec with overly broad media types.** A custom `*/*` or `Object` decoder at high priority can hijack payloads not meant for it. Restrict Java types/media types to your wire format.

**Pitfall 6 — Replacing Jackson ObjectMapper carelessly with new ObjectMapper().** Can lose Boot-provided modules, Java Time, and naming/serialization settings. Use Jackson configuration/Boot-managed mappers when appropriate.

**Pitfall 7 — Confusing Content-Type and Accept.** `Content-Type` governs how request bodies are read; `Accept`/`produces` govern response format. 415 and 406 have distinct causes.

**Pitfall 8 — Raising WebFlux maxInMemorySize unboundedly.** Increases heap/direct memory pressure and masks large upload/JSON design issues. Choose streaming or deliberate size caps.

**Pitfall 9 — Writing a custom reactive decoder that calls JDBC or block().** A reactive codec does not free the event loop if internal code blocks. Keep codecs focused on bytes ↔ object conversion; call the DB in services with appropriate clients.

**Pitfall 10 — Writing a custom DataBuffer codec without releasing buffers.** Mishandling pooled buffers can leak memory. Use framework abstractions or follow buffer ownership/lifecycle rules.

**Pitfall 11 — Testing only JSON output.** You might miss broken request body decoding. Test POST echo to verify both directions, plus regressions for plain text/legacy formats.

**Pitfall 12 — Assuming Jackson JSON encoder always streams per object like NDJSON.** Streaming depends on media type, codec, publisher, and proxy flushing/buffering. Test with a streaming-capable client.

## 16. Selection and Implementation Checklist

1. Identify the real web stack: MVC Servlet or WebFlux Reactive; avoid guessing from controller names or `Mono` imports.
2. For MVC, understand `HttpMessageConverter`, `canRead`/`canWrite`, media types, and converter ordering.
3. For WebFlux, understand `HttpMessageReader/Writer`, `Encoder/Decoder`, `DataBuffer`, reactive publishers, and codec selection.
4. Use a Boot-configured JSON serializer like Jackson; avoid creating a new mapper just for one JSON rule.
5. If only adding a format in MVC, prefer `extendMessageConverters` over replacing the entire default list.
6. If adding a WebFlux codec, use `ServerCodecConfigurer.customCodecs()` and keep defaults unless intentionally managing everything.
7. Configure appropriate buffer and payload size limits, watching for `DataBufferLimitException` when aggregating large bodies.
8. Keep JDBC, blocking HTTP, and heavy CPU work off the Netty event loop even when code sits inside a reactive pipeline.
9. Verify content negotiation: `Content-Type`, `Accept`, `consumes`, `produces`; do not treat 415/406 as a single error.
10. Test JSON POST echo in both MVC and WebFlux; add tests for 400/415/406 and oversized bodies.
11. For NDJSON/`Flux` streaming, measure memory, flush behavior, latency, backpressure, and proxy buffering with a real HTTP client.
12. When upgrading major versions, re-verify Jackson/Spring Boot APIs and auto-configured default codecs.

**Remember:** `HttpMessageConverter` is the body conversion boundary in **Spring MVC Servlet**, whereas **Spring WebFlux** uses `HttpMessageReader`/`HttpMessageWriter` alongside `Encoder`/`Decoder` in a reactive pipeline. The same JSON body can yield the same DTO and response, yet **I/O mechanics, buffering, streaming, and customization points differ**. Preserve defaults, configure JSON in the right place, and regression-test both read and write paths to avoid breaking existing HTTP contracts.
