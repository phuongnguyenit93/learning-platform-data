# Reusable Converters for Array or Collection Elements in Spring

A **Converter<S, T>** typically describes a single-value conversion: from source type **S** to target type **T**. In Java applications, data often arrives as an array or collection. For example, a form submits multiple tag strings while the target object wants to hold **List<Tag>**; or a service receives **List<String>** and needs to produce **Set<Tag>**.

Spring provides built-in structural converters for common cases. When a **ConversionService** contains a **String → Tag** converter along with the corresponding array/collection converters, Spring can apply that value converter to each element while converting the entire array or collection. You usually only need to write a converter for the element type, rather than writing separate converters for every pair like **String[] → List<Tag>**, **List<String> → Set<Tag>**, or **String[] → Tag[]**.

The critical requirement is that Spring must know the **element type** of both source and target. Property generic information or **TypeDescriptor** supplies that context. This article explains the mechanism, registration, usage with **ConversionService**, **DataBinder** integration, failure cases, and a standalone runnable Java 17 example.

## 1. Idea: Convert Elements, Then Convert Structure

Suppose the application has a target type:

~~~java
public record Tag(String value) {}
~~~

and a converter:

~~~java
public final class StringToTagConverter implements Converter<String, Tag> {
    @Override
    public Tag convert(String source) {
        return new Tag(source.trim().toLowerCase(Locale.ROOT));
    }
}
~~~

These are two illustrative snippets; the complete runnable example in section 5 provides all classes and imports. The converter only understands **String → Tag**. It does not need to know whether an element lives inside an array, List, or Set.

If the input is:

~~~text
[" Java ", "SPRING", "data-binding"]
~~~

and the target is **List<Tag>**, the logical flow is:

~~~text
String[]  [" Java ", "SPRING", "data-binding"]
    |
    v
Array-to-Collection converter
    |
    +-- StringToTagConverter: " Java " -> Tag("java")
    +-- StringToTagConverter: "SPRING" -> Tag("spring")
    +-- StringToTagConverter: "data-binding" -> Tag("data-binding")
    |
    v
List<Tag>
~~~

This is converter composition: one converter handles the outer structure, and the value converter handles each element. Spring's structural converter is responsible for creating the target container and iterating through elements; the application converter only normalizes a single string into a Tag.

| Source type | Target type | Structural converter | Value converter invoked |
| --- | --- | --- | --- |
| **String[]** | **List<Tag>** | Array-to-Collection | **String → Tag** for each string |
| **List<String>** | **Set<Tag>** | Collection-to-Collection | **String → Tag** for each element |
| **String[]** | **Tag[]** | Array-to-Array | **String → Tag** for each element |
| **List<Tag>** | **Tag[]** | Collection-to-Array | No element conversion needed |
| **Tag[]** | **List<Tag>** | Array-to-Collection | No element conversion needed |

These cases require the corresponding container converter to be registered and element types to be determinable. Spring provides standard converters for arrays/collections/maps in default ConversionServices; for minimal registries or special type pairs, verify the actual conversion path.

## 2. Structural Converters Provided by Spring

**DefaultConversionService** pre-registers common converters, including scalar converters and converters for arrays, collections, and maps. Important structural converters include:

- **ArrayToArrayConverter**: converts one array to another; can convert each element if element types differ.
- **ArrayToCollectionConverter**: converts a source array into a target collection, using the target element type to convert each item.
- **CollectionToArrayConverter**: converts a source collection into a target array.
- **CollectionToCollectionConverter**: converts a source collection into a target collection; can change both container type and element type.
- **MapToMapConverter**: converts a map to another map; can convert keys and values based on their respective descriptors.
- Other scalar/container converters handle matching pairs, such as object to collection or collection to object array.

Do not depend on internal implementation class names when you only need the API. What matters is that **ConversionService** locates a structural conversion path; each element can then pass through its own value converter. If an element converter is missing, the entire container conversion can fail even when the structural converter exists.

**You do not have to write a GenericConverter just because data is a collection.** For basic element transformations, a strongly typed **Converter<S, T>** is usually simpler and safer. Only consider **GenericConverter** when logic genuinely depends on multiple type pairs, generic metadata, annotations, or field/property context.

## 3. TypeDescriptor: How Spring Knows Generic Element Types

Java generics undergo **type erasure** at runtime: from a plain ArrayList instance alone, you cannot always tell whether it is **List<String>**, **List<Tag>**, or **List<Order>**. To convert parameterized collections accurately, Spring needs additional metadata.

**org.springframework.core.convert.TypeDescriptor** describes a type and the context in which it appears (field, method parameter, collection element, map key/value, etc.). Through it, **ConversionService** knows what the target collection's element type is.

Example describing **List<Tag>**:

~~~java
TypeDescriptor target = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Tag.class));
~~~

Describing source type **String[]**:

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String[].class);
~~~

Once both descriptors are ready, use the TypeDescriptor conversion overload:

~~~java
Object result = conversionService.convert(
        sourceValue, sourceTypeDescriptor, targetTypeDescriptor);
~~~

With the array-to-List example:

~~~java
List<Tag> tags = (List<Tag>) conversionService.convert(
        sourceArray,
        TypeDescriptor.valueOf(String[].class),
        TypeDescriptor.collection(List.class, TypeDescriptor.valueOf(Tag.class)));
~~~

This method has return type **Object**, so the example casts to **List<Tag>**. The application must ensure the target descriptor matches the actual cast type.

### Three Ways to Obtain a TypeDescriptor

**Construct explicitly** when types are known:

~~~java
TypeDescriptor tagsType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Tag.class));
~~~

**Obtain from a Java field with a generic declaration:**

~~~java
TypeDescriptor tagsField =
        new TypeDescriptor(RegistrationForm.class.getDeclaredField("tags"));
~~~

**Obtain from a method parameter or property** when describing that declared context. Preserve generic metadata from Field/MethodParameter instead of passing raw List.class.

Note: **TypeDescriptor.forObject(list)** cannot recover erased **List<String>** generics when runtime only reveals an ArrayList object. For collections with parameterized element types, obtain the descriptor from a field declaration or build it with **TypeDescriptor.collection(...)**.

### canConvert Does Not Guarantee Every Element Converts Successfully

When converting arrays/collections/maps, **canConvert(sourceType, targetType)** can return true because Spring finds a matching structural converter. Yet a specific element can still fail when **convert(...)** runs. For example, the registry knows the **String[] → List<Tag>** path, while the **String → Tag** converter rejects `"bad value"`. Always wrap the actual conversion in proper error handling for ConversionException/ConversionFailedException, and never treat canConvert alone as validation of all data.

## 4. Registering the Element Converter and Scope of Reuse

A converter can be registered in the registry as follows:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTagConverter());
~~~

**DefaultConversionService** already registers default converters for common types and arrays/collections. Adding **String → Tag** allows standard structural converters to reuse it.

A Spring application can manage ConversionService as a shared bean or use **FormattingConversionService** in web applications. Register the converter in the exact registry used by the actual processing path. Instantiating **new DefaultConversionService()** inside a test does not automatically put the converter into MVC, another binder, or Jackson.

Converters should be **stateless**, storing no request data in fields. ConversionService is designed to be shared after startup configuration; finish registration before serving concurrent requests. Avoid mutating the registry while other threads are converting data.

**When is a dedicated container converter needed?** Only when structural conversion diverges from standard rules—for instance, combining multiple elements into a single value, splitting one scalar by a custom delimiter, handling custom domain containers, preserving special metadata, or applying field-specific rules. In ordinary cases, adding a scalar converter and letting Spring handle container conversion requires less code and is easier to test.

## 5. Complete Java 17 Example: Reusing a Converter for Arrays and Collections

The following program uses **Spring Framework 6.2.10**, JDK 17+, and Maven; no Spring Boot or web server is needed. It registers only **StringToTagConverter**, then converts:

1. **String[] → List<Tag>**.
2. **List<String> → Set<Tag>**.
3. **String[] → Tag[]**.

Inputs are normalized to lowercase and trimmed; for instance, **" java "** becomes **Tag("java")**.

Project structure:

~~~text
converter-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConverterContainerDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-container-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ConverterContainerDemo.java**:

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterContainerDemo {

    public static void main(String[] args) {
        // Register converter for a single value: String -> Tag.
        DefaultConversionService conversionService =
                new DefaultConversionService();
        conversionService.addConverter(new StringToTagConverter());

        // Case 1: String[] -> List<Tag>.
        String[] rawArray = {" Java ", "SPRING", "data-binding"};
        TypeDescriptor stringArray = TypeDescriptor.valueOf(String[].class);
        TypeDescriptor tagList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Tag.class));

        @SuppressWarnings("unchecked")
        List<Tag> tags = (List<Tag>) conversionService.convert(
                rawArray, stringArray, tagList);

        // Case 2: List<String> -> Set<Tag>.
        List<String> rawList = List.of(" MVC ", "JAVA", " spring ");
        TypeDescriptor stringList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class));
        TypeDescriptor tagSet = TypeDescriptor.collection(
                Set.class, TypeDescriptor.valueOf(Tag.class));

        @SuppressWarnings("unchecked")
        Set<Tag> tagSetResult = (Set<Tag>) conversionService.convert(
                rawList, stringList, tagSet);

        // Case 3: String[] -> Tag[].
        Tag[] tagArray = (Tag[]) conversionService.convert(
                new String[] {" HTTP ", "SPRING"},
                TypeDescriptor.valueOf(String[].class),
                TypeDescriptor.valueOf(Tag[].class));

        System.out.println("list = " + values(tags));
        System.out.println("set = " + values(tagSetResult));
        System.out.println("array = "
                + Arrays.stream(tagArray)
                        .map(Tag::value)
                        .collect(Collectors.joining(", ")));
        System.out.println("converterRegistered = "
                + conversionService.canConvert(String.class, Tag.class));
    }

    public record Tag(String value) {
    }

    public static final class StringToTagConverter
            implements Converter<String, Tag> {

        @Override
        public Tag convert(String source) {
            if (source == null) {
                return null;
            }

            String normalized = source.trim().toLowerCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Tag must not be blank");
            }
            if (!normalized.matches("[a-z0-9-]+")) {
                throw new IllegalArgumentException(
                        "Tag contains unsupported characters: " + source);
            }
            return new Tag(normalized);
        }
    }

    private static String values(Iterable<Tag> tags) {
        StringBuilder result = new StringBuilder("[");
        boolean first = true;

        for (Tag tag : tags) {
            if (!first) {
                result.append(", ");
            }
            result.append(tag.value());
            first = false;
        }
        return result.append("]").toString();
    }
}
~~~

From the directory containing **pom.xml**, with JDK 17+ and Maven, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterContainerDemo
~~~

**Lines printed by the program itself**:

~~~text
list = [java, spring, data-binding]
set = [mvc, java, spring]
array = http, spring
converterRegistered = true
~~~

The target Set is created by the default collection conversion mechanism, preserving element order from the source data in the example. The program does not rely on arbitrary HashSet iteration order.

Analysis:

- The converter is registered only once for **String → Tag**. There is no **StringArrayToTagListConverter** or **StringListToTagSetConverter** class.
- When converting **String[] → List<Tag>**, Spring finds the array-to-collection converter, reads the target element descriptor Tag, and applies the String → Tag converter to each element.
- When converting **List<String> → Set<Tag>**, the collection-to-collection converter runs the same process with Set as the target container.
- When converting **String[] → Tag[]**, the array-to-array converter reuses the element converter for the target array.
- **canConvert(String.class, Tag.class)** confirms the scalar converter is registered; it does not substitute for actually calling convert on data.

If one input element is changed to **"java spring"**, the converter throws **IllegalArgumentException**; ConversionService surfaces the corresponding conversion error (typically **ConversionFailedException** during execution). An entire container conversion can fail because of a single invalid element; do not ignore the exception and proceed with an incomplete collection.

## 6. Converting Generic Collections Directly: Do Not Forget TypeDescriptor

A common mistake is passing only **List.class** as the target type:

~~~java
conversionService.convert(input, List.class);
~~~

This only describes the raw List type, without saying whether elements should be Tag, String, or another type. When converting parameterized collections, supply both **TypeDescriptor**s:

~~~java
List<Tag> result = (List<Tag>) conversionService.convert(
        input,
        TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class)),
        TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Tag.class)));
~~~

This illustrative snippet assumes **input** is actually **List<String>** and **String → Tag** is registered. The descriptor pair tells Spring the source type is List<String> and the target type is List<Tag>. If source generics do not match runtime data, errors can still occur; descriptors do not coerce mismatched data on the application's behalf.

### Converting Nested Collections

The mechanism can apply to nested containers if the required structural converters and type descriptors are supported, e.g., **List<List<Tag>>**. When the source is **String[][]** or **List<List<String>>**, Spring must know the outer container and inner element type. Raw **List.class** loses the necessary metadata. Obtain descriptors from declared generic fields or build nested descriptors and test on the exact source/target type pair.

Do not assume every custom container type or arbitrary nested generic automatically converts. Standard Collection interfaces are supported by Spring; specialized containers may require additional converters or a specific implementation.

## 7. Using an Element Converter in DataBinder

In property binding, a JavaBean can declare:

~~~java
public class SearchForm {
    private List<Tag> tags;

    public List<Tag> getTags() {
        return tags;
    }

    public void setTags(List<Tag> tags) {
        this.tags = tags;
    }
}
~~~

This is an illustrative JavaBean for use with **DataBinder**. When the source contains multiple form parameters and the target property is **List<Tag>**, Spring can extract the element type from the property's generic declaration via BeanWrapper/TypeDescriptor.

Illustrative configuration snippet:

~~~java
SearchForm form = new SearchForm();

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTagConverter());

DataBinder binder = new DataBinder(form, "searchForm");
binder.setConversionService(service);
binder.setAllowedFields("tags");
binder.bind(new MutablePropertyValues(Map.of(
        "tags", new String[] {" java ", "spring"})));

BindingResult result = binder.getBindingResult();
if (!result.hasErrors()) {
    System.out.println(form.getTags());
}
~~~

This snippet uses **SearchForm** and **StringToTagConverter** from earlier, requiring imports for **DataBinder**, **MutablePropertyValues**, **BindingResult**, and **Map**. In web environments, multi-valued request parameters are typically represented as String[]; in manual code, we construct that array explicitly.

**setAllowedFields("tags")** restricts which properties clients are allowed to bind. The element converter only converts types—it does not check whether the sender is authorized to pick a tag or whether the tag exists in the database.

In Spring MVC, custom element converters can be registered via **WebMvcConfigurer.addFormatters(...)** so MVC's FormattingConversionService uses them. MVC's binder then uses the converter per framework configuration. Avoid creating a new service inside every controller when the intent is shared converter configuration; also distinguish the **@ModelAttribute** path from **@RequestBody** JSON bodies, since Jackson deserializes JSON via its own mechanism.

## 8. When to Use ConverterFactory or GenericConverter?

**Converter<S, T>** fits a clear single source/target pair, such as **String → Tag**. When reused for collections/arrays, structural converters invoke it for each element.

**ConverterFactory<S, R>** fits when one source type converts into a family of target types sharing a common base, e.g., **String** to multiple enum types. Register the factory once and Spring selects the concrete converter per target type.

**GenericConverter** is useful when supporting multiple type pairs or logic depending on **TypeDescriptor**. Examples:

- Conversions that inspect annotations on fields/properties.
- Conversions requiring generic metadata or nested types.
- General converters handling map keys and values under different descriptors.
- Conversion rules that vary by source/target context.

Do not write a GenericConverter to replace standard ArrayToCollectionConverter or CollectionToCollectionConverter merely because the input is a container. Spring already includes structural converters. GenericConverter should be reserved for cases genuinely needing metadata or multiple type pairs, as its API is less type-safe than Converter<S,T>.

A GenericConverter/ConditionalGenericConverter can inspect target annotations or metadata to decide whether to apply. If logic depends on an annotation on the container field, test whether that context is available on the element descriptor the way you expect; do not assume container annotations propagate automatically to every element.

## 9. Common Pitfalls and Limitations

**Registering only a scalar converter while using an empty ConversionService.** A String → Tag converter does not automatically create structural converters for arrays/collections. Use DefaultConversionService/DefaultFormattingConversionService or explicitly register the appropriate default converters.

**Failing to provide generic element types.** List.class does not say what the elements are. Use TypeDescriptor.collection(...) or obtain the descriptor from a field/method declaration.

**canConvert returns true yet convert still fails.** For containers, Spring may know a structural converter exists while an individual item fails to convert. Surround convert with proper error handling and report per-element messages when needed.

**Converter mishandling blanks under the contract.** Null elements may be handled according to ConversionService's null semantics; empty/whitespace strings are actual values, and the converter must decide whether to normalize or reject them. Never turn blanks into valid Tags unless business rules permit it.

**Converter depending on database or user state.** A converter may be shared across requests/threads; querying the database or checking permissions inside convert makes type parsing unpredictable and expensive. Keep converters pure; verify existence, status, and permissions in the service/domain layer after conversion.

**Silently dropping failing elements.** If one element is malformed, do not silently filter it out and return a partial collection. Define an explicit all-or-nothing policy or build index-level error collection in a dedicated layer.

**Registering duplicate or conflicting converters.** Multiple converters for the same type pair make selection confusing or registry-dependent. Register clear rules and test the exact type pairs.

**Confusing ArrayToCollection with scalar-to-list conversion.** Supporting **String[] → List<Tag>** does not mean **String → List<Tag>** is also supported. If input is a single string that needs splitting by a delimiter, define the syntax explicitly and write an appropriate converter.

**Using @RequestBody to test property binding.** JSON converters/deserializers read bodies through a separate mechanism. Use DataBinder or @ModelAttribute forms when verifying array/collection element conversion via property binding.

## 10. Testing and Choosing an Approach

| Test case | Source → target type | What to verify |
| --- | --- | --- |
| Single value | **String → Tag** | Converter trims, normalizes, and creates Tag properly |
| Array → List | **String[] → List<Tag>** | Each element converts cleanly, preserving order |
| List → Set | **List<String> → Set<Tag>** | Element converter is reused, target container is right |
| Array → array | **String[] → Tag[]** | Target element type is applied |
| Invalid value in middle | **String[] → List<Tag>** with one bad item | The convert call fails instead of pretending full success |
| Wrong TypeDescriptor | Raw descriptor or mismatched element | Prevents lost generic metadata |
| DataBinder | List<Tag> form receiving String[] | BindingResult and target are correct |
| Multi-thread | Multiple requests sharing service | Stateless converter, no state leakage |
| MVC registration | Converter registered via addFormatters | Form endpoint uses the right registry |
| Separate JSON | @RequestBody with collection | Verify deserialization path separately |

In unit tests, verify **size**, **order**, **element values**, and exceptions when an invalid element is present. For Set, add duplicate tests to confirm container semantics; Set deduplicates elements based on the element type's equals/hashCode. For Map, test key and value descriptors separately since failures on either side can fail the entire conversion.

### Choosing a Solution

- **Only changing element types with standard container rules:** write a Converter<S,T>, register it in DefaultConversionService, and let Spring handle arrays/collections.
- **Converting parameterized collections in direct code:** provide TypeDescriptors for source and target to preserve generic metadata.
- **Needing locale-dependent parse/print:** consider Formatter<T>.
- **Needing a family of target types from one source:** consider ConverterFactory.
- **Needing metadata/annotations or multiple type pairs:** consider GenericConverter/ConditionalGenericConverter.
- **Needing content, database, or permission validation:** perform it in a Validator/service/domain layer without putting side effects into the element converter.

The key principle to remember is **separating element conversion from structural conversion**. A value converter performs one small, strongly typed job; ConversionService and TypeDescriptor collaborate to reuse that logic over every element of an array/collection whenever a standard conversion path exists.

## Official Documentation

- [Spring Framework — Type Conversion: Converter, ConversionService, and array/collection reuse](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework 6.2.10 API — ConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2.10 API — TypeDescriptor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2.10 API — DefaultConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
