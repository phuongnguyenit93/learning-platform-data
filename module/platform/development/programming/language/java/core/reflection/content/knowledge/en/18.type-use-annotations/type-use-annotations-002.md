# `AnnotatedType` and the Underlying Type in Java Reflection

## 1. What is `AnnotatedType` for?

Since Java 8, annotations can appear directly at **a type-use position**: on generic element types, field types, return types, array elements, wildcards, type variable bounds, etc. Reflection provides the `java.lang.reflect.AnnotatedType` interface to hold both pieces of information:

1. **The underlying type**: returned via `getType()`, which is a `java.lang.reflect.Type`.
2. **Annotations attached at that exact type-use position**: accessed using `getAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()` on the `AnnotatedType` node.

Example:

~~~java
List<@NonNull String> names;
~~~

If `@NonNull` is an annotation applicable to `TYPE_USE` with `RetentionPolicy.RUNTIME`, Reflection can read the annotation at **the `String` argument type**, not implicitly on `List`, the variable name `names`, or every other `String` object.

The most important point: **`AnnotatedType` is not a new modified `Type`**. It is the layer representing a type position *together with its annotations*. Call `getType()` to obtain the corresponding `Type`; call the `Annotated...` APIs to descend into child structures while preserving annotations at each node.

## 2. Comparing `Type`, `AnnotatedType`, and declaration annotations

| Component | Question it answers | Example |
| --- | --- | --- |
| `Class<?>` | Runtime type or class of a field when viewed as a raw type | `List.class`, `String[].class` |
| `Type` | Represents a Java type that may contain generics | `List<String>`, `? extends Number`, `T` |
| `AnnotatedType` | Type **used at a specific position**, along with annotations at that position | `@Mark List<@Mark String>` |
| `AnnotatedElement` of `Field`/`Method` | Annotations declared on the **field/method element** | `@Deprecated` on a method |

An `AnnotatedType` itself implements `AnnotatedElement`, so it has `getAnnotation()` and `getAnnotations()`. However, that **does not make it identical to `Field` or `Method`**.

Example:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark { }

class Example {
    List<@Mark String> values;
}
~~~

The snippet above requires importing `java.lang.annotation.*` and `java.util.List`; it is illustrative and not a standalone program.

- `Example.class.getDeclaredField("values").getDeclaredAnnotations()` checks annotations declared directly **on the field**; in the example there is no declaration annotation there.
- `field.getAnnotatedType()` represents the use of `List<...>`. Since `List` has no direct annotation, `getAnnotation(Mark.class)` on the root node is `null`.
- `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()[0]` represents `String`, and this node has `@Mark`.

**`field.getAnnotatedType().getType()` only retrieves the `Type` structure; do not use that result to query annotations of individual generic positions.**

## 3. Where do you get `AnnotatedType` from?

| Reflection source | API | Type-use position described |
| --- | --- | --- |
| Field | `Field.getAnnotatedType()` | Type of the field |
| Method | `Method.getAnnotatedReturnType()` | Return type |
| Method | `Method.getAnnotatedParameterTypes()` | Each parameter type in order |
| Method/Constructor | `getAnnotatedExceptionTypes()` | Exception types declared in `throws` |
| Constructor/Method | `getAnnotatedReceiverType()` | Receiver type, if applicable |
| Class | `Class.getAnnotatedSuperclass()` | `extends` type |
| Class | `Class.getAnnotatedInterfaces()` | `implements` or interface `extends` types |
| Type variable | `TypeVariable.getAnnotatedBounds()` | Bound types of the type variable |
| Record component (Java 16+) | `RecordComponent.getAnnotatedType()` | Type of the record component |

Not every API guarantees returning a non-`null` object: for instance, `getAnnotatedSuperclass()` can return `null` when there is no corresponding superclass. Array-returning APIs can return empty arrays. Check the actual values and structure before casting.

For a generic field:

~~~java
Field field = Box.class.getDeclaredField("labels");

Class<?> raw = field.getType();          // List.class
Type generic = field.getGenericType();  // List<String>
AnnotatedType annotated = field.getAnnotatedType();
Type base = annotated.getType();         // Type representing List<String>
~~~

This is an illustrative snippet; it requires `Box`, `import java.lang.reflect.*`, and handling `NoSuchFieldException`.

- **Field's** `getType()` returns `Class<?>`, so a `List<String>` field is normally seen as raw `List.class`.
- **Field's** `getGenericType()` returns `Type` and preserves the declared generic structure.
- **AnnotatedType's** `getType()` also returns a `Type` describing the underlying type at that node. For `List<String>`, it is a `ParameterizedType`, not necessarily a `Class`.
- Do not blindly cast `(Class<?>) annotated.getType()`; if the type is `List<String>`, the cast can cause a `ClassCastException`.

## 4. `AnnotatedType` hierarchy: following the shape of the underlying type

Specialized subinterfaces allow traversing each kind of type:

| Interface | Common underlying type | API to get child nodes with annotations |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `ParameterizedType`, e.g., `List<String>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | Array `Class` or `GenericArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `WildcardType`, e.g., `? extends Number` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `TypeVariable`, e.g., `T` | `getAnnotatedBounds()` |

This is a **tree of type positions**, not a flat array of annotations. Example:

~~~java
List<@A ? extends @B Number>
~~~

These nodes can be observed (if `@A`, `@B` are type-use annotations retained to runtime):

1. Root `List<...>`: `AnnotatedParameterizedType`.
2. Generic argument `? extends Number`: `AnnotatedWildcardType`, carrying `@A` on the wildcard.
3. Upper bound `Number`: a separate `AnnotatedType`, carrying `@B`.

If you only ask `getAnnotations()` at the `List` root, you **do not automatically receive** annotations on the wildcard or bound. You must step into the corresponding child nodes.

### Type variables and substituted runtime types

With the declaration:

~~~java
class Repository<T extends @A Number> { }
~~~

The annotation `@A` is attached to the **bound `Number`** of type parameter `T`, not always on `T` itself. Read it using:

~~~java
TypeVariable<?> t = Repository.class.getTypeParameters()[0];
AnnotatedType bound = t.getAnnotatedBounds()[0];
~~~

Because **Java generics use type erasure**, `AnnotatedType` does not tell you the actual object type of every element stored in a `List<T>` at runtime. It tells you **the type declaration and the type-use annotations that can be preserved via metadata**. Do not confuse declaration information with dynamic value checking or castability.

## 5. Complete Java 17+ example: underlying types and annotations at each node

Save the file **`AnnotatedTypeLesson.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.*;
import java.util.List;

public class AnnotatedTypeLesson {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Mark {
        String value();
    }

    static class Box<T extends @Mark("bound") Number> {
        public @Mark("list") List<@Mark("element") String> labels;
        public @Mark("component") String @Mark("dimension") [] tags;
        public List<@Mark("wildcard") ? extends @Mark("upper") Number> numbers;

        public @Mark("return") String echo(@Mark("param") String word) {
            return word;
        }
    }

    static String mark(AnnotatedType type) {
        Mark annotation = type.getAnnotation(Mark.class);
        return annotation == null ? "(none)" : annotation.value();
    }

    public static void main(String[] args) throws Exception {
        Field labels = Box.class.getDeclaredField("labels");
        AnnotatedType root = labels.getAnnotatedType();
        System.out.println("root Type=" + root.getType().getTypeName());
        System.out.println("root Mark=" + mark(root));

        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) root;
        AnnotatedType element =
                parameterized.getAnnotatedActualTypeArguments()[0];
        System.out.println("argument Type=" + element.getType().getTypeName());
        System.out.println("argument Mark=" + mark(element));

        Field tags = Box.class.getDeclaredField("tags");
        AnnotatedArrayType array =
                (AnnotatedArrayType) tags.getAnnotatedType();
        System.out.println("array Type=" + array.getType().getTypeName());
        System.out.println("dimension Mark=" + mark(array));
        System.out.println("component Mark="
                + mark(array.getAnnotatedGenericComponentType()));

        Field numbers = Box.class.getDeclaredField("numbers");
        AnnotatedParameterizedType num =
                (AnnotatedParameterizedType) numbers.getAnnotatedType();
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType) num.getAnnotatedActualTypeArguments()[0];
        System.out.println("wildcard Type="
                + wildcard.getType().getTypeName());
        System.out.println("wildcard Mark=" + mark(wildcard));
        System.out.println("upper Mark="
                + mark(wildcard.getAnnotatedUpperBounds()[0]));

        TypeVariable<Class<Box>> var = Box.class.getTypeParameters()[0];
        AnnotatedType bound = var.getAnnotatedBounds()[0];
        System.out.println("bound Type=" + bound.getType().getTypeName());
        System.out.println("bound Mark=" + mark(bound));

        Method echo = Box.class.getDeclaredMethod("echo", String.class);
        System.out.println("return Mark="
                + mark(echo.getAnnotatedReturnType()));
        System.out.println("param Mark="
                + mark(echo.getAnnotatedParameterTypes()[0]));
        System.out.println("declared field annotations="
                + labels.getDeclaredAnnotations().length);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AnnotatedTypeLesson.java
java AnnotatedTypeLesson
~~~

Stdout output from the program above:

~~~text
root Type=java.util.List<java.lang.String>
root Mark=list
argument Type=java.lang.String
argument Mark=element
array Type=java.lang.String[]
dimension Mark=dimension
component Mark=component
wildcard Type=? extends java.lang.Number
wildcard Mark=wildcard
upper Mark=upper
bound Type=java.lang.Number
bound Mark=bound
return Mark=return
param Mark=param
declared field annotations=0
~~~

### Interpreting the results

- `labels` has underlying type `List<String>`: `root.getType()` displays the generic structure, while `mark(root)` retrieves `@Mark("list")` at the `List` type position.
- The child node of `AnnotatedParameterizedType` has underlying type `String` with `@Mark("element")`, not an annotation on the field itself.
- `String @Mark("dimension") []` has `AnnotatedArrayType` at the root for the **array dimension**, while `@Mark("component") String` attaches to the **element** type. The two annotation positions are different.
- In `List<@Mark("wildcard") ? extends @Mark("upper") Number>`, the wildcard carries `"wildcard"`; the upper bound `Number` carries `"upper"`.
- The bound of `T extends Number` carries `@Mark("bound")`; annotations on the return type and parameter type are `"return"` and `"param"` respectively.
- `labels.getDeclaredAnnotations().length == 0` because the annotations in the example are at **type-use** positions, not annotations declared directly on the field. This result illustrates why reading annotations only from `Field` is insufficient.

The program above does not rely on guessing logic based on class names of internal `Type` implementations. `getTypeName()` helps print the type shape readably; the underlying API remains `Type`.

## 6. Multidimensional arrays: annotations sit on each dimension

Java supports attaching type-use annotations to both the element type and each array dimension:

~~~java
@Mark("element") String @Mark("outer") [] @Mark("inner") [] matrix;
~~~

The declaration snippet above is purely illustrative inside a class that has the `@Mark` annotation as in the complete example. When Reflection describes `matrix`:

1. `field.getAnnotatedType()` represents **the outermost array type** (`AnnotatedArrayType`) and holds `@Mark("outer")`.
2. `getAnnotatedGenericComponentType()` steps down one dimension; for a 2D array, this node is still an `AnnotatedArrayType`, carrying `@Mark("inner")`.
3. Stepping down one more time reaches the element type `String` with `@Mark("element")`.

Writing `String @Mark("x") []` differs in **annotation position** from `@Mark("x") String[]`. If you need to interpret an array field accurately, you must follow the `AnnotatedArrayType` chain rather than inspecting only `String[][].class`. On generic array types, the underlying type can be `GenericArrayType`; do not assume it is always `Class<?>[]`.

## 7. When should you take `getType()`, and when must you traverse `AnnotatedType`?

### Only need the type structure?

If a library only needs to know a field is `List<String>` to map data, `Field.getGenericType()` or `AnnotatedType.getType()` provides the appropriate `Type` structure. When you want to know the generic argument, check `instanceof ParameterizedType` and call `getActualTypeArguments()`. The result is **`Type`**, which does not directly carry type-use annotations of each branch.

### Need rules marked by annotations?

If a framework uses `@NonNull`, `@Sensitive`, `@Validated`, or a custom annotation to drive schema checks, it needs to traverse **the `AnnotatedType` nodes** and read annotations at the exact positions. Safe pattern:

~~~java
AnnotatedType type = field.getAnnotatedType();

if (type instanceof AnnotatedParameterizedType parameterized) {
    for (AnnotatedType argument :
            parameterized.getAnnotatedActualTypeArguments()) {
        // Check annotations on EACH type argument, then continue recursing.
    }
}
~~~

This is an illustrative snippet inside a method that has `Field field`. Do not cast every `AnnotatedType` to `AnnotatedParameterizedType`; the underlying type could be `Class`, `TypeVariable`, `GenericArrayType`, `WildcardType`, or another form. When deeper processing is required, branch on each corresponding `Annotated...` interface.

### Type-use metadata does not mean automatic validation

A `@NonNull` annotation on a type argument **does not cause the JVM to automatically forbid null**, and `AnnotatedType.getAnnotation` only reads metadata. Real data checking requires an enforcement mechanism implemented by a library or application. Even when the annotation is present, `Type` cannot replace runtime element checks.

Similarly, an annotation at `List<@NonNull String>` does not turn Java generics into *reified generics*. Due to erasure, the JVM lacks runtime information to prove that every element of an arbitrary `List` is genuinely a `String`.

## 8. Conditions for Reflection to read annotations

Common definition:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNull { }
~~~

Points to note:

- `TYPE_USE` allows an annotation to appear on **type-use positions**. `TYPE_PARAMETER` is a separate target for type variable declarations, e.g., right on the `T` of `class Box<@A T>`; if both are needed, declare `@Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})`.
- `RetentionPolicy.RUNTIME` is required if you want to read the annotation via Reflection at runtime. `SOURCE` does not exist in the class file; `CLASS` is written to the class file but is not present in normal runtime Reflection.
- The compiler can emit type-use annotations into metadata attributes in the class file; what becomes visible depends on declaring the proper target/retention and the Java element actually being compiled.
- `getAnnotation(MyAnnotation.class)` returns `null` when the annotation is not at that exact position. If the annotation is on a **child node**, querying only the root node is insufficient.
- Annotations applied to methods/classes are **distinct** from annotations applied to types. An annotation may allow multiple targets, and you must pick the API according to the actual question.

**Do not treat `getType()` as a tool for retrieving annotations:** `Type` is underlying type information. To walk type-use metadata, you must keep and traverse `AnnotatedType`.

## 9. Common mistakes

| Mistake | Correct understanding |
| --- | --- |
| "`AnnotatedType` always has `Class<?> getType()`." | `getType()` returns `Type`; generics are usually `ParameterizedType`, wildcards are `WildcardType`, etc. |
| "An annotation on `List<@A String>` is on `List`." | `@A` is on **the `String` argument**; go through `getAnnotatedActualTypeArguments()`. |
| "Reading `field.getAnnotations()` is enough for all related annotations." | That API queries annotations **on the field element**; type-use annotations must be queried via `getAnnotatedType()`. |
| "`@A String[]` and `String @A []` are the same." | The annotation can attach to **different type components**: the element or the array dimension. |
| "Every `AnnotatedType` is an `AnnotatedParameterizedType`." | You must check `instanceof` before casting. |
| "Not seeing an annotation means the class file has no annotation." | You may be querying the wrong node, the target is inappropriate, or retention is not `RUNTIME`. |
| "`AnnotatedType.getType()` tells you the generic type argument of the current object." | It describes **the declared type at the Reflection position**; Java generics do not reify all runtime type arguments. |
| "`isAnnotationPresent` on the root automatically checks the whole tree." | No: it checks **the current node**; to check children you must traverse explicitly. |

## 10. Practice checklist

1. **Identify the declaration location** to inspect: field, method parameter, return type, superclass, interface, type-variable bound, array, or record component.
2. **Obtain `AnnotatedType` with the right API**. Do not substitute `getAnnotations()` on the element when type-use annotations are needed.
3. **Read `getType()`** to understand the underlying type being described; use `instanceof` for `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType` when needed.
4. **Read annotations on the right node** with `getAnnotation`/`getAnnotations`.
5. **Traverse child nodes** via the `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable` interfaces; for inner classes, also check `getAnnotatedOwnerType()`.
6. **Verify `@Target(TYPE_USE)` and `@Retention(RUNTIME)`** of the annotation you want to read.
7. **Do not infer validation logic or runtime castability from metadata alone**; those rules are implemented by the application.

### Self-check questions

**1.** For `List<@Mark String>`, is querying annotations on `field.getAnnotatedType()` guaranteed to find `@Mark`?  
**No.** The annotation is on the `String` generic argument node; you must traverse `getAnnotatedActualTypeArguments()[0]`.

**2.** Does `AnnotatedType.getType()` return `Class<?>` for `List<String>`?  
**Not by default.** It returns `Type`, which in this case is typically a `ParameterizedType` representing `List<String>`.

**3.** In `String @Mark []`, where is `@Mark` attached?  
**The array dimension**, so inspect the `AnnotatedArrayType` node. `@Mark String[]` has a different annotation position.

**4.** How do you find the annotation on `? extends @Mark Number`?  
Go to `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]`, then call `getAnnotation(Mark.class)`.

**5.** Can an annotation with `@Retention(CLASS)` be read from `AnnotatedType` using runtime Reflection?  
**Not via standard Reflection.** To read it at runtime, `RUNTIME` is required.

**6.** Do `Field.getType()` and `Field.getAnnotatedType().getType()` always match in their level of generic information?  
**No.** The first API returns raw `Class<?>`; the second returns the underlying `Type` of the type position, which can preserve generic structure.

**Conclusion:** `AnnotatedType` is **a type-use node carrying annotations**. `getType()` returns **the underlying type at that node**, while `getAnnotation()` and the `Annotated...` interfaces allow reading annotations appearing **at each exact position** in trees of generics, arrays, wildcards, and type-variable bounds.

### Official references

- [JDK 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [JDK 17 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [JDK 17 — `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html)
- [JDK 17 — `Field.getAnnotatedType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType())
- [JLS 17 §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)
