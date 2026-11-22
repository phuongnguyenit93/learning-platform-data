# Java Generics: Generic types and parameterized classes

> **Topic:** OOP → Language Mechanics → Generic types and parameterized classes.  
> **Goal:** Declare and use `Box<T>`, `Pair<K,V>`, and parameterized data-storage classes; understand generic types, type parameters, type arguments, type inference, type bounds, wildcards, and type erasure; and avoid common Java API design mistakes.

## 1. What problems do generics solve?

**Generics** let classes, interfaces, and methods declare **some data types as parameters** instead of duplicating code for each type. The Java compiler can therefore catch many type mismatches at compile time.

An example from before type-safe generics:

~~~java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList(); // raw type: không chỉ ra kiểu phần tử
raw.add("Java");
raw.add(123);              // Cả chuỗi lẫn số đều được chấp nhận

String name = (String) raw.get(1);
// Biên dịch được (có cảnh báo raw/unchecked) nhưng chạy sẽ
// gặp ClassCastException vì phần tử ở vị trí 1 là Integer.
~~~

With generics, the type contract becomes explicit:

~~~java
List<String> names = new ArrayList<>();
names.add("Java");
names.add("OOP");

// names.add(123); // LỖI BIÊN DỊCH: Integer không phải String.
String first = names.get(0); // Không phải ép kiểu thủ công.
~~~

**Key point:** Generics improve **compile-time type safety**, clarify API intent, and reduce casts. They **do not create a separate runtime class for every type argument**: Java implements generics largely through *type erasure* (removing type-parameter information from many places in bytecode), explained below.

## 2. Reading generic-type syntax correctly

| Syntax | Meaning | Example |
|---|---|---|
| `class Box<T>` | Declares **a class with one type parameter** named `T` | `Box<String>` |
| `interface Store<K,V>` | An interface with two type parameters | `Store<Long,User>` |
| `Box<String>` | A **parameterized type**: a specific use of `Box` with the type argument `String` | `Box<String> x` |
| `T`, `K`, `V` | **Type parameters**: symbolic names in a declaration | `T value` |
| `String`, `Long`, `User` | **Type arguments**: types supplied when using a generic | `new Box<String>(...)` |
| `<>` | The **diamond operator**: lets the compiler infer suitable type arguments | `new Box<>("Hi")` |
| `<T> T first(...)` | A generic method declaring its **own** type parameter | `static <T> T first(List<T> list)` |

`T` is not a Java keyword. Common conventions include `T` (Type), `E` (Element), `K` (Key), `V` (Value), `R` (Result), and `S` (another type). More descriptive names such as `ENTITY` or `ID` may suit complex systems, though short uppercase names keep familiar Java APIs readable.

Compare these two declarations:

~~~java
class Holder<T> {
    T value; // T do class khai báo, dùng được ở instance member.

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U> U identity(U x) {
        // U được khai báo bởi chính phương thức static này.
        return x;
    }
}
~~~

A `static` method **cannot** use the class's `T` to declare a field or method signature tied to an instance type parameter because static members belong to the class, not a particular `Holder<String>` or `Holder<Integer>`. A static method **can declare its own** `<U>`, as `identity` does.

## 3. Complete Java 17 example: generic Box, Pair, and Repository

This standalone example runs on JDK 17+ with no Spring or external libraries. It demonstrates three levels of use:

1. `Box<T>` stores a value whose concrete type is chosen at the usage site.
2. `Pair<K,V>` has **two** independent type parameters.
3. `InMemoryRepository<ID,T>` reuses one data-storage implementation for different entity and ID types while enforcing type consistency.

Create **`GenericsDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

// Generic class: T đại diện cho kiểu dữ liệu được chứa.
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    T get() {
        return value;
    }

    void set(T next) {
        value = Objects.requireNonNull(next, "next");
    }

    // Generic method: R là tham số kiểu MỚI của phương thức.
    // Có thể biến Box<String> thành Box<Integer>, v.v.
    <R> Box<R> map(Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(mapper, "mapper");
        return new Box<>(
                Objects.requireNonNull(mapper.apply(value), "mapped value"));
    }
}

// Generic record: các thành phần độc lập về kiểu.
record Pair<K, V>(K key, V value) {}

// Entity ví dụ, record bất biến.
record User(String id, String name) {}

// Repository in-memory phục vụ demo, không phải kho dữ liệu bền vững.
final class InMemoryRepository<ID, T> {
    private final Function<T, ID> idOf;
    private final Map<ID, T> data = new HashMap<>();

    InMemoryRepository(Function<T, ID> idOf) {
        this.idOf = Objects.requireNonNull(idOf, "idOf");
    }

    void save(T item) {
        Objects.requireNonNull(item, "item");
        ID id = Objects.requireNonNull(idOf.apply(item), "id");
        data.put(id, item);
    }

    Optional<T> findById(ID id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(data.get(id));
    }
}

public class GenericsDemo {
    public static void main(String[] args) {
        Box<String> language = new Box<>("Java"); // Diamond: suy luận T
        Box<Integer> counter = new Box<>(42);

        System.out.println("Box<String>: " + language.get());
        System.out.println("Box<Integer>: " + counter.get());

        // R = Integer vì String::length trả về int, được boxing.
        Box<Integer> length = language.map(String::length);
        System.out.println("Độ dài: " + length.get());

        Pair<String, Long> invoice = new Pair<>("HD-01", 180_000L);
        System.out.println(
                "Hóa đơn: " + invoice.key() + " = " + invoice.value());

        InMemoryRepository<String, User> users =
                new InMemoryRepository<>(User::id);
        users.save(new User("U-01", "Lan"));

        System.out.println(
                "Người dùng: " + users.findById("U-01").orElseThrow().name());
    }
}
~~~

Run:

~~~bash
javac GenericsDemo.java
java GenericsDemo
~~~

Expected output:

~~~text
Box<String>: Java
Box<Integer>: 42
Độ dài: 4
Hóa đơn: HD-01 = 180000
Người dùng: Lan
~~~

### Tracing the type flow

- For `Box<String> language`, every use of `T` in an instance member of `Box<T>` is **treated as `String` by the compiler**. `language.set(123)` will not compile.
- For `Box<Integer> counter`, `counter.get()` has the return type `Integer` at compile time.
- `<R> Box<R> map(...)` converts between different value types, such as `Box<String>` to `Box<Integer>`. The method's type parameter `R` is independent of the class's `T`.
- `Pair<K,V>` represents two values that can have different types. With `Pair<String,Long>`, `key()` returns `String` and `value()` returns `Long`.
- `InMemoryRepository<ID,T>` keeps the **key type** and **entity type** consistent. Here `findById` accepts `String` and returns `Optional<User>` without casting from `Object`.
- `User::id` is a method reference that extracts a key as a `Function<User,String>`. The repository need not know how each entity stores its `id` field.

**Example scope:** `InMemoryRepository` demonstrates type safety and reuse; it does not implement transactions, durable persistence, concurrent access, or duplicate-key controls. Do not use it directly as a production repository for a multithreaded application.

## 4. Multiple type parameters and where to apply bounds

A generic class can declare multiple type parameters:

~~~java
interface Repository<ID, ENTITY> {
    void save(ENTITY entity);
    Optional<ENTITY> findById(ID id);
}
~~~

Examples of different usages:

~~~java
Repository<Long, Product> products;
Repository<String, Customer> customers;
~~~

`Product` and `Customer` are illustrative domain types that must be defined in the project. Each combination creates a **source-level parameterized type**, not a separate bytecode class.

How many type parameters should a class have? Add one only when **clients need to specify and check that type**. If a generic class has five or six parameters and an unreadable signature, consider splitting responsibilities, adding a type alias via a separate abstraction (Java lacks a general-purpose type-alias syntax found in some languages), or wrapping related properties in a meaningful domain type.

### 4.1. When an algorithm requires a bound on `T`

A `Box<T>` that only stores/returns values need not know what operations `T` supports. To call `doubleValue()`, however, declare `<T extends Number>`; to call `compareTo`, use a bound as follows:

~~~java
static <T extends Comparable<? super T>> T greater(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

In generic declarations, `extends` accepts **both classes and interfaces**. Multiple bounds use `&` (with the class first, if any): `<T extends Number & Comparable<? super T>>`. Java does not support `<T super Number>`; lower bounds are only supported on wildcards such as `? super Number`.

A bound ensures an API is available at compile time; it **does not** validate business values, nulls, or ordering semantics. The **Type parameter bounds** lesson covers `NumberBox`, `Comparable<? super T>`, intersection/recursive bounds, tests, and erasure limitations in detail.

### 4.2. Generic methods versus generic classes

A whole generic class is unnecessary when only **one method** works across multiple types:

~~~java
import java.util.List;
import java.util.NoSuchElementException;

final class Lists {
    private Lists() {}

    // <T> xuất hiện TRƯỚC kiểu trả về T.
    static <T> T first(List<T> items) {
        if (items.isEmpty()) {
            throw new NoSuchElementException("empty list");
        }
        return items.get(0);
    }
}

// Trong method khác:
String title = Lists.first(List.of("Java", "OOP"));
Integer number = Lists.first(List.of(10, 20));
~~~

Both calls use **the same method**; the compiler infers `T = String` or `T = Integer` from arguments and context. You can also specify a type argument explicitly:

~~~java
String title = Lists.<String>first(List.of("Java", "OOP"));
~~~

Explicit syntax is rarely needed when inference suffices. If the project already declares a `title` variable in an earlier snippet, put this example in a separate method to avoid redeclaring a local variable.

## 5. Type inference: how much can the compiler infer?

Java infers type arguments in many situations:

~~~java
Box<String> box = new Box<>("Hello");  // Diamond operator
var another = new Box<>("World");      // Suy ra Box<String> trong JDK 10+
Pair<String, Integer> pair = new Pair<>("SKU-7", 3);
~~~

**Inference is not dynamic typing**: `var another` still has a definite static compile-time type, `Box<String>`. Calling `another.set(100)` is still a compilation error.

Be careful when a generic constructor infers its type from an initializer expression with no target type:

~~~java
var emptyStrings = new java.util.ArrayList<String>();
emptyStrings.add("A");

// var unknown = new java.util.ArrayList<>();
// Nếu không có thông tin ràng buộc, phần tử thường được suy ra
// kiểu Object; không thể tự kỳ vọng là String.
~~~

When an API needs an explicit element type, declare `List<String> names = new ArrayList<>();` or use a constructor with explicit type arguments. Read the generic method signature before attempting to “fix” code with a cast.

## 6. Invariance: why isn't Box<Integer> a Box<Number>?

`Integer extends Number` is a valid subtype relationship. But with ordinary generic types, Java **does not infer** that `Box<Integer> extends Box<Number>`. Likewise, `List<Integer>` is not a subtype of `List<Number>`.

~~~java
Box<Integer> ints = new Box<>(10);

// Box<Number> numbers = ints; // KHÔNG biên dịch.
~~~

If it were allowed, a client could insert a `Double` into a box intended to hold only `Integer` values:

~~~java
// Giả sử giả định sai: Box<Number> numbers = ints;
numbers.set(3.14);             // 3.14 là Double hợp lệ cho Number
Integer x = ints.get();        // Nhưng ints lẽ ra chỉ chứa Integer!
~~~

Therefore, type arguments of generics such as `Box<T>` and `List<T>` are **invariant** by default. Do not bypass the error with raw types or unchecked casts; consider whether the API needs wildcards or another abstraction.

By contrast, Java arrays are **covariant**, but invalid writes may fail at runtime:

~~~java
Number[] nums = new Integer[1];
nums[0] = 3.14; // ArrayStoreException lúc chạy.
~~~

Generic invariance prevents a class of type errors at compile time. This matters when migrating an array-based API to generic collections.

## 7. Wildcards for safely accepting different collection types

Ordinary generics are **invariant**: `List<Integer>` cannot be assigned to `List<Number>`. Wildcards express which types may be **read** or **written** while retaining type checks:

| Signature | Compiler guarantee | Adding elements |
| --- | --- | --- |
| `List<?>` | Reads as `Object` | Only `null` is type-safe to add |
| `List<? extends Number>` | Reads as `Number` | Cannot arbitrarily add `Integer`/`Double` |
| `List<? super Integer>` | Can safely add `Integer`; reads as `Object` | Can add `Integer` |
| `List<Number>` | Reads/writes as exactly `Number` | May add `Number` subtypes |

~~~java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) total += n.doubleValue();
    return total;
}

static <T> void copyAll(
        List<? extends T> source, List<? super T> destination) {
    for (T item : source) destination.add(item);
}
~~~

`sum(List.of(1, 2, 3))` compiles even when the source is a `List<Integer>`; `copyAll` can copy a `List<Integer>` into a `List<Number>`. **PECS** (Producer Extends, Consumer Super) describes source/destination roles in a method; it does not make collections immutable. Collections created by `List.of` still reject `add` at runtime even when the signature permits writing.

Wildcards differ from `<T>`: name the type parameter `T` when several input/output positions must have related types. The **Type relationships in generic constructs** lesson covers invariance, wildcard capture, PECS, and generic inheritance with complete compile/error tables and tests.

## 8. Erasure: the compiler knows `T`, but runtime has no separate class per type argument

With Java generics, the compiler checks `List<String>` and `List<Integer>` using type arguments, yet both `ArrayList` instances have the same runtime class:

~~~java
var texts = new java.util.ArrayList<String>();
var ints = new java.util.ArrayList<Integer>();
System.out.println(texts.getClass() == ints.getClass()); // true
~~~

After **type erasure**, an unbounded `T` is generally replaced with `Object`; a bounded parameter is generally erased to its leftmost bound, such as `T extends Number` becoming `Number`. The compiler may insert casts and bridge methods to preserve verified behavior.

| Directly invalid expression | Reason |
|---|---|
| `new T()`, `T.class`, `new T[10]` | Runtime does not know the concrete type of `T` |
| `obj instanceof List<String>` | `List<String>` is not reifiable for checking its type argument |
| `static T shared` in `class Box<T>` | A static member does not belong to a separate `Box<String>` variant |
| Overloading `f(List<String>)` and `f(List<Integer>)` | Both signatures collide after erasure |
| `class CustomError<T> extends Exception` | Subclasses of `Throwable` cannot be generic |

To construct `T`, pass a `Supplier<? extends T>`; for runtime class checks, pass `Class<T>` and use `isInstance/cast`. Reflection can inspect **declared generic signatures** but does not turn `ArrayList<String>` into a different runtime class from `ArrayList<Integer>`.

Raw types and unchecked casts in the next section can undermine the compiler's type-safety guarantees.

## 9. Raw types, unchecked warnings, and heap pollution

A **raw type** omits all type arguments: `List` instead of `List<String>`, or `Box` instead of `Box<User>`. Raw types often appear in older Java code or nongeneric APIs; using them in new code loses important type checks.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List raw = names;        // Cùng object, nhìn qua kiểu raw.
raw.add(123);           // Cảnh báo unchecked nhưng có thể biên dịch.
String name = names.get(1);
// ClassCastException khi đọc: Integer đã được thêm ở chỉ số 1.
~~~

When a variable/collection declared with a parameterized type contains incompatible values, that is **heap pollution**. If Java reports `unchecked assignment`, `unchecked call`, or `unchecked cast`, do not simply suppress the warning. Trace the boundary to raw types and convert with meaningful checks.

If a legacy API returns `List<?>`, inspect each element using `instanceof String` and copy validated values into a new `List<String>`; that performs meaningful runtime checking. A mere cast to `(List<String>) raw` cannot validate every element.

This distinction matters for public APIs: **generic type safety is trustworthy only when unchecked casts or raw types do not silently bypass its guarantees**.

## 10. Designing generic classes: how general should they be?

Generics are useful when types share **structures and processing rules** while type arguments capture meaningful relationships. Do not make every domain class generic merely because `<T>` is available.

### Appropriate uses

- `Box<T>`, `Optional<T>`: wrap a value or its possible absence.
- `Pair<K,V>`, `Map<K,V>`: relate multiple typed values.
- `Repository<ID,ENTITY>`: reuse the same key/entity type relationship.
- `Result<T>`: wrap a successful result of a known type with an explicitly modeled failure state.
- Collection processors or algorithms independent of specific types except for capabilities required by their bounds.

### Cases where generics should not be forced

Suppose the domain contains only a `BankAccount` governed by account-number, status, and balance rules. Turning it into `BankAccount<TBalance,TState,TId>` with no actual need for multiple types can obscure the business concept and hurt readability. Favor meaningful domain types and introduce generics only at genuinely reusable abstractions.

### Practical design guidelines

1. **Expose necessary type parameters accurately** in public APIs: returning `Object` and forcing callers to cast undermines the value of `<T>`.
2. **Prefer collection interfaces** as parameters when no `ArrayList`- or `HashSet`-specific behavior is needed.
3. **Keep bounds no stricter than necessary**; do not require `T extends SomeBaseClass` merely because current code uses that class when a smaller interface satisfies the algorithm.
4. **Document the null policy**. The example `Box<T>` rejects null, but Java's type parameter `T` **does not inherently guarantee non-null values**.
5. **Maintain consistent types** across methods/constructors: `Repository<ID,T>.findById(ID)` should return `Optional<T>` rather than `Object` or an unchecked cast.
6. **Test invalid type usage at compile time** and correct behavior at runtime; merely demonstrating that a class can hold a value is insufficient.
7. **Do not confuse generic types with inheritance polymorphism**. `List<Integer>` does not extend `List<Number>`; wildcards express more flexible constraints when necessary.

## 11. Testing generic classes and their contracts

Generic testing has two complementary levels:

- **Compile-time type safety:** `Box<String> box; box.set(1);` must be rejected by the compiler. This is a type-system property, not a runtime exception to catch with JUnit.
- **Runtime behavior:** Even a correctly typed generic signature does not guarantee correct implementation logic (returning the wrong value, altering state, or violating a null contract).

Example JUnit Jupiter 5 tests for `Box<T>` and `InMemoryRepository<ID,T>` in section 3, are placed in `GenericsDemoTest.java` in the same package's test source set:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;

class GenericsDemoTest {
    @Test
    void boxPreservesTheDeclaredValueType() {
        Box<String> language = new Box<>("Java");
        assertEquals("Java", language.get());

        language.set("Spring");
        assertEquals("Spring", language.get());

        Box<Integer> length = language.map(String::length);
        assertEquals(6, length.get());
    }

    @Test
    void repositoryUsesConsistentIdAndEntityTypes() {
        InMemoryRepository<String, User> users =
                new InMemoryRepository<>(User::id);

        users.save(new User("U-9", "Mai"));

        assertEquals("Mai",
                users.findById("U-9").orElseThrow().name());
        assertTrue(users.findById("U-unknown").isEmpty());

        assertThrows(NoSuchElementException.class,
                () -> users.findById("U-unknown").orElseThrow());
    }

    @Test
    void boxedNullIsRejectedByThisImplementation() {
        assertThrows(NullPointerException.class,
                () -> new Box<String>(null));
    }
}
~~~

These tests require the `org.junit.jupiter:junit-jupiter` dependency and a compatible JUnit runner. They verify implementation behavior and null contracts; **there is no need** for separate runtime tests for every `T` argument when the algorithm is the same and the compiler already checks type relationships.

For complex generic libraries, test diverse type families such as `String`, `Integer`, records/domain objects, and advanced bounds to detect unreasonable algorithm assumptions.

## 12. Frequently asked questions

**Q1. Is `List<String>` a separate class inheriting from `List`?**  
No. `List<String>` is a **parameterized type** of the generic `List<E>` interface. It specifies a type argument at compile time; the runtime does not create separate classes for every `String` argument.

**Q2. Why is `Box<int>` invalid but `Box<Integer>` valid?**  
Java generic type arguments must be reference types. Boxing/unboxing converts between `int` and `Integer` in many expressions, but does not make a primitive type argument valid.

**Q3. Must a class with type parameters be abstract or an interface?**  
No. `class Box<T>` can be concrete, as in this example. `record Pair<K,V>` and `interface Repository<ID,T>` may also declare type parameters.

**Q4. Do generics replace inheritance/polymorphism?**  
Not entirely. Inheritance/interface polymorphism defines **behavioral contracts**, while generics express **type relationships in APIs** and reuse algorithms/structures with different type arguments. They work together.

**Q5. Does `T extends Number` define generic addition using `+` for every class?**  
No. Java defines no generic addition operator for `Number`. Precise arithmetic may require a dedicated interface, strategy, or appropriate concrete API; `doubleValue()` can lose precision.

**Q6. When should `<?>` be used instead of `<T>`?**  
When there is no need to name and connect types across several positions, a wildcard is more concise. When the same type parameter relates inputs and outputs, `<T>` is usually more meaningful.

## 13. Practice: implement a type-safe Cache<K,V>

Implement this class:

~~~java
public final class Cache<K, V> {
    // TODO:
    // 1. private final Map<K, V> entries;
    // 2. public void put(K key, V value);
    // 3. public Optional<V> get(K key);
    // 4. public boolean containsKey(K key);
    // 5. public int size();
}
~~~

Requirements:

1. Reject null keys and values according to your chosen policy, documented in JavaDoc.
2. Create `Cache<String,User>`, store `User("U-01", "Lan")`, and retrieve an appropriately typed `Optional<User>`.
3. Create `Cache<Long,String>` with the same class and `Long` IDs.
4. Try `cache.put(123L, user)` when the cache is a `Cache<String,User>` to observe the compilation error.
5. If copying between collections is needed, write a `<T> void copyAll(List<? extends T>, List<? super T>)` helper and explain PECS.
6. Try declaring a `static V lastValue` field inside `Cache<K,V>` and explain why Java rejects it.
7. If the cache needs TTL, concurrency, or eviction, identify the **additional runtime requirements** rather than assuming generic signatures address them.

### Self-check after this lesson

- Where is `<T>` declared? How do `class Box<T>` and `static <T> T identity(T value)` differ?
- Why can't `List<Integer>` be assigned directly to `List<Number>` even though `Integer extends Number`?
- What is gained by using `List<? extends Number>` to read values from multiple numeric subtypes?
- Why is `new T()` invalid in a generic class, and how does `Supplier<? extends T>` solve the problem?
- What runtime failure can raw types and unchecked casts cause?
- How does type erasure affect `instanceof`, method overloading, and generic-array creation?

**Remember:** Generics let us write **one structure or algorithm reusable across multiple types while checking type relationships at compile time**. When designing parameterized classes, consider API contracts, variance/invariance, appropriate wildcards, and type-erasure boundaries rather than simply appending `<T>`.
