# Configuring Codecs, Converters, Formatters, and Validators in Spring WebFlux

## 1. Four Components Solving Four Different Jobs

When a request enters Spring WebFlux, data may pass through multiple steps before reaching the controller:

1. **HTTP message codec** reads bytes from the request body, decodes them into a Java object, and encodes objects into the response body.
2. **Converter** converts a value from one type to another, typically a String into a domain type.
3. **Formatter** parses and prints values according to a locale-aware format, such as dates or monetary amounts.
4. **Validator** verifies that bound or deserialized data satisfies validation rules.

For example, a product-creation API receives JSON, while also having a search endpoint:

- The JSON body is read by the Jackson codec into CreateProductRequest.
- The query parameter category=BOOKS is converted by a Converter into CategoryCode.
- The query parameter from=01/03/2026 is converted by a Formatter into LocalDate.
- @NotBlank, @Positive, and a date-range validator verify that the data is valid.

These components can work together on the same request, but they do not replace one another. A Converter is not a JSON decoder; a Formatter is not a validator; a Validator does not read bytes from an HTTP body on its own.

## 2. Request Processing Flow in WebFlux

For annotated controllers, the overall flow:

~~~text
HTTP request
    |
    +-- Content-Type / body bytes
    |       |
    |       v
    |   HttpMessageReader
    |       |
    |       v
    |   Decoder / Codec
    |       |
    |       v
    |   Java object (@RequestBody, @RequestPart)
    |
    +-- Query / path / header / form values
            |
            v
        WebDataBinder
            |
            +-- ConversionService
            |       +-- Converter
            |       +-- Formatter
            |
            +-- Validator
                    |
                    v
             Controller method
                    |
                    v
          HttpMessageWriter / Encoder
                    |
                    v
             HTTP response bytes
~~~

The request-body reading path normally uses HttpMessageReader and Decoder. The response-writing path uses HttpMessageWriter and Encoder. For String values from query, path, header, or model attributes, Spring uses the binding system and ConversionService. After binding or deserialization, validation checks the object.

For functional endpoints, codecs are still used when calling bodyToMono, bodyToFlux, or writeWith. Converters and Validators are usually invoked more explicitly in handlers or via WebExchangeDataBinder if the application binds data manually.

## 3. HTTP Message Codecs: Reading and Writing Bodies

### 3.1. What Is a Codec?

A codec is a component that converts between bytes and objects in a non-blocking manner:

| Component | Responsibility |
| --- | --- |
| Encoder | Encodes an object into a byte stream |
| Decoder | Decodes a byte stream into an object |
| HttpMessageReader | Reads an HTTP message body and uses an appropriate Decoder |
| HttpMessageWriter | Writes an HTTP message body and uses an appropriate Encoder |
| DataBuffer | Abstraction for byte regions read/written by codecs |
| CodecConfigurer | Registers and customizes default or custom readers/writers |

Spring Core provides support for byte[], ByteBuffer, DataBuffer, Resource, and String. Spring Web adds codecs for JSON, XML, form data, multipart, server-sent events, and other formats when the corresponding libraries are on the classpath.

In a Spring Boot WebFlux application, default codecs are auto-configured based on dependencies. For example, if Jackson is on the classpath, JSON readers/writers are registered. You do not need to create all readers/writers manually for common formats.

### 3.2. Content-Type and Accept

Two key headers:

- **Content-Type** describes the body format sent by the client. The server chooses a matching HttpMessageReader to read it.
- **Accept** describes the response format the client wants to receive. The server chooses a matching HttpMessageWriter to write it.

Example:

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard","price":49.90}
~~~

The controller receives CreateProductRequest; the Jackson decoder reads the JSON. When the controller returns an object, the Jackson encoder writes the JSON response.

If a request sends a Content-Type with no matching reader, WebFlux can return 415 Unsupported Media Type. If there is no writer matching Accept, it can return 406 Not Acceptable. If the body format is supported but the data is syntactically invalid, a decode error usually becomes a 400 bad request error.

### 3.3. Customizing Default Codecs

Use WebFluxConfigurer to configure server-side readers/writers:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
~~~

The example sets the aggregation buffer limit to 512 KiB. This limit applies when a codec must buffer content to decode into a single value such as String, byte[], or a JSON object. When the limit is exceeded, the application may receive a DataBufferLimitException.

This is not a total upload size limit for the entire request. For large data, prefer streaming processing with Flux<DataBuffer>, Flux<PartEvent>, or an appropriate Resource instead of buffering all content into an in-memory object.

### 3.4. Configuring Jackson ObjectMapper

If you want to use the ObjectMapper configured by Spring Boot, you can replace the default decoder/encoder with instances using that mapper:

~~~java
@Configuration
public class JsonCodecConfiguration implements WebFluxConfigurer {

    private final ObjectMapper objectMapper;

    public JsonCodecConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(512 * 1024);

        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));

        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
    }
}
~~~

The ObjectMapper provided by Spring Boot may already have spring.jackson.* settings, the Java Time module, and Jackson modules found on the classpath. Sharing the mapper keeps JSON body serialization/deserialization consistent under one policy.

When replacing a default decoder or encoder, ensure the new codec supports all MediaTypes the API needs. Do not replace a default codec with a decoder that only reads one media type and accidentally lose support for application/json.

### 3.5. Registering Custom Codecs

If the API uses a custom format or needs special decoding behavior, you can register a custom Encoder/Decoder or HttpMessageReader/Writer:

~~~java
MimeType customType = MimeType.valueOf("application/x-example-json");

configurer.customCodecs().registerWithDefaultConfig(
        new Jackson2JsonDecoder(objectMapper, customType));

configurer.customCodecs().registerWithDefaultConfig(
        new Jackson2JsonEncoder(objectMapper, customType));
~~~

registerWithDefaultConfig registers the codec while applying certain default settings such as maxInMemorySize and request-details logging if configured. Use register() when you need to manage the codec's configuration yourself.

If a custom codec needs the same buffer limit as default codecs, use registerWithDefaultConfig or configure the corresponding limit explicitly. Do not assume a custom codec automatically inherits all defaultCodecs settings if registered only with register().

### 3.6. Do Not Arbitrarily Disable Default Codecs

CodecConfigurer provides registerDefaults(false). When set to false, Spring does not register default readers/writers; the application must supply all necessary codecs itself.

Only use this when you want complete control over HTTP formats. If you only need to add a custom format, register it via customCodecs() and keep the default codecs.

### 3.7. WebClient Codecs Are Configured Separately

Configuring ServerCodecConfigurer in WebFluxConfigurer affects the HTTP server. It does not automatically change WebClient's codecs.

The client has its own configuration:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(512 * 1024);
        })
        .build();
~~~

You can register custom decoders/encoders for WebClient via ClientCodecConfigurer. Configure both sides if the application both receives HTTP requests and calls external APIs.

### 3.8. Spring Boot 3.5 Configuration

Spring Boot 3.5 supports shared codec configuration for auto-configured WebFlux servers and WebClient instances via:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
      log-request-details: false
~~~

max-in-memory-size limits the number of bytes buffered when an input stream must be aggregated. log-request-details enables logging form data at DEBUG and headers at TRACE when set to true. This data can contain tokens, personal information, or sensitive data; keep it false in production unless there is a clear reason and proper safeguards.

You can configure via properties or CodecConfigurer. If separate policies per server/client or custom codecs are needed, configuring in Java gives finer control.

## 4. Converter: Data Type Conversion

### 4.1. What Problem Does Converter Solve?

HTTP typically transmits values as text. Controllers may need to receive a domain type rather than parsing Strings manually in every method.

Converter<S,T> defines a conversion from source type S to target type T:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Example converting the string "books" into CategoryCode:

~~~java
public record CategoryCode(String value) {
}

public class StringToCategoryCodeConverter
        implements Converter<String, CategoryCode> {

    @Override
    public CategoryCode convert(String source) {
        String normalized = source.trim()
                .toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z][a-z0-9-]{0,19}")) {
            throw new IllegalArgumentException("Invalid category code");
        }

        return new CategoryCode(normalized);
    }
}
~~~

Converter fits general type conversion logic that does not require locale-specific display formatting. Other examples: String to UUID, String to a domain enum, Long to AccountId, or String to a business code type.

### 4.2. Registering a Global Converter

WebFluxConfigurer.addFormatters receives a FormatterRegistry. This registry is also where Converters are registered:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCategoryCodeConverter());
    }
}
~~~

Once registered, Spring can convert String to CategoryCode when binding values such as path variables, request parameters, or model attribute fields.

Example:

~~~java
@GetMapping("/categories/{category}/products")
Mono<List<Product>> products(
        @PathVariable CategoryCode category) {
    return service.findByCategory(category);
}
~~~

If a request calls /categories/BOOKS/products, the converter normalizes the value into CategoryCode("books"). The controller receives the converted domain type.

### 4.3. A Converter Can Fail

If the input value is invalid, the converter can throw IllegalArgumentException. Spring translates the conversion error into a context-appropriate binding/request error.

Do not use a converter to replace validation for an entire object. A converter only answers "which target type value does this String represent?". A validator answers "does the converted object satisfy business rules?".

For example, "books" can convert to a valid CategoryCode, yet a SearchCriteria containing a `from` after `to` is still invalid. These are two distinct steps.

## 5. Formatter: Locale-Aware Parsing and Printing

### 5.1. How Does Formatter Differ from Converter?

Formatter is designed for display/input data in a web environment and accepts a Locale:

~~~java
public interface Formatter<T> {
    T parse(String text, Locale locale) throws ParseException;
    String print(T object, Locale locale);
}
~~~

| Aspect | Converter | Formatter |
| --- | --- | --- |
| Purpose | General type conversion | Parse/print values by format |
| Locale | No Locale parameter | Accepts Locale |
| Conversion direction | Source to Target | String to object and object to String |
| Example | String to CategoryCode | "12/03/2026" to LocalDate |

If you only need type conversion, use Converter. If you need to represent dates, numbers, or currencies by language/region, Formatter is more appropriate.

### 5.2. Formatter for LocalDate

Example formatter using the dd/MM/yyyy date format:

~~~java
public class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException error) {
            ParseException exception =
                    new ParseException("Expected dd/MM/yyyy", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
~~~

Formatter receives the request's Locale so it can choose an appropriate parse/print style. In this example the date pattern is kept fixed so the API has an explicit contract. If you want fully localized date formatting, you can create a DateTimeFormatter with DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale).

Do not use a shared SimpleDateFormat in a singleton formatter because SimpleDateFormat is not thread-safe. DateTimeFormatter is immutable and thread-safe, suitable for reactive applications with many concurrent requests.

### 5.3. Registering a Formatter

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToCategoryCodeConverter());
    registry.addFormatter(new LocalDateFormatter());
}
~~~

Controllers can receive LocalDate directly:

~~~java
@GetMapping("/search")
Mono<SearchResult> search(
        @RequestParam LocalDate from,
        @RequestParam LocalDate to) {
    return service.search(from, to);
}
~~~

Request:

~~~http
GET /search?from=01%2F03%2F2026&to=31%2F03%2F2026
~~~

Spring binds the query parameter strings into LocalDate using the registered formatter.

### 5.4. Formatter Can Be Used for Model Attributes and Forms

When using @ModelAttribute, WebDataBinder binds multiple fields into one object. Converters and Formatters apply to each property according to its target type.

~~~java
@GetMapping("/search-form")
Mono<SearchResult> searchForm(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
    return service.search(criteria);
}
~~~

If SearchCriteria has CategoryCode and LocalDate fields, Spring uses the converter and formatter to bind the corresponding strings.

Spring WebFlux already installs built-in formatters for many numeric and date types. Annotations such as @NumberFormat, @DurationFormat, and @DateTimeFormat can customize formatting for fields/parameters without writing a new formatter.

### 5.5. DateTimeFormat and HTML Date Inputs

Browsers use fixed HTML formats for input type="date" and input type="time". For web forms, you can configure DateTimeFormatterRegistrar:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
~~~

ISO format matches HTML date/time fields. Distinguish between display formatting in a custom-designed form and the standard format that browsers send for input type="date".

## 6. DataBinder and @InitBinder

### 6.1. What Does DataBinder Do?

WebDataBinder coordinates binding request values into objects, type conversion, and running validation. It is normally created per bind operation and should not be kept in a shared field.

An @InitBinder method can register:

- Legacy PropertyEditors.
- Converters or Formatters scoped to the binder.
- Local Validators.
- Binding settings such as allowed fields or direct field access when appropriate.

### 6.2. Registering a Local Validator

~~~java
@Controller
public class SearchController {

    @InitBinder("criteria")
    void initCriteriaBinder(WebDataBinder binder) {
        binder.addValidators(new SearchCriteriaValidator());
    }
}
~~~

The name criteria matches the model attribute name. The validator applies only to that object's binder. If @InitBinder is used in @ControllerAdvice, it can apply to multiple controllers or controller groups as configured.

### 6.3. Global Converter/Formatter vs. Local Binder

Use WebFluxConfigurer.addFormatters when a conversion type is used across many controllers. Use @InitBinder when a rule fits only a specific form or controller.

Do not register the same formatter in multiple ways without reason, as registration order and scope can make binding behavior hard to predict.

## 7. Validator: Validating Data After Binding

### 7.1. Spring Validator

Spring provides the Validator interface:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

supports indicates whether the validator handles that object type. validate checks the object and records errors into Errors/BindingResult.

Example validating a date range:

~~~java
public class SearchCriteriaValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SearchCriteria.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchCriteria criteria = (SearchCriteria) target;

        if (criteria.getFrom() != null
                && criteria.getTo() != null
                && criteria.getTo().isBefore(criteria.getFrom())) {
            errors.rejectValue(
                    "to",
                    "date.range.invalid",
                    "to must not be before from"
            );
        }
    }
}
~~~

The validator checks the relationship between two fields. This is a fitting example for a custom validator because a single annotation on each individual field cannot directly express the rule that `from` must be less than or equal to `to`.

### 7.2. Bean Validation with Jakarta

Spring WebFlux supports Jakarta Bean Validation. Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

When a provider such as Hibernate Validator is on the classpath, Spring registers LocalValidatorFactoryBean as the default global Validator.

Commonly used annotations:

| Annotation | Meaning |
| --- | --- |
| @NotNull | Value must not be null |
| @NotBlank | String must not be null, empty, and must contain at least one non-whitespace character |
| @NotEmpty | String/collection/map/array must not be empty |
| @Size | Limits length or number of elements |
| @Min / @Max | Bounds integer values by a threshold |
| @Positive / @PositiveOrZero | Number must be positive or non-negative |
| @DecimalMin / @DecimalMax | Bounds decimal values |
| @Email | Checks basic email format |
| @Pattern | Checks against a regular expression |
| @Valid | Triggers cascading validation on nested objects |

Example:

~~~java
public record CreateProductRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
) {
}
~~~

Controller:

~~~java
@PostMapping("/products")
Mono<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    return service.create(request);
}
~~~

If name is blank or price is less than 0.01, WebFlux rejects the request before invoking controller logic.

### 7.3. @Valid and @Validated

@Valid requests validation of the object and cascades down to nested fields/objects. @Validated is Spring's annotation, supporting validation groups and additional ways to trigger validation.

@Valid is not a constraint annotation. @Valid itself does not trigger method validation; it only requests validation of the annotated object and nested objects.

Nested validation example:

~~~java
public record AddressRequest(
        @NotBlank String city,
        @NotBlank String street
) {
}

public record CustomerRequest(
        @NotBlank String name,
        @Valid @NotNull AddressRequest address
) {
}
~~~

If @Valid is missing on address, constraints on city/street may not be checked via cascading.

### 7.4. Validation for @RequestBody, @RequestPart, and @ModelAttribute

WebFlux supports validation for command objects marked with @Valid or @Validated on parameters such as:

- @RequestBody CreateProductRequest.
- @RequestPart UploadMetadata.
- @ModelAttribute SearchCriteria.

For Map or Collection parameters, validation conditions differ; it is usually better to wrap data in a DTO to declare constraints and nested validation clearly.

If you need to retain errors so the controller can decide itself, place Errors or BindingResult immediately after the validated parameter. Otherwise, WebFlux raises the appropriate exception.

## 8. Two Types of Validation Exceptions in WebFlux

Since Spring Framework 6.1, WebFlux includes built-in method validation for annotated controllers. Applications should distinguish two main exceptions:

| Exception | When It Typically Occurs |
| --- | --- |
| WebExchangeBindException | Validation of a single command object such as @ModelAttribute, @RequestBody, or @RequestPart |
| HandlerMethodValidationException | Method validation when constraints such as @Min or @NotBlank are placed directly on parameters or return values |

Method parameter constraint example:

~~~java
@GetMapping("/page")
Mono<PageResult> page(@RequestParam("page") @Min(1) int page) {
    return Mono.just(new PageResult(page));
}
~~~

If page is less than 1, built-in method validation can raise HandlerMethodValidationException.

To use Spring Framework 6.1+'s built-in method validation, do not place @Validated at the controller class level. Class-level @Validated activates AOP proxy-based method validation; that changes the mechanism and exception used.

Applications should handle both WebExchangeBindException and HandlerMethodValidationException because which exception is raised depends on the controller signature.

### 8.1. Centralized Validation Error Handling

~~~java
@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ValidationError> handleBinding(
            WebExchangeBindException exception) {

        String detail = exception.getFieldErrors().stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ValidationError("VALIDATION_ERROR", detail));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ValidationError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        return ResponseEntity.badRequest().body(
                new ValidationError(
                        "METHOD_VALIDATION_ERROR",
                        "One or more method parameters are invalid"));
    }
}
~~~

In production, return enough error codes and field information for the client to fix the request. Do not return stack traces or internal validator details. If localized messages are needed, use MessageSource and message bundles rather than hardcoding all messages.

## 9. Global Validator and Local Validator

### 9.1. Default Validator

When Bean Validation is present, LocalValidatorFactoryBean is registered globally. You can use it for @Valid/@Validated on controller arguments and inject it into services if you need to validate objects in the business layer.

### 9.2. Customizing the Global Validator

WebFluxConfigurer has getValidator():

~~~java
@Override
public Validator getValidator() {
    return customGlobalValidator;
}
~~~

If you override the global validator, understand that it replaces the default validator. If Bean Validation is still needed, combine/delegate to LocalValidatorFactoryBean rather than accidentally dropping Jakarta constraints.

### 9.3. Local Validator via @InitBinder

~~~java
@InitBinder("criteria")
void initBinder(WebDataBinder binder) {
    binder.addValidators(new SearchCriteriaValidator());
}
~~~

This adds rules for one object without replacing the global validator. It is an easy-to-control choice when a custom rule applies only to one form.

### 9.4. Custom Constraint Annotations

If a rule is reusable across multiple DTOs, you can create a @Constraint annotation and a ConstraintValidator. For example, @ValidProductCode can validate product code format. SpringConstraintValidatorFactory allows validators to receive Spring dependencies when instantiated by LocalValidatorFactoryBean.

Use a Spring Validator when a rule is tied to an object and needs Errors; use a Jakarta constraint when you want a reusable annotation on fields, properties, parameters, or classes.

## 10. Runnable Java 17+ Example: Codecs, Converter, Formatter, and Validator

The example uses Spring Boot 3.5.16, Java 17+, and WebFlux. The application provides:

- POST /api/products accepts JSON and validates @NotBlank, @Size, @DecimalMin.
- GET /api/search binds category via Converter, from/to via Formatter, and validates the date range with a Spring Validator.
- GET /api/page validates a method parameter directly with @Min.
- POST /api/codec-echo demonstrates JSON bodies read/written by the configured Jackson codec.

### 10.1. Project Structure

~~~text
webflux-binding-demo/
├── pom.xml
└── src/
    ├── main/java/example/binding/
    │   ├── DemoApplication.java
    │   ├── WebConfig.java
    │   ├── ProductController.java
    │   ├── CategoryCode.java
    │   ├── StringToCategoryCodeConverter.java
    │   ├── LocalDateFormatter.java
    │   ├── SearchCriteria.java
    │   ├── SearchCriteriaValidator.java
    │   ├── CreateProductRequest.java
    │   ├── ProductMessage.java
    │   ├── SearchResult.java
    │   ├── ProductResponse.java
    │   ├── PageResult.java
    │   ├── ValidationError.java
    │   └── ValidationAdvice.java
    └── test/java/example/binding/
        └── ProductControllerTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 10.3. DemoApplication.java

~~~java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. CategoryCode.java

~~~java
package example.binding;

public record CategoryCode(String value) {
}
~~~

### 10.5. StringToCategoryCodeConverter.java

~~~java
package example.binding;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToCategoryCodeConverter
        implements Converter<String, CategoryCode> {

    @Override
    public CategoryCode convert(String source) {
        String normalized = source.trim()
                .toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z][a-z0-9-]{0,19}")) {
            throw new IllegalArgumentException(
                    "Category must contain 1-20 lowercase letters, digits or hyphens");
        }

        return new CategoryCode(normalized);
    }
}
~~~

### 10.6. LocalDateFormatter.java

~~~java
package example.binding;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException error) {
            ParseException exception =
                    new ParseException("Expected dd/MM/yyyy", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
~~~

### 10.7. SearchCriteria.java

~~~java
package example.binding;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;

public class SearchCriteria {

    @NotNull
    private CategoryCode category;

    @NotNull
    private LocalDate from;

    @NotNull
    private LocalDate to;

    public CategoryCode getCategory() {
        return category;
    }

    public void setCategory(CategoryCode category) {
        this.category = category;
    }

    public LocalDate getFrom() {
        return from;
    }

    public void setFrom(LocalDate from) {
        this.from = from;
    }

    public LocalDate getTo() {
        return to;
    }

    public void setTo(LocalDate to) {
        this.to = to;
    }
}
~~~

### 10.8. SearchCriteriaValidator.java

~~~java
package example.binding;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class SearchCriteriaValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SearchCriteria.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchCriteria criteria = (SearchCriteria) target;

        if (criteria.getFrom() != null
                && criteria.getTo() != null
                && criteria.getTo().isBefore(criteria.getFrom())) {
            errors.rejectValue(
                    "to",
                    "date.range.invalid",
                    "to must not be before from"
            );
        }
    }
}
~~~

### 10.9. CreateProductRequest.java

~~~java
package example.binding;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
) {
}
~~~

### 10.10. ProductMessage.java

~~~java
package example.binding;

public record ProductMessage(String id, String name) {
}
~~~

### 10.11. Response records

~~~java
package example.binding;

import java.time.LocalDate;

public record SearchResult(
        String category,
        LocalDate from,
        LocalDate to
) {
}
~~~

~~~java
package example.binding;

import java.math.BigDecimal;

public record ProductResponse(String name, BigDecimal price) {
}
~~~

~~~java
package example.binding;

public record PageResult(int page) {
}
~~~

~~~java
package example.binding;

public record ValidationError(String code, String detail) {
}
~~~

The records above can be placed in their corresponding files as listed in the project structure.

### 10.12. WebConfig.java

~~~java
package example.binding;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebFluxConfigurer {

    private final ObjectMapper objectMapper;

    public WebConfig(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(512 * 1024);

        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));

        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCategoryCodeConverter());
        registry.addFormatter(new LocalDateFormatter());
    }
}
~~~

Do not add @EnableWebFlux in this Spring Boot example. Only implement WebFluxConfigurer to add configuration while preserving Boot's WebFlux auto-configuration.

### 10.13. ProductController.java

~~~java
package example.binding;

import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.validation.Validator;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ProductController {

    @GetMapping("/categories/{category}")
    public Mono<SearchResult> category(
            @PathVariable CategoryCode category) {
        return Mono.just(new SearchResult(
                category.value(), null, null));
    }

    @GetMapping("/search")
    public Mono<SearchResult> search(
            @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
        return Mono.just(new SearchResult(
                criteria.getCategory().value(),
                criteria.getFrom(),
                criteria.getTo()
        ));
    }

    @PostMapping(
            path = "/products",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        return Mono.just(new ProductResponse(
                request.name(),
                request.price()
        ));
    }

    @PostMapping(
            path = "/codec-echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductMessage> codecEcho(
            @RequestBody ProductMessage message) {
        return Mono.just(message);
    }

    @GetMapping("/page")
    public Mono<PageResult> page(
            @RequestParam("page") @Min(1) int page) {
        return Mono.just(new PageResult(page));
    }

    @InitBinder("criteria")
    void initCriteriaBinder(WebDataBinder binder) {
        binder.addValidators(new SearchCriteriaValidator());
    }
}
~~~

The categories endpoint tests Converter. The search endpoint tests Converter, Formatter, Bean Validation, and the custom Spring Validator. The products endpoint tests the JSON codec and Jakarta constraints. The page endpoint tests method validation directly on a parameter.

### 10.14. ValidationAdvice.java

~~~java
package example.binding;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ValidationError> handleBinding(
            WebExchangeBindException exception) {

        String detail = exception.getFieldErrors().stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ValidationError("VALIDATION_ERROR", detail));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ValidationError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        return ResponseEntity.badRequest().body(
                new ValidationError(
                        "METHOD_VALIDATION_ERROR",
                        "One or more method parameters are invalid"));
    }
}
~~~

### 10.15. application.yml

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
      log-request-details: false
~~~

This property is Spring Boot 3.5's way to configure auto-configured codecs. WebConfig in the example also sets the limit directly in Java to demonstrate the ServerCodecConfigurer API. In real applications, pick one configuration source as the standard to avoid two conflicting values.

### 10.16. ProductControllerTest.java

~~~java
package example.binding;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void convertsCategoryPathVariable() {
        webTestClient.get()
                .uri("/api/categories/BOOKS")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.category").isEqualTo("books");
    }

    @Test
    void formatsDatesAndRunsCustomSearchValidator() {
        webTestClient.get()
                .uri("/api/search?category=BOOKS&from=01%2F03%2F2026&to=31%2F03%2F2026")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.category").isEqualTo("books")
                .jsonPath("$.from").isEqualTo("2026-03-01")
                .jsonPath("$.to").isEqualTo("2026-03-31");
    }

    @Test
    void rejectsInvalidDateRange() {
        webTestClient.get()
                .uri("/api/search?category=books&from=31%2F03%2F2026&to=01%2F03%2F2026")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR")
                .jsonPath("$.detail").value(
                        value -> org.assertj.core.api.Assertions
                                .assertThat(value.toString())
                                .contains("to"));
    }

    @Test
    void rejectsInvalidJsonRequest() {
        webTestClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest(
                        " ",
                        BigDecimal.ZERO
                ))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");
    }

    @Test
    void readsAndWritesJsonWithConfiguredCodec() {
        webTestClient.post()
                .uri("/api/codec-echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new ProductMessage("p-1", "Keyboard"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("p-1")
                .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void rejectsInvalidMethodParameter() {
        webTestClient.get()
                .uri("/api/page?page=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_VALIDATION_ERROR");
    }
}
~~~

### 10.17. Running the Application and Tests

In the directory containing pom.xml:

~~~bash
mvn test
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

Test Converter:

~~~bash
curl -i http://localhost:8080/api/categories/BOOKS
~~~

Sample response:

~~~json
{
  "category": "books",
  "from": null,
  "to": null
}
~~~

Test Formatter and SearchCriteriaValidator:

~~~bash
curl -i "http://localhost:8080/api/search?category=BOOKS&from=01%2F03%2F2026&to=31%2F03%2F2026"
~~~

Sample response:

~~~json
{
  "category": "books",
  "from": "2026-03-01",
  "to": "2026-03-31"
}
~~~

Test Bean Validation:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":" ","price":0}'
~~~

An invalid request returns HTTP 400 with code VALIDATION_ERROR. The detail content depends on the Bean Validation provider's messages and message source configuration.

Test method validation:

~~~bash
curl -i "http://localhost:8080/api/page?page=0"
~~~

The request returns HTTP 400 with code METHOD_VALIDATION_ERROR.

## 11. Streaming, DataBuffer, and Memory Limits

Codecs do not always aggregate the entire body. With reactive streams, a Decoder can receive Flux<DataBuffer> and emit objects according to backpressure.

Key points to remember:

- bodyToMono usually needs to complete a single value; some decoders must aggregate data.
- bodyToFlux fits when the format and codec support streaming.
- application/x-ndjson and text/event-stream can emit data item by item.
- Regular JSON arrays can be decoded into a Flux of elements; buffering behavior depends on the codec and media type.
- DataBuffer may be pooled/direct memory; code manipulating buffers directly must follow retain/release rules.
- maxInMemorySize limits the data region being aggregated, and does not replace total request limits, timeouts, or upload quotas.

Do not convert a large file stream into byte[] just to use Jackson if the application can process it in chunks. For multipart, use FilePart or PartEvent as needed and manage cleanup with the proper lifecycle.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking Converter handles JSON bodies | JSON is not read through Converter | Use Decoder/HttpMessageReader |
| Using Formatter for every conversion | Type conversion logic is unnecessarily tied to formatting and Locale | Use Converter for general conversion |
| Using Converter for locale-formatted dates | No Locale available to parse/print | Use Formatter or DateTimeFormat |
| Registering a custom codec with register() only and expecting all default settings | Custom codec may not receive maxInMemorySize/logging config | Use registerWithDefaultConfig or configure manually |
| Replacing the Jackson decoder with a decoder supporting only one MIME type | application/json may no longer be supported | Keep all required MIME types or register a separate custom codec |
| Disabling registerDefaults while forgetting basic codecs | Common requests/responses cannot be read/written | Keep defaults and only add codecs when possible |
| Setting maxInMemorySize too high | Large requests can grow heap usage with concurrency | Set limits based on payloads and stream large data |
| Thinking maxInMemorySize is a total request limit | Does not protect the entire request or uploads | Use gateway/body-size policies and stream counters |
| Calling a Formatter with shared mutable state | Race conditions across requests | Use immutable DateTimeFormatter and stateless formatters |
| Using a singleton SimpleDateFormat | SimpleDateFormat is not thread-safe | Use DateTimeFormatter |
| Returning null from a Converter for invalid input | Confusing binding errors or masking bad data | Throw IllegalArgumentException with a clear message |
| Using Validator to convert types | Mixes conversion and validation | Convert first, validate object afterwards |
| Forgetting @Valid on nested objects | Child object constraints do not cascade | Annotate @Valid on fields/parameters needing cascading |
| Thinking @Valid enables method validation by itself | Constraints directly on method params do not run as expected | Place constraints like @Min directly when method validation is needed |
| Placing @Validated on the whole controller in Spring 6.1+ | Switches to AOP method validation | Remove class-level @Validated to use built-in validation |
| Handling only WebExchangeBindException | Misses method validation exceptions | Handle HandlerMethodValidationException as well |
| Exposing overly detailed validation errors to clients | Can leak internal structure | Return filtered error codes and field messages |

## 13. Configuration Design Checklist

Before deploying, verify:

1. Which Content-Types does the API accept and which media types does it return?
2. Are the default codecs on the classpath sufficient?
3. Are custom Encoders, Decoders, HttpMessageReaders, or HttpMessageWriters needed?
4. Do custom codecs receive the right buffer limits and logging policies?
5. Is maxInMemorySize appropriate for payloads and concurrency?
6. Are server codecs and WebClient codecs configured separately as needed?
7. Are there domain types in query/path/headers that need a Converter?
8. Do date/number values need a locale-aware Formatter?
9. Is the browser input type=date format ISO?
10. Does Bean Validation have its provider and starter dependency?
11. Are nested objects annotated with @Valid?
12. Do cross-field/business rules need a dedicated Spring Validator?
13. Are both WebExchangeBindException and HandlerMethodValidationException handled?
14. Does the controller avoid class-level @Validated if using built-in method validation?
15. Do tests cover codecs, conversion, formatting, object validation, and method validation?

## 14. Key Takeaways

- Codecs handle byte streams and objects via Encoder, Decoder, HttpMessageReader, and HttpMessageWriter.
- Content-Type selects the reader for requests; Accept participates in selecting the writer for responses.
- ServerCodecConfigurer configures server-side codecs; ClientCodecConfigurer configures WebClient codecs.
- WebFluxConfigurer.configureHttpMessageCodecs customizes default codecs or adds custom codecs.
- registerWithDefaultConfig lets custom codecs inherit default settings such as maxInMemorySize and logging.
- Spring Boot 3.5 uses spring.http.codecs.max-in-memory-size for the codec aggregation limit.
- Converter performs general type conversion; Formatter parses/prints by Locale.
- WebFluxConfigurer.addFormatters registers global Converters and Formatters for web binding.
- @InitBinder customizes WebDataBinder and validators per controller/model attribute.
- Bean Validation uses annotations such as @NotBlank, @Size, @Positive, and @Valid.
- Spring Validator fits rules involving multiple fields or domain-specific business logic.
- WebExchangeBindException typically represents validation of a command object; HandlerMethodValidationException represents built-in method validation.
- With Spring Framework 6.1+, avoid class-level @Validated on controllers if you want to use built-in method validation.
- Codec memory limits are not total request limits; large data needs streaming and limits at appropriate layers.

**Official Documentation:**
- [Spring Framework 6.2 — WebFlux Config: codecs, conversion, formatting and validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — Reactive Core: HTTP message readers and writers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — DataBinder and @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Boot 3.5 — Common Application Properties: spring.http.codecs](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Framework 6.2 — WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
- [Spring Framework 6.2 — Jackson2JsonDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/json/Jackson2JsonDecoder.html)
- [Spring Framework 6.2 — Jackson2JsonEncoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/json/Jackson2JsonEncoder.html)
- [Spring Framework — Formatter SPI](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
