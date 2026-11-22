# Designing Heterogeneous Containers with `Class<T>` as Keys in Java Generics

## 1. The problem: a container holding multiple data types while keeping the API type-safe

A structure like `Map<String, Object>` can hold a `String` username, an `Integer` retry count, or a `Duration` timeout. However, reading APIs typically require casting:

```java
Object raw = values.get("retryCount");
Integer retries = (Integer) raw;
```

This is an illustrative snippet, assuming a `values` variable exists. The compiler cannot prove `"retryCount"` is always associated with `Integer`. If other code puts a `String` under the same key, the cast may throw `ClassCastException` at runtime.

An alternative design uses a **runtime class token `Class<T>` as the key**:

```java
registry.put(String.class, "Java");
registry.put(Integer.class, 3);

String language = registry.get(String.class);
Integer retries = registry.get(Integer.class);
```

When the caller passes `String.class`, the compiler knows the corresponding value must have type `String`. With `Integer.class`, the compiler knows the value must be `Integer`. Internally it can still use a `Map<Class<?>, Object>`, while the **generic public API** connects the key's type and the value's type.

This design is commonly called a **typesafe heterogeneous container**: a container that does not declare a single shared type parameter like `Box<T>`, but instead gives **each entry its own type relationship** via a class key.

Core takeaway:

> It is not that `Map<Class<?>, Object>` is inherently type-safe. Safety comes from permitting map access only through APIs such as `<T> void put(Class<T>, T)` and `<T> T get(Class<T>)`, while using `Class.cast` to enforce the constraint at runtime.

This lesson builds a registry from the minimal level to a practical design: type tokens, `Class.cast`, `null`, value replacement, subclasses/interfaces, key identity, limitations with `List<String>`, concurrency, data mutability, testing, and common pitfalls. Complete programs use Java 17 or later.

## 2. How do the key's type and the value's type relate?

Consider the method:

```java
public <T> void put(Class<T> type, T value)
```

`T` is a **method type parameter**. It appears simultaneously on both key and value:

- `Class<T>` indicates a specific class token is being used.
- `T value` says the value must be compatible with that token type.
- Callers do not need to write `<T>` explicitly if the compiler can infer it from the call.

Similarly:

```java
public <T> T get(Class<T> type)
```

When passing `String.class` of type `Class<String>`, the result is typed as `String`.

Example:

```java
registry.put(String.class, "hello");   // Valid
registry.put(Integer.class, 123);      // Valid

// INTENTIONALLY DOES NOT COMPILE:
// registry.put(String.class, 123);     // String and Integer are incompatible
```

To know the types, the compiler does not need to inspect the map's runtime contents: **the generic signature** suffices to check well-typed calls.

The signature does not make Java Generics reified. If code uses raw types, unchecked casts, reflection, or accesses the backing map through another path, the key/value relationship can still be broken. Hence **write paths** must be locked down and runtime validation used.

## 3. Minimal design: `Map<Class<?>, Object>`

A basic registry class:

```java
final class Registry {
    private final Map<Class<?>, Object> values = new HashMap<>();

    public <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    public <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
```

This is an illustrative declaration fragment; `Map` and `HashMap` must be imported, or fully qualified as in the program below.

Why is the field `Map<Class<?>, Object>` rather than `Map<Class<T>, T>`?

- **There is no single shared `T` for all entries.** A `String.class` key has a `String` value, and an `Integer.class` key has an `Integer` value.
- `Class<?>` lets the map accept class tokens of many classes.
- `Object` lets it store object references belonging to many classes.
- The **method-level** generic signature `<T>` ensures each operation has the right type relationship.

Also, do not mistake `Map<Class<?>, Object>` for a `Map<Class<T>, T>` for a single `T`. A class-level generic parameter would restrict the entire registry to one type, defeating the heterogeneous goal.

`Class.cast` is an additional runtime verification step: if `type` represents `String` and `value` is not a `String`, it throws `ClassCastException`. For `null`, `Class.cast(null)` returns `null`, so a dedicated `null` policy is needed if the application does not want to allow it.

## 4. Runnable example: minimal registry

Create the file **`BasicTypeRegistryDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class BasicTypeRegistryDemo {

    static final class Registry {
        private final Map<Class<?>, Object> values = new HashMap<>();

        public <T> void put(Class<T> type, T value) {
            values.put(type, type.cast(value));
        }

        public <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        registry.put(String.class, "Java 17");
        registry.put(Integer.class, 4);
        registry.put(Boolean.class, true);

        String label = registry.get(String.class);
        Integer attempts = registry.get(Integer.class);
        Boolean enabled = registry.get(Boolean.class);

        System.out.println(label);
        System.out.println(attempts);
        System.out.println(enabled);
        System.out.println(registry.get(Double.class) == null);
    }
}
```

Compile and run:

```bash
javac BasicTypeRegistryDemo.java
java BasicTypeRegistryDemo
```

Stdout:

```text
Java 17
4
true
true
```

Explanation:

1. The registry has only **one internal map**, not three maps for `String`, `Integer`, and `Boolean`.
2. `put(String.class, "Java 17")` stores the matching class/value pair.
3. `get(Integer.class)` returns a result of type `Integer`; the caller does not need to cast `(Integer)`.
4. Because `Double.class` has no entry yet, `Map.get` returns `null`, and `Class.cast(null)` returns `null`.
5. This is a simple example to see the mechanism, **without yet deciding policies for `null` and primitive class tokens**.

When using this design in a library, do not stop at the minimal example: clarify missing keys, `null`, updates, thread safety, and the ability to store generic parameterized types.

## 5. Why is `Class<T>` a "type token"?

A class literal:

```java
Class<String> s = String.class;
Class<Integer> n = Integer.class;
```

is a reference to the runtime `Class` objects of `String` and `Integer`.

The token provides APIs such as:

- `type.cast(object)` — checks and returns the object with type `T`, or throws `ClassCastException`.
- `type.isInstance(object)` — checks whether a non-null object is a compatible instance.
- `type.getName()` — class name for logging/diagnostics.
- `type.isPrimitive()` — identifies tokens representing primitives.
- `type.isInterface()` — identifies interfaces.
- `type.isAssignableFrom(otherClass)` — checks runtime assignability in the appropriate direction.

The registry here uses tokens by **runtime class identity**, not merely by string name. `String.class` is one key; `CharSequence.class` is another key even though a `String` value can be stored under either.

Distinguish:

```java
registry.put(String.class, "text");
```

from:

```java
registry.put(CharSequence.class, "text");
```

The two calls can hold the exact same runtime object yet write under **two distinct keys**.

## 6. How does `Class.cast` protect the key–value relationship?

An implementer might write:

```java
@SuppressWarnings("unchecked")
public <T> T get(Class<T> type) {
    return (T) values.get(type);
}
```

When casting to a type variable `T`, the compiler cannot perform a full runtime check due to erasure. Client code might only receive an error later when the result is used as a concrete type.

Replacing it with:

```java
public <T> T get(Class<T> type) {
    return type.cast(values.get(type));
}
```

has two benefits:

1. **Clear intent**: the result must belong to the runtime class passed in by the caller.
2. **Clear check site**: `Class.cast` performs a concrete type check via the token rather than relying on the assumption that map data is always valid.

`type.cast(value)` should also be used on the `put` path to guard against calls that are not fully typed, such as a raw `Class` supplied by legacy code.

However, `Class.cast` **does not inspect inside `List<String>`**. If `type` is `List.class`, it only verifies that an object implements the `List` interface, without caring whether elements are `String` or `Integer`. That limitation is analyzed separately in a later section.

## 7. Practical API: forbidding null, returning previous values, and type-safe removal

For an easily testable contract, suppose the registry chooses:

- `null` **is not allowed as a value**.
- `null` class tokens are rejected.
- Primitive tokens such as `int.class` are rejected.
- Each `Class<?>` key has **at most one value**; a new `put` replaces the old value.
- `get` returns `null` when the key is absent; `find` can return `Optional<T>`.
- `remove` returns the previous value of type `T`, or `null` if absent.

File **`StrictTypeRegistryDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class StrictTypeRegistryDemo {

    static final class Registry {
        private final Map<Class<?>, Object> entries = new HashMap<>();

        private static <T> Class<T> checkToken(Class<T> type) {
            Objects.requireNonNull(type, "type");

            if (type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Primitive class token is unsupported");
            }

            return type;
        }

        public <T> T put(Class<T> type, T value) {
            type = checkToken(type);
            Objects.requireNonNull(value, "value");

            Object previous = entries.put(type, type.cast(value));
            return type.cast(previous);
        }

        public <T> T get(Class<T> type) {
            type = checkToken(type);
            return type.cast(entries.get(type));
        }

        public <T> Optional<T> find(Class<T> type) {
            return Optional.ofNullable(get(type));
        }

        public <T> T remove(Class<T> type) {
            type = checkToken(type);
            return type.cast(entries.remove(type));
        }

        public boolean contains(Class<?> type) {
            checkToken(type);
            return entries.containsKey(type);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        System.out.println(registry.put(String.class, "first"));
        System.out.println(registry.put(String.class, "second"));
        System.out.println(registry.get(String.class));
        System.out.println(registry.contains(String.class));
        System.out.println(registry.find(Integer.class).isPresent());
        System.out.println(registry.remove(String.class));
        System.out.println(registry.contains(String.class));
    }
}
```

Compile and run on Java 17:

```bash
javac StrictTypeRegistryDemo.java
java StrictTypeRegistryDemo
```

Stdout:

```text
null
first
second
true
false
second
false
```

Explanation:

- `put` returns the **previous value** of the same class if an entry already existed; the first time it returns `null`.
- `get` and `remove` have return type `T` based on the token.
- `containsKey` helps distinguish absence in the contract if needed.
- `Optional.ofNullable` expresses "value present or absent" when `null` values are forbidden.
- `checkToken` rejects primitive class tokens because they cannot be used like reference tokens in `Class.cast`.

This example is **not safe under concurrent access by multiple threads**, because the backing map is `HashMap`. If concurrent access is needed, use a different design rather than assuming the generic API handles concurrency.

## 8. Null policy: decide clearly from the start

`HashMap` allows `null` as a value. `Class.cast(null)` also returns `null`. Therefore the minimal registry cannot distinguish whether:

```java
registry.get(String.class) == null
```

means "no entry" or "entry with value null".

There are three valid design directions:

**Option A — Disallow null values.** Use `Objects.requireNonNull(value)` in `put`; then `get(...) == null` unambiguously indicates the key is absent. This is the choice of `StrictTypeRegistryDemo`.

**Option B — Allow null but provide a `contains` API.** `containsKey(type)` distinguishes an absent key from a key present with `null`. `Optional<T>` **cannot** separately represent the three states absent / present-with-null / present-with-non-null.

**Option C — Use a dedicated result model.** For instance, a record or sealed type describing `Absent`, `PresentNull`, `PresentValue<T>` if business logic needs full distinction.

Do not mechanically store `Optional<T>` as the map value to solve everything. It adds another object layer and still requires agreeing on what `Optional.empty()` represents.

With `ConcurrentHashMap`, `null` keys and `null` values are disallowed; a no-null policy is mandatory if choosing that backing map.

## 9. Primitive tokens: `int.class` differs from `Integer.class`

An advanced detail:

```java
System.out.println(int.class.isPrimitive());
System.out.println(Integer.class.isPrimitive());
```

The two lines above (when placed in `main`) print:

```text
true
false
```

Java has class tokens for primitives to support reflection, yet generic type arguments cannot be primitive. In class-literal contexts, `int.class` can participate in APIs with type `Class<Integer>` under special rules for `Class` literals, **which does not mean `int.class` is equivalent to `Integer.class`**.

The runtime class token of `int` is not the runtime class of a boxed `Integer` instance. In a registry storing `Object`, the simplest contract is:

- **Use `Integer.class`** when wanting to store an `Integer` value (autoboxed from `int` if needed).
- **Reject `int.class`** when registering values with `Class.cast`.
- Similarly use `Boolean.class` and `Double.class` instead of primitive tokens.

`Class.cast` on a primitive class token does not perform general boxing/unboxing like a converter. Do not treat `int.class.cast(1)` as a way to convert `Integer` to primitive `int`.

## 10. Registry keys by exact class token, not automatic subtype lookup

When calling:

```java
registry.put(String.class, "A");
```

the registry records the key `String.class`. A subsequent call:

```java
registry.get(CharSequence.class);
```

does not automatically find the `String.class` entry, even though `String implements CharSequence`.

Reason: `Map.get` looks up the **exact key**, rather than running a class-hierarchy traversal algorithm.

If business logic needs "find all services implementing interface X", that is **a different problem**:

- You can register explicitly under the interface key: `registry.put(CharSequence.class, "A")`.
- You can design a resolver using `isAssignableFrom` to locate matching candidates.
- Yet when multiple implementations match, the resolver needs precedence/uniqueness rules; it cannot arbitrarily return the first map entry as a reliable contract.

This lesson's core design favors **exact class-key lookup**, because it is simple, deterministic, and easy to keep type-safe.

## 11. Program demonstrating interface keys and implementation keys

File **`ExactClassKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class ExactClassKeyDemo {
    static final class Registry {
        private final Map<Class<?>, Object> values = new HashMap<>();

        <T> void put(Class<T> type, T value) {
            values.put(type, type.cast(value));
        }

        <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        registry.put(String.class, "concrete");

        System.out.println(registry.get(String.class));
        System.out.println(registry.get(CharSequence.class));

        registry.put(CharSequence.class, "interface");
        System.out.println(registry.get(String.class));
        System.out.println(registry.get(CharSequence.class));
    }
}
```

Compile/run:

```bash
javac ExactClassKeyDemo.java
java ExactClassKeyDemo
```

Stdout:

```text
concrete
null
concrete
interface
```

`String.class` and `CharSequence.class` are two distinct keys. Both can point to objects whose runtime class is `String`, yet the API identifies them by **the class tokens chosen at registration**.

This behavior should be clearly documented in the API; otherwise callers easily misassume `get(SuperType.class)` will automatically find all subtype instances.

## 12. `Class<T>` invariance and wildcards in the registry

The generic class `Class<T>` is **invariant**. Even though `Integer extends Number`, you cannot directly assign `Class<Integer>` to a `Class<Number>` variable:

```java
// INTENTIONALLY DOES NOT COMPILE:
// Class<Number> token = Integer.class;
```

However:

```java
Class<? extends Number> numericToken = Integer.class;
```

is valid.

When using a wildcard token, the compiler only knows **an unspecified subtype** of `Number`:

```java
Class<? extends Number> type = Integer.class;
```

An API:

```java
<T> T get(Class<T> type)
```

can return a value safely viewed as `Number` when given a `Class<? extends Number>`, yet cannot assume it is **any** specific subtype chosen arbitrarily by the caller.

Helpers should use `Class<? extends Base>` if accepting plugin implementations, while public `get(Class<T>)` keeps **the same type parameter `T`** linking the class token and the result.

Do not change signatures to raw `Class` to "solve" wildcard errors. When needed, use a capture helper or transform values within known bounds.

## 13. When keys come dynamically from `Class.forName`

A plugin application might receive a class name from configuration:

```java
Class<?> loaded = Class.forName("java.lang.String");
```

The token has static type `Class<?>`: the compiler does not know a concrete `T`. If you need to restrict plugins to an interface or base class, check at runtime:

```java
Class<? extends CharSequence> type =
        loaded.asSubclass(CharSequence.class);
```

`asSubclass` returns a token with the checked bound, or throws `ClassCastException` if the class is not an appropriate subtype.

**Do not do this for arbitrary class names from untrusted input and instantiate them.** Loading/instantiating can execute code, consume resources, and touch access-control policies. Use an allowlist or a verified plugin list when implementing a runtime registry.

In a class-key registry, an API accepting `Class<?>` helps inspect metadata or check entry presence; however, if `get` is expected to return a specific type with a compile-time guarantee, **the caller must possess an appropriately typed token**. Passing a class name as a string cannot make the compiler know the result type on its own.

## 14. Do not use string keys to pretend a type relationship exists

Compare two APIs:

```java
Object get(String key);
<T> T get(Class<T> type);
```

The first API cannot infer a `Integer` return type from a string `"port"` unless there is another schema/registry and the caller casts.

The second API directly links the return value to the type argument of `Class<T>` in the method signature. It suits data where **each class has only one entry** and class identity is a sensible key.

However, if business logic needs **two different keys** such as `"firstName"` and `"lastName"` both carrying type `String`, a class-key registry is insufficient:

```java
registry.put(String.class, "first");
registry.put(String.class, "last");
```

The second write **replaces** the first because the key is identical.

A solution can be a **typed key object** combining a name and a class token, such as `Key<T>("firstName", String.class)`, or a key comprising namespace + type. That is a different structure from the "one key per runtime class" problem.

## 15. When one class needs multiple values: named typed keys

If business logic needs multiple values of the same type, you can use a key with its own identity while storing the token to preserve the relationship with the value.

One model:

```java
record Key<T>(String name, Class<T> type) {
}
```

Note carefully: generic `Key<T>` undergoes erasure, and Java record equality compares **name and type**; if two keys have the same name and class token, they are equal even if instantiated twice.

A reasonable design can have:

```java
Map<Key<?>, Object> values;
<T> void put(Key<T> key, T value);
<T> T get(Key<T> key);
```

and check `key.type().cast(value)` in both directions. This pattern adds a **business-identity** dimension beyond runtime class.

In the present lesson, the focus remains `Class<T>` as the key. Typed named keys are an **extension option** when one class needs more than one registration or needs key namespaces.

## 16. Extended example: `Key<T>` combining name and class token

File **`NamedTypedKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class NamedTypedKeyDemo {

    record Key<T>(String name, Class<T> type) {
        Key {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
        }
    }

    static final class Registry {
        private final Map<Key<?>, Object> values = new HashMap<>();

        <T> void put(Key<T> key, T value) {
            Objects.requireNonNull(value);
            values.put(key, key.type().cast(value));
        }

        <T> T get(Key<T> key) {
            return key.type().cast(values.get(key));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        Key<String> first = new Key<>("firstName", String.class);
        Key<String> last = new Key<>("lastName", String.class);

        registry.put(first, "An");
        registry.put(last, "Nguyen");

        System.out.println(registry.get(first));
        System.out.println(registry.get(last));
    }
}
```

Compile/run:

```bash
javac NamedTypedKeyDemo.java
java NamedTypedKeyDemo
```

Stdout:

```text
An
Nguyen
```

This is a solution with **two distinct keys sharing the same class token `String.class`**. It shows when the design must be upgraded beyond `Map<Class<?>,Object>`.

Note: if case-insensitive names, namespaces, tenants, or other validity constraints are needed, you must define the identity rules on the record/key class yourself. A generic signature does not replace business data modeling.

## 17. Crucial limitation: `List<String>` and `List<Integer>` share `List.class`

Java Generics have **type erasure**. A parameterized type like `List<String>` has no separate class literal:

```java
// INTENTIONALLY DOES NOT COMPILE:
// Class<List<String>> stringList = List<String>.class;
```

At runtime there is only:

```java
Class<?> listClass = List.class;
```

Consequence in a class-key registry:

- There are no two separate keys `List<String>.class` and `List<Integer>.class`.
- `List.class` only verifies that an object implements the `List` interface.
- You cannot use `type.cast(value)` with `List.class` to verify every element is a `String`.
- Under the basic design, a registry holds one entry for `List.class`, without distinguishing generic type arguments.

### Example demonstrating the limitation accurately

File **`ListClassTokenLimitDemo.java`**:

```java
import java.util.List;

public class ListClassTokenLimitDemo {
    public static void main(String[] args) {
        List<?> text = List.of("A", "B");
        List<?> numbers = List.of(1, 2);

        System.out.println(List.class.isInstance(text));
        System.out.println(List.class.isInstance(numbers));

        Object mixed = List.of("A", 10);
        List<?> accepted = List.class.cast(mixed);

        System.out.println(accepted.size());
        System.out.println(accepted.get(1));
    }
}
```

Compile/run:

```bash
javac ListClassTokenLimitDemo.java
java ListClassTokenLimitDemo
```

Stdout:

```text
true
true
2
10
```

`List.class` accepts a string list, a number list, and a mixed list alike. That is accurate for the raw runtime interface, yet **not a type-argument check**.

When needing to store **nested generic types** as keys, you must use a key kind able to describe `Type`, `ParameterizedType`, type references, or a dedicated schema, plus a validation policy if you want to trust runtime data.

## 18. Why is `Map<Type,Object>` not automatically safe either?

An advanced option is using `java.lang.reflect.Type` as key, e.g., from `TypeReference<List<String>>` and `TypeReference<List<Integer>>`. Thanks to `ParameterizedType`, two keys can distinguish **generic structure**.

However, you must not write:

```java
// Insufficient idea for safety:
Map<Type, Object> values;
```

and claim it is already type-safe.

Why?

1. `Type` describes a generic declaration/type schema; **it does not validate an arbitrary object on its own**.
2. `Type` provides no general `cast` like `Class<T>` to check `List<String>` at runtime.
3. A caller could insert a mixed `List<Object>` into the map if the API uses unchecked casts.
4. If `List<String>` is required, a validator must iterate elements and check `String` against the schema, or rely on a deserializer with explicit validation.

Therefore separate:

- **Class-key registry**: simple runtime class relationship; uses `Class.cast`.
- **Generic type-key registry**: keys retain `Type` structure and require stricter validation models and trust boundaries.

Do not build a `get(Type)` API returning unchecked `<T> T` and call it safe merely because the key contains the text `List<String>`.

## 19. Identity issues: Class objects, class loaders, and modules

`Class` objects are bound by the JVM to **runtime type definitions**. Two classes with the same binary name defined by different class loaders can be **two distinct runtime classes**.

This matters in plugin registries:

- Do not use `Class.getName()` as a reliable substitute for class identity.
- `Class.cast` and `isAssignableFrom` check real type relationships rather than merely comparing name strings.
- `Map<Class<?>,Object>` uses class tokens as keys via `Class`'s `equals/hashCode`, tied to runtime class identity.
- If a plugin is unloaded/reloaded with a new class loader, old tokens and entries do not automatically become tokens of the new class.

**Class-loader leaks:** a long-lived singleton registry holding plugin `Class<?>` keys or plugin instance values can keep the class loader/plugin from being garbage-collected. When plugin lifecycles exist, support scoped remove/close/clear and avoid holding references longer than needed.

This is a reference-lifecycle management issue, not a flaw in Generic type checking.

## 20. Ownership and mutability: type-safe does not mean immutable

Suppose a registry holds an `ArrayList` under the `List.class` token or a concrete class `ArrayList.class`. The caller receives a reference to **the exact object** stored in the map.

If that object is mutable, the caller can modify it:

```java
List<String> names = new ArrayList<>();
names.add("A");
registry.put(List.class, names); // Review generic API and raw List policy.
```

This is a discussion snippet, not a recommended pattern: using `List.class` only represents the raw interface and does not preserve `String` in the token. Do not use this example as proof that a `List<String>` was runtime-checked.

A better approach is designing registries to store **service objects or immutable configurations**, and specifying whether callers may mutate objects after `put`.

Possible policies include:

- Storing the reference as-is: fast, though caller mutations are visible through the registry.
- Creating defensive copies for suitable data types.
- Storing immutable value objects/records, or unmodifiable snapshots.
- Restricting access via the registry or read-only service APIs.

`Class<T>` guarantees **runtime type on put/get**, without automatically copying or making values immutable.

## 21. When should `ConcurrentHashMap` be used?

`HashMap` does not safely support unsynchronized concurrent mutations. If multiple threads can call `put`/`get`/`remove` on the same registry, choose a thread-safety strategy.

One option is:

```java
private final ConcurrentHashMap<Class<?>, Object> values =
        new ConcurrentHashMap<>();
```

Advantages:

- `get`, `put`, `putIfAbsent`, and `remove` support `ConcurrentHashMap`'s concurrency guarantees.
- Null keys/values are disallowed, fitting a no-null policy.
- Atomic operations exist for many cases such as `computeIfAbsent`.

Limitations:

- Map thread safety **does not make mutable value objects thread-safe**.
- If logic requires consistency across multiple keys or multiple steps, independent single-map operations do not guarantee a transaction.
- With `computeIfAbsent`, the mapping function should be short and must not update the map itself in ways that can cause errors or deadlocks.
- Do not assume every side effect in a factory runs at most once under arbitrary external failure/retry scenarios.

If the registry is only used in a single-threaded scope, `HashMap` may be sufficient and simpler.

## 22. Complete example: concurrent type registry

File **`ConcurrentTypeRegistryDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public class ConcurrentTypeRegistryDemo {

    static final class Registry {
        private final ConcurrentMap<Class<?>, Object> values =
                new ConcurrentHashMap<>();

        private static <T> Class<T> checkType(Class<T> type) {
            Objects.requireNonNull(type, "type");

            if (type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Primitive class tokens not supported");
            }

            return type;
        }

        <T> T registerIfAbsent(Class<T> type, T value) {
            type = checkType(type);
            Objects.requireNonNull(value, "value");

            Object previous = values.putIfAbsent(
                    type, type.cast(value));

            return type.cast(previous);
        }

        <T> T get(Class<T> type) {
            type = checkType(type);
            return type.cast(values.get(type));
        }

        <T> T getOrCreate(
                Class<T> type,
                Supplier<? extends T> factory) {

            type = checkType(type);
            Objects.requireNonNull(factory, "factory");
            Class<T> checked = type;

            Object found = values.computeIfAbsent(
                    checked,
                    ignored -> checked.cast(
                            Objects.requireNonNull(factory.get())));

            return checked.cast(found);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        System.out.println(
                registry.registerIfAbsent(String.class, "first"));
        System.out.println(
                registry.registerIfAbsent(String.class, "second"));

        System.out.println(registry.get(String.class));
        System.out.println(
                registry.getOrCreate(Integer.class, () -> 5));
        System.out.println(
                registry.getOrCreate(Integer.class, () -> 99));
    }
}
```

Compile/run:

```bash
javac ConcurrentTypeRegistryDemo.java
java ConcurrentTypeRegistryDemo
```

Stdout:

```text
null
first
first
5
5
```

Explanation:

- `putIfAbsent` only inserts `"first"` when the `String.class` token has no entry yet.
- Registering `"second"` returns the already-stored value `"first"` instead of overwriting.
- `computeIfAbsent` creates the `Integer` value when missing; the next call reads the existing value `5`.
- `Supplier<? extends T>` lets the factory return a compatible subtype.
- `Class.cast` verifies the class at write/read boundaries.

This is a sequential `main` run to produce deterministic stdout. Confirming correctness under real concurrency also requires proper stress testing and clear lifecycle design for service values.

## 23. Lazy factories and service registry scope

A class-key registry is often used in dependency injection or service locators:

```java
registry.put(Logger.class, logger);
registry.put(Clock.class, clock);
```

This is illustrative code; assume `Logger`/`Clock` are suitable and already initialized.

An API can choose:

- **Eager registration**: calling `put` with an already-created value.
- **Lazy creation**: `getOrCreate(token, supplier)` when the token has no value yet.
- **Per-request scope**: each request has its own registry.
- **Application scope**: one shared registry across the application's lifetime.

Scope choice strongly affects mutability and concurrency. An application-wide singleton registry may retain services longer than necessary. A per-request registry simplifies isolation, yet should not slow down the system if services are expensive to construct.

If **multiple configurations** are needed for the same class (e.g., two database connections), a class key alone cannot distinguish them; use named typed keys, qualifiers, or a scoped/qualified DI container.

## 24. `getRequired`: returning a clear error message when an entry is missing

An API `get(Class<T>)` returning `null` offers flexibility, though many applications want a missing service to be a configuration error.

You can add:

```java
<T> T getRequired(Class<T> type) {
    T value = get(type);

    if (value == null) {
        throw new IllegalStateException(
                "No registration for " + type.getName());
    }

    return value;
}
```

This is an illustrative method that must live inside a class defining `get(type)`.

Advantages:

- Callers do not have to unbox/dereference `null` manually.
- The message names the **missing class token**.
- Configuration errors are caught early.

Condition: the registry must forbid `null` values so that `null` strictly means "not registered". If `null` values are allowed, `containsKey` must be used to distinguish.

An alternative method:

```java
<T> Optional<T> find(Class<T> type)
```

is good when a missing entry is a normal state. Do not throw exceptions for an entirely expected "not found" case when the API can express it clearly with `Optional`.

## 25. Limitations of a class-key registry

Decision table:

| Need | Is `Map<Class<?>, Object>` suitable? | Notes |
|---|---|---|
| One service instance per runtime class token | Yes | `<T> get(Class<T>)` API is clear and safe |
| One `String` and one `Integer` together in the registry | Yes | Two distinct class keys |
| One value under an interface token and one under an implementation token | Yes | Two separate entries |
| Auto-finding subtypes from a base interface | Not automatically | Needs a resolver and ambiguity policy |
| Two `String` values named `first`, `last` | Insufficient | Add named typed keys/qualifiers |
| Distinguishing `List<String>` and `List<Integer>` | No | Shared `List.class`; needs generic type keys/schemas |
| Verifying `List<String>` contents at runtime | No | `Class.cast(List.class)` only checks raw `List` |
| Storing primitive data without boxing | Not directly | Values are reference objects |
| Concurrent reads/writes | Depends on backing map | Consider `ConcurrentHashMap` and value thread safety |
| Auto-instantiating objects from class tokens | Not automatically | Needs factory, constructor reflection, or DI |
| Guaranteeing immutable values | No | Needs separate contracts/copies |
| Sharing the same class across multiple class loaders | Not unified | Runtime `Class` identity depends on loader |

A good API should document these limitations so callers do not rely on overly broad assumptions about type safety.

## 26. Anti-patterns: raw `Class`, unchecked casts, and exposed backing maps

**Do not** expose the backing map externally:

```java
Map<Class<?>, Object> mutableBacking() {
    return entries;
}
```

Callers could write `entries.put(String.class, 123)` and break the invariant that public `put` tries to protect.

**Do not** use raw `Class` in the primary method:

```java
Object get(Class type)
```

This loses the generic link between token and result and forces callers to cast.

**Do not** write:

```java
<T> T get(Class<T> type) {
    return (T) entries.get(type);
}
```

and merely slap `@SuppressWarnings("unchecked")` on it to silence the warning. `Class.cast` expresses runtime validation more clearly.

**Do not** blindly use `Class.forName(userInput).newInstance()` for self-registration. Reflective construction has access errors, missing constructors, side effects, and security risks; even the old `Class.newInstance()` is not a recommended API.

**Do not** stuff multiple parameterized types under `List.class` and assume the map retains individual type arguments.

These mistakes often stay hidden when testing valid data, yet turn into bugs at legacy/unchecked boundaries or as designs grow.

## 27. Type safety does not hide semantic errors

A registry that is completely safe regarding runtime classes can still be **semantically wrong**.

Example:

```java
registry.put(Integer.class, 8080);
```

Type-wise, this is a valid `Integer`. Yet is it the HTTP port, user count, or retry count? If the system needs multiple distinct `Integer`s, `Integer.class` is not a clear enough key.

Similarly, a `Clock` service might be registered under `Clock.class` yet use the wrong timezone or a mock calendar for production logic. Class tokens only check object types; they do not verify semantic correctness.

When multiple pieces of information share the same class, use:

- Named typed keys (name + `Class<T>`).
- Qualifier annotations with a registry that handles them.
- Specialized value classes/records such as `Port`, `RetryCount`, `Timeout`.
- A DI container with proper scopes/qualifiers.

This is **clear semantic API design**, not a language limitation solvable by generic syntax.

## 28. Practice exercises: checking API choices

### Exercise 1 — Why is the field `Map<Class<?>, Object>`?

**Answer:** Each key belongs to a different class, and each value belongs to the corresponding class. There is no single shared `T` for the whole container; method-level `<T>` restores the relationship per operation.

### Exercise 2 — Does a mistyped `put` compile?

```java
registry.put(String.class, 42);
```

**Answer:** Invalid in normal typed code because generic inference cannot make `42` compatible with `String` for `Class<String>`.

### Exercise 3 — Does `get` require a cast at the caller?

```java
String s = registry.get(String.class);
```

**Answer:** No. The `<T> T get(Class<T>)` signature causes the compiler to infer `T = String`.

### Exercise 4 — Does `Class.cast` reject null?

**Answer:** No; `String.class.cast(null)` returns `null`. Use `Objects.requireNonNull` yourself if you want to forbid `null` values.

### Exercise 5 — With an entry for String, lookup by CharSequence?

**Answer:** `get(CharSequence.class)` does not automatically find `String.class`. They are distinct keys; it only returns a value if registered specifically under `CharSequence.class`.

### Exercise 6 — Can there be two distinct String entries under class keys?

**Answer:** No, if the map only uses `String.class` as the key; the new entry replaces the old one. Typed named keys/qualifiers are needed if you want both.

### Exercise 7 — Does `List<String>.class` exist?

**Answer:** No. Java does not produce a class literal for that parameterized type.

### Exercise 8 — Does `List.class.cast(...)` verify String elements?

**Answer:** Not yet. It only checks that the object is a `List`. Per-element checks or another decoder/schema are needed if required.

### Exercise 9 — Why not use `(T)` in the getter?

**Answer:** Casting to an erased type variable does not verify the concrete runtime class. `type.cast(...)` uses the caller's class token to check before returning.

### Exercise 10 — Does a concurrent registry solve thread safety of service objects?

**Answer:** No. `ConcurrentHashMap` protects map operations; mutable values still need their own concurrency mechanisms.

### Exercise 11 — Should `int.class` be a key for `Integer`?

**Answer:** No, per the example API. Use `Integer.class` as the key; `int.class` is a primitive token and does not perform boxing in `Class.cast`.

### Exercise 12 — What if both missing keys and null values are allowed?

**Answer:** Use `containsKey` or an explicit result type to distinguish them. `get == null` is not enough.

### Exercise 13 — How do plugin class loaders affect class keys?

**Answer:** Classes with the same name defined by different loaders have distinct runtime `Class` identities; keys do not automatically match.

### Exercise 14 — When should a registry be split into named keys?

**Answer:** When multiple values of the same runtime class must be distinguished by name, scope, or business qualifier.

### Exercise 15 — Can a class token be used to auto-instantiate via constructor?

**Answer:** Reflection can be used provided the class has a suitable constructor and proper access permissions, though a registry should not by default auto-create every class on a missing entry.

## 29. Production checklist

1. Write a clear contract: **at most one value per class token**, or are multiple keys needed?
2. Define policies for **null tokens, null values, and primitive class tokens**.
3. Ensure the backing map is **private**, exposing no other write path.
4. Use `<T> put(Class<T>, T)` and `<T> get(Class<T>)`.
5. Use `type.cast` at data boundaries when runtime validation is needed.
6. Specify whether `put` overwrites or uses `putIfAbsent`; should the old value be returned?
7. Design missing-key APIs: nullable `get`, `Optional` `find`, or throwing `getRequired`.
8. Distinguish interface keys from implementation keys — lookup is **by exact key**.
9. Do not assume `List.class` distinguishes generic arguments.
10. If `List<String>` and `List<Integer>` must both be stored, design generic `Type` keys with validators instead of unchecked casts.
11. For concurrent access, use appropriate maps/locks; protect mutable values too if needed.
12. If factories are lazy, check exceptions, nulls, and side effects.
13. Define lifecycle, clearing/removing when a scope or plugin ends.
14. Avoid retaining `Class` tokens from plugin loaders longer than necessary.
15. Do not conflate class type safety with qualifier or key semantics.
16. Write unit tests for **wrong types**, **missing keys**, **replacement**, **nulls**, **interface tokens**, and **repeated same-class keys**.
17. Do not silence compiler errors with raw types.
18. Document that `Class<T>` enables runtime class checking yet does not reify parameterized types.

## 30. Summary and references

**A heterogeneous container using `Class<T>` as keys** is a useful design when you want to hold multiple object types in the same container while callers still receive concretely typed results:

```java
registry.put(String.class, "text");
registry.put(Integer.class, 7);

String text = registry.get(String.class);
Integer number = registry.get(Integer.class);
```

At its core are the internal `Map<Class<?>, Object>` field and method-level type parameters linking **`Class<T>` with `T`**. `Class.cast` checks the runtime class on read/write paths, while the map must be kept private to preserve the invariant.

Yet this design is **not a type token for all parameterized types**: it does not distinguish `List<String>` from `List<Integer>` because both share `List.class`. Class keys also do not automatically solve multiple entries per class, subtype lookup, value mutation, null policies, or concurrency.

Choose a class-key registry when **runtime class identity** is genuinely the business key. If the problem requires named/qualified keys or nested generic schemas, use an extended abstraction along with corresponding validation.

Standard references:

- [Java SE 17 `Class<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `cast`, `isInstance`, primitive tokens, class identity.
- [Java SE 17 `Map<K,V>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): map key semantics, `put`, `get`, `containsKey`.
- [Java SE 17 `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thread-safe map operations and `computeIfAbsent`.
- [Java SE 17 `Optional<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): representing potentially absent results.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments and invariance.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): runtime limitations of Generics.
- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): why `List<String>` has no separate class literal.