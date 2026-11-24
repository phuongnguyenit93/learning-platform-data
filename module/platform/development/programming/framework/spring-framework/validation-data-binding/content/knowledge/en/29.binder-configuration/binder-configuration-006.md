# `WebMvcConfigurer.addFormatters` and `getValidator` — Binder Configuration in Spring MVC

## Lesson Objectives

In Spring MVC, users submit string-based data through forms or query strings, while controllers want strongly typed Java objects such as `LocalDate`, `BigDecimal`, enums, domain identifiers, or form DTOs. To go from raw strings to objects and determine whether those objects are valid, Spring uses two **distinct yet typically sequential** mechanisms:

1. **Conversion / formatting:** transforms source data into the target Java type and supports printing back to a string. The `WebMvcConfigurer.addFormatters(FormatterRegistry)` hook registers `Converter`, `Formatter`, and formatting registrars for Spring MVC.
2. **Validation:** checks rules on the bound object such as `@NotNull`, `@NotBlank`, `@Min`, Jakarta Bean Validation constraints, and configured Spring `Validator`s. The `WebMvcConfigurer.getValidator()` hook selects the **global Validator** used by the MVC infrastructure in scenarios like `@Valid @ModelAttribute` and `@Valid @RequestBody`.

**A formatter is not a validator.** A formatter knows that `"bk-a12"` can become `BookingCode("BK-A12")`; a validator knows that `contactName` cannot be blank, `seats` must be positive, and whether `code` is required.

After this lesson, you will be able to:

- Distinguish `addFormatters(...)`, `getValidator()`, `@InitBinder`, and `@Valid`/`@Validated`.
- Understand the lifecycle of `WebDataBinder`, `FormattingConversionService`, `BindingResult`, and `FieldError`.
- Choose appropriately among `Converter<S,T>`, `Formatter<T>`, `FormatterRegistrar`, and `AnnotationFormatterFactory<A>`.
- Preserve Bean Validation when replacing the global validator with `LocalValidatorFactoryBean`.
- Build a Spring Boot 3 / Java 17+ application with a custom `Formatter<BookingCode>`, `WebMvcConfigurer`, form controller, Thymeleaf, and MockMvc tests.
- Avoid confusing MVC binding with JSON/Jackson, Spring Boot conversion services, WebFlux, and AOP method validation.

## 1. The Big Picture: Binding Differs from Validation

Suppose a form submits:

~~~http
POST /reservations
Content-Type: application/x-www-form-urlencoded

code=bk-a12&contactName=Lan&seats=3
~~~

Server-side DTO:

~~~java
public class ReservationForm {
    private BookingCode code;
    private String contactName;
    private Integer seats;

    // getters and setters
}
~~~

Spring MVC cannot directly assign the string `"bk-a12"` to field `BookingCode code` without an appropriate conversion rule. `addFormatters` supplies that rule.

A typical logical sequence:

~~~text
HTTP request parameters / form fields
    |
    v
@ModelAttribute("reservationForm")
    |
    v
WebDataBinder
    |-- constructor/property binding
    |-- FormattingConversionService
    |     |-- Converter / Formatter / @DateTimeFormat...
    |     '-- "bk-a12" -> BookingCode("BK-A12")
    |
    |-- conversion error -> FieldError, typeMismatch
    |
    v
@Valid / @Validated on controller argument
    |
    v
global Validator (getValidator() or default)
    |-- @NotNull(code)
    |-- @NotBlank(contactName)
    '-- @Min(1)(seats)
    |
    v
BindingResult
    |-- errors -> controller returns form, th:errors
    '-- valid -> service / redirect
~~~

Two error branches to distinguish:

| Input | Conversion | Validation | Typical Error |
| --- | --- | --- | --- |
| `code=bk-a12` | Formatter creates `BookingCode("BK-A12")` | `@NotNull` passes | No error |
| `code=WRONG` | Formatter fails to parse | Property remains `null` and may also be checked | `typeMismatch` on `code` |
| `contactName=` | String binds normally | `@NotBlank` fails | `NotBlank` |
| `seats=0` | String converts to `Integer` 0 | `@Min(1)` fails | `Min` |
| `seats=abc` | Fails to convert to `Integer` | Raw value cannot be assigned to `Integer` field | `typeMismatch` |
| `code` completely omitted | Property stays `null` | `@NotNull` fails | `NotNull` |

Do **not** expect `@Valid` to coerce invalid types or turn `"WRONG"` into a valid code. Conversely, even if a formatter parses a string successfully, the object can still violate other constraints.

## 2. What Is `WebMvcConfigurer`?

`org.springframework.web.servlet.config.annotation.WebMvcConfigurer` is Spring MVC's configuration interface with **default methods**. In a Spring Boot MVC app, you typically write a `@Configuration implements WebMvcConfigurer` class to customize parts of the default mechanism instead of replacing the entire MVC infrastructure.

Skeleton example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.validation.Validator;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Register additional converters / formatters.
    }

    @Override
    public Validator getValidator() {
        // Return the validator MVC should use.
        return null; // Keep the default validator.
    }
}
~~~

This is an **API explanation snippet**, not a standalone application. The two methods have completely different parameter types, return types, and scopes:

| Hook | Input/Output | Role | When Needed |
| --- | --- | --- | --- |
| `addFormatters(FormatterRegistry)` | Takes registry, returns `void` | Adds conversion/formatting strategies | Custom domain types, input/output formats, shared formatters |
| `getValidator()` | Returns Spring `Validator` or `null` | Selects the global MVC `Validator` | When replacing or explicitly choosing the global validator |
| `@InitBinder` | Takes `WebDataBinder` | Customizes binder per controller/model attribute | Allowed fields, per-form validators, local custom editors |
| `@Valid` / `@Validated` | Placed on arguments or bean properties | Requests validation and selects groups | Checking object contents after binding |

Distinguish **configuration registration** from **per-request processing**: Spring calls `addFormatters(...)` when setting up the MVC conversion service. It is not a callback invoked once per field or request. Similarly, `getValidator()` selects the validator for the infrastructure, not a function where you read or validate request data directly inside the method.

### Avoid Enabling `@EnableWebMvc` Just to Add a Formatter

In Spring Boot:

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {
    // Customize what you need.
}
~~~

This is normally sufficient. `@EnableWebMvc` hands full control of MVC configuration back to the application and can disable many Spring Boot auto-configurations (static resources, converters, view configuration, etc.). Never add `@EnableWebMvc` solely to implement `addFormatters` or `getValidator`.

Only if a project intentionally wants complete control over Spring MVC should you evaluate `@EnableWebMvc` or extending `WebMvcConfigurationSupport`, along with the responsibility for configuring the infrastructure yourself.

## 3. `addFormatters`: When to Use `Converter` vs. `Formatter`?

`FormatterRegistry` extends Spring's `ConverterRegistry`, allowing you to register multiple kinds of strategies.

### 3.1. `Converter<S,T>` — One-Way Conversion

`Converter<String, BookingCode>` is appropriate for a simple transformation from a string into a custom domain type:

~~~java
public final class BookingCodeConverter
        implements org.springframework.core.convert.converter
                .Converter<String, BookingCode> {

    @Override
    public BookingCode convert(String source) {
        return new BookingCode(source.trim().toUpperCase(
                java.util.Locale.ROOT));
    }
}
~~~

This is an **illustrative snippet**, meaningful only alongside a `BookingCode` definition and requiring syntax validation for production use. Registration:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new BookingCodeConverter());
}
~~~

A `Converter<S,T>` defines only **S → T**. If views need `BookingCode → String` for display, you may also need the reverse converter or a `Formatter<T>` to support both `parse` and `print`.

### 3.2. `Formatter<T>` — Parse and Print, with `Locale` Support

`org.springframework.format.Formatter<T>` has two operations:

~~~java
public interface Formatter<T> {
    T parse(String text, Locale locale)
            throws ParseException;

    String print(T object, Locale locale);
}
~~~

This is an **abbreviated form** of the API; import `java.util.Locale` and `java.text.ParseException` when implementing it. `Formatter<T>` makes forms bidirectional:

~~~text
HTTP "bk-a12"
    -> parse(...)
    -> BookingCode("BK-A12")
    -> DTO

BookingCode("BK-A12")
    -> print(...)
    -> HTML field value "BK-A12"
~~~

`locale` is useful for types such as currency, dates, and numbers. For instance, a Vietnamese locale may use different numeric separators than an English locale. Identifiers are usually locale-independent, so the demo normalizes characters with `Locale.ROOT`.

### 3.3. `GenericConverter` and `ConditionalGenericConverter`

When a conversion rule depends on source/target type metadata or covers multiple type pairs, use `GenericConverter`. For dynamic conditions, `ConditionalGenericConverter` activates only on matching type pairs.

Do not use `GenericConverter` for simple transformations already clearly expressed by `Converter<String,T>`. More complex APIs require testing source types, target types, and converter ordering.

### 3.4. `FormatterRegistrar` and `AnnotationFormatterFactory`

When registering a related group of formatters, use `FormatterRegistrar`:

~~~java
public class DateFormattingRegistration
        implements org.springframework.format.FormatterRegistrar {

    @Override
    public void registerFormatters(
            org.springframework.format.FormatterRegistry registry) {
        // Register related formatters.
    }
}
~~~

This is only an SPI snippet; it lacks standalone logic. `AnnotationFormatterFactory<A>` fits when formatting is triggered by an annotation on a property (such as `@DateTimeFormat` and `@NumberFormat`), rather than uniformly by Java type. Choosing the right abstraction avoids applying an unsuitable format to every field of that type.

## 4. Where Does `FormatterRegistry` Apply?

`addFormatters(...)` in `WebMvcConfigurer` adds converters/formatters to **Spring MVC's shared `FormattingConversionService`**, affecting conversions for annotated controllers such as:

- `@RequestParam BookingCode code` from query `?code=bk-a12`.
- `@PathVariable BookingCode code` where supported by the MVC conversion service.
- `@ModelAttribute ReservationForm form` with a `BookingCode code` field.
- Rendering fields back via Spring form binding / Thymeleaf `th:field`.
- Other MVC conversions on controller arguments per their argument resolvers.

**Do not over-generalize across the entire framework:**

- JSON `@RequestBody` is typically deserialized by Jackson via `HttpMessageConverter`. An MVC `Formatter<BookingCode>` **does not automatically become a Jackson deserializer**.
- Spring Data JPA, R2DBC, `@ConfigurationProperties`, and service methods may use different conversion services that do not see formatters in `mvcConversionService`.
- Spring WebFlux uses `WebFluxConfigurer` for reactive web configuration, not `WebMvcConfigurer`.
- Formatters do not determine validation groups, do not generate `@NotBlank` errors, and do not replace `@Valid`.

### Built-in Default Formatters and Annotations

Spring MVC already supports many numeric, date, and time types along with annotations such as:

~~~java
@org.springframework.format.annotation.DateTimeFormat(
        iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
private java.time.LocalDate startDate;

@org.springframework.format.annotation.NumberFormat(
        pattern = "#,##0.00")
private java.math.BigDecimal amount;
~~~

This is a DTO field snippet, not a standalone class. Usually **you do not need to register a custom formatter** for every `LocalDate` or `BigDecimal`. When you want global format control, use a registrar/formatter; when a single property needs an exception, an annotation is often clearer.

Note: Spring may use the request's locale when parsing/printing. Conversely, browser `<input type="date">` elements require values in standard HTML format—typically `yyyy-MM-dd`—regardless of the user's display locale. Do not write a slash-delimited date formatter and expect `input type="date"` to understand it.

## 5. `getValidator`: Choosing the Global Validator

The second hook:

~~~java
@Override
public org.springframework.validation.Validator getValidator() {
    return null;
}
~~~

Per the `WebMvcConfigurer` contract, **returning `null` means no custom Validator is provided**, letting the default mechanism select the validator. When a Jakarta Bean Validation provider is present (such as Hibernate Validator), Spring MVC typically uses an adapter/factory validator capable of processing `jakarta.validation.constraints.*` annotations.

`getValidator()` has return type **`org.springframework.validation.Validator`**, not `jakarta.validation.Validator`. These are two different APIs:

| Component | Type | Typical Methods |
| --- | --- | --- |
| Spring Validator | `org.springframework.validation.Validator` | `supports(Class<?>)`, `validate(Object, Errors)` |
| Spring SmartValidator | `org.springframework.validation.SmartValidator` | `validate(Object, Errors, Object... hints)` |
| Jakarta Validator | `jakarta.validation.Validator` | `validate(T, Class<?>... groups)`, `forExecutables()` |
| LocalValidatorFactoryBean | Spring/Jakarta Adapter | Usable as both Spring `Validator` and Jakarta `Validator` |

`LocalValidatorFactoryBean` is the crucial bridge. It initializes the Jakarta Validation provider while implementing Spring's `Validator`/`SmartValidator` APIs so Spring MVC can run `@Valid`/`@Validated`. When Spring manages it as a bean, initialization and shutdown lifecycles are handled by the framework.

### 5.1. Why Returning a Hand-Written Spring Validator Can Break `@NotBlank`

An example **not to do carelessly**:

~~~java
@Override
public Validator getValidator() {
    return new MyOnlyCustomValidator();
}
~~~

If `MyOnlyCustomValidator` checks only one form type with `supports(ReservationForm.class)` and only calls `errors.rejectValue(...)` for custom rules, returning it as the **global MVC validator** can replace the default Jakarta validator. `@NotBlank`/`@Email`/`@Min` constraints on other forms will stop being validated through the provider as before.

This is an anti-pattern snippet assuming a custom class exists. When adding a rule for **one form**, prefer:

- A custom Jakarta `@Constraint` + `ConstraintValidator` so the rule participates in Bean Validation.
- `@InitBinder` + `binder.addValidators(...)` to add a Spring Validator scoped to a controller/attribute.
- A properly configured `LocalValidatorFactoryBean` as the global validator if you must customize the Jakarta provider strategy, message interpolator, or global settings.

Only override `getValidator()` when you fully understand its impact on other controllers.

### 5.2. Combining with `@Valid` and `@Validated`

~~~java
@PostMapping("/reservations")
String create(
        @Valid @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "reservation-form";
    }
    return "redirect:/reservations/success";
}
~~~

`@Valid` on the form causes MVC to invoke the configured validator after binding and record errors into `BindingResult`, if declared. `@Validated(Group.class)` also lets you pick validation groups on the argument. With `LocalValidatorFactoryBean`, Jakarta constraints honor groups like `Default` and marker interfaces.

`BindingResult` **must appear immediately after** the `@ModelAttribute` parameter it describes. Without a properly positioned `BindingResult`, Spring MVC may throw `MethodArgumentNotValidException` when argument validation fails; with Spring 6.1+ native method validation triggered by direct constraints on handler methods, you may see `HandlerMethodValidationException`. Do not confuse configuring the global validator with AOP method validation on services.

### 5.3. One Global Validator, Multiple Configurers

An application can have multiple classes implementing `WebMvcConfigurer`. Registering formatters via `addFormatters(...)` additively contributes converters/formatters to the registry. For `getValidator()`, however, multiple configurers returning **non-null** validators do not automatically compose. Standardize on a single global validator and avoid conflicting configs; attach additional rules at appropriate hooks instead of having each module return its own global validator.

## 6. Runnable Example: Spring Boot 3.5.7, Java 17, MVC + Thymeleaf

We build a reservation page with three fields:

- `code` is a `BookingCode`, not a `String`. The user types `bk-a12`, and the formatter produces `BookingCode("BK-A12")`.
- `contactName` is a `String` with `@NotBlank`.
- `seats` is an `Integer` with `@NotNull` and `@Min(1)`.

The application configures **both hooks**: `addFormatters` and `getValidator`. `getValidator` returns the Spring-managed singleton `LocalValidatorFactoryBean` so Jakarta Bean Validation is preserved. The controller uses `@InitBinder` to allowlist bindable fields.

### 6.1. Directory Structure

~~~text
mvc-formatter-validator/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvc/
    │   │   ├── Application.java
    │   │   ├── BookingCode.java
    │   │   ├── BookingCodeFormatter.java
    │   │   ├── ReservationForm.java
    │   │   ├── ValidationBeans.java
    │   │   ├── MvcSettings.java
    │   │   └── ReservationController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/reservation-form.html
    └── test/
        └── java/com/example/mvc/
            └── ReservationControllerTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-formatter-validator</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

This is a **Servlet/MVC** application, not WebFlux. `spring-boot-starter-web` provides Spring MVC; `spring-boot-starter-validation` provides the Jakarta Validation provider; `spring-boot-starter-thymeleaf` renders the HTML form; the test starter supports JUnit 5 and MockMvc.

The Spring Boot version in the example is pinned for reproducibility. In production code, follow your project's BOM/patch version security policy.

### 6.3. `Application.java`

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 6.4. `BookingCode.java` — Java 17 Value Object

~~~java
package com.example.mvc;

public record BookingCode(String value) {
}
~~~

This is an immutable record. Rather than having the controller accept a raw `String` for `code`, using a dedicated type demonstrates why a formatter is needed. The record does not enforce syntax itself; form parsing rules live in `BookingCodeFormatter`.

### 6.5. `BookingCodeFormatter.java` — Bidirectional Parse/Print

~~~java
package com.example.mvc;

import org.springframework.format.Formatter;

import java.text.ParseException;
import java.util.Locale;
import java.util.regex.Pattern;

public final class BookingCodeFormatter
        implements Formatter<BookingCode> {

    private static final Pattern CODE =
            Pattern.compile("BK-[A-Z0-9]{3,8}");

    @Override
    public BookingCode parse(String text, Locale locale)
            throws ParseException {

        String canonical = text.trim()
                .toUpperCase(Locale.ROOT);

        if (!CODE.matcher(canonical).matches()) {
            throw new ParseException(
                    "Booking code must match BK-XXX", 0);
        }

        return new BookingCode(canonical);
    }

    @Override
    public String print(BookingCode object, Locale locale) {
        return object.value();
    }
}
~~~

Demo rules:

- `"bk-a12"` → trim, uppercase → `"BK-A12"` → valid record.
- `" BK-123 "` → `"BK-123"`.
- `"WRONG"`, `"BK-1"`, or `"BK-AB_12"` → `ParseException`; Spring's binder records a type-conversion error on the field.
- `print(new BookingCode("BK-A12"), locale)` → `"BK-A12"` for view rendering.

`Locale.ROOT` prevents locale-dependent case conversions when normalizing identifiers. The `Locale locale` parameter of `Formatter` is still required by the interface signature even though this business code rule does not use it.

**Important separation of responsibility:** the pattern in the formatter decides whether a string **can form a `BookingCode`**; the `@NotNull` constraint on `code` checks whether a code is present. If a business rule such as "has this code already been issued?" requires database/I/O access, enforce it in a service rather than calling the database inside a formatter.

### 6.6. `ReservationForm.java` — Jakarta Constraints

~~~java
package com.example.mvc;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ReservationForm {

    @NotNull
    private BookingCode code;

    @NotBlank
    private String contactName;

    @NotNull
    @Min(1)
    private Integer seats;

    public BookingCode getCode() {
        return code;
    }

    public void setCode(BookingCode code) {
        this.code = code;
    }

    public String getContactName() {
        return contactName;
    }

    public void setContactName(String contactName) {
        this.contactName = contactName;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }
}
~~~

`@NotNull` and `@Min` are **validation** constraints, not converters. In this example, Bean Validation does not need `@Valid` on `BookingCode` because the `BookingCode` record has no internal constraints to cascade into. If constraints are later added to fields inside the record and you want validation via `ReservationForm.code`, consider `@Valid` on that edge or an appropriate custom class-level constraint.

### 6.7. `ValidationBeans.java` — Spring-Managed Validator

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationBeans {

    @Bean("appValidator")
    @Primary
    public LocalValidatorFactoryBean appValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

`LocalValidatorFactoryBean` is a Spring-managed singleton. Spring runs lifecycle initialization (including setting up the Jakarta provider) during bean initialization, so you do not call `afterPropertiesSet()` manually on every request. `@Primary` clarifies precedence when multiple validator candidates of the same type exist.

When this bean is present, Spring Boot's validation auto-configuration may **back off** from creating another default Jakarta Validator. `MvcSettings.getValidator()` below returns this exact managed instance instead of creating a new factory per call.

### 6.8. `MvcSettings.java` — Both `addFormatters` and `getValidator`

~~~java
package com.example.mvc;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcSettings implements WebMvcConfigurer {

    private final LocalValidatorFactoryBean appValidator;

    public MvcSettings(
            @Qualifier("appValidator")
            LocalValidatorFactoryBean appValidator) {
        this.appValidator = appValidator;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new BookingCodeFormatter());
    }

    @Override
    public Validator getValidator() {
        return appValidator;
    }
}
~~~

This is the core of the lesson:

- `addFormatters(...)` adds the parser/printer for `BookingCode` to the MVC conversion service. One `Formatter` class can be reused across many controllers and form fields of that type.
- `getValidator()` returns the **Spring Validator** that MVC uses; `LocalValidatorFactoryBean` implements this API while still supporting Jakarta annotations.
- Because Spring manages the validator bean, the provider/factory is initialized once, avoiding repeated instantiation.
- No `@EnableWebMvc`: Spring Boot continues managing its MVC auto-configuration.
- Both hooks operate globally in the **MVC infrastructure**, unlike single-form customization via `@InitBinder`.

In a simple Boot application, **overriding only `addFormatters` and leaving `getValidator` at its default is sufficient** when a Bean Validation provider is present. This example intentionally overrides `getValidator` to show how to configure a global validator safely when customization is required.

### 6.9. `ReservationController.java` — Binder and Validation

~~~java
package com.example.mvc;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class ReservationController {

    @InitBinder("reservationForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "code", "contactName", "seats");
    }

    @GetMapping("/reservations/new")
    public String newForm(Model model) {
        model.addAttribute(
                "reservationForm", new ReservationForm());
        return "reservation-form";
    }

    @PostMapping("/reservations")
    public String create(
            @Valid @ModelAttribute("reservationForm")
            ReservationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "reservation-form";
        }

        // If valid, invoke business service if applicable.
        return "redirect:/reservations/success";
    }

    @GetMapping("/reservations/success")
    @ResponseBody
    public String success() {
        return "Accepted";
    }
}
~~~

Explanation:

1. Spring receives form fields and uses the formatter to convert `code` from `String` to `BookingCode`.
2. `@Valid` triggers the global validator—here `LocalValidatorFactoryBean` from `getValidator()`.
3. `BindingResult` right after the form holds all errors from both conversion and validation, avoiding separate exceptions in this HTML form flow.
4. If errors exist, returning `reservation-form` **within the same request** lets the user see their entered values.
5. If valid, the handler redirects to an endpoint returning `Accepted`. The demo does not write to a database.
6. `@InitBinder("reservationForm")` allows only three properties to bind. This is a mass-assignment protection policy, not an extra constraint.

`setAllowedFields(...)` in the controller is only local configuration for the matching binder; it does not "register a global converter." With multiple forms, each form can have its own allowlist while still sharing `BookingCodeFormatter`.

### 6.10. `templates/reservation-form.html` — Using `th:field`

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Reservation</title>
    <style>
        .error { color: #b00020; }
        .invalid { border: 1px solid #b00020; }
    </style>
</head>
<body>
<h1>Reservation</h1>

<form th:action="@{/reservations}"
      th:object="${reservationForm}"
      method="post">

    <div>
        <label for="code">Booking code</label>
        <input type="text"
               th:field="*{code}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('code')}"
           th:errors="*{code}"></p>
    </div>

    <div>
        <label for="contactName">Contact name</label>
        <input type="text"
               th:field="*{contactName}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('contactName')}"
           th:errors="*{contactName}"></p>
    </div>

    <div>
        <label for="seats">Seats</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{seats}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('seats')}"
           th:errors="*{seats}"></p>
    </div>

    <button type="submit">Reserve</button>
</form>
</body>
</html>
~~~

`th:object="${reservationForm}"` must match the name in `@ModelAttribute("reservationForm")`. `th:field="*{code}"` integrates with Spring binding status, so when the bean holds a valid `BookingCode`, the MVC formatter prints it back as a `String`. When parsing fails, `BindingResult` provides the **rejected value** so the user still sees the invalid text they typed. `th:errors` renders the corresponding field error.

Use `th:field` rather than calling `form.getCode().toString()`: default `record.toString()` produces `BookingCode[value=BK-A12]` rather than the format the form should display. The formatter's `print` method defines the UI-friendly representation.

### 6.11. `application.properties` and Running the Application

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

Disabling the template cache here is just to make HTML edits easier while learning. Run:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/reservations/new`. Scenarios:

- `code=bk-a12`, `contactName=Lan`, `seats=3`: formatter normalizes to `BK-A12`; Bean Validation passes; controller redirects **HTTP 302** to `/reservations/success`.
- `code=WRONG`, `contactName=Lan`, `seats=3`: formatter fails to parse; controller renders the form view with a `FieldError` on `code` and preserves the entered input.
- `code=bk-a12`, `contactName=`, `seats=3`: formatter **succeeds**, but `@NotBlank` creates an error on `contactName`.
- `code=bk-a12`, `contactName=Lan`, `seats=0`: numeric value binds, `@Min(1)` fails.
- `code=bk-a12`, `contactName=Lan`, `seats=abc`: `Integer` conversion fails, causing `typeMismatch`.
- `code` omitted: `@NotNull` reports an error because the field is absent.

These are the behaviors expected from the code; the default text rendered by `th:errors` varies by locale/message bundle, so do not rely on a specific unconfigured English/Vietnamese error string.

## 7. Testing with MockMvc

Create `src/test/java/com/example/mvc/ReservationControllerTest.java`:

~~~java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.ModelAndView;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReservationControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    @Qualifier("appValidator")
    LocalValidatorFactoryBean appValidator;

    @Autowired
    @Qualifier("mvcValidator")
    Validator mvcValidator;

    @Autowired
    @Qualifier("mvcConversionService")
    FormattingConversionService conversionService;

    @Test
    void globalMvcValidatorIsConfiguredBean() {
        assertSame(appValidator, mvcValidator);
    }

    @Test
    void formatterParsesAndPrints() {
        BookingCode code =
                conversionService.convert(
                        "bk-a12", BookingCode.class);

        assertNotNull(code);
        assertEquals("BK-A12", code.value());

        String display =
                conversionService.convert(code, String.class);

        assertEquals("BK-A12", display);
    }

    @Test
    void getFormHasBackingObject() throws Exception {
        mvc.perform(get("/reservations/new"))
                .andExpect(status().isOk())
                .andExpect(view().name("reservation-form"))
                .andExpect(model().attributeExists(
                        "reservationForm"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/reservations/success"));
    }

    @Test
    void formatterFailureRetainsRejectedText()
            throws Exception {

        var action = mvc.perform(post("/reservations")
                        .param("code", "WRONG")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(view().name("reservation-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "code"))
                .andReturn();

        ModelAndView mav = action.getModelAndView();
        assertNotNull(mav);

        BindingResult errors = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "reservationForm");

        assertNotNull(errors);

        FieldError conversionError =
                errors.getFieldErrors("code").stream()
                        .filter(FieldError::isBindingFailure)
                        .findFirst()
                        .orElseThrow();

        assertEquals("typeMismatch",
                conversionError.getCode());

        assertEquals("WRONG",
                conversionError.getRejectedValue());

        assertEquals("WRONG",
                errors.getFieldValue("code"));
    }

    @Test
    void jakartaConstraintsStillRunWithCustomGlobalValidator()
            throws Exception {

        mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "")
                        .param("seats", "0"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm",
                        "contactName", "seats"));
    }

    @Test
    void codeNormalizesEvenWhenOtherFieldIsInvalid()
            throws Exception {

        var action = mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "contactName"))
                .andReturn();

        ModelAndView mav = action.getModelAndView();
        assertNotNull(mav);

        ReservationForm form = (ReservationForm)
                mav.getModel().get("reservationForm");

        assertNotNull(form);
        assertNotNull(form.getCode());
        assertEquals("BK-A12", form.getCode().value());
    }

    @Test
    void absentCodeFailsNotNullConstraint() throws Exception {
        mvc.perform(post("/reservations")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "code"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The **eight tests** serve distinct purposes:

1. `globalMvcValidatorIsConfiguredBean` confirms `getValidator()` returns the chosen validator bean, not an unexpected object.
2. `formatterParsesAndPrints` tests bidirectional conversion and canonical formatting.
3. `getFormHasBackingObject` verifies the GET view has the proper form model.
4. `validFormRedirects` checks a valid POST.
5. `formatterFailureRetainsRejectedText` checks `FieldError.isBindingFailure()`, `typeMismatch`, and the rejected input.
6. `jakartaConstraintsStillRunWithCustomGlobalValidator` proves choosing a global validator did not drop `@NotBlank`/`@Min`.
7. `codeNormalizesEvenWhenOtherFieldIsInvalid` proves conversion succeeds independently of constraints on other fields.
8. `absentCodeFailsNotNullConstraint` shows missing input differs from a parse failure.

Do not rely on the iteration order of constraint violations. For fields that may have multiple errors, find the `FieldError` using `isBindingFailure()` rather than assuming `getFieldError()` is the only error.

If you add Spring Security later, `MockMvc` POST tests may need a CSRF token and proper authentication. An HTTP 403 from CSRF happens **before** form binding, not from the formatter or Bean Validation.

### Explaining `@Qualifier` Beans in Tests

`mvcConversionService` and `mvcValidator` are infrastructure bean names commonly created by Spring MVC configuration. `@Qualifier` in the test explicitly selects the exact MVC beans rather than accidentally injecting another conversion service or validator in the application.

Across Spring Boot/Spring Framework versions, bean wiring and auto-configuration may vary; verify your actual application context before turning tests that rely on internal bean names into system-wide public contracts.

## 8. When Do You Not Need to Override `getValidator`?

Many applications only need:

~~~java
@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new BookingCodeFormatter());
    }
}
~~~

This snippet replaces `MvcSettings`, assuming `BookingCodeFormatter` exists. If Spring Boot already provides a Jakarta Validation provider and a suitable global `LocalValidatorFactoryBean`, **you do not need to define `ValidationBeans` or override `getValidator()`**. That is usually simpler and easier to maintain.

Rule of thumb:

- **To add a formatter:** override `addFormatters`.
- **To keep default Bean Validation:** do not override `getValidator` unnecessarily, or return `null`.
- **To change how Jakarta Validation behaves globally:** configure a `LocalValidatorFactoryBean`/provider explicitly and return that instance.
- **To add a custom rule for one controller/form:** use `@InitBinder(...).addValidators(...)` or a custom Jakarta constraint.
- **To restrict bindable properties:** use dedicated DTOs and `WebDataBinder.setAllowedFields(...)`.
- **To customize error messages:** configure `MessageSource`, `MessageCodesResolver`, or constraint message templates; do not use formatters to craft UI exception text.

## 9. Global Validator vs. Local Validator

### 9.1. Custom Spring `Validator`

Spring provides the interface:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

This is an abbreviated API reference; do not redefine the interface in your application. A custom validator can record property errors:

~~~java
if (form.getContactName() != null
        && form.getContactName().equalsIgnoreCase("system")) {
    errors.rejectValue(
            "contactName",
            "contactName.reserved",
            "This name cannot be used");
}
~~~

This snippet assumes `form` and `errors` are inside an appropriate `validate(...)` method. A custom validator should be pure data logic, free of side effects and unnecessary blocking I/O.

### 9.2. `addValidators` Instead of `setValidator`

If a controller has a custom validator for `ReservationForm`:

~~~java
@InitBinder("reservationForm")
void addRules(WebDataBinder binder) {
    binder.addValidators(customReservationValidator);
}
~~~

This snippet requires an injected `customReservationValidator` implementing `org.springframework.validation.Validator`. `addValidators(...)` **appends** the validator to the list, whereas `setValidator(...)` **replaces** the validator configured on the binder. When you want to keep Jakarta Bean Validation and add a local rule, `addValidators` is usually the safer choice.

Always check `supports(clazz)` so a specialized validator applies only to the right target type. Do not attach a validator that supports only `ReservationForm` to all controller attributes and ignore runtime errors when the target differs.

### 9.3. Validation Groups

Jakarta Validation has the default group `Default`. Spring's `@Validated(Group.class)` on an argument can select custom groups:

~~~java
@PostMapping("/reservations/final")
String finalSubmit(
        @Validated({Default.class, FinalSubmit.class})
        @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {
    // ...
}
~~~

This is a snippet requiring imports for `jakarta.validation.groups.Default`, `org.springframework.validation.annotation.Validated`, and a `FinalSubmit` marker interface. Using `@Validated(FinalSubmit.class)` alone skips constraints in `Default`; if both are required, list both as shown.

`LocalValidatorFactoryBean` forwards validation hints/groups from Spring MVC to the Jakarta provider. A custom Spring `Validator` implementing only `Validator.validate(Object, Errors)` does not inherently understand Jakarta groups the way `SmartValidator` does.

## 10. Ensuring Errors Are Displayed and Debuggable

### 10.1. `BindingResult` and Rejected Values

When `BookingCodeFormatter.parse("WRONG", ...)` fails, the Java field `ReservationForm.code` may remain `null`. Yet `BindingResult` holds a `FieldError` capturing the failed input:

~~~java
FieldError error = errors.getFieldErrors("code")
        .stream()
        .filter(FieldError::isBindingFailure)
        .findFirst()
        .orElseThrow();

Object rawInput = error.getRejectedValue();
Object displayInput = errors.getFieldValue("code");
~~~

This snippet assumes `errors` already exists; it is not a standalone class. Both values here can be the string `"WRONG"`. `th:field="*{code}"` redisplays the input using Spring's binding status; reading `form.getCode()` directly would lose the invalid input.

When `code` parses into a `BookingCode` while `contactName` is invalid, `code` has no `FieldError`; the view uses the formatter's `print` method to redisplay the canonical form `"BK-A12"`.

### 10.2. Message Codes and Localization

Spring generates field error codes at multiple specificity levels. For example:

~~~text
typeMismatch.reservationForm.code
typeMismatch.code
typeMismatch.com.example.mvc.BookingCode
typeMismatch
~~~

These are **illustrative code patterns**, not a guarantee of every exact code across all message resolvers, Spring versions, or configurations. Inspect `FieldError.getCodes()` at runtime when defining resource-bundle keys.

You can define `src/main/resources/messages.properties`:

~~~properties
typeMismatch.reservationForm.code=Code must match BK-XXX
NotNull.reservationForm.code=Please enter a booking code
NotBlank.reservationForm.contactName=Contact name is required
Min.reservationForm.seats=Seats must be at least 1
typeMismatch.reservationForm.seats=Seats must be a whole number
~~~

If `messages_vi.properties` is present, Spring can resolve messages for the Vietnamese locale. Note that a formatter's `ParseException` message does not automatically become a localized user-facing message; mapping through message codes/`MessageSource` separates technical parsing errors from user experience.

### 10.3. Reading Metadata When Suspecting the Formatter Didn't Run

~~~java
for (FieldError error : errors.getFieldErrors()) {
    System.out.println(
            error.getField()
            + " | " + error.getCode()
            + " | binding=" + error.isBindingFailure());
}
~~~

The snippet above is strictly for debugging or tests. **Never** print raw `error.getRejectedValue()` for sensitive fields (passwords, tokens, card numbers). If you see `typeMismatch` on `code`, check whether the formatter is registered, how `parse` behaves, and the target type. If you see `NotBlank` on `contactName`, the converter is not the cause of that error.

## 11. Interaction with Spring Boot Auto-Configuration

Spring Boot gives you a ready-to-use MVC setup. Using `WebMvcConfigurer` generally **augments** configuration while keeping defaults intact.

Key misconceptions:

### 11.1. The MVC Conversion Service Is Not Every `ConversionService`

Spring Boot may create separate conversion services for binding configuration properties, the environment, or other subsystems. `addFormatters` targets Spring MVC's conversion service. If you inject a bean solely by `ConversionService` type, it is not guaranteed to be `mvcConversionService` containing `BookingCodeFormatter`.

In integration tests, inject `@Qualifier("mvcConversionService")` explicitly or test through the MVC request binder itself; do not assume every bean implementing that interface shares the same registry.

### 11.2. JSON/Jackson Does Not Use `Formatter` Like Forms Do

Suppose:

~~~java
@PostMapping(
        path = "/api/reservations",
        consumes = "application/json")
ResponseEntity<?> api(
        @Valid @RequestBody ReservationForm form) {
    // ...
}
~~~

This is an illustrative snippet without full imports or return body. Jackson decodes JSON using its own metadata first, and then Bean Validation checks the DTO. A JSON field like `"code": "bk-a12"` is not automatically parsed by MVC's custom `BookingCodeFormatter`. If you need an equivalent rule in JSON, design a Jackson deserializer/creator or a suitable JSON DTO and test it separately.

You can still use the same **global MVC Validator** to validate the bean after Jackson deserializes it, but JSON decoding and String-to-`BookingCode` form parsing are two separate pipelines.

### 11.3. WebFlux Uses a Different Configuration Interface

`WebMvcConfigurer` is for Spring MVC/Servlet. If an application uses `spring-boot-starter-webflux` and reactive annotated controllers, the matching hook is `WebFluxConfigurer`. Do not add `WebMvcConfigurer` to a WebFlux app and assume formatters/validators were activated.

### 11.4. AOP Method Validation Is a Separate Boundary

A Spring service class annotated with `@Validated` at the class level and `@NotBlank` on a method parameter, invoked via a Spring AOP proxy, uses method-validation infrastructure (typically throwing `ConstraintViolationException` by default). That is **not equivalent** to Spring MVC controller binding's `getValidator()`. Many applications share the same Jakarta validation provider, yet triggers, exceptions, and constraint groups can differ.

In other words:

~~~text
WebMvcConfigurer.getValidator()
    -> global Spring MVC argument validator

@Validated on a Spring-managed service
    -> method validation via AOP proxy

Validator.validate(bean) called manually
    -> returns Set<ConstraintViolation<T>>
~~~

Do not put a rule inside `Formatter.parse(...)` expecting it to automatically guard every service method or every JSON API.

## 12. Security and Performance

### 12.1. Never Bind Directly to Entities

An entity may have `id`, `role`, `approved`, or `balance`. If an HTTP binder can write every property, clients can submit fields absent from the HTML form and tamper with values. Use dedicated web-input DTOs and appropriate `setAllowedFields(...)`. `@Valid` is not an authorization mechanism, and formatters do not prevent mass assignment.

### 12.2. Keep Converters and Validators Lightweight and Side-Effect-Free

Formatters are typically registered globally. Write them to be **stateless**, thread-safe, and deterministic: do not store request data in instance fields, and never share an unsynchronized mutable `SimpleDateFormat`. For identifiers, use an immutable `Pattern` and `Locale.ROOT` as shown.

Avoid database calls inside formatters or using a validator to persist entities. I/O and domain checks belong in the service/repository layer with proper transactions and permissions.

### 12.3. Never Expose Sensitive Data in Errors

`FieldError.getRejectedValue()` and `ConstraintViolation.getInvalidValue()` can contain raw user input. Never serialize raw exceptions, target objects, or rejected values directly into REST responses or logs. Use error codes, field names, and escaped/approved messages.

### 12.4. CSRF, Authorization, and Input Sanitization

In apps with Spring Security, form POSTs require CSRF tokens; a request rejected with HTTP 403 may never even reach the binder or Bean Validation. Validation does not replace authentication, authorization, HTML escaping, or domain security rules.

## 13. Common Mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| `code=bk-a12` reports `typeMismatch` | Formatter not registered or parsing failed | Check `addFormatters`, `BookingCode` type, and parse logic |
| Field renders `BookingCode[value=...]` | View calls `toString()` instead of formatter | Use `th:field` / Spring form tags and `Formatter.print` |
| `@NotBlank` stops working after customizing `getValidator` | Global validator replaced with custom Spring Validator that doesn't delegate to Jakarta | Use `LocalValidatorFactoryBean` or add local rules |
| `getValidator()` returns `null` yet `@Valid` still runs | Spring picks default validator when provider is present | This is expected behavior |
| Calling `new LocalValidatorFactoryBean()` per request | Confusing config hook with per-request callback | Use a Spring-managed singleton bean |
| Multiple `WebMvcConfigurer`s return custom `Validator`s | Conflicting global configuration | Standardize on one choice; use local validators if needed |
| JSON `@RequestBody` fails to parse `BookingCode` | Jackson does not use MVC's `FormatterRegistry` for JSON decoding | Design a separate JSON DTO/deserializer |
| `@RequestParam BookingCode` fails to convert | Registered on a non-MVC conversion service | Use MVC config and test via binder |
| `@Valid` produces no errors | Missing Bean Validation provider/annotations or group mismatch | Check starter, constraints, and groups |
| `BindingResult` misses form errors | Placed far from `@ModelAttribute` or mismatched attribute | Place immediately after the form argument |
| Form loses invalid `code` string | Reading null bean property after conversion failure | Use `BindingResult.getFieldValue()` or `th:field` |
| All Boot MVC settings disappear | Added `@EnableWebMvc` unnecessarily | Use `WebMvcConfigurer` without `@EnableWebMvc` in Boot |
| Test injects the wrong `ConversionService` | App has multiple conversion services | Add `@Qualifier("mvcConversionService")` |
| `ParseException` message leaks details | Returning raw exception to client | Use message codes / `MessageSource` |
| Admin field modified via form | Entity used as form DTO without property restrictions | Dedicated DTO, `setAllowedFields`, business authorization |
| Custom validator blocks unrelated DTOs | Global validator has overly broad `supports` or mis-scoped rule | Use `@InitBinder.addValidators` / properly scoped custom constraints |

## 14. Debugging Checklist When Binding/Validation Behaves Unexpectedly

1. **Verify the web stack:** Is this Spring MVC/Servlet or WebFlux? For WebFlux, `WebMvcConfigurer` is the wrong hook.
2. **Inspect the raw request:** Check `Content-Type`, request parameters, and property names. Do not confuse `application/json` with `application/x-www-form-urlencoded`.
3. **Inspect the DTO:** Do fields have the right types, getters/setters/constructors, existing nested paths, and inclusion in allowed fields?
4. **Inspect the MVC configurer:** Is the class annotated with `@Configuration`, component-scanned, overriding `addFormatters(...)` with the exact signature, and matching the formatter's target type?
5. **Test bidirectionally:** Call `mvcConversionService.convert("bk-a12", BookingCode.class)` and then `convert(code, String.class)`.
6. **Inspect `BindingResult`:** Does the error have `isBindingFailure()==true` and code `typeMismatch`, or a Bean Validation error like `NotBlank`/`Min`?
7. **Inspect the validator:** Does `getValidator()` return `null` or an instance; are the Bean Validation provider, `LocalValidatorFactoryBean`, and `@Valid` on the argument present?
8. **Inspect handler parameter order:** `BindingResult` must sit immediately after `@ModelAttribute` if the controller handles errors inline.
9. **Inspect the view:** Does `th:object` match the name, does `th:field` use the right path, is rejected input preserved, and is the locale right?
10. **Inspect security/domain boundaries:** Should the field be bindable at all, does the form have a CSRF token, and are DB checks kept out of `Formatter`/`Validator`?

## 15. Practice Exercises

**Exercise 1 — `Converter` or `Formatter`?** If you only need `String → UUID`, would you pick `Converter` or `Formatter`? When a `Money` type must also print in a Vietnamese locale and parse back into an object, which interface is better?

**Exercise 2 — Parsing and validation:** Submit `code=BK-1` and then `code=BK-ABC` with `contactName=""`. Which case is a `typeMismatch`? Which case is a Jakarta constraint violation?

**Exercise 3 — Lifecycle:** Why is instantiating `new LocalValidatorFactoryBean()` inside a per-request callback bad practice? Explain how to define a Spring-initialized singleton bean and return it from `getValidator()`.

**Exercise 4 — Default selection:** Remove the `getValidator()` override and the `ValidationBeans` class from the demo while keeping `spring-boot-starter-validation`. Verify whether `@NotBlank` and `@Min` still work, and explain how Spring MVC selects the default validator.

**Exercise 5 — Local rule:** Add a Spring `Validator` forbidding `contactName="system"` only for the reservation form using `@InitBinder.addValidators(...)`. Prove that other forms do not inherit this rule.

**Exercise 6 — JSON differs from forms:** Send `{"code":"bk-a12"}` to `@RequestBody ReservationForm`. Why might the custom `Formatter` not be used? Design a JSON DTO with `String code` mapped to `BookingCode` at the application boundary, or use appropriate Jackson deserialization.

**Exercise 7 — Rejected input:** Submit `code=WRONG` and inspect `FieldError.getRejectedValue()`, `getFieldValue("code")`, `isBindingFailure()`, and the HTML input rendered back by `th:field`.

**Exercise 8 — Locale:** Build a `Formatter<Money>` that prints/parses amounts using `Locale`; compare Vietnamese and English outputs. Note the difference between localized number display and `<input type="number">`'s fixed syntax.

**Exercise 9 — Allowed fields:** Submit an extra `role=ADMIN` or `approved=true` parameter in the form. Why does `@NotBlank` alone not prevent mass assignment? Test `binder.getBindingResult().getSuppressedFields()` to observe fields blocked from binding.

**Exercise 10 — Method validation:** Annotate a service with `@Validated` and place `@NotBlank` on a method parameter. Call it through a proxy and via `new`, comparing exceptions to understand why `WebMvcConfigurer.getValidator()` is not the same as AOP method validation.

## 16. Knowledge Summary

Mental map:

~~~text
              Spring MVC setup
                     |
         +-----------+-----------+
         |                       |
   addFormatters(...)        getValidator()
         |                       |
   FormattingConversionService   global Spring Validator
         |                       |
   String <-> Java types       @Valid / @Validated
         |                       |
         +-----------+-----------+
                     |
               WebDataBinder
                     |
               BindingResult
                     |
             Controller / View
~~~

- `addFormatters` **registers** converters/formatters to convert and present data.
- `getValidator` **selects** the global validator to validate objects against declared rules.
- `@Valid`/`@Validated` **triggers** validation and groups on arguments; `BindingResult` **holds** binding/validation errors.
- In Spring Boot, overriding only `addFormatters` and keeping the default validator is usually enough. If you genuinely need a custom global validator, use a `LocalValidatorFactoryBean`/adapter so Jakarta constraints are not lost.
- `@InitBinder` adds local binder customization and restricts writable properties.
- Form conversion differs from JSON deserialization; Spring MVC differs from WebFlux; controller binding differs from Spring AOP method validation.

**Conclusion:** Valid formatting does not guarantee valid data, and proper validation cannot fix type-conversion failures. Placing each responsibility in the right hook makes code easier to test, maintain, and secure.

## References

- [Spring Framework 6.2 — WebMvcConfigurer API: addFormatters, getValidator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — MVC config: Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — MVC config: Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — MVC configuration: @EnableWebMvc and Spring Boot](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/enable.html)
- [Spring Framework — Formatter SPI](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework — FormatterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — BindingResult and FieldError](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Boot 3.5 — ValidationAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/validation/ValidationAutoConfiguration.html)
- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
