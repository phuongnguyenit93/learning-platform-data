# Building `Box<T>`, `Pair<K,V>`, and a Generic Storage Interface in Java 17+

This lab builds a small yet complete model consisting of **`Box<T>`**, **`Pair<K,V>`**, and the **`Storage<K,V>` interface** along with an in-memory implementation. The goal is not merely "adding `<T>` so the code compiles," but designing **accurate type relationships, data immutability, operation contracts, responsibility boundaries, and testing** so it can scale into a real-world API.

After completing this lab, you will be able to:

- Create a generic class/record carrying **one** type parameter `T`, with a static generic factory and a generic instance method.
- Create `Pair<K,V>` with **two** independent type parameters, usable for key–value pairs.
- Declare the **generic interface `Storage<K,V>`**, where `K` is the key type and `V` is the value type; implement it using `LinkedHashMap<K,V>`.
- Choose `Optional<V>` to represent **not found**, distinguishing it from a `null` value.
- Keep internal data `private`, avoid leaking the mutable backing map, and provide a snapshot list that is **structurally** unmodifiable.
- Apply `K/V/T/R`, method type parameters, `? extends`/`? super`, type inference, and API design patterns without raw/unchecked casts.
- Write a standalone, runnable Java 17+ program with verifiable output; clearly distinguish compile-time contracts from checks that still must happen at runtime.

## 1. Problem Statement and Design Diagram

Suppose we need to manage keyed values, such as a list of users by ID or scores by name. We want a system with three components:

```text
Box<T>
  ├── value(): T
  ├── of(U): Box<U>                 (static generic factory)
  └── map(Function<T,R>): Box<R>   (value type transformation)

Pair<K,V>
  ├── key(): K
  └── value(): V

Storage<K,V>                        (contract decoupled from storage technology)
  ├── put(K, V)
  ├── find(K): Optional<V>
  ├── remove(K): Optional<V>
  ├── containsKey(K): boolean
  ├── size(): int
  ├── snapshot(): List<Pair<K,V>>
  └── isEmpty(): boolean           (default method)

InMemoryStorage<K,V> implements Storage<K,V>
  └── private LinkedHashMap<K,V>   (implementation detail)
```

An application can choose:

```java
Storage<Integer, Box<String>> users = new InMemoryStorage<>();
Storage<String, Integer> scores = new InMemoryStorage<>();
```

Both variables use the **same interface** but bind different types. For `users`, the compiler knows the key is `Integer` and the value is `Box<String>`; for `scores`, the key is `String` and the value is `Integer`.

**Do not equate generic storage with a database:** this version only stores data temporarily in RAM; it does not persist to files/SQL, does not guarantee transactions, does not guarantee thread safety, and does not deep-copy stored objects. Those capabilities require separate designs and contracts.

## 2. Choosing Meaningful Type Parameters

Common parameter names:

| Name | Meaning in this lab | Type relationship |
| --- | --- | --- |
| `T` | Type of the single value in `Box<T>` | `Box<String>` holds `String`, `Box<Integer>` holds `Integer` |
| `K` | Key type in `Pair<K,V>` and `Storage<K,V>` | Input to `put/find/remove/containsKey` |
| `V` | Value type in `Pair<K,V>` and `Storage<K,V>` | Input to `put`, element type in `Optional<V>` |
| `U` | Own type parameter of static factory `Box.of` | Avoids confusion with the class's `T` |
| `R` | New result type in `Box<T>.map` | Links callback result to `Box<R>` |

The names `K` and `V` **do not require two different runtime classes**. `Storage<String,String>` is completely valid. Similarly, `Box<Integer>` and `Box<String>` typically share the same runtime class `Box` due to **type erasure**, even though the compiler checks them as distinct parameterized types.

A good design chooses type parameters to express **data relationships that the compiler can enforce**. If everything were replaced with `Object`, callers would have to cast and risk late `ClassCastException` errors.

## 3. Building `Box<T>`: A Container-Level Immutable Generic Wrapper

In Java 17, a `record` lets us represent a structure holding a single value:

```java
import java.util.Objects;
import java.util.function.Function;

record Box<T>(T value) {
    Box {
        Objects.requireNonNull(value, "value");
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }

    <R> Box<R> map(Function<? super T, ? extends R> mapper) {
        return Box.of(Objects.requireNonNull(mapper, "mapper")
                             .apply(value));
    }
}
```

This is a **standalone declaration snippet**; the complete runnable program is in section 10 with declarations nested inside a class containing `main`.

### Why use `record Box<T>`?

A record automatically provides a component-based constructor, the `value()` accessor, `equals`, `hashCode`, and `toString` based on its components. We add a compact canonical constructor to **forbid `null`** because Box's contract in this example is "always holds a value."

```java
Box<String> name = Box.of("Java");
String text = name.value(); // "Java"
```

When using a record, references to component fields are fixed after creation (no setters). However, "immutable record" here means **immutable with respect to component references**: if `T` is a mutable `ArrayList`, the list's contents can still be modified through another alias. Records do not deep-copy component objects.

### Static factory with its own `<U>`

```java
static <U> Box<U> of(U value)
```

`U` is declared by the **`of` method itself**, not the `T` of record `Box<T>`. This is the right approach because a static method cannot directly reference the class's type variable `T` in a static context.

Callers can use type inference:

```java
Box<String> words = Box.of("hello");
Box<Integer> count = Box.of(42);
```

Or an explicit type witness when needed:

```java
Box<String> words = Box.<String>of("hello");
```

There is no need for, and you should not use, raw `Box`.

## 4. `Box<T>.map`: A Generic Method with a New Result Type

A wrapper is often more useful if it can transform the value inside:

```java
<R> Box<R> map(Function<? super T, ? extends R> mapper)
```

When `T = String`, a callback `String::length` yields `Integer`, so:

```java
Box<String> text = Box.of("Binh");
Box<Integer> length = text.map(String::length);
System.out.println(length.value()); // 4
```

Distinguish clearly:

- `T` belongs to record `Box<T>`, i.e., the callback input type for the current instance.
- `R` belongs to method `map`, i.e., the output type inferred by the method.
- `Function<? super T, ? extends R>` expresses a callback that can **consume a `T` value** and **produce an `R`-compatible value**.

`map` **does not mutate the original `Box<T>`**; it creates a new `Box<R>`. With the current implementation, `mapper` must not be `null`, and the mapper's result must not be `null` because `Box.of` invokes the null-forbidding constructor.

If you want to support "value present or absent," design a wrapper with different semantics or use `Optional<T>`. Do not silently change the current Box to nullable while keeping Javadoc claiming "always holds a value."

### Reading `? super T` and `? extends R` correctly

`? super T` is the callback's **consumer** relationship: a function accepting `Object` can also accept `String`. `? extends R` is the **producer** relationship: a function returning `Integer` can be used where a `Number` is expected.

These wildcards do not affect the runtime class of `Box`; they make the compile-time API more flexible without needing unchecked casts.

## 5. Building `Pair<K,V>`: Two Independent Components

A pair binds a key to a value:

```java
import java.util.Objects;

record Pair<K,V>(K key, V value) {
    Pair {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
    }
}
```

Caller:

```java
Pair<Integer, String> ticket = new Pair<>(7, "READY");
Integer id = ticket.key();
String status = ticket.value();
```

Using `K` for key and `V` for value makes the code immediately readable while preserving the type relationship:

```java
// DOES NOT COMPILE:
// Pair<Integer, String> wrong = new Pair<>("seven", 7);
```

Records automatically provide `equals`, `hashCode`, and `toString` based on their components. For example:

```text
Pair[key=7, value=READY]
```

**Important distinction:** `Pair<K,V>` is a **data carrier**, not the storage itself. A Pair can hold any pair of values; it does not implement lookup, updating, or key uniqueness guarantees. Those rules belong to the `Storage` interface and its implementation.

### Why does the constructor forbid null?

This lab deliberately chooses **non-null** keys and values because `Storage.find` returns `Optional<V>`: null is not used as "a stored value that happens to be null." This keeps the distinction between *absent* and *present* unambiguous.

This is an API contract choice, **not a default rule of Java Generics forbidding null**. Another `Pair<String,Integer>` type could certainly allow null if its author designed it that way.

## 6. Designing the `Storage<K,V>` Interface: Establishing the Contract Before Implementation

Definition:

```java
import java.util.List;
import java.util.Optional;

interface Storage<K,V> {
    void put(K key, V value);
    Optional<V> find(K key);
    Optional<V> remove(K key);
    boolean containsKey(K key);
    int size();
    List<Pair<K,V>> snapshot();

    default boolean isEmpty() {
        return size() == 0;
    }
}
```

This is a generic interface with two type parameters declared by the **interface**. `Storage<Integer, Box<String>>` causes every method to use `K` and `V` accordingly at compile time.

| Member | Input/return type | Contract chosen for this lab |
| --- | --- | --- |
| `put(K,V)` | Accepts exact K, V | Insert or overwrite value by key; reject null |
| `find(K)` | `Optional<V>` | Key present: return value; absent: `Optional.empty()` |
| `remove(K)` | `Optional<V>` | Remove key, return old value if present |
| `containsKey(K)` | `boolean` | Indicates whether key is currently stored |
| `size()` | `int` | Count of **distinct keys** currently stored |
| `snapshot()` | `List<Pair<K,V>>` | Return structurally unmodifiable snapshot list of entries |
| `isEmpty()` | `boolean` | Default method based on `size()==0` |

### Why doesn't the interface pick `HashMap` itself?

An interface should describe the **capabilities clients use**, while details of storing in RAM, a database, or a file belong to the implementation. If business code holds a variable:

```java
Storage<String, Integer> scores = new InMemoryStorage<>();
```

then later you can swap in another implementation, provided it adheres to the **same contract**. However, generic type safety does not automatically guarantee that two implementations share the same ordering, atomicity, or concurrency semantics; those requirements must be documented in the public contract.

### Why `Optional<V>`?

`Optional<V>` expresses a **potentially absent** result without using `null` as an ambiguous signal:

```java
Optional<Integer> maybeScore = scores.find("An");
int score = maybeScore.orElse(0);
```

To keep these semantics clear, this lab chooses to **forbid storing null values**. If a design allowed `null` as a valid value, `Optional.ofNullable(data.get(key))` could not distinguish "key exists with null" from "key does not exist." In that case, a different result type or a clearly defined policy would be required.

## 7. Implementing `InMemoryStorage<K,V>` with `LinkedHashMap`

An initial implementation:

```java
import java.util.*;

final class InMemoryStorage<K,V> implements Storage<K,V> {
    private final Map<K,V> data = new LinkedHashMap<>();

    @Override
    public void put(K key, V value) {
        data.put(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    @Override
    public Optional<V> find(K key) {
        return Optional.ofNullable(
                data.get(Objects.requireNonNull(key, "key")));
    }

    @Override
    public Optional<V> remove(K key) {
        return Optional.ofNullable(
                data.remove(Objects.requireNonNull(key, "key")));
    }

    @Override
    public boolean containsKey(K key) {
        return data.containsKey(
                Objects.requireNonNull(key, "key"));
    }

    @Override
    public int size() {
        return data.size();
    }

    @Override
    public List<Pair<K,V>> snapshot() {
        List<Pair<K,V>> entries = new ArrayList<>();

        for (Map.Entry<K,V> entry : data.entrySet()) {
            entries.add(
                    new Pair<>(entry.getKey(), entry.getValue()));
        }

        return List.copyOf(entries);
    }
}
```

**How it works:**

- `Map<K,V>` preserves the same type relationship as the interface; `put` calls require no casts.
- `LinkedHashMap` by default preserves **key insertion order** when iterating `entrySet()`. Updating the value of an existing key does not turn it into a new key in insertion-order mode.
- `private final Map<K,V> data` prevents callers from directly holding a reference to the backing map through the public API. `final` does not make the map immutable; it only fixes the **field reference** after initialization.
- `put` calls `Objects.requireNonNull` on both key and value to enforce the non-null policy at runtime.
- `Optional.ofNullable(data.get(key))` returns empty when the key is not found; since null values are forbidden, the behavior is unambiguous as long as the invariant holds.
- `remove` retrieves the old value and removes it; if the key is not found, it returns empty.
- `snapshot()` iterates over current entries, constructs **new `Pair<K,V>` instances**, and uses `List.copyOf` so callers cannot call `add/remove/set` on the returned list.

### Invariants to maintain

Implementation invariants:

1. **All stored keys and values are non-null**, enforced by all controlled public write paths.
2. `data` is never exposed as a mutable alias.
3. Each key appears at most once, according to `Map`/key equality and hash semantics.
4. `size()` equals the current number of entries in the map.
5. `find/remove` follow a consistent "not found" rule.
6. `snapshot()` is unaffected by subsequent structural changes after creation.
7. This class **does not claim thread safety**; concurrent operations are not automatically safe.

These invariants belong to program logic alongside compile-time generic type argument checks. If code deliberately uses **raw `Storage`**, unchecked casts, or reflection to break them, a polluted `Map<K,V>` can still fail later — Java Generics cannot stop every attempt to bypass the type system.

## 8. Invariance: `Storage<Integer,String>` Is Not `Storage<Number,Object>`

Java Generics are **invariant** in their type arguments. For example:

```java
Storage<Integer, String> typed = new InMemoryStorage<>();

// DOES NOT COMPILE:
// Storage<Number, Object> wider = typed;
```

This does not contradict `Integer extends Number` and `String extends Object`. If such an assignment were allowed, a caller could invoke `wider.put(3.14, new Object())` and break the `Storage<Integer,String>` promise.

Similarly:

```java
Storage<Integer, Box<String>> users = new InMemoryStorage<>();

// DOES NOT COMPILE:
// users.put("101", Box.of("An")); // key must be Integer
// users.put(101, Box.of(42));     // value must be Box<String>
```

**That is the benefit of a generic API**: the compiler rejects many invalid operations before execution.

Do not work around it with a raw cast or `(Storage)`: doing so discards type argument checking, leading to heap pollution and errors surfacing far from the violation site.

## 9. Generic Helper Method: Working with Any Storage Having Matching K and V

We can write a reusable method for all storages:

```java
static <K,V> void printAll(Storage<K,V> storage) {
    for (Pair<K,V> pair : storage.snapshot()) {
        System.out.println(pair.key() + " => " + pair.value());
    }
}
```

When called as:

```java
Storage<String,Integer> scores = new InMemoryStorage<>();
scores.put("An", 9);
printAll(scores);
```

the compiler infers `K=String` and `V=Integer`. This generic method **needs no specific knowledge** of `Integer` or `String`; it relies solely on the operations guaranteed by the interface.

With `Box<String>` as the value, `pair.value()` has compile-time type `Box<String>`. Printing the record directly uses its component-based `toString()`, though print formatting is a **helper choice**, not part of the storage contract.

### When to use wildcards?

If a helper only reads entries to print them without needing to relate parameter/return types, you can also write a wildcard variant:

```java
static void showUnknown(Storage<?,?> storage) {
    for (Pair<?,?> pair : storage.snapshot()) {
        System.out.println(pair.key() + " => " + pair.value());
    }
}
```

Here we accept a storage with unknown key/value types and only **read**; calling `storage.put` on `Storage<?,?>` with a concrete key/value is unsafe because the compiler does not know the wildcard captures.

If a method needs to connect the types of a source storage and a destination storage, use named type parameters and deliberate wildcards rather than `Object` everywhere.

## 10. Complete Java 17+ Program

Save as **`GenericStorageDemo.java`**. The entire program uses only the Java standard library, **with no external dependencies**:

```java
import java.util.*;
import java.util.function.Function;

public class GenericStorageDemo {
    record Box<T>(T value) {
        Box {
            Objects.requireNonNull(value, "value");
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        <R> Box<R> map(Function<? super T, ? extends R> mapper) {
            return Box.of(
                    Objects.requireNonNull(mapper, "mapper")
                            .apply(value));
        }
    }

    record Pair<K,V>(K key, V value) {
        Pair {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
        }
    }

    interface Storage<K,V> {
        void put(K key, V value);
        Optional<V> find(K key);
        Optional<V> remove(K key);
        boolean containsKey(K key);
        int size();
        List<Pair<K,V>> snapshot();

        default boolean isEmpty() {
            return size() == 0;
        }
    }

    static final class InMemoryStorage<K,V>
            implements Storage<K,V> {
        private final Map<K,V> data = new LinkedHashMap<>();

        @Override
        public void put(K key, V value) {
            data.put(
                    Objects.requireNonNull(key, "key"),
                    Objects.requireNonNull(value, "value"));
        }

        @Override
        public Optional<V> find(K key) {
            return Optional.ofNullable(
                    data.get(Objects.requireNonNull(key, "key")));
        }

        @Override
        public Optional<V> remove(K key) {
            return Optional.ofNullable(
                    data.remove(Objects.requireNonNull(key, "key")));
        }

        @Override
        public boolean containsKey(K key) {
            return data.containsKey(
                    Objects.requireNonNull(key, "key"));
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public List<Pair<K,V>> snapshot() {
            List<Pair<K,V>> result = new ArrayList<>();

            for (Map.Entry<K,V> entry : data.entrySet()) {
                result.add(
                        new Pair<>(entry.getKey(), entry.getValue()));
            }

            return List.copyOf(result);
        }
    }

    static <K,V> void printAll(Storage<K,V> storage) {
        for (Pair<K,V> pair : storage.snapshot()) {
            System.out.println(pair.key()
                    + " => " + pair.value());
        }
    }

    static void expectFailure(String title, Runnable operation) {
        try {
            operation.run();
            System.out.println(title + ": unexpected success");
        } catch (NullPointerException
                 | UnsupportedOperationException ex) {
            System.out.println(title + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Storage<Integer, Box<String>> users = new InMemoryStorage<>();

        System.out.println("Initially empty: " + users.isEmpty());

        users.put(101, Box.of("An"));
        users.put(102, Box.of("Binh"));

        System.out.println("User 101: "
                + users.find(101)
                       .map(Box::value)
                       .orElse("missing"));

        System.out.println("User 999: "
                + users.find(999)
                       .map(Box::value)
                       .orElse("missing"));

        System.out.println("Mapped length: "
                + users.find(102).orElseThrow()
                       .map(String::length).value());

        Pair<Integer,String> ticket = new Pair<>(7, "READY");
        System.out.println("Pair: " + ticket);

        List<Pair<Integer, Box<String>>> before = users.snapshot();

        users.put(103, Box.of("Chi"));

        System.out.println("Snapshot count: " + before.size());
        System.out.println("Storage count: " + users.size());

        System.out.println("Remove 101: "
                + users.remove(101)
                       .map(Box::value).orElse("missing"));

        System.out.println("Contains 101: " + users.containsKey(101));

        System.out.println("Remaining entries:");
        printAll(users);

        expectFailure("Null value",
                () -> users.put(999, null));
        expectFailure("Null key",
                () -> users.find(null));
        expectFailure("Snapshot mutation",
                () -> before.add(new Pair<>(9, Box.of("X"))));

        Storage<String,Integer> scores = new InMemoryStorage<>();
        scores.put("An", 9);
        System.out.println("Score: "
                + scores.find("An").orElseThrow());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 GenericStorageDemo.java
java GenericStorageDemo
```

**Standard output**:

```text
Initially empty: true
User 101: An
User 999: missing
Mapped length: 4
Pair: Pair[key=7, value=READY]
Snapshot count: 2
Storage count: 3
Remove 101: An
Contains 101: false
Remaining entries:
102 => Box[value=Binh]
103 => Box[value=Chi]
Null value: NullPointerException
Null key: NullPointerException
Snapshot mutation: UnsupportedOperationException
Score: 9
```

Key lines to understand:

1. Before `put`, `size()==0`, so the default `isEmpty()` returns `true`.
2. `find(101)` finds `Box<String>`; `Optional.map(Box::value)` extracts the string `"An"`.
3. `find(999)` returns `Optional.empty()`, so `orElse("missing")` evaluates to `"missing"`.
4. `Box<String>.map(String::length)` returns a `Box<Integer>` with value 4, leaving the original Box unmodified.
5. The Pair record has a `toString()` generated from its two components.
6. `before` contains two entries at the time of `snapshot()`; adding key 103 afterward brings storage `size()` to 3, while `before.size()` remains 2.
7. `remove(101)` returns the old value; `containsKey(101)` afterward is `false`.
8. `LinkedHashMap` preserves insertion order for the remaining keys: 102 then 103.
9. Both null operations are blocked by `Objects.requireNonNull`; mutating the snapshot list throws `UnsupportedOperationException`.
10. The same `InMemoryStorage<K,V>` implementation works for `Storage<String,Integer>` without casts.

The `expectFailure` helper is only for demonstrating expected exceptions; in professional tests, use proper assertions verifying that the **exact expected exception** is thrown and failing the test if the operation **does not throw**, rather than merely printing `unexpected success`.

## 11. Null, Empty, and Error Rules: Document Them Clearly

There is no default rule in Java Generics requiring `T`, `K`, or `V` to be non-null. It is a **deliberate contract** chosen for the classes in this lab.

For `Box<T>`:

- `new Box<>(null)` or `Box.of(null)` is rejected by the constructor with `NullPointerException`.
- `box.map(null)` is also rejected.
- In `box.map(...)`, if the mapper returns null, `Box.of` rejects the null result.
- `Box<T>` has no concept of empty; use `Optional<T>` if you need to represent "no value."

For `Pair<K,V>`:

- Both key and value must be non-null.
- The components may share the **same runtime class**; they are not required to differ.
- Pair does not enforce key uniqueness, sorting, or persistence.

For `Storage<K,V>`:

- `put` accepts non-null key and value; if the key already exists, it updates the value.
- `find`/`remove` return `Optional.empty()` if absent.
- `find(null)`, `remove(null)`, `containsKey(null)`, and `put(null,...)` are all invalid according to the implementation.
- `snapshot()` returns the pairs present at creation in a new list; clients cannot add/remove elements from the result.
- Storage does not guarantee deep cloning of value objects and is not inherently thread-safe.

**Document the contract with Javadoc** rather than forcing users to infer it from `Optional` or from the name `InMemoryStorage`.

## 12. Javadoc for a Generic Interface: Documenting Both Types and Behavior

A public interface can declare:

```java
/**
 * Stores non-null values under non-null keys.
 *
 * @param <K> key type, using its equals/hashCode semantics
 * @param <V> stored value type
 */
interface Storage<K,V> {
    /**
     * Inserts or replaces a value associated with a key.
     *
     * @param key non-null key
     * @param value non-null value
     * @throws NullPointerException if key or value is null
     */
    void put(K key, V value);

    /**
     * Looks up a value without removing it.
     *
     * @param key non-null key
     * @return present value, or empty if the key is absent
     * @throws NullPointerException if key is null
     */
    Optional<V> find(K key);

    // Other operations follow the same contract.
}
```

This is a **standalone declaration snippet illustrating Javadoc**; the runnable program in section 10 contains the full version of the interface. For a public API, add Javadoc for `remove`, `size`, `containsKey`, `snapshot`, ordering, and concurrency policy.

Syntax notes:

- `@param <K>`, `@param <V>` describe the interface's **type parameters**.
- `@param key`, `@param value` describe the method's **value parameters**.
- `@return` explains the empty/present semantics.
- `@throws` specifies failure conditions per contract.

Documentation is no substitute for **enforcing** the contract. If Javadoc states that null is forbidden, the implementation must check for it or use a data structure that consistently enforces the same policy.

## 13. Why Use `Map<K,V>` Instead of `Object[]` in the First Implementation?

An `Object[]` or raw `Map` implementation might require unchecked casts and complex invariant proofs. Here, `LinkedHashMap<K,V>` already provides a sufficiently typed API:

```java
private final Map<K,V> data = new LinkedHashMap<>();
```

The compiler protects calls such as:

```java
data.put(key, value);
V stored = data.get(key);
```

No `@SuppressWarnings("unchecked")`, no manual generic array creation, and no `(V)` cast in the getter are needed.

**Design rule:** choose a standard generic collection when it models the data accurately without introducing unnecessary business constraints. Only write low-level storage on `Object[]` when there is a genuine memory, algorithmic, or layout reason, and even then maintain invariants across all read/write paths while keeping cast scopes tight.

Type erasure still exists: if a caller deliberately uses raw `Storage` or reflection, they can partially bypass compile-time guarantees. That is not a reason to abandon generics in normal APIs.

## 14. `Pair<K,V>` vs. `Map.Entry<K,V>`: Which Should You Choose?

Java already provides `Map.Entry<K,V>` and `Map.entry(key,value)` for representing simple entries. So why have a dedicated `Pair<K,V>`?

**`Pair<K,V>` makes sense when:**

- Your problem needs a data carrier **independent of the Map concept**.
- You want clear component names like `key`/`value` or `first`/`second`.
- You want a record that is immutable in its component references with record-based `equals/hashCode/toString`.
- You want to add appropriate domain behavior and document key/value constraints.

**`Map.Entry<K,V>` makes sense when:**

- You are working directly with the `Map` API.
- You do not need a standalone Pair abstraction.
- You can use `Map.entry(k,v)` for a pair with a matching contract (this factory does not accept null).

**Do not equate `Map.Entry` obtained from `map.entrySet()` with an immutable snapshot.** Entries from a map view may reflect live data and have implementation-dependent rules for `setValue`/mutation; if you return them externally, check the specific contract. In our example, we create new `Pair` instances and wrap them with `List.copyOf` to avoid exposing a live `entrySet()` directly to callers.

## 15. Snapshots Are Structurally Immutable; the Object Graph May Be Mutable

Returning `List.copyOf(entries)` protects the output list from `add`, `remove`, and `set`; the list also does not change automatically when entries are later added to or removed from storage.

Consider a mutable value, however:

```java
Storage<Integer, List<String>> store = new InMemoryStorage<>();
List<String> original = new ArrayList<>(List.of("a"));
store.put(1, original);

List<Pair<Integer,List<String>>> snapshot = store.snapshot();
original.add("b");

System.out.println(snapshot.get(0).value()); // [a, b]
```

This code shows that a **structural snapshot is not a deep copy**. The `Pair` record holds a reference to the same `List<String>`; that list's contents can still be modified through `original`.

If your application requires a deep snapshot:

- You can require `V` to be an immutable type by contract (though Java generic bounds cannot generally express "every object of V is immutable").
- You can accept a copier `Function<? super V,? extends V>` or serializer to create appropriate copies, depending on the domain.
- You can transfer data into immutable domain records/DTOs whose mutable fields are controlled.
- You must also handle concurrency and consistency when reading the source.

An API should not promise a "fully immutable snapshot" solely because it returns a `List<Pair<K,V>>` created via `List.copyOf`.

## 16. PECS When Copying Between Two Compatible Storages

In the main example, `Storage<K,V>` maintains strict type relationships. For an operation that **only reads from a source and writes to a destination**, use-site variance can be applied:

```java
static <K,V> int copyEntries(
        Storage<K, ? extends V> source,
        Storage<K, ? super V> destination) {
    int count = 0;

    for (Pair<K, ? extends V> pair : source.snapshot()) {
        destination.put(pair.key(), pair.value());
        count++;
    }

    return count;
}
```

This is a **helper method snippet** using the already defined `Storage` and `Pair`. PECS relationships:

- `source` produces values read as `V` or a subtype of `V`, so it uses `? extends V`.
- `destination` consumes `V` values, so it uses `? super V`.
- `K` is kept as the same type parameter so keys from source can be passed to destination with the exact right type.

Valid example:

```java
Storage<String,Integer> small = new InMemoryStorage<>();
Storage<String,Number> wide = new InMemoryStorage<>();
small.put("a", 3);

int copied = copyEntries(small, wide);
```

This call is valid because `Integer` is a subtype of `Number`. However, **`Storage<String,Integer>` is still not a direct subtype of `Storage<String,Number>`**. It is the wildcards in the **helper signature** that allow these arguments to participate together in one operation.

One business note: `copyEntries` iterates over the source snapshot and overwrites if a key already exists in the destination. The return value `count` here is the number of entries successfully processed, **not the number of genuinely new keys added**. If destination shares keys or is the same instance as source, clarify semantics and side effects.

## 17. Comparing `Storage<K,V>` with `Storage<K,Box<V>>`

You have two viable design styles:

```java
Storage<Integer,String> direct = new InMemoryStorage<>();
Storage<Integer,Box<String>> wrapped = new InMemoryStorage<>();
```

In `direct`, values are strings. In `wrapped`, values are **wrappers with mapping capability and a non-null invariant**.

Neither choice is universally right:

- **Choose `Storage<K,V>` directly** if the Box abstraction adds no domain meaning and only forces callers to write `.value()`.
- **Choose `Storage<K,Box<V>>`** if the domain genuinely needs a wrapper layer: provenance, validation, normalized state, or transformations with their own contracts.
- With `Optional<V>`, do not automatically create `Box<Optional<V>>` unless the wrapper layers have clearly distinct meanings; excessive wrapping makes the API hard to understand.

This lab uses `Storage<Integer,Box<String>>` to demonstrate generic type composition; in production code, evaluate whether Box adds real design value.

## 18. Testing Edge Cases

Beyond the runnable program, a professional test suite should verify:

| Scenario | Expected outcome per contract |
| --- | --- |
| `new InMemoryStorage<>()` | `isEmpty()==true`, `size()==0` |
| First `put(k,v)` | `size` increments by one, `find(k)` returns `v` |
| `put(k,v2)` with existing key | `size` does not increase, `find(k)` returns `v2` |
| `find(missing)` | `Optional.empty()` |
| `remove(existing)` | Returns old value, key disappears |
| `remove(missing)` | `Optional.empty()`, size unchanged |
| `containsKey(existing)` | `true` |
| `null` key in put/find/remove/containsKey | `NullPointerException` |
| `null` value in put | `NullPointerException` |
| `Box.of(null)`, `new Pair<>(null,v)` | `NullPointerException` |
| `Box.map` with valid mapper | Creates new `Box<R>`, leaves old Box unchanged |
| `Box.map` with `null` mapper / returning `null` | `NullPointerException` |
| Snapshot before/after mutation | Prior snapshot retains entry count and key/value references from creation time |
| `snapshot().add(...)` | `UnsupportedOperationException` |
| Mutable value modified via alias | Snapshot may observe the updated state of that value object |
| `Storage<K,V>` with wrong K or V | Typed call rejected by compiler |
| Identical type arguments `K`, `V` | Still valid |
| Multi-threaded operations | No thread-safety guarantee from sample implementation |

With JUnit 5, you can use `assertThrows(NullPointerException.class, () -> storage.put(1,null))` and `assertEquals(...)`; however, JUnit is an external dependency outside the JDK and is not needed to run the program in section 10.

### Compile-time type testing

An intentionally invalid fixture might contain:

```java
// DOES NOT COMPILE, only to verify the compiler:
Storage<Integer,String> text = new InMemoryStorage<>();
text.put("not an Integer", "A");
text.put(1, 123);
```

If your API accidentally degrades `put(K,V)` to `put(Object,Object)`, these calls may cease to be rejected by the compiler — a sign that the **type contract has weakened** even though functional tests with valid data still pass.

## 19. Common Mistakes When Building Your Own Generic API

**Mistake 1 — Using raw `Storage`:**

```java
Storage raw = new InMemoryStorage();
raw.put("key", 3);
```

The code may compile with raw/unchecked warnings, but it loses the K/V type relationship. Use `Storage<String,Integer>` if that is the contract you want.

**Mistake 2 — Assuming `Pair<K,V>` requires K to differ from V:** no. `Pair<String,String>` is completely valid.

**Mistake 3 — Assuming `Box<T>` can declare `static T cache`:** no. A static context cannot use a class's type variable that way; a static factory must declare its own type parameter, like `static <U> Box<U> of(U)`.

**Mistake 4 — Creating `new T[n]` for generic storage:** illegal with non-reifiable type variables. Use standard generic collections whenever they meet your needs.

**Mistake 5 — Confusing `Storage<Integer,Box<String>>` with `Storage<Integer,String>`:** the value types differ; you cannot automatically coerce a Box into a String at compile time. To convert data, write an explicit mapping step.

**Mistake 6 — Calling `find` and assuming a value is always present:** `Optional<V>` may be empty. Use `orElse`, `ifPresent`, `map`, or `orElseThrow` with a clear error policy.

**Mistake 7 — Using null as a missing signal in an implementation that allows null values:** makes `Optional.ofNullable(data.get(k))` unable to distinguish missing from present-null. Pick a non-null invariant or a different result type.

**Mistake 8 — Exposing the backing map:** callers can mutate state outside methods that guard invariants. Here, the map is `private` and snapshots are built separately.

**Mistake 9 — Assuming `final Map<K,V>` means an immutable map:** `final` applies only to the field reference; the map's contents remain mutable.

**Mistake 10 — Assuming `List.copyOf` deep-copies every element:** no. Objects referenced by Pair/Box can still be mutable.

**Mistake 11 — Assuming the interface always dictates ordering:** insertion order is a choice made by `LinkedHashMap` in this implementation. If all implementations must guarantee the same order, put it into the **interface contract** and test it.

**Mistake 12 — Assuming thread safety because generics are used:** generic typing does not guarantee synchronization or visibility. Choose a concurrent implementation or manage synchronization if needed.

**Mistake 13 — Using an unchecked cast to bridge `Storage<K,V>` and `Storage<K,? super V>`:** you can usually write a typed PECS helper instead; casting is not a safe shortcut.

**Mistake 14 — Leaving `put` overwrite semantics unspecified:** with Map, the same key replaces the old value; API users need to know whether that is an update or a duplicate-key error.

**Mistake 15 — Making Box mutable unnecessarily:** if you only need a value passed between steps, a Box record immutable in its component reference is usually easier to reason about than a class with `set(T)`.

## 20. Guided Extension Exercises

### Exercise A — Add `putIfAbsent`

Extend `Storage<K,V>`:

```java
Optional<V> putIfAbsent(K key, V value);
```

Choose and document the contract: if the key does not exist, insert it and return empty; if it exists, keep it unchanged and return the old value. Use `Map.putIfAbsent` after null checks, while ensuring the implementation disallows storing null. Test that size stays unchanged when the key already exists.

### Exercise B — Create a Read-Only `Storage<K,V>`

If many callers only read, split out an interface:

```java
interface ReadOnlyStorage<K,V> {
    Optional<V> find(K key);
    boolean containsKey(K key);
    int size();
    List<Pair<K,V>> snapshot();
}
```

Then have `Storage<K,V>` extend `ReadOnlyStorage<K,V>`. This *interface segregation* approach prevents read-only code from depending on `put/remove`.

**Note:** a read-only interface does not itself guarantee an immutable backing storage — code holding a writable alias can still update the data. This is permission separation at the **API level**, not necessarily an immutable snapshot.

### Exercise C — Add `mapValues`

Design a helper:

```java
static <K,V,R> Storage<K,R> mapValues(
        Storage<K,V> source,
        Function<? super V, ? extends R> mapper)
```

The method should create a **new storage**, keep keys `K`, transform values `V` into `R`. Check that `mapper` is non-null, mapper results are non-null per `Storage`'s contract, and define ordering/side effects if `mapper` throws an exception.

### Exercise D — Verify Snapshot Behavior

Create a snapshot when two entries exist, add a new entry to storage, and verify the earlier snapshot still has two entries. Next, try a mutable list as the value to observe that the snapshot does not deep-copy. Document the two layers: **structural immutability** and **internal object state immutability**.

### Exercise E — Switch Implementation to Persistence

Try defining `FileStorage<K,V>` or `DatabaseStorage<K,V>` still implementing `Storage<K,V>`. Do not assume `put` is always cheap, atomic, or free of I/O failures. You must add an exception strategy, serialization/codec for K/V, transactions, and a concurrency policy in the contract.

## 21. Lab Evaluation Checklist

Before using this set of classes in a larger module, check yourself against these points:

1. **Are all three abstractions scoped properly?** Box holds one value; Pair carries two components; Storage defines storage behavior.
2. **Are type parameter names consistent?** Do `T`, `K`, `V`, `R`, `U` play their proper roles?
3. **Is the static generic factory declared correctly?** `static <U> Box<U> of(U)`, not using the class's `T` in a static context.
4. **Is the typed API free of unnecessary raw casts?** `Map<K,V>`, `Pair<K,V>`, `List<Pair<K,V>>` are explicit.
5. **Is the null policy clear?** No confusion between missing and present-null.
6. **Are update/remove semantics clear?** Same key overwrites; remove returns the value prior to deletion.
7. **Is snapshot a copy or a view?** In this lab it is a structural copy, not a deep copy.
8. **Is entry ordering required?** If needed as a public API guarantee, put it in the interface contract.
9. **Has polymorphism been tested?** Same interface used with `Integer/Box<String>` and `String/Integer`.
10. **Are there unit tests for edge cases?** Empty, duplicate key, null, wrong generic types, snapshot mutation, nullable mapper result.
11. **Are concurrency/persistence needed?** If so, design them beyond the sample generic interface.
12. **Is domain policy separated from storage logic?** Do not force a user-specific policy into `Storage<K,V>` if it applies only to one business entity.

## 22. Summary

`Box<T>`, `Pair<K,V>`, and `Storage<K,V>` illustrate three levels of using Java Generics: **wrapping a single type**, **relating two types**, and **building an implementation-independent behavioral contract**. `Box<T>` demonstrates a static generic factory and generic `map`; `Pair<K,V>` demonstrates two components of different types; `Storage<K,V>` uses the same type parameters across `put`, `find`, `remove`, and `snapshot`, while `InMemoryStorage` implements it via `LinkedHashMap<K,V>` without unchecked casts.

The key takeaway goes beyond `<T>` and `<K,V>` syntax: a good generic API must **preserve accurate type relationships at compile time**, **clearly state runtime conditions** (null, missing, update, order, mutation, ownership), **hide backing data**, and **test boundaries**. When those pieces align, abstractions can be reused and extended without forcing callers to rely on raw types or unchecked casts.