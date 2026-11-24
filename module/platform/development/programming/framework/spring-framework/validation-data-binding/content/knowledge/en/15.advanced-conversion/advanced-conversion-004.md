# ConditionalConverter and the matches Condition in Spring Framework

## 1. Concept

Spring may have multiple converters supporting the same source–target type pair, while only one converter fits a specific field or member. For example, two fields both have target type `ReferenceCode` and accept `String`; one field carries an annotation specifying a reference code rule, while the other does not. Looking only at `Class`, the registry cannot distinguish that metadata.

`org.springframework.core.convert.converter.ConditionalConverter` adds the method:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}
```

`matches` returns `true` if the converter under consideration applies to the two `TypeDescriptor`s; it returns `false` if the converter should be skipped. This method **only selects the converter**; it does not parse or convert the source value. Conversion logic belongs in `convert(...)` of `Converter`, `GenericConverter`, or a converter supplied by `ConverterFactory`.

## 2. Where Does TypeDescriptor Matter?

`TypeDescriptor` carries richer information than `Class<?>`. It can carry:
- Source/target Java types.
- Generic element, key, or value types.
- Annotations on a field or method.
- Information about the member from which the descriptor was created.
- Array, collection, map, and nested type context.

Two fields of the same type `ReferenceCode` can have different annotations. `Class` only says they share the same type; `TypeDescriptor` lets `matches` inspect markers such as `@ReferenceFormat`.

```java
TypeDescriptor source = TypeDescriptor.valueOf(String.class);
TypeDescriptor target =
        TypeDescriptor.field(Invoice.class.getField("referenceCode"));
boolean marked = target.hasAnnotation(ReferenceFormat.class);
```

This is a reflection snippet; `Invoice` and `ReferenceFormat` are defined in the example. The annotation requires `RetentionPolicy.RUNTIME` to be readable at runtime.

## 3. Related SPIs

| SPI | Contract | Capabilities |
| --- | --- | --- |
| Converter<S,T> | T convert(S source) | Single type pair; may also implement ConditionalConverter |
| GenericConverter | ConvertiblePair + convert with TypeDescriptor | Multiple type pairs and metadata |
| ConverterFactory<S,R> | One source to a family of target subtypes of R | Multiple targets sharing a common base type |
| ConditionalGenericConverter | GenericConverter + ConditionalConverter | Declares pairs and matches together |

`ConditionalGenericConverter` is a combined interface:

```java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

Implementations must provide `getConvertibleTypes()`, `matches(...)`, and `convert(...)`. The registry first matches by `ConvertiblePair`; then `matches` narrows selection by descriptor. If `matches=false`, Spring can look for another converter for the same type pair.

## 4. Java 17 / Spring 6.2.6 Example

This example converts `String` to `ReferenceCode` only when the target field carries the `@ReferenceFormat` annotation. Both `Invoice.referenceCode` and `Customer.legacyCode` have the same Java type, yet only the first field carries the annotation.

Project structure:

```text
conditional-converter-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ReferenceFormat.java
    ├── ReferenceCode.java
    ├── Invoice.java
    ├── Customer.java
    ├── StringToReferenceCode.java
    └── ConditionalConverterDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conditional-converter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConditionalConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**ReferenceFormat.java**

```java
package demo;
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface ReferenceFormat { }
```

**ReferenceCode.java**

```java
package demo;
public record ReferenceCode(String value) {
    public ReferenceCode {
        if (value == null || !value.matches("REF-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid reference code");
        }
    }
    @Override public String toString() { return value; }
}
```

**Invoice.java**

```java
package demo;
public class Invoice {
    @ReferenceFormat
    public ReferenceCode referenceCode;
}
```

**Customer.java**

```java
package demo;
public class Customer {
    public ReferenceCode legacyCode;
}
```

**StringToReferenceCode.java**

```java
package demo;

import java.util.Set;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

public final class StringToReferenceCode
        implements ConditionalGenericConverter {
    private static final ConvertiblePair PAIR =
            new ConvertiblePair(String.class, ReferenceCode.class);

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(PAIR);
    }

    @Override
    public boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType) {
        return targetType.hasAnnotation(ReferenceFormat.class);
    }

    @Override
    public Object convert(Object source, TypeDescriptor sourceType,
                          TypeDescriptor targetType) {
        if (source == null) return null;
        String normalized = source.toString().trim().toUpperCase();
        return new ReferenceCode(normalized);
    }
}
```

**ConditionalConverterDemo.java**

```java
package demo;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.GenericConversionService;

public final class ConditionalConverterDemo {
    public static void main(String[] args) throws Exception {
        GenericConversionService service = new GenericConversionService();
        service.addConverter(new StringToReferenceCode());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor invoiceTarget = TypeDescriptor.field(
                Invoice.class.getField("referenceCode"));
        TypeDescriptor customerTarget = TypeDescriptor.field(
                Customer.class.getField("legacyCode"));

        System.out.println("invoice.matches=" +
                service.canConvert(source, invoiceTarget));
        System.out.println("customer.matches=" +
                service.canConvert(source, customerTarget));

        ReferenceCode code = (ReferenceCode) service.convert(
                " ref-0042 ", source, invoiceTarget);
        System.out.println("invoice.code=" + code);
    }
}
```

Run in the project directory:

```bash
mvn -q clean compile exec:java
```

Stdout:

```text
invoice.matches=true
customer.matches=false
invoice.code=REF-0042
```

Both fields share the same pair `String → ReferenceCode`, so both are type-level candidates. `matches` selects only the `Invoice` field because its descriptor carries the annotation. `Customer` lacks the annotation, so the converter is skipped. The actual `convert` call runs only on the `Invoice` descriptor.

`canConvert(TypeDescriptor, TypeDescriptor)` checks whether a converter matches by metadata; it does not test every source value. If you pass `BAD-CODE`, `matches` is still `true`, yet `convert`/the `ReferenceCode` constructor will reject the content.

## 5. How Does matches Differ from convert?

| matches | convert |
| --- | --- |
| Receives sourceType and targetType | Receives source value along with both descriptors |
| Decides converter selection | Produces target value |
| Checks annotation/generic/member metadata | Parses, normalizes, and validates content |
| Returns boolean | Returns target object or throws an error |

Do not parse strings or validate input regex inside `matches` because it does not receive the source value. If data is malformed, handle it in `convert` or appropriate validation. When a converter is invoked via `ConversionService`, `IllegalArgumentException` is typically wrapped in `ConversionFailedException`.

## 6. What Data Can Conditions Rely On?

- **Target annotation:** run only when the target field/method carries a marker.
- **Source annotation:** run only for marked source fields.
- **Generic type:** distinguish `List<String>` from `List<ReferenceCode>`.
- **Class/method characteristics:** run only if the target class has a matching factory/finder method.
- **Type pair:** `getConvertibleTypes` declares preliminary pairs; `matches` checks concrete metadata.

Spring documentation gives an example of a `String → Account` converter selected only when the target `Account` defines a public static finder method such as `findAccount(String)`. `matches` checks for the presence/suitability of the method; actually creating `Account` belongs in `convert` or a dedicated service.

## 7. Multiple Converters for the Same Type Pair

A registry can hold multiple converters with the same `ConvertiblePair`. A converter with `matches=false` may be skipped to try another converter. Therefore:

- Design conditions so they do not overlap unintentionally.
- Do not rely on registration order instead of explicit conditions.
- Test general and specialized converters coexisting together.
- If no converter matches, there is no suitable conversion path.
- If a converter matches yet the value is invalid, that is a conversion error, not a matching error.

`matches` can be invoked many times and across many requests. Keep it pure, fast, deterministic, with no DB queries, network calls, sensitive logging, or state mutation.

## 8. When to Use ConditionalConverter?

| Need | Choice |
| --- | --- |
| One type pair, one fixed rule | Converter<S,T> |
| Converter runs only when target has an annotation | Converter + ConditionalConverter |
| Multiple pairs or needing descriptors in convert | GenericConverter |
| Both declaring pairs and making them conditional | ConditionalGenericConverter |
| One source to a family of target subtypes | ConverterFactory |
| Locale-aware parsing/printing | Formatter<T> |

Use a plain `Converter` if metadata does not affect selection. Add conditional logic only when the same type pair genuinely requires different rules based on annotations, generics, or member context.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Parsing input inside matches | Wrong responsibility, no source value available | Parse inside convert |
| Checking only Class when condition depends on annotation | Selects converter for the wrong field | Inspect TypeDescriptor |
| Forgetting ConvertiblePair | Registry sees no candidate pair | Declare the proper source/target |
| Thinking matches=true means value is valid | convert can still fail | Validate values inside convert |
| Annotation lacking RUNTIME retention | Unreadable at runtime | RetentionPolicy.RUNTIME |
| Side effects in matches | Slow and unpredictable lookups | Keep conditions pure |
| Overlapping conditions | Unpredictable converter selection | Design mutually exclusive conditions, test registry |
| Using generic SPIs too early | Unnecessary complexity | Prefer Converter when sufficient |
| Using matches for authorization | Bypasses real authorization | Enforce permissions in service/domain |

## 10. Testing

Unit tests should construct `TypeDescriptor`s from fields with and without the annotation, then assert `matches` is true/false. Integration tests should register the converter into `GenericConversionService`, call `canConvert(sourceDescriptor, targetDescriptor)`, and then call `convert` with valid and invalid values.

Scenarios to test:
1. Field with annotation.
2. Field without annotation.
3. Annotation placed on a method/parameter.
4. Source descriptor with different annotations or generics.
5. Generic target with matching/non-matching element type.
6. `matches=false` when another converter exists.
7. `matches=true` with invalid data.
8. Repeated calls and multithreading to confirm no state/side effects.

Do not test `matches` in isolation and conclude the registry is configured correctly; test through `ConversionService`.

## 11. Spring MVC and Data Binding

Spring MVC uses `ConversionService` when binding query parameters, path variables, and form/model attributes. When the field/method `TypeDescriptor` carries an annotation, `ConditionalConverter` can select the corresponding rule. Write integration tests with a real binder to confirm the descriptor provided by MVC actually carries the expected metadata.

Do not conflate `@ModelAttribute` with `@RequestBody` JSON. JSON typically goes through an `HttpMessageConverter` such as Jackson and has its own deserialization mechanism; MVC converters do not automatically replace full Jackson mapping.

Three responsibilities to separate:
- `matches` selects the converter based on metadata.
- `convert` transforms the concrete value.
- `Validator` checks data constraints.
- Service/domain enforces permissions, state, and business invariants.

## 12. Self-Check

**1.** What does `matches` receive?  
Source and target `TypeDescriptor`s.

**2.** Does `matches` returning `true` parse the string?  
No; it only confirms the converter matches the metadata.

**3.** Why is `Class` not enough?  
Two fields of the same type can have different annotations/generics/member metadata.

**4.** Which interfaces does `ConditionalGenericConverter` combine?  
`GenericConverter` and `ConditionalConverter`.

**5.** Does `matches=false` mean every conversion is impossible?  
No; the registry can find another converter.

**6.** If a converter matches yet the value is invalid, where does the error occur?  
In `convert` or the constructor/value object.

**7.** Why should `matches` be stateless?  
Lookups can run repeatedly from multiple threads; conditions must be stable and free of side effects.

## 13. Design Checklist

1. Identify the exact source/target pair.
2. Choose the metadata driving the condition: annotation, generic, field, method, or class characteristic.
3. Pick the appropriate SPI, avoiding Generic SPIs if `Converter` suffices.
4. Keep `matches` fast, deterministic, without value parsing or side effects.
5. Let `convert` validate contents and build the target type.
6. Test true/false and integration via `GenericConversionService`.
7. Check competing converters for the same pair.
8. Verify the actual `TypeDescriptor` provided by the binder.
9. Do not use `matches` as authorization or validation.
10. Keep it simple if no metadata condition is required.

**Key takeaway:** `ConditionalConverter` adds a selection condition via `matches(TypeDescriptor, TypeDescriptor)`. The condition is based on source/target metadata; conversion logic lives in `convert`. `ConditionalGenericConverter` combines source/target pair declaration with fine-grained conditions, fitting cases where the same type pair needs different rules depending on annotations, generics, or field/type characteristics.

## 14. Official References

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): GenericConverter, ConditionalGenericConverter, and matching metadata.
- [ConditionalConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html): matches(TypeDescriptor, TypeDescriptor).
- [ConditionalGenericConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html): combining GenericConverter and ConditionalConverter.
- [GenericConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html): ConvertiblePair and convert.
- [TypeDescriptor Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): type, annotation, and generic metadata.
- [GenericConversionService Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html): registration, lookup, and dispatch.
