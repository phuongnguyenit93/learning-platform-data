# Relationship between ConversionService, Converter, and Formatter in Spring Framework

## 1. The problem and core idea

Data entering an application often arrives as strings: URL parameters `?page=3`, path variables `/orders/42`, form inputs `04/11/2026`. In Java, however, target objects have types like `Integer`, `OrderId`, `LocalDate`, `BigDecimal`, etc. Spring must transform source data into the right type before assigning properties or passing method arguments.

Three components are related yet have distinct responsibilities:

- **`ConversionService`**: the unified interface to *request* converting from a source type to a target type; the caller does not need to know which conversion rule is selected.
- **`Converter<S, T>`**: a *rule* converting from type `S` to type `T`, typically unidirectional and without taking a `Locale`.
- **`Formatter<T>`**: a pair of rules to *parse* `String → T` and *print* `T → String`, taking a `Locale` parameter to serve user input and display by region/language.

Key bridge: **`FormattingConversionService` is both a `ConversionService` and a `FormatterRegistry`**. It registers both `Converter` and `Formatter` into the same conversion system. Thus calling code can still invoke `conversionService.convert(...)`, while Spring chooses the matching converter or parser/printer.

## 2. Roles and APIs of each component

### 2.1. ConversionService: the common entry point

The interface lives in `org.springframework.core.convert.ConversionService`. Two commonly used operations:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
```

This is an **API signature excerpt**, not a standalone Java program. Other overloads accept `TypeDescriptor` to carry concrete type, generic, and annotation metadata for source/target.

For example, `convert("42", Integer.class)` can use a built-in converter; `convert("42", OrderId.class)` needs a custom rule if Spring does not yet know what `OrderId` is. `canConvert(...)` tells you whether the service has a conversion path for the supplied type information, not that every input value is guaranteed valid: `"abc"` can still fail when parsed as a number.

`ConversionService` is solely a **read/execute contract**. Registering converters belongs to `ConverterRegistry`; therefore you cannot call `addConverter(...)` on a variable whose static type is only `ConversionService`. Concrete classes such as `GenericConversionService` or `DefaultFormattingConversionService` expose the registration API.

### 2.2. Converter<S, T>: general type conversion rule

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Domain examples: `String → OrderId`, `String → ProductCode`, or `Long → Instant`. `Converter` has only one method; it does not automatically generate the reverse direction. If you need `OrderId → String` with custom logic, register the corresponding reverse converter or handle it appropriately.

`Converter` fits when conversion **does not depend on language/region presentation**. Examples include normalizing identifiers, parsing technical codes, or mapping one value object to another. Avoid using `Converter` to hardcode how currency or dates are parsed when that depends on each user's `Locale`.

More flexible SPIs exist such as `ConverterFactory` (families of target types) and `GenericConverter`/`ConditionalGenericConverter` (needing `TypeDescriptor` or applicability conditions), but most single-pair rules only require `Converter<S, T>`.

### 2.3. Formatter<T>: Locale-aware parse and print

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

// Methods declared by the two parent interfaces:
String print(T object, java.util.Locale locale);
T parse(String text, java.util.Locale locale)
        throws java.text.ParseException;
```

This is a **condensed signature summary**, not a complete Java file. `Formatter<T>` extends two interfaces declaring the methods above; it does not directly declare those two methods itself.

- `parse`: reads a user-entered string into a Java value, e.g., `"04/11/2026" → LocalDate` using day/month/year order.
- `print`: outputs a Java value as a string for forms/UI, e.g., `LocalDate → "04/11/2026"`.
- `locale`: governs presentation rules such as number separators, day/month/year ordering, and currency symbols. A `Formatter` can use `Locale` to pick different representations for `vi-VN` and `en-US`.

`Formatter` is especially useful at the user-interface layer. Ensure `parse`/`print` are mutually consistent for the same locale, handle invalid inputs clearly, and implement them thread-safely because formatters are typically shared across requests.

## 3. How the three components work together

```text
Source data (e.g., a String from a request)
           |
           v
Spring MVC / DataBinder / convert(...) call
           |
           v
ConversionService  [general calling interface]
           |
           v
FormattingConversionService  [implementation + registry]
           |
           +--> Converter<S,T>           : conversion without Locale
           |
           +--> Formatter<T>.parse(...)  : String -> T, with Locale
           |
           +--> Formatter<T>.print(...)  : T -> String, with Locale
           |
           v
Target-typed value / display string
```

When a `Formatter<T>` is registered into `FormattingConversionService`, Spring wraps its parser/printer functionality into appropriate conversion adapters and places them in the unified converter selection mechanism. Code calling `ConversionService` does not have to decide whether to call `parse` or `print` manually.

Distinguishing common implementations:

| Component | Role | Accepts Converter | Accepts Formatter |
| --- | --- | --- | --- |
| `ConversionService` | API for requesting type conversion | No registration API | No registration API |
| `GenericConversionService` | Conversion engine and registry | Yes | Does not directly implement `FormatterRegistry` |
| `DefaultConversionService` | `GenericConversionService` with default converters | Yes | Not directly |
| `FormattingConversionService` | Conversion engine with `FormatterRegistry` | Yes | Yes |
| `DefaultFormattingConversionService` | `FormattingConversionService` pre-populated with common converters/formatters | Yes | Yes |

Note: `FormatterRegistry extends ConverterRegistry`; hence `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` can register both `registry.addConverter(...)` and `registry.addFormatter(...)`.

## 4. Comparison to choose the right tool

| Criterion | Converter<S,T> | Formatter<T> |
| --- | --- | --- |
| Direction | Unidirectional `S → T` | Bidirectional `String ↔ T` |
| Main API | `convert(S)` | `parse(String, Locale)`, `print(T, Locale)` |
| Locale | Not passed directly | Passed directly |
| Typical use case | `String → OrderId`, domain codes | Dates, numbers, money, and locale-sensitive input/display |
| Registration | `ConverterRegistry.addConverter` | `FormatterRegistry.addFormatter` / `addFormatterForFieldType` |
| Usage from caller code | Via `ConversionService.convert` | Via `FormattingConversionService.convert` or a binder using that service |

Not every `String` source requires a `Formatter`. If the `String` is a technical code with fixed syntax, a simple `Converter<String, T>` may be the clearest choice. Conversely, user-facing dates/money typically need a formatter or annotation-based formatting.

## 5. Runnable example with Java 17 and Spring Framework 6.2.3

The following example uses **both Converter and Formatter in the same ConversionService**. `OrderId` is a locale-independent domain identifier. `LocalDate` illustrates two formatting conventions: `vi` uses `dd/MM/uuuu`, while other locales use `MM/dd/uuuu`.

Create the structure:

```text
conversion-demo/
├── pom.xml
└── src/main/java/demo/ConversionDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.3</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConversionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ConversionDemo.java`:**

```java
package demo;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class ConversionDemo {

    record OrderId(long value) {
        OrderId {
            if (value <= 0) {
                throw new IllegalArgumentException("OrderId must be positive");
            }
        }
    }

    static final class StringToOrderId implements Converter<String, OrderId> {
        @Override
        public OrderId convert(String source) {
            return new OrderId(Long.parseLong(source.trim()));
        }
    }

    static final class LocalDateFormatter implements Formatter<LocalDate> {
        private DateTimeFormatter patternFor(Locale locale) {
            String pattern = locale.getLanguage().equals("vi")
                    ? "dd/MM/uuuu"
                    : "MM/dd/uuuu";
            return DateTimeFormatter.ofPattern(pattern, locale)
                    .withResolverStyle(ResolverStyle.STRICT);
        }

        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text.trim(), patternFor(locale));
        }

        @Override
        public String print(LocalDate object, Locale locale) {
            return object.format(patternFor(locale));
        }
    }

    public static void main(String[] args) {
        var service = new DefaultFormattingConversionService();

        service.addConverter(new StringToOrderId());
        service.addFormatterForFieldType(
                LocalDate.class, new LocalDateFormatter());

        LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
        try {
            System.out.println(
                    service.canConvert(String.class, OrderId.class));
            System.out.println(service.convert(" 42 ", OrderId.class));
            System.out.println(
                    service.convert("04/11/2026", LocalDate.class));
            System.out.println(
                    service.convert(LocalDate.of(2026, 11, 4), String.class));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

In the `conversion-demo` directory, JDK 17+ and Maven are required. Run:

```bash
mvn -q compile exec:java
```

**Program stdout:**

```text
true
OrderId[value=42]
2026-11-04
04/11/2026
```

Explanation:

1. `addConverter` declares how to turn a `String` into an `OrderId`. `" 42 "` is trimmed and parsed as a `long`; the `record` prints using its default `toString()`.
2. `addFormatterForFieldType(LocalDate.class, ...)` registers both `String → LocalDate` and `LocalDate → String`. In the example, it is added after the default formatters to apply a custom convention for `LocalDate`.
3. `LocaleContextHolder.setLocale(...)` sets the locale for the current thread; Spring's adapter uses the contextual locale when invoking a `Formatter` from `FormattingConversionService`. The `finally` block restores the context, preventing locale leakage to other tasks.
4. `dd/MM/uuuu` combined with `ResolverStyle.STRICT` prevents invalid calendar dates like `31/02/2026`. This convention is **illustrative**; real applications should establish locale/formatting policies per product and avoid arbitrarily altering published API formats.
5. `service` is declared as the concrete class to register rules. Once configured, business code can accept it as `ConversionService` and simply call `convert`.

If you change the locale to `en-US` in the example, the formatter will parse/display dates as `MM/dd/uuuu`. `Converter<String, OrderId>` does not change behavior by locale. Converting `"abc"` to `OrderId` or `"31/02/2026"` to `LocalDate` causes a conversion error; `canConvert` may still return `true` because a conversion path is registered.

## 6. Application in Spring MVC and Data Binding

Typical flow for query parameters, path variables, or forms:

1. Spring receives HTTP values as strings (or collections of strings).
2. Spring MVC/`WebDataBinder` looks up conversion settings matching the parameter/field type.
3. `ConversionService` selects a registered converter or formatter parser.
4. If conversion succeeds, the typed value is passed into the controller parameter or `@ModelAttribute` object.
5. If validation is enabled, constraint checking runs on the bound data; conversion errors and validation errors are two distinct categories of issues.

Shared registration for formatting/conversion in Spring MVC:

```java
// Illustrative configuration snippet for an application with spring-webmvc.
// The converter/formatter classes are defined similarly to the Section 5 example.
@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderId());
        registry.addFormatterForFieldType(
                LocalDate.class, new LocalDateFormatter());
    }
}
```

The corresponding imports are `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, and `org.springframework.format.FormatterRegistry`. The snippet **illustrates configuration**, not a standalone runnable file; place your custom classes in the same package or import them from your application module. In Spring Boot MVC, you can implement `WebMvcConfigurer` on a `@Configuration` bean; Spring MVC will apply the registered rules within the MVC context.

For instance, if the application declares `@PathVariable OrderId id` and has registered a suitable `Converter<String, OrderId>`, the string `"42"` from the path can be converted into `OrderId` before the controller executes. For a `@ModelAttribute` containing a `LocalDate`, the formatter can parse the date string from the form. When rendering data back to the form, the `print` direction provides the locale-formatted string.

**Important note on annotations:** `@DateTimeFormat` and `@NumberFormat` attach formatting rules to fields/parameters. Spring uses `AnnotationFormatterFactory` and type/annotation metadata when the binder has sufficient context. A direct call `convert("04/11/2026", LocalDate.class)` only passes two `Class` objects, so it does not carry annotations from any field. When programmatic conversion must respect annotations, look at the overloads taking `TypeDescriptor`.

**Distinction from JSON:** `@RequestBody` accepting JSON is normally decoded via `HttpMessageConverter` (e.g., Jackson), using its own serialization/deserialization settings. Do not assume that registering an MVC `Formatter` changes how Jackson parses dates in JSON.

**Distinction from validation:** `Converter`/`Formatter` is responsible for producing a rightly typed value; `Validator`/Bean Validation annotations like `@NotNull` and `@Min` check business validity. Syntax mistakes like `"not-a-date"` can trigger a binding/type mismatch error before any business rule has a chance to inspect the `LocalDate` value. With `@ModelAttribute` forms, `BindingResult` lets the controller check bind/validation errors if placed in the right position.

## 7. Where to register and what to watch out for?

- **In standalone code:** instantiate `DefaultFormattingConversionService`, register rules, and pass it to the components needing conversion.
- **In Spring MVC:** use `WebMvcConfigurer.addFormatters(FormatterRegistry)` or the equivalent MVC configuration to register rules for MVC flows. `FormatterRegistry` accepts both converters and formatters.
- **In the Spring container generally:** a `ConversionService` bean can be configured as appropriate (where Spring integrates it); verify which subsystem actually uses that bean. Do not assume MVC, Spring Boot property binding, JSON/Jackson, and every bean in the application share one registry.
- **Per field/annotation:** prefer `@DateTimeFormat`, `@NumberFormat`, or `AnnotationFormatterFactory` when formatting varies by field, instead of installing a global rule affecting every field of that type.

When multiple rules cover the same type pair (e.g., a `String → LocalDate` converter and a `LocalDate` formatter), they may compete or make behavior unpredictable. Choose a clear strategy, register intentionally, and test actual conversion paths—especially with `Locale` and annotations.

## 8. Common pitfalls and misconceptions

| Misconception / error | Consequence | How to handle |
| --- | --- | --- |
| "`ConversionService` is itself a converter" | Mixing up the calling API with conversion rules | Treat `ConversionService` as the façade and `Converter` as a component used by the registry |
| Using `Converter<String, LocalDate>` hardcoding `dd/MM` for all users | Date `04/05` is misinterpreted under other locales | Use `Formatter` or appropriate formatting annotations |
| Thinking `Converter<S,T>` automatically supports `T → S` | Reverse rendering lacks a conversion path | Register a separate reverse rule, or use `Formatter<T>` for display scenarios |
| Thinking `canConvert == true` guarantees valid input | Specific values still fail to parse | Test edge values, catch errors at request boundary, return clear error responses |
| Sharing a mutable formatter across threads | Race conditions, corrupted formatted output | Use immutable formatters like `DateTimeFormatter`; avoid sharing mutable `SimpleDateFormat` |
| Forgetting `Locale` context or not resetting after setting it manually | Wrong locale rendering / leaking into other requests | Obtain locale from the request or use `LocaleContextHolder` properly scoped |
| Changing global formatter for `LocalDate` without checking other fields | Affects multiple forms/parameters | Prefer field annotations or narrow configuration scope |
| Expecting an MVC `Formatter` to handle `@RequestBody` JSON | Dates in JSON remain unchanged | Configure Jackson/`HttpMessageConverter` accordingly |
| Treating parse errors as business validation errors | Handling errors or guiding users in the wrong place | Separate binding type-conversion errors from `Validator` errors |

Cases to verify during QA: valid values, empty/whitespace strings, nonexistent calendar dates, negative numbers if disallowed by the domain, `vi-VN` and `en-US` locales, reverse conversion, and the same type with multiple annotations. For empty strings/nulls, how binders and default converters behave depends on the target type and configuration; establish an explicit policy before returning `null` or inventing default values.

## 9. Self-check questions

1. If the system needs to turn `"ORD-42"` into a language-independent `OrderId` value object, what should you write? **`Converter<String, OrderId>`**.
2. If a money field must display `1.234,50` or `1,234.50` depending on locale, what capability is needed? **`Formatter`/annotation-driven formatter**, having `parse` and `print` based on `Locale`.
3. Which object should controller or binder code call for uniform conversion? **`ConversionService`**.
4. Which component allows registering both `Converter` and `Formatter`? **`FormatterRegistry`**, implemented by `FormattingConversionService`.
5. If `canConvert(String.class, LocalDate.class) == true`, is `"31/02/2026"` valid? **No**; checking whether a conversion path exists is different from validating a specific value.

**Remember:** `ConversionService` is the *caller gateway*, `Converter` is a *type conversion rule*, and `Formatter` is a *locale-aware string parse/print rule*. `FormattingConversionService` combines both kinds of rules, giving Spring Data Binding and Spring MVC a consistent conversion mechanism.

## 10. Official documentation for deeper reference

- Spring Framework — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `Converter`, and registries.
- Spring Framework — [Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `FormatterRegistry`, `FormattingConversionService`.
- Spring Framework MVC — [Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registration via `WebMvcConfigurer.addFormatters`.
- Spring Framework MVC — [Controller Method Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): controller arguments and type conversion errors.