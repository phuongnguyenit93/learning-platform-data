# FormattingConversionService Combining Formatter and Converter

## 1. Problem: One Place for Type Conversion and Data Formatting

In a Spring application, data regularly crosses multiple boundaries: HTTP form/query parameters, model objects, services, and rendered views. A value may need to be converted into a Java type and then represented back as a user-friendly string.

For example:

- Client sends `"C-2048"`; the model expects domain type `CustomerId`.
- Form sends `"03/2026"`; the model expects `YearMonth`.
- When re-rendering the form, `YearMonth.of(2026, 3)` needs to be printed as `"03/2026"`.
- One `BigDecimal` field may use the number pattern `#,##0.00` while another field uses its own formatting rule.

Spring has two complementary SPIs:

- **`Converter<S, T>`** performs general-purpose conversion from a source type to a target type.
- **`Formatter<T>`** combines parsing input strings into objects and printing objects into strings; it fits UI display data and can accept `Locale`.

**`FormattingConversionService`** bridges these two worlds. It implements `ConversionService` to perform conversions and `FormatterRegistry` to register formatters, parsers/printers, converters, and annotation-based formatter factories. This allows an application to declare formatting/conversion rules in one shared registry rather than scattering configuration across controllers.

Lesson objectives:

1. Distinguish `Converter`, `Formatter`, `Printer`, and `Parser`.
2. Understand the relationship between `FormattingConversionService` – `FormatterRegistry` – `ConversionService`.
3. Register both a converter and a formatter into the same service.
4. Use `Locale` during parse/print and understand annotation formatting.
5. Integrate the registry into Spring MVC using `WebMvcConfigurer#addFormatters`.
6. Test bidirectional conversion, invalid input, and how Spring DataBinder uses the service.

Examples use **Java 17+ and Spring Framework 6.2.x**. The core APIs have remained stable in recent Spring releases; use Spring Boot's BOM/plugin if your project manages dependencies with Boot.

## 2. Converter and Formatter Solve Two Different Needs

### Converter: general type conversion

`Converter<S, T>` has one method:

~~~java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
~~~

This is the conceptual SPI signature. Converter focuses on one direction: from `S` to `T`. For example `String → CustomerId`, `String → UUID`, `Long → InvoiceNumber`.

A converter can be used in many places unrelated to the UI. It does not accept `Locale` directly and has no contract for printing objects into strings.

### Formatter: parse and print for display data

`Formatter<T>` combines two interfaces:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException;
}
~~~

The signatures above illustrate the SPI. `parse` takes a client string and creates an object; `print` takes an object and returns a display string. Both include `Locale`, making them well suited for dates, numbers, currencies, or language/region-dependent formats.

| Need | Converter | Formatter |
| --- | --- | --- |
| One type to another | Yes | Can participate via parse/print when String is involved |
| Single conversion direction | Ideal | Usually provides both parse and print |
| Needs Locale | No direct Locale parameter | Built in |
| Web forms, data display | Used for general conversion logic | Ideal for UI strings |
| Domain value objects | Very suitable | Suitable when parsing/printing value objects |

**Selection rule:** use `Converter` for general-purpose type conversion; use `Formatter` when you need to parse and print values according to UI/locale formatting. Do not write a formatter merely to replace a simple one-way converter if the application does not need parse/print.

## 3. What is FormattingConversionService?

Key components:

| Component | Responsibility |
| --- | --- |
| `ConversionService` | API to query whether conversion is possible and perform conversions |
| `ConverterRegistry` | API to register converters, converter factories, and generic converters |
| `FormatterRegistry` | API to register formatters, parsers/printers, and annotation formatters |
| `FormattingConversionService` | Combines registry and conversion service; provides infrastructure to select formatters/converters |
| `DefaultFormattingConversionService` | Common implementation preinstalled with default formatters and supporting custom extensions |
| `FormatterRegistrar` | Packages a group of converters/formatters for registration into a registry |

`FormattingConversionService` implements both `ConversionService` and `FormatterRegistry`. This is the meeting point: a single object accepts converter and formatter registrations and is then used via `convert(...)`.

### Common APIs on FormatterRegistry

~~~java
void addConverter(Converter<?, ?> converter);
void addFormatter(Formatter<?> formatter);
void addFormatterForFieldType(
        Class<?> fieldType, Formatter<?> formatter);
void addFormatterForFieldAnnotation(
        AnnotationFormatterFactory<? extends Annotation> factory);
~~~

These are abbreviated signatures illustrating the API groups; methods inherited from `ConverterRegistry` can also register `ConverterFactory` and `GenericConverter`. Overloads exist for registering by field type or `Printer`/`Parser` pairs.

Key points to remember:

- `addConverter(...)` registers a general conversion.
- `addFormatter(...)` registers a formatter for the type declared by the formatter.
- `addFormatterForFieldType(...)` binds a formatter to a specific field type.
- `addFormatterForFieldAnnotation(...)` binds formatting logic to an annotation.
- `ConversionService.convert(...)` performs conversions; `FormatterRegistry` is where configuration happens.

### Why the word "Default"?

`DefaultFormattingConversionService` is the common practical implementation. It inherits the conversion infrastructure and automatically registers default formatters for common types. Depending on constructor/configuration, an application can toggle registration of default formatters and then add custom rules.

In most applications, starting with `new DefaultFormattingConversionService()` is convenient because common conversions/formatters such as numbers and dates are pre-registered. If you want full control over the list, you can instantiate an appropriate `FormattingConversionService`/`GenericConversionService` and register only what is needed.

## 4. Java 17+ Example: Same Service Accepting Converter and Formatter

Let's build a small application with two domain types:

- `CustomerId`: a value object created from the string `C-2048`.
- `YearMonth`: a time type to accept and print using the pattern `MM/yyyy`.

The Converter for `CustomerId` is a general conversion. The Formatter for `YearMonth` handles both parse and print.

### 4.1. Project structure

~~~text
formatting-conversion-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/FormattingDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'formatting-conversion-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.FormattingDemo'
}
~~~

`spring-context` pulls in the modules needed for Spring core/formatting. The example uses Spring Framework 6.2.14 for a pinned environment. In a Spring Boot project, let the Boot BOM manage compatible Spring versions.

### 4.2. Runnable Java file

Create `src/main/java/demo/FormattingDemo.java`:

~~~java
package demo;

import java.text.ParseException;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormattingDemo {

    public record CustomerId(long value) {}

    public static final class CustomerIdConverter
            implements Converter<String, CustomerId> {

        private static final Pattern FORMAT =
                Pattern.compile("C-(\\d+)");

        @Override
        public CustomerId convert(String source) {
            if (source == null) {
                return null;
            }

            Matcher matcher = FORMAT.matcher(source.trim());
            if (!matcher.matches()) {
                throw new IllegalArgumentException(
                        "Customer ID must match C-<digits>");
            }

            return new CustomerId(
                    Long.parseLong(matcher.group(1)));
        }
    }

    public static final class YearMonthFormatter
            implements Formatter<YearMonth> {

        private DateTimeFormatter formatter(Locale locale) {
            return DateTimeFormatter.ofPattern(
                    "MM/uuuu", locale);
        }

        @Override
        public YearMonth parse(String text, Locale locale)
                throws ParseException {
            try {
                return YearMonth.parse(
                        text.trim(), formatter(locale));
            } catch (RuntimeException ex) {
                ParseException parseException =
                        new ParseException(
                                "Month must match MM/yyyy", 0);
                parseException.initCause(ex);
                throw parseException;
            }
        }

        @Override
        public String print(YearMonth object, Locale locale) {
            return formatter(locale).format(object);
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
            new DefaultFormattingConversionService();

        service.addConverter(new CustomerIdConverter());
        service.addFormatter(new YearMonthFormatter());

        CustomerId customerId =
                service.convert("C-2048", CustomerId.class);

        YearMonth month =
                service.convert("03/2026", YearMonth.class);

        String printedMonth =
                service.convert(month, String.class);

        System.out.println("customerId=" + customerId.value());
        System.out.println("yearMonth=" + month);
        System.out.println("printedMonth=" + printedMonth);
    }
}
~~~

This is a complete Java program in a single file. Nested classes are used to keep the example compact; in larger applications, each converter/formatter can be placed in its own file.

### 4.3. Running the program

Use the Gradle Wrapper at the root directory:

~~~bash
./gradlew run
~~~

On Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout of the Java class, omitting Gradle logs:

~~~text
customerId=2048
yearMonth=2026-03
printedMonth=03/2026
~~~

The output shows the same `DefaultFormattingConversionService` handling two different extension types:

1. `String → CustomerId` goes through `CustomerIdConverter`.
2. `String → YearMonth` goes through `YearMonthFormatter.parse(...)`.
3. `YearMonth → String` goes through `YearMonthFormatter.print(...)`.

That is the point of combining converters and formatters in one conversion service: callers simply use the `convert` API, while the registry selects the right strategy based on source and target types.

## 5. How Does Locale Affect Formatter?

`Formatter` receives `Locale` in both `parse` and `print`. With the date pattern `MM/yyyy`, the output happens not to vary much across locales, whereas number/currency formats differ much more noticeably:

- Some locales use a comma as the decimal separator.
- Other locales use a dot as the decimal separator.
- Thousands grouping separators and currency symbols can also differ.

Example using `NumberFormat`:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
Number number = format.parse(text);
String rendered = format.format(number);
~~~

This is an illustrative fragment requiring `java.text.NumberFormat` import and `ParseException` handling. It shows why formatters should use the passed-in locale instead of hardcoding a decimal separator.

### Do not assume Locale in direct ConversionService calls

`Formatter` has `Locale`, but the common overload `conversionService.convert(source, targetClass)` has no locale parameter. In a web environment, the formatter is invoked through Spring's formatting infrastructure and the request's locale context. When called directly from non-web code, the active locale may rely on the context holder or default locale depending on implementation and invocation.

For `YearMonthFormatter` in section 4, the numeric pattern `MM/uuuu` does not change output by language, so stdout is stable. For currencies/display numbers, test under your target locales in the actual runtime context.

If you need to pass a locale explicitly in standalone code, you can call the formatter directly:

~~~java
YearMonthFormatter formatter = new YearMonthFormatter();
YearMonth parsed = formatter.parse(
        "03/2026", Locale.US);
String text = formatter.print(parsed, Locale.US);
~~~

This fragment uses the nested class from section 4. It allows direct control of the locale without depending on a request context.

## 6. Annotation-Driven Formatting

There are cases where you do not want to register a single formatter for every property of the same type. Instead, **annotations on fields/parameters** determine how formatting works.

Spring supports familiar annotations:

- `@NumberFormat`: formats numbers.
- `@DateTimeFormat`: formats dates/times.
- A custom annotation can be wired to a formatter via `AnnotationFormatterFactory`.

Example:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate invoiceDate;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public LocalDate getInvoiceDate() {
        return invoiceDate;
    }

    public void setInvoiceDate(LocalDate invoiceDate) {
        this.invoiceDate = invoiceDate;
    }
}
~~~

This is a complete JavaBean for two properties. When `DefaultFormattingConversionService` (or formatting infrastructure with the corresponding formatters registered) is used with `DataBinder`, the annotations supply metadata to pick the right format for each field.

For example, `@DateTimeFormat(iso = ISO.DATE)` uses the ISO date format `yyyy-MM-dd`. `@NumberFormat(pattern = "#,##0.00")` sets a number pattern; grouping/decimal separators still depend on the active locale.

**Note:** annotations take effect when conversion goes through Spring's formatting mechanism that inspects field/parameter metadata. Calling `convert("...", BigDecimal.class)` directly passes only the target class, providing no annotation context for a specific field. To apply annotations on properties, the binder needs to work with `TypeDescriptor`/property metadata.

## 7. TypeDescriptor Tells the Formatter Which Field Is Being Processed

`ConversionService` has overloads accepting `TypeDescriptor`. A descriptor provides information about the type and declaration site, including generics, annotations, and property metadata.

Example of obtaining a field's descriptor:

~~~java
Field field = InvoiceForm.class.getDeclaredField("amount");
TypeDescriptor amountDescriptor = new TypeDescriptor(field);

Object amount = service.convert(
        "1,234.50",
        TypeDescriptor.valueOf(String.class),
        amountDescriptor);
~~~

This **fragment** requires importing `java.lang.reflect.Field` and `org.springframework.core.convert.TypeDescriptor`; the `service` variable must be a conversion service with the appropriate default formatters registered. It illustrates why passing only `BigDecimal.class` may not be enough to apply field annotations.

When a binder processes a property, Spring can construct a descriptor tied to the field and use annotation metadata to select the formatter. This is the underlying mechanism behind annotation-driven formatting.

### AnnotationFormatterFactory

To support a custom annotation, implement `AnnotationFormatterFactory<A>`:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {

    Set<Class<?>> getFieldTypes();

    Printer<?> getPrinter(A annotation, Class<?> fieldType);

    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

This is the abbreviated SPI signature. How it works:

1. Declare an annotation with `RetentionPolicy.RUNTIME` and targets like FIELD/PARAMETER.
2. `getFieldTypes()` returns the property types that can use the annotation.
3. `getPrinter(...)` provides how to print the object into a string.
4. `getParser(...)` provides how to parse the string into an object.
5. Register the factory via `FormatterRegistry.addFormatterForFieldAnnotation(...)`.

This is the right choice when the annotation carries metadata such as pattern, precision, or unit. There is no need to create a factory if you only have one simple formatter for a type; `addFormatter(...)` or `addFormatterForFieldType(...)` is easier.

## 8. FormatterRegistrar: Grouping Converter and Formatter Registrations

`FormatterRegistrar` allows grouping related rules into a single registration unit:

~~~java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
~~~

This is the SPI signature.

Example:

~~~java
public class DomainFormattingRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new FormattingDemo.CustomerIdConverter());
        registry.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }
}
~~~

This class compiles when placed in package `demo` with `FormatterRegistrar`/`FormatterRegistry` imported. It registers the two components written in section 4.

A registrar is useful when:

- There are multiple formatters for the same domain group (currencies, business dates, identifiers).
- You need to add converters and formatters as a configuration module.
- A formatter needs to be registered for a field type different from the generic type declared on the formatter.
- You want to reuse conversion configuration across multiple application contexts.

A registrar **does not perform conversions itself**; it only adds rules to the passed-in registry. The service then applies those rules.

## 9. Integrating into Spring MVC

Spring MVC has its own formatting conversion service for binding request parameters, path variables, form model attributes, and other type conversion points. To register custom converters/formatters, implement `WebMvcConfigurer`:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new FormattingDemo.CustomerIdConverter());
        registry.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }
}
~~~

This is a complete configuration class for Spring MVC. In Spring Boot Web MVC, the configuration is discovered by component scanning when its package is under the application root.

Once registered, controllers can receive target types directly:

~~~java
@GetMapping("/customers/{id}")
ResponseEntity<?> find(@PathVariable CustomerId id) {
    return ResponseEntity.ok(id.value());
}

@PostMapping("/invoices")
String save(@ModelAttribute InvoiceForm form) {
    // form.amount and form.invoiceDate have already been bound/converted.
    return "success";
}
~~~

This is a controller fragment requiring MVC annotation imports and `CustomerId`/`InvoiceForm` declarations. `/customers/C-2048` can be converted to `CustomerId` via the registered converter. For forms, the corresponding formatter/annotation is used during binding.

### Registering via FormatterRegistrar in MVC

If the rule group is large, use a registrar:

~~~java
@Configuration
public class WebFormattingConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        new DomainFormattingRegistrar()
                .registerFormatters(registry);
    }
}
~~~

This is an alternative to registering each component directly. Use only **one appropriate configuration** in the application; do not simultaneously register manually and via a registrar for the same converters/formatters.

## 10. DataBinder Using FormattingConversionService

`DataBinder` uses a conversion service to convert input values before assigning them to properties. Because `FormattingConversionService` is also a `ConversionService`, it can be configured on a standalone binder:

~~~java
FormattingConversionService conversionService =
        new DefaultFormattingConversionService();

conversionService.addConverter(
        new FormattingDemo.CustomerIdConverter());
conversionService.addFormatter(
        new FormattingDemo.YearMonthFormatter());

DataBinder binder = new DataBinder(form, "invoice");
binder.setConversionService(conversionService);
binder.bind(propertyValues);

BindingResult result = binder.getBindingResult();
~~~

This is a fragment; `form` must be an object with getters/setters, `propertyValues` must be valid `PropertyValues`, and `DataBinder`/`BindingResult` plus formatting APIs must be imported. In MVC, the framework already provides a built-in conversion service so you rarely need to instantiate a binder manually in controllers.

The binding flow can be understood as:

~~~text
HTTP String values
       |
       v
WebDataBinder / DataBinder
       |
       v
FormattingConversionService
       |
    +--+----------------+
    |                   |
Converter              Formatter
String -> CustomerId  String <-> YearMonth
    |                   |
    +---------+---------+
              |
       Bean property / model
              |
        BindingResult
~~~

`BindingResult` records binding/conversion errors according to the binder's mechanism. For example, `yearMonth=not-a-month` cannot produce a `YearMonth`; the controller can check `hasErrors()` and return the form or an error response.

## 11. Handling Parse/Convert Errors Properly

When a converter/formatter receives invalid input:

- `Converter` can throw an appropriate conversion exception or an exception describing the invalid input so Spring wraps it through the conversion path.
- `Formatter.parse(...)` declares `ParseException`; do not return a default object when the string is malformed.
- `DataBinder` can place conversion errors into `BindingResult` so the controller can display field-level errors.
- Calling `ConversionService.convert(...)` directly may throw `ConversionException`/`ConversionFailedException`; the caller handles it per its contract.

Example of checking an error directly:

~~~java
try {
    service.convert("not-a-month", YearMonth.class);
} catch (ConversionException ex) {
    System.out.println("Unable to convert month");
}
~~~

This fragment requires importing `org.springframework.core.convert.ConversionException` and using a service with `YearMonthFormatter` registered. The displayed message is decided by the application; do not expose raw stack traces or exception details to clients.

**Do not mix validation with formatting.** `"03/2026"` may parse validly into `YearMonth`, but a rule like "do not allow selecting a month in the past" is separate business validation. Formatters should stay focused on representation/conversion.

## 12. Thread Safety and Good Design

`ConversionService` is designed to be stateless, typically initialized at application startup and shared across many threads. `FormattingConversionService` fits that same centralized usage.

However, **custom converters/formatters must guarantee concurrency safety themselves**:

- Do not store the current input value in a field.
- Do not store `BindingResult`, request `Locale`, or the latest parse result in mutable fields.
- Use local variables inside `convert`, `parse`, and `print`.
- Shared configuration should be immutable.
- Use immutable/thread-safe APIs like `DateTimeFormatter`; avoid sharing mutable `SimpleDateFormat` across requests.
- Do not query the database or update business state inside a formatter; that is the responsibility of services/domain logic.

`YearMonthFormatter` in the example creates a `DateTimeFormatter` from locale on each call. `DateTimeFormatter` itself is immutable and thread-safe, so it can be safely reused if stored in a final field with an appropriate fixed configuration.

If a formatter depends on timezone, locale, currency unit, or user context, pass/read the context through an explicit contract. Never stash the previous request's locale in a singleton.

## 13. Converter, Formatter, and Annotation Formatter: Which One to Choose?

| Scenario | Recommended Design |
| --- | --- |
| String → CustomerId, no reverse direction needed | `Converter<String, CustomerId>` |
| String ↔ YearMonth by pattern/locale | `Formatter<YearMonth>` |
| Multiple target types in the same family | `ConverterFactory` |
| A field needs a pattern specified by an annotation | `AnnotationFormatterFactory` |
| Multiple formatters/converters in the same domain group | `FormatterRegistrar` |
| Centralized registration and use in MVC/DataBinder | `FormattingConversionService` |
| Rules specific to MVC request binding | `WebMvcConfigurer#addFormatters` |

Do not use `Formatter` just because it has "format" in its name when the problem needs neither locale nor printing. Conversely, avoid using `Converter` for display strings if the logic depends on locale or needs to convert objects back to strings.

A field type may have a default formatter, a type-registered formatter, and an annotation-bound formatter. When rules overlap, verify which converter is selected in the actual context and write tests instead of assuming precedence.

## 14. Testing Formatters and Converters

Do not test only successful conversions. Test bidirectional parse/print, locales, invalid input, and binder integration.

### JUnit 5 unit test

File `src/test/java/demo/FormattingDemoTest.java`:

~~~java
package demo;

import java.time.YearMonth;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.*;

class FormattingDemoTest {

    private final DefaultConversionService service =
            new DefaultConversionService();

    FormattingDemoTest() {
        service.addConverter(
                new FormattingDemo.CustomerIdConverter());
        service.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }

    @Test
    void convertsDomainId() {
        var id = service.convert(
                "C-2048", FormattingDemo.CustomerId.class);
        assertEquals(2048L, id.value());
    }

    @Test
    void parsesAndPrintsYearMonth() {
        YearMonth month =
                service.convert("03/2026", YearMonth.class);

        String printed = service.convert(month, String.class);

        assertEquals(YearMonth.of(2026, 3), month);
        assertEquals("03/2026", printed);
    }

    @Test
    void rejectsMalformedCustomerId() {
        assertThrows(RuntimeException.class, () ->
                service.convert(
                        "bad-id", FormattingDemo.CustomerId.class));
    }

    @Test
    void formatterCanUseExplicitLocale() throws Exception {
        var formatter = new FormattingDemo.YearMonthFormatter();
        var value = formatter.parse("03/2026", Locale.US);
        assertEquals("03/2026", formatter.print(value, Locale.US));
    }
}
~~~

The test class uses JUnit Jupiter. Add to `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

Asserting `RuntimeException` for invalid data is only used to keep the demo broad; in a real project, assert the exact specific exception after settling how the converter and Spring version wrap errors.

### Integration tests you should have

- Register both converter and formatter via `WebMvcConfigurer` and submit a form request.
- Test `@DateTimeFormat`/`@NumberFormat` on actual fields.
- Send different locales and verify corresponding parse/print behavior.
- Verify invalid formats create proper field errors in `BindingResult`.
- Confirm converters/formatters do not share mutable state across requests.
- Test the same source/target types with different field annotations if using `AnnotationFormatterFactory`.

## 15. Common Pitfalls

**Registering only Converter and forgetting Formatter.** The service converts the domain type but lacks a suitable rule to print the string. Use `Formatter` when bidirectional parse/print is needed.

**Using a fixed default Locale.** Output can be wrong for users in other locales. Use the locale parameter in Formatter instead of hardcoding display rules.

**Assuming every ConversionService has default formatters.** `GenericConversionService` and `DefaultFormattingConversionService` do not share the same initial set of converters/formatters. Choose and configure the implementation deliberately.

**Expecting annotations to work when calling convert with Class only.** Class-only calls carry no field metadata; use `TypeDescriptor` or a binder processing annotated properties.

**Putting @DateTimeFormat on a type without going through Spring binding.** The annotation does not magically enable parsing when calling `LocalDate.parse` directly; it requires a conversion service/binder with the appropriate formatter registered.

**Unintentionally overriding default rules.** When registering a formatter for a common type, check its impact on other controllers and model attributes. Use annotation-based formatting when only certain fields need a custom representation.

**Parser returning null on invalid data.** Null may be a valid value under the contract and can mask errors. Invalid input should throw an appropriate exception so the binder records it.

**Storing a mutable parser in a singleton.** For example `SimpleDateFormat` can cause race conditions. Use `DateTimeFormatter` or local instances.

**Performing business validation inside Formatter.** Formatting is conversion/representation; business rules belong in Spring Validator/Bean Validation or services.

## 16. Summary

`FormattingConversionService` combines **`ConversionService` for type conversion** with **`FormatterRegistry` for registering formatting rules**. This lets an application manage converters and formatters in one shared registry. Converters fit one-way general conversions; formatters fit locale-aware parse/print; annotation formatters handle fields needing special rules; registrars group related configurations.

In Spring MVC, register via `WebMvcConfigurer#addFormatters` so request binding, models, and view rendering share the same rules. Test both directions, locales, annotation metadata, and invalid inputs so conversion remains consistent across the application.

### Official References

- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring MVC — Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [FormattingConversionService API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html)
- [FormatterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Formatter API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
