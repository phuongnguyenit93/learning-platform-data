# Configuring Converters, Formatters, and Validators with WebFluxConfigurer

## 1. Goals and Context

Spring WebFlux is Spring Framework's reactive web stack. When an HTTP request reaches an annotated controller, the framework must **read data**, **convert data to Java types**, and **validate constraints** before invoking business logic. These three responsibilities do not belong to the same API:

- **Converter** transforms a value from a source type to a target type, such as `String -> OrderCode` or `String -> CustomerId`.
- **Formatter** parses a string into an object and prints an object to a string, typically considering `Locale` or display conventions like dates, currency, and percentages.
- **Validator** checks a bound object/value and records errors, such as `@NotNull`, `@Min`, or custom business rules.

In Spring WebFlux, the `org.springframework.web.reactive.config.WebFluxConfigurer` interface provides hooks to configure these three groups:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Register Converters and Formatters used in argument binding.
    }

    @Override
    public Validator getValidator() {
        // Select the global Validator for WebFlux.
        return null; // API skeleton only, not a complete configuration.
    }
}
```

The snippet above is an **illustrative skeleton**, not a standalone runnable program. It requires importing `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry`, `org.springframework.validation.Validator`, and `org.springframework.web.reactive.config.WebFluxConfigurer`. A complete runnable project with Java 17/Spring Boot is in section 7.

Core insight: **`WebFluxConfigurer#addFormatters` configures conversion/formatting for parameter or binding data; `getValidator` chooses the global validator. They are not the sole place controlling JSON request/response bodies.** Reading/writing bodies via HTTP message codecs is a separate mechanism.

## 2. WebFlux Processing Pipeline

For an annotated controller receiving a form or request parameter, the flow can be pictured as:

```text
HTTP request
   |
   v
WebFlux HandlerMapping + HandlerAdapter
   |
   v
Argument resolution / WebExchangeDataBinder
   |-- extract query/form/path/header
   |-- ConversionService: Converter/Formatter
   |-- binding errors: typeMismatch, ...
   |
   v
Validator triggered by @Valid / @Validated
   |-- Bean Validation constraints
   |-- Spring Validator if configured
   |
   +-- errors -> BindingResult (if immediately after @ModelAttribute)
   |          or WebExchangeBindException on the appropriate path
   v
Controller method -> return value -> HTTP response
```

For `@RequestBody` JSON, **body reading** goes through `HttpMessageReader` (Jackson JSON decoder when configured), and only then does validation run on the decoded object. Registering `String -> OrderCode` via `addFormatters` **does not automatically** make Jackson deserialize a JSON string field into `OrderCode` using that converter.

This diagram teaches the typical flow; WebFlux can accept `Mono<T>`/`Flux<T>`, with resolution and validation occurring in the corresponding reactive pipeline. Do not infer that every handler blocks and executes identically to a servlet thread.

## 3. Configuring WebFluxConfigurer Properly

### 3.1. Minimal configuration

With Spring Boot and the `spring-boot-starter-webflux` dependency:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebConfig implements WebFluxConfigurer {
    // Override only the hooks you need to customize.
}
```

Spring Boot continues to provide most auto-configuration. **There is no need to add `@EnableWebFlux`** in standard cases.

If using plain Spring Framework WebFlux directly, `@EnableWebFlux` enables default configuration. However, in a Spring Boot app, adding `@EnableWebFlux` is a **takeover** option: you may lose some of Boot's automatic WebFlux customizations. Spring docs recommend implementing `WebFluxConfigurer` without `@EnableWebFlux` when you want to retain auto-configuration.

**Interface name confusion:** `WebMvcConfigurer` is for the Spring MVC Servlet stack; `WebFluxConfigurer` is for Spring WebFlux. They are not interchangeable names for the same infrastructure.

### 3.2. Related hooks

| Hook | Purpose |
| --- | --- |
| `addFormatters(FormatterRegistry)` | Add converters, formatters, and formatter registrars for annotated-controller argument binding |
| `getValidator()` | Provide a global Spring `Validator` |
| `configureHttpMessageCodecs(ServerCodecConfigurer)` | Customize HTTP body readers/writers and certain codec settings |
| `configureContentTypeResolver(...)` | Customize how request media types are resolved |
| `addCorsMappings(...)` | Configure CORS mappings |
| `addResourceHandlers(...)` | Configure static resources |

This lesson focuses on the first three hooks and their differences. Do not override every method merely because the interface offers many callbacks.

## 4. Converter: Transforming Values from One Type to Another

Spring's Conversion SPI provides:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

This is an **illustrative signature** of `org.springframework.core.convert.converter.Converter`, not an interface you define yourself.

Suppose an application has an identifier value type:

```java
public record OrderCode(String value) {}
```

A converter can normalize input text into an order code:

```java
public class StringToOrderCode implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String raw) {
        String code = raw.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("ORD-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(code);
    }
}
```

This is a **partial snippet**; it requires importing `Converter`, `Locale`, and the `OrderCode` record. The full runnable version is in section 7.

Registering with WebFlux:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToOrderCode());
}
```

When a request has `code=ord-123` and the Java parameter/property expects `OrderCode`, the conversion service invokes the converter to create `new OrderCode("ORD-123")`.

**Rules for writing a Converter:**

- Perform only type conversion; do not query databases or execute blocking I/O.
- If the format is invalid, throw a clear exception; the binder/argument resolver converts it into the corresponding error depending on where conversion runs.
- Avoid mutating global state during conversion.
- Do not use `Converter<String,T>` to replace Jackson's JSON body deserialization.
- For `null` values, the conversion service has rules for empty sources; validators check `@NotNull` when missing values must be rejected.
- When formats vary by locale, prefer `Formatter` or a `Locale`-aware parser instead of hardcoding a contextless conversion.

### 4.1. When to use GenericConverter and ConverterFactory?

If a rule needs to support a family of target types, Spring also offers `ConverterFactory<S,R>`; if you need source/target type descriptors or complex structures, there is `GenericConverter`. For a simple, fixed type pair, `Converter<S,T>` is easier to read, test, and maintain.

## 5. Formatter: Parse, Print, and Locale

Spring's Formatting SPI defines:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {

    // Parser<T>: T parse(String text, Locale locale)
    // Printer<T>: String print(T object, Locale locale)
}
```

This is the **API shape for explanation**, not code to write anew. Unlike a one-way converter, a formatter covers both:

- `parse(text, locale)`: from user-entered text to a Java object.
- `print(object, locale)`: from an object to a display string.

Example value type `DeliveryDate` accepting input `2026/11/20`:

```java
public record DeliveryDate(LocalDate value) {}
```

Illustrative formatter:

```java
public class DeliveryDateFormatter implements Formatter<DeliveryDate> {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("uuuu/MM/dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public DeliveryDate parse(String text, Locale locale) {
        return new DeliveryDate(LocalDate.parse(text, FORMAT));
    }

    @Override
    public String print(DeliveryDate object, Locale locale) {
        return FORMAT.format(object.value());
    }
}
```

When `addFormatters(registry)` calls `registry.addFormatter(new DeliveryDateFormatter())`, WebFlux can convert `"2026/11/20"` into `DeliveryDate(LocalDate.of(2026,11,20))` and format it back according to the formatter's rules.

The formatter above uses a fixed format and ignores the `locale` parameter for separators. That is intentional for this API example. For currencies, regional numbers, or localized dates, use `locale` properly and test both `parse` and `print` directions.

### 5.1. Built-in formatters

Spring WebFlux registers many default formatters for numbers and date/time types and supports annotations:

- `@DateTimeFormat`
- `@NumberFormat`
- `@DurationFormat` (in supporting versions)

For example, if you need HTML `<input type="date">` with a fixed ISO format instead of locale-based date parsing:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
```

This is an integration config snippet requiring `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`. When adding it to real configuration, combine it with other converters/formatters inside **the same `addFormatters` method** instead of declaring multiple methods with the same signature.

### 5.2. Conversion and formatting are not JSON codecs

For example, `@RequestParam("shipOn") DeliveryDate shipOn` uses WebFlux conversion/formatting. However, `@RequestBody Mono<BookingRequest>` uses an HTTP message reader to deserialize JSON. Customizing `DeliveryDate` inside JSON typically requires Jackson serializers/deserializers, annotations, or modules; **do not treat `FormatterRegistry` as a replacement for ObjectMapper configuration**.

## 6. Validator: Checking Bound Data

### 6.1. Default behavior with Jakarta Bean Validation

When a Jakarta Bean Validation provider (usually Hibernate Validator) is on the classpath, Spring WebFlux can register `LocalValidatorFactoryBean` as the global validator for `@Valid` and `@Validated` on controller method arguments. Hence many apps only need:

```java
public class BookingForm {

    @NotNull
    private OrderCode code;

    @NotNull
    private DeliveryDate deliveryDate;

    @NotNull
    @Min(1)
    private Integer amount;

    // Constructors, getters, and setters...
}
```

If `@Valid @ModelAttribute("booking") BookingForm form` is bound, validation detects missing values or amounts below 1.

### 6.2. Which Validator should getValidator() return?

The `WebFluxConfigurer` method is:

```java
@Override
public org.springframework.validation.Validator getValidator() {
    // Return the Spring Validator to use globally.
    return configuredValidator;
}
```

**Returning a custom validator without Jakarta Bean Validation integration can replace the default validator.** In that case, annotations like `@NotNull`, `@Email`, and `@Min` on DTOs will no longer be evaluated via the global validation path unless the new validator executes Bean Validation.

A clear example to **keep Jakarta constraints** while explicitly supplying the global validator in a `@Configuration` class:

```java
@Bean
public LocalValidatorFactoryBean applicationJakartaValidator() {
    return new LocalValidatorFactoryBean();
}

@Override
public Validator getValidator() {
    return applicationJakartaValidator();
}
```

This is an **integration config snippet**: `LocalValidatorFactoryBean` is both a Spring `Validator`/`SmartValidator` and a Jakarta Bean Validation integration. With default `@Configuration` (proxy bean methods), calling `applicationJakartaValidator()` is intercepted by Spring to return the managed bean; do not blindly copy this into `@Configuration(proxyBeanMethods=false)` assuming a direct method call still returns the singleton.

**Most Spring Boot apps do not need to override `getValidator()`**; only do so when you need explicit control over the global validator/factory, message interpolation, or validation settings. The full example in section 7 intentionally uses this hook to show how the wiring works.

### 6.3. Spring Validator and SmartValidator

Spring's `org.springframework.validation.Validator` has two methods:

```java
boolean supports(Class<?> clazz);
void validate(Object target, Errors errors);
```

A custom validator inspects the object and records errors with `errors.rejectValue("field","code")` or `errors.reject("code")`. `SmartValidator` adds support for hints (such as validation groups) via `validate(target,errors,hints...)`. `LocalValidatorFactoryBean` forwards `@Validated(SomeGroup.class)` hints to the provider.

Do not assume a custom Spring `Validator` implementing only the two basic methods understands validation groups; if group branching is needed, implement `SmartValidator` or use the appropriate Bean Validation APIs directly.

### 6.4. Local validators with @InitBinder

When a rule applies to only one controller/form, keep the global validator and **add** the local rule:

```java
@InitBinder("booking")
void initBookingBinder(WebDataBinder binder) {
    binder.addValidators(bookingPolicyValidator);
}
```

This is a **controller snippet**, not standalone; it needs `WebDataBinder`, a `bookingPolicyValidator` field/bean, and `@InitBinder`. 
- `addValidators(...)` preserves already-registered validators.
- `setValidator(...)` replaces the binder's validator list, which can accidentally drop global Bean Validation.
- The validator's `supports(BookingForm.class)` must match the target type being bound.
- `@InitBinder` does not trigger validation by itself; it configures the binder. A parameter marked `@Valid` or `@Validated` triggers validation on the corresponding path.

In WebFlux, a form object **not wrapped in a reactive type** can be followed directly by `BindingResult` in the controller signature. If you declare `@ModelAttribute Mono<BookingForm>`, you cannot place a synchronous `BindingResult` right after it to handle errors; handle errors inside the reactive pipeline instead.

### 6.5. WebFlux errors and exceptions differ from MVC

For `@Valid @ModelAttribute` without an adjacent `BindingResult`, Spring WebFlux typically throws `WebExchangeBindException` on binding/validation failure; in Spring MVC on the Servlet stack, the equivalent exception is usually `MethodArgumentNotValidException`. With direct constraints on handler parameters, WebFlux 6.1+ also has a method-validation path that can raise `HandlerMethodValidationException`. Never write a WebFlux `@ControllerAdvice` that catches only Spring MVC's exception.

A form with a trailing `BindingResult` handled by the controller **does not automatically return HTTP 400**: the controller must choose the status, response body, or view. Additionally, HTTP body decode errors, missing required query parameters, and codec memory limits follow different exception paths rather than all turning into `FieldError` entries.

## 7. Runnable Java 17 / Spring Boot 3.5.6 Example: Converter + Formatter + Validator

This lab uses a WebFlux annotated controller, not Spring MVC. A request sends three properties:

- `code=ord-123`: Converter `String -> OrderCode` produces `ORD-123`.
- `deliveryDate=2026/11/20`: Formatter parses into `DeliveryDate` holding a `LocalDate`.
- `amount=2`: Bean Validation enforces `@NotNull @Min(1)`.
- `code=ORD-000`: a local Spring Validator enforces a reserved-code rule.

### 7.1. Structure

```text
webflux-conversion-validation/
├── pom.xml
└── src/main/java/demo/reactive/
    ├── ReactiveApp.java
    ├── OrderCode.java
    ├── DeliveryDate.java
    ├── BookingForm.java
    ├── WebFluxConfig.java
    ├── BookingPolicyValidator.java
    └── BookingController.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>webflux-conversion-validation</artifactId>
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
```

**Important:** do not add `spring-boot-starter-web` alongside when the goal is running a WebFlux application. In typical Boot setup, when both MVC and WebFlux are present, MVC may be chosen as the web application type. This example uses only WebFlux + Validation.

### 7.3. ReactiveApp.java

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApp.class, args);
    }
}
```

### 7.4. OrderCode.java

```java
package demo.reactive;

public record OrderCode(String value) {
}
```

`OrderCode` is a **value object**. The converter creates this object from the form parameter instead of having the controller parse raw code text.

### 7.5. DeliveryDate.java

```java
package demo.reactive;

import java.time.LocalDate;

public record DeliveryDate(LocalDate value) {
}
```

The record holds the date in an explicit Java type. The formatter is responsible for the request's textual syntax.

### 7.6. BookingForm.java

```java
package demo.reactive;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public class BookingForm {

    @NotNull
    private OrderCode code;

    @NotNull
    private DeliveryDate deliveryDate;

    @NotNull
    @Min(1)
    private Integer amount;

    public BookingForm() {
    }

    public OrderCode getCode() {
        return code;
    }

    public void setCode(OrderCode code) {
        this.code = code;
    }

    public DeliveryDate getDeliveryDate() {
        return deliveryDate;
    }

    public void setDeliveryDate(DeliveryDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public Integer getAmount() {
        return amount;
    }

    public void setAmount(Integer amount) {
        this.amount = amount;
    }
}
```

`@NotNull` forbids missing `code`, `deliveryDate`, and `amount`; `@Min(1)` forbids zero or negative `amount` once bound to `Integer`.

### 7.7. WebFluxConfig.java

```java
package demo.reactive;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
        registry.addFormatter(new DeliveryDateFormatter());
    }

    @Bean("applicationJakartaValidator")
    public LocalValidatorFactoryBean applicationJakartaValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        // @Configuration defaults to proxyBeanMethods=true:
        // Spring intercepts the call to return the managed bean.
        return applicationJakartaValidator();
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        // For body codecs; does not replace addFormatters.
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }

    private static final class StringToOrderCodeConverter
            implements Converter<String, OrderCode> {

        @Override
        public OrderCode convert(String source) {
            String normalized =
                    source.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("ORD-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid order code");
            }

            return new OrderCode(normalized);
        }
    }

    private static final class DeliveryDateFormatter
            implements Formatter<DeliveryDate> {

        private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("uuuu/MM/dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public DeliveryDate parse(String text, Locale locale) {
            return new DeliveryDate(LocalDate.parse(text, DATE));
        }

        @Override
        public String print(DeliveryDate object, Locale locale) {
            return DATE.format(object.value());
        }
    }
}
```

This is the central configuration of the example:

- `addFormatters` registers the global converter and formatter for argument binding.
- `getValidator` returns a `LocalValidatorFactoryBean` **managed as a Spring bean**, so Jakarta constraints continue working. The example intentionally overrides this hook to illustrate the API; many Spring Boot apps should stick with the default validator unless customization is needed.
- `configureHttpMessageCodecs` caps the in-memory buffer of certain HTTP body codecs at 512 KiB; it **does not** dictate `deliveryDate` formatting or `code` syntax from forms.
- `@Configuration` uses default proxy-method mode; do not switch to `proxyBeanMethods=false` while still calling `applicationJakartaValidator()` from `getValidator()`.
- `@EnableWebFlux` is omitted, preserving Spring Boot's WebFlux auto-configuration.

This is not the only way to integrate a Jakarta validator; you can also inject an existing Jakarta provider and adapt it properly. The key is that the chosen global validator still supports the DTO constraints you need.

### 7.8. BookingPolicyValidator.java

```java
package demo.reactive;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class BookingPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        if (form.getCode() != null
                && "ORD-000".equals(form.getCode().value())) {
            errors.rejectValue(
                "code", "reservedCode",
                "This order code is reserved");
        }
    }
}
```

The validator is a singleton bean without per-request mutable state. It runs after the code has been normalized by the converter. This is a form-local rule and does not affect other controllers.

### 7.9. BookingController.java

```java
package demo.reactive;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class BookingController {

    private final BookingPolicyValidator bookingPolicy;

    public BookingController(BookingPolicyValidator bookingPolicy) {
        this.bookingPolicy = bookingPolicy;
    }

    @InitBinder("booking")
    void initBookingBinder(WebDataBinder binder) {
        // Add local rule without replacing the global validator.
        binder.addValidators(bookingPolicy);
    }

    @PostMapping(
        path = "/bookings",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> create(
            @Valid @ModelAttribute("booking") BookingForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String codes = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + shortCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                    .body("INVALID|" + codes);
        }

        return ResponseEntity.ok(
                "OK|" + form.getCode().value()
                + "|" + form.getDeliveryDate().value()
                + "|" + form.getAmount());
    }

    private static String shortCode(FieldError error) {
        String[] codes = error.getCodes();
        return codes == null || codes.length == 0
                ? "unknown"
                : codes[codes.length - 1];
    }
}
```

Note three points:

1. `@InitBinder("booking")` adds the local validator for model attribute `booking`; the name must match `@ModelAttribute("booking")`.
2. `@Valid` triggers validation on the bound object; both the global validator and local validator contribute errors to `BindingResult`.
3. `BindingResult` sits **immediately after** `BookingForm` and is not wrapped in `Mono<BindingResult>`. The controller can return errors directly. Only after `hasErrors()` is false should converted values be used.

This is an **annotated WebFlux handler returning `ResponseEntity<String>` directly**—a valid return type in WebFlux. It performs no blocking I/O. With async business work such as reactive database reads, you can switch the body to `Mono<ResponseEntity<...>>` while keeping the same clean validation design.

### 7.10. Run commands and results

Requires Java 17+, Maven 3.x, and port 8080 available. In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The app uses Reactor Netty via the default WebFlux starter. In another bash/zsh/WSL terminal, send the requests.

**Case A — Converter, Formatter, and Validator all succeed:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=2'
```

HTTP **200 OK**, response body:

```text
OK|ORD-123|2026-11-20|2
```

- Converter transforms `ord-123` to `OrderCode("ORD-123")`.
- Formatter parses `2026/11/20` into `LocalDate.of(2026,11,20)`.
- Global validator accepts all three fields.
- Local validator detects no reserved code.

**Case B — Jakarta Bean Validation catches invalid amount:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=0'
```

HTTP **400 Bad Request**, body:

```text
INVALID|amount:Min
```

Code `Min` comes from global Jakarta Bean Validation. The controller explicitly returns status 400; `BindingResult` does not pick HTTP status on its own.

**Case C — Local Spring Validator catches disallowed code:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-000' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=2'
```

HTTP **400 Bad Request**, body:

```text
INVALID|code:reservedCode
```

Code `reservedCode` comes from `BookingPolicyValidator`; the global `@NotNull` rule does not replace local logic.

**Case D — Formatter fails to parse date:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/13/20' \
  --data-urlencode 'amount=2'
```

Parsing cannot turn month 13 into a `LocalDate`. With standard property binding, `BindingResult` records a `typeMismatch` error on `deliveryDate` and the controller returns HTTP 400. Expected body format in the example:

```text
INVALID|deliveryDate:typeMismatch
```

This is a **conversion/formatting error**, not an `@Min` failure or a date constraint that ran. If an app customizes message codes or binding behavior, exact error code strings may vary; the crucial part is returning a structured error and never processing `deliveryDate` as if it converted cleanly.

**Case E — Missing date property:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'amount=2'
```

Because `deliveryDate` remains `null` after binding, the global validator catches `@NotNull`; HTTP 400, body:

```text
INVALID|deliveryDate:NotNull
```

The outputs above are **HTTP response bodies**, not full Maven, Netty, or Spring Boot logs. `curl -s` also does not add a trailing newline. The program intentionally prints general error codes and sorts them to avoid depending on `FieldError` creation order.

### 7.11. What if getValidator() is removed or replaced with a non-Jakarta validator?

If you delete the `getValidator()` override while keeping the validation provider dependency and normal Boot config, the framework usually supplies a default global Bean Validation validator, so constraints still execute. **Removing the override does not disable validation.**

If you replace `getValidator()` with a Spring `Validator` that only checks `BookingForm.code` without using the provider, `@NotNull`/`@Min` can be skipped along the global binder validation path. In that case you must intentionally design a composite strategy if you want both; do not rely on Hibernate Validator merely sitting on the classpath.

## 8. How Does configureHttpMessageCodecs Differ from addFormatters?

Although the word "converter" can be misleading, WebFlux HTTP **codecs** handle byte buffers/HTTP body content, whereas Spring **ConversionService** handles typed values during argument binding.

| Scenario | Primary API / Mechanism |
| --- | --- |
| `?count=12` to `int` | ConversionService / default converters |
| `?code=ord-123` to `OrderCode` | Custom `Converter<String, OrderCode>` in `addFormatters` |
| `?deliveryDate=2026/11/20` to `DeliveryDate` | Custom `Formatter<DeliveryDate>` in `addFormatters` |
| `@Valid @ModelAttribute BookingForm` | WebExchangeDataBinder + WebFlux global/local Validator |
| `@RequestBody Mono<BookingJson>` reading JSON | `HttpMessageReader` + Jackson decoder/codec |
| `Mono<BookingResponse>` writing JSON | `HttpMessageWriter` + Jackson encoder/codec |
| Limiting in-memory bytes when decoding body | `configureHttpMessageCodecs` / `ServerCodecConfigurer` |
| Configuring JSON date serialization | Jackson serializer/deserializer/module, not plain `FormatterRegistry` |

Example configuring body memory limit:

```java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer codecs) {
    codecs.defaultCodecs().maxInMemorySize(512 * 1024);
}
```

Do not assume a 512 KiB limit caps the length of a single `@RequestParam` or every streaming payload; it governs the buffer size of certain codec decode/aggregate operations. For large uploads, design streaming, inspect specific codec settings, validate inputs, and enforce limits at the web server/gateway layer.

In Spring Boot apps, if you only need to adjust codec buffer sizes, consider Boot-supported configuration properties or customizers instead of overriding all of `WebFluxConfigurer`. Either way, do not modify the formatter registry just to fix a JSON decoder error.

## 9. Scope of Application: Controller Annotations, Reactive Types, and Functional Routes

`WebFluxConfigurer#addFormatters` serves type conversion/formatting for annotated controller method arguments and related data binding. It does not make every place in the entire system automatically invoke the same converters:

- `WebClient` reads JSON responses using its own codecs, not by applying server-side custom argument converters to individual JSON fields by default.
- Functional routes (`RouterFunction` + `HandlerFunction`) can use shared codecs for request/response bodies, yet if a handler manually pulls a `String` from query params and parses it, you must explicitly invoke `ConversionService` or an appropriate parser.
- Reactive repositories/services are not automatically validated by WebFlux's `getValidator()`. Explicit Bean Validation, service method validation, or validation inside reactive pipelines may be needed depending on architecture.
- `@ModelAttribute Mono<T>` supports reactive binding, yet synchronous `BindingResult` **cannot** sit adjacent to a reactive wrapper. Handle binding/validation errors inside `Mono`.

Do not force all business rules into `Converter` or `Formatter`. They should convert types consistently and fast; uniqueness checks in a database belong in the service/database layer, especially since controller validation cannot guarantee data stays unchanged across concurrent requests.

## 10. Customizing Validators and Multiple Checkers

If your application has multiple rule layers:

- **Global:** use `LocalValidatorFactoryBean` for Jakarta annotations.
- **Local:** use `@InitBinder("booking")` with `binder.addValidators(bookingPolicyValidator)` for a specific form.
- **Extended Validator:** implement Spring `Validator` and declare `supports(Class<?>)` accurately. For multiple fields, call `errors.rejectValue(...)` for field errors or `errors.reject(...)` for object-level errors.

Distinguishing binder APIs:

| API | Effect |
| --- | --- |
| `binder.addValidators(v1, v2)` | Keeps existing validators and appends v1, v2 |
| `binder.setValidator(v)` | Replaces the list with the single supplied validator |
| `binder.replaceValidators(v1,v2)` | Replaces the entire list with multiple validators |
| `binder.getValidators()` | Inspects the list of registered validators |

Do not write an unscoped `@InitBinder` that adds a validator supporting only `BookingForm` to binders for every class; `supports(clazz)` may mismatch and fail configuration. 
When placing `@InitBinder` in `@ControllerAdvice`, you can share rules across controllers, provided you control the selector and model attribute names. Avoid registering the same validator twice across advice and controller, which duplicates errors.

### SmartValidator, hints, and groups

`@Validated(Group.class)` can forward group/hints to `SmartValidator`. `LocalValidatorFactoryBean` understands Jakarta groups. If a custom rule implements only plain `Validator`, it does not automatically distinguish validation groups; design group awareness explicitly if needed.

**Keep behavior stable under concurrency:** Spring singleton validators/converters can be shared across concurrent requests; avoid per-request mutable fields on those classes. `DateTimeFormatter` in the example is immutable/thread-safe, suitable as `static final` on a formatter.

## 11. Common Configuration Mistakes

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| Overrode `addFormatters` yet JSON output/input unchanged | Confused conversion service with Jackson codecs | Use Jackson serializers/deserializers for JSON bodies |
| Used `WebMvcConfigurer` in a WebFlux project | Confused Servlet MVC with reactive WebFlux | Use `WebFluxConfigurer` from the right package |
| Adding `@EnableWebFlux` broke some Boot customizations | Triggered framework config takeover | Remove annotation to keep Boot auto-configuration |
| `@Min` on form does not run | Missing provider or global validator replaced by custom validator | Check starter-validation, `getValidator()`, and groups |
| `@InitBinder` does not run for target form | Model attribute name mismatch or wrong controller scope | Match `@InitBinder("booking")` with `@ModelAttribute("booking")` |
| Local validator erased global constraints | Used `setValidator(...)` instead of `addValidators(...)` | Keep global validator and append local ones |
| `Converter` failed with `typeMismatch` error | String did not match target syntax | Return 4xx from binder/argument resolver; never treat as valid |
| `Formatter` parses dates incorrectly | Format/request Locale mismatch or invalid calendar date | Test format and `Locale`; distinguish HTML ISO dates |
| `BindingResult` unusable after `Mono<Form>` | Reactive wrapper model attribute | Handle errors inside the reactive pipeline |
| Catching only `MethodArgumentNotValidException` in WebFlux | Wrongly applied MVC exception path | Handle `WebExchangeBindException` and WebFlux equivalents |
| `DataBufferLimitException` raised | Body codec memory setting too small for payload | Check `configureHttpMessageCodecs`/Boot properties and streaming |
| Another controller misses desired converter | WebFlux config not scanned or MVC running instead of WebFlux | Check application type, package scan, starters, and config classes |
| Same rule runs twice | Duplicate validator registered globally, locally, or via ControllerAdvice | Separate scopes and validator lists cleanly |

## 12. Practical Testing Strategy

Test across at least two layers:

1. **Unit tests** for `StringToOrderCodeConverter#convert` and `DeliveryDateFormatter#parse/print` with valid and invalid inputs.
2. **WebFlux integration tests** using `WebTestClient` to verify the registry actually applies to `@ModelAttribute`, validators run, and HTTP statuses match.

Cases to cover:

- `ord-123` converts to `ORD-123` as an `OrderCode` record.
- Date `2026/11/20` parses to `2026-11-20`.
- Date `2026/13/20` triggers a conversion error rather than being accepted.
- `amount=0` is rejected by `@Min(1)` from the global validator.
- Missing `amount`/`deliveryDate` is rejected by `@NotNull`.
- `ORD-000` triggers `reservedCode` from the local validator.
- A request with multiple invalid fields populates `BindingResult` with all corresponding errors.
- JSON `@RequestBody` does not automatically apply a custom `Formatter<DeliveryDate>` without Jackson config.
- Reactive form `Mono<BookingForm>` follows a different error-handling path than synchronous `BindingResult`.
- When direct method constraints exist, test the `HandlerMethodValidationException` path (WebFlux 6.1+).
- Verify invalid input never causes the controller to return success or trigger business side effects.

If choosing `WebTestClient`, you can use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `@AutoConfigureWebTestClient` with `spring-boot-starter-test`, though this is a **testing extension** beyond section 7's sample code. For pure callbacks like converters/formatters, simple Java unit tests isolate bugs quickly before testing HTTP.

## 13. Safe Implementation Principles

- **Never block the event loop:** Avoid blocking JDBC repositories, blocking network calls, large file reads, or sleeps inside `Converter`, `Formatter`, or `Validator`. When async validation is needed, build an explicit reactive workflow instead of hiding I/O inside synchronous SPIs.
- **Never let requests bind arbitrary entity properties:** Use dedicated DTOs; when using property binding, restrict allowed fields to reduce mass assignment risks.
- **Do not treat HTTP-boundary validation as authorization:** Always verify authentication, authorization, and operation permissions in the service layer.
- **Do not use formatters for business rules:** Formatters handle syntax formatting, validators handle value rules; database uniqueness or existence must be enforced with proper transactions/constraints.
- **Never expose sensitive data in errors:** `FieldError#getRejectedValue()`, raw object arguments, and stack traces can contain sensitive details; normalize error codes and safe messages.
- **Do not rely on `getFieldErrors()` ordering:** The example chain uses `sorted()`; real APIs should define a stable error response model and support localization via `MessageSource`.
- **Never configure two competing global validators without verifying:** If multiple `WebFluxConfigurer` beans return custom global validators, configuration can become ambiguous or fail. Choose one deterministic strategy and test it.
- **Never ignore locale-sensitive conversions:** Web form locales and formats can differ from a developer's machine; test valid dates, nonexistent dates, and UI re-display.

## 14. Summary

`WebFluxConfigurer` is the configuration extension point for Spring WebFlux:

- Use **`addFormatters(FormatterRegistry)`** to register `Converter`, `Formatter`, and formatter registrars for annotated-controller argument binding.
- Use **`getValidator()`** to specify a global Spring `Validator`. To keep Jakarta annotations like `@NotNull` and `@Min` active, use a Bean Validation-integrated validator, commonly `LocalValidatorFactoryBean`.
- Use **`@InitBinder(...).addValidators(...)`** to add local Spring Validators without losing the global validator.
- Use **`configureHttpMessageCodecs(ServerCodecConfigurer)`** when customizing **HTTP body** readers/writers; do not confuse this mechanism with parameter type conversion.
- In Spring Boot, implementing `@Configuration implements WebFluxConfigurer` is usually sufficient; avoid `@EnableWebFlux` unless intentionally taking over configuration.

Always test through real WebFlux requests to confirm converters, formatters, and validators fire in the right places. In reactive WebFlux, also ensure every synchronous converter and validator stays lightweight, thread-safe, and never blocks the event loop.

## References

- Spring Framework 6.2 Reference — WebFlux Config, Conversion/Formatting/Validation/Codecs: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2 Javadoc — `WebFluxConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework 6.2 Reference — WebFlux `@ModelAttribute`, `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 Reference — WebFlux controller arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.2 Reference — WebFlux validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 Reference — Spring type conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 Reference — Spring field formatting: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2 Javadoc — `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Boot reference — Reactive web applications: https://docs.spring.io/spring-boot/reference/web/reactive.html