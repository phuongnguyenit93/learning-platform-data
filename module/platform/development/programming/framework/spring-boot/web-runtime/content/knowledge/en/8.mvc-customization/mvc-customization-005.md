# Customizing HttpMessageConverter Without Losing Default Converters

In a **Spring Boot application using Spring MVC**, `HttpMessageConverter` is the mechanism that reads data from an **HTTP request body** into a Java object and writes a Java object into an **HTTP response body**. For example: converting JSON into a `@RequestBody` DTO, converting `String` into `text/plain`, or returning `byte[]` as binary data. These converters operate inside `DispatcherServlet` request processing, specifically when `RequestMappingHandlerAdapter` reads parameters and writes return values.

A common customization requirement is: **adding a new content format or adjusting an existing converter while keeping the default converters** that Spring Boot has configured. How you choose the extension point determines whether JSON, String, form data, static resources, and existing media types continue working.

**Core principle:** With Spring MVC and Spring Boot 3.x, when you only want to **add to** or **adjust** the existing list, prefer `WebMvcConfigurer#extendMessageConverters(List<HttpMessageConverter<?>>)`. Do not use `configureMessageConverters` to add elements carelessly: when the list populated in that hook is non-empty, Spring MVC's default converter registration mechanism can be bypassed.

## 1. Where Does HttpMessageConverter Sit in the MVC Flow?

Simplified flow when a client sends JSON to a REST controller:

~~~text
HTTP client
  |
  | Content-Type: application/json
  | Accept: application/json
  | Request body: {"name":"Lan"}
  v
Servlet container -> FilterChain -> DispatcherServlet
                                       |
                                       v
                                 HandlerMapping
                                       |
                                       v
                                 HandlerAdapter
                                       |
                        select converter to read body
                            canRead(Type, MediaType)
                                       |
                                       v
                          @RequestBody Java object
                                       |
                                       v
                             Controller / Service
                                       |
                                       v
                        select converter to write body
                           canWrite(Type, MediaType)
                                       |
                                       v
                         JSON / text / bytes / ...
                                       |
                                       v
HTTP response via Servlet container -> Client
~~~

`HttpMessageConverter` is not the mechanism for parsing all HTTP data:

- `@RequestParam` typically reads query parameters or form parameters via a different binding mechanism.
- `@PathVariable` extracts values from the URL.
- `@RequestBody` typically uses a converter to read the **entire request body** into the target type.
- `@ResponseBody`, `@RestController`, and many `ResponseEntity` cases typically use a converter to write the body.
- `multipart/form-data` also involves multipart resolution; individual `@RequestPart` items may use converters for a part's content.

If no converter supports the combination of **Java type + media type**, having a protocol-valid HTTP body does not mean Spring MVC can process that body.

## 2. What Do the Default Converters Do?

Spring MVC provides core converters, and Spring Boot can extend or adjust the list based on **dependencies/classpath** and application configuration. For a typical `spring-boot-starter-web` project, common types include:

| Converter / Group | Typical Role | Notes |
|---|---|---|
| `ByteArrayHttpMessageConverter` | Reads/writes `byte[]` | Serves byte-array bodies |
| `StringHttpMessageConverter` | Reads/writes `String` | Essential for endpoints returning plain text |
| `ResourceHttpMessageConverter` and related resource converters | Reads/writes `Resource` | Useful when returning resource content |
| `AllEncompassingFormHttpMessageConverter` / form converters | Handles forms and appropriate multipart bodies | Supported scope depends on components |
| `MappingJackson2HttpMessageConverter` | Reads/writes JSON via Jackson 2 | Typically included by Spring Boot 3.x when Jackson is present |
| Corresponding XML converter | Reads/writes XML when appropriate dependency is present | Not present in every project |

**Do not memorize a fixed list** for all versions: order, count, and features depend on the Spring Boot/Spring Framework version, classpath, and custom beans. Spring Boot 3.x in the examples below uses Jackson 2; when upgrading major versions, re-check the APIs and how Boot integrates the actual JSON library.

If you replace the entire list with a custom converter that only reads `text/plain`, existing JSON endpoints can lose the ability to read `application/json`, resource-returning endpoints may fail, and content negotiation will change. This is why you must **keep default converters** when the requirement is purely an addition.

## 3. Four Ways to Customize and Their Impact

| Approach | Preserves Default List? | When to Use |
|---|---|---|
| `spring.jackson.*` properties | Usually yes, when corresponding Boot/Jackson auto-config is active | Changing common JSON rules like omitting null fields |
| `Jackson2ObjectMapperBuilderCustomizer` bean | Usually yes, if using Boot's Jackson 2 | Customizing how `ObjectMapper` is built without replacing the converter |
| `WebMvcConfigurer#extendMessageConverters` | **Yes**, acts on the already-established converter list | Adding a custom converter or adjusting an existing element |
| `WebMvcConfigurer#configureMessageConverters` | **Risks bypassing default registration** if the list is populated here | Intentionally owning the converter list from scratch, knowing everything that must be registered |

One point to distinguish: in Spring Boot, an `HttpMessageConverter` bean supplied by the application can also be added to the converter list via auto-configuration. This is a valid integration path, though type, ordering, and replacement of same-type default converters must be controlled. Do not both register the same converter as a bean and manually add it again without understanding the result.

In this lesson, the primary illustration uses **`extendMessageConverters`**: its additive effect is easy to see, it does not require recreating the framework's JSON/String/bytes list, and it makes it easy to test that existing converters still work.

## 4. Why Does configureMessageConverters Easily Drop Default Converters?

Spring MVC has two hooks with very similar names:

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Explicitly configure the converter list.
}

@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Add to or adjust the list that was already created.
}
~~~

The snippets above are method signatures inside a class implementing `WebMvcConfigurer`, not standalone Java files.

When `configureMessageConverters` leaves the list **non-empty**, Spring MVC's mechanism may skip registering default converters via the usual path. Therefore, the following pattern is **an example to avoid** when the goal is merely to add one converter:

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(new ScoreHttpMessageConverter());
}
~~~

If you do that without registering the other necessary converters, JSON, String, bytes, and common media types may stop being handled as expected. In Spring Boot, other customizers or converter beans may also participate in configuration, so you should not claim every project loses the exact same list; however, **this is not the safe default hook for adding a converter**.

A better approach:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(0, new ScoreHttpMessageConverter());
}
~~~

At this point the default list has already been prepared by Spring MVC/Spring Boot; we prepend a narrowly scoped converter to the beginning of the list. The remaining converters stay intact.

**Do not confuse with `@EnableWebMvc`.** That annotation represents choosing deeper control over MVC configuration and causes Spring Boot's normal MVC auto-configuration to back off. It does not mean Spring MVC cannot have any default converters, but many of Boot's configuration conveniences will no longer be applied automatically as before. When you only want to add a converter, **do not add `@EnableWebMvc`**.

## 5. Complete Example: Adding the application/vnd.example.score Format

Suppose there is a small API that accepts an integer as plain text, increments it by one, and writes the result back in the same format:

~~~http
POST /scores/plus-one HTTP/1.1
Content-Type: application/vnd.example.score
Accept: application/vnd.example.score

41
~~~

Expected response is HTTP 200, with body:

~~~text
42
~~~

This is **not JSON**: the body is just digits representing an integer. We create a converter dedicated to the Java type `Score` and media type `application/vnd.example.score`. This converter does not handle `String`, `Map`, or JSON. As a result, when we add it to the list, existing converters remain in charge of existing formats.

### 5.1. Dependencies

The example uses **Spring Boot 3.x, Java 17+**, a Gradle project with the Spring Boot plugin and appropriate dependency management. In `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The web starter provides Spring MVC and core JSON libraries managed by Spring Boot in this example. No extra starter is needed for the custom converter because it is written directly with Spring APIs.

### 5.2. Runnable Java Code in a Spring Boot Project

Create file **`src/main/java/demo/converter/ConverterDemoApplication.java`**:

~~~java
package demo.converter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.http.converter.HttpMessageNotWritableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterDemoApplication.class, args);
    }
}

record Score(int value) {
}

final class ScoreHttpMessageConverter
        extends AbstractHttpMessageConverter<Score> {

    ScoreHttpMessageConverter() {
        super(MediaType.parseMediaType(
                "application/vnd.example.score"
        ));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return Score.class == clazz;
    }

    @Override
    protected Score readInternal(
            Class<? extends Score> clazz,
            HttpInputMessage input
    ) throws IOException, HttpMessageNotReadableException {
        String body = new String(
                input.getBody().readAllBytes(),
                StandardCharsets.UTF_8
        ).trim();

        try {
            return new Score(Integer.parseInt(body));
        } catch (NumberFormatException ex) {
            throw new HttpMessageNotReadableException(
                    "Score must be an integer",
                    ex,
                    input
            );
        }
    }

    @Override
    protected void writeInternal(
            Score score,
            HttpOutputMessage output
    ) throws IOException, HttpMessageNotWritableException {
        byte[] bytes = Integer.toString(score.value())
                .getBytes(StandardCharsets.UTF_8);
        output.getBody().write(bytes);
    }
}

@Configuration(proxyBeanMethods = false)
class ConverterMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters
    ) {
        // Add to the existing list without removing default converters.
        converters.add(0, new ScoreHttpMessageConverter());
    }
}

@RestController
class ConverterDemoController {

    @PostMapping(
            path = "/scores/plus-one",
            consumes = "application/vnd.example.score",
            produces = "application/vnd.example.score"
    )
    public Score plusOne(@RequestBody Score input) {
        return new Score(input.value() + 1);
    }

    @GetMapping(path = "/plain", produces = MediaType.TEXT_PLAIN_VALUE)
    public String plain() {
        return "text-ok";
    }

    @PostMapping(
            path = "/json/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> echoJson(
            @RequestBody Map<String, String> payload
    ) {
        return payload;
    }
}
~~~

**Why does this example work?**

1. `@SpringBootApplication` starts Spring MVC and scans classes in package `demo.converter`.
2. `ScoreHttpMessageConverter` declares support only for Java class `Score` and media type `application/vnd.example.score`.
3. `readInternal` reads the request body bytes into an integer and returns `Score`. If the body does not represent an `int`, it throws `HttpMessageNotReadableException` so MVC handles the body-reading error.
4. `writeInternal` converts the integer to UTF-8 bytes and writes them to the HTTP output body.
5. `ConverterMvcConfiguration` uses **`extendMessageConverters`**; the new converter is inserted at the start of the list without removing other converters.
6. The `/plain` endpoint continues using String handling, and `/json/echo` continues using the existing JSON converter.

`Score` is a record with no business logic beyond holding an integer value. `ScoreHttpMessageConverter` is only an example of a custom format: in practice, prefer standard formats like JSON unless there is a requirement to interoperate with a custom protocol.

### 5.3. Running and Testing over HTTP

From the Spring Boot project configured with the Gradle wrapper and main class above:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. If port 8080 is occupied or reconfigured, adjust the port accordingly.

In another terminal, call the new format:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: application/vnd.example.score' \
  -H 'Accept: application/vnd.example.score' \
  --data-binary '41'
~~~

In Bash-style shell syntax, `\` continues the line. In Windows PowerShell, run `curl.exe` on a single line or adapt line continuation syntax for your shell. When successful, **HTTP status is 200**, and the response body is:

~~~text
42
~~~

Verify the String converter still works:

~~~bash
curl -i -H 'Accept: text/plain' http://localhost:8080/plain
~~~

Expected body:

~~~text
text-ok
~~~

Verify the Jackson JSON converter was not lost:

~~~bash
curl -i http://localhost:8080/json/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"hello"}'
~~~

In an application with no interfering security/filters, the result returns a JSON body representing the same data, for example:

~~~json
{"message":"hello"}
~~~

These three checks serve distinct purposes: **the new converter works**, **plain text still works**, and **default JSON still works**. Testing only the custom endpoint is insufficient to prove existing configuration was not broken.

The example does not pin HTTP headers like `Date` or `Transfer-Encoding`; they may vary by Servlet container. Status and body are what should be verified here.

## 6. Converter Selection Sequence: canRead and canWrite

Spring MVC does not pick converters solely by class name. Key factors include:

- **The Java type** to read/write, such as `Score`, `String`, `Map`, `byte[]`, or a DTO.
- **The request's `Content-Type`** when reading `@RequestBody`.
- **The client's `Accept` header** and `produces` constraints when writing the response body.
- **The converter list and order** in which they are registered.
- Each converter's `canRead` / `canWrite` capability for the type and media type, along with generic-type-aware API variants.

In the example:

- Request body `41` with `Content-Type: application/vnd.example.score`, target `Score`: the custom converter is chosen to **read**.
- Controller returns `Score(42)` and client accepts the new media type: the custom converter is chosen to **write**.
- Controller returns `Map<String,String>` for JSON: the custom converter says it does not support `Map`; the JSON converter continues to be chosen.
- Controller returns `String` for `text/plain`: the custom converter says it does not support `String`; `StringHttpMessageConverter` does the job.

**Ordering matters when there is overlap**. If you create a converter claiming `canRead(Object.class, application/json)` or `canWrite(Object.class, */*)`, it can take over handling from existing JSON/String converters. For a converter dedicated to a specialized format, **strictly scope the Java types and media types** instead of declaring overly broad support.

In the example, placing the custom converter at the start of the list is safe because its scope is very narrow. If a new converter overlaps with Jackson, evaluate its position, selection conditions, and test each body type.

## 7. Content-Type, Accept, and Related Error Codes

**Content-Type** indicates the media type of the body the client **sends**. It influences which converter is used to read `@RequestBody`. **Accept** indicates the media types the client can **receive**. Together with `produces`, it influences response body writing.

| Scenario | Typical Result | How to Investigate |
|---|---|---|
| Client sends media type not matching `consumes` | HTTP 415 Unsupported Media Type | Check `Content-Type` and mapping |
| Converter cannot read body for target type | Usually 400 or 415 depending on cause | Check `canRead`, media type, payload, exception |
| Body fails to parse as an integer in the example | HTTP 400 Bad Request | Check body, format, and read error |
| Client only accepts media type not matching `produces` | HTTP 406 Not Acceptable | Check `Accept` and mapping |
| Converter cannot write return type | Response handling error, possibly 500/406 depending on path | Check `canWrite` and converter selection |
| No matching HTTP method mapping | Possibly 404 or 405 | Check request mapping; not necessarily a converter issue |

Example sending the wrong content type:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/vnd.example.score' \
  --data-binary '41'
~~~

The endpoint declares `consumes=application/vnd.example.score`, so in the illustrative setup it can respond with **HTTP 415** before the custom converter is even used to read the body.

Example where the client only accepts JSON:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: application/vnd.example.score' \
  -H 'Accept: application/json' \
  --data-binary '41'
~~~

Because the endpoint only declares `produces=application/vnd.example.score`, the result is usually **HTTP 406**. This is a **content negotiation** issue, not evidence that the JSON converter was removed.

If the body is `hello` instead of an integer with valid headers, the custom converter throws `HttpMessageNotReadableException`, leading to HTTP 400 under Spring MVC's default exception handling in the example.

**Do not confuse:** an endpoint returns 415/406 even when the JSON converter still exists if `consumes`, `produces`, or client headers are incompatible.

## 8. Adjusting Jackson JSON While Preserving Default Configuration

Many "customize converter" requests actually only need to adjust **Jackson rules**: omitting null fields, date/time formats, naming policies, or modules. Do not replace all of `MappingJackson2HttpMessageConverter` just to enforce a common JSON rule.

### 8.1. Prefer Spring Boot Properties

Example `application.yml` in a Spring Boot/Jackson 2 application with corresponding configuration:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
    serialization:
      indent_output: false
~~~

Configuration makes the intent clear and lets Spring Boot continue building the default `ObjectMapper`/converter. Actual property names may differ across major versions or JSON libraries; check against your running version.

When you only need to hide nulls on a single DTO, consider Jackson annotations on the class/field rather than changing the entire application's JSON policy.

### 8.2. Use Jackson2ObjectMapperBuilderCustomizer When Code Is Needed

In **Spring Boot 3.x with Jackson 2**, a customizer bean can look like this:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JacksonSerializationConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer includeNonNullFields() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

This configuration class must be visible to Spring Boot's package scan. `Jackson2ObjectMapperBuilderCustomizer` adjusts how the builder configures `ObjectMapper`; Boot's JSON converter normally remains intact. This affects all `ObjectMapper` instances built via the associated builder, not just one controller; evaluate its scope before applying globally.

Do not use both `spring.jackson.default-property-inclusion` and an equivalent customizer with different values without checking precedence rules. When a difference is needed for only one endpoint, use DTO-specific annotations or targeted configuration instead of a global policy.

### 8.3. Avoid Creating a Blank ObjectMapper to Replace the Converter

A side-effect-prone example is:

~~~java
// Risk illustration: DO NOT blindly replace default converters.
converters.removeIf(c ->
        c instanceof MappingJackson2HttpMessageConverter);
converters.add(new MappingJackson2HttpMessageConverter(
        new ObjectMapper()));
~~~

This is a fragment, not standalone Java source. Calling `new ObjectMapper()` can lose modules, custom serializers/deserializers, naming policies, Java time support, and customizations registered through Boot. Removing and re-adding the converter can also change ordering or supported media types.

If you genuinely must replace the converter, intentionally reproduce the required settings, check the impact on both requests and responses, and cover it with integration tests. **Do not recreate the converter just to enable a simple Jackson option.**

## 9. Modifying an Existing Converter Inside extendMessageConverters

Some projects need to modify an existing element. `extendMessageConverters` receives the list Spring MVC has built, so you can find by type, adjust in a controlled way, and keep the remaining elements untouched.

Example of merely **inspecting** the list in a debug environment without changing order:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters
) {
    for (HttpMessageConverter<?> converter : converters) {
        System.out.println(
                converter.getClass().getSimpleName()
        );
    }
}
~~~

This is a fragment inside a class implementing `WebMvcConfigurer`. Do not repeatedly log the entire list at a high level in production, though startup logging can help verify which converters actually exist.

If you want to expand an existing converter's media types, **copy** `getSupportedMediaTypes()` first, check the value to add, and call `setSupportedMediaTypes(...)` if the converter's API allows it. Do not call `list.clear()` or `converters.clear()` when the goal is just to add one format. Remember that a Jackson converter already supports broad media types like `application/*+json`; manually adding compatible JSON subtypes may be completely unnecessary.

Avoid mutating the state of a shared `ObjectMapper` used across multiple components once the application is serving traffic. Customize during startup configuration; do not update converter/`ObjectMapper` settings per request to avoid race conditions and unpredictable behavior.

## 10. Automated Testing That a New Converter Does Not Break Defaults

Seeing Spring Boot start up successfully is not enough: failures may surface only when JSON or plain text endpoints are called. A test strategy should protect **at least three behaviors**:

1. The custom-format API reads and writes bodies correctly.
2. JSON APIs read and write as before.
3. Plain text APIs still return `String`.

In a project with `spring-boot-starter-test`, `MockMvc` can execute MVC requests in tests. Here is a Spring Boot test using the actual converter configuration:

~~~java
package demo.converter;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ConverterMvcIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customScoreConverterWorks() throws Exception {
        mvc.perform(post("/scores/plus-one")
                .contentType("application/vnd.example.score")
                .accept("application/vnd.example.score")
                .content("41"))
           .andExpect(status().isOk())
           .andExpect(content().string("42"));
    }

    @Test
    void defaultPlainTextStillWorks() throws Exception {
        mvc.perform(get("/plain")
                .accept(MediaType.TEXT_PLAIN))
           .andExpect(status().isOk())
           .andExpect(content().string("text-ok"));
    }

    @Test
    void defaultJsonStillWorks() throws Exception {
        mvc.perform(post("/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
           .andExpect(status().isOk())
           .andExpect(content().json(
                   "{\"message\":\"hello\"}"
           ));
    }
}
~~~

Create **`src/test/java/demo/converter/ConverterMvcIntegrationTest.java`** and add the dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Command to execute with Gradle:

~~~bash
./gradlew test
~~~

The tests pass when the project uses the example configuration, the test runtime has JUnit/Spring Test, and no security, profile, or other configuration alters mappings/responses. `MockMvc` runs inside MVC test infrastructure rather than opening a real socket server. To verify real HTTP server behavior (content type/proxy/container), add a `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client.

**Testing takeaway:** avoid testing only the new converter and concluding "defaults were preserved." Include regression tests for at least the key default converters your system relies on, especially JSON if APIs use it heavily.

## 11. Checking Registered Converters and Actual Order

When a custom converter is not selected, check step by step:

- Is the configuration class scanned by Spring? Is `@Configuration` inside the application entrypoint's package?
- Does the application run Spring MVC Servlet or WebFlux? The two stacks have different codec/converter pipelines.
- Does another `WebMvcConfigurer` bean alter the converter list or ordering?
- Does `@EnableWebMvc` or a `WebMvcConfigurationSupport` subclass alter Boot's MVC auto-configuration?
- Does the converter actually return `true` for the request/response type + media type?
- Does `@RequestMapping` declare `consumes` or `produces` that rejects the request before converter selection?
- Does the client send matching `Content-Type` and `Accept`?
- Is Jackson/JSON library actually on the runtime classpath?
- Did an overly broad custom converter get registered and intercept work meant for default converters?
- Was a duplicate converter registered via both `@Bean` and `extendMessageConverters`?

Do not rely on bean names or converter counts to guess priority; Spring MVC uses read/write capability and the actual list order. If you must log the list, do so in a controlled manner at startup, never logging bodies containing tokens, passwords, or sensitive information.

## 12. Common Mistakes and How to Fix Them

### 12.1. Using configureMessageConverters to Add One Element

**Symptom:** after adding an XML/custom converter, JSON or String endpoints return errors.

**Cause:** populating the list in `configureMessageConverters` can prevent Spring MVC from auto-registering default converters through the normal path.

**Fix:** move the addition to `extendMessageConverters` or register a converter bean via Boot's mechanism with controlled type/ordering. Re-test JSON/text.

### 12.2. Adding @EnableWebMvc Just to Customize Bodies

**Symptom:** some MVC configurations provided by Spring Boot stop working as before, even though controllers still run.

**Cause:** `@EnableWebMvc` shifts ownership of MVC configuration, so standard Spring Boot MVC auto-configuration no longer applies as when merely implementing `WebMvcConfigurer`.

**Fix:** remove the annotation if full MVC control is not needed and use plain `WebMvcConfigurer`. Re-verify message converters, static resources, path matching, CORS, and other MVC features as needed.

### 12.3. Creating a Converter Supporting Object.class and */*

**Symptom:** JSON bodies are mistakenly processed by the custom converter, or content negotiation returns the wrong format.

**Cause:** `supports` or supported media types are too broad, combined with high converter priority.

**Fix:** restrict the Java type/media type and test multiple endpoints with different bodies. Do not use `*/*` as a default supported media type unless you understand the consequences.

### 12.4. Replacing ObjectMapper and Losing Configured Modules

**Symptom:** date/time data serializes differently, and annotations or custom modules stop taking effect.

**Cause:** creating `new ObjectMapper()` and replacing the default Jackson converter instead of adjusting the builder or properties.

**Fix:** prefer `spring.jackson.*` and `Jackson2ObjectMapperBuilderCustomizer` when compatible, or deliberately reuse existing `ObjectMapper` configuration.

### 12.5. Confusing 415 and 406

**Symptom:** requests fail and developers look for bugs in the controller even though the handler never ran.

**Cause:** `Content-Type` does not match `consumes`, or `Accept` does not match `produces`.

**Fix:** inspect headers and mappings before editing converters; write dedicated negative test cases.

### 12.6. Converter Does Not Handle Malformed Data Clearly

**Symptom:** parsing errors cause 500 or return confusing messages.

**Cause:** custom conversion code throws an inappropriate exception or fails to bound input.

**Fix:** for unreadable request bodies, use `HttpMessageNotReadableException` or handle errors via Spring MVC appropriately; enforce size limits and input validation. Do not print raw sensitive request bodies to logs.

### 12.7. Ignoring Charset and Encoding

**Symptom:** Vietnamese characters are corrupted or bytes do not match a digitally signed body.

**Cause:** relying on the OS default charset, misinterpreting `Content-Type`, or arbitrarily transforming bytes.

**Fix:** use an explicit charset when the format handles text; the example converter uses `StandardCharsets.UTF_8`. For binary formats or protocols with client-specified charsets, handle according to the real media type contract rather than always calling `trim()` as in the integer example.

### 12.8. Reading the Stream Twice

**Symptom:** body is empty in the controller or converter because a filter already read the body earlier.

**Cause:** the request input stream is typically single-read; a filter consumed the content without proper wrapping/caching.

**Fix:** do not arbitrarily read the body in filters; if body logging is necessary, cap size and use responsible request wrapping. Converters are designed to consume the request body at the proper MVC stage.

### 12.9. Converter Holds Per-Request Mutable State

**Symptom:** concurrent requests return mixed-up data or fail intermittently.

**Cause:** a converter is a shared component, yet stores parsed/written per-request content in instance fields.

**Fix:** use local variables inside `readInternal` and `writeInternal`; keep converter configuration immutable at runtime, or synchronize properly if shared mutable state truly exists.

### 12.10. Testing Only the New Format

**Symptom:** the custom API works, but legacy JSON clients fail in production.

**Cause:** lack of regression tests for default converters.

**Fix:** test the custom media type, JSON, plain text, and formats like `byte[]`/resource/form that the real system depends on side by side.

## 13. When Should You Not Write a Custom HttpMessageConverter?

Not every data transformation needs a converter:

- **Changing JSON date/time format:** usually use Jackson config/serializers.
- **Changing just one DTO field:** use Jackson annotations, serializers, or an appropriate data type.
- **Validating business values:** use Bean Validation and services, not tight coupling inside an HTTP parser.
- **Converting query parameters to enums/objects:** use `Converter` or `Formatter` in Spring MVC's conversion service; that is not an `HttpMessageConverter` for bodies.
- **Standardizing response envelopes:** consider `ResponseBodyAdvice`, depending on impact on content types and converters.
- **Standardizing exception responses:** use `@RestControllerAdvice` / `@ExceptionHandler` appropriately.
- **Need HTTP client codecs:** `RestClient`, `RestTemplate`, or `WebClient` have their own message converter/codec configuration; do not assume server MVC customizers automatically apply to all clients.
- **Reactive server processing:** Spring WebFlux uses `HttpMessageReader`/`HttpMessageWriter` and codec configuration, not Servlet MVC's `WebMvcConfigurer`.

Only write a custom converter when you **genuinely have a specialized wire format** that must integrate at the HTTP body boundary with MVC APIs. The more narrowly you define read/write capability, the lower the risk of altering default converter behavior.

## 14. Safe Implementation Checklist

1. Confirm the application actually runs on the **Spring MVC Servlet stack**, with required dependencies on the runtime classpath.
2. Separate the need to add a **new media type** from merely adjusting **JSON rules**; if only adjusting JSON, prefer properties/builder customizers.
3. If adding a converter, implement read/write support for specific types and media types; handle malformed input cleanly and keep no per-request state.
4. Register via `WebMvcConfigurer#extendMessageConverters` or Boot's appropriate bean mechanism; **never clear the default list**.
5. Do not use `configureMessageConverters` or `@EnableWebMvc` just to add a simple converter.
6. Check ordering if the custom converter has overlapping scope; remove duplicate registrations.
7. Test requests with matching `Content-Type`, `Accept`, and `consumes`/`produces` constraints.
8. Separately test malformed bodies, wrong media types, incompatible `Accept` headers, and oversized payloads.
9. Run regression tests at minimum for **JSON + String + the new media type**, plus any other default converters the system relies on.
10. Observe the actual failure before editing code: 400, 415, 406, and response-write errors do not mean the same thing.
11. Do not log sensitive bodies; avoid mutating `ObjectMapper`/converters while the server is serving traffic.
12. After upgrading Spring Boot/Spring Framework major versions, re-check packages/APIs and auto-configuration instead of blindly copying older code.

**Conclusion:** `HttpMessageConverter` is the conversion layer for **HTTP body ↔ Java object** in Spring MVC. When the requirement is simply **controlled addition or adjustment**, use **`extendMessageConverters`** to keep the list Spring MVC/Spring Boot built. If only changing JSON rules, prefer Jackson configuration over replacing the converter yourself. A change is truly safe only when **the new converter works and existing JSON, text, and resource endpoints continue passing regression tests**.
