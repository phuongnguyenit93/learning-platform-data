# TypeDescriptor with Element Types, Generics, and Annotations in Spring

## 1. Why Is TypeDescriptor Needed?

Java provides `Class<?>` to describe runtime types, but generics undergo type erasure. Thus, `List<String>` and `List<Integer>` share the same raw class `List.class`. Relying solely on source/target classes, the conversion service cannot tell which type collection elements need to be converted from or to.

Spring Core provides `org.springframework.core.convert.TypeDescriptor` to carry additional metadata for conversion: raw type, generic element/key/value types, and annotations declared on a field or method parameter. As a result, a converter can convert `List<String>` to `List<Integer>`, convert both keys and values of a map, or activate only when the target has a specific annotation.

After this lesson, you will be able to create descriptors from classes/fields/collections/maps, read nested generics, access annotation metadata, and understand when `GenericConverter` or `ConditionalGenericConverter` is needed.

## 2. Class<?> and TypeDescriptor

`Class<?>` is sufficient when rules depend only on runtime types such as `String.class` or `Integer.class`. `TypeDescriptor` extends that information.

| Need | Class<?> | TypeDescriptor |
| --- | --- | --- |
| Raw Java class | Yes | Yes via getType() |
| Generic element of List | Not retained in List.class | getElementTypeDescriptor() |
| Generic key/value of Map | Not retained in Map.class | getMapKeyTypeDescriptor() / getMapValueTypeDescriptor() |
| Annotation on field | Not described | getAnnotation() / hasAnnotation() |
| Deep generic structure | No | Metadata via getResolvableType() and child descriptors |

`TypeDescriptor` does not recover lost generics on arbitrary runtime objects. `TypeDescriptor.forObject(value)` knows the runtime class, but cannot reliably deduce whether an `ArrayList` is used as `List<String>` or `List<Integer>`. To preserve generic metadata, build the descriptor from a typed field/parameter declaration or provide an explicit element descriptor.

## 3. Commonly Used APIs

`TypeDescriptor` resides in the `org.springframework.core.convert` package.

| API | Meaning |
| --- | --- |
| valueOf(Class<?>) | Descriptor from class |
| new TypeDescriptor(Field) | Preserves generics and annotations of the field |
| getType() | Raw class |
| getResolvableType() | Generic type resolution |
| getElementTypeDescriptor() | Element type of collection/array |
| getMapKeyTypeDescriptor() | Key type of map |
| getMapValueTypeDescriptor() | Value type of map |
| hasAnnotation(Class<?>) / getAnnotation(Class<A>) | Check/read annotation |
| getAnnotations() | Annotation metadata |
| getSource() | Underlying declaration source if present |
| isCollection() / isArray() / isMap() | Check structural kind |
| isAssignableTo(TypeDescriptor) | Check assignability |
| collection(Class, TypeDescriptor) | Create collection descriptor |
| array(TypeDescriptor) | Create array descriptor |
| map(Class, TypeDescriptor, TypeDescriptor) | Create map descriptor |

Descriptors created solely from raw classes usually lack element/key/value types. Check for null before accessing child descriptors because generics may be undeclared or unresolvable.

### 3.1. Collections and Arrays

~~~java
TypeDescriptor strings = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor integers = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));
TypeDescriptor stringArray =
        TypeDescriptor.array(TypeDescriptor.valueOf(String.class));
~~~

`strings` describes `List<String>`, and `integers` describes `List<Integer>`. The caller explicitly supplies generic metadata so the conversion service knows to convert each element.

### 3.2. Maps

~~~java
TypeDescriptor stringToInteger = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(Integer.class));
~~~

The descriptor above represents `Map<String, Integer>`. In map conversion, keys and values are two independent type branches. If two different source keys convert into the same target key, entries may collide; `TypeDescriptor` does not decide collision-handling policy on its own.

## 4. Reading Generic Metadata from a Field

Create a model with a collection, map, and nested generics:

~~~java
import java.util.List;
import java.util.Map;

public class ImportForm {
    private List<String> codes;
    private Map<String, Integer> quantities;
    private List<List<String>> matrix;

    public List<String> getCodes() { return codes; }
    public void setCodes(List<String> codes) { this.codes = codes; }

    public Map<String, Integer> getQuantities() { return quantities; }
    public void setQuantities(Map<String, Integer> quantities) {
        this.quantities = quantities;
    }

    public List<List<String>> getMatrix() { return matrix; }
    public void setMatrix(List<List<String>> matrix) {
        this.matrix = matrix;
    }
}
~~~

Read the element type from the reflected field:

~~~java
Field codesField = ImportForm.class.getDeclaredField("codes");
TypeDescriptor codes = new TypeDescriptor(codesField);

System.out.println(codes.getType().getSimpleName());
System.out.println(
        codes.getElementTypeDescriptor().getType().getSimpleName());
~~~

Output:

~~~text
List
String
~~~

`getType()` returns the raw type `List`; `getElementTypeDescriptor()` returns the element descriptor `String`. You do not need to instantiate `ImportForm` to read the generic signature on the field.

### 4.1. Nested Generics

For `List<List<String>> matrix`:

~~~java
Field field = ImportForm.class.getDeclaredField("matrix");
TypeDescriptor matrix = new TypeDescriptor(field);
TypeDescriptor row = matrix.getElementTypeDescriptor();
TypeDescriptor cell = row.getElementTypeDescriptor();

System.out.println(matrix.getType().getSimpleName());
System.out.println(row.getType().getSimpleName());
System.out.println(cell.getType().getSimpleName());
~~~

Output:

~~~text
List
List
String
~~~

Each step down one level obtains the element descriptor of the current level. With raw collections, wildcards, or unresolved type variables, child descriptors may be absent or insufficiently specific. Do not guess the type from the first element of a runtime collection.

### 4.2. Generic Metadata of a Map

~~~java
Field field = ImportForm.class.getDeclaredField("quantities");
TypeDescriptor quantities = new TypeDescriptor(field);

System.out.println(
        quantities.getMapKeyTypeDescriptor().getType().getSimpleName());
System.out.println(
        quantities.getMapValueTypeDescriptor().getType().getSimpleName());
~~~

Output:

~~~text
String
Integer
~~~

Spring has the metadata to convert keys and values according to their respective target types. If a generic branch is undeclared, check the child descriptor before accessing it.

## 5. Annotation Metadata on TypeDescriptor

Annotations can describe conventions for a field. For example, an application defines `@UppercaseCode` to require normalizing codes to uppercase.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
public @interface UppercaseCode {
}
~~~

Attach to a field:

~~~java
public class ProductForm {
    @UppercaseCode
    private String productCode;

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }
}
~~~

Read the annotation through the descriptor:

~~~java
Field field = ProductForm.class.getDeclaredField("productCode");
TypeDescriptor descriptor = new TypeDescriptor(field);

boolean enabled = descriptor.hasAnnotation(UppercaseCode.class);
UppercaseCode annotation =
        descriptor.getAnnotation(UppercaseCode.class);

System.out.println(enabled);
System.out.println(annotation != null);
~~~

The output is `true` and `true`. `RetentionPolicy.RUNTIME` is required if a converter reads the annotation via reflection at runtime.

### 5.1. Annotations on Fields vs. Type Arguments

An `@UppercaseCode` annotation with target `FIELD` on `List<String>` describes the collection property itself; it does not automatically become an annotation on each `String` element. If you want the annotation attached directly to the type argument, you must declare `@Target(ElementType.TYPE_USE)` and use the syntax `List<@UppercaseCode String>`. Then inspect the corresponding descriptor/`ResolvableType` on your specific Spring version to confirm metadata sits at the right level.

## 6. GenericConverter and ConditionalGenericConverter

`Converter<S,T>` suffices when the rule only needs fixed source and target types. When generic metadata or annotations are needed, Spring provides `GenericConverter`:

~~~java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

`getConvertibleTypes()` declares the supported raw source/target pairs. `convert(...)` receives the descriptors of the specific invocation to access generics and annotations when metadata is available.

`ConditionalGenericConverter` adds `matches(sourceType, targetType)` so the converter is selected only when metadata conditions match.

Example of a converter that normalizes `String` on targets annotated with `@UppercaseCode`:

~~~java
import java.util.Locale;
import java.util.Set;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

public final class UppercaseCodeConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, String.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType, TypeDescriptor targetType) {
        return targetType.hasAnnotation(UppercaseCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        if (source == null) {
            return null;
        }
        return source.toString().trim().toUpperCase(Locale.ROOT);
    }
}
~~~

This is an integration class that must be registered in the appropriate registry; the annotation and `ProductForm` must exist in the project. The `String -> String` pair is very broad, so the `matches` condition is essential. Test both annotated targets and plain targets to ensure the converter does not hijack unrelated conversion paths.

| SPI | When to Use |
| --- | --- |
| Converter<S,T> | Fixed type pair, no generics/annotations needed |
| ConverterFactory<S,R> | One source converting to multiple target types in the same family |
| GenericConverter | Needs TypeDescriptor or multiple type pairs |
| ConditionalGenericConverter | Needs conditions based on annotations/metadata |
| Formatter<T> | Needs Locale-aware parse/print |

Choose the least complex SPI that expresses the requirement accurately. There is no need for `GenericConverter` if a simple `Converter` suffices.

## 7. Converting Collections Using Source/Target Descriptors

`ConversionService` has an overload accepting source and target descriptors:

~~~java
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Example converting `List<String>` to `List<Integer>`:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

TypeDescriptor source = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor target = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        List.of("12", "34"), source, target);

System.out.println(converted);
~~~

Result with the default conversion service:

~~~text
[12, 34]
~~~

If the collection contains an element like `abc` that cannot be parsed into `Integer`, the conversion can fail; do not assume Spring silently skips invalid elements.

### 7.1. Converting Map Keys and Values

~~~java
TypeDescriptor sourceMap = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(String.class));
TypeDescriptor targetMap = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(Long.class),
        TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        Map.of("100", "7"), sourceMap, targetMap);
~~~

Spring has sufficient metadata to convert `String -> Long` keys and `String -> Integer` values. In practice, specify the target map type and handle potential key collisions.

## 8. TypeDescriptor in Data Binding

Spring MVC uses the conversion service when binding request values to model attributes. When the target property is `List<Integer>`, the property's descriptor can provide the element type so Spring converts each element.

~~~java
public class OrderForm {
    private List<Integer> quantities;

    public List<Integer> getQuantities() { return quantities; }
    public void setQuantities(List<Integer> quantities) {
        this.quantities = quantities;
    }
}
~~~

`TypeDescriptor` is metadata for conversion, not a validator. It does not replace `@Valid`, does not check business rules, does not decide authorization, and does not fully define the request schema.

`@RequestBody` JSON goes through an HTTP message converter/JSON mapper. Do not assume a custom converter registered for form binding also governs JSON deserialization.

## 9. When Metadata Is Missing or Generics Are Unresolved

Raw collection:

~~~java
List rawValues;
~~~

No generic element is declared. With a wildcard:

~~~java
List<? extends Number> values;
~~~

The element type is not a simple concrete class. `ResolvableType` assists in analyzing generic structure, yet a converter must still decide how to handle unresolved wildcards/type variables.

Principles:

1. Null-check element/key/value descriptors before using them.
2. Do not guess the element type from the first element of the collection.
3. If the caller needs a generic type and the source lacks metadata, require supplying an explicit descriptor.
4. Use `getResolvableType()` to inspect generic structure.
5. Do not treat an absent annotation as a default annotation.
6. With nested generics, check each level.
7. An empty collection reveals no element type; metadata must come from a field/parameter or the caller.

`TypeDescriptor.forObject(value)` is suitable when only the runtime type is needed. It does not replace a declaration-site descriptor when generics/annotations are needed.

## 10. Standalone Runnable Java 17+ Example

The example uses Java 17+ and Spring Core 6.2.12. The program reads generics/annotations from fields and converts `List<String>` into `List<Integer>`.

settings.gradle:

~~~groovy
rootProject.name = 'type-descriptor-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.12'
}

application {
    mainClass = 'TypeDescriptorDemo'
}
~~~

src/main/java/TypeDescriptorDemo.java:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.List;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public class TypeDescriptorDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface NormalizeCode {
    }

    public static class Sample {
        @NormalizeCode
        private List<String> codes;

        private List<List<String>> matrix;
    }

    public static void main(String[] args) throws Exception {
        Field codesField = Sample.class.getDeclaredField("codes");
        TypeDescriptor codes = new TypeDescriptor(codesField);

        Field matrixField = Sample.class.getDeclaredField("matrix");
        TypeDescriptor matrix = new TypeDescriptor(matrixField);
        TypeDescriptor row = matrix.getElementTypeDescriptor();

        System.out.println("raw=" + codes.getType().getSimpleName());
        System.out.println("element="
                + codes.getElementTypeDescriptor().getType().getSimpleName());
        System.out.println("annotation="
                + codes.hasAnnotation(NormalizeCode.class));
        System.out.println("nested="
                + row.getElementTypeDescriptor().getType().getSimpleName());

        DefaultConversionService service =
                new DefaultConversionService();
        TypeDescriptor target = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Integer.class));

        Object converted = service.convert(
                List.of("12", "34"), codes, target);

        System.out.println("converted=" + converted);
    }
}
~~~

Run with JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

If the Gradle Wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. When dependencies are not cached, the environment needs access to Maven Central.

Expected stdout:

~~~text
raw=List
element=String
annotation=true
nested=String
converted=[12, 34]
~~~

The `codes` descriptor is taken from the field so it contains the element type and annotation. The target descriptor is explicitly constructed as `List<Integer>`. The `NormalizeCode` annotation only illustrates metadata; the demo conversion does not automatically apply an uppercase rule. Being able to read metadata and having a converter actually use that metadata are two separate things.

## 11. Common Mistakes

**Passing only List.class and expecting Spring to know the element type.** A raw class does not retain generic arguments. Create descriptors from fields/parameters or use `TypeDescriptor.collection`.

**Using forObject to recover generics.** Runtime objects do not store generic signatures after type erasure. Keep the descriptor from the declaration or pass one explicitly.

**Annotation missing runtime retention.** To read via reflection, choose `RetentionPolicy.RUNTIME`.

**Confusing container annotations with element annotations.** `List<@A String>` differs from `@A List<String>`. Declare the proper annotation target and test the descriptor at the right level.

**GenericConverter matching too broadly.** The `String -> String` pair is common; use `matches` to restrict the target descriptor, and test negative paths.

**Not null-checking child descriptors.** Raw/wildcard generics may lack a concrete element descriptor.

**Using TypeDescriptor instead of validation.** Metadata helps select conversions; constraints and business rules require separate validators.

**Assuming failing elements are always skipped.** Collection conversion can fail the entire conversion. Partial success requires explicit logic.

**Overlooking map key collisions.** Two text keys may convert into the same key. Define a policy before writing data.

**Ignoring the source of metadata.** A descriptor from a `Field` retains generics/annotations; a descriptor from a raw class does not carry the same information.

## 12. Adoption Checklist

1. Does the rule only need the class, or does it need generics/annotations?
2. Does the source descriptor come from a Field/parameter or a runtime object?
3. Does the target descriptor have complete element/key/value types?
4. Can child descriptors be null?
5. How are raw types, wildcards, and nested generics handled?
6. Is the annotation placed on `FIELD`, `PARAMETER`, or `TYPE_USE`? Is retention `RUNTIME`?
7. Is `matches` scoped narrowly enough?
8. Does collection/map conversion handle errors and key collisions clearly?
9. Is conversion being confused with validation or JSON deserialization?
10. Are collections, maps, nested generics, empty collections, and invalid elements tested?
11. Are targets both with and without the annotation tested?
12. Have you checked the Javadoc for your exact Spring version?

## 13. Official References

- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [TypeDescriptor Javadoc (Spring 6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ResolvableType.html)
- [Java Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)
- [Java Reflection Field API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)

**Key takeaway:** `TypeDescriptor` tells Spring more than a raw `Class`: generic element/key/value types and annotation metadata when provided by the declaration source. Preserve metadata from fields/parameters or construct explicit descriptors; use `GenericConverter` when rules genuinely depend on metadata, and always guard against unresolved generics.
