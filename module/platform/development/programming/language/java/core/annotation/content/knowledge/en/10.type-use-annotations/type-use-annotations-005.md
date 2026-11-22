# Annotations on the Element Type and Each Dimension of an Array in Java

A Java array can carry metadata not only at the variable declaration, but also at **each level of the array type**. For the type `String[][]`, there are three type-use positions to distinguish: **the element type `String`**, **the two-dimensional array `String[][]`**, and **the one-dimensional array `String[]` inside it**. Since Java 8, annotations with `@Target(ElementType.TYPE_USE)` can mark each of these positions individually.

This is an important case of *type annotations*: placing an annotation **before the type name** versus **before each pair of `[]`** carries different meanings. In particular, an annotation immediately before `String` does not automatically mean that “the entire `String[][]` array is annotated”.

## 1. Why Distinguish Between the Element Type and Each Dimension of an Array?

Consider the variable:

```java
String[][] matrix;
```

This type can be read across three levels:

```text
matrix
  └─ String[][]        ← Type of matrix: outer array (2-dimensional)
       └─ String[]      ← Type of each element in the outer array: inner array
            └─ String   ← Element type at the final level
```

A reference of type `String[][]` can point to the outer array; each element of the outer array is a reference of type `String[]`; each element of the inner array is a reference of type `String`. These are **three distinct type positions** that a static analysis tool may need to distinguish.

Suppose a nullness-checking library wants to describe:

- The reference to the **outer array** must not be `null`.
- Each **sub-array** (row) must not be `null`.
- The **strings** in each row must not be `null`.

Those are three independent requirements. Java does not enforce these rules automatically just because the code has annotations; a checker or library must understand and apply the corresponding metadata. However, the language syntax allows us to place markers at each exact position so the checker has accurate information.

For a one-dimensional array `String[]`, there are only two levels to distinguish: `String[]` and `String`.

## 2. Standard Syntax: Annotations Placed Immediately Before the Marked Type Component

Suppose three annotation types `@ElementMark`, `@OuterMark`, and `@InnerMark` all have `@Target(ElementType.TYPE_USE)`. The following snippet illustrates **annotation placement**:

```java
@ElementMark String @OuterMark [] @InnerMark [] matrix;
```

Standard interpretation:

| Syntactic component | Annotated type | Position meaning |
| --- | --- | --- |
| `@ElementMark String` | `String` | Final element type. |
| `@OuterMark []` (first `[]`) | `String[][]` | Type of the **outer array**. |
| `@InnerMark []` (second `[]`) | `String[]` | **Sub-array** type, which is the component type of the outer array. |

The rule in the Java Language Specification is: **an annotation placed before a pair of `[]` attaches to the array type level represented by that pair of brackets**. In the standard syntax where brackets follow the type name, the first pair from left to right corresponds to the outermost array.

We can compare four declarations (these are illustrative snippets assuming the annotations target `TYPE_USE`):

```java
@ElementMark String[][] a;        // Marks the element type String
String @OuterMark [][] b;         // Marks the outer array String[][]
String[] @InnerMark [] c;         // Marks the sub-array String[]
@ElementMark String @OuterMark [] @InnerMark [] d; // Marks all three levels
```

**Do not guess the position from the annotation name.** An annotation named `@NonNull` placed before `String` marks the **element type**; if placed before the first `[]`, it marks the **outer array type**. Actual null-checking behavior is still determined by the tool consuming the annotation.

## 3. Valid Type Annotation Declarations

To use annotations in positions inside an array type, define the annotation type with `ElementType.TYPE_USE`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ElementLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface DimensionLabel {
    String value();
}
```

Here:

- `@Target(TYPE_USE)` permits placing the annotation on a type use, including the element type and each array level.
- `@Retention(RUNTIME)` preserves metadata in the class file and allows parts of Java Reflection to read it at runtime.
- `value()` is an annotation element for storing a descriptive string; the values `"outer"`, `"inner"`, and `"cell"` are for illustration only and are not interpreted by Java as built-in rules.

If changed to `@Target(ElementType.FIELD)` alone, the annotation targets **field declarations** and is not eligible to be written at `[]` positions or to annotate the element type. To support both purposes, you can declare `@Target({ElementType.FIELD, ElementType.TYPE_USE})`, but you must understand that they are two independent contexts.

An annotation that does not declare a retention defaults to `CLASS`; reflecting on type annotations at runtime in the example below requires `RUNTIME`.

## 4. Complete Java 17+ Example: Reading All Three Levels Separately with Reflection

Create a file named exactly **`ArrayTypeAnnotationDemo.java`** and place all of the following code into it:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ElementLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface DimensionLabel {
    String value();
}

class DataGrid {
    @ElementLabel("cell")
    String @DimensionLabel("outer") [] @DimensionLabel("inner") [] cells;
}

public class ArrayTypeAnnotationDemo {
    public static void main(String[] args) throws Exception {
        Field field = DataGrid.class.getDeclaredField("cells");

        AnnotatedType outer = field.getAnnotatedType();
        AnnotatedType inner =
                ((AnnotatedArrayType) outer).getAnnotatedGenericComponentType();
        AnnotatedType element =
                ((AnnotatedArrayType) inner).getAnnotatedGenericComponentType();

        System.out.println("type=" + field.getType().getTypeName());
        System.out.println("outer=" +
                outer.getAnnotation(DimensionLabel.class).value());
        System.out.println("inner=" +
                inner.getAnnotation(DimensionLabel.class).value());
        System.out.println("element=" +
                element.getAnnotation(ElementLabel.class).value());
        System.out.println("allocated=" + (new String[2][3]).length);
    }
}
```

Run in the directory containing the file with JDK 17 or later:

```bash
javac -encoding UTF-8 ArrayTypeAnnotationDemo.java
java ArrayTypeAnnotationDemo
```

**Exact stdout:**

```text
type=java.lang.String[][]
outer=outer
inner=inner
element=cell
allocated=2
```

This example has been tested to compile and run on JDK 21, and uses only features available in Java 17.

### Why Does the Output Look Like That?

1. `DataGrid.cells` has the underlying Java type `String[][]`. Attaching annotations at type levels **does not turn it into a new array type**, so `field.getType().getTypeName()` remains `"java.lang.String[][]"`.
2. `field.getAnnotatedType()` returns an `AnnotatedType` representing the **outermost type**, which is `String[][]` marked with `@DimensionLabel("outer")`.
3. Since this is an array, that object can be treated as an `AnnotatedArrayType`. Calling `getAnnotatedGenericComponentType()` once steps down **one level** to the type `String[]`, which holds `@DimensionLabel("inner")`.
4. Calling it again navigates to the **`String`** type, which holds `@ElementLabel("cell")`.
5. `getAnnotation(DimensionLabel.class)` or `getAnnotation(ElementLabel.class)` is called on the **exact `AnnotatedType` object for each level**; that is why the same annotation type `DimensionLabel` yields two different values.
6. `new String[2][3]` allocates an outer array of length `2` (two rows), each row of length `3`. Type annotations on the field do not change the allocation or length, and this expression does not automatically inherit metadata from the field.

**Important:** `Field.getAnnotations()` is intended to retrieve annotations on the **field declaration**; it cannot replace `Field.getAnnotatedType()` when you need to inspect annotations on the element type or individual `[]` levels. For this task, you must access the **annotated type structure**.

## 5. Distinguishing Outer Array, Inner Array, and Final Element

Example:

```java
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] matrix;
```

`matrix` has type `String[][]`. Suppose there is a checker that understands the annotation meaning:

- `@DimensionLabel("outer")` attaches to the type `String[][]`, the type of the **variable `matrix`**.
- `@DimensionLabel("inner")` attaches to the type `String[]`, the type of **`matrix[i]`**.
- If `@ElementLabel("cell")` is also placed immediately before `String`, that annotation attaches to the type of **`matrix[i][j]`**.

In the example, `DimensionLabel` and `ElementLabel` themselves only store text; Java does not use `"outer"` or `"inner"` to forbid null values. Annotation placement and verification capability are two separate matters.

For a **three-dimensional** array:

```java
String @DimensionLabel("3D") []
       @DimensionLabel("2D") []
       @DimensionLabel("1D") [] cube;
```

From left to right, the three pairs of `[]` correspond to the three levels `String[][][]`, `String[][]`, and `String[]`. An annotation before the name `String`, if present, still targets the **final element type `String`**.

You can read each level by repeatedly calling `AnnotatedArrayType.getAnnotatedGenericComponentType()` until encountering an `AnnotatedType` that is no longer an array. If the type has only one dimension, there is exactly **one** step down from the array type to the element type.

## 6. Annotations on Array Creation Expressions

Type annotations can also appear in **array creation expressions**, before each dimension size, with a syntax slightly different from variable declarations:

```java
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] data =
        new String @DimensionLabel("outer") [2]
                   @DimensionLabel("inner") [3];
```

On the left-hand side, `[]` declares the array type levels; on the right-hand side, `[2]` and `[3]` allocate each dimension. The annotation stands **immediately before the `[`** of the corresponding dimension.

If you need to annotate the element type in an array creation expression:

```java
@ElementLabel("cell")
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] data =
        new @ElementLabel("cell")
            String @DimensionLabel("outer") [2]
                   @DimensionLabel("inner") [3];
```

These are standalone syntax illustration snippets; they assume `ElementLabel` and `DimensionLabel` are declared as in Section 3. The variable declaration and the `new` expression are **two separate type-use contexts**. Java does not automatically copy a type annotation from the declaration to the array creation expression; writing the annotation on either side is a choice made in the source code on that side.

When creating a partially allocated multidimensional array, such as `new String[2][]`, only the outer dimension is allocated; the inner arrays in each slot are initially `null`. A type-use marker does not automatically cause the inner arrays to be created or become non-null.

## 7. Type Annotations and Declaration Annotations: Same `@`, Different Positions

Compare the two examples:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldMarker {
}

@Target(ElementType.TYPE_USE)
@interface TypeMarker {
}

class Holder {
    @FieldMarker
    String[] first;

    String @TypeMarker [] second;

    @TypeMarker
    String[] third;
}
```

- `@FieldMarker` is placed before the field and has `@Target(FIELD)`: it marks the **field declaration**.
- `String @TypeMarker [] second` marks the **array type `String[]`** of the field `second`.
- `@TypeMarker String[] third` marks the **element type `String`** of the array `third` (because the annotation type only has `TYPE_USE`).

The syntactic position before the type name can be treated as either a declaration context or a type context depending on the annotation's `@Target`, so **do not rely solely on whitespace** to determine its meaning. The key criteria are the valid target and the position immediately before the array dimension brackets.

For example, `@TypeMarker` here does not automatically require a variable to have a value, does not add null checks, and does not change the JVM type. It simply attaches metadata to the type use.

## 8. Confusions Related to Arrays with Multiple Values

An annotation type with an array-typed element is **different** from an annotation on an **array type**.

```java
@interface Tags {
    String[] value();
}

@Tags({"a", "b"})
class Sample {
}
```

In this case, `Tags.value()` returns a `String[]` containing two strings. `@Tags` is placed on the **class declaration** (this annotation does not specify a target, so by default it applies to appropriate declaration contexts), and it does **not** mean annotating an array dimension.

Conversely:

```java
class TypeUseSample {
    String @DimensionLabel("outer") [] names;
}
```

`@DimensionLabel` is placed on the **array type** of the field `names`. It does not require `DimensionLabel` to have an array-typed element; in the example, the `value()` element is just a single string.

Also, do not equate a type annotation with array size: `String @DimensionLabel("outer") []` **does not contain the number `2` or `3`**, because array length is runtime information of the object. `@DimensionLabel("outer")` only indicates which **type level** this annotation is attached to.

## 9. Important Considerations When Combining Multiple `[]`

### Declarations with Brackets After the Variable Name

Java still allows the legacy syntax:

```java
String[] first, second[];
```

Here, `first` is `String[]`, while `second` is `String[][]`. However, when type annotations are attached to array levels, mixing brackets after the type name and after the variable name can easily cause confusion about dimension order.

According to the Java Language Specification, annotation ordering is determined by how the bracket pairs of the type are composed for **each variable**, rather than arbitrarily reading across the entire line sequentially. Therefore, in code that needs to annotate multiple dimensions, write each declaration explicitly, placing all brackets to the right of the **type name**:

```java
String @DimensionLabel("outer") [] first;
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] second;
```

This is a readability recommendation; Java still permits the C-style array declaration syntax.

### Annotated Array Types Do Not Change Type Compatibility

```java
String @DimensionLabel("outer") [] first;
String[] second;

second = first;
```

Under the **standard Java type system**, both variables have type `String[]` and the assignment is valid; this annotation does not create a new subtype by itself. An additional checking tool may emit its own warnings or errors depending on the semantics and configuration it defines for `DimensionLabel`.

Do not assume that `String @NonNull []` is checked against `null` by the Java compiler without an appropriate checker. Many ecosystems such as the Checker Framework provide their own annotations and processing tools under their own contracts; that is an additional verification layer on top of Java syntax.

### Reflection Only Sees Retained Annotations and Preserved Positions

If an annotation declares `@Retention(SOURCE)`, it can be useful for source-reading tools, but it is **no longer present in the class file** for runtime Reflection to retrieve. With `CLASS` retention, the information may be present in the class file, but standard Java Reflection does not expose it the way it does for `RUNTIME`. The main example uses `RUNTIME` to allow reading each level via `AnnotatedType`.

For *local variable* declarations, Java Reflection does not have an API equivalent to `Field.getAnnotatedType()` to list all type annotations on local variables inside a method. The runnable code intentionally uses a **field** to demonstrate a clear way to read them at runtime.

## 10. Common Mistakes

| Mistake or Misconception | Correct Understanding |
| --- | --- |
| Writing `@ElementMark String[][]` and thinking the marker attaches to the entire 2D array | A marker before `String` belongs to the **element type**. Place it before the first `[]` to mark the outer array. |
| Writing `String @OuterMark [] @InnerMark []` and calling both of them annotations on `String` | The first marker belongs to `String[][]`; the second marker belongs to `String[]`. |
| Defining an annotation with only `@Target(FIELD)` and placing it between `String` and `[]` | Use `@Target(TYPE_USE)` to place it at an array type level. |
| Using `Field.getAnnotations()` to read annotations on array dimensions | Use `Field.getAnnotatedType()`, then traverse down the `AnnotatedArrayType` levels. |
| Using `@Retention(SOURCE)` and expecting runtime Reflection to read it | Choose `RUNTIME` if access via Reflection is needed. |
| Assuming annotations make Java automatically forbid null or change array size | Annotations do not automatically alter runtime behavior or array dimensions. |
| Confusing `String[] value()` in an annotation declaration with `String @A []` | One is the **type of an annotation element**, while the other is an **annotation attached to an array type**. |
| Thinking all `[]` in `String[][]` refer to the same type | Each pair of `[]` creates an array type level with its own component type. |

## 11. Self-Check

Suppose `@A`, `@B`, and `@C` all have `@Target(TYPE_USE)`. Consider the declaration:

```java
@C String @A [] @B [] names;
```

1. Which type does `@A` attach to? **`String[][]`**, which is the outer array.
2. Which type does `@B` attach to? **`String[]`**, which is the type of each sub-array.
3. Which type does `@C` attach to? **`String`**, which is the final element type.
4. If you only write `@C String[][] names;`, does `@C` automatically apply to all levels? **No**: its position is still the element type `String`.
5. If you declare `String @A [] @B [] names;` where `@B` only has `@Target(FIELD)`, will it compile? **No**: the position before `[]` is a type-use context, not a field declaration.
6. If you need to read `@B` at runtime from a field, can you call `field.getAnnotation(B.class)` directly? **Not appropriate**: you need to get `field.getAnnotatedType()` and then call `getAnnotatedGenericComponentType()` on the outer array first.

Official references: [Java Language Specification 21 – §9.7.4 Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4) and [§10.1 Array Types, §10.2 Array Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html). These two sections specify exactly how annotations apply to **element types** and **each array dimension**, including the order of bracket pairs.
