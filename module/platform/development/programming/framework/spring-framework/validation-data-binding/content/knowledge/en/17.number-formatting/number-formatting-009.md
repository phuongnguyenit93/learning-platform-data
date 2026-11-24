# Distinguishing Spring Field Formatting from JSON Serialization

> **Context:** Spring MVC, Spring Framework's data binding/field formatting mechanism, and JSON (de)serialization via Jackson. Examples use Java 17 and Spring Boot 3.3.x to run Spring MVC. Focus is on **number formatting**; date formatting is mentioned alongside to clarify the boundary between the two mechanisms.

## 1. Two mechanisms solving two different problems

Spring **field formatting** converts between *strings users enter or view* and *typed Java values* during form binding or rendering. For example, a user in the `en-US` locale enters `1,234.50`; Spring can parse that string into `BigDecimal("1234.50")`. When re-rendering the form, the formatter can print the number as `1,234.50`.

**JSON serialization** turns a Java object into an HTTP body containing JSON; **JSON deserialization** does the reverse. When an endpoint uses `@RequestBody` or returns an object via `@ResponseBody`/`@RestController`, Spring MVC typically selects a JSON `HttpMessageConverter` backed by Jackson. JSON numbers are tokens following JSON syntax, e.g., `1234.50`, **without locale-dependent thousands separators**.

| Question | Spring Field Formatting | JSON via Jackson |
| --- | --- | --- |
| Typical input data | Query parameters, path variables, form fields, `@ModelAttribute` | `application/json` body with `@RequestBody` |
| Key components | `WebDataBinder`, `ConversionService`, `Converter`, `Formatter` | `HttpMessageConverter`, `ObjectMapper`, serializer/deserializer |
| Representative annotations | `@NumberFormat`, `@DateTimeFormat` | `@JsonFormat`, `@JsonSerialize`, `@JsonDeserialize`, `@JsonProperty` |
| Locale awareness | Can use `Locale` to parse/print display strings | JSON numbers have locale-independent syntax; configure Jackson separately if needed |
| Target effect | String ↔ Java field/argument values during binding or form rendering | How objects ↔ JSON bodies are read/written |
| Automatically controls the other mechanism? | No | No |

Note: `@ModelAttribute` can receive query parameters and form data; `@RequestBody` reads the body through a message converter. Even though both paths may construct a Java object, **they do not share annotation-based formatting rules by default**.

## 2. Path of a numeric value

### 2.1. Query/form → Spring data binding

```text
GET /amount/form?amount=1%2C234.50
     │  string "1,234.50", en-US locale
     ▼
Spring MVC argument resolution / @ModelAttribute
     ▼
WebDataBinder → FormattingConversionService
     ▼
@NumberFormat(pattern = "#,##0.00")
     ▼
BigDecimal(1234.50) in Java object
```

`Formatter<T>` provides `parse(String, Locale)` to read strings and `print(T, Locale)` to generate display strings. `ConversionService` is Spring's unified type conversion API, coordinating `Converter` and `Formatter`. A formatter may be registered globally or selected via field annotations.

Here `@NumberFormat` describes how a number is **parsed/printed during binding/formatting**. It does not turn `BigDecimal` into text, does not automatically round business values for database persistence, and does not force Jackson to emit JSON matching this pattern.

For instance, pattern `#,##0.00` is interpreted under number formatting rules and locale. In `en-US`, commas group thousands and periods separate decimals; in many other locales, those symbols are reversed. Do not deduce the same number from `"1,234"` across every locale.

### 2.2. JSON body → Jackson deserialization

```text
POST /amount/json
Content-Type: application/json

{"amount":1234.50}
     ▼
@RequestBody → JSON HttpMessageConverter → Jackson
     ▼
AmountJson(BigDecimal("1234.50"))
```

On this path, Jackson reads JSON tokens according to its own configuration. If the DTO carries `@NumberFormat`, Jackson **does not implicitly use** Spring's formatter to parse JSON strings.

Response direction:

```text
Java object with amount = BigDecimal("1234.50")
     ▼
@RestController / @ResponseBody
     ▼
JSON HttpMessageConverter → Jackson
     ▼
{"amount":1234.50}
```

A valid JSON number is `1234.50`; `1,234.50` is not a valid JSON number token. The string `"1,234.50"` is a valid *JSON string*, not a JSON number; default Jackson should not be assumed to understand thousands-grouping commas when binding that string to `BigDecimal`.

## 3. Runnable example: same `amount` field, two processing paths

Create a Java 17 Maven project with the structure:

```text
format-vs-json/
├── pom.xml
└── src/main/java/demo/FormatBoundaryApplication.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>format-vs-json</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

**`src/main/java/demo/FormatBoundaryApplication.java`**:

```java
package demo;

import java.math.BigDecimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormatBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatBoundaryApplication.class, args);
    }

    @RestController
    public static class AmountController {

        // Spring binds query string into the @ModelAttribute property.
        @GetMapping(value = "/amount/form",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public String fromForm(@ModelAttribute AmountForm form) {
            BigDecimal amount = form.getAmount();
            return amount == null
                    ? "amount=<missing>"
                    : "amount=" + amount.toPlainString();
        }

        // Jackson reads the JSON body and writes the JSON response.
        @PostMapping(value = "/amount/json",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.APPLICATION_JSON_VALUE)
        public AmountJson fromJson(@RequestBody AmountJson payload) {
            return payload;
        }
    }

    public static class AmountForm {
        @NumberFormat(pattern = "#,##0.00")
        private BigDecimal amount;

        public BigDecimal getAmount() {
            return amount;
        }

        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    public record AmountJson(BigDecimal amount) { }
}
```

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn spring-boot:run
```

**Test 1 — binding a form value** (using a second terminal):

```bash
curl -sS -G 'http://localhost:8080/amount/form' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'amount=1,234.50'
```

Response body:

```text
amount=1234.50
```

Here `@NumberFormat` lets Spring parse the display value `1,234.50` into `BigDecimal`. `toPlainString()` is only used to produce an easily observable output in the example; this is **not JSON serialization**.

**Test 2 — JSON body**:

```bash
curl -sS -X POST 'http://localhost:8080/amount/json' \
  -H 'Content-Type: application/json' \
  -d '{"amount":1234.50}'
```

Expected response body (with default Jackson in the sample project):

```json
{"amount":1234.50}
```

Jackson handles `BigDecimal` as a JSON number. `AmountJson` has no `@NumberFormat`, and adding that annotation to a JSON DTO still would not make Jackson apply Spring's format pattern.

**Test 3 — sending a "thousands-grouped number" in JSON**:

```json
{"amount":1,234.50}
```

This is **invalid JSON**: commas separate elements/property pairs and have no thousands-grouping role in numeric literals. Sending `{"amount":"1,234.50"}` makes the JSON document syntactically valid, yet the `amount` value is a string; with default Jackson, it does not satisfy standard numeric-string syntax to deserialize into `BigDecimal`.

## 4. Two DTOs with the same Java type can still have different representations

These are illustrative snippets placed inside their respective DTOs (not a standalone program):

```java
// DTO used for query/form binding:
public class SearchForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    // Constructor/getters/setters matching the chosen binding style.
}

// DTO used for JSON body:
public record SearchJson(
    BigDecimal amount,
    @JsonFormat(pattern = "dd/MM/yyyy") LocalDate fromDate
) { }
```

Corresponding imports: `org.springframework.format.annotation.NumberFormat`, `org.springframework.format.annotation.DateTimeFormat`, `com.fasterxml.jackson.annotation.JsonFormat`, `java.math.BigDecimal`, and `java.time.LocalDate`.

- `@DateTimeFormat` helps Spring parse/print date fields along the binding path. It does not automatically force JSON to use the same pattern.
- `@JsonFormat(pattern = "dd/MM/yyyy")` instructs **Jackson** to format a date type that supports that pattern. For `LocalDate`, Jackson's Java Time module is required; `spring-boot-starter-web` in this Boot 3 example already provides/configures that module.
- `@JsonFormat` is not a "JSON mirror" of `@NumberFormat`: the meaning of `pattern` depends on the serializer/deserializer and data type. Do not assume `@JsonFormat(pattern = "#,##0.00")` turns `BigDecimal` into a JSON number with grouping separators.
- `@JsonProperty("amount")` renames the JSON property; it does not localize decimal separators. Conversely, `@NumberFormat` does not rename JSON properties.

If an API **genuinely must return a formatted display number** (such as `"1,234.50"`), design a clearly named `String` field like `displayAmount` in the response DTO, or use a custom Jackson serializer emitting a controlled **JSON string**. Keep the `amount` field as a JSON number for calculations, sorting, and system-to-system integration.

Example response with two separate fields:

```json
{
  "amount": 1234.50,
  "displayAmount": "1,234.50"
}
```

`displayAmount` is produced by the presentation layer matching the viewer's locale; clients in other locales will not necessarily use that exact string. Avoid using display strings as business data or canonical interchange formats.

## 5. Distinguishing binding errors from JSON parsing errors

| Scenario | Where the Problem Arises | Resolution |
| --- | --- | --- |
| Query/form receives number string incompatible with locale/pattern | Spring binding/`ConversionService`; may become a field error in `BindingResult` | Show input error, check locale/pattern, place `BindingResult` after `@ModelAttribute` to handle in controller |
| Syntactically invalid JSON body, e.g., `{"amount":1,234.50}` | JSON parser/message converter; typically leads to `HttpMessageNotReadableException` and HTTP 400 | Fix JSON to follow standard syntax |
| Valid JSON body yet fails to deserialize into DTO | Jackson mapping/deserialization | Check field types and JSON contract; use a custom deserializer when explicitly required |
| JSON output uses a pattern different from forms | Two independently configured mechanisms | Check `@NumberFormat`/`ConversionService` on forms and Jackson configuration/annotations on JSON |

In Spring MVC, binding/validation errors may map to HTTP 400 depending on configuration and method signatures; **do not assume every error produces the exact same exception or error body**. `@Valid`/Bean Validation checks data constraints *after or alongside* type conversion, and does not replace formatters/deserializers.

## 6. Design principles and common mistakes

1. **Pick the right data path:** For query/form/`@ModelAttribute`, think `Converter`/`Formatter`/`@NumberFormat`; for JSON requests/responses, think Jackson and JSON message converters.
2. **Separate machine-readable data from presentation:** JSON number `1234.50` is a stable contract; thousands separators, localized decimal signs, and currency symbols belong to the presentation layer. Do not pass `"1.234,50"` as a general canonical numeric value unless the API explicitly defines that string type.
3. **Control locale deliberately:** Test `en-US` and user-facing locales; verify locale resolvers, whitespace/grouping characters, and real inputs. Do not treat the JVM's `Locale.getDefault()` as always matching the request locale.
4. **Preserve precision:** Use `BigDecimal` for money or decimals requiring decimal accuracy; `double` can introduce binary rounding errors. Round only per explicit business rules; display formatting must never silently alter the underlying amount.
5. **Do not mix up annotations:** `@NumberFormat` does not format JSON; `@JsonFormat` does not drive Spring form binding; `@JsonProperty` does not change number parsing. Annotations do not sync automatically just by sitting on the same field.
6. **Do not confuse JSON syntax:** `{"amount":1,234.50}` is a syntax error; `{"amount":"1,234.50"}` is a string, not a number. JSON numbers always use a period for the decimal point and have no thousands grouping separators.
7. **Test both directions:** For forms, test parsing and printing by locale; for JSON, test request deserialization and response serialization, including type/syntax errors and `BigDecimal` precision. Assert numeric values and JSON types, not just a printed string snippet.

## 7. Tool-selection checklist

- Need to parse `1,234.50` in `en-US` from query/form into `BigDecimal`? → `@NumberFormat` or `Formatter<BigDecimal>` via `ConversionService`.
- Need to return `{"amount":1234.50}` from `@RestController`? → JSON DTO with `BigDecimal` and default Jackson as a starting point.
- Need to change JSON date representation? → Look at `@JsonFormat`/Jackson Java Time, independent of `@DateTimeFormat` used in forms.
- Need a display field with grouping separators or currency symbols? → Add a string `displayAmount` field formatted with explicit locale; do not alter the original numeric field's semantics.
- Need to diagnose a parse error? → Determine whether the request goes through `WebDataBinder` or a JSON message converter before changing annotations/configuration.

**Conclusion:** Spring field formatting handles **strings in field input/output contexts**; JSON serialization handles **object representations in message bodies**. One DTO might be used along both paths, yet their conversion mechanisms and annotations maintain separate boundaries.

### Further reading (official documentation)

- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
