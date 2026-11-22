# Testing Annotations on Generics, Arrays, and Records in Java

## 1. Purpose and Scope

Annotations in Java are not limited to classes, methods, or fields. Since Java 8, `ElementType.TYPE_USE` allows attaching annotations at a **type-use position** (*type use*): generic type arguments, bound types, array component types, individual array dimensions, return types, and many other positions. Java 8 also supports `ElementType.TYPE_PARAMETER` for **type parameter declarations**. Since Java 16, records have been a standard feature, accompanied by `ElementType.RECORD_COMPONENT` and the `RecordComponent` reflection API.

When testing, a source line that “has an annotation” is not enough to prove that every reflection API will return that annotation. You must ask the right three questions:

1. Which **target** is the annotation placed on: `TYPE_USE`, `TYPE_PARAMETER`, `FIELD`, or `RECORD_COMPONENT`?
2. Is the annotation retained until **runtime**, and does the test use Java reflection or an annotation processor?
3. Is the test querying the **right metadata layer**: the declaration via `Field.getAnnotation(...)`, the generic argument via `AnnotatedParameterizedType`, the array dimension via `AnnotatedArrayType`, or the record component via `RecordComponent`?

This guide covers designing tests for the most commonly confused cases in **Java 17+**: annotations on generic declarations and bounds, annotations on generic type arguments, annotating one-dimensional/multi-dimensional arrays, record components, and distinguishing original metadata from metadata propagated by the compiler to related record members.

## 2. Two Target Groups: Declaration Annotations and Type-Use Annotations

`@Target` belongs to `java.lang.annotation` and determines where an annotation is allowed to be used. The directly relevant targets are:

| Target | Meaning | Example |
|---|---|---|
| `ElementType.TYPE_PARAMETER` | Declaration of a type parameter | `class Box<@TypeParamMark T> {}` |
| `ElementType.TYPE_USE` | Position where a type is used | `List<@TypeMark String>` |
| `ElementType.FIELD` | Field declaration | `@FieldMark String name;` |
| `ElementType.METHOD` | Method declaration | `@MethodMark String read()` |
| `ElementType.PARAMETER` | Method/constructor parameter declaration | `void f(@ParamMark String x)` |
| `ElementType.RECORD_COMPONENT` | Record component declaration | `record User(@ComponentMark String id) {}` |

Two examples of annotation type declarations:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParamMark {
    String value();
}
```

`TypeParamMark` describes the **declaration** `T` in `class Box<T>`. `TypeMark` describes a **type-use position**, such as `String` in `List<String>` or `Number` in the bound `T extends Number`. These are two metadata layers that can be independent of each other.

**Note on target overlap:** `TYPE_USE` also applies in certain type/type-parameter declaration contexts according to the Java specification. To make tests easy to explain, the examples below use annotation types **dedicated to a single target each**. Do not infer that an annotation appearing directly before the `String` keyword must necessarily be retrieved with `Field.getAnnotation`; it may be a type-use annotation.

## 3. Conditions for Annotation Visibility via Runtime Reflection

To test via Java reflection, the annotation type must have `@Retention(RetentionPolicy.RUNTIME)`. If only `SOURCE` is used, the metadata does not exist in the compiled class file; `CLASS` is still written to the class file, but it does not appear through the standard reflection API.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface RuntimeTypeMark {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE_USE)
@interface BytecodeTypeMark {
    String value();
}
```

These two declarations are standalone examples and require importing `Retention`, `RetentionPolicy`, `Target`, and `ElementType`.

Runtime tests:

- `getAnnotatedType()` / `getAnnotatedReturnType()` / `getAnnotatedBounds()` and related auxiliary APIs only see annotations matching `RUNTIME` retention.
- `RetentionPolicy.CLASS` can be checked using a class file inspection tool, such as `javap -v` or a bytecode parser.
- Not seeing an annotation via reflection does **not** prove the source is wrong; check the retention, target, and the object being queried first.

Attributes in the class file typically take the form of `RuntimeVisibleTypeAnnotations` and `RuntimeInvisibleTypeAnnotations` for type-use annotations. This differs from `RuntimeVisibleAnnotations`/`RuntimeInvisibleAnnotations` used for many declaration annotations. When analyzing bytecode, you need to look up the right attribute kind according to the annotated location.

## 4. Testing Generic Type Parameter Declarations

Example:

```java
class Repository<@TypeParamMark("entity-parameter") T> {
}
```

The annotation here describes the **type parameter `T` of class `Repository`** itself, not an object of type `T` at runtime. We read it via:

```java
import java.lang.reflect.TypeVariable;

TypeVariable<?> variable =
        Repository.class.getTypeParameters()[0];

TypeParamMark annotation =
        variable.getAnnotation(TypeParamMark.class);
```

`TypeVariable` implements `AnnotatedElement`, so it supports annotation-reading APIs. `getTypeParameters()` returns `TypeVariable` instances, which differs from `getGenericInterfaces()` or `Field.getAnnotatedType()`.

Another case:

```java
class Pair<
    @TypeParamMark("key") K,
    @TypeParamMark("value") V
> {
}
```

Tests should ensure:

- There are exactly **two** type variables.
- Their names are ordered as `K` then `V`.
- Each `TypeVariable` has the annotation with its corresponding value.
- If an annotation only targets `TYPE_PARAMETER`, do not assume the annotation will appear everywhere the user subsequently writes `K` or `V`.

An annotation on the declaration `T` is **not automatically propagated** to the type argument `String` in `Repository<String>`. These are two different contexts; if a type argument value is required to carry an annotation, the annotation must be written at that exact position.

## 5. Testing Annotations on Generic Bounds

Declaration:

```java
class NumericBox<T extends @TypeMark("upper-bound") Number> {
}
```

`@TypeMark` here is attached to the **type `Number` used as the upper bound**, not to `T` as a `TYPE_PARAMETER` declaration annotation.

Reading the correct location:

```java
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.TypeVariable;

TypeVariable<?> t =
        NumericBox.class.getTypeParameters()[0];

AnnotatedType bound = t.getAnnotatedBounds()[0];
TypeMark mark = bound.getAnnotation(TypeMark.class);
```

Points to verify:

1. `NumericBox.class.getTypeParameters()[0]` is the `TypeVariable` for `T`.
2. `getAnnotatedBounds()` returns the annotated bounds.
3. `bound.getAnnotation(TypeMark.class)` reads the annotation **attached to the `Number` bound**.

Do not call `t.getAnnotation(TypeMark.class)` and conclude that the bound is not annotated; that mistakenly queries the **declaration** of `T` instead of the **bound type**.

With multiple interface bounds:

```java
class ComparableBox<
    T extends @TypeMark("number") Number
        & @TypeMark("comparable") Comparable<T>
> {
}
```

`getAnnotatedBounds()` contains multiple entries corresponding to the declared bounds. Tests should verify the exact number of elements and the value on each bound in order, rather than merely checking whether “an annotation exists”.

## 6. Testing Generic Type Arguments with `AnnotatedParameterizedType`

This is a frequently overlooked case:

```java
import java.util.List;

class Messages {
    List<@TypeMark("message") String> values;
}
```

The annotation is not attached directly to the `values` field declaration. It resides on the **type argument `String` inside `List<String>`**.

The appropriate API:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;

Field field = Messages.class.getDeclaredField("values");

AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType argument =
        parameterized.getAnnotatedActualTypeArguments()[0];

TypeMark mark = argument.getAnnotation(TypeMark.class);
```

This is an illustrative snippet, assuming `TypeMark` has already been declared and the `NoSuchFieldException` exception is handled.

**Distinguishing the three APIs:**

| API | Returns | Primary Information |
|---|---|---|
| `field.getType()` | `Class<?>` | Generic-erased type at the field level (here `List.class`) |
| `field.getGenericType()` | `Type` | Generic structure, for example `List<String>` |
| `field.getAnnotatedType()` | `AnnotatedType` | Type structure **including type-use annotations** |

`field.getAnnotation(TypeMark.class)` does not query into the type argument inside `List<...>`. A test must properly read `AnnotatedParameterizedType` and then descend into `getAnnotatedActualTypeArguments()`.

### Nested Generics

Example:

```java
import java.util.Map;
import java.util.List;

class NestedMap {
    Map<@TypeMark("key") String,
        List<@TypeMark("item") Integer>> value;
}
```

The reflection structure is a tree:

```text
AnnotatedParameterizedType: Map
  ├── AnnotatedType: String
  │     └── @TypeMark("key")
  └── AnnotatedParameterizedType: List
        └── AnnotatedType: Integer
              └── @TypeMark("item")
```

If a test only checks annotations on the outermost `Map` or `List`, it will miss annotations nested deep inside the type arguments. The proper way to test is to traverse the tree of annotated types.

In a general-purpose application, you should check `instanceof AnnotatedParameterizedType` before casting, because the field might change from `List<String>` to a simple type, an array type, or a type variable in a future refactoring.

## 7. Testing Individual Array Dimensions: `AnnotatedArrayType`

Annotations on arrays can belong to an **array dimension** or to the **final element type**.

Example:

```java
class MatrixHolder {
    String @TypeMark("outer") []
           @TypeMark("inner") [] matrix;
}
```

`matrix` has type `String[][]`, but the `outer` annotation is attached to the **outer dimension** and `inner` to the **inner dimension**. Read via:

```java
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.Field;

Field field = MatrixHolder.class.getDeclaredField("matrix");

AnnotatedArrayType outer =
        (AnnotatedArrayType) field.getAnnotatedType();

AnnotatedArrayType inner =
        (AnnotatedArrayType) outer.getAnnotatedGenericComponentType();

TypeMark outerMark = outer.getAnnotation(TypeMark.class);
TypeMark innerMark = inner.getAnnotation(TypeMark.class);
```

This is an illustrative snippet; `TypeMark` must be declared and `NoSuchFieldException` must be handled when placing it in a program.

**Most important test:** the two values must reside at **two different `AnnotatedArrayType` levels**, not both at `field.getAnnotation(...)` or only at a single array level.

For a one-dimensional array:

```java
class OneDimension {
    String @TypeMark("array-dimension") [] names;
}
```

`field.getAnnotatedType()` is an `AnnotatedArrayType` with the `array-dimension` annotation, while `getAnnotatedGenericComponentType()` leads to the annotated type of `String`.

### Annotations on the Element Type Instead of the Array Dimension

```java
class AnnotatedComponent {
    @TypeMark("element") String[] names;
}
```

For an annotation with only `@Target(TYPE_USE)`, this position targets the **element type `String`**, not the `FIELD` declaration itself. To read it in a one-dimensional array:

```java
AnnotatedArrayType array =
        (AnnotatedArrayType) AnnotatedComponent.class
                .getDeclaredField("names")
                .getAnnotatedType();

TypeMark componentMark =
        array.getAnnotatedGenericComponentType()
             .getAnnotation(TypeMark.class);
```

Because the syntax looks very similar to a field declaration annotation, tests should deliberately separate an annotation type targeting only `TYPE_USE` from an annotation type targeting only `FIELD` in order to observe the exact metadata.

### Arrays of Generics

```java
class GenericArrayHolder {
    List<@TypeMark("item") String>
            @TypeMark("array") [] names;
}
```

Reflection tree:

```text
AnnotatedArrayType: array
  └── @TypeMark("array")
  └── AnnotatedParameterizedType: List
        └── AnnotatedType: String
              └── @TypeMark("item")
```

The test must navigate from `AnnotatedArrayType` to the `AnnotatedParameterizedType` component, and then into the actual type argument `String`.

## 8. A Record Component Is a Separate Metadata Location

Since Java 16, Java has **records** as a way to declare a data type containing components:

```java
record User(String id, int age) {}
```

A record typically has elements corresponding to:

- A **record component** in the record header.
- A corresponding separate field declared by the compiler.
- An accessor method such as `id()`.
- A parameter of the canonical constructor.

However, these are **different elements in the language and in reflection**. You should not call `Field.getAnnotation(...)` and assume it fully reflects annotations targeting only `RECORD_COMPONENT`.

Define a separate annotation declaration for components:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMark {
    String value();
}
```

Example:

```java
record User(
    @ComponentMark("identifier") String id,
    String displayName
) {}
```

Querying:

```java
import java.lang.reflect.RecordComponent;

RecordComponent[] components =
        User.class.getRecordComponents();

ComponentMark mark =
        components[0].getAnnotation(ComponentMark.class);
```

A more robust check should look up the component by `getName()` instead of always choosing index `0` when the test goal does not depend on order; for a fixed record declaration, `getRecordComponents()` returns components in record header order.

Two other important APIs:

- `User.class.isRecord()` indicates whether it is a record class.
- `component.getAnnotatedType()` provides annotation metadata on the **component's type**, unlike `component.getAnnotation(...)`, which queries annotations on the **record component declaration**.
- `component.getAccessor()` allows querying the corresponding accessor if the test also needs to check metadata on the method.
- `component.getGenericType()` provides generic type information for the component.

If only `@Target(RECORD_COMPONENT)` is used, do not expect that annotation to automatically appear on the field/accessor/constructor parameter because those other targets are not permitted.

## 9. Record Components with Type-Use Annotations and Generics

Two annotations can appear together in the record header while carrying different meanings:

```java
record Entry(
    @ComponentMark("key")
    @TypeMark("text-type")
    String key
) {}
```

Here:

- `@ComponentMark("key")` is a **record component declaration annotation**.
- `@TypeMark("text-type")` is an **annotation on the component's `String` type** because `TypeMark` only has `@Target(TYPE_USE)`.

Proper test:

```java
RecordComponent component =
        Entry.class.getRecordComponents()[0];

ComponentMark declaration =
        component.getAnnotation(ComponentMark.class);

TypeMark typeUse =
        component.getAnnotatedType()
                 .getAnnotation(TypeMark.class);
```

Both can be read if the retention is `RUNTIME`. Do not swap these two locations.

### Record Generics

```java
import java.util.List;

record Inbox(
    List<@TypeMark("record-argument") String> messages
) {}
```

Reading:

```java
RecordComponent component =
        Inbox.class.getRecordComponents()[0];

AnnotatedParameterizedType type =
        (AnnotatedParameterizedType) component.getAnnotatedType();

TypeMark argMark =
        type.getAnnotatedActualTypeArguments()[0]
            .getAnnotation(TypeMark.class);
```

Even though `Inbox` is a record, the generic type argument is still looked up through the same `AnnotatedParameterizedType` tree as a regular field.

### Arrays in Records

```java
record Batch(String @TypeMark("record-array") [] values) {}
```

`Batch.class.getRecordComponents()[0].getAnnotatedType()` can be cast to `AnnotatedArrayType` to read `record-array` on the array dimension, just like with a field.

**Key takeaway:** Records do not create a “different type-use annotation mechanism”. They additionally provide the **`RecordComponent` object**, from which the `AnnotatedType` types are reused according to the component's type structure.

## 10. When Are Annotations in a Record Propagated to the Field, Accessor, and Constructor?

According to Java record rules, certain annotations written on a record component can be **propagated** to the corresponding field, the implicitly declared accessor, or the formal parameter of the canonical constructor, **if the annotation type has appropriate targets**.

Example of a multi-target annotation:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Labelled {
    String value();
}

record Task(@Labelled("task-id") String id) {}
```

Because `Labelled` permits multiple targets, the compiler can emit the corresponding metadata on the elements implicitly declared by the record according to the specification rules.

However, you must distinguish between:

1. **Record component**: query `Task.class.getRecordComponents()`.
2. **Field**: `Task.class.getDeclaredField("id")`.
3. **Accessor**: `Task.class.getDeclaredMethod("id")`.
4. **Canonical constructor parameter**: obtain the `Constructor<?>` with the matching signature and then call `getParameters()` or `getParameterAnnotations()`.

**Do not generalize that every annotation on a record component appears in all four places.** Propagation depends on `@Target` and the specific element kind.

An advanced note: if you **explicitly declare an accessor** or **canonical constructor**, the propagation rules to explicit declarations have different conditions than for compiler-generated implicit members. When you need to guarantee the contract in those places, write dedicated tests for the actual record form used in your project; do not merely test a “shorthand” record and extrapolate.

To avoid confusion in the unit tests in this article, the runnable example in the next section uses one annotation **targeting only `RECORD_COMPONENT`** and one annotation **targeting only `TYPE_USE`**, so that each query reflects a clear intent.

## 11. Complete Java 17+ Program: Generics, Arrays, and Records

Create a **single file** named `AnnotationShapeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMark {
    String value();
}

class Samples<@ParamMark("T") T extends @TypeMark("bound") Number> {
    List<@TypeMark("argument") String> texts;

    String @TypeMark("outer") []
           @TypeMark("inner") [] matrix;
}

record Entry(
    @ComponentMark("name")
    @TypeMark("type")
    String name
) {}

public class AnnotationShapeDemo {
    private static String getValue(TypeMark mark) {
        if (mark == null) {
            throw new AssertionError("Missing TypeMark");
        }
        return mark.value();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        TypeVariable<?> parameter =
                Samples.class.getTypeParameters()[0];

        System.out.println("type parameter="
                + parameter.getAnnotation(ParamMark.class).value());

        AnnotatedType bound =
                parameter.getAnnotatedBounds()[0];

        System.out.println("bound="
                + getValue(bound.getAnnotation(TypeMark.class)));

        Field texts =
                Samples.class.getDeclaredField("texts");

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) texts.getAnnotatedType();

        AnnotatedType typeArgument =
                listType.getAnnotatedActualTypeArguments()[0];

        System.out.println("type argument="
                + getValue(typeArgument.getAnnotation(TypeMark.class)));

        Field matrix =
                Samples.class.getDeclaredField("matrix");

        AnnotatedArrayType outer =
                (AnnotatedArrayType) matrix.getAnnotatedType();

        AnnotatedArrayType inner =
                (AnnotatedArrayType) outer.getAnnotatedGenericComponentType();

        System.out.println("array outer="
                + getValue(outer.getAnnotation(TypeMark.class)));

        System.out.println("array inner="
                + getValue(inner.getAnnotation(TypeMark.class)));

        RecordComponent component =
                Entry.class.getRecordComponents()[0];

        System.out.println("record declaration="
                + component.getAnnotation(ComponentMark.class).value());

        System.out.println("record type="
                + getValue(component.getAnnotatedType()
                        .getAnnotation(TypeMark.class)));
    }
}
```

Compile and run from the directory containing the file using JDK 17 or newer:

```bash
javac AnnotationShapeDemo.java
java AnnotationShapeDemo
```

**Exact expected stdout:**

```text
type parameter=T
bound=bound
type argument=argument
array outer=outer
array inner=inner
record declaration=name
record type=type
```

### Analysis of Each Result

1. `ParamMark` is placed on the **declaration of `T`**: retrieved using `TypeVariable.getAnnotation(ParamMark.class)`.
2. `TypeMark("bound")` is placed on the `Number` type in the bound: must query `TypeVariable.getAnnotatedBounds()[0]`.
3. `TypeMark("argument")` is placed on `String` in `List<String>`: traversed via `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
4. The two `TypeMark` annotations on `matrix` belong to **two array levels**; from the outer `AnnotatedArrayType`, you must descend one more `AnnotatedArrayType` to see `inner`.
5. `ComponentMark` is a declaration annotation on the record component `name`.
6. `TypeMark("type")` describes the type of the record component; retrieved via `RecordComponent.getAnnotatedType()`.

`getValue(...)` throws an `AssertionError` if the expected type-use metadata is absent, preventing the lesson from silently printing `null` in cases of wrong target or retention.

There is no annotation processor or external library in this example. This is a **runtime reflection** test; all annotations have `RUNTIME` retention. Only `AnnotationShapeDemo` is a public top-level class and its name matches the file, so the remaining types can be declared in the same compilation unit.

## 12. Writing Assertions Instead of Only Inspecting Stdout

In test code, you should verify the **exact value** and reflection location, not just print to the console.

A simple helper without depending on JUnit:

```java
static void expect(String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected " + expected + " but got " + actual);
    }
}
```

This is an illustrative method to add **inside a test class**.

Instead of:

```java
System.out.println(typeArgument.getAnnotation(TypeMark.class));
```

you should write:

```java
TypeMark mark =
        typeArgument.getAnnotation(TypeMark.class);

if (mark == null) {
    throw new AssertionError("Missing annotation on type argument");
}

expect("argument", mark.value());
```

This approach detects both errors:

- Metadata is **absent**, usually due to the wrong `@Target`, retention, or reflection path.
- Metadata is **present but has the wrong value**, such as accidentally attaching the annotation to a different type argument.

If using JUnit 5, the principle remains the same: use `assertNotNull`, `assertEquals`, `assertArrayEquals`, and `assertThrows` appropriately. This article does not require a JUnit dependency because baseline tests can be written in plain Java.

### A Good Test Also Includes “Absence” Checks

For example, with `ComponentMark` targeting only `RECORD_COMPONENT`, you can verify it does not appear as a field annotation:

```java
Field field = Entry.class.getDeclaredField("name");
if (field.isAnnotationPresent(ComponentMark.class)) {
    throw new AssertionError("Unexpected field annotation");
}
```

This snippet is executed in a context where `NoSuchFieldException` is handled and uses the types defined in Section 11.

This negative test proves the code does not mistakenly read record component metadata as field declaration metadata. When the annotation type's target is extended to include `FIELD`, the expected result must be re-evaluated according to record annotation propagation rules.

## 13. Negative Test Cases for `@Target` and Syntax

### 13.1. Using a `TYPE_PARAMETER`-Only Annotation on a Type Argument

```java
import java.util.List;

// INTENTIONALLY WRONG: ParamMark only allows TYPE_PARAMETER.
class WrongGeneric {
    List<@ParamMark("bad") String> values;
}
```

`String` in `List<String>` is a **type argument use**, not a type parameter declaration. Use an annotation with `@Target(TYPE_USE)`, such as `@TypeMark("ok")`.

### 13.2. Using a `RECORD_COMPONENT`-Only Annotation on a Regular Field

```java
// INTENTIONALLY WRONG: ComponentMark only allows RECORD_COMPONENT.
class WrongField {
    @ComponentMark("bad")
    String name;
}
```

`name` here is a field in a class, not a record component. When the goal is to mark a field declaration, use an annotation with `@Target(FIELD)`.

### 13.3. Using `List<String>` as an Annotation Element Type

```java
import java.util.List;

// INTENTIONALLY WRONG: annotation elements do not accept List<String>.
@interface InvalidMetadata {
    List<String> values();
}
```

This is a different issue from **placing an annotation on a generic type argument**. Java allows `List<@TypeMark String>` at a type-use position, but **does not** allow an annotation element to return `List<String>`.

An annotation element may only return primitives, `String`, an appropriate `Class`, enums, annotations, or one-dimensional arrays of those types. Do not confuse “a generic type can carry type-use annotations” with “annotation elements support all generic types”.

### 13.4. Missing `@Retention(RUNTIME)` When Checking via Reflection

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface CompileOnlyMark {
}
```

Omitting `@Retention` means the default is `CLASS`. Testing with `getAnnotatedType().getAnnotation(CompileOnlyMark.class)` will not see the annotation, even though the bytecode may still contain class-file metadata.

### 13.5. Testing Arrays Using `field.getAnnotation`

```java
Field matrix = Samples.class.getDeclaredField("matrix");
TypeMark mark = matrix.getAnnotation(TypeMark.class);
```

`mark` is not the `outer` or `inner` value because they are annotations **on the dimensions of the array type**, not declaration annotations on `Field`. You must start with `matrix.getAnnotatedType()` and traverse the `AnnotatedArrayType` tree.

## 14. Deep Testing for Nested Generics and Nested Arrays

For a general-purpose library handling type-use annotations, you should not test only a single level of `List<String>`. Add sample data:

```java
import java.util.List;
import java.util.Map;

class ComplexTypes {
    Map<@TypeMark("map-key") String,
        List<@TypeMark("list-item") Integer>> nested;

    List<@TypeMark("element") String>
            @TypeMark("array") [] genericArray;

    @TypeMark("base") String @TypeMark("dimension") [] simpleArray;
}
```

Corresponding test cases:

| Position | Reflection Path |
|---|---|
| `"map-key"` | `AnnotatedParameterizedType(Map)` → arg 0 |
| `"list-item"` | `AnnotatedParameterizedType(Map)` → arg 1 (`List`) → arg 0 |
| `"array"` | Outermost `AnnotatedArrayType` |
| `"element"` | `AnnotatedArrayType` → component is `AnnotatedParameterizedType(List)` → arg 0 |
| `"dimension"` | Outermost `AnnotatedArrayType` |
| `"base"` | `AnnotatedArrayType` → `String` component |

If an annotation supports multiple positions, a single declaration can carry both an **element annotation** and an **array dimension annotation**. Tests must distinguish between those two locations.

An algorithm for traversing an annotated type tree typically needs branching:

```java
if (type instanceof AnnotatedArrayType arrayType) {
    // Process annotations on the array dimension.
    // Traverse arrayType.getAnnotatedGenericComponentType().
} else if (type instanceof AnnotatedParameterizedType parameterized) {
    // Process annotations on the generic type.
    // Traverse parameterized.getAnnotatedActualTypeArguments().
} else {
    // Check annotations at leaves or on other AnnotatedType forms.
}
```

This is an illustrative snippet inside a method that has an `AnnotatedType type` variable and the corresponding imports. A **complete** traverser must also account for `AnnotatedTypeVariable`, `AnnotatedWildcardType`, bounds, and owner types according to the generic structure. Do not assume that the two branches above cover every Java type form.

## 15. Testing Wildcards and Type Variables in Generics

The Java generics model is not limited to `List<String>`. Example:

```java
import java.util.List;

class Variance {
    List<? extends @TypeMark("upper") Number> upper;
    List<? super @TypeMark("lower") Integer> lower;
}
```

`? extends ...` and `? super ...` create an **annotated wildcard type**. Query following the structure:

1. `Field.getAnnotatedType()` → `AnnotatedParameterizedType` for `List`.
2. `getAnnotatedActualTypeArguments()[0]` → `AnnotatedWildcardType` for the wildcard.
3. `getAnnotatedUpperBounds()` or `getAnnotatedLowerBounds()` → annotated type of the bound.
4. `getAnnotation(TypeMark.class)` on the corresponding bound.

Distinguish an annotation **on the wildcard symbol**:

```java
List<@TypeMark("wildcard") ? extends Number> example;
```

from an annotation **on the bound type**:

```java
List<? extends @TypeMark("bound") Number> example;
```

For an accurate comparison, test both and verify whether the annotation resides on the `AnnotatedWildcardType` object or on an `AnnotatedType` returned from `getAnnotatedUpperBounds()`.

For a type variable used in a field's type:

```java
class Holder<@ParamMark("parameter") T> {
    @TypeMark("use") T item;
}
```

The annotation `ParamMark("parameter")` is attached to the **type parameter declaration `T`**; `TypeMark("use")` is attached to the **use position of `T` on the field**. Test both locations via two separate read paths: `Holder.class.getTypeParameters()[0].getAnnotation(ParamMark.class)` and `Holder.class.getDeclaredField("item").getAnnotatedType().getAnnotation(TypeMark.class)`.

## 16. Record Annotations and Propagation Tests

When using an annotation with multiple targets, the record header can affect metadata on **multiple generated elements**.

Example:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface VisibleAt {
    String value();
}

record Order(@VisibleAt("id") String id) {}
```

An integration test suite can place four independent checks:

- `Order.class.getRecordComponents()[0].getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredField("id").getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredMethod("id").getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredConstructor(String.class).getParameters()[0].getAnnotation(VisibleAt.class)`.

For records **that do not explicitly redefine the accessor/canonical constructor**, Java's record rules govern annotation propagation depending on the target. If there is an **explicit** accessor or constructor, write a separate test because propagation should not be assumed to be the same for all declaration forms.

To avoid hard-to-detect regressions:

1. Test **record declaration** and **type-use** separately.
2. Test the implicitly generated elements corresponding to the target.
3. If the developer explicitly writes an accessor/canonical constructor, test the **explicit version**.
4. Do not use `getDeclaredFields()` and assume every field is the “source of truth” for record component metadata.
5. Do not discard information attached to `RecordComponent` just because a serializer library only scans fields.

## 17. Compile-Time and Bytecode Testing Alongside Runtime

Reflection works well for annotations with `RUNTIME` retention, but it does not represent the entire behavior of the Java compiler.

### Compile-Time Testing with an Annotation Processor

If an annotation only has `SOURCE` retention, you can use an annotation processor (JSR 269) to inspect `TypeElement`, `Element`, `AnnotationMirror`, or types represented by `TypeMirror` during compilation. This is suitable when a project needs to check source metadata, generate code, or validate generic/record structures early.

Things to keep in mind:

- `RoundEnvironment.getElementsAnnotatedWith(...)` primarily queries annotations on **elements** according to processor rules; it does not automatically replace traversing every **type-use annotation** nested deep inside generic arguments and arrays.
- To test annotations on type uses, check `TypeMirror.getAnnotationMirrors()` on the **right TypeMirror** and use `Types`/`Elements` to traverse the type structure.
- For a processor to receive work, it must be registered/invoked; having `@Retention(SOURCE)` alone does not automatically create a test.
- `Filer` generates new files and `Messager` reports diagnostics; they are not runtime reflection APIs.

### Class-File Testing

When an annotation has `CLASS` retention, `javap -v` helps confirm that the compiler wrote the annotation into the class file:

```bash
javap -v Samples
javap -v Entry
```

In the output, look for `RuntimeInvisibleTypeAnnotations` for `TYPE_USE` with `CLASS` retention and `RuntimeVisibleTypeAnnotations` when `RUNTIME`. Declaration annotations may reside in other attributes, such as `RuntimeVisibleAnnotations`. For records, the class file also has a structure related to the `Record` attribute.

**Caution:** `javap -v` displays class file and constant pool details, which is not a stable interface to test by matching the entire stdout verbatim across all JDK versions. Check the required metadata content/target instead of relying on constant-pool indices or printed line positions.

## 18. Common Errors Table and How to Fix Them

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `Field.getAnnotation` returns `null` for `List<@Mark String>` | The annotation is on the type argument, not the field declaration | `Field.getAnnotatedType()` → `AnnotatedParameterizedType` → arg |
| Array annotation “loses a dimension” | Only the outer `AnnotatedArrayType` is read | Continue traversing `getAnnotatedGenericComponentType()` |
| Generic bound annotation does not appear on `TypeVariable` | Reading the declaration instead of the bound | Use `getAnnotatedBounds()` |
| `TYPE_PARAMETER` annotation is not seen on `List<String>` | Confusing the declaration `T` with the use `String` | Read `Class.getTypeParameters()` |
| Record component annotation is not seen on the field | The annotation only targets `RECORD_COMPONENT` | Read `RecordComponent.getAnnotation` |
| Record type-use annotation is not seen via `RecordComponent.getAnnotation` | Metadata is on the component's type | Use `RecordComponent.getAnnotatedType()` |
| Java 17 test fails to compile with record | Record syntax is not supported by an older JDK/lower source level | Check `java -version`, `javac -version`, `--release` |
| Annotation is visible in source but not seen by reflection | `SOURCE`/`CLASS` retention or wrong target | Check `@Retention`, `@Target`, bytecode |
| `ClassCastException` when casting `AnnotatedType` | Assuming every field is parameterized/array | Use `instanceof` before casting |
| Test depends on reflection method order | `getDeclaredMethods()` does not guarantee an order suitable for tests | Sort or select methods by name |
| Annotation on a generic type argument is ignored in a processor | Only scanning elements without traversing TypeMirror | Traverse the appropriate type tree |
| User-written record accessor has unexpected metadata | Confusing implicit/explicit member propagation | Write a dedicated test for explicit accessors/constructors |

Other errors can appear when the generic signature or annotation type cannot be loaded during reflection. In that case, check the classpath, class loader, dependency versions, and compiler output instead of assuming the API always returns an empty array.

## 19. Recommended Testing Workflow for Real-World Projects

A robust test suite can be organized into three layers:

**Layer 1 — Compilation Tests:** verify valid/invalid `@Target`, class names, generic signatures, and record syntax; if there is a processor, verify appropriate diagnostics. Intentionally invalid snippets must reside in **separate negative test files**, not in the normal runnable demo suite.

**Layer 2 — Reflection Tests:** for `RUNTIME` retention, create small fixtures containing each case and read the exact `AnnotatedType`/`RecordComponent` tree. Assertions should check the annotation value, count, location, and absence cases.

**Layer 3 — Integration Tests:** if a mapper, serializer, or DI framework reads metadata, actually test that consumption path. An annotation being present via reflection does not prove the framework automatically applies the expected behavior.

Suggested minimal fixture list:

1. A generic type parameter with `@Target(TYPE_PARAMETER)`.
2. A generic bound with `@Target(TYPE_USE)`.
3. A `List<@Mark String>` and a nested `Map<K, List<V>>`.
4. A one-dimensional array with an annotation on the array dimension.
5. A two-dimensional array with an annotation on each dimension.
6. An annotation on the array's element type, not the dimension.
7. A record component with `@Target(RECORD_COMPONENT)`.
8. A record component with a type-use annotation on its type.
9. A generic/array record with an annotation on the type argument/dimension.
10. A record with an explicit accessor/canonical constructor if the project uses them.
11. A `CLASS` annotation checked only via bytecode, not via runtime reflection.
12. A fixture with an invalid `@Target` used as a negative compilation test.

For each fixture, give it a clear name such as `GenericArgumentCase`, `ArrayDimensionsCase`, or `RecordComponentCase` and document the **reflection path that the test intends to traverse**. This ensures the test reflects the source intent rather than accidentally passing because an annotation appears at another position.

## 20. Self-Check Exercises

Consider the following declarations:

```java
import java.util.List;

class Example<
    @ParamMark("P") T extends @TypeMark("B") Number
> {
    List<@TypeMark("A") String> items;
    String @TypeMark("D1") [] @TypeMark("D2") [] matrix;
}

record RecordExample(
    @ComponentMark("RC")
    List<@TypeMark("G") String> values
) {}
```

Assume `ParamMark` targets `TYPE_PARAMETER`; `TypeMark` targets `TYPE_USE`; `ComponentMark` targets `RECORD_COMPONENT`; all three have `RUNTIME` retention.

Determine:

1. To read `"P"`, which API must you start with?
2. To read `"B"`, should you query the annotation on `T` directly or on the annotated bound?
3. To read `"A"` in `items`, why is `Field.getAnnotation(TypeMark.class)` insufficient?
4. Do `"D1"` and `"D2"` reside in one or two `AnnotatedArrayType` objects?
5. What value does `RecordExample.class.getRecordComponents()[0].getAnnotation(ComponentMark.class)` return?
6. To read `"G"` in `RecordExample.values`, you must use `RecordComponent.getAnnotatedType()` and then which API next?
7. If `TypeMark` changes its retention to `CLASS`, will `Field.getAnnotatedType().getAnnotation(TypeMark.class)` still read `"A"` at runtime?
8. Can you declare an annotation element `List<String> tags();` just because Java generics support `List`?
9. If `matrix` becomes a one-dimensional array, is casting the second level to `AnnotatedArrayType` still valid?
10. When an annotation only targets `RECORD_COMPONENT`, should you always expect to find it on the `values()` accessor?

**Answers:**

1. `Example.class.getTypeParameters()[0].getAnnotation(ParamMark.class)`.
2. `TypeVariable.getAnnotatedBounds()[0].getAnnotation(TypeMark.class)`.
3. Because `"A"` is on the **type argument `String`**, `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` is needed.
4. **Two `AnnotatedArrayType` levels**: outer and inner.
5. The value `"RC"`.
6. `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` to access `String`.
7. **No.** `CLASS` retention does not appear through standard runtime reflection.
8. **No.** Annotation element types have a restricted set of types, which does not include `List`.
9. **No.** You must check the annotated type structure before casting.
10. **No.** An annotation targeting only `RECORD_COMPONENT` is not treated as a method declaration annotation on the accessor.

## 21. End-of-Article Checklist

- [ ] Know whether the annotation targets a declaration or a type use.
- [ ] Choose `@Target(TYPE_PARAMETER)` properly for type parameter declarations and `TYPE_USE` for generic arguments/bounds/array dimensions.
- [ ] Set `@Retention(RUNTIME)` if checking via reflection; use a bytecode tool when checking `CLASS` metadata.
- [ ] Read type parameter annotations via `TypeVariable`.
- [ ] Read generic bounds via `TypeVariable.getAnnotatedBounds()`.
- [ ] Read type arguments via `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.
- [ ] Read wildcard bounds using `AnnotatedWildcardType` if wildcards are present.
- [ ] For multi-dimensional arrays, traverse each `AnnotatedArrayType` via `getAnnotatedGenericComponentType()`.
- [ ] Distinguish annotations on the **array dimension** from annotations on the **element type**.
- [ ] For records, use `Class.getRecordComponents()` and `RecordComponent.getAnnotation(...)` when the annotation targets the declaration.
- [ ] Read record component type-use annotations via `RecordComponent.getAnnotatedType()`.
- [ ] If testing propagation, verify the exact target and distinguish implicit vs. explicit accessors/constructors.
- [ ] Write assertions for values, counts, positions, and absence cases.
- [ ] Place intentionally invalid examples in separate negative compilation tests rather than mixing them with runnable fixtures.
- [ ] Do not infer that a framework will understand an annotation just because reflection can read it.
- [ ] Avoid tests relying on an order not guaranteed by the API; look up fields/methods/components by their appropriate names.
- [ ] Run with a source level/JDK that supports records (Java 17 is a stable choice).
- [ ] Check compile-time, class-file, and runtime according to the annotation's intended purpose.

## 22. Reference Documentation

- [Java SE 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): common interface for annotations at type-use positions.
- [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): annotated type arguments of generics.
- [`AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html): annotations on array dimensions and navigating to the component type.
- [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): record component metadata, annotated type, and accessor.
- [JLS Java 17 — Chapter 9](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): annotation types, `@Target`, and where annotations may appear.
- [JLS Java 17 — Section 8.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record classes and related members.

**In summary:** Testing annotations on generics, arrays, and records requires checking the **metadata location**, not merely checking that “an annotation was attached”. `TYPE_PARAMETER` and `TYPE_USE` exist at two different layers; arrays have separate dimensions; records have component declarations distinct from type-use annotations. When `AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType`, and `RecordComponent` are used properly, tests become transparent, rigorous, and more resilient against regressions.
