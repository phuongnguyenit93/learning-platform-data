# Shared `static` Members Across Parameterized Types in Java Generics

When a Java class declares `class Box<T>`, users can create `Box<String>`, `Box<Integer>`, or `Box<Customer>`. These usages have **different type contracts at compile time**, yet they do not create independent copies of the `Box` class in the JVM. Therefore, **a `static` field declared on `Box` is shared state** across objects of the same runtime class, regardless of which type argument they are parameterized with.

This is critical if you place object counters, caches, registries, or shared configurations in a generic class. If you mistakenly assume that `Box<String>` and `Box<Integer>` each own a separate copy of a `static` field, the program can miscount statistics, mix state across types, or suffer concurrency bugs. This lesson clarifies the rules for `static` fields and methods, *type erasure*, class initialization, the scope of `T`, and how to design `static` members safely.

## 1. How Do Instance Fields and `static` Fields Differ?

Example:

```java
class Box<T> {
    private final T value;
    private static int created;

    Box(T value) {
        this.value = value;
        created++;
    }

    T get() {
        return value;
    }

    static int createdCount() {
        return created;
    }
}
```

This is an **illustrative Java class declaration**, without `main` yet. The two fields have different lifetimes and owners:

- `value` is an **instance field**. Each `Box` object has its own `value` field. With a `Box<String>` reference, the compiler checks `value` against the `String` type argument through the constructor/getter; with `Box<Integer>`, the corresponding type is `Integer`.
- `created` is a **`static` field of the `Box` class**. `Box<String>` and `Box<Integer>` objects access the same `created` field belonging to the class definition loaded by the JVM. Every constructor invocation increments the counter, regardless of what type the new object holds.
- `createdCount()` is a **`static` method**. It reads the shared counter and is called via the class name: `Box.createdCount()`.

Distinguish the **type parameter `T`** from a **type argument at the use site**. `T` describes type relationships for appropriate instance members; it does not create a separate `static` memory space for each `T`.

| Declaration | Belongs to | Separated for each `Box<String>` and `Box<Integer>`? |
|---|---|---|
| `private T value;` | Each `Box` object | Each object has its own field; compiler checks against the parameterized type. |
| `private static int created;` | Runtime class `Box` | **No**; one shared field across all parameterizations of the same loaded class. |
| `T get()` | Instance method | Called on each object and uses its corresponding `T` type contract. |
| `static int createdCount()` | Runtime class `Box` | **No**; one shared method definition. |
| `static <U> Box<U> of(U value)` | Class method with its own type parameter `U` | One shared method; `U` is inferred independently for each call. |

## 2. Runnable Example: One Shared Counter for Multiple Type Arguments

Save the file **`SharedStaticDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedStaticDemo {
    static final class Box<T> {
        private static final AtomicInteger CREATED = new AtomicInteger();
        private final T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
            CREATED.incrementAndGet();
        }

        T get() {
            return value;
        }

        static int createdCount() {
            return CREATED.get();
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);
        Box<Double> third = new Box<>(2.5);

        System.out.println(first.get());
        System.out.println(second.get() + 1);
        System.out.println(third.get());
        System.out.println(Box.createdCount());
        System.out.println(first.getClass() == second.getClass());
        System.out.println(second.getClass() == third.getClass());
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 SharedStaticDemo.java
java SharedStaticDemo
```

Exact output (`stdout`):

```text
Java
18
2.5
3
true
true
```

**Why does it print `3`?** The constructor `Box(T value)` is called three times. All three calls increment the same `AtomicInteger CREATED`. There are no separate counters for `Box<String>`, `Box<Integer>`, or `Box<Double>`.

**Why does it print `true` twice?** When calling `getClass()` on all three objects, the JVM returns the same `Class` object representing the runtime nested class `SharedStaticDemo.Box`. Differences in type arguments are source-level type checks; that information does not make the JVM create three specialized runtime classes.

The example uses `AtomicInteger` so incrementing the counter is safe when constructors are called concurrently. For a strictly sequential program, `static int created; created++;` produces the same result, yet `created++` is not an atomic operation if multiple threads execute simultaneously. `AtomicInteger` **only protects the counter operation itself**, without automatically making every other member of the class thread-safe.

## 3. Why Do Parameterizations Share `static` Members?

Java implements most generics through **type erasure**. After compilation, an ordinary generic class is not duplicated into independent runtime classes for each type argument:

```java
// Illustrative snippet inside a method:
Box<String> strings = new Box<>("hello");
Box<Integer> numbers = new Box<>(42);
```

Both object creations instantiate objects of the same runtime class `Box`. Generic signatures are checked by the compiler and generic info in the `.class` file may remain in metadata for tools to read, yet the JVM does not maintain two copies of `static` state separately for `String` and `Integer`.

Relationship diagram:

```text
                   class Box<T>
                        |
                 JVM: class Box
                        |
             +----------+----------+
             |                     |
       static CREATED          static methods
             |
        one shared state
             |
      +------+------+ 
      |             |
Box<String>     Box<Integer>
instance A       instance B
own value        own value
```

The diagram above depicts **one runtime class and separate objects**, not separate JVM processes or memory spaces. The `Box` class is still compiled with generic metadata to support tools and type checking, yet there is no "per-type-argument `static` table".

One consequence is that the syntax `Box<String>.class` is invalid in Java; class literals use a type name representable at runtime, such as `Box.class`. Likewise, an `instanceof Box<String>` check is disallowed because the `String` argument cannot be checked directly via `instanceof` after erasure; `instanceof Box<?>` can be used if you only need to confirm the object belongs to the `Box` class.

## 4. `static` Member Initialization: Once per Defined Class

Consider:

```java
class Sequence<T> {
    private static int nextId = 1;

    static int newId() {
        return nextId++;
    }
}
```

This is an **illustrative class declaration**. Typical execution sequence in a normal environment:

1. The JVM loads/defines the `Sequence` class and prepares its `static` state according to JVM rules.
2. When an action triggers class initialization, `static` field initializers and `static` initializer blocks execute in declaration order.
3. `Sequence.newId()` shares `nextId` across all callers, regardless of whether the application intends the result for `Sequence<String>` or `Sequence<Integer>`.
4. Creating another `Sequence<U>` object with a different type argument **does not** re-run `static` initialization as a new "initialization for `U`".

Do not misunderstand this as "the entire JVM always has strictly one copy" under every circumstance. A class can be defined separately by different **class loaders**, and each such class definition has its own `static` state. In practice, the rule to remember is that **the same class defined by the same class loader shares `static` members**, regardless of Java Generics type arguments.

### Verifying `static` Initialization

Save the file **`InitializationDemo.java`**:

```java
public class InitializationDemo {
    static final class Token<T> {
        private static int created;

        static {
            System.out.println("Token initialized");
        }

        Token() {
            created++;
        }

        static int count() {
            return created;
        }
    }

    public static void main(String[] args) {
        Token<String> a = new Token<>();
        Token<Integer> b = new Token<>();
        System.out.println(Token.count());
    }
}
```

Run:

```bash
javac -encoding UTF-8 InitializationDemo.java
java InitializationDemo
```

`stdout`:

```text
Token initialized
2
```

The `static { ... }` block executes **once** when the `Token` class is initialized, before the first constructor runs. The two instantiations `Token<String>` and `Token<Integer>` do not result in printing `Token initialized` twice.

Note: **class loading**, **class linking**, and **class initialization** are distinct steps in the JVM. Not every operation mentioning a class name in source code necessarily triggers the `static` block immediately; for example, referencing a compile-time constant may not trigger initialization of the class declaring that constant. In the object-creation example above, class initialization takes place before the first constructor runs.

## 5. Why Is `static T shared` a Compilation Error?

If `T` is a class type parameter:

```java
class InvalidBox<T> {
    // private static T lastValue;       // Wrong
    // static T getLastValue() { ... }   // Wrong
    // static void print(T value) { ... }// Wrong if T belongs to the class
}
```

The erroneous lines are **intentionally commented out**. Java does not allow a `static` member to directly use the non-static type variable `T` declared on `InvalidBox<T>`.

Explaining by contradiction: if `static T lastValue` were allowed, there would be one shared field for both `InvalidBox<String>` and `InvalidBox<Integer>`. One side expects the field to be `String`, while the other expects `Integer`. The JVM could not guarantee both type contracts hold simultaneously for a shared field across all operations.

Distinguish this error from being unable to instantiate objects via `new T()`. Both relate to generics yet belong to two different rules: `static T field` misuses a type parameter in a static context; `new T()` is invalid because a type parameter lacks runtime constructor information after erasure, even inside an instance method.

### The Right Way: Choose a Concrete Type or the Method's Own Type Parameter

A `static` field can have a **concrete type independent of `T`**:

```java
class SafeBox<T> {
    private static long totalCreated;
    private final T value;

    SafeBox(T value) {
        this.value = value;
        totalCreated++;
    }

    static long totalCreated() {
        return totalCreated;
    }

    T get() {
        return value;
    }
}
```

The `totalCreated` field belongs to a single runtime class; it does not attempt to describe each object's `T` value.

If a `static` function needs to work with multiple kinds of values, **declare the method's own type parameter**:

```java
static <U> U identity(U input) {
    return input;
}
```

This snippet must sit inside a class. `<U>` belongs to no instance, so `identity("Java")` and `identity(42)` can share the same `static` method definition while the compiler still checks the type relationship between parameter and return value at each call site.

Merely renaming `T` to `U` is not the essence of the fix; what matters is placing **its own type parameter declaration list `<U>`** on the method signature.

## 6. Generic `static` Methods Have No Separate State per Type Argument

Consider two calls:

```java
String text = Toolbox.<String>identity("Java");
Integer count = Toolbox.<Integer>identity(21);
```

Suppose `Toolbox` declares `static <T> T identity(T input)`. On the first call, the compiler determines `T = String`; on the second call, `T = Integer`. However, **the `identity` method does not create two corresponding `static` variable areas**. Each call uses its own local variables and parameters for that invocation; any `static` members it accesses still belong to the declaring class.

### Example Combining a Generic Factory and Shared Static State

Save as **`FactoryCounterDemo.java`**:

```java
import java.util.Objects;

public class FactoryCounterDemo {
    static final class Box<T> {
        private static int count;
        private final T value;

        private Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
            count++;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }

        static int count() {
            return count;
        }
    }

    public static void main(String[] args) {
        Box<String> a = Box.of("spring");
        Box<Integer> b = Box.of(99);
        Box<String> c = Box.of("java");

        System.out.println(a.get().toUpperCase());
        System.out.println(b.get());
        System.out.println(c.get());
        System.out.println(Box.count());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FactoryCounterDemo.java
java FactoryCounterDemo
```

`stdout`:

```text
SPRING
99
java
3
```

Here:

- `Box<T>` is a generic class, while `static <U> Box<U> of(U value)` is a separate generic method.
- The compiler infers `U` for each call to `Box.of(...)`.
- The constructor increments the shared `count` after checking the value is non-`null`.
- `Box<String>` and `Box<Integer>` still share the same counter. The `of` method does not create a separate counter per `U`.
- The example uses `int count` for simplicity; that is only appropriate if there is no concurrent update requirement. Under multithreading, replace it with `AtomicInteger` or appropriate synchronization.

## 7. `static final` Members Are Also Shared

`static final` fields can represent shared configurations, constants, or references:

```java
class CacheBox<T> {
    static final String DEFAULT_NAME = "cache";
    static final int MAX_ENTRIES = 100;
}
```

Those fields **are not duplicated** into one `DEFAULT_NAME` for `CacheBox<String>` and another `DEFAULT_NAME` for `CacheBox<Integer>`. They belong to the `CacheBox` class.

Distinguish two meanings of `final`:

- With `static final int MAX_ENTRIES = 100`, the primitive value is fixed once assigned. This can also be a compile-time constant.
- With `static final List<String> ITEMS = new ArrayList<>()`, the `final` keyword only prevents reassigning the `ITEMS` reference; **the contents of the list can still be mutated** if that object permits modification. The list is shared state across all parameterizations of the class.

Example:

```java
import java.util.ArrayList;
import java.util.List;

class SharedMessages<T> {
    static final List<String> MESSAGES = new ArrayList<>();
}
```

This is an **illustrative class declaration**. If an object used as `SharedMessages<String>` adds an element to `MESSAGES` and another piece of code using `SharedMessages<Integer>` reads that list, they are looking at the exact same collection.

To prevent external code from accidentally mutating shared state, it is generally good practice to keep mutable `static` fields `private` and expose only controlled APIs. Do not treat `final` as a guarantee of deep immutability.

## 8. When Per-Type Statistics Are Needed: Design a Grouping Structure Yourself

There are problems that genuinely require counting boxes holding `String`, `Integer`, or another object type separately. **Java does not split `static` fields by generic argument**, so the application must pick an explicit grouping key.

One option is passing **`Class<T>`** as a type token at the API boundary, then using a `static` map keyed by `Class<?>`. The map field is still **one shared map**; groups are separated by keys in data, not by copies of the generic class.

### Example: Statistics Keyed by Runtime Class

Create the file **`PerClassStatsDemo.java`**:

```java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class PerClassStatsDemo {
    static final class TypedBox<T> {
        private static final Map<Class<?>, AtomicInteger> COUNTS =
                new ConcurrentHashMap<>();

        private final Class<T> type;
        private final T value;

        TypedBox(Class<T> type, T value) {
            this.type = Objects.requireNonNull(type, "type");
            this.value = type.cast(value);
            COUNTS.computeIfAbsent(
                    type, ignored -> new AtomicInteger()).incrementAndGet();
        }

        T get() {
            return value;
        }

        Class<T> type() {
            return type;
        }

        static int countFor(Class<?> type) {
            AtomicInteger count = COUNTS.get(type);
            return count == null ? 0 : count.get();
        }
    }

    public static void main(String[] args) {
        TypedBox<String> a = new TypedBox<>(String.class, "A");
        TypedBox<Integer> b = new TypedBox<>(Integer.class, 1);
        TypedBox<String> c = new TypedBox<>(String.class, "B");

        System.out.println(a.get() + c.get());
        System.out.println(b.type().getSimpleName());
        System.out.println(TypedBox.countFor(String.class));
        System.out.println(TypedBox.countFor(Integer.class));
        System.out.println(TypedBox.countFor(Double.class));
    }
}
```

Run:

```bash
javac -encoding UTF-8 PerClassStatsDemo.java
java PerClassStatsDemo
```

`stdout`:

```text
AB
Integer
2
1
0
```

Points to distinguish:

1. `COUNTS` is still just **one shared `static` field** of `TypedBox`.
2. Each key `String.class` or `Integer.class` gets its own counter **created by the program**.
3. `type.cast(value)` checks the object against the passed-in `Class<T>`. If the value is incompatible, the cast throws `ClassCastException`.
4. `computeIfAbsent` on `ConcurrentHashMap` together with `AtomicInteger` makes updating the counter safe when multiple threads create boxes concurrently; each box's `value` data is assigned once in the constructor.
5. `null` handling must be specified explicitly: `Class.cast(null)` returns `null` so it does not reject null by itself; if non-`null` values are required, add `Objects.requireNonNull(value)`.

**Limitation of `Class<?>`:** a type token like `List.class` only distinguishes the runtime class `List`, not `List<String>` vs. `List<Integer>`. If grouping by nested parameterized types is required, a richer token model must be used and its type representation explicitly specified; you cannot just call `getClass()` and infer all generic arguments after erasure.

## 9. `static` Members and Multithreading: Sharing Means Synchronizing Properly

If multiple threads concurrently create `Box<T>` objects of different types, every constructor still updates the same `static` counter. Simple example:

```java
static int count;

Box(T value) {
    this.value = value;
    count++;
}
```

This is **illustrative code placed inside a `Box<T>` class**, assuming the relevant declarations exist. `count++` consists of reading the value, adding, and writing back; that operation is **non-atomic**. Two threads can read the same old value and both write back the same new value, causing lost increments.

Solutions depend on the goal:

| Need | Common approach | Note |
|---|---|---|
| Exact counter under concurrent updates | `AtomicInteger.incrementAndGet()` or `AtomicLong.incrementAndGet()` | Atomic updates, though numeric types still have overflow limits. |
| High-contention counting prioritizing throughput | `LongAdder.increment()` | Suitable for statistics; `sum()` during concurrent updates is not a linearizable snapshot. |
| Keeping multiple fields consistent in a small transaction | `synchronized` or an appropriate lock | Making a single variable atomic is insufficient if multiple variables must change together. |
| Shared cache map | `ConcurrentHashMap<K,V>` | Atomicity of compound operations must be understood per the API contract. |
| State that does not need sharing | Instance field or method-local data | Reduces unnecessary sharing, lowering concurrency risk. |

A race condition cannot be resolved by changing `Box<String>` to `Box<Integer>`: generic type arguments do not separate `static` state.

### When Should `static` Not Be Used?

Do not use a `static` field merely to access data "from anywhere". Consider whether that data genuinely has a **class-level lifecycle** or belongs to each object, request, session, or individual task. If it belongs to each object, use an instance field `T value`. If shared configuration/dependencies are needed with an application-level lifecycle, manage them through service objects or dependency injection rather than implicitly storing mutable state in `static` fields.

## 10. `static` Members of Nested Classes and Generic Interfaces

### 10.1. `static` Nested Class Does Not Use the Enclosing Class's `T`

```java
class Outer<T> {
    static final class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }
    }
}
```

`Nested<U>` has **its own** type parameter `U`, rather than taking `T` from `Outer<T>`. When instantiating:

```java
// Illustrative snippet inside a method:
Outer.Nested<String> first = new Outer.Nested<>("A");
Outer.Nested<Integer> second = new Outer.Nested<>(2);
```

No `Outer<String>` object is needed to instantiate `Outer.Nested<String>`. Like the rule for `static` methods, a static nested class stands independent of the enclosing class's parameterization.

### 10.2. Generic Interfaces Also Have Shared `static` Methods

```java
interface Formatter<T> {
    String format(T value);

    static <U> U identity(U value) {
        return value;
    }
}
```

`Formatter<T>` uses `T` in the contract of the instance method `format(T value)`. Yet `identity` is a `static` method on the interface, so it declares its own type parameter `<U>`.

You can call `Formatter.identity("Java")`; there is no need to pick a `Formatter<String>` implementation and no way to use the interface's `T` directly to declare a static method. Fields declared in an interface are `public static final` by language rule, not instance fields tied to each parameterized type.

## 11. Distinguishing a Generic Class's Counter from Subclass Counters

The same `static` field declared on a parent class can be accessed by subclasses when access rights permit. Having two different subclasses inherit from the same generic class **does not automatically create new copies** of the parent class's `static` field.

Example:

```java
class Base<T> {
    protected static int total;

    Base() {
        total++;
    }
}

final class TextBox extends Base<String> { }
final class NumberBox extends Base<Integer> { }
```

This is an **illustrative group of declarations**. `TextBox` and `NumberBox` use two parameterizations of `Base<T>`, yet `Base`'s constructor always increments `Base.total`. Both subclasses share an inheritance relationship with **the same field declared in `Base`**.

If a subclass declares **a new `static` field with the same name**, that is *field hiding*, creating a separate field belonging to the subclass. That arises from **declaring an additional field**, not from choosing type argument `String` or `Integer`.

Likewise, `static` methods can be hidden under static method hiding rules, without polymorphic dispatch like overridden instance methods. When calling a utility or counter, explicitly write the **declaring class's** name to avoid confusion.

## 12. Rules for Calling and Observing `static` Members

Prefer the syntax:

```java
Box.createdCount();
Box.<String>of("Java");
```

These are **call-site templates**, assuming `Box` defines the two corresponding `static` methods. Having the class name at the start of the call makes clear to readers that the member belongs to the class, not to a specific `Box<String>` object.

Do not interpret `Box<String>.createdCount()` as a mechanism to select a separate counter for `String`. Static member calls should use the generic class name in the form `Box`, not a parameterized type as an object owning separate state.

Even if you already have a reference:

```java
Box<String> item = Box.of("A");
```

some `static` members can be accessed through an expression in Java, yet writing `item.createdCount()` misleads readers into thinking state depends on `item`. Compilers and static analysis tools commonly recommend accessing via the class name: `Box.createdCount()`.

**A runtime note:** if an expression is used instead of a class name to reference a `static` member, the qualifier expression may still be evaluated per Java rules even though the object is not actually used as the target of the `static` call. Writing the class name directly is both clearer and avoids unnecessary side effects.

## 13. Common Mistakes

| Statement or code snippet | Issue | Proper understanding / fix |
|---|---|---|
| “`Box<String>` has one static counter, and `Box<Integer>` has another.” | Type arguments do not create runtime class copies. | A counter declared on `Box` is shared by both. |
| `static T last;` inside `class Box<T>` | The class's `T` cannot be used directly in a static context. | Use a concrete type, an instance field `T`, or a map design with appropriate type keys. |
| `static T identity(T value)` with `T` declared only on the class | Static methods cannot use the class's type parameter. | `static <U> U identity(U value)`. |
| Changing `static int count` to `static final List<T> shared` | Still uses the class's `T` in a static member, so it is invalid. | Use a fixed type or manage data by key with an explicit contract. |
| “`static final List<String>` is deeply immutable.” | `final` does not prevent mutating the list object. | Use immutable data or guard write access. |
| `count++` from multiple threads | Lost updates due to race conditions. | Use `AtomicInteger`, `LongAdder`, or proper synchronization. |
| “Every class loader in the JVM shares the same static variable.” | Different class loaders can define identically named classes with distinct runtime identities. | Understand sharing scope per class definition. |
| “`Box<String>.class` and `Box<Integer>.class` are two Class objects.” | Class literals for parameterized types like that are invalid. | Use `Box.class`; parameterized objects can share the same `getClass()`. |
| “Changing `T` in a generic static call resets the cache.” | A type argument is only compile-time call info. | If per-group resetting is needed, design an API with explicit group keys. |
| “`static final` guarantees thread-safe access to mutable data.” | `final` does not make operations on the referenced object thread-safe. | Choose concurrent data structures or synchronize access. |

## 14. Self-Check Exercises

**Question 1.** Consider:

```java
class Bucket<T> {
    static int count;
    Bucket() { count++; }
}
```

If two `Bucket<String>` and one `Bucket<Integer>` are created in the same runtime class and then `Bucket.count` is read, what is the result assuming no other operations?

**Question 2.** Why is `static T latest;` invalid inside `class Bucket<T>`, even though `T` is already declared?

**Question 3.** In `static <U> Bucket<U> of(U item)`, does `U` belong to the class or the method? Does calling `of("A")` and then `of(12)` create two copies of the counter?

**Question 4.** When a program prints `true` for `boxString.getClass() == boxInteger.getClass()`, what does that say about generics at runtime?

**Question 5.** If you want to count boxes holding `String` and `Integer` separately, how can a `static` map be designed? Why is it still said that there is only one `static` field?

**Question 6.** Why can a `static int count` counter with `count++` be wrong in a multithreaded program? What does `AtomicInteger.incrementAndGet()` fix?

**Suggested Answers:** (1) `3` because every constructor run increments the same `static` field. (2) Static members cannot directly use the class's type parameter. (3) `U` belongs to the method; calls share one method definition and one class counter. (4) Type arguments do not create separate specialized runtime classes; generics are primarily checked at compile time. (5) A `Map<Class<?>, AtomicInteger>` using `String.class`, `Integer.class` as keys; the map is still one shared field of the class. (6) `count++` is non-atomic; atomic increment prevents lost increments under concurrent updates to the counter.

**Takeaway:** A `static` member belongs to **the defined runtime class**, not separately to each type argument of a generic class. `Box<String>`, `Box<Integer>`, and `Box<Double>` can hold different instance data, yet share the `static` fields of the same `Box`. If you want data grouped by type, represent the groups yourself with appropriate data structures and keys, and protect shared state when multiple threads are involved.
