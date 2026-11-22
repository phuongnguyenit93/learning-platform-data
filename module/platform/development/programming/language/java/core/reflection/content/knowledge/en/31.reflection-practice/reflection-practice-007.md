# Resolving a Subclass's Generic Type Across Multiple Inheritance Levels in Java

## 1. Practical Problem

In Java, generics largely undergo **type erasure** at runtime. However, information about the **declared superclass type** often remains in the class file and can be read via reflection. Thanks to this, a framework can determine the concrete type argument supplied by a subclass across multiple inheritance levels — for example, to build serializers, repositories, mappers, or handler registries.

Consider the chain:

```java
class Base<T> {}
class Middle<U> extends Base<java.util.List<U>> {}
class End extends Middle<String> {}
```

What we want to find is: when viewed from `End`, `T` of `Base<T>` is actually `List<String>`. Looking at just one parent class is not enough to conclude this, because `Middle` passes `List<U>`, and `U` is only fixed to `String` by `End`.

The desired outcome is **contextual resolution**:

```text
Base.T = java.util.List<java.lang.String>
```

We must preserve the identity of each `TypeVariable` and trace links across levels. Simply looking up variable names `T`/`U` or calling `getSuperclass()` is insufficient.

## 2. Which APIs Should We Read?

| API | Value returned | Role |
| --- | --- | --- |
| `Class.getSuperclass()` | `Class<?>` of the direct superclass | Shows the raw relationship, **does not contain** generic arguments like `String` |
| `Class.getGenericSuperclass()` | `Type` describing the declared parent type | May be a `ParameterizedType` if the subclass declares generic arguments |
| `Class.getTypeParameters()` | `TypeVariable<?>[]` | Lists the type variables declared by that class itself, in order |
| `ParameterizedType.getRawType()` | `Type` (typically `Class<?>`) | Identifies the underlying generic class such as `Middle.class` |
| `ParameterizedType.getActualTypeArguments()` | `Type[]` | Arguments such as `String.class`, `List<U>`, `U[]` |
| `TypeVariable.getGenericDeclaration()` | `GenericDeclaration` | Distinguishes two variables with the same name from two different declarations |
| `TypeVariable.getBounds()` | `Type[]` | Upper bounds of an unfixed variable, **not** the passed argument |

Objects you may encounter when traversing `Type`:

- `Class<?>`: a concrete class, primitive, or array with no generic variables left to resolve.
- `ParameterizedType`: a type with arguments, such as `List<U>` or `Map<String, ? extends U>`.
- `TypeVariable<?>`: a type variable such as `T`, `U`, or `Z`.
- `GenericArrayType`: an array type whose component is a generic type, e.g., `X[]`.
- `WildcardType`: `?`, `? extends U`, `? super U`.

**Common mistake:** `Base.class.getTypeParameters()[0]` will still be the variable `T`. It does not automatically know which subclass is under inspection. To obtain `List<String>`, you must build a **substitution table from the concrete subclass up to the ancestor class**.

## 3. Tracing Multiple Levels with a Type Variable Binding Map

Suppose:

```java
class Three<A, B, C> {}
class Two<X, Y> extends Three<
        java.util.List<Y>,
        X[],
        java.util.Map<String, ? extends Y>> {}
class One<Z> extends Two<String, Z> {}
class Concrete extends One<Integer> {}
```

The arguments when walking up from `Concrete` to `Three`:

| Inheritance edge | Mapping per parent type declaration |
| --- | --- |
| `Concrete extends One<Integer>` | `One.Z → Integer` |
| `One<Z> extends Two<String,Z>` | `Two.X → String`, `Two.Y → One.Z` |
| `Two<X,Y> extends Three<List<Y>,X[],Map<String,? extends Y>>` | `Three.A → List<Two.Y>`, `Three.B → Two.X[]`, `Three.C → Map<String, ? extends Two.Y>` |

From there, apply **recursion**:

- `Three.A → List<Two.Y> → List<One.Z> → List<Integer>`.
- `Three.B → Two.X[] → String[]`.
- `Three.C → Map<String,? extends Two.Y> → Map<String,? extends One.Z> → Map<String,? extends Integer>`.

Each variable name is merely a descriptive symbol. In code, the map key must be the **`TypeVariable<?>` object**, not the string `"X"` or `"Z"`. Since any two classes can both declare `T`, a `Map<String,Type>` could accidentally overwrite another class's binding.

### Algorithm for a single-class inheritance chain

1. Start with `Class<?> leaf` as the subclass being inspected.
2. Get `leaf.getGenericSuperclass()`.
3. If it is a `ParameterizedType`, take the parent's raw class and its type arguments array; pair each `rawClass.getTypeParameters()[i]` with `getActualTypeArguments()[i]` in the binding map.
4. If it is a `Class<?>`, that is an unparameterized edge to continue walking up; **do not invent a concrete type argument**.
5. Continue up parent classes until reaching `Object` or having no parent left.
6. When you need to know an ancestor class's type variable, **recursively substitute** through the collected map. For composite types, descend into `ParameterizedType`, `GenericArrayType`, and `WildcardType` instead of stopping at the outer layer.

The map in the example can temporarily store `Three.A → List<Two.Y>`. There is no need to "freeze" the result the moment `Three` is visited; resolving all links at the end produces the right answer once lower-level variables have been recorded.

## 4. Complete Java 17+ Example: Resolving Signatures Across Three Levels

The following example intentionally **returns string representations of resolved types**, rather than building custom implementations of `ParameterizedType`/`WildcardType`. This approach fits when the goal is diagnostics and learning the algorithm. If a program needs an actual substituted `Type` object for a framework, you must add `Type` implementations or use a type-token library with clear contracts.

Save the file `GenericHierarchyResolverDemo.java`:

```java
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.Collectors;

public class GenericHierarchyResolverDemo {
    static class Three<A, B, C> {}

    static class Two<X, Y> extends Three<
            List<Y>, X[], Map<String, ? extends Y>> {}

    static class One<Z> extends Two<String, Z> {}

    static final class Concrete extends One<Integer> {}

    // From class with unfixed R: must not treat bound Number as the actual type.
    static class Open<R extends Number> extends One<R> {}

    static Map<TypeVariable<?>, Type> collectBindings(Class<?> leaf) {
        Map<TypeVariable<?>, Type> bindings = new LinkedHashMap<>();
        Class<?> current = leaf;

        while (current != null && current != Object.class) {
            Type genericParent = current.getGenericSuperclass();

            if (genericParent instanceof ParameterizedType parent) {
                Type raw = parent.getRawType();
                if (!(raw instanceof Class<?> parentClass)) {
                    throw new IllegalArgumentException(
                            "Unsupported raw type: " + raw);
                }

                TypeVariable<?>[] variables =
                        parentClass.getTypeParameters();
                Type[] arguments = parent.getActualTypeArguments();

                if (variables.length != arguments.length) {
                    throw new IllegalStateException(
                            "Mismatched generic signature");
                }

                for (int i = 0; i < variables.length; i++) {
                    bindings.put(variables[i], arguments[i]);
                }
                current = parentClass;
            } else if (genericParent instanceof Class<?> rawParent) {
                current = rawParent;
            } else {
                break;
            }
        }
        return bindings;
    }

    static String describe(Type type, Map<TypeVariable<?>, Type> bindings) {
        return describe(type, bindings, new HashSet<>());
    }

    static String describe(Type type, Map<TypeVariable<?>, Type> bindings,
            Set<TypeVariable<?>> visiting) {

        if (type instanceof TypeVariable<?> variable) {
            if (!visiting.add(variable)) {
                return variable.getName();
            }
            try {
                Type replacement = bindings.get(variable);
                if (replacement == null || replacement.equals(variable)) {
                    return variable.getName();
                }
                return describe(replacement, bindings, visiting);
            } finally {
                visiting.remove(variable);
            }
        }

        if (type instanceof ParameterizedType parameterized) {
            String arguments = Arrays.stream(
                    parameterized.getActualTypeArguments())
                    .map(argument -> describe(
                            argument, bindings, visiting))
                    .collect(Collectors.joining(", "));
            return parameterized.getRawType().getTypeName()
                    + "<" + arguments + ">";
        }

        if (type instanceof GenericArrayType genericArray) {
            return describe(
                    genericArray.getGenericComponentType(),
                    bindings, visiting) + "[]";
        }

        if (type instanceof WildcardType wildcard) {
            Type[] lower = wildcard.getLowerBounds();
            if (lower.length > 0) {
                return "? super " + Arrays.stream(lower)
                        .map(bound -> describe(
                                bound, bindings, visiting))
                        .collect(Collectors.joining(" & "));
            }

            Type[] upper = wildcard.getUpperBounds();
            if (upper.length == 1 && upper[0] == Object.class) {
                return "?";
            }
            return "? extends " + Arrays.stream(upper)
                    .map(bound -> describe(bound, bindings, visiting))
                    .collect(Collectors.joining(" & "));
        }

        return type.getTypeName();
    }

    static String resolveParameter(
            Class<?> ancestor, int index,
            Map<TypeVariable<?>, Type> bindings) {
        TypeVariable<?>[] variables = ancestor.getTypeParameters();
        if (index < 0 || index >= variables.length) {
            throw new IndexOutOfBoundsException(index);
        }
        return describe(variables[index], bindings);
    }

    static void requireEquals(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Map<TypeVariable<?>, Type> concrete =
                collectBindings(Concrete.class);

        String a = resolveParameter(Three.class, 0, concrete);
        String b = resolveParameter(Three.class, 1, concrete);
        String c = resolveParameter(Three.class, 2, concrete);
        String z = resolveParameter(One.class, 0, concrete);

        requireEquals("java.util.List<java.lang.Integer>", a);
        requireEquals("java.lang.String[]", b);
        requireEquals(
                "java.util.Map<java.lang.String, ? extends java.lang.Integer>",
                c);
        requireEquals("java.lang.Integer", z);

        System.out.println("Concrete.Three.A=" + a);
        System.out.println("Concrete.Three.B=" + b);
        System.out.println("Concrete.Three.C=" + c);
        System.out.println("Concrete.One.Z=" + z);

        Map<TypeVariable<?>, Type> open = collectBindings(Open.class);
        String unresolved = resolveParameter(Three.class, 0, open);
        requireEquals("java.util.List<R>", unresolved);
        System.out.println("Open.Three.A=" + unresolved);

        System.out.println("rawParent=" +
                Concrete.class.getSuperclass().getSimpleName());
        System.out.println("checks=PASS");
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 GenericHierarchyResolverDemo.java
java GenericHierarchyResolverDemo
```

Stdout:

```text
Concrete.Three.A=java.util.List<java.lang.Integer>
Concrete.Three.B=java.lang.String[]
Concrete.Three.C=java.util.Map<java.lang.String, ? extends java.lang.Integer>
Concrete.One.Z=java.lang.Integer
Open.Three.A=java.util.List<R>
rawParent=One
checks=PASS
```

### Reading the Example Step by Step

- `Concrete` extends `One<Integer>`: `getGenericSuperclass()` is a `ParameterizedType`, yielding `One.Z → Integer`.
- `One<Z>` extends `Two<String,Z>`: yielding `Two.X → String` and `Two.Y → One.Z`.
- `Two<X,Y>` extends `Three<List<Y>,X[],Map<String,? extends Y>>`: records bindings for `Three.A`, `Three.B`, and `Three.C`.
- When printing `Three.A`, `describe` descends from `TypeVariable` into `ParameterizedType` and follows both variables `Y` and `Z`; the result is `List<Integer>`.
- `Three.B` uses `GenericArrayType` (an array whose component is type variable `X`), which after substitution becomes `String[]`.
- `Three.C` forces the resolver into a `ParameterizedType` containing a `WildcardType`; simply calling `Type.getTypeName()` on the original structure would still leave `? extends Y` **only partially resolved**.
- `Open<R extends Number>` produces `List<R>` because `R` **has not been fixed** by a concrete subclass. Never automatically replace `R` with `Number`: a bound is a type constraint, not an actual argument.
- `requireEquals` makes the program **self-verify** the results, rather than just printing descriptive strings.

The `collectBindings` method is designed for a **superclass chain**. It does not walk `getGenericInterfaces()`, does not include the owner type of a non-static nested class in the output string, and does not reconstruct a `Type` object tree usable across every framework. Those limitations must be addressed before using it as a full generic resolution library.

## 5. Why Must `TypeVariable` Be Distinguished by Declaration Site?

Example:

```java
class Parent<T> {}
class Child<T> extends Parent<T> {}
class Fixed extends Child<String> {}
```

`Parent.T` and `Child.T` both have the name `"T"`, yet they are **two distinct type variables** because they are declared on two different classes. The proper mapping is:

```text
Parent.T -> Child.T
Child.T  -> java.lang.String
Result Parent.T = java.lang.String
```

If you use `Map<String, Type>` keyed by `"T"`, the second step can overwrite the first and break the link structure; in complex branches, results become wrong or hit spurious loops. Using `Map<TypeVariable<?>,Type>` preserves identity and declaration context. You can inspect `variable.getGenericDeclaration()` to tell which class, interface, method, or constructor owns the variable.

The `describe` method also takes `Set<TypeVariable<?>> visiting` to prevent non-terminating recursion on cyclic mappings. This is a defensive guard in the resolver, **not** an indication that arbitrary generics can create a cyclic superclass in Java.

## 6. Generic Arrays, Wildcards, Raw Types, and Unknown Types

### Generic arrays and wildcards

The type `X[]` in `Two<X,Y>` typically appears as a `GenericArrayType` because the component `X` is a `TypeVariable`. A generic resolver that skips this branch will return raw `X[]` instead of `String[]`.

Similarly, `Map<String, ? extends Y>` is a `ParameterizedType` containing a `WildcardType`. The argument `? extends Y` must be resolved further to become `? extends Integer`. For `? super Y`, handle `getLowerBounds()`; for an unbounded wildcard, `getUpperBounds()` is typically `Object.class` and renders as `?`.

**Do not confuse a bound with a type argument**: `class Open<R extends Number>` does not mean `R` is `Number`. An instance of `Open<Long>` is valid, so `R` should only be replaced by `Long` when an actual subclass or inheritance path supplies that argument.

### Raw types erase information

```java
class Box<T> {}
class Raw extends Box {} // Raw type, does not provide a concrete T.
```

This is an illustrative snippet. `Raw.class.getGenericSuperclass()` may be a raw `Class<?>` rather than a `ParameterizedType`; there is no data to conclude whether `T` is `String` or `Integer`. In a strict framework, **report unresolved or reject it**, rather than guessing `Object` as the concrete argument simply because of type erasure or the default `Object` bound.

### Runtime objects cannot recover arbitrary `List<String>`

`new ArrayList<String>().getClass()` only yields the runtime class `ArrayList`; the expression `new ArrayList<String>()` does not create a subclass carrying `String` in `ArrayList`'s `generic superclass`. Reflection can resolve arguments from **parent type declarations** on a subclass whose signature is recorded in the class file; it cannot read arbitrary type arguments from an ordinary object.

Another way to carry generic info is an **anonymous subclass / type token**, such as `new TypeReference<List<String>>() {}`, where the superclass is parameterized in the class file. Type tokens are a separate technique, not evidence that every object retains generics at runtime.

## 7. Interfaces, Owner Types, and Areas to Extend

Java allows a class to **extend one superclass** yet **implement multiple interfaces**. If your goal is generics declared by an interface, you must expand to `Class.getGenericInterfaces()` and traverse the interface/superclass graph.

Example:

```java
interface Handler<E> {}
interface NamedHandler<X> extends Handler<java.util.List<X>> {}
class NamedStringHandler implements NamedHandler<String> {}
```

To resolve `Handler.E` in the context of `NamedStringHandler`, you must traverse interface edges:

```text
NamedStringHandler
  -> NamedHandler<String>
  -> Handler<List<X>>
  -> Handler.E = List<String>
```

You **cannot** use only `getGenericSuperclass()` to discover these edges. In a general resolver, each traversal branch should carry its **own binding environment**; avoid using a single global map that mixes distinct paths. Avoid revisiting nodes, check `target.isAssignableFrom(candidate)` appropriately, and resolve inheritance paths down to the exact declaration.

Additionally, a non-static member class can use type variables from its enclosing class via **owner type** (`ParameterizedType.getOwnerType()`). If the description must be complete, resolve the owner as well and format nested class names accurately. The runnable example in Section 4 **does not claim to support this case**.

A `ParameterizedType`/`TypeVariable` returned from metadata can also lead to `TypeNotPresentException` or `MalformedParameterizedTypeException` if the signature references a missing type or malformed metadata. Production libraries should handle these explicitly, logging the class/module/loader being analyzed for diagnosis.

## 8. Common Mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Using only `getSuperclass()` | Loses type arguments of the parent edge | Use `getGenericSuperclass()` |
| Inspecting only one level | Gets `List<U>` instead of `List<String>` | Follow the variable substitution map down to the leaf class |
| Keying variables by string name | Two classes can both declare `T` | Key by `TypeVariable<?>` |
| Casting every `Type` to `ParameterizedType` | Raw parents, concrete types, wildcards, and arrays are not that type | Check `instanceof` per branch |
| Substituting `TypeVariable` only at the top level | `List<U>`/`Map<?,U>` still retain inner variables | Recursively walk `ParameterizedType`, wildcards, and arrays |
| Using `getBounds()` as the concrete type of an unbound variable | A bound is not an actual argument | Preserve unresolved state |
| Assuming raw types mean exact `Object` | No actual type argument information exists | Report missing info; decide fallback per contract |
| Mixing superclasses and interfaces without walking interfaces | Misses paths to generic interfaces | Walk `getGenericInterfaces()` with per-branch environments |
| Assuming `new List<String>()`-style objects retain type arguments | Type erasure prevents inferring from ordinary objects | Rely on declared signatures or type tokens |
| Ignoring class loaders | Identical class names from two loaders are not necessarily the same type | Compare actual `Class<?>`/`Type` instances and record loader context when debugging |

## 9. Practice Exercises

**Exercise 1.** `class A<T> {}`; `class B<U> extends A<U[]> {}`; `class C extends B<Long> {}`. Resolve `A.T` in the context of `C`.

**Answer:** `java.lang.Long[]`. Variable `U` of `B` is fixed to `Long`, so `U[]` becomes `Long[]`.

**Exercise 2.** `class A<T> {}`; `class B<T> extends A<List<T>> {}`; `class C extends B<String> {}`. Is it safe to use `Map<String,Type>` keyed by `"T"`?

**Answer:** Unsafe. `A.T` and `B.T` are distinct despite having the same name. Use `TypeVariable<?>` as the key.

**Exercise 3.** `class A<T extends Number> {}`; `class B<U extends Number> extends A<U> {}`. Does `A.T` automatically resolve to `Number`?

**Answer:** No. `B` has not fixed `U`; the result remains the variable `U` with bound `Number`.

**Exercise 4.** Can a class implementing `interface Handler<T>` through a chain of intermediate interfaces be resolved using only `getGenericSuperclass()`?

**Answer:** No. You must traverse `getGenericInterfaces()` and map variables along the interface edges.

**Exercise 5.** After resolving `List<? extends U>` with `U=Integer`, can you drop the wildcard and treat it as `List<Integer>`?

**Answer:** No. `List<? extends Integer>` and `List<Integer>` are not the same generic type; the resolver must preserve the wildcard.

**Key takeaway:** To resolve generics across multiple levels, follow the **right inheritance path**, build a **declaration-scoped TypeVariable → Type argument** map, and recursively substitute **nested types, generic arrays, and wildcards**. Conclude a concrete type only when the declaration chain genuinely provides sufficient information.

Java 17 API References: [`Class.getGenericSuperclass()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html).