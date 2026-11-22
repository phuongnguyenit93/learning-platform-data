# Relationship Between Generic Classes and Generic Interfaces in Java

In Java, a **generic class** can `implements` a **generic interface**, or `extends` another generic class. When inheriting, the subclass must **preserve**, **forward**, or **fix** the type parameters according to the declaration syntax. In doing so, the method type contract is maintained from interface to implementation and to the call site.

For example, `Store<K,V>` defines the ability to store data by key. `MapStore<K,V> implements Store<K,V>` preserves both type parameters for reuse, whereas `UserStore extends MapStore<Long,User>` fixes the key–value type pair for a specific domain. Each approach directly affects the method signatures that the compiler accepts.

After this lesson, you will be able to explain the relationship between generic `class` and `interface`, distinguish parameter-preserving inheritance from specialization, properly apply `@Override`, read signatures across multiple inheritance levels, and recognize errors involving type invariance, type erasure, and raw types. All complete examples use Java 17 or higher.

## 1. Three Relationships to Distinguish

In Java, the following declarations express three distinct relationships:

```java
interface Reader<K, V> {
    V read(K key);
}

interface Store<K, V> extends Reader<K, V> {
    void put(K key, V value);
}

class MemoryStore<K, V> implements Store<K, V> {
    private final java.util.Map<K, V> map = new java.util.HashMap<>();

    @Override
    public void put(K key, V value) {
        map.put(key, value);
    }

    @Override
    public V read(K key) {
        return map.get(key);
    }
}
```

1. `Store<K,V> extends Reader<K,V>`: an **interface extending another interface** and adding to the contract.
2. `MemoryStore<K,V> implements Store<K,V>`: a **class implementing an interface** and having to provide the required abstract methods.
3. `class Specialized extends MemoryStore<String,Integer>`: a **class extending another class**, which can fix the superclass's type arguments.

The keyword `extends` has two uses in inheritance structures: `class Child extends Parent` and `interface Sub extends Base`. `implements` is the relationship of a class implementing an interface. By contrast, `extends` in `T extends Number` serves as a **type parameter bound**; that is a different syntactic context.

**The symbols `K` and `V` in declarations are not class names or runtime variables.** They are type parameters. Meanwhile, `Store<String,Integer>` is a **parameterized type** with type arguments `String` and `Integer`.

## 2. Generic Interface Defines the Contract, Generic Class Implements the Contract

A generic interface describes methods in terms of type relationships:

```java
interface Repository<ID, ENTITY> {
    void save(ID id, ENTITY entity);
    java.util.Optional<ENTITY> findById(ID id);
}
```

The implementing class can preserve both type parameters:

```java
class MemoryRepository<ID, ENTITY>
        implements Repository<ID, ENTITY> {

    private final java.util.Map<ID, ENTITY> data =
            new java.util.HashMap<>();

    @Override
    public void save(ID id, ENTITY entity) {
        data.put(id, entity);
    }

    @Override
    public java.util.Optional<ENTITY> findById(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

`MemoryRepository<ID,ENTITY>` **redeclares the two parameters with the same roles on the class itself**, and **passes them** into `Repository<ID,ENTITY>`. Naming them `ID` and `ENTITY` like the interface improves readability, yet **type arguments are not required to share the same names**:

```java
class AlternateStore<K, V> implements Repository<K, V> {
    private final java.util.Map<K, V> data = new java.util.HashMap<>();

    @Override
    public void save(K key, V value) {
        data.put(key, value);
    }

    @Override
    public java.util.Optional<V> findById(K key) {
        return java.util.Optional.ofNullable(data.get(key));
    }
}
```

`K` corresponds to `ID`, and `V` corresponds to `ENTITY`. **Type parameter names do not define the inheritance relationship**; compatibility comes from type argument positions and method signatures.

When declaring:

```java
Repository<Long, String> repo = new MemoryRepository<>();
repo.save(1L, "ready");
java.util.Optional<String> found = repo.findById(1L);
```

the compiler treats `save` as accepting `(Long,String)` and `findById` as returning `Optional<String>`. `new MemoryRepository<>()` uses the **diamond operator** to infer type arguments from context; it is not a raw type.

### Which Methods Need to Be Implemented?

A **concrete** class implementing `Repository<ID,ENTITY>` must implement all abstract methods of the contract, unless they are already validly inherited from a superclass. `@Override` helps the compiler detect incorrect signatures. Methods implementing abstract interface methods must have `public` visibility:

```java
@Override
public void save(ID id, ENTITY entity) { ... }
```

Omitting `public`, swapping input types, or changing the return type incompatibly can cause the class to **fail to properly implement** the required method. If it does not yet provide all abstract methods, the class must be declared `abstract`.

A generic interface only specifies **data types** and the described signatures/behaviors. It does not automatically create storage, verify ID uniqueness, handle transactions, or become thread-safe by default.

## 3. Non-Generic Class Fixing the Interface's Type Arguments

If an implementation serves only a single data type, it can omit `<...>`:

```java
interface Sink<T> {
    void accept(T value);
}

class StringSink implements Sink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

`StringSink` has **specialized** `T` to `String`. The required signature is `accept(String)`. You do not need and should not declare `class StringSink<T>` if the class's domain is solely for strings.

The same applies with two type parameters:

```java
class UserRepository
        implements Repository<Long, User> {
    // Must implement save(Long, User)
    // and findById(Long) returning Optional<User>.
}
```

`User` is an illustrative domain type; the snippet above is only a **structural sketch** and would need actual method bodies to be a valid concrete class. In the complete runnable program in section 6, `UserStore` is specialized by extending a complete generic implementation.

### Fixing Part and Keeping Part

You can fix the key type while keeping the value type parameterized:

```java
class LongKeyRepository<T> implements Repository<Long, T> {
    private final java.util.Map<Long, T> data = new java.util.HashMap<>();

    @Override
    public void save(Long id, T item) {
        data.put(id, item);
    }

    @Override
    public java.util.Optional<T> findById(Long id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

`LongKeyRepository<T>` remains generic in `T`, yet **the key always has type `Long`**. Use `LongKeyRepository<Order>` or `LongKeyRepository<User>` depending on the domain object. `LongKeyRepository<String>` does not ask for the key type again upon instantiation.

Clearly distinguish **whether a class is generic** from **the parent/interface types the class chooses**: a class without `<T>` can still implement or extend a generic type with concrete type arguments.

## 4. Generic Class Extending a Generic Class Alongside `implements`

`implements Repository<K,V>` requires a **class** to fulfill an interface contract; `extends MemoryRepository<K,V>` **inherits from a class that already has an implementation**. The two relationships can combine: the subclass reuses the superclass's implementation, while the superclass's interface contract continues to apply after type argument substitution.

Using `MemoryRepository<ID,ENTITY>` declared in section 2, we have three forms:

```java
class AuditedRepository<K,V> extends MemoryRepository<K,V> {}
class LongKeyRepository<V> extends MemoryRepository<Long,V> {}
class FixedCounts extends MemoryRepository<String,Integer> {}
```

- `AuditedRepository<K,V>` forwards both K and V to the superclass; the subclass itself remains generic.
- `LongKeyRepository<V>` fixes the key type Long and keeps V variable.
- `FixedCounts` fixes both: `Repository<String,Integer>` is its interface contract through the superclass.

You do not need to rewrite `implements Repository<...>` if that relationship is already properly implemented by the superclass; if you add a new interface, the class must still satisfy all required methods of that interface. Constructors are not inherited and require appropriate `super(...)` calls when the superclass requires them. The declarations above are meant to compare **extending a class** with **implementing an interface**; the program in section 6 demonstrates actual stateful storage and overriding behavior.

## 5. Generic Interface Extending a Generic Interface

An `interface` can `extends` **multiple interfaces**:

```java
interface Reader<K, V> {
    V find(K key);
}

interface Writer<K, V> {
    void save(K key, V value);
}

interface ReadWrite<K, V> extends Reader<K, V>, Writer<K, V> {
}
```

`ReadWrite<String,Integer>` inherits both `find(String)` returning `Integer` and `save(String,Integer)`. Even though `ReadWrite` adds no methods of its own, it combines two type contracts.

Like a class, a subinterface can fix the type arguments of its superinterface:

```java
interface StringReader extends Reader<Long, String> {
}
```

Read as: `StringReader` has `find(Long)` returning `String`. The name `StringReader` here emphasizes the result type, not the key type.

An interface can also explicitly reorder type parameters:

```java
interface Flipped<V, K> extends Reader<K, V> {
}
```

When using `Flipped<String,Long>`, the inherited contract is `Reader<Long,String>`. **The declaration order of type parameters matters**; the compiler binds by position, not by variable name.

### Inheriting `default` Methods

```java
interface Reader<K, V> {
    java.util.Optional<V> find(K key);

    default boolean contains(K key) {
        return find(key).isPresent();
    }
}
```

A class implementing `Reader<String,Integer>` receives `contains(String)` if it does not override it, provided the implementation supplies `find(String)`. The `default` method uses the parent interface's type parameter under the chosen specialization.

If a class inherits two `default` methods with the same signature from two unrelated interfaces, Java may require an override to resolve the conflict. Making interfaces generic does not eliminate this conflict resolution rule.

## 6. Complete Java 17+ Program: `extends` and `implements` Working Together

Create the file **`Main.java`**. The example includes a read-only interface `Reader<K,V>`, a read/write interface `Store<K,V>`, a generic implementation class `MapStore<K,V>`, a fixed-type subclass `UserStore`, and a parameter-preserving subclass `CountingStore<K,V>`.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Main {
    record User(long id, String name) {}

    interface Reader<K, V> {
        Optional<V> find(K key);
    }

    interface Store<K, V> extends Reader<K, V> {
        void put(K key, V value);
    }

    static class MapStore<K, V> implements Store<K, V> {
        private final Map<K, V> data = new LinkedHashMap<>();

        @Override
        public void put(K key, V value) {
            data.put(
                    Objects.requireNonNull(key),
                    Objects.requireNonNull(value));
        }

        @Override
        public Optional<V> find(K key) {
            return Optional.ofNullable(data.get(key));
        }
    }

    static final class UserStore extends MapStore<Long, User> {
        void putUser(User user) {
            put(user.id(), user);
        }
    }

    static final class CountingStore<K, V> extends MapStore<K, V> {
        private int writes;

        @Override
        public void put(K key, V value) {
            super.put(key, value);
            writes++;
        }

        int writes() {
            return writes;
        }
    }

    public static void main(String[] args) {
        Store<String, Integer> stock = new MapStore<>();
        stock.put("SKU-01", 7);
        System.out.println("stock: "
                + stock.find("SKU-01").orElse(-1));

        UserStore users = new UserStore();
        users.putUser(new User(42L, "Lan"));
        System.out.println("user: "
                + users.find(42L).map(User::name).orElse("missing"));

        CountingStore<String, String> preferences =
                new CountingStore<>();
        preferences.put("theme", "dark");
        preferences.put("lang", "vi");
        System.out.println("writes: " + preferences.writes());
        System.out.println("theme: "
                + preferences.find("theme").orElse("-"));

        Reader<String, Integer> view = stock;
        System.out.println("reader: "
                + view.find("SKU-01").orElse(-1));

        // stock.put("SKU-01", "seven"); // Invalid: V must be Integer.
        // users.put("42", new User(42L, "Lan")); // Invalid: K must be Long.
    }
}
```

Using JDK 17 or higher, in the directory containing the file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Stdout output:

```text
stock: 7
user: Lan
writes: 2
theme: dark
reader: 7
```

**Explanation of each relationship:**

1. `Store<K,V> extends Reader<K,V>`: `find(K)` is the contract inherited from the parent interface; `put(K,V)` is added by the child interface.
2. `MapStore<K,V> implements Store<K,V>`: the generic class keeps both type parameters to implement the read and write contracts using `Map<K,V>`. The `@Override` methods have signatures compatible with the interface contract.
3. `UserStore extends MapStore<Long,User>`: the non-generic class fixes the parent's type pair. `put` is inherited with contract `(Long,User)` and `find` returns `Optional<User>`, so method `putUser(User)` can call `put(user.id(),user)` in a type-safe manner.
4. `CountingStore<K,V> extends MapStore<K,V>`: the subclass stays generic, overrides `put(K,V)`, and calls `super.put(...)`. Only after the storage call succeeds is the `writes` counter incremented.
5. `Store<String,Integer> stock = new MapStore<>()`: the variable is declared using the **interface**, while the object is instantiated with the implementation. Callers depend on the `Store` contract and do not need to know the class uses `LinkedHashMap` internally.
6. `Reader<String,Integer> view = stock`: interface `Store<String,Integer>` **is a subtype** of `Reader<String,Integer>` due to the `extends` relationship; variable `view` can only call methods visible on `Reader`.
7. The two intentionally erroneous commented lines illustrate that the compiler prevents type mismatches when calls go through references with explicit type arguments.

The `find` method uses `Optional` to represent that a key may not exist yet. That is an **API design decision**; generics do not choose `Optional` on their own. The example stores data in memory and is not thread-safe, nor does it represent transactions, persistence, or data access authorization.

## 7. Reading Effective Types Across Multiple Inheritance Levels

Consider the following chain:

```java
interface Source<T> {
    T read();
}

abstract class AbstractSource<T> implements Source<T> {
}

class TextSource extends AbstractSource<String> {
    @Override
    public String read() {
        return "hello";
    }
}
```

Type relationships by level:

```text
Source<T>
    ↑ implements
AbstractSource<T>
    ↑ extends (T = String)
TextSource
```

When viewing `TextSource` as `Source<String>`, the `read()` method returns `String`. `AbstractSource<T>` is declared `abstract` because it has not yet implemented `read()`, which is valid when implementing a generic interface without providing every method at an intermediate class.

**Not every class in the chain needs to be generic.** An intermediate class can preserve `T`, while the final class can fix `T = String` to represent a concrete domain.

If a generic superclass has a constructor taking `T`, the subclass must call `super(...)` with an appropriate value after choosing type arguments. Generic inheritance does not automatically generate constructors in subclasses.

### Forwarding Type Parameters Through Superclass and Interface

```java
interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
}

final class UserEntity extends Entity<Long> {
    private final Long id;

    UserEntity(Long id) {
        this.id = id;
    }

    @Override
    public Long id() {
        return id;
    }
}
```

`UserEntity` fixes `ID = Long` via superclass `Entity<Long>`, so it also satisfies `Identifiable<Long>`. At use sites:

```java
Identifiable<Long> entity = new UserEntity(5L);
Long id = entity.id();
```

You do not need and must not assume `UserEntity` implements `Identifiable<String>` just because both `Long` and `String` are `Object`.

## 8. Checking Overridden Method Signatures After Specialization

Suppose:

```java
interface Formatter<T> {
    String format(T value);
}
```

A class fixing `T = Integer` must implement the corresponding signature:

```java
class IntegerFormatter implements Formatter<Integer> {
    @Override
    public String format(Integer value) {
        return "value=" + value;
    }
}
```

The method `format(Integer)` is the implementation of the `Formatter<Integer>` contract. The following line **does not fulfill** that contract:

```java
// Invalid example when replacing the required method:
// public String format(String value) { return value; }
```

Even though the method name is still `format`, the `String` parameter is wrong. If a concrete class lacks a method with the exact signature, the compiler will require implementing the method or declaring the class `abstract`.

### Return Type Compatibility

Java permits **covariant return types** for appropriate reference return types. For instance, if an interface declares `Number read()`, an implementation can return `Integer`. However, generic containers are **invariant** by default, so you cannot deduce that a method declared to return `List<Number>` can be overridden to return `List<Integer>`.

`@Override` protects the author from accidentally creating a method with a different signature when intending to implement an interface or override a superclass method. It does not replace unit tests for business logic.

### Bridge Methods Due to Type Erasure

```java
interface Processor<T> {
    T process(T value);
}

class StringProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.strip();
    }
}
```

At the source level, the implementation writes `process(String)`. Java compiles generics primarily via **type erasure**, so the compiler may generate a **synthetic bridge method** to preserve polymorphic dispatch when the erased signatures differ. You do not need and should not write bridge methods manually; declare the proper generic signature and let the compiler handle bytecode details.

## 9. Limits of Substitutability: Class `extends` vs. Subtyping Between Generic Types

Suppose:

```java
class Animal {}
class Dog extends Animal {}
```

Even though `Dog extends Animal`, the following two types **have no direct subtype relationship**:

```java
java.util.List<Dog> dogs = new java.util.ArrayList<>();

// Does not compile:
// java.util.List<Animal> animals = dogs;
```

If this assignment were allowed, callers via `List<Animal>` could add an `Animal` that is not a `Dog` into a list that is actually meant only for `Dog`.

The same rule applies to interfaces you declare yourself:

```java
// In a context having Store<Long,Dog> dogs:
Store<Long, Dog> dogStore = null;

// Does not compile:
// Store<Long, Animal> animalStore = dogStore;
```

**Distinguish clearly:**

- `Store<K,V> extends Reader<K,V>` establishes a subtype relationship **between two interface declarations** under the same corresponding parameterization.
- `Store<Long,Dog>` and `Store<Long,Animal>` are two parameterizations of **the same generic interface**, which is invariant in its type arguments by default.

Because `Store<Long,Dog>` is a subtype of `Reader<Long,Dog>`, the assignment `Reader<Long,Dog> view = dogStore` is valid. However, you cannot jump to `Store<Long,Animal>` merely because `Dog extends Animal`.

### Using Wildcards According to Actual Needs

If an API **only reads** values belonging to the `Animal` family, it can be expressed as:

```java
Reader<Long, ? extends Animal> readOnly = dogStore;
```

Because `Reader` has no write operations, the wildcard `? extends Animal` allows using the read result as an `Animal`-compatible value after unwrapping `Optional`. If an API allows writing, the wildcard must be chosen carefully according to data flow direction; `? extends Animal` does not permit writing an arbitrary `Animal` into a `Store<Long, ? extends Animal>`.

The rule commonly called "producer extends, consumer super" (PECS) is guidance on read/write direction, not a mechanism that automatically turns generic types into covariant ones.

## 10. Type Parameter Bounds in Inheritance

When an interface needs to ensure an entity has an ID of the right type, it can declare a bound:

```java
interface HasId<ID> {
    ID id();
}

interface EntityRepository<ID, E extends HasId<ID>> {
    void save(E entity);
    java.util.Optional<E> find(ID id);
}
```

`E extends HasId<ID>` requires the entity type to provide an `id()` method returning the exact type `ID`. If a class preserves both type parameters, it must also satisfy the bound:

```java
class InMemoryEntityRepository<ID, E extends HasId<ID>>
        implements EntityRepository<ID, E> {

    private final java.util.Map<ID, E> data =
            new java.util.HashMap<>();

    @Override
    public void save(E entity) {
        data.put(entity.id(), entity);
    }

    @Override
    public java.util.Optional<E> find(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

If you write `class Broken<ID,E> implements EntityRepository<ID,E>`, the compiler rejects it because `E` is not bounded to ensure it is a valid subtype of `HasId<ID>`. The fix is to pass a concrete type meeting the bound or repeat the appropriate bound on the subclass declaration.

**A class cannot widen the bound of a parent's type parameter** in a way that breaks the parent's contract. When a subclass remains generic, ensure the type arguments passed to the superclass or interfaces satisfy all required bounds.

### Subclasses Can Add Stricter Bounds

Suppose `Box<T>` allows any reference type; a subclass can be more restrictive:

```java
class NumberBox<N extends Number> extends Box<N> {
    NumberBox(N value) {
        super(value);
    }

    double asDouble() {
        return get().doubleValue();
    }
}
```

`NumberBox<Integer>` is valid, while `NumberBox<String>` is rejected. The subclass chooses a narrower set of type arguments while still satisfying the general requirement of `Box<N>`.

## 11. Type Erasure and Inheritance Conflicts

Java uses **type erasure**: in bytecode, type variables are erased to their upper bound (or `Object` if unbounded), and the compiler inserts casts and bridge methods when needed. An instance of `MapStore<String,Integer>` does not have a distinct runtime class compared to `MapStore<Long,User>`; both share the runtime class `MapStore` in the program.

The following syntaxes are invalid:

```java
// Cannot check the exact type arguments:
// if (obj instanceof Store<String, Integer>) { ... }

// No class literal for a parameterized type:
// Store<String, Integer>.class
```

You can use `obj instanceof Store<?, ?>` to test whether an object belongs to a parameterization with **unknown type arguments**. It does not verify the inner key and value types.

### A Generic Interface Cannot Be Inherited with Two Different Type Arguments

The snippet below is **intentionally invalid**, because a class cannot simultaneously inherit two incompatible parameterizations of the same interface:

```java
interface Processor<T> {
    T process(T input);
}

interface StringProcessor extends Processor<String> {
}

interface IntegerProcessor extends Processor<Integer> {
}

// Does not compile:
// class Mixed implements StringProcessor, IntegerProcessor { ... }
```

`StringProcessor` requires `Processor<String>`; `IntegerProcessor` requires `Processor<Integer>`. After type erasure, the JVM cannot treat `Mixed` as implementing the same generic interface in two incompatible ways. You cannot solve this by adding two overloads `process(String)` and `process(Integer)` and claiming both interfaces are validly inherited.

### Methods with the Same Erasure

Within the same type, two overloads `void handle(List<String>)` and `void handle(List<Integer>)` have the same parameter shape `List` after erasure, so they clash. This is why you should not rely on type arguments to distinguish overloads when the runtime signatures are identical.

## 12. Raw Types, Unchecked Warnings, and Contract Loss Risks

When a class implements/extends a generic type while **omitting type arguments**, Java may treat it as a raw type for compatibility with legacy code:

```java
// Not recommended:
class LegacyStore extends java.util.HashMap {
}
```

`HashMap` has two type parameters, yet raw `HashMap` no longer carries concrete key/value contracts for many operations. When calling generic methods through a raw reference, `unchecked` warnings may appear; invalid data may only be detected upon retrieval and casting.

The same issue occurs with:

```java
java.util.Map<String, Integer> typed = new java.util.HashMap<>();
java.util.Map raw = typed;
raw.put("count", "not an integer"); // Unchecked warning.
```

Later reading `Integer count = typed.get("count");` can throw `ClassCastException` at runtime. Learning programs should use complete type arguments (`Map<String,Integer>`), restrict raw types to legacy integration boundaries, and validate data rather than suppressing warnings indiscriminately.

**`new HashMap<>()` is not a raw type.** The diamond lets the compiler infer type arguments; it differs from `new HashMap()`.

## 13. Common Mistakes and How to Fix Them

**Mistake 1 — Forgetting to forward the subclass's type parameter to the parent:** `class Child<T> extends Parent` is raw inheritance if `Parent` is generic. Use `extends Parent<T>` when preserving the same type relationship, or `extends Parent<String>` when fixing it.

**Mistake 2 — Using `T` without declaring `T`:**

```java
// Invalid:
// class Child extends Box<T> { }

// Valid when preserving T:
class Child<T> extends Box<T> {
    Child(T value) { super(value); }
}
```

**Mistake 3 — Wrong implementation signature after specialization:** with `implements Formatter<Integer>`, the method must accept `Integer` per the contract, not `String`. Use `@Override` and let the compiler verify.

**Mistake 4 — Treating type parameter names as if they must match the parent:** `class Child<A,B> implements Store<A,B>` is valid even though the interface declares `Store<K,V>`. What matters is **positional correspondence and bounds**, not names.

**Mistake 5 — Thinking generic `extends` automatically grants covariance:** `Dog extends Animal` does not imply `Store<Long,Dog> extends Store<Long,Animal>`. Wildcards or appropriate API designs are required when reading/writing at an abstract level.

**Mistake 6 — Inheriting one interface with two parameterizations:** for instance, both `Processor<String>` and `Processor<Integer>` on the same class is invalid. Separate roles or use a different interface.

**Mistake 7 — Overriding with an incompatible return type:** `Optional<Dog>` is not a subtype of `Optional<Animal>`; covariant return rules do not validate invariant generic wrappers.

**Mistake 8 — Dropping bounds in a generic subclass:** if the parent interface requires `E extends HasId<ID>`, a subclass keeping `E` must also ensure that bound.

**Mistake 9 — Confusing type erasure with no compiler checking:** generic information is checked primarily at compile time, yet raw types or unchecked casts can still break the contract. Do not rely on `instanceof Store<String,Integer>` to check full type arguments.

**Mistake 10 — Forgetting behavioral contracts:** inheriting signatures does not automatically guarantee persistence, immutability, thread safety, or authorization. Implementations and documentation must specify those guarantees.

## 14. When to Stay Generic and When to Specialize?

Choose a **generic class implementing a generic interface** when multiple data types need the same algorithm, for example `MapStore<K,V>` providing key-based storage operations for many type pairs.

Choose a **generic subclass extending a generic class** when adding common behavior while preserving the same type arguments, such as `CountingStore<K,V> extends MapStore<K,V>`.

Choose a **non-generic class fixing type arguments** when the domain needs an explicit contract, such as `UserStore extends MapStore<Long,User>` or `IntegerFormatter implements Formatter<Integer>`.

Choose a **specialized subinterface** when naming a specific API role, such as `interface UserReader extends Reader<Long,User>`; this remains an interface, without an implementation yet.

Avoid overusing inheritance just to rename types; consider composition when components only need to collaborate rather than forming an **is-a** relationship. Generic inheritance is most useful when the subclass genuinely **is a specialized version** of the parent type and adheres to the contract clients expect.

| Scenario | Declaration pattern |
| --- | --- |
| Subinterface preserving types | `interface Store<K,V> extends Reader<K,V>` |
| Generic class implementing interface | `class MapStore<K,V> implements Store<K,V>` |
| Subclass staying generic | `class CountingStore<K,V> extends MapStore<K,V>` |
| Subclass fixing types | `class UserStore extends MapStore<Long,User>` |
| Generic class fixing one type argument | `class LongKeyStore<T> implements Repository<Long,T>` |
| Subinterface fixing types | `interface UserReader extends Reader<Long,User>` |
| Intermediate class not yet fully implemented | `abstract class AbstractSource<T> implements Source<T>` |

## 15. Self-Check Exercises

**Question 1.** Given `interface Sink<T> { void accept(T x); }`, what is the right signature when `class Logger implements Sink<String>`?

**Answer:** `public void accept(String x)`. Type parameter `T` has been fixed to `String`, and the overriding method must have appropriate visibility.

**Question 2.** How does `class Child<T> extends Box<T>` differ from `class Child extends Box<String>`?

**Answer:** The first form keeps the subclass generic and forwards `T` to the superclass; the second form creates a non-generic subclass and fixes `String` for the superclass.

**Question 3.** Why can `Store<String,Integer>` be assigned to `Reader<String,Integer>`?

**Answer:** Because the declaration `Store<K,V> extends Reader<K,V>` establishes a subtype relationship between the two interfaces after applying the same pair of type arguments. Clients can view the store as a reader and invoke only the read API.

**Question 4.** If `Dog extends Animal`, can `Store<Long,Dog>` be assigned to a `Store<Long,Animal>` variable?

**Answer:** No. Generic types are invariant in their type arguments; if allowed, callers could store an `Animal` that is not a `Dog` into a store meant for `Dog`.

**Question 5.** Why is `class Broken<ID,E> implements EntityRepository<ID,E>` invalid when the interface's `E` is bounded by `HasId<ID>`?

**Answer:** Type parameter `E` on `Broken` lacks a suitable bound, so the compiler cannot guarantee it satisfies `E extends HasId<ID>`. You must declare the corresponding bound or use a concrete type satisfying the contract.

**Question 6.** Can a class implement both `Processor<String>` and `Processor<Integer>` through two different subinterfaces?

**Answer:** No, if both inheritance paths lead to the same generic interface with two incompatible parameterizations. Java rejects this due to type conflict and erasure.

**Question 7.** Does switching `MapStore<K,V>` to raw `MapStore` to avoid writing type arguments benefit type safety?

**Answer:** No. Raw types strip away most type-argument checking on operations and can lead to `unchecked` warnings or runtime `ClassCastException`.

## Conclusion

The relationship between **generic classes** and **generic interfaces** is established through `implements` and `extends`. Interfaces define type contracts; classes can preserve parameters (`MapStore<K,V>`), fix part of them (`LongKeyRepository<T>`), or fix all of them (`UserStore extends MapStore<Long,User>`), provided signatures and bounds are honored properly. Inheritance between type declarations does not automatically create subtype relationships between different parameterizations: Java generics remain invariant by default. Using `@Override`, checking bounds, and avoiding raw types helps preserve contracts from design to callers, while business and runtime requirements must be verified separately.