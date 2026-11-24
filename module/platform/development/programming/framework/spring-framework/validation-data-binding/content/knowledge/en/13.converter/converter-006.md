# Converting String to Enum and Case-Sensitivity Rules in Spring

## 1. Problem and Goal to Understand

In Java, an `enum` represents a finite, strongly typed set of constants. When receiving HTTP parameters, form data, or configuration strings, Spring typically receives the initial value as a `String` and then must convert it to the `enum` type to assign to a parameter or object property.

Example:

```java
public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    DONE
}
```

For the constant name `DONE`, the two strings `"DONE"` and `"done"` are **not the same**. Case-sensitivity rules are part of the conversion policy. By default, Spring Framework matches enum constant names in a **case-sensitive** manner; if you want `done`, `Done`, and `DONE` accepted identically, you must select or configure an appropriate conversion mechanism.

After this article, you should be able to distinguish: Java's `Enum.valueOf` behavior; how Spring's `ConversionService` converts `String` to enum; the role of a custom `Converter`; how errors enter data binding; and the boundary between query/path/form binding and JSON bodies.

## 2. Java Foundation: Enum Constant Name Is an Exact Value

`Enum.valueOf(OrderStatus.class, text)` looks up the constant whose **name matches `text` exactly**. This method does not automatically `trim()`, does not normalize case, and does not search by display labels or business codes.

- `Enum.valueOf(OrderStatus.class, "DONE")` → `OrderStatus.DONE`.
- `Enum.valueOf(OrderStatus.class, "done")` → throws `IllegalArgumentException`.
- `Enum.valueOf(OrderStatus.class, " DONE ")` → throws `IllegalArgumentException` if passed directly, due to spaces.
- `Enum.valueOf(OrderStatus.class, "IN_PROGRESS")` → `OrderStatus.IN_PROGRESS`.
- `Enum.valueOf(OrderStatus.class, "IN-PROGRESS")` → error: a hyphen is not an underscore.
- `Enum.valueOf(..., null)` → throws `NullPointerException`; this is a Java API rule and must be distinguished from Spring's null-input handling.

`name()` returns the declared name, e.g., `DONE`. `toString()` may be overridden to show a different label, yet **it does not change how `Enum.valueOf` searches**. Do not rely on user-friendly labels to infer Java constant names.

## 3. How Does Spring Convert String to Enum?

### 3.1. Default ConversionService and ConverterFactory

`ConversionService` is Spring's type-conversion contract. Default services such as `DefaultConversionService` register a `String` → `Enum` converter via `StringToEnumConverterFactory`. Essentially, the enum conversion path checks for an empty string, then looks up the constant name via `Enum.valueOf(targetEnumType, source.trim())`.

Conceptual flow:

```text
String source (query / path / form)
          |
          v
Spring ConversionService / WebDataBinder
          |
          v
StringToEnumConverterFactory (default)
          |
          +-- source == "" ---------> null
          |
          +-- source.trim()
                    |
                    v
          Enum.valueOf(enumType, text)
                    |
             exact name match?
                /          \
              yes           no
              |              |
            Enum     conversion error
```

Because `trim()` occurs in Spring's default step, `" DONE "` can resolve to `DONE` and succeed, even though passing that exact string directly to `Enum.valueOf` would fail. However, `trim()` does **not** turn `"done"` into `"DONE"`.

### 3.2. Default Behavior Table

Suppose the target type is `OrderStatus { NEW, IN_PROGRESS, DONE }` and the service uses Spring Framework's `StringToEnumConverterFactory`:

| Input string | Result | Explanation |
| --- | --- | --- |
| `"NEW"` | `NEW` | Exact name match |
| `"new"` or `"New"` | Conversion error | Case mismatch |
| `" DONE "` | `DONE` | Spring strips leading/trailing whitespace |
| `"IN_PROGRESS"` | `IN_PROGRESS` | Matches constant name |
| `"in_progress"` | Conversion error | Case mismatch |
| `"IN-PROGRESS"` | Conversion error | `-` is not `_` |
| `""` | `null` | Truly empty strings are handled specially by the default converter |
| `"   "` | Conversion error | Initial string is non-empty; after `trim()` the name becomes `""`, matching no constant |
| `"UNKNOWN"` | Conversion error | Enum has no corresponding constant |

For `ConversionService.convert(null, OrderStatus.class)`, the service normally returns `null` without calling `Converter.convert` for null input. You must distinguish `null`, empty string `""`, and whitespace-only string `"   "`; do not assume all three behave identically.

When no enum is found, `Enum.valueOf` throws `IllegalArgumentException`; when invoked through `ConversionService`, the error is usually wrapped in `ConversionFailedException`. How the framework turns that error into an HTTP response or `BindingResult` also depends on where the data is bound.

## 4. Standalone Java 17+ Example to Verify the Rules

Create file `EnumCaseDemo.java`:

```java
import java.util.Locale;

public class EnumCaseDemo {
    enum OrderStatus {
        NEW, IN_PROGRESS, DONE
    }

    public static void main(String[] args) {
        System.out.println(Enum.valueOf(OrderStatus.class, "DONE"));

        try {
            Enum.valueOf(OrderStatus.class, "done");
        } catch (IllegalArgumentException ex) {
            System.out.println("done -> INVALID");
        }

        String normalized = " in_progress "
                .trim()
                .toUpperCase(Locale.ROOT);

        System.out.println(Enum.valueOf(OrderStatus.class, normalized));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac EnumCaseDemo.java
java EnumCaseDemo
```

Exact stdout:

```text
DONE
done -> INVALID
IN_PROGRESS
```

This example uses **plain Java** to demonstrate normalization before `Enum.valueOf`. It does not use Spring yet, so it does not by itself verify the specific configuration of a Spring MVC or Spring Boot application.

## 5. Where Are Enums Bound in Spring MVC?

For URI, query, or form parameters, Spring MVC uses the type conversion mechanism of `WebDataBinder`/`FormattingConversionService` configured for the application. An example controller fragment (inside an application that already has Spring Web MVC):

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders")
    public String list(@RequestParam OrderStatus status) {
        return "status=" + status.name();
    }
}
```

If MVC uses Spring Framework's default enum rules:

- `GET /orders?status=DONE` → binds `OrderStatus.DONE`; the example controller returns `status=DONE`.
- `GET /orders?status=done` → type conversion error; in typical MVC flows this leads to HTTP 400 and the controller is not called.
- `GET /orders?status=%20DONE%20` → whitespace is stripped before matching the name.
- `GET /orders?status=UNKNOWN` → type conversion error; not a valid enum value.

The same mechanism applies to `@PathVariable`, `@RequestHeader`, and enum properties in `@ModelAttribute`, depending on the active `ConversionService`. With `@ModelAttribute`, errors may be recorded as `typeMismatch` in `BindingResult`; for unboundable method parameters, Spring MVC may throw an exception such as `MethodArgumentTypeMismatchException`. Inspect the exact handling path rather than assuming every conversion error goes through Bean Validation.

If empty input turns into `null`, a required `@RequestParam` may still be treated as missing and result in HTTP 400. Optional parameters must be designed explicitly—for instance, `required = false` or `Optional<OrderStatus>`—along with defining behavior when absent.

## 6. When Case-Insensitivity Is Needed: Write an Explicit Converter

If the API contract wants to accept `done`, `Done`, and `DONE`, you can write a `Converter<String, OrderStatus>`. The example below applies specifically to `OrderStatus`, avoiding accidentally altering the policy for all enums in the system.

**File `src/main/java/com/example/demo/OrderStatus.java`:**

```java
package com.example.demo;

public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    DONE
}
```

**File `src/main/java/com/example/demo/OrderStatusConverter.java`:**

```java
package com.example.demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class OrderStatusConverter implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        String normalized = source.trim();

        // Custom policy: whitespace-only strings are treated as absent.
        if (normalized.isEmpty()) {
            return null;
        }

        try {
            return OrderStatus.valueOf(normalized.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Unknown OrderStatus: '" + source + "'", ex);
        }
    }
}
```

**File `src/main/java/com/example/demo/WebConversionConfig.java`:**

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new OrderStatusConverter());
    }
}
```

**File `src/main/java/com/example/demo/OrderController.java`:**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders")
    public String list(@RequestParam OrderStatus status) {
        return "status=" + status.name();
    }
}
```

These files are components of a **Spring MVC/Spring Boot project with the Web dependency**, not a standalone Java program runnable with `javac` alone. When `WebConversionConfig` is component-scanned, the MVC registry contains the registered converter. Calling `GET /orders?status=done` or `GET /orders?status=%20DoNe%20` binds to `DONE` and the controller above returns `status=DONE`.

Explanation of decisions inside the converter:

1. `trim()` removes leading/trailing whitespace, yet does not normalize `-`, `_`, or internal spaces.
2. `toUpperCase(Locale.ROOT)` matches uppercase enum constants using a stable locale; do not let the server or user locale control enum identifiers.
3. `valueOf` confirms the normalized value must still be a real enum constant. `"finished"` cannot magically turn into `DONE`.
4. `normalized.isEmpty()` returns `null` per **the example's policy**. This differs from Spring's default for `"   "`; if the API contract wants to reject all empty/whitespace values, replace this branch with an exception.
5. Throw an exception for invalid values so Spring reports a clear bind error. Do not automatically fall back to `DONE`, the first constant, or `null` for unrecognized strings, as that masks client errors.

You do not always need to uppercase every enum: if constant names follow another convention, or if the API accepts aliases, domain codes `"in-progress"`, numeric codes, or Vietnamese labels, build an explicit mapping table. `equalsIgnoreCase` can be used when iterating constants, yet you must still handle the case where no constant matches.

## 7. Testing ConversionService Before Using Over HTTP

To decouple conversion rules from controllers, test `DefaultConversionService` directly. The JUnit 5 example below assumes `OrderStatus` and `OrderStatusConverter` from section 6 are on the classpath alongside `spring-core` and JUnit Jupiter dependencies:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.*;

class OrderStatusConversionTest {
    @Test
    void defaultConversionIsCaseSensitive() {
        var service = new DefaultConversionService();

        assertEquals(OrderStatus.DONE,
                service.convert(" DONE ", OrderStatus.class));
        assertNull(service.convert("", OrderStatus.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert("done", OrderStatus.class));
        assertThrows(ConversionFailedException.class,
                () -> service.convert("   ", OrderStatus.class));
    }

    @Test
    void customConversionAcceptsMixedCase() {
        var service = new DefaultConversionService();
        service.addConverter(new OrderStatusConverter());

        assertEquals(OrderStatus.DONE,
                service.convert(" dOnE ", OrderStatus.class));
        assertEquals(OrderStatus.IN_PROGRESS,
                service.convert("in_progress", OrderStatus.class));
        assertNull(service.convert("   ", OrderStatus.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert("finished", OrderStatus.class));
    }
}
```

The first test suite confirms Spring Framework's default; the second confirms **the converter we explicitly registered**. They do not prove the full web application uses that exact same registry: add integration tests with `MockMvc` against real endpoints, checking valid cases, invalid cases, empty input, and corresponding HTTP status codes.

Suggested integration test table when using section 6's custom converter:

| `status` in URL | Value after conversion | Expected behavior |
| --- | --- | --- |
| `DONE` | `DONE` | Succeeds |
| `done` | `DONE` | Succeeds |
| `DoNe` | `DONE` | Succeeds |
| `%20done%20` | `DONE` | Succeeds |
| `in_progress` | `IN_PROGRESS` | Succeeds |
| `in-progress` | No match | Input error |
| `unknown` | No match | Input error |
| `%20%20%20` | `null` | With required `@RequestParam`, typically 400 due to missing value after conversion |

## 8. Distinguishing Type Conversion from Validation, JSON, and Configuration

**Conversion happens before validation.** A converter must construct `OrderStatus` from the string before Bean Validation constraints such as `@NotNull` on an enum-typed property take effect. `@NotNull` only checks for null values—it **does not accept `done` or normalize strings**. If conversion fails, a type mismatch error may appear at the binding layer; do not expect every bad enum input to produce a `@NotNull` message.

**`@RequestBody` JSON typically goes through Jackson**, for example a DTO body `{"status":"done"}` deserialized by `ObjectMapper`. A `Converter<String, OrderStatus>` registered in `WebMvcConfigurer.addFormatters` does not automatically become a JSON deserializer. JSON enum policies require appropriate Jackson configuration (such as case-insensitive enum features or `@JsonCreator`), aligned with the API contract.

**Spring Boot configuration binding can differ from Spring MVC.** Spring Boot provides converters and relaxed binding in certain configuration contexts, including case-insensitive enum support. Do not infer from `@ConfigurationProperties` accepting `done` that every `@RequestParam` in the application also accepts `done`. Verify the actual `ConversionService` used in the target flow and test on your exact project version/configuration.

**Letter casing is an API contract decision.** If clients are expected to send exact enum names, prefer keeping the strict policy to catch typos early. If multiple spellings are allowed to improve ergonomics, clearly specify the normalization rule—such as `case-insensitive + trim`—and its scope. If an enum is part of a stable public API, renaming constant `NEW` to `CREATED` can break older clients even with case-insensitivity enabled.

## 9. Common Errors and How to Diagnose Them

- **`done` fails even though the enum has `DONE`:** check the case-sensitive default; either send `DONE` or register an appropriate converter.
- **`" DONE "` works while `"  "` fails:** Spring trims by default before `valueOf` yet only gives special handling to **initially empty** strings; decide a policy for whitespace-only input.
- **Converter written yet endpoint still fails:** check whether the configuration class is scanned, whether the converter was added to MVC's `FormatterRegistry`, and whether another registry/`ConversionService` is in use.
- **Query parameter works while JSON body still fails:** Jackson deserializes JSON via a separate mechanism; check mapper configuration.
- **Applies to one enum yet not another:** `Converter<String, OrderStatus>` handles only `OrderStatus`. To apply across multiple enums, consider `ConverterFactory<String, Enum>` and evaluate system-wide impact before registering.
- **Enum display values are translated or `toString()` is overridden:** default lookup uses `name()`; if domain codes or labels are needed, build an explicit mapping instead of mixing Java names with wire formats.
- **HTTP error mistaken for a `@NotNull` error:** inspect the root cause (type conversion vs. constraint violation), required parameter flags, and `BindingResult`/exception handlers.

## 10. Summary of Practical Rules

1. Start from the enum and input contract: which constant names are allowed, and are different cases, whitespace, or aliases accepted?
2. With Spring Framework's default `ConversionService`, `String` → `Enum` is **case-sensitive**, performs `trim()`, returns `null` for `""`, and may fail on whitespace-only strings.
3. When case-insensitivity is needed, normalize intentionally with `Locale.ROOT` and `Enum.valueOf` inside a converter, then register it in the right registry. Never swallow unknown values into a default.
4. Test the converter standalone and test real binding (query/path/form). If JSON bodies exist, test Jackson independently; if configuration binding exists, test Spring Boot in that context.
5. Treat enum constant names as part of the contract between systems whenever they are sent directly over an API.

### References

- Spring Framework — [Type Conversion in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- Spring Framework — [Type Conversion and ConverterFactory](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).
- Spring Framework Source — [StringToEnumConverterFactory](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/StringToEnumConverterFactory.java).
