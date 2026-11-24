# Mapping Collection or Map Paths to an API Contract in Spring Validation

## 1. The problem: when an error is nested in a list or Map, what path should be returned?

A REST API receiving nested data may contain product lists, addresses, dynamically keyed configurations, or lists of child objects. When Spring MVC and Jakarta Validation validate the data, errors often carry **internal field paths** such as:

```text
lineItems[0].sku
lineItems[1].quantity
preferences[alerts].enabled
preferences[weekly.news].enabled
```

However, the frontend needs to know **where in the JSON request** the error occurred so it can highlight the exact input, scroll to the row in a list, or display a message next to a configuration entry with a specific key.

The problem is:

- Spring's `FieldError#getField()` can use **dot-and-bracket** property path syntax.
- JSON arrays are **zero-indexed**; JSON Maps are **objects with string keys**.
- Map keys can contain dots, slashes, tildes, or special characters.
- A path from a Java object **does not necessarily** match the JSON field name if `@JsonProperty`, naming strategies, aliases, or DTO mappings are used.
- An array index can change when the user inserts, deletes, or reorders rows.
- An error may apply to the entire collection or object, **not** to a single element.

Therefore, instead of returning the raw Spring path string and forcing clients to guess its meaning, you should **define an explicit API contract for error locations**. This lesson uses **JSON Pointer (RFC 6901)** for JSON requests, while also explaining when safe conversion is not possible and an object-level or request-level error should be returned instead.

### Learning objectives

After this lesson, you will be able to:

1. Recognize `List`, array, `Map`, and nested bean paths in `BindingResult` / `FieldError`.
2. Distinguish Java/Spring paths from paths in the JSON document sent over HTTP.
3. Convert **syntactically constrained** cases into JSON Pointer, applying RFC 6901 escaping properly.
4. Return responses with `pointer`, `code`, and `message`, ensuring error codes do not depend on translation text.
5. Separate validation errors from JSON parse/deserialization errors and method validation.
6. Write `MockMvc` tests to verify ordering, indices, Map keys, and cases where a path cannot be derived.
7. Avoid leaking sensitive data in Map keys, prevent mass assignment, and avoid naive parsers turning keys into bogus paths.

**Technical scope:** Spring Framework 6.x, Spring MVC, Java 17+, Spring Boot 3.x, Jakarta Validation. `WebFlux` examples have a different exception pipeline and should not be treated as strictly equivalent.

## 2. How are Spring paths formed?

Example Java DTOs:

```java
public record CheckoutRequest(
        List<CartLine> lineItems,
        Map<String, NotificationPreference> preferences) {
}

public record CartLine(String sku, Integer quantity) {
}

public record NotificationPreference(Boolean enabled) {
}
```

These classes are **model fragments** without constraints yet. Once `@Valid` is added on nested values along with appropriate constraints, Bean Validation can detect:

- First product missing SKU: `lineItems[0].sku`.
- Second product with quantity below the required minimum: `lineItems[1].quantity`.
- `alerts` configuration missing an `enabled` value: `preferences[alerts].enabled`.
- Map key containing a dot `weekly.news`: `preferences[weekly.news].enabled`.

Spring translates Jakarta Validation violations into `FieldError` or `ObjectError` entries in `BindingResult`; building field paths typically goes through `SpringValidatorAdapter`. With `@Valid @RequestBody` on a single object in Spring MVC, constraint failures are normally placed into `MethodArgumentNotValidException`, which exposes `getBindingResult()`.

Example reading field errors in a handler:

```java
List<FieldError> errors =
        ex.getBindingResult().getFieldErrors();

for (FieldError error : errors) {
    String springPath = error.getField();
    String[] lookupCodes = error.getCodes();
    boolean conversionFailure = error.isBindingFailure();
}
```

The snippet above is a **fragment** where `MethodArgumentNotValidException ex` and required imports are already in scope. Note: `getField()` is Spring metadata, and `getCodes()` are message lookup codes; neither is **automatically a stable public API contract**.

### Why are Map keys containing dots especially dangerous when splitting?

Suppose:

```text
preferences[weekly.news].enabled
```

If code naively calls `path.split("\\.")`, it splits the key `weekly.news` into two segments `weekly` and `news`. That result is wrong: the JSON key is a **single** string `"weekly.news"`.

In a Spring path, dots **outside** square brackets usually traverse JavaBean properties, whereas dots **inside** brackets can belong to a Map key. A proper path converter must **parse segment by segment**, not blindly replace characters.

### Table of examples before and after conversion

| Spring source | Data meaning | Expected API pointer |
| --- | --- | --- |
| `name` | Root property | `/name` |
| `lineItems[0].sku` | SKU of the first element | `/lineItems/0/sku` |
| `lineItems[12].quantity` | Quantity of the 13th element | `/lineItems/12/quantity` |
| `lineItems` | Error on the entire list | `/lineItems` |
| `preferences[alerts].enabled` | Map key `alerts` | `/preferences/alerts/enabled` |
| `preferences[weekly.news].enabled` | Map key containing a dot | `/preferences/weekly.news/enabled` |
| `preferences[team/a~b].enabled` | Map key containing `/` and `~` | `/preferences/team~1a~0b/enabled` |
| `shipping.address.postcode` | Nested property | `/shipping/address/postcode` |
| Object-level error | No single field path | `""` (pointer to root) |

These examples represent **path-conversion conventions** for DTOs whose property names match JSON names. For complex keys containing quoting characters, closing brackets, escapes, or converted Map key types, do not apply a generic string replacement without verifying the actual format.

## 3. JSON Pointer (RFC 6901): definition and escaping

A JSON Pointer is a string composed of **reference tokens** separated by `/`. The `pointer` field in this lesson's contract uses the **string representation** of RFC 6901, not the URI fragment representation.

Example request:

```json
{
  "lineItems": [
    {"sku": "ABC", "quantity": 2},
    {"sku": "", "quantity": 0}
  ],
  "preferences": {
    "alerts": {"enabled": true},
    "weekly.news": {"enabled": null}
  }
}
```

The pointers:

- `/lineItems/0/sku` → `"ABC"`.
- `/lineItems/1/quantity` → `0`.
- `/preferences/alerts/enabled` → `true`.
- `/preferences/weekly.news/enabled` → `null`.

**Mandatory escaping rules under RFC 6901**: in each token,

- The character `~` is replaced with `~0`.
- The character `/` is replaced with `~1`.

For example, the token `team/a~b` becomes `team~1a~0b`. A token with a dot such as `weekly.news` does **not** need dot escaping in JSON Pointer.

The encoding order is:

```java
static String escapePointerToken(String token) {
    return token.replace("~", "~0").replace("/", "~1");
}
```

When **decoding** a token, the reverse order required by the RFC is replacing `~1` with `/` **first**, then replacing `~0` with `~`. Doing it in the reverse order can corrupt a token containing `~01`.

### Empty pointer vs. single-slash pointer are not the same

- The string **`""`** represents the **entire JSON document** (root).
- The string **`"/"`** represents a member with an **empty-string** key on the root object.
- The string **`"/lineItems"`** points to the collection, not an individual element.
- The string **`"/lineItems/0"`** points to the first element object.

Document this rule clearly in the API schema. Avoid using `"/"` to mean "unknown error location"; it means something different from `""` in JSON Pointer.

### JSON string pointer vs. URI fragment

- String pointer: `/preferences/team~1a~0b/enabled`.
- URI fragment representation: may have a leading `#` and also requires percent-encoding under URI fragment rules.

Do not prepend `#` to the `pointer` field if your contract defines the **string representation**. If you place a pointer inside a URL path or fragment, apply proper URI encoding as well, not only `~` and `/` escaping.

### Syntactically valid pointers that may not resolve on the failing body

Suppose the submitted JSON **omits** the `enabled` field entirely:

```json
{"preferences":{"alerts":{}}}
```

Jakarta `@NotNull` on `enabled` can still produce the field path `preferences[alerts].enabled`, because the deserialized model has `null` for that property. However, the pointer `/preferences/alerts/enabled` **does not resolve to an existing member in the raw JSON**, because the request never sent that key.

Therefore, if your API uses pointers to **indicate expected schema locations**, document that a pointer can represent a **logical address to fix** rather than guaranteeing the reference exists in the raw request. If consumers require strict JSON Pointer evaluation, consider returning the error at the parent pointer `/preferences/alerts` with a separate `missingField="enabled"` attribute. This is an **API contract decision**, not something a string parser alone can resolve.

## 4. Three ways to return error locations in an API

### 4.1. Approach A: return the raw Spring property path

Example:

```json
{
  "field": "lineItems[1].quantity",
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

Pros: minimal transformation, close to `BindingResult`. Cons: clients must understand Spring property path syntax; couples clients to Java refactorings and struggles with special Map keys.

Suitable when frontend and backend share internal conventions with clear tests and do not treat the path as a long-term independent contract.

### 4.2. Approach B: return a JSON Pointer per the request contract

Example:

```json
{
  "pointer": "/lineItems/1/quantity",
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

Pros: clear standard location format for JSON; the frontend can bind pointers to the form tree without knowing Java syntax. Risk: the server must map **exact JSON names** and Map keys, handling escaping and container indices.

This is the approach demonstrated with runnable code below.

### 4.3. Approach C: return a structured list of path segments

Example:

```json
{
  "segments": ["lineItems", 1, "quantity"],
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

A string Map key `"0"` differs from numeric array index `0` when using JSON types, so typed segments express semantics even more cleanly. However, this is a **custom schema**, not RFC 6901 JSON Pointer itself; client and server must agree on formatting, numeric/integer values, parent handling, and root errors.

If the primary goal is frontend form binding rather than generic JSON tree traversal, an API may choose path segments instead of pointers. However, **do not emit all three formats without specifying which one is canonical**; otherwise you have to maintain multiple representations that easily drift apart.

### Lesson choice

We choose a **`pointer` field formatted as a JSON Pointer string**, a **stable `code` field**, and a **`message` field** for display. When a path cannot be mapped safely, the example uses pointer `""` (root fallback) rather than publishing a guessed path.

## 5. Stable error codes should not depend on paths

An error at `lineItems[0].sku` and an error at `lineItems[8].sku` can carry the same code `REQUIRED_TEXT`. The index represents the **current position**, not a different error type.

Example:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    },
    {
      "pointer": "/lineItems/8/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    }
  ]
}
```

Never embed indices into error codes, such as `LINE_0_SKU_EMPTY` or `LINE_8_SKU_EMPTY`. When a user inserts a row at the top of the list, indices shift, yet the "text required" error meaning remains unchanged.

**What must stay stable** in the API contract:

- Response field names such as `code`, `errors`, `pointer`.
- Meanings of `code`: for example `REQUIRED_TEXT`, `MIN_VALUE`, `REQUIRED_VALUE`.
- Pointer syntax: JSON Pointer string, escaping rules, and root fallback.
- Behavior when a path cannot be represented.
- HTTP status rules for validation errors and deserialization errors.
- Error sorting rules if clients or tests expect deterministic ordering.

**What may change in a controlled manner:** localized `message` wording, raw validator error emission order, indices reflecting the array state at request time, and internal Java class organization as long as the translation layer preserves the API contract.

## 6. Runnable Java 17 example: Spring Boot MVC, List, and Map

### 6.1. Goal of the example

Create endpoint `POST /baskets` accepting JSON with:

- `lineItems` as `List<LineItem>`, each element having `sku` and `quantity`.
- `preferences` as `Map<String, NotificationPreference>`, each value having `enabled`.
- Constraint violations go through `MethodArgumentNotValidException`.
- The HTTP response contains an error list with properly formatted pointers.
- Unreadable JSON returns a separate code `UNREADABLE_BODY`, **without** a fabricated pointer list.
- Java property names match JSON field names in this demo; scenarios using `@JsonProperty`/naming strategies need a dedicated mapping layer.

Sample test payload:

```json
{
  "lineItems": [
    {"sku": "", "quantity": 0},
    {"sku": "SKU-2", "quantity": 3}
  ],
  "preferences": {
    "alerts": {"enabled": null}
  }
}
```

Expected errors at `/lineItems/0/sku`, `/lineItems/0/quantity`, and `/preferences/alerts/enabled`.

### 6.2. Directory structure

```text
nested-errors-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── NestedErrorsApplication.java
    │   ├── CreateBasketRequest.java
    │   ├── BasketController.java
    │   ├── SpringFieldPath.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── SpringFieldPathTest.java
        └── BasketControllerTest.java
```

### 6.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>nested-errors-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Spring Boot starters align compatible versions of MVC, Jackson, and Hibernate Validator. `spring-boot-starter-validation` is required so `@Valid` evaluates the Jakarta constraints in this example.

### 6.4. NestedErrorsApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedErrorsApplication.class, args);
    }
}
```

### 6.5. CreateBasketRequest.java

```java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateBasketRequest(
        @NotEmpty List<@Valid LineItem> lineItems,
        @NotNull Map<String, @Valid NotificationPreference> preferences
) {

    public record LineItem(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity
    ) {
    }

    public record NotificationPreference(
            @NotNull Boolean enabled
    ) {
    }
}
```

**Why place `@Valid` on the type arguments?**

- `List<@Valid LineItem>` requests cascading validation into **each element** of the list.
- `Map<String, @Valid NotificationPreference>` requests cascading validation into **each value** of the Map.
- `@NotEmpty` on the list requires the collection to have at least one element (and be non-null).
- `@NotNull` on the Map requires the map to be non-null, **but does not forbid an empty map**.
- `@NotNull` on `enabled` detects a null value or missing `enabled` key inside the value object.
- `@Min(1)` applies to `Integer quantity` after Jackson parses the number; `"abc"` failing to parse as `Integer` typically triggers a deserialization error before validation.

You do not need a separate `ConstraintValidator` per element. Jakarta Validation supports container-element validation and cascaded validation when a compatible provider is present.

**Note:** the placement of `@Valid` and `@NotNull` matters. `List<@Valid LineItem>` does not by itself forbid `null` elements; if you want to forbid `null` elements, add `@NotNull` on the element type as well. Similarly, `Map<String, @Valid NotificationPreference>` does not forbid `null` map values without a corresponding constraint on the value type.

### 6.6. SpringFieldPath.java — parser with explicit bounds

The code below converts the paths used in this demo:

- Property names: ASCII letters, digits after the first character, and underscores.
- Index/key segments enclosed in square brackets, such as `[0]`, `[alerts]`, `[weekly.news]`, or `[team/a~b]`.
- Does not handle arbitrary property path syntax with quoting, nested brackets, complex escapes, or keys containing `]`.
- Rejects empty, overly long, or malformed paths; returns `Optional.empty()` instead of producing a wrong pointer.
- Escapes each token according to RFC 6901 rules for `~` and `/`.

**This is an illustrative adapter with a constrained grammar, not a universal parser for every Spring property path.** In systems supporting arbitrary Map keys, start from structured path metadata (such as Jakarta Validation `Path.Node`s) or use a proven library/parser tested against Spring escaping, Jackson naming strategies, and real keys. Do not rely on this simple heuristic as a universal guarantee.

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public final class SpringFieldPath {

    private SpringFieldPath() {
    }

    public static Optional<String> toJsonPointer(String field) {
        if (field == null || field.isEmpty()
                || field.length() > 512) {
            return Optional.empty();
        }

        List<String> tokens = new ArrayList<>();
        int i = 0;

        while (i < field.length()) {
            char current = field.charAt(i);
            if (current == '.' || current == ']') {
                return Optional.empty();
            }

            if (current == '[') {
                // Do not allow index/key at the root for the demo DTO.
                if (tokens.isEmpty()) {
                    return Optional.empty();
                }

                int end = field.indexOf(']', i + 1);
                if (end < 0) {
                    return Optional.empty();
                }

                String key = field.substring(i + 1, end);
                // Only support keys matching the illustrative grammar.
                if (!key.matches("[A-Za-z0-9._~/:-]+")) {
                    return Optional.empty();
                }

                tokens.add(key);
                i = end + 1;
            } else {
                int start = i;

                while (i < field.length()
                        && field.charAt(i) != '.'
                        && field.charAt(i) != '['
                        && field.charAt(i) != ']') {
                    i++;
                }

                String name = field.substring(start, i);
                if (!name.matches("[A-Za-z_][A-Za-z0-9_]*")) {
                    return Optional.empty();
                }

                tokens.add(name);
            }

            if (i == field.length()) {
                break;
            }

            if (field.charAt(i) == '.') {
                i++;
                // Disallow trailing dot or dot immediately before '['.
                if (i == field.length()
                        || field.charAt(i) == '.'
                        || field.charAt(i) == '[') {
                    return Optional.empty();
                }
            } else if (field.charAt(i) != '[') {
                return Optional.empty();
            }
        }

        if (tokens.isEmpty()) {
            return Optional.empty();
        }

        return Optional.of(tokens.stream()
                .map(SpringFieldPath::escapeToken)
                .collect(Collectors.joining("/", "/", "")));
    }

    private static String escapeToken(String token) {
        return token.replace("~", "~0").replace("/", "~1");
    }
}
```

This is a **standalone Java 17 class in the project**. Notable design decisions:

1. Never split on dots while inside a bracket segment.
2. Verify that brackets close with `]` and key characters belong to the supported character set.
3. Never turn an unrecognized Spring path into an arbitrary JSON address.
4. Escape **per token**, not across the entire joined pointer string. Escaping `/` after joining would turn the path separators into `~1` and corrupt the result.
5. `String#replace("~","~0")` runs before `replace("/","~1")` so it does not corrupt escaped slashes.
6. The parser caps field paths at 512 UTF-16 code units; production systems should also bound token count, nesting depth, and individual key lengths according to risk.

### 6.7. BasketController.java

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BasketController {

    @PostMapping("/baskets")
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateBasketRequest request) {

        // Runs only when JSON is readable and validation succeeds.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "created",
                        "lines", request.lineItems().size()
                ));
    }
}
```

The controller intentionally has **no direct constraints** such as `@NotNull` on the method parameter and does not declare `BindingResult` immediately after the DTO. As a result, nested DTO errors in this typical setup are routed by Spring MVC into `MethodArgumentNotValidException`, giving the advice below access to the full request object's `BindingResult`.

Spring MVC 6.1+ provides built-in method validation when constraints are placed directly on method parameters or return values. For signatures like `@Min(1) @RequestParam int page`, you may need to handle `HandlerMethodValidationException`; do not conflate it with single-DTO errors in this example.

### 6.8. ApiErrorAdvice.java

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record FieldIssue(
            String pointer,
            String code,
            String message
    ) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = new ArrayList<>();

        for (FieldError error :
                ex.getBindingResult().getFieldErrors()) {

            String pointer = SpringFieldPath
                    .toJsonPointer(error.getField())
                    .orElse(""); // Root fallback if path is unsupported.

            String code = stableCode(error);
            issues.add(new FieldIssue(
                    pointer, code, safeMessage(code)
            ));
        }

        for (ObjectError error :
                ex.getBindingResult().getGlobalErrors()) {

            // Object-level error: do not arbitrarily assign a specific field.
            issues.add(new FieldIssue(
                    "",
                    "INVALID_OBJECT",
                    "Request object violates a rule"
            ));
        }

        issues.sort(Comparator
                .comparing(FieldIssue::pointer)
                .thenComparing(FieldIssue::code)
                .thenComparing(FieldIssue::message));

        Map<String, Object> body = Map.of(
                "code", "VALIDATION_FAILED",
                "errors", issues
        );

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "code", "UNREADABLE_BODY",
                "message", "JSON body cannot be read"
        );

        return new ResponseEntity<>(body, headers, status);
    }

    private static String stableCode(FieldError error) {
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }

        String[] codes = error.getCodes();
        List<String> candidates = codes == null
                ? List.of()
                : Arrays.asList(codes);

        if (candidates.contains("NotBlank")) {
            return "REQUIRED_TEXT";
        }
        if (candidates.contains("NotNull")) {
            return "REQUIRED_VALUE";
        }
        if (candidates.contains("NotEmpty")) {
            return "REQUIRED_COLLECTION";
        }
        if (candidates.contains("Min")) {
            return "MIN_VALUE";
        }
        return "INVALID_FIELD";
    }

    private static String safeMessage(String code) {
        return switch (code) {
            case "REQUIRED_TEXT" -> "A text value is required";
            case "REQUIRED_VALUE" -> "A value is required";
            case "REQUIRED_COLLECTION" ->
                    "At least one element is required";
            case "MIN_VALUE" -> "Value must meet the minimum";
            case "INVALID_TYPE" -> "Value has an invalid type";
            default -> "Field value is invalid";
        };
    }
}
```

**Key points in the error handler:**

- `handleMethodArgumentNotValid(...)` belongs to **Spring MVC's** `ResponseEntityExceptionHandler`, not WebFlux.
- The handler returns only three public fields per field error: `pointer`, `code`, `message`. It never serializes `FieldError` directly.
- `stableCode(...)` inspects constraint/binding metadata and translates it into API-owned vocabulary. It **does not return raw Spring codes** like `NotBlank.createBasketRequest.lineItems[0].sku` to clients.
- `safeMessage(...)` uses fixed safe messages so the demo stays self-contained; production code can use `MessageSource` and `Locale` for translation, **but never translate `code`**.
- Global errors use `pointer=""` to denote the root per the contract.
- If the parser does not support a path, it falls back to root instead of emitting a guessed wrong pointer. Production systems can add `locationKnown=false` to distinguish "genuinely a root error" from "insufficient mapping info"; the minimal example omits that field.
- The list is sorted by `pointer` then `code` so tests do not depend on Jakarta Validation's iteration order.
- When JSON has syntax errors or cannot be deserialized, Spring MVC typically throws `HttpMessageNotReadableException` before building a DTO. A dedicated handler returns `UNREADABLE_BODY` without guessing field pointers from unparsed JSON text.
- `HttpStatusCode status` and `HttpHeaders headers` are passed by Spring; the code preserves the default status (typically 400 in both branches).

**Security boundary:** default messages are safe, application-defined strings; the code does not expose `FieldError#getRejectedValue()`, `Throwable#getMessage()`, or disallowed Map key values. However, `pointer` still contains **Map keys**, so production systems must consider whether keys could be emails, tokens, account IDs, or private data.

### 6.9. SpringFieldPathTest.java — unit tests for the path parser

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringFieldPathTest {

    private void check(String input, String expected) {
        assertEquals(expected,
                SpringFieldPath.toJsonPointer(input).orElseThrow());
    }

    @Test
    void nestedArrayIndex() {
        check("lineItems[0].sku", "/lineItems/0/sku");
        check("lineItems[12].quantity",
                "/lineItems/12/quantity");
        check("lineItems", "/lineItems");
    }

    @Test
    void mapKeyContainingDotIsOneToken() {
        check("preferences[weekly.news].enabled",
                "/preferences/weekly.news/enabled");
    }

    @Test
    void slashAndTildeAreEscapedByRfc6901() {
        check("preferences[team/a~b].enabled",
                "/preferences/team~1a~0b/enabled");
    }

    @Test
    void deepBeanProperty() {
        check("shipping.address.postcode",
                "/shipping/address/postcode");
    }

    @Test
    void invalidOrUnsupportedPathsAreNotGuessed() {
        assertTrue(SpringFieldPath.toJsonPointer("").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "preferences[complex]key].enabled").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "lineItems..sku").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "lineItems[0].").isEmpty());
    }
}
```

These tests **verify only the API adapter's parser**. They do not verify what paths Spring/Hibernate Validator actually emit at runtime. That is why MVC integration tests are also required.

### 6.10. BasketControllerTest.java — integration tests via MockMvc

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasketControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void nestedListAndMapErrorsExposePointers() throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"","quantity":0}
                              ],
                              "preferences":{
                                "alerts":{"enabled":null}
                              }
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors.length()").value(3))
                .andExpect(jsonPath("$.errors[*].pointer",
                        hasItems(
                            "/lineItems/0/sku",
                            "/lineItems/0/quantity",
                            "/preferences/alerts/enabled"
                        )))
                .andExpect(jsonPath("$.errors[*].code",
                        hasItems(
                            "REQUIRED_TEXT",
                            "MIN_VALUE",
                            "REQUIRED_VALUE"
                        )));
    }

    @Test
    void errorOnSecondArrayElementUsesIndexOne()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"A-1","quantity":1},
                                {"sku":"","quantity":2}
                              ],
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/lineItems/1/sku"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("REQUIRED_TEXT"));
    }

    @Test
    void mapKeyContainingDotRemainsOneToken()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"OK","quantity":1}
                              ],
                              "preferences":{
                                "weekly.news":{"enabled":null}
                              }
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/preferences/weekly.news/enabled"));
    }

    @Test
    void emptyCollectionErrorTargetsCollection()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[],
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/lineItems"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("REQUIRED_COLLECTION"));
    }

    @Test
    void malformedJsonUsesDifferentErrorCode()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"lineItems\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void incompatibleJsonShapeIsNotBeanValidation()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":"not-an-array",
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void successfulRequestReachesController()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"A-1","quantity":3}
                              ],
                              "preferences":{
                                "alerts":{"enabled":true}
                              }
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.lines").value(1));
    }
}
```

**Goals of the 7 integration tests**:

- Real Spring binds JSON into the record DTO, and Jakarta Validation cascades into both `List` and `Map`.
- Nested errors are translated into JSON Pointers at the exact locations.
- The second array element uses index `1`, not `2`.
- A Map key containing a dot is not mistakenly split into two properties.
- `@NotEmpty` at the collection root uses `/lineItems`.
- Malformed or shape-incompatible JSON receives the distinct `UNREADABLE_BODY` code.
- Valid payloads reach the controller and return HTTP 201.

**Verification note:** assertions in these tests rely on the Spring/Jakarta Validation property-path conventions in this demo setup. If you upgrade the provider, change the `Map` key type, or configure custom validators, verify the actual field paths emitted. Do not assume this bounded parser supports every possible key format.

### 6.11. Running the project

From the `nested-errors-demo` directory on a machine with JDK 17+ and Maven:

```bash
mvn -q clean test
```

The test suite includes **5 unit tests** for the parser and **7 integration tests** for Web MVC, **12 tests** in total. Assertions are expected to pass with Maven returning exit code 0 under the described setup. We do not report Maven stdout as an observed run because actual execution depends on dependency resolution and environment versions.

Start the server:

```bash
mvn spring-boot:run
```

Send a failing payload:

```bash
curl -i -X POST 'http://localhost:8080/baskets' \
  -H 'Content-Type: application/json' \
  --data '{
    "lineItems":[{"sku":"","quantity":0}],
    "preferences":{"alerts":{"enabled":null}}
  }'
```

A response matching the demo contract (key order within each JSON object is not fixed):

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/quantity",
      "code": "MIN_VALUE",
      "message": "Value must meet the minimum"
    },
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    },
    {
      "pointer": "/preferences/alerts/enabled",
      "code": "REQUIRED_VALUE",
      "message": "A value is required"
    }
  ]
}
```

The response list is sorted by pointer and code, though **JSON object key ordering** is not part of the contract. The codes `MIN_VALUE`, `REQUIRED_TEXT`, and `REQUIRED_VALUE` are **demo-defined codes**, not Spring Framework constants.

## 7. Key considerations when converting Spring property paths to JSON Pointer

### 7.1. Java paths are not necessarily JSON paths

Suppose a DTO:

```java
public record CreateOrderRequest(
        @JsonProperty("items")
        List<@Valid LineItem> lineItems) {
}
```

This is a fragment requiring `com.fasterxml.jackson.annotation.JsonProperty` and an appropriate `LineItem` class. Jackson accepts the JSON property named `items`, yet Spring validation can report the field path `lineItems[0].sku` using the **Java property name**. A purely syntactic dot/bracket conversion would emit `/lineItems/0/sku`, **which does not point to the JSON document**. The public contract needs `/items/0/sku`.

Solutions:

- For simple DTOs, keep JSON property names and JavaBean names aligned.
- If using `@JsonProperty`, `PropertyNamingStrategies.SNAKE_CASE`, `@JsonAlias`, `@JsonUnwrapped`, polymorphism, or custom deserializers, use **schema-aware mapping** from Java path segments to actual JSON names.
- You can use Jackson introspection on the typed DTO in the current context to translate property names; never run global string replacements like `replace("lineItems","items")` on paths where a Map key might match the substring.
- Paths that cannot be translated reliably should return a root-level error or alternative metadata with a safe message.

This is a **contract design concern**, not a limitation of RFC 6901.

### 7.2. Map property names are data, not Java field names

With:

```json
{
  "preferences": {
    "weekly.news": {
      "enabled": null
    }
  }
}
```

The key `weekly.news` is a **string in a JSON object**. The parser must preserve this token intact when constructing the pointer. If a key contains spaces, square brackets, or backslashes, the parser above **intentionally rejects it** because it lacks rules guaranteeing a faithful round-trip. An application allowing arbitrary keys needs a parser and tests to match; do not "fix" it by silently stripping awkward characters.

With `Map<Long, Value>` or `Map<UUID, Value>`, Jackson can also deserialize JSON keys into non-String Java types. When mapping back from `FieldError.getField()` to a pointer, you must understand how the key is formatted and you might not recover the verbatim JSON key. In such cases, retaining metadata from the decoder or schema-aware mapping is more reliable than a string parser.

### 7.3. JSON Pointer array indices depend on the current data type

A pointer `/lineItems/0/sku` contains the token `"0"`. RFC 6901 resolves this token depending on **whether the current value is a JSON array or object**:

- If the current node is an array: token `0` is the **first element**.
- If the current node is an object: token `"0"` can be a **key named "0"**.

Hence, from the pointer string alone you cannot tell whether token `0` is an array index without knowing the document structure. If clients want that distinction directly in the schema, use typed segments instead of a pointer string.

### 7.4. List indices are not durable business identifiers

If a user deletes the first element and resubmits, `lineItems[2]` today may no longer refer to the same product as in the previous request. Never use an index as a permanent ID in databases, audit logs, or job retries.

An API can also echo a client-supplied `itemId` or `clientRowId`, provided that:

- You do not pull this value unconditionally from `FieldError#getRejectedValue()`.
- You do not treat `itemId` as proof of authorization.
- If mapping ID → position, you verify the ID exists in the request/schema and belongs to the caller.
- With duplicate IDs, a single ID cannot uniquely identify a row; you still need the position or a collection-level error.

Typically `pointer` describes **location within the current request**, whereas an ID represents **business identity** — two distinct concepts.

## 8. Error types that lack a specific field pointer

### 8.1. Collection-level constraints

For example, `@NotEmpty` on `lineItems` produces an error on the **whole list**, not `lineItems[0]`. The pointer should be `/lineItems`.

Similarly, `@Size(max=20)` on a list should be reported at the collection level, because the element-count rule is not tied to any single item.

### 8.2. Object-level or cross-field constraints

A class-level constraint may require `startDate` before `endDate` or disallow combining two configuration modes. If the validator emits an `ObjectError`, do not fabricate a field path. The root pointer `""` can be an appropriate contract choice.

If the validator explicitly adds a property node for a specific field, such as `endDate`, the adapter can map it to `/endDate`. Which approach is right depends on the **meaning of the constraint**, not merely the annotation name.

### 8.3. Element-level constraints on a List

Example:

```java
public record Request(
        List<@NotBlank String> tags) {
}
```

This is a fragment. If the second element of `tags` is an empty string, the error can be represented by a path containing the element index, such as `tags[1]`. Do not invent a synthetic property like `value`, because the element itself is the invalid string.

### 8.4. Map key constraints vs. Map value constraints

Example:

```java
public record Request(
        Map<@NotBlank String, @Valid NotificationPreference> preferences) {
}
```

This is a fragment. `@NotBlank` on a **Map key** can produce a container-element key path depending on the provider and how Spring converts `ConstraintViolation.getPropertyPath()` into a field. Semantically, the error is in the **key name**, not an `enabled` property inside the value.

If an API allows dynamic keys and needs to report an "invalid key name", consider an error code like `INVALID_MAP_KEY` with `pointer` pointing to the entry/parent and appropriate metadata. Never append `/key` to a JSON Pointer as if the JSON object had a child field named `key` when it does not.

### 8.5. Unreadable JSON body

With `@RequestBody`:

```text
{"lineItems":,}
```

Spring MVC cannot construct the DTO. `HttpMessageNotReadableException` does not go through the same `BindingResult#getFieldErrors()` branch. You may have Jackson parser location details, but you should not claim a reliable field pointer when the failing document node cannot be accurately identified.

The demo returns `UNREADABLE_BODY` instead of emitting a bogus pointer.

### 8.6. Method validation in Spring MVC 6.1+

A method:

```java
@GetMapping("/baskets")
public List<BasketSummary> list(
        @RequestParam @Min(1) int page) {
    // ...
}
```

This is a fragment; controller imports, `BasketSummary`, and implementation are needed. A direct constraint `@Min(1)` on a parameter can trigger **`HandlerMethodValidationException`**, not the single-DTO `MethodArgumentNotValidException`. Metadata is grouped by `ParameterValidationResult`.

To give query parameter errors a location, define the error source explicitly:

```json
{
  "source": "query",
  "parameter": "page",
  "code": "MIN_VALUE"
}
```

Do not default to `pointer="/page"` claiming it points into a JSON body when the request is a GET with no JSON body. Many APIs use a `source` discriminator with `pointer` **only when `source` is `body`**, while query/header/path parameters use dedicated fields.

## 9. Reading structured metadata when `FieldError` lacks enough information

In Jakarta Bean Validation, `ConstraintViolation#getPropertyPath()` provides a `jakarta.validation.Path` consisting of `Path.Node` elements. These nodes can carry:

- Property name.
- Node kind (property, bean, container element, parameter...).
- `isInIterable()` indicating whether the node is inside an iterable.
- `getIndex()` when the path traverses a `List`/array.
- `getKey()` when a `Map` is involved.

Example fragment (assumes `ConstraintViolation<?> violation` is in scope):

```java
for (jakarta.validation.Path.Node node :
        violation.getPropertyPath()) {

    String property = node.getName();
    boolean iterable = node.isInIterable();
    Integer index = node.getIndex();
    Object key = node.getKey();

    // Choose conversion only after inspecting node kind,
    // JSON name mapping, and container type.
}
```

The strength of a structured path is knowing the **key or index** with richer metadata than a pre-formatted string. Even so, the JSON Pointer adapter must still understand **actual JSON names**, key types, null/missing fields, container elements, and naming strategies.

**Important boundary:** when you only receive a `FieldError` from `BindingResult`, you do not always still have the original `ConstraintViolation` with all its structured nodes. Do not write code that blindly casts or forces `FieldError` into `ConstraintViolation`; they are two separate APIs. If arbitrary Map key conversion requirements are complex, build a dedicated integration with the validation engine or preserve structured path metadata at the point the error is created.

Spring's `SpringValidatorAdapter` typically uses the stringified property path of a Jakarta violation as the Spring `Errors` field name; this is convenient for HTML form binding, but can **lose information needed for an exact reverse-mapping to JSON**.

## 10. Security when exposing paths with dynamic Map keys

### 10.1. Keys themselves can be sensitive data

A Map might use email addresses, tokens, device IDs, account IDs, phone numbers, recovery codes, or internal identifiers as keys. Returning:

```json
{
  "pointer": "/tokens/private-secret-abc/active",
  "code": "REQUIRED_VALUE"
}
```

exposes that key in the error response. Even if the caller sent the request, reflecting such data into logs, analytics, or shared screens introduces risk.

Mitigations:

- Define which fields/keys are permitted to be reflected in error responses.
- For sensitive keys, return the parent pointer and a dedicated code instead of a path embedding the key.
- Cap pointer length, path depth, and maximum errors in responses.
- Never serialize rejected values from `FieldError#getRejectedValue()`.
- Never return raw exceptions, SQL messages, or stack traces.
- Avoid logging full payloads or JSON Pointers when they may contain secrets.

### 10.2. Prevent path injection from unescaped string concatenation

Wrong:

```java
String pointer = "/preferences/" + userKey + "/enabled";
```

If `userKey="team/a"`, the pointer becomes `/preferences/team/a/enabled`, which means **two segments** `team` and `a`. The right approach escapes each token:

```java
String escapedKey = userKey
        .replace("~", "~0")
        .replace("/", "~1");

String pointer = "/preferences/" + escapedKey + "/enabled";
```

This is a fragment; `userKey` must still be validated for null, length, and schema, and must not contain secrets that should be hidden. The goal is preserving the semantics of a **single Map key**, not serving as an authorization check or malicious-input sanitizer.

### 10.3. Pointers are not an authorization boundary

A JSON Pointer only indicates where a field sits. A client knowing `/users/123/role` does not mean it is authorized to modify `role`. The service layer must enforce permissions for the resource and operation rather than relying on whether a field name passed validation.

For `@ModelAttribute` property binding, consider `setAllowedFields(...)` or dedicated DTOs to prevent mass assignment; for JSON `@RequestBody`, Jackson deserializes according to the schema/DTO and does not use `allowedFields` the way form-urlencoded property binding does. Validators only check constraints; they never enforce authorization on their own.

## 11. Mapping errors on the frontend: UX and request lifecycle

### 11.1. Rendering errors by pointer

A frontend may hold state like:

```json
{
  "lineItems": [
    {"sku": "A", "quantity": 1},
    {"sku": "", "quantity": 0}
  ]
}
```

If it receives:

```json
{
  "pointer": "/lineItems/1/sku",
  "code": "REQUIRED_TEXT",
  "message": "A text value is required"
}
```

the UI can highlight the `sku` field on the second row. To process pointers, the client needs a **standard JSON Pointer library or a thoroughly tested parser**, rather than calling `split("/")` and forgetting to unescape `~0`/`~1`. Furthermore, some paths may not resolve against the original payload because the field was **required but omitted**.

### 11.2. Do not retain stale errors by index after the list changes

If the user deletes the first row after the server returns errors, `/lineItems/1/sku` may now point to a different row. Common strategies:

- Tie errors to the submitted request snapshot and clear or resync them when form state changes.
- Use a frontend-stable row ID (distinct from array index) to track transient errors.
- On resubmission, the server returns pointers matching the new list.
- Never blindly carry pointers from a previous submission into the state of a newer submission.

### 11.3. Error codes and messages serve different roles

The client can pick an icon from `REQUIRED_TEXT`, focus the input from `pointer`, and render the localized `message`. Never branch logic on text like `"A text value is required"`, because text changes when the locale changes. Error codes should be published, versioned, and contract-tested by the backend.

### 11.4. Multiple errors on the same field

For instance, `quantity` might violate multiple constraints if annotations or validation groups overlap. The API should return a **list of errors**, not collapse them into a `pointer -> single message` Map that drops subsequent errors. If the UI displays only one message, that is a documented presentation-priority choice on the frontend or backend.

The demo preserves every `FieldError` and sorts them deterministically; it does not discard errors sharing the same pointer.

## 12. Common mistakes and how to fix them

### 12.1. Replacing brackets and dots without a parser

Unsafe pattern:

```java
String pointer = "/" + springPath
        .replace("[", "/")
        .replace("]", "")
        .replace(".", "/");
```

On `preferences[weekly.news].enabled`, this fails because the key `weekly.news` is split into two path tokens. Tokenize according to the actual grammar or convert from structured metadata.

### 12.2. Forgetting to escape slashes and tildes in Map keys

`team/a~b` must become `team~1a~0b`. Otherwise, an API client decoding the pointer will navigate to a different node or fail to find it. Escape per token, never the `/` separators.

### 12.3. Using pointer "/" for the root

Root is `""`. `"/"` points to a member with an empty key. When the API does not know the error location, define an explicit fallback instead of using an arbitrary slash.

### 12.4. Assuming field path always equals JSON field name

`@JsonProperty("items")` on property `lineItems` changes the JSON name. A naive Java path parser is unaware of this. Translate using the DTO schema or avoid publishing inaccurate pointers.

### 12.5. Treating a dotted Map key as a nested bean property

In `preferences[weekly.news].enabled`, the dot inside the brackets belongs to **one key**. If the frontend parses it wrongly, it may attach the error to a non-existent field.

### 12.6. Attaching a collection-level error to the first item

`@NotEmpty List<?> lineItems` fails when the list is empty; at that point there is no first item to attach the error to. The pointer should target `/lineItems`, not a fabricated `/lineItems/0`.

### 12.7. Returning JSON decoding errors as FieldErrors

If JSON has invalid syntax or an unreadable field type, Spring MVC usually stops in the HTTP message converter and throws `HttpMessageNotReadableException`. There is no `BindingResult` as with a validated DTO. Handle it separately with a body-read error code.

### 12.8. Testing only the first element

Testing only `lineItems[0]` makes it easy to miss off-by-one index bugs. Include tests for `lineItems[1]`, `lineItems[12]` where relevant, and list deletions/insertions/reordering.

### 12.9. Claiming arbitrary Map key support without actually supporting it

Keys can contain `]`, quotes, spaces, Unicode, escape sequences, numbers, or other characters. The demo parser accepts only a subset; for keys outside that subset, it returns `Optional.empty()`. Production systems must expand this using structured data, round-trip tests, and safety limits — never silently strip characters and alter the key.

### 12.10. Returning internal Spring field paths as long-term API identifiers

Refactoring a model name, Java property, or Bean Validation adapter can change internal paths. If your response contract publishes `pointer` against a JSON schema, protect it with integration tests and plan migrations whenever the JSON contract actually changes.

### 12.11. Confusing field errors with query/header errors

If an error occurs on `@RequestParam int page`, the source is `query`, not the JSON body. Do not construct `pointer="/page"` as if a body field existed. Return `source="query"`, `parameter="page"`, or an equivalent error schema.

### 12.12. Failing to bound error counts

A large list can generate thousands of `FieldError` entries. Serializing all of them with long pointers can bloat response sizes and leak key data. Enforce error limits, maximum request sizes, nesting depth caps, truncation contracts, and appropriate logging.

## 13. Testing the API contract systematically

| Scenario | Example | What to verify |
| --- | --- | --- |
| Nested object | `shipping.address.postcode` | `/shipping/address/postcode` |
| First element | `lineItems[0].sku` | `/lineItems/0/sku` |
| Second element | `lineItems[1].quantity` | `/lineItems/1/quantity` |
| Two-digit index | `lineItems[12].sku` | `/lineItems/12/sku` |
| Simple Map key | `preferences[alerts].enabled` | `/preferences/alerts/enabled` |
| Dotted Map key | `preferences[weekly.news].enabled` | Key is not split in two |
| Map key with slash and tilde | `preferences[team/a~b].enabled` | `/preferences/team~1a~0b/enabled` |
| Map key outside grammar | e.g., containing `]` | Root fallback or dedicated structural error; no guessing |
| Empty list | `@NotEmpty lineItems` | Error at `/lineItems` |
| Missing nested property | `{"alerts":{}}` | Document that pointer can be a logical target |
| Class-level constraint | Cross-field rule | Root error or explicit field node |
| Unreadable JSON | Syntax/type mismatch | `UNREADABLE_BODY`, no fabricated pointers |
| JSON name differs from Java name | `@JsonProperty("items")` | API pointer uses JSON name, not Java name |
| Query parameter error | `page=0` with `@Min(1)` | Not mislabeled with body source |
| Multiple constraints on same pointer | Multiple `FieldError`s | No errors dropped |
| Sensitive Map key | Key contains email/token | Not exposed when disallowed |

A strong contract test asserts **path, error code, and HTTP status together**, not merely the error count. If the API supports multiple DTO versions or aliased field names, run the same test suite against each version.

## 14. Path toward production-grade implementations

The parser in this project intentionally restricts its grammar for a runnable lesson. A larger system may also need:

1. **Schema-aware JSON property translation** aligned with actual Jackson configuration so Java field names never leak into the API.
2. **A structured path adapter** built from Jakarta `Path.Node` when metadata is available, distinguishing properties, iterable indices, and Map keys.
3. **An explicit location model**: `source=body/query/header/path` paired with the corresponding pointer or parameter.
4. **A consistent error envelope**: request-level code, field/global error list, trace ID, locale, and optional Problem Details.
5. **Stable business codes** independent of collection indices and key names.
6. **Security redaction** for sensitive keys and rejected values.
7. **Bounded responses**: limits on error count, pointer length, segment count, and nesting depth.
8. **Contract tests** run after upgrading Spring, Hibernate Validator, Jackson, or changing naming strategies.
9. **A compliant frontend pointer decoder** following RFC 6901, tested on `~0`, `~1`, Map keys, empty tokens, and missing properties.
10. **Error schema versioning** so pointer rules or field names can evolve without breaking older clients.

### `ProblemDetail` and the `pointer` field

Spring supports `ProblemDetail`/RFC 9457. An error response can look like:

```json
{
  "type": "https://api.example.org/problems/validation-failed",
  "title": "Request validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    }
  ]
}
```

This is a **suggested schema**, differing from the exact output of the runnable demo. `errors` and `pointer` are **application-defined extension fields**, not mandatory RFC 9457 fields. When adopting Problem Details, preserve the semantics of `type`/`title`/`status`/`detail`/`instance` and add extensions only within a clear namespace/contract.

### Distinguishing pointers to request input vs. pointers to response

For resource-creation endpoints, the request DTO may differ from the domain entity and response representation. Pointers in validation errors should be documented as **locations in the request input schema**, not necessarily in the database object or returned JSON response. This is especially important when using DTO → entity mapping or renaming fields between representations.

## 15. Implementation checklist

- [ ] Clearly define `pointer` as an RFC 6901 JSON Pointer string representation.
- [ ] Keep `code` stable, independent of indices or localized messages.
- [ ] Distinguish Spring paths, Jakarta structured paths, and JSON property names.
- [ ] Test index 0, index 1, and multi-digit indices.
- [ ] Never split on dots when a key is inside brackets.
- [ ] Escape `~` to `~0` and `/` to `~1` **per token**.
- [ ] Distinguish root `""` from empty-key member `"/"`.
- [ ] When a field is missing, document pointers as logical field locations or choose the parent pointer.
- [ ] Never emit a pointer if the path is outside the grammar or incompatible with the JSON naming strategy.
- [ ] Define rules for collection-level and object-level validation.
- [ ] Distinguish `MethodArgumentNotValidException` from JSON decoding and method validation.
- [ ] Never return raw rejected values or sensitive Map keys unless the contract permits it.
- [ ] Bound error count, pointer length, path depth, and request body size.
- [ ] Test the API via `MockMvc`, not only with unit tests on the string parser.
- [ ] Whenever a DTO changes `@JsonProperty` or naming strategies, update and test the adapter against the JSON contract.
- [ ] When the frontend reorders lists, do not blindly keep stale errors attached by index.
- [ ] For query/header fields, use a location model distinct from JSON body pointers.

## 16. Conclusion

**Mapping collection or Map paths to an API contract** is more than replacing `.` and square brackets with `/`.

Spring `BindingResult`/`FieldError` expresses error locations as **property paths**; RFC 6901 JSON Pointer expresses locations in the **JSON document structure**. A correct conversion requires understanding **array indices, Map keys, nested properties, `~` and `/` escaping, actual JSON names, and missing-field cases**.

An API can pair `pointer` + `code` + `message` so the frontend displays errors accurately inside lists or Maps. Whenever path semantics are uncertain, return a parent/root-level error with a documented fallback rather than **publishing a wrong pointer**. Combining typed validation paths, DTO-schema-aware mapping, security bounds, and contract tests yields error responses that are usable, consistent, and resilient as your API grows.

## References

- [RFC 6901 — JavaScript Object Notation (JSON) Pointer](https://www.rfc-editor.org/rfc/rfc6901)
- [Spring Framework 6.2 — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — SpringValidatorAdapter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html)
- [Spring Framework — MVC @RequestBody and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Jakarta Bean Validation 3.0 — ConstraintViolation and Path](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Spring Framework — Problem Details / Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
