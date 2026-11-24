# Distinguishing General Type Conversion from Field Formatting in Spring Framework

## 1. Two Distinct Needs

Applications often need to transform data between Java types and strings that users enter or see. These two tasks are related but not identical:

- **General type conversion:** transforms a value from a source type to a target type, for example `String` to `CurrencyCode`, `Integer` to `Long`, or `LegacyId` to `CustomerId`. The focus is on meaning and data type.
- **Field formatting:** parses user-entered strings into typed values and prints those values into strings suited for the UI/locale. The same date December 31, 2026 may be displayed as `31/12/2026` or `12/31/2026`.

Spring provides two primary SPIs:

- `Converter<S,T>` in `org.springframework.core.convert.converter` for general type conversion.
- `Formatter<T>` in `org.springframework.format` for locale-aware parsing and printing of field values.

`ConversionService` provides a unified API for performing conversions; `FormattingConversionService` integrates both converters and formatters. The difference lies in the SPI's purpose and contract, not in any inability to work together.

## 2. Same Value, Multiple Representations

Domain value:

```java
LocalDate date = LocalDate.of(2026, 12, 31);
```

A `LocalDate` object does not carry display conventions on its own. Depending on the UI/locale, it can be rendered as:

| Convention | Example String | Meaning |
| --- | --- | --- |
| Day/month/year | `31/12/2026` | Common in Vietnam |
| Month/day/year | `12/31/2026` | Example of US convention |
| ISO | `2026-12-31` | Year-month-day |

These strings represent the same date. If UI strings are stored as domain values, the system can easily confuse day and month when switching locales or exchanging data.

Ask: "What Java type does this value need to become?" then choose Converter; "How should this Java value be displayed to a user in the current locale?" then choose Formatter. Formatting should not alter the domain value.

## 3. Converter: General Type Conversion

### 3.1. API Contract

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`S` is the source type, `T` is the target type. A Converter is typically stateless, thread-safe, and may throw `IllegalArgumentException` when the source is invalid. It has no `Locale` parameter and provides no reverse printing method.

Example of converting a currency code string into a value object:

```java
public record CurrencyCode(String value) {}

public final class StringToCurrencyCodeConverter
        implements Converter<String, CurrencyCode> {
    @Override
    public CurrencyCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Currency is blank");
        }
        String code = source.strip().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
        return new CurrencyCode(code);
    }
}
```

Requires importing `java.util.Locale` and `Converter`. Input `" usd "` becomes `CurrencyCode("USD")`. `Locale.ROOT` is used because identifier normalization should not be affected by the UI locale.

This converter does not know whether the string will appear in HTML, logs, or JSON. It simply creates a normalized, meaningful data type.

### 3.2. Converter does not format in reverse automatically

`Converter<String, CurrencyCode>` only handles the String-to-CurrencyCode direction. If you want the reverse direction, register another converter:

```java
public final class CurrencyCodeToStringConverter
        implements Converter<CurrencyCode, String> {
    @Override
    public String convert(CurrencyCode source) {
        return source == null ? null : source.value();
    }
}
```

The two converters are independent; they do not form a locale-aware parse/print contract. When output requires localization, Formatter is usually a better fit.

### 3.3. When to use Converter?

Use Converter when converting an identifier/string into a domain value object; converting `Long` into `CustomerId`; or when the conversion logic is stable and locale-independent. Converters can be reused across BeanFactory, DataBinder, SpEL, and anywhere `ConversionService` is used.

Do not put database lookups, authorization, or business side effects into a shared converter.

## 4. Formatter: parse and print for the UI

### 4.1. Formatter Contract

```java
public interface Printer<T> {
    String print(T fieldValue, Locale locale);
}
public interface Parser<T> {
    T parse(String clientValue, Locale locale) throws ParseException;
}
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

- `parse` reads a client-submitted string and creates an object of type `T`.
- `print` turns an object `T` into a display string.
- Both accept `Locale`.
- `parse` may throw `ParseException` or `IllegalArgumentException`.
- Shared formatters must be thread-safe. Avoid holding a shared mutable `SimpleDateFormat`; immutable `DateTimeFormatter` is a safe choice.

### 4.2. Formatter Example for LocalDate

```java
public final class LocalDateShortFormatter
        implements Formatter<LocalDate> {
    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        DateTimeFormatter format =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale)
                .withResolverStyle(ResolverStyle.STRICT);
        try {
            return LocalDate.parse(text, format);
        }
        catch (DateTimeParseException ex) {
            ParseException error =
                new ParseException(ex.getMessage(), 0);
            error.initCause(ex);
            throw error;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
            .withLocale(locale).format(value);
    }
}
```

Requires imports `java.text.ParseException`, `java.time.LocalDate`, `java.time.format.*`, `java.util.Locale`, and `org.springframework.format.Formatter`.

`FormatStyle.SHORT` picks the short date style for the locale. Under US conventions, December 31, 2026 can be parsed from `12/31/26`; other locales may use a different field order. `ResolverStyle.STRICT` rejects nonexistent dates instead of silently adjusting them. Test the locales your product supports.

### 4.3. Parse/print are not necessarily exact inverses

A formatter has two operations, but the printed string may drop precision or detail. For example, a formatter might print only the date without the time; parsing it back restores only the date part. The rules should clearly define the accepted input form, output string, locale, policy for empty/null strings, and behavior for malformed values.

## 5. Comparing Converter and Formatter

| Criterion | `Converter<S,T>` | `Formatter<T>` |
| --- | --- | --- |
| Purpose | General type conversion | Field formatting for client/UI |
| Direction | One-way `S → T` | Parse string to T, print T to string |
| Locale | No locale parameter | Has Locale on both parse and print |
| Focus | Data type semantics | Human-readable representation |
| Example | `String → CurrencyCode` | `String → LocalDate` by locale and `LocalDate → String` |
| Registration | `ConverterRegistry.addConverter` | `FormatterRegistry.addFormatter` |
| Use case | Domain IDs, value objects | Date, currency, percentage forms |

Selection rule: if you need locale-independent type semantic conversion, choose Converter; if you need locale-aware parsing/printing of display strings, choose Formatter. An application typically needs both.

## 6. How does ConversionService connect the two SPIs?

`ConversionService` is the API for querying and executing conversions:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
```

`FormatterRegistry` is the SPI for registering converters and formatters. `FormattingConversionService` implements both `FormatterRegistry` and `ConversionService`, so a single service can perform general conversions, parse date strings, and print dates by locale.

Example:

```java
DefaultFormattingConversionService service =
    new DefaultFormattingConversionService();

service.addConverter(new StringToCurrencyCodeConverter());
service.addFormatterForFieldType(
    LocalDate.class,
    new LocalDateShortFormatter()
);
```

Requires importing `DefaultFormattingConversionService` and the custom classes. Once registered, callers use `convert` instead of invoking each converter/formatter directly:

```java
CurrencyCode currency =
    service.convert(" usd ", CurrencyCode.class);

LocalDate date =
    service.convert("12/31/26", LocalDate.class);

String rendered = service.convert(date, String.class);
```

Date results depend on the locale context and formatter; do not assume identical display strings on every machine. `DefaultFormattingConversionService` is a built-in implementation preconfigured with common converters/formatters; it is not a separate SPI from `FormattingConversionService`.

## 7. TypeDescriptor and Property Metadata

The `convert(source, targetClass)` API suffices for many simple transformations. However, `Class<?>` cannot always describe generics and annotations.

`TypeDescriptor` can carry metadata about generic element types of `List`/arrays, key/value types of `Map`, annotations on fields/properties, and component types.

`List<Integer>` and `List<String>` share the same runtime class `List.class`. Passing only `List.class` does not express the source/target element types:

```java
TypeDescriptor source = TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(Integer.class));

TypeDescriptor target = TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(String.class));

Object result = service.convert(
    List.of(1, 2, 3), source, target);
```

Requires importing `TypeDescriptor`; with an Integer→String converter, the result is the string list `["1", "2", "3"]`. During property binding, Spring usually extracts metadata from properties; when calling low-level APIs, the caller may need to supply the descriptor.

## 8. Where to Register Converters and Formatters?

### 8.1. FormatterRegistry

```java
registry.addConverter(new StringToCurrencyCodeConverter());
registry.addFormatter(new LocalDateShortFormatter());
registry.addFormatterForFieldType(
    LocalDate.class, new LocalDateShortFormatter());
```

`addConverter` registers a general type conversion; `addFormatter` registers a formatter by its type `T`; `addFormatterForFieldType` restricts a formatter to a specific field type; `addFormatterForFieldAnnotation` binds rules to an annotation.

### 8.2. Spring MVC

Register centrally via `WebMvcConfigurer.addFormatters`:

```java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCurrencyCodeConverter());
        registry.addFormatterForFieldType(
            LocalDate.class, new LocalDateShortFormatter());
    }
}
```

This is an integration fragment requiring Spring MVC imports and the custom classes. Spring MVC includes default formatters for many number/date types; this configuration adds custom converters/formatters. The request locale is supplied to the formatter by the framework; avoid grabbing the JVM default locale when the framework already provides an appropriate locale.

### 8.3. DataBinder and WebDataBinder

`DataBinder` uses a conversion service when binding properties:

```java
DataBinder binder = new DataBinder(form, "form");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
```

This is a fragment for a target JavaBean with writable properties. `WebDataBinder` extends DataBinder for web environments. Formatters can parse request strings into field objects; when redisplaying, formatters can print values according to locale.

Formatters do not automatically force JSON serializers to use their print rules. `@RequestBody` and Jackson/`HttpMessageConverter` have their own deserialization mechanism.

## 9. Annotation Formatters

Spring supports annotations on fields/parameters, commonly `@DateTimeFormat` and `@NumberFormat`:

```java
public class SearchForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    // getters/setters
}
```

Requires importing the annotations, `LocalDate`, and `BigDecimal`. `@DateTimeFormat` specifies how to parse/print dates; `@NumberFormat` specifies how to format numbers. Annotations do not change the Java type of the property.

If two `LocalDate` fields in the same form require two different rules, annotation-based configuration is a better fit than a default formatter for all `LocalDate` fields.

## 10. Java 17 Example: Using ConversionService and DataBinder Together

This example uses a Converter for currency codes and a Formatter for dates, both registered into `DefaultFormattingConversionService`; then `DataBinder` uses the service to bind a form.

### 10.1. Maven Structure

```text
formatter-demo/
├── pom.xml
└── src/main/java/example/FormatterDemo.java
```

`pom.xml` uses Java 17 and Spring Framework 6.2.14:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>formatter-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.14</version>
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
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.FormatterDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/FormatterDemo.java`:

```java
package example;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.FormatStyle;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class FormatterDemo {

    public record CurrencyCode(String value) {}

    public static final class StringToCurrencyCode
            implements Converter<String, CurrencyCode> {
        @Override
        public CurrencyCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Currency is blank");
            }
            String code = source.strip().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency");
            }
            return new CurrencyCode(code);
        }
    }

    public static final class LocalDateFormatter
            implements Formatter<LocalDate> {
        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {
            DateTimeFormatter format =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                    .withLocale(locale)
                    .withResolverStyle(ResolverStyle.STRICT);
            try {
                return LocalDate.parse(text, format);
            }
            catch (DateTimeParseException ex) {
                ParseException error =
                    new ParseException(ex.getMessage(), 0);
                error.initCause(ex);
                throw error;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale).format(value);
        }
    }

    public static class SearchForm {
        private CurrencyCode currency;
        private LocalDate startDate;

        public CurrencyCode getCurrency() { return currency; }
        public void setCurrency(CurrencyCode value) { currency = value; }
        public LocalDate getStartDate() { return startDate; }
        public void setStartDate(LocalDate value) { startDate = value; }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
            new DefaultFormattingConversionService();
        service.addConverter(new StringToCurrencyCode());
        service.addFormatterForFieldType(
            LocalDate.class, new LocalDateFormatter());

        SearchForm form = new SearchForm();
        DataBinder binder = new DataBinder(form, "searchForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("currency", " usd ");
        values.add("startDate", "12/31/26");

        LocaleContextHolder.setLocale(Locale.US);
        try {
            binder.bind(values);
        }
        finally {
            LocaleContextHolder.resetLocaleContext();
        }

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            throw new IllegalStateException(
                "Binding failed: " + errors.getAllErrors());
        }

        System.out.println("currency=" + form.getCurrency().value());
        System.out.println("date-iso=" + form.getStartDate());
        System.out.println("date-display=" +
            service.convert(form.getStartDate(), String.class));
        System.out.println("errors=" + errors.hasErrors());
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected `stdout` on Java 17/Spring 6.2.14:

```text
currency=USD
date-iso=2026-12-31
date-display=12/31/26
errors=false
```

`currency=USD` demonstrates the Converter normalizing the code; `date-iso` is the `LocalDate` value; `date-display` is the Formatter printing in US locale with SHORT style. The locale is set via `LocaleContextHolder` while the binder runs and reset in `finally` to prevent leaking to other work on the same thread.

In Spring MVC, the locale resolver/request context supplies the request locale. A standalone program must set the context when testing locale-dependent parse/print.

## 11. Parse Errors, Conversion Errors, and Validation

| Scenario | Appropriate Layer |
| --- | --- |
| `"abc"` cannot become an Integer | Converter/built-in conversion |
| `"31/02/2026"` is a nonexistent date | Formatter parse |
| Code `"usd"` needs normalizing to `"USD"` | Converter |
| Date needs to be printed according to US/VN locale | Formatter print |
| Date parses validly but falls outside booking window | Business validation |
| User is not allowed to use this currency | Authorization/service |

Parse/convert only creates typed values. Validation checks constraints. Authorization checks execution permissions. Do not put database lookups or side effects into a Formatter.

When a Formatter/Converter fails via DataBinder, the binder can record field errors in `BindingResult`. The handler must check `hasErrors()` before calling the service. If calling `ConversionService.convert` directly, exceptions may propagate to the caller depending on the API.

With Spring MVC forms, place `BindingResult` immediately after `@ModelAttribute`. With JSON `@RequestBody`, the message converter/JSON mapper handles deserialization; DataBinder's Formatter does not automatically replace Jackson.

## 12. Common Pitfalls

1. Using Converter for locale-aware UI printing: Converter does not receive Locale; use Formatter.
2. Using Formatter for every domain conversion: general type conversions should remain Converters.
3. Scattering formatting logic across controllers: register centrally via FormatterRegistry.
4. Using a singleton SimpleDateFormat: mutable and not thread-safe; use DateTimeFormatter.
5. Relying on JVM default locale: results differ across environments; use the Locale passed by the framework or set in tests.
6. Confusing formatting with storage: store proper date/money types, not display strings as domain data.
7. Failing to control ResolverStyle: invalid dates can be silently adjusted if the resolver is not strict.
8. Assuming Formatter controls JSON: JSON mappers have their own serializers/deserializers.
9. Registering duplicate rules: conflicting converters/formatters lead to confusing behavior.
10. Putting business rules inside Formatter: keep Formatter focused on parse/print; validation and access control belong in other layers.

## 13. Testing and Choosing an Abstraction

You should test Converters with valid input, whitespace, empty input, and invalid input; Formatters with parse/print per locale, invalid dates, and round-trips; DataBinder with valid fields, invalid fields, BindingResult, and target values; MVC integration with request locales and the formatter registry.

| Need | Choice |
| --- | --- |
| String to domain ID/value object | `Converter<String,T>` |
| Date entered and displayed by locale | `Formatter<LocalDate>` |
| Currency entered/printed by locale | `Formatter<BigDecimal>` |
| Per-field custom rules | Annotation formatter |
| Both conversion and formatting needed | `FormattingConversionService` |
| Generic collections | `TypeDescriptor` |

## 14. Self-Check Exercises

**Exercise 1.** Convert `"42"` into `CustomerId(42)`, independent of locale. What do you use?

**Answer:** `Converter<String, CustomerId>` because this is a general domain type conversion.

**Exercise 2.** A form accepts dates in the user's convention and redisplays them in the same locale. What do you use?

**Answer:** `Formatter<LocalDate>` with parse and print accepting Locale.

**Exercise 3.** One LocalDate displays as `31/12/2026` in form A and `12/31/2026` in form B. Do you need two LocalDate types?

**Answer:** No. Keep one domain type; select the appropriate formatter/locale per field.

**Exercise 4.** `CurrencyCode("USD")` converts successfully; the account is not permitted to transact in USD. Should the Converter look up the account and reject it?

**Answer:** No. Transaction permissions and business validation belong in the service/domain layer.

## 15. Official References

- Spring Framework Reference — [Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Converter/Formatter differences, Printer, Parser, FormatterRegistry, and FormatterRegistrar.
- Spring Framework Reference — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter SPI, TypeDescriptor, and registries.
- Spring Framework Reference — [Spring MVC Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering formatters/converters via WebMvcConfigurer.
- Spring Framework Javadoc — [Formatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Formatter.html): parse/print contract.
- Spring Framework Javadoc — [FormattingConversionService](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/support/FormattingConversionService.html): FormatterRegistry and ConversionService.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): binding via ConversionService.
