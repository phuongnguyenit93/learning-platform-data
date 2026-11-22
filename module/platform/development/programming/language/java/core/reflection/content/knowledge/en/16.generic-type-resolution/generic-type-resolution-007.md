# Limits of Unbound Types and Raw Type Cases in Java Reflection

## 1. Framing the problem accurately: generic metadata does not always supply a concrete type

Java supports generic types such as `Box<String>`, `Box<T>`, or `Box<?>`, yet Reflection cannot automatically recover every type parameter of an object at runtime. When analyzing a generic class, field, method, or inheritance relationship, we must clearly distinguish three outcomes:

1. **Concretely bound:** for example `class StringBox extends Box<String>`. When querying the generic superclass of `StringBox.class`, the declared signature still retains the argument `String`, so Reflection can return a `ParameterizedType` with argument `String.class`.
2. **An unresolved type variable remains:** for example `class OpenBox<U> extends Box<U>`. The generic superclass has the form `Box<U>`; the argument `U` is a `TypeVariable`, **not** the concrete data type held by an `OpenBox` object.
3. **Inheritance through a raw type:** for example `class RawBox extends Box`. The declaration `extends Box` omits the type parameter list, so `getGenericSuperclass()` may return only a `Class` representing `Box`. There is no `getActualTypeArguments()` to retrieve an omitted `T`.

In applications using serializers, mappers, dependency injection, or generic libraries, **you must never silently interpret an unknown case as a guessed concrete type**. Upper bounds such as `Object` or `Number` only place a constraint on the type variable; they are not the actual bound value.

## 2. Kinds of `Type` to recognize

In `java.lang.reflect`, `Type` is the common abstraction. Reading a generic signature can yield:

| Reflection kind | Example in declaration | Meaning |
| --- | --- | --- |
| `Class<?>` | `String` or superclass using raw `Box` | Concrete class type, carrying no generic argument list on the `Class` value itself |
| `ParameterizedType` | `Box<String>`, `Box<U>`, `List<?>` | Declaration applying a generic type with an argument list; **arguments inside may still be unresolved** |
| `TypeVariable<?>` | `T`, `U`, `N extends Number` | Type variable declared by a class, method, or constructor |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` | Wildcard argument, bounding a type relationship rather than a single concrete type |
| `GenericArrayType` | `T[]` in a generic declaration | Array type whose component type cannot be represented by `Class<?>[]` alone |

`Class.getGenericSuperclass()` and `Class.getGenericInterfaces()` return metadata for the direct superclass/superinterface relationships; `Field.getGenericType()` and `Method.getGenericReturnType()` return the generic signature of a field/return type. To inspect the type variables **declared** on a class or executable, use `getTypeParameters()`.

Note: `getTypeParameters()` provides the **list of declared variables**, not the substituted arguments for a runtime object. For example, `Box.class.getTypeParameters()[0]` is `T` even if some instance was created via `new Box<String>(...)`.

## 3. `TypeVariable`: when `T` or `U` is still unbound

Example:

```java
class Box<T> {
    T value;
}

class OpenBox<U> extends Box<U> {}
```

This is an **illustrative declaration snippet**, not a complete Java file.

When analyzing `OpenBox.class.getGenericSuperclass()`, we can obtain a `ParameterizedType` describing `Box<U>`. However, its actual argument is a `TypeVariable` representing `U`; there is no basis to claim `U = String`, `U = Integer`, or `U = Object` from `OpenBox.class` alone.

`TypeVariable` provides:

- `getName()`: variable name, such as `U`. **Name alone is insufficient for identification**; two different classes can both declare `T`.
- `getGenericDeclaration()`: the class, method, or constructor **that declared the variable**. Use this information (along with variable position) when building binding mappings.
- `getBounds()`: array of declared upper bounds; may contain `Class`, `ParameterizedType`, or `TypeVariable`.
- `getAnnotatedBounds()`: use when annotation metadata attached to bound positions is also needed.

### 3.1. No bound declared: `Object` is the default upper bound

For `class Box<T>`, `T.getBounds()` returns an array with upper bound `java.lang.Object`. That means `T` can be substituted by **any valid reference type**; it does not mean every `Box<T>` is actually `Box<Object>`.

Therefore, when a resolver encounters `TypeVariable T` with no `T -> concrete type` mapping, the accurate answer is **UNRESOLVED `T` (upper bound: `Object`)**. Picking `Object.class` as the *erasure* is sometimes useful for bytecode-level operations, but **it must not be called the actual type argument**.

### 3.2. An explicit bound is still not a bound argument

```java
class NumericBox<N extends Number & Comparable<N>> {}
```

Here `N.getBounds()` has two parts, `Number` and `Comparable<N>`, respectively. Knowing the upper bounds helps check constraints and erasure, yet still cannot choose among `Integer`, `Double`, or another conforming type.

According to Java's type erasure rules, the erasure of a type variable follows its **leftmost bound**: `T` with no explicit bound has erasure `Object`, whereas `N extends Number & Comparable<N>` has erasure `Number`. Erasure is the type used by the compiler for the JVM representation after removing generic information, **distinct from** resolving a concrete type argument.

### 3.3. Things that cannot be inferred from an ordinary instance

`new Box<String>("x").getClass()` and `new Box<Integer>(123).getClass()` are the same runtime `Class` `Box` (within the same class loader). Thus, the `Class` object itself does not store `String` or `Integer` for each generic instance. Inspecting the current value also does not reliably determine the generic type: the object may hold `null`, an interface/supertype, or be accessed through multiple generic paths.

If a program needs a type at runtime, it can intentionally pass a `Class<T>`/`Type` token, use a subclass that closes the type in its inheritance signature, or use corresponding declaration metadata. Do not guess from variable names or arbitrary data.

## 4. Raw types: no type argument list

A raw type is the use of a generic type **without type arguments**:

```java
class Box<T> {}
class RawBox extends Box {}          // extends the raw type Box
class StringBox extends Box<String> {}
```

This is an **illustrative declaration snippet**. `Box` is a generic class, yet the expression `extends Box` provides no `<...>`; that is using a raw type for compatibility with legacy Java code.

Distinguish these three expressions:

- `Box<String>`: explicit type argument `String`.
- `Box<?>`: **parameterized type with wildcard**, which still has a type argument list.
- `Box`: **raw type**, which has no type argument list.

Do not equate raw `Box` with `Box<Object>` or `Box<?>`. All three expressions relate to the same generic declaration, yet differ in compile-time type checking, generic metadata, and the potential for unchecked operations.

According to the JLS, the supertypes of a raw type are the **erasures** of the corresponding supertypes. Member calls through a raw type can produce `unchecked` warnings because field/parameter types have lost generic information. The fact that a program compiles does not guarantee the absence of `ClassCastException`.

### 4.1. Reflection of a raw superclass

```java
Type parent = RawBox.class.getGenericSuperclass();

if (parent instanceof Class<?> rawClass) {
    System.out.println(rawClass.getSimpleName());
}
```

In the example above, `parent` is the `Class` corresponding to `Box`, not a `ParameterizedType` with a synthetic `Object` argument.

Common mistake:

```java
ParameterizedType p =
        (ParameterizedType) RawBox.class.getGenericSuperclass();
```

This statement can throw `ClassCastException` because the actual kind of `Type` is `Class`. Always check with `instanceof` before casting. If the result is the `Class` of a generic declaration used raw, the resolution status should report **RAW / UNKNOWN TYPE ARGUMENT**, not that a concrete argument was resolved.

## 5. Complete Java 17+ example and verified output

Create the file **`GenericLimitsDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.Arrays;
import java.util.stream.Collectors;

public class GenericLimitsDemo {
    static class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static class StringBox extends Box<String> {
        StringBox() { super("hello"); }
    }

    static class OpenBox<U> extends Box<U> {
        OpenBox(U value) { super(value); }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static class RawBox extends Box {
        RawBox() { super(42); }
    }

    static class BoundedBox<N extends Number & Comparable<N>>
            extends Box<N> {
        BoundedBox(N value) { super(value); }
    }

    static class IntegerBox extends BoundedBox<Integer> {
        IntegerBox() { super(7); }
    }

    static class Lists {
        java.util.List<?> any;
        java.util.List<String> strings;
    }

    static String kind(Type t) {
        if (t instanceof Class<?>) return "Class";
        if (t instanceof TypeVariable<?>) return "TypeVariable";
        if (t instanceof ParameterizedType) return "ParameterizedType";
        if (t instanceof WildcardType) return "WildcardType";
        if (t instanceof GenericArrayType) return "GenericArrayType";
        return "Other";
    }

    static void inspect(Class<?> type) {
        Type parent = type.getGenericSuperclass();
        System.out.println(type.getSimpleName() + " -> " + parent.getTypeName());

        if (parent instanceof ParameterizedType p) {
            Type arg = p.getActualTypeArguments()[0];
            System.out.println(
                    "  argument=" + arg.getTypeName() + ", kind=" + kind(arg)
            );
        } else if (parent instanceof Class<?>) {
            System.out.println("  raw superclass: no actual type argument");
        }
    }

    public static void main(String[] args) throws Exception {
        inspect(StringBox.class);
        inspect(OpenBox.class);
        inspect(RawBox.class);
        inspect(IntegerBox.class);

        TypeVariable<?> t = Box.class.getTypeParameters()[0];
        TypeVariable<?> u = OpenBox.class.getTypeParameters()[0];
        TypeVariable<?> n = BoundedBox.class.getTypeParameters()[0];

        System.out.println("T bounds=" + Arrays.stream(t.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));
        System.out.println("U bounds=" + Arrays.stream(u.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));
        System.out.println("N bounds=" + Arrays.stream(n.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));

        Field value = Box.class.getDeclaredField("value");
        System.out.println("Box.value generic=" + value.getGenericType().getTypeName()
                + ", erased=" + value.getType().getTypeName());

        Field any = Lists.class.getDeclaredField("any");
        Type wildcard = ((ParameterizedType) any.getGenericType())
                .getActualTypeArguments()[0];
        System.out.println("List<?> argument=" + wildcard.getTypeName()
                + ", kind=" + kind(wildcard));

        System.out.println("Same runtime class="
                + (new Box<>("x").getClass() == new Box<>(123).getClass()));

        @SuppressWarnings({"rawtypes", "unchecked"})
        Box<Integer> unsafe = new Box("not an integer");
        try {
            Integer result = unsafe.get();
            System.out.println(result);
        } catch (ClassCastException e) {
            System.out.println("Raw assignment: ClassCastException on read");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 GenericLimitsDemo.java
java GenericLimitsDemo
```

**Stdout on JDK 21 with `--release 17`:**

```text
StringBox -> GenericLimitsDemo$Box<java.lang.String>
  argument=java.lang.String, kind=Class
OpenBox -> GenericLimitsDemo$Box<U>
  argument=U, kind=TypeVariable
RawBox -> GenericLimitsDemo$Box
  raw superclass: no actual type argument
IntegerBox -> GenericLimitsDemo$BoundedBox<java.lang.Integer>
  argument=java.lang.Integer, kind=Class
T bounds=java.lang.Object
U bounds=java.lang.Object
N bounds=java.lang.Number & java.lang.Comparable<N>
Box.value generic=T, erased=java.lang.Object
List<?> argument=?, kind=WildcardType
Same runtime class=true
Raw assignment: ClassCastException on read
```

**Part-by-part analysis:**

1. `StringBox` has generic superclass `Box<String>`. `getActualTypeArguments()[0]` is a `Class` `String.class`; we can conclude the argument of the **declared inheritance relationship** is `String`.
2. `OpenBox<U>` also returns a `ParameterizedType`, but its argument is `TypeVariable U`. The presence of a `ParameterizedType` **does not guarantee** all arguments are concretely bound.
3. `RawBox` returns `Class` because the parent class is declared in raw form. It has no type argument list to read.
4. `IntegerBox` binds `BoundedBox<Integer>`. If continuing past `BoundedBox<N> extends Box<N>`, concluding `Box<Integer>` requires **propagating the `N -> Integer` mapping** across each level. Reading only `BoundedBox.class.getGenericSuperclass()` shows `N`, not yet `Integer`.
5. `Box.value` has `getGenericType() == T` (in metadata terms), while `getType() == Object.class` because `T` is erased to `Object`. `getType()` does not supply the actual argument of a specific instance.
6. `List<?>` yields `WildcardType`, not raw. `?` is an unknown argument with default upper bound `Object`; you cannot arbitrarily turn it into an actual `Object`.
7. Two `Box`es with different compile-time arguments share the same runtime class. Finally, assignment through a raw type bypasses generic checks, causing `Integer result = unsafe.get()` to throw `ClassCastException` when bytecode casts the `String` value to `Integer`.

`@SuppressWarnings({"rawtypes", "unchecked"})` in the example is placed right where it **intentionally illustrates the risk of raw types**. It does not make unsafe code safe; in real codebases, avoid or isolate legacy interactions as narrowly as possible.

## 6. Why can't `getBounds()` replace type resolution?

A `TypeVariable` can remain unbound even if it has one or more upper bounds:

| Declaration | `getBounds()` | Is the actual argument known? |
| --- | --- | --- |
| `class Box<T>` | `Object` | **Not yet** |
| `class Numeric<N extends Number>` | `Number` | **Not yet** |
| `class ComparableBox<N extends Number & Comparable<N>>` | `Number`, `Comparable<N>` | **Not yet** |
| `class StringBox extends Box<String>` | `T` still exists on `Box` declaration | **Has `String` argument in `StringBox`'s inheritance relationship** |
| `class OpenBox<U> extends Box<U>` | `U` defaults to bound `Object` | **Not yet**, unless mapped from an enclosing/sub layer |

**Upper bounds** are used for type constraints and erasure. **Actual type arguments** are the values supplied when a parameterized type is declared/used. There is no rule saying "if `T` cannot be resolved, take its first bound as `T`".

For example, `N extends Number` states that `N` is a conforming subtype of `Number`. It does **not** allow a resolver to assert `N = Number`; `Integer`, `Double`, and many other types satisfy the bound.

## 7. Multi-level resolution requires variable substitution, not just looping `getGenericSuperclass()`

Consider the declaration snippet:

```java
class Base<T> {}

class Mid<U> extends Base<java.util.List<U>> {}

class Concrete extends Mid<String> {}
```

This is an **illustrative code snippet**, not a standalone Java file.

- `Concrete.class.getGenericSuperclass()` represents `Mid<String>`, giving the mapping `Mid.U -> String`.
- `Mid.class.getGenericSuperclass()` represents `Base<List<U>>`. Its argument is a `ParameterizedType` `List<U>`, in which `U` is still a `TypeVariable`.
- To determine the relationship from `Concrete` to `Base`, the resolver must substitute `U -> String` **inside** `List<U>`, yielding `Base<List<String>>`.

A practical generic resolver algorithm must:

1. Read `TypeVariable` declarations via **`getTypeParameters()` of the exact declaring class**.
2. Read the actual arguments of the `ParameterizedType` on the current inheritance edge.
3. Record mappings from declared variables to their corresponding `Type`s, distinguishing same-named variables from different declarations.
4. Apply mappings recursively to `ParameterizedType`, `GenericArrayType`, `WildcardType`, and `TypeVariable`, avoiding cycles when bounds are self-referential such as `T extends Comparable<T>`.
5. Propagate those mappings while continuing to walk superclasses or interfaces, handling multiple interface branches if applicable.
6. When hitting a raw edge or an unmapped variable, **report unresolved** and keep bounds/erasure metadata separate; do not fill in `Object` or an arbitrary `Class` as a placeholder.

In the `Concrete -> Mid<String> -> Base<List<U>>` example, a resolver inspecting each edge in isolation will miss the `U -> String` substitution. Conversely, a resolver that "guesses `U` as its `Object` bound" will wrongly conclude `List<Object>` even though `String` exists on the lower edge.

## 8. A raw type in the middle of an inheritance chain

Example:

```java
class Store<T> {}
@SuppressWarnings("rawtypes")
class LegacyStore extends Store {}
class SpecializedStore extends LegacyStore {}
```

This is an **illustrative declaration snippet**.

- `LegacyStore.class.getGenericSuperclass()` represents raw `Store` and supplies no `T`.
- `SpecializedStore.class.getGenericSuperclass()` gives `LegacyStore.class` (an ordinary superclass).
- When walking up to `Store<T>`, no concrete argument for `Store.T` can be produced from this chain. The valid outcome is **unknown `T` because a raw edge was crossed**.

Two analysis levels must be distinguished:

- **Erasure:** can determine the base runtime class, such as `Store.class`.
- **Generic argument resolution:** cannot recover a `T` that was never recorded in the raw signature.

If a framework cannot handle raw inputs, require explicit generic declarations, `Type` tokens, or valid configuration metadata; avoid silently treating raw `Store` as `Store<Object>`.

## 9. An unbounded wildcard is not a raw type

Look at two fields:

```java
java.util.List<?> unknownElements;
java.util.List rawElements;
```

This is a **field declaration snippet**; place them inside a class to compile as a program.

For `unknownElements`:

- `getGenericType()` is a `ParameterizedType` describing `List<?>`.
- `getActualTypeArguments()[0]` is a `WildcardType`.
- `getUpperBounds()` of an implicitly bounded wildcard has `Object`; `getLowerBounds()` is empty.
- `List<?>` preserves partial compile-time type safety: you cannot arbitrarily `add("text")` to that list (except `null`).

For `rawElements`:

- `getGenericType()` is usually `Class` `List.class`, with no actual arguments.
- Raw types allow potentially type-unsafe operations, leading to unchecked warnings and delayed failures.

Similarly, `? extends Number` is an **upper-bounded** wildcard rather than a variable `N extends Number`; `? super Integer` carries a **lower bound**. Neither wildcards nor type variables should be coerced into `Class<?> concrete` solely because they have bounds.

## 10. Designing APIs that return trustworthy resolution results

When building a Reflection library, return **an explanatory resolution status** rather than a fabricated `Class<?>`:

| Suggested status | Example | Reasonable behavior |
| --- | --- | --- |
| `RESOLVED` | `Box<String>` on `StringBox` | Return `Type` `String.class` |
| `UNRESOLVED_VARIABLE` | `Box<U>` on `OpenBox<U>` with no `U` mapping | Return `TypeVariable U`, declaration, bounds |
| `RAW` | `extends Box` | Report missing argument right at the raw inheritance edge |
| `WILDCARD` | `List<?>`, `List<? extends Number>` | Preserve `WildcardType` and its bounds |
| `PARTIALLY_RESOLVED` | `List<U>` when `U` is unknown | Preserve `ParameterizedType` structure and the unknown variable position |

The status labels above are **application design suggestions**, not built-in JDK enums.

If a runtime type is needed for serialization/validation, accept `Type` or a *type token* from the caller. For example, an API signature can be `decode(String json, Type targetType)` instead of just `decode(String json, Class<?> targetClass)`, because `Class<List>` cannot represent `List<String>`. Even with a `Type` token, you must still handle unbound `TypeVariable`s and raw/wildcard cases according to the API contract.

## 11. Common pitfalls

| Pitfall | Why it is wrong and how to fix it |
| --- | --- |
| Unconditionally casting `getGenericSuperclass()` to `ParameterizedType` | A raw superclass can return `Class`; check with `instanceof` |
| Seeing `ParameterizedType` and assuming a concrete type is ready | Inner arguments may be `TypeVariable`, `WildcardType`, or nested `ParameterizedType` |
| Using bound `Object` as the actual argument when `T` is unresolved | Bounds/erasure are not bindings; preserve unresolved status |
| Merging all `T`s with the same name into one variable | Each variable also has its own `GenericDeclaration`; key by declaration and position |
| Relying on `obj.getClass()` to obtain `Box<String>` from `new Box<String>()` | Type erasure makes the runtime class shared across instantiations |
| Treating raw `Box` as `Box<Object>` | Raw types lose type arguments and have different compile-time behavior |
| Treating `List<?>` as raw `List` | `List<?>` retains wildcard metadata and different type checking from raw |
| Ascending only one superclass level when multiple generic levels exist | Must propagate variable mappings across inheritance edges |
| Failing to substitute variables recursively inside `List<U>` | Misses concrete `List<String>` across multiple levels |
| Ignoring `unchecked` warnings on raw assignments | Can trigger `ClassCastException` at read/use time |
| Attempting `obj instanceof T` with an unbound type variable | Illegal under reifiable type restrictions; design type checks differently |

## 12. Self-check

1. Why does `OpenBox<String>` created via `new OpenBox<>("x")` not make `OpenBox.class.getGenericSuperclass()` become `Box<String>`?
2. What does `getBounds()` return for a `TypeVariable T` with no declared bound? Is that value the actual argument?
3. What kind of `Type` does `class RawChild extends Box {}` make `RawChild.class.getGenericSuperclass()` return? Can `getActualTypeArguments()` be called directly?
4. If `N extends Number & Comparable<N>`, what is the erasure of `N`? From that, do we know `N = Number`?
5. How do `List<?>` and raw `List` differ in metadata?
6. Given `Concrete extends Mid<String>` and `Mid<U> extends Base<List<U>>`, what steps are needed to find `Base<List<String>>`?
7. Why can assigning through raw `Box` lead to `ClassCastException` even though the program compiled?

**Answers:** (1) the object uses runtime class `OpenBox`, whose declaration signature remains `Box<U>`; (2) bound `Object`, not an actual argument; (3) `Class` of `Box`, with no `getActualTypeArguments()`; (4) `Number`, still does not imply a concrete binding; (5) wildcard vs. missing raw arguments; (6) propagate `U -> String` across relationships and substitute recursively inside `List<U>`; (7) raw bypasses generic checks, and failure occurs when the cast executes at the use site.

## 13. Conclusion and references

In Reflection generic resolution, **no information** and **type `Object`** are two distinct states. For an unbound `TypeVariable`, preserve the variable along with its declaration and bounds; for a raw type, record that type arguments were lost; for a wildcard, preserve the wildcard structure and bounds; for an inheritance chain, substitute variables level by level when valid mappings exist.

Official references:

- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html): `getBounds()`, `getGenericDeclaration()`.
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): `getActualTypeArguments()` and `getRawType()`.
- [Java SE 21 — `Class.getGenericSuperclass()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()): superclass relationship in generic metadata.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure rules.
- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): meaning and risks of raw types.