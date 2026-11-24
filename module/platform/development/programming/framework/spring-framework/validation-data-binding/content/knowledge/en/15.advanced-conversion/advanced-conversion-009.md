# Priority Between Specific and General Converters in Spring

When Spring has multiple converters capable of handling a conversion, `ConversionService` must select one suitable converter. For example, an application might register at the same time:

- A specific converter from `String` to `CustomerCode`.
- A general `GenericConverter` from `String` to `Object`, capable of producing several different code types based on the target type.

When converting `"C-42"` to `CustomerCode`, the specific converter should be evaluated before the general `String -> Object` pair. Yet this must not be oversimplified into a rule that “`Converter` always beats `GenericConverter`”. **Spring selects based on type pairs and type hierarchy traversal order; if multiple converters register the same pair, conditions and registration order can also affect selection.**

This lesson explains the selection mechanism in `GenericConversionService`, distinguishes type-pair specificity from SPI kind, clarifies `ConditionalConverter`/`ConditionalGenericConverter`, illustrates specific and general cases with a runnable Java 17+ program, and presents design practices to avoid accidental configuration-dependent outcomes.

## 1. First Understand What “Specific” and “General” Mean

Two different concepts are often conflated:

**Type-pair specificity** refers to the registered source and target types.

~~~java
Converter<String, CustomerCode>
~~~

is a specific pair `String -> CustomerCode`.

~~~java
GenericConverter // ConvertiblePair(String.class, Object.class)
~~~

is a broader pair `String -> Object`. It can be considered when the target is `CustomerCode`, because `CustomerCode` is a subtype of `Object`.

**SPI kind** refers to the interface being implemented:

- `Converter<S,T>`: one source/target pair specified via generics.
- `ConverterFactory<S,R>`: one source type to a family of target types sharing a bounded base type.
- `GenericConverter`: can declare multiple `ConvertiblePair` entries and receives source/target `TypeDescriptor`s.
- `ConditionalConverter`: adds a condition for selecting a converter.
- `ConditionalGenericConverter`: combines `GenericConverter`'s pair declaration with `matches(...)` conditions.

These are two independent axes. A `GenericConverter` can register the exact `String -> CustomerCode` pair and be very specific; conversely, a `Converter` can be very broad if its target type is a supertype. Priority cannot be determined simply by looking at the interface name.

| Comparison | Specific Converter | General Converter |
| --- | --- | --- |
| Example type pair | `String -> CustomerCode` | `String -> Object` |
| Scope | One explicit target type | Many target types that sit under Object |
| Metadata on convert | Receives only source value in `convert(S)` | Receives source and target `TypeDescriptor`s |
| Can coexist? | Yes | Yes |
| Deciding question | Is this type pair evaluated first? | Is the general pair still a candidate after specific pairs? |

## 2. How Does ConversionService Locate a Converter?

Common implementations such as `GenericConversionService` maintain a registry of registered converters and look them up by type pair. When a value needs conversion, the service identifies the source/target types, locates a matching converter, and executes the selected converter.

At a conceptual level:

~~~text
convert(source, targetType)
            |
            v
Create source/target TypeDescriptors
            |
            v
Check cache by source + target
            |
        cache miss
            |
            v
Traverse source type hierarchy
            |
            v
For each source type, traverse
    target type hierarchy
            |
            v
Find matching ConvertiblePair
            |
            v
Check ConditionalConverter.matches(...)
            |
      +-----+------+
      |            |
Candidate found  None yet
      |            |
Select converter  Try next pair
      |
      v
Execute convert(...)
~~~

The `GenericConversionService` source code explicitly describes searching across the **entire class/interface hierarchy** of source and target. The traversal works as follows:

1. Build the list of source types in hierarchy order.
2. Build the list of target types in hierarchy order.
3. Iterate over each source type; for each source type, iterate over target types.
4. For each pair, locate registered converters and check conditions if a converter is conditional.
5. Stop at the first matching converter; if no pair matches, use a fallback or report converter not found.

Because the source hierarchy is the outer loop, **there is no single linear rule that “exact target always beats exact source” in all cases**. For example, the pair `String -> CodeValue` can be evaluated before `Object -> CustomerCode` because Spring traverses `String` before `Object`, even though the first target is a shared interface.

### Hierarchy Order Example

Suppose:

~~~java
interface CodeValue {}
final class CustomerCode implements CodeValue {}
~~~

For a `String -> CustomerCode` request, the target type list can include `CustomerCode` first, followed by interfaces it implements, and finally supertypes such as `Object`.

Candidates can be evaluated in an order like:

~~~text
(String, CustomerCode)    // specific target pair
(String, CodeValue)       // target interface
(String, Object)          // general target
...
~~~

When both share source `String`, the `String -> CustomerCode` pair precedes `String -> Object`. This is why a converter registered for a specific target is typically chosen ahead of a converter with a broader target.

However, if the source types in the pairs also differ, source order participates in the decision. Therefore, inspect the actual type pairs declared in converters and test against the intended targets rather than guessing from “specific” or “generic” labels.

## 3. Intuitive Example: String -> CustomerCode vs. String -> Object

Suppose there are two code types:

~~~java
public interface CodeValue {
    String value();
}

public record CustomerCode(String value) implements CodeValue {}

public record OrderCode(String value) implements CodeValue {}
~~~

A specific converter:

~~~java
public final class StringToCustomerCode
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

A general converter:

~~~java
public final class StringToCodeValue
        implements GenericConverter {

    // General pair, may be considered for concrete targets under Object.
    // convert(...) must inspect target's TypeDescriptor.
}
~~~

When `String -> CustomerCode` is requested, Spring can find the direct `String -> CustomerCode` pair before `String -> Object`. The specific converter is used.

When `String -> OrderCode` is requested and there is no dedicated converter for `OrderCode`, the `String -> Object` pair can act as the general candidate. `GenericConverter` can inspect `targetType` and return the proper target object type.

This illustrates a useful design principle: **register explicit converters for pairs with dedicated rules, and use general converters only for parts that genuinely share one algorithm.**

## 4. Runnable Java 17+ Program: Specific Pair and General Pair

The following example uses Spring Framework `6.2.0` and `DefaultConversionService`. A specific `Converter<String, CustomerCode>` is registered alongside a `GenericConverter` declaring `String -> Object`.

Expected outcome:

- `CustomerCode` uses the specific converter.
- `OrderCode` uses the general converter, because there is no dedicated `String -> OrderCode` pair.
- `canConvert(...)` reports type-level capability; it does not evaluate specific values.

Directory structure:

~~~text
converter-priority-demo/
├── pom.xml
└── src/main/java/example/ConverterPriorityDemo.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>converter-priority-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.ConverterPriorityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. ConverterPriorityDemo.java

~~~java
package example;

import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterPriorityDemo {

    public interface CodeValue {
        String value();
    }

    public record CustomerCode(String value) implements CodeValue {
    }

    public record OrderCode(String value) implements CodeValue {
    }

    public static final class StringToCustomerCode
            implements Converter<String, CustomerCode> {

        @Override
        public CustomerCode convert(String source) {
            return new CustomerCode(
                    "specific:" + source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static final class StringToCodeValue
            implements GenericConverter {

        private static final Set<ConvertiblePair> PAIRS =
                Set.of(new ConvertiblePair(String.class, Object.class));

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return PAIRS;
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            String normalized = source.toString()
                    .trim().toUpperCase(Locale.ROOT);

            Class<?> target = targetType.getObjectType();

            if (target == OrderCode.class) {
                return new OrderCode("generic:" + normalized);
            }

            if (target == CustomerCode.class) {
                return new CustomerCode("generic:" + normalized);
            }

            throw new IllegalArgumentException(
                    "Unsupported code type: " + target.getName());
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        // Register general converter and specific converter.
        service.addConverter(new StringToCodeValue());
        service.addConverter(new StringToCustomerCode());

        CustomerCode customer =
                service.convert(" c-42 ", CustomerCode.class);

        OrderCode order =
                service.convert(" ord-9 ", OrderCode.class);

        System.out.println("customer=" + customer.value());
        System.out.println("order=" + order.value());
        System.out.println("canConvertCustomer="
                + service.canConvert(String.class, CustomerCode.class));
        System.out.println("canConvertOrder="
                + service.canConvert(String.class, OrderCode.class));
    }
}
~~~

### 4.3. Running the Program

With JDK 17+ and Maven, run inside the `converter-priority-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
customer=specific:C-42
order=generic:ORD-9
canConvertCustomer=true
canConvertOrder=true
~~~

Explanation:

1. `StringToCustomerCode` registers the `String -> CustomerCode` pair.
2. `StringToCodeValue` registers the broader `String -> Object` pair. When converting to `OrderCode`, the target falls under `Object` so the general converter is a candidate.
3. When converting to `CustomerCode`, lookup encounters the specific target pair before `String -> Object`; thus the value has the `specific:` prefix.
4. When converting to `OrderCode`, there is no more specific converter; `GenericConverter` inspects `targetType` and creates `OrderCode`.
5. `canConvert(...)` returns `true` for both pairs because a type-compatible converter path exists; it does not prove every string is valid or that the converter will not throw exceptions.

This is a complete program requiring no Spring Boot or web server. The output shown above is the expected output based on the written type pairs and converter logic; run Maven in your project environment when applying it.

## 5. Priority Is Not a “Converter Beats GenericConverter” Table

A common misconception is:

> Converter always has higher priority than GenericConverter.

This is not a general SPI contract. When a `Converter<S,T>` is registered, Spring adapts it into an internal converter with a defined pair; a `GenericConverter` can also register the exact same pair. In that case, the two candidates compete **on the same ConvertiblePair**, and the outcome depends on the registry's internal ordering and match conditions, not on which interface name sounds “higher level”.

Distinguish three scenarios:

| Scenario | Mechanism to Watch | Typical Outcome |
| --- | --- | --- |
| Specific pair vs. general pair, e.g. `String -> CustomerCode` and `String -> Object` | Source/target hierarchy traversal order | The specific pair can be evaluated before the general pair. |
| Two converters both register `String -> CustomerCode` | Candidate ordering for the same pair; conditional matching | The first matching candidate in the list is selected. |
| A converter whose `matches(...)` returns false | Condition of `ConditionalConverter` or `ConditionalGenericConverter` | The converter is skipped; Spring continues searching other candidates. |

### 5.1. Same Pair: Registration Order Must Be Understood Correctly

In the current `GenericConversionService` implementation, the registry for a given pair stores converters in a deque structure; when adding a converter, the implementation prepends the new converter to the front of the list. Lookup iterates over candidates in that list and selects the first matching converter.

That means if multiple converters register the same `String -> CustomerCode` pair, a later-registered converter can appear ahead of an earlier-registered converter in this implementation. If a converter is conditional, Spring must check `matches(sourceType, targetType)`; a candidate failing the condition is not selected.

**Do not build business contracts relying on accidental registration order.** Internal registry ordering is an implementation detail; bean configuration or component scanning can make initialization order hard to predict. If two converters for the same pair have conflicting logic, merge them into one converter with explicit conditions or narrow each converter's type pairs.

### 5.2. Different Pairs: Source and Target Hierarchy Order Is Key

Consider two pairs:

~~~text
Converter A: String -> CodeValue
Converter B: Object -> CustomerCode
Request:     String -> CustomerCode
~~~

You cannot look solely at the target and claim B always wins because B's target is highly specific. `GenericConversionService` traverses the **source hierarchy first**. With exact source `String`, converter A can be evaluated before lookup moves up to supertype source `Object`. Therefore, priority between pairs depends not only on the target, but on the order of both hierarchies.

That is why tests matter more than guessing from “specific” or “generic” labels.

## 6. ConditionalConverter: Metadata-Based Decisions

`ConditionalConverter` lets a converter answer for itself whether it fits the current type pair via:

~~~java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

For example, both conversions go from `String` to `LocalDate`, yet you only want a custom converter used for fields with a special annotation. The converter can inspect target metadata in `TypeDescriptor` and accept only matching cases.

A `ConditionalGenericConverter` both declares type pairs via `getConvertibleTypes()` and implements `matches(...)`. This is useful when:

- The type pair is the same, yet rules depend on field annotations.
- Data kinds or target metadata must be distinguished.
- A general converter should apply only to a specific domain group.
- A custom converter should yield to another candidate when conditions do not fit.

Illustrative example:

~~~java
public final class ConditionalStringToCode
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, CodeValue.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        // Runs only when matches(...) returns true.
        return createCode(source.toString(), targetType.getObjectType());
    }
}
~~~

This is a structural snippet, not a standalone program: `SpecialCode` and `createCode(...)` are application-defined. If a conditional converter returns `false`, the service can continue evaluating other matching converters during lookup.

**Do not use conditionals to mask unclear competition.** Conditions should express an understandable domain/metadata rule and have tests for both true and false branches.

## 7. ConverterFactory and GenericConverter in Competition

`ConverterFactory<S,R>` is also registered as an internal adapter and has a source/target-bound pair. During lookup, the factory adapter can call `getConverter(targetType)` to obtain the specific converter for the current target; if the factory or produced converter is conditional, its condition is also evaluated.

Example:

~~~java
ConverterFactory<String, CodeValue> factory = ...;
Converter<String, CustomerCode> customer =
        factory.getConverter(CustomerCode.class);
~~~

If the target is `CustomerCode`, the factory produces the matching converter. The pair registered by the factory normally represents the `CodeValue` bound type, so it can be evaluated along the target hierarchy when a concrete implementation type is requested.

`GenericConverter` can support multiple pairs and use `TypeDescriptor` directly, making it suitable when algorithms depend on metadata or multiple source/target types. However, **GenericConverter does not by default have higher or lower priority than ConverterFactory**. You must check which pair matches first, match conditions, and competing candidates for the same pair.

## 8. Generic Types: Raw Pairs Are Not the Whole Story

Two collections share the same raw class but have different element types:

~~~java
List<String>
List<Integer>
~~~

If a converter inspects only the raw `Class` `List.class`, it cannot distinguish these two parameterized types. `TypeDescriptor` provides property generic metadata so a converter can inspect element types, annotations, and other attributes.

In Spring `GenericConversionService`, converters may need to match full generic types. Adapters for `Converter`/`ConverterFactory` rely on generic signatures; `GenericConverter` can inspect `TypeDescriptor` directly. For certain unresolvable generic types, Spring has dedicated fallback logic, and behavior has been adjusted across versions.

### Note on Changes Since Spring 6.2.3

Spring 6.2.x source code includes a compatibility fallback branch for certain `ConverterAdapter` cases with unresolvable generic types, noted as a fallback to pre-6.2.3 behavior. Therefore, when your converter relies on `List<?>`, raw types, or incomplete generic types, test on the exact patch version in use.

Do not assume that two converters both registering `Collection -> Collection` can reliably distinguish elements using only raw pairs. Use `TypeDescriptor` and test explicitly with `List<String>`/`List<Integer>` when generic metadata matters.

## 9. Caching and Lookup Lifecycle

`GenericConversionService` caches lookup results keyed by source/target descriptor pairs. The goal is to avoid re-traversing the entire type hierarchy for identical conversion calls. The registry also handles cache invalidation when converters are added or removed.

In applications, you should:

- Register converters at startup or during an explicit configuration phase.
- Keep `ConversionService` stateless and shared across threads.
- Avoid mutating the registry arbitrarily while requests are running.
- Not assume component-scan registration order is always stable if multiple converters share a pair.
- Test actual outputs for a source/target pair after all configuration has loaded.

Caching does not alter lookup principles: the service still selects the converter matching source/target and metadata. It only reuses the resolved selection on subsequent calls.

## 10. Designing to Avoid Converter Conflicts

When multiple converters target the same data area, clarify ownership:

**Prefer specific pairs** for dedicated rules:

~~~java
Converter<String, CustomerCode>
Converter<String, OrderCode>
~~~

**Use general converters** when an algorithm is genuinely shared and can identify targets precisely:

~~~java
GenericConverter // String -> Object, with controlled targetType
~~~

**Use ConditionalGenericConverter** when selection also depends on annotations or metadata:

~~~java
matches(sourceType, targetType)
~~~

Practical guidelines:

1. Avoid registering two incompatible converters for the same pair.
2. If two implementations must share a pair, use explicit conditions and ensure both never return `true` for the same metadata.
3. Do not rely on bean initialization order to select domain logic.
4. Do not declare overly broad pairs such as `Object -> Object` if the converter cannot handle every target.
5. Narrow `GenericConverter` type pairs to what is actually needed; avoid catch-all wildcard pairs that force guessing targets inside a giant conditional block.
6. When multiple contexts or registries exist, verify the converter is registered in the `ConversionService` actually being used.
7. With generic collections, use `TypeDescriptor` instead of comparing only raw `Class`.
8. After upgrading Spring dependencies, re-run converter selection tests on critical source/target pairs.

## 11. Verifying Which Converter Is Selected

`ConversionService` exposes APIs such as:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
~~~

`canConvert` does not return the name of the chosen converter. It answers whether the service has a conversion path for the type pair.

To verify which specific converter is invoked:

- Produce distinguishable output markers in tests (like the `specific:` and `generic:` prefixes in the example).
- Place breakpoints inside `convert(...)` of each converter.
- For `GenericConverter`, log an identifier or target descriptor details at debug level if logs contain no sensitive data.
- Inspect registered converters via appropriate configuration/implementation APIs; do not parse `toString()` strings as a stable API.

Do not expose converter class names as part of business API responses. That is internal configuration-debugging information.

## 12. Recommended Test Suite

| Test Case | Configuration | What to Verify |
| --- | --- | --- |
| Specific pair vs. general pair | `String -> CustomerCode` and `String -> Object` | Target `CustomerCode` uses the specific converter. |
| Only general converter | `String -> Object` | Subtype target is handled properly by `GenericConverter`. |
| Unsupported target | `GenericConverter` rejects target | `ConversionService` reports no matching converter found. |
| Conditional true | `matches(...)` returns true | Conditional converter is selected when pair matches. |
| Conditional false | `matches(...)` returns false | Service evaluates another candidate or finds none. |
| Two converters on same pair | Two implementations for `String -> CustomerCode` | Test configured behavior; remove order dependency if possible. |
| Source subclass | Source extends/implements registered type | Verify source hierarchy rules. |
| Target subclass/interface | Target sits under registered class/interface | Verify target hierarchy rules. |
| Generic collections | `List<String>` and `List<Integer>` | Verify `TypeDescriptor` and generic matching. |
| Cache after configuration | Complete registration before converting | Results do not depend on nondeterministic initialization order. |

With JUnit 5, an output test can verify the chosen converter:

~~~java
@Test
void concretePairIsChosenBeforeBroadTargetPair() {
    DefaultConversionService service = createService();

    CustomerCode result =
            service.convert("c-42", CustomerCode.class);

    assertEquals("specific:C-42", result.value());
}
~~~

This is a test excerpt; `createService()` must initialize the registry as in section 4. For same-pair cases, do not simply assert that the “later-registered” converter wins and treat that as a contract. If business rules require a single behavior, register only one candidate or use non-overlapping conditional matching.

## 13. Common Mistakes

**Mistake 1 — Thinking Converter always beats GenericConverter.** SPI kind is not a priority table. You must examine `ConvertiblePair`, class hierarchies, and conditions.

**Mistake 2 — Looking only at the target type.** Lookup traverses the source hierarchy first, then target; source specificity also affects ordering.

**Mistake 3 — Registering multiple converters for the same pair and relying on XML order.** Implementations can have their own ordering rules; component scanning also makes initialization order unpredictable. Consolidate logic or use conditional criteria.

**Mistake 4 — GenericConverter declaring overly broad pairs.** A `String -> Object` converter can be evaluated for many targets. Without careful `targetType` checks, it can return the wrong object or throw on unsupported targets.

**Mistake 5 — ConditionalConverter returning true too broadly.** Insufficiently specific conditions can cause the converter to compete with other converters on the same pair. Test both true and false branches.

**Mistake 6 — Testing only canConvert.** `canConvert` does not prove which specific converter executes and does not validate input values.

**Mistake 7 — Ignoring TypeDescriptor.** For generic collections or annotations, comparing raw `Class` loses essential information.

**Mistake 8 — Mutating the registry while the application serves requests.** Caches and registries must be managed deliberately; converter registration should finish at startup.

**Mistake 9 — Assuming DefaultConversionService.addConverter replaces all default converters.** It adds a converter to the registry; selection afterward still follows lookup rules and existing converters.

## 14. Checklist When Analyzing Priority

1. Record the actual source type and target type, including generics/`TypeDescriptor` if present.
2. List every `ConvertiblePair` that could match, including pairs from converter factories.
3. Sketch the source hierarchy and target hierarchy; remember lookup traverses source candidates first, then target candidates.
4. For converters on the same pair, check `ConditionalConverter.matches(...)` and candidate ordering of the active implementation.
5. Do not use SPI kind as the sole priority criterion.
6. Write tests demonstrating which converter is chosen via observable output.
7. Verify on your application's exact Spring patch version, especially if logic depends on generic matching or fallbacks.
8. Narrow general converters and eliminate unnecessary overlapping pairs.
9. Ensure conversion errors are handled before invoking business services.
10. Only once selection rules are clear and tests are stable should the registry be used in DataBinder/MVC or application services.

### Conclusion

Spring does not have a simplistic rule that `Converter` always takes priority over `GenericConverter`. In `GenericConversionService`, selection relies on source/target pairs and type hierarchy traversal order; specific pairs are typically evaluated before general pairs when source types match. If multiple converters register the same pair, conditional matching and candidate order also participate in the decision.

For maintainable configurations, register specific pairs for specialized logic, use general converters when an algorithm is genuinely shared, and use conditional converters when metadata alters rules. Above all, test converter selection on your application's exact dependency version rather than inferring from interface names or configuration file order.

### Official References

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — GenericConversionService source code](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java)
- [Spring Framework 6.2 — GenericConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework — ConditionalConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [Spring Framework — ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
