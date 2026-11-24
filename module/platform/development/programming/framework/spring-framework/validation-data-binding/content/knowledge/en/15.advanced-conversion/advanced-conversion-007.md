# Unknown Element Types and Lost Generic Information

When converting a collection in Java, knowing that a value has type `List` is not enough. An application may need to know whether it is `List<String>`, `List<ProductCode>`, or `List<LocalDate>` in order to convert each element properly. However, due to Java generics **type erasure**, a runtime collection object typically reveals only its class as `ArrayList`/`List`; the declared element type cannot always be retrieved from the object instance.

Spring provides `TypeDescriptor` and `ResolvableType` to preserve or resolve generic metadata when the framework has a type declaration site such as a field, JavaBean property, method parameter, or when the caller supplies an explicit target descriptor. If that information is absent or unresolvable, the framework must treat the element type as **unknown**; do not guess from a random element and treat that as the contract for the entire collection.

This lesson explains type erasure, sources of generic metadata, how Spring conversion handles typed and untyped collections, how to pass target descriptors, and limitations when types are raw, wildcards, or unresolvable type variables. Examples use Java 17+ and Spring Framework 6.2.x.

## 1. Why Is Knowing List Not Enough?

Suppose a form has the property:

```java
private List<ProductCode> productCodes;
```

If the input is a list of strings `["ab-123", "cd-456"]`, the application wants to convert each element into `ProductCode`. To do so, the conversion system needs to know the target container is `List`, the target element type is `ProductCode`, and which `String -> ProductCode` converter is registered.

Passing only `List.class` provides no element information. Java reflection looking solely at `List.class` cannot conclude whether that list holds `ProductCode` or `String`.

| Declaration | Container Type | Element Type |
| --- | --- | --- |
| `List<String>` | `List` | `String` |
| `List<ProductCode>` | `List` | `ProductCode` |
| `List<?>` | `List` | wildcard, no concrete class |
| `List<T>` | `List` | type variable, depends on context |
| raw `List` | `List` | undeclared |
| `List<? extends Number>` | `List` | upper bound `Number`, not a concrete subtype |

For `List<ProductCode>`, the compiler checks types when compiling source code. Yet the generic argument is not stored on each `ArrayList` instance. To handle conversion accurately, the framework needs **metadata at the declaration site** or target metadata supplied by the caller.

## 2. Type Erasure: What Remains and What Is Lost?

The Java compiler uses generics for type checking and applies type erasure when generating bytecode. For example:

```java
List<String> names = new ArrayList<>();
List<ProductCode> codes = new ArrayList<>();

System.out.println(names.getClass() == codes.getClass());
```

Both variables can point to objects of the same runtime class `ArrayList`. The runtime class does not store “this object came from `List<String>`” or “that object came from `List<ProductCode>`”.

That does not mean all generic metadata vanishes from the program. Signatures of fields, methods, and classes can retain generic declarations in the class file for reflection to read. A field declared `List<ProductCode> productCodes` still retains its generic type signature for Spring to introspect.

Distinguish three cases:

1. **Runtime object:** `new ArrayList<ProductCode>()` does not carry its generic element type on the instance itself.
2. **Reflective declaration:** the field `List<ProductCode> productCodes` retains generic metadata; the framework can read it from the declaration.
3. **Class-only API:** passing `List.class` drops the generic argument at that call site; `Class<?>` cannot represent `List<ProductCode>` completely.

```text
Field declaration                         Runtime object
List<ProductCode> productCodes            ArrayList instance
        |                                         |
        | reflection/signature                    | getClass()
        v                                         v
TypeDescriptor / ResolvableType             ArrayList.class
(element = ProductCode)                     (element unknown)
        |                                         |
        +------------------+----------------------+
                           |
                  ConversionService
```

**Consequence:** do not assume that if the first element is `ProductCode`, the entire list always has the contract `List<ProductCode>`. The collection could be empty, contain nulls, or contain heterogeneous types due to raw types/unchecked casts.

## 3. Spring TypeDescriptor: Describing Types at the Access Site

`org.springframework.core.convert.TypeDescriptor` is metadata describing a type Spring needs to convert. Beyond `Class<?>`, it can hold array/collection/map generics, annotations at the declaration site, and the metadata source such as a field, property, or method parameter.

| API | Purpose |
| --- | --- |
| `TypeDescriptor.valueOf(Class<?>)` | Descriptor from a class; adds no generics |
| `TypeDescriptor.forObject(Object)` | Descriptor from a source object |
| `new TypeDescriptor(Field)` | Reads generics/annotations from a field |
| `new TypeDescriptor(Property)` | Describes a JavaBean property |
| `new TypeDescriptor(MethodParameter)` | Describes a method parameter/return value |
| `getElementTypeDescriptor()` | Retrieves element type if resolvable |
| `getMapKeyTypeDescriptor()` / `getMapValueTypeDescriptor()` | Key/value types of a Map |
| `TypeDescriptor.collection(Class, TypeDescriptor)` | Builds a collection descriptor with element type |
| `TypeDescriptor.map(Class, TypeDescriptor, TypeDescriptor)` | Builds a Map descriptor with key/value types |
| `getResolvableType()` | Accesses the underlying `ResolvableType` |

JavaBean example:

```java
public class CatalogForm {
    private List<ProductCode> codes;

    public List<ProductCode> getCodes() { return codes; }
    public void setCodes(List<ProductCode> codes) { this.codes = codes; }
}
```

When Spring introspects the `codes` property, it can read `List<ProductCode>` from the declaration and build a descriptor with element type `ProductCode`. Thus, the binder has context to convert each element.

### 3.1. Raw Descriptor vs. Typed Descriptor

```java
TypeDescriptor raw = TypeDescriptor.valueOf(List.class);

TypeDescriptor typed = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(ProductCode.class));
```

- `raw.getElementTypeDescriptor()` is `null` because only the `List` class is known.
- `typed.getElementTypeDescriptor()` describes `ProductCode` because the caller supplied the type.

`TypeDescriptor.collection` does not read list contents and does not convert a collection when the descriptor is constructed. It describes the **requested target type**; conversion occurs only when calling `ConversionService.convert`.

## 4. ResolvableType: Resolving Generics Across Hierarchies and Context

`org.springframework.core.ResolvableType` introspects and resolves generic types. It is useful for fields, parameterized superclasses/interfaces, method parameters/return types, and type variables replaceable from a concrete subclass.

Example:

```java
class BaseForm<T> {
    private List<T> values;
}

class ProductForm extends BaseForm<ProductCode> {}
```

The field in the base class declares `List<T>`. In the context of `ProductForm`, `T` can be resolved to `ProductCode`. Reading the raw field type alone yields only `List.class`; the generic signature plus context is needed to resolve it.

```java
ResolvableType type = ResolvableType.forClass(ProductForm.class)
        .as(BaseForm.class)
        .getGeneric(0);

Class<?> resolved = type.resolve();
```

This snippet reads the generic argument of `BaseForm` resolved in the `ProductForm` context. When `resolve()` returns `null`, current metadata is insufficient to confirm a concrete class.

**Do not equate unknown with explicit Object.** `List<Object>` has a declared element type of `Object`; raw `List` has no generic declaration. These two cases can lead to different converter choices.

## 5. Converting Collections: Target Element Type Matters

Spring provides default converters for collections/arrays and can reuse converters for the element type. If you already registered `Converter<String, ProductCode>`, you normally do not need to write an extra specialized `List<String> -> List<ProductCode>` converter.

```java
DefaultConversionService service =
        new DefaultConversionService();
service.addConverter(new ProductCodeConverter());

List<String> source = List.of("ab-123", "cd-456");

TypeDescriptor sourceType = TypeDescriptor.forObject(source);
TypeDescriptor targetType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(ProductCode.class));

@SuppressWarnings("unchecked")
List<ProductCode> result =
        (List<ProductCode>) service.convert(
                source, sourceType, targetType);
```

Here:

1. `sourceType` describes the source object; each element's type can be narrowed from its runtime value.
2. `targetType` specifies the `List` container and element type `ProductCode`.
3. Spring selects collection conversion and converts each element via the scalar converter.
4. The result contains newly created `ProductCode` objects, not a cast list of strings.

The `ConversionService.convert(Object, Class<T>)` overload accepts only a target `Class<T>`, which cannot represent parameterized collections. When a generic target is needed, use the overload taking source/target `TypeDescriptor`s.

### 5.1. When Target Element Type Is Unknown

If you only have:

```java
Class<?> targetClass = List.class;
```

then Spring cannot tell whether the caller wants `List<ProductCode>` or `List<UUID>`. Obtain the descriptor from a field/property/method parameter if binding into a typed declaration; build an explicit descriptor if converting programmatically; or define an explicit contract if the API truly accepts a raw/unknown collection.

Do not guess the type from the first sample in the collection. For an empty list, that heuristic has no data; for raw/unsafe input, the first element may not represent the remaining elements.

## 6. Runnable Java 17+ Example: With and Without Metadata

This example uses Spring Framework 6.2.12 to demonstrate:

- The runtime class of two differently parameterized generic lists is still the same.
- `BeanWrapper` reads the descriptor from a `List<ProductCode>` property.
- A raw `List` has no declared element descriptor.
- `ConversionService` converts each `String` to `ProductCode` when the target descriptor specifies the type.

### 6.1. Project Structure

```text
generic-conversion-demo/
├── pom.xml
└── src/main/java/GenericConversionDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>generic-conversion-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/GenericConversionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.core.ResolvableType;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class GenericConversionDemo {

    public record ProductCode(String value) {
        public ProductCode {
            if (value == null || !value.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
        }
    }

    public static final class ProductCodeConverter
            implements Converter<String, ProductCode> {
        @Override
        public ProductCode convert(String source) {
            if (source == null) {
                return null;
            }
            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new ProductCode(normalized);
        }
    }

    public static class CatalogForm {
        private List<ProductCode> codes = new ArrayList<>();

        @SuppressWarnings("rawtypes")
        private List rawCodes = new ArrayList();

        public List<ProductCode> getCodes() { return codes; }
        public void setCodes(List<ProductCode> codes) { this.codes = codes; }

        @SuppressWarnings("rawtypes")
        public List getRawCodes() { return rawCodes; }

        @SuppressWarnings("rawtypes")
        public void setRawCodes(List rawCodes) { this.rawCodes = rawCodes; }
    }

    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<ProductCode> codes = new ArrayList<>();

        System.out.println("same.runtime.class=" +
                (strings.getClass() == codes.getClass()));

        CatalogForm form = new CatalogForm();
        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(form);

        TypeDescriptor codesDescriptor =
                wrapper.getPropertyTypeDescriptor("codes");
        TypeDescriptor rawDescriptor =
                wrapper.getPropertyTypeDescriptor("rawCodes");

        System.out.println("declared.codes.element=" +
                codesDescriptor.getElementTypeDescriptor().getType()
                        .getSimpleName());
        System.out.println("declared.rawCodes.element=" +
                (rawDescriptor.getElementTypeDescriptor() == null
                        ? "unknown"
                        : rawDescriptor.getElementTypeDescriptor()
                                .getType().getSimpleName()));

        ResolvableType resolved =
                ResolvableType.forField(getCodesField());
        System.out.println("resolvable.codes.element=" +
                resolved.getGeneric(0).resolve().getSimpleName());

        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new ProductCodeConverter());

        List<String> input = List.of("ab-123", "cd-456");
        TypeDescriptor sourceType = TypeDescriptor.forObject(input);
        TypeDescriptor targetType = TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(ProductCode.class));

        @SuppressWarnings("unchecked")
        List<ProductCode> converted =
                (List<ProductCode>) service.convert(
                        input, sourceType, targetType);

        System.out.println("target.element=" +
                targetType.getElementTypeDescriptor().getType()
                        .getSimpleName());
        System.out.println("converted=" +
                converted.stream().map(ProductCode::value).toList());
        System.out.println("converted.element=" +
                converted.get(0).getClass().getSimpleName());
    }

    private static java.lang.reflect.Field getCodesField() {
        try {
            return CatalogForm.class.getDeclaredField("codes");
        } catch (NoSuchFieldException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
```

Run from the `generic-conversion-demo` directory using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=GenericConversionDemo
```

Stdout:

```text
same.runtime.class=true
declared.codes.element=ProductCode
declared.rawCodes.element=unknown
resolvable.codes.element=ProductCode
target.element=ProductCode
converted=[AB-123, CD-456]
converted.element=ProductCode
```

### 6.2. Result Explanation

- Two `ArrayList` objects have the same runtime class even though the variables were declared `List<String>` or `List<ProductCode>`.
- `BeanWrapper.getPropertyTypeDescriptor("codes")` reads JavaBean property metadata. The declared `List<ProductCode>` field/setter lets Spring determine the element type.
- `rawCodes` uses raw `List`, so the descriptor cannot determine the element type from the declaration; the code prints `unknown`.
- `ResolvableType.forField(...)` reads the generic signature directly from the field and resolves it to `ProductCode`.
- The target descriptor is created with `TypeDescriptor.collection(...)`, so the conversion system knows to convert each element to `ProductCode`.
- The scalar converter normalizes each string. No separate converter is needed for the entire list.

The example does not read generics from object instances. Metadata comes from class/property/field declarations or caller-provided descriptors.

## 7. Generic Metadata in BeanWrapper and DataBinder

When binding into a JavaBean declaring:

```java
class ImportForm {
    private List<LocalDate> dates;

    public List<LocalDate> getDates() { return dates; }
    public void setDates(List<LocalDate> dates) { this.dates = dates; }
}
```

Spring introspection can obtain the element type from the property. When a converter/formatter is registered for the date type, the binder has context to convert each element. With indexed paths such as `dates[0]`, nested property metadata also plays a role.

```java
BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(form);

TypeDescriptor property =
        wrapper.getPropertyTypeDescriptor("dates");
TypeDescriptor element =
        property.getElementTypeDescriptor();
```

This is an illustrative snippet using `form` with a `dates` property. If the element descriptor is non-null, inspect `element.getType()` to see the resolved type.

`DataBinder` uses property access and corresponding conversion when binding `PropertyValues`. When the element type is declared, the framework can convert each item; if an input is invalid, the binder can record an error associated with a path such as `dates[1]` in `BindingResult`. Verify the actual `FieldError` rather than assuming every collection conversion case generates the same error code/path.

**Raw collections reduce available information.** If a property is declared as raw `List`, Spring cannot derive a declared element class from the signature. A runtime value may sometimes allow narrowing the descriptor for one concrete element, yet it does not restore the missing contract for empty collections or other elements.

## 8. GenericConverter: When Source/Target Descriptors Are Truly Needed

`Converter<S,T>` is convenient for simple type pairs. When you need to inspect generics/annotations of the source and target, Spring provides `GenericConverter`:

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
```

This is a condensed form of the SPI. `getConvertibleTypes()` declares the type pairs; `convert(...)` receives descriptors to read generic declarations, annotations, or property/parameter declaration sites.

For instance, an array-to-collection converter may need to know the target is `List<ProductCode>` to convert each element. Spring already provides default collection converters for many cases; write a custom `GenericConverter` only when logic genuinely requires special metadata.

**Do not use GenericConverter to guess the caller's intent.** If the target type is genuinely unknown, the descriptor cannot invent a business schema either. The caller must supply the type or the API must have an explicit schema.

`ConditionalGenericConverter` can execute only when descriptors satisfy a condition, such as a specific annotation or generic type. It adds complexity; for ordinary `String -> ProductCode` needs, `Converter<String, ProductCode>` is simpler.

## 9. Generic Types: Resolvable, Unresolvable, or Partially Resolvable

| Declaration/Context | Resolvability | Handling Guidance |
| --- | --- | --- |
| `List<ProductCode>` | Clear `ProductCode` element | Read from field/property |
| `List<T>` in `Base<T>`, target is `Base<ProductCode>` | Resolvable if context is supplied | Use `ResolvableType`/`TypeDescriptor` with subclass context |
| `List<T>` with raw `Base` | `T` unknown | Require caller to provide schema |
| `List<?>` | Wildcard specifies no concrete class | Do not guess target element |
| `List<? extends Number>` | Has upper bound `Number`, no concrete subtype specified | Do not assume Integer/BigDecimal |
| raw `List` | No element type declared | Refactor API to typed collection if possible |
| `List<Object>` | Declared element type is `Object` | Metadata exists, though very broad |
| `List<List<ProductCode>>` | Nested generics if declaration is complete | Traverse descriptors level by level |

`List<? extends Number>` and `List<Number>` are not equivalent. A wildcard expresses a type bound; writing elements is also constrained by Java's variance rules. DTOs used for binding are more predictable when declaring concrete element types and suitable mutable collections.

### 9.1. Type Variables in Generic Classes

```java
class BaseForm<T> {
    private List<T> items;
}

class ProductForm extends BaseForm<ProductCode> {}
```

If you introspect `BaseForm.items` without context, `T` cannot be resolved concretely. If Spring knows it is processing `ProductForm`, it can substitute `T` with `ProductCode` via the generic hierarchy.

That is why Spring provides `ResolvableType` instead of relying only on `Field.getType()`. `getType()` returns raw `List.class`; `getGenericType()` or Spring `ResolvableType` preserves the generic signature structure to resolve against context.

## 10. Maps Also Have Two Generic Arguments

A `Map` has a key type and a value type:

```java
Map<CustomerId, ProductCode> assignments;
```

`TypeDescriptor` provides `getMapKeyTypeDescriptor()` and `getMapValueTypeDescriptor()`; when building descriptors manually, use `TypeDescriptor.map(...)`:

```java
TypeDescriptor mapType = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(CustomerId.class),
        TypeDescriptor.valueOf(ProductCode.class));
```

This is a descriptor for `Map<CustomerId, ProductCode>`. It does not read data and does not query a database to verify customers/products. It only specifies the target key/value types for conversion.

If a `Map` is declared raw or `Map<?, ?>`, key/value descriptors may be unknown. Do not infer types for the entire `Map` from the first key/value entry.

## 11. Nested TypeDescriptors and Annotation Metadata

A property can have multiple levels:

```java
List<Map<String, ProductCode>> groupedCodes;
```

Metadata includes the `List` container, element `Map<String, ProductCode>`, key `String`, and value `ProductCode`. `TypeDescriptor` can represent these collection/map layers; `nested(int)` and related APIs help navigate to nested types. If generics cannot be resolved, deeper descriptors may be unavailable.

Descriptors also carry annotations on fields/properties/parameters. A `GenericConverter` can read annotations via `targetType.getAnnotation(...)` to select conversion rules. Even so, annotation metadata does not turn a converter into a place for authorization checks or business queries.

**Metadata is not runtime data.** `TypeDescriptor` describes the target site receiving a value; it does not hold the collection's contents, does not guarantee existing elements have the right type, and does not enforce domain constraints.

## 12. Why Not Use instanceof to Infer Generics for an Entire Collection?

An unsafe pattern:

```java
if (value instanceof List<?> list && !list.isEmpty()) {
    Class<?> elementClass = list.get(0).getClass();
    // Cannot conclude that every element uses the same type.
}
```

Problems:

- An empty collection has no first element.
- A collection can contain nulls.
- A raw collection/unchecked cast can hold mixed types.
- The first element may be a subtype rather than the declared contract.
- A runtime element does not replace the annotation/generic context of the target property.

`elementTypeDescriptor(Object element)` can narrow a descriptor for **one concrete element**. That does not prove the entire collection has that element type contract. To convert an entire collection to a typed target, obtain the element type from the property or pass an explicit descriptor.

## 13. Common Errors When Generic Metadata Is Lost

| Symptom | Cause | Solution |
| --- | --- | --- |
| `List.class` reveals no element | Only raw class passed | Use `TypeDescriptor.collection(...)` |
| BeanWrapper gets no element type | Property declared as raw `List` | Change to a concrete `List<T>` |
| Base class returns unresolved `T` | Missing concrete context | Resolve via subclass using `ResolvableType` |
| Target collection remains String | Target element descriptor is unknown/Object | Supply a typed target descriptor |
| Conversion fails at element N | One element fails converter | Inspect input and field error path |
| Empty collection gives no type | No runtime element to narrow | Use declaration/contract |
| Nested generics fail to resolve | Raw/wildcard/type variable at one level | Inspect each nested descriptor |
| `ClassCastException` after conversion | Cast list without converting elements | Use ConversionService |
| MVC and manual convert differ | MVC has property metadata; manual code passes only Class | Use TypeDescriptor in manual code |
| Map keys/values converted wrongly | Described only as raw Map | Use property descriptor or `TypeDescriptor.map` |

A dangerous error is an unchecked cast:

```java
@SuppressWarnings("unchecked")
List<ProductCode> codes = (List<ProductCode>) rawList;
```

This does not convert elements. It merely tells the compiler not to warn; real failures will surface when reading/casting individual items. To convert, create a new target collection and convert each element according to the contract.

## 14. Choosing APIs by Scenario

| Scenario | Suitable API | Why |
| --- | --- | --- |
| Convert one concrete type | `Converter<S,T>` + ConversionService | Simple, strongly typed |
| Convert collection per property declaration | Bean property metadata + TypeDescriptor | Reads generic declaration |
| Manual code converting `List<S>` to `List<T>` | ConversionService with source/target TypeDescriptor | Supplies generic descriptors |
| Type variable via superclass/interface | `ResolvableType` | Resolves across hierarchy/context |
| Converter needs target annotations/generics | `GenericConverter` | Receives source/target descriptors |
| Metadata-conditional conversion | `ConditionalGenericConverter` | Conditional matching |
| Locale-dependent UI text | `Formatter<T>` | Locale-aware parse/print |
| JavaBean data binding | `DataBinder`/`BeanWrapper` | Framework holds property metadata |

Do not default to `GenericConverter` for every collection. Spring already provides common collection/array conversions; a scalar converter for elements is usually enough. Switch to the generic SPI only when logic genuinely needs descriptors or multiple source/target pairs.

## 15. Testing Generic Conversion

Minimum test cases:

1. **Typed property:** `List<ProductCode>` yields element descriptor `ProductCode`.
2. **Raw property:** raw `List` has unknown/null element descriptor.
3. **Parameterized target:** collection descriptor with `ProductCode` converts each element.
4. **Empty list:** target descriptor still knows the element type even with no source elements.
5. **Invalid input:** one malformed string triggers a conversion error.
6. **Nested types:** `List<Map<String, ProductCode>>` yields corresponding key/value descriptors when declarations are complete.
7. **Generic inheritance:** `BaseForm<T>` resolves `T` in a concrete subclass when context is present.
8. **Unsafe raw input:** mixed-type data is caught cleanly without relying on casts.
9. **Null elements:** null policy is explicitly defined.
10. **MVC and manual code:** test both if the application uses both conversion paths.

Illustrative JUnit assertion:

```java
assertEquals(ProductCode.class,
        wrapper.getPropertyTypeDescriptor("codes")
                .getElementTypeDescriptor().getType());

assertNull(wrapper.getPropertyTypeDescriptor("rawCodes")
        .getElementTypeDescriptor());
```

This test snippet requires `wrapper` from `CatalogForm` in section 6 and JUnit. It proves generic metadata comes from the property declaration, not the list instance.

When testing conversion programmatically, assert every resulting element has the expected class and value. Asserting only that the result is a `List` does not verify the element type.

## 16. API Design Notes

- Avoid raw collections in DTOs/public APIs; declare concrete generics when the element type is known.
- Do not use wildcards when a binder must instantiate/populate concrete elements without a contract.
- For dynamic structures, use an explicit schema/discriminator and resolve safely at the appropriate layer.
- Do not accept arbitrary class names from clients and call `Class.forName` to pick types; that is not a safe generic binding mechanism.
- Do not use the runtime class of the first element to decide the type of an entire collection.
- For large collections, bound body size/element count at the input layer; generic metadata does not bound resources.
- Per-element validation is a separate step; descriptors do not prove business validity.
- If generics cannot be resolved, treat as unknown and require an explicit contract; never silently pick `Object` and cast.

## 17. Self-Check Knowledge Quiz

**1. Why do `new ArrayList<String>()` and `new ArrayList<ProductCode>()` share the same runtime class?**  
Because of Java type erasure. Generic arguments serve compile-time checking and may remain in declaration signatures, yet are not stored on each instance.

**2. Does `TypeDescriptor.valueOf(List.class)` know the element type?**  
No. It describes only the raw class; `getElementTypeDescriptor()` may return null.

**3. When does BeanWrapper know a property is `List<ProductCode>`?**  
When the generic is declared concretely in the field/getter/setter signature and Spring introspection can read that metadata.

**4. Why is `ConversionService.convert(source, List.class)` insufficient to request `List<ProductCode>`?**  
Target `Class` does not represent generic arguments. Use the overload taking `TypeDescriptor`.

**5. Does `TypeDescriptor.collection(...)` convert the list immediately?**  
No. It creates metadata describing the target; conversion happens when calling `ConversionService`.

**6. Can `List<?>` be resolved to `ProductCode` from the first element?**  
You should not treat the first element as a contract. A wildcard supplies no concrete target type; callers must state `List<ProductCode>` when required.

**7. How does `ResolvableType` help with `Base<T>`?**  
It can resolve type variables in the context of a concrete subclass/interface if the generic hierarchy provides enough information.

**8. Is a separate `List<String> -> List<ProductCode>` converter needed?**  
Normally no. Register a scalar converter and supply the target element descriptor; Spring can reuse its default collection converter.

**9. Does a descriptor prove every current element has the right type?**  
No. It describes the declaration/target, not an inspection of the entire runtime collection.

**10. What should you do if the element type is unknown?**  
Keep it marked unknown, require an explicit schema/descriptor, or refactor the API to a typed collection. Do not guess and do not perform unchecked casts.

**Key takeaway:** generic metadata does not live on individual collection instances after type erasure; it comes from **declaration/context** or **caller-provided target descriptors**. `TypeDescriptor` describes types at conversion sites, `ResolvableType` resolves generics across hierarchies, and `ConversionService` uses that metadata to convert each element accurately. When metadata is absent, acknowledge **unknown** and clarify the contract instead of guessing.

## Official References

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2 — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework 6.2 — GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework 6.2 — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Java Language Specification — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
