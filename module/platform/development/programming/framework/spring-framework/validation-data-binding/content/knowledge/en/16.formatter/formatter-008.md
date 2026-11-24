# AnnotationFormatterFactory and Creating Custom Formatting Annotations in Spring

## 1. Problem and Role of Annotation Formatters

Spring has two foundational SPIs for text formatting: `Printer<T>` to print Java values into strings and `Parser<T>` to read strings into Java values. `Formatter<T>` combines both directions. They are especially useful when applications need to convert `Locale`-dependent data such as dates, numbers, and monetary amounts.

A single Java type may appear on multiple fields while each field has different rules. For example, three `BigDecimal` properties might require 2, 4, and 3 decimal places respectively. A single formatter registered globally for `BigDecimal` cannot tell which rule the current field needs; creating a separate wrapper type per field fragments the model.

`AnnotationFormatterFactory<A>` solves this by connecting an annotation on a field/parameter to a parser and printer. The annotation holds configuration; the factory reads the annotation instance and field type and returns the appropriate implementation. When the `TypeDescriptor` of a conversion carries the annotation, `FormattingConversionService` can select the formatter from that metadata.

In this lesson we create the `@DecimalPlaces(value)` annotation for `BigDecimal` to specify the number of decimal places:

| Field | Annotation | Input/output in Locale.US |
| --- | --- | --- |
| subtotal | @DecimalPlaces(2) | 1,234.50 |
| unitPrice | @DecimalPlaces(4) | 1,234.5000 |
| taxRate | @DecimalPlaces(3) | 0.082 |

This is an example input and presentation convention. It is not a universal rounding or accounting rule for every currency or domain.

## 2. Core APIs

### 2.1. Printer, Parser, and Formatter

The contracts in Spring:

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

`Formatter` covers both input and display directions, receiving `Locale` on every invocation. Because `Locale` is a method parameter, there is no need to store a request's locale in a mutable field on a singleton formatter.

### 2.2. AnnotationFormatterFactory<A>

The factory belongs to package `org.springframework.format`. Key methods:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();

    Printer<?> getPrinter(A annotation, Class<?> fieldType);

    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

| Method | Role |
| --- | --- |
| getFieldTypes() | Declares the field types supported by the factory |
| getPrinter(annotation, fieldType) | Creates a printer for a field carrying the annotation |
| getParser(annotation, fieldType) | Creates a parser for a field carrying the annotation |

`A` is the concrete annotation type. Spring supplies the annotation instance attached to the target and the corresponding field type. The factory does not activate automatically just because the annotation exists; it must be registered with the `FormatterRegistry`/`FormattingConversionService` used in the conversion flow.

### 2.3. TypeDescriptor as the Metadata Bridge

`TypeDescriptor` describes source/target types more richly than `Class<?>`: beyond the raw type, a descriptor can carry annotation metadata obtained from a `Field` or `MethodParameter`. For example:

~~~java
Field field = InvoiceForm.class.getDeclaredField("subtotal");
TypeDescriptor descriptor = new TypeDescriptor(field);
~~~

This descriptor describes `BigDecimal` and can read `@DecimalPlaces(2)`. If you only construct `TypeDescriptor.valueOf(BigDecimal.class)`, field-specific metadata does not exist; the factory cannot know whether the field needs scale 2 or scale 4.

## 3. Designing the Annotation

File `DecimalPlaces.java`:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
public @interface DecimalPlaces {
    int value() default 2;
}
~~~

Rationale:

- `RUNTIME` so reflection and `TypeDescriptor` can read the annotation while the application runs.
- `FIELD` supports placing the annotation directly on fields.
- `METHOD` and `PARAMETER` allow usage in other locations if the integration path constructs appropriate descriptors; the runnable example in this lesson uses `FIELD`.
- `value` is the number of digits after the decimal point, defaulting to 2.

The annotation does not enforce value bounds by itself. Allowing 0 to 8 digits, for example, is an application policy; the factory/formatter must validate the value so misconfiguration does not silently enter the system.

## 4. Writing Formatter<BigDecimal>

File `DecimalPlacesFormatter.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class DecimalPlacesFormatter
        implements Formatter<BigDecimal> {

    private final int scale;

    public DecimalPlacesFormatter(int scale) {
        if (scale < 0 || scale > 8) {
            throw new IllegalArgumentException(
                    "Scale must be between 0 and 8");
        }
        this.scale = scale;
    }

    private DecimalFormat newFormat(Locale locale) {
        String pattern = scale == 0
                ? "#,##0"
                : "#,##0." + "0".repeat(scale);

        DecimalFormat format = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format;
    }

    @Override
    public String print(BigDecimal value, Locale locale) {
        if (value == null) {
            return "";
        }
        return newFormat(locale).format(value);
    }

    @Override
    public BigDecimal parse(String text, Locale locale) {
        if (text == null || text.isBlank()) {
            return null;
        }

        String candidate = text.trim();
        ParsePosition position = new ParsePosition(0);
        Number parsed = newFormat(locale).parse(candidate, position);

        if (!(parsed instanceof BigDecimal decimal)
                || position.getIndex() != candidate.length()
                || position.getErrorIndex() >= 0) {
            throw new IllegalArgumentException("Invalid decimal input");
        }

        return decimal.setScale(scale, RoundingMode.UNNECESSARY);
    }
}
~~~

Intentional design choices:

1. `scale` is `final`, so the formatter configuration is immutable after construction.
2. `DecimalFormat` is created fresh on every `parse`/`print` call. `DecimalFormat` is mutable and unsafe to share concurrently across requests.
3. `DecimalFormatSymbols` is taken from the passed-in `Locale`, rather than relying on the machine's default locale.
4. `setParseBigDecimal(true)` preserves decimal precision instead of parsing via `Double`.
5. `ParsePosition` verifies that the entire input was consumed. `"12abc"` is not accepted merely because prefix `"12"` parses.
6. `setScale` with `UNNECESSARY` rejects input having more decimal places than the annotation allows. Whether to reject or round input is a business decision; do not let `DecimalFormat` decide silently in place of the API contract.

This example uses `HALF_UP` during `print` and rejects input exceeding `scale` precision during `parse`. The two directions may have different policies, provided they are explicitly documented and tested. If the domain requires uniform or currency-specific rounding, place those rules in the appropriate domain/service layer.

## 5. Creating AnnotationFormatterFactory

File `DecimalPlacesAnnotationFormatterFactory.java`:

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.format.AnnotationFormatterFactory;
import org.springframework.format.Parser;
import org.springframework.format.Printer;

public final class DecimalPlacesAnnotationFormatterFactory
        implements AnnotationFormatterFactory<DecimalPlaces> {

    @Override
    public Set<Class<?>> getFieldTypes() {
        return Set.of(BigDecimal.class);
    }

    @Override
    public Printer<?> getPrinter(
            DecimalPlaces annotation, Class<?> fieldType) {
        return new DecimalPlacesFormatter(annotation.value());
    }

    @Override
    public Parser<?> getParser(
            DecimalPlaces annotation, Class<?> fieldType) {
        return new DecimalPlacesFormatter(annotation.value());
    }
}
~~~

The factory declares support only for `BigDecimal`. Both `Printer` and `Parser` use a formatter configured from the annotation's `value`. Returning two separate instances is fine since the two directional APIs are independent; in this example the formatter holds only immutable `scale` and creates `DecimalFormat` locally.

Do not declare `Number.class` if the implementation does not properly handle every `Number` subclass. `getFieldTypes` is the factory's contract, so it must accurately reflect the types the parser/printer truly support.

## 6. Applying the Annotation to the Model

File `InvoiceForm.java`:

~~~java
import java.math.BigDecimal;

public class InvoiceForm {

    @DecimalPlaces(2)
    private BigDecimal subtotal;

    @DecimalPlaces(4)
    private BigDecimal unitPrice;

    @DecimalPlaces(3)
    private BigDecimal taxRate;

    public BigDecimal getSubtotal() { return subtotal; }
    public void setSubtotal(BigDecimal value) { this.subtotal = value; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal value) { this.unitPrice = value; }

    public BigDecimal getTaxRate() { return taxRate; }
    public void setTaxRate(BigDecimal value) { this.taxRate = value; }
}
~~~

The Java type is `BigDecimal` in all three cases, yet each field carries its own annotation instance. Metadata is read when Spring conversion processes the field's descriptor. Formatting annotations belong on DTOs/forms or presentation-responsible properties; avoid coupling persistence entities to a specific UI's presentation conventions.

If the annotation is placed on a getter rather than a field, ensure the property accessor metadata Spring inspects can actually see that annotation. Avoid putting the annotation on a field while constructing descriptors from another accessor without understanding how introspection merges metadata.

## 7. Registering the Factory

### 7.1. Manual registration

~~~java
FormattingConversionService conversionService =
        new FormattingConversionService();

conversionService.addFormatterForFieldAnnotation(
        new DecimalPlacesAnnotationFormatterFactory());
~~~

This configures a directly instantiated conversion service. Code using this service must actually invoke that configured instance.

### 7.2. Registering for Spring MVC

In an MVC application, you can use `WebMvcConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldAnnotation(
                new DecimalPlacesAnnotationFormatterFactory());
    }
}
~~~

Spring MVC calls `addFormatters` to configure the registry used for conversion/formatting in binders. With Spring Boot MVC, `WebMvcConfigurer` is usually the right way to extend existing configuration; do not replace the entire MVC infrastructure just to add a factory.

Registering a converter in a test-created `FormattingConversionService` does not prove production MVC uses that same service. Always verify the active registry along the real request path.

## 8. Using TypeDescriptor to Parse and Print by Field

The snippet below creates a descriptor from the `subtotal` field:

~~~java
Field field = InvoiceForm.class.getDeclaredField("subtotal");
TypeDescriptor fieldType = new TypeDescriptor(field);
~~~

Because the descriptor carries `@DecimalPlaces(2)`, `FormattingConversionService` can select the corresponding parser/printer:

~~~java
LocaleContextHolder.setLocale(Locale.US);
try {
    BigDecimal parsed = (BigDecimal) conversionService.convert(
            "1,234.50",
            TypeDescriptor.valueOf(String.class),
            fieldType);

    String printed = (String) conversionService.convert(
            new BigDecimal("1234.5"),
            fieldType,
            TypeDescriptor.valueOf(String.class));

    System.out.println(parsed.toPlainString());
    System.out.println(printed);
} finally {
    LocaleContextHolder.resetLocaleContext();
}
~~~

`LocaleContextHolder` is set for deterministic demo output and reset in `finally`. During a normal MVC request, locale context is managed by the framework across the request lifecycle. Never store the current `Locale` in a field on a singleton formatter.

Expected output:

~~~text
1234.50
1,234.50
~~~

When converting using the field descriptor, the factory knows the field's annotation. Passing only `BigDecimal.class` drops field metadata, so annotation-based rules cannot be selected.

## 9. Standalone Runnable Example with Java 17+ and Gradle

Create a project with the files: `DecimalPlaces.java`, `DecimalPlacesFormatter.java`, `DecimalPlacesAnnotationFormatterFactory.java`, `InvoiceForm.java`, and `AnnotationFormatterFactoryDemo.java`. Place them in the same package (default package in the example below).

`settings.gradle`:

~~~groovy
rootProject.name = 'annotation-formatter-factory-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'AnnotationFormatterFactoryDemo'
}
~~~

`AnnotationFormatterFactoryDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.support.FormattingConversionService;

public class AnnotationFormatterFactoryDemo {

    public static void main(String[] args) throws Exception {
        FormattingConversionService service =
                new FormattingConversionService();

        service.addFormatterForFieldAnnotation(
                new DecimalPlacesAnnotationFormatterFactory());

        Field subtotalField =
                InvoiceForm.class.getDeclaredField("subtotal");
        TypeDescriptor subtotalType =
                new TypeDescriptor(subtotalField);

        Field unitPriceField =
                InvoiceForm.class.getDeclaredField("unitPrice");
        TypeDescriptor unitPriceType =
                new TypeDescriptor(unitPriceField);

        LocaleContextHolder.setLocale(Locale.US);
        try {
            BigDecimal subtotal = (BigDecimal) service.convert(
                    "1,234.50",
                    TypeDescriptor.valueOf(String.class),
                    subtotalType);

            BigDecimal unitPrice = (BigDecimal) service.convert(
                    "1,234.5000",
                    TypeDescriptor.valueOf(String.class),
                    unitPriceType);

            String subtotalText = (String) service.convert(
                    new BigDecimal("1234.5"),
                    subtotalType,
                    TypeDescriptor.valueOf(String.class));

            String unitPriceText = (String) service.convert(
                    new BigDecimal("1234.5"),
                    unitPriceType,
                    TypeDescriptor.valueOf(String.class));

            System.out.println("subtotal=" + subtotal.toPlainString());
            System.out.println("unitPrice=" + unitPrice.toPlainString());
            System.out.println("subtotalText=" + subtotalText);
            System.out.println("unitPriceText=" + unitPriceText);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Run from the project directory with JDK 17+:

~~~bash
gradle -q run
~~~

If using the Gradle Wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. Maven Central access is needed if dependencies are not yet cached.

Expected stdout:

~~~text
subtotal=1234.50
unitPrice=1234.5000
subtotalText=1,234.50
unitPriceText=1,234.5000
~~~

The example shows a single factory driving two fields of the same type with different annotation values. `AnnotationFormatterFactoryDemo.java` is not standalone on its own: it requires the four companion files in the same package as listed.

## 10. How Spring Selects Factories and Limitations

A factory applies only when all of the following conditions hold:

1. The annotation has runtime retention.
2. The annotation resides in metadata readable by the conversion's descriptor.
3. The source/target `TypeDescriptor` contains the matching annotation.
4. The field type belongs to the set returned by `getFieldTypes()`.
5. The factory is registered in the active `FormatterRegistry`.
6. Execution goes through the conversion service owning that registry.

When multiple factories or formatters could match, avoid ambiguous configuration and test selection order/behavior in your specific Spring version. Do not rely on component-scan order as a contract.

An annotation on a `List<BigDecimal>` field does not automatically mean the factory supports annotations on individual `BigDecimal` elements. Field type and element type live at different metadata levels. If you want to format elements via type-use annotations, design the annotation targets carefully and inspect `TypeDescriptor` at the element level; do not extrapolate from a field formatter example to assume automatic support for every generic element.

`AnnotationFormatterFactory` handles annotation-driven formatting. It does not replace `Converter` for all conversions, nor does it replace Bean Validation: a string can parse into a `BigDecimal` and still violate business constraints.

## 11. Custom Annotation Formatter or Built-In Mechanisms?

Spring already provides `@DateTimeFormat` and `@NumberFormat`. Use them when common rules already cover your needs.

| Need | Mechanism to Consider |
| --- | --- |
| ISO dates or patterns | `@DateTimeFormat` |
| Common numbers, currencies, percentages | `@NumberFormat` |
| Custom parse/print rules driven by a custom annotation | `AnnotationFormatterFactory` |
| Converting a pair of types without printing | `Converter<S,T>` |
| Conversions depending on complex generics/metadata | `GenericConverter` / `ConditionalGenericConverter` |
| Business rules after parsing | `Validator` / Jakarta Bean Validation / service |

`AnnotationFormatterFactory` fits when a field needs formatter configuration declared directly on the model. If rules depend on currency, tenant, or policies that change over time, consider moving policy into an appropriate layer rather than cramming everything into static annotations.

## 12. Locale, Thread Safety, and Performance

`FormattingConversionService` is typically shared across the application context. Factories and formatters must therefore be safe for concurrent multi-threaded calls.

- Keep formatter configuration immutable, e.g., `scale` in a `final` field.
- Never store the latest parsed value, `Locale`, request, `BindingResult`, or `WebDataBinder` in fields.
- Construct mutable `DecimalFormat` instances fresh on every call.
- Use the `Locale` passed into the method rather than the implicit system default locale.
- Do not make database/HTTP calls to decide how to parse strings.
- Do not swallow parse errors into `null`; empty and malformed are two distinct cases.
- Avoid caching formatters if caching risks sharing mutable objects or is unnecessary.

If you want to cache formatters by scale, cache only immutable formatters and ensure all mutable helpers are still created per invocation. Benchmark before optimizing allocations; correctness outweighs saving one small object.

## 13. Comprehensive Testing

### 13.1. Parse and print

For `@DecimalPlaces(2)`, test:

- Parse `"1,234.50"` into `BigDecimal` `1234.50`.
- Print `BigDecimal` `1234.5` as `"1,234.50"`.
- Parsing `"12abc"` must fail because of the suffix.
- Parsing `"1,234.567"` must obey the scale policy (rejected in this example).
- Empty string returns `null` per the defined contract.
- Negative scale or scale above 8 is rejected.

For `@DecimalPlaces(4)`, the same factory must parse/print four decimal places. Assert the exact `BigDecimal` scale if the contract distinguishes `1234.50` from `1234.5000`.

### 13.2. Locale

The same number can be written differently under `Locale.US` and `Locale.GERMANY`. Set the locale per test and reset the context afterward. Do not assume `"1.234,50"` is valid in all locales.

System-to-system APIs should generally use stable, locale-independent wire formats. User-locale formatting belongs in UIs, not necessarily in storage or external integrations.

### 13.3. Spring MVC integration

Use `MockMvc` or real requests to verify:

- `@InitBinder`/`FormatterRegistry` has registered the factory.
- Annotated `@ModelAttribute` fields parse properly.
- Returned values print properly when rendering forms.
- Parse errors are added to `BindingResult` via MVC's path.
- Two fields with different scales do not pick up each other's configuration.
- Requests with different locales do not leak state.

### 13.4. Concurrency

Use the same `FormattingConversionService` and registered factory from multiple threads. Each task parses/prints its own input and compares output. Verify thread cleanup for `LocaleContextHolder`. Never share `DecimalFormat` across tasks. Concurrency tests supplement code review; they do not conclusively prove race conditions are impossible.

## 14. Common Mistakes

**Annotation is not applied:** check `RUNTIME` retention, targets, field descriptor, and factory registration.

**Factory is not selected:** check `getFieldTypes`, the actual field type, and whether conversion uses a `TypeDescriptor` built from the field.

**Creating a descriptor from `BigDecimal.class` only:** that descriptor does not carry the property's specific annotation.

**Parsing prefix while accepting suffix:** check that `ParsePosition` consumed the entire string.

**Shared `DecimalFormat` causing concurrent corruption:** create `DecimalFormat` per call.

**One request's locale affecting another:** do not store locale in formatter fields; use the `Locale` parameter and manage context lifecycle properly.

**Turning invalid input into `null`:** distinguish empty strings from malformed input; let exceptions propagate for the binder to handle.

**Factory advertising too many types:** `getFieldTypes` must contain only field types the implementation actually supports.

**Unclear rounding:** define parse and print policies separately and state the rounding mode explicitly.

**Confusing formatting with validation:** successful parsing does not mean the value is business-valid.

**Writing a custom annotation for built-in needs:** check `@DateTimeFormat` and `@NumberFormat` before building a custom factory.

## 15. Implementation Checklist

1. Do the annotation's name and attributes clearly express the policy?
2. Is retention `RUNTIME`?
3. Do annotation targets match the field/parameter sites in use?
4. Does the factory declare accurate field types?
5. Do `getPrinter` and `getParser` use the annotation instance?
6. Does the formatter handle `null`, empty, malformed input, locale, and rounding clearly?
7. Does the parser verify the entire string was consumed?
8. Are mutable helpers created fresh per invocation?
9. Do the factory and formatter keep configuration immutable?
10. Is the factory registered in the active MVC `FormattingConversionService`?
11. Does `TypeDescriptor` retain the field's annotations?
12. Are there parse and print tests for multiple annotation values?
13. Are there tests for locales, malformed input, and concurrency?
14. Are there integration tests through `MockMvc`/`WebDataBinder`?
15. Have you cross-checked Javadoc for your exact Spring version?

## 16. Official Documentation

- [Spring Framework – Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [AnnotationFormatterFactory Javadoc (Spring 6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html)
- [Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Formatter.html)
- [Printer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Printer.html)
- [Parser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Parser.html)
- [FormatterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [FormattingConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/support/FormattingConversionService.html)
- [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Java DecimalFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [Java Locale API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)

**Core principle:** `AnnotationFormatterFactory` maps annotation metadata to a parser/printer matching the field type. For it to work properly, the annotation must have runtime retention, the factory must be registered in the right registry, `TypeDescriptor` must carry the annotation, and the formatter must handle `Locale` and mutable parsing state safely. Test both parse/print and the exact binding path your application uses.
