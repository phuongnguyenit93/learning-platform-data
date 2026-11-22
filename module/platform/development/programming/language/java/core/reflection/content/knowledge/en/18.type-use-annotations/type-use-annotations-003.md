# AnnotatedParameterizedType and Annotations on Type Arguments in Java Reflection

In Java Reflection, `AnnotatedParameterizedType` helps read **annotations attached to a parameterized type use**, including annotations placed on **each type argument**. This is an important difference compared to obtaining only `ParameterizedType`.

For example, the following two declarations both have the generic type `List<String>`, yet carry different type-use annotation metadata:

```java
List<@Tag("element") String> first;
@Tag("container") List<String> second;
```

These are standalone syntax examples; the `Tag` annotation must be declared with `@Target(ElementType.TYPE_USE)` and an appropriate retention. In `first`, the annotation is attached to **`String` at the generic argument position**. In `second`, the annotation is attached to **the `List<String>` type use itself**. To read each position accurately, we need `AnnotatedType` and `AnnotatedParameterizedType`, not just `Field.getType()` or `Field.getGenericType()`.

## 1. Context: what is a type-use annotation?

Java 8 introduced type annotations and the corresponding Reflection APIs. An annotation can be attached not only to a *declaration* such as a class, method, or field, but also to **a type-use position**: return type, field type, generic argument, array element, wildcard bound, etc.

An annotation used in this lesson:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Tag {
    String value();
}
```

This snippet illustrates the annotation declaration; the full runnable program in section 4 declares `Tag` inside a class so it compiles standalone.

The two meta-annotations serve distinct roles:

- `@Target(ElementType.TYPE_USE)` permits appearing at type-use positions, such as `List<@Tag("x") String>`.
- `@Retention(RetentionPolicy.RUNTIME)` requires retaining the annotation so Reflection can read it at runtime. If `@Retention` is omitted, the default is `CLASS`: the compiler can store the information in the class file, but runtime Reflection APIs will **not return** that annotation as expected.

Not every annotation appearing near a field is necessarily an annotation on a type argument. You must examine the exact **position in the type tree** where the annotation is attached.

**Note:** The Java compiler does not automatically check or enforce the business meaning of `@Tag`. It only records and exposes metadata according to the language contract; interpreting `"element"` as a validation, serialization, or nullness rule requires a separate framework/tool.

## 2. AnnotatedType, ParameterizedType, and AnnotatedParameterizedType

These APIs serve different responsibilities:

| API | Package | Explanation |
| --- | --- | --- |
| `Type` | `java.lang.reflect` | General interface representing a Java type; can be `Class`, `ParameterizedType`, `TypeVariable`, etc. |
| `ParameterizedType` | `java.lang.reflect` | Metadata of a generic type with actual arguments, e.g., `List<String>`; `getActualTypeArguments()` returns `Type[]` |
| `AnnotatedType` | `java.lang.reflect` | **A single use of a type** that may carry type-use annotations; `getType()` returns the underlying `Type`, `getAnnotations()` reads annotations at **the current node** |
| `AnnotatedParameterizedType` | `java.lang.reflect` | An `AnnotatedType` representing **a parameterized type use**; `getAnnotatedActualTypeArguments()` returns each argument as `AnnotatedType[]`, thereby preserving annotations at each argument |

Data example:

```java
Map<@Tag("key") String, List<@Tag("item") Integer>> values;
```

The type tree has multiple levels:

```text
Map<String, List<Integer>>     (outermost parameterized type)
├─ argument[0]: String         (@Tag("key") on String)
└─ argument[1]: List<Integer>  (nested parameterized type)
   └─ argument[0]: Integer     (@Tag("item") on Integer)
```

If you only call `ParameterizedType.getActualTypeArguments()`, you get `String` and `List<Integer>` as `Type` objects, but **you cannot directly read the annotations attached to each type use** from those `Type` objects. To retrieve `@Tag("key")` and `@Tag("item")`, you must traverse the **`AnnotatedType` tree**.

### Annotation on the type itself and annotation on an argument are two distinct positions

Consider:

```java
@Tag("outer") List<@Tag("element") String> names;
```

- The outer `AnnotatedType` node represents the use of `List<String>` and has `@Tag("outer")`.
- Because the outer node is an `AnnotatedParameterizedType`, you can call `getAnnotatedActualTypeArguments()`.
- The first element in the returned array represents the use of `String` and has `@Tag("element")`.

`getAnnotations()` on the **outer node** does not automatically collect annotations from child nodes. Conversely, an annotation on `String` does not automatically become an annotation on `List`. You must read at the right level.

## 3. Where do you get AnnotatedParameterizedType from?

Normally you do not construct an `AnnotatedParameterizedType` directly; instead, you obtain an `AnnotatedType` from Reflection and then **check the node kind** before casting.

| Where the type use appears | API to start retrieving `AnnotatedType` |
| --- | --- |
| Declared type of a field | `Field.getAnnotatedType()` |
| Return type of a method | `Method.getAnnotatedReturnType()` |
| Type of each method/constructor parameter | `Method.getAnnotatedParameterTypes()` or `Constructor.getAnnotatedParameterTypes()` |
| Type of each parameter via a `Parameter` object | `Parameter.getAnnotatedType()` |
| Superclass type that may carry annotations | `Class.getAnnotatedSuperclass()` |
| Superinterfaces that may carry annotations | `Class.getAnnotatedInterfaces()` |
| Exception types declared on an executable | `Executable.getAnnotatedExceptionTypes()` |

Basic example on a `names` field:

```java
Field field = Sample.class.getDeclaredField("names");
AnnotatedType annotated = field.getAnnotatedType();

if (annotated instanceof AnnotatedParameterizedType parameterized) {
    AnnotatedType[] args = parameterized.getAnnotatedActualTypeArguments();
    // Each args[i] is a type use and may have its own annotations.
}
```

This is an illustrative snippet requiring `Sample`, imports for Reflection types, and handling `NoSuchFieldException`. Even for a generic field `List<String>` **with no annotations attached**, `getAnnotatedType()` can still be an `AnnotatedParameterizedType`; an empty annotation array does not mean the node is not parameterized.

Conversely, a field `String single` has a plain `String` type use (no type arguments), so you should not blindly cast that node to `AnnotatedParameterizedType`.

**Attention:** An `AnnotatedType` can belong to several concrete forms such as `AnnotatedArrayType`, `AnnotatedWildcardType`, or `AnnotatedTypeVariable`. Only cast to `AnnotatedParameterizedType` when `instanceof` confirms the node kind.

## 4. Complete Java 17+ example and deterministic output

Create the file `AnnotatedTypeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

public class AnnotatedTypeDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Tag {
        String value();
    }

    public static class Sample {
        public @Tag("outer") List<@Tag("element") String> names;

        public Map<@Tag("key") String,
                   List<@Tag("nested") Integer>> scores;

        public List<String> plain;
        public String single;

        public void accept(List<@Tag("parameter") String> values) {}

        public List<@Tag("result") String> read() {
            return List.of();
        }
    }

    static String label(AnnotatedType type) {
        Tag tag = type.getAnnotation(Tag.class);
        return tag == null ? "none" : tag.value();
    }

    public static void main(String[] args) throws Exception {
        Field names = Sample.class.getDeclaredField("names");
        System.out.println("erased=" + names.getType().getTypeName());
        System.out.println("generic=" + names.getGenericType().getTypeName());

        AnnotatedType annotated = names.getAnnotatedType();
        System.out.println("root=" + label(annotated));
        System.out.println(
                "parameterized="
                + (annotated instanceof AnnotatedParameterizedType)
        );

        AnnotatedType first =
                ((AnnotatedParameterizedType) annotated)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println(
                "argument=" + first.getType().getTypeName()
                + ",tag=" + label(first)
        );

        AnnotatedParameterizedType scores =
                (AnnotatedParameterizedType) Sample.class
                .getDeclaredField("scores").getAnnotatedType();

        AnnotatedType[] pair =
                scores.getAnnotatedActualTypeArguments();
        System.out.println("key=" + label(pair[0]));

        AnnotatedType nested =
                ((AnnotatedParameterizedType) pair[1])
                .getAnnotatedActualTypeArguments()[0];
        System.out.println("nested=" + label(nested));

        AnnotatedType plain =
                Sample.class.getDeclaredField("plain").getAnnotatedType();
        System.out.println(
                "plain parameterized="
                + (plain instanceof AnnotatedParameterizedType)
        );
        System.out.println(
                "plain argument="
                + label(((AnnotatedParameterizedType) plain)
                        .getAnnotatedActualTypeArguments()[0])
        );
        System.out.println(
                "single parameterized="
                + (Sample.class.getDeclaredField("single")
                        .getAnnotatedType()
                        instanceof AnnotatedParameterizedType)
        );

        Method accept =
                Sample.class.getDeclaredMethod("accept", List.class);
        System.out.println(
                "method parameter="
                + label(((AnnotatedParameterizedType)
                        accept.getAnnotatedParameterTypes()[0])
                        .getAnnotatedActualTypeArguments()[0])
        );

        Method read = Sample.class.getDeclaredMethod("read");
        System.out.println(
                "method result="
                + label(((AnnotatedParameterizedType)
                        read.getAnnotatedReturnType())
                        .getAnnotatedActualTypeArguments()[0])
        );
    }
}
```

Compile and run with Java 17 or newer:

```bash
javac AnnotatedTypeDemo.java
java AnnotatedTypeDemo
```

Output:

```text
erased=java.util.List
generic=java.util.List<java.lang.String>
root=outer
parameterized=true
argument=java.lang.String,tag=element
key=key
nested=nested
plain parameterized=true
plain argument=none
single parameterized=false
method parameter=parameter
method result=result
```

Explanation:

1. `Field.getType()` only gives the erased class: `java.util.List`.
2. `Field.getGenericType()` gives `java.util.List<java.lang.String>`, which is not yet a node tree holding type-use annotations.
3. `Field.getAnnotatedType()` returns the outer node; `label(annotated)` reads `@Tag("outer")`.
4. `getAnnotatedActualTypeArguments()[0]` returns the node for `String` inside `List<...>`; that node carries `@Tag("element")`.
5. Field `scores` holds a `Map` with **two type arguments**. The first node carries `key`, and the second node is `List<Integer>`; you must descend into the second node to get `nested` on `Integer`.
6. Field `plain` proves that **having no annotations** on a generic argument does not eliminate its parameterized nature. Field `single` proves that not every `AnnotatedType` can be cast to `AnnotatedParameterizedType`.
7. `getAnnotatedParameterTypes()[0]` and `getAnnotatedReturnType()` can also lead to annotated type arguments just like a field.

The program reads metadata via Reflection, **without needing an instance of `Sample`** and without calling `accept()`/`read()`. It also does not rely on the ordering of `getDeclaredFields()` or `getDeclaredMethods()`, because it always looks up each field/method by its exact name and parameter types.

## 5. How to read annotations on each type argument

`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` returns `AnnotatedType[]`. The array indices correspond to **the declared positions of the generic arguments in the type use**, for example:

```java
Map<@Tag("key") String, @Tag("value") Integer> data;
```

- `args[0]` represents `String`; `args[0].getAnnotation(Tag.class)` has `value() == "key"`.
- `args[1]` represents `Integer`; `args[1].getAnnotation(Tag.class)` has `value() == "value"`.

When there is no `Tag` annotation at the inspected node, `getAnnotation(Tag.class)` returns `null`. Use `getAnnotations()` to read type-use annotations present on **that exact node**, or `getDeclaredAnnotations()` when you need annotations declared directly at the node. You should verify `@Retention(RUNTIME)` of the annotations you intend to read.

A safely guarded processing pattern:

```java
AnnotatedType typeUse = field.getAnnotatedType();

if (typeUse instanceof AnnotatedParameterizedType pt) {
    AnnotatedType[] typeArgs = pt.getAnnotatedActualTypeArguments();

    for (int i = 0; i < typeArgs.length; i++) {
        AnnotatedType argument = typeArgs[i];
        Tag tag = argument.getAnnotation(Tag.class);
        // tag may be null if the i-th argument is not annotated with @Tag.
    }
}
```

This is an illustrative snippet in a context that already has `Field field` and annotation `Tag` in scope. If you need annotations on the **container type** `List` or `Map`, query `typeUse.getAnnotation(Tag.class)` before iterating the elements; do not use `field.getAnnotation(Tag.class)` as a substitute.

### Field annotations vs. type-use annotations

An annotation with `@Target(ElementType.FIELD)` targets the **field declaration** and is queried via `Field.getAnnotation`. An annotation with only `@Target(ElementType.TYPE_USE)` targets **type uses** and is queried via `Field.getAnnotatedType().getAnnotation` or child nodes.

If an annotation has multiple targets such as `FIELD` and `TYPE_USE`, you should consult documentation on **syntactic context and annotation placement** to determine where it is stored. Do not infer that `field.getAnnotations()` always contains every annotation on generic arguments.

The same applies to methods: `method.getAnnotations()` refers to **annotations on the method declaration**, while `method.getAnnotatedReturnType()` refers to **annotations on the return type**. For parameters, `Parameter.getAnnotation` relates to annotations on the parameter declaration, unlike `Parameter.getAnnotatedType()` for the parameter's type.

## 6. Nested generic types: recursive traversal is required

A `Map<String, List<Integer>>` is a multi-level tree. `getAnnotatedActualTypeArguments()` on `Map` **only returns two direct child nodes**: `String` and `List<Integer>`; it does not automatically flatten down to `Integer`.

A general type-traversal algorithm can branch across the subinterfaces:

| Node type | API to continue traversing |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()`; when a nested owner is needed: `getAnnotatedOwnerType()` |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| Plain `AnnotatedType` | Read annotations right at the node; there may be no child nodes to traverse |

Example (non-standalone illustrative snippet):

```java
static void visit(AnnotatedType type) {
    // Handle annotations on the type itself here.

    if (type instanceof AnnotatedParameterizedType pt) {
        for (AnnotatedType arg : pt.getAnnotatedActualTypeArguments()) {
            visit(arg);
        }
    } else if (type instanceof AnnotatedArrayType at) {
        visit(at.getAnnotatedGenericComponentType());
    } else if (type instanceof AnnotatedWildcardType wt) {
        for (AnnotatedType upper : wt.getAnnotatedUpperBounds()) {
            visit(upper);
        }
        for (AnnotatedType lower : wt.getAnnotatedLowerBounds()) {
            visit(lower);
        }
    } else if (type instanceof AnnotatedTypeVariable tv) {
        for (AnnotatedType bound : tv.getAnnotatedBounds()) {
            visit(bound);
        }
    }
}
```

This snippet requires importing `AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, and `AnnotatedTypeVariable`; it is assumed to sit inside a Java class. **Important note:** Type-variable bounds can self-reference or form cyclic type graphs (e.g., `T extends Comparable<T>`), so a production metadata traversal algorithm must **detect cycles / limit the visited node set** rather than recursing infinitely. `visit` above only presents the API branches and is not a complete traversal library.

If a generic argument is `List<@Tag String>`, the argument node is an **`AnnotatedParameterizedType`**, not a leaf node. If it is `? extends @Tag Number`, you must enter `AnnotatedWildcardType.getAnnotatedUpperBounds()`. If it is `String @Tag []`, pay attention to whether the annotation attaches to the array position or the array component per Java syntax; the path lies in `AnnotatedArrayType`.

## 7. getAnnotatedOwnerType() and nested generic types

For a nested/member type use, annotations may reside on the **owner**. `AnnotatedParameterizedType.getAnnotatedOwnerType()` returns the annotated type representation of the enclosing type if present, rather than merging the owner's annotations into the nested type's type arguments.

Conceptual example:

```java
class Outer<T> {
    class Inner<U> {}
}
```

If code uses a type like `Outer<String>.Inner<Integer>` and has an annotation attached to the `Outer<String>` use, a metadata analysis tool must also inspect `getAnnotatedOwnerType()` of the `Inner` node. It must not assume owner annotations appear inside `Inner`'s `getAnnotatedActualTypeArguments()`.

For top-level types without an owner, `getAnnotatedOwnerType()` returns `null`. Oracle's documentation also notes that `getAnnotatedActualTypeArguments()` **can be an empty array** in some rare cases, such as a node representing a non-parameterized member type nested inside a parameterized type. Therefore, do not infer the element count merely from casting to `AnnotatedParameterizedType`; always use the actual array length.

The `getAnnotatedOwnerType()` contract has existed since Java 9; the examples and knowledge in this lesson apply well to Java 17+.

## 8. Limitations and what the API does not do

**Does not alter runtime generic erasure:** `List<@Tag String>` and `List<String>` still have the same raw class `List.class`. Annotations do not cause the JVM to generate a new class named `ListOfTagString`, nor do they change the contents of `List` elements.

**Does not automatically validate values:** Simply having `@Tag` does not make Java automatically check every `String` in the list. If rule enforcement is required, a framework needs code to read the annotation at the right position and validate the data.

**Does not resolve generic type variables per subclass:** `Box<T>` inherited as `Box<String>` does not automatically turn every `TypeVariable` on `Box`'s declaration into `String` when calling Reflection on the original declaration. To understand type argument values for a specific subclass, you must inspect the `TypeVariable` mapping and generic superclass/interface separately.

**Does not guarantee annotations are always readable:** If retention is not `RUNTIME`, Reflection will not see the annotation as desired; class-file transformations, metadata limits, or other type-use forms must also be handled according to contract.

**Not always an `AnnotatedParameterizedType`:** `int`, `String`, `String[]`, and wildcards/type variables may all require other forms of `AnnotatedType`. Check with `instanceof`.

**Do not mix up positions and annotation names:** Annotations of the same `Tag` type can appear simultaneously on the container, type argument, wildcard bound, and array dimension with different values. Reading an annotation at the wrong node easily leads to inaccurate metadata reporting even when the code throws no exception.

## 9. Common mistakes and how to fix them

| Mistake | Correct understanding |
| --- | --- |
| Using `Field.getType()` to find annotations on `List<@Tag String>` | `getType()` only returns the raw erased type; use `getAnnotatedType()` |
| Using `Field.getGenericType()` and thinking `ParameterizedType` carries full type-use annotations | `ParameterizedType` carries generic structure; for annotations at each position use `AnnotatedParameterizedType` |
| Reading `annotated.getAnnotations()` and assuming it holds all annotations of type arguments | It only reads annotations on the current node; you must traverse `getAnnotatedActualTypeArguments()` |
| Seeing `getAnnotations()` empty and claiming it is not generic | A generic type use can still be an `AnnotatedParameterizedType` without carrying annotations |
| Casting every `AnnotatedType` to `AnnotatedParameterizedType` | Check `instanceof`, because arrays, wildcards, type variables, and plain types exist |
| Thinking `List<@Tag String>` automatically enforces `Tag` constraints on elements | Type-use annotations are metadata; runtime enforcement is up to the application/framework |
| Traversing only `Map`'s type arguments and skipping inner `List<Integer>` | Recursively traverse the annotated type tree; watch out for type variable cycles |
| Thinking `getAnnotatedOwnerType()` always returns a type | For top-level types, it is usually `null` |
| Forgetting `@Retention(RUNTIME)` | Annotations do not appear through runtime Reflection if retention is inappropriate |
| Using `Method.getAnnotations()` instead of type-use annotations on the return type | Use `Method.getAnnotatedReturnType()` and traverse at the right level |

## 10. Knowledge self-check

1. For `List<@Tag String>`, which API retrieves the annotation attached to `String`? **`Field.getAnnotatedType()` → check/cast `AnnotatedParameterizedType` → `getAnnotatedActualTypeArguments()[0].getAnnotation(Tag.class)`.**
2. What is `AnnotatedParameterizedType` a subinterface of? **`AnnotatedType`** (and indirectly extends `AnnotatedElement`).
3. What data type does `ParameterizedType.getActualTypeArguments()` return? **`Type[]`**, unlike **`AnnotatedType[]`** from `getAnnotatedActualTypeArguments()`.
4. For `@Tag("outer") List<@Tag("inner") String>`, what does `getAnnotation(Tag.class)` on the outer node return? **`outer`**, not `inner`.
5. Why does an annotation meant to be read by Reflection need `@Retention(RUNTIME)`? **So that runtime Reflection can query the annotation.**
6. Without annotations on generic arguments, is `getAnnotatedType()` still an `AnnotatedParameterizedType`? **Yes, it can be**, because the parameterized shape is independent of whether annotations are present.
7. In `Map<String, List<@Tag Integer>>`, how do you reach `Integer`? **Enter the second argument of Map, then enter the first argument of List**.
8. Which node holds the annotation in `? extends @Tag Number`? **The upper bound node** of `AnnotatedWildcardType`.
9. Can a plain `String` type use be cast directly to `AnnotatedParameterizedType`? **No**, use `instanceof`.
10. Does a type-use annotation automatically verify that data in a `List` satisfies the rule? **No**, it is metadata that other tools may interpret.

## 11. Official references

- [Oracle Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): `getAnnotatedActualTypeArguments()`, `getAnnotatedOwnerType()`, and empty-array notes in nested types.
- [Oracle Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html): `getType()`, `getAnnotations()`, `getAnnotation()`, and subinterfaces.
- [Oracle Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html): `getType()`, `getGenericType()`, `getAnnotatedType()`.
- [Oracle Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): generic type arguments without per-type-use annotation metadata.
- [Java Language Specification SE 21 — §9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7): annotation locations and type-use annotations.

**Remember:** `ParameterizedType` tells you **which generic types** are used, while `AnnotatedParameterizedType` lets you know **where annotations lie on the generic type use itself or on each type argument**. To accurately read `List<@Tag String>` or nested generics, you must traverse the `AnnotatedType` tree rather than looking only at the raw type or an annotation array on the outer node.