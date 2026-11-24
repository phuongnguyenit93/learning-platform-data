# Relationship Between Shared Jackson Configuration and Stack-Specific JSON Customization in Spring Boot

## 1. Practical Problem to Solve

A Spring Boot project may declare `spring.jackson.*`, create a shared `ObjectMapper` bean, and still run into situations where JSON returned from a controller differs from JSON produced by an `ObjectMapper` injected directly. When adding `WebMvcConfigurer`, `MappingJackson2HttpMessageConverter`, `CodecCustomizer`, `WebFluxConfigurer`, or manually building a `WebClient`, discrepancies become even easier to encounter.

For instance, a system wants to omit null properties:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

`objectMapper.writeValueAsString(new Reply("Lan", null))` may produce:

~~~json
{"name":"Lan"}
~~~

Yet a particular HTTP endpoint returns:

~~~json
{"name":"Lan","note":null}
~~~

This can be completely expected if that endpoint uses a converter/codec with its own `ObjectMapper` configured to **keep** null properties. This is not necessarily a Spring Boot bug failing to read the property.

This lesson clarifies:
- What does shared Jackson configuration include, and how far does it apply?
- Which component converts objects to JSON in Spring MVC?
- Which components convert request/response bodies in Spring WebFlux?
- Why can a server and `WebClient`, or two endpoints within the same stack, differ?
- How to customize locally without accidentally altering every endpoint or losing Boot defaults?
- How to inspect the `ObjectMapper` actually used by each converter/codec?
- How to test responses before and after changes, covering both serialization and deserialization?

The main examples use **Java 17+, Spring Boot 3.5.x, Jackson 2.x** with imports belonging to that generation. Spring Boot 4 switches the default JSON stack to Jackson 3 in many areas; do not use 3.5 packages and extension points verbatim to infer 4.x behavior. The content clearly distinguishes complete runnable code from illustrative snippets to be integrated into a project.

## 2. Three Configuration Layers: Jackson, Web Stack, HTTP Client

When diagnosing JSON discrepancies, separate three layers.

### Layer A — Shared Jackson

Spring Boot auto-configures Jackson when appropriate dependencies are present, including:
- The Spring-managed `ObjectMapper` bean.
- `Jackson2ObjectMapperBuilder` and builder customizers.
- `spring.jackson.*` properties.
- `Module` beans, `@JsonComponent`, and certain discovered Jackson modules.
- DTO annotations such as `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, `@JsonFormat`.

These determine how the *Boot-built mapper* serializes/deserializes. There is no rule stating that **every `ObjectMapper` instance in the JVM automatically receives** the same configuration.

### Layer B — Stack-Specific JSON Adapters

- **Spring MVC / Servlet:** `HttpMessageConverter`, typically `MappingJackson2HttpMessageConverter` for JSON. The converter holds or references an `ObjectMapper` and participates in representation selection based on type, `Content-Type`, `Accept`, `produces`, and `consumes`.
- **Spring WebFlux / reactive:** `HttpMessageReader` / `HttpMessageWriter` and `CodecConfigurer`. Jackson JSON typically uses `Jackson2JsonDecoder`/`Jackson2JsonEncoder` under reader/writer adapters.

Both can benefit from Boot's shared Jackson configuration, but **they do not share the same HTTP converter/codec list and do not necessarily share the same mapper instance** once customized by the application.

### Layer C — Individual HTTP Clients

- `RestClient`/`RestTemplate` use client-side converter mechanisms.
- `WebClient` uses `ExchangeStrategies` and client-side codecs.
- Clients created with `new`, a manual builder, or custom settings may not receive full Boot auto-configuration.

Even when a WebFlux server uses standard codecs, a `WebClient` with its own `ExchangeStrategies` can still enforce a different JSON policy. **Do not equate "application-wide" with "every inbound and outbound HTTP path."**

~~~text
spring.jackson.* + Jackson customizers + Modules
                       |
         Boot's ObjectMapper bean / builder
                       |
              +--------+---------+
              |                  |
         Spring MVC          Spring WebFlux
     HttpMessageConverter     HttpMessageReader/Writer
              |                  |
       Controller JSON     Controller JSON / streaming
              |                  |
          Local MVC          Local WebFlux
       converter/mapper      encoder/decoder/mapper
              |
          Separate HTTP Client (RestClient/WebClient)
          can be configured independently
~~~

The diagram is conceptual; verify the wiring of your specific version and application context before concluding that two components share the same instance.

## 3. Shared Jackson Configuration: spring.jackson.*

In Spring Boot 3.5, `spring.jackson.*` allows declaring serialization/deserialization policies without manually registering converters.

Example:

~~~properties
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent_output=false
spring.jackson.deserialization.fail-on-unknown-properties=false
spring.jackson.serialization.write-dates-as-timestamps=false
~~~

Illustrative keys:
- `default-property-inclusion=non_null`: null fields are normally omitted when a serializer uses this mapper, unless overridden by an annotation or specific config.
- `serialization.indent_output`: enables/disables JSON pretty printing.
- `deserialization.fail-on-unknown-properties`: handles JSON fields absent from the DTO.
- `serialization.write-dates-as-timestamps`: affects how serializers supporting temporal types format dates/times.

Remember that `spring.jackson.*` configures the **Boot-managed Jackson mapper**; it does not automatically create custom HTTP converters per media type. A manually constructed `new ObjectMapper()` may lack the Java Time module, `@JsonComponent`, or features provided by Boot.

### 3.1. Property Precedence

When the same key exists across `application.properties`, profile-specific YAML, environment variables, and command-line arguments, Spring's `Environment` resolves the value according to configuration source precedence. Example:

~~~bash
java -jar target/my-app.jar --spring.jackson.default-property-inclusion=always
~~~

Replace `my-app.jar` with the actual built JAR. For the mapper bound by Boot from `Environment`, the final value in this example can switch the policy from `non_null` to `always`.

However, a high-precedence property **cannot force** an HTTP converter already configured with its own mapper to obey it. Separate `PropertySource` precedence from which converter/codec is actually selected.

### 3.2. Default ObjectMapper Bean and Auto-Configuration Back-Off

Spring Boot automatically registers an `ObjectMapper` when no bean satisfies the auto-configuration condition. If the application declares another `@Bean ObjectMapper`, auto-configuration can back off from creating the default mapper. A manually created mapper must be fully configured rather than assuming all `spring.jackson.*` settings still apply.

When shared behavior needs to be added, usually **prefer a customizer** over replacing the entire mapper.

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer globalJacksonPolicy() {
    return builder ->
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
}
~~~

This is an illustrative snippet inside a `@Configuration` class, using:
- `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`;
- `com.fasterxml.jackson.annotation.JsonInclude`;
- `org.springframework.context.annotation.Bean`.

The customizer runs when the builder constructs the mapper; it does not turn mappers outside DI into shared beans. When multiple customizers exist, `Ordered`/`@Order` and actual configuration steps can affect the final settings.

### 3.3. Module, @JsonComponent, and DTO Annotations

Different Jackson extension mechanisms have different scopes:

| Tool | Intended Scope | Limitation |
|---|---|---|
| `spring.jackson.*` | Shared policy of the Boot-configured mapper | Does not update manual mappers |
| `Jackson2ObjectMapperBuilderCustomizer` | Customizes the shared builder | Only mappers built via that builder |
| Jackson `Module` bean | Registers serializers/deserializers on managed mappers | Not guaranteed to enter completely independent mappers |
| `@JsonComponent` | Registers serializers/deserializers via Boot mechanism | Subject to application scanning and mapper integration |
| `@JsonInclude` on DTO | Inclusion rule for a specific type/field | May differ from global default |
| `@JsonFormat` | Representation of a specific field/type | Does not create a new HTTP codec |
| `@JsonIgnore`, `@JsonProperty` | Field naming/exclusion during bind/serialize | Must consider read/write directions and security |
| `ObjectMapper.copy()` | Creates an independent mapper from existing config | Modifying the copy does not mutate the original mapper |

**Important rule:** a library adding a module or serializer can alter system-wide output if attached to the shared mapper. A converter/codec using a manually created mapper may bypass that module.

## 4. JSON Mechanics in Spring MVC

In Spring MVC, when a controller returns an object or accepts `@RequestBody`, `RequestResponseBodyMethodProcessor` and related components select an appropriate `HttpMessageConverter`.

Example:

~~~java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<OrderView> create(@RequestBody OrderInput input) {
    return ResponseEntity.ok(service.create(input));
}
~~~

The snippet above is a fragment inside a controller with existing DTO/service types. With Jackson on the classpath, a `MappingJackson2HttpMessageConverter` is typically used:
1. Reads the `application/json` request and deserializes it into `OrderInput`.
2. Serializes the returned `OrderView` to JSON when the response media type matches.
3. Relies on the `ObjectMapper` attached to the converter.

`@RequestBody` does not mean "Jackson always reads the body." For example, text/binary uses other converters; when no converter supports the media type and Java type, the request can be rejected.

### 4.1. MVC-Specific Customization Approaches

Common paths:
- A specific `HttpMessageConverter` bean via Spring Boot `HttpMessageConverters`.
- `WebMvcConfigurer.extendMessageConverters(List<HttpMessageConverter<?>>)` to adjust the assembled list.
- `WebMvcConfigurer.configureMessageConverters(...)` when deep control over the list is needed; in raw framework usage this can replace defaults, so verify Boot/Framework behavior for your version.
- A converter with a dedicated `ObjectMapper` for one media type or response scope.
- `ResponseBodyAdvice` for altering MVC-layer bodies/headers per contract.
- `@JsonView` or separate DTOs/annotations when only changing the representation of a group of fields.

Do not use `@EnableWebMvc` merely to change a JSON property, because doing so shifts responsibility for certain MVC defaults away from Spring Boot.

### 4.2. Converters Are Selected by Media Type and Order

Adding a converter does not guarantee it will be chosen. Spring MVC evaluates:
- Java parameter/return type.
- Request `Content-Type` and client `Accept`.
- `consumes`/`produces` on the handler.
- `canRead`/`canWrite` and supported media types list.
- Order of converters in the list.

The default Jackson converter typically supports `application/json` and JSON subtypes such as `application/*+json`. If you add a custom converter for a vendor media type at the end of the list, the default converter may be selected first in some cases. Therefore test `Content-Type`, response bodies, and place specialized converters at an explicit priority position if needed.

## 5. JSON Mechanics in Spring WebFlux

In WebFlux, controllers can return `Mono<T>`/`Flux<T>` and receive `@RequestBody Mono<T>`; encoding/decoding happens via reactive codecs:

- `HttpMessageReader`: reads request bytes into objects.
- `HttpMessageWriter`: writes objects into response bytes.
- `Jackson2JsonDecoder`: deserializes JSON via Jackson.
- `Jackson2JsonEncoder`: serializes JSON via Jackson.
- `ServerCodecConfigurer`, `ClientCodecConfigurer`, `CodecCustomizer`: codec configuration points at different scopes.

Spring Boot 3.5 applies `spring.jackson.*` to WebFlux's default Jackson codecs. However, if a customizer replaces the default encoder/decoder with an instance holding a separate mapper, **the settings on that mapper** are what get used for HTTP requests.

Example of `WebFluxConfigurer` replacing server-side JSON codecs:

~~~java
@Configuration(proxyBeanMethods = false)
class LocalReactiveJsonConfiguration implements WebFluxConfigurer {

    private final ObjectMapper global;

    LocalReactiveJsonConfiguration(ObjectMapper global) {
        this.global = global;
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        ObjectMapper local = global.copy();
        local.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        configurer.defaultCodecs()
                .jackson2JsonEncoder(new Jackson2JsonEncoder(local));
        configurer.defaultCodecs()
                .jackson2JsonDecoder(new Jackson2JsonDecoder(local));
    }
}
~~~

This is an illustrative class with imports:
- `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.annotation.JsonInclude`;
- `org.springframework.context.annotation.Configuration`;
- `org.springframework.http.codec.ServerCodecConfigurer`;
- `org.springframework.http.codec.json.Jackson2JsonEncoder`/`Jackson2JsonDecoder`;
- `org.springframework.web.reactive.config.WebFluxConfigurer`.

Check both encode and decode if the application needs a bidirectional policy change. `ObjectMapper.copy()` inherits current settings and allows modifying the copy without mutating the mapper injected elsewhere.

### 5.1. CodecCustomizer vs. WebFluxConfigurer

Spring Boot 3.5's `CodecCustomizer` (package `org.springframework.boot.web.codec.CodecCustomizer`) customizes codecs configured by Boot. `WebFluxConfigurer.configureHttpMessageCodecs` is an extension point in server-side WebFlux configuration.

Do not assume an arbitrary `CodecCustomizer` affects only the server or only `WebClient`: check which `CodecConfigurer` instances auto-configuration passes to the customizer. If the requirement is for one specific HTTP client, configure that client's builder directly.

Do not call:

~~~java
configurer.registerDefaults(false);
~~~

casually: this disables default codecs and can break JSON, text, form, or SSE support unless full replacements are registered. To customize Jackson, prefer `defaultCodecs().jackson2JsonEncoder/Decoder` or supported narrow configuration APIs.

## 6. WebClient and RestClient Can Differ from the Server

A common bug: the WebFlux controller returns valid JSON, yet an outbound `WebClient` sends a different body, or a direct `ObjectMapper` test succeeds while requests via the client fail.

Reasons:
- `WebClient` uses `ExchangeStrategies` with client-side codecs.
- A Boot auto-configured `WebClient.Builder` can receive Boot customizers, whereas calling `WebClient.builder()` directly or `WebClient.create()` does not necessarily receive container configurations.
- `RestClient`/`RestTemplate` uses client-side `HttpMessageConverters`, not MVC's server converter list.
- A dedicated client bean may replace codecs/converters or use a custom `ObjectMapper`.

The right verification is not "the mapper bean serializes as expected," but **sending/receiving real HTTP through the exact client instance used at runtime**.

### 6.1. Example Configuring a Dedicated WebClient

The fragment below illustrates setting a JSON codec on **one specific WebClient** without altering all controllers:

~~~java
@Bean
WebClient auditWebClient(WebClient.Builder builder, ObjectMapper commonMapper) {
    ObjectMapper local = commonMapper.copy();
    local.setSerializationInclusion(JsonInclude.Include.ALWAYS);

    return builder.clone()
            .codecs(codecs -> {
                codecs.defaultCodecs()
                        .jackson2JsonEncoder(new Jackson2JsonEncoder(local));
                codecs.defaultCodecs()
                        .jackson2JsonDecoder(new Jackson2JsonDecoder(local));
            })
            .baseUrl("https://audit.example.org")
            .build();
}
~~~

This is a fragment inside a configuration class requiring imports `WebClient`, `ObjectMapper`, `JsonInclude`, `Jackson2JsonEncoder/Decoder`, and `@Bean`. The URL is a placeholder example; do not send requests to it. `clone()` avoids mutating a shared builder injected into other clients.

If you create a new client using `WebClient.builder()` instead of injecting the Boot-configured builder, builder customizers in the application context may not be applied. When comparing JSON, always record **which client** and **how it was created**.

## 7. Effective Scope Matrix for Each Customization Approach

| Configuration Approach | Typical Intended Scope | What Must Be Verified |
|---|---|---|
| `spring.jackson.*` | Default mapper/JSON codecs configured by Boot | Whether runtime converters/codecs inherit it |
| `Jackson2ObjectMapperBuilderCustomizer` | Mappers created by the shared builder | Whether custom beans/manual mappers replace the default |
| Jackson `Module` bean | Mappers integrated by Boot with modules | Whether manual mappers or custom codecs include the module |
| DTO `@JsonInclude`/`@JsonFormat` | Annotated type/field | Whether annotations override globals and which endpoints use the DTO |
| Dedicated MVC `MappingJackson2HttpMessageConverter` | Matching MVC HTTP routes/media types | Supported media types, `canWrite`, converter ordering |
| MVC `WebMvcConfigurer` | Servlet MVC server stack | Whether `@EnableWebMvc` or other converters interfere |
| WebFlux `WebFluxConfigurer` | Reactive server codecs/configuration | Which encoder/decoder is used and whether another customizer overrides it |
| Boot `CodecCustomizer` | `CodecConfigurer` instances passed to customizers by Boot | Server/client scope and customizer order for the version |
| `WebClient.Builder.codecs(...)` | `WebClient` built from that builder | Whether the right client instance is used |
| `new ObjectMapper()` | Newly created independent mapper | Which shared properties/modules/configs are missing |
| `ObjectMapper.copy()` then configured | Separate mapper inheriting initial settings | Whether the original shared mapper is accidentally mutated |
| `@Primary ObjectMapper` | Preferred bean for injection when multiple mappers exist | Does not guarantee every converter/codec uses it |

Do not call a configuration "global" merely because it lives in a `@Configuration` class. Examine bean scope, dependency wiring, and which framework components actually consume the bean.

## 8. Complete Runnable Example 1 — Spring MVC: Global Omits Null, Vendor JSON Keeps Null

This experiment intentionally produces **two different JSON responses on the same MVC stack**, while sharing one root Boot-configured `ObjectMapper`.

Outcomes to prove:
- `GET /standard` uses the default JSON converter: `note=null` is omitted.
- `GET /vendor` uses a specialized converter and copied mapper: `note=null` is preserved.
- The `ObjectMapper` injected into other beans is not altered by the customization meant only for the vendor media type.

### 8.1. Create the Maven Project

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>mvc-jackson-scope</artifactId>
    <version>1.0.0</version>
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

File `src/main/resources/application.properties`:

~~~properties
spring.jackson.default-property-inclusion=non_null
server.port=8080
~~~

File `src/main/java/example/mvc/JacksonMvcApplication.java`:

~~~java
package example.mvc;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class JacksonMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonMvcApplication.class, args);
    }
}

record Reply(String name, String note) {}

@RestController
class JsonController {

    @GetMapping(path = "/standard", produces = MediaType.APPLICATION_JSON_VALUE)
    Reply standard() {
        return new Reply("Lan", null);
    }

    @GetMapping(path = "/vendor",
            produces = "application/vnd.example.full+json")
    Reply vendor() {
        return new Reply("Lan", null);
    }
}

@Configuration(proxyBeanMethods = false)
class VendorConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper sharedMapper;

    VendorConverterConfiguration(ObjectMapper sharedMapper) {
        this.sharedMapper = sharedMapper;
    }

    @Override
    public void extendMessageConverters(List<HttpMessageConverter<?>> converters) {
        ObjectMapper vendorMapper = sharedMapper.copy();
        vendorMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        MappingJackson2HttpMessageConverter vendorConverter =
                new MappingJackson2HttpMessageConverter(vendorMapper);
        vendorConverter.setSupportedMediaTypes(List.of(
                MediaType.parseMediaType("application/vnd.example.full+json")));

        converters.add(0, vendorConverter);
    }
}
~~~

This is **one compilable Java file** with a single public class matching the filename. `Reply` is a package-private record; the controller and configuration in the same package are scanned by `@SpringBootApplication`. The specialized converter sits ahead of the general converter and supports only the specified vendor media type.

### 8.2. Run and Inspect JSON

In the project directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/standard
curl -i -H "Accept: application/vnd.example.full+json" http://localhost:8080/vendor
~~~

Expected key parts:

| Request | Status | Content-Type | Body |
|---|---:|---|---|
| `/standard` | 200 | `application/json` | `{"name":"Lan"}` |
| `/vendor` | 200 | `application/vnd.example.full+json` | `{"name":"Lan","note":null}` |

Header order, `Content-Length`, charset, and JSON property ordering depend on the container/converter. The table lists only the values significant for the experiment.

Step-by-step explanation:
1. The global property makes the auto-configured `ObjectMapper` omit nulls.
2. The general converter uses that policy-bearing mapper when writing `application/json`.
3. The configuration creates a **copy** of the mapper, switches inclusion to `ALWAYS`, and places it into a converter dedicated to vendor JSON.
4. MVC selects the converter matching `produces` and media type, so `/vendor` keeps `note:null`.
5. The original mapper is not mutated; `/standard` continues omitting nulls.

If you move the specialized converter to the end of the list, re-check actual behavior: the general converter may support `application/*+json` and get chosen earlier. That is why the experiment deliberately calls `converters.add(0, ...)`.

### 8.3. Test with MockMvc

Add `src/test/java/example/mvc/JacksonMvcApplicationTests.java`:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JacksonMvcApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void defaultJsonOmitsNull() throws Exception {
        mvc.perform(get("/standard").accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"name\":\"Lan\"}", true));
    }

    @Test
    void vendorJsonKeepsNull() throws Exception {
        mvc.perform(get("/vendor")
                    .accept("application/vnd.example.full+json"))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        "application/vnd.example.full+json"))
                .andExpect(content().json(
                        "{\"name\":\"Lan\",\"note\":null}", true));
    }
}
~~~

Run `mvn test`. Both tests verify the **actual response of the MVC stack**, not merely calling `ObjectMapper.writeValueAsString`. `content().json(..., true)` compares JSON in strict mode; when `note` is written as null, the structure differs from when the field does not exist.

## 9. Complete Runnable Example 2 — WebFlux: Shared ObjectMapper Differs from Server Codecs

The second example is a **separate project**, not placed alongside the MVC example's `pom.xml` above. It demonstrates:
- The shared mapper has `NON_NULL` due to `spring.jackson.*`.
- Server-side WebFlux codecs are replaced with a copied mapper configured with `ALWAYS`.
- With the same record having `note=null`, direct serialization via the shared mapper differs from HTTP JSON sent by WebFlux.

This illustrates that the `ObjectMapper` bean and WebFlux's Jackson encoder do not have to remain the same instance after customization.

### 9.1. Maven Dependencies and Properties

File `pom.xml` for the separate WebFlux project:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-jackson-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/resources/application.properties`:

~~~properties
spring.jackson.default-property-inclusion=non_null
server.port=8080
~~~

Use only the WebFlux starter for this project; if you add the MVC starter, Boot usually defaults to the MVC runtime and `WebFluxConfigurer` may not govern the running server.

### 9.2. Complete Java Source

File `src/main/java/example/reactive/JacksonWebFluxApplication.java`:

~~~java
package example.reactive;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class JacksonWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonWebFluxApplication.class, args);
    }
}

record Reply(String name, String note) {}

@RestController
class ReactiveJsonController {

    private final ObjectMapper commonMapper;

    ReactiveJsonController(ObjectMapper commonMapper) {
        this.commonMapper = commonMapper;
    }

    @GetMapping(path = "/direct", produces = MediaType.TEXT_PLAIN_VALUE)
    String direct() throws JsonProcessingException {
        return commonMapper.writeValueAsString(new Reply("Lan", null));
    }

    @GetMapping(path = "/http", produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Reply> http() {
        return Mono.just(new Reply("Lan", null));
    }
}

@Configuration(proxyBeanMethods = false)
class ServerJsonCodecConfiguration implements WebFluxConfigurer {

    private final ObjectMapper commonMapper;

    ServerJsonCodecConfiguration(ObjectMapper commonMapper) {
        this.commonMapper = commonMapper;
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        ObjectMapper serverMapper = commonMapper.copy();
        serverMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        configurer.defaultCodecs()
                .jackson2JsonEncoder(new Jackson2JsonEncoder(serverMapper));
        configurer.defaultCodecs()
                .jackson2JsonDecoder(new Jackson2JsonDecoder(serverMapper));
    }
}
~~~

There is one public class matching the filename. `/direct` explicitly serializes via the `ObjectMapper` bean and returns `text/plain`; that response does not use `Jackson2JsonEncoder` to serialize `Reply` again. `/http` returns `Mono<Reply>`, processed by the WebFlux HTTP writer/encoder.

### 9.3. Run and Verify

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/direct
curl -i -H "Accept: application/json" http://localhost:8080/http
~~~

Result table to observe:

| Request | Status | Content-Type | Body |
|---|---:|---|---|
| `GET /direct` | 200 | `text/plain` | `{"name":"Lan"}` |
| `GET /http` | 200 | `application/json` | `{"name":"Lan","note":null}` |

Key point: the controller uses the same `Reply` record, yet the two responses write differently. `/direct` uses the shared mapper; `/http` flows through the customized WebFlux JSON codec. The difference does not mean Boot ignored the property—it proves **the two serialization paths do not share the same mapper**.

If a real project adds other `CodecCustomizer` or `WebFluxConfigurer` beans, customizer order and later configurations can replace the encoder/decoder again. Therefore, test over HTTP against the actual application context when evaluating systems with multiple libraries.

## 10. Verify Deserialization, Not Just Serialization

JSON discrepancies are not limited to null fields in responses. The receiving `@RequestBody` side may also use a distinct decoder/converter:

- Are unknown JSON fields allowed?
- Are case-insensitive property names accepted?
- Are `LocalDateTime`, `Instant`, enums, and numbers formatted consistently?
- Are custom deserializer/serializer modules registered on both paths?
- Are large payloads bounded by WebFlux buffer limits?
- Does the endpoint accept `application/json` or a vendor media type, and does the converter return true for `canRead`?

For example, if a local mapper enables:

~~~java
localMapper.configure(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
~~~

then JSON containing extra fields will be rejected by the converter/decoder using that local mapper, even though the shared mapper still ignores them.

**This is only a fragment** requiring `import com.fasterxml.jackson.databind.DeserializationFeature` and an existing `localMapper` variable. Do not add this line to the two sample programs above if you want to keep their test results as documented.

### 10.1. Do Not Guess HTTP Status from Lower-Level Exceptions

In MVC, unreadable JSON typically leads to `HttpMessageNotReadableException` and a default status of 400. In WebFlux, decode/validation failures may travel through `ServerWebInputException` or related exceptions, with error mapping depending on framework version and handlers. Payload/buffer limits can also fail the request before the controller executes.

If `Content-Type` is unsupported by readers/converters, the status is typically 415; if `Accept` has no suitable representation, it can be 406. Do not assume every JSON failure is a mapper bug or always returns 400.

## 11. When to Use DTO Annotations Instead of Changing Codecs?

Not every JSON requirement needs a new converter or codec.

For example, a single field needing a different format on one DTO:

~~~java
public record InvoiceView(
        String number,
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate issuedDate) {
}
~~~

This is a fragment using Jackson annotations and `java.time.LocalDate`. It changes `issuedDate` on this type without altering every `LocalDate` across the system.

A DTO that should always keep nulls:

~~~java
@JsonInclude(JsonInclude.Include.ALWAYS)
public record AuditEvent(String action, String reason) {
}
~~~

Choosing scope:
- Single field/DTO: prefer annotations/DTO projections if they do not break shared contracts.
- All JSON across the application: `spring.jackson.*`, shared mapper builder/customizer.
- Single MIME type or group of MVC endpoints: specialized converter, DTO view, or conditional response advice.
- Reactive server generally: `WebFluxConfigurer`/codecs.
- A dedicated `WebClient`: configure codecs on that specific client builder.

For public APIs, changing global inclusion or date formats is a **data contract change**. Plan versioning, compatibility tests, and real client verification before applying it broadly.

## 12. ObjectMapper.copy, new ObjectMapper, and Thread Safety

`ObjectMapper` is typically configured once and shared across threads. Registering modules, changing settings, or swapping serializers **after the mapper is used at runtime** can produce inconsistent behavior. Avoid mutating a shared mapper inside a request handler.

Wrong direction:

~~~java
@GetMapping("/temporary")
String bad(@RequestParam boolean showNull) throws Exception {
    commonMapper.setSerializationInclusion(
            showNull ? JsonInclude.Include.ALWAYS : JsonInclude.Include.NON_NULL);
    return commonMapper.writeValueAsString(new Reply("Lan", null));
}
~~~

This is an illustrative fragment **that must not be used**: concurrent requests can interfere with each other's policy.

Safer strategies:
1. Build shared mappers before the application begins serving requests.
2. Create a copied mapper for converters/codecs requiring different settings, also at startup.
3. For per-call serialization settings, consider dedicated `ObjectWriter`/`ObjectReader` instances, which are designed to be shared and configured for reading/writing.
4. Use DTOs/annotations if differences are limited to specific fields.

Comparison:
- `commonMapper.copy()`: inherits most configuration and registered serializers/modules, then allows customizing the new instance.
- `new ObjectMapper()`: starts with standalone Jackson defaults, **with no guarantee** of inheriting Spring Boot modules and features.
- `Jackson2ObjectMapperBuilder`: constructs mappers through the configured builder, suitable when you want to leverage Boot's customization pipeline.

If the mapper bean is created or replaced as `@Primary` by another library, directly inspect which `ObjectMapper` is injected before assuming `copy()` inherits the configuration you expect.

## 13. How to Verify the Actual Mapper and Converter/Codec in Use

Do not stop at seeing `spring.jackson.default-property-inclusion=non_null` in a file. QA verification should span four layers.

### 13.1. Verify Effective Properties

Check `Environment`, active profiles, environment variables, and command-line arguments:

~~~java
String configured = environment.getProperty(
        "spring.jackson.default-property-inclusion");
~~~

This fragment assumes `Environment` is injected. Actuator `/actuator/env` and `/actuator/configprops` (when enabled and secured) help inspect property sources and bindings; they do not by themselves prove which mapper runtime codecs use.

### 13.2. Verify ObjectMapper in the Context

Example fragment checking the mapper's policy via serialization:

~~~java
String json = objectMapper.writeValueAsString(
        new Reply("Lan", null));
System.out.println(json);
~~~

With the shared mapper in the two sample projects, expected output:

~~~text
{"name":"Lan"}
~~~

If it prints `{"name":"Lan","note":null}`, the mapper bean may have been replaced, the property may not be effective, or another annotation/module affects inclusion. Do not conclude the HTTP server definitely produces the same output: the converter/codec layer still sits between them.

### 13.3. Verify the List of MVC Converters

In an MVC application, you can inspect `RequestMappingHandlerAdapter.getMessageConverters()` to see the converters, their order, and the `ObjectMapper` inside `MappingJackson2HttpMessageConverter`.

Example fragment in a class with injected `RequestMappingHandlerAdapter adapter`:

~~~java
for (HttpMessageConverter<?> converter : adapter.getMessageConverters()) {
    if (converter instanceof MappingJackson2HttpMessageConverter json) {
        System.out.println(json.getSupportedMediaTypes());
        System.out.println(json.getObjectMapper()
                .getSerializationConfig()
                .getDefaultPropertyInclusion());
    }
}
~~~

This is debug inspection code, not an HTTP test; avoid logging sensitive full configurations. For converters supporting multiple mappers per type or custom converters, also check their mapper selection logic.

### 13.4. Verify WebFlux Server and Client with HTTP Tests

In WebFlux, inspecting the `ObjectMapper` bean alone is insufficient to prove the behavior of `Jackson2JsonEncoder` wired into `ServerCodecConfigurer`. The most reliable way:
- Use `WebTestClient` or curl to call JSON endpoints over the **real web stack**.
- Use a mock HTTP server or dedicated test server to observe the JSON body sent out by the **exact WebClient instance**.
- Check status, `Content-Type`, body, and decode errors.
- When needed, debug `CodecConfigurer` where it is configured rather than constructing a standalone codec to inspect and inferring runtime behavior.

Note: `@WebMvcTest` and `@WebFluxTest` are test slices that often do not load all third-party configs/beans like `@SpringBootTest`. If an issue stems from a library's customizer, test with the full application context and real dependencies.

## 14. Watch Out When Both Starters Exist in the Same Application

An application may declare both `spring-boot-starter-web` and `spring-boot-starter-webflux` to use `WebClient` inside MVC. Spring Boot defaults to **preferring the Spring MVC server** in this case.

Consequently:
- `WebMvcConfigurer` is where controller responses are affected.
- A `WebFluxConfigurer` intended for a reactive server **does not automatically** govern MVC controller responses.
- `WebClient` still uses reactive client codecs, which can differ from MVC server converters.
- Do not infer "having `Jackson2JsonEncoder` means controllers definitely run on WebFlux."

If you must run a WebFlux server, choose the appropriate web application type, verify auto-configuration, and audit dependencies. Do not switch stacks merely to customize serialization on a single route.

## 15. Common Design Mistakes

1. **Assuming `spring.jackson.*` configures every `new ObjectMapper()`.** Properties only apply through Boot-managed Jackson configuration.
2. **Creating a new `@Bean ObjectMapper` and forgetting modules/date features.** A custom bean can cause the default auto-configured mapper to back off.
3. **Mutating the shared mapper inside request handlers.** Causes race conditions and inconsistent JSON across requests.
4. **Confusing MVC `HttpMessageConverter` with reactive `HttpMessageWriter`/encoders.** They are two separate pipelines.
5. **Configuring WebFlux codecs while the app runs an MVC server.** Controllers will not use the extension point you expect.
6. **Assuming every `CodecCustomizer` only affects the WebFlux server.** Check where the customizer is applied.
7. **Calling `WebClient.builder()` directly and expecting all Boot customizers.** Managed/configured builders differ.
8. **Placing a vendor converter after the general converter** when the media type is also matched by the general converter. The new converter may not be chosen.
9. **Adding an overly broad `application/json` converter** just to fix one route. It can alter the whole application.
10. **Calling `registerDefaults(false)` when only changing JSON.** Can disable essential default codecs.
11. **Seeing `ObjectMapper` serialize properly and assuming HTTP does too.** Always test through the runtime-selected converter/codec.
12. **Changing only the encoder and forgetting the decoder** when both reading and writing JSON are required. Leads to asymmetric APIs.
13. **Changing `FAIL_ON_UNKNOWN_PROPERTIES` globally without testing clients.** Can break older requests.
14. **Using Jackson annotations on sensitive domain entities to "hide" fields.** Serialization rules do not replace authorization and DTOs.
15. **Failing to distinguish unknown properties from null inclusion.** One governs input deserialization; the other governs output serialization.
16. **Assuming date formatting properties affect all Java Date/Time types identically.** Appropriate modules, types, and annotations are required.
17. **Ignoring media type selection.** An endpoint can return 406/415 before Jackson even runs.
18. **Using test slices and assuming production libraries are imported.** Use full context when analyzing third-party customizers.

## 16. Pre-Implementation Checklist for Jackson Customization

- [ ] Distinguished app-wide changes from single-endpoint/media-type/client changes.
- [ ] Identified Boot version, Jackson 2/3 version, and web application type.
- [ ] Verified which configuration sources bind `spring.jackson.*`.
- [ ] Verified whether the active `ObjectMapper` bean is Boot-created/configured.
- [ ] Checked `@JsonComponent`, Jackson `Module`s, DTO annotations, and customizers.
- [ ] Checked actual MVC `HttpMessageConverter`s, supported media types, and ordering.
- [ ] If using WebFlux, distinguished `ServerCodecConfigurer`, `CodecCustomizer`, and `WebClient` codecs.
- [ ] Avoided mutating the shared mapper once the application starts serving requests.
- [ ] Used a copied mapper or DTO-level config when local differences are needed.
- [ ] Tested both serialization and deserialization when changes affect both directions.
- [ ] Verified `Content-Type`, `Accept`, `produces`, and `consumes`.
- [ ] Verified Jackson modules supporting Java Time, Kotlin, or required custom types.
- [ ] Added real HTTP tests for MVC/WebFlux and each relevant client.
- [ ] Covered null, unknown fields, dates, enums, malformed JSON, and payload size in regressions where applicable.
- [ ] Avoided disabling default codecs wholesale or adding unnecessary `@EnableWebMvc`/`@EnableWebFlux`.

## 17. Conclusion

**Shared Jackson configuration and stack-specific JSON handling are related, not identical.** `spring.jackson.*`, builder customizers, and Jackson modules establish policies for Boot-managed mappers/codecs. Spring MVC reads/writes JSON via `HttpMessageConverter`, while WebFlux uses `HttpMessageReader`/`HttpMessageWriter` and Jackson encoders/decoders. A converter, codec, or `WebClient` bound to its own mapper can intentionally differ from the shared policy. Good design chooses the **narrowest customization scope** fitting the API contract, avoids mutating shared mappers during request handling, and verifies results with runtime-accurate HTTP tests.

## Official Documentation for API Reference

- Spring Boot 3.5 — JSON and Jackson: https://docs.spring.io/spring-boot/3.5/reference/features/json.html
- Spring Boot 3.5 — Reactive Web Applications and HTTP codecs: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Servlet Web Applications and HttpMessageConverters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Spring MVC how-to: https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html
- Spring Framework 6.2 — MVC Message Converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html
- Spring Framework 6.2 — WebFlux HTTP Codecs: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
