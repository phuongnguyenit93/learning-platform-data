# Writing a Converter for Business Codes and a Locale-Aware Formatter

## Goal and Problem Statement

In Spring MVC, values from URLs, query strings, and forms usually start as `String`. The business layer should not have to manually trim, normalize, validate code patterns, or guess decimal separators in every controller. This hands-on lesson in the Spring Framework — validation-data-binding module builds:

1. `Converter<String, ProductCode>` turning `" abc-0042 "` into the domain value `ProductCode("ABC-0042")`, enforcing a pattern of three Latin letters and four digits. Identifier codes are **Locale-independent**.
2. `Converter<ProductCode, String>` to print the code inside a Spring form instead of the record's default `toString()`.
3. `Formatter<MoneyAmount>` to parse and print `BigDecimal` according to the request `Locale`. For example, `1.234,50` with `vi-VN` and `1,234.50` with `en-US` represent the same value `1234.50`.
4. `WebMvcConfigurer.addFormatters` to register these components with Spring MVC's `FormattingConversionService`.
5. A REST controller accepting `@PathVariable ProductCode` and `@RequestParam MoneyAmount`, a Thymeleaf form using `@ModelAttribute`/`BindingResult`, and a JUnit/MockMvc test suite.
6. Distinguishing type conversion errors from Bean Validation, and distinguishing MVC conversion from JSON `@RequestBody` handled by Jackson.

The lesson includes a complete Maven project for **Java 17+ and Spring Boot 3.5.7**. A newer JDK can be used, but when upgrading Spring/Boot you must check the documentation for that exact version.

### Why Not Keep Using String and double?

A request:

~~~http
GET /api/quotes?code=abc-0042&amount=1.234,50
Accept-Language: vi-VN
~~~

carries two strings with different semantics: `code` is a machine-readable identifier and `amount` is a number formatted by language/region. If you handle both by string concatenation or `Double.parseDouble`, codes may lack invariants, numbers can get the wrong decimal separator, and monetary math can suffer binary floating-point errors.

Target design:

~~~text
HTTP "abc-0042"
  → ProductCodeConverter.convert(...)
  → ProductCode("ABC-0042")      [Locale.ROOT]

HTTP "1.234,50" + vi-VN
  → MoneyAmountFormatter.parse(...)
  → MoneyAmount(BigDecimal 1234.50)
  → Bean Validation / business rules

MoneyAmount(1234.50) + en-US
  → MoneyAmountFormatter.print(...)
  → "1,234.50"
~~~

### Demo Conventions

| Part | Convention |
| --- | --- |
| Business code | `AAA-0000`, three `A-Z` letters, `-`, four ASCII digits |
| Normalization | Strip leading/trailing whitespace, uppercase with `Locale.ROOT` |
| Amount | `BigDecimal` with scale 2, no silent rounding |
| Vietnamese locale | `1.234,50` |
| US English locale | `1,234.50` |
| Valid form input | Minimum amount 0.01 and at most eight integer digits |
| API response data | Canonical decimal string `1234.50`, independent of Locale |
| Errors | Parser/Converter fails → binding error or HTTP 400 |

**Locale does not mean currency.** The same USD amount can be displayed under `vi-VN` or `en-US`. If multiple currencies are supported, model `Currency` explicitly—never guess currency from Locale.

## 1. How Does Converter Differ from Formatter?

### 1.1. Converter<S,T> Has No Locale

`org.springframework.core.convert.converter.Converter<S,T>` has only one method:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

This is an illustrative signature; you do not need to define this interface yourself. `Converter` is well suited for turning an identifier string into a domain type with **fixed** rules. Never use `source.toUpperCase()` relying on the default JVM Locale for ASCII codes: in some languages such as Turkish, the letter `i` has different uppercasing rules. Use:

~~~java
source.strip().toUpperCase(Locale.ROOT)
~~~

to normalize identifiers independently of the user's language.

### 1.2. Formatter<T> Is Bidirectional and Locale-Aware

`org.springframework.format.Formatter<T>` combines `Printer<T>` and `Parser<T>`:

~~~java
public interface Printer<T> {
    String print(T value, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException;
}

public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

This is also a signature diagram, not source code to compile. `parse` reads localized input; `print` formats the domain value for display. Thus a formatter can be invoked both when **receiving** a form and when **rendering** a form, not only when a parser is called manually.

### 1.3. ConversionService and Scope of Operation

`ConversionService` is Spring's type conversion interface; `FormattingConversionService` adds formatting. Spring MVC has a conversion service used for binding query, path, and form values. Spring Boot has a separate conversion service for `application.properties`/`application.yaml`. Do not assume registering in one place automatically applies everywhere.

| Usage site | Goes through MVC converter/formatter? |
| --- | --- |
| `@PathVariable ProductCode` | Yes |
| `@RequestParam MoneyAmount` | Yes |
| `@ModelAttribute OfferForm.amount` | Yes, via WebDataBinder |
| Thymeleaf `th:field="*{amount}"` | Yes, via Spring-aware form binding |
| `@RequestBody JSON` | Not via this pipeline; handled by Jackson |
| JSON `@ResponseBody` | Does not automatically use all MVC formatters for serialization |
| `@ConfigurationProperties` | Boot's configuration conversion service, separate from MVC |

A **Converter** is one-way (String→domain) and does not automatically generate domain→String. For forms, we explicitly register the reverse `ProductCode→String` direction.

## 2. Project Organization

~~~text
business-code-locale-format/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/formatdemo/
    │   │   ├── Application.java
    │   │   ├── ProductCode.java
    │   │   ├── ProductCodeConverter.java
    │   │   ├── ProductCodeToStringConverter.java
    │   │   ├── MoneyAmount.java
    │   │   ├── MoneyAmountFormatter.java
    │   │   ├── WebFormatConfiguration.java
    │   │   ├── QuoteController.java
    │   │   ├── OfferForm.java
    │   │   ├── OfferPageController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/offers/
    │           ├── form.html
    │           └── success.html
    └── test/java/com/example/formatdemo/
        ├── ProductCodeConverterTest.java
        ├── MoneyAmountFormatterTest.java
        ├── QuoteMvcTest.java
        └── OfferFormMvcTest.java
~~~

All Java files share the `com.example.formatdemo` package. No database or external API is needed; the example separates conversion/validation from persistence logic.

### 2.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>business-code-locale-format</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` provides Spring MVC/Jackson, the Thymeleaf starter provides Spring form binding, the Validation starter provides Jakarta Bean Validation, and the test starter provides MockMvc/JUnit. The Boot parent manages compatible Spring Framework versions; do not override an individual Spring JAR outside the BOM without evaluating it first.

### 2.2. Application.java

~~~java
package com.example.formatdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 2.3. ProductCode.java

~~~java
package com.example.formatdemo;

import java.util.Objects;
import java.util.regex.Pattern;

public record ProductCode(String value) {

    private static final Pattern FORMAT =
            Pattern.compile("[A-Z]{3}-[0-9]{4}");

    public ProductCode {
        Objects.requireNonNull(value, "code is required");

        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Product code must be AAA-0000");
        }
    }
}
~~~

The canonical record constructor protects the domain invariant: even if internal code calls `new ProductCode("ABC-42")` directly, an invalid value is rejected. The converter normalizes before calling the constructor; do not duplicate the regex in controllers or services.

### 2.4. ProductCodeConverter.java

~~~java
package com.example.formatdemo;

import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {

        String canonical =
                source.strip().toUpperCase(Locale.ROOT);

        if (canonical.isEmpty()) {
            throw new IllegalArgumentException(
                    "Product code is required");
        }

        return new ProductCode(canonical);
    }
}
~~~

`strip()` removes leading and trailing whitespace. `Locale.ROOT` guarantees stable machine-readable output when HTTP `Accept-Language` or JVM locale changes. The converter does not query the database, has no side effects, and makes no authorization decisions. When `source` is null, Spring `ConversionService` normally handles null before calling the converter; the demo is not designed for direct `convert(null)` calls.

### 2.5. ProductCodeToStringConverter.java

~~~java
package com.example.formatdemo;

import org.springframework.core.convert.converter.Converter;

public final class ProductCodeToStringConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

The reverse direction lets `th:field="*{productCode}"` output `ABC-0042` instead of the record's `toString()` like `ProductCode[value=ABC-0042]`.

### 2.6. MoneyAmount.java

~~~java
package com.example.formatdemo;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record MoneyAmount(
        @DecimalMin("0.01")
        @Digits(integer = 8, fraction = 2)
        BigDecimal value) {

    public MoneyAmount {
        Objects.requireNonNull(value, "amount is required");
        value = value.setScale(
                2, RoundingMode.UNNECESSARY);
    }
}
~~~

`BigDecimal` stores exact decimal numbers. The constructor enforces scale 2 and **never rounds silently**. `@DecimalMin` and `@Digits` are Bean Validation constraints: they are checked after binding when `@Valid` applies, not on every constructor invocation. A `MoneyAmount(-1.00)` can parse successfully yet fail `@DecimalMin` on the form.

### 2.7. MoneyAmountFormatter.java

~~~java
package com.example.formatdemo;

import org.springframework.format.Formatter;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public final class MoneyAmountFormatter
        implements Formatter<MoneyAmount> {

    @Override
    public MoneyAmount parse(String text, Locale locale)
            throws ParseException {

        String input = text.strip();

        if (input.isEmpty()) {
            throw new ParseException(
                    "Amount must not be empty", 0);
        }

        NumberFormat format =
                NumberFormat.getNumberInstance(locale);

        if (!(format instanceof DecimalFormat decimal)) {
            throw new ParseException(
                    "Unsupported number format", 0);
        }

        decimal.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = decimal.parse(input, position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getErrorIndex() >= 0
                || position.getIndex() != input.length()) {
            throw new ParseException(
                    "Invalid localized amount",
                    Math.max(0, position.getIndex()));
        }

        try {
            return new MoneyAmount(amount);
        } catch (ArithmeticException ex) {
            throw new ParseException(
                    "Amount must have at most two decimals",
                    position.getIndex());
        }
    }

    @Override
    public String print(MoneyAmount object, Locale locale) {
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);

        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(
                RoundingMode.UNNECESSARY);

        return format.format(object.value());
    }
}
~~~

**Analyzing `parse`:**

- `NumberFormat.getNumberInstance(locale)` creates a parser suited to the request locale.
- `DecimalFormat.setParseBigDecimal(true)` ensures the result is a `BigDecimal`, avoiding `doubleValue()` which could lose precision.
- `ParsePosition` checks that the entire input was consumed. `NumberFormat.parse(String)` alone can accept a valid prefix and ignore the suffix: `1,234.50oops` must not be treated as valid.
- The `MoneyAmount` constructor protects the scale; if there are more than two significant fraction digits it throws `ArithmeticException`, which is converted into `ParseException`.
- The parser does not decide on its own whether negative amounts are allowed; that is a constraint/domain policy.

**Analyzing `print`:**

- Creates a fresh `NumberFormat` each time. `DecimalFormat` is mutable and not thread-safe if shared as a singleton across requests.
- Enables grouping and two fraction digits; `vi-VN`/`en-US` determines the separators.
- `RoundingMode.UNNECESSARY` prevents unintended rounding because `MoneyAmount` has already normalized the scale.

**Limitation:** `DecimalFormat` can be fairly lenient with grouping separators. Checking full-string consumption **does not guarantee strict grouping grammar in every case**. A string valid in one locale can be interpreted as a different number in another locale. For sensitive financial data, declare the input locale clearly, add strict grammar validation, enforce length limits, and use a canonical data format when appropriate.

### 2.8. WebFormatConfiguration.java

~~~java
package com.example.formatdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormatConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(
            FormatterRegistry registry) {

        registry.addConverter(
                new ProductCodeConverter());

        registry.addConverter(
                new ProductCodeToStringConverter());

        registry.addFormatter(
                new MoneyAmountFormatter());
    }
}
~~~

Registered for **Spring MVC**. Do not add `@EnableWebMvc` in Spring Boot just to register a converter: doing so can disable Boot's MVC auto-configuration. If multiple formatters need dependency injection, you can use Spring beans or `FormatterRegistrar`; for pure value converters, instantiating objects directly in the registry is straightforward.

### 2.9. QuoteController.java

~~~java
package com.example.formatdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {

    public record ProductView(String code) {
    }

    public record QuoteView(
            String code, String amount) {
    }

    @GetMapping("/api/products/{code}")
    public ProductView product(
            @PathVariable("code") ProductCode code) {

        return new ProductView(code.value());
    }

    @GetMapping("/api/quotes")
    public QuoteView quote(
            @RequestParam("code") ProductCode code,
            @RequestParam("amount") MoneyAmount amount) {

        return new QuoteView(
                code.value(),
                amount.value().toPlainString());
    }
}
~~~

This is **real** Spring MVC argument conversion, without calling converters manually inside the controller. The JSON returns the amount as a canonical decimal string `"1234.50"` so machine consumers do not have to guess the Locale. If choosing a JSON number instead of a string, define a clear schema/precision policy for JS clients.

### 2.10. OfferForm.java

~~~java
package com.example.formatdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public class OfferForm {

    @NotNull
    private ProductCode productCode;

    @NotNull
    @Valid
    private MoneyAmount amount;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }

    public MoneyAmount getAmount() {
        return amount;
    }

    public void setAmount(MoneyAmount amount) {
        this.amount = amount;
    }
}
~~~

`@Valid` on `MoneyAmount` is required so `@DecimalMin` and `@Digits` on `MoneyAmount.value` are validated. `@NotNull` alone only ensures the form field is non-null; it does not cascade automatically.

### 2.11. OfferPageController.java

~~~java
package com.example.formatdemo;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

import java.math.BigDecimal;

@Controller
public class OfferPageController {

    @GetMapping("/offers/new")
    public String showForm(Model model) {
        OfferForm form = new OfferForm();

        form.setProductCode(
                new ProductCode("ABC-1234"));

        form.setAmount(new MoneyAmount(
                new BigDecimal("1234.50")));

        model.addAttribute("offerForm", form);
        return "offers/form";
    }

    @PostMapping(
            path = "/offers/new",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public String submit(
            @Valid @ModelAttribute("offerForm") OfferForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            return "offers/form";
        }

        model.addAttribute(
                "code", form.getProductCode().value());

        model.addAttribute(
                "canonicalAmount",
                form.getAmount().value().toPlainString());

        return "offers/success";
    }
}
~~~

`BindingResult` is placed **immediately after** `@ModelAttribute`. When conversion or validation fails, the controller re-renders the form and Spring preserves the errors in the model. The demo returns the success view directly; in production you can use POST/Redirect/GET and a CSRF policy to avoid double submission.

### 2.12. ApiErrorAdvice.java

~~~java
package com.example.formatdemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(
            MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> invalidParameter(
            MethodArgumentTypeMismatchException ex) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.BAD_REQUEST,
                        "A path or query value is invalid.");

        body.setTitle("Invalid parameter");
        body.setProperty("code", "INVALID_PARAMETER");

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Unconvertible REST path/query parameters typically produce `MethodArgumentTypeMismatchException` and HTTP 400. The advice exposes only a safe error code, without leaking raw rejected input or exception internals. The form uses `BindingResult` and therefore does not need to throw the same exception to render field errors.

### 2.13. application.properties

~~~properties
server.port=8080
spring.thymeleaf.cache=false
server.error.include-message=never
~~~

Template caching is disabled only for convenient editing while learning; production can enable it. No separate conversion service configuration for Boot properties is needed.

### 2.14. templates/offers/form.html

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Offer editor</title>
</head>
<body>
<h1>Edit offer</h1>

<form th:action="@{/offers/new}"
      th:object="${offerForm}"
      method="post">

    <label for="productCode">Product code</label>
    <input type="text" th:field="*{productCode}">

    <label for="amount">Amount</label>
    <input type="text" th:field="*{amount}">

    <ul th:if="${#fields.hasAnyErrors()}">
        <li th:each="error : ${#fields.allErrors()}"
            th:text="${error}">Invalid value</li>
    </ul>

    <button type="submit">Save</button>
</form>
</body>
</html>
~~~

On a GET request with `Accept-Language: vi-VN`, `th:field` calls `Formatter.print` to render amount `1.234,50`; with `en-US`, it renders `1,234.50`. The reverse `ProductCode` converter prints `ABC-1234`. The form intentionally uses `type="text"` inputs because HTML `type="number"` follows browser-specific rules and does not accept the same localized strings by default.

### 2.15. templates/offers/success.html

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Offer accepted</title>
</head>
<body>
<h1>Offer accepted</h1>
<p>Product: <strong th:text="${code}">ABC-1234</strong></p>
<p>Canonical amount:
    <strong th:text="${canonicalAmount}">1234.50</strong>
</p>
<a th:href="@{/offers/new}">New offer</a>
</body>
</html>
~~~

The success view displays the canonical amount so learners can distinguish machine data from the form's localized string.

## 3. Running and HTTP Output

From the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

### 3.1. Business Code in URL

~~~bash
curl -i "http://localhost:8080/api/products/abc-0042"
~~~

HTTP 200 result:

~~~json
{"code":"ABC-0042"}
~~~

Calling `/api/products/abc-42` causes the converter/record to reject the malformed code; the advice returns HTTP 400 with `"code":"INVALID_PARAMETER"`.

### 3.2. Monetary Amount in Vietnamese Locale

~~~bash
curl -i \
  -H "Accept-Language: vi-VN" \
  "http://localhost:8080/api/quotes?code=abc-0042&amount=1.234,50"
~~~

HTTP 200:

~~~json
{
  "code": "ABC-0042",
  "amount": "1234.50"
}
~~~

### 3.3. Monetary Amount in US English Locale

~~~bash
curl -i \
  -H "Accept-Language: en-US" \
  "http://localhost:8080/api/quotes?code=abc-0042&amount=1,234.50"
~~~

HTTP 200 with the **exact same** canonical JSON:

~~~json
{
  "code": "ABC-0042",
  "amount": "1234.50"
}
~~~

### 3.4. Rendering and Submitting the Form

~~~bash
curl -s -H "Accept-Language: vi-VN" \
  "http://localhost:8080/offers/new"
~~~

The amount input in HTML has value `1.234,50`; under `en-US` it is `1,234.50`.

~~~bash
curl -i -X POST "http://localhost:8080/offers/new" \
  -H "Accept-Language: vi-VN" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "productCode=abc-0042" \
  --data-urlencode "amount=1.234,50"
~~~

The success view displays product code `ABC-0042` and canonical amount `1234.50`. Input `1.234,50oops` is recorded as a binding error instead of creating an offer.

## 4. Unit Tests: ProductCodeConverter

File `src/test/java/com/example/formatdemo/ProductCodeConverterTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class ProductCodeConverterTest {

    private final ProductCodeConverter incoming =
            new ProductCodeConverter();

    private final ProductCodeToStringConverter outgoing =
            new ProductCodeToStringConverter();

    @Test
    void normalizesCode() {
        assertEquals("ABC-0042",
                incoming.convert("  abc-0042  ").value());
    }

    @Test
    void rejectsBadCodes() {
        assertThrows(IllegalArgumentException.class,
                () -> incoming.convert("abc-42"));

        assertThrows(IllegalArgumentException.class,
                () -> incoming.convert("abc_0042"));
    }

    @Test
    void reverseConverterPrintsPlainCode() {
        assertEquals("ABC-0042",
                outgoing.convert(
                        new ProductCode("ABC-0042")));
    }

    @Test
    void normalizationIsIndependentOfDefaultLocale() {
        Locale old = Locale.getDefault();
        try {
            Locale.setDefault(
                    Locale.forLanguageTag("tr-TR"));

            assertEquals("MIX-0042",
                    incoming.convert("mix-0042").value());
        } finally {
            Locale.setDefault(old);
        }
    }
}
~~~

A test that changes the JVM default Locale modifies **global state**; if CI runs tests in parallel, use a resource lock or isolate this test. `finally` restores the Locale. The test proves the machine-readable code does not depend on the uppercasing rules of a locale like `tr-TR`.

## 5. Unit Tests: MoneyAmountFormatter

File `src/test/java/com/example/formatdemo/MoneyAmountFormatterTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.text.ParseException;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class MoneyAmountFormatterTest {

    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private static final Locale EN = Locale.US;

    private final MoneyAmountFormatter formatter =
            new MoneyAmountFormatter();

    @Test
    void parsesVietnameseAmount() throws Exception {
        MoneyAmount amount =
                formatter.parse("1.234,50", VI);

        assertEquals(new BigDecimal("1234.50"),
                amount.value());
    }

    @Test
    void parsesEnglishAmount() throws Exception {
        MoneyAmount amount =
                formatter.parse("1,234.50", EN);

        assertEquals(new BigDecimal("1234.50"),
                amount.value());
    }

    @Test
    void printsVietnameseAmount() {
        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        assertEquals("1.234,50",
                formatter.print(money, VI));
    }

    @Test
    void printsEnglishAmount() {
        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        assertEquals("1,234.50",
                formatter.print(money, EN));
    }

    @Test
    void roundTripPreservesDecimal()
            throws Exception {

        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        for (Locale locale : new Locale[]{VI, EN}) {
            String displayed =
                    formatter.print(money, locale);

            assertEquals(money.value(),
                    formatter.parse(
                            displayed, locale).value());
        }
    }

    @Test
    void trailingGarbageIsRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse(
                        "1,234.50oops", EN));
    }

    @Test
    void tooManyFractionDigitsAreRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse(
                        "1,234.567", EN));
    }

    @Test
    void blankInputIsRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse("  ", VI));
    }

    @Test
    void negativeAmountCanParseBeforeValidation()
            throws Exception {

        assertEquals(new BigDecimal("-1.00"),
                formatter.parse("-1,00", VI).value());
    }
}
~~~

`Formatter.parse` only checks numeric structure/scale. Bean Validation enforces `@DecimalMin` and `@Digits` per policy. On different JDKs or locale data providers, grouping characters can differ: if a test deviates from expectations, inspect the Locale/`DecimalFormatSymbols` data before assuming business conversion is broken.

## 6. MockMvc: REST Path/Query

File `src/test/java/com/example/formatdemo/QuoteMvcTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productPathUsesConverter() throws Exception {
        mvc.perform(get("/api/products/abc-0042"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("ABC-0042"));
    }

    @Test
    void invalidPathReturns400() throws Exception {
        mvc.perform(get("/api/products/abc-42"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"));
    }

    @Test
    void vietnameseAmountInQuery() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "vi-VN")
                        .param("code", "abc-0042")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("ABC-0042"))
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"));
    }

    @Test
    void englishAmountInQuery() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "en-US")
                        .param("code", "abc-0042")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"));
    }

    @Test
    void malformedAmountReturns400() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "en-US")
                        .param("code", "ABC-0042")
                        .param("amount", "1,234.50oops"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"));
    }

    @Test
    void codeDoesNotDependOnLocale() throws Exception {
        mvc.perform(get("/api/products/mix-0042")
                        .header("Accept-Language", "tr-TR"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("MIX-0042"));
    }
}
~~~

MockMvc exercises the actual Spring MVC argument resolver, `ConversionService`, and advice without opening a socket. It proves the converters/formatters are properly registered, not just classes with `convert`/`parse` methods.

## 7. MockMvc: Thymeleaf Form

File `src/test/java/com/example/formatdemo/OfferFormMvcTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OfferFormMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void vietnameseFormPrintsLocalizedAmount()
            throws Exception {

        mvc.perform(get("/offers/new")
                        .header("Accept-Language", "vi-VN"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(content().string(
                        containsString("1.234,50")))
                .andExpect(content().string(
                        containsString("ABC-1234")));
    }

    @Test
    void englishFormPrintsLocalizedAmount()
            throws Exception {

        mvc.perform(get("/offers/new")
                        .header("Accept-Language", "en-US"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(content().string(
                        containsString("1,234.50")));
    }

    @Test
    void vietnameseFormAcceptsValidInput()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "abc-0042")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/success"))
                .andExpect(model().attribute(
                        "code", "ABC-0042"))
                .andExpect(model().attribute(
                        "canonicalAmount", "1234.50"));
    }

    @Test
    void englishFormAcceptsValidInput()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/success"))
                .andExpect(model().attribute(
                        "canonicalAmount", "1234.50"));
    }

    @Test
    void invalidCodeCreatesBindingError()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "bad")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "productCode"));
    }

    @Test
    void invalidAmountTextCreatesBindingError()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "1.234,50oops"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount"));
    }

    @Test
    void negativeAmountFailsNestedBeanValidation()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "-1,00"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount.value"));
    }

    @Test
    void oversizedAmountFailsDigitsConstraint()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "123,456,789.00"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount.value"));
    }
}
~~~

**Interpreting results accurately:**

- `productCode=bad` and `amount=1.234,50oops`: **conversion** errors on the corresponding fields, typically code `typeMismatch`.
- `amount=-1,00`: parsing succeeds, but `@DecimalMin` validation on nested `amount.value` fails.
- An amount with nine integer digits: parsing succeeds, `@Digits(integer=8)` fails.
- A form with errors returns HTTP 200 because the controller intentionally re-renders HTML; tests should assert the view and `BindingResult`, rather than equating HTTP 200 with valid data.
- Invalid JSON input does not go through the same `BeanPropertyBindingResult`/formatter; it must be tested separately at the Jackson boundary.

The full demo suite has **27 tests**: four converter tests, nine formatter tests, six REST MockMvc tests, and eight form MockMvc tests. Run:

~~~bash
mvn test
~~~

Or individually:

~~~bash
mvn -Dtest=ProductCodeConverterTest test
mvn -Dtest=MoneyAmountFormatterTest test
mvn -Dtest=QuoteMvcTest test
mvn -Dtest=OfferFormMvcTest test
~~~

## 8. Locale Resolution and Formatting Traps

### 8.1. Where Does the Request Locale Come From?

Spring MVC normally uses `AcceptHeaderLocaleResolver` to choose the Locale from `Accept-Language` when no other policy is configured. In MockMvc, the `Accept-Language: vi-VN` header passes `Locale.forLanguageTag("vi-VN")` to the formatter; `en-US` provides US symbols.

If you want to switch languages via `?lang=vi`, you must configure an appropriate `LocaleResolver`/`LocaleChangeInterceptor`; do not assume the `lang` query parameter automatically switches Spring's locale.

### 8.2. A String Can Be Interpreted Differently in Another Locale

`-1,00` in `vi-VN` means minus one, whereas in `en-US` the comma usually acts as a grouping separator and can parse as minus one hundred. A parser given the wrong Locale can return a **different number** instead of an error. `ParsePosition` verifying full-string consumption is necessary but not sufficient for strict grammar.

In real applications, keep the Locale consistent between rendering the form and submitting it; if that cannot be guaranteed, prefer **canonical decimal input** for APIs and localized display only in the UI.

### 8.3. DecimalFormat Is Not Thread-Safe

Do not do:

~~~java
private static final DecimalFormat FORMAT =
        new DecimalFormat("#,##0.00");
~~~

and then mutate symbols/Locale on a singleton across requests. `NumberFormat` and `DecimalFormat` are mutable; the demo instantiates a new one inside `parse` and `print`. Spring typically keeps Formatters in a shared registry, so a formatter's state must be thread-safe.

### 8.4. Why Not Convert via Double?

Avoid:

~~~java
Number parsed = NumberFormat.getNumberInstance(locale)
        .parse(text);

BigDecimal amount =
        BigDecimal.valueOf(parsed.doubleValue());
~~~

Here the decimal number passes through a binary floating-point representation. Use `DecimalFormat.setParseBigDecimal(true)`, then keep `BigDecimal`. When rounding is needed, specify `RoundingMode` explicitly according to business rules before rounding.

### 8.5. Input type="number" Differs from Localized Text

HTML form `input type="number"` follows standard/browser rules and may not submit localized formatted strings as expected. If you want a Formatter to receive `1.234,50`, `type="text"` as in the demo is the explicit choice. If using number inputs, design the client to send canonical decimals and configure the server parser accordingly.

### 8.6. Do Not Guess Currency from Locale

Locale determines display formatting, not the currency of an order. For multi-currency, model it in the domain:

~~~java
public record Price(
        BigDecimal amount,
        Currency currency) {
}
~~~

This is a supplementary snippet outside the Maven demo and requires importing `java.util.Currency`. Each currency has its own scale/rounding policy and can be displayed across multiple Locales.

## 9. Converter/Formatter Does Not Replace Validation and Authorization

Both only produce **typed values**. A converter accepting `ABC-0042` does not prove the user is authorized to edit that product. Check permissions in the service by resource ID/owner/tenant, and protect input DTOs against mass assignment.

Separation of responsibilities:

~~~text
HTTP text → Converter/Formatter
             |
             +-- Cannot parse → typeMismatch
             |
             v
         Typed input
             |
             +-- Bean Validation → DecimalMin/Digits/NotNull...
             |
             v
         Authentication + authorization
             |
             v
         Business state/transaction/persistence
~~~

Never let a Converter call the DB or open transactions with side effects. A Converter can be invoked repeatedly during binding/rendering/testing; it should be deterministic and side-effect-free.

### 9.1. Limiting Input Length

Extremely long strings can consume CPU/memory. Before parsing, you can add:

~~~java
if (input.length() > 64) {
    throw new ParseException(
            "Amount text is too long", 0);
}
~~~

This is a hardening snippet, not part of the demo formatter file. In production, choose a limit suited to your transactions and add HTTP body/parameter limits; `@Digits` runs only after parsing and does not prevent the cost of parsing overly long strings.

### 9.2. Do Not Expose rejectedValue

`FieldError.getRejectedValue()` can contain passwords, tokens, or PII. API error responses should expose only safe error codes, paths, and messages; never serialize raw exceptions or rejected values directly. For Thymeleaf forms, verify output escaping and preserve `BindingResult` to display errors properly without introducing new XSS vectors.

## 10. When to Use AnnotationFormatterFactory or @NumberFormat?

If a field is just `BigDecimal` or `LocalDate` and does not need a dedicated domain value type, Spring provides built-ins:

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate deliveryDate;
~~~

These are snippets requiring imports. `@NumberFormat` and `@DateTimeFormat` are usually enough for common fields; do not write a custom formatter merely to reimplement built-in behavior.

Related SPIs:

- `ConverterFactory<S,R>`: a family of target types (e.g., many enums).
- `GenericConverter` and `ConditionalGenericConverter`: when `TypeDescriptor`/annotation metadata or multiple source/target pairs are needed.
- `AnnotationFormatterFactory<A>`: applies a formatter only to fields carrying a specific annotation.
- `FormatterRegistrar`: registers a reusable group of formatters/converters.

For **one** domain code and **one** domain money type in the demo, `Converter<String,ProductCode>` + `Formatter<MoneyAmount>` is simple and clear.

## 11. Common Errors and Diagnostics

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `@PathVariable ProductCode` does not convert | Converter not registered, code violates pattern | Check MVC config and MockMvc |
| Path `abc-42` returns HTTP 400 | Expected: code does not match regex | Return a safe error code |
| Form renders `ProductCode[value=...]` | Missing `ProductCode→String` direction | Register reverse converter |
| Form renders `MoneyAmount[value=...]` | Formatter not used during rendering | Check `th:field`/registry |
| Query `1.234,50` errors out | Locale is `en-US` or another | Check `Accept-Language` |
| Formatter prints fine, parser fails | Only tested `print` | Unit test `parse`/round-trip |
| Parser accepts `1,234.50abc` | Used only `NumberFormat.parse(String)` | Use `ParsePosition` to check full consumption |
| Parser yields wrong decimals/negatives | Went through `double` | Use `parseBigDecimal` and `BigDecimal` |
| Negative form amount reports no error | Missing `@Valid` cascade | Add `@Valid` on `MoneyAmount` |
| Invalid form still returns HTTP 200 | Controller re-renders the view | Assert `BindingResult` and view |
| JSON body ignores MVC formatter | Jackson is a different pipeline | Dedicated DTO/JSON mapping |
| Boot config properties ignore converter | MVC conversion service is separate | `WebMvcConfigurer.addFormatters` |
| `@EnableWebMvc` breaks Boot customizations | Disables auto-configuration | Implement `WebMvcConfigurer` only |
| Money shows strange separators | Different JDK locale data | Check `DecimalFormatSymbols` |
| Shared `DecimalFormat` races | Formatter has mutable singleton state | Create `NumberFormat` per call |
| Code turns into odd characters in `tr-TR` | Locale-dependent `toUpperCase()` | Use `Locale.ROOT` |
| Form loses entered values after error | Created new model instead of `BindingResult` | Keep original `BindingResult` object |
| Conversion succeeds, user lacks permission | Converter does not perform authorization | Service checks resource rights |
| VND/USD amounts confused | Used Locale as currency | Separate domain `Currency` |
| Oversized input causes slowdown | No length limit before parsing | Limit string/request size |
| HTTP 400 leaks sensitive values | Returned `rejectedValue`/exception | Use safe error codes and messages |

### 11.1. Testing ConversionService Standalone

You can instantiate a `DefaultFormattingConversionService` outside HTTP to verify registration:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new ProductCodeConverter());
service.addConverter(
        new ProductCodeToStringConverter());
service.addFormatter(new MoneyAmountFormatter());

ProductCode code = service.convert(
        "abc-0042", ProductCode.class);

assertEquals("ABC-0042", code.value());
~~~

This is a test snippet with appropriate Spring/JUnit imports. To test Locale, set `LocaleContextHolder` inside a `try/finally` block:

~~~java
Locale previous = LocaleContextHolder.getLocale();

try {
    LocaleContextHolder.setLocale(
            Locale.forLanguageTag("vi-VN"));

    MoneyAmount amount = service.convert(
            "1.234,50", MoneyAmount.class);

    assertEquals(new BigDecimal("1234.50"),
            amount.value());
} finally {
    LocaleContextHolder.setLocale(previous);
}
~~~

This test only verifies the registry you built; **MockMvc** is still needed to ensure request Locale and MVC argument binding actually use the converter/formatter.

## 12. Internationalizing Form Errors

Spring `BindingResult` can generate message codes such as:

~~~text
typeMismatch.offerForm.productCode
typeMismatch.offerForm.amount
typeMismatch.amount
typeMismatch
~~~

Specific codes depend on `MessageCodesResolver`, object name, and type. If you want Vietnamese field errors, you can configure `messages.properties` and `messages_vi.properties` with keys such as:

~~~properties
typeMismatch.offerForm.productCode=Mã sản phẩm không hợp lệ
typeMismatch.offerForm.amount=Số tiền không đúng định dạng
DecimalMin.offerForm.amount.value=Số tiền phải lớn hơn hoặc bằng 0,01
Digits.offerForm.amount.value=Số tiền vượt giới hạn cho phép
~~~

This is an **optional extension configuration**, not a required file in the demo. For Boot to pick up `MessageSource` by default, a valid base bundle such as `messages.properties` is required. Before standardizing keys, inspect `BindingResult.getFieldError(...).getCodes()` in a test; do not guess the `objectName` or nested path.

## 13. Practice Exercises

**Exercise 1.** Change the business code format to `PRD-123456` and update the record and tests. Why shouldn't the regex live in every controller?

**Exercise 2.** Test `tr-TR` with code `mix-0042`. Compare `toUpperCase()` and `toUpperCase(Locale.ROOT)`.

**Exercise 3.** Add `Locale.FRANCE` to the formatter; check that the grouping separator may be a non-breaking space, and do not blindly replace it with an ASCII space.

**Exercise 4.** Try parsing `1,234.567` and `1.234,567` with the corresponding locales. Propose a strict grouping grammar.

**Exercise 5.** Change the scale policy from `RoundingMode.UNNECESSARY` to `HALF_EVEN`, and write tests for midpoint values. Explain who owns the decision on rounding policy.

**Exercise 6.** Build `Price(BigDecimal,Currency)`, distinguishing presentation locale from transaction currency.

**Exercise 7.** Add a JSON endpoint accepting code/amount. Write a Jackson deserializer or dedicated canonical DTO; prove the MVC formatter does not run for `@RequestBody`.

**Exercise 8.** Submit malformed, negative, and oversized amount strings and distinguish `typeMismatch` from `DecimalMin`/`Digits` by exact field path.

**Exercise 9.** Add a language selector; ensure values shown when opening the form and submitted back are parsed under the same locale or a canonical protocol.

**Exercise 10.** Use `@NumberFormat` on `BigDecimal` and compare it with a custom `Formatter<MoneyAmount>`. Which fits better in which scenarios?

**Exercise 11.** Add Spring Security tests for CSRF and owner/tenant authorization after the code has been converted validly.

**Exercise 12.** Add a 64-character limit before parsing the amount, test extremely long input, and ensure rejected values are never logged.

## Conclusion

~~~text
HTTP path/query/form
      |
      v
Spring MVC FormattingConversionService
      |
      +-- String → ProductCode  (Locale.ROOT)
      |
      +-- String ↔ MoneyAmount (request Locale)
      |
      v
Typed domain values
      |
      v
Bean Validation → authorization → service
      |
      v
Canonical JSON response / localized form

@RequestBody JSON → Jackson (does not go through MVC formatter by default)
~~~

A **Converter** produces domain types with fixed machine-readable rules; a **Formatter** parses and prints data according to `Locale`. With exact `BigDecimal`, `WebMvcConfigurer.addFormatters`, `BindingResult`, and bidirectional tests, you can build forms and APIs with reliable business codes and unambiguous decimal/grouping separators.

## References

- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.2 — Parser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework 6.2 — Converter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — WebMvcConfigurer.addFormatters](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot 3.5 — MVC Conversion Service](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Thymeleaf 3.1 — Spring Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)
- [Java 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [Java 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [Java 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
