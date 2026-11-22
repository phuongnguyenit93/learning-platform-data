# AnnotatedWildcardType and Bound Annotations in Java Reflection

## 1. Context: annotations can appear directly on `?` or on its bound

In Java, a wildcard is a type argument used in generics, such as `List<?>`, `List<? extends Number>`, and `List<? super Integer>`. Since Java 8, an annotation with `@Target(ElementType.TYPE_USE)` can appear **at type-use positions**, including the wildcard and the bound type.

Two distinct positions:

```java
List<@Mark("wildcard") ? extends @Mark("bound") Number> values;
```

- `@Mark("wildcard")` sits **on the wildcard `?` itself**.
- `@Mark("bound")` sits **on the `Number` type** after the `extends` keyword.

These two annotations do not replace each other, even though both appear in one generic declaration. When using Reflection:

- `AnnotatedWildcardType.getAnnotation(Mark.class)` reads the annotation attached to `?`.
- `AnnotatedWildcardType.getAnnotatedUpperBounds()[0].getAnnotation(Mark.class)` reads the annotation attached to the upper bound `Number`.

If you only obtain `WildcardType` via `Field.getGenericType()` and call `getUpperBounds()`, you observe **the bound's type**, but **you cannot read the bound's type-use annotation** using the plain `Type` API. To preserve annotation metadata by position, you need the `AnnotatedType` branch and its subinterfaces.

**Goal:** understand `AnnotatedWildcardType`, accessing annotations on wildcards/upper bounds/lower bounds, implicit bound cases, traversing nested generics, and the limits of runtime metadata in Java 17+.

## 2. Wildcards and bounds in the Java language

Three common forms:

| Written in Java | Upper bound | Lower bound | Type meaning |
| --- | --- | --- | --- |
| `?` | Implicit `Object` | No explicit lower bound | Unbounded wildcard (explicitly) |
| `? extends Number` | Explicit `Number` | No explicit lower bound | Unknown type argument, upper-bounded by `Number` |
| `? super Integer` | Implicit `Object` | Explicit `Integer` | Unknown type argument, lower-bounded by `Integer` |

Examples of annotations at each position:

```java
List<@Mark("any") ?> any;
List<@Mark("wild") ? extends @Mark("upper") Number> upper;
List<@Mark("wild") ? super @Mark("lower") Integer> lower;
List<? extends @Mark("onlyUpper") Number> onlyUpper;
```

These examples are **illustrative field declarations**; `Mark` must be defined with `TYPE_USE` and `RUNTIME` as in the complete example in section 5.

Pay attention to the syntax:

- `@Mark("wild") ?`: annotation on **the wildcard node**.
- `? extends @Mark("upper") Number`: annotation on **the upper-bound type node**.
- `? super @Mark("lower") Integer`: annotation on **the lower-bound type node**.
- `?` has no explicit bound, yet per Reflection it still has an unannotated upper bound of `Object`.

Under current Java wildcard syntax, a wildcard cannot have both `extends` and `super`, and you cannot write an intersection bound like `? extends A & B` in Java source. However, the Reflection methods return **arrays** of bounds; processing code should iterate the array instead of assuming every runtime has only index `[0]`.

## 3. Where does `AnnotatedWildcardType` sit in Reflection?

`java.lang.reflect.AnnotatedWildcardType` is an interface extending `AnnotatedType` (since Java 8), representing a wildcard type argument that may be annotated; upper/lower bounds may also carry annotations.

Primary APIs:

| API | Returns | What to remember |
| --- | --- | --- |
| `AnnotatedWildcardType.getType()` | `Type` (usually `WildcardType`) | Gives the generic shape, not the place to read bound annotations |
| `getAnnotations()` | `Annotation[]` | Annotations on the wildcard node itself |
| `getAnnotation(Mark.class)` | `Mark` or `null` | Directly queries the marker on the wildcard |
| `getAnnotatedUpperBounds()` | `AnnotatedType[]` | Upper bounds **which may have their own annotations** |
| `getAnnotatedLowerBounds()` | `AnnotatedType[]` | Lower bounds **which may have their own annotations** |
| `getAnnotatedOwnerType()` | `null` for wildcards | Not an API for accessing upper/lower bounds |

`AnnotatedWildcardType` belongs to the **annotated** branch. It differs from `java.lang.reflect.WildcardType`:

```java
WildcardType wildcard = (WildcardType) annotatedWildcard.getType();
Type[] upperTypes = wildcard.getUpperBounds();
Type[] lowerTypes = wildcard.getLowerBounds();

AnnotatedType[] annotatedUpper =
        annotatedWildcard.getAnnotatedUpperBounds();
AnnotatedType[] annotatedLower =
        annotatedWildcard.getAnnotatedLowerBounds();
```

This is an **illustrative snippet**: it requires `import java.lang.reflect.*` and an already defined `annotatedWildcard` variable.

- `WildcardType.getUpperBounds()` and `getLowerBounds()` return plain generic types (`Type`), such as `Number.class` or `Integer.class`.
- `AnnotatedWildcardType.getAnnotatedUpperBounds()` and `getAnnotatedLowerBounds()` return `AnnotatedType`, which both hold the type and allow reading annotations at the bound's type-use position.
- `AnnotatedType.getType()` on the bound gives the associated type; `AnnotatedType.getAnnotation(...)` gives the annotation attached **to that specific bound**.

If you need **both** the annotation on the wildcard **and** the annotation on the bound, you must not pick one kind of metadata and ignore the other.

## 4. Reaching a wildcard properly from Field, Method, Parameter

Suppose there is a field:

```java
List<@Mark("wildcard") ? extends @Mark("bound") Number> numbers;
```

Path from the field to the type annotations:

```text
Field numbers
  └── getAnnotatedType(): AnnotatedParameterizedType [List<...>]
       └── getAnnotatedActualTypeArguments()[0]
            └── AnnotatedWildcardType [? extends Number]
                 ├── getAnnotation(Mark.class)       -> "wildcard"
                 ├── getAnnotatedUpperBounds()
                 │     └── AnnotatedType [Number]
                 │           └── getAnnotation(Mark.class) -> "bound"
                 └── getAnnotatedLowerBounds()       -> empty
```

Below are the properly structured Reflection steps:

```java
Field field = Sample.class.getDeclaredField("numbers");

// Not (AnnotatedWildcardType) field.getAnnotatedType():
// field is List<...>, the outermost layer is a parameterized type.
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType argument = listType.getAnnotatedActualTypeArguments()[0];
AnnotatedWildcardType wildcard = (AnnotatedWildcardType) argument;

Mark wildcardMark = wildcard.getAnnotation(Mark.class);
AnnotatedType bound = wildcard.getAnnotatedUpperBounds()[0];
Mark boundMark = bound.getAnnotation(Mark.class);
```

The snippet above is illustrative only and requires declaring `Sample.numbers`, defining `Mark`, `import java.lang.reflect.*`, and handling checked exceptions. The complete runnable code is in section 5.

**Why must we go through `AnnotatedParameterizedType` first?** Because the outermost type is `List<...>`. It is a type argument of `List` that is the wildcard `?`. Casting `field.getAnnotatedType()` directly to `AnnotatedWildcardType` will cause a `ClassCastException`.

Other starting points, depending on where the wildcard appears:

- **Field:** `Field.getAnnotatedType()`.
- **Method/constructor parameter:** `Parameter.getAnnotatedType()` or `Executable.getAnnotatedParameterTypes()`.
- **Method return type:** `Method.getAnnotatedReturnType()`.
- **Annotated generic superclass/interface:** `Class.getAnnotatedSuperclass()` and `Class.getAnnotatedInterfaces()`.
- **Exceptions in a throws clause:** `Executable.getAnnotatedExceptionTypes()` when needed.

On each branch, continue based on the **actual** interface type of `AnnotatedType`: `AnnotatedParameterizedType`, `AnnotatedWildcardType`, `AnnotatedArrayType`, or `AnnotatedTypeVariable`. Do not assume every declaration shares the same structure.

## 5. Complete Java 17+ example: wildcards, extends, super, and nested generics

Save the file **`AnnotatedWildcardDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

public class AnnotatedWildcardDemo {
    List<@Mark("question") ? extends @Mark("upper") Number> producers;

    List<@Mark("question") ? super @Mark("lower") Integer> consumers;

    List<@Mark("any") ?> unknown;

    List<? extends @Mark("onlyUpper") Number> onlyBound;

    Map<String, List<@Mark("nestedW") ?
            extends @Mark("nestedUpper") Number>> nested;

    static String mark(AnnotatedType type) {
        Mark annotation = type.getAnnotation(Mark.class);
        return annotation == null ? "-" : annotation.value();
    }

    static void show(String fieldName) throws NoSuchFieldException {
        Field field = AnnotatedWildcardDemo.class
                .getDeclaredField(fieldName);

        AnnotatedParameterizedType list =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedWildcardType wildcard = (AnnotatedWildcardType)
                list.getAnnotatedActualTypeArguments()[0];

        System.out.println(fieldName + " wildcard=" + mark(wildcard));

        for (AnnotatedType upper : wildcard.getAnnotatedUpperBounds()) {
            System.out.println("  upper=" + upper.getType().getTypeName()
                    + " mark=" + mark(upper));
        }

        for (AnnotatedType lower : wildcard.getAnnotatedLowerBounds()) {
            System.out.println("  lower=" + lower.getType().getTypeName()
                    + " mark=" + mark(lower));
        }

        System.out.println("  lower count="
                + wildcard.getAnnotatedLowerBounds().length);
    }

    public static void main(String[] args) throws Exception {
        show("producers");
        show("consumers");
        show("unknown");
        show("onlyBound");

        Field field = AnnotatedWildcardDemo.class
                .getDeclaredField("nested");

        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType)
                mapType.getAnnotatedActualTypeArguments()[1];

        AnnotatedWildcardType nestedWildcard =
                (AnnotatedWildcardType)
                listType.getAnnotatedActualTypeArguments()[0];

        System.out.println("nested wildcard=" + mark(nestedWildcard));
        AnnotatedType nestedUpper =
                nestedWildcard.getAnnotatedUpperBounds()[0];

        System.out.println("nested upper="
                + nestedUpper.getType().getTypeName()
                + " mark=" + mark(nestedUpper));
    }
}
```

Compile and run:

```bash
javac AnnotatedWildcardDemo.java
java AnnotatedWildcardDemo
```

**Expected stdout:**

```text
producers wildcard=question
  upper=java.lang.Number mark=upper
  lower count=0
consumers wildcard=question
  upper=java.lang.Object mark=-
  lower=java.lang.Integer mark=lower
  lower count=1
unknown wildcard=any
  upper=java.lang.Object mark=-
  lower count=0
onlyBound wildcard=-
  upper=java.lang.Number mark=onlyUpper
  lower count=0
nested wildcard=nestedW
nested upper=java.lang.Number mark=nestedUpper
```

### Explaining the results

1. For `producers`, the `question` annotation sits on the wildcard; `upper` sits on `Number`. `getAnnotatedUpperBounds()` contains `Number`, with no explicit lower bound.
2. For `consumers`, the lower bound `Integer` carries `lower`. The default upper bound is unannotated `Object`, even though the declaration uses `super`.
3. For `unknown`, the wildcard still has the default upper bound `Object`; `getAnnotatedLowerBounds()` returns an empty array.
4. For `onlyBound`, the wildcard has no annotation of its own, so the helper `mark(wildcard)` prints `-`. Yet the bound `Number` carries `onlyUpper`, demonstrating that annotation positions must be read independently.
5. For `nested`, the outermost type is `Map`. The second argument is `List<...>`, and the first argument of `List` is the wildcard. It takes **two steps** through `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` to reach the wildcard and the bound to inspect.

The fields are declared solely for type inspection; they do not need to be initialized to actual `List` or `Map` instances. Reflection here reads metadata of the *declaration*, not elements of a runtime collection.

### What if you only have `WildcardType`?

A snippet like:

```java
Field f = AnnotatedWildcardDemo.class
        .getDeclaredField("producers");

java.lang.reflect.ParameterizedType p =
        (java.lang.reflect.ParameterizedType) f.getGenericType();

java.lang.reflect.WildcardType w =
        (java.lang.reflect.WildcardType)
        p.getActualTypeArguments()[0];

System.out.println(w.getUpperBounds()[0].getTypeName());
```

will give `java.lang.Number`, but **does not preserve the `@Mark("upper")` annotation on this `Type`**. To read the annotation on the upper bound, follow `Field.getAnnotatedType()` as in the runnable example above.

This snippet illustrates plain generic Reflection only, assuming the class name and field are defined as in the earlier example; it must run inside a method handling `NoSuchFieldException`.

## 6. Implicit upper/lower bound rules

### Unbounded `?`

```java
List<?> values;
```

For this wildcard:

- `getAnnotatedUpperBounds()` returns an **unannotated** `Object` upper bound, since Java wrote no explicit upper bound.
- `getAnnotatedLowerBounds()` returns an array of length `0`.

Do not interpret an empty lower array as "no type relationship exists"; it only states **no lower bound was explicitly declared**. Likewise, the appearance of `Object` **does not prove the source code literally wrote `extends Object`**.

### `? extends Number`

```java
List<? extends @Mark("limit") Number> values;
```

- The upper bound is `Number`, with annotation `limit`.
- Lower bounds are empty.
- The wildcard itself may have no annotations.

### `? super Integer`

```java
List<? super @Mark("floor") Integer> values;
```

- The lower bound is `Integer`, with annotation `floor`.
- The upper bound reflects the default `Object` (unannotated).
- `getAnnotatedUpperBounds().length` should not be assumed to be `0` just because the declaration uses `super`.

### Avoid assuming every array has only one element

According to Java documentation, wildcard source currently has at most one explicit upper bound or one explicit lower bound, yet the API still uses `AnnotatedType[]` and notes that callers should be prepared for multiple bounds in the future. Iterating with a `for` loop is cleaner and more resilient than always indexing `[0]`. Only use `[0]` right after checking the length or when deliberately illustrating specific Java syntax.

## 7. An annotation on a wildcard is not an annotation on the field

Consider a case with two `@Target` values:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ColumnInfo {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeInfo {
    String value();
}

class Record {
    @ColumnInfo("scores")
    List<@TypeInfo("wild") ? extends
            @TypeInfo("bound") Number> scores;
}
```

This is an **illustrative snippet**; compiling standalone requires imports from `java.lang.annotation` and `java.util.List`.

The different read locations:

| Annotation location | Primary API |
| --- | --- |
| `@ColumnInfo` on declaration of field `scores` | `Field.getAnnotation(ColumnInfo.class)` |
| `@TypeInfo("wild")` on `?` | `AnnotatedWildcardType.getAnnotation(TypeInfo.class)` |
| `@TypeInfo("bound")` on `Number` | `getAnnotatedUpperBounds()[0].getAnnotation(TypeInfo.class)` |

Do not use `field.getAnnotations()` expecting it to return type-use annotations on wildcards or bounds. Those annotations belong to **child positions in the annotated type tree**, not the same node as the field declaration.

Similarly, `AnnotatedParameterizedType.getAnnotations()` on the `List<...>` node does not automatically "gather" annotations sitting deeper on `?` or bounds. To retrieve all of them, you must traverse the type tree.

## 8. When the bound is a parameterized type, array, or type variable

The bound's `AnnotatedType` does not necessarily represent just a simple `Class<?>`.

### Bound containing nested generics

```java
List<? extends @Mark("boundList")
        List<@Mark("element") String>> nestedBound;
```

This is an illustrative field declaration with type-use semantics. In Reflection, the wildcard's upper bound is an `AnnotatedParameterizedType` representing `List<String>`:

1. `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]` gets the bound node.
2. `bound.getAnnotation(Mark.class)` can yield `boundList`.
3. Cast the bound to `AnnotatedParameterizedType` and call `getAnnotatedActualTypeArguments()[0]` to get the `String` node.
4. `getAnnotation(Mark.class)` on the `String` node yields `element`.

Querying only `bound.getAnnotations()` while skipping actual type arguments will miss deeper annotations.

### Bound is an array type

```java
List<? extends @Mark("element") Number[]> arrayBound;
```

Reading array types requires inspecting the exact annotation positions on the component and dimension; `AnnotatedArrayType.getAnnotatedGenericComponentType()` steps into the inner element type or dimension according to Reflection's structure. For example, an annotation on `Number` and an annotation on the array brackets `Number @Mark("dimension") []` are **two different type-use positions**. Do not infer the position merely from `Type.toString()`.

### Bound is a type variable

```java
class Catalog<T extends Number> {
    List<? extends T> values;
}
```

The upper bound of this wildcard is the type variable `T`. If you need to inspect *the declared bounds of `T`* (such as `T extends Number`), continue inspecting `AnnotatedTypeVariable.getAnnotatedBounds()` when relevant metadata is present.

Distinction:

- **Wildcard bound:** `? extends T` — use `AnnotatedWildcardType.getAnnotatedUpperBounds()`.
- **Type variable's declared bound:** `T extends Number` — use `TypeVariable.getAnnotatedBounds()` or `AnnotatedTypeVariable.getAnnotatedBounds()` from the annotated type variable view.

The two bound levels are not the same node. For recursive bounds (e.g., `T extends Comparable<T>`), when writing a general recursive traversal algorithm you must avoid infinite loops by tracking visited nodes/types.

## 9. Example reading wildcards on method parameters and return types

The APIs are not limited to fields. Example:

```java
class Service {
    java.util.List<@Mark("returnWild") ?
            extends @Mark("returnBound") Number> find() {
        return java.util.List.of();
    }

    void accept(java.util.List<@Mark("paramWild") ?
            super @Mark("paramBound") Integer> values) {
    }
}
```

This is an additional illustrative snippet using the `Mark` annotation from section 5.

For method `find`:

```java
Method method = Service.class.getDeclaredMethod("find");
AnnotatedParameterizedType returned =
        (AnnotatedParameterizedType) method.getAnnotatedReturnType();
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        returned.getAnnotatedActualTypeArguments()[0];
AnnotatedType bound = wildcard.getAnnotatedUpperBounds()[0];
```

For method `accept`:

```java
Method method = Service.class
        .getDeclaredMethod("accept", java.util.List.class);
AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType)
        method.getParameters()[0].getAnnotatedType();
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        parameterized.getAnnotatedActualTypeArguments()[0];
AnnotatedType bound = wildcard.getAnnotatedLowerBounds()[0];
```

Requires `import java.lang.reflect.*;` and handling `NoSuchMethodException`. The complete runnable example in section 5 demonstrates the same steps on fields.

This illustrates that `getAnnotatedReturnType()` and `Parameter.getAnnotatedType()` are **entry points into the annotated type structure**, while `getAnnotatedUpperBounds()/getAnnotatedLowerBounds()` appear only after locating the wildcard node.

## 10. Metadata limits: not every annotation is readable via Reflection

For a type-use annotation to be readable at runtime, a typical declaration needs:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}
```

If `@Retention` is omitted, the default is `RetentionPolicy.CLASS`: the annotation may be stored by the compiler in the class file, yet **is not returned by core Reflection APIs as a runtime annotation**. With `RetentionPolicy.SOURCE`, the annotation is normally discarded before the class file is produced. If a library modifies or obfuscates bytecode, the metadata may also be altered.

Never interpret `getAnnotation(Mark.class) == null` as proof that the source never had an annotation: it could be due to retention, stripped metadata, querying the wrong position, an incompatible `@Target`, or the annotation class being unavailable.

### Type erasure and reading generic annotations

`List<? extends Number>` and `List<? super Integer>` at runtime are both objects of the raw type `List` in the JVM. Reflection reads generic structure from declaration metadata such as `Signature` and related type annotation attributes. These annotations describe **the declared type**, not runtime annotations of individual actual elements inside a list.

For instance, `List<@Mark ? extends Number>` does not mean every `Number` inside the list is an object annotated with `@Mark`; the annotation here is metadata on **the generic argument's type use**.

A plain `java.lang.reflect.Type` can report the generic bound accurately, but cannot preserve annotation positions; use `AnnotatedType` when the question concerns annotations on types and bounds.

### When class file metadata is insufficient

Possible situations:

- The generic `Signature` was stripped or corrupted, making type-argument analysis unreliable.
- The type-use annotation has `CLASS` or `SOURCE` retention, so runtime APIs do not see it.
- Obfuscation or bytecode transformation altered the metadata.
- A referenced type in the generic signature no longer exists, potentially throwing `TypeNotPresentException` or a corresponding reflection exception.
- A parser attempts to cast to the wrong node kind, e.g., casting an `AnnotatedArrayType` to `AnnotatedWildcardType`.

When metadata does not exist, treat the data as **unknown** instead of inferring whether an annotation was or was not written in source. If pre-runtime information is needed, use a compiler/source AST tool or class-file reader suited to the purpose.

## 11. Inspecting the class file with `javap`

After compiling `AnnotatedWildcardDemo.java` from section 5:

```bash
javap -v -p AnnotatedWildcardDemo
```

Look for the relevant sections:

- `Signature` stores generic representations, such as wildcard upper/lower type arguments.
- `RuntimeVisibleTypeAnnotations` stores type-use annotations with runtime retention along with **type path/target** information indicating the annotation position: wildcard, bound, deeper generic node.
- Some annotations without runtime retention may be stored in `RuntimeInvisibleTypeAnnotations` depending on retention; core Reflection does not expose them in the same way as runtime-visible annotations.

`javap` is useful for cross-checking positions against class-file data, though it does not replace the `AnnotatedWildcardType` API when writing runtime Reflection logic.

If `getAnnotation(...)` does not find an annotation, identify **precisely which node you are querying** before concluding the annotation is missing: field declaration, `List`, wildcard `?`, upper bound, or lower bound.

## 12. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Casting `field.getAnnotatedType()` directly to `AnnotatedWildcardType` | The field is `List<...>`, not a wildcard | Go through `AnnotatedParameterizedType` and get the type argument |
| Using `Field.getGenericType()` to read bound annotations | Plain `Type` does not carry per-node type-use annotations | Use `getAnnotatedType()` |
| Calling `wildcard.getAnnotation(Mark.class)` to find an annotation on `Number` | The annotation is on the bound, not on `?` | Query `getAnnotatedUpperBounds()[0].getAnnotation(...)` |
| For `? super Integer`, assuming upper bounds are empty | The implicit upper bound is `Object` | Check upper and lower independently |
| For `?`, assuming there are no bounds | The implicit upper bound is still `Object` | Read `getAnnotatedUpperBounds()` |
| Assuming every wildcard is argument index 0 | Maps/nested generics can have multiple type arguments | Traverse the annotated type tree properly |
| Traversing bounds only one level deep | A bound can be `List<@Mark String>` or an array/type variable | Traverse `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedTypeVariable` as needed |
| Expecting `Field.getAnnotations()` to contain annotations on `?` | Declaration annotations differ from type-use annotations | Use the annotated type APIs |
| Omitting `@Retention(RUNTIME)` yet expecting Reflection to see the marker | Default retention is `CLASS` | Use `RUNTIME` when runtime reading is needed |
| Treating generic annotations as annotations of runtime objects | The metadata belongs to the declared type use | Separate declaration metadata from runtime values |
| Relying on `getAnnotatedUpperBounds()[0]` in all situations | The API returns an array; actual shapes may vary | Check the length and iterate with a `for` loop |
| Treating every `AnnotatedType` as `AnnotatedWildcardType` | Reflection's classification has multiple branches | Use `instanceof` / class checks before casting |

## 13. Self-check exercises

**Question 1.** In `List<@Mark("A") ? extends @Mark("B") Number>`, where are `A` and `B` read from?

**Answer:** `A` is at `AnnotatedWildcardType.getAnnotation(Mark.class)`; `B` is at `getAnnotatedUpperBounds()[0].getAnnotation(Mark.class)`.

**Question 2.** What upper bound does `List<? super @Mark("LOW") Integer>` have at runtime?

**Answer:** It has an unannotated upper bound `Object`, and lower bound `Integer` carrying `LOW`.

**Question 3.** Why is `Field.getAnnotation(Mark.class)` not the right API to read `@Mark` placed directly on `?`?

**Answer:** Because that is a **type-use** annotation on the wildcard node in the generic signature; it does not directly annotate the `Field` declaration.

**Question 4.** What does `getAnnotatedLowerBounds().length == 0` indicate?

**Answer:** There is no **explicit** lower bound in the reflection of that wildcard. Do not infer that the wildcard has no upper bound.

**Question 5.** If a field is `Map<String, List<? extends Number>>`, can you immediately cast `field.getAnnotatedType()` to `AnnotatedWildcardType`?

**Answer:** No. First is `AnnotatedParameterizedType` for `Map`; the second type argument is `List`, also an `AnnotatedParameterizedType`; the wildcard sits at `List`'s type argument.

**Question 6.** With `@Retention(CLASS)`, does core Reflection guarantee returning annotations on bounds?

**Answer:** No. The class file may retain metadata, but the annotation lacks runtime retention for Reflection to expose it as a runtime annotation.

**Question 7.** Should you choose `getAnnotatedUpperBounds()` or `getAnnotatedLowerBounds()` for `? extends @Mark Number` and `? super @Mark Integer`?

**Answer:** `extends` → upper; `super` → lower.

## 14. Key takeaways

**`AnnotatedWildcardType` describes a wildcard `?` that may be annotated, and each bound is an `AnnotatedType` that can be annotated independently.** To read complete metadata, follow the path from field/method/parameter to `AnnotatedParameterizedType`, retrieve the `AnnotatedWildcardType` node, query annotations on the wildcard, and then traverse upper/lower bounds. An unbounded wildcard still has an `Object` upper bound; `? super T` likewise has upper bound `Object` and lower bound `T`.

When encountering nested generics, traverse the `AnnotatedType` tree rather than trying to strip annotations out of plain `Type` or casting blindly. Metadata is reliable at runtime only if retention and the class file actually preserve the required information.

**Standard references:**

- [Java SE 17 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java Language Specification `4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html)