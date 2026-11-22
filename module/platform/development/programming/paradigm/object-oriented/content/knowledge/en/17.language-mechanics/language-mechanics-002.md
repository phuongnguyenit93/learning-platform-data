# Type Parameter Bounds (Bounded Type Parameters) in Java Generics

**Topic:** OOP → Language Mechanics → Type parameter bounds.  
**Goal:** Understand how to restrict types accepted by generic classes or methods; correctly use `extends` and multiple bounds with `&`; write algorithms using `Comparable`; distinguish type parameters from wildcards; and recognize type-erasure limitations.

## 1. Why do generics need bounds?

Generics let one structure or algorithm work with multiple types while preserving compile-time type checking:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Both `Box<String>` and `Box<Integer>` are valid. But calling `value.doubleValue()` inside `Box<T>` is rejected: `T` may be any reference type and does not necessarily expose `doubleValue()`.

A **bounded type parameter** restricts valid types and allows generic code to use members guaranteed by that bound:

```java
final class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}

NumberBox<Integer> a = new NumberBox<>(42);
NumberBox<java.math.BigDecimal> b =
        new NumberBox<>(new java.math.BigDecimal("12.50"));

// Lỗi biên dịch: String không phải subtype của Number.
// NumberBox<String> wrong = new NumberBox<>("42");
```

Here `extends` means **the type must satisfy an upper bound**. It works with a **class** or **interface** bound, even though Java normally calls the relation to an interface `implements`.

For example, `<T extends Number>` accepts `Integer`, `Long`, `Double`, `BigDecimal`, and other `Number` subtypes. It rejects `String`.

**Note:** `T extends Number` does not make every arithmetic operator valid on `T`. Java does not permit `a + b` when `a` and `b` have type `T`; only operations guaranteed by `Number` (such as `doubleValue()`) or explicitly supplied arithmetic services are available. Conversion to `double` may lose precision, especially for money.

## 2. Declaration syntax and placement

| Purpose | Java syntax | Guarantee |
| --- | --- | --- |
| Unbounded generic class | `class Box<T>` | `T` has a default upper bound of `Object` |
| Generic class with an upper bound | `class NumberBox<T extends Number>` | `T` is a subtype of `Number` |
| Interface bound | `<T extends Comparable<T>>` | `compareTo(T)` is available through the interface |
| Generic method | `static <T extends Number> double value(T x)` | The bound belongs to the method's type parameter |
| Multiple bounds | `<T extends Number & Comparable<T>>` | Must satisfy both bounds |
| Upper-bounded wildcard | `List<? extends Number>` | List elements belong to some subtype of `Number` |
| Lower-bounded wildcard | `List<? super Integer>` | List element type is `Integer` or its supertype |

For methods, **the type-parameter declaration precedes the return type**:

```java
static <T extends Number> double twiceAsDouble(T value) {
    return value.doubleValue() * 2;
}
```

In this snippet, `T` is a generic type parameter **of the method**; the containing class need not be generic.

For a generic class, `T` can appear in fields, constructors, arguments, return types, and instance methods:

```java
final class Pair<T extends CharSequence> {
    private final T first;
    private final T second;

    Pair(T first, T second) {
        this.first = first;
        this.second = second;
    }

    int totalLength() {
        return first.length() + second.length();
    }

    T first() {
        return first;
    }
}
```

Both `String` and `StringBuilder` implement `CharSequence`, but **StringBuilder is mutable**, so a `Pair<StringBuilder>` does not automatically become immutable merely because its fields are `final`.

## 3. Multiple bounds: intersection types

Sometimes an algorithm needs **several capabilities at once**. For example, a value may need to be numeric (`Number`) and comparable (`Comparable`):

```java
static <T extends Number & Comparable<? super T>>
T greater(T first, T second) {
    java.util.Objects.requireNonNull(first);
    java.util.Objects.requireNonNull(second);
    return first.compareTo(second) >= 0 ? first : second;
}
```

Here:

- `Number` is the class upper bound on `T`, providing the API of `Number`.
- `Comparable<? super T>` requires `T` to support comparison with `T` or a suitable supertype.
- **`&`** means **all bounds must hold**, not that one of them is enough.
- When bounds contain a class and interfaces, **the class must be first**; subsequent bounds must be interfaces. Java cannot combine two unrelated class bounds.

Valid:

```java
<T extends Number & Comparable<T>>
<T extends java.io.Serializable & Comparable<T>>
<T extends Number & java.io.Serializable & Comparable<T>>
```

Invalid:

```java
// Class Number phải đứng trước các interface.
// <T extends Comparable<T> & Number>

// Không được có hai class bound.
// <T extends Number & java.util.ArrayList<String>>

// Không dùng dấu phẩy để mô tả nhiều bound của một T.
// <T extends Number, Comparable<T>>
```

A comma in `<T, U>` declares **separate type parameters**, as in `<T extends Number, U extends CharSequence>`. Use `&` for multiple bounds on **the same T**.

### Why use `Comparable<? super T>`?

`<T extends Comparable<T>>` works for types such as `String` and `Integer` but may exclude valid subtypes.

Suppose `Person implements Comparable<Person>` and `Employee extends Person`. An `Employee` inherits `Person` comparison behavior but **does not necessarily implement `Comparable<Employee>`**. Thus:

```java
<T extends Comparable<? super T>>
```

the following is more flexible:

- `Employee` can be compared to a `Person`.
- `Person` is a supertype of `Employee`.
- `Comparable<Person>` satisfies `Comparable<? super Employee>`.

This is useful for maximum-element algorithms and sorting by **natural ordering**.

## 4. Standalone runnable Java 17 example

Create **BoundedGenericsDemo.java**. It demonstrates three operations: selecting a maximum using `Comparable`, maintaining a valid numeric range, and handling enums through recursive bounds. All rely on one principle: accept only types with the required algorithmic capabilities.

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class BoundedGenericsDemo {

    // Comparable<? super T> chấp nhận cả kiểu so sánh với supertype.
    public static <T extends Comparable<? super T>>
    T max(List<? extends T> values) {
        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            throw new IllegalArgumentException(
                    "Danh sách không được rỗng");
        }

        T best = Objects.requireNonNull(values.get(0), "element");
        for (T item : values) {
            Objects.requireNonNull(item, "element");
            if (item.compareTo(best) > 0) {
                best = item;
            }
        }
        return best;
    }

    // T phải là Number VÀ có khả năng so sánh tự nhiên.
    public record NumericRange<T extends Number & Comparable<? super T>>(
            T lower, T upper) {

        public NumericRange {
            Objects.requireNonNull(lower, "lower");
            Objects.requireNonNull(upper, "upper");
            if (lower.compareTo(upper) > 0) {
                throw new IllegalArgumentException(
                        "Giới hạn dưới lớn hơn giới hạn trên");
            }
        }

        public boolean contains(T value) {
            Objects.requireNonNull(value, "value");
            return lower.compareTo(value) <= 0
                    && upper.compareTo(value) >= 0;
        }
    }

    // Lớp cha so sánh theo level.
    public static class Person implements Comparable<Person> {
        private final int level;

        public Person(int level) {
            this.level = level;
        }

        public int level() {
            return level;
        }

        @Override
        public int compareTo(Person other) {
            Objects.requireNonNull(other, "other");
            return Integer.compare(this.level, other.level);
        }
    }

    // Employee thừa hưởng Comparable<Person>, không khai báo
    // Comparable<Employee>.
    public static final class Employee extends Person {
        public Employee(int level) {
            super(level);
        }
    }

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    // Bound đệ quy như cấu trúc Enum<E extends Enum<E>> trong JDK.
    public static <E extends Enum<E>> E parseEnum(
            Class<E> enumClass, String constantName) {
        Objects.requireNonNull(enumClass, "enumClass");
        Objects.requireNonNull(constantName, "constantName");
        return Enum.valueOf(enumClass, constantName);
    }

    public static void main(String[] args) {
        System.out.println("Max score: " + max(List.of(10, 25, 14)));

        System.out.println("Max date: " + max(List.of(
                LocalDate.of(2026, 1, 10),
                LocalDate.of(2026, 8, 20)
        )));

        Employee senior = max(List.of(
                new Employee(3),
                new Employee(9)
        ));
        System.out.println("Max employee level: " + senior.level());

        NumericRange<BigDecimal> range = new NumericRange<>(
                new BigDecimal("1.00"),
                new BigDecimal("2.00")
        );
        System.out.println("In range: " +
                range.contains(new BigDecimal("1.25")));

        System.out.println("Priority: " +
                parseEnum(Priority.class, "HIGH"));
    }
}
```

Run:

```bash
javac BoundedGenericsDemo.java
java BoundedGenericsDemo
```

Output:

```text
Max score: 25
Max date: 2026-08-20
Max employee level: 9
In range: true
Priority: HIGH
```

**Interpret each bound's result:**

1. `max(List.of(10, 25, 14))`: `Integer` supplies `Comparable<Integer>`, satisfying the upper bound.
2. `max(List<LocalDate>)`: `LocalDate` provides natural ordering through `ChronoLocalDate`, a superinterface compatible with `Comparable<? super LocalDate>`.
3. `max(List<Employee>)`: the subclass inherits comparison through `Comparable<Person>`; the `<? super T>` bound keeps this valid case available.
4. `NumericRange<BigDecimal>`: `BigDecimal` extends `Number` and implements `Comparable<BigDecimal>`, satisfying the intersection bound.
5. `parseEnum(Priority.class, "HIGH")`: `Priority` is an enum matching `<E extends Enum<E>>`.

`BigDecimal.compareTo` compares **numeric values**, whereas `equals` also considers scale (such as `1.0` and `1.00`). For numeric ranges, `compareTo` is appropriate under the assumed value semantics; other domains must specify their own comparator and boundary rules.

The example intentionally does not combine `Double` and `BigDecimal` in one `NumericRange<T>`: comparisons use a consistent contract for **one T**, not implicit conversions across representations with potentially different precision or meaning.

## 5. What can the compiler verify through bounds?

Consider the method:

```java
static <T extends CharSequence> int countChars(T text) {
    return text.length();
}
```

Valid:

```java
countChars("Java");                  // String implements CharSequence
countChars(new StringBuilder("OOP")); // StringBuilder cũng vậy
```

Invalid:

```java
// Integer không triển khai CharSequence.
// countChars(123);
```

At a generic method call, Java infers `T` from arguments, target types in some contexts, and constraints. Compilation fails when no inference yields a `T` satisfying all requirements.

**What upper bounds do not guarantee:**

- They do not prohibit passing `null` at compile time. A subtype bound is not a non-null annotation or null-safety type system.
- They do not validate business rules, such as “amount must be positive” or “start date precedes end date”; runtime checks are required.
- They do not make `T` immutable or thread-safe automatically.
- They do not enable every primitive operator, such as `+` or `<`, on variables of type `T`.
- They do not guarantee that `doubleValue()` is exact for every `Number` subtype.

Bounds permit calling APIs defined by the upper bound. Business constraints outside the type system must still be validated explicitly.

## 6. Bounded type parameters versus bounded wildcards

Both forms use `extends` but serve different purposes:

**Named type parameter (`T extends Number`):** assigns a reusable name to a type to express **consistent relationships** across a signature.

```java
static <T extends Number> T firstOf(List<T> values) {
    return values.get(0);
}
```

The result has type `T`: if you pass `List<Integer>`, the call can return `Integer`. The name `T` expresses the link between input element type and return type.

**Wildcard (`? extends Number`):** accepts an unknown element type known to satisfy an upper bound.

```java
static double sumAsDouble(List<? extends Number> values) {
    double sum = 0.0;
    for (Number value : values) {
        sum += value.doubleValue();
    }
    return sum;
}
```

`sumAsDouble(List.of(1, 2, 3))` accepts `List<Integer>`; the method **does not need to know** its precise element type or preserve/return it. It only reads values as `Number`.

**`List<Integer>` is not a subtype of `List<Number>`**. Concrete Java generic parameters are **invariant**:

```java
List<Integer> integers = List.of(1, 2, 3);

// Lỗi biên dịch dù Integer extends Number.
// List<Number> numbers = integers;

List<? extends Number> readableNumbers = integers;
Number n = readableNumbers.get(0);
```

With `List<? extends Number>`, you cannot ordinarily add an `Integer` or `Double` because the actual element type could be another `Number` subtype. `null` may be added if the collection permits it, but that is not useful for a read-only API.

A **lower-bounded wildcard** uses `super` to express a destination that accepts a type and its subtypes:

```java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
    Object first = target.get(0);
}
```

A caller can pass a mutable `List<Integer>`, `List<Number>`, or `List<Object>`. Because the concrete element type of `target` is unknown, retrieved values can safely be treated only as `Object` without further knowledge.

| Construct | When to use | Safe read type | What can be added? |
| --- | --- | --- | --- |
| `<T extends Number>` | Need a reusable name `T` in the signature | `T` or `Number` | According to the API of the structure carrying `T` |
| `List<? extends Number>` | Mainly **reading** numeric values | `Number` | No non-`null` values through this reference |
| `List<? super Integer>` | Mainly **writing** `Integer` | `Object` | `Integer` (and subtypes, if any) |
| `List<Number>` | Exactly a list with element type `Number` | `Number` | Valid `Number` subtypes |

Remember **PECS — Producer Extends, Consumer Super**: use `extends` for a source that **produces values to read** and `super` for a destination that **consumes values to write**. This is an API-selection heuristic, not an inflexible rule for every method.

### `super` does not bound named type parameters

Invalid:

```java
// Java không cho khai báo lower bound trực tiếp cho T.
// class Box<T super Integer> {}
```

Valid:

```java
static void putInteger(List<? super Integer> output) {
    output.add(100);
}
```

An easy distinction to miss: `Comparable<? super T>` **is still within an upper bound for `T`**, but the type argument of `Comparable` is itself a lower-bounded wildcard. Those are two separate syntactic levels.

## 7. API design: when to name T and when to use wildcards

Suppose you want to read a list of numbers:

```java
static double average(List<? extends Number> numbers) {
    if (numbers.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    double total = 0;
    for (Number number : numbers) {
        total += number.doubleValue();
    }
    return total / numbers.size();
}
```

Here **T is unnecessary** because the method does not link the type of an input value to an output type. A wildcard gives a simpler contract.

In contrast, when a result must have **the same concrete type** as an element in the collection:

```java
static <T extends Comparable<? super T>> T chooseMax(
        List<? extends T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

The name `T` links the return type to the list's element type. In a public API, prefer wildcards where they add flexibility without sacrificing required type relationships.

**Avoid overengineering:** do not introduce a generic type parameter merely to replace `Number` with `T` if it conveys no useful type information to callers.

## 8. Recursive bounds (including F-bounded types)

A bound may refer to the type parameter being declared:

```java
interface SelfComparable<T extends SelfComparable<T>>
        extends Comparable<T> {
}
```

The idea is for implementations to describe operations using their own compatible types. This is **F-bounded polymorphism**. It appears in APIs that retain type relationships across inheritance or multilevel builders.

A familiar JDK example:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Phần triển khai thật của JDK có thêm chi tiết nội bộ.
}
```

When declaring:

```java
enum Status { NEW, DONE }
```

`Status` is an enum type compatible with `<E extends Enum<E>>`. Therefore this helper accepts the appropriate enum type:

```java
static <E extends Enum<E>> E parseEnum(
        Class<E> enumType, String name) {
    return Enum.valueOf(enumType, name);
}
```

`parseEnum(Status.class, "DONE")` returns `Status` without a manual cast. An invalid constant name makes `Enum.valueOf` throw `IllegalArgumentException`; that is a runtime input-data error, not a type-inference error.

**Do not apply F-bounds to every interface**. They can produce hard-to-read signatures, especially with multiple inheritance levels, wildcards, and recursive generics. Use them only when the relation “this type uses its own concrete type” adds clear value.

## 9. Type erasure and its limitations

Java generics are primarily checked at **compile time**. In executable bytecode, much type-parameter information is **erased** to its bounds; the compiler can insert casts and generate **bridge methods** to preserve polymorphism.

For example:

```java
final class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Conceptually after erasure, the first upper bound of `T` is `Number`, so corresponding fields/methods use `Number` in bytecode. This is **an explanatory model**, not an exact line-by-line Java listing emitted by the compiler.

With multiple bounds:

```java
class Store<T extends Number & Comparable<T>> {
    T value;
}
```

**T erases to its leftmost bound**, namely `Number`. Since bound order matters for erasure, Java requires class bounds to precede interfaces. The compiler handles calls to methods on other bounds to preserve compile-time typing contracts.

### Operations you cannot perform directly with T

```java
class Example<T extends Number> {
    // Không thể tạo mới đối tượng chỉ từ một type variable:
    // T value = new T();

    // Không thể tạo generic array:
    // T[] values = new T[10];

    // Không thể kiểm tra kiểu thực tế của T theo cách này:
    // boolean exact = obj instanceof T;

    // Không thể dùng type parameter của class trong static field:
    // static T shared;
}
```

Choose a solution based on the goal:

- To create an instance of `T`: pass a `Supplier<T>`, factory, or `Class<T>` with a controlled creation mechanism.
- To hold multiple `T` values: prefer `List<T>` over generic arrays when appropriate.
- To check types at runtime: pass `Class<T>` and call `Class.isInstance/cast`, without assuming `Class<List<String>>` retains the list's `String` element type at runtime.
- To use `T` in a static context: declare a **static generic method** with its own type parameter.

```java
static <T extends Number> T requireNumber(T value) {
    return java.util.Objects.requireNonNull(value);
}
```

Two parameterizations of the same **raw class** generally cannot be distinguished with `instanceof`:

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size());
}

// Không hợp lệ:
// if (value instanceof java.util.List<String> strings) { ... }
```

Erasure can also make two methods whose only difference is the type argument of one raw collection collide after erasure:

```java
// Không thể cùng khai báo trong một class:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
// Sau erasure cả hai đều nhận List.
```

**Important:** Type erasure does not make generics “useless at runtime.” Compile-time type checks are their primary advantage; reflection can still expose some generic declaration details in certain signatures. But the JVM does not assign a distinct `List<String>` runtime label to each `ArrayList` instance.

## 10. Common mistakes and remedies

| Mistake | Why it is wrong / hard to maintain | Approach |
| --- | --- | --- |
| With `<T extends Number>`, writing `a + b` | Arithmetic operators are not defined on reference type variables | Use `Number` APIs with precision awareness or inject an addition strategy |
| Using `<T extends Comparable<T>>` everywhere | Can exclude subtypes comparable through a supertype | Consider `Comparable<? super T>` |
| Trying `<T super Number>` | Java does not support direct lower bounds on type parameters | Use `? super ...` in wildcard positions |
| `List<Number> x = new ArrayList<Integer>()` | Generic parameters are invariant | Use `List<? extends Number>` if mostly reading |
| Adding concrete values to `List<? extends Number>` | Actual element type is unknown | Use `List<? super Integer>` when writing Integer values |
| Placing an interface before a class in an intersection bound | Class bound must come first | `<T extends Number & Comparable<T>>` |
| Assuming upper bounds exclude null | `null` can still pass through generic references | Use `Objects.requireNonNull` and validation |
| Using `doubleValue()` for exact money arithmetic | Can lose precision and scale | Use `BigDecimal` with a clear rounding policy |
| Using raw `Comparable` for “simplicity” | Loses type safety and may fail with runtime casts | Parameterize `Comparable<T>` or `Comparable<? super T>` |
| Overly complex generic APIs for one concrete use | Understanding/maintenance costs outweigh reuse | Use concrete types or focused abstractions |

### Can T be bound to a primitive?

No: Java generics accept **reference types** as type arguments. Primitive `int` and `double` cannot be used in `List<int>` or `Box<int>`. Use wrapper types `Integer` and `Double` (autoboxing), or primitive-specific structures such as `IntStream` and `int[]` when performance/memory matters.

### Must a class explicitly implement all interfaces in multiple bounds?

A type can satisfy bounds through **inheritance** or **indirectly implemented interfaces**; it need not list every interface name directly in an `implements` clause. Java checks actual type relationships in the hierarchy.

### Is an upper bound a type constraint or a value constraint?

Bounds constrain **types**, not **values**. `T extends Number` does not express `T > 0`. Positive-number requirements need runtime validation. `T extends Comparable<T>` does not prove that `compareTo` is correct, transitive, or consistent with `equals`; implementations must honor the `Comparable` contract.

## 11. Exercise: repository for sensor measurements

Build a model to store sensor readings. Every measurement has **a sensor ID**, **a value**, and **a recorded timestamp**.

1. Write `Measurement<T extends Number & Comparable<? super T>>` as a `record`; reject blank sensor IDs and null values.
2. Write `maxMeasurement(List<Measurement<T>>)` to return the measurement with the largest value using an appropriately bounded type parameter. Reject empty lists explicitly.
3. Create examples with `Integer` and `BigDecimal`. Explain why comparisons need a consistent contract rather than automatically mixing all `Number` representations.
4. Write a method that only **reads** `List<? extends Number>` and computes an approximate `double` sum; describe limitations for financial data.
5. Write a method to append a default value to `List<? super Integer>`, then invoke it using `List<Integer>`, `List<Number>`, and `List<Object>`.
6. Write JUnit 5 tests for null, empty lists, equal values, negative values, and a subtype inheriting `Comparable` from a supertype.

**Self-check:** Which variables truly must share type `T`? Where is a wildcard enough? Which conditions does the compiler guarantee, and which need runtime checks? What does `Comparable<? super T>` do when a subclass inherits its comparison from a superclass?

## 12. Key points for correct usage

- `<T extends Bound>` is an **upper-bounded type parameter**: it restricts accepted types and which members can be invoked safely.
- One `T` may have **multiple bounds joined by `&`**; place the class bound first when present.
- `Comparable<? super T>` is often preferable to `Comparable<T>` for subtypes that inherit comparison against a supertype.
- A named `T` expresses **type relationships** across arguments, fields, and results; wildcards fit where that relationship need not be named.
- `? extends` supports reading at the upper bound; `? super` supports writing a concrete type under PECS.
- **Type erasure** restricts some runtime operations; generic bounds ensure compile-time type checking but do not replace validation or tests.
- Choose the weakest bound that satisfies the algorithm. Overly strict bounds exclude usable types, while overly loose bounds force risky casts.

**Conclusion:** Type parameter bounds describe **the capabilities an algorithm requires** directly in Java APIs. Appropriate bounds make code reusable, type-safe, and understandable; knowing wildcard, erasure, and runtime constraints avoids common generics pitfalls.
