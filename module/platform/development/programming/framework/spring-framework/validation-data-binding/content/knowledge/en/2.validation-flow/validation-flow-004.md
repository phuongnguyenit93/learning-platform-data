# Converting from Strings to Target Data Types in Spring Framework

## 1. Why Is Type Conversion Needed?

When Spring receives data from an HTTP request, many values start out as strings: query parameters, path variables, form fields, or individual form elements. However, controller parameters and object properties can be declared as `int`, `long`, `BigDecimal`, `LocalDate`, `Enum`, or domain types. Spring needs to **convert source strings into target Java types** before assigning values (data binding) or invoking the method.

For example, `GET /orders?quantity=3&date=2026-11-02` can be mapped to `Integer quantity` and `LocalDate date`. The two values `"3"` and `"2026-11-02"` are strings in the request but are converted by Spring into the appropriate objects.

Distinguish between:
- **Conversion**: turning `"3"` into `Integer.valueOf(3)`, `"ACTIVE"` into an enum, or `"2026-11-02"` into a date.
- **Binding**: assigning the converted value to a parameter or object property; may include nested properties and collections.
- **Validation**: checking constraints *after* data has been converted/bound, such as quantity having to be greater than 0. A conversion failure is not the same as a validation failure.

## 2. General Processing Flow

```text
HTTP request (strings / source value set)
        |
        v
HandlerMethodArgumentResolver or WebDataBinder
        |
        v
Look up converter by source type -> target type
        |
        +-- Converter / ConverterFactory / GenericConverter
        |   (and Formatter/Parser for locale-dependent representations)
        v
Converted Java value
        |
        v
Assign to @RequestParam, @PathVariable,
@ModelAttribute parameter or object property
        |
        v
Validation (when triggered) -> controller if successful
```

Spring provides the `ConversionService` system (in `org.springframework.core.convert`) for type conversion independent of the web layer. `GenericConversionService` manages converters; `DefaultConversionService` registers many common converters; `DefaultFormattingConversionService` adds formatters for numbers, dates, and types with locale-dependent representations. In Spring MVC, conversion for binding is typically performed through `WebDataBinder` and the MVC configuration mechanism.

Actual conversion capabilities depend on the configured `ConversionService`. Do not assume every string or every date format is accepted by default.

## 3. Common Conversions

| Source string | Target type | Example result | Things to note |
| --- | --- | --- | --- |
| `"42"` | `Integer` / `int` | `42` | Invalid strings or out-of-range values cause a conversion error |
| `"true"` | `Boolean` / `boolean` | `true` | Accepted representations depend on the registered converter |
| `"19.95"` | `BigDecimal` | `19.95` | Watch decimal separators and locale when using a formatter |
| `"2026-11-02"` | `LocalDate` | November 2, 2026 | Explicitly declare format using `@DateTimeFormat` |
| `"ACTIVE"` | `Status` enum | `Status.ACTIVE` | Default enum converter uses constant names and is case-sensitive |
| `"a,b,c"` | `List<String>` | `[a,b,c]` | ConversionService has a related converter, though request binding rules may vary by source and config |

Cases such as empty strings, `null`, primitive values, or strings with whitespace should be tested against the real configuration. In particular, a conversion returning `null` cannot satisfy a primitive parameter.

## 4. Example with Spring MVC Parameters

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders")
    String query(
            @RequestParam int quantity,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate date) {
        return "quantity=" + quantity + ", date=" + date;
    }
}
```

Request:

```http
GET /orders?quantity=3&date=2026-11-02
```

Response body when the request is valid:

```text
quantity=3, date=2026-11-02
```

`@RequestParam` extracts values from the request, Spring converts `"3"` to `int`, and `@DateTimeFormat` guides the parser to read the date in ISO format. If `quantity=abc`, the error occurs **before the `query` method runs**. Missing a required `quantity` differs from failing to convert `"abc"`.

The example above is a controller used inside a configured Spring MVC application; it is not a standalone Java program runnable via `java OrderController`.

## 5. Conversion on `@ModelAttribute` and Form Binding

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class RegistrationForm {
    private Integer age;
    private BigDecimal budget;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public BigDecimal getBudget() { return budget; }
    public void setBudget(BigDecimal budget) { this.budget = budget; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) { this.startDate = startDate; }
}
```

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
class RegistrationController {

    @PostMapping("/register")
    @ResponseBody
    String register(@ModelAttribute RegistrationForm form,
                    BindingResult bindingResult) {
        if (bindingResult.hasErrors()) {
            return "Invalid input";
        }
        return "age=" + form.getAge()
                + ", budget=" + form.getBudget()
                + ", startDate=" + form.getStartDate();
    }
}
```

When submitting form fields `age=28`, `budget=150.50`, `startDate=2026-11-02`, the binder attempts to convert each value and assign it to the corresponding property. `BindingResult` must sit **immediately after** the bound model parameter it describes; the binder can store field errors (such as `typeMismatch`) for the controller to handle. Never infer that a field that failed conversion definitely holds a valid default value; always check for errors before using it.

In JSON APIs with `@RequestBody`, JSON deserialization is performed by `HttpMessageConverter` (usually Jackson); do not equate it with `WebDataBinder`'s string-to-type flow for query/form/path variables. The `@DateTimeFormat` annotation also does not replace Jackson's JSON date format configuration.

## 6. Defining a Custom `Converter<S, T>`

Use a converter when you need to map from a specific source type to a target type and it **does not depend on locale**. For example, converting a string product code into a value object:

```java
public record ProductCode(String value) {
    public ProductCode {
        if (value == null || !value.matches("[A-Z]{2}-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
```

```java
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source.trim());
    }
}
```

To make Spring MVC use the converter on bound parameters and properties, register it via `WebMvcConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
    }
}
```

Then:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {
    @GetMapping("/products/{code}")
    String find(@PathVariable ProductCode code) {
        return code.value();
    }
}
```

The request `GET /products/AB-1234` is converted to `new ProductCode("AB-1234")` and returns `AB-1234`. The request `GET /products/bad` causes a conversion error; the framework handles it according to the parameter/binding error mechanism and exception handler configuration. You should not rely on specific exception message text in the API contract.

`ConverterFactory<S, R>` is suitable when one source needs to convert into multiple subtypes of the same family, such as enums. `GenericConverter` supports conversions that take `TypeDescriptor` and nested types into account, at the cost of higher complexity; use it only when a simple `Converter` does not suffice.

## 7. `Formatter<T>` and Locale Handling

`Formatter<T>` consists of `parse(String, Locale)` and `print(T, Locale)`. It is useful for monetary amounts, dates/times, or values whose representation varies with `Locale`. `Converter` only takes the source and has no locale parameter.

For example, a parser/formatter for a domain currency type can choose the decimal separator based on `Locale`. When you only need standard date formatting, prefer the built-in annotation:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate effectiveDate;
```

Or use an explicit pattern:

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate effectiveDate;
```

The pattern must match the actual data, such as `02/11/2026` for `dd/MM/yyyy`. Do not use an unspecified date input format and rely on the server's default locale. With Spring Boot, additional converters/formatters and conversion configuration may depend on context type; verify which MVC `ConversionService` is actually active.

## 8. Calling `ConversionService` Directly

You can test conversion logic independently from the web layer. The example below is a structurally standalone Java class, though it requires the Spring Core JARs on the classpath:

```java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionDemo {
    public static void main(String[] args) {
        ConversionService service = new DefaultConversionService();

        Integer count = service.convert("12", Integer.class);
        Boolean enabled = service.convert("true", Boolean.class);

        System.out.println(count);
        System.out.println(enabled);
    }
}
```

Output:

```text
12
true
```

With Maven/Gradle, declare the `org.springframework:spring-core` dependency matching your project's Spring version. After building, run `ConversionDemo` with a runtime classpath containing Spring Core and its related dependencies. `javac ConversionDemo.java` alone cannot compile or run without the Spring JARs. `ConversionService#canConvert(String.class, Integer.class)` can check whether a conversion path exists, but **does not guarantee** a specific string `"xyz"` is valid.

## 9. Common Errors and How to Handle Them

- **Unable to parse numbers or dates**: use the appropriate target type and `@DateTimeFormat`, and return a 400 error with helpful field details; never silently interpret an invalid string as `0`.
- **Enum does not match constant name**: by default, the exact enum name is usually required. If the API allows aliases or case-insensitivity, write an explicit converter; avoid accidentally altering global semantics.
- **Wrong locale/decimal separator**: distinguish data transmitted over machine-to-machine APIs from representations in user-facing forms. For APIs, standardize the format and document it.
- **Converter is not invoked**: check that it is registered with the right `ConversionService`/MVC context, check the generic source/target types, and check whether another converter takes precedence.
- **Using `@Valid` to handle parse failures**: validation constraints do not fix strings that fail conversion; handle binding errors and validation errors separately.
- **Confusing `@RequestBody` with `@ModelAttribute`**: JSON uses a deserializer, while query/path/form usually goes through binder/conversion; test the actual path.
- **Creating an overly broad converter**: avoid a `String -> Object` converter with unexpected behavior across all parameters; choose a specific target type and report errors clearly.
- **Not handling `BindingResult`**: in forms, place it immediately after the corresponding model attribute so you can return field error messages; in REST controllers, handle appropriate exceptions via `@ControllerAdvice` if you want a consistent response.

## 10. Checklist When Applying

1. Identify the data source (query/path/form/JSON), target Java type, and mechanism used by Spring.
2. Prefer default converters/formatters, and declare exact formats for dates and numbers.
3. Write custom converters for domain-specific rules, and register them in the right registry.
4. Test valid values, empty values, invalid formats, out-of-range values, and relevant locales.
5. Handle conversion/binding errors predictably before using the object; run validation separately for domain constraints.
6. Keep the HTTP contract clear, for example: `quantity` is a positive integer and `date` follows ISO `yyyy-MM-dd`.

**Key takeaway:** Spring converts string values to target Java types through the conversion/formatting infrastructure, and only then binds and validates them. Understanding the data source, registered converters, and how errors are reported helps avoid silent or hard-to-diagnose input bugs.
