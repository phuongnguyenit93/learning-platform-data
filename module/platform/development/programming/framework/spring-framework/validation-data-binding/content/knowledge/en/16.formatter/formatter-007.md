# Registering Formatters by Field Type or Annotation in Spring

## 1. What Is a Formatter and Why Register It?

Data submitted from forms is typically text, whereas Java models require concrete types. For example, a user submits the date `2026-11-02`, the monetary amount `$1,234.50`, or a percentage value. When redisplaying objects, the application also needs to convert Java values back into human-readable text.

Spring provides two conversion directions:

- **`Converter<S,T>`** performs one-way conversion between two Java types, such as `String → CustomerId`. Its signature does not accept `Locale`.
- **`Formatter<T>`** specializes in converting between text and objects, providing both `parse(String, Locale)` and `print(T, Locale)`. This is the natural choice when input or display depends on language, region, or formatting conventions.

A `Formatter<T>` can be registered in two ways:

1. **By field type:** every field of that type shares the formatter, e.g., all `LocalDate` fields in forms.
2. **By annotation on the field/property:** the formatter is selected when the field carries a specific annotation, e.g., `@UsdAmount` applies only to currency fields requiring USD, even if multiple fields share the `BigDecimal` type.

The two central APIs of `FormatterRegistry` are `addFormatterForFieldType(...)` and `addFormatterForFieldAnnotation(...)`. Choosing the right registration scope lets a single Java type be formatted differently according to each field's meaning without inventing multiple types solely for presentation.

## 2. The Formatter and Parser/Printer Contracts

Spring defines `org.springframework.format.Formatter<T>` as a contract combining `Printer<T>` and `Parser<T>`:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}
```

- `parse` takes text and locale and produces an object of type `T`.
- `print` takes an object and locale and produces a display string.
- `Locale` enables handling dates, numbers, and currencies according to regional conventions.
- `ParseException` represents unparseable text; when the formatter runs through the conversion infrastructure, Spring translates the failure into an appropriate conversion exception.

Formatters should have semantically symmetric parse and print. If `print` produces a string that `parse` cannot read back, form round-trips can corrupt data. Avoid manually replacing commas/dots with `String.replace` when formatting depends on locale.

## 3. Registration by Field Type: addFormatterForFieldType

Use type-based registration when all fields of the same data type share the same parse/print rules.

```java
FormatterRegistry registry = ...;
registry.addFormatterForFieldType(
    LocalDate.class,
    new IsoLocalDateFormatter()
);
```

`FormatterRegistry` belongs to `org.springframework.format`. The method `addFormatterForFieldType(Class<?>, Formatter<?>)` registers a formatter for a specific field type. Overloads exist for separate `Printer<?>` or `Parser<?>` if the application only needs one direction.

Example of an ISO date formatter:

```java
public final class IsoLocalDateFormatter
        implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text);
        } catch (DateTimeParseException ex) {
            ParseException failure =
                new ParseException("Expected ISO date yyyy-MM-dd", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return value.toString();
    }
}
```

The snippet requires importing `java.time.LocalDate`, `java.time.format.DateTimeParseException`, `java.text.ParseException`, and `java.util.Locale`. `LocalDate.toString()` uses ISO-8601, so locale does not affect the output. If localized date display is required, use a locale-appropriate `DateTimeFormatter` instead of hardcoding ISO.

**When using type-based registration:**

- Any field of matching type can use the formatter.
- It does not distinguish the business meaning of different fields of the same type.
- Configuration is simple and easy to test.
- If one field needs a different format, consider annotation-based registration or a conditional formatter rather than complicating a global type formatter.

## 4. Registration by Annotation: addFormatterForFieldAnnotation

Use this when formatting rules depend on metadata on the field/property, not merely its Java type.

For example, a form has two `BigDecimal` fields: `usdPrice` is a USD monetary amount, while `ratio` is a ratio. If you only register a formatter for `BigDecimal.class`, both receive the same formatting. An annotation lets you pick the context-appropriate formatter.

```java
registry.addFormatterForFieldAnnotation(
    new UsdAmountAnnotationFormatterFactory()
);
```

The factory implements `AnnotationFormatterFactory<A>`, where `A` is the annotation type. The factory declares:

- `getFieldTypes()`: the Java types supported by the annotation.
- `getPrinter(annotation, fieldType)`: the printer matching the annotation and field type.
- `getParser(annotation, fieldType)`: the corresponding parser.

The core methods look like:

```java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();
    Printer<?> getPrinter(A annotation, Class<?> fieldType);
    Parser<?> getParser(A annotation, Class<?> fieldType);
}
```

This is the core Spring SPI signature. The factory returns the corresponding parser/printer. If a formatter supports both directions, a single `Formatter<T>` implementation can be returned from both methods.

### The annotation must have runtime retention

The factory needs to read the annotation at runtime, so the annotation must have `RetentionPolicy.RUNTIME` and appropriate targets:

```java
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface UsdAmount {}
```

The annotation only marks which fields use the USD rule; it does not perform parse/print itself. The logic lives in `AnnotationFormatterFactory` and the formatter it supplies.

## 5. Choosing Registration by Type or by Annotation?

| Criterion | By Field Type | By Annotation |
| --- | --- | --- |
| API | `addFormatterForFieldType` | `addFormatterForFieldAnnotation` |
| Selection basis | Java type of the field | Annotation metadata and field type |
| Best suited when | Fields of the same type share uniform rules | Same Java type but different meanings/formats |
| Example | All `LocalDate` fields use ISO | `@UsdAmount BigDecimal` formats as USD |
| Configuration | Simple, broadly applied | Explicit per field |
| Risk | Rules may unintentionally apply to other fields of the same type | Missing annotation or misdeclaring supported types |

Do not put annotations on every field if the rules are uniform anyway. Conversely, when the same Java type carries different meanings, a type-based formatter may apply rules too broadly. You can register both approaches in a single service: type-based formatters handle general cases, while annotations supply specific context for marked fields.

## 6. FormattingConversionService and TypeDescriptor

`FormattingConversionService` is a `ConversionService` implementation with integrated formatting support. `DefaultFormattingConversionService` pre-registers many common converters/formatters and serves as a convenient starting point.

```java
DefaultFormattingConversionService service =
    new DefaultFormattingConversionService();

service.addFormatterForFieldType(
    LocalDate.class, new IsoLocalDateFormatter()
);
service.addFormatterForFieldAnnotation(
    new UsdAmountAnnotationFormatterFactory()
);
```

Both registration methods add formatters into one registry/service. When converting, Spring uses the type and metadata of the source/target site to pick the right rule.

### Why is TypeDescriptor important?

If you only call:

```java
service.convert("$1,234.50", BigDecimal.class);
```

the caller only supplies the target type `BigDecimal.class`. Spring has no idea the value belongs to field `usdPrice` annotated with `@UsdAmount`. Model annotations cannot appear in a class-only call.

When a binder/MVC converts a specific property, Spring can supply a `TypeDescriptor`. The descriptor describes:

- The Java type of the field.
- Generic element types or map key/value types if present.
- Annotations attached to the declaration site.
- Metadata needed by conditional converters/formatters.

Example:

```java
Field field = PriceForm.class.getDeclaredField("usdPrice");
TypeDescriptor target = new TypeDescriptor(new Property(field));

Object amount = service.convert(
    "$1,234.50",
    TypeDescriptor.valueOf(String.class),
    target
);
```

The snippet requires importing `java.lang.reflect.Field`, `org.springframework.beans.Property`, and `org.springframework.core.convert.TypeDescriptor`. Because the descriptor is built from the field, it retains the `@UsdAmount` annotation. This is the decisive difference between class-based conversion and declaration-metadata-based conversion.

**Do not expect** `convert(text, BigDecimal.class)` to automatically apply field annotations. That call discards field metadata. Use the `TypeDescriptor` overload or let `DataBinder`/MVC perform property conversion when annotation-aware formatting is required.

## 7. Runnable Java 17 Example: One Type-Based Formatter and One Annotation-Based Formatter

The program below uses Spring Framework 6.1.14 and `DefaultFormattingConversionService`. It registers:

- `IsoDateFormatter` for fields of type `LocalDate`.
- `UsdAmountFormatterFactory` for `BigDecimal` fields annotated with `@UsdAmount`.

Structure:

```text
formatter-registration-demo/
├── pom.xml
└── src/main/java/demo/FormatterRegistrationDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-registration-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/FormatterRegistrationDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Currency;
import java.util.Locale;
import java.util.Set;

import org.springframework.beans.Property;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.AnnotationFormatterFactory;
import org.springframework.format.Formatter;
import org.springframework.format.Printer;
import org.springframework.format.Parser;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class FormatterRegistrationDemo {

    @Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
    @Retention(RetentionPolicy.RUNTIME)
    public @interface UsdAmount {}

    public static final class PriceForm {
        private LocalDate deliveryDate;

        @UsdAmount
        private BigDecimal usdPrice;

        public LocalDate getDeliveryDate() {
            return deliveryDate;
        }

        public BigDecimal getUsdPrice() {
            return usdPrice;
        }
    }

    public static final class IsoDateFormatter
            implements Formatter<LocalDate> {

        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {
            try {
                return LocalDate.parse(text);
            } catch (DateTimeParseException ex) {
                ParseException failure =
                    new ParseException("Expected ISO date yyyy-MM-dd", 0);
                failure.initCause(ex);
                throw failure;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return value.toString();
        }
    }

    public static final class UsdAmountFormatter
            implements Formatter<BigDecimal> {

        private NumberFormat createFormat(Locale locale) {
            NumberFormat format =
                NumberFormat.getCurrencyInstance(locale);
            format.setCurrency(Currency.getInstance("USD"));
            if (format instanceof java.text.DecimalFormat decimal) {
                decimal.setParseBigDecimal(true);
            }
            return format;
        }

        @Override
        public BigDecimal parse(String text, Locale locale)
                throws ParseException {
            NumberFormat format = createFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            if (parsed == null
                    || position.getErrorIndex() >= 0
                    || position.getIndex() != text.length()) {
                int errorAt = Math.max(
                    0,
                    Math.max(position.getErrorIndex(), position.getIndex())
                );
                throw new ParseException("Invalid USD amount", errorAt);
            }
            if (parsed instanceof BigDecimal decimal) {
                return decimal;
            }
            return new BigDecimal(parsed.toString());
        }

        @Override
        public String print(BigDecimal value, Locale locale) {
            return createFormat(locale).format(value);
        }
    }

    public static final class UsdAmountFormatterFactory
            implements AnnotationFormatterFactory<UsdAmount> {

        private final Formatter<BigDecimal> formatter =
            new UsdAmountFormatter();

        @Override
        public Set<Class<?>> getFieldTypes() {
            return Set.of(BigDecimal.class);
        }

        @Override
        public Printer<?> getPrinter(
                UsdAmount annotation, Class<?> fieldType) {
            return formatter;
        }

        @Override
        public Parser<?> getParser(
                UsdAmount annotation, Class<?> fieldType) {
            return formatter;
        }
    }

    private static TypeDescriptor field(String name)
            throws NoSuchFieldException {
        Field field = PriceForm.class.getDeclaredField(name);
        return new TypeDescriptor(new Property(field));
    }

    public static void main(String[] args) throws Exception {
        var service = new DefaultFormattingConversionService();

        // Field-type registration: all LocalDate fields use ISO.
        service.addFormatterForFieldType(
            LocalDate.class, new IsoDateFormatter()
        );

        // Annotation-based registration: BigDecimal fields annotated with @UsdAmount.
        service.addFormatterForFieldAnnotation(
            new UsdAmountFormatterFactory()
        );

        TypeDescriptor textType =
            TypeDescriptor.valueOf(String.class);
        TypeDescriptor dateType = field("deliveryDate");
        TypeDescriptor usdType = field("usdPrice");

        LocalDate date = (LocalDate) service.convert(
            "2026-11-02", textType, dateType
        );

        BigDecimal amount = (BigDecimal) service.convert(
            "$1,234.50", textType, usdType
        );

        String dateText = (String) service.convert(
            date, dateType, textType
        );
        String moneyText = (String) service.convert(
            amount, usdType, textType
        );

        System.out.println("date=" + date);
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("dateText=" + dateText);
        System.out.println("moneyText=" + moneyText);
    }
}
```

Run from the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FormatterRegistrationDemo
```

With the formatter and `TypeDescriptor` above, the lines printed by the program under `Locale.US` are:

```text
date=2026-11-02
amount=1234.50
dateText=2026-11-02
moneyText=$1,234.50
```

Explanation:

1. `addFormatterForFieldType(LocalDate.class, ...)` applies the ISO formatter to the `deliveryDate` field.
2. Field `usdPrice` has type `BigDecimal` and annotation `@UsdAmount`.
3. `TypeDescriptor` is built from the field so Spring can read the annotation. The factory explicitly declares support for `BigDecimal.class`.
4. `getParser` and `getPrinter` return the USD formatter for both parse and print directions.
5. US locale formats `$1,234.50`; the formatter sets currency code USD explicitly.
6. When converting objects back to text, the field descriptor continues helping Spring pick the right formatter.

This is a standalone Java program without starting Spring MVC. It demonstrates the registration and `TypeDescriptor`-based conversion mechanism that Spring binding can also use.

## 8. AnnotationFormatterFactory: Designing with the Right Scope

The factory should restrict the supported field types. For instance, `UsdAmountFormatterFactory` returns `Set.of(BigDecimal.class)`. If the annotation is mistakenly placed on a `String` field, the factory does not claim support for that type.

Principles:

- Generic annotation parameter `A` must be the actual annotation placed on the model.
- `getFieldTypes()` returns the types that the parser/printer can handle.
- `getPrinter(A annotation, Class<?> fieldType)` picks a printer matching the annotation and field type.
- `getParser(A annotation, Class<?> fieldType)` picks the corresponding parser.
- You can read annotation attributes, such as `@DatePattern(pattern = "...")`, to configure the formatter per field.
- Formatters are typically used across multiple requests; keep them stateless/thread-safe or construct stateful objects safely.

If the annotation has configuration attributes, the factory can build a formatter from the annotation instance itself. Do not cache a formatter configured for one annotation and reuse it for another annotation with a different pattern/currency if the formatter holds mutable state.

## 9. Annotations with Attributes: Custom Date Patterns

Example:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface DatePattern {
    String value();
}
```

The factory can read `annotation.value()` and construct a formatter using `DateTimeFormatter.ofPattern(pattern, locale)`. Two fields of the same `LocalDate` type can then have distinct patterns. This is the annotation-based approach when formats vary by field, whereas registering `LocalDate.class` applies one global rule.

Validate patterns eagerly during configuration initialization; an invalid pattern is a configuration error, not a user data error. Also, Java date/time patterns are case-sensitive: `M` is month, `m` is minute. Test parse/print with boundary values.

## 10. Registering in Spring MVC

Spring MVC allows adding formatters via `FormatterRegistry` inside `WebMvcConfigurer#addFormatters(...)`:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
            LocalDate.class, new IsoDateFormatter()
        );
        registry.addFormatterForFieldAnnotation(
            new UsdAmountFormatterFactory()
        );
    }
}
```

This snippet is an integration example in a Spring MVC application with web dependencies and the defined formatter classes.

- `@ModelAttribute` and `WebDataBinder` use Spring's binding/conversion infrastructure; suitable formatters can parse/print fields based on property metadata.
- For annotation-based formatting, the conversion call site must preserve the field/parameter descriptor; you cannot pass just `BigDecimal.class` and expect Spring to know which field carried the annotation.
- In Spring Boot, typically configure via `WebMvcConfigurer` or the corresponding formatter registry mechanism, while letting the Boot BOM manage Spring versions.
- `@RequestBody` JSON normally goes through an `HttpMessageConverter` such as Jackson. Spring Formatter registration does not automatically change JSON deserialization rules; Jackson has its own modules/deserializers.
- Formatters are useful for form/query values and re-rendering values in views.

## 11. Locale, parse/print, and Round-Trip

Locale affects numbers, dates, and currencies. Several key rules:

1. The US locale commonly uses a dot for decimals and a comma for grouping; other locales may swap those conventions.
2. A currency symbol is not enough to identify the currency code. `$` can represent many currencies; if business logic requires USD, configure USD explicitly as shown.
3. Parsing should use the exact locale the form uses; avoid falling back to the server's default locale when users have their own locale.
4. Check that the entire text was parsed; do not accept a valid prefix and discard trailing garbage.
5. For money, use `BigDecimal` instead of `double` to avoid binary representation errors.
6. Scale/rounding rules belong to the domain. A formatter should not round monetary values silently unless the contract permits it.
7. `NumberFormat` and `DecimalFormat` are unsafe to share as mutable instances across threads; create a separate instance per operation or use an immutable solution.
8. `print(parse(text, locale), locale)` should reproduce the canonical representation or at least preserve the meaningful value.

## 12. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Annotation formatter does not run | Passed only `BigDecimal.class`, missing field descriptor | Use `TypeDescriptor` or let `DataBinder`/MVC handle the property |
| Annotation is not recognized | Factory not registered or retention is not RUNTIME | Register via `FormatterRegistry` and check annotation metadata |
| Factory is not applied | `getFieldTypes()` does not include the field type | Declare all supported types accurately |
| All `LocalDate` fields get the same format unintentionally | Type-based formatter applies globally | Use annotations if fields need distinct rules |
| Parse fails in another locale | Separators/grouping do not match | Select the right locale and test per locale |
| `$` symbol does not identify the right currency | One symbol is shared by multiple currencies | Specify currency code explicitly |
| Print succeeds but parse fails | Two directions are asymmetric | Write round-trip tests |
| Strings with trailing garbage are accepted | Parser does not check the entire input | Check `ParsePosition`/index or full string consumption |
| Cross-request glitches | Formatter shares unsafe mutable state | Keep stateless or construct per-call state safely |
| Formatter does not run in MVC | Registered on the wrong registry/service | Use `WebMvcConfigurer`/the real MVC registry |
| Formatter does not handle JSON as expected | JSON is read by Jackson | Configure Jackson deserializers when needed |
| Wrong annotation pattern | Configuration mistake detected late | Validate patterns at startup |

## 13. Formatter Testing Workflow

For type-based or annotation-based formatters, verify:

- **Registration:** the registry resolves the intended formatter/factory.
- **Valid parse:** locale-formatted text constructs the expected object.
- **Invalid parse:** malformed input throws an appropriate exception rather than returning a fake value.
- **Print:** the object produces a string matching locale conventions.
- **Round-trip:** parsing after printing preserves the meaningful value.
- **Annotation scope:** annotated fields use the formatter; unannotated fields of the same type are not affected by mistake.
- **Metadata:** conversions using `TypeDescriptor` preserve required annotation/generic metadata.
- **Concurrency:** shared formatters do not share unsafe mutable state.
- **MVC:** if the application uses web binding, test through `@ModelAttribute` and `WebDataBinder`.

## 14. Self-Check Questions

1. What is the difference between `Converter<S,T>` and `Formatter<T>`? Why does Formatter accept Locale?
2. When should you use `addFormatterForFieldType` versus `addFormatterForFieldAnnotation`?
3. Why is `TypeDescriptor` needed to choose a formatter based on a field's annotation?
4. In which method does `AnnotationFormatterFactory` declare supported types?
5. Why does the annotation require `RetentionPolicy.RUNTIME`?
6. For two `BigDecimal` fields where one is USD money and one is a ratio, should you use type-based or annotation-based registration?
7. Why does `convert(text, BigDecimal.class)` not automatically know the field's annotation?
8. When parsing monetary amounts, why should you use `BigDecimal` and specify the currency explicitly?
9. Does Spring Formatter registration automatically affect `@RequestBody` JSON handled by Jackson?
10. How do you test parse/print round-trips across multiple Locales?

**Remember:** Field-type registration applies one Formatter to all fields of that type; annotation-based registration picks a formatter from each field's metadata. `TypeDescriptor` carries annotation and generic metadata to `ConversionService`. Use type-based when rules are uniform; use annotation-based when the same Java type has different meanings or display formats.

## References

- Spring Framework — Formatter SPI: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — Registering Formatters: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.1.14 — FormatterRegistry Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/FormatterRegistry.html
- Spring Framework 6.1.14 — AnnotationFormatterFactory Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework 6.1.14 — FormattingConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html
