# `getBounds()` and Multiple Type Bounds in Java Reflection

## 1. Goal and Core Problem

In Java Generics, a type parameter does not necessarily accept every reference type. A programmer can declare **upper bounds** to require the actual type to be a subtype of a class and/or implement specific interfaces:

```java
class Metric<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
```

This declaration requires `T` simultaneously to:

- Be a subtype of `Number`.
- Implement `Comparable<T>` (comparable with the corresponding type `T`).
- Implement `Serializable`.

The `&` sign means the **intersection** of type constraints; it is not a runtime AND operation on values, nor is it multiple distinct generic arguments.

With Reflection, the key question is: **How do you read each bound in the exact order and exact generic structure?** The central API is `java.lang.reflect.TypeVariable.getBounds()`.

This lesson clearly distinguishes:

1. `TypeVariable.getBounds()` used for type parameters such as `T`, `U`.
2. `WildcardType.getUpperBounds()` and `getLowerBounds()` used for wildcards such as `? extends Number` and `? super Integer`.
3. Rules for **multiple bounds**, class bounds, interface bounds, and **type erasure**.
4. How to read complex bounds such as `Comparable<T>`, annotations on bounds, and self-referential bounds.
5. Reflection's limitation: knowing **the declared type contract**, without necessarily knowing the concrete type used for an object at runtime.

## 2. Starting from `TypeVariable<?>`

A type parameter is reflected through the interface `java.lang.reflect.TypeVariable<D>`, where `D` is the kind of generic declaration that owns the type parameter (class, method, or constructor).

Example:

```java
class Holder<T extends Number> {
    T item;
}
```

To get the metadata of `T`:

```java
TypeVariable<?> variable = Holder.class.getTypeParameters()[0];
System.out.println(variable.getName()); // T
```

Essential APIs:

| API | Return type | Meaning |
|---|---|---|
| `getName()` | `String` | Declared name of the type variable (`T`, `U`, ...) |
| `getBounds()` | `Type[]` | The declared **upper bounds** |
| `getAnnotatedBounds()` | `AnnotatedType[]` | Those upper bounds along with type-use annotations |
| `getGenericDeclaration()` | `GenericDeclaration` | The class, method, or constructor that **declares** the type variable |
| `getTypeName()` | `String` | Representative name of the type variable; usually `T` |

This is a standalone snippet; you need `import java.lang.reflect.TypeVariable` and to bring `Holder` into the same context; a complete runnable program is in section 10.

To retrieve type parameters from different declaration sites:

```java
TypeVariable<?>[] fromClass = Holder.class.getTypeParameters();
TypeVariable<?>[] fromMethod = someMethod.getTypeParameters();
TypeVariable<?>[] fromConstructor = someConstructor.getTypeParameters();
```

`someMethod` must be a `java.lang.reflect.Method` and `someConstructor` a `Constructor<?>` that has been validly looked up. `Class`, `Method`, and `Constructor` all provide `getTypeParameters()` because they are `GenericDeclaration`s. The array is empty if that declaration itself declares no type parameters.

**Important:** A class's type parameter, e.g., `Holder<T>`, and a method's type parameter, e.g., `<T> void work(T arg)`, are **two different declarations** even when both are named `T`. Use `getGenericDeclaration()` to distinguish them when analyzing metadata.

## 3. What Does `TypeVariable.getBounds()` Actually Return?

Signature:

```java
Type[] getBounds()
```

The return value is an array of `java.lang.reflect.Type` objects corresponding to **the upper bounds of the type variable**. With multiple bounds, they appear in declaration order, so do not reorder them if analyzing erasure semantics.

Three important cases:

| Declaration | Contents of `getBounds()` | Interpretation |
|---|---|---|
| `class A<T> {}` | `[Object.class]` | With no bound written, the implicit upper bound is `Object` |
| `class B<T extends Number> {}` | `[Number.class]` | Single bound is a class |
| `class C<T extends Number & Comparable<T> & Serializable> {}` | `[Number.class, Comparable<T>, Serializable.class]` | Three bounds in order; the second bound is a `ParameterizedType` |

Do not assume the array elements are all `Class<?>`. Because `getBounds()` returns `Type[]`, an element can represent:

- `Class<?>`: an ordinary bound such as `Number` or `Serializable`.
- `ParameterizedType`: a bound with type arguments such as `Comparable<T>` or `Function<String, Integer>`.
- `TypeVariable<?>`: a bound pointing to another type parameter, such as `<A extends Number, B extends A>`.

When no bound is declared, **`getBounds()` still returns a single-element array `[Object.class]`**, not an empty array. Therefore, code that lists bounds should treat `Object` as the default upper bound, rather than inferring from `array.length == 0` that there are "no constraints."

Example:

```java
TypeVariable<?> t = C.class.getTypeParameters()[0];
for (Type bound : t.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

In the context of `C<T extends Number & Comparable<T> & Serializable>` declared above, the output is:

```text
java.lang.Number
java.lang.Comparable<T>
java.io.Serializable
```

These snippets are illustrations depending on class `C` and imports `java.lang.reflect.Type`, `TypeVariable`. `getTypeName()` is suitable for display; when you need to analyze the semantics of a bound, use the `Type` interfaces instead of splitting strings at `<` or `>`.

## 4. Multiple-Bounds Syntax: Class First, Interfaces After

Java allows writing multiple upper bounds for a type parameter:

```java
class Processor<T extends Number & Comparable<T> & java.io.Serializable> {
}
```

Important source rules:

1. If there is a **class bound**, that class must **come first**, followed (if present) by interfaces.
2. At most **one class** in the bounds list (Java does not support multiple class inheritance).
3. There can be **multiple interface bounds**, joined with `&`.
4. If there are **only interface bounds**, the first interface stands first in the list and determines erasure.
5. When there is no `extends`, the implicit upper bound is `Object`.
6. Java does not support `<T super Number>` for type parameter declarations. `super` is the lower-bound syntax for **wildcards**, not a bound syntax for `T`.
7. Bounds must obey Java type rules, such as not repeating an interface in ways that create different parameterizations with the same erasure.

Some examples:

```java
// Valid: class first, interfaces after
class A<T extends Number & Comparable<T> & java.io.Serializable> {}

// Valid: interfaces only
class B<T extends Runnable & AutoCloseable> {}

// Valid: single bound
class C<T extends Number> {}

// Valid: no bound declared (implicitly Object)
class D<T> {}
```

The following declarations are **invalid** (for recognizing errors only, do not put into a program to compile):

```java
// Invalid: placing class after interface
// class WrongA<T extends Comparable<T> & Number> {}

// Invalid: cannot have two class bounds
// class WrongB<T extends Number & java.util.ArrayList<String>> {}

// Invalid: type variable declaration does not allow "super"
// class WrongC<T super Integer> {}
```

Supporting multiple interface bounds is useful when an algorithm requires **multiple capabilities simultaneously**. For example, a type satisfying `Runnable & AutoCloseable` can both be executed via `run()` and closed via `close()`, without forcing it to inherit from a library-specific base class.

## 5. The First Bound and Type Erasure: Why Does Order Matter?

**Erasure** is one reason the order of bounds must be preserved. Under Java rules, a type parameter is replaced by the erasure of its **first bound**; if no bound is declared, `Object`.

Example:

```java
class Numeric<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
```

For `Numeric.value`:

- `field.getType()` returns `Number.class`, because `T` is erased to `Number`.
- `field.getGenericType()` returns a `TypeVariable<?>` representing `T`.
- `((TypeVariable<?>) field.getGenericType()).getBounds()` still contains all of `Number`, `Comparable<T>`, and `Serializable`.

Thus **erasure does not mean Reflection erases all generic signatures**. Erasure affects runtime types and related code, while generic signature metadata can retain the declaration structure for Reflection to analyze.

When there are only interface bounds:

```java
class ComparableHolder<U extends Comparable<U> & java.io.Serializable> {
    U value;
}
```

`field.getType()` of `value` is `Comparable.class`, not `Serializable.class` and not `Object.class`. The first interface serves as the erasure when there is no class bound.

When there is no bound:

```java
class AnyHolder<V> {
    V value;
}
```

`getType()` of `value` is `Object.class`; `getGenericType()` is `V`; `getBounds()` of `V` is `[Object.class]`.

Comparison table:

| Type parameter declaration | Erasure of parameter | `getBounds()` |
|---|---|---|
| `<T>` | `Object` | `[Object]` |
| `<T extends Number>` | `Number` | `[Number]` |
| `<T extends Number & Serializable>` | `Number` | `[Number, Serializable]` |
| `<T extends Comparable<T> & Serializable>` | `Comparable` | `[Comparable<T>, Serializable]` |
| `<T extends Runnable & AutoCloseable>` | `Runnable` | `[Runnable, AutoCloseable]` |

**Do not reorder bounds to make them "look nicer"** when analyzing signatures: order can affect erasure and bytecode method/field descriptors. If you only want to display them alphabetically in a UI, recognize that you are creating a secondary presentation, not the semantically meaningful source order.

## 6. Analyzing Each Bound According to Its `Type` Structure

For a type variable, do not write code like this:

```java
Class<?> bound = (Class<?>) variable.getBounds()[0];
```

A direct cast is valid only if the first bound is actually represented by `Class<?>`. For `T extends Comparable<T>`, the first bound is a `ParameterizedType` and that cast will throw `ClassCastException`.

Safe approach:

```java
for (Type bound : variable.getBounds()) {
    if (bound instanceof Class<?> clazz) {
        System.out.println("Class/interface: " + clazz.getName());
    } else if (bound instanceof ParameterizedType p) {
        System.out.println("Parameterized: " + p.getTypeName());
        System.out.println("Raw: " + p.getRawType().getTypeName());
    } else if (bound instanceof TypeVariable<?> other) {
        System.out.println("Another type parameter: " + other.getName());
    } else {
        System.out.println("Other Type kind: " + bound.getTypeName());
    }
}
```

The snippet above assumes a valid `variable` and imports from `java.lang.reflect`. `Type` objects can be nested: for `Comparable<T>`, `getRawType()` gives `Comparable` and `getActualTypeArguments()[0]` gives the type variable `T`. You must step into `ParameterizedType` to preserve the type arguments.

Example:

```java
class Ranked<T extends Comparable<T>> {
}
```

```java
TypeVariable<?> t = Ranked.class.getTypeParameters()[0];
ParameterizedType p = (ParameterizedType) t.getBounds()[0];

System.out.println(p.getRawType().getTypeName());           // java.lang.Comparable
System.out.println(p.getActualTypeArguments()[0].getTypeName()); // T
```

To support more complex types, a metadata analyzer may also need to handle `GenericArrayType` and `WildcardType` when traversing deeply into type arguments. However, **not every `Type` has `getBounds()`**: it is a specialized method of `TypeVariable` (alongside the corresponding accessors on `WildcardType`).

### A Bound That Is Another Type Variable

Java allows a type parameter to depend on a previously declared type parameter:

```java
class Pair<A extends Number, B extends A> {
    B value;
}
```

`Pair.class.getTypeParameters()[1].getBounds()[0]` reflects the type variable `A` (a `TypeVariable<?>`), rather than automatically substituting `Number.class`. To deduce deeper effective bounds, a tool must follow on to `A`'s bounds and avoid cycles for self-referential types.

## 7. Self-Referential Bounds and Cycle Handling

A valid generic type can reference its own type parameter:

```java
class Node<T extends Comparable<T>> {
}
```

A more familiar example from the Java API:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Abbreviated declaration to illustrate the signature,
    // not the full source code of java.lang.Enum.
}
```

This is **F-bounded polymorphism**: `E`'s bound is `Enum<E>`, in which the type argument of `Enum` is `E` itself. Reflection data represents this relationship validly; do not implement a recursive displayer in a way that loops `E` → `Enum<E>` → `E` → ... infinitely.

One-level reading example:

```java
TypeVariable<?> e = Enum.class.getTypeParameters()[0];
Type[] bounds = e.getBounds();
System.out.println(bounds[0].getTypeName()); // java.lang.Enum<E>
```

If building a schema graph, track the set of visited type variables/declarations to break cycles. When comparing type variables, use proper `equals`/`getGenericDeclaration()` semantics; do not assume reference identity (`==`) is always the sole way to identify reified Reflection metadata.

A type variable having complex bounds **does not mean** the program knows the concrete type argument at runtime. For instance, `class Holder<T extends Number>` receiving `Holder<Integer>` still generally has a single `Class` for `Holder` after erasure; Reflection cannot read `Integer` from an arbitrary instance using only `T.getBounds()`.

## 8. `TypeVariable.getBounds()` vs. Wildcard Upper/Lower Bounds

This is the most common confusion when building a generic inspector.

### 8.1. Type Parameter: `T extends ...`

`TypeVariable.getBounds()` returns the list of **upper bounds**. Type parameters have no `getLowerBounds()` API because the declaration syntax `<T super X>` is not supported by Java.

Example:

```java
class Service<T extends Number & Comparable<T>> {
}
```

The result is two bounds: `Number`, `Comparable<T>`.

### 8.2. Wildcard: `? extends ...` or `? super ...`

Wildcards appear inside type arguments, for example:

```java
java.util.List<? extends Number> producers;
java.util.List<? super Integer> consumers;
java.util.List<?> unknown;
```

Each wildcard is reflected via `java.lang.reflect.WildcardType` with two separate APIs:

| Wildcard | `getUpperBounds()` | `getLowerBounds()` |
|---|---|---|
| `? extends Number` | `[Number]` | `[]` |
| `? super Integer` | `[Object]` | `[Integer]` |
| `?` | `[Object]` | `[]` |

If a wildcard has no explicit upper bound, the API returns upper bound `Object`. If it has no explicit lower bound, `getLowerBounds()` returns an **empty array**, not `[Object]`. For `? super Integer`, the default upper bound is still `Object`; the lower bound is `Integer`.

To find the wildcard of a field declared as `List<? extends Number>`:

```java
Field f = Example.class.getDeclaredField("producers");
ParameterizedType list = (ParameterizedType) f.getGenericType();
WildcardType wildcard =
        (WildcardType) list.getActualTypeArguments()[0];

for (Type upper : wildcard.getUpperBounds()) {
    System.out.println(upper.getTypeName());
}
```

This snippet depends on class `Example` having field `producers` and importing the corresponding reflection types. Note that `field.getGenericType()` is the **`ParameterizedType` of `List`**, not yet `WildcardType`. You must go to the actual type argument to retrieve the wildcard.

### 8.3. Are "Multiple Bounds" on Wildcards the Same as on `TypeVariable`?

**Not in current Java source syntax.**

- A type parameter allows `<T extends Number & Comparable<T>>`.
- Wildcards use `? extends Number`, `? super Integer`, or `?`. Java source **does not allow writing `List<? extends Number & Serializable>`** with intersection bounds in the type-parameter style.
- The APIs `WildcardType.getUpperBounds()` and `getLowerBounds()` still return **`Type[]` arrays**; the documentation notes that code using the API should be written generally enough to handle multiple elements if future type forms support them. Do not infer from the array return type that current source syntax accepts multiple wildcard bounds.

Generic guidelines such as **PECS** (producer extends, consumer super) are helpful when deciding read/write operations on collections, but that is a topic about collection type safety. In Reflection, the immediate task here is determining **bound metadata structure**, not arbitrarily mutating collection elements.

## 9. Annotations on Each Bound: `getAnnotatedBounds()`

Since Java 8, annotations can be placed on **type uses** (`ElementType.TYPE_USE`) if the annotation is defined appropriately.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Marked {}

class Sample<T extends @Marked Number & @Marked Comparable<T>> {}
```

`TypeVariable.getBounds()` supplies the `Type` objects, telling us `Number` and `Comparable<T>`, but does not provide an interface for querying **annotations on each bound**. To get those annotations, use:

```java
TypeVariable<?> t = Sample.class.getTypeParameters()[0];
AnnotatedType[] annotatedBounds = t.getAnnotatedBounds();

boolean firstMarked =
        annotatedBounds[0].isAnnotationPresent(Marked.class);
boolean secondMarked =
        annotatedBounds[1].isAnnotationPresent(Marked.class);
```

These two snippets illustrate the same context; you need imports for `Retention`, `RetentionPolicy`, `Target`, `ElementType`, and `AnnotatedType`. A complete runnable example with type-use annotations is provided in section 10.

Difference between the two APIs:

- `getBounds()`: the declared type structure, as `Type[]`.
- `getAnnotatedBounds()`: the same upper bounds wrapped in `AnnotatedType[]` for reading type-use annotations.
- `AnnotatedType.getType()` gives the `Type` of the corresponding bound.
- `AnnotatedType.getAnnotations()` / `getAnnotation(...)` read annotations on **the type use**, not every annotation declared on the `Number` class or `Comparable` interface itself.

When no bound is declared, `getAnnotatedBounds()` represents the unannotated `Object` upper bound. Pay attention to retention policy: annotations are available in runtime Reflection only if metadata is retained at runtime as applied.

## 10. Complete Java 17+ Program: Class, Method, Erasure, Wildcard, and Annotations

The following example uses a single file `BoundsDemo.java` and covers:

- Multiple bounds with class + interfaces.
- Multiple bounds with interfaces only.
- Unbounded type parameter, self-referential bound, and method type parameter.
- Bounds with type-use annotations.
- Distinguishing `TypeVariable.getBounds()` from wildcard bounds.
- The difference between erasure and generic metadata when querying a field via a subclass.

### 10.1. Source Code

Save verbatim to `BoundsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;

public class BoundsDemo {
    static class Multi<T extends Number & Comparable<T> & java.io.Serializable> {
        public T item;
    }

    static class IntegerMulti extends Multi<Integer> { }

    static class Interfaces<U extends Comparable<U> & java.io.Serializable> {
        U value;
    }

    static class Unbounded<V> {
        V value;
    }

    static class Recursive<E extends Enum<E>> { }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Marked { }

    static class Annotated<A extends @Marked Number & @Marked Comparable<A>> { }

    static class Wildcards {
        List<? extends Number> upper;
        List<? super Integer> lower;
        List<?> any;
    }

    static <M extends Runnable & AutoCloseable> void process(M value) { }

    private static String names(Type[] types) {
        return Arrays.toString(Arrays.stream(types)
                .map(Type::getTypeName).toArray(String[]::new));
    }

    private static void wildcard(String fieldName) throws NoSuchFieldException {
        Field field = Wildcards.class.getDeclaredField(fieldName);
        ParameterizedType list = (ParameterizedType) field.getGenericType();
        WildcardType wildcard = (WildcardType) list.getActualTypeArguments()[0];
        System.out.println(fieldName + " upper=" + names(wildcard.getUpperBounds())
                + " lower=" + names(wildcard.getLowerBounds()));
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        TypeVariable<?> multi = Multi.class.getTypeParameters()[0];
        System.out.println("Multi bounds: " + names(multi.getBounds()));
        System.out.println("Multi erased: "
                + Multi.class.getDeclaredField("item").getType().getTypeName());
        System.out.println("Multi generic: "
                + Multi.class.getDeclaredField("item").getGenericType().getTypeName());

        System.out.println("Interfaces bounds: "
                + names(Interfaces.class.getTypeParameters()[0].getBounds()));
        System.out.println("Interfaces erased: "
                + Interfaces.class.getDeclaredField("value").getType().getTypeName());
        System.out.println("Unbounded bounds: "
                + names(Unbounded.class.getTypeParameters()[0].getBounds()));
        System.out.println("Recursive bounds: "
                + names(Recursive.class.getTypeParameters()[0].getBounds()));

        Method method = BoundsDemo.class.getDeclaredMethod("process", Runnable.class);
        System.out.println("Method bounds: "
                + names(method.getTypeParameters()[0].getBounds()));

        AnnotatedType[] annotated =
                Annotated.class.getTypeParameters()[0].getAnnotatedBounds();
        System.out.println("Annotated count: " + annotated.length);
        System.out.println("Annotations present: "
                + (annotated[0].isAnnotationPresent(Marked.class)
                && annotated[1].isAnnotationPresent(Marked.class)));

        wildcard("upper");
        wildcard("lower");
        wildcard("any");

        System.out.println("Subclass field generic: "
                + IntegerMulti.class.getField("item").getGenericType().getTypeName());
        System.out.println("Subclass generic parent: "
                + IntegerMulti.class.getGenericSuperclass().getTypeName());
    }
}
```

### 10.2. Compile and Run

Use JDK 17 or newer:

```bash
javac --release 17 BoundsDemo.java
java BoundsDemo
```

Output verified by compiling with `--release 17` and running on OpenJDK 21:

```text
Multi bounds: [java.lang.Number, java.lang.Comparable<T>, java.io.Serializable]
Multi erased: java.lang.Number
Multi generic: T
Interfaces bounds: [java.lang.Comparable<U>, java.io.Serializable]
Interfaces erased: java.lang.Comparable
Unbounded bounds: [java.lang.Object]
Recursive bounds: [java.lang.Enum<E>]
Method bounds: [java.lang.Runnable, java.lang.AutoCloseable]
Annotated count: 2
Annotations present: true
upper upper=[java.lang.Number] lower=[]
lower upper=[java.lang.Object] lower=[java.lang.Integer]
any upper=[java.lang.Object] lower=[]
Subclass field generic: T
Subclass generic parent: BoundsDemo$Multi<java.lang.Integer>
```

### 10.3. Explanation of Output by Group

**`Multi<T>`:** Has three upper bounds. `Number` comes first, so field `item` has erased runtime type `Number`. Even so, the field's `getGenericType()` still returns type variable `T`.

**`Interfaces<U>`:** Has only interface bounds. `Comparable<U>` comes first, so erasure becomes `Comparable`; `Serializable` still appears in the `getBounds()` result.

**`Unbounded<V>`:** Without an `extends` declaration, `getBounds()` returns `Object`.

**`Recursive<E>`:** The bound is `Enum<E>`, containing a back-reference to `E`. This is a `ParameterizedType`, not a plain `Enum.class`.

**Method `process`:** Type parameter `M` belongs to **the method's generic declaration**. `getDeclaredMethod("process", Runnable.class)` uses `Runnable.class` because that is the erasure of the first bound in `M extends Runnable & AutoCloseable`.

**Type-use annotations:** Both bounds of `A` have `@Marked`, so `getAnnotatedBounds()` returns two elements and both contain the annotation at runtime.

**Wildcards:** `? extends Number` has upper bound `Number` and no lower bound; `? super Integer` has default upper bound `Object` and lower bound `Integer`; `?` has `Object` and no lower bound.

**`IntegerMulti`:** Even though the subclass fixes the type argument `Integer`, field `item` is still declared by `Multi<T>`. Retrieving that field through the subclass, `getGenericType()` **is still `T`**. The `Multi<Integer>` relationship resides in `IntegerMulti.class.getGenericSuperclass()` metadata and must be combined if you want to infer the concrete type in the subclass context.

## 11. Applications of Bounds in Frameworks and Analysis Tools

### 11.1. Checking Generic API Contracts

A plugin library may require a type parameter to satisfy multiple capabilities:

```java
interface Task { void run(); }
interface Stoppable { void stop(); }

class TaskPool<T extends Task & Stoppable> { }
```

A metadata scanner reading `TaskPool.class.getTypeParameters()[0].getBounds()` will know the contract requires **both `Task` and `Stoppable`**. If you only inspect raw erasure, you might see `Task` and miss `Stoppable`.

This is useful when generating API docs, checking plugin signatures, or analyzing schemas; metadata itself does not replace compile-time generic type checking.

### 11.2. Mappers / Serializers with Generic Superclasses

A serializer can inspect `T extends Number` to know a field's baseline contract; however, when an object belongs to subclass `IntegerMulti`, to learn `T = Integer` it must also read the `ParameterizedType` of the generic superclass and build a mapping from type variable (`T`) to type argument (`Integer`).

`getBounds()` returns **allowed constraints**, not **the actual chosen type argument**. Those are two independent questions:

- `T extends Number` answers "What minimum type must `T` satisfy?"
- `Multi<Integer>` answers "In this specific inheritance relationship, what type is assigned to `T`?"

Do not assume that when `T extends Number`, every instance holds `Integer`; `Double` or another `Number` subtype can also be valid if it satisfies any additional interface bounds.

### 11.3. Building a Robust Generic Inspector

An inspector typically needs to:

1. Obtain `Class.getTypeParameters()` or `Method.getTypeParameters()`.
2. For each `TypeVariable<?>`, record `getName()` and `getGenericDeclaration()`.
3. Traverse **all** elements of `getBounds()` in exact order.
4. Classify each `Type` using `instanceof`.
5. When encountering a `ParameterizedType`, descend into `getRawType()` and `getActualTypeArguments()`.
6. For type-use annotations, read `getAnnotatedBounds()` in matching order.
7. For recursive bounds, detect cycles; for generic superclasses, build contextual type-variable mappings.

**You do not have to call `setAccessible(true)`** to read generic type parameter metadata. Access suppression relates to accessing restricted members, not a general requirement for `getBounds()`.

## 12. Common Mistakes and How to Avoid Them

| Mistake | Cause | Fix |
|---|---|---|
| Thinking `getBounds()` is empty for `<T>` | Unbounded still has implicit `Object` | Handle `[Object.class]` |
| Reading only `getBounds()[0]` | Misses additional interface bounds | Traverse the entire `Type[]` |
| Casting every bound to `Class<?>` | `Comparable<T>` is a `ParameterizedType` | Classify `Type` with `instanceof` |
| Reordering bounds arbitrarily | Erasure depends on the first bound | Preserve source order |
| Thinking multiple bounds = multiple classes | Java has no multiple class inheritance | At most one class bound, remaining are interfaces |
| Writing `T super Number` | Type parameters have no lower-bound syntax | Use `extends` for type parameters; `? super` for wildcards |
| Writing `List<? extends A & B>` in Java source | Wildcards do not support this intersection syntax | Use type parameter `<T extends A & B>` at an appropriate declaration |
| Calling `getBounds()` directly on `ParameterizedType` | `ParameterizedType` has no such API | Traverse `getActualTypeArguments()`, then recognize `TypeVariable` or `WildcardType` |
| Thinking `? super Integer` has upper bound `Integer` | `Integer` is the **lower bound** | `upper=[Object]`, `lower=[Integer]` |
| Assuming `getBounds()` gives the concrete type of `Box<Integer>` | Bounds are declaration metadata | Inspect `getGenericSuperclass()`/generic interfaces and resolve type variables |
| Infinite recursion on `Enum<E extends Enum<E>>` | Bound references the type variable back | Track visited declarations/type variables |
| Looking for bound annotations in `getBounds()` | `Type[]` has no type-use annotation API | Use `getAnnotatedBounds()` |
| Using `Type.getTypeName()` to parse generics with simple regex | Nested types and wildcards make manual parsing fragile | Analyze the `Type` structure |
| Assuming metadata is always pristine | Generic signatures may be missing/malformed | Handle `TypeNotPresentException`, `MalformedParameterizedTypeException`, `GenericSignatureFormatError` appropriately |

A few additional notes:

- `TypeVariable.getBounds()` may trigger resolution of types mentioned in bounds. With invalid metadata or unloadable types, the Javadoc permits `TypeNotPresentException` or `MalformedParameterizedTypeException` in specific cases.
- Generic signatures come from bytecode/class metadata. Never use Reflection results as a security check to permit arbitrarily loading/running classes; reading schemas and executing code are two separate activities.
- Two type variables sharing the name `T` can belong to different generic declarations. When building a lookup table, identification keys must include the declaration, not just the character name.

## 13. Self-Check Knowledge Questions

1. For `class A<T> {}`, how many elements does `A.class.getTypeParameters()[0].getBounds()` return, and what is that element?
2. For `T extends Number & Comparable<T> & Serializable`, why are there three bounds yet a field of type `T` has only one raw `Class<?>`, `Number`?
3. Why should `getBounds()[1]` for `Comparable<T>` not be cast to `Class<?>`?
4. If only `T extends Runnable & AutoCloseable` is written, which interface determines erasure?
5. How does `<T extends A & B>` differ from `List<? extends A>`? Can `? extends A & B` be used in Java source?
6. In what data do `getBounds()` and `getAnnotatedBounds()` differ?
7. Why can the `Enum<E>` bound of `E extends Enum<E>` lead to a loop during recursive analysis?
8. When field `T` is declared in a generic superclass but queried through subclass `Superclass<Integer>`, why can `Field.getGenericType()` still return `T`?
9. For `List<? super Integer>`, what are the wildcard's lower bound and upper bound respectively?
10. To display all upper bounds of a method's type parameter, starting from the `Method` object, which APIs do you call?

**Takeaway:** `TypeVariable.getBounds()` returns **all upper bounds** of a type parameter, with `Object` implicitly when no bound is declared. With multiple bounds, **the first bound determines erasure**, while generic metadata retains the additional bounds. `WildcardType` has its own upper/lower bounds APIs, and `getAnnotatedBounds()` is used to inspect annotations on each type bound.

Standard references for cross-checking: [TypeVariable (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [WildcardType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html), [ParameterizedType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [AnnotatedType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [JLS §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4), [JLS §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).