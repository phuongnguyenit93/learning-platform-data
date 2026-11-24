# Configuring FormattingConversionService for Input and Display Needs

When a user enters `"12,50"` or `"31/12/2026"`, the application must **parse** the string according to the user's conventions, convert it into an appropriate Java type, and be able to **display** the data back in the desired format. Spring Framework provides `FormattingConversionService` to unify both directions alongside general type conversion.

This lesson focuses on **how to configure** the formatting service for forms, model objects, and Spring MVC: choosing formatter/converter types, registering in the right scope, handling `Locale`, supporting field annotations, verifying parse/print directions, and diagnosing errors. The examples use Java 17+ and Spring Framework 6.x APIs.

## 1. Framing the Requirement: Input and Display Are Bidirectional

Suppose an application has a quantity/decimal property in its model. A user chooses German and enters `12,50`; the Java object stores `BigDecimal("12.50")`. When displayed back to an English (US) user, the UI can print `12.50`.

```text
INPUT (client -> model)
"12,50" + Locale.GERMANY
          |
          | Formatter.parse(...) or related converter
          v
        Java object: BigDecimal("12.50")
          |
          | business processing/validation (if any)
          v
DISPLAY (model -> client)
Java object + Locale.US
          |
          | Formatter.print(...)
          v
        "12.50"
```

String formatting should not be treated as changing the underlying business value. `12,50` and `12.50` are two representations of the number 12.5 across different locales. For storage and computation, use the appropriate data type (`BigDecimal` for many exact decimal cases, `LocalDate` for dates without time zones, etc.); format at the UI boundary.

For fields in Spring MVC, the flow is typically:

1. The request carries field names and text values.
2. `WebDataBinder` identifies the target property/type.
3. `ConversionService`/`Formatter` parses the value according to type and `Locale`.
4. The binder assigns the value or records a type conversion error into `BindingResult`.
5. Validation is triggered when configured/requested.
6. The form view uses Spring's field binding mechanism to re-render values with the appropriate formatter.

**Bidirectional does not mean strictly symmetric for every input.** A formatter may normalize output formatting (for example, parsing `12,5` but printing `12,50`). Rounding rules, precision, and accepted input shapes must be clearly defined.

## 2. Participating Components

| Component | Role | When to use |
| --- | --- | --- |
| `Converter<S,T>` | Converts one type to another, without directly receiving `Locale` | `String -> Enum`, `String -> ID`, `Long -> Instant` with clear conventions |
| `Printer<T>` | Converts a typed value to `String` for the UI | Printing dates, numbers, display codes |
| `Parser<T>` | Parses `String` into a typed value | Reading user text input |
| `Formatter<T>` | Combines `Printer<T>` and `Parser<T>`, both receiving `Locale` | Numbers, dates, and region/language-dependent display values |
| `ConversionService` | General conversion API (`convert`, `canConvert`) | Used by binders/SpEL or application code |
| `FormatterRegistry` | API to register `Converter`, `Formatter`, `Printer`, `Parser`, annotation formatters | Centralized configuration |
| `FormattingConversionService` | A `ConversionService` that is also a `FormatterRegistry` | Hub for bidirectional configuration |
| `DefaultFormattingConversionService` | Implementation preloaded with many default converters/formatters | Common starting point |
| `FormatterRegistrar` | Packages registration of a group of formatters/converters | Configuring date/time or related formatting groups |

`FormattingConversionService` extends `GenericConversionService` and implements `FormatterRegistry`. It allows registering both general type conversions and `Locale`-aware formatters. Common calls:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new MyConverter());       // Converter<S,T>
service.addFormatter(new MyTypeFormatter());   // Formatter<T>
```

This is **API illustration code**: `MyConverter` and `MyTypeFormatter` must have real implementations. `new DefaultFormattingConversionService()` already registers many converters, number/date formatters, and support for common formatting annotations. When you only need to add a custom type, **keeping the defaults and adding your formatter** is usually the simplest option with the least risk of losing built-in behavior.

Distinguish the two constructors:

- `new DefaultFormattingConversionService()`: registers default converters and default formatters.
- `new DefaultFormattingConversionService(false)`: still registers default converters, but **does not register default formatters**; intended for intentional replacement setups. When using this, you must re-register the exact formatters/annotation formatters the application needs.

`new FormattingConversionService()` is a blank registry for manual setup; do not assume it comes with the full rule set of `DefaultFormattingConversionService`.

## 3. Registering Formatters by Type or by Annotation

`FormatterRegistry` supports the following forms:

```java
registry.addFormatter(new QuantityFormatter());
registry.addFormatterForFieldType(Quantity.class, new QuantityFormatter());
registry.addFormatterForFieldAnnotation(new MyAnnotationFormatterFactory());
```

Example class names are illustrative; `QuantityFormatter` is implemented in full later.

- **By type:** every property of type `Quantity` within the registry's scope uses the formatter registered for that type when parsing/printing. `addFormatter(...)` can infer type `T` from the implementation's generic parameter; `addFormatterForFieldType(...)` states the type explicitly.
- **By annotation:** only fields/parameters carrying the matching annotation receive the rule. Suitable when the same type requires multiple formatting styles—for example, monetary amounts and quantities both using `BigDecimal` while displaying differently.
- **By group:** `FormatterRegistrar.registerFormatters(FormatterRegistry)` registers multiple converters/formatters together for consistent configuration.
- **Splitting directions:** `addPrinter(...)` and `addParser(...)` are useful when only one direction is needed; for full input and display forms, `Formatter<T>` is usually clearer.

Avoid registering a formatter that applies globally to `String` or `BigDecimal` just to handle one special field if other parts of the application use different formats. When a custom rule is needed, prefer field annotations, dedicated value object types, or an appropriate binder scope.

## 4. Standalone Java 17+ Example with Spring: Locale for Parse and Print

This example uses a `Quantity` value object to clearly demonstrate how a `Formatter<Quantity>` works through `DefaultFormattingConversionService`. With `Locale.GERMANY`, the comma is the decimal separator; with `Locale.US`, the period is the decimal separator.

Create the Maven structure:

```text
formatting-demo/
├── pom.xml
└── src/main/java/FormattingServiceDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>formatting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/FormattingServiceDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormattingServiceDemo {
    // Target type holding parsed data; does not preserve UI commas/dots.
    public record Quantity(BigDecimal value) {}

    public static final class QuantityFormatter implements Formatter<Quantity> {
        private DecimalFormat decimalFormat(Locale locale) {
            // Create a new instance per call because DecimalFormat is not thread-safe.
            DecimalFormat format =
                    (DecimalFormat) NumberFormat.getNumberInstance(locale);
            format.setParseBigDecimal(true);
            format.setGroupingUsed(false);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            return format;
        }

        @Override
        public Quantity parse(String text, Locale locale) throws ParseException {
            DecimalFormat format = decimalFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            // Parsing must consume the entire string to avoid accepting trailing characters.
            if (!(parsed instanceof BigDecimal number)
                    || position.getIndex() != text.length()) {
                throw new ParseException("Invalid quantity: " + text, 0);
            }
            // Example convention: at most two decimal places.
            if (number.scale() > 2) {
                throw new ParseException("Too many decimal places: " + text, 0);
            }
            return new Quantity(number);
        }

        @Override
        public String print(Quantity quantity, Locale locale) {
            return decimalFormat(locale).format(quantity.value());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(new QuantityFormatter());

        try {
            LocaleContextHolder.setLocale(Locale.GERMANY);
            Quantity quantity = service.convert("12,50", Quantity.class);

            System.out.println("internal=" + quantity.value().toPlainString());
            System.out.println("display.de=" + service.convert(quantity, String.class));

            LocaleContextHolder.setLocale(Locale.US);
            System.out.println("display.us=" + service.convert(quantity, String.class));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Run in the `formatting-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=FormattingServiceDemo
```

Lines printed by the program:

```text
internal=12.50
display.de=12,50
display.us=12.50
```

Reading the example by responsibility:

1. `Quantity` is the model type; `BigDecimal` stores the decimal value independently of display formatting.
2. `QuantityFormatter.parse` converts a string in the active locale into `Quantity`.
3. `QuantityFormatter.print` outputs a string in the active locale from `Quantity`.
4. `service.addFormatter(...)` registers both directions for type `Quantity`.
5. `service.convert(...)` uses the appropriate formatter adapter when converting between `String` and `Quantity`.
6. `LocaleContextHolder.setLocale(...)` simulates the active locale so the example yields deterministic output. In a normal MVC request, Spring integrates the request locale into the processing context; in tests or standalone code, set and reset the context carefully.

**Scope of the demo:** `setGroupingUsed(false)` removes thousands separators to keep output clear; it does not represent all international number input rules. The "at most two decimal places" rule is part of the example design; real applications must also specify min/max bounds, negative signs, rounding, units, and invalid data policies. `DecimalFormat` is not safe to share across threads; the example always creates a fresh instance.

If `"12,50"` is changed to `"abc"` under `Locale.GERMANY`, `parse` fails; when calling `ConversionService.convert` directly, the error is raised to the caller as a conversion exception (with the corresponding parse cause). If the operation goes through `DataBinder`, the error is typically recorded in `BindingResult`.

## 5. Registering in a Spring MVC Application

In a Spring MVC or Spring Boot application using Spring MVC, the natural configuration hook for form formatters is `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Extract Quantity and QuantityFormatter from the previous example into classes
        // accessible within the application.
        registry.addFormatter(new QuantityFormatter());

        // Separate example: ISO formatting for MVC's java.time types.
        DateTimeFormatterRegistrar dates = new DateTimeFormatterRegistrar();
        dates.setUseIsoFormat(true);
        dates.registerFormatters(registry);
    }
}
```

This is a **configuration snippet for a Spring MVC project**, not a standalone file; it requires the `QuantityFormatter` class from section 4 and the `spring-webmvc` dependency (or the corresponding web starter). Place `WebFormattingConfig` within the application's component scan scope. `addFormatters` lets you add converters/formatters to MVC's registry without manually creating and replacing the entire default service.

When only custom `Quantity` formatting is needed, omit the `DateTimeFormatterRegistrar` block to keep existing date/time behavior. `dates.setUseIsoFormat(true)` is a **global configuration choice for date/time types**; apply it if the UI/API expects ISO, and do not add it mechanically if the system has other conventions.

Declaring `@Configuration` is usually preferable to each controller manually transforming strings with `replace(",", ".")`, because a single registration serves multiple forms and reduces inconsistencies between input and display.

### Is the `conversionService` Bean in the Spring Container the Same as the MVC Registry?

Not completely. The **BeanFactory** `ConversionService` is used for conversion during bean/property configuration and supporting flows; the **Spring MVC** `ConversionService` is used for request/model data binding. The two scopes can be configured differently.

For the Spring container, an example bean registration is:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

@Configuration
class CoreConversionConfig {
    @Bean("conversionService")
    static ConversionService conversionService() {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(new QuantityFormatter());
        return service;
    }
}
```

This snippet depends on `QuantityFormatter` from section 4. A bean named `conversionService` is one way to configure `ConversionService` for the Spring container. **Do not assume merely declaring that bean replaces Spring MVC's formatter registry in every setup**, especially when the application uses Spring Boot auto-configuration. To customize MVC forms, the targeted choice is `WebMvcConfigurer.addFormatters`.

If the application uses Spring XML configuration, Spring also provides `FormattingConversionServiceFactoryBean` with `converters`, `formatters`, and `formatterRegistrars` properties; use it when the project genuinely needs declarative XML configuration.

## 6. Using @NumberFormat and @DateTimeFormat Instead of Writing Custom Formatters

Common numeric/date types are usually **already supported**, so you only need to declare rules directly on fields/parameters when you do not want a global effect.

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate checkIn;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal budget;

    public LocalDate getCheckIn() { return checkIn; }
    public void setCheckIn(LocalDate checkIn) { this.checkIn = checkIn; }

    public BigDecimal getBudget() { return budget; }
    public void setBudget(BigDecimal budget) { this.budget = budget; }
}
```

This is a **model class** for use with a binder/MVC, without `main`. Meaning:

- `@DateTimeFormat(iso = ISO.DATE)`: date in ISO format such as `2026-12-31`, suitable when input requires a consistent representation.
- `@NumberFormat(pattern = "#,##0.00")`: describes a number format with integer grouping and two decimal digits; actual symbols in the UI are interpreted according to `Locale`. With `Locale.GERMANY`, display might be `1.234,50`; with `Locale.US`, `1,234.50`.
- `@NumberFormat(style = NumberFormat.Style.CURRENCY)`: rule to print numbers in the locale's currency style. This is **display formatting** only; it does not define currency code, exchange rate, financial precision, or business units.
- `@DateTimeFormat(pattern = "dd/MM/yyyy")`: fixes a date input/output pattern. For public APIs or inter-system data exchange, ISO is usually easier to standardize.

**Crucial point:** annotations are evaluated when the system has **field/parameter context and its metadata**, such as during Spring MVC binding. A call like `service.convert("...", LocalDate.class)` only passes source/target types; it provides no metadata from the `checkIn` field to apply the annotation on `BookingForm`.

When the same type needs multiple formatting styles, field annotations fit better than replacing the global formatter for every field. For a dedicated value object (`Quantity`), a type-registered `Formatter<Quantity>` is usually convenient.

## 7. Locale: Where It Comes From, When It Is Used, and How to Test It

`Formatter<T>` receives a `Locale` parameter in both `parse(String, Locale)` and `print(T, Locale)`. This is the major difference from a basic `Converter<S,T>`.

In Spring MVC, the locale usually comes from the configured request locale mechanism (for example, the `Accept-Language` header if the app uses the corresponding resolver). In direct code, `FormattingConversionService` commonly uses `LocaleContextHolder` to supply the locale to formatter adapters. When writing tests, **pin the locale** rather than relying on the CI machine's default locale.

Example test cases to verify:

| Locale | Input string | Expected model | Printed string with two decimals |
| --- | --- | --- | --- |
| `Locale.GERMANY` | `12,50` | `BigDecimal("12.50")` | `12,50` |
| `Locale.US` | `12.50` | `BigDecimal("12.50")` | `12.50` |
| `Locale.GERMANY` | `abc` | Parse fails | Print not performed |
| `Locale.GERMANY` | `12,345` | Rejected by example `QuantityFormatter` due to >2 decimal digits | Print not performed |

These rows describe the formatter **from the section 4 example**, not a guarantee that all of Spring's default formatters accept/reject those exact strings.

Common traps:

- **Hardcoding separators:** calling `replace(",", ".")` breaks inputs with thousands grouping separators or other locales.
- **Not specifying locale explicitly in tests:** identical input can produce different outcomes depending on the default locale.
- **Leaking ThreadLocal locale state:** when calling `LocaleContextHolder.setLocale(...)` manually, use `try/finally` to reset it and avoid affecting subsequent processing/tests.
- **Sharing mutable `SimpleDateFormat` or `DecimalFormat`:** they are not thread-safe; instantiate per call or use appropriate immutable APIs like `java.time.format.DateTimeFormatter`.
- **Ignoring JDK differences:** `FormatStyle`/locale-based formatting can vary across JDK locale data; use ISO formats or controlled patterns for data requiring high stability.

### HTML Date/Time Inputs vs. Text Inputs

For `<input type="text">`, browsers send the raw string typed by the user, so parsing by app locale/pattern is important. However, HTML `<input type="date">` sends a standardized `yyyy-MM-dd` value regardless of how the calendar renders regionally; `<input type="time">` likewise follows HTML's machine-readable format.

Therefore, avoid applying a localized date formatter like `dd/MM/yyyy` to an HTML `type="date"` field assuming the browser will submit that exact format. You can configure ISO for such fields with `@DateTimeFormat(iso = ISO.DATE)` or register ISO date/time formatters appropriately. Distinguish **the control's wire value** from **how the browser visually renders the control**.

## 8. Integrating with DataBinder and Handling Input Errors

To simulate binding outside web requests, you can configure `DataBinder` with the same `FormattingConversionService`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

// QuantityForm is a JavaBean with a quantity property of type Quantity,
// along with getter/setter; QuantityFormatter is from section 4.
QuantityForm form = new QuantityForm();
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();
service.addFormatter(new QuantityFormatter());

DataBinder binder = new DataBinder(form, "quantityForm");
binder.setConversionService(service);

MutablePropertyValues values = new MutablePropertyValues();
values.add("quantity", "12,50");

// Requires Locale.GERMANY in the active context.
binder.bind(values);
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Use fieldErrors/rejectedValue to return an appropriate message.
}
```

This is an **integration illustration snippet**, not a standalone runnable program: `QuantityForm` and the locale context must be declared/set up according to the application. `DataBinder` performs assignment, `FormattingConversionService` converts the string to `Quantity`, and `BindingResult` holds errors if conversion fails.

If the user enters `"abc"`, a parse failure can become a field binding error, typically with code `typeMismatch`; check `result.getFieldError("quantity")`. When code calls `ConversionService.convert` directly, exceptions must be handled by the caller as needed; that API does not produce a `BindingResult`.

**Formatting is not validation:** successfully parsing `"0,00"` into `Quantity` does not prove the value is valid for business rules. If a positive quantity (>0) is required, check it via Spring `Validator`, Jakarta Bean Validation (e.g., `@DecimalMin` on an appropriate numeric field), or the service/domain layer. Calling `DataBinder.bind` directly does not mean `binder.validate()` has run.

**Formatting is not security:** successful formatting does not grant write access to properties. Form binding from untrusted input requires DTOs/constructors with appropriate field lists and, where applicable, allowed fields configuration. Do not use formatters to replace authorization checks or prevent mass assignment.

## 9. Three Configuration Levels: Choosing the Right Place and Avoiding Side Effects

| Need | Appropriate configuration approach | Notes |
| --- | --- | --- |
| A local code block or standalone binder | Create `DefaultFormattingConversionService`, `addFormatter`, then `binder.setConversionService(...)` | Clear scope control; reuse the service once configured |
| All Spring MVC forms needing custom formatters | `WebMvcConfigurer.addFormatters` | Uses MVC's registry; does not replace all default converters |
| A single field needing a custom pattern | `@NumberFormat` / `@DateTimeFormat` | Minimal impact on other fields of the same type |
| Application-wide shared date/time rules | `DateTimeFormatterRegistrar` / `DateFormatterRegistrar` | Distinguish `java.time` from `java.util.Date`; test both directions |
| A suite of custom formatters | `FormatterRegistrar` | Reduces scattered configuration, maintains consistency |
| Spring XML project | `FormattingConversionServiceFactoryBean` | Declares converters, formatters, and registrars |
| Affecting bean property conversion in container | Bean named `conversionService` | Compare actual scope against MVC/Boot registries |

With Spring Boot using MVC, inspect existing MVC configuration before adding beans. Boot offers `spring.mvc.format.*` settings for some common date/time formats; these have their own scope and rules. When only adding custom formatters, registering via `WebMvcConfigurer` is clear. Avoid adding `@EnableWebMvc` solely to register formatters in a Boot app relying on MVC auto-configuration; that annotation can alter how the application receives other automatic configurations.

### When Default Date/Time Formats Must Be Replaced Broadly

Spring provides an intentional configuration option, for example:

```java
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

DefaultFormattingConversionService custom =
        new DefaultFormattingConversionService(false);

DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
registrar.setUseIsoFormat(true);
registrar.registerFormatters(custom);
```

This snippet is **only meant to illustrate the API structure**. With `false`, default formatters are not registered: other annotation formatters, such as `@NumberFormat`, may need explicit re-registration. Unless you have a requirement to replace all defaults, using `new DefaultFormattingConversionService()` and adding specific rules is usually safer.

Per Spring documentation, when specifying global date/time formatting, `DateTimeFormatterRegistrar` handles `java.time`, while legacy `Date`/`Calendar` types have `DateFormatterRegistrar`. Do not assume one registrar covers all date/time types.

## 10. Diagnosing Input/Display Issues

| Symptom | Causes to check | How to verify/fix |
| --- | --- | --- |
| Entering `12,50` triggers `typeMismatch` | Locale, unregistered formatter, or not applied to the field | Check active locale, `addFormatters`, and `FieldError` |
| Input parses fine, but display uses a different decimal separator | Locale at print time differs from parse time | Record request locale during rendering; test parse/print per locale |
| Custom formatter exists, yet Spring MVC ignores it | Registered in a different `ConversionService` than MVC's registry | Move configuration to `WebMvcConfigurer.addFormatters` or wire the right service |
| `@DateTimeFormat` annotation seems ineffective | Direct conversion without field metadata, or binder lacks annotation support | Check binding path and property `TypeDescriptor` |
| `type="date"` form date rejected as invalid format | Localized pattern applied to input that submits ISO | Use ISO for HTML date input data |
| Global format change breaks other forms | Formatter registered for too broad a type or defaults disabled | Narrow using field annotations/value objects; restore needed defaults |
| Thousands separators or decimals are wrong | Using `replace`/`parseDouble` ignoring locale | Use a number formatter and define grouping/precision rules |
| Same test gives different results on CI | Dependent on environment locale/JDK | Pin locale, timezone when relevant, input samples, and JDK |
| User enters bad input, but page shows no error message | `BindingResult` misused or view does not render errors | Check parameter placement and view field error rendering |
| JSON format differs from HTML forms | `@RequestBody` goes through HTTP message converters (usually Jackson) | Configure JSON serializer/deserializer separately if the API requires that format |

A short debugging workflow:

1. Identify the **request type**: HTML form/`@ModelAttribute` or JSON/`@RequestBody`.
2. Record the **field name, raw string, target type, and `Locale`**.
3. Verify the formatter/converter is registered in the **correct service/binder**.
4. Test `String -> T` and `T -> String` separately under a fixed locale.
5. Inspect the form's `BindingResult` to distinguish parse errors from validation errors.
6. Check whether form rendering uses Spring field binding (e.g., Thymeleaf `th:field` or Spring form tags) or simply prints raw properties.
7. Run tests with all supported locales, boundary values, empty inputs, malformed syntax, and numbers with grouping/decimal separators.

**Note on JSON:** `FormattingConversionService` is tied to Spring binding/forms; Jackson serializes/deserializes JSON using its own mechanisms and settings. Do not expect `@NumberFormat` or a `Formatter<T>` in MVC to automatically alter how JSON is written by `@ResponseBody`.

## 11. Self-Check Questions

**1. Why might `Converter<String, BigDecimal>` not be the best solution for internationalized input?** Because a basic converter does not receive a `Locale` parameter; `Formatter<BigDecimal>` provides locale-aware `parse` and `print`, making it better suited for UIs. If input always follows a single fixed machine-readable format, a converter can still make sense.

**2. A `LocalDate` property needs to accept `yyyy-MM-dd` from an HTML `type="date"` input—what should you choose?** You can declare `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`; for many fields sharing the requirement, configure ISO date/time via the appropriate registrar.

**3. `QuantityFormatter` exists, yet the controller still ignores it on submit. Where do you check?** First verify whether the formatter was registered in the **MVC FormatterRegistry** or only in another bean/service; next verify the request type and property type.

**4. What does `new DefaultFormattingConversionService(false)` do, and what must you watch out for?** It disables registering default formatters so you can define rules explicitly; you must re-register any needed formatters/annotation formatters and test affected types.

**5. Does successfully parsing `"0,00"` mean business logic accepts it?** No. Parsing confirms representability and data type; validators/domain logic check conditions such as positive quantity.

**6. With `@NumberFormat` on a property, will calling `conversionService.convert(text, BigDecimal.class)` directly read that annotation?** No. That call does not identify the property carrying the annotation; binding with field metadata is what enables annotation-driven formatters to operate.

## References

- [Spring Framework — Field Formatting, Formatter SPI, FormatterRegistry, AnnotationFormatterFactory](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework — Configuring a Global Date and Time Format](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format-configuring-formatting-globaldatetimeformat.html)
- [Spring MVC — Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — DefaultFormattingConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
- [Spring Boot — Servlet Web Applications: Type Conversion and Formatting](https://docs.spring.io/spring-boot/reference/web/servlet.html)
