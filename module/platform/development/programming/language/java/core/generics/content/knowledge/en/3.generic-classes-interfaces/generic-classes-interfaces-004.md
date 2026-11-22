# Declaring Generic Interfaces and Type-Safe Contracts in Java

A **generic interface** is an interface that declares one or more **type parameters** right after its name, for example `interface Repository<ID, T>`. This interface describes operations with type relationships: the identifier key must have type `ID`, while the stored and returned data has type `T`. When using `Repository<Long, User>`, the compiler checks that the save method takes `Long` and `User`, while the lookup method returns `Optional<User>`.

Generic interfaces are especially useful when multiple data types share **the same contract**, and input and output types must remain consistent. This lesson focuses on declaration syntax, implementing with `implements`, extending via `extends`, the kinds of methods allowed in declarations, type bounds, and common mistakes. The complete example uses Java 17 or later.

## 1. Why Do We Need Generic Interfaces?

Suppose an application has a user store indexed by `Long` IDs and a product store indexed by `String` codes. If two independent interfaces are written, their signatures easily duplicate each other:

```java
interface UserStore {
    void save(Long id, User user);
    User findById(Long id);
}

interface ProductStore {
    void save(String code, Product product);
    Product findById(String code);
}
```

The short snippets in this lesson are **illustrative code within an appropriate context**; `User` and `Product` above are hypothetical business types, not complete Java files.

We can describe the common relationship using two type parameters:

```java
interface Repository<ID, T> {
    void save(ID id, T entity);
    java.util.Optional<T> findById(ID id);
}
```

`ID` is the key type; `T` is the entity type. Use the interface by passing **type arguments**:

```java
Repository<Long, User> users;
Repository<String, Product> products;
```

The compiler knows that `users.save` takes `(Long, User)`, while `products.save` takes `(String, Product)`. The names `ID` and `T` are simply Java type parameters, not two data variables or classes generated at runtime.

A non-generic version weakens the contract:

```java
interface WeakRepository {
    void save(Object id, Object entity);
    Object findById(Object id);
}
```

Here, callers must manually cast the found value and can mix up the key type with the data type. Generics helps shift many type errors from runtime to **compile time**. However, it does not automatically verify business rules such as whether an ID exists, whether an entity is valid, or whether a caller has permission to view data.

## 2. Declaration Syntax and How to Read the Contract

Single-parameter form:

```java
interface Holder<T> {
    void set(T value);
    T get();
}
```

Multi-parameter form:

```java
interface Dictionary<K, V> {
    void put(K key, V value);
    V get(K key);
}
```

| Element | Meaning |
| --- | --- |
| `interface Holder<T>` | **Declares** type parameter `T` in the interface scope |
| `Holder<String>` | **Uses** the interface with type argument `String` |
| `interface Dictionary<K,V>` | Declares two type parameters, with key and value roles |
| `Dictionary<Long,String>` | Binds `K = Long`, `V = String` for a specific reference |
| `new MemoryDictionary<>()` | Diamond operator `<>` relies on context to infer the constructor's type arguments |

In `Holder<String>`, the compiler views `get()` as a method returning `String`; in `Holder<Integer>`, that method returns `Integer`. There is no need to cast `Object` manually when calling through a fully typed reference.

Common names are `T` (type), `E` (element), `K` (key), and `V` (value). If a problem involves multiple types, a name that clearly expresses a role such as `ID` is also valid. Do not use ambiguous names that make it hard for callers to infer the contract.

**Remember:** standard Java generic parameters are reference types. `Repository<long, User>` is invalid; use `Repository<Long, User>`. Boxing/unboxing can occur when passing primitive numbers to positions expecting wrappers.

## 3. Complete Java 17+ Program

The following program illustrates the same interface for a user store (`Long` -> `User`) and an inventory store (`String` -> `Integer`). The read contract is separated from the write contract; the `exists` method is a `default` method. The `Converter<I,O>` interface illustrates a separate generic method inside a generic interface.

Save under the exact filename **`Main.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Main {
    record User(long id, String name) {}

    interface ReadRepository<ID, T> {
        Optional<T> findById(ID id);

        default boolean exists(ID id) {
            return findById(id).isPresent();
        }
    }

    interface Repository<ID, T> extends ReadRepository<ID, T> {
        void save(ID id, T entity);
    }

    static final class InMemoryRepository<ID, T>
            implements Repository<ID, T> {
        private final Map<ID, T> entries = new LinkedHashMap<>();

        @Override
        public void save(ID id, T entity) {
            entries.put(
                    Objects.requireNonNull(id, "id"),
                    Objects.requireNonNull(entity, "entity"));
        }

        @Override
        public Optional<T> findById(ID id) {
            return Optional.ofNullable(entries.get(id));
        }
    }

    @FunctionalInterface
    interface Converter<I, O> {
        O convert(I input);

        default <R> Converter<I, R> andThen(
                Converter<? super O, ? extends R> next) {
            Objects.requireNonNull(next, "next");
            return input -> next.convert(convert(input));
        }
    }

    public static void main(String[] args) {
        Repository<Long, User> users = new InMemoryRepository<>();
        users.save(101L, new User(101L, "Lan"));

        System.out.println("user: "
                + users.findById(101L)
                        .map(User::name)
                        .orElse("not found"));
        System.out.println("exists 999: " + users.exists(999L));

        Repository<String, Integer> stock = new InMemoryRepository<>();
        stock.save("SKU-01", 7);
        System.out.println("stock: "
                + stock.findById("SKU-01").orElse(-1));

        Converter<String, Integer> count = String::length;
        Converter<String, String> label =
                count.andThen(n -> "length=" + n);

        System.out.println("length: " + count.convert("Java"));
        System.out.println("label: " + label.convert("Java"));

        // users.save("101", new User(101L, "Lan"));
        // Wrong ID type: Repository<Long,User> requires Long.
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
user: Lan
exists 999: false
stock: 7
length: 4
label: length=4
```

### Why Does This Program Enforce the Type Contract?

- `Repository<Long,User>` means `save` requires a `Long` and a `User`; `findById` returns `Optional<User>`. The line passing `"101"` (type `String`) is commented out because it **does not compile** if enabled.
- `Repository<String,Integer>` uses **the same definition** `Repository<ID,T>` and **the same implementation class** `InMemoryRepository<ID,T>`, but with different type arguments; `findById("SKU-01")` returns `Optional<Integer>`.
- `InMemoryRepository<ID,T>` keeps both type parameters when it `implements Repository<ID,T>`; it stores data in `Map<ID,T>` and uses `@Override` so the compiler verifies that signatures properly implement the interface.
- `ReadRepository<ID,T>` defines the read API; `Repository<ID,T>` inherits it via `extends`. The `default exists(ID)` method operates according to the exact ID type of the parameterized repository.
- `Converter<I,O>` maintains the relationship between input and output types. `count` has type `Converter<String,Integer>`; `count.andThen(...)` creates a `Converter<String,String>` via a step transforming the result from `Integer` to `String`.

`InMemoryRepository` is only an in-memory example; it does not represent a database-accessing repository and does not by itself guarantee transactions or thread safety. The rule disallowing `null` keys and entities comes from `Objects.requireNonNull` in the **implementation**, not from the `<ID,T>` syntax.

## 4. Two Ways to Implement a Generic Interface

### 4.1. The Implementing Class Keeps the Type Parameters

```java
interface Store<K, V> {
    void put(K key, V value);
    V get(K key);
}

class MemoryStore<K, V> implements Store<K, V> {
    private final java.util.Map<K, V> data =
            new java.util.HashMap<>();

    @Override
    public void put(K key, V value) {
        data.put(key, value);
    }

    @Override
    public V get(K key) {
        return data.get(key);
    }
}
```

`MemoryStore<K,V>` remains a generic class. We can use `Store<String,Integer>` or `Store<Long,User>` without changing the class structure. The signatures of `put` and `get` must match the exact declared `K` and `V`.

### 4.2. The Implementing Class Fixes Concrete Types

```java
class StringIntStore implements Store<String, Integer> {
    private final java.util.Map<String, Integer> data =
            new java.util.HashMap<>();

    @Override
    public void put(String key, Integer value) {
        data.put(key, value);
    }

    @Override
    public Integer get(String key) {
        return data.get(key);
    }
}
```

`StringIntStore` has no `<K,V>` on the class name; it fixes `String` and `Integer` when declaring `implements Store<String,Integer>`. Therefore, the implementation must provide the corresponding methods:

- `public void put(String, Integer)`
- `public Integer get(String)`

You cannot quietly replace `put(String,Integer)` with `put(String,String)` and consider the required method implemented; the class would no longer satisfy the contract.

**Common rule:** abstract interface methods are declared `public` (except for special cases of other method kinds), so overriding methods in a class must be `public`. `@Override` helps detect wrong names, wrong parameters, and errors that keep a method from actually overriding.

If a class only implements part of an abstract contract, that class must be declared `abstract` so subclasses can supply the remaining implementations.

## 5. A Generic Interface Extending Another Interface

An interface can **extend** one or more interfaces via `extends`, while preserving or fixing type arguments.

**Preserving types across layers:**

```java
interface Reader<ID, T> {
    java.util.Optional<T> find(ID id);
}

interface Writer<ID, T> {
    void save(ID id, T item);
}

interface ReadWriteStore<ID, T>
        extends Reader<ID, T>, Writer<ID, T> {
}
```

With `ReadWriteStore<Long, User>`, `find` takes `Long` and returns `Optional<User>`, while `save` takes `Long,User`. Type relationships are propagated through each interface without rewriting every method.

**Fixing type arguments on a sub-interface:**

```java
interface IdLookup<T> {
    T find(long id);
}

interface UserLookup extends IdLookup<User> {
}
```

`UserLookup` no longer has a type parameter; it chooses `T = User`. A class implementing `UserLookup` must implement `User find(long id)` when no suitable implementation is inherited.

**Adding default behavior after specialization:**

```java
interface Sender<T> {
    void send(T message);
}

interface TextSender extends Sender<String> {
    default void sendUpperCase(String value) {
        send(value.toUpperCase(java.util.Locale.ROOT));
    }
}
```

`TextSender` inherits the `send(String)` contract and adds a string-specific operation. It does not define the destination itself; a class implementing `TextSender` must still provide `send(String)`.

An interface can extend multiple interfaces when signatures are compatible. If two interfaces provide conflicting `default` methods, the implementing class usually must override to resolve the conflict explicitly. A type cannot arbitrarily inherit two different parameterizations of the same generic interface, such as both `Comparable<String>` and `Comparable<Integer>`, because that can conflict due to type erasure.

## 6. Distinguishing Interface Type Parameters and Method Type Parameters

### 6.1. `T` Declared on the Interface

```java
interface Box<T> {
    void set(T value);
    T get();
}
```

An instance viewed through `Box<String>` uses `T = String` in both methods; `Box<Integer>` uses `T = Integer`. `T` belongs to **the entire instance contract**.

### 6.2. Method Declaring Its Own `<R>`

```java
interface Mapper<T> {
    <R> R map(
            T source,
            java.util.function.Function<? super T, ? extends R> function);
}
```

`T` is chosen when using `Mapper<T>`. In contrast, `R` can differ across calls to `map`. The `<R>` **must appear before the return type** `R`; it is the declaration of a separate generic method.

If you only need a generic algorithm in a single method and do not need to keep the same `T` across methods, you can declare a method-level generic inside a non-generic interface:

```java
interface Identity {
    <R> R same(R value);
}
```

Avoid naming a method's type parameter the same as the interface's type parameter if doing so obscures the meaning of another type parameter; for example, adding a new `<T>` at the method level inside `interface Box<T>` creates a separate `T`, easily misleading readers.

### 6.3. `default` Methods Use the Interface's Type

```java
interface Matcher<T> {
    boolean matches(T value);

    default boolean rejects(T value) {
        return !matches(value);
    }
}
```

`default` has a method body, inherited or overridden by implementing classes when needed. `rejects` still accepts the exact `T`. This is a way to share default behavior without forcing every implementation to duplicate the same logic.

In `Main.java`, `ReadRepository<ID,T>` has `default boolean exists(ID id)` calling `findById(ID)`. The type parameter does not change between the two calls, and implementations do not have to rewrite `exists`.

### 6.4. `static` Methods Declare Their Own Type Parameters When Needed

A static method on a generic interface cannot directly use the type parameter `T` belonging to an interface instance:

```java
interface Factory<T> {
    T create();

    static <R> Factory<R> of(
            java.util.function.Supplier<? extends R> source) {
        java.util.Objects.requireNonNull(source);
        return source::get;
    }
}
```

In `of`, `<R>` is the type parameter **of the static method**, whereas `T` belongs to the `Factory<T>` contract when using a factory instance. `Factory.of(() -> "ready")` can infer the type `Factory<String>`.

The following hypothetical snippet is an error:

```java
// Invalid: T is only declared on Factory<T>.
// static T createDefault() { ... }
```

Call static methods via the interface name (`Factory.of(...)`), not as an instance method inherited through an object implementing the interface.

## 7. Functional Interfaces Can Still Be Generic

A functional interface has a single functional abstract method, serving as a target type for lambdas or method references.

```java
@FunctionalInterface
interface Converter<I, O> {
    O convert(I input);
}
```

Type arguments ensure the lambda is checked against the exact signature:

```java
Converter<String, Integer> count = String::length;
Integer size = count.convert("Java");
```

`String::length` fits because it takes a string and returns `int` (autoboxed to `Integer`). If you write:

```java
// Does not compile:
// Converter<String, Integer> wrong = text -> text.toUpperCase();
```

then the lambda result is `String` while `O = Integer`, so the compiler rejects it.

`@FunctionalInterface` still permits `default` and `static` methods, because these methods do not count as additional abstract methods under the SAM (single abstract method) contract. For example, `Converter<I,O>` in `Main.java` has both abstract `convert` and default `andThen`.

**Composing converters:** the signature part

```java
default <R> Converter<I, R> andThen(
        Converter<? super O, ? extends R> next)
```

allows connecting the output of type `O` from the first step to the input accepted by the second step, returning a converter of type `I -> R`. `? super O`/`? extends R` are wildcards expressing the ability to accept compatible inputs and produce compatible outputs; they make the API more flexible while staying type-checked.

## 8. Constraining Types with `extends`

Not every type `T` is always suitable. If implementations need to call a specific method on entities, a generic interface can declare a **bound**:

```java
interface Identified<ID> {
    ID id();
}

interface EntityStore<ID, T extends Identified<ID>> {
    void save(T entity);
    java.util.Optional<T> findById(ID id);
}
```

`T extends Identified<ID>` ensures the entity type has an `id()` method returning the exact ID type. A record can satisfy the constraint:

```java
record Ticket(Long id, String title) implements Identified<Long> {}

class TicketStore implements EntityStore<Long, Ticket> {
    private final java.util.Map<Long, Ticket> values =
            new java.util.HashMap<>();

    @Override
    public void save(Ticket ticket) {
        values.put(ticket.id(), ticket);
    }

    @Override
    public java.util.Optional<Ticket> findById(Long id) {
        return java.util.Optional.ofNullable(values.get(id));
    }
}
```

If a type only implements `Identified<String>`, it cannot be chosen as `T` in `EntityStore<Long,T>` unless it also satisfies the appropriate bound. Bounds make the contract **stronger**: not just "the ID has type `Long`," but the entity must be able to provide an ID of that same type.

Multiple bounds can be declared when genuinely needed, for example `T extends Identified<ID> & java.io.Serializable`; if the list includes a class bound, the class must appear first followed by interface bounds.

**Do not add bounds just to make code look more complex.** If methods do not use the capability provided by the bound, consider keeping the contract simple.

## 9. A Type Contract Is Not the Same as a Behavioral Contract

`Repository<ID,T>` helps answer:

- What key and entity types must `save` accept?
- What data type does `findById` return?
- Does the implementing class properly override the methods?

But the interface **does not by itself decide**:

- whether `save` overwrites an old entity or rejects duplicate IDs;
- whether `findById` returns `Optional.empty()` when data is absent or raises an infrastructure error;
- whether `null` keys or values are allowed;
- whether data is persisted durably, transactional, or protected against concurrent access;
- how user read and write permissions are enforced;
- whether the passed ID matches the ID property inside the entity.

API authors must describe and enforce those rules in contracts/documentation, validation, and implementations. A generic interface is a **type contract understood by the compiler**, whereas business semantics require separate guarantees.

From a design standpoint, use interface-typed references when callers only need that contract:

```java
Repository<Long, User> users = new InMemoryRepository<>();
```

The benefit is easily swapping suitable implementations without callers depending directly on the internal `Map` structure. Still, having many ceremonial interfaces that do not express a shared contract often makes a project harder to read.

## 10. Invariance and Wildcards When Working Through Interfaces

Generics in Java are **invariant** by default. Suppose `Manager extends Employee`:

```java
Repository<Long, Manager> managers = null;
// Repository<Long, Employee> employees = managers; // Does not compile.
```

Reason: if the assignment were allowed, a caller through the `Repository<Long,Employee>` reference could save a non-`Manager` `Employee` into a store meant only for `Manager`s.

If only reading is needed, a more flexible variable type may be needed:

```java
ReadRepository<Long, ? extends Employee> readOnly = null;
```

A `ReadRepository<Long,Manager>` is eligible to be assigned to that broader read type, because the `readOnly` variable only knows the result is an unspecified subtype of `Employee`. The result of `findById` relates to `Optional<? extends Employee>`, though it cannot arbitrarily be assigned to `Optional<Employee>` due to `Optional`'s invariance.

When designing APIs, `? extends T` is usually useful where `T` is **produced/read**; `? super T` is usually useful where `T` is **consumed/written**. This guideline directs usage and does not replace checking each method's actual signature.

Raw types lose many checking capabilities:

```java
Repository raw = new InMemoryRepository();
```

Calling `raw.save(...)` may compile with an `unchecked` warning, opening the door to runtime type errors. Prefer `Repository<Long,User>` or declarations with appropriate type parameters. `Repository<?,?>` is better than a raw type when you only want to hold a reference with unknown types, though because the type arguments are unknown you cannot arbitrarily call `save` with arbitrary values.

## 11. Type Erasure and Runtime Limitations

Java implements generics primarily via **type erasure**. The compiler checks constraints at compile time, and afterward most type argument information is no longer present on runtime objects. `InMemoryRepository<Long,User>` and `InMemoryRepository<String,Integer>` both use the same runtime class `InMemoryRepository`, rather than generating a new JVM class per type pair.

You cannot write the following condition to fully check ID and entity types:

```java
// Does not compile:
// if (value instanceof Repository<Long, User>) { ... }
```

The syntax `value instanceof Repository<?, ?>` can check whether the object belongs to that interface type, yet **does not verify** that the actual arguments are `Long` and `User`.

If code receives data from JSON, reflection, raw collections, or legacy libraries, generic types do not replace boundary validation and type checking. JSON libraries may provide type references or schemas for parameterized types; specific APIs depend on the library.

### Bridge Methods

When a class implements a generic method with a concrete type, the compiler sometimes generates a **synthetic bridge method** to preserve polymorphism after erasure:

```java
interface Processor<T> {
    T process(T value);
}

class StringProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
```

You only need to implement `process(String)`; do not write bridge methods manually. This explains why inspecting bytecode or Reflection may show synthetic methods alongside the declared methods.

### Two Overloads Differing Only in Type Arguments Can Collide in Signature

```java
// Does not compile:
// interface Bad {
//     void handle(java.util.List<String> names);
//     void handle(java.util.List<Integer> numbers);
// }
```

After erasure, both take a `List` parameter; Java cannot distinguish those two overloads solely by generic arguments. The fix is to rename the methods meaningfully, design an appropriate generic method, or use two genuinely different parameter types.

A class also cannot arbitrarily implement the same generic interface with two different type arguments when that leads to an erasure conflict, such as both `Comparable<String>` and `Comparable<Integer>`.

## 12. Common Declaration and Implementation Mistakes

**Mistake 1 — Using `T` without declaring it:**

```java
// Invalid because T is not yet in scope:
// interface Broken { T get(); }

// Valid:
interface Holder<T> {
    T get();
}
```

**Mistake 2 — Forgetting to fix or forward type arguments on `implements`:**

```java
// Valid when the class is also generic:
class GenericHolder<T> implements Holder<T> {
    private T value;

    @Override
    public T get() {
        return value;
    }
}
```

For a non-generic class, a concrete type must be chosen, such as `implements Holder<String>`. Writing raw `implements Holder` discards type information and typically causes warnings/checking difficulties.

**Mistake 3 — Wrong method signature or reduced visibility in implementation:** if `implements Holder<String>`, the `get()` method must return `String` or a compatible return type under overriding rules, and must be `public`. It cannot be changed to `private`, nor can an overload taking different parameters count as a proper override.

**Mistake 4 — Putting a type parameter at the wrong level:** `<R>` on a method allows different result types across calls; `<T>` on an interface binds multiple methods to the same type. Choose the declaration level that matches the relationship.

**Mistake 5 — Calling a static method as an instance method:** `static` methods in an interface must be called via the declaring interface name; an interface's instance type parameter cannot directly appear in a static signature.

**Mistake 6 — Checking generic types with a concrete `instanceof`:** due to erasure, `instanceof Repository<Long,User>` is invalid. Use `Repository<?,?>` to check the interface type at runtime, then validate actual data if needed.

**Mistake 7 — Abusing `Object` or unchecked casts:** callers lose type guarantees, and errors can shift from compile time to runtime. Avoid `(T)` casts just to make an API look generic without a sound guarantee.

**Mistake 8 — Assuming an interface can be instantiated directly:** you cannot write `new Repository<Long,User>()` without an anonymous class body implementing all methods. You need an instance of an implementing class or another valid way to create an instance.

**Mistake 9 — Ignoring default behavior and null rules:** `default` methods contain concrete logic and must be evaluated against the implementation's semantics. `Optional<T>` also does not automatically make every `save` operation valid: null handling, permissions, or uniqueness are separate checks.

## 13. Knowledge Check

**Question 1.** For `Repository<String, Integer> stock`, what are the types of `save` and `findById`?

**Answer:** `save(String, Integer)`; `findById(String)` returns `Optional<Integer>`. These types are inferred directly from the two type arguments of the `stock` variable.

**Question 2.** Why is `class X<T> implements Holder<T>` valid, whereas `class X implements Holder<T>` is invalid if `T` does not exist in scope?

**Answer:** `X<T>` declares `T` at the class level; whereas `class X` declares no type parameter and has no other source providing `T`. You must keep `<T>` on the class or replace `T` with a concrete type.

**Question 3.** Can an interface be both `@FunctionalInterface` and have `default` methods?

**Answer:** Yes. A functional interface must satisfy the single functional abstract method rule; default and static methods do not count as additional abstract methods. In the example, `Converter<I,O>` has abstract `convert` and default `andThen`.

**Question 4.** Can `Repository<Long,Manager>` be assigned directly to `Repository<Long,Employee>` if `Manager` extends `Employee`?

**Answer:** No, because generics are invariant by default. The assignment would allow the recipient to write an `Employee` that is not a `Manager` into a repository intended for `Manager`s.

**Question 5.** Why is `EntityStore<ID,T extends Identified<ID>>` stronger than `Repository<ID,T>`?

**Answer:** The bound requires `T` to be capable of providing an ID of the same type `ID`, so implementations can call `entity.id()` and get back an ID of the exact type. `Repository<ID,T>` does not by itself require entities to have such a method.

**Question 6.** Can a generic interface confirm all type arguments at runtime using `instanceof`?

**Answer:** No. Java generics primarily uses type erasure; you can check `Repository<?,?>`, but cannot check `Repository<Long,User>` with a normal `instanceof`. External data still requires validation against an appropriate schema/contract.

## Conclusion

Generic interfaces allow describing contracts **by type relationships**, such as `Repository<ID,T>`, instead of forcing every method to take and return `Object`. When a class `implements` an interface or an interface `extends` another interface, type parameters can be **preserved, specialized, or further constrained**. This supports implementation reuse, early detection of type mismatches, and swapping implementations behind a stable API. When designing, separate interface-level and method-level type parameters, use `default`/`static` appropriately, and clearly state the business guarantees that Java's generic type system does not enforce on its own.
