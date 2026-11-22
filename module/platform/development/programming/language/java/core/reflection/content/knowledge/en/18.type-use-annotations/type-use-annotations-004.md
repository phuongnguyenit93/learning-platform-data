# `AnnotatedArrayType` and Annotations on Array Dimensions — Java Reflection

## 1. The problem: a multidimensional array has multiple annotation positions

In Java, an annotation with `@Target(ElementType.TYPE_USE)` can be placed **on the element type** or **on each dimension of the array type**. Example:

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] matrix;
~~~

Suppose `@Pos` is a `TYPE_USE` annotation retained at runtime. The declaration above has three independent positions:

- `@Pos("outer")`: the **outermost array** position, with underlying type `String[][]`.
- `@Pos("inner")`: the **component array** position, with underlying type `String[]`.
- `@Pos("element")`: the **final element type** position, with underlying type `String`.

If you only call `Field.getType()` or `Field.getGenericType()`, you receive the type structure but **cannot query annotations separately at each dimension**. Java Reflection represents this tree using `AnnotatedType`, specifically `AnnotatedArrayType` nodes.

**Rule to remember:** an `n`-dimensional array must be traversed through `n` `AnnotatedArrayType` nodes before reaching the element type, which may carry its own annotations.

## 2. What is `AnnotatedArrayType`?

`java.lang.reflect.AnnotatedArrayType` is a subinterface of `AnnotatedType` (since Java 8) describing an **array type-use position**, together with the type-use annotations of **that exact position**.

Two key operations:

~~~java
AnnotatedType root = field.getAnnotatedType();
Type underlying = root.getType();

if (root instanceof AnnotatedArrayType array) {
    AnnotatedType component =
            array.getAnnotatedGenericComponentType();
}
~~~

This is an illustrative snippet inside a method that has a `Field field` variable and `import java.lang.reflect.*`; it is not a standalone program.

- `root.getType()` returns the **underlying type** as a `java.lang.reflect.Type`. For `String[][]`, that value is typically the `Class` of the array type; for `T[]`, it can be a `GenericArrayType`.
- `root.getAnnotation(Pos.class)` queries annotations located at **the current root node**, without automatically collecting annotations from inner dimensions.
- `getAnnotatedGenericComponentType()` steps down **exactly one component type level**, while preserving type-use annotation metadata at the next level.
- After stepping through all dimensions, you reach the element type such as `String`, `int`, `T`, or `List<String>`. The final node is not necessarily an `AnnotatedArrayType`.
- `AnnotatedArrayType.getAnnotatedOwnerType()` returns `null`: an array type is not an owner-type case of a member class.

The Javadoc of `AnnotatedArrayType` is not limited to annotated arrays. Even when a dimension **has no annotations**, it can still be an `AnnotatedArrayType` node; in that case `getAnnotations().length == 0` and `getAnnotation(Pos.class) == null`.

## 3. Distinguishing annotations on the element vs. on `[]`

Compare these three declarations:

~~~java
@Pos("element") String[] first;
String @Pos("dimension") [] second;
@Pos("element") String @Pos("dimension") [] third;
~~~

Assume they are inside a class using an `@Pos` annotation with `TYPE_USE` and `RUNTIME`.

| Declaration | Annotation on `String[]` array node | Annotation on `String` element node |
| --- | --- | --- |
| `@Pos("element") String[] first` | None | `element` |
| `String @Pos("dimension") [] second` | `dimension` | None |
| `@Pos("element") String @Pos("dimension") [] third` | `dimension` | `element` |

**Placing an annotation before `String` is not equivalent to placing an annotation before `[]`.**

Code to inspect each location:

~~~java
AnnotatedType root = field.getAnnotatedType();
Pos onArray = root.getAnnotation(Pos.class);

AnnotatedType component =
        ((AnnotatedArrayType) root).getAnnotatedGenericComponentType();
Pos onElement = component.getAnnotation(Pos.class);
~~~

This example is only illustrative when `field` is an array field, `Pos` is available, and exceptions are declared/handled around the Reflection calls. Do not cast to `AnnotatedArrayType` when the field does not actually have an array type.

### With a two-dimensional array

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] matrix;
~~~

We traverse in this order:

~~~text
AnnotatedArrayType: String[][]   → @Pos("outer")
    │ getAnnotatedGenericComponentType()
    ▼
AnnotatedArrayType: String[]     → @Pos("inner")
    │ getAnnotatedGenericComponentType()
    ▼
AnnotatedType:      String      → @Pos("element")
~~~

The outer dimension is **the first node** returned by `Field.getAnnotatedType()`, not the last dimension. So do not reverse the annotation order when generating JSON schemas or error messages.

For three or more dimensions, apply the same recursive rule: each call to `getAnnotatedGenericComponentType()` peels off one outer array dimension and moves down to the next component type node.

## 4. At what level do you retrieve annotation metadata?

There are three different questions:

| Question | API |
| --- | --- |
| What type was the field declared with, ignoring generics? | `field.getType()` |
| What generic structure does the field have? | `field.getGenericType()` |
| Which type-use annotations are placed on array dimensions and the element? | `field.getAnnotatedType()`, then traverse `AnnotatedArrayType` |

A `Field` is also an `AnnotatedElement`, yet:

~~~java
field.getDeclaredAnnotations();
~~~

queries annotations declared **on the field itself**, without automatically collecting type-use annotations on `String` or each `[]`.

Even when `field.getDeclaredAnnotations()` returns an empty array, `field.getAnnotatedType()` and its child nodes can still contain annotations at type positions. That is not contradictory data; they describe **two different annotation targets**.

Note that `getAnnotatedType().getType()` returns `Type`, not always `Class<?>`. When working with generic array types like `T[]`, casting directly to `Class<?>` can cause a `ClassCastException`.

## 5. Complete Java 17+ program: traversing each array dimension

Save the following code into **`AnnotatedArrayDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class AnnotatedArrayDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Pos {
        String value();
    }

    static class Sample<T extends @Pos("bound") Number> {
        public @Pos("element") String
                @Pos("outer") [] @Pos("inner") [] matrix;

        public List<
                @Pos("member-element") String
                @Pos("member-dimension") []> groups;

        public T @Pos("generic-dimension") [] genericArray;

        public @Pos("return-element") String
                @Pos("return-dimension") [] echo(
                    @Pos("param-element") String
                    @Pos("param-dimension") [] words) {
            return words;
        }
    }

    static String ann(AnnotatedType type) {
        Pos p = type.getAnnotation(Pos.class);
        return p == null ? "-" : p.value();
    }

    static void walk(String label, AnnotatedType type) {
        int depth = 0;
        while (type instanceof AnnotatedArrayType array) {
            System.out.println(label + "[" + depth + "] "
                    + type.getType().getTypeName()
                    + " @" + ann(type));
            type = array.getAnnotatedGenericComponentType();
            depth++;
        }
        System.out.println(label + "[" + depth + "] "
                + type.getType().getTypeName()
                + " @" + ann(type));
    }

    public static void main(String[] args) throws Exception {
        Field matrix = Sample.class.getDeclaredField("matrix");
        walk("matrix", matrix.getAnnotatedType());
        System.out.println("field annotations="
                + matrix.getDeclaredAnnotations().length);

        Field groups = Sample.class.getDeclaredField("groups");
        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) groups.getAnnotatedType();
        walk("groups.arg",
                parameterized.getAnnotatedActualTypeArguments()[0]);

        Field generic = Sample.class.getDeclaredField("genericArray");
        System.out.println("generic underlying is GenericArrayType="
                + (generic.getAnnotatedType().getType()
                        instanceof GenericArrayType));
        walk("generic", generic.getAnnotatedType());

        TypeVariable<?> t = Sample.class.getTypeParameters()[0];
        System.out.println("T.bound @"
                + ann(t.getAnnotatedBounds()[0]));

        Method echo = Sample.class.getDeclaredMethod(
                "echo", String[].class);
        walk("return", echo.getAnnotatedReturnType());
        walk("parameter", echo.getAnnotatedParameterTypes()[0]);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AnnotatedArrayDemo.java
java AnnotatedArrayDemo
~~~

Stdout:

~~~text
matrix[0] java.lang.String[][] @outer
matrix[1] java.lang.String[] @inner
matrix[2] java.lang.String @element
field annotations=0
groups.arg[0] java.lang.String[] @member-dimension
groups.arg[1] java.lang.String @member-element
generic underlying is GenericArrayType=true
generic[0] T[] @generic-dimension
generic[1] T @-
T.bound @bound
return[0] java.lang.String[] @return-dimension
return[1] java.lang.String @return-element
parameter[0] java.lang.String[] @param-dimension
parameter[1] java.lang.String @param-element
~~~

### Full explanation

1. **`matrix`**: `walk` steps from `String[][]` down to `String[]`, then to `String`. The annotations at each node are `outer`, `inner`, and `element` respectively. Underlying type names are printed using `Type.getTypeName()`, independent of Reflection implementation `toString()`.
2. **`field annotations=0`**: the `@Pos` annotation only has target `TYPE_USE`. It attaches to parts of the **field type**, not as a declaration annotation on the `Field` object itself.
3. **`groups`**: the outermost type is `List<...>`, so the root is `AnnotatedParameterizedType`. You must enter `getAnnotatedActualTypeArguments()[0]` before encountering the `AnnotatedArrayType` representing `String[]`.
4. **`genericArray`**: the underlying type is `T[]`, represented by `GenericArrayType` rather than a `Class` of an array with a known concrete element type. Still, `AnnotatedArrayType` lets you step down from `T[]` to type variable `T`.
5. **`T.bound`**: `@Pos("bound")` is on the `T extends Number` declaration; it **does not automatically appear on every use of `T`**, so `generic[1]` has `@-`. Bounds must be retrieved via `TypeVariable.getAnnotatedBounds()`.
6. **Method**: `getAnnotatedReturnType()` and `getAnnotatedParameterTypes()` also preserve annotations per array dimension; this is not limited to fields.

This example inspects metadata without instantiating `Sample` and without reading array contents; Reflection reads the declared structure **without needing actual array values**.

## 6. Generic arrays, parameterized types, and component types

There are two kinds of arrays to distinguish when inspecting the underlying `Type`:

| Declaration | Root `AnnotatedType` | Root `getType()` is typically |
| --- | --- | --- |
| `String[][]` | `AnnotatedArrayType` | `Class` representing `String[][].class` |
| `int[]` | `AnnotatedArrayType` | `Class` representing `int[].class` |
| `T[]` in a generic class | `AnnotatedArrayType` | `GenericArrayType` |
| `List<String>[]` in a valid declaration | `AnnotatedArrayType` | `GenericArrayType` |
| `List<String[]>` | `AnnotatedParameterizedType` at root | `ParameterizedType`; the generic argument node is `AnnotatedArrayType` |

Case `List<String[]>`:

~~~text
AnnotatedParameterizedType: List<String[]>
    └── AnnotatedArrayType: String[]
            └── AnnotatedType: String
~~~

Whereas for `List<String>[]`:

~~~text
AnnotatedArrayType: List<String>[]
    └── AnnotatedParameterizedType: List<String>
            └── AnnotatedType: String
~~~

Key point: these two declarations **differ in where the array sits in the type tree**. One is **a list of arrays**; the other is **an array of lists**. Casting the root must be based on the actual structure, not on the field name or an assumption that "if generics are present, the root is `AnnotatedParameterizedType`."

When you want to count the dimensions of an array node, loop `while (type instanceof AnnotatedArrayType)` and count the steps downward. For a complex generic tree, full traversal requires additional branches for `AnnotatedParameterizedType`, `AnnotatedWildcardType`, and `AnnotatedTypeVariable`; `AnnotatedArrayType` alone only handles the path through the array dimensions.

## 7. Why not use `Class.getComponentType()` instead?

There are two similarly named APIs with different responsibilities.

`Class.getComponentType()`:

~~~java
Class<?> component = String[][].class.getComponentType();
// String[].class
~~~

returns **the component type `Class`** of a runtime array type. It does not preserve type-use annotations and cannot directly represent `T[]` with a generic underlying type.

`AnnotatedArrayType.getAnnotatedGenericComponentType()`:

~~~java
AnnotatedType node = field.getAnnotatedType();
AnnotatedType next =
        ((AnnotatedArrayType) node).getAnnotatedGenericComponentType();
~~~

returns **the `AnnotatedType` of the component type**, meaning you can still query annotations attached to the next dimension or the element type. In a schema analyzer that must preserve annotations by position, the second API is essential.

**Do not descend only through `getType()` and try to recover annotations:** annotation information is not encoded into the underlying `Class`, `ParameterizedType`, or `GenericArrayType`. You must walk the **`AnnotatedType` tree** alongside the `Type` tree.

## 8. Annotations on array brackets placed after the variable name

Java allows legacy array syntax with `[]` after the variable name, for example:

~~~java
// Not recommended for new code:
String[] names[];
~~~

This form can cause confusion about array dimension positions and annotations, especially when mixed with `[]` placed near the type. In new code, prefer putting all array dimensions in the **type** portion before the variable name:

~~~java
String[][] names;
~~~

When type-use annotations are present, place each annotation right next to the array dimension it describes:

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] names;
~~~

If you are analyzing source code of a library or code generator, do not infer annotation positions merely by counting `[]` strings in text; check the type at the use site according to Java rules and compiled metadata. Dimension ordering can be hard to read when brackets are placed after the variable name.

## 9. Pitfalls of `@Target` and `@Retention`

An annotation intended to be read at runtime in an **array type-use position** should have:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Pos {
    String value();
}
~~~

This is a declaration snippet requiring `import java.lang.annotation.*` and placement in a suitable Java context.

- `TYPE_USE` lets the annotation attach to the element type and array dimensions. `ElementType.FIELD` is only for field declaration positions and does not substitute for `TYPE_USE`.
- `RetentionPolicy.RUNTIME` is required if you want `AnnotatedType.getAnnotation()` to read the annotation while the JVM is running. `CLASS` still writes metadata to the class file, but it is not visible through normal runtime Java Reflection; `SOURCE` is not retained past compilation.
- `@Target({FIELD, TYPE_USE})` allows using the annotation in multiple positions. In that case you must determine accurately whether you want declaration metadata or type-use metadata.
- `AnnotatedType.getAnnotation(Pos.class)` checks only **the current node**. If it returns `null`, traverse the dimensions or corresponding generic arguments instead of concluding the entire field has no annotations.
- No call on `AnnotatedArrayType` makes the JVM automatically check whether array elements are `null`. Annotations are metadata; validation must be implemented separately by the application/framework.

## 10. Common mistakes when writing Reflection code

| Confusion | What is true |
| --- | --- |
| "`String[][]` is one array, just read annotations at the root." | It has **two dimensions**, requiring two `AnnotatedArrayType` nodes, then the element type. |
| "`@A String[]` and `String @A []` carry the same type-use meaning." | The first `@A` attaches to the element; the second attaches to the array dimension. |
| "`getAnnotatedGenericComponentType()` always returns `AnnotatedArrayType`." | After the last dimension, it can return the `AnnotatedType` of `String`, `T`, `List<...>`, etc. |
| "`AnnotatedArrayType.getType()` is always a `Class`." | `T[]` and arrays of a parameterized type can use `GenericArrayType`. |
| "An annotation on `T`'s bound automatically appears on `T[]`." | Bound annotations and annotations on a use of `T` are different positions. |
| "Reading `field.getDeclaredAnnotations()` shows annotations on `[]`." | You need `field.getAnnotatedType()` and to traverse array nodes. |
| "`getAnnotation()` on one dimension searches through all remaining dimensions." | It queries only the current node; you must recurse through components. |
| "No annotation in the result means the array type is unannotated." | You might be on the wrong node or the annotation lacks runtime retention. |
| "Type-use annotations will be automatically enforced by the JVM for validation." | Reflection only supplies metadata; application code must implement business rules. |

## 11. Array traversal pattern for applications

A utility that **only traverses the array path**, usable for any array field that may carry annotations on each dimension:

~~~java
static void visitArray(AnnotatedType type) {
    int dimension = 0;
    while (type instanceof AnnotatedArrayType array) {
        // Read annotations of the current array dimension here.
        // Example: type.getAnnotations(), type.getType().getTypeName()
        dimension++;
        type = array.getAnnotatedGenericComponentType();
    }

    // Reached the element type, which may still have its own annotations.
    // If it is an AnnotatedParameterizedType, you can continue traversing generics.
}
~~~

This is an illustrative method inside a class with `import java.lang.reflect.*`; `dimension` represents the number of array levels traversed so far, not an application-specific dimension index convention.

When designing a schema/validator:

1. Obtain `Field.getAnnotatedType()` or the equivalent API for method parameters, return types, and record components.
2. If the node is `AnnotatedArrayType`, read annotations at **the array dimension node**, then descend into `getAnnotatedGenericComponentType()`.
3. If the node is `AnnotatedParameterizedType`, enter `getAnnotatedActualTypeArguments()` to check arrays nested inside generic arguments.
4. If the node is `AnnotatedWildcardType` or `AnnotatedTypeVariable`, traverse bounds using the right APIs.
5. Separate reading metadata from **evaluating runtime data**. Type-use annotations do not validate array contents by themselves.
6. Check `instanceof` before casting, and do not equate the underlying `Type` with `AnnotatedType`.

## 12. Self-check questions

**Question 1.** Where are the annotations located in `@A String @B [] @C [] matrix`?  
`@B` is on the outer array dimension `String[][]`; `@C` is on the inner dimension `String[]`; `@A` is on the element type `String`.

**Question 2.** If `field.getAnnotatedType().getAnnotation(A.class)` does not see `@A`, does that mean there are no annotations on any array dimensions?  
**No.** The annotation may be on a child node; you must follow `getAnnotatedGenericComponentType()`.

**Question 3.** What kind of underlying `getType()` does `T[]` (where `T` is a type parameter) usually have?  
**`GenericArrayType`**. However, the root annotated node can still be `AnnotatedArrayType`.

**Question 4.** Does `List<String[]>` have an `AnnotatedArrayType` as its root?  
**No.** The root is `AnnotatedParameterizedType`; entering the type argument yields `AnnotatedArrayType`.

**Question 5.** Does `List<String>[]` have an `AnnotatedArrayType` as its root?  
**Yes.** This is an array of lists; its component is a parameterized type.

**Question 6.** Are `Class.getComponentType()` and `AnnotatedArrayType.getAnnotatedGenericComponentType()` interchangeable when per-dimension annotations are needed?  
**No.** The `Class` API does not preserve component type-use annotations; the `AnnotatedArrayType` API can preserve them.

**Question 7.** Can an annotation with `@Target(TYPE_USE)` but `@Retention(CLASS)` be read via `AnnotatedType.getAnnotation()` at runtime?  
**Not via standard runtime Reflection.** `RUNTIME` is required.

**Conclusion:** `AnnotatedArrayType` represents **each annotated level of an array type**. Call `getAnnotation()` at each node, then use `getAnnotatedGenericComponentType()` to step from outer dimensions to inner dimensions and finally to the element type. This avoids losing annotations when analyzing multidimensional arrays, generic arrays, or arrays inside generic arguments.

### Official references

- [JDK 17 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [JDK 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [JDK 17 — `Field.getAnnotatedType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType())
- [JLS 17 §10.1 — Array Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.1)
- [JLS 17 §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)