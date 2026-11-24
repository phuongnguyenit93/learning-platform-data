# DefaultFormattingConversionService and Default Formatters in Spring

Spring Framework provides a unified infrastructure to **convert data types** and **format values for presentation and communication**. Applications commonly receive strings from forms or query parameters and need to convert them into `Integer`, `BigDecimal`, `LocalDate`, enums, or domain types. When rendering back, the application needs to convert Java values into strings according to conventions that may depend on locale.

`DefaultFormattingConversionService` is a convenient implementation combining two capabilities: Spring Core's general-purpose type conversion mechanism (`ConversionService`) and a registry for formatters. It registers common converters/formatters while allowing applications to add custom converters, formatters, and annotation formatters.

This lesson explains default formatters, how locale affects parse/print, number formatting annotations, date/time formatters, registering custom formatters, and extension points in Spring MVC. A standalone Java 17+ example demonstrates converting numbers/booleans with default converters alongside a locale-aware domain formatter.

## 1. ConversionService, Formatter, and FormattingConversionService

### ConversionService

`org.springframework.core.convert.ConversionService` provides the API to check and execute conversions:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

The API also has overloads accepting `TypeDescriptor` to describe generic types and property metadata. Common conversions include `String -> Integer`, `String -> Boolean`, conversions between numeric types, and collection/array conversions when Spring can determine source/target types.

A `Converter<S,T>` performs a one-way conversion from S to T:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Converters are suited for technical or domain conversions that do not require locale, such as `String -> UUID` or `String -> CustomerId`.

### Formatter

`org.springframework.format.Formatter<T>` combines the `Printer<T>` and `Parser<T>` interfaces:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Two core operations:

- `parse(String text, Locale locale)`: converts user-entered text into an object `T`.
- `print(T object, Locale locale)`: converts an object into a string for display.

Formatters receive `Locale`, making them suitable for numbers, dates/times, currencies, and data with language/region-specific display conventions. For instance, the same number `1234.5` may display as `1,234.5` in the US locale and `1.234,5` in the German locale.

### FormattingConversionService

`FormattingConversionService` is both a `ConversionService` and a `FormatterRegistry`. It allows registering:

- `Converter<S,T>` for one-way conversion.
- `ConverterFactory<S,R>` when a family of target types is needed.
- `GenericConverter` when `TypeDescriptor`-level control is required.
- `Formatter<T>` for locale-aware parse/print.
- `AnnotationFormatterFactory<A>` for annotation-driven formatting.

`DefaultFormattingConversionService` is an implementation with useful default configuration. It does not automatically understand custom domain types; those still require converters or formatters provided by the application.

## 2. What Does DefaultFormattingConversionService Register?

When initialized with defaults, the service registers common scalar converters and standard formatters. In broad strokes:

| Group | Examples |
|---|---|
| String and scalars | String to numbers, Boolean, Character, enums, and several simple types |
| Number | Conversions between supported numeric types |
| Array/collection | Element and container conversions when source/target types are known |
| Object and text | String/object conversions supplied by corresponding converters |
| Formatting annotations | For example `@NumberFormat` on numeric fields/properties |
| Date/time | Formatters registrable for Java Date/Time; Java Time configuration uses its corresponding registrar |

Separate two concepts. Converting `"42"` into `Integer(42)` is basic type conversion. Displaying a `BigDecimal` with locale-specific grouping and decimal separators is formatting. The same service manages both, yet converters and formatters serve different purposes.

`DefaultFormattingConversionService`'s constructor lets you choose whether to register default formatters:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

// Create a service without auto-registering default formatters:
DefaultFormattingConversionService withoutDefaultFormatters =
        new DefaultFormattingConversionService(false);
~~~

Passing `false` skips registering default formatters; the application can register needed formatters explicitly via the registry. Do not choose this mode if code relies on annotation formatters or standard formatting rules without providing replacement configuration.

Exact default converters and formatters can vary across Spring versions. When exact behavior for a type matters, check the Javadoc/reference for the Spring version you run and write tests for the actual configuration.

## 3. The @NumberFormat Annotation

Spring supports `@NumberFormat` to declare how numeric properties are formatted:

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal total;

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Common styles:

- `NUMBER`: standard number formatting.
- `CURRENCY`: locale-based currency formatting.
- `PERCENT`: locale-based percentage formatting.

The annotation can also declare a pattern following `DecimalFormat` rules. Patterns must be chosen carefully and tested against the application's real locales. Do not store formatted strings like `"1.234,50"` in a database instead of canonical numeric values; store `BigDecimal` and format only at communication boundaries.

Examples of how locales produce different representations:

| Locale | Number Example |
|---|---|
| `Locale.US` | `1,234.5` |
| `Locale.GERMANY` | `1.234,5` |
| `Locale.FRANCE` | Decimal comma and grouping character per French convention |

Do not hardcode dots or commas when parsing user data. For money, `CURRENCY` may also include currency symbols and spaces depending on locale/JDK. Locale **does not determine the currency** for business logic; applications still need a separate currency code if distinguishing EUR, USD, or others.

### Annotations and TypeDescriptor

When converting a property annotated with `@NumberFormat`, Spring needs the property's metadata. `TypeDescriptor` can carry annotations and generic information. Therefore, converting with `Class<BigDecimal>` is not always equivalent to converting with the descriptor of the annotated field: the Class-only overload carries no field annotation metadata.

Example using a descriptor:

~~~java
TypeDescriptor sourceType = TypeDescriptor.valueOf(String.class);
TypeDescriptor targetType =
        new TypeDescriptor(InvoiceForm.class.getDeclaredField("total"));

Object result = service.convert(
        "1,234.50", sourceType, targetType);
~~~

The result depends on the active locale and annotations on the property. Use `TypeDescriptor` when field metadata is needed; use the `Class` overload when converting purely by source and target types.

## 4. Date and Time Formatting with Java Time

Dates and times have many representations: `dd/MM/uuuu`, `MM/dd/uuuu`, localized month names, or ISO-8601. In Spring MVC, `DateTimeFormatterRegistrar` registers standard formatters for Java Time types.

Configuration example:

~~~java
import java.time.format.DateTimeFormatter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();

        registrar.setDateFormatter(
                DateTimeFormatter.ofPattern("dd/MM/uuuu"));
        registrar.setDateTimeFormatter(
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm"));

        registrar.registerFormatters(registry);
    }
}
~~~

This is a Spring MVC integration configuration, not a standalone program. The patterns above are an explicit application-wide convention; they do not automatically vary by locale.

Notes:

- `LocalDate` contains no time zone. Do not interpret it as an instant.
- `LocalDateTime` likewise specifies no time zone; if you need a global point in time, consider `Instant` or `OffsetDateTime` per your contract.
- In Java Time patterns, `uuuu` represents the proleptic year; `YYYY` is week-based-year and can differ around New Year boundaries.
- Nonexistent dates such as February 31 must be rejected, not silently adjusted to another date.
- If locale-based formatting is desired, use a localized formatter or locale-aware configuration instead of always locking in a single pattern.

## 5. Standalone Java 17+ Example: Default Converters and Custom Formatter

This program uses `DefaultFormattingConversionService` to convert `String -> Integer` and `String -> Boolean` with built-in converters, then registers a formatter for the `Price` domain type. The formatter parses and prints using the active locale.

Structure:

~~~text
formatting-service-demo/
├── pom.xml
└── src/main/java/demo/FormattingServiceDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatting-service-demo</artifactId>
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
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/FormattingServiceDemo.java`:

~~~java
package demo;

import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.support.DefaultFormattingConversionService;
import org.springframework.format.Formatter;

public final class FormattingServiceDemo {

    public record Price(BigDecimal amount) {
    }

    public static final class PriceFormatter implements Formatter<Price> {

        @Override
        public Price parse(String text, Locale locale) {
            String input = text.trim();
            NumberFormat format = NumberFormat.getNumberInstance(locale);
            ParsePosition position = new ParsePosition(0);
            Number number = format.parse(input, position);

            if (number == null || position.getIndex() != input.length()) {
                throw new IllegalArgumentException(
                        "Invalid price format: " + text);
            }

            return new Price(new BigDecimal(number.toString()));
        }

        @Override
        public String print(Price price, Locale locale) {
            NumberFormat format = NumberFormat.getNumberInstance(locale);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            return format.format(price.amount());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        Integer quantity = service.convert("42", Integer.class);
        Boolean enabled = service.convert("true", Boolean.class);

        System.out.println("quantity=" + quantity);
        System.out.println("enabled=" + enabled);

        service.addFormatterForFieldType(Price.class, new PriceFormatter());

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            Price price = service.convert("1.234,50", Price.class);
            String display = service.convert(price, String.class);

            System.out.println("price.amount=" + price.amount().toPlainString());
            System.out.println("price.display=" + display);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Run with JDK 17+ and Maven:

~~~bash
cd formatting-service-demo
mvn -q compile exec:java -Dexec.mainClass=demo.FormattingServiceDemo
~~~

Stdout of the Java statements:

~~~text
quantity=42
enabled=true
price.amount=1234.5
price.display=1.234,50
~~~

Maven may print its own logs depending on the environment. The `price.display` output uses `Locale.GERMANY` set via `LocaleContextHolder`. The formatter reads the active locale for parse/print. Because `LocaleContextHolder` is thread-bound, the example resets it in `finally`; during web requests Spring typically manages locale context across the request lifecycle.

Explanation:

1. `service.convert("42", Integer.class)` uses the default number converter.
2. `service.convert("true", Boolean.class)` uses the default Boolean converter.
3. `addFormatterForFieldType(Price.class, ...)` registers the formatter for the `Price` domain type.
4. When converting a string to `Price` and `Price` to `String`, the formatter is invoked in both parse and print directions.
5. The formatter uses a locale-specific `NumberFormat` and verifies the entire string was parsed; trailing characters are rejected.

The example illustrates a locale-aware numeric formatter, not a complete monetary model. Real monetary applications need explicit currency, decimal scale, rounding, and storage units. `BigDecimal` is far better suited to decimal values than binary floating-point types.

## 6. Converter and Formatter: Which Should You Choose?

| Criterion | Converter | Formatter |
|---|---|---|
| Contract | `Converter<S,T>` | `Formatter<T>` |
| Direction | Usually one-way S → T | Bidirectional parse and print |
| Locale | Base SPI does not receive locale | Receives locale on both parse and print |
| Best suited for | Technical/domain conversion | Parsing and displaying user data |
| Example | `String -> UUID` | `String <-> LocalDate` |

Registering a converter:

~~~java
registry.addConverter(new CustomerIdConverter());
~~~

Registering a formatter:

~~~java
registry.addFormatter(new PriceFormatter());
~~~

There is no need to create a formatter just to wrap a locale-independent converter. Conversely, if a value has a language/region-dependent representation, a formatter is usually the more natural choice.

## 7. Registering in Spring MVC via WebMvcConfigurer

Spring MVC provides a formatting conversion service for data binding of forms and query parameters. `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` is the extension point for registering additional formatters/converters into the service managed by MVC.

Example:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                LocalDate.class,
                new Formatter<>() {
                    private final DateTimeFormatter formatter =
                            DateTimeFormatter.ofPattern("dd/MM/uuuu");

                    @Override
                    public LocalDate parse(String text, Locale locale) {
                        return LocalDate.parse(text, formatter);
                    }

                    @Override
                    public String print(LocalDate value, Locale locale) {
                        return formatter.format(value);
                    }
                });
    }
}
~~~

This is an MVC integration configuration. Applications should avoid registering multiple conflicting formatters for the same type without clearly defining intent. If you want date patterns to adapt automatically to locale, use a localized formatter or registrar rather than a fixed pattern.

Handler receiving a form:

~~~java
@PostMapping("/appointments")
String create(@Valid @ModelAttribute("form") AppointmentForm form,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "appointments/form";
    }
    // Continue business checks after binding/validation succeeds.
    return "appointments/success";
}
~~~

If the request submits `date=31/12/2026`, the formatter can convert it into a `LocalDate`. Malformed or nonexistent dates produce field errors recorded in `BindingResult`. The `BindingResult` parameter must immediately follow the related model attribute.

`@RequestBody` JSON is a separate processing path: Jackson/`HttpMessageConverter` deserializes the body. Do not assume a formatter configured for `@ModelAttribute` will automatically govern all JSON serialization/deserialization. Jackson modules and JSON rules must be configured separately according to the API contract.

## 8. Where Does Locale Come From?

Formatters accept `Locale` to know parse/print conventions. In web applications, locale is typically determined through `LocaleResolver` or `LocaleContextResolver` and request information. Common sources:

- Application default locale.
- HTTP `Accept-Language` header.
- Locale chosen by the user and stored via session/cookie configuration.
- `LocaleContextHolder` during request processing.

Do not rely solely on the server's default locale to interpret user strings. A server running in Germany does not mean every user enters data using German conventions. Machine-to-machine APIs should use contract-stable formats such as ISO-8601 for dates; locale-friendly formats belong at the UI boundary.

For money, locale determines how numbers are formatted, not the currency itself. `1.234,50` in the example only shows German numeric formatting; it does not prove the currency is EUR or anything else.

## 9. Common Mistakes

**Confusing Converter and Formatter.** A one-way converter does not automatically provide locale-aware reverse rendering. When both parse and print are needed, implement `Formatter<T>`.

**Hardcoding grouping/decimal separators.** Using `replace(",", ".")` or `Double.parseDouble` across multiple locales is error-prone. Use a locale-aware formatter.

**Confusing locale with currency.** Locale governs display convention; currency is a separate business attribute.

**Using the wrong year pattern.** In Java Time, `YYYY` is week-based-year, not the same as `uuuu` or `yyyy` in every context. Near year boundaries it can produce unexpected results.

**Formatting at the storage layer.** Storing `"1.234,50"` as a string makes arithmetic, querying, and sorting difficult. Store `BigDecimal` or an appropriate domain type; format only at UI/API boundaries.

**Parsing only part of the input.** Custom formatters must check that the entire string was consumed; otherwise inputs with trailing garbage may be accepted.

**Registering conflicting formatters.** Multiple formatters for the same type make selection confusing. Establish one clear formatter or use annotations to distinguish properties.

**Confusing MVC binding with JSON.** `WebDataBinder` and formatters for `@ModelAttribute` differ from Jackson reading `@RequestBody`. Test each path separately.

**Ignoring conversion errors.** Place `BindingResult` in the right position, display appropriate errors, and do not proceed to save data when the form has errors.

## 10. Tests You Should Have

| Scenario | What to Verify |
|---|---|
| `"42"` to Integer | Numeric value 42 |
| `"true"` to Boolean | Boolean true |
| `"1.234,50"` with German locale | Domain value 1234.50 |
| Same Price printed with US locale | US-locale decimal/grouping separators |
| String with trailing characters | Formatter rejects instead of partial parse |
| Valid date matching pattern | Parses to the exact LocalDate |
| Nonexistent date | Produces conversion error without silently adjusting to another date |
| `@NumberFormat` on field | Annotation affects conversion when TypeDescriptor metadata is used |
| MVC form with error | BindingResult contains an error for the right field |
| JSON `@RequestBody` | Test Jackson/JSON rules separately |

For custom formatters, test bidirectional parse/print, multiple locales, boundary values, empty strings, null per contract, and invalid data. If the conversion service is shared, ensure formatters hold no per-request mutable state.

## 11. Choosing the Right Configuration

- Use `DefaultFormattingConversionService` when you need a standalone service with common converters and formatters.
- Use the `DefaultFormattingConversionService(false)` constructor if you want full control registering formatters without defaults; provide complete replacement configuration.
- Use `addConverter(...)` for one-way technical/domain conversions.
- Use `addFormatter(...)` or `addFormatterForFieldType(...)` when locale-aware parse/print is needed.
- Use `@NumberFormat` when a numeric property needs its own formatting rule.
- Use `DateTimeFormatterRegistrar` to configure the group of Java Time types in Spring MVC.
- Use `WebMvcConfigurer.addFormatters(...)` to extend MVC's formatters/converters instead of creating a new service per request.
- Keep domain data as typed numbers/dates/times; format only when receiving or outputting data.
- Check conversion/validation errors and keep form binding distinct from JSON deserialization.

**Remember:** `DefaultFormattingConversionService` is a useful starting point because it combines core type conversion with default formatters. `ConversionService` answers "what type can this value be converted into?", while `Formatter` answers "in which locale does the user enter and see this value?". Proper configuration keeps data parsed and displayed consistently across a Spring application.

### References

- Spring Framework Reference — Spring Type Conversion: `ConversionService`, `Converter`, `TypeDescriptor`.
- Spring Framework Reference — Spring Field Formatting: `Formatter`, `FormattingConversionService`, and annotation formatting.
- Spring Framework Reference — Spring MVC Data Binding and `WebMvcConfigurer.addFormatters(...)`.
- Spring Framework Javadoc — `DefaultFormattingConversionService`, `FormattingConversionService`, `FormatterRegistry`, `DateTimeFormatterRegistrar`.
