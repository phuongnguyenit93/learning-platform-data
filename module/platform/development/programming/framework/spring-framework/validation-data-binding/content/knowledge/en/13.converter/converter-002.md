# Handling Non-Null Sources Under the Converter Contract in Spring Framework

## 1. The Problem to Understand

In Spring Framework, `org.springframework.core.convert.converter.Converter<S, T>` represents a transformation of **a source value of type S** into **a target value of type T**. The core point of the contract: **every time Spring calls `Converter.convert(S source)`, the `source` argument is guaranteed to be non-`null`**. Therefore, a converter registered and invoked properly through Spring's conversion infrastructure can focus on processing a present source value, rather than writing an `if (source == null)` branch at the start of the method.

However, distinguish three concepts:

1. **Non-null source**: `source` is an existing object; this is the guarantee of the `Converter` contract.
2. **Valid source value**: the content of the object must satisfy the rules of the conversion; an empty string, a whitespace-only string, or a malformed code are **non-null yet may be invalid**.
3. **Non-null result**: the `Converter` contract does **not** guarantee this; the API allows `convert` to return `null` when the conversion is designed to do so.

For example: `"12"`, `""`, and `"abc"` are three non-null `String` sources. A string-to-number converter can convert `"12"` to `12`; for `""` or `"abc"`, it must apply the defined business policy (such as reporting an error or producing a null result). A non-null source by itself does not make the content valid.

## 2. The Contract at the Right API Layer

~~~java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
~~~

This is a shortened form to illustrate the essential method; the actual declaration in Spring also includes nullability annotations and the default `andThen` method. From the Javadoc of `convert`:

- `source` must be an instance of type `S` and **must not be null**.
- The return value is an instance of type `T` and **may be null**.
- When the source cannot be converted to the target, the converter should throw `IllegalArgumentException` to indicate an invalid source.
- A converter should be **thread-safe** because it can be reused and invoked from multiple threads.

Key distinctions:

| Invocation style | Can a null source be passed in? | Who is responsible for handling it? |
| --- | --- | --- |
| Direct call `converter.convert(source)` | Not under the `Converter` contract | The caller must ensure `source != null`. |
| `conversionService.convert(source, Target.class)` | Yes; `ConversionService` accepts a null source | The conversion infrastructure handles null before calling the application converter. |
| `converter.convert("")` | Yes: an empty string is still a non-null object | The converter handles it according to input rules, not null rules. |
| `converter.convert("invalid format")` | Yes | The converter validates and reports an error if it cannot be converted. |

**Do not infer backward** that because `ConversionService` accepts `null`, every `Converter` must also handle `null`. The two APIs have different contracts.

## 3. Null Handling Flow When Using ConversionService

In the typical case with `GenericConversionService` or `DefaultConversionService`:

~~~text
Application / Spring Data Binder / Spring MVC
                 |
                 v
      ConversionService.convert(...)
                 |
         source == null ?
           /           \
         Yes            No
          |               |
  Handle null at     Select converter
 conversion layer          |
          |                v
          |       Converter<S,T>.convert(source)
          |                |
          +--------+-------+
                   |
             Result / error
~~~

- If the source is **non-null** and conversion is needed, Spring finds the appropriate converter and calls `convert` with the non-null source.
- If the source is **null**, `GenericConversionService` uses a null-source handling path instead of passing null to a normal converter. For reference target types such as `Integer` or a custom record, the default result is usually `null`. Some target types have special handling (for example, `Optional` can receive `Optional.empty()`).
- Primitive target types such as `int` cannot hold `null`; do not assume that converting `null` to `int.class` returns 0. `GenericConversionService` throws `ConversionFailedException` when null cannot be assigned to a primitive type.
- A converter is only invoked when the system needs an appropriate conversion; if the source type is already directly assignable to the target type, the conversion service may return the source as-is. Do not rely on a custom converter being guaranteed to run on every type assignment.

This explains why `service.convert(null, SomeType.class)` can complete without `SomeConverter.convert` ever running. In the data binding flow, handling of absent values may also involve binder- or controller-specific rules; do not equate all of them with the converter.

## 4. Complete Example: String → TicketCode

Suppose the system accepts a ticket code consisting of **two letters, a hyphen, and three digits**, such as `AB-123`. The source may have leading/trailing whitespace and lowercase letters; the conversion rule is to normalize and then check the format. Empty strings, whitespace-only strings, or malformed strings must be rejected.

The example uses **Java 17** and **Spring Framework 6.2.14**. Project structure:

~~~text
converter-contract/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConverterContractDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/ConverterContractDemo.java`:

~~~java
package demo;

import java.util.Locale;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterContractDemo {

    record TicketCode(String value) {}

    static final class StringToTicketCode implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            // Spring only invokes this method with a non-null source.
            String normalized = source.strip().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                    "Ticket code must match AA-999");
            }

            return new TicketCode(normalized);
        }
    }

    public static void main(String[] args) {
        var service = new DefaultConversionService();
        service.addConverter(new StringToTicketCode());

        TicketCode code = service.convert("  ab-123  ", TicketCode.class);
        System.out.println(code.value());

        // ConversionService accepts null and handles it before the converter.
        System.out.println(service.convert(null, TicketCode.class));

        try {
            service.convert("abc", TicketCode.class);
        } catch (ConversionFailedException ex) {
            System.out.println(ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Run from the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterContractDemo
~~~

Program stdout:

~~~text
AB-123
null
IllegalArgumentException
~~~

Explanation of each path:

1. `"  ab-123  "` is a non-null source. The converter is invoked, `strip()` removes leading/trailing whitespace, `toUpperCase(Locale.ROOT)` normalizes to `AB-123`, the regex accepts it, so `TicketCode("AB-123")` is returned.
2. `service.convert(null, TicketCode.class)` is handled by the **conversion service**, returning `null` for this reference type. `StringToTicketCode.convert` is not invoked, so calling `source.strip()` inside the converter still conforms to the contract.
3. `"abc"` is a non-null source but invalid. The converter throws `IllegalArgumentException`; when going through `ConversionService`, the conversion error is wrapped in `ConversionFailedException` with root cause `IllegalArgumentException`. That is why the last line prints the root cause class's simple name.
4. If the application **directly calls** `new StringToTicketCode().convert(null)`, it violates the API precondition. Do not use that call as a benchmark for evaluating converters registered through Spring.

There is no mutable per-call state field in `StringToTicketCode`, so this example also satisfies the thread-safety requirement.

## 5. Designing Data Handling: Missing, Empty, Whitespace, Malformed

A non-null source only lets you omit the **null-reference** check inside the converter. It does not replace designing a policy for each kind of input.

| Data | What category? | Recommended handling for ticket codes |
| --- | --- | --- |
| `null` | No source object | Handled by `ConversionService`/binding layer; validation may be needed to mark required. |
| `""` | Non-null String, length 0 | Report `IllegalArgumentException` due to missing valid code. |
| `"   "` | Non-null String, whitespace only | Becomes empty after `strip()`; report error. |
| `"  ab-123  "` | Non-null String, normalizable | Return `TicketCode("AB-123")`. |
| `"ab123"` | Non-null String, missing hyphen | Report format error. |
| `"AB-123"` | Non-null String, valid | Return `TicketCode("AB-123")`. |

Some business rules instead specify that a whitespace string means “not entered” and want it converted to `null`. In that case the converter can be written as:

~~~java
@Override
public TicketCode convert(String source) {
    String value = source.strip();
    if (value.isEmpty()) {
        return null;  // Specific business policy, NOT null-source handling.
    }
    // Validate format, construct TicketCode...
}
~~~

This is an **illustrative snippet inside a converter body**, not a standalone program; this policy differs from the complete example above. Only choose to return `null` if downstream APIs accept the absent state. Do not arbitrarily use `return null` to mask invalid data: it can cause invalid input errors to be misinterpreted as “no data”.

The decision flow should be: **present source → valid normalization → constraint check → produce value T or report a clear error**. If “blank input = absent” truly has domain meaning, write that policy explicitly and test it separately.

## 6. How Does Conversion Differ from Validation?

These two layers answer different questions:

- **Conversion**: “Can the present string be converted into the target object?” For example, `"AB-123"` → `TicketCode`, while `"abc"` → conversion error.
- **Validation**: “Does the converted object/property satisfy data rules?” For example, whether a ticket code is required, has the right length, or exists in the system. In Bean Validation, `@NotNull` can check for absent values; complex business rules can use custom constraints.

Therefore:

1. Do not use the “non-null `source`” contract to conclude that an input field is required. An absent field may **not go through the converter** and still require `@NotNull` or a UI-layer required mechanism.
2. Do not expect a converter to always be invoked before all validation. Actual ordering depends on the binding path, object type, configuration, and errors encountered; the goal is to place each responsibility in the right layer.
3. Do not assume `@NotNull` will catch whitespace strings. A String containing spaces is still non-null; if the constraint requires non-blank text, consider `@NotBlank` on an appropriate string property.
4. When a converter throws an error, Spring MVC may represent it as a binding/type mismatch error; how that error turns into an HTTP response or UI message depends on the controller, `BindingResult`, and exception-handling configuration. Do not assume the converter's `IllegalArgumentException` will always surface verbatim to the client.

Placing responsibilities clearly ensures erroneous data is explained properly: **missing value**, **unconvertible format**, and **well-typed value violating business rules** are three distinct cases.

## 7. Registering a Converter for Spring MVC

When Spring Web MVC is on the classpath, you can register the converter into `FormatterRegistry` via `WebMvcConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ConverterContractDemo.StringToTicketCode());
    }
}
~~~

This is an **integration snippet used in a Spring MVC application**, not part of the standalone Spring Core program in section 4; it requires the corresponding web application dependencies. With the converter registered, the framework can use it for matching binding/conversion paths (for example, a `TicketCode` parameter received from a string). The non-null source rule still resides in the `Converter` contract; the meaning of missing parameters, empty strings, and error messages belongs to the web/binder layer.

If using Spring Boot, identify which conversion service is used in the specific context: an application-configured `ConversionService` bean does not automatically mean every binding mechanism uses that exact bean. Registering via `addFormatters` here specifically targets Spring MVC's conversion registry.

## 8. Converter.andThen and Intermediate Null Values

`Converter` supports `andThen(after)` to compose two steps. The non-null input contract applies to the first converter; the second converter should only receive a **non-null** intermediate value. In Spring's `andThen` implementation, if the first step returns `null`, the combined result is `null` and the second step does not run.

This illustrative snippet can be placed inside a Java method, with `Converter` imported:

~~~java
Converter<String, String> normalize = text ->
    text.isBlank() ? null : text.strip();

Converter<String, Integer> measure = text -> text.length();

Converter<String, Integer> chained = normalize.andThen(measure);

System.out.println(chained.convert("  ABC  ")); // 3
System.out.println(chained.convert("   "));     // null
~~~

- Both calls to the first converter receive a **non-null** String `source`.
- In the second call, `normalize` returns `null` per application policy, `measure` is not invoked with null, and the chain result is null.
- If you **directly call** `chained.convert(null)`, the initial input violates the initial precondition; `andThen` does not turn that direct call into a valid one.

This is why **null at the input** and **null produced by an intermediate step** must be kept distinct. Chaining converters does not guarantee that every value remains non-null after the first step.

## 9. Testing Against the Contract

Test at **two levels** to avoid conflating responsibilities.

**Unit level — calling the converter directly with non-null sources**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ConverterContractDemoTest {
    private final ConverterContractDemo.StringToTicketCode converter =
        new ConverterContractDemo.StringToTicketCode();

    @Test
    void convertsValidNonNullSource() {
        var result = converter.convert("  ab-123  ");
        assertEquals("AB-123", result.value());
    }

    @Test
    void rejectsBlankAndMalformedSources() {
        assertThrows(IllegalArgumentException.class,
            () -> converter.convert("   "));
        assertThrows(IllegalArgumentException.class,
            () -> converter.convert("ab123"));
    }
}
~~~

This test snippet belongs in `src/test/java/demo/ConverterContractDemoTest.java` and needs `package demo;` at the top of the file, along with JUnit Jupiter on the test classpath. This is additional test code for the sample project and will not be executed by Maven unless test dependencies/plugins are added.

**Integration level — calling `ConversionService` to test null at the boundary**:

~~~java
@Test
void serviceHandlesNullBeforeCallingConverter() {
    var service = new DefaultConversionService();
    service.addConverter(new ConverterContractDemo.StringToTicketCode());

    assertNull(service.convert(null, ConverterContractDemo.TicketCode.class));

    var failure = assertThrows(ConversionFailedException.class,
        () -> service.convert("xxx", ConverterContractDemo.TicketCode.class));

    assertInstanceOf(IllegalArgumentException.class, failure.getCause());
}
~~~

Additional imports required for this integration snippet:

~~~java
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.support.DefaultConversionService;
~~~

To run all JUnit 5 tests in the sample project, add the following snippets to `pom.xml` in their respective locations:

~~~xml
<!-- Inside <dependencies> -->
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>

<!-- Inside <build><plugins> -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
~~~

Then run `mvn test`. When combining tests into **a single valid Java file**, place `package demo;` at the top, followed by all `import` statements, then merge the three `@Test` methods inside one `ConverterContractDemoTest` class. The short blocks above illustrate individual parts, so do not paste them consecutively with `import` statements appearing after the class declaration.

**Do not write `assertDoesNotThrow(() -> converter.convert(null))`**: that test imposes the wrong contract on the converter. If you want to test how the application layer accepts null, call `ConversionService` and assert how it handles it. Conversely, if a converter has a separate direct-call API defined by the application itself, document and test the preconditions for that API rather than inferring them from Spring.

Cases to include as business rules expand: strings with Unicode accents, whitespace, overly long codes, special characters, syntactically valid data that is no longer valid by business rules, and multiple threads calling the same converter.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why is it wrong? | What to do |
| --- | --- | --- |
| Every converter starts with `if (source == null) return null;` | Obscures the “non-null source” precondition; can mask direct calls that violate the contract. | Put null handling in `ConversionService`/caller; let the converter focus on present `S` values. |
| Calling `converter.convert(null)` and concluding Spring is unsafe | Direct call bypasses the infrastructure's null-filtering step. | Test `service.convert(null, Target.class)` when verifying Spring's behavior. |
| Treating `""` or `"   "` as `null` | They are non-null `String` objects. | Define explicit policies for empty/blank strings, normalize, and validate. |
| Assuming a converter must always return a non-null T | The contract permits a null result. | Document when null is returned; confirm the receiver accepts null. |
| Catching `NullPointerException` to handle bad source data | Masks programming bugs and hides the real cause. | Validate source content and throw `IllegalArgumentException` when unconvertible. |
| Returning an arbitrary default value on parse error | The system may store wrong data without reporting it. | Only use default values when explicitly specified. |
| Relying on `canConvert` to claim a value is always valid | `canConvert` mainly checks type-level convertibility, not individual string content. | Attempt actual value conversion and handle errors. |
| Storing temporary state in a singleton converter field | Concurrent requests can interfere with each other. | Use local variables; if caching is needed, design it thread-safely. |
| Assuming having a converter replaces validation | Conversion and validation check different conditions. | Check requiredness and business constraints in the appropriate validation layer. |

## 11. Implementation Checklist

1. Document the `S → T` type pair and where the converter is registered.
2. Define the meaning of `null` at the **calling layer**; do not assume the converter directly receives null.
3. Separately specify behavior for non-null sources that are empty, whitespace, malformed, or out of range.
4. Normalize data intentionally (e.g., `strip()`, fixed locale) before checking; do not silently alter values that business rules require preserving.
5. Choose explicitly between returning `T`, returning `null` by deliberate policy, or throwing `IllegalArgumentException` when unconvertible.
6. Keep converters free of per-request mutable state or ensure thread safety.
7. Test the converter with non-null sources; test null handling and exception wrapping through `ConversionService`.
8. Verify how the application's Spring MVC/data binder/validation translates errors into user-facing information.

**Self-check:** (a) Why can `service.convert(null, TicketCode.class)` return null even though `StringToTicketCode.convert` calls `source.strip()` immediately? (b) Does the string `"   "` violate the “non-null source” contract? (c) When `Converter.andThen` gets null from the first step, should the second converter be called with null? The answers respectively are: null is handled in the conversion service first; a whitespace string is non-null so it does not violate the contract, though it may fail rules; `andThen` skips the second step if the intermediate result is null.

## 12. References

- Spring Framework Reference, *Spring Type Conversion*: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Javadoc `Converter<S,T>`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Javadoc `GenericConversionService`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
