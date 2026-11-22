# Mapping `TypeVariable` to Concrete Types Across Multiple Inheritance Levels

## 1. The problem: a field is declared with type `T`, but the subclass chose `String`

In Java, generic inheritance can pass type parameters across multiple levels. Consider the chain:

~~~java
class Base<T> {
    T item;
}
class Middle<U> extends Base<List<U>> {
}
class Leaf extends Middle<String> {
}
~~~

When looking at `Base.class`, the field `item` has generic type **`T`**; there is no `String` in `Base`'s declaration. However, when looking from `Leaf`, we trace:

~~~text
Leaf extends Middle<String>
     U = String

Middle<U> extends Base<List<U>>
     T = List<U>

Substituting U = String into T = List<U>:
     T = List<String>

Base<T>.item, viewed from Leaf:
     List<String>
~~~

**This is type resolution in the context of the subclass**, not modifying the original metadata of `Base`. `Base.class.getDeclaredField("item").getGenericType()` still returns a `TypeVariable` representing `T`; Reflection has no single-step API that automatically turns every `T` into `List<String>` for an arbitrary subclass. You must read the generic superclass/interfaces, build a type variable mapping, and apply substitutions step by step.

Frameworks such as serializers, ORMs, dependency injection containers, or type-aware API generators often need to solve this problem: the same generic base class can be specialized into many concrete types depending on the actual subclass.

## 2. `Type` representations to understand

`java.lang.reflect.Type` is the interface representing reflective type information. Important representations:

| `Type` kind | Example | What Reflection provides |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class`, `int.class` | Concrete type or raw type |
| `TypeVariable<?>` | `T` in `Base<T>`, `U` in `Middle<U>` | Type parameter declared by a class/method/constructor |
| `ParameterizedType` | `Base<List<U>>`, `List<String>` | Raw type along with the list of actual type arguments |
| `WildcardType` | `? extends T`, `? super Number` | Upper/lower bounds of a wildcard |
| `GenericArrayType` | `T[]` or `List<T>[]` | Generic component type when the component is not yet an ordinary class type |

A `TypeVariable` has **declaration identity**, not just a name. Two classes can both declare a type parameter named `T`, yet they are **two distinct type variables**. When building a mapping table, the key should be `TypeVariable<?>`, such as `Map<TypeVariable<?>, Type>`, instead of `Map<String, Type>`; mapping solely by the string `"T"` can accidentally overwrite a variable from a different declaration.

A `TypeVariable` can have bounds:

~~~java
class Store<T extends Number> {
    T amount;
}
~~~

`T` is still a type variable. `T.getBounds()` reflects the bound `Number`; it does **not** mean every instance of `Store` uses `Number` itself. For example, `Store<Integer>` binds `T` to `Integer` in the context of that subclass. Do not use the bound as a concrete result when no mapping exists.

## 3. Reflection APIs connecting inheritance links

A class `Leaf extends Middle<String>` holds key data in `Leaf.class.getGenericSuperclass()`:

- If the superclass has type arguments, the result is usually a `ParameterizedType`. `getRawType()` points to `Middle.class`, and `getActualTypeArguments()` contains `String.class`.
- `Middle.class.getTypeParameters()` returns the list of type variables of `Middle`, here `U`. Pair each formal type variable with its actual type argument by **position**: `U → String`.
- Next, `Middle.class.getGenericSuperclass()` represents `Base<List<U>>`. `Base.class.getTypeParameters()` returns `T`, and the actual argument is `List<U>`: record `T → List<U>`.
- Apply the mapping recursively: `T → List<U> → List<String>`.

| Step on the path from the concrete class | Formal parameter of parent declaration | Actual argument on the inheritance edge |
| --- | --- | --- |
| `Leaf → Middle<String>` | `Middle.U` | `String` |
| `Middle<U> → Base<List<U>>` | `Base.T` | `List<U>` |
| Resolving `Base.T` in the context of `Leaf` | `Base.T` | `List<String>` |

You must obtain the inheritance edge from **`getGenericSuperclass()`**, not plain `getSuperclass()`. The `getSuperclass()` API only returns the raw `Class` and loses the `String` or `List<U>` argument information on that edge.

Similarly, for generic interfaces, you must use `getGenericInterfaces()` together with `ParameterizedType` to retrieve arguments. However, interfaces can form a multi-branch graph rather than a single superclass chain; an algorithm is needed to traverse interface edges and identify the declaration being resolved.

## 4. Runnable Java 17+ example: mapping and resolving nested generics

Create the file `GenericTypeResolverDemo.java`:

~~~java
import java.lang.reflect.*;
import java.util.*;

public class GenericTypeResolverDemo {
    static class Base<T> {
        T item;
        List<T> history;
        List<? extends T> readable;
    }

    static class Middle<U> extends Base<List<U>> {
    }

    static class Leaf extends Middle<String> {
    }

    static Map<TypeVariable<?>, Type> bindings(
            Class<?> concrete, Class<?> declaringClass) {
        Map<TypeVariable<?>, Type> result = new LinkedHashMap<>();

        if (!declaringClass.isAssignableFrom(concrete)) {
            throw new IllegalArgumentException("Not an ancestor");
        }

        Class<?> current = concrete;
        while (current != declaringClass) {
            Type parent = current.getGenericSuperclass();
            if (parent == null) {
                throw new IllegalArgumentException("No superclass path");
            }

            if (parent instanceof ParameterizedType p) {
                Class<?> raw = (Class<?>) p.getRawType();
                TypeVariable<?>[] formals = raw.getTypeParameters();
                Type[] actuals = p.getActualTypeArguments();

                for (int i = 0; i < formals.length; i++) {
                    result.put(formals[i], actuals[i]);
                }
                current = raw;
            } else {
                // An extends edge without generic arguments.
                current = (Class<?>) parent;
            }
        }
        return result;
    }

    // Display the type after variable substitution. This is an example for the superclass path.
    static String render(
            Type type, Map<TypeVariable<?>, Type> bindings) {
        if (type instanceof TypeVariable<?> variable) {
            Type replacement = bindings.get(variable);
            if (replacement == null || replacement.equals(variable)) {
                return variable.getName();
            }
            return render(replacement, bindings);
        }

        if (type instanceof ParameterizedType p) {
            List<String> parts = new ArrayList<>();
            for (Type argument : p.getActualTypeArguments()) {
                parts.add(render(argument, bindings));
            }
            return render(p.getRawType(), bindings)
                    + "<" + String.join(", ", parts) + ">";
        }

        if (type instanceof WildcardType w) {
            if (w.getLowerBounds().length > 0) {
                return "? super "
                        + render(w.getLowerBounds()[0], bindings);
            }
            Type upper = w.getUpperBounds()[0];
            return upper == Object.class
                    ? "?"
                    : "? extends " + render(upper, bindings);
        }

        if (type instanceof GenericArrayType a) {
            return render(a.getGenericComponentType(), bindings) + "[]";
        }

        if (type instanceof Class<?> c) {
            return c.isArray()
                    ? render(c.getComponentType(), bindings) + "[]"
                    : c.getSimpleName();
        }

        return type.getTypeName();
    }

    public static void main(String[] args) throws Exception {
        Map<TypeVariable<?>, Type> map =
                bindings(Leaf.class, Base.class);

        for (TypeVariable<?> variable : Middle.class.getTypeParameters()) {
            System.out.println(variable.getName() + " -> "
                    + render(variable, map));
        }
        for (TypeVariable<?> variable : Base.class.getTypeParameters()) {
            System.out.println(variable.getName() + " -> "
                    + render(variable, map));
        }

        for (String name : List.of("item", "history", "readable")) {
            Field field = Base.class.getDeclaredField(name);
            System.out.println(name
                    + ": raw=" + field.getType().getSimpleName()
                    + ", generic=" + field.getGenericType().getTypeName()
                    + ", resolved=" + render(field.getGenericType(), map));
        }
    }
}
~~~

Compile and run commands:

~~~bash
javac --release 17 GenericTypeResolverDemo.java
java GenericTypeResolverDemo
~~~

Output:

~~~text
U -> String
T -> List<String>
item: raw=Object, generic=T, resolved=List<String>
history: raw=List, generic=java.util.List<T>, resolved=List<List<String>>
readable: raw=List, generic=java.util.List<? extends T>, resolved=List<? extends List<String>>
~~~

The output was verified using an equivalent snippet in JShell: compiling/providing Java 17 type metadata and running on JDK 24 produces these exact lines.

### Analysis of each field

- `item` of `Base<T>`: `Field.getType()` returns `Object.class` because the erasure of an unbounded `T` is `Object`; `getGenericType()` is still `TypeVariable T`. In the context of `Leaf`, `T` resolves to `List<String>`.
- `history`: declared as `List<T>`. When `T → List<String>`, the entire expression becomes `List<List<String>>`. Type variable substitution must **recurse inside the arguments** of `ParameterizedType`.
- `readable`: declared as `List<? extends T>`. The result is `List<? extends List<String>>`. Do not drop the wildcard during resolution; `? extends` still carries the API's variance meaning.
- `U` of `Middle<U>` maps to `String`, so `T` of `Base<T>` can be further resolved through `List<U>`.

In the example, `render` returns a string to **explain the result**, without reconstructing a new `Type` object. If a framework actually needs a `ParameterizedType` object with substituted type arguments, it must create an immutable representation conforming to the `ParameterizedType` contract (or use a proven type-resolution library) and handle `ownerType`, `WildcardType`, `GenericArrayType`, and equality/hashCode.

## 5. Why must the mapping table walk from the concrete class up to the declaring class?

You start where **concrete arguments are known**, such as `Leaf extends Middle<String>`. If you only inspect `Middle.class` and `Base.class` independently, nothing guarantees `U` is `String`; they only know the relationship `T = List<U>`.

General procedure for a superclass path:

1. Take `Class<?> concrete` as the actual class and `Class<?> declaring` as the class declaring the field/method to resolve.
2. Determine the route `concrete → ... → declaring` via `getGenericSuperclass()`.
3. On each edge `Subclass extends Parent<...>`, match `Parent.getTypeParameters()` with `ParameterizedType.getActualTypeArguments()` to record `TypeVariable → Type` mappings.
4. When encountering a type variable in a field, method, or constructor, look up its binding by the `TypeVariable<?>` object itself and substitute recursively until no more mappings apply.
5. When encountering a `ParameterizedType`, substitute **every argument**; for wildcards and generic arrays, traverse their bounds/component types structurally.
6. If an unresolved type variable remains, keep it in an **unresolved** state or explicitly represent it as unknown; do not default to `Object` or its upper bound as a concrete type.

In the example, the map intentionally stores `T → List<U>` rather than insisting on eagerly turning it into `List<String>` at insertion time. When `render(T, map)` is called, it follows `T → List<U>` and looks up `U → String` to produce the final result.

For a generic field declared in a superclass, do not call `leaf.getDeclaredField("item")`: `getDeclaredField` only searches fields declared directly on `Leaf`. Look up `Base.class.getDeclaredField("item")` or inspect a found field via `field.getDeclaringClass()`; then use the concrete class as the resolution context.

## 6. Generic methods and method-owned type variables

`Method.getGenericReturnType()` and `Method.getGenericParameterTypes()` can also contain `TypeVariable`s. Distinguish two sources:

~~~java
class Container<T> {
    T find() {
        return null;
    }

    <R> R convert(R value) {
        return value;
    }
}
~~~

- `T` belongs to the **class** declaration `Container<T>`. With `StringContainer extends Container<String>`, the generic superclass mapping allows inferring the return type of `find()` as `String` in that context.
- `R` belongs to the **method** declaration `convert`, not a type variable of `Container`. Knowing only a subclass of `Container<String>` is **not** enough to infer what `R` is; determining `R` requires additional method invocation context or corresponding type inference.

You can call `TypeVariable.getGenericDeclaration()` to check whether a type variable is declared by a `Class`, `Method`, or `Constructor`. This prevents confusing a method's `T` with a class's `T`, even when they share the same name.

**Type erasure:** generic metadata allows analyzing type constraints, but the JVM does not make a `new ArrayList<String>()` object have a distinct runtime class from `new ArrayList<Integer>()`. `obj.getClass()` only yields `ArrayList.class`. If code needs to know `String`, a reliable source must come from a declared generic superclass/interface, a captured `Type`, an annotation, or an appropriate type token; it cannot always be recovered from a runtime object.

## 7. Extending to generic interfaces

Example:

~~~java
interface Handler<T> {
    void handle(T value);
}

interface NamedHandler<U> extends Handler<List<U>> {
}

class StringHandler implements NamedHandler<String> {
    @Override
    public void handle(List<String> value) {
    }
}
~~~

The relationship to resolve is:

~~~text
StringHandler -> NamedHandler<String>
NamedHandler<U> -> Handler<List<U>>

U = String
Handler.T = List<U> = List<String>
~~~

Each **interface** link is obtained via `Class.getGenericInterfaces()`; the raw interface `Handler.class` has type parameter `T`, while the generic edge provides the actual type arguments. Walking upward from `StringHandler.class` may encounter multiple interfaces, superclasses implementing interfaces, and nested generic interfaces: thus the algorithm must traverse the **interface + superclass graph**, locate the target declaration, and accumulate mappings along each valid path.

The declarations above are a theoretical example; the `bindings` code in section 4 **only supports a single superclass chain**, so it must not be applied directly to `StringHandler → Handler` and falsely conclude there is no path. A framework-grade implementation should add `getGenericInterfaces()` traversal and handle repeated interfaces in the graph.

## 8. Cases where a simple mapping is insufficient

### A. Raw types lose arguments

~~~java
class RawMiddle extends Base { }
class RawLeaf extends RawMiddle { }
~~~

When choosing `extends Base` without type arguments, the generic edge provides no `T → SomeType`. A strict algorithm must recognize metadata loss caused by raw types. It **cannot infer** a concrete `String` from erased information; `T` may remain unresolved, even though runtime erasure corresponds to `T`'s bound.

### B. Bounded variables and wildcards

~~~java
class NumberBase<T extends Number> {
    List<? super T> consumer;
}
class IntegerBase extends NumberBase<Integer> {
}
~~~

From `IntegerBase`, the mapping is `T → Integer`; the field's type becomes `List<? super Integer>`. **Do not turn** it into `List<Integer>` because the wildcard `? super` is not identical to the concrete argument `Integer`. Wildcard upper/lower bounds are metadata to preserve, just like type variable bounds when still unresolved.

### C. Generic arrays

~~~java
class ArrayBase<T> {
    T[] values;
}
class ArrayChild extends ArrayBase<String> {
}
~~~

`ArrayBase.values` has a `GenericArrayType` corresponding to `T[]`; from `ArrayChild`, it can be interpreted at the type level as `String[]`. However, a solution rendered as a string is only for human reading. If you need to construct a `Type` usable by a framework, distinguish a reifiable array `Class<?>`, a `GenericArrayType`, and the runtime capability to safely allocate arrays.

### D. Nested/owner types

For example, `Outer<String>.Inner<Integer>` has an `ownerType` and actual type arguments. Simply taking `getRawType()` + `getActualTypeArguments()` and concatenating them as a string is insufficient to represent all nested type semantics. A real resolver must account for `ParameterizedType.getOwnerType()`, especially for non-static inner classes.

### E. Cyclic bounds and unbound variables

`class Node<T extends Comparable<T>>` contains a self-referential relationship in its **bound**. A complete resolver must not infinitely recurse when analyzing bounds or aliases. It should maintain a `visited` set / mark the resolution context and return an unresolved/cyclic state when necessary. The `render` function in the example only resolves linear mappings, not a general parser/renderer for all Java types.

### F. Class loaders and identical variable names

A `TypeVariable` is tied to its exact declaration. If multiple libraries or class loaders provide classes with the same simple name, string-based mapping like `"T"` or `"U"` easily breaks. Use `TypeVariable<?>` objects and their declaring sources; for logging/debugging, print the full `getGenericDeclaration()` when disambiguation is needed.

## 9. Distinguishing `getType()`, `getGenericType()`, and the resolved type

| Question | API/action | On field `Base.item` in the example |
| --- | --- | --- |
| What field type does the JVM see after erasure? | `Field.getType()` | `Object.class` |
| What does the original generic declaration in Base state? | `Field.getGenericType()` | `TypeVariable T` |
| In the context of Leaf, how is T bound? | Traverse `getGenericSuperclass()` and substitute type variables | `List<String>` |
| Does `obj.getClass()` reveal the `String` type argument? | Runtime class of the object | Insufficient to recover arbitrary generic arguments |

`getType()` is not wrong to return `Object.class`: the JVM uses type erasure for descriptors. `getGenericType()` retains declaration information so Reflection can reconstruct *part* of the generic relationships. Full resolution requires the concrete context of the subclass and the type argument edges.

For method parameters, the corresponding APIs are `getParameterTypes()` and `getGenericParameterTypes()`. For method return types, use `getReturnType()` and `getGenericReturnType()`. Returning the original generic type does not mean subclass bindings have been automatically applied.

## 10. Common mistakes and how to fix them

| Common mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Calling `Base.class.getDeclaredField("item").getType()` and concluding the field is Object in all contexts | That is only the erased type | Combine `getGenericType()` with bindings from the concrete subclass |
| Calling `getSuperclass()` to walk generic inheritance | Loses actual type arguments | Use `getGenericSuperclass()` |
| Taking `getGenericSuperclass()` of `Base` without considering `Leaf` | `Base` does not yet know concrete arguments | Start from the concrete class with concrete generic links |
| Substituting `T` only at the direct level, without substituting `U` inside `List<U>` | Substitution is not recursive | Follow the mapping chain all the way to `List<String>` |
| Mapping type variables by name `"T"` | Different declarations can reuse the same name | Use `Map<TypeVariable<?>, Type>` |
| Dropping `? extends`/`? super` when substituting types | Loses variance and bounds | Resolve inside the wildcard, preserving wildcard structure |
| Treating `T extends Number` as `T = Number` | A bound is a constraint, not an actual argument | Leave `T` unresolved if no binding exists |
| Using a superclass-only algorithm for generic interface paths | Interfaces form a graph | Also traverse `getGenericInterfaces()` |
| Using `new ArrayList<String>().getClass()` to infer String | Type erasure | Need generic metadata on a declaration or a type token |
| Fabricating a `ParameterizedType` solely as a string | A string does not satisfy the Type contract, equality, owner, or arrays | Build a full Type structure or use a proven library |

## 11. Self-check

**Question 1:** `class A<T>`, `class B<U> extends A<List<U>>`, `class C extends B<Integer>`. In `C`, what is `A.T`? **`List<Integer>`**.

**Question 2:** Does `Field.getGenericType()` on `A.class` return `T` or `List<Integer>`? **`T`**, because that is the metadata of `A`'s declaration; resolution is substitution in the context of `C`.

**Question 3:** Why can using `TypeVariable.getName()` as a key fail? **Because two different declarations can both name their variable `T`**.

**Question 4:** Given `List<? extends T>` and `T → String`, what is the resolved type? **`List<? extends String>`**, not automatically `List<String>`.

**Question 5:** If `class B extends A` uses a raw type, can you be sure `A.T` is `String`? **No**, because that edge supplies no concrete type argument.

**Question 6:** With `interface I<T>`, can an implementing class always resolve `T` via `getGenericSuperclass()` alone? **Not always**; you must inspect interface edges from `getGenericInterfaces()` and possibly multiple branches.

**Question 7:** A generic method `<R> R convert(R value)` is inside `A<T>`. Does binding `A.T → String` automatically make `R → String`? **No**; `R` belongs to the method declaration and requires its own inference context.

**Remember:** To map `TypeVariable`s across multiple inheritance levels, you must preserve the **exact declaration of each variable**, read **generic edges** from the concrete class back to the declaring site, and **substitute recursively** inside nested parameterized types, wildcards, and arrays. When metadata is insufficient (raw types, erasure, unbound method variables), represent the result as unresolved rather than guessing a concrete type.
