# Handling Wildcards, Generic Arrays, and Owner Types in Java Reflection Generic Resolution

## 1. The problem: `Type` is not always `Class<?>`

When programming with generics in Java, a declaration can contain parameterized types, wildcards, generic arrays, and enclosing owner types of nested classes:

```java
List<? extends Number> numbers;
List<? super Integer> targets;
List<String>[] pages;
Outer<String>.Inner<Integer> entry;
```

These are **illustrative declarations** that need to be placed in an appropriate class with matching imports and an `Outer` definition.

If a Reflection tool only calls `Field.getType()` and casts the result to `Class<?>`, most of the generic structure has already been lost to **type erasure**. To read and resolve it properly, you must start from `Field.getGenericType()`, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Constructor.getGenericParameterTypes()`, or `Class.getGenericSuperclass()` / `getGenericInterfaces()`.

Those APIs return objects belonging to the **`java.lang.reflect.Type`** family. Three branches are especially important in this lesson:

- **`WildcardType`:** type arguments `?`, `? extends X`, or `? super X` with upper/lower bounds.
- **`GenericArrayType`:** an array type whose component type is a non-reifiable generic type, such as `T[]` or `List<String>[]`.
- **`ParameterizedType.getOwnerType()`:** the owning type of a nested/member type, such as the `Outer<String>` part in `Outer<String>.Inner<Integer>`.

To **resolve generics** rather than merely listing them, you must also handle `TypeVariable<?>` and map type variables according to classes/methods and inheritance relationships. Skipping any branch can cause the algorithm to lose bounds, component details, or the outer's generic mapping.

## 2. The `Type` tree to recognize

`java.lang.reflect.Type` is an interface. A generic analysis tool must know the following core implementations:

| `Type` kind | Declaration example | Meaning / how to handle |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Runtime type; for ordinary arrays use `Class.isArray()` and `getComponentType()` |
| `ParameterizedType` | `List<String>`, `Map<String,Integer>`, `Outer<String>.Inner<Integer>` | Handle `getRawType()`, `getActualTypeArguments()`, and `getOwnerType()` |
| `TypeVariable<?>` | `T` in `class Box<T>` | Look up mapping by the type variable **of the exact declaration**, not just string name |
| `WildcardType` | `? extends Number`, `? super Integer` | Read `getUpperBounds()` and `getLowerBounds()`, resolving recursively if needed |
| `GenericArrayType` | `T[]`, `List<? extends Number>[]` | Read `getGenericComponentType()` and resolve the component recursively |

Recognize using `instanceof` (Java 17+):

```java
if (type instanceof ParameterizedType parameterized) {
    // Has raw type, actual arguments, and possibly an owner type.
} else if (type instanceof WildcardType wildcard) {
    // Read upper/lower bounds.
} else if (type instanceof GenericArrayType array) {
    // Read generic component type.
} else if (type instanceof TypeVariable<?> variable) {
    // Look up binding / bounds of the type variable.
} else if (type instanceof Class<?> clazz) {
    // Normal class, primitive, or array class.
}
```

This is an **algorithm fragment**, not a standalone program; it requires importing the interfaces from `java.lang.reflect` and declaring `type`.

**Rule not to skip:** Structures can be nested across many levels. For example, `List<? extends T[]>[]` has an outer `GenericArrayType`, component `ParameterizedType`, argument `WildcardType`, and an upper bound that is another `GenericArrayType` containing `TypeVariable<T>`. An algorithm that processes one level and casts all children to `Class<?>` will produce wrong results.

## 3. `WildcardType`: distinguishing upper and lower bounds

Wildcards appear in *type arguments*, not in every position where type variables can occur:

```java
List<?> any;
List<? extends Number> producers;
List<? super Integer> consumers;
```

When reading `List<? extends Number>` via Reflection:

1. The field's type is a `ParameterizedType` with raw type `List.class`.
2. `getActualTypeArguments()[0]` is a `WildcardType`.
3. `wildcard.getUpperBounds()` contains `Number.class`.
4. `wildcard.getLowerBounds()` is an empty array.

Similarly, for `List<? super Integer>`, the lower bound is `Integer.class`, while the upper bound is typically `Object.class`.

### 3.1. Two bounds methods of `WildcardType`

| Syntax | `getUpperBounds()` | `getLowerBounds()` |
| --- | --- | --- |
| `?` | `[Object.class]` | `[]` |
| `? extends Number` | `[Number.class]` | `[]` |
| `? super Integer` | `[Object.class]` | `[Integer.class]` |
| `? extends T` | `[TypeVariable<T>]` | `[]` |

The cells above describe the typical wildcard structure produced by the Java compiler, **not** stdout strings of `Arrays.toString`. The APIs return `Type[]`, so bounds may be `Class<?>`, `TypeVariable<?>`, `ParameterizedType`, or other `Type` kinds. When writing general-purpose code, do not assume `getUpperBounds()[0]` is always a `Class<?>`.

- **Unbounded wildcard `?`:** upper bound defaults to `Object`; no lower bound.
- **`? extends U`:** upper-bounded by `U`. If `U` is `T`, after inferring `T → String`, the resolved representation corresponds to `? extends String`.
- **`? super L`:** lower-bounded by `L`; upper bound is typically `Object`.
- **Keep the bound direction intact:** never turn `? super Integer` into `? extends Integer` when substituting types.

### 3.2. Usage connection: PECS

The phrase *Producer Extends, Consumer Super* helps remember many cases:

```java
List<? extends Number> src;  // Read elements as Number; adding non-null values is restricted
List<? super Integer> dst;   // Can add Integer; reading generally only guarantees Object
```

This describes usage constraints in Java source; in Reflection, we read the **bounds structure** for validation, serialization, or metadata generation. Do not use `WildcardType` to assume that a runtime `List` actually contains elements of that exact type: the object's generic type information may already have been erased.

### 3.3. A wildcard is not the same as a `TypeVariable`

`? extends Number` is a **wildcard**; `T extends Number` in `class Holder<T extends Number>` is a **named declared type variable**.

Do not read `TypeVariable.getBounds()` and assume it is completely identical to `WildcardType.getUpperBounds()`. A `TypeVariable` has declaration identity and can have intersection bounds; a wildcard is a type argument describing a variance range of types.

## 4. `GenericArrayType`: generic components inside an array

A declaration such as `T[]` or `List<String>[]` cannot always be reflected by an ordinary `Class<?>`.

```java
class Store<T> {
    T[] items;
    List<String>[] lists;
    String[] strings;
}
```

With `Store.class.getDeclaredField(...).getGenericType()`:

| Field | Typical `Type` received | Component type |
| --- | --- | --- |
| `items` (`T[]`) | `GenericArrayType` | `TypeVariable<T>` |
| `lists` (`List<String>[]`) | `GenericArrayType` | `ParameterizedType List<String>` |
| `strings` (`String[]`) | `Class<?>` with `isArray() == true` | `String.class` |

**Not all arrays are `GenericArrayType`.** In a resolution algorithm, you must also handle the `Class.isArray()` branch to descend into ordinary arrays, especially when formatting or transforming multi-dimensional arrays.

For example:

```java
Type fieldType = Store.class.getDeclaredField("lists")
        .getGenericType();
GenericArrayType array = (GenericArrayType) fieldType;
Type component = array.getGenericComponentType();
// component is a ParameterizedType representing List<String>
```

This illustrative snippet requires importing `Type` and `GenericArrayType`, as well as handling `NoSuchFieldException`. Do not do `(Class<?>) component` without checking the subtype.

### 4.1. Why do generic arrays exist if `new List<String>[10]` is forbidden?

Java generally **forbids directly creating** arrays with non-reifiable parameterized components:

```java
// Does not compile:
// List<String>[] data = new List<String>[10];
```

Even so, **declaring a field or parameter** with type `List<String>[]` is legal. Reflection can retain the generic structure of that declaration in a `GenericArrayType`. The presence of generic array metadata does not prove you are allowed to instantiate that array using `new List<String>[...]` syntax.

An actual runtime array still has a class based on its erased component, such as `List[].class`. Resolving `List<String>[]` metadata does not turn runtime array store checks into checks for the `String` type argument; type erasure limits still apply.

### 4.2. When substituting `T`, how should it be handled?

Suppose:

```java
class Base<T> {
    T[] values;
    List<? extends T>[] groups;
}

class StringBase extends Base<String> {}
```

The mapping from `StringBase` for `Base`'s variable `T` is `T → String`. When resolving the *generic structure*:

- `T[]` becomes a representation of `String[]`.
- `List<? extends T>[]` becomes `List<? extends String>[]`.
- If you need to return a real `Type` object, you must reconstruct/represent the substituted nodes properly; you cannot merely replace substrings inside `getTypeName()`.

If the component has been substituted into a concrete `Class<?>` and the task needs the **array's Class object**, you can obtain a corresponding class via `java.lang.reflect.Array.newInstance(componentClass, 0).getClass()`. If the component is still a `ParameterizedType` or contains a wildcard, there is no `Class<?>` that directly represents the full parameterized information; you must preserve a `GenericArrayType` or an equivalent metadata object.

## 5. `ParameterizedType.getOwnerType()`: generic owner of a member type

Consider the declaration:

```java
class Outer<A> {
    class Inner<B> {
        A fromOuter;
        B fromInner;
    }
}
```

A field in an appropriate place can use the type:

```java
Outer<String>.Inner<Integer> entry;
```

This is a **member inner class**. The `ParameterizedType` of field `entry` has the structure:

```text
ParameterizedType: Outer<String>.Inner<Integer>
├── getRawType()                 → Class: Outer.Inner
├── getActualTypeArguments()     → [Class: Integer]
└── getOwnerType()               → ParameterizedType: Outer<String>
    ├── getRawType()             → Class: Outer
    └── getActualTypeArguments() → [Class: String]
```

Key point: **`getActualTypeArguments()` of `Inner<Integer>` only contains `Integer`**, and does not automatically repeat `String` from outer. To resolve the field `fromOuter` of type `A`, the algorithm must ascend to **`getOwnerType()`** to obtain the `A → String` binding.

If you only build `Map<TypeVariable<?>, Type>` from `Inner.class.getTypeParameters()`, you only have `B → Integer` and will lose the meaning of `A`.

### 5.1. Owner type differs from enclosing instance

Three concepts must not be conflated:

- **`getOwnerType()`:** the `Type` object describing the type containing the member type, which may carry generic arguments like `Outer<String>`. This is **type metadata**.
- **Enclosing instance:** a specific **object** of type `Outer<?>` required to instantiate a non-static member inner object, e.g. `outer.new Inner<Integer>()`. This is a **runtime value**, not a `Type`.
- **`Class.getEnclosingClass()` / `getDeclaringClass()`:** returns `Class<?>` metadata about the declaration site/lexical context, not necessarily including the type arguments of a specific usage.

Do not pass `ParameterizedType getOwnerType()` as a constructor argument in place of a real `Outer` instance.

### 5.2. Owner type of a static nested class

A `static nested class` can have owner type metadata even though it **is not bound to an enclosing instance**. For example:

```java
class Outer<A> {
    static class Nested<B> {}
}
```

The valid usage type is `Outer.Nested<Integer>`, **not** `Outer<String>.Nested<Integer>`, because a static nested class does not depend on the outer's parameterization. In Reflection, the owner may represent `Outer.class` (a `Class<?>`) rather than `Outer<String>`; you still must not infer from `getOwnerType() != null` that an enclosing instance must be passed.

For a top-level parameterized type like `List<String>`, `getOwnerType()` returns `null`. However, when the raw type is a member class, the owner can be non-`null`, and `getActualTypeArguments()` can even be empty if the member **declares no type parameters** yet sits under a parameterized owner. Your traversal must inspect owner independently of the actual arguments array length.

## 6. Systematic generic resolution algorithm

A type resolver should take two inputs:

1. A **`Type` to resolve**, such as the generic type of a field/return/parameter.
2. A binding environment **`Map<TypeVariable<?>, Type>`** inferred from the usage context (subclass, interface implementation, parameterized owner, method context...).

Then recurse:

```text
resolve(type, bindings)
    Class:
        if array → resolve(component); may construct Class-array if appropriate
        otherwise → keep as-is
    TypeVariable:
        look up binding by exact TypeVariable declaration; if none → keep as-is
        if present → resolve(binding) (with cycle guard)
    ParameterizedType:
        resolve(owner) if non-null
        resolve each actual type argument
        keep raw type; combine into a new ParameterizedType representation if changed
    GenericArrayType:
        resolve(generic component)
        combine into an array type, keeping parameterized form if component is non-reifiable
    WildcardType:
        resolve all upper bounds
        resolve all lower bounds
        preserve extends/super direction and wildcard distinction
    Other:
        preserve as-is or explicitly report unsupported type
```

This is **pseudocode**, not Java syntax for compiling.

**Crucial regarding identity:** Two variables with the same name `T` belonging to `class Box<T>` and `<T> void send(T item)` are **two distinct `TypeVariable<?>`s**. Do not use a plain `Map<String, Type>` keyed by `"T"`; use `TypeVariable<?>` directly as the key and inspect `getGenericDeclaration()` when debugging.

**Crucial regarding mapping chains:** In multi-level inheritance, you may encounter `U → T` and then `T → String`. Resolution must keep following mappings until stable, while guarding against cycles/self-referential bounds. If no binding exists, return the unresolved type variable; **do not arbitrarily turn it into `Object`**.

### 6.1. Collecting bindings from supertypes

```java
class Parent<T> {
    T[] values;
}

class Child<U> extends Parent<U> {}

class Concrete extends Child<String> {}
```

The initial mapping from `Concrete` is `U → String`. When inspecting `Child<U>`'s superclass, `T → U` is added. The algorithm must follow `T → U → String` before producing `String[]` for `Parent.values`.

To work across multiple interface/superclass levels, use `getGenericSuperclass()` and `getGenericInterfaces()`, following the exact path from the concrete class to the declaration owning the member. Do not mix up bindings from unrelated branches; each `TypeVariable` always belongs to a specific declaration.

### 6.2. Collecting bindings from owner before member

For `Outer<String>.Inner<Integer>`:

1. Process `getOwnerType() == Outer<String>`, mapping `Outer.A → String`.
2. Process `getRawType() == Inner.class` and `Inner`'s own arguments, mapping `Inner.B → Integer`.
3. Resolve fields in `Inner`: `A` and `B` become `String` and `Integer`, respectively.

For multi-level nested types, keep walking the owner chain until `null` or a non-parameterized `Class<?>`. Do not assume `getOwnerType()` is always a `ParameterizedType`: it can be a `Class<?>`.

## 7. Complete Java 17+ program: reading and resolving all three branches

The following program uses a recursive **type renderer**. It does not attempt to mimic a library that constructs new `ParameterizedType`/`WildcardType` instances; instead, it reads Reflection structures and applies bindings to produce an easily testable representation. This is the step for learning the algorithm before writing a resolver that returns new `Type` objects.

Create the file **`GenericGraphDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class GenericGraphDemo {
    static class Container<A> {
        class Entry<B> {
            A ownerValue;
            B value;
            List<? extends A>[] grids;
        }

        static class Nested<C> {
            C data;
        }
    }

    static class Template<T> {
        T[] values;
        List<? extends T>[] producers;
        List<? super T> consumers;
    }

    static class TextTemplate extends Template<String> {}

    static class Cases {
        Container<String>.Entry<Integer> member;
        Container<String>.Entry<Integer>[] memberArray;
        List<? extends Number>[] numberArrays;
        List<? super Integer> sinks;
        List<?> anything;
        String[] ordinaryArray;
    }

    // Collect type-variable bindings from owner first,
    // then from the type arguments of the member type itself.
    static void bind(Type type, Map<TypeVariable<?>, Type> env) {
        if (!(type instanceof ParameterizedType p)) {
            return;
        }
        if (p.getOwnerType() != null) {
            bind(p.getOwnerType(), env);
        }

        Class<?> raw = (Class<?>) p.getRawType();
        TypeVariable<?>[] vars = raw.getTypeParameters();
        Type[] args = p.getActualTypeArguments();

        for (int i = 0; i < vars.length; i++) {
            env.put(vars[i], args[i]);
        }
    }

    static String show(Type type, Map<TypeVariable<?>, Type> env) {
        return show(type, env, new HashSet<>());
    }

    static String show(Type type, Map<TypeVariable<?>, Type> env,
                       Set<TypeVariable<?>> visiting) {
        if (type instanceof Class<?> c) {
            return c.isArray()
                    ? show(c.getComponentType(), env, visiting) + "[]"
                    : c.getSimpleName();
        }

        if (type instanceof TypeVariable<?> v) {
            Type replacement = env.get(v);
            if (replacement == null || replacement.equals(v)
                    || !visiting.add(v)) {
                return v.getName();
            }
            try {
                return show(replacement, env, visiting);
            } finally {
                visiting.remove(v);
            }
        }

        if (type instanceof GenericArrayType a) {
            return show(a.getGenericComponentType(), env, visiting) + "[]";
        }

        if (type instanceof WildcardType w) {
            Type[] lowers = w.getLowerBounds();
            if (lowers.length != 0) {
                return "? super " + show(lowers[0], env, visiting);
            }
            Type[] uppers = w.getUpperBounds();
            if (uppers.length == 0 ||
                    (uppers.length == 1 && uppers[0] == Object.class)) {
                return "?";
            }
            StringJoiner upper = new StringJoiner(" & ");
            for (Type bound : uppers) {
                upper.add(show(bound, env, visiting));
            }
            return "? extends " + upper;
        }

        if (type instanceof ParameterizedType p) {
            Class<?> raw = (Class<?>) p.getRawType();
            Type owner = p.getOwnerType();
            String head = owner == null
                    ? raw.getSimpleName()
                    : show(owner, env, visiting) + "." + raw.getSimpleName();
            Type[] args = p.getActualTypeArguments();
            if (args.length == 0) {
                return head;
            }

            StringJoiner body = new StringJoiner(", ", "<", ">");
            for (Type arg : args) {
                body.add(show(arg, env, visiting));
            }
            return head + body;
        }

        // Avoid making assumptions about other Type implementations.
        return type.getTypeName();
    }

    public static void main(String[] args) throws Exception {
        Type numbers = Cases.class
                .getDeclaredField("numberArrays").getGenericType();
        GenericArrayType array = (GenericArrayType) numbers;
        ParameterizedType list =
                (ParameterizedType) array.getGenericComponentType();
        WildcardType upper =
                (WildcardType) list.getActualTypeArguments()[0];

        System.out.println("numberArrays generic array: "
                + (numbers instanceof GenericArrayType));
        System.out.println("component raw List: "
                + (list.getRawType() == List.class));
        System.out.println("upper is Number: "
                + (upper.getUpperBounds()[0] == Number.class));
        System.out.println("lower bound count: "
                + upper.getLowerBounds().length);

        ParameterizedType sinks = (ParameterizedType) Cases.class
                .getDeclaredField("sinks").getGenericType();
        WildcardType lower =
                (WildcardType) sinks.getActualTypeArguments()[0];
        System.out.println("super lower Integer: "
                + (lower.getLowerBounds()[0] == Integer.class));
        System.out.println("super upper Object: "
                + (lower.getUpperBounds()[0] == Object.class));

        Type plain = Cases.class
                .getDeclaredField("ordinaryArray").getGenericType();
        System.out.println("ordinary array Class: "
                + (plain instanceof Class<?>));

        Type members = Cases.class
                .getDeclaredField("memberArray").getGenericType();
        System.out.println("memberArray generic array: "
                + (members instanceof GenericArrayType));

        Type memberType = Cases.class
                .getDeclaredField("member").getGenericType();
        ParameterizedType entry = (ParameterizedType) memberType;
        ParameterizedType owner =
                (ParameterizedType) entry.getOwnerType();
        System.out.println("owner argument String: "
                + (owner.getActualTypeArguments()[0] == String.class));
        System.out.println("inner argument Integer: "
                + (entry.getActualTypeArguments()[0] == Integer.class));

        Map<TypeVariable<?>, Type> byOwner = new HashMap<>();
        bind(memberType, byOwner);

        System.out.println("outer field resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("ownerValue").getGenericType(),
                        byOwner));
        System.out.println("inner field resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("value").getGenericType(),
                        byOwner));
        System.out.println("grids resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("grids").getGenericType(),
                        byOwner));

        Type base = TextTemplate.class.getGenericSuperclass();
        Map<TypeVariable<?>, Type> bySubclass = new HashMap<>();
        bind(base, bySubclass);

        System.out.println("T array resolved: "
                + show(Template.class
                        .getDeclaredField("values").getGenericType(),
                        bySubclass));
        System.out.println("wildcard array resolved: "
                + show(Template.class
                        .getDeclaredField("producers").getGenericType(),
                        bySubclass));
        System.out.println("super wildcard resolved: "
                + show(Template.class
                        .getDeclaredField("consumers").getGenericType(),
                        bySubclass));
    }
}
```

Compile and run in the directory containing the file using JDK 17 or higher:

```bash
javac GenericGraphDemo.java
java GenericGraphDemo
```

**Expected stdout:**

```text
numberArrays generic array: true
component raw List: true
upper is Number: true
lower bound count: 0
super lower Integer: true
super upper Object: true
ordinary array Class: true
memberArray generic array: true
owner argument String: true
inner argument Integer: true
outer field resolved: String
inner field resolved: Integer
grids resolved: List<? extends String>[]
T array resolved: String[]
wildcard array resolved: List<? extends String>[]
super wildcard resolved: List<? super String>
```

### 7.1. Explaining the observed type tree

- `numberArrays` is an array with component `List<? extends Number>`; `getGenericType()` returns a `GenericArrayType`, inside which is a `ParameterizedType`, then a `WildcardType`. The upper bound is `Number`.
- `sinks` has argument `? super Integer`, so the lower bound is `Integer` and the default upper bound is `Object`.
- `ordinaryArray` has a generic type that is a `Class<?>` representing `String[]`.
- `memberArray` has generic component `Container<String>.Entry<Integer>`, so it is a `GenericArrayType`.
- `entry.getActualTypeArguments()` contains only `Integer`. `String` resides in `entry.getOwnerType()`.
- The `bind` method walks the owner and adds `Container`'s variable `A` along with `Entry`'s variable `B`. Therefore, when inspecting `Entry`'s fields, `A` resolves to `String` and `B` to `Integer`.
- For `TextTemplate extends Template<String>`, the binding from `getGenericSuperclass()` is `T → String`. `show` traverses `T[]`, wildcards, and generic arrays, preserving the structure and substituting the right type variable.

**Intentional limitations of the example:** `show` produces a **descriptive string**, not a new `Type` object. `bind` illustrates two specific scenarios (a parameterized owner and a parameterized superclass). A resolver used in a real library must support multi-level inheritance/interfaces, generic method contexts, missing `Signature` attributes, raw types, and non-standard `Type` implementations. Do not treat this demo as a complete generic resolver system for all valid bytecode.

## 8. When you need to return a substituted `Type`, not just a string

In applications such as schema generation or serializers, the result usually needs to be a **new `Type` structure** rather than a display string. In that case:

- Ordinary `Class<?>` can be kept as-is.
- A `TypeVariable<?>` with a binding must be replaced by its corresponding `Type`.
- `ParameterizedType` needs a new representation holding the **resolved owner**, **raw type**, and **resolved actual type arguments**.
- `GenericArrayType` needs a new representation holding the **resolved generic component type**; if the component has become a valid `Class<?>`, you can obtain the corresponding array class via `Array.newInstance(...)`.
- `WildcardType` needs a new representation with **resolved upper/lower bounds**, without losing the `extends`/`super` direction.
- If nothing changed, you can keep the original `Type` instead of allocating a new object.

The `ParameterizedType`, `GenericArrayType`, and `WildcardType` interfaces define the data contracts; Java SE does not provide a general public factory to construct arbitrary combinations. Libraries can use their own `Type` implementations, provided they properly implement `equals`/`hashCode`, return defensive copies of bounds/arguments arrays, and satisfy `getTypeName()`/`toString()` semantics. **Do not create a fake `Class<?>` to represent `List<String>`:** at runtime, `List.class` does not hold the `String` type argument.

For example, after `T → String`:

- `T[]` can become `String[].class` if a reifiable array class is needed.
- `List<? extends T>[]` still needs a generic type representation for the `List<? extends String>` component; there is no class literal `List<? extends String>[].class`.
- `Outer<T>.Inner<Integer>` must also substitute the owner `Outer<String>`, not only the inner argument `Integer`.

## 9. Type erasure and metadata limits

Not every `Type` you want always exists with complete information:

- **Generic signatures can be missing.** Post-erasure JVM field/method descriptors do not fully describe wildcards and type arguments. Reflection generic APIs rely on `Signature` metadata when present.
- **Raw types are insufficient to reconstruct generics.** From `List.class`, you cannot deduce whether a value was `List<String>` or `List<Integer>`.
- **Method type parameters have their own scope.** A `<T> T convert(T input)` cannot automatically resolve `T` from class generic bindings alone; it may need call-site context that basic Reflection does not supply.
- **Generic arrays do not turn JVM arrays into type-argument-checking structures.** Runtime array types are still subject to erasure and can cause heap pollution if developers misuse raw types/unchecked casts.
- **Recursive bounds:** `class Node<T extends Comparable<T>>` references `T` itself. Printing/resolving bounds must guard against cycles to avoid infinite recursion.
- **Module visibility / classpath:** when reading generic metadata, Reflection can throw `TypeNotPresentException`, `MalformedParameterizedTypeException`, or `GenericSignatureFormatError` if a referenced type is missing or a signature is invalid. Do not assume every missing detail is caused by wildcard logic.
- **Original syntax cannot be inferred:** import forms, whitespace, or equivalent declaration styles cannot be accurately reconstructed from `Type.getTypeName()`.

### 9.1. Do not silently "resolve" a type variable to its upper bound

Suppose:

```java
class NumericBox<T extends Number> {
    T value;
}
```

If you inspect `NumericBox.class` **without** a context like `NumericBox<Integer>`, `T` is still `TypeVariable<T>`. Knowing `getBounds()[0] == Number.class` does not allow concluding that the field is semantically `Number`: `Number` is only an **upper bound**, not a bound argument. You may use the bound for validation or an erased view if the problem requires it, but keep the distinction clear.

### 9.2. Name strings do not replace structure

`Type.getTypeName()` is useful for logging. However:

- Do not parse/replace `"T"` with `"String"` in a long string, because type names, variable names, or variables from other declarations can collide.
- Do not split strings on `<`, `>`, `[` to locate wildcards/arrays; that is the job of the `Type` tree and reflection APIs.
- Do not rely solely on names generated by `toString()` implementations to determine type identity.
- Use `TypeVariable.getGenericDeclaration()`, `ParameterizedType.getRawType()`, and child `Type` arrays for accurate resolution.

## 10. Framework application workflow

A controlled implementation approach:

1. **Identify the member declaration:** field, method, parameter, superclass, or interface.
2. **Retrieve generic metadata:** `getGenericType()` / `getGenericReturnType()` / `getGenericParameterTypes()`; avoid starting with `getType()` when generic arguments are needed.
3. **Identify the usage context:** subclass, parameterized owner type, or type token storing generic args.
4. **Build bindings by declaration:** walk from context to the class owning the member; traverse superclasses/interfaces and owner types; use `TypeVariable<?>` as the key.
5. **Traverse every branch recursively:** `ParameterizedType`, `WildcardType`, `GenericArrayType`, `TypeVariable`, `Class<?>`, including ordinary arrays.
6. **Preserve semantics:** wildcard bound directions, array components, owner parameterization, argument ordering, and raw types.
7. **Handle unknowns:** preserve unbound variables instead of assuming `Object`; if signatures are malformed/missing, report the limitation.
8. **Test thoroughly:** include tests for `List<?>`, `? extends`, `? super`, `T[]`, `List<T>[]`, `Outer<String>.Inner<Integer>`, static nested classes, and multi-level inheritance.

### Common pitfalls table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Casting every `Type` to `Class<?>` | `ClassCastException` or lost generics | Branch using `instanceof` |
| Ignoring `WildcardType.getLowerBounds()` | `? super Integer` is misinterpreted | Distinguish upper and lower bounds |
| Assuming wildcards always have a lower bound | Fails for `?` and `? extends X` | Lower bounds array can be empty |
| Resolving a wildcard by taking its single upper bound | Loses `?` and variance direction | Preserve wildcard node when reconstructing |
| Supporting only `GenericArrayType` | Misses `String[]` reflected as `Class` | Also handle `Class.isArray()` |
| Reading only `getActualTypeArguments()` on an inner type | Loses `A → String` from `Outer<String>` | Read `getOwnerType()` recursively |
| Treating `getOwnerType() != null` as needing an outer object | Confuses generic metadata with enclosing instance | Handle `static` and member class structures separately |
| Using `Map<String,Type>` keyed by `"T"` | Collides type variables from different declarations | Use `TypeVariable<?>` as key |
| Always mapping `T → Number` upon seeing `T extends Number` | Hardcodes an unknown type argument | Keep `T` unresolved |
| Parsing `getTypeName()` instead of walking the tree | Breaks on nested generics/wildcards/owners | Use the `Type` subtypes |
| Keeping `ParameterizedType` unchanged even when owner changed | Inconsistent internal result | Resolve both owner and arguments |
| Assuming generic metadata is always complete | Fails on class files missing/having malformed `Signature` | Handle missing metadata and reflection errors |

## 11. Self-check exercises

### Question 1: wildcard bounds

For `List<? super Long>`, what do `getUpperBounds()` and `getLowerBounds()` of the wildcard typically contain?

**Answer:** Upper contains `Object.class`; lower contains `Long.class`. If you only read upper, you lose the most important information of `super`.

### Question 2: generic array

Does field `Map<String,Integer>[] mapping` have `getGenericType()` as `Class<?>` or `GenericArrayType`?

**Answer:** `GenericArrayType`; the component is a `ParameterizedType` representing `Map<String,Integer>`. It differs from field `String[] names`, which has a `Class<?>` array class.

### Question 3: owner type

Given `Outer<String>.Inner<Integer>` with `class Outer<A> { class Inner<B> {} }`. Why doesn't `Inner.class.getTypeParameters()` help find `A → String`?

**Answer:** `Inner` only declares variable `B`. `A` belongs to the `Outer` declaration, and the `String` argument resides in `ParameterizedType.getOwnerType()`.

### Question 4: static nested

`Outer.Nested<Integer>` is a static nested class. If Reflection shows a non-`null` owner type, is an `Outer` instance required to invoke `Nested`'s constructor?

**Answer:** No. The owner type here is type-structure metadata. A static nested class does not require an enclosing instance for this nesting relationship.

### Question 5: type substitution chain

Suppose `Parent<T>`, `Child<U> extends Parent<U>`, `Concrete extends Child<String>`. How do you resolve field `Parent<T>.value` in the context of `Concrete`?

**Answer:** Build `U → String` and `T → U`, then recursively resolve `T → U → String`. Map by each declaration's `TypeVariable<?>`, not by string name.

### Question 6: insufficient metadata

If only `List.class` is available at runtime, can an algorithm know for sure that the source type argument was `String`?

**Answer:** No. Erasure has removed the type parameter; you need a `ParameterizedType` in a generic declaration, a type token, or other real metadata—otherwise record it as unknown.

## 12. Summary

When resolving generics with Reflection, treat `Type` as a **structural tree**:

- **`WildcardType`:** preserve upper/lower bounds and `extends`/`super` direction.
- **`GenericArrayType`:** recursively resolve the component type; distinguish from ordinary arrays reflected as `Class<?>`.
- **`ParameterizedType.getOwnerType()`:** follow the owning type of a member type so outer generic class bindings are not lost.
- **`TypeVariable<?>`:** map by declaration identity, follow contextual bindings, and guard against cycles.

A good resolver returns meaningful metadata or explicitly marks unknowns; it does not fabricate generic arguments from a raw `Class<?>` and does not equate type metadata with a runtime enclosing instance.

### References

- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 21 — `WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Java SE 21 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java Language Specification `4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html)