# ConditionalGenericConverter: When Two Mechanisms Need to Be Combined in Spring

In Spring Core, some converters need two capabilities at once: **describing multiple source/target type pairs and receiving full type metadata**, while **applying only when a condition on the type or property is satisfied**. The **ConditionalGenericConverter** interface solves this by combining **GenericConverter** with **ConditionalConverter**.

- **GenericConverter** declares which type pairs can be converted and receives source/target **TypeDescriptor**s when executing.
- **ConditionalConverter** adds the **matches(sourceType, targetType)** method to decide whether the converter applies to a specific descriptor pair.
- **ConditionalGenericConverter** extends both: Spring knows which class pairs the converter handles and also checks metadata-based conditions before selecting it.

For example, an application has a **Code** type, but only wants to normalize strings into slugs when the target property carries the **@Slugged** annotation. Both fields have Java type **Code**, yet the converter applies only to the annotated field. This is why combining type-pair description with conditional selection is needed.

## 1. When Do Both Mechanisms Need to Be Combined?

A regular **Converter<S, T>** expresses a single explicit type pair, such as **String → Code**. This is a good choice when one rule applies uniformly to every property of that type pair.

However, in large systems, the same type pair can carry different semantics:

- One `Code` field needs the string converted into a lowercase slug.
- Another `Code` field must preserve the code issued by an external system.
- A collection property needs handling based on its generic element type or element metadata.
- A type pair should convert only when the descriptor has a certain annotation or context.

Looking only at **String.class → Code.class** may not be enough to pick the right logic. **TypeDescriptor** describes additional context; **matches(...)** checks whether the converter applies in that context.

| Interface | Describes Type Pairs | Receives TypeDescriptor on convert | matches Condition |
| --- | --- | --- | --- |
| **Converter<S,T>** | One explicit generic pair | Not in the regular convert signature | No |
| **GenericConverter** | A set of ConvertiblePair | Yes, source/target TypeDescriptor | Not required |
| **ConditionalConverter** | Does not define convert or type pairs itself | matches receives both descriptors | Yes |
| **ConditionalGenericConverter** | A set of ConvertiblePair | Yes, via GenericConverter | Yes, via ConditionalConverter |

The two smaller interfaces have distinct responsibilities. The combined interface is useful only when a converter genuinely needs both.

## 2. API Contracts of the Three Interfaces

These interfaces reside in the **org.springframework.core.convert.converter** package.

### GenericConverter

Condensed contract:

~~~java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

**getConvertibleTypes()** declares the set of type pairs the converter can handle. Each **ConvertiblePair** consists of a source class and a target class. **convert(...)** receives the actual value along with detailed descriptors to perform conversion.

### ConditionalConverter

Condition contract:

~~~java
public interface ConditionalConverter {
    boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

**matches(...)** returns `true` if the converter applies to the descriptor pair under consideration; `false` otherwise.

### ConditionalGenericConverter

The combined interface is essentially declared as:

~~~java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
~~~

It adds no new mandatory methods beyond those inherited. Implementing classes must provide **getConvertibleTypes()**, **convert(...)**, and **matches(...)**.

Two questions should be distinguished:

1. **getConvertibleTypes()** answers: which class pairs can this converter handle?
2. **matches(...)** answers: for this specific `TypeDescriptor` pair right now, should the converter apply?

Do not try to encode all metadata conditions into class pair declarations. Conversely, do not use `matches` merely to repeat what the type pair already defines.

## 3. TypeDescriptor Makes Conditions Meaningful

**TypeDescriptor** provides richer information than **Class<?>**:

- The object type after handling primitives/wrappers.
- Annotations attached to a field or method parameter.
- Component type of an array.
- Element type of a collection.
- Key/value types of a map.
- Generic metadata obtained from property or parameter declarations.

A `ConvertiblePair(String.class, Code.class)` only describes class types. If two properties both have type `Code`, this pair cannot distinguish which property has `@Slugged`.

When Spring passes the target descriptor to **matches(...)**, the converter can check:

~~~java
boolean slugged = targetType.hasAnnotation(Slugged.class);
~~~

This snippet is valid when `Slugged` is a runtime annotation attached to the element described by the descriptor.

In manual code, build a descriptor from a field via reflection:

~~~java
TypeDescriptor targetDescriptor =
        new TypeDescriptor(ArticleForm.class.getDeclaredField("slugCode"));
~~~

As a result, the same `Code` class can have different conversion policies per property.

### Generic Element Metadata

For a field:

~~~java
private List<Code> codes;
~~~

A `TypeDescriptor` created from the field preserves the generic element type `Code`. During collection conversion, Spring uses the element descriptor when evaluating converters for each item. If the condition depends on the generic type, you can inspect **sourceType.getElementTypeDescriptor()** or **targetType.getElementTypeDescriptor()** when present.

The element descriptor may be null if the declared type does not supply enough metadata or is not a collection. Always check for null before reading the element type. For maps, there are APIs describing key/value; for arrays, there is a corresponding component type descriptor.

**TypeDescriptor.valueOf(Code.class)** only describes the `Code` class and carries no annotations from a specific field. If the condition depends on a property annotation, obtain the descriptor from the field/property context.

## 4. How Does Spring Select a Converter?

A `ConversionService` such as **GenericConversionService** or **DefaultConversionService** manages registered converters. When **canConvert(...)** or **convert(...)** is called, the registry looks up a conversion path by source/target types and converter conditions.

~~~text
canConvert(sourceType, targetType) or convert(...)
                |
                v
Find converters with compatible ConvertiblePair
                |
                v
If conditional converter:
matches(sourceDescriptor, targetDescriptor)?
          | true                  | false
          v                       v
Keep as candidate            Skip this candidate
          |
          v
Select matching converter by registry/specificity
          |
          v
convert(source, sourceDescriptor, targetDescriptor)
~~~

This is a conceptual model, not a guarantee of a fixed `matches` invocation order across all implementations. The registry may cache converter lookup results; what converter authors must ensure is that **matches(...) has no side effects and produces stable results for a given descriptor**.

Note:

1. `matches` may be evaluated when checking convertibility, not only when `convert` runs. It must be fast and pure.
2. `canConvert` returning `true` only indicates Spring found a converter for the current metadata; specific data values may still be rejected inside `convert`.
3. `matches` returning `false` excludes this converter from the current context; another converter may still handle it if the registry has an alternative path.
4. If multiple converters match, selection also depends on type pairs and the registry. Avoid overlapping conditions that produce different outcomes.
5. Do not assume a custom converter will always win over built-in converters. Test with the exact property descriptor.

## 5. Complete Java 17 Example: Convert Code Only When Field Has @Slugged

This example uses **Spring Framework 6.2.10**, JDK 17+, and Maven; no Spring Boot or web server is required. A `ConditionalGenericConverter` handles `String → Code`, applying only if the target field has the **@Slugged** annotation.

Two fields both have type `Code`:

- **slugCode** carries `@Slugged`, so the string is trimmed, lowercased, and spaces are replaced with hyphens.
- **externalCode** lacks the annotation, so this converter declines to participate.

Structure:

~~~text
conditional-generic-converter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConditionalGenericConverterDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conditional-generic-converter-demo</artifactId>
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

**src/main/java/demo/ConditionalGenericConverterDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConditionalGenericConverterDemo {

    public static void main(String[] args) throws NoSuchFieldException {
        DefaultConversionService service = new DefaultConversionService();
        service.addConverter(new SlugCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor slugTarget =
                new TypeDescriptor(ArticleForm.class.getDeclaredField("slugCode"));
        TypeDescriptor plainTarget =
                new TypeDescriptor(ArticleForm.class.getDeclaredField("externalCode"));

        System.out.println("sluggedCanConvert = "
                + service.canConvert(source, slugTarget));
        System.out.println("plainCanConvert = "
                + service.canConvert(source, plainTarget));

        Code converted = (Code) service.convert(
                "  Spring Conversion Rules  ", source, slugTarget);

        System.out.println("converted = " + converted.value());
        System.out.println("targetHasSlugged = "
                + slugTarget.hasAnnotation(Slugged.class));
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface Slugged {
    }

    public record Code(String value) {
    }

    public static final class ArticleForm {
        @Slugged
        private Code slugCode;

        private Code externalCode;

        public Code getSlugCode() {
            return slugCode;
        }

        public void setSlugCode(Code slugCode) {
            this.slugCode = slugCode;
        }

        public Code getExternalCode() {
            return externalCode;
        }

        public void setExternalCode(Code externalCode) {
            this.externalCode = externalCode;
        }
    }

    public static final class SlugCodeConverter
            implements ConditionalGenericConverter {

        @Override
        public Set<GenericConverter.ConvertiblePair> getConvertibleTypes() {
            return Set.of(new GenericConverter.ConvertiblePair(
                    String.class, Code.class));
        }

        @Override
        public boolean matches(
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            return sourceType.getObjectType() == String.class
                    && targetType.getObjectType() == Code.class
                    && targetType.hasAnnotation(Slugged.class);
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            String normalized = source.toString()
                    .trim()
                    .toLowerCase(Locale.ROOT)
                    .replaceAll("\\s+", "-");

            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Slug must not be blank");
            }

            return new Code(normalized);
        }
    }
}
~~~

In the directory containing `pom.xml`, run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConditionalGenericConverterDemo
~~~

**Program stdout**:

~~~text
sluggedCanConvert = true
plainCanConvert = false
converted = spring-conversion-rules
targetHasSlugged = true
~~~

Explanation:

- **getConvertibleTypes()** declares the `String → Code` pair. This is the class-level scope the converter can handle.
- **matches(...)** checks the source type, target type, and `@Slugged` annotation on the target descriptor. Matching classes without the annotation on the target are rejected.
- **convert(...)** normalizes the concrete value after the registry selects the converter.
- **DefaultConversionService.addConverter(...)** accepts `GenericConverter`; because the class is also a `ConditionalGenericConverter`, the registry can check the condition.
- The `TypeDescriptor` is created from a real field so it retains runtime annotations. Using only **TypeDescriptor.valueOf(Code.class)** loses field metadata and causes `matches` to return `false`.
- **canConvert(...)** runs prior to conversion; for the plain field, this converter does not match and no fallback converter exists for `String → Code`, so the result is `false`.

The example focuses on selecting a converter by field metadata; it does not set up a `DataBinder` or HTTP request. The next section shows how to apply the same principle to property binding.

## 6. Integration with DataBinder and Spring MVC

In real applications, annotation metadata usually sits on DTO properties. When `DataBinder` processes properties, Spring can provide the corresponding `TypeDescriptor` to the converter. If the converter inspects annotations, ensure the annotation is placed where the target descriptor represents it.

Manual `DataBinder` example:

~~~java
ArticleForm form = new ArticleForm();

DefaultConversionService conversions = new DefaultConversionService();
conversions.addConverter(new SlugCodeConverter());

DataBinder binder = new DataBinder(form, "articleForm");
binder.setConversionService(conversions);
binder.setAllowedFields("slugCode");
binder.bind(new MutablePropertyValues(Map.of(
        "slugCode", " Spring Conversion Rules "
)));

BindingResult result = binder.getBindingResult();
if (!result.hasErrors()) {
    System.out.println(form.getSlugCode().value());
}
~~~

This is an illustrative snippet using the classes from the example above; it requires importing `DataBinder`, `MutablePropertyValues`, `BindingResult`, and `Map`. The `slugCode` property must be a writable JavaBean property. The annotation is placed on the field so `TypeDescriptor` reflects it. If the annotation is placed on a getter/setter or record component, verify where Spring introspection reads metadata from.

In Spring MVC, converters can be registered via **WebMvcConfigurer.addFormatters(...)**:

~~~java
@Configuration
class ConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new ConditionalGenericConverterDemo.SlugCodeConverter());
    }
}
~~~

This is an illustrative snippet for an MVC application; it requires the `spring-webmvc` dependency, `@Configuration`, `FormatterRegistry`, and `WebMvcConfigurer`. Registering in MVC's registry makes the converter available to MVC-scoped binders; do not create a separate `ConversionService` per controller.

Important boundaries:

- **@ModelAttribute form:** `DataBinder` performs property binding and uses `ConversionService`/`TypeDescriptor` for type conversion.
- **@RequestBody JSON:** Jackson typically deserializes the body. Do not assume custom Spring `ConversionService` converters run automatically for JSON fields; if needed, configure an appropriate Jackson deserializer/module.
- **@Valid:** Bean Validation is a separate mechanism; converters do not replace validation.
- Do not query databases, check permissions, or write data inside `matches`/`convert`.
- Shared converters can execute concurrently; keep implementations stateless and thread-safe.

## 7. Combining Conditions with Generic Element Metadata

Some applications need to convert **List<String> → List<Code>**, but only when the target element descriptor has matching metadata. When Spring converts a collection, a structural converter handles the outer container; the element converter is evaluated against each item's `TypeDescriptor`.

~~~text
List<String>
    |
    v
CollectionToCollectionConverter
    |
    +-- String[0] -> Code
    +-- String[1] -> Code
    +-- String[2] -> Code
    |
    v
List<Code>
~~~

A `ConditionalGenericConverter` can declare `ConvertiblePair(String.class, Code.class)` and use `matches(sourceElementDescriptor, targetElementDescriptor)` to inspect element context. However, a condition based on an annotation on the **container field** versus an annotation on the **element type** are two different contexts. Do not assume an annotation placed on a `List<Code>` field always appears on the descriptor of each element.

If the logic lives on the container field's annotation, an element converter may not see it directly through the element descriptor. A clearer option is placing the annotation on the element type or writing a custom container-level converter that can read full field metadata. Choose based on annotation placement and rule complexity.

When a condition needs to reference the element type, use the corresponding descriptor API:

~~~java
TypeDescriptor element = targetType.getElementTypeDescriptor();
if (element == null) {
    return false;
}
return element.getObjectType() == Code.class;
~~~

This illustrative snippet belongs inside an appropriate `matches(...)`; add element annotation checks if that is the intended semantics. You must handle null descriptors because not every source/target is a collection.

## 8. Designing matches(...) Properly

**matches(...) decides whether the converter is selected.** Keep this method small, deterministic, and based solely on the passed source/target metadata.

Do:

- Check that source/target object types are compatible with the declared type pairs.
- Check annotations with **hasAnnotation(...)** or metadata on `TypeDescriptor`.
- Check collection element/key/value descriptors only when certain the descriptor is non-null.
- Return `false` when metadata is missing or does not satisfy the condition, unless the contract defines an explicit fallback.
- Keep results stable: the same descriptor pair must not depend on time, session, or database state.

Don't:

- Query a database to decide whether the converter applies.
- Mutate source/target objects inside `matches`.
- Log sensitive data or perform heavy side effects.
- Use `matches` to report specific data validation errors. Conditions only select converters; value errors belong in `convert` or the validation layer.
- Write a condition that always returns `true` just to implement the interface; when no condition is needed, use a simpler `GenericConverter` or `Converter<S,T>`.

### convert(...) Must Still Validate Values

`matches` does not replace input validation. The converter must still handle:

- Null handling according to the target type and `ConversionService` contract.
- Blank/whitespace according to data rules.
- Invalid characters, lengths, and formats.
- Clear exceptions if the source cannot be converted into the target value.

For example, `matches` accepts a field annotated with `@Slugged`, yet the source is `"###"`; the converter must still reject it if slug syntax forbids those characters. Conditions choose which converter participates; `convert` decides whether a concrete value can be converted.

## 9. Registration, Overlapping Converters, and Caching

A `ConversionService` can register many converters, both conditional and unconditional. When multiple converters declare compatible type pairs, the registry must pick a matching converter. A narrow condition can exclude one converter from a context, but does not guarantee it always beats another converter sharing the same pair.

Design principles:

1. Avoid registering multiple converters with the same `ConvertiblePair` and overlapping conditions if their outputs differ.
2. Write specific and easily testable `matches` logic.
3. Account for Spring's default converters; do not assume custom converters replace every built-in converter.
4. Use **canConvert(sourceDescriptor, targetDescriptor)** in tests to verify metadata picks the right path.
5. Call **convert(...)** directly to verify the converter runs properly and errors are reported appropriately.
6. Complete registration at application startup, before the `ConversionService` is shared.

If no converter matches, `canConvert` may return `false` or `convert` raises a conversion error. If multiple conversion paths exist, Spring has a lookup algorithm and may cache results by descriptor pair. Therefore, never vary `matches` results based on mutable state outside the descriptors.

## 10. Misconceptions and Common Mistakes

**Confusing ConditionalGenericConverter with ConditionalConverter.** `ConditionalConverter` only provides `matches`; it does not define `getConvertibleTypes` and `convert` itself. `ConditionalGenericConverter` extends both `GenericConverter` and `ConditionalConverter`.

**Confusing ConvertiblePair with TypeDescriptor.** A pair is a class tuple used to advertise converter scope; a descriptor carries additional annotation and generic element metadata.

**Using target class to inspect field annotations.** `TypeDescriptor.valueOf(Code.class)` carries no annotations from a specific field. Obtain the descriptor from the field/property context if the condition depends on field metadata.

**Making matches depend on request data or database state.** This makes converter selection unpredictable and it may be invoked repeatedly. Conditions should rely strictly on metadata.

**Using convert to decide whether a converter applies.** Use `matches` for selection; `convert` for value conversion.

**Not handling null element descriptors.** Sources/targets that are not collections or are raw generics may lack element descriptors. Return `false` or handle intentionally instead of throwing `NullPointerException`.

**Placing annotations in the wrong spot.** An annotation on a container field does not equate to an annotation on the element type. Decide whether the condition applies to the container or elements and test the received descriptor.

**canConvert is true yet convert still fails.** This is normal when the specific source value violates syntax. `canConvert` checks conversion paths by metadata, not the contents of every value.

**Ignoring built-in converters or duplicate pairs.** Multiple converters may compete; test the exact descriptor pair and avoid relying arbitrarily on registration order.

**Using converters for business checks.** Normalizing a slug does not prove the slug is unused, the user is authorized to create it, or the entity exists. Those checks belong in service/domain/database layers.

## 11. Testing and Choosing the Right Interface

| Test Case | Source Descriptor | Target Descriptor | Expected Result |
| --- | --- | --- | --- |
| Annotated field | String | Code field with @Slugged | matches true, canConvert true |
| Unannotated field | String | Code field without annotation | matches false, canConvert false if no other converter |
| Valid metadata, valid input | String with whitespace | @Slugged Code | Converts into normalized slug |
| Valid metadata, empty input | Empty String | @Slugged Code | convert throws error per contract |
| Wrong source type | Integer | @Slugged Code | Does not match ConvertiblePair |
| Different annotation | String | Code field with another annotation | matches false |
| Descriptor missing metadata | String | Code without annotation | Condition returns false cleanly |
| Competing converters | Same source/target pair | Different context descriptors | Registry selects expected path |
| DataBinder | Property Code with @Slugged | String property input | BindingResult and target are accurate |
| MVC form | @ModelAttribute with annotated field | Form parameter | Converter in MVC registry is used |

Use unit tests for `matches(...)` with constructed `TypeDescriptor`s and test `ConversionService` for both `canConvert` and `convert`. Use `MockMvc` separately to verify registration and actual metadata from property binding; do not conclude from direct `ConversionService` tests that MVC/Jackson necessarily use the same registry.

### Choosing an Interface

| Need | Recommended Choice |
| --- | --- |
| One simple type pair, always applies | **Converter<S,T>** |
| Multiple type pairs needing TypeDescriptor during convert | **GenericConverter** |
| Only need an applicability condition on a converter | **ConditionalConverter** combined with an appropriate converter |
| Multiple type pairs and descriptor-based condition | **ConditionalGenericConverter** |
| One source type to a family of target types sharing a base type | **ConverterFactory<S,R>** |
| Locale-dependent parsing/printing | **Formatter<T>** |

Do not pick a more complex interface just because you can. Use **ConditionalGenericConverter** when you genuinely need both the multi-pair/`TypeDescriptor` capabilities of `GenericConverter` and the selection condition of `ConditionalConverter`.

## Official References

- [Spring Framework — ConditionalGenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework — ConditionalConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [Spring Framework — TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework — GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework — Type Conversion reference](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
