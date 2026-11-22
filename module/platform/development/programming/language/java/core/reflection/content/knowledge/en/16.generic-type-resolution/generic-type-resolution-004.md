# Substituting Nested Types in ParameterizedType with Java Reflection

When Reflection reads a generic declaration, the result often still contains type variables such as `T`, `U`, `V`, even when analyzing a subclass that has bound them to concrete types. For example, a field `Map<T, List<U[]>>` of a nested class may need to be interpreted in context as `Map<String, List<Integer[]>>`. This is the **generic type substitution** problem: trace inheritance relationships and enclosing owner classes, build a mapping from `TypeVariable` to `Type`, and then substitute **recursively** throughout the `Type` tree.

The hardest part is not merely replacing `T` appearing in the first element of a `ParameterizedType`. You must descend into every `getActualTypeArguments()`, handle `GenericArrayType`, `WildcardType`, multi-step mappings, and `getOwnerType()` of nested types such as `Outer<String>.Inner<Integer>`. The lesson below distinguishes **reading metadata**, **building the generic context**, and **constructing the substituted `Type` structure**.

## 1. Components that make up the `Type` tree

`java.lang.reflect.Type` is the root interface for generic type representations in Reflection:

| `Type` variant | Example | APIs used to descend |
| --- | --- | --- |
| `Class<?>` | `String.class`, `int.class`, `String[].class` | `getComponentType()` if it is an array |
| `ParameterizedType` | `List<T>`, `Map<String, List<U[]>>`, `Outer<T>.Inner<U>` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `TypeVariable<?>` | `T`, `U`, `V` | `getGenericDeclaration()`, `getName()`, `getBounds()` |
| `WildcardType` | `? extends U`, `? super T` | `getUpperBounds()`, `getLowerBounds()` |
| `GenericArrayType` | `U[]`, `List<T>[]` in a generic declaration | `getGenericComponentType()` |

For a field declared as `Map<T, List<U[]>>`, `field.getType()` is only `Map.class` due to *type erasure*. However, `field.getGenericType()` returns a `ParameterizedType` tree containing `T` and a child `ParameterizedType` `List<U[]>`. The `U[]` part is described by a `GenericArrayType`, because the component `U` is not yet a reifiable type.

It is easy to visualize the structure before substitution:

~~~text
ParameterizedType: Map<T, List<U[]>>
├── rawType: Map.class
├── arg[0]: TypeVariable T
└── arg[1]: ParameterizedType List<U[]>
    └── arg[0]: GenericArrayType
        └── component: TypeVariable U
~~~

The context `T → String`, `U → Integer` transforms it into:

~~~text
ParameterizedType: Map<String, List<Integer[]>>
├── rawType: Map.class
├── arg[0]: Class String
└── arg[1]: ParameterizedType List<Integer[]>
    └── arg[0]: Class Integer[] 
~~~

`Integer[]` is now a `Class` representing a real array because `Integer` is a concrete type. **Do not skip nested levels**: replacing only `arg[0]` at the Map level without descending into `List<U[]>` leaves `U` unresolved.

## 2. Why can't type variables be substituted by name alone?

Suppose two different declarations both use the name `T`:

~~~java
class First<T> {}
class Second<T> {}
~~~

The two type variables here **do not share the same identity**. Each `TypeVariable` is tied to the exact `GenericDeclaration` that declared it. A generic method `<T> void doWork(T value)` can also have a `T` distinct from the class's `T`.

Therefore, you should use:

~~~java
Map<TypeVariable<?>, Type> bindings = new HashMap<>();
~~~

instead of `Map<String, Type>` keyed by names like `"T"`. Use `getTypeParameters()` from the exact raw class for the keys; use `getActualTypeArguments()` from the corresponding `ParameterizedType` for the values.

**Do not use `getSimpleName()`, `getTypeName()`, or regex string replacement** as a type resolution mechanism. Those APIs are for name formatting; they do not preserve the full identity of `TypeVariable`, raw types, owner types, arrays, and wildcards.

## 3. Nested types with two parameter levels: owner and inner itself

Example:

~~~java
class Outer<T> {
    class Slot<U> {
        Map<T, List<U[]>> table;
    }
}
~~~

In a specific usage `Outer<String>.Slot<Integer>`:

- `T` belongs to the declaration `Outer<T>`, receiving `String`.
- `U` belongs to the declaration `Outer<T>.Slot<U>`, receiving `Integer`.
- The `ParameterizedType` representing **Slot** has `getRawType() == Outer.Slot.class`.
- `getActualTypeArguments()` of **Slot** contains only `Integer` (variable `U`).
- **The argument `String` for `T` resides in `getOwnerType()`** — it is not merged as two elements into Slot's argument array.

This is a fundamental mistake when handling nested types: traversing only `getActualTypeArguments()` while ignoring `getOwnerType()` will miss the `Outer.T → String` mapping.

**Note:** `static` nested types do not hold an instance of the outer class the way non-static inner classes do. The owner metadata of a `ParameterizedType` may still represent the enclosing type, but you must not infer from it that a static nested class uses the outer's generic parameters; a static nested type cannot reference type variables of an outer instance like a non-static inner class can.

## 4. Resolving across multiple inheritance levels

Consider the declaration chain:

~~~java
class Outer<T> {
    class Slot<U> {}
}

class Middle<V> extends Outer<V>.Slot<Integer> {
    Middle(Outer<V> owner) {
        owner.super();
    }
}

class End extends Middle<String> {
    End() {
        super(new Outer<String>());
    }
}
~~~

**Illustrative code example**, showing the type relationships. Note that `owner.super()` is the syntax for calling the constructor of a non-`static` inner class from a subclass.

Key metadata:

| Read step | Declared `Type` | Collected mappings |
| --- | --- | --- |
| `End.class.getGenericSuperclass()` | `Middle<String>` | `Middle.V → String` |
| `Middle.class.getGenericSuperclass()` | `Outer<V>.Slot<Integer>` | `Outer.T → Middle.V`, `Slot.U → Integer` |
| Transitive substitution | `Outer.T → V → String` | `Outer.T → String`, `Slot.U → Integer` |

You must not stop at the mapping `T → V`; you must continue looking up `V` in the context. Because `getGenericSuperclass()` on `Middle.class` describes **Middle's declaration**, it still contains `V` and does not automatically become `String` just because the caller started from `End.class`.

The general procedure for a class inheritance chain: start at the concrete target type; traverse each `getGenericSuperclass()` upward; for each `ParameterizedType`, collect type variable mappings for the **raw type** and also the **owner** if present; then recursively substitute variables when reading generic fields/methods on the original declaring class.

If the inheritance path involves **generic interfaces**, you must also read `getGenericInterfaces()` at the relevant nodes. Data or library classes can have multiple interface paths; you must track relationships along each branch and detect when information is not completely supplied.

## 5. Structurally sound recursive substitution algorithm

Given `resolve(type, bindings)`:

1. If `type` is a `TypeVariable`, look it up by `TypeVariable` key and **continue resolving** the mapped type. If no mapping exists, keep the `TypeVariable`. Guard against mapping cycles to avoid infinite recursion.
2. If it is a `ParameterizedType`, **resolve the owner**, then resolve **every actual type argument** in exact order, keeping `rawType` unchanged; construct a new `ParameterizedType` preserving the structure.
3. If it is a `GenericArrayType`, resolve the component. When the component is a concrete `Class<?>`, it can be represented as an array `Class` (such as `Integer[].class`); if it still has a generic component, keep the `GenericArrayType` form.
4. If it is a `WildcardType`, resolve both `getUpperBounds()` and `getLowerBounds()` without stripping `? extends` or `? super`.
5. For an ordinary `Class<?>`, keep it as-is. A `Class<?>[]` or `String[].class` is already a real runtime type and contains no `TypeVariable` to substitute.

To **return an actual `Type`**, you cannot mutate the `ParameterizedType` object provided by Reflection in place; you must construct other objects implementing `ParameterizedType`, `GenericArrayType`, and `WildcardType` as needed. Implementations should be immutable, have `equals`/`hashCode` consistent with the interface contracts, and return defensive array copies. Below is a small educational implementation based on Java 17 records.

## 6. Complete Java 17+ program: substituting owner, nested arguments, arrays, and wildcards

Create the file **`NestedTypeSubstitutionDemo.java`**:

~~~java
import java.lang.reflect.*;
import java.util.*;

class Outer<T> {
    class Slot<U> {
        Map<T, List<U[]>> table;
        List<? extends U> upper;
    }
}

class Middle<V> extends Outer<V>.Slot<Integer> {
    Middle(Outer<V> outer) {
        outer.super();
    }
}

class End extends Middle<String> {
    End() {
        super(new Outer<String>());
    }
}

public class NestedTypeSubstitutionDemo {
    record P(Type owner, Type raw, List<Type> args)
            implements ParameterizedType {
        P { args = List.copyOf(args); }
        public Type getOwnerType() { return owner; }
        public Type getRawType() { return raw; }
        public Type[] getActualTypeArguments() {
            return args.toArray(Type[]::new);
        }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof ParameterizedType p
                    && Objects.equals(owner, p.getOwnerType())
                    && Objects.equals(raw, p.getRawType())
                    && Arrays.equals(getActualTypeArguments(),
                                     p.getActualTypeArguments());
        }
        @Override public int hashCode() {
            return Arrays.hashCode(getActualTypeArguments())
                    ^ Objects.hashCode(owner) ^ Objects.hashCode(raw);
        }
    }

    record A(Type component) implements GenericArrayType {
        public Type getGenericComponentType() { return component; }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof GenericArrayType a
                    && component.equals(a.getGenericComponentType());
        }
        @Override public int hashCode() { return component.hashCode(); }
    }

    record W(List<Type> upper, List<Type> lower)
            implements WildcardType {
        W {
            upper = List.copyOf(upper);
            lower = List.copyOf(lower);
        }
        public Type[] getUpperBounds() {
            return upper.toArray(Type[]::new);
        }
        public Type[] getLowerBounds() {
            return lower.toArray(Type[]::new);
        }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof WildcardType w
                    && Arrays.equals(getUpperBounds(), w.getUpperBounds())
                    && Arrays.equals(getLowerBounds(), w.getLowerBounds());
        }
        @Override public int hashCode() {
            return Arrays.hashCode(getUpperBounds())
                    ^ Arrays.hashCode(getLowerBounds());
        }
    }

    static void bind(Type type, Map<TypeVariable<?>, Type> env) {
        if (!(type instanceof ParameterizedType p)) {
            return;
        }
        bind(p.getOwnerType(), env);
        TypeVariable<?>[] keys =
                ((Class<?>) p.getRawType()).getTypeParameters();
        Type[] values = p.getActualTypeArguments();
        for (int i = 0; i < keys.length; i++) {
            env.put(keys[i], values[i]);
        }
    }

    static Type substitute(Type type, Map<TypeVariable<?>, Type> env) {
        return substitute(type, env, new HashSet<>());
    }

    private static Type substitute(Type type,
            Map<TypeVariable<?>, Type> env,
            Set<TypeVariable<?>> visiting) {
        if (type instanceof TypeVariable<?> v) {
            Type replacement = env.get(v);
            if (replacement == null || replacement.equals(v)
                    || !visiting.add(v)) {
                return v;
            }
            try {
                return substitute(replacement, env, visiting);
            } finally {
                visiting.remove(v);
            }
        }
        if (type instanceof ParameterizedType p) {
            Type owner = p.getOwnerType() == null ? null
                    : substitute(p.getOwnerType(), env, visiting);
            List<Type> args = new ArrayList<>();
            for (Type arg : p.getActualTypeArguments()) {
                args.add(substitute(arg, env, visiting));
            }
            return new P(owner, p.getRawType(), args);
        }
        if (type instanceof GenericArrayType a) {
            Type child = substitute(
                    a.getGenericComponentType(), env, visiting);
            if (child instanceof Class<?> c) {
                return java.lang.reflect.Array.newInstance(c, 0)
                        .getClass();
            }
            return new A(child);
        }
        if (type instanceof WildcardType w) {
            List<Type> upper = new ArrayList<>();
            List<Type> lower = new ArrayList<>();
            for (Type t : w.getUpperBounds()) {
                upper.add(substitute(t, env, visiting));
            }
            for (Type t : w.getLowerBounds()) {
                lower.add(substitute(t, env, visiting));
            }
            return new W(upper, lower);
        }
        return type;
    }

    static String describe(Type t) {
        if (t instanceof ParameterizedType p) {
            Class<?> raw = (Class<?>) p.getRawType();
            String base = p.getOwnerType() == null
                    ? raw.getSimpleName()
                    : describe(p.getOwnerType()) + "."
                            + raw.getSimpleName();
            Type[] args = p.getActualTypeArguments();
            if (args.length == 0) return base;
            List<String> parts = new ArrayList<>();
            for (Type arg : args) parts.add(describe(arg));
            return base + "<" + String.join(", ", parts) + ">";
        }
        if (t instanceof GenericArrayType a) {
            return describe(a.getGenericComponentType()) + "[]";
        }
        if (t instanceof WildcardType w) {
            Type[] lower = w.getLowerBounds();
            if (lower.length > 0) {
                return "? super " + describe(lower[0]);
            }
            Type[] upper = w.getUpperBounds();
            if (upper.length == 0 || (upper.length == 1
                    && upper[0] == Object.class)) return "?";
            return "? extends " + describe(upper[0]);
        }
        if (t instanceof TypeVariable<?> v) return v.getName();
        if (t instanceof Class<?> c) {
            return c.isArray()
                    ? describe(c.getComponentType()) + "[]"
                    : c.getSimpleName();
        }
        return t.getTypeName();
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Map<TypeVariable<?>, Type> env = new LinkedHashMap<>();

        Type endParent = End.class.getGenericSuperclass();
        bind(endParent, env); // V -> String
        Type middleParent = Middle.class.getGenericSuperclass();
        bind(middleParent, env); // T -> V, U -> Integer

        System.out.println("T -> " + describe(substitute(
                Outer.class.getTypeParameters()[0], env)));
        System.out.println("U -> " + describe(substitute(
                Outer.Slot.class.getTypeParameters()[0], env)));
        System.out.println("V -> " + describe(substitute(
                Middle.class.getTypeParameters()[0], env)));

        ParameterizedType nested = (ParameterizedType) middleParent;
        System.out.println("Owner: " + describe(
                substitute(nested.getOwnerType(), env)));
        System.out.println("Nested: " + describe(
                substitute(middleParent, env)));

        Field table = Outer.Slot.class.getDeclaredField("table");
        Type declared = table.getGenericType();
        Type resolved = substitute(declared, env);
        System.out.println("Raw field: " + table.getType().getSimpleName());
        System.out.println("Declared: " + declared.getTypeName());
        System.out.println("Resolved: " + describe(resolved));
        System.out.println("Nested argument: "
                + (((ParameterizedType) resolved)
                    .getActualTypeArguments()[1]
                    instanceof ParameterizedType));
        Type upper = Outer.Slot.class.getDeclaredField("upper")
                .getGenericType();
        System.out.println("Wildcard: "
                + describe(substitute(upper, env)));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 NestedTypeSubstitutionDemo.java
java NestedTypeSubstitutionDemo
~~~

**Stdout:**

~~~text
T -> String
U -> Integer
V -> String
Owner: Outer<String>
Nested: Outer<String>.Slot<Integer>
Raw field: Map
Declared: java.util.Map<T, java.util.List<U[]>>
Resolved: Map<String, List<Integer[]>>
Nested argument: true
Wildcard: List<? extends Integer>
~~~

The example's `describe(Type)` **intentionally uses `Class#getSimpleName()`** for concise display; thus the string `Resolved: Map<String, List<Integer[]>>` does not print `java.util.` or `java.lang.`. In systems requiring unique identification or durable caching, use the `Type` and `Class` structures rather than relying on this abbreviated string.

### What to observe in the output

- **`T → String`**: goes through `End → Middle<String>` and then `Outer<V>`, yielding a transitive mapping.
- **`U → Integer`**: received directly from the type argument of `Slot<Integer>`.
- **`Owner: Outer<String>`**: proves the algorithm does not forget `getOwnerType()`.
- **`Nested: Outer<String>.Slot<Integer>`**: substitutes both the owner and the inner type's argument.
- **`Raw field: Map`**: `Field#getType()` has lost the arguments due to type erasure.
- **`Declared: java.util.Map<T, java.util.List<U[]>>`**: `Field#getGenericType()` reflects the declaration, without knowing `End` automatically.
- **`Resolved: Map<String, List<Integer[]>>`**: the algorithm descends through `Map`, `List`, `GenericArrayType`, and replaces `U` with `Integer`.
- **`Nested argument: true`**: the result still holds a real `ParameterizedType` argument at the `List<...>` level; it has not been collapsed into a string.
- **`Wildcard: List<? extends Integer>`**: the wildcard keeps its bound operator; the type variable inside the upper bound is substituted.

### Why are there three records `P`, `A`, `W`?

They are `Type` implementations **for the exercise**, not public JDK classes provided to construct arbitrary `ParameterizedType`s:

- `P` stores owner, raw type, and arguments, implementing `ParameterizedType`.
- `A` holds a generic array component when the component is not yet `Class<?>`.
- `W` holds upper/lower bounds of a wildcard.
- `List.copyOf` and `toArray(Type[]::new)` prevent callers from mutating internal arrays/lists.
- `equals`/`hashCode` compare components according to the reflection contracts; `getTypeName()` formatting uses the separate `describe` helper.

The implementations in the example fit learning goals and the generic types Java source can produce. Production frameworks need additional invariant checks (that raw type actually matches, argument count is valid, owner is valid, bounds are non-null/well-formed), caching policies, multi-branch resolution models, and tests against other complex type shapes.

## 7. Using `ParameterizedType` properly after substitution

A resolved `ParameterizedType` can be inspected via APIs rather than string splitting:

~~~java
ParameterizedType mapType = (ParameterizedType) resolved;
Type key = mapType.getActualTypeArguments()[0];
Type list = mapType.getActualTypeArguments()[1];

System.out.println(key == String.class); // true
System.out.println(list instanceof ParameterizedType); // true
~~~

This is an **illustrative code snippet** placed after creating the `resolved` variable in the main program, with `import java.lang.reflect.*`. They are `Type` objects, so you can continue reading raw type, owner, and arguments; there is no need to parse `getTypeName()`.

Checking the generic array after substitution:

~~~java
ParameterizedType listType = (ParameterizedType) list;
Type arrayArg = listType.getActualTypeArguments()[0];
System.out.println(arrayArg == Integer[].class); // true
~~~

After `U` resolves to `Integer.class`, the array `U[]` is represented by `Integer[].class`. If the component were still an unresolved type parameter, `GenericArrayType` would continue to be the appropriate representation.

**Do not think `substitute` alters the Java declaration or bytecode.** `Field#getGenericType()` on `Outer.Slot.table` still returns the metadata `Map<T, List<U[]>>`; the new `Type` object is only an **interpreted result under the context** constructed by the program. `Outer<T>`, `Slot<U>`, and runtime objects themselves are not modified.

## 8. Other nested forms to consider

### 8.1. Nested `ParameterizedType` in collections

For example `Map<String, List<Map<T, U>>>`. If you traverse only one level, `T` and `U` deep inside `Map<T,U>` will remain unsubstituted. The right rule is **iterate every element of `getActualTypeArguments()` and invoke the same algorithm recursively**.

### 8.2. Generic wildcards at multiple levels

`List<? extends U>` uses a `WildcardType` in `List`'s argument. `Map<? super T, ? extends List<U>>` can contain both lower bounds and upper bounds. You must descend into `getLowerBounds()` and `getUpperBounds()`, and not convert a wildcard directly into its bound type; `? extends Integer` is **not** the same declaration as `Integer`.

### 8.3. Generic arrays in arguments

`U[]` differs from `List<U>`. While still generic, it may be a `GenericArrayType`; when `U` becomes `Integer`, the result can be the array `Class` `Integer[].class`. If `U` instead substitutes to a `ParameterizedType` such as `List<String>`, an array `List<String>[]` must remain a `GenericArrayType`, because there is no reifiable `Class` for `List<String>[]`.

### 8.4. Static nested types and owner

A static nested class does not use the enclosing instance's generic parameters the way a non-static inner class does. You must read the actual metadata from `getOwnerType()` and `getActualTypeArguments()`, avoiding "filling in" the enclosing class's type arguments by guesswork. `ownerType` is not synonymous with an instance reference or an extra generic argument of a raw inner class.

### 8.5. `TypeVariable` declared on a method

A generic method like `<X> X convert(X input)` has `X` declared on the `Method` itself, not as a class parameter. Mappings built solely from superclasses **cannot automatically resolve `X`**. Separate context is needed (such as the method signature and the framework's type inference) if sufficient information actually exists. Otherwise, keeping an unresolved `TypeVariable` is a better result than guessing `Object`.

## 9. Important limitation: type erasure and available context

Reflection cannot infer every generic parameter from a **runtime instance**.

For example, two objects created from:

~~~java
// Illustrative; not a standalone runnable snippet.
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
~~~

Both `a.getClass()` and `b.getClass()` may be `ArrayList.class`; the type arguments `String` and `Integer` are not stored on the instance in a way Reflection can automatically recover. Only when there is a generic field on a concrete class or an interface/superclass parameterized in a declaration does Reflection have the needed metadata.

That is why the example uses **`class End extends Middle<String>`**: `End`'s superclass declaration holds `String`, and `Middle`'s declaration holds `Outer<V>.Slot<Integer>`. These two links supply enough context to resolve `T` and `U`.

If a type path is used as a **raw type**, some parameters may have no concrete mapping left. Do not treat `null`/missing mappings as proof that a type variable must be replaced with `Object` in all cases. Preserve the unresolved `TypeVariable` or represent bounds explicitly, depending on the API's goal.

## 10. Avoid five common design mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| `Map<String, Type>` keyed by `"T"` | Conflates unrelated `T`s across classes/methods | Use `Map<TypeVariable<?>, Type>` |
| Traversing only outer arguments of `ParameterizedType` | Leaves `List<U[]>` or `Map<T, U>` unresolved | Recursively resolve every argument |
| Ignoring `getOwnerType()` | Loses `Outer.T` mapping in `Outer<T>.Inner<U>` | Bind/resolve owner before or alongside inner |
| Substituting `T → V` once and stopping | Misses `V → String` on a closer supertype | Resolve transitively with cycle detection |
| Casting every `Type` to `Class` | Loses wildcards, parameterization, and generic arrays | Branch on the corresponding `Type` interfaces |

In addition, when creating a custom `ParameterizedType`, **do not merely override `toString()`** and treat it as a type resolver. You must store and return the exact raw type, owner, and arguments, preserve structure, and implement `equals`/`hashCode` appropriately. Display strings do not replace real type information.

## 11. Self-check questions

**Question 1.** With `Outer<String>.Inner<Integer>`, why doesn't `inner.getActualTypeArguments()` necessarily contain both `String` and `Integer`?

**Answer:** `String` resides in the metadata of the **owner** `Outer<String>`, whereas `getActualTypeArguments()` of `Inner<Integer>` holds the argument `Integer` corresponding to the type variable declared by `Inner` itself.

**Question 2.** From `Map<T, List<U[]>>`, if `T → String`, `U → Integer`, what is the result after full substitution?

**Answer:** `Map<String, List<Integer[]>>`. You must traverse the nested `List` and the `GenericArrayType` of `U[]`.

**Question 3.** Why shouldn't you use `Map<String, Type>` to store mappings for variables named `T`?

**Answer:** Variables with the same name can be declared by different `GenericDeclaration`s. The proper key is the `TypeVariable` object, not just the name string.

**Question 4.** Given `End extends Middle<String>`, `Middle<V> extends Outer<V>.Slot<Integer>`. How many mapping links must be traversed to resolve `Outer.T`?

**Answer:** Two links: `Outer.T → Middle.V` and `Middle.V → String`; yielding `Outer.T → String`.

**Question 5.** If a wildcard is `? extends U` and `U → Integer`, should we drop the `?` sign?

**Answer:** No. The result is `? extends Integer`, still a `WildcardType`, not plain `Integer`.

**Question 6.** Does `field.getGenericType()` automatically change to the substituted type after calling a resolver utility?

**Answer:** No. The resolver only produces a `Type` describing how the metadata is interpreted under a specific context; it does not modify the field declaration or class bytecode.

**Question 7.** Can you find the type argument `String` solely from `new ArrayList<String>().getClass()`?

**Answer:** No. `getClass()` returns `ArrayList.class`, while the argument of the instantiation expression is normally erased at runtime; you need information from a generic declaration that retains a signature.

## 12. Process summary

When resolving a nested type in a `ParameterizedType`: start from a concrete type that retains generic signatures, **follow the superclass/interface and owner chain**, map `TypeVariable`s by exact identity, and then **recursively resolve** across `ParameterizedType`, `GenericArrayType`, and `WildcardType`. Afterward, inspect the result using the `Type` APIs rather than strings alone.

In the example, combining `Middle.V → String`, `Outer.T → V`, and `Slot.U → Integer` allows transforming the declared field `Map<T, List<U[]>>` into a `Type` tree representing `Map<String, List<Integer[]>>` without losing the owner or nested levels.
