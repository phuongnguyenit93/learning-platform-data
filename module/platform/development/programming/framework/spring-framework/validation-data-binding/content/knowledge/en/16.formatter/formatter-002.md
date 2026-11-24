# Parser.parse and Printer.print in Spring Formatter

In Spring Framework, **`Parser<T>`** and **`Printer<T>`** are two interfaces that separate the two conversion directions between user text and Java types:

- **`Parser<T>.parse(String text, Locale locale)`** takes an input string and creates an object of type `T`.
- **`Printer<T>.print(T object, Locale locale)`** takes an object of type `T` and creates a string for display.

`Formatter<T>` combines both interfaces, so a single formatter can both **read input data (parse)** and **display data (print)**. This is Spring's field formatting SPI, especially suited for web UIs because the same value can be entered and displayed according to locale conventions.

For example, a user enters the code `" sku-123 "`; the parser normalizes it into `ProductCode("SKU-123")`. When rendering the object back to the UI, the printer produces the string `"SKU-123"`. For numbers and dates, the same value can have different display formats depending on `Locale`.

## 1. Two Interfaces Solving Two Different Directions

Spring defines the core contracts:

~~~java
public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}
~~~

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}
~~~

These are **simplified declarations** to illustrate the API; when writing code, import `java.util.Locale`, `java.text.ParseException`, and the corresponding Spring package.

| Interface | Method | Input | Output | When is it used? |
| --- | --- | --- | --- | --- |
| `Parser<T>` | `parse(String, Locale)` | String from client, current locale | Object of type `T` | When binding text to a field/object |
| `Printer<T>` | `print(T, Locale)` | Java object, current locale | Display string | When producing a text representation for a field/object |

The two methods are not two sides of a strictly lossless inverse function. The parser may accept multiple input forms and normalize them into a single object; the printer typically chooses one canonical display form. For example:

~~~text
User input string: " sku-123 "
                |
                v
       Parser.parse(text, locale)
                |
                v
         ProductCode("SKU-123")
                |
                v
       Printer.print(object, locale)
                |
                v
             "SKU-123"
~~~

Therefore, a round-trip usually follows **parse → print → normalized string**, and the printed string does not necessarily match the raw input verbatim.

## 2. Parser.parse — Converting a String into an Object

Signature:

~~~java
T parse(String text, Locale locale)
        throws ParseException;
~~~

- `text`: the text content to parse, for example `"21/11/2026"`, `"1,234.50"`, or `"sku-123"`.
- `locale`: the current language/region convention, affecting decimal separators, digit grouping separators, date layout, or month names.
- Return value: an object of type `T` if the string is valid.
- `ParseException`: may occur when the parser uses parsing APIs in `java.text` and cannot read the string.
- `IllegalArgumentException`: may also be used to report an invalid string under the formatter contract.

Example parser for a date using a specific pattern:

~~~java
public LocalDate parse(String text, Locale locale) throws ParseException {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    return LocalDate.parse(text, formatter);
}
~~~

This is an **illustrative method snippet**; it requires importing `java.time.LocalDate` and `java.time.format.DateTimeFormatter`. With `"31/12/2026"`, the parser produces `LocalDate.of(2026, 12, 31)`. With `"31/19/2026"`, `DateTimeParseException` may be thrown; it does not have to be `java.text.ParseException`.

The `Parser.parse` signature declares `ParseException` but does not restrict parsers to throwing only that exception type. When integrated with Spring binding, the conversion service translates appropriate parse failures into conversion/binding errors for higher layers to display.

### When does locale matter?

| Locale | Common representation of number 1234.5 |
| --- | --- |
| `Locale.US` | `1,234.5` |
| `Locale.GERMANY` | `1.234,5` |
| `Locale.FRANCE` | Decimal comma and space-style grouping separator |

Do not assume numeric strings look the same across all locales. Parser and printer must use consistent conventions or the locale provided by Spring.

## 3. Printer.print — Converting an Object into a String

Signature:

~~~java
String print(T object, Locale locale);
~~~

Example:

~~~java
public String print(LocalDate date, Locale locale) {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    return formatter.format(date);
}
~~~

This is an **illustrative method snippet**. With `LocalDate.of(2026, 12, 31)` and pattern `dd/MM/uuuu`, the result is `"31/12/2026"`.

A printer should not mutate the input object; it creates a representation string. If `object` is `null`, a clear contract must be decided: return `""`, a placeholder, or let the caller handle it. Do not assume all printers handle null identically.

### Do parse and print need to be strictly symmetric?

No. They need to be contract-compatible:

- A string emitted by the printer should be parseable back by the corresponding parser.
- The parser may accept extra whitespace, aliases, or legacy formats that the printer does not emit.
- The printer may normalize casing or format according to locale.
- Not every string accepted by the parser needs to be printed back identically.

Round-trip check:

~~~java
T value = parser.parse(text, locale);
String normalized = printer.print(value, locale);
T parsedAgain = parser.parse(normalized, locale);
~~~

This is a **conceptual test snippet**. Usually you verify that `parsedAgain` is equivalent to `value`, not that `normalized.equals(text)`.

## 4. Formatter<T> Combines Parser and Printer

Spring provides the interface:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

When a type needs both string parsing and string display, implement a formatter class:

~~~java
public final class ProductCodeFormatter
        implements Formatter<ProductCode> {

    @Override
    public ProductCode parse(String text, Locale locale) {
        // String -> ProductCode
    }

    @Override
    public String print(ProductCode value, Locale locale) {
        // ProductCode -> String
    }
}
~~~

This is an illustrative **class skeleton**, not a standalone program. Main imports:

~~~java
import java.util.Locale;
import org.springframework.format.Formatter;
~~~

`Formatter` keeps both directions aligned under a shared policy, such as the same product code normalization, date pattern, or number rules. For a formatter that does not use locale, it still must accept the `Locale` parameter per the interface; you may intentionally leave it unused and document why.

### Comparison with Converter

| Component | Direction | Accepts Locale? | Purpose |
| --- | --- | --- | --- |
| `Converter<S,T>` | `S → T` | Not directly | General-purpose type conversion |
| `Parser<T>` | `String → T` | Yes | Parsing input |
| `Printer<T>` | `T → String` | Yes | Displaying object |
| `Formatter<T>` | Both parse and print | Yes | Bidirectional field formatting |

Use `Converter` when you only need general type conversion, such as `String → UUID` or `Long → DomainId`. Use `Formatter` when you need locale-aware parsing and printing for form fields like currency, dates, or percentages. Use `Parser` or `Printer` alone if the application only needs one direction.

`ConversionService` provides a unified API for Spring to use both `Converter` and `Formatter`, though the two SPIs retain distinct roles.

## 5. Complete Java 17+ Example: Custom Formatter for Product Code

Example rules:

- Allow leading/trailing whitespace on input.
- Normalize the code to uppercase.
- Accept only two letters, a hyphen, and three digits, e.g., `AB-123`.
- Printer always emits the normalized form.
- Locale is passed by Spring but does not affect this technical code.

### 5.1. Maven project

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-formatter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` pulls in required Spring modules such as `spring-core` and `spring-beans`. In a Spring Boot application, let Boot's BOM/parent manage modules at aligned versions; do not pin a single Spring module out of sync with the stack in use.

### 5.2. Complete source code

Create `src/main/java/example/FormatterDemo.java`:

~~~java
package example;

import java.util.Locale;

import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormatterDemo {

    public record ProductCode(String value) {
    }

    public static final class ProductCodeFormatter
            implements Formatter<ProductCode> {

        @Override
        public ProductCode parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Product code must not be blank");
            }

            String normalized =
                    text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Product code must match AA-999");
            }

            // Locale does not affect technical code formatting.
            return new ProductCode(normalized);
        }

        @Override
        public String print(ProductCode value, Locale locale) {
            if (value == null) {
                return "";
            }
            return value.value();
        }
    }

    public static void main(String[] args) {
        ProductCodeFormatter formatter =
                new ProductCodeFormatter();

        Locale locale = Locale.US;

        ProductCode code =
                formatter.parse(" ab-123 ", locale);
        String display = formatter.print(code, locale);

        System.out.println("parsed=" + code.value());
        System.out.println("printed=" + display);

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addFormatter(formatter);

        ProductCode converted = conversionService.convert(
                " cd-456 ", ProductCode.class);
        String convertedBack =
                conversionService.convert(converted, String.class);

        System.out.println("service.parsed=" + converted.value());
        System.out.println("service.printed=" + convertedBack);

        try {
            formatter.parse("wrong", locale);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Key points:

- `parse` returns `ProductCode`, not a normalized `String`.
- `print` accepts `ProductCode` and produces a display string.
- `Locale.ROOT` is used to normalize uppercase consistently under technical rules, avoiding dependence on the user's machine language.
- The `locale` parameter is kept in the signature so Spring can pass context; product codes have no regional rules so it is unused.
- `DefaultFormattingConversionService.addFormatter(...)` registers both parser and printer for the corresponding type.
- Invalid input throws `IllegalArgumentException`, rather than silently creating an invalid code.

### 5.3. Compile and run

Structure:

~~~text
spring-formatter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── FormatterDemo.java
~~~

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.FormatterDemo
~~~

Output produced by `System.out.println`:

~~~text
parsed=AB-123
printed=AB-123
service.parsed=CD-456
service.printed=CD-456
invalid=IllegalArgumentException
~~~

Other Maven log lines (if any) are not part of the illustrative stdout. The example runs as a standalone Maven Java program without needing Spring Boot or an HTTP server.

When a formatter depends on locale, `FormattingConversionService` obtains the locale from the active context in formatting flows. Testing `parse/print` directly as above allows passing an explicit `Locale` without depending on thread context.

## 6. Registering a Formatter in Spring MVC

Spring MVC can register a formatter so `WebDataBinder` and `ConversionService` use it during form binding:

~~~java
@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new ProductCodeFormatter());
    }
}
~~~

This is a **configuration snippet** that requires importing `@Configuration`, `FormatterRegistry`, and `WebMvcConfigurer`. `ProductCodeFormatter` must reside in an application package and be imported.

JavaBean DTO:

~~~java
public class OrderForm {
    private ProductCode productCode;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }
}
~~~

This class needs an import or to be in the same package as `ProductCode`. When a form request sends `productCode=ab-123`, the parser can convert it into `ProductCode("AB-123")`. When redisplaying the field, the printer can produce the appropriate string.

Controller snippet:

~~~java
@PostMapping("/orders")
String submit(
        @ModelAttribute OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "order-form";
    }
    return "order-success";
}
~~~

This is a **snippet** requiring `@Controller`, MVC imports, and views. `BindingResult` is placed immediately after the model attribute to capture field parse/conversion errors. Formatters only perform conversion; business validation must be configured separately.

### With Spring WebFlux

WebFlux also has a similar formatting/conversion system via `FormattingConversionService` and WebFlux configuration. Use `WebFluxConfigurer#addFormatters(FormatterRegistry)`:

~~~java
@Configuration
public class ReactiveFormattingConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new ProductCodeFormatter());
    }
}
~~~

This is a **WebFlux configuration snippet**, requiring imports for `org.springframework.web.reactive.config.WebFluxConfigurer` and related classes. Do not mix `WebMvcConfigurer` and `WebFluxConfigurer` in the same configuration just because both interfaces have an `addFormatters` method; choose the web stack your application uses.

## 7. Annotation-Driven Formatting and Scope of Application

In addition to type-based registration, Spring can register formatters by field annotation via `AnnotationFormatterFactory`. This is useful when the same Java type requires multiple formats depending on field annotation or context.

Spring includes built-in annotations such as `@NumberFormat` and `@DateTimeFormat`:

~~~java
public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate invoiceDate;

    // Getter/setter...
}
~~~

This is an **illustrative class snippet**, requiring imports for `NumberFormat`, `DateTimeFormat`, `BigDecimal`, and `LocalDate`. Built-in annotations reduce the need to write custom formatters for common cases.

If a type has different rules per field, a **field annotation formatter** may fit better than global registration by type. If every field of type `ProductCode` always shares the same contract, a type-based formatter is usually simpler.

## 8. Locale: parse and print Must Be Consistent

Locale is a critical parameter that helps formatters work properly with user conventions. Example with the number `1234.5`:

~~~java
NumberStyleFormatter formatter = new NumberStyleFormatter();
String us = formatter.print(1234.5, Locale.US);
String de = formatter.print(1234.5, Locale.GERMANY);
~~~

This is an **excerpt**, requiring import of `org.springframework.format.number.NumberStyleFormatter`. Illustrative output is typically:

~~~text
us=1,234.5
de=1.234,5
~~~

When parsing, `"1,234.5"` under the US locale can be interpreted as 1234.5, whereas under the German locale it may be invalid or mean something different. Therefore:

1. Use the locale provided by the user/request context.
2. Avoid relying on `Locale.getDefault()` inside formatters for all requests; the server default may differ from the user's.
3. The same field should parse and print using consistent rules.
4. Test multiple important locales, including decimal and grouping separators.
5. If data is a technical code, ID, or locale-independent token, use a stable rule such as `Locale.ROOT`.

Locale is not just about translating message text. It also affects how data is written and read.

## 9. Thread Safety and State in Formatter

Formatters are typically registered in a shared `ConversionService` across the application. Implementations should be **thread-safe**:

- Do not store `ParsePosition`, `StringBuilder`, or current request values in mutable fields reused across requests.
- Do not share a mutable `SimpleDateFormat` across threads; use immutable/thread-safe APIs like `DateTimeFormatter`.
- Do not mutate formatter configuration after placing it into a shared registry.
- Keep state in local variables within `parse`/`print`.
- If caching is needed, use thread-safe structures and cache only immutable data.

`ProductCodeFormatter` in section 5 is stateless: the `normalized` variable only exists during the method call; no request value is stored in a field. Hence the same formatter instance can be reused.

**Do not confuse with PropertyEditor:** JavaBeans `PropertyEditor` holds `setValue/getValue` state, whereas `Formatter<T>` receives input and returns output directly through method parameters and is usually much easier to implement thread-safely.

## 10. Common Mistakes When Writing Parser and Printer

### Implementing only parse and forgetting print

If a field needs both display and input handling, having only a parser may suffice for binding but fails to provide a full bidirectional formatter. Implement `Formatter<T>` or register parser/printer separately if intentional.

### Printer not following the same contract as parser

If `print` produces a string that `parse` cannot read, data may display properly but fail upon resubmission. Test round-trips across multiple locales and boundary values.

### Failing to handle empty strings or null

`""`, whitespace-only strings, and `null` can carry different meanings: left blank, cleared value, or missing required input. The parser should follow its chosen contract; validation decides whether a field is required.

### Swallowing ParseException and returning a default value

Turning invalid input into `0`, a default date, or an empty object can hide user errors and produce corrupt data. Throw an appropriate exception so Spring records a binding error.

### Using formatter for non-text conversions

If you only convert `Long → CustomerId` without locale-based input/display, `Converter<Long, CustomerId>` is more appropriate. A formatter adds value when one side is client text.

### Using the server's default locale

An application on a server whose locale differs from the user's can misread decimal separators or dates. Use the passed-in `Locale` and test accordingly.

### Confusing conversion with validation

`parse("15", locale)` may succeed in creating the number 15. If business rules require a minimum age of 18, that is validation, not a parse failure.

### Testing only the formatter directly without testing registry/binder

Correct `parse/print` when called directly does not prove `FormattingConversionService` or `WebDataBinder` has the formatter registered in the right scope. Also test request binding and value rendering in the application.

## 11. Self-Check Exercises

1. How do `Parser<T>` and `Printer<T>` differ in conversion direction?
2. Why does `Formatter<T>` extend both interfaces?
3. What problem does a `DateFormatter` solve by accepting `Locale`?
4. If the printer prints `"31.12.2026"` but the parser only reads `"dd/MM/yyyy"`, what happens when the form is resubmitted?
5. When you only need to convert `String → UUID` without locale-aware display, should you choose `Converter` or `Formatter`?
6. Why should you not keep a mutable `SimpleDateFormat` as a singleton field inside a formatter?
7. If input `"15"` parses successfully but fails the minimum age check, does the error belong to parsing or validation?
8. How do you register the same formatter in Spring MVC and WebFlux without mixing configurations of the two stacks?

**Remember:** `Parser.parse(String, Locale)` turns text into a Java type; `Printer.print(T, Locale)` turns an object into text; `Formatter<T>` combines both directions. Use a formatter when a field needs locale-aware parse/print, register it in the right `ConversionService`/web configuration scope, and keep the implementation thread-safe. Successful parsing only proves the string can build an object, not that the data is business-valid.

## Official References

- [Spring Framework Javadoc — Parser](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework Javadoc — Printer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Printer.html)
- [Spring Framework Javadoc — Formatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework Javadoc — FormatterRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework Reference — ConversionService](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework MVC — Data Binding and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
