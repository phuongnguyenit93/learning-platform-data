# FormatterRegistry and Ways to Register Formatters in Spring Framework

Spring Formatters convert text into Java objects and print objects back into text. A Formatter receives a Locale in both directions, making it well suited for UI input where dates, numbers, and monetary amounts vary by region. FormatterRegistry is where formatters are registered so DataBinder, Spring MVC, and ConversionService can find them.

This lesson explains registration by field type, by annotation, via FormatterRegistrar, and in MVC configuration; it also distinguishes Formatter from Converter, covers locale selection, handling malformed strings, and includes a Java 17/Spring 6.2 example.

## 1. Formatter and FormatterRegistry

The `org.springframework.format.Formatter<T>` interface combines two contracts:

- `Parser<T>`: `parse(String text, Locale locale)` reads text into an object.
- `Printer<T>`: `print(T object, Locale locale)` prints an object into text.

Core signature:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

FormatterRegistry belongs to package `org.springframework.format` and extends `ConverterRegistry`. Thus, the same registry can register both formatters and converters.

Commonly used methods:

```java
public interface FormatterRegistry extends ConverterRegistry {
    void addFormatter(Formatter<?> formatter);

    void addFormatterForFieldType(
            Class<?> fieldType, Formatter<?> formatter);

    void addFormatterForFieldType(
            Class<?> fieldType,
            Printer<?> printer,
            Parser<?> parser);

    void addFormatterForFieldAnnotation(
            AnnotationFormatterFactory<? extends Annotation> factory);
}
```

Meaning:

| API | Scope |
| --- | --- |
| addFormatter(formatter) | Formatter self-declares its target type via generic `Formatter<T>` |
| addFormatterForFieldType(type, formatter) | Uses the formatter for a specific field type |
| addFormatterForFieldType(type, printer, parser) | Registers separate printer and parser for the same type |
| addFormatterForFieldAnnotation(factory) | Formats fields or parameters marked with an annotation |
| addConverter(...) | Registers one-way type conversion |

FormatterRegistry is the place for registration. ConversionService is the place that executes conversion/formatting on demand. An object such as `DefaultFormattingConversionService` typically implements both roles.

## 2. How Is Formatter Different from Converter?

| Criterion | Formatter | Converter |
| --- | --- | --- |
| Conversion direction | Text ↔ object | Source type → target type |
| Locale | Receives Locale on parse and print | Does not receive locale directly |
| Contract | parse and print | convert |
| Typical cases | Dates, numbers, money on forms | String to domain type or between two Java types |

If you need to parse and display text data by locale, use Formatter. If you only need one-way conversion between two Java types, Converter is usually simpler. Formatter must provide both directions per the Parser/Printer contract; Converter only needs one direction.

## 3. Approach 1: Register Directly by Generic Type

When a formatter implements `Formatter<Price>`, it can be registered as:

```java
registry.addFormatter(new PriceFormatter());
```

Spring infers the target type from the declared generic argument. This is concise when a formatter has a single fixed target type. Avoid raw `Formatter` types if you want the framework to determine the target type unambiguously.

## 4. Approach 2: Register Explicitly by Field Type

When you want to declare the formatted target type explicitly:

```java
registry.addFormatterForFieldType(
        Price.class, new PriceFormatter());
```

This makes it immediately clear to readers of the configuration that `Price` is the formatted type. You can also split it into a printer and parser:

```java
registry.addFormatterForFieldType(
        Price.class, pricePrinter, priceParser);
```

Printer and parser must agree on the representation contract of `Price`. Parser reads text into `Price`; printer prints `Price` into a string. If the application only needs one direction, consider Converter instead of creating an incomplete formatter.

## 5. Approach 3: Register by Annotation

Some fields of the same Java type need different representations. For instance, two `BigDecimal` fields: one displayed as a percentage, the other as a regular decimal number. Type-based registration cannot distinguish those two contexts.

`AnnotationFormatterFactory` links an annotation to an appropriate formatter. Register the factory via:

```java
registry.addFormatterForFieldAnnotation(
        new MoneyFormatAnnotationFormatterFactory());
```

The factory supplies a formatter for fields/parameters with the matching annotation and compatible data type. It can read annotation attributes to choose patterns, styles, or formatting options.

Spring includes built-in formatter factories for common annotations like `@NumberFormat` and `@DateTimeFormat` in default conversion services. If every `Price` field shares the same display format, a type-based formatter is simpler; use annotations when policy depends on each usage site.

## 6. Approach 4: FormatterRegistrar

`FormatterRegistrar` lets you group multiple formatters/converters in one place:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

Example:

```java
public class ApplicationFormatterRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
        registry.addFormatter(new LocalDateFormatter());
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

A registrar is useful when a module has many formatters to reuse across multiple applications. However, instantiating a registrar object does not register it automatically; you must wire it to the conversion service or appropriate MVC configuration.

## 7. DefaultFormattingConversionService

`DefaultFormattingConversionService` is a conversion service implementation with a formatter registry and default rules. You can instantiate it and add custom formatters:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();
service.addFormatter(new PriceFormatter());
```

The default service provides common converters/formatters. When creating your own conversion service, decide whether you want default formatters registered or a minimal registry.

`FormattingConversionService` is the general base; `DefaultFormattingConversionService` adds standard formatters. In a Spring application, you can declare a conversion service as a bean if needed at the container level, but make sure to wire the exact registry used by the application layer.

## 8. Runnable Example: Locale-Aware PriceFormatter

Example using Java 17 and Spring Framework 6.2. The `Price` type stores `BigDecimal`. The formatter parses and prints numbers according to locale. The console program tests the formatter directly and registers it into `DefaultFormattingConversionService`.

Structure:

```text
formatter-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/format/FormatterRegistryDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'formatter-registry-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.format.FormatterRegistryDemo'
}
```

Create `src/main/java/demo/format/FormatterRegistryDemo.java`:

```java
package demo.format;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.support.DefaultFormattingConversionService;
import org.springframework.format.Formatter;

public class FormatterRegistryDemo {

    public record Price(BigDecimal amount) {
        public Price {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Price must be non-negative");
            }
        }
    }

    public static final class PriceFormatter implements Formatter<Price> {
        @Override
        public Price parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("Price is required");
            }

            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            if (!(nf instanceof DecimalFormat df)) {
                throw new IllegalStateException(
                        "Expected DecimalFormat");
            }

            df.setParseBigDecimal(true);
            String input = text.trim();
            ParsePosition position = new ParsePosition(0);
            Number parsed = df.parse(input, position);

            if (parsed == null || position.getErrorIndex() >= 0
                    || position.getIndex() != input.length()) {
                throw new IllegalArgumentException(
                        "Invalid price for locale " + locale);
            }

            return new Price((BigDecimal) parsed);
        }

        @Override
        public String print(Price price, Locale locale) {
            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            nf.setMinimumFractionDigits(2);
            nf.setMaximumFractionDigits(2);
            return nf.format(price.amount());
        }
    }

    public static void main(String[] args) {
        PriceFormatter formatter = new PriceFormatter();
        Locale germany = Locale.GERMANY;

        Price parsed = formatter.parse("1.234,50", germany);
        System.out.println("parsed=" + parsed.amount().toPlainString());
        System.out.println("printed=" + formatter.print(parsed, germany));

        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatterForFieldType(Price.class, formatter);

        LocaleContextHolder.setLocale(germany);
        try {
            Price converted = service.convert("2.345,75", Price.class);
            System.out.println("service="
                    + converted.amount().toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }

        try {
            formatter.parse("12,3x", germany);
        } catch (IllegalArgumentException exception) {
            System.out.println("invalid=rejected");
        }
    }
}
```

Run from the project directory:

```bash
gradle -q run
```

If using the Gradle Wrapper, run `./gradlew -q run` on Unix/macOS or `gradlew.bat -q run` on Windows.

Program stdout:

```text
parsed=1234.50
printed=1.234,50
service=2345.75
invalid=rejected
```

Explanation:

1. `Locale.GERMANY` uses dots for grouping and commas for decimals.
2. `parse` reads the string `1.234,50` into `BigDecimal` `1234.50`.
3. `print` renders the string `1.234,50` again.
4. `addFormatterForFieldType` registers the formatter for `Price`.
5. `LocaleContextHolder` provides the locale to the conversion service in the current context; `finally` always resets it to avoid leaking thread state.
6. `ParsePosition` confirms the entire string was consumed. Strings with extra characters like `12,3x` are rejected.

`NumberFormat`/`DecimalFormat` is created fresh on every call. Never share a single mutable `DecimalFormat` instance across multiple threads.

## 9. Registering Formatters for Spring MVC

The standard way to add global formatters for MVC is to implement `WebMvcConfigurer` and override `addFormatters`:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

This is a Java configuration needing the corresponding imports and formatter/converter classes. MVC uses this registry in conversion and data-binding flows as appropriate.

Common scenarios:

- `@RequestParam Price price`: query parameter is converted through the conversion/formatting service.
- `@ModelAttribute PaymentForm form`: `Price` properties can be bound using the formatter.
- Form redisplay: printer formats objects into text by locale when the rendering mechanism uses the formatter.

In Spring Boot, you usually only need to add a `WebMvcConfigurer` to extend existing MVC behavior. Do not add `@EnableWebMvc` merely to register a formatter, as that annotation alters Boot's MVC auto-configuration.

### 9.1. Using FormatterRegistrar with MVC

If you have a registrar grouping formatters, invoke it inside `addFormatters`:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    formatterRegistrar.registerFormatters(registry);
}
```

This assumes the registrar has been injected. Avoid registering the same formatter through multiple mechanisms if they may run together.

### 9.2. What role does @InitBinder play?

`@InitBinder` configures `WebDataBinder` for a specific controller or target object. It fits when rules should apply only within a narrow scope. For formatters used across MVC, `WebMvcConfigurer.addFormatters` is generally clearer. Do not repeat global formatter registrations inside every controller.

## 10. Choosing the Right Registration Style

| Need | Registration Style |
| --- | --- |
| Every `Price` field shares one format | `addFormatterForFieldType(Price.class, formatter)` |
| Formatter declares `Formatter<Price>` | `addFormatter(formatter)` |
| Specific fields need custom formatting | `addFormatterForFieldAnnotation(factory)` |
| Multiple formatters in the same module | `FormatterRegistrar` |
| Shared across MVC query/form binding | `WebMvcConfigurer.addFormatters(...)` |
| Only one controller needs custom binding | `@InitBinder` |
| One-way Java type conversion, no locale needed | `Converter<S,T>` |

Register by type when all properties of that type share a common policy. Register by annotation when the policy depends on each usage site.

## 11. Locale and Error Handling

Formatters receive locale in both `parse` and `print`. In MVC, locale typically comes from `LocaleResolver`/`LocaleContextResolver` and request context; `LocaleContextHolder` supplies the current locale for integration code.

Principles:

1. Use the request locale rather than assuming the server locale.
2. Use `Locale.ROOT` for language-independent technical normalization.
3. Do not use locale-based display formats as permanent storage formats.
4. For machine-to-machine APIs, prefer stable standard formats where appropriate.
5. Parse the entire string; do not accept a valid prefix and drop trailing characters.

Formatters can reject invalid input with an appropriate exception. When run through data binding, Spring can record the error into `BindingResult` so the form redisplays messages. Never return stack traces or sensitive values to clients.

Do not catch every exception and silently return a default value. If the string `abc` turns into `0`, the user never knows the data was wrong and the application may process an unintended value.

## 12. Thread-Safety and Lifecycle

Formatters are usually registered once in a shared conversion service. Therefore, a formatter must not store locale, request data, or per-request mutable state in fields.

`DecimalFormat` and `SimpleDateFormat` are unsafe to share across multiple threads. Create an instance per call or use thread-safe/immutable APIs. For example, `PriceFormatter` creates a new `NumberFormat` on each `parse`/`print` and uses the passed-in locale.

## 13. Testing FormatterRegistry

| Test | What to Verify |
| --- | --- |
| Generic registration | Service recognizes formatter by type |
| Field type registration | Fields of that type use the registered formatter |
| Annotation registration | Only annotated fields receive the custom rule |
| Valid parse | Text builds the expected object |
| Print | Object prints in the right locale |
| Different locales | Separators match each locale |
| Empty string | Matches required/empty policy |
| Trailing characters | Rejected when full string must be parsed |
| Boundary data | Negative numbers, huge numbers, nonexistent dates |
| MVC integration | Formatter is present in the real MVC registry |
| Concurrency | No unsafe mutable formatter state shared |

Unit tests can instantiate `DefaultFormattingConversionService`, register the formatter, and invoke conversions. MVC integration tests should use `MockMvc` to prove requests actually pass through MVC's registry. Checking `canConvert` alone does not prove every string parses cleanly.

## 14. Common Pitfalls

1. Confusing FormatterRegistry with ConversionService: the registry registers, the service executes.
2. Implementing only parse and forgetting print: Formatter requires both directions.
3. Using Converter when locale is needed: Converter does not receive locale directly.
4. Registering for the wrong target type: `Formatter<Price>` must be bound to `Price`.
5. Creating a formatter bean but forgetting to register it: MVC will not necessarily pick up that bean automatically.
6. Duplicate registration through multiple mechanisms: centralize configuration responsibility.
7. Sharing DecimalFormat across requests: risks race conditions.
8. Ignoring locale: the same numeric string can mean different values.
9. Accepting partial string parses: verify the entire input is consumed.
10. Assuming MVC formatters automatically apply to Jackson: JSON uses `HttpMessageConverter` and separate configuration.
11. Using formatters for business validation: validators/services remain responsible for domain rules.
12. Assuming server locale is always the user's locale: use the request locale.

## 15. Self-Practice Exercises

1. Write a `LocalDateFormatter` that parses and prints by locale; test nonexistent dates.
2. Register `PriceFormatter` using `addFormatterForFieldType`.
3. Write a `FormatterRegistrar` registering currency and date formatters.
4. Create a `@CompactNumber` annotation and `AnnotationFormatterFactory` so selected fields have custom display formatting.
5. Register the formatter in `WebMvcConfigurer.addFormatters` and test `@RequestParam`.
6. Run the same value with `Locale.US`, `Locale.GERMANY`, and `vi-VN`; explain the separators.
7. Write a multithreaded test to ensure the formatter does not share a mutable `DecimalFormat`.

You have mastered this lesson when you can explain what kinds of formatters `FormatterRegistry` accepts, how registration by type differs from registration by annotation, what `FormatterRegistrar` helps with, and why locale affects both parse and print.

## Official References

- [Spring Framework 6.2 — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework — FormatterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework — Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework — FormatterRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistrar.html)
- [Spring Framework — AnnotationFormatterFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html)
- [Spring Framework — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
