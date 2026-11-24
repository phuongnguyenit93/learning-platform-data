# Adding Formatters, Converters, and Argument Resolvers in Spring Boot MVC

## 1. Objectives and Scope

Spring MVC performs a great deal of work before invoking a controller method: selecting the route, extracting path variables/query parameters/headers, converting HTTP strings into Java types, reading the request body, and producing the response body. Spring Boot's defaults cover common cases; when you have domain data types or specialized data-passing mechanisms, you can add a **Formatter**, **Converter**, and **HandlerMethodArgumentResolver**. Another kind of converter, **HttpMessageConverter**, handles the HTTP body content and must be clearly distinguished.

After this lesson, you will be able to:

- Explain the roles of `Formatter`, `Converter<S,T>`, `HttpMessageConverter<T>`, and `HandlerMethodArgumentResolver`.
- Choose the right extension point instead of manually parsing strings in every controller.
- Register custom formatters/converters and argument resolvers using `WebMvcConfigurer` while keeping Spring Boot's MVC auto-configuration.
- Add a message converter for a custom body format while preserving JSON, String, and default converters.
- Write a runnable Java 17+ example on Spring Boot 3.3.x, test with MockMvc, and distinguish binding errors, media type errors, and missing-data errors.
- Recognize risks related to locale, body limits, converter ordering, header security, and accidentally overriding framework defaults.

**Scope:** Spring MVC on the Servlet web stack, typically when using `spring-boot-starter-web`. Spring WebFlux has a different reactive pipeline and extension API; do not assume that MVC's `WebMvcConfigurer` or `HandlerMethodArgumentResolver` work directly in WebFlux.

## 2. What Steps Does a Request Go Through?

Given an example endpoint:

~~~http
GET /api/orders/sku-0123?period=11%2F2026 HTTP/1.1
Host: localhost:8080
X-Tenant-Id: store-a
Accept: application/json
~~~

General processing flow:

~~~text
HTTP client
   |
   v
Servlet container (e.g., Tomcat)
   |
   v
Servlet Filters
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping: find controller method
   |
   +--> HandlerAdapter: prepare arguments
   |       |
   |       +--> Converter: "sku-0123" -> ProductCode
   |       |
   |       +--> Formatter: "11/2026" -> BillingPeriod
   |       |
   |       +--> ArgumentResolver: X-Tenant-Id -> TenantContext
   |       |
   |       +--> HttpMessageConverter when @RequestBody is present
   |
   +--> Controller / Service
   |
   +--> HttpMessageConverter for @ResponseBody
   |
   v
HTTP response
~~~

**Three distinct tasks:**

1. Converting a single value from a source type to a target type: Converter.
2. Parsing and printing a data type according to a format or locale: Formatter.
3. Determining the value of an entire controller parameter from the request/context: HandlerMethodArgumentResolver.

For request/response bodies, use `HttpMessageConverter`; this differs from Spring Core's `Converter<String, T>`.

## 3. Quick Selection Table

| Need | Appropriate Tool | Example |
| --- | --- | --- |
| Convert path/query text into a value object | Converter<S,T> | "sku-0123" -> ProductCode("SKU-0123") |
| Parse and print formats that may depend on locale | Formatter<T> | "11/2026" <-> BillingPeriod |
| Build a controller parameter from headers or request context | HandlerMethodArgumentResolver | @Tenant TenantContext |
| Read/write the entire HTTP body by media type | HttpMessageConverter<T> | text/plain <-> PlainNote |
| Validate input object constraints | Jakarta Bean Validation / Validator | @Valid, @NotBlank |
| Customize JSON fields, property names, or date serialization | Jackson configuration / module | JSON from Java object |
| Pre-processing before controller | Servlet Filter / HandlerInterceptor | trace ID, cross-cutting logic |
| Read configuration file into a Bean | @ConfigurationProperties | application.yml -> AppSettings |

Multiple tools can appear together in the same request without replacing one another's mechanisms. For instance, `@RequestBody` receiving JSON is the job of a message converter, whereas `@RequestParam ProductCode` typically uses the conversion service. A header identifying a tenant can use `@RequestHeader String` in simple cases; a custom resolver is only useful when a shared object and rule are needed.

## 4. Converter<S,T>: Converting a Value to a Java Type

`Converter` resides in package `org.springframework.core.convert.converter`. The contract is simple:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

`Converter` transforms a source object into a target object; the `convert` method does not take a `Locale`. An application can use a converter to map IDs, enums, business codes, or normalized string formats.

For example, a `ProductCode` type always normalized to `SKU-xxxx`:

~~~java
record ProductCode(String value) {
}

final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-0000");
        }
        return new ProductCode(normalized);
    }
}
~~~

This snippet requires importing `Converter` and `Locale`; it will be placed in the runnable project in Section 9. Once the converter is registered in the MVC conversion service, a method can accept it directly:

~~~java
@GetMapping("/api/products/{code}")
public String find(@PathVariable ProductCode code) {
    return code.value();
}
~~~

With `GET /api/products/sku-0123`, Spring MVC can convert the path variable string into `ProductCode("SKU-0123")` before calling the controller. If the data is invalid, the conversion error is typically handled as HTTP 400 rather than invoking the controller with an invalid object.

**Do not overuse converters:** If only one endpoint needs simple string validation, `@Pattern` or a validator on a DTO may suffice. Only create a `Converter` when the domain type has clear semantics, is reused in multiple places, or when you want a centralized conversion boundary.

### 4.1. Converter and GenericConverter

`Converter<S,T>` describes a static source-target pair. When conversion depends on generic types, annotations, or needs to conditionally support multiple type pairs, Spring also provides `GenericConverter` and `ConditionalGenericConverter`. They are more flexible but more complex. For an ordinary ID/value object, `Converter<S,T>` is the easiest to read and test.

### 4.2. Does Every Conversion Run for JSON?

No. Converters registered in MVC's `ConversionService` primarily serve data binding such as query, path, form, and model properties. JSON requests/responses are usually handled by Jackson through `HttpMessageConverter`. A `Converter<String,ProductCode>` does not automatically control how Jackson deserializes `ProductCode` from JSON. To change JSON handling, configure Jackson or the appropriate message conversion mechanism.

## 5. Formatter<T>: Formatting-Context Parse and Print

`Formatter` resides in `org.springframework.format`. The contract is bidirectional:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Core methods:

- parse(String text, Locale locale): converts text into a Java object.
- print(T object, Locale locale): produces a text representation.
  
`Formatter` is suitable for dates, monetary amounts, percentages, and domain types with presentation conventions; `Locale` enables different representations by language/region. Not every formatter has to use `Locale`: if an API contract specifies a fixed format, it can intentionally ignore `Locale`, and that should be documented clearly.

Example `BillingPeriod` accepting `MM/yyyy` text, stored as `YearMonth`:

~~~java
record BillingPeriod(YearMonth value) {
}

final class BillingPeriodFormatter
        implements Formatter<BillingPeriod> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public BillingPeriod parse(String text, Locale locale)
            throws ParseException {
        try {
            return new BillingPeriod(YearMonth.parse(text, FORMAT));
        } catch (DateTimeParseException ex) {
            ParseException failure = new ParseException(
                    "Expected billing period MM/yyyy", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(BillingPeriod object, Locale locale) {
        return FORMAT.format(object.value());
    }
}
~~~

This example intentionally uses the fixed `MM/yyyy` format to keep the API contract consistent. If building forms localized to the user's language, you can choose `DateTimeFormatter`/`NumberFormat` by `Locale` and test all supported locales.

After registering the formatter, a method can accept:

~~~java
@GetMapping("/api/reports")
public String report(@RequestParam BillingPeriod period) {
    return period.value().toString();
}
~~~

Request `/api/reports?period=11%2F2026` converts to `BillingPeriod(YearMonth.of(2026, 11))`. The controller returns the string `2026-11`.

**Note on print:** `Formatter#print` is used by the conversion/formatting service when an object needs to be rendered as a string, such as form binding or formatting. Returning a record via `@ResponseBody` JSON does not mean Jackson will call `Formatter#print`; JSON serialization has its own mechanism.

### 5.1. When to Prefer Built-in Tools?

Before writing a new `Formatter`, try built-in capabilities:

- @DateTimeFormat on date/time parameters or fields.
- @NumberFormat for numbers.
- Default conversions for enums, primitives, UUIDs, and framework-supported types.
- @JsonFormat or Jackson config if the issue actually belongs to the JSON body.

For example, an endpoint that only needs `LocalDate`:

~~~java
@GetMapping("/api/by-date")
public String byDate(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

This is illustrative controller code; it requires importing `DateTimeFormat` and `LocalDate`. Do not write a global `Formatter<LocalDate>` just so one endpoint uses ISO dates, because a global formatter can alter how dates are parsed across many other endpoints.

## 6. HandlerMethodArgumentResolver: Building Controller Parameters

Spring MVC provides built-in resolvers for `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody`, `HttpServletRequest`, `Principal`, and many other types. When you want to add a specialized parameter type, you can implement `HandlerMethodArgumentResolver`.

Two main methods:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

`supportsParameter` decides which parameters the resolver is responsible for; `resolveArgument` actually extracts the data and constructs the object for the controller to use.

For example, a controller wants to receive:

~~~java
@GetMapping("/api/orders")
public String listOrders(@Tenant TenantContext tenant) {
    return tenant.id();
}
~~~

Here `@Tenant` is an application annotation. The resolver reads `X-Tenant-Id` from the header and constructs `TenantContext`. The controller does not have to repeat header-reading logic.

A good resolver should:

- Only match the exact annotation/parameter type it owns; do not match `String` or `Object` parameters too broadly.
- Handle missing, malformed, or unauthorized data explicitly.
- Not store per-request mutable state in singleton fields.
- Not arbitrarily read the entire request body when `@RequestBody` already handles it via a message converter.
- Have tests for present, missing, and invalid headers.

**Security warning:** `X-Tenant-Id` in this example is solely for learning how data is passed. A client-sent header does not prove tenant identity or access rights. In a real multi-tenant application, the resolver must rely on authenticated security principals/claims and verified authorization checks, never trusting an unauthenticated header to grant data access.

### 6.1. Why Not Use Converter for Every Parameter?

`Converter` transforms *a single value* `S -> T` that the framework has already extracted. A resolver can decide the source of the parameter: header, cookie, request attribute, session, principal, or multi-field context. It can also assemble a complex object from multiple sources.

If you want `@RequestHeader("X-Tenant-Id") TenantContext`, you can use `Converter<String,TenantContext>`. If you want custom syntax `@Tenant` and to pull data from the security context or other metadata, `HandlerMethodArgumentResolver` is a better fit.

## 7. HttpMessageConverter<T>: Reading and Writing HTTP Bodies

Two types of converters are easily confused:

- Spring Core Converter<S,T>: converts Java values via the conversion service.
- Spring Web HttpMessageConverter<T>: reads/writes *the entire HTTP message body* based on content type, accept header, and Java type.

When a controller uses `@RequestBody`, Spring MVC selects an `HttpMessageConverter` capable of reading the required Java type with the request's `Content-Type`. When a controller returns `@ResponseBody` or uses `@RestController`, the framework finds a converter capable of writing the return value in a media type matching `Accept` and `produces` configuration.

Common default converters include:

- StringHttpMessageConverter for String/plain text.
- MappingJackson2HttpMessageConverter (in Spring Framework 6.x with Jackson configured) for JSON.
- ByteArrayHttpMessageConverter for byte[].
- ResourceHttpMessageConverter for Resource/appropriate streaming.

**Content-Type** specifies the format in which the request body is sent; **Accept** states the response formats the client wants to receive. If the request body is unsupported, HTTP 415 may be returned; if no acceptable response format can be produced, HTTP 406 may be returned. Failure to bind/parse the body typically results in HTTP 400, depending on the exception and the application's exception handler.

Add a message converter for a custom format when a dedicated content contract exists. If you only need to rename JSON fields or adjust object serialization, use Jackson annotations/serializers/configuration before writing an HTTP converter yourself.

## 8. Integrating into Spring Boot with WebMvcConfigurer

Spring Boot MVC auto-configuration supplies default converters, formatters, and argument resolvers. The standard way to extend them is to create a `@Configuration` class implementing `WebMvcConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
class MvcCustomizationConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(new BillingPeriodFormatter());
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new TenantArgumentResolver());
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new PlainNoteMessageConverter());
    }
}
~~~

This is illustrative code; Section 9 contains the complete project and its imports.

Meaning:

- addFormatters: adds Converter and Formatter to MVC's FormattingConversionService.
- addArgumentResolvers: adds handler method argument resolvers for specialized types/annotations; built-in resolvers remain active.
- extendMessageConverters: extends the body converter list after the default list is prepared; list order can affect converter selection.

**Do not add @EnableWebMvc** to a Spring Boot application just to register converters or resolvers. `@EnableWebMvc` switches to more manual MVC control and prevents Boot's MVC auto-configuration from applying as usual. This easily causes loss of static resource configuration, formatters, converters, or other defaults the project relies on.

### 8.1. configureMessageConverters and extendMessageConverters

In plain Spring MVC configuration, adding converters via `configureMessageConverters` can alter default registration behavior. Spring Boot applies its own adjustments and also automatically collects `HttpMessageConverter` beans. When the goal is to *add* a converter while keeping existing ones, `extendMessageConverters` is straightforward.

Do not call `clear()` on the default list or replace all converters just to add `text/plain`. If you add a converter whose `supports()` or media type is too broad, it can steal work from Jackson/String converters and alter existing responses.

### 8.2. Can Standalone Beans Be Used?

Spring Boot supports contributing `Converter`, `GenericConverter`, `Formatter`, and `HttpMessageConverter` via appropriate beans. Whether using beans or `WebMvcConfigurer`, you must understand registration scope: the MVC conversion service serves web binding, whereas Boot's `ApplicationConversionService` for `application.properties` configuration has its own registration path. Adding a converter to one conversion service does not automatically guarantee that all other services use it.

## 9. Runnable Example: Converter, Formatter, Resolver, and MessageConverter

This example uses **Spring Boot 3.3.x, Java 17+**, Spring MVC, and default embedded Tomcat. It demonstrates all four extension points in a small project with no database dependency.

Endpoints:

- `GET /api/orders/{code}?period=MM/yyyy` with header `X-Tenant-Id`: receives `ProductCode`, `BillingPeriod`, and `TenantContext`.
- `POST /api/echo` with `text/plain` body: reads the body into `PlainNote` and writes `PlainNote` back as `text/plain`.

### 9.1. Directory Structure

~~~text
mvc-extensions-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          mvc/
            MvcExtensionsApplication.java
    test/
      java/
        example/
          mvc/
            MvcExtensionsApplicationTests.java
~~~

In this learning example, multiple package-private classes are placed in a single Java file to make the entire pipeline easy to follow. In a real project, each class with a distinct responsibility should be in its own file for maintainability.

### 9.2. File settings.gradle

~~~groovy
rootProject.name = 'mvc-extensions-demo'
~~~

### 9.3. File build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

A Gradle Wrapper compatible with Spring Boot 3.3.x and JDK 17 or newer is required. Plugin versions in the example are pinned for reproducibility; in a real module, follow the version set managed by your project's build.

### 9.4. File MvcExtensionsApplication.java

~~~java
package example.mvc;

import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcExtensionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcExtensionsApplication.class, args);
    }
}

record ProductCode(String value) {
}

record BillingPeriod(YearMonth value) {
}

record TenantContext(String id) {
}

record PlainNote(String text) {
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface Tenant {
}

final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-0000");
        }
        return new ProductCode(normalized);
    }
}

final class BillingPeriodFormatter implements Formatter<BillingPeriod> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public BillingPeriod parse(String text, Locale locale)
            throws ParseException {
        try {
            return new BillingPeriod(YearMonth.parse(text, FORMAT));
        } catch (DateTimeParseException ex) {
            ParseException failure = new ParseException(
                    "Expected billing period MM/yyyy", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(BillingPeriod object, Locale locale) {
        return FORMAT.format(object.value());
    }
}

final class TenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(Tenant.class)
                && parameter.getParameterType() == TenantContext.class;
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest request,
            WebDataBinderFactory binderFactory) {

        String value = request.getHeader("X-Tenant-Id");
        if (value == null
                || !value.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "X-Tenant-Id is missing or invalid");
        }
        return new TenantContext(value);
    }
}

final class PlainNoteMessageConverter
        extends AbstractHttpMessageConverter<PlainNote> {

    private static final int MAX_BYTES = 4096;

    PlainNoteMessageConverter() {
        super(new MediaType("text", "plain", StandardCharsets.UTF_8));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return PlainNote.class.isAssignableFrom(clazz);
    }

    @Override
    protected PlainNote readInternal(
            Class<? extends PlainNote> clazz,
            HttpInputMessage input) throws IOException {

        byte[] bytes = input.getBody().readNBytes(MAX_BYTES + 1);
        if (bytes.length > MAX_BYTES) {
            throw new HttpMessageNotReadableException(
                    "Plain text body exceeds 4096 bytes", input);
        }

        MediaType contentType = input.getHeaders().getContentType();
        Charset charset = contentType != null
                && contentType.getCharset() != null
                ? contentType.getCharset()
                : StandardCharsets.UTF_8;

        return new PlainNote(new String(bytes, charset));
    }

    @Override
    protected void writeInternal(
            PlainNote note, HttpOutputMessage output) throws IOException {
        output.getBody().write(
                note.text().getBytes(StandardCharsets.UTF_8));
    }
}

@Configuration(proxyBeanMethods = false)
class MvcCustomizationConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(new BillingPeriodFormatter());
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new TenantArgumentResolver());
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new PlainNoteMessageConverter());
    }
}

@RestController
class ExampleController {

    @GetMapping("/api/orders/{code}")
    public Map<String, String> order(
            @PathVariable("code") ProductCode code,
            @RequestParam("period") BillingPeriod period,
            @Tenant TenantContext tenant) {

        return Map.of(
                "productCode", code.value(),
                "period", period.value().toString(),
                "tenant", tenant.id());
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public PlainNote echo(@RequestBody PlainNote input) {
        return input;
    }
}
~~~

`main` is inside the single `public` class matching the file name `MvcExtensionsApplication.java`. The remaining classes/records/annotation are package-private so they can reside in the same Java file in this example.

**Four integration points at runtime:**

1. When parsing `{code}`, `ProductCodeConverter.convert` normalizes the string to `ProductCode`.
2. When parsing `period`, `BillingPeriodFormatter.parse` creates `BillingPeriod`.
3. For a parameter annotated with `@Tenant`, `TenantArgumentResolver` extracts `X-Tenant-Id` and creates `TenantContext`.
4. For `/api/echo`, `PlainNoteMessageConverter.readInternal` reads the `text/plain` body into `PlainNote`; `writeInternal` serializes `PlainNote` into a `text/plain` response.

At `/api/orders`, the controller returns a `Map`, so JSON is still handled by the default converter. Because `extendMessageConverters` only adds a converter supporting `PlainNote`, existing JSON APIs can still use Jackson.

### 9.5. Running the Application

On Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

From another terminal, call the endpoint:

~~~bash
curl -i "http://localhost:8080/api/orders/sku-0123?period=11%2F2026" -H "X-Tenant-Id: store-a"
~~~

If the server starts successfully on the default port and no other configuration overrides it, the expected status is HTTP 200 and the JSON response body contains three values:

~~~json
{"productCode":"SKU-0123","period":"2026-11","tenant":"store-a"}
~~~

JSON key ordering is not guaranteed. What matters is that `productCode` is normalized to `SKU-0123`, `period` becomes `2026-11`, and `tenant` comes from the header.

Send `text/plain`:

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: text/plain; charset=UTF-8" -H "Accept: text/plain" --data-binary "Hello"
~~~

Expected status: HTTP 200. Response body:

~~~text
Hello
~~~

In this endpoint, incoming data is capped at 4096 bytes in the custom converter. This is a simple limit for demonstration; production requires request body size limits at the appropriate layers and thorough charset/validation handling.

### 9.6. Testing Valid Error Cases

- Omit `X-Tenant-Id`: the resolver returns HTTP 400 because the required header is missing.
- Send `X-Tenant-Id` with characters outside the allowed pattern: HTTP 400.
- Call `/api/orders/abc?period=11%2F2026` with a valid header: `ProductCodeConverter` cannot construct `ProductCode`, so Spring MVC typically returns HTTP 400.
- Call `period=13%2F2026`: the formatter rejects month 13, typically returning HTTP 400.
- `POST /api/echo` with `Content-Type: application/json` when the mapping requires `text/plain`: HTTP 415.
- Send `Accept: application/json` to `/api/echo`, which declares `produces=text/plain`: HTTP 406 if no negotiable response format exists.
- Send more than 4096 bytes of `text/plain`: the custom message converter refuses to read the body, which Spring MVC handles as HTTP 400 by default.

Exact status codes can be altered by a global exception handler or security filter chain in a real project. When troubleshooting errors, inspect status, content type, exceptions, and relevant logs; do not guess from the controller alone.

## 10. Testing with MockMvc

This section tests the four customizations without opening a real TCP port. `MockMvc` passes through Spring MVC's request mapping, argument resolution, and message conversion layers according to the test context configuration.

File `src/test/java/example/mvc/MvcExtensionsApplicationTests.java`:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcExtensionsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void converterFormatterAndResolverWorkTogether() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "11/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.productCode").value("SKU-0123"))
                .andExpect(jsonPath("$.period").value("2026-11"))
                .andExpect(jsonPath("$.tenant").value("store-a"));
    }

    @Test
    void plainNoteMessageConverterReadsAndWrites() throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("Hello"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(content().string("Hello"));
    }

    @Test
    void invalidProductCodeReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/invalid")
                        .param("period", "11/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPeriodReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "13/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingTenantHeaderReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "11/2026"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongContentTypeReturnsUnsupportedMediaType()
            throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"abc\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Run tests:

~~~bash
./gradlew test
~~~

The tests verify status codes, JSON fields, text bodies, and errors rather than merely checking that the context loads. For real converter/resolver changes, add tests for existing endpoints to make sure the new configuration does not break existing binding, JSON, or API contracts.

### 10.1. How Do @WebMvcTest and @SpringBootTest Differ?

- `@WebMvcTest` is suitable when you only want an MVC slice and faster execution for controller/web configuration. However, custom configs/converters/resolvers and dependencies must be included completely in the slice test; otherwise tests may fail due to missing beans or report inaccurate behavior.
- `@SpringBootTest` + `@AutoConfigureMockMvc` (as in the example) creates a broader application context without opening a real port, making it suitable for verifying how customizations work together.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real embedded server to test the HTTP connector, filter chain, and network integration; suitable for final integration tests.

Do not rely solely on unit tests that call `ExampleController.order(...)` directly to conclude that formatters or argument resolvers work, because direct method calls bypass the MVC binding pipeline.

## 11. Understanding How Spring MVC Selects an Extension

### 11.1. When Is Converter/Formatter Invoked?

Built-in resolvers, such as those handling `@PathVariable` or `@RequestParam`, first extract the raw value from the request and then need to convert it to the target type. `WebDataBinder` and `ConversionService`/`FormattingConversionService` can perform this step. A `Converter` or `Formatter` is chosen when a matching registered source-target pair exists.

That means a `@RequestParam ProductCode` is still picked up by the built-in request-parameter resolver, while the underlying `String` value is converted by `ProductCodeConverter`. You do not need to write a `HandlerMethodArgumentResolver` just to parse a path variable into a simple value object.

If multiple converters/formatters share the same type pair, registration order and method can lead to unpredictable behavior. Avoid registering multiple conflicting strategies for the same type globally; use annotations or local binders when formatting must vary per endpoint.

### 11.2. When Is HandlerMethodArgumentResolver Invoked?

`RequestMappingHandlerAdapter` maintains a list of resolvers. The framework finds the first resolver whose `supportsParameter(...)` returns `true` for a controller parameter and then calls `resolveArgument(...)`.

Custom resolvers added via `WebMvcConfigurer.addArgumentResolvers` are used alongside built-in resolvers. Built-ins for standard annotations such as `@RequestParam`/`@PathVariable` still take priority according to the framework's ordering; custom resolvers fit best when using custom annotations and application-specific types. Do not try to override `@RequestBody` or `@RequestParam` handling with a generic custom resolver.

If you truly must alter built-in argument resolution, you need a deep understanding of `RequestMappingHandlerAdapter` and its configuration. That is a wide-ranging change and all affected APIs must be tested.

### 11.3. When Is HttpMessageConverter Invoked?

`RequestResponseBodyMethodProcessor` and related MVC components use `HttpMessageConverters` to read `@RequestBody` and write `@ResponseBody`. They consider Java type, `Content-Type`, `Accept`, `consumes`/`produces`, and registered converter order.

A converter claiming to support `Object.class` and all media types can preempt Jackson, leading to broken output. `PlainNoteMessageConverter` in the example only supports `PlainNote` and `text/plain`; therefore its blast radius stays controlled.

## 12. Formatters, Locale, and Data Consistency

The symmetry between `parse` and `print` matters when building input forms:

- Parse: `"11/2026"` -> `BillingPeriod(YearMonth.of(2026,11))`.
- Print: `BillingPeriod(...)` -> `"11/2026"`.

Both directions must be compatible so data does not change meaning after being displayed and resubmitted. If a formatter depends on locale, test both directions under every locale the application supports.

For instance, the decimal string `"1,234"` can mean different things across locales. Do not use the server machine's default `NumberFormat` for a public API if the API contract requires a fixed format. If the API expects ISO dates or dot-separated decimals, specify the contract explicitly and validate inputs rather than leaving it to an arbitrary locale.

A global custom `Formatter<LocalDate>` can affect numerous endpoints and forms. When only a single field has a special format, consider `@DateTimeFormat` or a controller-level `@InitBinder` instead of a global override.

## 13. Validation and Exception Handling

A `Converter`/`Formatter` is responsible for producing a value of the right type and format. Validation can add business constraints after the data is bound.

Different mechanisms:

- Failing to parse path/query into target type: conversion/binding error, typically returns 400.
- `@Valid` DTO failing constraints: Spring MVC typically translates validation errors into 400.
- Message converter failing to read body: `HttpMessageNotReadableException`, typically returns 400.
- Unsupported media type: 415 or 406 depending on request/response direction.
- Argument resolver missing required context: decide the error response explicitly, such as `ResponseStatusException(400)` in the sample.
- Unauthorized access: 401/403 must be handled by appropriate security mechanisms, not substituted with a 400 parse error.

Production applications can use `@RestControllerAdvice` to map errors to a consistent structure such as `ProblemDetail`. Avoid returning raw exception messages containing system details, SQL, or sensitive data to clients. At the same time, log enough request ID and root-cause information for investigation.

Do not wrap every converter error into a `RuntimeException` returning HTTP 500; invalid input errors should be classified properly. Conversely, do not hide serious programming bugs under a 400 status just to look "safe".

## 14. Scope of Application: Global, Per-Controller, and Per-Field

There are multiple configuration levels:

| Scope | Example Mechanism | When to Choose |
| --- | --- | --- |
| Entire MVC application | WebMvcConfigurer.addFormatters | Value objects used consistently across many controllers |
| Specific field/parameter | @DateTimeFormat, @NumberFormat | Built-in Spring conventions suffice |
| Single controller/binder | @InitBinder | Custom parser/editor for a specific form/controller group |
| By HTTP body type | HttpMessageConverter | Custom media type or representation |
| By parameter type/annotation | HandlerMethodArgumentResolver | Specialized request context injected into controllers |
| Entire JSON schema | Jackson configuration | Intentional changes to JSON serialization/deserialization |

Do not register something globally just to solve a small local case. The wider the boundary, the greater the risk of affecting unrelated endpoints.

For REST APIs, prefer well-specified input formats, clear JSON DTOs, and built-in annotations. Custom extensions should address genuinely recurring needs and must have tests locking down behavior.

## 15. Impact of @EnableWebMvc and Default Configuration

Spring Boot normally auto-configures MVC when an appropriate `spring-boot-starter-web` is on the classpath. Those defaults may include `HttpMessageConverters`, the conversion service, static resource mappings, view resolvers, and path matching configuration.

If you only want to add formatters/converters/resolvers, use `@Configuration implements WebMvcConfigurer` and **do not add @EnableWebMvc**. In Boot, using `@EnableWebMvc` alters the auto-configuration mechanism; the application can lose defaults it depends on.

Signs of over-customization:

- Endpoints that previously returned JSON now return 406.
- `@RequestBody` that used to read JSON now returns 415.
- Static resources return 404 after MVC configuration changes.
- A controller receives requests, yet default parameter binding stops working.
- A global formatter alters date or number formatting across many APIs.

Check configuration diffs, newly added `WebMvcConfigurer` classes, the converter list, and the behavior of existing endpoints. Fix the exact extension point; avoid disabling all MVC defaults to solve a narrow requirement.

## 16. Controlling Converter Ordering and Breadth

A few operational principles:

1. `supports(Class<?>)` should only return `true` for types genuinely belonging to the custom format.
2. Media types must be specific; avoid claiming support for all requests/responses unless needed.
3. Registration order matters when multiple converters support the same Java type and media type.
4. When adding a new one, use `extendMessageConverters` to preserve defaults; verify with JSON and text tests.
5. When genuinely overriding defaults, document the goal, endpoint impact, and rollback plan.
6. Do not read unbounded request bodies with `readAllBytes()` in a public converter without proper size limits.
7. Parse data with an explicit charset and handle malformed input per contract.
8. If streaming large files is required, examine `Resource`/`StreamingResponseBody` or an appropriate streaming solution instead of buffering the whole body in RAM.

In the example, `PlainNoteMessageConverter` is inserted at index 0, yet `supports()` only accepts `PlainNote` and its media type is `text/plain`. This choice keeps its impact small; for a converter capable of handling multiple types, placing it at the front of the list must be carefully evaluated.

## 17. Security and Multi-Tenancy Considerations

Headers, cookies, or principals can all serve as data sources for `HandlerMethodArgumentResolver`, but authentication/authorization responsibilities must remain clear.

In a real system:

- An authentication filter or security chain must verify the user/token before the application trusts any identity.
- `TenantContext` should be built from authenticated principals/claims and cross-checked against data access permissions.
- Do not let an arbitrary header determine the database tenant if the client has not been authenticated.
- Avoid storing the tenant in static mutable fields because requests execute concurrently.
- When using `ThreadLocal` or context propagation, understand lifecycle, cleanup, async dispatch, and executors; do not leak request data to another thread uncontrolled.
- If a resolver queries a database or remote service, understand the latency, timeout, and failure mode impact on every request.

A custom resolver reduces code duplication, yet also becomes shared infrastructure; a bug in it can affect every endpoint using that annotation. Write unit and integration tests covering multiple authorization scenarios.

## 18. Common Issues and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| @PathVariable ProductCode returns 400 | Converter not registered or invalid format | Check addFormatters, source type, regex, and URL |
| @RequestParam BillingPeriod returns 400 | Formatter parse failed or input is not MM/yyyy | Check format, encoding, and exception |
| @Tenant annotation has no effect | supportsParameter does not match annotation/type or resolver not registered | Check @Retention(RUNTIME), addArgumentResolvers, signature |
| Resolver handles the wrong parameter | supportsParameter is too broad | Match only explicit annotation/type |
| @RequestBody text/plain returns 415 | Missing custom message converter or wrong consumes/media type | Check Content-Type, supports, converter list |
| Returning PlainNote gives 406 | No converter writes the type for Accept/produces | Check converter write support and media type |
| Existing JSON breaks after adding custom converter | Converter supports Object or overly broad media type | Narrow supports/media type, check ordering |
| Static resources/default formatting lost | @EnableWebMvc enabled or over-broad config override | Keep WebMvcConfigurer extension instead of replacing Boot MVC |
| Unit test passes but HTTP fails | Test calls controller directly, bypassing MVC pipeline | Use MockMvc/integration tests |
| Date format differs across environments | Uncontrolled Locale or global formatter | Pin API contract, use @DateTimeFormat, or test locales |
| Large POST body spikes memory | Converter reads full body unbounded | Enforce body limits and control streaming |
| Tenant gets spoofed | Unauthenticated header treated as identity | Use verified principal/claims and authorization |
| Changing JSON has no effect | Modified Converter<String,T> while Jackson handles JSON | Use Jackson config/serializer/deserializer |
| Spring WebFlux present and MVC config does not run | Application uses the reactive web stack | Use WebFlux APIs/configuration |

## 19. Extended Practice Exercises

After running the sample project, try these exercises:

**Exercise 1 — Converter:** Change the `ProductCode` rule to `SKU-xxxxxx` and add tests for valid codes, codes containing letters, codes with missing digits, and codes with whitespace. Explain whether normalization belongs in the converter or the domain constructor.

**Exercise 2 — Formatter:** Switch `BillingPeriod` to `yyyy-MM` format; update the formatter and test `parse` and `print` in both directions. If the product supports multiple languages, add appropriate `Locale` handling and prove round-trip consistency.

**Exercise 3 — Resolver:** Add `@CurrentRequestId RequestId` reading from a request attribute set by a trusted filter, with a safe fallback. Test requests missing the attribute and multiple concurrent/sequential requests to prove there is no shared mutable state.

**Exercise 4 — Body converter:** Test valid `PlainNote` `text/plain` requests and oversized bodies; verify response status, charset, and body. Ensure `GET` JSON endpoints still pass with the custom converter registered.

**Exercise 5 — Errors:** Add `@RestControllerAdvice` to produce consistent error responses; preserve accurate 400/406/415 status codes without leaking stack traces.

**Exercise 6 — Boundaries:** Try writing a JSON converter instead of `text/plain` and compare it with a Jackson serializer. Choose the lower-impact approach and explain why.

Completion evidence should include source code, curl or MockMvc output, error logs for invalid inputs, and confirmation that existing endpoints still work as before.

## 20. Self-Check Questions

1. How does `Converter<S,T>` differ from `HttpMessageConverter<T>`?
2. Why does `Formatter<T>` have both `parse` and `print`, whereas `Converter<S,T>` only has `convert`?
3. When is `@DateTimeFormat` better than a global `Formatter<LocalDate>`?
4. Why does `@PathVariable ProductCode` typically only need a `Converter` instead of a custom argument resolver?
5. What scope should `supportsParameter(...)` of a `HandlerMethodArgumentResolver` match?
6. Why should a client-sent header not be used as proof of an authenticated tenant?
7. What mechanism does MVC use to process `@RequestBody` and `@ResponseBody`?
8. How do `Content-Type` and `Accept` influence message converter selection?
9. Why should you use `extendMessageConverters` when only adding a converter?
10. What effects can adding `@EnableWebMvc` have in Boot?
11. Does registering a `Formatter` for MVC automatically change Jackson's JSON formatting?
12. What does a `MockMvc` test prove, and does it open a real TCP port?
13. When encountering 400, 406, or 415 errors, which processing layers should be checked first?
14. If a custom converter breaks existing JSON APIs, how should you inspect `supports`, media types, and ordering?
15. What should be tested before promoting a shared argument resolver to production?

## Official Documentation

- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot – Spring MVC Customization](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework – Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework – MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [WebMvcConfigurer API (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)

The examples focus on MVC on Spring Boot 3.3.x. When upgrading the framework version, review the corresponding APIs and default behaviors before copying configuration to a production application.
