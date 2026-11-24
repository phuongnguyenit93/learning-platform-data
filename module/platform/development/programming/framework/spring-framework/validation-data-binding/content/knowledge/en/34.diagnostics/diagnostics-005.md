# Formatter Not Applied Because Data Flows Through JSON Converter

## 1. Symptom: Formatter Works for Forms/Queries Yet Fails for JSON

You declare a `Formatter<LocalDate>`, register it via `WebMvcConfigurer#addFormatters`, and test it successfully with a request parameter:

```http
GET /api/events/query?title=Conference&eventDate=06.11.2026
Accept: application/json
```

Yet when sending the same value in JSON:

```http
POST /api/events/json
Content-Type: application/json

{"title":"Conference","eventDate":"06.11.2026"}
```

the server returns **400 Bad Request**. You put a breakpoint inside `Formatter#parse`, and the breakpoint **is never hit**. Did Spring lose the Formatter, or did the bean fail to register?

**Usually neither.** The two requests flow through **two different data conversion mechanisms**:

1. `@RequestParam`, `@PathVariable`, and `@ModelAttribute` receive string/field binding values → Spring MVC `ConversionService`, `Formatter`, `Converter`, `WebDataBinder`.
2. `@RequestBody` with JSON content → Spring MVC selects a matching `HttpMessageConverter` (typically `MappingJackson2HttpMessageConverter` in Spring Boot 3.3) → Jackson `ObjectMapper`/deserializers construct the Java object. A `Formatter<T>` registered on MVC `FormatterRegistry` **does not automatically become a Jackson deserializer**.

Example:

```text
                        HTTP request
                             |
                       DispatcherServlet
                             |
                    HandlerMethod argument
                         /         \
                        /           \
        @RequestParam / @ModelAttribute    @RequestBody EventInput
                   |                              |
      WebDataBinder + ConversionService          HttpMessageConverter
                   |                              |
      Formatter<LocalDate>.parse()               Jackson ObjectMapper
                   |                              |
             EventInput                     EventInput
                   \                              /
                    \                            /
                          @Valid (if present)
                                |
                         Controller method
                                |
                       @ResponseBody JSON
                                |
                     HttpMessageConverter
                     (Jackson serialization)
```

Therefore, **a valid formatter configuration does not guarantee JSON uses that formatter**. Fix the issue by identifying **the exact request path** before modifying code.

**Scope:** Spring Framework 6.1.x, Spring Boot 3.3.6, Servlet Spring MVC, Java 17+, Jackson, and Jakarta Validation. Newer versions may rename or change the JSON converter choice; the principle of separating Spring field formatting from JSON object mapping should still be verified against your actual system.

## 2. Which Layer Does Each Component Belong To?

| Component | Role | Common application |
| --- | --- | --- |
| `org.springframework.core.convert.ConversionService` | API for converting between types | `@RequestParam`, `@PathVariable`, `@ModelAttribute`, Spring binding |
| `org.springframework.core.convert.converter.Converter<S,T>` | Converts one type to another, typically locale-independent | Converting strings into value objects in Spring conversion |
| `org.springframework.format.Formatter<T>` | `parse(String,Locale)` and `print(T,Locale)` | UI field values, forms/queries, locale-aware representations |
| `FormattingConversionService` | Combines converters, formatters, and annotation-based formatters | Binding strings into method parameters/model attributes |
| `@DateTimeFormat` | Selects date/time format for Spring conversion | Method parameter or field/model attribute |
| `@NumberFormat` | Configures number formatting for Spring formatting | Field/model attribute, compatible request arguments |
| `WebDataBinder` | Binds request values onto a model object, manages binding errors and validation | `@ModelAttribute`; also used for validation after `@RequestBody` |
| `HttpMessageConverter` | Reads/writes **HTTP body** by media type and target type | `@RequestBody`, `@ResponseBody` |
| `MappingJackson2HttpMessageConverter` | JSON body ↔ Java object via Jackson | JSON requests/responses in Spring MVC 6.1 |
| `ObjectMapper` and Jackson deserializers | Decodes JSON tokens, creator properties, date/time formats | Jackson JSON pathway |
| `@JsonFormat` | Jackson format metadata for property/type | JSON serialization/deserialization |
| `@Valid` / `@Validated` | Runs Bean Validation after data is constructed/bound | Usable on both forms and JSON |

**Two easy misconceptions:**

- `@RequestBody` may get a `WebDataBinder` created by Spring to **run validation after Jackson constructs the object**, but that does **not** mean Jackson uses `WebDataBinder` to parse individual JSON fields.
- `Content-Type: application/json` governs media-type selection. Changing the header alone does not turn `@ModelAttribute` into `@RequestBody`. The **handler argument annotation**, target type, and converter configuration determine the processing path.

### 2.1. What Is a Spring Formatter?

Interface:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    String print(T object, Locale locale);
    T parse(String text, Locale locale) throws ParseException;
}
```

This is an **explanatory signature**, not code to drop into a project as a standalone file. In Spring, `Formatter<T>` targets **string field** representations on clients/UI; `Locale` is part of the API. It can be registered via:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DottedLocalDateFormatter());
}
```

This customizes Spring MVC's `FormattingConversionService`. It does **not** invoke:

```java
objectMapper.registerModule(...);
```

nor does it automatically register a Jackson `JsonDeserializer<LocalDate>`. That is an intentional architectural boundary.

### 2.2. How Does Jackson Read JSON?

When a controller defines:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public EventView create(@RequestBody EventInput input) {
    ...
}
```

Spring MVC picks a converter capable of reading `EventInput` from JSON. With standard Spring Boot 3.3 configuration, Jackson reads the JSON object, maps properties to the record's canonical constructor or bean properties per Jackson metadata, and invokes the deserializer for `LocalDate`.

`LocalDate` is normally read by the Jackson Java Time module in ISO format `yyyy-MM-dd` unless another format is configured. The string `"06.11.2026"` accepted by the custom Spring Formatter **is not** an ISO local date under Jackson's default, so the JSON payload is rejected.

**Not every `@RequestBody` uses Jackson.** If the argument is `String` or `byte[]`, a different `HttpMessageConverter` may be chosen. If Gson/JSON-B is configured or converters are customized, the fix must match accordingly. Always inspect the actual converter rather than assuming Jackson solely from `Content-Type`.

## 3. Systematic Diagnosis

### 3.1. Start from the Handler Signature

Check which annotation the endpoint uses:

```java
// Spring string/field conversion:
@GetMapping("/query")
public Object query(@RequestParam LocalDate eventDate) { ... }

// Spring model attribute binding:
@PostMapping("/form")
public Object form(@ModelAttribute EventInput input) { ... }

// HTTP body conversion (typically Jackson):
@PostMapping("/json")
public Object json(@RequestBody EventInput input) { ... }
```

These examples are method snippets, not complete classes.

This is the single most effective step. If `@RequestBody` is present, look at `ObjectMapper`/`HttpMessageConverter` first rather than adding another `Formatter` hoping JSON behavior will change.

### 3.2. Inspect Content-Type and Target Type

Examples:

- `application/x-www-form-urlencoded` + `@ModelAttribute`: form fields are supplied by Servlet request parameter APIs, then the Spring binder converts Strings to target types.
- `application/json` + `@RequestBody EventInput`: Jackson JSON path.
- `application/json` + `@RequestBody String`: can be read by `StringHttpMessageConverter`, not necessarily Jackson object parsing.
- `multipart/form-data`: handling depends on `@RequestPart`, `MultipartFile`, form fields, or JSON parts; a JSON part read by a message converter does not go through Formatter.
- `@RequestParam` does not unpack JSON object properties from the body; if a client sends JSON while the controller expects query/form params, values will generally not appear as expected.

### 3.3. Set Breakpoints in the Right Places

In Spring MVC 6.1:

- `org.springframework.web.method.annotation.AbstractNamedValueMethodArgumentResolver` and argument resolvers: `@RequestParam`, `@PathVariable`...
- `org.springframework.web.method.annotation.ModelAttributeMethodProcessor` or its Servlet subclass: `@ModelAttribute`, binder.
- `org.springframework.web.servlet.mvc.method.annotation.RequestResponseBodyMethodProcessor`: `@RequestBody`.
- `org.springframework.web.servlet.mvc.method.annotation.AbstractMessageConverterMethodArgumentResolver#readWithMessageConverters`: selects and invokes the body converter.
- `org.springframework.http.converter.json.MappingJackson2HttpMessageConverter`: reads JSON via Jackson.
- Your custom `org.springframework.format.Formatter#parse`: Spring formatting parse path.
- Jackson `LocalDateDeserializer` or custom deserializer: JSON parse path.

If the breakpoint in `Formatter#parse` hits on form/query calls yet **does not** hit on JSON calls while the Jackson breakpoint hits, that is clear diagnostic proof of **two separate pipelines**.

### 3.4. Classify the Exception Instead of Just Looking at HTTP 400

| Scenario | Typical exception / error location |
| --- | --- |
| `@RequestParam LocalDate` malformed | `MethodArgumentTypeMismatchException` or mismatch resolution |
| `@ModelAttribute` field fails conversion | `BindingResult`/`FieldError` with `typeMismatch`; if no result, may throw `MethodArgumentNotValidException` |
| `@RequestBody` JSON cannot parse into `LocalDate` | `HttpMessageNotReadableException`, nested Jackson mapping/format error |
| JSON deserializes yet `@NotNull`/`@NotBlank` fails | `MethodArgumentNotValidException` when `@Valid` runs |
| Media type unsupported by endpoint | HTTP 415, typically `HttpMediaTypeNotSupportedException` |
| JSON body completely missing with `@RequestBody(required=true)` | Unreadable/missing body, typically 400 |

**Warning:** do not label every error a "Bean Validation error." If Jackson has not constructed an object from JSON yet, `@Valid` has no object to inspect; if JSON succeeds with a null date, `@NotNull` may catch it in the next step.

### 3.5. Targeted Diagnostic Logging

In dev/test environments, you can raise log levels for handler/converter packages:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation=DEBUG
logging.level.org.springframework.http.converter=DEBUG
logging.level.org.springframework.web.method.annotation=DEBUG
```

Exact log output depends on version, code path, and log level. **Do not** rely on specific log text as a stable contract; combine it with MockMvc/debugger. Never enable verbose body/header logging in production if payloads contain personal data, authorization headers, or secrets.

## 4. `@DateTimeFormat` Differs from `@JsonFormat`

### 4.1. `@DateTimeFormat` in Spring Field Binding

```java
public record SearchInput(
        @DateTimeFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

On an eligible `@ModelAttribute`/`@RequestParam`, Spring's annotation formatter applies the declared format to string values. In the example, `06.11.2026` represents November 6, 2026. `@DateTimeFormat` does not guarantee Jackson JSON reads that format.

You can write:

```java
@GetMapping("/search")
public EventView search(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate eventDate) {
    // ...
}
```

to accept ISO format `2026-11-06` for that argument. Spring MVC supports annotation-driven formatting per field/method parameter; this rule can override a type-registered formatter.

### 4.2. `@JsonFormat` for Jackson Properties

```java
public record JsonInput(
        @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

Jackson can apply that pattern when reading/writing the `eventDate` JSON property if the Java Time module and annotation introspection are active. `@JsonFormat` is a **Jackson** annotation and does not configure Spring's `FormattingConversionService`.

A class/record can hold **both** `@DateTimeFormat` and `@JsonFormat` on the same property when two distinct representations must be supported. Be clear on how they work:

- The form/query path inspects `@DateTimeFormat`.
- The JSON path inspects `@JsonFormat`.
- When an endpoint returns `@ResponseBody` JSON, the Jackson writer determines the output format.
- Only with explicit custom integration do the two mechanisms share a single set of formatting rules.

The hands-on project below uses **one global Spring Formatter** for forms/queries and a **JSON record with `@JsonFormat`** for side-by-side comparison.

### 4.3. `spring.mvc.format.date` and `spring.jackson.*`

`spring.mvc.format.date` or `WebMvcConfigurer#addFormatters` controls Spring MVC conversion/field formatting. They are not the default configuration for Jackson `ObjectMapper`.

Conversely, Spring Boot supports Jackson ObjectMapper customization. For Java Time types, pay attention to the Jackson Java Time module and per-type/per-property serializers/deserializers; global `spring.jackson.date-format` should not be assumed to apply to **every `java.time.LocalDate`** without testing, because Java Time deserializers follow their own rules.

A pragmatic principle: if a JSON API publishes dates in ISO 8601, keep JSON in ISO; if the UI needs `dd.MM.uuuu`, use a formatter on forms/queries. Do not force JSON into a locale-specific display format merely because a UI Formatter was registered.

## 5. Choosing the Right Fix for Your Goal

### 5.1. Keep JSON ISO, Use Formatter Only for Forms/Queries

**Recommended API design:** JSON uses `"2026-11-06"`, while forms accept `"06.11.2026"` if UX requires it. Spring Formatter and Jackson each handle their own path. This is the demo's default approach.

Benefits:

- Consistent JSON schema across multi-language clients.
- Minimal dependence on server locale.
- Frontend can change date presentation without altering the API contract.
- Mobile/web clients use the standard ISO representation.

### 5.2. Use a Custom Pattern in JSON with `@JsonFormat`

When the business contract genuinely requires dotted strings in JSON:

```java
public record JsonDottedInput(
        @NotBlank String title,
        @JsonFormat(pattern = "dd.MM.uuuu")
        @NotNull LocalDate eventDate
) {}
```

This configures **Jackson per property**. It does not make the Spring Formatter run; it configures **a dedicated Jackson date format**.

Avoid changing every JSON date across the entire application just to accommodate one form if the API already publishes ISO format to existing clients.

### 5.3. Complex JSON Formats: Custom `JsonDeserializer`

For formats such as locale-dependent `dd MMM uuuu`, conditional parsing, or complex value objects, you can write a Jackson `JsonDeserializer<T>` and register it via `@JsonDeserialize(using=...)`, a Jackson Module, or Spring Boot `@JsonComponent`.

Points to watch:

- Parsing must be strict and not silently normalize nonexistent dates.
- Return clear errors on pattern mismatch without leaking internal parsing details.
- Never use the OS locale as an implicit contract for multi-region APIs.
- Do not "reuse" a Spring Formatter via an ad-hoc adapter that compromises thread safety or format consistency.
- Test **both** serialization and deserialization, including null, invalid strings, and timezone/offset when types include time.

### 5.4. Parsing a JSON String into `LocalDate` in the Service?

Another option is accepting `String` in the DTO:

```java
public record RawDateRequest(
        String eventDate
) {}
```

and calling an application-owned parser in the service. This can make sense when returning rich business-specific errors independent of Jackson. However, it has drawbacks: mixing validation with manual parsing, more untested edge cases, altered Swagger/OpenAPI schemas, and extra conversion code. Prefer Jackson configuration when a standard JSON format suffices.

## 6. Runnable Project: Comparing Spring Formatter and Jackson

Java 17, Spring Boot 3.3.6, Spring MVC, and Jakarta Validation application. It exposes five endpoints:

| Endpoint | Input source | Accepted date format in demo |
| --- | --- | --- |
| `POST /api/events/form` | `@ModelAttribute EventInput` | `06.11.2026` via custom Formatter |
| `GET /api/events/query` | `@RequestParam LocalDate` | `06.11.2026` via custom Formatter |
| `GET /api/events/query-iso` | `@RequestParam @DateTimeFormat(iso=ISO.DATE)` | `2026-11-06` via annotation |
| `POST /api/events/json` | `@RequestBody EventInput` | `2026-11-06` via Jackson default |
| `POST /api/events/json-dotted` | `@RequestBody JsonDottedInput` | `06.11.2026` via Jackson `@JsonFormat` |

### 6.1. Project Structure

```text
formatter-json-diagnosis/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/formatdiag/
        FormatDiagnosisApplication.java
        DottedLocalDateFormatter.java
        WebFormattingConfiguration.java
        EventInput.java
        JsonDottedInput.java
        EventView.java
        FieldIssue.java
        ApiError.java
        ErrorPayloadMapper.java
        EventController.java
        EventExceptionAdvice.java
      resources/
        application.properties
    test/
      java/com/example/formatdiag/
        FormatterVsJsonTest.java
```

### 6.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'formatter-json-diagnosis'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` in Boot 3.3 provides MVC and Jackson with Java Time support via the JSON starter. `spring-boot-starter-validation` provides the Jakarta Validation provider. No manual Jackson module dependency is needed here because Boot's standard auto-configuration already includes the Java Time module from those dependencies.

### 6.3. Main Application

`src/main/java/com/example/formatdiag/FormatDiagnosisApplication.java`:

```java
package com.example.formatdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormatDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatDiagnosisApplication.class, args);
    }
}
```

### 6.4. `application.properties`

`src/main/resources/application.properties`:

```properties
spring.application.name=formatter-json-diagnosis
spring.jackson.serialization.write-dates-as-timestamps=false
```

The Jackson property above makes clear the intent to serialize Java Time values as ISO strings in the demo. It **does not make Jackson parse dotted format**; dotted input still requires `@JsonFormat` or a custom deserializer.

Do not add `@EnableWebMvc` solely to register a Formatter, as that annotation can alter how Boot auto-configures MVC. `WebMvcConfigurer` is sufficient for customization in standard setups.

### 6.5. Custom `Formatter<LocalDate>`

`src/main/java/com/example/formatdiag/DottedLocalDateFormatter.java`:

```java
package com.example.formatdiag;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

@Component
public class DottedLocalDateFormatter implements Formatter<LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd.MM.uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, FORMAT);
    }

    @Override
    public String print(LocalDate date, Locale locale) {
        return date.format(FORMAT);
    }
}
```

Explanation:

- `Formatter<LocalDate>` provides a parser/printer for Spring MVC string field conversion.
- Pattern `dd.MM.uuuu` accepts `06.11.2026`.
- `ResolverStyle.STRICT` rejects nonexistent dates such as `31.02.2026`.
- `DateTimeFormatter` is immutable and thread-safe; a `static final` field is safe inside a singleton Spring bean.
- The `Locale` parameter is unused because the example chooses a **fixed language-independent pattern**. If localized month names are needed, design and test an explicit locale policy.
- `LocalDate.parse` can throw `DateTimeParseException`, a runtime exception. Spring conversion/binding handles it via its pipeline; the formatter does not emit HTTP statuses itself.

### 6.6. Registering the Formatter in Spring MVC

`src/main/java/com/example/formatdiag/WebFormattingConfiguration.java`:

```java
package com.example.formatdiag;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    private final DottedLocalDateFormatter formatter;

    public WebFormattingConfiguration(
            DottedLocalDateFormatter formatter) {
        this.formatter = formatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(formatter);
    }
}
```

Spring MVC uses the registry to convert `String` values into `LocalDate` on eligible binding paths.

**Check question:** does this code call `ObjectMapper#registerModule`? **No.** It registers a Spring Formatter. When a controller receives `@RequestBody` JSON, Jackson does not come here to call `formatter.parse(...)`.

If the formatter does not hit even on forms/queries, verify:

- Is the Configuration class component-scanned?
- Was `addFormatters` actually invoked by Spring?
- Is `@EnableWebMvc` or custom MVC config disabling expected auto-configuration?
- Is another `Converter<String,LocalDate>` or `@DateTimeFormat` annotation taking precedence?
- Does the method signature/target type actually use `LocalDate`?
- Is the request truly going to `@RequestParam`/`@ModelAttribute` rather than a `@RequestBody` argument?

### 6.7. DTO Used for Both Forms and ISO JSON

`src/main/java/com/example/formatdiag/EventInput.java`:

```java
package com.example.formatdiag;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record EventInput(
        @NotBlank String title,
        @NotNull LocalDate eventDate
) {}
```

With `@ModelAttribute`, Spring constructor binding reads the `eventDate` string from the request and calls the matching formatter. With `@RequestBody`, Jackson reads JSON and constructs the same record using a JSON deserializer.

Records have no setters, yet Spring MVC 6.1 supports constructor binding. `@NotNull` catches a missing date after the object is constructed; it does not catch unconvertible date text in JSON because that failure occurs in Jackson before validation.

### 6.8. DTO for Dotted JSON Configured Separately

`src/main/java/com/example/formatdiag/JsonDottedInput.java`:

```java
package com.example.formatdiag;

import com.fasterxml.jackson.annotation.JsonFormat;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record JsonDottedInput(
        @NotBlank String title,

        @NotNull
        @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

`@JsonFormat` is metadata for Jackson. It does **not** prove the custom Spring Formatter ran; it simply instructs Jackson's Java Time deserializer to use its own pattern. In real APIs, avoid two DTOs with different formats unless required by business rules, as that easily confuses clients. The demo has two DTOs **to clearly observe both pipelines**.

### 6.9. Response DTO and Error Schema

`src/main/java/com/example/formatdiag/EventView.java`:

```java
package com.example.formatdiag;

import java.time.LocalDate;

public record EventView(
        String title,
        LocalDate eventDate
) {}
```

`src/main/java/com/example/formatdiag/FieldIssue.java`:

```java
package com.example.formatdiag;

public record FieldIssue(
        String field,
        String code
) {}
```

`src/main/java/com/example/formatdiag/ApiError.java`:

```java
package com.example.formatdiag;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> fields
) {}
```

`EventView` holds `LocalDate`: when returned as `@ResponseBody`, the Jackson serializer outputs dates in ISO format. This **does not contradict** dotted pattern form inputs—input parsing and output serialization are distinct.

`ApiError` never returns raw exception text, rejected JSON, or field values. Those can contain personal data; return only controlled error codes.

### 6.10. Error Mapper Using `BindingResult`

`src/main/java/com/example/formatdiag/ErrorPayloadMapper.java`:

```java
package com.example.formatdiag;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public final class ErrorPayloadMapper {

    private ErrorPayloadMapper() {
    }

    public static ApiError invalid(BindingResult result) {
        List<FieldIssue> fields = result.getAllErrors()
                .stream()
                .map(ErrorPayloadMapper::toFieldIssue)
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        return new ApiError("VALIDATION_ERROR", fields);
    }

    private static FieldIssue toFieldIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        return new FieldIssue(field, code);
    }
}
```

The mapper collects both `FieldError` and `ObjectError`, retains machine-readable codes, and sorts the output. Do not assume provider/Binder error order matches field declaration order. If the product needs localized error messages, add a separate `MessageSource`, though that **is not the mechanism that helps Jackson parse dates**.

### 6.11. `EventController` with Five Endpoints

`src/main/java/com/example/formatdiag/EventController.java`:

```java
package com.example.formatdiag;

import jakarta.validation.Valid;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/events")
public class EventController {

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> fromForm(
            @Valid @ModelAttribute("eventInput") EventInput input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    ErrorPayloadMapper.invalid(errors)
            );
        }

        return ResponseEntity.ok(
                new EventView(input.title(), input.eventDate())
        );
    }

    @GetMapping("/query")
    public EventView fromQuery(
            @RequestParam String title,
            @RequestParam LocalDate eventDate) {

        return new EventView(title, eventDate);
    }

    @GetMapping("/query-iso")
    public EventView fromAnnotatedQuery(
            @RequestParam String title,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate eventDate) {

        return new EventView(title, eventDate);
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EventView fromJson(
            @Valid @RequestBody EventInput input) {

        return new EventView(input.title(), input.eventDate());
    }

    @PostMapping(
            path = "/json-dotted",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EventView fromConfiguredJson(
            @Valid @RequestBody JsonDottedInput input) {

        return new EventView(input.title(), input.eventDate());
    }
}
```

**Reading each role accurately:**

- `fromForm` uses `@ModelAttribute`, so `WebDataBinder` uses the MVC `Formatter<LocalDate>`.
- `fromQuery` uses `@RequestParam LocalDate`, also going through Spring MVC conversion.
- `fromAnnotatedQuery` uses `@DateTimeFormat(iso=ISO.DATE)` to require ISO **for that parameter**, without affecting Jackson.
- `fromJson` uses `@RequestBody EventInput`, so the JSON body is parsed by Jackson.
- `fromConfiguredJson` is still parsed by **Jackson**, but `@JsonFormat` selects the dotted pattern.
- `EventView` JSON responses are **serialized** by Jackson; `Formatter#print` is not used merely because the object holds a `LocalDate`.

`BindingResult errors` stands **immediately after** the `@Valid @ModelAttribute` argument. Inserting another parameter between them can prevent Spring from binding errors properly.

### 6.12. Global Advice Distinguishing JSON, Query, and Validation Errors

`src/main/java/com/example/formatdiag/EventExceptionAdvice.java`:

```java
package com.example.formatdiag;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class EventExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidArgument(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                ErrorPayloadMapper.invalid(
                        exception.getBindingResult()
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_JSON", List.of())
        );
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidQueryParameter(
            MethodArgumentTypeMismatchException exception) {

        FieldIssue issue = new FieldIssue(
                exception.getName(),
                "typeMismatch"
        );

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "QUERY_TYPE_MISMATCH",
                        List.of(issue)
                )
        );
    }
}
```

In the demo:

- Malformed JSON date string → `HttpMessageNotReadableException` → `INVALID_JSON`.
- Malformed query param date → `MethodArgumentTypeMismatchException` → `QUERY_TYPE_MISMATCH`.
- Object constructed successfully yet `@NotNull`/`@NotBlank` violated → `MethodArgumentNotValidException` (JSON) or `BindingResult` (form) → `VALIDATION_ERROR`.
- Unparseable `LocalDate` form field is normally recorded as a binding error in `BindingResult`; the response is still `VALIDATION_ERROR` while `FieldIssue.code` can be `typeMismatch`.

**These are error codes designed for this demo**, not default HTTP error codes enforced by Spring on every application. Production APIs may choose RFC 9457 `ProblemDetail`, while keeping binding, parsing, and validation distinct.

## 7. Practical Testing with MockMvc

File `src/test/java/com/example/formatdiag/FormatterVsJsonTest.java`:

```java
package com.example.formatdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormatterVsJsonTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formUsesCustomSpringFormatter() throws Exception {
        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Conference"))
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void queryUsesCustomSpringFormatter() throws Exception {
        mvc.perform(get("/api/events/query")
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void isoStringIsNotTheCustomFormFormat()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void isoQueryIsNotTheCustomQueryFormat()
            throws Exception {

        mvc.perform(get("/api/events/query")
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("QUERY_TYPE_MISMATCH"));
    }

    @Test
    void annotatedQueryCanUseIsoInstead() throws Exception {
        mvc.perform(get("/api/events/query-iso")
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void annotatedIsoQueryRejectsDottedInput()
            throws Exception {

        mvc.perform(get("/api/events/query-iso")
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("QUERY_TYPE_MISMATCH"));
    }

    @Test
    void normalJsonUsesJacksonIsoDeserialization()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "2026-11-06"
                        }
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void sameDottedTextInJsonDoesNotUseSpringFormatter()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "06.11.2026"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void jsonFormatMakesJacksonAcceptDottedText()
            throws Exception {

        mvc.perform(post("/api/events/json-dotted")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "06.11.2026"
                        }
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void jsonFormatDoesNotMeanJsonAlsoAcceptsIso()
            throws Exception {

        mvc.perform(post("/api/events/json-dotted")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "2026-11-06"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void missingDateInFormFailsNotNull()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("eventDate"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotNull"));
    }

    @Test
    void missingDateInJsonFailsValidationNotParsing()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"Conference"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotNull"));
    }

    @Test
    void blankTitleInJsonIsBeanValidation()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"  ","eventDate":"2026-11-06"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("title"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotBlank"));
    }

    @Test
    void malformedJsonFailsInConverter()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Conference\",\"eventDate\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void invalidCalendarDateInFormIsRejected()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "31.02.2026"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void invalidCalendarDateInJsonIsRejected()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title":"Conference",
                          "eventDate":"2026-02-31"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void unsupportedMediaTypeDoesNotBecomeFormatterFailure()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"Conference","eventDate":"2026-11-06"}
                        """))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

The test suite contains **17 `@Test` methods**. They verify:

1. Form-urlencoded accepts `06.11.2026`.
2. Query parameter accepts `06.11.2026`.
3. ISO form value does not match the custom formatter → binding error.
4. ISO query value does not match the custom formatter → query type mismatch.
5. `@DateTimeFormat(iso=ISO.DATE)` makes a query parameter parse ISO.
6. Annotated ISO query rejects dotted input.
7. Default JSON parses ISO via Jackson.
8. The same dotted text in JSON is rejected even though the Spring Formatter is registered.
9. `@JsonFormat` makes **Jackson** parse dotted text without needing the Spring Formatter.
10. The JSON endpoint configured with a dotted pattern rejects ISO when the pattern mismatches.
11. Form missing date → Bean Validation `NotNull`.
12. JSON missing date, when the record is constructed with null → Bean Validation `NotNull`.
13. JSON blank title → Bean Validation `NotBlank`.
14. Malformed JSON → converter/parser error.
15. Nonexistent calendar date is rejected by the custom Formatter.
16. Nonexistent calendar date is rejected by Jackson.
17. Wrong Content-Type/consumes → 415, not a formatter failure.

### 7.1. Running the Tests

From the project directory with a Gradle wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If there is no wrapper yet, you can run `gradle test` with an installed Gradle or generate the wrapper first.

**Expected:** 17 tests PASS with Spring Boot 3.3.6, Java 17, and the declared dependencies, assuming no other custom converters/mappers interfere. This expectation comes from static review of the source; it is **not** a claim that Gradle/JUnit was actually executed while authoring the article.

### 7.2. Why Choose These Assertions?

Checking only HTTP 400 is insufficient to diagnose "Formatter did not apply." HTTP 400 can stem from Jackson deserialization, Bean Validation, Spring property binding, or Servlet parameter resolution. Hence the tests also compare:

- Which endpoint was called.
- `Content-Type`.
- Dotted vs. ISO date strings.
- Advice error codes: `INVALID_JSON`, `VALIDATION_ERROR`, `QUERY_TYPE_MISMATCH`.
- On success, the ISO `eventDate` in the response proves the **Jackson writer** serializes dates independently of the Spring Formatter input.

Do not assert a specific English error sentence from Jackson/Bean Validation; it can change with locale, version, or provider. Demo error codes are more stable for diagnosis.

## 8. Expected HTTP Responses: Comparing the Same Date

### 8.1. Form-Urlencoded with Formatter

```bash
curl -i -X POST 'http://localhost:8080/api/events/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Conference' \
  --data-urlencode 'eventDate=06.11.2026'
```

Expected HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

Although **input** is dotted, **output** is ISO. This is not a bug: the request goes through Spring Formatter, while the JSON response goes through the Jackson serializer.

### 8.2. Default JSON with the Same Dotted Input

```bash
curl -i -X POST 'http://localhost:8080/api/events/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"06.11.2026"}'
```

Expected HTTP 400:

```json
{
  "code": "INVALID_JSON",
  "fields": []
}
```

Here Jackson cannot parse the dotted format using the default ISO `LocalDate` deserializer. The registered Spring Formatter **is never called**, because `@RequestBody` uses `HttpMessageConverter`.

### 8.3. ISO JSON

```bash
curl -i -X POST 'http://localhost:8080/api/events/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"2026-11-06"}'
```

Expected HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

### 8.4. Dotted JSON with `@JsonFormat`

```bash
curl -i -X POST 'http://localhost:8080/api/events/json-dotted' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"06.11.2026"}'
```

Expected HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

In this endpoint Jackson was instructed to parse the dotted pattern via `@JsonFormat` on the **request DTO**. When serializing the `EventView` response DTO without `@JsonFormat`, the Jackson writer uses ISO.

### 8.5. Query with `@DateTimeFormat`

```bash
curl -i 'http://localhost:8080/api/events/query-iso?title=Conference&eventDate=2026-11-06'
```

Expected HTTP 200 with ISO date. Even though the global `Formatter<LocalDate>` uses the dotted pattern, `@DateTimeFormat(iso=...)` on the argument chooses the format for Spring argument binding.

## 9. Common Mistakes When "Fixing a Formatter for JSON"

### 9.1. Registering More Formatters While Still Using `@RequestBody`

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DottedLocalDateFormatter());
}
```

Adding this code again will not change Jackson. Look at `ObjectMapper`, `@JsonFormat`, or `JsonDeserializer` instead of repeating the same registration.

### 9.2. Placing `@DateTimeFormat` on a JSON DTO Expecting Jackson to Use It

```java
public record JsonDateInput(
        @DateTimeFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

This annotation serves Spring formatting, not Jackson deserialization. With `@RequestBody` JSON, if only that annotation is present, Jackson can still reject dotted input. Use `@JsonFormat` if the JSON format genuinely needs to change.

### 9.3. Placing `@JsonFormat` When Handling `@RequestParam`

```java
@GetMapping("/query")
public String query(
        @RequestParam @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate) {
    return eventDate.toString();
}
```

A Jackson annotation is not how you configure request parameter string conversion. You need `@DateTimeFormat` or an appropriate Spring `Formatter`/`Converter`. This snippet simply illustrates the separation of responsibilities.

### 9.4. Using `@EnableWebMvc` to Try to Fix the Issue

In Spring Boot, enabling `@EnableWebMvc` can significantly alter MVC auto-configuration and converters. Just to add a formatter, use `WebMvcConfigurer#addFormatters`; do not override all of Web MVC without good reason and tests.

### 9.5. Confusing `Formatter` with a Jackson Serializer

`Formatter#print` produces strings for **Spring field formatting**, not what `MappingJackson2HttpMessageConverter` does when serializing JSON. Both "format" data, yet they have distinct SPIs and lifecycles.

### 9.6. Treating `@Valid` as a JSON Parser

`@Valid` does not parse JSON. It runs after the object is successfully constructed. If a date string is not understood by Jackson, the error is normally `HttpMessageNotReadableException`, not the default `@NotNull`.

### 9.7. Handling Every 400 with One "Validation failed" Message

Returning a uniform HTTP 400 is fine if the API contract chooses to, yet backend logs/metrics should distinguish:

- Unsupported media type.
- JSON parse/deserialize failure.
- Spring binding/type conversion failure.
- Bean Validation constraint failure.
- Business-level validation failure.

If everything turns into "invalid input" without context, it becomes very hard to tell why a formatter breakpoint never hit.

### 9.8. Using `LocaleResolver` and Expecting Jackson to Use the Same Locale

Spring Formatter receives `Locale` as a parameter and can apply the Spring-resolved request locale. Jackson deserialization does not automatically inherit all Spring `LocaleResolver` rules simply because `Accept-Language: vi` was sent. If JSON has localized dates or numbers, define an explicit Jackson locale/format policy and test it; in public APIs, ISO/numeric JSON is usually far more interoperable.

### 9.9. Confusing JSON Numbers with Locale-Formatted Strings

For JSON:

```json
{"price": 1234.56}
```

`price` is a JSON **number token**, not a `String` `"1.234,56"` for Spring `@NumberFormat` to parse. Jackson handles the token type accordingly. If JSON needs a string value with thousands separators, design the JSON schema and Jackson deserializer/format for that field; do not expect Spring `Formatter<BigDecimal>` to kick in automatically.

### 9.10. Ignoring Annotation Precedence

If you put `@DateTimeFormat(iso=ISO.DATE)` on a method parameter, it can override Spring's type-based formatter selection. Then the custom Formatter breakpoint will not hit on **the annotated query endpoint**, which is completely different from **the JSON endpoint**. Distinguish the two causes:

- The JSON path **bypasses Spring FormattingConversionService** for deserialization.
- The Spring conversion path **selects a different annotation-specific formatter**.

Testing pairs with the same format with/without annotations reveals the cause.

### 9.11. Testing Only a JSON Endpoint and Skipping Forms/Queries

If a formatter does not run, how do you know whether registration is missing or the request went through a converter? Simple test:

1. Call `@RequestParam LocalDate` with a dotted string.
2. Call `@ModelAttribute` with a dotted form field.
3. Call `@RequestBody` with a dotted JSON string.

If 1 and 2 succeed while 3 fails, registration is not the primary bug. If 1 and 2 also fail, inspect the Spring MVC converter registry, component scan, and annotation precedence.

### 9.12. Malformed JSON and Validation Groups Are Separate Issues

If method validation/`@Validated` is enabled on the controller class, exception types may differ from Spring MVC's built-in method validation in Framework 6.1; however, that **does not turn a Spring Formatter into a Jackson deserializer**. Do not change validation groups to fix parsing. Keep each layer's responsibility separate.

## 10. Production Diagnostic Checklist

1. Identify the method parameter annotation: `@RequestParam`, `@ModelAttribute`, `@RequestBody`, `@RequestPart`, or another type.
2. Check `Content-Type` and target Java type; do not guess from the URL or client code.
3. If `@RequestBody` JSON, inspect the selected `HttpMessageConverter`, Jackson ObjectMapper, and Java Time module.
4. If form/query, inspect `FormattingConversionService`, `WebMvcConfigurer#addFormatters`, and `FormatterRegistry`.
5. Check for `@DateTimeFormat` / `@NumberFormat` on fields/method parameters.
6. Set breakpoints in custom `Formatter#parse`, Jackson deserializer, and converter resolver to identify the pipeline.
7. Do not use `@DateTimeFormat` to control Jackson JSON; use `@JsonFormat` or a Jackson deserializer.
8. Do not use `@JsonFormat` to control Spring query/form field binding; use a Formatter/Converter or `@DateTimeFormat`.
9. Distinguish an invalid body from a null/missing property after deserialization.
10. Verify `@Valid` runs after binding/deserialization and that exception mapping is right.
11. Never echo raw JSON bodies, SQL logs, tokens, or sensitive exception details in client error responses.
12. For API dates, prefer ISO 8601 in JSON and localized formatting in the UI; carefully control time zones for `Instant`, `OffsetDateTime`, and `ZonedDateTime`.
13. Test all three paths—form, query, and JSON—on both success and failure.
14. Test annotation precedence: with/without `@DateTimeFormat` and per-property `@JsonFormat`.
15. Test nonexistent dates, null/missing values, malformed text, malformed bodies, and wrong media types.
16. Never enable `@EnableWebMvc` casually just to register a Formatter.
17. Align docs/OpenAPI/JSON schema: the JSON contract must publish date formats for clients.
18. When upgrading Boot/Spring/Jackson, re-run tests because implementations, defaults, and error messages may change.

**Conclusion:** When a Formatter does not run in a JSON endpoint, inspect **the request processing path** before adding configuration. `@ModelAttribute` and `@RequestParam` normally use Spring `ConversionService`/`Formatter` to convert from request strings, whereas `@RequestBody` JSON uses `HttpMessageConverter` and a JSON mapper (typically Jackson). The two mechanisms do not automatically share formatter registrations. The fix depends on your goal: **keep ISO JSON** for simplicity, or configure **`@JsonFormat`/Jackson deserializer** when JSON truly needs another pattern. Comparing form, query, and JSON in tests diagnoses the issue far more reliably than merely looking at HTTP 400.

## 11. References

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `Parser`, `Printer`, and `FormattingConversionService`.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): string-based conversion of request arguments.
- [Spring Framework — MVC Conversion Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): `WebMvcConfigurer#addFormatters` and `@DateTimeFormat`.
- [Spring Framework — @ModelAttribute Argument](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): `WebDataBinder`, binding request parameters, and validation.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization via `HttpMessageConverter` and subsequent validation.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converters for request/response bodies.
- [Spring Framework — MVC Message Converter Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): customizing converters.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC ConversionService and HttpMessageConverters.
- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): ObjectMapper auto-config and custom serializers/deserializers.
- [Jackson — JsonFormat Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.17.3/com/fasterxml/jackson/annotation/JsonFormat.html): pattern/shape/locale for Jackson properties.
