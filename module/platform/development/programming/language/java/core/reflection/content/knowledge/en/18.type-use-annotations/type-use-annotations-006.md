# AnnotatedTypeVariable and Annotated Bounds in Java Reflection

## 1. The problem: where is an annotation placed on a type variable?

Java supports annotations on **used types** (*type-use annotation*) and on **type parameter declarations** (*type-parameter declaration*). When using Reflection to read generics, you must distinguish three positions:

1. Annotation on **the type variable declaration**: `<@ParameterMark T ...>`.
2. Annotation on **a bound of the type variable**: `T extends @BoundMark Number`.
3. Annotation on **a use of the type variable**: `@UseMark T value` or `Comparable<@UseMark T>`.

They are not automatically the same annotation, nor do they necessarily live on the same Reflection object.

Example:

```java
class Sample<@ParameterMark T extends @BoundMark Number
        & Comparable<@UseMark T>> {
    @UseMark T value;
}
```

Here:

- `@ParameterMark` attaches to the **declaration** of `T` itself.
- `@BoundMark` attaches to the **`Number` type used as an upper bound** of `T`.
- `@UseMark` inside `Comparable<@UseMark T>` attaches to **the use of `T` as a type argument**.
- `@UseMark` in `@UseMark T value` attaches to **the field's type**, without automatically becoming a declaration annotation of `T`.

To read these positions accurately, Java provides `TypeVariable`, `AnnotatedType`, `AnnotatedTypeVariable`, and `AnnotatedParameterizedType`.

**Core idea:** `AnnotatedTypeVariable` represents *a use of a type that is a type variable* (such as `@UseMark T`), while also letting you read the **annotated upper bounds** of that type variable via `getAnnotatedBounds()`. This is not a `Class<?>` of `T`: a generic type variable and a runtime class are two different concepts.

## 2. Related APIs and the relationships between them

| API | Return type | Purpose |
| --- | --- | --- |
| `Class.getTypeParameters()` | `TypeVariable<?>[]` | Type variables declared by the class/interface |
| `Method.getTypeParameters()` | `TypeVariable<Method>[]` | Type variables declared by a generic method |
| `Constructor.getTypeParameters()` | `TypeVariable<Constructor<?>>[]` | Type variables declared by a generic constructor |
| `TypeVariable.getName()` | `String` | Name such as `T`, `U` |
| `TypeVariable.getBounds()` | `Type[]` | Upper bounds, **without use-site annotations** |
| `TypeVariable.getAnnotatedBounds()` | `AnnotatedType[]` | Upper bounds **which may carry type-use annotations** |
| `TypeVariable.getAnnotation(...)` | annotation or `null` | Annotation on **the type variable declaration** |
| `Field.getGenericType()` | `Type` | Generic type of the field (may be `TypeVariable`), does not express type-use annotation positions |
| `Field.getAnnotatedType()` | `AnnotatedType` | Field type along with annotations at the use site |
| `Method.getAnnotatedReturnType()` | `AnnotatedType` | Return type, including annotations at the use site |
| `Executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` | Parameter types along with annotations |
| `AnnotatedTypeVariable.getAnnotatedBounds()` | `AnnotatedType[]` | Annotated bounds associated with the referenced type variable |
| `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | `AnnotatedType[]` | Annotated type arguments located **inside** a parameterized type |
| `AnnotatedType.getType()` | `Type` | Underlying type represented by an `AnnotatedType` |
| `AnnotatedType.getAnnotation(...)` | annotation or `null` | Annotation at **the exact type position** represented by this object |

Note: `AnnotatedTypeVariable` is a **subinterface of `AnnotatedType`**, not an object you can instantiate arbitrarily with `new AnnotatedTypeVariable(...)`. You obtain it through Reflection APIs and check it with `instanceof`.

### Distinguishing two common entry points

**Entry from the declaration:**

```java
TypeVariable<?> t = Sample.class.getTypeParameters()[0];
AnnotatedType[] annotatedBounds = t.getAnnotatedBounds();
```

**Entry from the use site:**

```java
Field field = Sample.class.getDeclaredField("value");
AnnotatedType fieldType = field.getAnnotatedType();
if (fieldType instanceof AnnotatedTypeVariable variableUse) {
    AnnotatedType[] bounds = variableUse.getAnnotatedBounds();
}
```

Both can help observe the bounds belonging to `T`'s declaration, yet **the use site** also carries its own annotations on `@UseMark T`. Do not read only `getAnnotatedBounds()` and conclude that all annotations of the field have been retrieved.

The code snippets in this section illustrate the APIs; they must be placed inside a method handling `NoSuchFieldException` together with suitable class/annotation declarations. The complete program is in section 4.

## 3. Conditions for annotations to be present when Reflection runs

Appropriate annotation declarations are required:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface UseMark {}
```

This is an **illustrative snippet**, requiring `import java.lang.annotation.*`. In the complete program below, these declarations reside in the same file.

- `ElementType.TYPE_PARAMETER` targets **the declaration** of a type variable such as `<@ParameterMark T>`.
- `ElementType.TYPE_USE` targets **type-use positions**, including the bound `extends @BoundMark Number`, type argument `Comparable<@UseMark T>`, or field `@UseMark T value`.
- `RetentionPolicy.RUNTIME` lets Reflection see the annotation at runtime. If an annotation only has `CLASS` retention or `SOURCE` retention, runtime APIs will not provide it as in the example.
- `@Inherited` does not automatically propagate type-use annotations across generic bounds; it should not be used to reason about annotated bounds.
- If using repeatable annotations, consider `getAnnotationsByType(...)` instead of only `getAnnotation(...)`.

**Remember to distinguish:** an annotation on **the declaration of `T`** is not automatically copied onto every use of `T`; nor does an annotation on **a bound of `T`** mean that every field of type `T` carries that annotation at the field's position.

## 4. Complete and verifiable Java 17+ example

Create the file **`AnnotatedTypeVariableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface UseMark {}

public class AnnotatedTypeVariableDemo {
    static class Sample<@ParameterMark T extends @BoundMark Number
            & Comparable<@UseMark T>> {
        @UseMark T value;
    }

    static class Unbounded<V> {}

    static <@ParameterMark U extends @BoundMark CharSequence>
            @UseMark U echo(@UseMark U value) {
        return value;
    }

    public static void main(String[] args) throws Exception {
        TypeVariable<?> variable = Sample.class.getTypeParameters()[0];
        System.out.println("Variable: " + variable.getName());
        System.out.println("Type-parameter annotation: "
                + (variable.getAnnotation(ParameterMark.class) != null));
        System.out.println("Bounds count: " + variable.getBounds().length);

        AnnotatedType[] bounds = variable.getAnnotatedBounds();
        for (int i = 0; i < bounds.length; i++) {
            System.out.println("Bound " + i + ": "
                    + bounds[i].getType().getTypeName());
            System.out.println("  @BoundMark: "
                    + (bounds[i].getAnnotation(BoundMark.class) != null));
        }

        AnnotatedParameterizedType comparable =
                (AnnotatedParameterizedType) bounds[1];
        AnnotatedType argument =
                comparable.getAnnotatedActualTypeArguments()[0];
        System.out.println("Comparable argument @UseMark: "
                + (argument.getAnnotation(UseMark.class) != null));
        System.out.println("Comparable argument is variable: "
                + (argument instanceof AnnotatedTypeVariable));

        Field field = Sample.class.getDeclaredField("value");
        AnnotatedType fieldType = field.getAnnotatedType();
        System.out.println("Field erased type: "
                + field.getType().getSimpleName());
        System.out.println("Field generic variable: "
                + (field.getGenericType() instanceof TypeVariable));
        System.out.println("Field is variable: "
                + (fieldType instanceof AnnotatedTypeVariable));
        System.out.println("Field use @UseMark: "
                + (fieldType.getAnnotation(UseMark.class) != null));

        AnnotatedTypeVariable reference =
                (AnnotatedTypeVariable) fieldType;
        System.out.println("Field type variable: "
                + reference.getType().getTypeName());
        System.out.println("Field variable bounds: "
                + reference.getAnnotatedBounds().length);

        Method method = AnnotatedTypeVariableDemo.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodVar = method.getTypeParameters()[0];
        System.out.println("Method variable: " + methodVar.getName());
        System.out.println("Method bound @BoundMark: "
                + (methodVar.getAnnotatedBounds()[0]
                        .getAnnotation(BoundMark.class) != null));
        System.out.println("Method parameter is variable: "
                + (method.getAnnotatedParameterTypes()[0]
                        instanceof AnnotatedTypeVariable));
        System.out.println("Method return @UseMark: "
                + (method.getAnnotatedReturnType()
                        .getAnnotation(UseMark.class) != null));

        AnnotatedType defaultBound =
                Unbounded.class.getTypeParameters()[0]
                        .getAnnotatedBounds()[0];
        System.out.println("Unbounded default: "
                + defaultBound.getType().getTypeName());
        System.out.println("Unbounded annotations: "
                + defaultBound.getAnnotations().length);
    }
}
```

Compile/run from the directory containing the file using JDK 17 or newer:

```bash
javac --release 17 AnnotatedTypeVariableDemo.java
java AnnotatedTypeVariableDemo
```

**Actual stdout (compiled and run on JDK 21 with `--release 17`):**

```text
Variable: T
Type-parameter annotation: true
Bounds count: 2
Bound 0: java.lang.Number
  @BoundMark: true
Bound 1: java.lang.Comparable<T>
  @BoundMark: false
Comparable argument @UseMark: true
Comparable argument is variable: true
Field erased type: Number
Field generic variable: true
Field is variable: true
Field use @UseMark: true
Field type variable: T
Field variable bounds: 2
Method variable: U
Method bound @BoundMark: true
Method parameter is variable: true
Method return @UseMark: true
Unbounded default: java.lang.Object
Unbounded annotations: 0
```

### Explaining four key findings

**(1) The declaration of `T` and the bound `Number` are two different places.**

`variable.getAnnotation(ParameterMark.class)` returns the annotation on **the type parameter declaration** `T`. Meanwhile, `bounds[0].getAnnotation(BoundMark.class)` returns the annotation on **the `Number` type serving as a bound**. If you use `variable.getAnnotation(BoundMark.class)` to ask "Does Number have an annotation?", you have queried the wrong Reflection object.

**(2) An annotated bound can be a generic/parameterized type.**

The second bound is `Comparable<T>`. The `@UseMark` flag is not on the `bounds[1]` object itself (the `Comparable` shell); it sits **inside the type argument `T`**. Therefore you must cast to the proper type:

```java
AnnotatedParameterizedType apt =
        (AnnotatedParameterizedType) bounds[1];
AnnotatedType inner = apt.getAnnotatedActualTypeArguments()[0];
boolean marked = inner.isAnnotationPresent(UseMark.class);
```

In this case, `inner` is also an `AnnotatedTypeVariable` because the type argument used is `T`. If you only call `bounds[1].getAnnotations()` and stop, you will miss nested annotations.

**(3) A field of type `T` has both a generic type and an annotated type.**

`field.getType()` returns `Number.class` due to **type erasure**: in `T extends Number & Comparable<T>`, the erasure of `T` is the first bound `Number`. `field.getGenericType()` still represents `T` as a `TypeVariable`. `field.getAnnotatedType()` returns an `AnnotatedTypeVariable` carrying the annotation on the use `@UseMark T`.

The three APIs describe **three different layers of information**, with no contradiction:

| Call on field `@UseMark T value` | Information obtained |
| --- | --- |
| `field.getType()` | Runtime erased type: `Number.class` |
| `field.getGenericType()` | Generic type: `TypeVariable` named `T` |
| `field.getAnnotatedType()` | `AnnotatedTypeVariable` representing `@UseMark T` |
| `((AnnotatedTypeVariable) field.getAnnotatedType()).getAnnotatedBounds()` | Two bounds: `@BoundMark Number` and `Comparable<@UseMark T>` |

**(4) Generic methods also have their own type variables.**

`echo` declares `<@ParameterMark U extends @BoundMark CharSequence>`. Because the erasure of `U` is `CharSequence`, looking up the method with `getDeclaredMethod` requires passing `CharSequence.class`, not `Object.class` or an arbitrary class of a passed value.

`method.getTypeParameters()[0]` represents **the declaration of `U`**; `getAnnotatedParameterTypes()[0]` and `getAnnotatedReturnType()` represent **the use positions of `U` in parameter/return**. The program observes all three of these positions.

## 5. How to use `AnnotatedTypeVariable.getAnnotatedBounds()`

Suppose from a field, parameter, or return type you have `AnnotatedType annotated`:

```java
if (annotated instanceof AnnotatedTypeVariable variableUse) {
    for (AnnotatedType bound : variableUse.getAnnotatedBounds()) {
        System.out.println(bound.getType().getTypeName());
        for (Annotation mark : bound.getAnnotations()) {
            System.out.println(mark.annotationType().getName());
        }
    }
}
```

This is an **illustrative snippet** requiring `import java.lang.annotation.Annotation` and `java.lang.reflect.*`; the `annotated` variable is supplied by the caller.

Proper workflow:

1. Check with `instanceof AnnotatedTypeVariable` before casting. A field could be `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, or a non-generic type rather than a type variable.
2. Call `getType()`; for `AnnotatedTypeVariable`, the corresponding underlying `Type` object is a `TypeVariable<?>`.
3. Call `getAnnotatedBounds()` to obtain **each upper bound**, in exact declaration order.
4. On each bound, read annotations attached **directly to the bound** using `getAnnotations()`, `getAnnotation(...)`, or `getAnnotationsByType(...)`.
5. If a bound has generic type arguments, cast safely to `AnnotatedParameterizedType` and traverse `getAnnotatedActualTypeArguments()` to find nested annotations inside.
6. If you need annotations at **the type variable use site**, read `variableUse.getAnnotations()`; they are not replaced by annotations on bounds.

### Multi-component bounds

Java supports intersection upper bounds:

```java
class Sample<T extends Number & Comparable<T>> {}
```

`T` has two upper bounds in order: `Number` and `Comparable<T>`. `TypeVariable.getBounds()` and `getAnnotatedBounds()` both represent **two positions**; the difference is that the annotated API preserves annotation metadata on each bound type use.

Do not assume there is only a single bound. For intersections, a class bound (if present) must appear first, and interface bounds follow according to Java rules. Corresponding annotations attach to the exact component they precede.

If **no bound is declared**:

```java
class Plain<T> {}
```

the default bound of `T` is `Object` with no annotations. `getAnnotatedBounds()` returns an array containing one `AnnotatedType` for unannotated `Object`; it does **not** return an empty array. This is demonstrated by `Unbounded<V>` in the runnable example in section 4.

## 6. Reading declaration annotations vs. reading type annotations

| Syntax in source | Where to read the annotation | Metadata entity |
| --- | --- | --- |
| `<@ParameterMark T>` | `typeVariable.getAnnotation(ParameterMark.class)` | Type variable declaration |
| `T extends @BoundMark Number` | `typeVariable.getAnnotatedBounds()[0].getAnnotation(BoundMark.class)` | Upper bound |
| `Comparable<@UseMark T>` | Cast bound to `AnnotatedParameterizedType` then read annotated argument | Type argument inside bound |
| `@UseMark T value` | `field.getAnnotatedType().getAnnotation(UseMark.class)` | Use of `T` in field |
| `@UseMark U echo(...)` | `method.getAnnotatedReturnType().getAnnotation(UseMark.class)` | Use of `U` in return type |
| `echo(@UseMark U value)` | `method.getAnnotatedParameterTypes()[0].getAnnotation(UseMark.class)` | Use of `U` in parameter |

**Avoid confusion:** `TypeVariable` is an `AnnotatedElement` and can return annotations from the type parameter declaration; however, `AnnotatedTypeVariable` implements `AnnotatedType` and represents annotations attached to a **specific type use**. Both share the method name `getAnnotation(...)`, yet the question asked of the two objects is different.

Some annotations have `@Target` for multiple places, such as both `TYPE_PARAMETER` and `TYPE_USE`. In that case checking positions remains critical; identical annotation names do not mean the runtime always stores them under the same target kind.

## 7. Generic erasure: Annotations on bounds do not change the runtime class

There are two independent concerns:

- **Generic signature** describes `T extends Number & Comparable<T>`. Reflection accesses it via `TypeVariable` and child `Type` instances.
- **Runtime erased type** of field `T value` is `Number` when `Number` is the first bound. The erased type does not store "this object is a specific subtype of T" at runtime.
- **TYPE_USE annotation** describes annotations on type positions in signatures; it does not automatically enforce data validation constraints at runtime.

For example, if `@BoundMark` carries the business meaning "validated", Reflection only reads that marker. Actually checking data still requires a separate validator/framework; the JVM does not replace validation code based solely on custom type-use markers.

A generic field containing a type variable cannot be used to automatically infer whether `T` is `Integer` or `Long` on a specific object due to type erasure. If you need actual type arguments of a parameterized superclass/interface, you must analyze `ParameterizedType` from the appropriate usage declaration and account for inheritance; that is a different problem from reading annotations on upper bounds.

## 8. When bounds are parameterized, array, or wildcard types

`AnnotatedType` has specialized subtypes and each subtype opens another structural layer:

| Type shape | Subtype to check | How to drill down |
| --- | --- | --- |
| `T` | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| `List<@A String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| `@A String[]` or `String @A []` | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `? extends @A Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` |
| `? super @A Integer` | `AnnotatedWildcardType` | `getAnnotatedLowerBounds()` |

Each level can carry its own annotations. You should not call only `getAnnotations()` at the outermost node and conclude you have retrieved all nested annotations.

**Especially with recursive bounds:**

```java
interface Node<T extends Comparable<T>> {}
```

A type variable can reappear inside its own bound (*F-bounded polymorphism*). Writing a recursive metadata traverser from `T` → `Comparable<T>` → `T` → bound... will loop infinitely if visited items are not tracked.

When writing a general traverser, you must record the `TypeVariable<?>` declarations already traversed in context (e.g., a set of visited variables); distinguish **annotations on the current use** from **expanding the declared bounds**. You can still record the annotations on the use node before deciding not to re-traverse its bounds.

`AnnotatedTypeVariable.getAnnotatedOwnerType()` returns `null` per the API contract; owner types apply to other nested member type forms, not as a mechanism to find where `T` is declared. If you need to know which class/method/constructor declared type variable `T`, use `((TypeVariable<?>) annotated.getType()).getGenericDeclaration()`.

## 9. Applying this in generic/annotation analysis tools

A schema generator, validation framework, or API documentation tool can use annotated bounds to understand type-shape constraints and metadata at exact positions. Practical workflow:

1. Identify the source: type variable declared on a **class**, **method**, or **constructor**, or type variable used in a **field/parameter/return**.
2. Retrieve declaration metadata via `getTypeParameters()` when type parameter annotations are needed.
3. Retrieve the annotated type of the use site via `getAnnotatedType()`, `getAnnotatedReturnType()`, or `getAnnotatedParameterTypes()`.
4. Branch by `AnnotatedType` subtype using `instanceof`; for variables, read `getAnnotatedBounds()`; for parameterized bounds, traverse annotated type arguments.
5. Distinguish annotations on the type variable declaration, on bounds, and on type uses. Do not transfer annotations from one position to another without an explicit business rule.
6. For class files from other compilers or libraries without `RUNTIME` retention, accept missing annotation metadata without inferring that the annotation never existed in source.
7. Prevent cycles on F-bounded/recursive generics; handle `TypeNotPresentException` and `MalformedParameterizedTypeException` when generic metadata is broken or referenced types are unavailable.
8. Write tests against real class files to confirm annotation placement, bound ordering, and nested annotation positions.

### A small helper to report annotated bounds

Place the following method in a utility class with `import java.lang.reflect.*` and `java.lang.annotation.*`:

```java
static void printDirectBoundAnnotations(TypeVariable<?> variable) {
    for (AnnotatedType bound : variable.getAnnotatedBounds()) {
        System.out.println("Bound: " + bound.getType().getTypeName());
        for (Annotation annotation : bound.getDeclaredAnnotations()) {
            System.out.println("  @" + annotation.annotationType().getSimpleName());
        }
    }
}
```

This is an **illustrative snippet**, reading only annotations attached directly to each **outer-level bound**, without traversing deeper into type arguments. For `Comparable<@UseMark T>`, if you want to capture `@UseMark`, you must add the `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` traversal step as in section 4.

## 10. Common confusions

| Confusion | Correct conclusion |
| --- | --- |
| "`TypeVariable.getBounds()` also returns annotations." | `getBounds()` returns `Type[]`; use `getAnnotatedBounds()` to retrieve annotations |
| "`AnnotatedTypeVariable` is the runtime class equivalent to `T`." | It is metadata for a type-variable use; `getType()` is `TypeVariable`, not a concrete `Class<?>` |
| "An annotation on `<@P T>` is an annotation on every bound of `T`." | Annotations on the declaration and annotations on bounds sit at two different positions |
| "`T extends @A Number` makes every `@T` field have `@A`." | Annotations on a bound do not automatically transfer to field positions |
| "Reading `bounds[1].getAnnotations()` is enough to get `Comparable<@A T>`." | The type argument annotation is nested inside `AnnotatedParameterizedType` |
| "If `extends` is not declared, annotated bounds are empty." | There is a default unannotated `Object` bound |
| "A type variable has only one bound." | Multiple upper bounds joined by `&` are possible |
| "`field.getType()` returns `TypeVariable`." | `getType()` returns erased `Class<?>`; use `getGenericType()` |
| "`TYPE_USE` annotations are readable at runtime by default." | `RetentionPolicy.RUNTIME` is required for Reflection to read them |
| "F-bounds can be expanded recursively without limit." | Easy to create cycles; you must track visited type variables |
| "Type-use metadata validates data automatically." | Markers are stored for other tools to interpret, not self-running validators |

## 11. Self-check questions

1. Given `class Box<@ParameterMark T extends @BoundMark Number> {}`, which two APIs read `@ParameterMark` and `@BoundMark`?
2. Why do `Field.getGenericType()` and `Field.getAnnotatedType()` provide different information?
3. With `Comparable<@UseMark T>` as an upper bound, does `@UseMark` sit on the `AnnotatedType` object for `Comparable` or on the inner type argument?
4. If a type variable does not declare `extends`, how many elements does `getAnnotatedBounds()` have and what type is it?
5. What does `AnnotatedTypeVariable.getAnnotatedBounds()` mean when `AnnotatedTypeVariable` is obtained from field `@UseMark T value`?
6. Why are `@Target(TYPE_USE)` and `@Retention(RUNTIME)` needed for an annotation you want to read on a bound via Reflection?
7. Does a field of type `T extends Number & Comparable<T>` have `getType()` as `T` or `Number.class`? How do you read `T` back at the generic level?
8. What can happen if a bound traverser expands `T extends Comparable<T>` without cycle detection?

**Answers:** (1) `TypeVariable.getAnnotation(...)` and `TypeVariable.getAnnotatedBounds()[0].getAnnotation(...)`; (2) one provides the underlying generic type, the other includes type-use annotations; (3) the inner type argument; (4) one unannotated `Object`; (5) returns the annotated upper bounds of `T`, whereas the annotation directly on the field is read from `AnnotatedTypeVariable` itself; (6) proper target and runtime visibility; (7) `Number.class`, use `getGenericType()`/`getAnnotatedType()`; (8) infinite loop/stack overflow.

## 12. Conclusion

**`AnnotatedTypeVariable` helps analyze an annotated use of a type variable and inspect its potentially annotated upper bounds.** To read accurately, separate three layers: *type-parameter declaration*, *bound type use*, and *variable type use*. Use `TypeVariable.getAnnotatedBounds()` or `AnnotatedTypeVariable.getAnnotatedBounds()` for bounds, and use the `AnnotatedParameterizedType`, `AnnotatedArrayType`, and `AnnotatedWildcardType` subtypes to find annotations inside complex type structures. Only generic/annotation data still present in the runtime class file can be read; Reflection does not eliminate type erasure or replace business validation.

Official references:

- [Java SE 21 — AnnotatedTypeVariable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html).
- [Java SE 21 — TypeVariable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 21 — AnnotatedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 21 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [JLS 17 `4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4) and [JLS 17 `9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).