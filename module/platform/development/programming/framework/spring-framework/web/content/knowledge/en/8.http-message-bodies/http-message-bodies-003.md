# Configuring HTTP Converters: Replacing Defaults vs. Extending the List in Spring MVC

## 1. Objectives and Context

In Spring MVC, when a controller receives a JSON request and returns JSON, turning **HTTP body bytes** into a Java object and vice versa is typically performed by `HttpMessageConverter`. Misconfiguring the converter list can cause previously working endpoints to suddenly return **415 Unsupported Media Type** or **406 Not Acceptable**. The central question of this lesson is: **when should you replace all default converters, and when should you simply extend the existing list?**

After this lesson, you will:
- Understand where Spring MVC uses `HttpMessageConverter`, how it selects a converter when reading and writing bodies, and the role of `Content-Type`, `Accept`, and list order.
- Distinguish `WebMvcConfigurer#configureMessageConverters` from `extendMessageConverters` in **Spring Framework 6.x**; understand the difference between plain Spring MVC and **Spring Boot 3.x**.
- Implement a custom converter, add it to the list while keeping default JSON working, and verify it through a controller, `curl`, and `MockMvc`.
- Know when to configure Jackson/`ObjectMapper`, use a Spring Boot converter bean, or intentionally replace the whole list; avoid confusing body converters with form/query parameter converters.

**Pinned version to avoid API confusion:** the code examples and signatures `configureMessageConverters(List<HttpMessageConverter<?>>)` / `extendMessageConverters(List<HttpMessageConverter<?>>)` here apply to **Spring Framework 6.x / Spring Boot 3.x, Java 17+**. Starting in Spring Framework 7, the configuration API evolved toward a builder model; do not copy the signatures here into a 7.x project without checking the documentation for your version.

## 2. At Which Step Is a Converter Invoked?

Consider two requests:

~~~http
POST /api/greetings/json HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"text":"hello"}
~~~

~~~http
POST /api/greetings/custom HTTP/1.1
Host: localhost:8080
Content-Type: application/vnd.demo.uppercase
Accept: application/vnd.demo.uppercase

hello
~~~

In the first example, Spring MVC can use the Jackson converter to read the JSON body into a `Greeting` object and write the object as JSON. In the second example, we will create a custom converter that reads text for a custom media type and writes it out in uppercase.

Typical processing flow:

1. `DispatcherServlet` routes the request to a handler.
2. For `@RequestBody` parameters (or a `@RequestPart` part that needs payload conversion), Spring MVC looks for a converter capable of **reading** the target Java type with the given `Content-Type`.
3. The handler processes the deserialized object.
4. For `@ResponseBody`, `@RestController`, or `ResponseEntity<T>`, Spring MVC selects a converter capable of **writing** the result type in the media type negotiated from `Accept`, `produces`, and configuration.
5. The converter uses the HTTP stream to read/write the actual bytes.

The `HttpMessageConverter<T>` interface defines behaviors such as `canRead`, `canWrite`, `read`, `write`, and supported media types. A converter can support reading, writing, or both, depending on its implementation.

`Content-Type` describes the **incoming body**; `Accept` describes the **response format the client accepts**. `consumes` and `produces` on a handler constrain which route is selected. They do not create converters by themselves and do not guarantee that the data can actually be parsed.

A few familiar converters (actual availability depends on the classpath and configuration):

| Converter | Purpose |
| --- | --- |
| `MappingJackson2HttpMessageConverter` | JSON to/from Java objects via Jackson (Framework 6.x) |
| `StringHttpMessageConverter` | Text string bodies |
| `ByteArrayHttpMessageConverter` | Reading/writing `byte[]` arrays |
| `ResourceHttpMessageConverter` | Working with `Resource` |
| `FormHttpMessageConverter` or `AllEncompassingFormHttpMessageConverter` | Handling form data and certain multipart write cases |
| XML converters | JSON/XML depending on related libraries on the classpath |

This is the **Spring MVC Servlet stack** mechanism, not `HttpMessageReader`/`HttpMessageWriter` in Spring WebFlux.

## 3. Two `WebMvcConfigurer` Hooks: The Core Difference

In Spring Framework 6.x:

~~~java
public interface WebMvcConfigurer {
    default void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {}

    default void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {}
}
~~~

The snippet above **mimics the signatures of the two methods**, not the full actual interface definition.

### 3.1. `configureMessageConverters`: Declaring the List from Scratch

In **plain Spring MVC** configuration, the list passed in starts empty. If `configureMessageConverters` configurations add converters to the list, **the framework's default converter registration does not run in the usual way**. You must ensure every format your system needs has a suitable converter.

The example below illustrates the **replacement approach** only for plain Spring MVC. **Do not add this class to the hands-on project in Section 5**:

~~~java
package com.example.demo.replace;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ReplaceConvertersConfig implements WebMvcConfigurer {

    @Override
    public void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(new MappingJackson2HttpMessageConverter());
    }
}
~~~

If the effective list ends up containing only the JSON converter, features relying on `StringHttpMessageConverter` or `ByteArrayHttpMessageConverter` can stop working. You must explicitly register all other needed converters when choosing replacement; do not fix one JSON issue only to accidentally drop support for text, bytes, forms, XML, or other body types.

**Important Spring Boot exception:** Spring Boot 3.x auto-configures converters and adds `HttpMessageConverter` beans through its `HttpMessageConverters` mechanism. Therefore, do not mechanically assume that adding one converter in `configureMessageConverters` will drop *all* converters in a Boot application. The effective result depends on Boot auto-configuration and other `WebMvcConfigurer` beans. When you need an additional converter while preserving Boot behavior, the more predictable approach is `extendMessageConverters` or Boot's converter registration mechanism.

### 3.2. `extendMessageConverters`: Adding to or Adjusting the List Afterward

This hook receives the already-configured list (including default converters, or the list set up by other configs) so you can **add, remove, reorder, or fine-tune**:

~~~java
@Configuration
public class ExtendConvertersConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new UppercaseGreetingConverter());
    }
}
~~~

This is an illustration in class form: it requires importing `Configuration`, `WebMvcConfigurer`, `HttpMessageConverter`, and having `UppercaseGreetingConverter` in the same project. The complete application in Section 5 provides all files.

- `add(0, ...)` puts the new converter at the **front of the list**, giving it priority if multiple converters support the same type and media type.
- `add(...)` at the end is generally a lower-impact choice when the added format is very specific.
- If the new converter's support is overly broad (`*/*`, `Object.class`), placing it first can "hijack" existing JSON/text handling.
- `extend` **does not guarantee defaults are kept** if you yourself call `converters.clear()`, `removeIf(...)`, or modify existing converters in a way that breaks reading/writing. The method name does not protect against breaking changes.

| Aspect | `configureMessageConverters` | `extendMessageConverters` |
| --- | --- | --- |
| When called in the MVC 6.x lifecycle | During converter list configuration | After default configuration / registration |
| Common purpose | Explicitly control the converter set used | Keep and customize the existing list |
| In plain Spring MVC | Adding a converter usually disables default registration | Defaults are populated first before extending if needed |
| Risk | Missing legacy read/write capabilities | Ordering conflicts or accidentally modifying/removing converters |
| Recommendation in Spring Boot 3.x | Must account for Boot auto-config interactions | Usually more convenient when only adding |
| What to verify | Effective converter list and multiple media types | List/ordering, existing JSON, and new media type |

### 3.3. When to Intentionally Replace Everything?

Only consider intentionally replacing the default set when you tightly control every format your application is permitted to exchange (e.g., a specialized API protocol or constrained environment). In that case, thoroughly test all active `@RequestBody`, `@ResponseBody`, `ResponseEntity`, exception responses, file/resource downloads, multipart/form, text, and JSON paths.

For common needs such as adding a media type, changing JSON naming strategy, swapping a serializer, or supporting a new payload type, you **do not need to tear down the default list**.

## 4. How Does Plain Spring MVC Differ from Spring Boot?

### Plain MVC Configuration

In Spring MVC enabled via `@EnableWebMvc`, Spring Framework registers MVC infrastructure components and supplies a default set of converters based on available libraries. `configureMessageConverters` lets you specify your own list, while `extendMessageConverters` lets you intervene after configuration. If both are used and `configure` populates converters, `extend` sees the list created by `configure`; do not assume defaults were kept.

### Spring Boot 3.x

`spring-boot-starter-web` typically includes Jackson and auto-configuration for JSON. Spring Boot collects `HttpMessageConverter` beans, adds/overrides certain default converters, and provides `HttpMessageConverters` to manage the composite list. Common configuration paths:

1. Keep auto-configuration and declare a custom converter bean when an extra converter is needed.
2. Use `WebMvcConfigurer#extendMessageConverters` when you need to control position or tweak the existing list.
3. For JSON, prefer `spring.jackson.*`, a `Jackson2ObjectMapperBuilderCustomizer` bean, or Jackson modules/DTO annotations if you only want to change part of serialization.
4. When full MVC control is required, you can opt for `@EnableWebMvc` or subclass advanced MVC configuration. **That choice makes Spring Boot back off from significant Web MVC auto-configuration**, so only use it when intentionally managing the consequences.

Do not add `@EnableWebMvc` to a `WebMvcConfigurer` class in a typical Spring Boot app just to register a converter.

**Version note:** `HttpMessageConverters` and builder/configuration mechanisms evolve across Spring Boot/Framework generations. When upgrading from Boot 3 to Boot 4/Framework 7, check the corresponding version's Javadoc instead of keeping 6.x API imports unchanged.

## 5. Practice: Adding a Custom Media Type While Keeping JSON Working

In this exercise, we build the `application/vnd.demo.uppercase` media type. The client sends text `hello`; the controller receives a `Greeting` object and returns the same object; the converter writes body `HELLO`. Alongside it, the default JSON endpoint continues reading and writing `{"text":"hello"}`.

Create a project via Spring Initializr with **Spring Boot 3.x**, **Java 17+**, **Maven**, and the **Spring Web** dependency. Add **Spring Boot Starter Test** to run the MockMvc tests. Do not add `ReplaceConvertersConfig` from Section 3.

File structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/Greeting.java
src/main/java/com/example/demo/UppercaseGreetingConverter.java
src/main/java/com/example/demo/ConverterConfig.java
src/main/java/com/example/demo/GreetingController.java
src/test/java/com/example/demo/GreetingControllerTest.java
~~~

### 5.1. Entry Point

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 5.2. Data Type

**`src/main/java/com/example/demo/Greeting.java`**

~~~java
package com.example.demo;

public record Greeting(String text) {
}
~~~

Jackson bundled with Starter Web in Boot 3.x supports this record using JSON with a `text` property.

### 5.3. Writing a Converter with a Narrow Media Type

**`src/main/java/com/example/demo/UppercaseGreetingConverter.java`**

~~~java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;

public class UppercaseGreetingConverter
        extends AbstractHttpMessageConverter<Greeting> {

    public static final String MIME = "application/vnd.demo.uppercase";

    public UppercaseGreetingConverter() {
        super(MediaType.parseMediaType(MIME));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return Greeting.class.equals(clazz);
    }

    @Override
    protected Greeting readInternal(
            Class<? extends Greeting> clazz,
            HttpInputMessage inputMessage) throws IOException {

        byte[] body = inputMessage.getBody().readAllBytes();
        String text = new String(body, StandardCharsets.UTF_8);
        return new Greeting(text);
    }

    @Override
    protected void writeInternal(
            Greeting greeting,
            HttpOutputMessage outputMessage) throws IOException {

        String upper = greeting.text().toUpperCase(Locale.ROOT);
        outputMessage.getBody()
                .write(upper.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

Details to understand:

- `AbstractHttpMessageConverter<Greeting>` implements most of the `HttpMessageConverter` contract, letting you focus on the supported Java type, reading, and writing.
- `supports` only accepts `Greeting.class`; the constructor registers **one** custom media type. The converter does not hijack Jackson's JSON (`application/json`) data.
- `readInternal` reads UTF-8 bytes from the HTTP request and creates `Greeting`; `writeInternal` produces uppercase using `Locale.ROOT` and writes UTF-8 bytes. It does not append a newline.
- `readAllBytes()` keeps the example simple; **in production**, enforce request size limits at the server/proxy before buffering bodies, or use streaming where appropriate. This example is not meant for large payloads.
- Input data is treated as UTF-8 text per the **custom media type contract of the example**. Real converters should inspect charsets and encoding rules, reporting errors on invalid data.
- For types with polymorphic subtypes, `supports(Greeting.class.equals(clazz))` may be too strict; here it is an intentional choice to prevent the converter from catching unrelated types.

### 5.4. Extending Instead of Replacing the Default List

**`src/main/java/com/example/demo/ConverterConfig.java`**

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new UppercaseGreetingConverter());
    }
}
~~~

Only `extendMessageConverters` is used. We add the custom converter to the effective list without wiping out existing JSON converter configuration. With narrow media type and narrow class support, `add(0, ...)` is safe within this example: the converter only competes when both the **Java type and media type** match. In real systems, evaluate the order and media types of other converters before choosing an index.

### 5.5. Controller Testing Both the Custom Format and JSON

**`src/main/java/com/example/demo/GreetingController.java`**

~~~java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @PostMapping(
            path = "/custom",
            consumes = UppercaseGreetingConverter.MIME,
            produces = UppercaseGreetingConverter.MIME)
    public Greeting custom(@RequestBody Greeting greeting) {
        return greeting;
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Greeting json(@RequestBody Greeting greeting) {
        return greeting;
    }
}
~~~

The `/custom` handler needs the custom converter on both the request and response paths; the `/json` handler needs Boot's Jackson converter. If default converters are replaced carelessly, the JSON test will catch the regression.

## 6. Running and Reading HTTP Results

From the project directory containing `pom.xml`, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run`; if the project has no wrapper, use `mvn spring-boot:run` when Maven is installed.

Send a text body with the custom media type:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/vnd.demo.uppercase"   -H "Accept: application/vnd.demo.uppercase"   --data-binary "hello"
~~~

**Expected result:** status **200 OK**, response header with `Content-Type` compatible with `application/vnd.demo.uppercase`, and **exact body**:

~~~text
HELLO
~~~

`writeInternal` does not add a newline character to the HTTP body; the Markdown block above has newlines for display, not to imply a trailing newline in the response.

Verify default JSON still works:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/json"   -H "Content-Type: application/json"   -H "Accept: application/json"   --data-binary '{"text":"hello"}'
~~~

**Expected result:** **200 OK** and an equivalent JSON body:

~~~json
{"text":"hello"}
~~~

JSON property order is not guaranteed. If running in Windows PowerShell, use `curl.exe` instead of the `curl` alias; JSON escaping and line continuations must match your shell. The commands above are for Linux/macOS/Git Bash.

### 6.1. Testing 415 and 406

Request with wrong `Content-Type` for the custom endpoint:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/json"   -H "Accept: application/vnd.demo.uppercase"   --data-binary '{"text":"hello"}'
~~~

Typical result: **415 Unsupported Media Type** because the handler only accepts `application/vnd.demo.uppercase`. Even though the application has Jackson, the handler's `consumes` condition still governs route selection.

Request accepting an incompatible response format:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/vnd.demo.uppercase"   -H "Accept: application/json"   --data-binary "hello"
~~~

Typical result: **406 Not Acceptable**, because the handler declares only `produces = application/vnd.demo.uppercase`, which cannot satisfy `Accept: application/json`. Error body content can vary by Spring Boot configuration, Servlet container, and `@ControllerAdvice`, so only assert status codes and the HTTP contract.

**Distinction:** 415 usually relates to the **request body's** media type; 406 relates to the **response** media type requested by the client; 400 can occur when the body has an accepted media type but the data cannot be parsed into the Java type.

## 7. Automated Testing with MockMvc

Add the `spring-boot-starter-test` dependency to the project. In Spring Boot 3.x, write:

**`src/test/java/com/example/demo/GreetingControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@Import(ConverterConfig.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void newConverterReadsAndWritesCustomMediaType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(UppercaseGreetingConverter.MIME)
                        .accept(UppercaseGreetingConverter.MIME)
                        .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        UppercaseGreetingConverter.MIME))
                .andExpect(content().string("HELLO"));
    }

    @Test
    void jacksonJsonStillReadsAndWrites() throws Exception {
        mockMvc.perform(post("/api/greetings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("hello"));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(UppercaseGreetingConverter.MIME)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseMediaType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(UppercaseGreetingConverter.MIME)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("hello"))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

All four tests are necessary because verifying that the custom endpoint succeeds **does not prove** default JSON still works. The second test is the core regression check when comparing "extend" vs. "replace". `@Import(ConverterConfig.class)` ensures the converter configuration is loaded into the test slice. `@WebMvcTest` tests the MVC stack with `MockMvc` without starting a real server.

If the test class lives in a project with Spring Security enabled with auth/CSRF rules, configure MockMvc according to that policy; do not arbitrarily disable security just to test converters. The sample project includes only Spring Web and Starter Test.

## 8. Changing JSON Behavior Without Writing a New Converter

If your goal is to change how Jackson serializes/deserializes JSON, customizing **Jackson** is usually simpler than replacing or creating an `HttpMessageConverter`. For example, Spring Boot 3.x can configure:

~~~properties
spring.jackson.serialization.indent_output=true
spring.jackson.default-property-inclusion=non_null
~~~

Note that these properties adjust JSON indentation and omit null properties in Jackson; they do not change media types or affect text or form converters. When upgrading, check the property list supported by your Boot version.

For more complex logic, you can register a `Jackson2ObjectMapperBuilderCustomizer` to configure the `ObjectMapper` built by Boot. If you manually instantiate `MappingJackson2HttpMessageConverter` with `new ObjectMapper()`, you can lose modules, Java Time support, mix-ins, naming strategies, and other settings prepared by Boot/Jackson. Using `@JsonFormat`, `@JsonProperty`, or a custom serializer on a DTO can even scope changes to a single model, which is safer for the whole application.

Sometimes you need to modify an existing converter inside `extendMessageConverters`. Illustrative example:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    for (HttpMessageConverter<?> candidate : converters) {
        if (candidate instanceof MappingJackson2HttpMessageConverter jackson) {
            // Found the Jackson converter.
            // Only make intentional, tested configuration adjustments.
        }
    }
}
~~~

This is an **illustrative snippet**, not a standalone Java class; it requires the corresponding imports and annotations/config. Avoid mutating a shared `ObjectMapper` after it has started serving requests: many Jackson settings are designed to be established at startup. If you need to adjust a specific converter, prepare the mapper/configuration before the server runs, and check for side effects on other places sharing that mapper.

## 9. Converter Order and Content Negotiation

Spring MVC may have multiple converters for a given Java type and media type. When converters both report `canRead`/`canWrite`, **registration order** can decide which converter is chosen. Especially when the client sends `Accept: */*`, an earlier converter is likely to be preferred. However, response selection also depends on `produces`, supported media types, return type, and content negotiation; the first converter in the list does not always win unconditionally.

Principles to follow:

- Keep `supportedMediaTypes` very narrow for custom converters (e.g., `application/vnd.demo.uppercase`), avoiding `MediaType.ALL` unless genuinely required.
- Only support the exact Java type in `supports`, or add explicit generic type checks if implementing `GenericHttpMessageConverter`.
- If you must override a default converter for the same type/media type, order intentionally and test **both reading and writing**; in Boot, consider bean/`HttpMessageConverters` mechanics.
- Avoid placing a generic converter accepting `Object` at the top of the list; it can intercept `MappingJackson2HttpMessageConverter` and return the wrong content or media type.
- Check request `Content-Type`, `Accept`, `consumes`, and `produces`. A 406/415 status alone is not enough to conclude a converter is "missing" before inspecting all of them.
- Never set `produces` inaccurately: a controller claiming JSON while a converter writes non-JSON text breaks the API contract.

To verify in a running system, you can inspect the registered converter list via `RequestMappingHandlerAdapter#getMessageConverters()` after context initialization; the result depends on auto-config and other `WebMvcConfigurer` beans. Reading a single config class alone is not enough to know the full effective list.

## 10. Distinguishing HTTP Body Converters from Data Binding

Spring MVC has two conversion groups with **different responsibilities**:

| Problem | Appropriate Mechanism | Example |
| --- | --- | --- |
| JSON body into Java object | `HttpMessageConverter` | `@RequestBody Greeting body` |
| Java object into JSON response | `HttpMessageConverter` | `@RestController` returning `Greeting` |
| JSON part in multipart | `HttpMessageConverter` per part | `@RequestPart("metadata") SomeDto dto` |
| Query parameter string into `LocalDate` | `ConversionService` / `Formatter` | `@RequestParam LocalDate date` |
| Form field string into model property | `WebDataBinder` and conversion/formatting | `@ModelAttribute Form form` |
| String needing trimming before form bind | `@InitBinder`/appropriate editor/formatter | `WebDataBinder.registerCustomEditor(...)` |

Do not modify `configureMessageConverters` to handle `@RequestParam("date") LocalDate date`; you normally need `Converter<String, LocalDate>`, `Formatter`, or `@DateTimeFormat`. Conversely, a conversion service `Converter<String, String>` does not automatically decode JSON bodies.

This confusion especially arises when a controller has both `@RequestBody` and `@RequestParam`: each parameter type has its own resolution and conversion mechanism.

## 11. Common Configuration Mistakes

### Mistake 1: Adding Only One Converter in `configureMessageConverters` in Plain MVC

**Symptom:** the new JSON endpoint works, but `String`, binary, form, or other format responses break.

**Cause:** an explicit list skips the usual default registration step.

**Fix:** switch to `extendMessageConverters` if only adding functionality; if genuinely replacing, declare every required converter and test existing endpoints.

### Mistake 2: Letting a Custom Converter Support `*/*` and `Object.class`

**Symptom:** `application/json` responses are sometimes written as custom text; the original serializer is never invoked.

**Cause:** the custom converter matches too many types/media types and has higher priority.

**Fix:** narrow `supports`, `supportedMediaTypes`, and list position; test JSON/text in both read and write directions.

### Mistake 3: Using `@EnableWebMvc` Just to Change One Converter in Spring Boot

**Symptom:** Boot's web/resource handling and many MVC customizations change unexpectedly.

**Cause:** `@EnableWebMvc` switches the app to manual MVC management, disabling common MVC auto-configuration paths.

**Fix:** use a plain `WebMvcConfigurer` bean without `@EnableWebMvc`, or use Boot's provided converter mechanisms.

### Mistake 4: Sending JSON with `Content-Type: text/plain`

**Symptom:** `@RequestBody` DTO fails to parse or returns status 415.

**Cause:** the Jackson converter normally targets JSON media types, whereas the header claims plain text.

**Fix:** send the proper `application/json` header and valid JSON data; do not change the converter to accept `*/*` to mask client errors.

### Mistake 5: Testing Only HTTP 200

**Symptom:** the new API works, while older APIs using other default converters break after deployment.

**Fix:** include regression tests for at least JSON read/write, the new media type, 415, and 406; expand to any text/bytes/form endpoints actually in use.

### Mistake 6: Confusing Validation Errors with Converter Errors

**Symptom:** the request converts to a Java object successfully, then fails with 400 due to `@Valid`.

**Cause:** the converter decoded the body successfully; the error occurred later during validation.

**Fix:** inspect the corresponding exception and logs (e.g., JSON parse errors usually produce `HttpMessageNotReadableException`; validation failures may produce `MethodArgumentNotValidException`), identifying the layer before changing configuration.

### Mistake 7: Assuming MVC Config Always Applies to RestClient or WebFlux

**Symptom:** a `RestClient` or reactive endpoint does not use the converter added in MVC.

**Cause:** HTTP clients and WebFlux have their own stacks; do not assume they share the converter list with the Spring MVC server.

**Fix:** configure the corresponding client or reactive codecs properly and test separately.

## 12. Decision Rules and Checklist

| Need | Best Starting Approach |
| --- | --- |
| Only add a new media type/Java type to MVC | `extendMessageConverters` with a narrow converter |
| Using Spring Boot 3.x with a custom converter bean | Register an `HttpMessageConverter` bean per Boot conventions; consider `HttpMessageConverters` if needed |
| Want to change JSON naming/date/null/indent | Jackson annotations, `spring.jackson.*`, customizer/`ObjectMapper` |
| Want to replace a specific default converter | Boot converter/bean override mechanism or `extend` with explicit ordering; test |
| Need full control over all supported protocols in plain MVC | `configureMessageConverters` and register all needed converters |
| Want to convert query/form fields | `ConversionService`, `Formatter`, `@InitBinder`, not HTTP body converters |

Before promoting a configuration to production, verify: **(1)** which framework and Boot versions are in use; **(2)** whether the effective converter list still supports existing media types; **(3)** whether custom converters restrict types/media types tightly enough; **(4)** whether both request/response and 406/415 are tested; **(5)** whether `@EnableWebMvc` was added unintentionally; **(6)** whether error responses, resource downloads, form/multipart, and other HTTP clients still work.

## Official Versioned Documentation

- [Spring Framework 6.2 — Message Converters in MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — `WebMvcConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 — MVC Enable Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/enable.html)
