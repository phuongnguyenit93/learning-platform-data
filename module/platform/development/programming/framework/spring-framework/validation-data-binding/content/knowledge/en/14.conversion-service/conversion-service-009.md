# Converting null, Empty Strings, and Primitives with Spring ConversionService

> **Topic:** Spring Framework – validation-data-binding  
> **Group:** ConversionService  
> **Scope:** Distinguishing `null` source, empty strings, whitespace-only strings, and numeric/boolean values; default converter behavior; primitives and wrappers; handling in Spring MVC, JavaBeans, and DataBinder. Examples use Java 17 and Spring Framework 6.2.x.

## 1. Why Are These Three States Easily Confused?

In Java and HTTP, the following values are not equivalent:

- `null`: no object reference.
- `""`: a String object of length 0.
- `"   "`: a String containing whitespace characters; `isEmpty()` is false while `isBlank()` is true.
- `0` and `false`: concrete values, not meaning the client omitted them.
- Omitting a parameter/property: the source does not supply that key.

Example:

```text
GET /search                    -> parameter q is absent
GET /search?q=                 -> q is present, value is ""
GET /search?q=%20%20           -> q is present, value is two spaces
GET /search?page=0             -> page has value "0"
GET /search?enabled=false      -> enabled has value "false"
```

With JSON:

```json
{}
{"nickname": ""}
{"nickname": null}
{"enabled": false}
{"page": 0}
```

A property omitted during deserialization may keep its field initializer or constructor default; an explicit null property may overwrite it with null depending on the mapper/creator. Therefore, never assume missing JSON and JSON null are the same state.

This lesson helps you explain:
1. What `ConversionService` does when source is null.
2. How standard converters handle empty/blank differently.
3. The difference between `Integer` and `int`, `Boolean` and `boolean`.
4. Why Spring MVC has special handling when conversion returns null for controller parameters.
5. How to design APIs to distinguish missing, empty, zero, and false.

## 2. ConversionService Handles Null Sources Separately

General API:

```java
public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);
    <T> T convert(Object source, Class<T> targetType);
}
```

`ConversionService.convert(...)` accepts a nullable source. When source is null, `GenericConversionService` handles it in the null-source branch (`convertNullSource(...)`), before invoking ordinary converters.

With Spring's default implementation:
- Most target types receive null.
- An `Optional` target receives `Optional.empty()`.
- A primitive target cannot represent null; conversion fails (`ConversionFailedException`).

Example:

```java
DefaultConversionService service = new DefaultConversionService();

Integer number = service.convert(null, Integer.class); // null
Optional<?> value = service.convert(null, Optional.class); // Optional.empty()
```

Spring's `Converter<S,T>` contract guarantees the argument passed to `convert(S source)` is non-null. Hence a null source is handled beforehand by `ConversionService`; ordinary custom converters should not rely on receiving null.

**A null source differs from an empty String source.** `convert(null, Integer.class)` goes through the null-source branch. `convert("", Integer.class)` has an actual empty String source, so the `String -> Number` converter is invoked and applies its own rules.

## 3. Empty Strings Depend on Converter and Target Type

There is no universal rule that every empty string becomes null. Selected default converters illustrate this:

| Source → target | `""` | `"   "` | Notes |
| --- | --- | --- | --- |
| `String -> String` | `""` | `"   "` | String is kept as-is |
| `String -> Integer/Long` | `null` | Not treated as missing; parsing may fail | Number converter checks empty String, no general blank normalization |
| `String -> Boolean` | `null` | `null` after trim | Accepts a specific set of true/false tokens |
| `String -> Character` | `null` | Space character | A single valid character |
| `String -> UUID` | `null` | `null` if no text | UUID converter checks text before parsing |
| `String -> custom value` | Decided by converter | Decided by converter | Contract must be defined |

The results above reflect the behavior of specific converters in `DefaultConversionService`, not a universal policy for all types. If you want blanks handled differently, configure a converter/formatter or normalize at the appropriate boundary.

### 3.1. String to Number

Spring has a converter factory for numeric types. The generated converter checks `source.isEmpty()`; if true, it returns null. If non-empty, it parses the value to the target number.

```java
Integer empty = service.convert("", Integer.class); // null
Integer zero = service.convert("0", Integer.class);  // 0
Integer one = service.convert("1", Integer.class);   // 1
```

`""` and `"0"` are completely different. An empty string may represent an unentered field; the number 0 is a concrete value. If business logic forbids 0, use validation such as `@Positive` or `@Min(1)` rather than turning 0 into null inside a converter.

Number converters check empty String, not treating all whitespace-only strings identically to empty. If an API needs a rule for `"   "`, trim/validate intentionally and write tests rather than relying on parser failures as a business policy.

### 3.2. String to Boolean

The standard Boolean converter:
1. Trims whitespace.
2. Converts to lowercase using `Locale.ROOT`.
3. Accepts true tokens: `"true"`, `"on"`, `"yes"`, `"1"`.
4. Accepts false tokens: `"false"`, `"off"`, `"no"`, `"0"`.
5. An empty string after trimming returns null; other tokens cause conversion failure.

| Input | Boolean result |
| --- | --- |
| `"true"`, `"yes"`, `"1"` | `true` |
| `"false"`, `"off"`, `"no"`, `"0"` | `false` |
| `""` | `null` |
| `"   "` | `null` after trim |
| `"enabled"` | Conversion failure |

`Boolean.FALSE` is distinct from null. If code needs to distinguish "client did not choose" from "client explicitly disabled", use the `Boolean` wrapper.

### 3.3. String to Character and UUID

The Character converter returns null for an empty string; for length 1 it returns that character; for length greater than 1 it reports an error. Thus `" "` is a space character, not empty.

The UUID converter checks whether the string has text and trims before parsing. Empty/blank can become null; non-empty strings with invalid format cause an error. This is a rule of the specific UUID converter and does not apply to every target.

## 4. Primitives and Wrappers: A Decisive Difference

Primitives cannot hold null; wrappers are objects so they can:

| Primitive | Wrapper | Can hold null? |
| --- | --- | --- |
| `int` | `Integer` | Integer only |
| `long` | `Long` | Long only |
| `boolean` | `Boolean` | Boolean only |
| `double` | `Double` | Double only |

Example:

```java
int count = 0;                  // Java default value
Integer optionalCount = null;   // Can represent absence

boolean enabled = false;
Boolean optionalEnabled = null;
```

When an object is newly instantiated, primitive fields take Java's defaults: 0 for integers, false for boolean, 0.0 for floating-point. Consequently, a primitive cannot tell whether the client actually sent data. If you need to distinguish missing from zero/false, use wrappers or a separate presence representation.

### 4.1. ConversionService with Primitive Targets

With a wrapper, null can be returned:

```java
Integer boxed = service.convert(null, Integer.class);
// boxed == null
```

With a primitive, null cannot be represented:

```java
int primitive = service.convert(null, int.class);
// ConversionFailedException
```

This is a rule at the ConversionService level. Do not assume every Spring MVC/DataBinder pipeline throws the exact same exception; those pipelines may apply their own handling.

### 4.2. Spring MVC Handling Null After Conversion

For named-value arguments such as `@RequestParam`, `@RequestHeader`, `@PathVariable`, and `@CookieValue`, Spring MVC runs a post-conversion step. If the final value is null:
- Primitive `boolean` is handled as `false`.
- Other primitives (such as `int`) cause an error because they cannot accept null.
- Wrappers such as `Integer` can receive null when the parameter is declared nullable, typically via `required = false` or `@Nullable`.
- If the parameter is required and the value becomes null after conversion, Spring treats it as missing and throws the corresponding missing-value exception.

Optional wrapper example:

```java
@GetMapping("/filter")
public String filter(
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Boolean enabled) {
    return "page=" + page + ", enabled=" + enabled;
}
```

With `/filter?page=&enabled=`, number/boolean converters can return null and the wrappers receive null per argument policy.

Primitive example:

```java
@GetMapping("/filter-primitive")
public String filter(
        @RequestParam(required = false) int page,
        @RequestParam(required = false) boolean enabled) {
    return "page=" + page + ", enabled=" + enabled;
}
```

A null result for `boolean` is converted to false; null for `int` cannot be represented and causes an error. Never declare `required=false` on a numeric primitive expecting the method to receive null. Use `Integer` if you need to represent an unset state.

If `@RequestParam(defaultValue = "20")` is declared, Spring applies the default when the parameter is missing or empty per annotation rules. Thus a client sending `?page=` may receive 20, identical to omitting the parameter. Only choose `defaultValue` if the API contract genuinely wants both cases to mean the same thing.

## 5. Summary Table by Input and Target

The table below describes default converters; the MVC columns address named-value arguments when conversion has returned null.

| Input | `ConversionService -> Integer` | `-> Boolean` | MVC `Integer`, optional | MVC `int`, optional |
| --- | --- | --- | --- | --- |
| Source null | null | null | null | Primitive error |
| `""` | null | null | null | Primitive error |
| `"   "` | Not treated as missing; may fail parsing | null after trim | null if conversion returns null | Error if conversion returns null |
| `"0"` | 0 | false | 0 | 0 |
| `"false"` | Number conversion failure | false | Number conversion failure | Number conversion failure |
| `"abc"` | Number conversion failure | Boolean conversion failure | Binding/conversion error | Binding/conversion error |

A `String` target preserves empty Strings. UUID, Character, and custom value types have their own rules. When reading the table, always identify source type, target type, converter, and pipeline.

## 6. Runnable Java 17 Example with Maven

Create the project:

```text
conversion-null-demo/
  pom.xml
  src/main/java/demo/NullEmptyConversionDemo.java
```

### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-null-demo</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### NullEmptyConversionDemo.java

```java
package demo;

import java.util.UUID;

import org.springframework.core.convert.ConversionException;
import org.springframework.core.convert.support.DefaultConversionService;

public final class NullEmptyConversionDemo {

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        Integer nullNumber = service.convert(null, Integer.class);
        Integer emptyNumber = service.convert("", Integer.class);
        Integer zero = service.convert("0", Integer.class);

        Boolean emptyBoolean = service.convert("", Boolean.class);
        Boolean blankBoolean = service.convert("   ", Boolean.class);
        Boolean falseBoolean = service.convert("false", Boolean.class);
        Boolean zeroBoolean = service.convert("0", Boolean.class);

        Character emptyCharacter = service.convert("", Character.class);
        UUID emptyUuid = service.convert("", UUID.class);
        String emptyString = service.convert("", String.class);

        System.out.println("nullToInteger=" + nullNumber);
        System.out.println("emptyToInteger=" + emptyNumber);
        System.out.println("zeroToInteger=" + zero);
        System.out.println("emptyToBoolean=" + emptyBoolean);
        System.out.println("blankToBoolean=" + blankBoolean);
        System.out.println("falseToBoolean=" + falseBoolean);
        System.out.println("zeroToBoolean=" + zeroBoolean);
        System.out.println("emptyToCharacter=" + emptyCharacter);
        System.out.println("emptyToUuid=" + emptyUuid);
        System.out.println("emptyStringLength=" + emptyString.length());

        try {
            service.convert(null, int.class);
            System.out.println("nullToInt=unexpected-success");
        } catch (ConversionException ex) {
            System.out.println("nullToInt=ConversionException");
        }
    }
}
```

Run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullEmptyConversionDemo
```

Stdout:

```text
nullToInteger=null
emptyToInteger=null
zeroToInteger=0
emptyToBoolean=null
blankToBoolean=null
falseToBoolean=false
zeroToBoolean=false
emptyToCharacter=null
emptyToUuid=null
emptyStringLength=0
nullToInt=ConversionException
```

The program requires the `spring-core` dependency; running plain `javac` without Spring on the classpath will not compile. Output illustrates Spring 6.2.x `DefaultConversionService`. If custom converters are registered or the implementation changes, behavior may differ.

## 7. Writing Custom Converters: Blank/Null Must Be Defined

Spring's `Converter<S,T>` contract guarantees the source passed into `convert` is non-null. Therefore:
- There is no need to handle null references as though standard converters receive them.
- You still must decide whether empty/blank is valid.
- Do not automatically return null for empty strings if that could hide invalid data.
- If blank means "not entered", express those semantics clearly in the DTO/application layer.

Value object example:

```java
package demo;

public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || !value.matches("CUS-[A-Z0-9]{5}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
    }
}
```

Converter:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        // source is non-null per Converter contract.
        String normalized = source.strip().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "Customer code must not be blank");
        }

        return new CustomerCode(normalized);
    }
}
```

With this converter, ConversionService handles a null source first; if source is `""`, the converter is called and rejects blank. This keeps a clear distinction between an absent object and a client sending an empty String.

If a value object is optional, make the field a nullable reference/Optional per the contract and define explicitly when blank is treated as missing. Do not construct fake value objects with `value == null`.

## 8. Optional Values and Validation

### 8.1. Required Values

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record PagingRequest(
        @NotNull
        @Min(1)
        Integer page
) {}
```

`@NotNull` detects null; `@Min(1)` rejects zero or negative numbers. `@Min` alone does not treat null as invalid, so the two constraints complement each other.

### 8.2. Optional While Still Distinguishing Zero/False

```java
public record SearchOptions(
        Integer page,
        Boolean includeArchived
) {}
```

Interpretation:
- `page == null`: not specified.
- `page == 0`: client explicitly specified zero; validation may reject if pages start at 1.
- `includeArchived == null`: not selected; policy may apply a default.
- `includeArchived == false`: client explicitly disabled.

Do not merge null and zero when zero carries distinct semantics.

### 8.3. Optional Parameters in MVC

```java
@GetMapping("/items")
public String items(
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Boolean includeArchived) {
    return "page=" + page + ", archived=" + includeArchived;
}
```

Use wrappers to accept null. If the contract wants defaults when missing/empty:

```java
@GetMapping("/items-default")
public String itemsDefault(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "false") boolean includeArchived) {
    return "page=" + page + ", archived=" + includeArchived;
}
```

`defaultValue` is a contract choice; it can make missing and empty parameters yield the exact same result. If you need to distinguish the two cases, track presence/value separately instead of using `defaultValue`.

## 9. Java Primitive Defaults Are Not Input Defaults

JavaBean example:

```java
public class UpdateOptions {
    private boolean enabled;
    private int retryCount;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
```

Right after `new UpdateOptions()`, `enabled` is false and `retryCount` is 0 due to Java's primitive initialization. This does not prove the client sent false or 0. If a form omits those fields, the object may still carry Java's defaults.

Wrappers allow distinguishing them:

```java
private Boolean enabled;
private Integer retryCount;
```

When unassigned, both wrapper fields are null. This is usually the better choice for input DTOs when "not sent" must be distinguished from "off" or "0".

`@NotNull` on a primitive does not detect missing values: a primitive always holds a value. Use wrappers and constraints when input presence is required.

## 10. DataBinder and Property Binding

DataBinder/BeanWrapper uses conversion when setting properties. Outcomes depend on target type:

- `String` properties keep empty strings.
- `Integer` properties can receive null after an empty String is converted to null.
- Primitive properties cannot store null; null-to-primitive is invalid and may be reported as binding/type mismatch depending on the pipeline.
- Custom PropertyEditors/Formatters can define empty handling differently from DefaultConversionService.

DTO example:

```java
public class FilterForm {
    private Integer page;
    private String keyword;

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
```

If input is `page=""`, the number converter may return null. If input is `keyword=""`, String stays empty. Choose appropriate validation: `@NotNull` if page is required; `@NotBlank` if keyword must have content.

For primitive properties, never assume null automatically turns into 0. Test the exact property type and binder in use. If you want a default page of 1, set the default in the DTO constructor/initializer or application service per contract rather than relying on conversion side effects.

## 11. JSON null, Missing, and Primitives

JSON bodies are normally read via an `HttpMessageConverter` such as Jackson, not the same query/form pipeline as WebDataBinder.

Points to control:
- Missing properties may retain field initializers or constructor values.
- Explicit null properties may assign null to wrappers/references.
- Primitives cannot hold null; JSON null/missing handling depends on Jackson settings and creators/properties.
- Settings such as `FAIL_ON_NULL_FOR_PRIMITIVES` can make JSON null for primitives fail.
- Record/constructor DTOs may receive null for both missing and explicit null unless the mapper tracks presence separately.

If an API must distinguish `{}` from `{"page":null}`, use a DTO/deserializer/JSON presence model that preserves that distinction. Do not apply `@RequestParam` rules to infer `@RequestBody` behavior.

## 12. Distinguishing Conversion from Validation

Conversion answers: "can the source value be converted to the target type?". Validation answers: "does the bound value satisfy the constraints?".

Examples:
- `"0"` → `Integer(0)`: conversion succeeds.
- If page must start at 1, `@Min(1)` rejects it.
- `""` → null with number converter.
- If page is required, `@NotNull` rejects null.
- `"abc"` → conversion error; validation typically does not receive a valid Integer to check.

Illustrative JSON controller:

```java
@PostMapping("/paging")
public String paging(@Valid @RequestBody PagingRequest request) {
    return "page=" + request.page();
}
```

This illustrates Bean Validation on a DTO after deserialization. Jackson conversion remains a separate pipeline; `@Valid` does not turn JSON parse errors into business rules.

## 13. API Scenario Matrix

| Contract | Recommended Java type | Handling |
| --- | --- | --- |
| Required page | `Integer` | `@NotNull` + `@Min(1)` |
| Optional page, zero has distinct meaning | `Integer` | null = omitted; 0 validated separately |
| Optional boolean, false has distinct meaning | `Boolean` | null = unselected; false = disabled |
| Boolean always defaults to false | `boolean` or wrapper with explicit default | Decide default in contract/service |
| String must contain content | `String` | `@NotBlank` |
| Optional string, empty differs from missing | `String` + presence tracking | Preserve key presence/value |
| Required value object | Reference type | Converter + invariant + `@NotNull` |
| Optional value object | Reference/Optional per contract | Define whether blank is missing or an error |

## 14. Common Pitfalls

**1. Treating null and empty as identical.** Null sources go through a dedicated branch; empty Strings go through converters.

**2. Assuming every empty string becomes null.** String, Number, Boolean, Character, and UUID each have their own behavior.

**3. Using primitives for optional inputs.** Cannot preserve missing state; use wrappers.

**4. Treating 0/false as missing.** These may be values explicitly sent by the client.

**5. Expecting Converter to handle null sources.** Spring handles null in ConversionService first; converters normally receive non-null sources.

**6. Assuming null automatically becomes 0.** ConversionService cannot represent null with a primitive; MVC has a special case turning boolean to false, while numeric primitives fail.

**7. Using `required=false` with primitive int to accept null.** Use Integer.

**8. Using defaultValue when empty and missing must be distinguished.** `defaultValue` can apply to both.

**9. Putting `@NotNull` on primitives.** Primitives can never be null.

**10. Using validation to handle malformed formats.** Binding/conversion failures must be handled separately.

**11. Equating JSON with query/form parameters.** Jackson and WebDataBinder are two different pipelines.

**12. Ignoring whitespace-only inputs in tests.** `""` and `"   "` can produce different results depending on the converter.

## 15. Testing Checklist

1. Define the contract for missing, null, empty, blank, zero, and false.
2. Choose primitives vs. wrappers based on whether fields can be absent.
3. Verify the specific converter for each source/target pair.
4. For custom converters, define whether blank is rejected, normalized, or returns null.
5. In MVC, verify `required`, `defaultValue`, `@Nullable`, and primitive behavior.
6. Run Bean Validation after binding to check null, ranges, and blank.
7. Separate binding errors from business rejections.
8. Test query/form separately from JSON bodies.
9. Test both zero/false and missing/empty.
10. Test on the application's exact Spring version and ConversionService registry.

### Minimum Test Matrix

| Test | Outcome to verify |
| --- | --- |
| `convert(null, Integer.class)` | null |
| `convert("", Integer.class)` | null with default number converter |
| `convert("0", Integer.class)` | 0 |
| `convert("", Boolean.class)` | null |
| `convert("  ", Boolean.class)` | null after trim |
| `convert("false", Boolean.class)` | false |
| `convert("0", Boolean.class)` | false |
| `convert("", String.class)` | Empty String |
| `convert(null, int.class)` | Conversion failure |
| MVC optional `Integer` when parameter is empty | Wrapper receives null if conversion returns null |
| MVC optional `int` when conversion returns null | Exception because primitive cannot accept null |
| MVC optional `boolean` when conversion returns null | false per named-value resolver |
| JSON missing and explicit null | Verify separately per Jackson/DTO policy |

**Remember:** null is the absence of an object; an empty String is a String of length 0; a blank String contains characters with no text; primitives cannot hold null while wrappers can. Spring handles them based on target type, converter, and pipeline. Design clear contracts, pick the right Java types, and test all states thoroughly.

## References

- [Spring Framework 6.2 – Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html): ConversionService, null-source conversion, and Converter contract.
- [Spring Framework 6.2 – MVC Controller Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html): empty String to null after conversion and required/nullable arguments.
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html): conversion API with nullable sources.
- [GenericConversionService source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java): null-source branch.
- [StringToBooleanConverter source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/StringToBooleanConverter.java): boolean tokens, trim, and blank-to-null.
- [Spring MVC named-value argument resolver source](https://github.com/spring-projects/spring-framework/blob/main/spring-web/src/main/java/org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver.java): primitive boolean and error for other primitives when result is null.
