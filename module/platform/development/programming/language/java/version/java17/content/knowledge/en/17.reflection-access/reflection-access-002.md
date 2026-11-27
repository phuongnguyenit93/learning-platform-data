# `Class.isRecord` and `Class.getRecordComponents` in Java 17

Java 17 provides the Record Reflection API so programs can identify a record type and read metadata for the components declared in the record header. Two key methods on `java.lang.Class` are:

- **`Class.isRecord()`**: indicates whether the `Class<?>` object represents a record class.
- **`Class.getRecordComponents()`**: returns metadata for the record components in declaration order.

These APIs are useful when building frameworks, serializers, mappers, type-inspection tools, logging utilities, or general-purpose object processors. Instead of guessing whether a class is a record based on its name, fields, or methods, code can ask the JVM directly via reflection.

Records were officially introduced in Java 16; these reflection methods have also been available since Java 16 and are stable in Java 17. This lesson focuses on how to identify records, read component metadata, invoke accessors, handle generic types and annotations, and understand the limitations when working with records via reflection.

## 1. What is a record component?

A record declares its data components directly in its header:

```java
public record Person(String name, int age) {
}
```

`name` and `age` are two **record components**. When declaring a record, Java automatically provides:

- A backing storage field corresponding to each component; these fields are `private final`.
- Accessors matching the component names, such as `name()` and `age()`.
- A canonical constructor accepting the components in declaration order.
- `equals()`, `hashCode()`, and `toString()` methods generated according to record rules.

Accessors can be called normally:

```java
Person person = new Person("Lan", 25);

System.out.println(person.name());
System.out.println(person.age());
```

Output:

```text
Lan
25
```

A record component is a concept in the record's declaration structure. It relates to the backing field, accessor, and canonical constructor parameter, but **is not synonymous with a `Field` object**. When you need to read the exact metadata of the record header, the dedicated API is `Class.getRecordComponents()`.

## 2. Checking whether a class is a record with `isRecord()`

`isRecord()` is called on a `Class<?>` object:

```java
Class<?> type = Person.class;

if (type.isRecord()) {
    System.out.println("This is a record class");
} else {
    System.out.println("This is not a record class");
}
```

Output:

```text
This is a record class
```

Comparison with regular types:

```java
record Point(int x, int y) {
}

class Employee {
}

System.out.println(Point.class.isRecord());    // true
System.out.println(Employee.class.isRecord()); // false
System.out.println(String.class.isRecord());   // false
System.out.println(int.class.isRecord());      // false
System.out.println(java.lang.Record.class.isRecord()); // false
```

`java.lang.Record` is the base class for records, but `Record.class` itself is not a record class. `isRecord()` inspects the metadata of the represented type, not merely whether the type inherits from `Record`.

### When should you use `isRecord()`?

Use `isRecord()` when code receives an unknown type, such as:

- A library receiving a `Class<?>` from a user.
- A serializer needing to process records by component.
- A debugging tool needing to display data structures.
- A mapper distinguishing records from regular JavaBeans.
- A framework choosing the appropriate instantiation or reading strategy.

Do not rely on a class name containing `Record`, field count, or inheritance from `java.lang.Record` as a substitute for `isRecord()`. This API clearly expresses intent and avoids error-prone guesses.

## 3. Reading the component list with `getRecordComponents()`

When a type is a record, `getRecordComponents()` returns a `RecordComponent[]` array:

```java
import java.lang.reflect.RecordComponent;

Class<?> type = Person.class;

if (type.isRecord()) {
    RecordComponent[] components = type.getRecordComponents();

    for (RecordComponent component : components) {
        System.out.println(component.getName());
        System.out.println(component.getType().getTypeName());
    }
}
```

For record `Person(String name, int age)`, the read metadata corresponds to:

```text
name
java.lang.String
age
int
```

**The order in the array matches the declaration order of components in the record header.** For `Person(String name, int age)`, the first component is `name` and the second component is `age`. This order is also the parameter order of the canonical constructor.

### Return value when the type is not a record

Pay attention to the method contract:

- If `Class` represents a record class, `getRecordComponents()` returns the array of components.
- If `Class` does not represent a record class, the method returns **`null`**.
- If a record declares no components, the method returns an empty array, not `null`.

Example:

```java
record Marker() {
}

RecordComponent[] markerComponents =
        Marker.class.getRecordComponents();

System.out.println(markerComponents.length); // 0

RecordComponent[] stringComponents =
        String.class.getRecordComponents();

System.out.println(stringComponents == null); // true
```

Therefore, never call `getRecordComponents().length` directly without first checking `isRecord()` or checking for `null`. A safe way to write it:

```java
static void printComponents(Class<?> type) {
    RecordComponent[] components = type.getRecordComponents();

    if (components == null) {
        System.out.println(type.getName() + " is not a record");
        return;
    }

    if (components.length == 0) {
        System.out.println(type.getName() + " is a record with no components");
        return;
    }

    for (RecordComponent component : components) {
        System.out.println(component.getName());
    }
}
```

You can call `isRecord()` first to make intent explicit; checking for `null` directly also protects the code when only processing the returned value.

## 4. Information readable from `RecordComponent`

Each element of `RecordComponent[]` is a `java.lang.reflect.RecordComponent` object. The API provides metadata about the component:

| Method | Information |
| --- | --- |
| `getName()` | The component name in the record header. |
| `getType()` | The runtime type as `Class<?>`, after type erasure for generic types. |
| `getGenericType()` | The declared type preserving generic information, returning `Type`. |
| `getAnnotatedType()` | The type with annotation metadata at type-use positions. |
| `getAccessor()` | The `Method` representing the component's accessor. |
| `getDeclaringRecord()` | The `Class<?>` of the record declaring the component. |
| `getAnnotation(Class<T>)` | Retrieves the annotation applied to the component, if present. |
| `getAnnotations()` | Retrieves annotations present on the component. |
| `isAnnotationPresent(Class<?>)` | Checks whether the component has the specified annotation. |

Example printing name, type, and accessor:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

static void describeRecord(Class<?> type) {
    if (!type.isRecord()) {
        throw new IllegalArgumentException("type must be a record");
    }

    for (RecordComponent component : type.getRecordComponents()) {
        Method accessor = component.getAccessor();

        System.out.println("Name: " + component.getName());
        System.out.println("Type: " + component.getType().getTypeName());
        System.out.println("Accessor: " + accessor.getName());
        System.out.println(
                "Declaring record: "
                        + component.getDeclaringRecord().getName()
        );
    }
}
```

For `Person`, the corresponding accessors are `name()` and `age()`. `getDeclaringRecord()` returns the record type itself that declares the component.

## 5. Complete example: inspecting record metadata

Create `RecordIntrospectionDemo.java`:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordIntrospectionDemo {

    public record Person(String name, int age, boolean active) {
    }

    public static void main(String[] args) {
        Class<?> type = Person.class;

        System.out.println("Class: " + type.getName());
        System.out.println("Is record: " + type.isRecord());

        if (!type.isRecord()) {
            return;
        }

        RecordComponent[] components = type.getRecordComponents();

        System.out.println("Component count: " + components.length);

        for (int i = 0; i < components.length; i++) {
            RecordComponent component = components[i];

            System.out.println("Component " + i);
            System.out.println("  name: " + component.getName());
            System.out.println(
                    "  type: " + component.getType().getTypeName()
            );
            System.out.println(
                    "  accessor: " + component.getAccessor().getName()
            );
        }

        System.out.println(
                "Names: " + Arrays.stream(components)
                        .map(RecordComponent::getName)
                        .toList()
        );
    }
}
```

Output:

```text
Class: RecordIntrospectionDemo$Person
Is record: true
Component count: 3
Component 0
  name: name
  type: java.lang.String
  accessor: name
Component 1
  name: age
  type: int
  accessor: age
Component 2
  name: active
  type: boolean
  accessor: active
Names: [name, age, active]
```

Compile and run with Java 17:

```bash
javac --release 17 -encoding UTF-8 RecordIntrospectionDemo.java
java RecordIntrospectionDemo
```

The example shows that you can read a record's structure directly from `Class<?>` without creating an instance. To read the actual values of each component, you need an instance and must invoke the corresponding accessor; that is covered next.

## 6. Using accessors to read component values via reflection

`getRecordComponents()` only returns metadata, not the values of an object. Each `RecordComponent` provides `getAccessor()` to get the `Method` representing the accessor.

Example:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class ReadRecordValues {

    public record Person(String name, int age) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Person person = new Person("Lan", 25);

        for (RecordComponent component :
                Person.class.getRecordComponents()) {

            Method accessor = component.getAccessor();
            Object value = accessor.invoke(person);

            System.out.println(component.getName() + " = " + value);
        }
    }
}
```

Output:

```text
name = Lan
age = 25
```

Explanation:

1. `Person.class.getRecordComponents()` retrieves metadata for the two components.
2. `component.getAccessor()` gets the corresponding accessor method.
3. `accessor.invoke(person)` invokes the accessor on the `person` instance.
4. The returned value is received as `Object` because reflection does not know the exact type at compile time.

A record's accessor is a method for reading the component, not a setter. Records do not provide default setters to mutate components after construction.

### Writing a helper to read all components into a Map

A small utility can convert a record into a name/value map:

```java
import java.lang.reflect.RecordComponent;
import java.util.LinkedHashMap;
import java.util.Map;

static Map<String, Object> toMap(Object value)
        throws ReflectiveOperationException {

    Class<?> type = value.getClass();

    if (!type.isRecord()) {
        throw new IllegalArgumentException("Object must be a record");
    }

    Map<String, Object> result = new LinkedHashMap<>();

    for (RecordComponent component : type.getRecordComponents()) {
        Object componentValue =
                component.getAccessor().invoke(value);

        result.put(component.getName(), componentValue);
    }

    return result;
}
```

Use `LinkedHashMap` to preserve insertion order matching the component order in the record header:

```java
record Product(String code, int quantity) {
}

Product product = new Product("P-01", 4);

System.out.println(toMap(product));
```

Output:

```text
{code=P-01, quantity=4}
```

This is a reflection illustration. A production serializer also needs to handle nested types, collections, nulls, annotations, object cycles, and policies for protecting sensitive data.

## 7. Distinguishing `getType()` and `getGenericType()`

For non-generic components, the two methods usually give very similar results. The difference becomes clear when the record uses generic types.

Example:

```java
import java.util.List;

record Envelope<T>(
        T payload,
        List<String> labels
) {
}
```

Inspecting metadata:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component :
        Envelope.class.getRecordComponents()) {

    System.out.println("Name: " + component.getName());
    System.out.println(
            "Type: " + component.getType().getTypeName()
    );
    System.out.println(
            "Generic type: " + component.getGenericType().getTypeName()
    );
}
```

Typical output:

```text
Name: payload
Type: java.lang.Object
Generic type: T
Name: labels
Type: java.util.List
Generic type: java.util.List<java.lang.String>
```

Explanation:

- `getType()` returns the `Class<?>` type after applying type erasure.
- `getGenericType()` returns a `Type` object that can retain generic information from the declaration signature.
- For component `T payload`, the runtime type after erasure is `Object` in this example, while the generic type still shows `T`.
- For `List<String> labels`, `getType()` returns the raw class `List`, whereas `getGenericType()` shows the type argument `String`.

`Type` is not always a `Class<?>`. Depending on the declaration, it may be a `ParameterizedType`, `TypeVariable`, `WildcardType`, or generic array type. If a framework needs to analyze generic types, it must handle the corresponding `Type` subtypes instead of casting everything to `Class`.

### Inspecting generic types with ParameterizedType

Example:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;

for (RecordComponent component :
        Envelope.class.getRecordComponents()) {

    Type genericType = component.getGenericType();

    if (genericType instanceof ParameterizedType parameterized) {
        System.out.println("Raw type: " + parameterized.getRawType());

        for (Type argument : parameterized.getActualTypeArguments()) {
            System.out.println("Type argument: " + argument.getTypeName());
        }
    }
}
```

For `List<String>`, the raw type is `List` and the type argument is `String`. For `T`, the generic type is a `TypeVariable`, so it does not enter the `ParameterizedType` branch.

## 8. Reading annotations on record components

Record components can carry annotations. For an annotation to appear via reflection, it needs appropriate retention, typically `RetentionPolicy.RUNTIME`, and its target must include `ElementType.RECORD_COMPONENT`.

Example annotation definition:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Sensitive {
}
```

Using the annotation on a record:

```java
public record Credentials(
        String username,
        @Sensitive String accessToken
) {
}
```

Checking the annotation:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component :
        Credentials.class.getRecordComponents()) {

    boolean sensitive = component.isAnnotationPresent(Sensitive.class);

    System.out.println(
            component.getName() + ": sensitive=" + sensitive
    );
}
```

Output:

```text
username: sensitive=false
accessToken: sensitive=true
```

You can retrieve the annotation directly:

```java
Sensitive annotation =
        Credentials.class
                .getRecordComponents()[1]
                .getAnnotation(Sensitive.class);
```

If an annotation does not have runtime retention, runtime reflection will not be able to read it via `getAnnotation()`.

### Annotations on record components can propagate to multiple elements

A record component relates to several compiler-generated elements: the field, the accessor, and the canonical constructor parameter. If an annotation is declared with multiple matching targets, the compiler can propagate that annotation to the corresponding elements according to record rules.

Example annotation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
})
@interface Label {
    String value();
}
```

Declaration:

```java
record User(
        @Label("Display name") String displayName
) {
}
```

When inspecting, be clear about where you are reading the annotation from:

- `RecordComponent.getAnnotation(...)` reads annotations on the record component.
- `Field.getAnnotation(...)` reads annotations on the backing field if the annotation was applied to fields.
- `Method.getAnnotation(...)` reads annotations on the accessor if the annotation was applied to methods.
- `Parameter.getAnnotation(...)` reads annotations on the canonical constructor parameter if the annotation was applied to parameters.

Do not assume an annotation appears in every location just because it is written in the record header. The result depends on the annotation's `@Target`.

## 9. Using `getAnnotatedType()` for type-use annotations

Annotations can attach to a **type** (type-use), not just to the component declaration itself.

Example annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmpty {
}
```

Record declaration:

```java
record SearchRequest(
        @NonEmpty String query
) {
}
```

Reading the annotated type:

```java
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component =
        SearchRequest.class.getRecordComponents()[0];

AnnotatedType annotatedType = component.getAnnotatedType();

System.out.println(annotatedType.getType().getTypeName());
System.out.println(
        annotatedType.isAnnotationPresent(NonEmpty.class)
);
```

Output:

```text
java.lang.String
true
```

`getAnnotation()` on `RecordComponent` and `getAnnotatedType()` address two different metadata locations. When building a validation framework, determine whether an annotation is defined for component declarations or for type-use so you read the right API.

Note: the `@NonEmpty` annotation in this example is only metadata. Java does not automatically enforce validation just because an annotation exists; a framework or application code must read and apply the corresponding rules.

## 10. Distinguishing record components from regular fields and methods

A record such as:

```java
record Order(String id, int quantity) {
    private static final String CATEGORY = "SALE";

    public String description() {
        return id + " x " + quantity;
    }
}
```

has two record components: `id` and `quantity`. However, when using `getDeclaredFields()`, reflection can also see the static field `CATEGORY`. When using `getDeclaredMethods()`, reflection can see accessors as well as explicitly declared methods.

Therefore, you should not use the number of fields to infer the number of record components.

| API | Returns | Purpose |
| --- | --- | --- |
| `Class.getRecordComponents()` | `RecordComponent[]` or `null` | Component structure declared in the record header. |
| `Class.getDeclaredFields()` | `Field[]` | Fields declared directly in the class, including non-public fields. |
| `Class.getDeclaredMethods()` | `Method[]` | Methods declared directly in the class, including non-public methods. |
| `Class.getDeclaredConstructors()` | `Constructor<?>[]` | Constructors declared directly in the class. |

Use the right API for the question you need to answer. If a serializer needs the names and order of a record's components, `getRecordComponents()` is the direct choice. If you need to inspect an auxiliary static field, use field reflection accordingly.

## 11. Record components and the canonical constructor

A record has a canonical constructor that takes parameters in component order. You can obtain the parameter types from metadata and look up the constructor via reflection.

Example:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;

record Coordinate(int x, int y) {
}

Class<Coordinate> type = Coordinate.class;

RecordComponent[] components = type.getRecordComponents();

Class<?>[] parameterTypes = new Class<?>[components.length];

for (int i = 0; i < components.length; i++) {
    parameterTypes[i] = components[i].getType();
}

Constructor<Coordinate> constructor =
        type.getDeclaredConstructor(parameterTypes);

Coordinate coordinate = constructor.newInstance(10, 20);

System.out.println(coordinate);
```

Output:

```text
Coordinate[x=10, y=20]
```

The component order in `getRecordComponents()` determines the parameter type order of the canonical constructor. However, type metadata does not supply input values; a serializer or mapper must extract values from the data source, convert them to the right types, and pass them in the right order.

### Creating a record with constructor validation

If a compact canonical constructor has validation, invoking the constructor via reflection still runs that validation:

```java
record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
```

When calling `newInstance(0)` via reflection, the constructor throws an exception. With `Constructor.newInstance()`, exceptions thrown by the constructor are typically wrapped in `InvocationTargetException`; you can inspect the cause with `getCause()`.

Do not attempt to instantiate a record by creating an object and setting fields via reflection. Use the canonical constructor to ensure the invariants defined by the record are enforced.

## 12. Writing a general helper to describe a record

You can combine `isRecord()`, `getRecordComponents()`, `getGenericType()`, and accessors into a description function:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.stream.Collectors;

static String describe(Class<?> type) {
    if (!type.isRecord()) {
        return type.getName() + " (not a record)";
    }

    String components = Arrays.stream(type.getRecordComponents())
            .map(component ->
                    component.getName()
                            + ": "
                            + component.getGenericType().getTypeName()
            )
            .collect(Collectors.joining(", "));

    return type.getName() + "(" + components + ")";
}
```

Example:

```java
record Employee(String name, int level) {
}

System.out.println(describe(Employee.class));
```

Output:

```text
Employee(java.lang.String name, int level)
```

A record-describing helper can be useful in logs, diagnostic tools, or schema-generation utilities. In production applications, do not use this descriptive string as a stable serialization format without defining versioning and compatibility rules.

## 13. Record reflection in a modular environment

The Record Reflection API does not bypass the access rules of the Java Platform Module System.

Some points to distinguish:

- `isRecord()` and `getRecordComponents()` provide type information and component metadata.
- `getAccessor()` returns the accessor method; invoking the method via reflection still follows standard access rules.
- If a public record resides in an exported package, other modules can use its public API according to readability and access rules.
- If a framework needs deep reflection access to private members, the package may need to be opened to the framework module using `opens`.
- Do not open a package merely to read record metadata; identify the exact reflective operation that requires additional access.

For example, a record in a library module:

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

```java
package com.acme.model.api;

public record UserView(String name, int age) {
}
```

Client module:

```java
module com.acme.client {
    requires com.acme.model;
}
```

The client can use the public record and accessors because the package is exported. If a framework needs to read private implementation details via deep reflection, that is a separate requirement and should be evaluated with `opens` targeting the appropriate module.

### Do not use reflection to modify component fields

Record component fields are final and do not support reflective writes. Even if code can reflectively access a field for reading, attempting to mutate a record's field value is not a supported mechanism for updating records.

The proper design is to create a new record instance:

```java
record Person(String name, int age) {
}

Person original = new Person("Lan", 25);

Person updated = new Person(
        original.name(),
        26
);
```

Records represent value-based data; when a different state is needed, create a new instance rather than trying to mutate the components of an existing one.

## 14. Common mistakes

| Symptom or mistake | Cause | How to handle |
| --- | --- | --- |
| Calling `getRecordComponents().length` directly on any class | The method returns `null` if the class is not a record. | Check `isRecord()` or check for `null` before iterating. |
| Treating `null` and an empty array as the same case | A record with no components returns an empty array; a non-record returns `null`. | Handle the two cases separately. |
| Using field count to count components | A record can have extra static fields; fields and components are different metadata. | Use `getRecordComponents()`. |
| Casting `getGenericType()` to `Class<?>` | `Type` can be a `ParameterizedType` or `TypeVariable`. | Handle the appropriate `Type` implementations. |
| Invoking an accessor without an instance | `Method.invoke()` requires a target object for instance methods. | Pass a valid record instance to `invoke()`. |
| Thinking `getRecordComponents()` returns object values | The API only returns type metadata. | Invoke the accessor on an instance to obtain its value. |
| Assuming annotations always appear on field, accessor, and parameter | Annotation propagation depends on `@Target`. | Read the annotation from the right element and declare the needed targets. |
| Assuming annotations automatically run validation | Annotations are only metadata. | Use a framework or code that reads annotations and enforces rules. |
| Trying to reassign a record component field via reflection | Record component fields are final and do not support reflective writes. | Create a new record instance through the canonical constructor. |
| Using record reflection APIs on older JDKs | `isRecord()` and `getRecordComponents()` did not exist before Java 16. | Use JDK/API 16+; for this lesson, compile with Java 17. |

## 15. Practice exercises

### Exercise 1 — Identifying records

Create a record `Book(String title, String author)` and a regular class `Library`. Use `isRecord()` to print which type is a record and which is not.

### Exercise 2 — Reading components in order

Use `getRecordComponents()` on:

```java
record Address(String city, String district, int postalCode) {
}
```

Print the index, component name, and type of each component. Verify that the metadata order matches the record header.

### Exercise 3 — Handling non-records and empty records

Try `String.class.getRecordComponents()` and `Marker.class.getRecordComponents()` with `record Marker() {}`. Explain why one result is `null` and the other is an empty array.

### Exercise 4 — Reading values with accessors

Create `record Product(String code, int quantity)` and an instance of it. Iterate over the components, retrieve `getAccessor()`, and use `invoke(instance)` to print the name and value.

### Exercise 5 — Distinguishing generic types

Create:

```java
record Page<T>(List<T> items, int pageNumber) {
}
```

Compare `getType()` and `getGenericType()` for the `items` component. Identify what information is lost to type erasure and what is preserved in the generic signature.

### Exercise 6 — Reading annotations

Create an annotation with `RetentionPolicy.RUNTIME` and `Target(ElementType.RECORD_COMPONENT)`. Apply it to a component, then use `isAnnotationPresent()` and `getAnnotation()` to read it.

### Exercise 7 — Instantiating via canonical constructor

Use metadata from `getRecordComponents()` to build an array of parameter types, retrieve the canonical constructor with `getDeclaredConstructor(...)`, and instantiate a record with `newInstance(...)`. Test with a record that has validation to observe `InvocationTargetException` when invalid data is passed.

## 16. Quick reference

| Need | API |
| --- | --- |
| Check whether a type is a record | `type.isRecord()` |
| Get component metadata | `type.getRecordComponents()` |
| Get component name | `component.getName()` |
| Get runtime type | `component.getType()` |
| Get generic type | `component.getGenericType()` |
| Get annotated type | `component.getAnnotatedType()` |
| Get accessor | `component.getAccessor()` |
| Get declaring record | `component.getDeclaringRecord()` |
| Check for annotation | `component.isAnnotationPresent(Annotation.class)` |
| Read annotation | `component.getAnnotation(Annotation.class)` |
| Read value on an instance | `component.getAccessor().invoke(recordInstance)` |
| Find canonical constructor | `type.getDeclaredConstructor(componentTypes)` |

**Core principle:** Use `Class.isRecord()` to accurately determine whether a type is a record; use `Class.getRecordComponents()` to read each component's name, order, type, generic metadata, annotations, and accessor. This method returns `null` for non-record classes and an empty array for records without components. Metadata describes the type structure; to retrieve values you must invoke accessors on an instance, and to create records you must go through a constructor so record invariants are preserved.
