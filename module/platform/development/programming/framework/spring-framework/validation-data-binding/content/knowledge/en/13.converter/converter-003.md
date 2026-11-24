# Reporting Invalid Input with Appropriate Exceptions in Spring Converter

## 1. Why Does a Converter Need to Report Errors Clearly?

A Spring Converter takes a source value and converts it to a target type. For example, an application receives a status code string `"ACTIVE"` and converts it to the enum `AccountStatus`. A valid value can be converted into an object; however, if the user sends `"UNKNOWN_STATUS"`, the converter must signal that **the source value cannot be converted under the defined rules**.

In Spring Core, the `org.springframework.core.convert.converter.Converter<S, T>` contract is:

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

For an invalid source value, Spring's documentation guides converters to throw an unchecked exception—specifically, **`IllegalArgumentException`** should be used to report an invalid source. `ConversionService` or the binding layer above will handle that exception and represent the failure according to context.

Things to distinguish:

- **`IllegalArgumentException` inside the converter:** the implementation states that the input value does not satisfy the conversion rules.
- **`ConversionFailedException`:** Spring's `ConversionService` reports that an actual conversion attempt failed; this exception can preserve the underlying cause.
- **`TypeMismatchException` / `BindException` / Spring MVC exceptions:** errors may be represented at the bean property binding or web request binding layer, depending on the data path.
- **Business validation:** data converted successfully to the Java type yet fails business rules; this needs validation or an appropriate business exception rather than forcing everything into a conversion error.

A converter should not swallow errors and return a fake value, because the calling layer will mistakenly assume the data was converted successfully.

## 2. The Converter Rule: Throw IllegalArgumentException

Example of a converter that turns a string into a postal code of exactly 5 digits:

```java
public final class PostalCodeConverter
        implements Converter<String, PostalCode> {

    @Override
    public PostalCode convert(String source) {
        if (source == null || !source.matches("\\d{5}")) {
            throw new IllegalArgumentException(
                "Postal code must contain exactly 5 digits"
            );
        }
        return new PostalCode(source);
    }
}
```

This is an abbreviated example, assuming a suitable `PostalCode` type exists. With `Converter.convert(S)`, Spring guarantees that the passed source is non-null by contract; the null check in the example is only to make the rule explicit if the method is invoked manually or the logic is reused. In a typical converter, you can focus on validating the format of the source actually provided by the contract.

Why choose `IllegalArgumentException`?

1. It expresses a failure caused by an invalid **argument value** for the conversion operation.
2. It is an unchecked exception, fitting the `T convert(S source)` signature which declares no checked exceptions.
3. Spring's `ConversionService` knows how to handle this exception during conversion and report an appropriate `ConversionException`.
4. The calling layer can use the cause for diagnostics or map it to an appropriate response.

**Do not throw `IllegalStateException`** for a user-entered string in the wrong format. `IllegalStateException` normally expresses that the program/object state is unsuitable for executing the operation. Invalid input data is an argument issue.

Also do not return `null` to signal conversion failure. `null` can carry valid meaning in the conversion system (for instance, a null source, a converter with a specific convention, or a nullable target); it does not clearly state that the user sent invalid data. Report errors with an exception.

## 3. How Does Spring Wrap the Error?

A custom converter throws `IllegalArgumentException`. When called through `GenericConversionService` or `DefaultConversionService`, Spring can wrap this exception in **`org.springframework.core.convert.ConversionFailedException`**, a subclass of `ConversionException`.

High-level flow:

```text
ConversionService.convert(source, TargetType)
                 |
                 v
        find matching Converter
                 |
                 v
     Converter.convert(source) 
                 |
         +-------+-------+
         |               |
conversion succeeds   throws IllegalArgumentException
         |               |
         v               v
    Target value    ConversionFailedException
                         |
                         v
           calling layer decides how to report error
```

`ConversionFailedException` describes an actual conversion attempt that failed. It can provide:

- `getSourceType()`: the source type being converted.
- `getTargetType()`: the desired target type.
- `getValue()`: the value that caused the failure (use caution when logging).
- `getCause()`: the cause, typically the exception thrown by the converter.

Not every failure when using `ConversionService` has `IllegalArgumentException` as its cause. For instance, failing to find a converter can lead to `ConverterNotFoundException`; some conversion paths can produce other appropriate exceptions. Therefore, do not catch `IllegalArgumentException` externally and assume every problem is an invalid input value.

### Distinguishing the Two Places Exceptions Are Thrown

| Place | Exception expected | Meaning |
| --- | --- | --- |
| Code inside custom converter | `IllegalArgumentException` | Source cannot be converted according to converter rules |
| Spring `ConversionService` executing converter | `ConversionFailedException` or corresponding `ConversionException` | Actual conversion attempt failed |
| No matching converter found | `ConverterNotFoundException` | Missing conversion capability, likely a configuration issue |
| JavaBean/property binding | Can be translated into `TypeMismatchException` and a binding error | Could not assign input to target property |
| Spring MVC request parameter/path variable | Specialized exception such as `MethodArgumentTypeMismatchException` | Could not convert request value to controller parameter type |

**Rule:** in a converter written against Spring's SPI, throw `IllegalArgumentException`; let `ConversionService` and the integration layer handle wrapping/mapping errors. Avoid throwing `ConversionFailedException` yourself merely to mimic Spring's wrapping, unless you are building an infrastructure layer that invokes that API directly and genuinely possesses full source/target metadata.

## 4. Runnable Java 17 Example: Invalid Input in a Converter

The following program uses `DefaultConversionService` from Spring Framework 6.1.14. The converter accepts a tracking code string shaped like `AB-123456`. If malformed, the converter throws `IllegalArgumentException`. When run through `ConversionService`, the program catches `ConversionFailedException` and prints the exception type, source/target types, and cause.

Structure:

```text
converter-invalid-input/
├── pom.xml
└── src/main/java/demo/ConverterInvalidInputDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-invalid-input</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ConverterInvalidInputDemo.java`:

```java
package demo;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterInvalidInputDemo {

    public record TrackingCode(String value) {}

    public static final class StringToTrackingCode
            implements Converter<String, TrackingCode> {

        @Override
        public TrackingCode convert(String source) {
            if (source == null || !source.matches("[A-Z]{2}-\\d{6}")) {
                throw new IllegalArgumentException(
                    "Expected format LL-123456"
                );
            }
            return new TrackingCode(source);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(new StringToTrackingCode());

        TrackingCode valid =
            service.convert("AB-123456", TrackingCode.class);
        System.out.println("valid=" + valid.value());

        try {
            service.convert("bad-code", TrackingCode.class);
        } catch (ConversionFailedException ex) {
            System.out.println("exception="
                + ex.getClass().getSimpleName());
            System.out.println("source="
                + ex.getSourceType().getType().getSimpleName());
            System.out.println("target="
                + ex.getTargetType().getType().getSimpleName());
            System.out.println("cause="
                + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterInvalidInputDemo
```

Lines printed by the program (excluding Maven/Spring logs if any):

```text
valid=AB-123456
exception=ConversionFailedException
source=String
target=TrackingCode
cause=IllegalArgumentException
```

Explanation:

1. `service.addConverter(...)` registers the converter for the `String → TrackingCode` pair.
2. The value `"AB-123456"` matches the format expression, so the converter constructs the `TrackingCode` record.
3. The value `"bad-code"` does not match, so the converter throws `IllegalArgumentException`.
4. `ConversionService` catches the internal conversion error and throws `ConversionFailedException` containing source, target, and cause details.
5. The calling code catches the exception at **an appropriate boundary** to handle or translate it into a response; the converter does not decide HTTP status codes itself.

## 5. Which Exception Should Be Used When?

Choose the exception according to **the layer handling it** and **the kind of error**.

### A. Inside a Converter: IllegalArgumentException

When the input has a valid source type yet its value falls outside the domain the converter can convert:

```java
@Override
public CurrencyCode convert(String source) {
    if (!source.matches("[A-Z]{3}")) {
        throw new IllegalArgumentException(
            "Currency code must contain 3 uppercase letters"
        );
    }
    return new CurrencyCode(source);
}
```

This is an illustrative snippet, assuming a `CurrencyCode` type. A converter only knows how to convert; it should not depend on `HttpServletResponse`, `ResponseEntity`, or the controller layer.

### B. When Calling ConversionService Directly: ConversionException

If the application calls `conversionService.convert(...)` itself, it can handle `ConversionException` at an appropriate boundary:

```java
try {
    TrackingCode code = conversionService.convert(
        rawValue, TrackingCode.class
    );
} catch (ConversionException ex) {
    // Translate into an input error according to the use case contract.
}
```

`ConversionFailedException` is a specific form of `ConversionException`. You can catch the superclass if you want to handle other conversion failures as well; catch the specific subclass if you need source/target metadata. Do not catch all `RuntimeException`s just to return "input invalid", as that hides programming bugs or infrastructure errors.

### C. When Binding to a JavaBean: TypeMismatchException and BindingResult

In property binding, Spring can turn conversion errors into `TypeMismatchException` and record them as `FieldError`s in `BindingResult`. With `DataBinder`, check:

```java
BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("quantity")) {
    // Input for quantity could not be bound or is invalid on the field.
}
```

When using `DataBinder`/`WebDataBinder`, you do not necessarily have to catch exceptions around each converter invocation; the binding mechanism usually manages errors through the `BindingResult` model. If you want fail-fast behavior, configure and invoke the appropriate API; do not assume every error escapes as an unhandled exception.

### D. In Spring MVC: Parameter-Specific Exceptions

Common scenarios:

| Input data style | Example | Common exception/error path |
| --- | --- | --- |
| `@RequestParam int page` | `?page=abc` | `MethodArgumentTypeMismatchException` |
| `@PathVariable UUID id` | `/orders/not-a-uuid` | `MethodArgumentTypeMismatchException` in the corresponding handler mapping |
| `@ModelAttribute` with numeric property | `quantity` field is `"abc"` | `BindingResult` has a field error; if thrown, it may be `BindException` |
| `@RequestBody` unreadable/unconvertible JSON | Malformed JSON or incompatible with target | Converter/deserialization exception such as `HttpMessageNotReadableException` |
| `@Valid @RequestBody` with constraint violation | `quantity < 1` after parsing succeeds | `MethodArgumentNotValidException` in standard MVC flow |

Do not throw `MethodArgumentTypeMismatchException` inside a converter. That exception requires method parameter metadata, parameter name, received value, and required type, which belong to the Spring MVC layer. A converter should not know which controller is calling it.

### E. When Data Has the Right Type Yet Fails Business Rules

For example, `quantity=0` parses successfully to `Integer`, yet ordering rules require a value greater than 0. This is not a conversion failure. Use Bean Validation (`@Min(1)`), a Spring `Validator`, or an appropriate business rule. Spring MVC can then throw `MethodArgumentNotValidException` or record errors in `BindingResult` depending on controller signature/trigger point.

Do not use `IllegalArgumentException` inside a converter for every business rule; a converter should focus on producing the target type from the source.

## 6. Mapping to HTTP Responses at the Web Boundary

Converters are often used across multiple places: bean configuration, DataBinder, MVC, WebFlux, services, or plain Java code. If a converter throws `ResponseStatusException` itself or depends on the Servlet API, it ceases to be a reusable Spring Core converter.

In Spring MVC, map errors in a controller advice or handler. **Illustrative** example for a type mismatch error on a request parameter:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.ResponseEntity;

@RestControllerAdvice
class ApiInputExceptionHandler {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<String> handleTypeMismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body("Invalid value for parameter: " + ex.getName());
    }
}
```

This snippet is an example for a Spring MVC REST application that already includes Spring Web. It does not replace the Java SE program in section 4. When you want to catch errors from a custom converter called directly by a service, you can handle `ConversionException` at the service boundary or translate it into an application exception; you should not map all conversion failures globally if some failures are internal configuration errors.

Real responses should have a consistent error structure and avoid sending stack traces, internal class names, or sensitive raw input to clients. Example JSON could be:

```json
{
  "error": "INVALID_INPUT",
  "field": "trackingCode",
  "message": "Tracking code must match LL-123456"
}
```

This response schema is designed by the application itself; Spring does not automatically return this exact JSON without a corresponding handler/exception mapping.

## 7. Design Mistakes in Custom Converters

### 7.1. Returning null When Data Is Invalid

```java
if (!valid(source)) {
    return null;
}
```

This approach is dangerous because the caller cannot distinguish "no value provided" from "user sent an unconvertible value". It can cause errors much further downstream, making the root cause hard to trace. Throw `IllegalArgumentException` for invalid input.

### 7.2. Swallowing Exceptions and Returning a Default Object

```java
try {
    return parse(source);
} catch (RuntimeException ex) {
    return DEFAULT_VALUE;
}
```

This is a silent fallback. For example, an invalid currency code being converted to VND by default can corrupt data. Only use a fallback if it is an explicit business policy placed in the appropriate layer, never to hide parse errors.

### 7.3. Throwing Checked Exceptions from a Converter

`Converter.convert` does not declare checked exceptions. Do not arbitrarily wrap checked exceptions in complex business exceptions if the failure is simply an unconvertible input. Choose `IllegalArgumentException` for an invalid source; if a serious infrastructure failure or non-input error occurs, let the appropriate exception propagate and handle it at the surrounding layer.

### 7.4. Coupling HTTP Status Codes to a Converter

Throwing `ResponseStatusException` directly inside a converter ties Spring Core to the web layer. A converter may be invoked from a batch job or service where an HTTP status has no meaning. Let the web adapter decide the appropriate status.

### 7.5. Catching Every Exception and Turning It into 400

A database error, a null pointer from buggy code, or a misconfigured converter may be a server error, not an input error. Only map error types known to be client-caused; log sufficient technical details on the server with sensitive data filtered out.

### 7.6. Using Exceptions Instead of Validation

The value `"16"` converts to `Integer` successfully, yet the minimum age is 18. That is a constraint, not a conversion error. Use `@Min(18)` or an appropriate validator.

## 8. Testing Converters and Exceptions

For a pure converter, include at least these cases:

| Test | Input | Expectation |
| --- | --- | --- |
| Valid | `AB-123456` | Returns `TrackingCode` with exact value |
| Malformed | `bad-code` | Converter throws `IllegalArgumentException` when called directly |
| Called via `ConversionService` | `bad-code` | `ConversionFailedException` with cause `IllegalArgumentException` |
| Unsupported target type | A target type with no converter | Likely `ConverterNotFoundException`, not invalid source |
| Null source | Depends on nullable/caller contract | Do not assume it acts like a malformed string; check API path |
| Collection containing bad element | List with one invalid item | Conversion can fail on that element; inspect exception cause |

JUnit 5 test example verifying that the converter rejects a source:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class TrackingCodeConverterTest {

    private final ConverterInvalidInputDemo.StringToTrackingCode converter =
        new ConverterInvalidInputDemo.StringToTrackingCode();

    @Test
    void rejectsInvalidSource() {
        assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("bad-code")
        );
    }
}
```

This is a test snippet depending on JUnit 5 and the class from section 4's example. A test at the `ConversionService` level should verify the wrapping exception and cause:

```java
assertThrows(
    ConversionFailedException.class,
    () -> service.convert("bad-code", TrackingCode.class)
);
```

In addition to checking the exception type, assert that `getCause()` is `IllegalArgumentException`. Do not lock tests to the entire wording of the message if messages may be refined; check error codes/fields and essential details per the public contract.

## 9. Exception Selection Workflow

When handling invalid input, ask these questions in order:

1. **Can the input be converted to the target type?** If not, a custom `Converter` throws `IllegalArgumentException`; `ConversionService` turns it into a conversion failure.
2. **Is there no converter for the source/target pair?** This is usually a conversion capability/configuration issue, such as `ConverterNotFoundException`; do not tell the user the format is wrong if the application is actually missing a converter.
3. **Did type conversion succeed yet violate a constraint?** Use Bean Validation or a Spring `Validator`; do not simulate a conversion error.
4. **Did the error occur during bean property binding?** Inspect `BindingResult`/`FieldError` or handle the appropriate binding exception.
5. **Is the error on a request parameter/path variable?** Use the exception provided by Spring MVC at the method argument layer, such as `MethodArgumentTypeMismatchException`.
6. **Did the error occur while reading a JSON body?** Look at `HttpMessageConverter`/Jackson exceptions, commonly `HttpMessageNotReadableException`.
7. **Where should the HTTP status be chosen?** In controller advice or at the web boundary, following the API contract; a reusable converter does not decide HTTP details.

## 10. Self-Check Questions

1. Why should a custom `Converter<String, T>` throw `IllegalArgumentException` when the source cannot be converted?
2. When a converter throws an error through `DefaultConversionService`, which exception usually wraps the cause? How do you retrieve the cause?
3. How does `ConverterNotFoundException` differ from `ConversionFailedException`?
4. Why should a converter not throw `ResponseStatusException`?
5. When `@RequestParam int page` receives `abc`, which exception can the MVC layer report?
6. Is an integer that converts successfully yet is smaller than a business limit a conversion error or a validation error?
7. Why can returning `null` or a default value for an invalid source make errors harder to detect?
8. When using `DataBinder`/`BindingResult`, why do you not necessarily need to catch converter exceptions around each property?
9. Why should you not map every `RuntimeException` to HTTP 400?

**Remember:** A custom Spring `Converter` uses `IllegalArgumentException` to report an invalid source value. When run through `ConversionService`, Spring can wrap it in `ConversionFailedException`. Property binding and Spring MVC have specialized error types at higher layers. Let converters report conversion errors, validators report constraint errors, and the web boundary decide the HTTP response.

## References

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1 — `Converter<S,T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Spring Framework 6.1 — `ConversionFailedException` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionFailedException.html
- Spring Framework 6.1 — `ConversionService` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework — Spring MVC Exceptions: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-exceptions.html
