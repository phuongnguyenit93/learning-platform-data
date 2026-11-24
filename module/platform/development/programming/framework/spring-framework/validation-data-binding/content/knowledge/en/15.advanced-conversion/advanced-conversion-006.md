# Converting Arrays, Collections, and Maps with Spring ConversionService

## 1. Why Does Container Conversion Need Metadata?

Spring `ConversionService` does not only convert single scalar values like `String → Integer`. It can also convert container-shaped data:

- Array to Collection: `String[] → List<Integer>`.
- Collection to Array: `List<String> → Integer[]`.
- Collection to Collection: `List<String> → Set<Long>`.
- Map to Map: `Map<String, String> → Map<Integer, Boolean>`.
- Delimited string to Collection, or Collection to string, when a suitable converter is registered.

Container conversion involves two layers of work:

1. Converting the **outer structure**: array, list, set, or map.
2. Converting **each element**: array/collection elements; map keys and values.

For example, `String[] → List<Integer>` requires knowing the target is a `List` whose elements are `Integer`. Spring can instantiate a suitable target collection and use `ConversionService` to convert each string into `Integer`. Similarly, when converting a `Map`, Spring can convert keys and values independently based on generic metadata.

The key point is that Java reflection at runtime usually reveals only `List.class` if we use `Class<?>`; it is not enough to distinguish `List<String>` from `List<Integer>`. Spring uses **`TypeDescriptor`** to carry generic element types, map key/value types, and annotations from the declaration site.

## 2. Container Types and Conversion Directions

| Source | Target | What Spring Needs to Do |
| --- | --- | --- |
| `String[]` | `List<Integer>` | Create collection, convert each String to Integer |
| `List<String>` | `Integer[]` | Create target array, convert each element to Integer |
| `List<String>` | `Set<Long>` | Create Set, convert each element to Long; Set deduplicates per equals/hashCode rules |
| `Set<String>` | `List<UUID>` | Create List and convert each String to UUID |
| `Map<String,String>` | `Map<Integer,Boolean>` | Convert each String key to Integer and each String value to Boolean |
| `String` | `List<Integer>` | Can use string → collection converter; splitting and element conversion depend on registered converters |
| `List<Integer>` | `String` | Requires corresponding collection → string converter and formatting rules |

Container conversions are not type casts. `(List<Integer>) someList` only casts at compile/runtime; it does not parse each string into a number. `ConversionService` actually constructs the target structure and converts the elements.

### Spring's Foundational Converters

`DefaultConversionService` registers many built-in converters for common container pairs, including array-to-collection, collection-to-array, collection-to-collection, and map-to-map, alongside converters for common element types. These converters leverage `ConversionService` to convert nested elements.

Do not assume every container pair is supported in every scenario. Support depends on:
- The source/target type pair.
- Whether generic metadata is available.
- Converters for the element, map key, and map value types.
- Registered custom converters.
- Ability to instantiate the target collection/map type.

## 3. Class and TypeDescriptor: The Decisive Difference

### Using Class When the Target Type Has No Generics to Distinguish

Simple overload:

```java
List<?> values = conversionService.convert(
    new String[]{"10", "20"}, List.class
);
```

Here the target is `List.class`. Spring knows it needs a `List`, but lacks sufficient generic information to enforce that elements must be `Integer`. Do not cast the result to `List<Integer>` based merely on a cast: generic types are erased at runtime and the element data may not have the type you expect.

### Using TypeDescriptor to Specify Element Types

`TypeDescriptor` describes a type together with metadata at its declaration site. A descriptor can be obtained from a field:

```java
Field field = Form.class.getDeclaredField("numbers");
TypeDescriptor targetDescriptor =
    new TypeDescriptor(new Property(field));
```

If the field is declared `List<Integer> numbers`, the descriptor retains the `Integer` generic information. Spring can use that metadata to locate a converter for each element.

Several helpful factory methods:

```java
TypeDescriptor.valueOf(String[].class);
TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(Integer.class)
);
TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(Integer.class),
    TypeDescriptor.valueOf(Boolean.class)
);
```

This approach is convenient when generic types are known explicitly in code. For annotations or complex nested generics, obtaining the descriptor from a field, getter, constructor parameter, or method parameter preserves fuller actual metadata.

### convert Overload Using TypeDescriptor

```java
Object result = conversionService.convert(
    source,
    sourceDescriptor,
    targetDescriptor
);
```

Spring looks up converters by **source and target descriptors**. For containers, the target descriptor provides the element type or key/value types. As the underlying converter iterates over elements, it can ask `ConversionService` to convert each element using the corresponding descriptors.

If no special metadata is needed, calling `convert(source, Target.class)` is sufficient. When working with generic collections/maps, proactively use `TypeDescriptor` rather than expecting `Class` to carry generic information on its own.

## 4. Arrays and Collections: Converting Element by Element

### Array → Collection

Example:

```java
String[] source = {"10", "20", "30"};
List<Integer> target = ...;
```

The process can be pictured as:

1. Spring recognizes `source` as an array and `target` as a `Collection`.
2. Determines the target element type from the descriptor, e.g., `Integer`.
3. Instantiates a collection matching the target type (e.g., `ArrayList` for `List`).
4. Iterates through the source elements.
5. Invokes conversion for each element from `String` to `Integer`.
6. Returns the collection containing the converted elements.

The collection size equals the number of source elements if all convert successfully. If one element fails, the entire conversion can fail; do not assume Spring returns a partial collection.

### Collection → Array

For example, `List<String> → Integer[]` requires:

1. Reading the element descriptor of the source collection when available.
2. Determining the target array's component type as `Integer`.
3. Allocating an array of the exact length.
4. Converting each element and placing it at the corresponding index.

Arrays have a fixed component type. If one element cannot be converted, the conversion fails; Java cannot produce a "mixed-type" array.

### Collection → Collection

For example, `List<String> → Set<Long>`:

- Creates the target collection based on the target type.
- Converts each element to `Long`.
- Adds each element to the target collection.

If the target is a `Set`, duplicate elements may be collapsed per the element type's equality rules; order is guaranteed only by specific implementations (`LinkedHashSet` preserves insertion order, `HashSet` makes no ordering guarantee). For `List`, elements retain source iteration order when handled by appropriate collection converters.

Do not rely on collection conversion to enforce business ordering or uniqueness if the target type does not guarantee those properties.

## 5. Map → Map: Converting Keys and Values Independently

Suppose:

```java
Map<String, String> source = Map.of(
    "1", "true",
    "2", "false"
);
```

The desired target is `Map<Integer, Boolean>`. There are two conversion streams:

- Key: `String → Integer`.
- Value: `String → Boolean`.

Spring needs both generic arguments on the target descriptor. Therefore, for `Map` as well, do not pass only `Map.class` if you want keys/values converted to different types.

General flow:

```text
Map<String, String>
       |
       v
Map-to-Map converter
       |
       +--> convert each key:   String -> Integer
       |
       +--> convert each value: String -> Boolean
       |
       v
Map<Integer, Boolean>
```

Failure scenarios:

- Key `"x"` cannot be parsed into `Integer`.
- Value `"perhaps"` cannot be converted into `Boolean` by the active converter.
- Two distinct source keys may convert into the same target key; the target map keeps only one entry per `Map.put` semantics.
- The target `Map` type cannot be instantiated or is incompatible with the structure supported by the converter.

**Do not assume key collisions will automatically raise an error.** If you need to detect when two distinct keys convert into the same target key, perform a dedicated check in business logic or write a custom converter. Likewise, Map conversion does not validate that a key exists in the system.

## 6. String to Collection: Delimiters and Splitting

Spring has built-in converters for certain string-to-array/collection cases. For example, data like:

```text
10,20,30
```

can be converted into a collection of numbers with a matching converter, via string splitting and element conversion.

However, do not assume every string is split by commas in every custom converter. Verify which converter is registered, the delimiter format, whitespace handling, empty elements, and commas inside quoted values.

If the input format belongs to a specific protocol, define an explicit converter. For example, CSV with quoting/escaping is genuinely more complex than `String.split(",")`; do not write a naive CSV splitter and ship it to production.

### Custom String Converter Example

```java
public final class CsvToIntegerList
        implements Converter<String, List<Integer>> {

    @Override
    public List<Integer> convert(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }
        return Arrays.stream(source.split(","))
            .map(String::trim)
            .map(Integer::valueOf)
            .toList();
    }
}
```

This is an illustrative snippet requiring imports for `Arrays` and `List`. It defines a very simple rule: split on commas, trim, and parse `Integer`. `Integer.valueOf` can throw `NumberFormatException`; when run through `ConversionService`, the error is typically wrapped as `ConversionFailedException`. Use this approach only if the input format truly lacks complex quoting/escaping.

## 7. Runnable Java 17 Example: Array, Collection, and Map

The following program uses Spring Framework 6.1.14 and `DefaultConversionService`. It converts three structures using `TypeDescriptor`s read from generic fields, demonstrating that elements, keys, and values are all converted to their target types.

Structure:

```text
container-conversion-demo/
├── pom.xml
└── src/main/java/demo/ContainerConversionDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>container-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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

File `src/main/java/demo/ContainerConversionDemo.java`:

```java
package demo;

import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.Property;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ContainerConversionDemo {

    public static final class Targets {
        private List<Integer> numbers;
        private Set<Long> uniqueNumbers;
        private Map<Integer, Boolean> flags;

        public List<Integer> getNumbers() {
            return numbers;
        }

        public Set<Long> getUniqueNumbers() {
            return uniqueNumbers;
        }

        public Map<Integer, Boolean> getFlags() {
            return flags;
        }
    }

    private static TypeDescriptor fieldType(String name)
            throws NoSuchFieldException {
        Field field = Targets.class.getDeclaredField(name);
        return new TypeDescriptor(new Property(field));
    }

    public static void main(String[] args) throws Exception {
        ConversionService service =
            new DefaultConversionService();

        String[] rawNumbers = {"10", "20", "30"};
        List<Integer> numbers = (List<Integer>) service.convert(
            rawNumbers,
            TypeDescriptor.valueOf(String[].class),
            fieldType("numbers")
        );

        List<String> rawUnique = List.of("2", "2", "5");
        Set<Long> unique = (Set<Long>) service.convert(
            rawUnique,
            TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class)
            ),
            fieldType("uniqueNumbers")
        );

        Map<String, String> rawFlags = Map.of(
            "1", "true",
            "2", "false"
        );
        Map<Integer, Boolean> flags =
            (Map<Integer, Boolean>) service.convert(
                rawFlags,
                TypeDescriptor.map(
                    Map.class,
                    TypeDescriptor.valueOf(String.class),
                    TypeDescriptor.valueOf(String.class)
                ),
                fieldType("flags")
            );

        System.out.println("arrayToList=" + numbers);
        System.out.println("listToSet=" + unique);
        System.out.println("mapToMap=" + flags);
    }
}
```

Run from the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContainerConversionDemo
```

Lines printed by the program:

```text
arrayToList=[10, 20, 30]
listToSet=[2, 5]
mapToMap={1=true, 2=false}
```

Explanation:

1. `String[]` is converted to `List<Integer>`. The target descriptor comes from the `numbers` field so Spring knows the element type is `Integer`; each string is parsed.
2. `List<String>` becomes `Set<Long>`. The target descriptor of `uniqueNumbers` contains `Long`; the two `"2"` strings become the same `Long` value 2 and the `Set` keeps a single element.
3. `Map<String,String>` converts to `Map<Integer,Boolean>`. The source descriptor has `String` keys/values; the target field descriptor has `Integer` keys and `Boolean` values. Spring converts both sides.
4. Map order in the output may depend on the instantiated implementation. With the default converter and this example it is normally an insertion-order-preserving Map; do not treat ordering as a general guarantee if the target type does not stipulate it.
5. The example shows generic metadata coming from fields; if only `Map.class` or `List.class` were used, element conversion to the target types might not be determined as intended.

Note: the code casts the result from the `TypeDescriptor` overload to a generic container to assign to Java variables. This is a controlled cast aligned with the passed target descriptor; it is not a substitute for generic metadata. In real applications, if you cannot guarantee the descriptor is accurate, validate/handle the result type instead of casting blindly.

## 8. Error When Converting One Element in a Container

A container can have many valid elements and just one invalid element:

```java
String[] input = {"10", "20", "not-a-number"};
```

When converting to `List<Integer>`, the third element cannot be parsed. The entire conversion can fail and `ConversionService` throws `ConversionException`; a typical container converter does not return a half-succeeded collection while silently dropping the failing element.

You can catch the error at the conversion boundary:

```java
try {
    List<Integer> result =
        service.convert(input, targetType);
} catch (ConversionException ex) {
    // Handle unconvertible input.
}
```

This snippet illustrates error handling; `targetType` and `service` must be declared appropriately. When you need to report the exact index of the failing element, an exception from a nested converter may not include the index in the format your public API expects. In that case, write controlled per-element parsing logic or a custom converter to enrich index details such as `items[2]`.

### Do Not Silently Drop Invalid Elements

A design like:

```java
for (String value : source) {
    try {
        result.add(Integer.valueOf(value));
    } catch (NumberFormatException ignored) {
        // ignore
    }
}
```

can turn invalid data into missing data without the caller's knowledge. Use a skip policy only if business rules explicitly allow it and the output indicates how many elements were dropped; otherwise, fail the conversion to avoid processing incomplete data.

### Size and Resource Limits

Client-submitted collection/map inputs can be very large. `ConversionService` performs work on the elements supplied; do not rely on the conversion layer to enforce resource limits. The request-receiving layer should bound:
- Body/query parameter size.
- Number of elements.
- Length of each string.
- Nesting depth and collection indices.
- Number of Map entries.

Otherwise, converting a huge array into a collection can consume significant CPU/memory.

## 9. Default Converters vs. Custom Container Converters

Before writing a custom converter, try `DefaultConversionService` with the proper source/target descriptors. Built-in converters already handle many cases of element conversion, container construction, and generic metadata.

When custom logic is needed:

### Convert Each Element via ConversionService

A custom container converter should not hand-parse every type with `if/else`. It can accept a `ConversionService` or use an appropriate delegation mechanism to convert each element. Ensure the converter does not create an infinite loop calling itself for the same descriptor.

### GenericConverter

`GenericConverter` fits when target type pairs have varying generics and require access to `TypeDescriptor`. For instance, an array-to-specialized-collection converter needs the target element descriptor to convert each item.

### ConditionalGenericConverter

Use when converter selection depends on annotations or container/element metadata. For example, map a `String[]` into an enum collection only when the target field carries a custom annotation. Matching conditions must be specific enough not to hijack normal conversion paths.

### Do Not Override Default Converters Carelessly

Registering a custom converter for a broad type pair such as `Object → Collection` can affect many conversion paths. Use specific source/target pairs and test interactions with default converters.

## 10. Integration with DataBinder and Spring MVC

`DataBinder` and `WebDataBinder` use `ConversionService` to convert property/form data into Java types. For example, if a form has a `List<Integer> itemIds` field, the binder may need to convert request source values into a collection of `Integer` elements when the data structure and resolver/binding path align.

In Spring MVC, converters can be registered in the MVC configuration:

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToItemCodeConverter());
    }
}
```

This illustrative snippet requires an appropriate `StringToItemCodeConverter` implementation and the Spring MVC dependency. MVC can then use it during binding/conversion at supported points.

Be careful to distinguish:
- `@ModelAttribute` uses `DataBinder`/`WebDataBinder` and property/constructor binding depending on context.
- `@RequestBody` JSON is normally read via an `HttpMessageConverter` (e.g., Jackson), not necessarily through the same `DataBinder` `ConversionService` path.
- Jackson has its own collection/map deserialization mechanism. Do not assume a custom Spring `Converter` automatically alters how Jackson reads every JSON array/object.
- Once the container is constructed, validation can inspect individual elements or relationships among elements using Bean Validation or a Spring `Validator`, depending on configuration.

## 11. Null, Empty, and Duplicate Elements

These three states have different meanings:

| State | Meaning |
| --- | --- |
| Null container | No container present; conversion depends on converter/null semantics and whether the target is nullable |
| Empty container | Valid container with 0 elements |
| Container with null element | Element slot exists without a value supplied; element converters may handle it differently |

Do not collapse null into empty if business rules distinguish "not provided" from "provided an empty list". For `Map`, null keys and null values also depend on the target `Map` type and converters.

Duplicate elements:
- `List` preserves duplicate elements.
- `Set` eliminates duplicates based on `equals/hashCode`.
- `Map` cannot hold multiple entries with the same key after key conversion; a later `put` can overwrite a prior value depending on the implementation.
- If duplicates must be detected before entries collapse, perform an explicit check or use a converter that tracks collisions.

## 12. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `List<String>` created, but elements are not Integer | Only `List.class` passed, missing generic target descriptor | Obtain `TypeDescriptor` from field/parameter or build a collection descriptor with element type |
| `canConvert` true, yet one element fails | Container pair supported, but a concrete value is invalid | Catch `ConversionException`, inspect cause and offending element |
| `Map` converts keys, yet values remain String | Target descriptor lacks key/value types or lost generics | Use a concrete Map descriptor and test both sides |
| `Set` loses duplicate elements | This is Set semantics | Choose List if duplicates must be kept, or validate duplicates before conversion |
| Target Map entries overwritten | Two source keys convert to the same target key | Detect collisions before/after conversion per business rules |
| Cannot instantiate target Collection | Target type/interface/implementation unsupported or non-instantiable | Choose an appropriate concrete target type or write a custom converter |
| CSV string splits incorrectly | Wrong delimiter/escaping assumptions | Define an explicit format and parser |
| Custom converter does not run | Registered in the wrong ConversionService | Check which registry MVC/DataBinder actually uses |
| JSON array ignores expected Spring Converter | Body deserialized by Jackson | Configure a Jackson module/deserializer or handle at the HTTP converter |
| Container input too large | No resource limits at request-receiving layer | Enforce size, element count, and depth limits before conversion |

## 13. Container Conversion Debugging Workflow

1. Write down the exact **source descriptor** and **target descriptor**, including element type or map key/value types.
2. Confirm a suitable container converter exists in the registry.
3. Verify element converters: `String → Integer`, `String → UUID`, `String → Boolean`...
4. Test with a small container where all elements are valid.
5. Test data with exactly one invalid element to confirm the exception propagates.
6. Test duplicates, null, empty, map key collisions, and nested paths if relevant to business rules.
7. If the error occurs only in MVC, verify whether data flows through `@ModelAttribute`, request parameters, or a JSON deserializer.
8. Check input size limits to prevent CPU/memory issues with large containers.

## 14. Self-Check Questions

1. Why does `String[] → List<Integer>` need target element metadata?
2. What information does `TypeDescriptor` provide that `List.class` lacks?
3. In `Map<String,String> → Map<Integer,Boolean>`, how many element conversion directions must Spring perform?
4. Why can `canConvert` return `true` while `convert` still fails on one invalid element?
5. What is the difference in outcome when the target is `List` versus `Set`?
6. If two source keys convert into the same target key, what can happen and how should it be detected?
7. Why should you not silently skip elements that fail parsing?
8. When should you write a `GenericConverter` instead of a `Converter<S,T>`?
9. Does a `@RequestBody` JSON array necessarily pass through Spring `DataBinder` `ConversionService`?
10. What should be bounded when accepting large collections/maps from external callers?

**Key takeaway:** Spring converts containers by combining an outer structural converter with converters for individual elements. For Collections, the element type is needed; for Maps, both key type and value type are needed. Use `TypeDescriptor` to retain generic metadata rather than relying on `List.class`/`Map.class` when the target has specific element types. `canConvert` only checks capability by descriptor; element data can still cause `convert` to fail.

## References

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework 6.1.14 — ConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.1.14 — GenericConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
- Spring Framework 6.1.14 — DefaultConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
