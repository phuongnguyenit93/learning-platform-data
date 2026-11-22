# Annotations on Type Casts, Object Creation, and Other Type Positions in Java

## 1. An Annotation Can Describe a *Type Use*

In Java, annotations are not attached only to class, method, or field declarations. An annotation with `@Target(ElementType.TYPE_USE)` can also be placed **at places where source code uses a type**: in variable declarations, parameter types, generic arguments, type casts, `new` expressions, `instanceof` tests, array element types, `extends`, `implements`, `throws`, and other positions specified by the Java Language Specification (JLS).

Example:

```java
@TypeTag("cast")
String result = (@TypeTag("checked") String) source;
```

Here, `@TypeTag("checked")` is attached to the **`String` type used in the cast**, while the annotation placed before the type in the variable declaration can describe **the variable's type**. They are not two invocations of an annotation like calling a function: annotations are metadata, with no effect of automatically converting values or checking the validity of the cast.

To declare your own annotation for type-use contexts:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}
```

- **`TYPE_USE`** allows an annotation to appear at a type-use position.
- **`RUNTIME`** retains the appropriate annotation information in the class file so that runtime APIs supporting metadata access can read it. Not **every** position inside a method body is provided with a direct API by Java Reflection for querying.
- `value()` is a `String` element, so you can write the shorthand form `@TypeTag("cast")`.
- Without `@Target(TYPE_USE)`, an annotation is only for declarations (according to the specific or default `@Target`), and **is not automatically allowed in casts or `new`**.

Annotations at type-use positions are the foundation for static analysis/type checkers to extend the type system, such as describing nullable/non-null types, tainted data, or validated data. **Merely defining `@TypeTag` does not make the default Java compiler automatically understand the meaning of "checked" or "non-null".** To have additional checking rules, you need an annotation-processing tool that properly understands the annotation type's semantics.

## 2. Distinguishing Between Declaration Annotations and Type-Use Annotations

Two positions look similar but represent different things:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldInfo {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNullType {}

class Example {
    @FieldInfo
    @NonNullType String text;
}
```

- `@FieldInfo` belongs to the **field declaration**: metadata on the field `text`.
- `@NonNullType` belongs to the **`String` type** of the field.
- `Field.getAnnotation(FieldInfo.class)` queries annotations on the declaration.
- `Field.getAnnotatedType().getAnnotation(NonNullType.class)` queries annotations on the type being used.

An annotation type can declare both `FIELD` and `TYPE_USE`; if placed in the shared position before the field's type, the same syntax can apply in **both contexts**. Therefore, read `@Target` and choose the right reflection API before concluding that an annotation was "lost".

Similarly, `TYPE_PARAMETER` is used to mark **type parameter declarations** such as `class Box<@Marker T>`, whereas `TYPE_USE` describes **the types being used** such as `Box<@Marker String>`. Both targets can appear together in `@Target({TYPE_PARAMETER, TYPE_USE})` if the annotation is designed for both.

## 3. Annotations on Type Casts

Java allows placing a type-use annotation inside the parentheses of a **cast expression**, right before the type:

```java
Object input = "hello";
String text = (@TypeTag("cast") String) input;
```

The execution order remains normal Java behavior:

1. The JVM performs the cast from `Object` to `String` according to Java's runtime rules.
2. If the value has an incompatible type, the cast throws `ClassCastException` just as it would without the annotation.
3. If the value is compatible (or is `null` for a reference cast), the cast succeeds.
4. `@TypeTag("cast")` is metadata attached to **the type written in the cast**. By itself, it does not change the type-checking logic.

For example, the following code **still fails at runtime**:

```java
Object number = 42;
String invalid = (@TypeTag("cast") String) number; // ClassCastException
```

A type-use annotation can express the developer's intent or a checker's contract, but it cannot "rescue" a cast that is inherently invalid.

### Casting Generic Types

Annotations can appear on type arguments:

```java
Object unknown = java.util.List.of("a", "b");

@SuppressWarnings("unchecked")
java.util.List<@TypeTag("element") String> strings =
        (java.util.List<@TypeTag("cast-element") String>) unknown;
```

The cast to `List<String>` is **unchecked** because at runtime only `List` can be checked, not whether each element is a `String`. `@TypeTag` does not change type erasure. Whether `@SuppressWarnings("unchecked")` is needed (if at all) is a separate cast-warning concern and is not automatically resolved by `TYPE_USE`.

## 4. Annotations on Object Creation Expressions Using `new`

In an **unqualified class instance creation expression**, you can annotate the class type immediately after `new`:

```java
String value = new @TypeTag("created-type") String("hello");
```

Here, `@TypeTag` describes **the type of the class being instantiated**. The constructor still runs normally; `TYPE_USE` has no effect on constructor invocation, memory allocation timing, or the constructor's ability to throw exceptions.

Example with a generic class:

```java
java.util.List<@TypeTag("element") String> names =
        new @TypeTag("list-type")
            java.util.ArrayList<@TypeTag("new-element") String>();
```

However, with a **package-qualified type name** (such as `java.util.ArrayList`), the annotation placement must strictly follow the syntactic rules for type names; placing the annotation before `java` as in the illustrative example above is not valid Java syntax. A reliably valid and readable form is to import the class and write:

```java
import java.util.ArrayList;
import java.util.List;

List<@TypeTag("element") String> names =
        new @TypeTag("list-type")
            ArrayList<@TypeTag("new-element") String>();
```

*The two blocks above are meant to compare placement; the block using the fully qualified name is a syntax example intentionally not meant to compile. Use the latter block in applications or runnable examples.*

Importantly: `@TypeTag` placed before `ArrayList` applies to **the type instantiated in the expression**, while the annotation placed inside `<...>` applies to **the generic type argument**.

### Anonymous Classes

With an anonymous class, the type used after `new` is still a type-use position. For example:

```java
Runnable task = new @TypeTag("anonymous-base") Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
```

The annotation here describes the `Runnable` interface type at the anonymous class creation site, **does not automatically become an annotation on the `run()` method**, and does not generate any additional runtime behavior.

## 5. Annotations on `instanceof` and Pattern Matching

A type test can carry a type-use annotation:

```java
Object input = "Java";
boolean stringValue = input instanceof @TypeTag("tested-type") String;
```

`instanceof` still returns a result according to Java rules: if the value is non-null and has a compatible type, it evaluates to `true`. The annotation on the tested type does not affect the result.

Java 17 also supports type patterns in `instanceof`:

```java
Object input = "Java";
if (input instanceof @TypeTag("pattern-type") String text) {
    System.out.println(text.toUpperCase());
}
```

This example tests the value and declares the pattern variable `text`; the annotation targets **the `String` type of the pattern** and does not cause `text` to be created by any different mechanism.

Do not confuse `@Target(TYPE_USE)` with `@Target(LOCAL_VARIABLE)`. An annotation on a variable declaration and an annotation on a type written in a pattern/expression may be subject to different rules. To know what is actually being annotated, you must look at both the syntax and `@Target`.

## 6. Generics: Type Arguments, Wildcard Bounds, Type Parameter Bounds

In Java Generics, you can annotate **a specific type** inside `<...>`:

```java
List<@TypeTag("element") String> names = List.of("A", "B");
```

The annotation here attaches to the type argument `String`, **not** to the `List` declaration, and it does **not** automatically annotate every `String` object inside the list.

A wildcard bound is also a type-use context:

```java
List<? extends @TypeTag("upper-bound") Number> values = List.of(1, 2);
List<? super @TypeTag("lower-bound") Integer> sink =
        new ArrayList<Number>();
```

- `@TypeTag("upper-bound") Number` is the **upper bound** of the wildcard.
- `@TypeTag("lower-bound") Integer` is the **lower bound** of the wildcard.
- `List<@TypeTag("wildcard") ?>` illustrates an annotation placed directly on the wildcard itself if your checker has a contract for that case.
- Generic assignment, variance, capture, and erasure still follow Java rules; type-use annotations do not alter `extends`/`super` relationships by themselves.

Type parameter bounds can also carry annotations:

```java
class NumericBox<T extends @TypeTag("bound") Number> {
    private final T value;
    NumericBox(T value) { this.value = value; }
    T get() { return value; }
}
```

In this example, `@TypeTag` attaches to **`Number` used as the bound**. The declaration of `T` is a type parameter, so if you want to annotate **the `T` declaration itself**, you need to consider `ElementType.TYPE_PARAMETER`; do not confuse it with an annotation on the bound.

Some expressions with **explicit type arguments** also allow type annotations:

```java
// Assuming List, Collections, and TypeTag are imported:
List<String> empty = java.util.Collections.<@TypeTag("call-arg") String>emptyList();
```

The annotation targets the `String` type in **the type argument list of the method call**. It does not turn the `emptyList` method into an annotated method declaration.

## 7. Arrays: Element Type vs. Annotations on Each Dimension

Java allows annotating **the element type** and **each level of an array type**. For example:

```java
@TypeTag("element") String @TypeTag("outer-array") [] values;
```

- `@TypeTag("element")` before `String` applies to the **String element type**.
- `@TypeTag("outer-array")` before `[]` applies to the **String[] array type**.
- For multidimensional arrays, each pair of `[]` can receive its own annotation.

```java
String @TypeTag("two-dimensional") []
       @TypeTag("inner-array") [] grid;
```

Annotation placement matters a great deal. Annotating the element type `String` is not the same as annotating `String[]`. When reflecting via `AnnotatedType`, the `AnnotatedArrayType` API lets you drill down level by level with `getAnnotatedGenericComponentType()`.

### Arrays in `new` Expressions

Both the element type and array dimensions can be annotated at an array creation expression:

```java
int @TypeTag("array-dimension") [] numbers =
        new int @TypeTag("new-dimension") [2];
```

This example still creates an `int[]` array of length 2. The annotations **do not change the array size, bounds checking, or default values** of the elements.

You must not place annotations arbitrarily anywhere around `[]` or between arbitrary tokens; they must be placed according to the Java type annotation grammar (specifically to the left of the `[` for the dimension to be annotated).

## 8. Other TYPE_USE Positions: extends, implements, throws, receiver, method references

### 8.1. Superclass and Superinterfaces

```java
class Base {}

class Worker extends @TypeTag("base") Base
        implements @TypeTag("interface") Runnable {
    @Override
    public void run() {}
}
```

The annotations attach to **the superclass type `Base`** and **the interface type `Runnable`** in the inheritance relationship. They do not automatically annotate the `Worker` class declaration itself, nor do they automatically attach to inherited methods.

Reflection on the class can query some type-use annotations here using:

```java
Worker.class.getAnnotatedSuperclass();
Worker.class.getAnnotatedInterfaces();
```

### 8.2. Return Type, Parameter Type, Receiver Type, and throws

```java
import java.io.IOException;

class Service {
    public @TypeTag("return") String read(
            @TypeTag("parameter") String key)
            throws @TypeTag("exception") IOException {
        return key;
    }

    void inspect(@TypeTag("receiver") Service this) {
        // Receiver type annotation, not an argument passed when calling the method.
    }
}
```

- The annotation on `String` before the method name is on the **return type**.
- The annotation on `String key` is on the **parameter type**; `TYPE_USE` alone may not create a declaration annotation on `java.lang.reflect.Parameter`.
- The annotation on `IOException` describes the exception type in `throws`.
- `Service this` is the **receiver parameter**: a special syntactic position for a type annotation that does not add an argument when calling `inspect()`.

The corresponding reflection APIs include `Method.getAnnotatedReturnType()`, `Executable.getAnnotatedParameterTypes()`, `Executable.getAnnotatedExceptionTypes()`, and `Executable.getAnnotatedReceiverType()`, depending on whether the declaration has a corresponding receiver.

### 8.3. Types in Method References

In a method reference expression, the reference type can also be annotated:

```java
java.util.function.Function<String, Integer> length =
        @TypeTag("reference-type") String::length;
```

This is a type-use annotation on the reference type `String`. The resulting method reference is still a lambda/function object according to Java semantics. The annotation does not automatically attach to the `String.length()` method.

A method reference with explicit type arguments (when the API syntax is applicable) can also annotate those type arguments.

## 9. Runnable Java 17+ Example: Multiple Positions in One Program

Create a **Main.java** file exactly as follows. The program shows that annotations in both expression and declaration type contexts are valid; metadata that has reflection APIs is read for clear comparison.

```java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.ArrayList;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Tag {
    String value();
}

class Base {}

class Sample extends @Tag("super") Base
        implements @Tag("interface") Runnable {

    public @Tag("return") String message(
            @Tag("parameter") String text)
            throws @Tag("throws") IOException {

        Object value = text;
        String casted = (@Tag("cast") String) value;
        String created = new @Tag("new") String(casted);

        List<@Tag("argument") String> names =
                new @Tag("generic-new")
                    ArrayList<@Tag("constructor-argument") String>();
        names.add(created);

        List<? extends @Tag("bound") Number> numbers = List.of(1, 2);
        int @Tag("array") [] values =
                new int @Tag("new-dimension") [2];

        if (casted instanceof @Tag("instanceof") String) {
            values[0] = numbers.size();
        }
        return names.get(0) + values[0];
    }

    @Override
    public void run() {}

    public void receiver(@Tag("receiver") Sample this) {}
}

public class Main {
    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();

        System.out.println(sample.message("ok"));

        System.out.println(Sample.class.getAnnotatedSuperclass()
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getAnnotatedInterfaces()[0]
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedReturnType().getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedParameterTypes()[0]
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedExceptionTypes()[0]
                .getAnnotation(Tag.class).value());
    }
}
```

Compile and run in the directory containing `Main.java`:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Output:

```text
ok2
super
interface
return
parameter
throws
```

Output explanation:

1. `message("ok")` casts `"ok"` from `Object` to `String`, creates a new `String`, adds it to `List`, sets `values[0] = 2` because the `numbers` list has two elements, and then concatenates the string to produce `"ok2"`.
2. `getAnnotatedSuperclass()` and `getAnnotatedInterfaces()` read the type-use annotations of the types written in `extends`/`implements`.
3. `getAnnotatedReturnType()`, `getAnnotatedParameterTypes()`, and `getAnnotatedExceptionTypes()` read the type-use annotations on the method signature.
4. The `cast`, `new`, `generic-new`, and `instanceof` annotations are inside **the method body**. They are not listed in the reflection output on the method signature. That **does not mean the compiler ignores annotations when generating the class file**; you can use a class file inspection tool to observe the metadata at those expression positions.

The program only demonstrates and reads metadata; it has no custom checker implementing logic for the `cast`, `new`, `bound`, or `throws` labels.

## 10. Reading Type-Use Annotations: Reflection and Class Files

Java reflection has **`AnnotatedType`** objects that describe types across many declaration positions:

| Position | Commonly Used Reflection API |
|---|---|
| Field type | `Field.getAnnotatedType()` |
| Method return type | `Method.getAnnotatedReturnType()` |
| Parameter type | `Executable.getAnnotatedParameterTypes()` |
| Exception type in `throws` | `Executable.getAnnotatedExceptionTypes()` |
| Receiver type | `Executable.getAnnotatedReceiverType()` |
| Superclass / interface | `Class.getAnnotatedSuperclass()`, `Class.getAnnotatedInterfaces()` |
| Generic argument | Cast to `AnnotatedParameterizedType`, then `getAnnotatedActualTypeArguments()` |
| Array dimension | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |

However, `AnnotatedType` **is not a system for traversing every expression in a method body**. Standard Java reflection has no direct methods like `getAnnotationsOnAllCasts()` or `getAnnotationsOnAllNewExpressions()`.

For annotations retained in the class file on cast/new/instanceof, bytecode analysis tools can read the corresponding `RuntimeVisibleTypeAnnotations` or `RuntimeInvisibleTypeAnnotations` attributes. The following example uses `javap` after compilation:

```bash
javap -v Sample
```

Inspect the `RuntimeVisibleTypeAnnotations` sections to see the type annotations recorded in the class file, including expression-related targets, if the compiler and retention policy produce that attribute. `javap` displays detailed information that differs from the reflection API; the output is only meant to illustrate class file structure, with no need to fabricate a fixed `javap` output.

**Retention does not mean runtime enforcement.** Even when an annotation has `RUNTIME` retention and the bytecode contains metadata, Java still does not automatically enforce the constraints intended by the annotation author.

## 11. Common Mistakes and How to Fix Them

### 11.1. Using the Wrong `@Target`

Incorrect example:

```java
@Target(ElementType.METHOD)
@interface MethodInfo {}

Object source = "text";
String result = (@MethodInfo String) source; // WRONG: cast is TYPE_USE
```

To annotate a type in a cast, the annotation type must include `TYPE_USE`. `METHOD` only allows use on method declarations and does not grant permission to annotate types used in expressions.

### 11.2. Writing the Annotation on the Wrong Side of the Type Name

A type annotation attaches to **the simple name of the type**. When using a qualified type such as `java.util.List`, you should not insert annotations arbitrarily among package tokens. Prefer importing and writing `new @Tag ArrayList<String>()`, or place it directly before the simple type name in a qualified type when allowed by JLS rules.

### 11.3. Assuming an Annotation Automatically Blocks `null`

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

@NonNull String value = null;
```

Without a checker or additional tool, the declaration above **is not automatically rejected by `javac` just because of `@NonNull`**. An annotation named `NonNull` does not contain any checking rules by itself; the annotation name is only metadata.

### 11.4. Assuming `@Tag` Alters Casts or Constructors

`(@Tag String) object` still casts according to JVM rules. `new @Tag Service()` still calls the constructor as usual. Annotations do not generate extra constructors, do not wrap objects, and do not add default runtime checks.

### 11.5. Reading the Declaration Instead of the Annotated Type

If `@Tag` only has `TYPE_USE`, `field.getAnnotation(Tag.class)` may not see the annotation on **the field's type**. You must use `field.getAnnotatedType().getAnnotation(Tag.class)`. For nested generics, you must traverse `AnnotatedParameterizedType` or `AnnotatedArrayType` at the appropriate level.

### 11.6. Looking at Reflection and Concluding the Compiler Dropped Cast Annotations

`Method.getAnnotations()` reads metadata on the **method declaration** and does not return type-use annotations placed on casts and `new` expressions inside the method body. To inspect those positions in the class file, use `javap -v` or an appropriate bytecode-reading tool.

### 11.7. Placing an Annotation Where the Grammar Does Not Allow It

`TYPE_USE` expands where annotations are permitted, but **does not allow inserting @Annotation at any arbitrary whitespace**. Positions in casts, `new`, `instanceof`, generics, `[]`, wildcard bounds, or method references each have specific grammar rules. If you encounter a parser error, consult JLS §4.11 and §9.7.4 before blaming `@Target`.

## 12. Checklist When Working with TYPE_USE

1. **Check `@Target`**: does the annotation type include `TYPE_USE`? If you want to annotate a type parameter declaration, also consider `TYPE_PARAMETER`.
2. **Identify the exact position**: are you annotating a class declaration, field declaration, field type, cast type, type after `new`, generic argument, array dimension, or return type?
3. **Choose the right syntax**: for example, `(@Tag String) value`, `new @Tag String("x")`, `List<@Tag String>`, `String @Tag []`.
4. **Distinguish metadata from logic**: does the program have an annotation processor/type checker that interprets `@Tag`? If not, the JVM processes expressions as usual.
5. **Identify the tool for reading metadata**: `AnnotatedType` is used for many signature/declaration positions; `javap -v` or a bytecode scanner is suitable for annotations inside a method body.
6. **Verify retention**: `SOURCE`, `CLASS`, and `RUNTIME` serve different purposes; reflection only sees data accessible via the API with the appropriate retention.
7. **Test compiling on the target JDK**: type annotation syntax requires Java 8+, while other constructs such as `instanceof` patterns require an appropriate Java version (for example, Java 17).

## 13. Official Reference Documentation

- [Java SE 17 JLS §4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): list of type contexts, including cast, new, array creation, instanceof, and method reference.
- [Java SE 17 JLS §9.6.4.1 — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): meaning of `ElementType.TYPE_USE`, `TYPE_PARAMETER`, and declaration targets.
- [Java SE 17 JLS §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): type annotation contexts and how to distinguish declarations from types.
- [Java SE 17 API — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): accessing annotated types via reflection.
- [Java SE 17 JVM Specification §4.7.20–4.7.21](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.20): format of `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` in class files.

**Remember:** `@Target(TYPE_USE)` allows an annotation to describe **a type where it is used**: casts, `new`, `instanceof`, generics, arrays, method references, `throws`, and many other type contexts. Type-use annotations do not change runtime semantics on their own. To inspect an annotation, you must know whether it is on a declaration/signature or an expression and choose Reflection or class file analysis accordingly.
