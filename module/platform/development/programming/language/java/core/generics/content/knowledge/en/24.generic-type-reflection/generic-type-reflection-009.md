# Limitations of Recovering Unbound `T` and the Cost of Processing Type Metadata in Java

## Learning Objectives

Java Generics allows writing `Box<T>`, `List<String>`, and algorithms that require only one implementation to operate across many types. Yet when a program needs **type reflection**, two seemingly similar questions are actually quite different:

1. "What type was this class/field/method **declared** to use?" — reflection can read a portion of the declaration's generic metadata.
2. "For **this instance**, what class was type variable `T` actually bound to where the object was created/held?" — usually **cannot be recovered** without an explicit binding source.

Beyond information limits, walking a class hierarchy, traversing `Type`, resolving `TypeVariable`, constructing/rebuilding `ParameterizedType`, and scanning many fields via reflection carry processing cost. You should avoid doing this repeatedly on a *hot path* if you can compute the metadata once and reuse it.

After this lesson, you will be able to:

- Distinguish runtime `Class<?>`, `Type`, `TypeVariable`, `ParameterizedType`, and **the concrete type argument of a use site**.
- Demonstrate that direct `Box<String>` and `Box<Integer>` both use runtime class `Box`, with no `T.class` token from a generic type variable.
- Explain when a subclass or anonymous subclass preserves a `Signature` containing `String`, and why a generic factory `<X>` only preserves `X`.
- Recognize **multi-level inheritance** cases that require mapping type variables across levels before deducing a type argument.
- Use `Class<T>` or a type reference declared in a concrete context to carry metadata explicitly.
- Understand that a `Type`/type token does not automatically mean **nested data validation**.
- Distinguish metadata query cost, hierarchy resolution cost, per-element checking cost, caching cost, and class-loading cost.
- Use `ClassValue` for caching keyed by runtime class, while understanding cache limitations and benchmarking mistakes.

**Requirements:** Java 17+ (`javac`, `java`, `javap`), no external libraries. The three standalone programs have been compiled with `-Xlint:all`; outputs below are verified results, except where explicitly marked illustrative or intentionally non-compiling.

## 1. Four Layers of Type Information to Keep Separate

Suppose we have the declaration:

```java
class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

And calling code:

```java
Box<String> words = new Box<>("Java");
Box<Integer> count = new Box<>(42);
```

Distinguish:

| Layer | Example | Which API Can Query It? | Limitation |
| --- | --- | --- | --- |
| Runtime class of the object | `words.getClass()` | `Object.getClass()` | Only sees actual class `Box`, does not know `String` |
| **Declared** generic parameter | `T` in `class Box<T>` | `Class.getTypeParameters()` | Returns variable `T`, not every instance's binding |
| Generic type of a **declaration** | Field `T value`, `extends Box<String>` | `Field.getGenericType()`, `Class.getGenericSuperclass()` | Reads signature stored at a specific declaration |
| Type of the **currently held value** | `words.get()` holds `String` | `value.getClass()` if non-null | Does not prove `T`: may be null or a subtype |

In source code, the compiler uses `String` to guard calls on `Box<String>`. For an ordinary generic class, however, the JVM does not create independent runtime versions `Box<String>` and `Box<Integer>`. They share the same runtime class definition `Box`.

The key takeaway: **metadata of a declaration differs from data attached to each instance**. For example, a field declared as `Box<String> field` can hold type metadata for **the field**; once you extract the object itself and only call `getClass()`, that object does not reveal that a user once assigned it to such a field.

## 2. Type Erasure Has No General Inverse

For a type variable `T` with no explicit bound, the effective bound is `Object`:

```java
class Box<T> {
    private T value;
    T get() { return value; }
}
```

At the JVM descriptor level, `T` positions use the erased form `Object`:

```text
Field T value             -> descriptor: Ljava/lang/Object;
Method T get()            -> descriptor: ()Ljava/lang/Object;
Constructor Box(T)        -> descriptor: (Ljava/lang/Object;)V
```

The class file can contain a `Signature` attribute so reflection tools see that the field was declared as `T`. Yet **a `Signature` containing the letter `T` is not a per-object lookup table `T -> String`**.

If `T extends Number`, the erasure of positions using `T` is typically the first upper bound, here `Number`. That also does **not** help guess whether an instance used `Integer`, `Double`, or `BigDecimal`: a bound only specifies the constraint set, not a concrete type argument.

In principle, many source-level choices can map to the same runtime class. Therefore, if the program **does not store the binding anywhere**, reflection lacks the data to "invert" type erasure. That limit cannot be overcome simply by calling more reflection APIs or building a more complex class-lookup algorithm.

## 3. Forbidden Syntax When `T` Is Not Reifiable

Inside a generic class, the following operations **intentionally do not compile**:

```java
class IllegalTypeRecovery<T> {
    Class<?> type() { return T.class; }
    T create() { return new T(); }
    boolean check(Object value) { return value instanceof T; }
}
```

This is a **negative test** illustrative file, not a runnable program. Try saving it as `IllegalTypeRecovery.java` and running:

```bash
javac IllegalTypeRecovery.java
```

On the tested Java compiler, the corresponding errors are:

```text
error: cannot select from a type variable
error: unexpected type
error: Object cannot be safely cast to T
3 errors
```

Because `T` is not a concrete runtime class literal:

- You cannot write `T.class` to obtain a token.
- You cannot invoke `new T()` without knowing the actual class/constructor.
- You cannot check `value instanceof T` for a non-reifiable type variable.

Do not replace those lines with unchecked casts and treat `T` as recovered. If you need to instantiate/check runtime objects, pass a `Class<T>` or factory with a proper contract right from the call site.

## 4. Program A — Inspecting Which Metadata Remains and Which Does Not

Create the file **`TypeRecoveryDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class TypeRecoveryDemo {
    static class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static final class NamedStringBox extends Box<String> {
        NamedStringBox(String value) { super(value); }
    }

    static class GenericChild<U> extends Box<List<U>> {
        GenericChild(List<U> value) { super(value); }
    }

    static final class ConcreteChild extends GenericChild<String> {
        ConcreteChild(List<String> value) { super(value); }
    }

    abstract static class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException(
                        "Expected parameterized parent");
            }
            type = p.getActualTypeArguments()[0];
        }

        Type type() { return type; }
    }

    static <X> TypeRef<X> makeRef(X value) {
        return new TypeRef<X>() {};
    }

    public static void main(String[] args)
            throws NoSuchFieldException {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(42);
        System.out.println("same runtime class: "
                + (text.getClass() == number.getClass()));
        System.out.println("runtime class: "
                + text.getClass().getSimpleName());

        TypeVariable<?> declared = Box.class.getTypeParameters()[0];
        Field field = Box.class.getDeclaredField("value");
        System.out.println("type variable: " + declared.getName());
        System.out.println("upper bound: "
                + declared.getBounds()[0].getTypeName());
        System.out.println("erased field: "
                + field.getType().getSimpleName());
        System.out.println("declaration type: "
                + field.getGenericType().getTypeName());
        System.out.println("values: "
                + text.get().getClass().getSimpleName() + ", "
                + number.get().getClass().getSimpleName());
        System.out.println("null has no class: "
                + (new Box<String>(null).get() == null));

        System.out.println("fixed parent: "
                + NamedStringBox.class
                        .getGenericSuperclass().getTypeName());
        System.out.println("intermediate parent: "
                + GenericChild.class
                        .getGenericSuperclass().getTypeName());
        System.out.println("concrete parent: "
                + ConcreteChild.class
                        .getGenericSuperclass().getTypeName());

        Type concreteRef = new TypeRef<List<String>>() {}.type();
        Type unresolvedRef = makeRef("hello").type();
        System.out.println("captured type: "
                + concreteRef.getTypeName());
        System.out.println("generic factory type: "
                + unresolvedRef.getTypeName());
        System.out.println("factory unresolved: "
                + (unresolvedRef instanceof TypeVariable<?>));
    }
}
```

Run:

```bash
javac -Xlint:all TypeRecoveryDemo.java
java TypeRecoveryDemo
```

**Verified stdout:**

```text
same runtime class: true
runtime class: Box
type variable: T
upper bound: java.lang.Object
erased field: Object
declaration type: T
values: String, Integer
null has no class: true
fixed parent: TypeRecoveryDemo$Box<java.lang.String>
intermediate parent: TypeRecoveryDemo$Box<java.util.List<U>>
concrete parent: TypeRecoveryDemo$GenericChild<java.lang.String>
captured type: java.util.List<java.lang.String>
generic factory type: X
factory unresolved: true
```

There are no warnings from `javac -Xlint:all` for this program.

## 5. Interpreting the Output: The Runtime Class Does Not Carry Each Object's `T`

The first two lines:

```text
same runtime class: true
runtime class: Box
```

are produced when two **distinct instances** `new Box<>("Java")` and `new Box<>(42)` both return runtime class `Box`. `getClass()` reports the actual class that instantiated the object rather than recovering how the reference variable was parameterized in source code.

The next lines:

```text
type variable: T
upper bound: java.lang.Object
erased field: Object
declaration type: T
```

illustrate two layers of metadata:

- `Box.class.getTypeParameters()[0]` is a `TypeVariable` representing the **declared parameter `T`**. `getBounds()` reports `Object` when there are no other bounds.
- `Field.getType()` reads the **erased runtime field type**: `Object`.
- `Field.getGenericType()` reads the **generic type declared for the field**: `T`.

Seeing `T` in reflection is **evidence of the generic signature**, not proof that `T` of the `text` instance was resolved to `String`.

## 6. Why Not Infer from the Held Value?

The program prints:

```text
values: String, Integer
null has no class: true
```

We can call `getClass()` on `text.get()` because the current value is a `String`. Yet that **does not verify `Box`'s type argument**.

For example:

```java
Box<CharSequence> a = new Box<>("Java");
Box<Number> b = new Box<>(Integer.valueOf(7));
```

This illustrative snippet uses `Box` in the same class context. Calling `a.get().getClass()` gives `String.class` even though the type argument is `CharSequence`; calling `b.get().getClass()` gives `Integer.class` even though the type argument is `Number`.

Additional cases:

- A `Box<String>` can hold `null`: there is no object to ask for a runtime class.
- A mutable `Box<Object>` can sequentially hold a `String`, an `Integer`, and then a `List`.
- A generic collection can be empty or hold subtypes of the declared type.
- Raw types and unchecked casts can cause data to no longer match the generic contract.

Hence, "inspect the first element and pick `T`" is an **unreliable heuristic**. If an API strictly requires the exact `T`, it must carry the binding into the API via a token, a declaration with concrete metadata, or a schema supplied upfront.

## 7. When Can `getGenericSuperclass()` Reveal a Concrete Type?

In Program A:

```java
static final class NamedStringBox extends Box<String> {
    NamedStringBox(String value) { super(value); }
}
```

When the compiler creates class `NamedStringBox`, the relationship **`extends Box<String>`** is part of the **subclass declaration**. Generic `Signature` metadata can store that relationship for reflection to read:

```java
Type parent = NamedStringBox.class.getGenericSuperclass();
System.out.println(parent.getTypeName());
```

In `TypeRecoveryDemo.java`, the output is:

```text
TypeRecoveryDemo$Box<java.lang.String>
```

This **does not contradict erasure**: metadata on `NamedStringBox`'s declaration carries `String`, while JVM descriptors of inherited methods still use erased types.

Two creation forms must be distinguished:

```java
Box<String> direct = new Box<>("A");
Box<String> viaSubclass = new NamedStringBox("B");
```

- `direct.getClass()` is `Box.class`, with no subclass declaration from which to find `String`.
- `viaSubclass.getClass()` is `NamedStringBox.class`. From there you can read the subclass's `extends Box<String>` declaration.

If an object is passed through multiple reference variables with different generic types while its runtime class carries no such constraint, there is **no general reflection way** to recover the type of each variable that held it.

## 8. Multi-Level Inheritance: Metadata Exists, but Is Not Yet Fully Resolved

Example from Program A:

```java
static class GenericChild<U> extends Box<List<U>> {
    GenericChild(List<U> value) { super(value); }
}

static final class ConcreteChild extends GenericChild<String> {
    ConcreteChild(List<String> value) { super(value); }
}
```

Output:

```text
intermediate parent: TypeRecoveryDemo$Box<java.util.List<U>>
concrete parent: TypeRecoveryDemo$GenericChild<java.lang.String>
```

The two calls are **different**:

- `GenericChild.class.getGenericSuperclass()` describes `GenericChild`'s direct parent: `Box<List<U>>`.
- `ConcreteChild.class.getGenericSuperclass()` describes `ConcreteChild`'s direct parent: `GenericChild<String>`.

If you want `Box<List<String>>` starting from `ConcreteChild`, you cannot just call `getGenericSuperclass()` once and blindly cast `getActualTypeArguments()[0]` to `Class`.

A sound resolver must:

1. Read `ConcreteChild extends GenericChild<String>`.
2. Record binding `U` (declared in `GenericChild<U>`) as `String`.
3. Continue to `GenericChild extends Box<List<U>>`.
4. Substitute `U` inside the **`List<U>` structure** with binding `String` to obtain `List<String>`.
5. Preserve owner types, nested parameterized types, wildcards, and generic arrays if the hierarchy uses them.

That is **declaration analysis + type-variable substitution**, not "recovering a type argument from an object" when the information was already lost.

Note especially: `getActualTypeArguments()` returns **`Type[]`**, not `Class<?>[]`. Elements can be `Class`, `TypeVariable`, `ParameterizedType`, `WildcardType`, or `GenericArrayType`. Casting all of them to `Class<?>` fails for structures like `List<U>`.

## 9. A Type Reference Only Captures the Type Written in the Declaration

A common pattern:

```java
abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();
        if (!(parent instanceof ParameterizedType p)) {
            throw new IllegalStateException(
                    "Expected parameterized parent");
        }
        type = p.getActualTypeArguments()[0];
    }

    Type type() { return type; }
}
```

This is an illustrative excerpt of `TypeRef`, requiring the corresponding imports; Program A has the complete definition.

Used at a **concrete site**:

```java
TypeRef<List<String>> ref = new TypeRef<List<String>>() {};
Type captured = ref.type();
```

The anonymous subclass carries `TypeRef<List<String>>` in its declaration; reflection can read:

```text
java.util.List<java.lang.String>
```

That is the **type explicitly written by the programmer / at compile time in the inheritance relationship**, not the result of guessing the contents of a runtime list.

If code needs to describe `Map<String, List<Integer>>`, a properly declared type reference can also carry nested `ParameterizedType`s. Still, **metadata describing an expected type does not validate actual data automatically**: a deserializer/validator must still inspect keys, values, and each element per its rules.

## 10. Major Pitfall: Creating a Type Reference Inside a Generic Factory

In Program A:

```java
static <X> TypeRef<X> makeRef(X value) {
    return new TypeRef<X>() {};
}
```

Call site:

```java
Type type = makeRef("hello").type();
```

gives output:

```text
generic factory type: X
factory unresolved: true
```

Reason: the anonymous subclass is compiled at a site where the type argument is still the **type variable `X`** of the generic method. Calling it with a `String` does not cause `javac` to emit a new specialized anonymous class for `X=String`.

This is a serious pitfall with helper methods like:

```java
static <T> Type inferT(T value) {
    return new TypeRef<T>() {}.type();
}
```

This function only captures **`T` from the generic method declaration**, rather than automatically inferring `String.class` for the type argument at a specific call. If you need a type bound at runtime, the caller must supply a concrete `Class<T>` or `Type`, or use an anonymous subclass declared where concrete type arguments are present.

**Quick rule:** ask "Where is `T` written?" If `T` is still a type variable when the compiler generates the anonymous class, metadata can only retain `T`. If the subclass explicitly writes `String` in the supertype declaration, metadata has the opportunity to retain `String`.

## 11. An Unbound `TypeVariable` Cannot Be Turned Into a Concrete `Class`

A `TypeVariable<D>` tells you:

- The variable name, e.g. `T`, `U`, `X`.
- The generic declaration that declared it (class, method, or constructor).
- Valid bounds, e.g. `Number`, `Comparable<T>`.

It **does not necessarily carry a binding for every use site**. For example, `<T extends Number>` does not tell you whether `T` is `Integer`, `Long`, or `Double`.

If a resolver encounters a `TypeVariable` with no mapping to a concrete type argument from the traversed declarations, the result may have to **keep the `TypeVariable` as is** or represent an unresolved state. **Do not replace `T` with `Object` and claim you found the user's type argument.**

The erasure `T -> Object` is a rule for compiling JVM descriptors, not type argument inference. Likewise, replacing `T extends Number` with `Number` is erased/bound information, not proof that the caller chose `Number` rather than a subtype.

At one API level, an erased `Class` is sometimes enough for coarse checks; when **exact generic types** are needed, preserve the unresolved state instead of creating the illusion of complete recovery.

## 12. Alternative Mechanism: Passing `Class<T>` Upfront

This is a clean design when you need the runtime type of **a concrete class**:

```java
static <T> T require(Object input, Class<T> token) {
    if (!token.isInstance(input)) {
        throw new IllegalArgumentException("Invalid type");
    }
    return token.cast(input);
}
```

At the call site:

```java
String s = require("hello", String.class);
Integer n = require(42, Integer.class);
```

the compiler links type parameter `T` with the passed token, and `Class.cast` performs the runtime check against that token.

**This is not reflection inferring `T` on its own**; the caller itself supplied the metadata. This pattern fits I/O boundaries, plugin factories, deserialization of a single class type, or data conversion configs very well.

Limits to remember:

- `Class<T>` does not fully represent `List<String>`: there is no `List<String>.class`.
- `Class.cast` checks the runtime type of the **object**, without traversing inner generic elements.
- `String.class.cast(null)` returns `null`; if null is disallowed, the API must define its own rule.
- The token must stay consistently tied to `T`; raw `Class`/unchecked casts can break the compile-time guarantee.

## 13. Program B — Validating Data with a Token Instead of Guessing `T`

Create the file **`VerifiedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class VerifiedBoundaryDemo {
    static <T> T require(Object candidate, Class<T> token) {
        Objects.requireNonNull(token, "token");
        if (!token.isInstance(candidate)) {
            throw new IllegalArgumentException(
                    "Expected " + token.getSimpleName());
        }
        return token.cast(candidate);
    }

    static <T> List<T> checkedCopy(List<?> input, Class<T> token) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(token, "token");
        List<T> result = new ArrayList<>();

        for (int i = 0; i < input.size(); i++) {
            Object value = input.get(i);
            if (!token.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Invalid index " + i);
            }
            result.add(token.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("single: "
                + require("ok", String.class));
        System.out.println("validated list: "
                + checkedCopy(List.of("A", "B"), String.class));

        try {
            checkedCopy(List.of("A", 9), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        try {
            require(null, String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("null rejected: " + ex.getMessage());
        }

        System.out.println("list class accepts integers: "
                + List.class.isInstance(List.of(1, 2)));
    }
}
```

Compile and run:

```bash
javac -Xlint:all VerifiedBoundaryDemo.java
java VerifiedBoundaryDemo
```

**Verified stdout:**

```text
single: ok
validated list: [A, B]
rejected: Invalid index 1
null rejected: Expected String
list class accepts integers: true
```

No compiler warnings under `-Xlint:all`.

### Why Does the Adapter Check Each Element?

`List.class.isInstance(List.of(1,2))` still returns `true`: the runtime object implements `List`. Yet the concrete generic argument is not reproduced by the JVM via the `List.class` token.

To return a trustworthy `List<String>` from a `List<?>` received at a boundary, `checkedCopy` performs three explicit actions:

1. Read each source element as `Object`.
2. Check `token.isInstance(value)`, reporting a specific error on a wrong element or `null`.
3. Use `token.cast(value)` to insert the verified value into a new `ArrayList<T>`; return `List.copyOf(result)`.

This is **per-element runtime validation**, not recovering a lost type argument. It also has cost proportional to the number of elements (`O(n)` checks, plus copy cost), unlike reading a few class-level metadata descriptors.

If the source can be mutated concurrently or contains mutable objects, design an appropriate snapshot/ownership policy. `List.copyOf` does not make mutable elements deeply immutable.

## 14. Why Does Reading Generic Metadata Have Cost?

Not all reflection operations cost the same. Do not use a blanket claim like "reflection is always slow" to generalize over every workload.

Work can be broken down by kind:

| Operation | Example | Main Cost Driver |
| --- | --- | --- |
| Accessing an existing class token | `String.class` | Lightweight, no hierarchy scan |
| Querying an object's runtime class | `obj.getClass()` | Reads actual class, does not resolve generic bindings |
| Reading a generic declaration | `field.getGenericType()` | Parsing/representing metadata depending on class and JDK |
| Enumerating many fields/methods | `getDeclaredFields()`, `getDeclaredMethods()` | Iterating many members and allocating arrays/descriptor objects |
| Traversing a multi-level hierarchy | Repeated `getGenericSuperclass()` | Extra cost per depth and branch count |
| Resolving `TypeVariable` | `U -> String` across two superclasses | Mapping structures, recursion over nested `Type`s |
| Analyzing `ParameterizedType` | `getActualTypeArguments()` | Traversing/constructing nested type expressions |
| Checking each element | `Class.isInstance` in a loop | Cost proportional to data size |
| Creating/growing caches | `ClassValue.get`, `computeValue` | Lookup, initial computation, and lifecycle cost |

A single `getGenericSuperclass()` call during startup is usually completely acceptable. Problems typically arise when **the same schema/class is re-analyzed many times** per record or request.

Some JDK implementations cache internally, yet you should not assume your application's entire resolver pipeline is free. For instance, if you rebuild `TypeVariable` mappings, walk fields, and construct serializer descriptors only to discard them on every request, the work outside the JDK's internal cache is still repeated.

**There is no universal nanosecond number** reliable across all JVMs/machines/metadata shapes. To claim a snippet is "X times slower", measure with your actual workload and configuration.

## 15. Simple Cost Model to Choose Where to Cache

Suppose the same schema class must be analyzed for `N` objects.

If each object re-runs the hierarchy analyzer:

```text
total work ≈ N × (scan declaration + resolve generics + apply to data)
```

If metadata is computed once and cached per class:

```text
total work ≈ (scan declaration + resolve generics) once
           + N × (cache lookup + apply to data)
```

This is only a guiding model, **not a benchmark or exact timing formula**. The benefit depends on hierarchy size, type complexity, class reuse count, contention, JDK allocations/caching, GC, and lookup cost.

Caching metadata avoids repeating the **class-invariant part**. It does not eliminate payload-processing cost: if verifying each element of a `List<?>` is required, you still must perform checks proportional to each instance's data.

Cache the **resolved schema**; do not cache a guessed "`T=String`" result inferred solely from runtime class `Box` and apply it to every `Box<Integer>` sharing that class. Doing so is both logically wrong and risks heap pollution.

## 16. Designing a Metadata Cache with `ClassValue`

`ClassValue<V>` is a JDK mechanism for associating a computed value with a runtime `Class<?>`. It is a useful choice for metadata that **truly depends on the class**.

Conceptual example:

```java
static final ClassValue<Metadata> CACHE = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return inspect(type);
    }
};

// Each time an object is processed:
Metadata metadata = CACHE.get(value.getClass());
```

This snippet is illustrative; `Metadata` and `inspect` must be defined. The full program is in Section 17.

Advantages of this approach:

- Queries via a readily available `Class` key.
- Provides a central point to compute metadata lazily when needed.
- Avoids manually maintaining a long-lived `static HashMap<Class<?>,...>` holding strong keys.
- Supports `remove(Class<?>)` when you want to drop the cached value for a class key.

However, understand its limits:

- **A cache only avoids recomputing metadata if the metadata is genuinely keyed by class.** It cannot resolve a type argument `T` not recorded on the class.
- `ClassValue.computeValue` may be invoked more than once under concurrent races/initialization. Do not place non-idempotent business side effects inside it, or assume a counter increments exactly once in every multithreaded program.
- Caches consume memory; the larger the cached values, the more carefully you must consider lifecycle and the number of generated classes.
- If metadata depends on configuration/schema version/classloader/locale beyond `Class`, keying solely by `Class` can be wrong. Define a **complete key** or organize caching appropriately.
- Do not store references to specific input objects inside a class-keyed metadata cache, since different instances of the same class can hold different data.

## 17. Program C — Comparing Inspection Counts Before/After Caching

Create the file **`MetadataCacheDemo.java`**:

```java
import java.lang.reflect.Type;
import java.util.concurrent.atomic.AtomicInteger;

public class MetadataCacheDemo {
    static class Parent<T> {}
    static final class Child extends Parent<String> {}

    record Metadata(String className, String declaredParent) {}

    static final AtomicInteger uncachedCalls =
            new AtomicInteger();
    static final AtomicInteger cachedComputations =
            new AtomicInteger();

    static Metadata inspectFresh(Class<?> type) {
        uncachedCalls.incrementAndGet();
        Type parent = type.getGenericSuperclass();
        return new Metadata(type.getSimpleName(),
                parent == null ? "(none)" : parent.getTypeName());
    }

    static final ClassValue<Metadata> CACHE = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            cachedComputations.incrementAndGet();
            Type parent = type.getGenericSuperclass();
            return new Metadata(type.getSimpleName(),
                    parent == null ? "(none)" : parent.getTypeName());
        }
    };

    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            inspectFresh(Child.class);
        }
        System.out.println("fresh inspections: "
                + uncachedCalls.get());

        Metadata one = CACHE.get(Child.class);
        Metadata two = CACHE.get(Child.class);
        Metadata three = CACHE.get(Child.class);

        System.out.println("cache same reference: "
                + (one == two && two == three));
        System.out.println("cache computations: "
                + cachedComputations.get());
        System.out.println("declared parent: "
                + one.declaredParent());

        CACHE.get(String.class);
        System.out.println("after another class: "
                + cachedComputations.get());

        CACHE.remove(Child.class);
        CACHE.get(Child.class);
        System.out.println("after removal: "
                + cachedComputations.get());
    }
}
```

Run:

```bash
javac -Xlint:all MetadataCacheDemo.java
java MetadataCacheDemo
```

**Verified stdout in sequential execution:**

```text
fresh inspections: 3
cache same reference: true
cache computations: 1
declared parent: MetadataCacheDemo$Parent<java.lang.String>
after another class: 2
after removal: 3
```

In the example:

- Three calls to `inspectFresh(Child.class)` execute the inspection body three times as written.
- Three calls to `CACHE.get(Child.class)` in **one thread, with no remove** reuse a single `Metadata` reference computed on the first call.
- `CACHE.get(String.class)` hits a new class key, incrementing the computation count.
- After `CACHE.remove(Child.class)`, calling `CACHE.get(Child.class)` runs `computeValue` again.

**Do not treat these counts as a speed benchmark.** They only demonstrate **how many times our code computes metadata** in a controlled scenario. A cache lookup still has cost; whether the savings are significant must be measured with the real resolver and workload.

## 18. Other Caching Options and Class Loader Lifecycles

A typical cache can be written:

```java
ConcurrentMap<Class<?>, Metadata> cache = new ConcurrentHashMap<>();
```

This is an illustrative snippet requiring appropriate imports and a `Metadata` class. In a system with few classes and a single classloader living for the entire application lifetime, this may be simple enough.

However, in plugin systems, hot-reload setups, or application servers that create multiple classloaders, **a long-lived static cache holding strong references to `Class` and related metadata** can prevent classloaders from being reclaimed.

Practical considerations:

| Storage Strategy | Strength | What to Verify |
| --- | --- | --- |
| Recompute every time | Simple, no cache management | Does repeated parsing hurt when request volume is high? |
| Local variable within one operation | Reused within a single request | Not shared across requests; good if workload is small |
| `ClassValue<Metadata>` | JDK cache design tied to class keys | Concurrency semantics; metadata must depend strictly on class |
| `ConcurrentHashMap<Class<?>,Metadata>` | Flexible, familiar | Classloader retention, invalidation, key cardinality |
| Cache by schema ID/version | Fits when metadata depends on external config beyond class | Key/version changes, data sync, evictions |

`ClassValue` is generally worth considering when data is **purely per-`Class`**. Even so, no option is free or right for every system. Measure retained heap, GC, classloader count, and hit rates under realistic conditions.

If using `ClassValue` for values holding **references out to external classloaders/objects**, you still need to check the lifecycle of those referenced objects. Do not promise "ClassValue can never leak"; what is true is that it provides a lifecycle mechanism tied to `Class` that is often better than holding strong class keys indefinitely.

## 19. Operations Best Done Once at Initialization

If an application uses reflection to map JSON/database rows to entity objects, a pipeline can:

1. Read class/field/method metadata once.
2. Resolve the resolvable parts of the generic hierarchy.
3. Check required annotations, constructors, or setters.
4. Build an immutable descriptor describing how to map data.
5. Store the descriptor in a cache keyed by class and schema version if needed.
6. When processing each record, use the prepared descriptor, performing only validation/conversion that actually depends on input data.

This reduces duplicated work and concentrates metadata-error checks into an earlier stage where failures are easier to report. Still, watch out for:

- If classes are loaded dynamically, preparation may have to run when a plugin/schema first appears.
- If metadata varies with runtime configuration, cache keys/invalidation must be designed properly.
- If classloader unloading is required, avoid arbitrary strong references from singletons/caches that are no longer needed.
- Do not share **mutable resolver state** across threads without a clear thread-safety contract.
- Using `ClassValue` does not make a cache safe if `Metadata` holds state modified concurrently without synchronization.

Expected outcome: **each stable class/schema is analyzed rarely**, while every input is still checked against the contract at the data boundary.

## 20. Separating Three Kinds of "Cost" in Reflection

### Metadata Analysis Cost

Operations such as reading `getGenericSuperclass()`, `getGenericInterfaces()`, `getDeclaredFields()`, `getGenericType()`, walking `TypeVariable`s, and traversing hierarchy structure. This can be precomputed/cached when it depends on the class.

### Per-Object Metadata Application Cost

Null checks, `Class.isInstance/cast`, parsing data, iterating collection elements, and constructing results. This cost is usually **proportional to the number of elements/fields processed** and is difficult to eliminate entirely with caching.

### Cache Management Cost

Lookups, lazy initialization, synchronization if any, memory holding `Metadata`, invalidation, and cache misses. A huge cache can cause GC or retention issues even while reducing parse counts.

Do not lump all three together as "reflection overhead". In a profiler, the hot spot might actually be **validation/serialization** or other application work, rather than `getGenericSuperclass()`.

## 21. How to Benchmark Without Drawing Wrong Conclusions

If you truly need to evaluate a resolver, prefer a microbenchmark framework such as **JMH** with warmup and JIT/GC control. Do not measure nanoseconds merely to illustrate concepts; the example in Section 17 uses counters because its goal is to **quantify how many times metadata is computed in a scenario**, not to make performance claims.

Useful workflow:

1. Define representative class metadata cases: plain class, concrete subclass, multi-level hierarchy, nested generic types, dynamically loaded class.
2. Separate three workloads: uncached, cache hit, cache miss/compute.
3. Warm up sufficiently so the JVM optimizes before sampling.
4. Consume benchmark results properly so the JIT does not eliminate dead/unobserved work.
5. Measure throughput/latency distributions, allocation rate, GC, and CPU—not just a single average time.
6. Run multiple forks/iterations with explicit configuration on identical JDK/hardware.
7. Verify cache correctness when classloaders change, under concurrency, or when schema versions change.
8. Compare against end-to-end workloads to see whether resolver optimization actually matters.

A single loop calling `System.nanoTime()` around 1000 reflection calls is **not reliable enough** to declare "cache is X times faster": JIT effects, allocations, warmup, escape analysis, and noise can overwhelm real differences.

**Production guidance:** optimize only after profiling shows metadata resolution is a meaningful bottleneck. Preserving the correctness of generic bindings takes priority over an unmeasured micro-optimization.

## 22. `getGenericSuperclass()` and Related APIs Do Not Always Return `ParameterizedType`

Common buggy snippet:

```java
ParameterizedType p =
        (ParameterizedType) someClass.getGenericSuperclass();
```

This illustrative snippet is dangerous: the parent class may be a raw/non-parameterized class, or `getGenericSuperclass()` returns `null` for classes like `Object`/interfaces; a direct cast can throw `ClassCastException` or fail otherwise.

Better pattern:

```java
Type parent = someClass.getGenericSuperclass();

if (parent instanceof ParameterizedType p) {
    for (Type argument : p.getActualTypeArguments()) {
        System.out.println(argument.getTypeName());
    }
} else {
    System.out.println("No parameterized direct superclass");
}
```

This is an illustrative method snippet requiring `someClass` and imports. When traversing generic interfaces, you must also read `getGenericInterfaces()`; looking only at the superclass is not enough.

Similarly, when obtaining a `Type`, do not immediately cast to `Class<?>`. Metadata may be an unresolved `TypeVariable`, a wildcard, or a nested `ParameterizedType`. Designing a `Type` processor with well-defined branches is usually far better than casting based on one simple working case.

## 23. The Cost of Rendering Metadata as Strings

`Type.getTypeName()` is very useful for logging, debugging, and writing observational tests. However, **a display string is not a type object usable for runtime checks**.

For example:

```java
Type complex = new TypeRef<List<String>>() {}.type();
String printed = complex.getTypeName();
```

`printed` might be `"java.util.List<java.lang.String>"`. It is not `Class<List<String>>`, nor does it automatically supply all data constraints/checks.

If an application must perform repeated type comparisons/resolutions, store a **normalized `Type`/descriptor structure** rather than repeatedly converting metadata to strings and re-parsing them. Hand-written stringification/parsing easily drops owner types, generic arrays, wildcards, bounds, and nested types.

Distinguish:

- **Type object**: structured metadata.
- **Type name string**: representation for humans/logging.
- **Class token**: runtime representation of a reifiable class/interface.
- **Data validation**: algorithm checking objects/collections against business rules.

Caching `getTypeName()` can help if logging the same metadata repeatedly, yet do not treat it as a valid way to infer type arguments that do not exist.

## 24. Cases Where Metadata May Be Missing or Unresolvable

Beyond type erasure, real-world metadata inspection can also encounter:

- A raw class/supertype declaration without concrete type arguments.
- A type variable with only bounds and no concrete binding.
- Hierarchies spanning multiple interfaces with type variables requiring substitution.
- Generic signature metadata missing or malformed in bytecode generated by other tools.
- Classes from different classloaders/plugins, even with identical class names.
- Dynamically generated classes or proxies whose hierarchy differs from the domain class expected by code.
- Access/module constraints when reflecting members and invoking constructors/methods (distinct from merely reading generic type names).
- APIs receiving objects that carry no information about the generic type argument of the source variable that referenced them.

In those situations, a solid resolver should represent **unresolved** or return a contextual error. Do not assert "`T=Object`" merely because the bound is `Object`.

If a business requirement cannot be satisfied due to missing metadata, the right fix is to **change the input contract** to accept `Type`, `Class<T>`, or an explicit schema—not to add speculative casts.

## 25. How to Compare Source and Bytecode with `javap`

After compiling the verified programs, run:

```bash
javap -p -s 'TypeRecoveryDemo$Box'
javap -p -s VerifiedBoundaryDemo
```

Single quotes around nested class names containing `$` are helpful in Bash/PowerShell. If `javap` runs from outside the class-file directory, add `-classpath <directory>` accordingly.

Part of `Box<T>` output:

```text
class TypeRecoveryDemo$Box<T> {
  private final T value;
    descriptor: Ljava/lang/Object;

  TypeRecoveryDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;
}
```

From `VerifiedBoundaryDemo`:

```text
static <T> T require(java.lang.Object, java.lang.Class<T>);
  descriptor: (Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;

static <T> java.util.List<T> checkedCopy(java.util.List<?>, java.lang.Class<T>);
  descriptor: (Ljava/util/List;Ljava/lang/Class;)Ljava/util/List;
```

The very contrast between the **generic method/field display line** and the **JVM descriptor** helps you see how `T` is erased in executable signatures while metadata still describes declarations.

To inspect generic metadata in detail, use `javap -v` and look for `Signature`. Inspect concrete subclasses like `TypeRecoveryDemo$NamedStringBox` and `TypeRecoveryDemo$ConcreteChild` as well.

**Do not conclude that metadata shown by `javap` proves the JVM synthesized a separate `Box<String>` runtime class.** Generic `Signature` can preserve declarations while method descriptors remain erased.

## 26. Comparing Solutions When Type Knowledge Is Needed

| Real-World Situation | Appropriate Solution | What Not to Do |
| --- | --- | --- |
| A direct `Box<T>`, object only | Accept the limitation; add a token/schema to the API | Guess `T` from `getClass()` |
| Subclass `extends Box<String>` | Read `getGenericSuperclass()` and inspect `Type` | Generalize that conclusion to every `Box<T>` |
| Multi-level subclass | Traverse hierarchy and substitute `TypeVariable`s soundly | Call one level and cast to `Class` |
| Generic factory `<X>` | Pass concrete `Class<X>` or `Type` | Expect `new TypeRef<X>() {}` to become `String` |
| Type such as `List<String>` | Type reference/`Type` + necessary validation | Use `List.class` to prove String elements |
| Legacy `List<?>` data | Check each element and build a typed copy | Unchecked cast the entire list |
| Frequently used resolver | Cache resolved metadata with the proper key | Re-parse hierarchy per record |
| Plugin/hot-reload system | Consider `ClassValue`, lifecycle, eviction | Hold strong references to all classes indefinitely |
| Performance numbers needed | Profile/JMH representing the workload | Claim speedup ratios from a single loop |

## 27. Common Conceptual and Coding Mistakes

**Mistake 1 — "`Box<T>.getClass()` must know `T` since the object was instantiated."** False: a direct object has runtime class `Box`; the type argument on the compiler's variable is not automatically stored as object state.

**Mistake 2 — "`getTypeParameters()[0]` returns the actual type argument."** The API returns the **declared** type parameter, e.g. `T`. That does not mean `String`.

**Mistake 3 — "`getGenericSuperclass()` is always a `ParameterizedType`."** False. Check `instanceof` and handle `Class`/`null` when needed.

**Mistake 4 — "A `ParameterizedType` definitely has `Class` actual args."** Arguments can be `TypeVariable`, `ParameterizedType`, wildcard, or generic array type.

**Mistake 5 — "`new TypeRef<T>() {}` inside a generic method captures the call-site inferred type."** False if `T` is still a type variable where the subclass is compiled.

**Mistake 6 — "Knowing the current value is `String` means the box's type argument is `String`."** It could be `Box<CharSequence>`, `Box<Object>`, or hold another value on another call.

**Mistake 7 — "Erasure of `T` is `Object`, so actual `T` is `Object`."** Erasure is not actual argument resolution; `Object` is just the JVM representation for an unbounded variable slot.

**Mistake 8 — "`Class<List>` proves every element is a `String`."** False. Runtime `List` enforces no generic element type constraint automatically.

**Mistake 9 — "An unchecked cast is enough to restore `T`."** False. Unchecked casts skip proof checks and can push errors to runtime.

**Mistake 10 — "Caching metadata recovers lost type arguments."** Caches only retain computed or available info; they do not conjure nonexistent info.

**Mistake 11 — "`ClassValue` always invokes `computeValue` once across all threads."** Do not assume that; concurrent contention can cause redundant computation. Write pure/idempotent computation functions.

**Mistake 12 — "Caching `Class<?>` in an unbounded static map has no lifecycle impact."** It can pin unused classloaders/classes; consider lifetimes and cache policies.

**Mistake 13 — "Counting metadata computations measures speed."** False. A counter only shows how many times code ran; per-operation/GC/JIT costs must be measured separately.

**Mistake 14 — "Reflection is always too slow and everything must be cached."** There is no absolute rule; optimize when profiling proves a hot spot and the benefit outweighs cache complexity.

**Mistake 15 — "Metadata type name is schema validation."** A `Type`/string `List<String>` describes expectations; payloads still must be validated when data is untrusted.

## 28. Practice Exercises with Answers

### Exercise 1 — Two Different Boxes

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);
```

**Question:** Can `a.getClass() == b.getClass()` be `true`? Can `T` be inferred from that expression?

**Answer:** `true` when both are instantiated directly from the same `Box` class; the comparison tells you neither `String` nor `Integer`.

### Exercise 2 — Unresolved `TypeVariable`

A generic method `<X> TypeRef<X> makeRef(X x)` creates `new TypeRef<X>() {}`. Caller passes `String`. What is `ref.type()`?

**Answer:** the anonymous subclass's metadata may retain `X` from the method declaration, rather than specializing to `String`. Program A verifies `generic factory type: X`.

### Exercise 3 — Subclass Metadata

What can `class NamedStringBox extends Box<String>` provide via `getGenericSuperclass()`?

**Answer:** the declaration `Box<String>` on the subclass, because `String` is explicitly written in the supertype declaration.

### Exercise 4 — Multi-Level Inheritance

`GenericChild<U> extends Box<List<U>>` and `ConcreteChild extends GenericChild<String>`. Does calling only `ConcreteChild.class.getGenericSuperclass()` yield `Box<List<String>>`?

**Answer:** no; it gives `GenericChild<String>`. You must proceed to `GenericChild` and substitute `U=String` inside `Box<List<U>>` to derive the corresponding structure.

### Exercise 5 — `Object` as Erasure

If `T` is unbounded, `Field.getType()` for `T field` returns `Object`. Can you conclude the caller chose `Box<Object>`?

**Answer:** no. `Object` is the erased field type, not an instance's actual type argument.

### Exercise 6 — Writing a Token-Accepting API

To write a function accepting `Object` and returning `String` after checking, how should `String.class` be used?

**Answer:** pass a `Class<T>` token into a generic method, using `token.isInstance`/`token.cast`, with an explicit null policy. `T.class` is not needed inside the generic method.

### Exercise 7 — Nested List

A `List<Integer>` satisfies `List.class.isInstance`. Is that enough to confirm it is `List<String>`?

**Answer:** no. The `List.class` token only checks the runtime interface. To ensure a list contains only `String`s, check elements or use appropriate schema validation.

### Exercise 8 — Caching

Run `inspectFresh(Child.class)` three times and `CACHE.get(Child.class)` three times in Example C. What are the counter values?

**Answer:** `fresh inspections: 3`, `cache computations: 1` in the tested sequential run; this is not execution time, and concurrent runs can differ.

### Exercise 9 — Wrong Cache Key

A metadata resolver depends on both `Class<?>` and a schema version. Is using `Class` alone as the key sufficient?

**Answer:** no, if the same class can be processed under different schema versions. You need a cache key containing the version or explicit invalidation.

### Exercise 10 — Classloader Retention

A `static ConcurrentHashMap<Class<?>,Metadata>` holds classes from plugin classloaders that have logically unloaded. What is the risk?

**Answer:** strong keys/values can keep those classes and classloaders reachable, preventing memory reclamation. Consider lifecycles, eviction, per-loader caches, or `ClassValue`.

### Exercise 11 — Performance Measurements

A benchmark calls `System.nanoTime()` once around a few calls and claims the cache is "100x faster". Is that well-founded?

**Answer:** no. Warmup, JIT/GC/allocation control, result consumption, and representative workloads are needed. JMH helps avoid many microbenchmark traps.

### Exercise 12 — Type Reference as Validation

You have a `TypeRef<List<String>>` describing a schema. If raw data contains an `Integer` in the list, does creating the type reference make the input valid?

**Answer:** no. A type reference holds expected metadata, not an automatic payload check. You must validate/deserialize against the schema.

## 29. Project Application Checklist

- [ ] Clearly distinguish **runtime class**, **generic declaration**, **binding from superclass**, and **type argument at a use site**.
- [ ] Do not infer `T` arbitrarily from `obj.getClass()` or the runtime class of one element.
- [ ] Do not treat an unbound `TypeVariable` as a concrete `Class`.
- [ ] Before casting `Type`, check whether it is `Class` / `ParameterizedType` / `TypeVariable` / wildcard / generic array.
- [ ] When resolving a hierarchy, substitute type variables **level by level**, not only by inspecting the direct superclass.
- [ ] If runtime type is needed, require the caller to pass `Class<T>`, `Type`, a type reference, or a schema.
- [ ] When nested generic data safety is required, check elements/keys/values against the contract.
- [ ] Do not use unchecked casts to "simulate" lost type information.
- [ ] Cache only reusable metadata under a properly defined key.
- [ ] Account for `ClassValue`, classloader lifecycles, concurrency, versioning, and invalidation.
- [ ] When evaluating performance, separate metadata resolution from per-item validation and cache cost.
- [ ] Profile/benchmark on meaningful workloads rather than relying on counts or single-pass timings.
- [ ] Compare generic `Signature` against erased JVM descriptors with `javap` when needed.

## Conclusion

**An unbound `T` cannot be recovered solely via `getClass()` or more elaborate reflection.** Type erasure causes multiple parameterizations to share a runtime class, while generic metadata stored at **declarations** can only help resolve types when a concrete binding exists, such as `extends Box<String>` or an explicitly written type reference. With multi-level hierarchies, `TypeVariable`s must be substituted soundly; if no mapping exists, the result must remain **unresolved** rather than guessed.

Regarding cost, reflection metadata should be handled pragmatically: analyze once at an appropriate boundary, reuse descriptors when the same class/schema repeats, and validate actual data when validation is required. `ClassValue` can reduce repeated metadata computations per class, yet caches must be designed for the right lifecycle and benchmarked accurately before optimizing. **Prioritize correctness of generic bindings first, and optimize metadata reading and resolution costs afterwards.**
