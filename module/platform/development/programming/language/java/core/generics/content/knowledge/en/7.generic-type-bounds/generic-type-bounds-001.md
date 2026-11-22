# Upper Bound `<T extends U>` and Allowed Operations on `T` in Java

An **upper bound** is a constraint requiring a generic type parameter to be a type compatible with a known superclass, an interface, or a known type variable. The common syntax is `<T extends U>`, where `T` is the declared type parameter and `U` is the upper bound: **the type argument passed for `T` must be `U` or a subtype of `U`**.

An upper bound solves an important problem: when an algorithm accepts data of different classes, the compiler needs to know **which methods can be safely called on `T`**. If only `<T>` is declared, the compiler does not assume `T` has `doubleValue()`, `compareTo()`, or any arbitrary business method. If `<T extends Number>` is declared, the compiler knows `T` supports the accessible members of `Number`, such as `doubleValue()`.

This article covers the syntax, compile-time checking mechanism, valid and invalid operations, multiple bounds, the difference between an upper bound on a type parameter and the `? extends U` wildcard, result types, type erasure, common pitfalls, and a runnable Java 17+ example.

## 1. Reading the `<T extends U>` Syntax Accurately

A simple example:

```java
static <T extends Number> double toDouble(T value) {
    return value.doubleValue();
}
```

In this signature:

1. `<T extends Number>` **declares** a new type parameter named `T`.
2. `Number` is the **upper bound**: the type argument substituted for `T` must be `Number` or a compatible subclass, such as `Integer`, `Long`, `Double`, or `BigDecimal`.
3. The return type of the method is fixed as `double`; it is not `T`.
4. The parameter `T value` accepts a value matching the `T` inferred/chosen by the compiler.
5. `doubleValue()` is valid because it is a method declared on `Number`.

Example calls:

```java
double a = toDouble(42);                       // T is inferred as Integer.
double b = toDouble(3.5);                      // T is inferred as Double.
double c = toDouble(new java.math.BigDecimal("2.25"));

// toDouble("42"); // Does not compile: String does not extend Number.
```

`Number` here is an abstract class in Java, with methods such as `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`. The existence of a method **does not guarantee lossless conversion**: `longValue()` can drop information and `doubleValue()` can round when the original numeric type holds higher precision.

The syntax `<T extends U>` does not mean `T` is **strictly equal to** `U`; `T` can be a subtype of `U`. The `extends` keyword is used for an upper bound whether it is a class, an interface, or a properly declared type variable.

### `U` does not have to be a class name

A bound can reference another type variable:

```java
static <U, T extends U> U upcast(T value) {
    return value;
}
```

Here `U` is declared first, so `T extends U` is valid. The method returns `U` because any compatible `T` can be treated as `U`. This illustrative snippet **does not need to be used in every problem**; in practice, simpler signatures are often easier to understand if only a standard upcast is needed.

### An upper bound can be an interface

```java
static <T extends CharSequence> int lengthOf(T value) {
    return value.length();
}
```

`CharSequence` is an interface. Even so, you still write `extends`, not `implements`, in the type parameter bound list. `String`, `StringBuilder`, and `StringBuffer` are suitable types to use here; `Integer` does not satisfy the `CharSequence` bound.

`T` can be a compatible class/interface subtype, but **cannot be a primitive**: `<T extends Number>` can use `Integer`, not `int` directly. Java uses boxing to support many calls with primitive literals, yet the actual type argument remains a reference type.

## 2. Why Does the Compiler Know Very Little About `T` Without a Bound?

Consider a generic method with no bound:

```java
static <T> String describe(T value) {
    return String.valueOf(value);
}
```

By default, `T` has an upper bound of `Object` if not otherwise constrained. The compiler only allows access to valid members guaranteed by that type, such as the `Object` methods permitted in that context (`toString`, `equals`, `hashCode`, `getClass`, ...). `String.valueOf(value)` also handles the `null` case.

**You cannot arbitrarily call a method belonging to an arbitrary subtype:**

```java
// Does not compile:
// static <T> double broken(T value) {
//     return value.doubleValue();
// }
```

The compiler must check that general method for **every valid `T`**, from `String` to `LocalDate` or a business class. There is no contract requiring every object to have `doubleValue()`.

If the code writes `<T extends Number>`, the members of `Number` become available:

```java
static <T extends Number> String describeNumber(T value) {
    return "double=" + value.doubleValue()
            + ", long=" + value.longValue();
}
```

An upper bound is a **compile-time type promise checked by the compiler**, not a runtime conversion from an arbitrary value to `Number`. A caller passing a `String` will be rejected along the fully type-checked generic call path.

## 3. Which Operations Are Allowed on `T extends U`?

Suppose you write:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2.0;
}
```

The compiler knows `value` has at least the contract of `Number`; therefore it can call `doubleValue()` and perform arithmetic operations on the **returned `double` value**.

| Operation | With `T extends Number` | Why |
| --- | --- | --- |
| `value.doubleValue()` | Valid | The method is declared in `Number` |
| `value.intValue()` | Valid | The method is declared in `Number` |
| `value.toString()` | Valid | Inherited/overridden method from `Object` |
| `Number n = value` | Valid | Every compatible `T` can be treated as `Number` |
| `Object o = value` | Valid | Every compatible reference type is an `Object` |
| `T copy = value` | Valid | Assignment to the same existing type `T` |
| `value.compareTo(other)` | Not guaranteed | `Number` does not declare `compareTo` |
| `value.add(other)` | Not guaranteed | Not every `Number` has an `add` method |
| `value + other` | Invalid for `T` bounded only by `Number` | Java does not define arithmetic operators directly for a type variable `T` like primitives |
| `new T()` | Invalid | Cannot instantiate a type variable directly with a constructor |
| `new T[10]` | Invalid | Java does not allow creating an array with a non-reifiable component type like type variable `T` |

An upper bound also **does not** grant access to `private` fields/methods of `U` simply because `T extends U`: Java access control still applies. Subclass-specific methods of `Integer` or `BigDecimal` cannot be called directly on `T` either if the bound is only `Number`.

### Do not confuse `T` with `U`

With `<T extends Number>`, you can assign `T` to `Number`, but you cannot arbitrarily assign `Number` to `T`:

```java
static <T extends Number> void example(T value) {
    Number number = value;       // Valid.
    // T wrong = number;         // Does not compile.
}
```

Reason: `T` might be `Integer`, while the `number` variable might reference a `Double`. The subtype relationship only guarantees the **T → Number** direction, not the reverse.

Similarly, `<T extends Number>` cannot be treated as a `cast` for any object. If data comes from an external source, its type and content must still be validated according to business requirements.

## 4. Upper Bounds at the Class Level and Method Level

### 4.1. Declared on a generic class

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` is declared **on the class**, so the constructor, field, and instance methods all know `T` must be compatible with `Number`. `NumericBox<Integer>` and `NumericBox<Double>` are valid; `NumericBox<String>` is invalid.

`T get()` returns `T` itself, while `double asDouble()` returns the primitive `double`: the two methods provide two different contracts while sharing the same upper bound.

### 4.2. Declared on a generic method

```java
class NumericTools {
    static <T extends Number> double square(T value) {
        double x = value.doubleValue();
        return x * x;
    }
}
```

The `NumericTools` class is **non-generic**; only the `square` method declares `<T extends Number>`. Each call can use a different subtype of `Number`.

### 4.3. Class bounds and method bounds are independent

```java
class Holder<T extends Number> {
    private final T number;

    Holder(T number) {
        this.number = number;
    }

    <U extends CharSequence> String append(U suffix) {
        return number + ":" + suffix;
    }
}
```

`T` belongs to the class and is bounded by `Number`; `U` belongs to the method and is bounded by `CharSequence`. The two type parameters have **separate scopes**. You should not declare a new `<T>` on the method if the goal is to use the class's own `T`; reusing the name can shadow the class-level type parameter.

## 5. Constraining with a Business Interface

You do not have to use `Number` or a built-in interface. Upper bounds are especially useful when an algorithm requires a **specific business contract**:

```java
interface HasId<ID> {
    ID id();
}

static <T extends HasId<String>> String extractId(T entity) {
    return entity.id();
}
```

When `T extends HasId<String>`, the method knows `entity.id()` returns `String`, whether the actual entity is `Product`, `Customer`, or another implementing type. This enables reusing logic based on **capabilities guaranteed by an interface**, instead of forcing every entity to inherit from the same business superclass.

Example:

```java
record Product(String id, String name) implements HasId<String> {}

String id = extractId(new Product("P-7", "Pen"));
```

If a class only implements `HasId<Long>`, it does not satisfy the `HasId<String>` bound above. The type arguments of a generic interface still matter; you cannot simply look at the name `HasId` and assume all parameterizations are compatible.

### A bound can link multiple type variables

```java
interface HasId<ID> {
    ID id();
}

static <ID, T extends HasId<ID>> ID idOf(T entity) {
    return entity.id();
}
```

`ID` is declared before `T`, and the bound `T extends HasId<ID>` describes the relationship between the two type parameters. When an entity implementing `HasId<Long>` is passed, the compiler can use that relationship to determine a result type compatible with `Long`.

This is an example of a bound that **helps the type contract**, not just calling methods: it connects the entity type to that entity's own ID type.

## 6. Recognizing Multiple Bounds Before Going Deeper

A type parameter may need two independent capabilities **simultaneously**, such as numeric conversion like `Number` and comparison like `Comparable<T>`. In that case, Java allows:

```java
class NumericHolder<T extends Number & Comparable<T>> {
    private final T value;
    NumericHolder(T value) { this.value = value; }
    double asDouble() { return value.doubleValue(); }
    boolean isGreaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
```

`Integer` satisfies both bounds, whereas `Number` **does not** itself implement `Comparable<Number>`. The `&` symbol requires satisfying **all** conditions, unlike the comma that separates multiple type parameters. If a class bound is present, the class comes first and subsequent bounds are interfaces; you cannot specify two class bounds.

This example only introduces why multiple bounds are needed; the focus of this article remains **which method calls an upper bound unlocks on `T`**. Programs with multiple interfaces, compatibility rules, and effects on erasure are covered separately in more complex scenarios.

## 7. `Comparable<? super T>` and the Algorithm to Pick the Maximum Element

A common requirement is **selecting the largest element** from a list without casting to `Object`. To call `compareTo` on `T`, an appropriate bound is needed:

```java
static <T extends Comparable<? super T>> T max(
        java.util.List<T> values) {

    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
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

`Comparable<? super T>` means `T` implements the ability to compare against `T` **or against a supertype of `T`**. When calling `value.compareTo(best)`, the compiler knows `best` of type `T` can be passed to the comparison contract.

Why not just write `T extends Comparable<T>`? That form itself is valid for many types, but **narrower**. There are subclasses that inherit `Comparable<Parent>` from a parent type: they can compare subclass objects via the `Comparable<Parent>` contract even without directly implementing `Comparable<Child>`. The `Comparable<? super T>` bound accepts such cases.

Example:

```java
String longestLexicographically =
        max(java.util.List.of("Go", "Java", "C"));

Integer maxScore = max(java.util.List.of(4, 9, 6));
```

Both `String` and `Integer` satisfy the bound, each with its own comparison rules. **`max` relies on `compareTo` ordering**, not string length: `"Java"` is greater than `"Go"` lexicographically in this example. Do not confuse the name `max` with "longest string".

With `T extends Number`, the compiler **does not** allow calling `compareTo()` because `Number` has no such method. Choose the bound based on the operations the algorithm actually needs.

## 8. Complete Java 17+ Program: What Does Each Bound Unlock?

Save all the code below into **`Main.java`**. The example uses:

- `T extends Number` to call `doubleValue()`;
- `T extends Comparable<? super T>` to call `compareTo`;
- `T extends Identified<String> & Named` to call both `id()` and `name()`;
- `T extends Number & Comparable<T>` to use both numeric conversion and comparison.

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    interface Identified<ID> {
        ID id();
    }

    interface Named {
        String name();
    }

    record Product(String id, String name)
            implements Identified<String>, Named {}

    static <T extends Number> double sum(List<T> values) {
        double total = 0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static <T extends Comparable<? super T>> T max(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        T best = values.get(0);
        for (T value : values) {
            if (value.compareTo(best) > 0) {
                best = value;
            }
        }
        return best;
    }

    static <T extends Identified<String> & Named>
    String describe(T entity) {
        return entity.id() + "/" + entity.name();
    }

    static final class PositiveBox<T extends Number & Comparable<T>> {
        private final T value;

        PositiveBox(T value) {
            this.value = value;
        }

        boolean greaterThan(T other) {
            return value.compareTo(other) > 0;
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    static <T extends Number> List<T> aboveThreshold(
            List<T> values, double threshold) {

        List<T> result = new ArrayList<>();
        for (T value : values) {
            if (value.doubleValue() > threshold) {
                result.add(value);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("sum integers: " + sum(List.of(1, 2, 3, 4)));
        System.out.println("sum decimals: " + sum(List.of(1.5, 2.25)));

        System.out.println("max string: " + max(List.of("Go", "Java", "C")));
        System.out.println("max integer: " + max(List.of(4, 9, 6)));

        System.out.println("product: "
                + describe(new Product("P-7", "Pen")));

        PositiveBox<Integer> box = new PositiveBox<>(7);
        System.out.println("larger: " + box.greaterThan(5));
        System.out.println("double: " + box.twice());

        System.out.println("above: "
                + aboveThreshold(List.of(1, 4, 6), 3.0));

        // sum(List.of("A", "B")); // Does not compile: String does not extend Number.
        // PositiveBox<Number> wrong; // Does not satisfy Comparable<Number>.
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
sum integers: 10.0
sum decimals: 3.75
max string: Java
max integer: 9
product: P-7/Pen
larger: true
double: 14.0
above: [4, 6]
```

### Explaining the output and type-checking mechanism

1. `sum(List.of(1,2,3,4))`: the compiler infers `T` compatible with `Integer`; the method only calls `doubleValue()`, which `Number` guarantees. Because `double` is used as the accumulator, the output displays `10.0`.
2. `sum(List.of(1.5,2.25))`: the type argument is compatible with `Double`; the same implementation is reused, resulting in `3.75`.
3. `max(List.of("Go","Java","C"))`: `String` satisfies `Comparable<String>`, so calling `compareTo` is valid; `"Java"` is greatest in lexicographical order.
4. `max(List.of(4,9,6))`: `Integer` also satisfies the bound, resulting in `9`.
5. `describe(Product)`: the `Product` record implements both `Identified<String>` and `Named`, so both methods are called safely.
6. `PositiveBox<Integer>`: `Integer` both extends `Number` and implements `Comparable<Integer>`. `greaterThan(5)` uses `compareTo` and `twice()` uses `doubleValue()`.
7. `aboveThreshold` returns `List<T>`, **preserving the element type** of the input list. With `List<Integer>`, the result still has type `List<Integer>`; the method only compares using the `double` value derived from each element.

**Limitations of the example:** `sum` computes the total via `doubleValue()`, so it is not intended for financial calculations requiring exact decimal precision. For `BigDecimal`, use operations on `BigDecimal` itself or an appropriate abstraction. `max` requires a non-empty list and comparable elements; the program throws `IllegalArgumentException` on an empty list, while `null` values can fail when accessing a method. Upper bounds **do not** automatically exclude `null`.

## 9. A Bound Does Not Mean All Arithmetic Operations Are Valid

A common point of confusion is the word `Number` in a bound. For example:

```java
static <T extends Number> double add(T a, T b) {
    return a.doubleValue() + b.doubleValue();
}
```

This is valid because the addition is performed between **two primitive `double` values**, after calling a method provided by `Number`.

Conversely:

```java
// Does not compile:
// static <T extends Number> T add(T a, T b) {
//     return a + b;
// }
```

Java has no general `+` operator for all `Number` subtypes, and cannot guarantee the result is the same subtype `T`. If `T = Integer`, addition might need overflow handling; if `T = BigDecimal`, addition must go through `add(...)`; if `T = AtomicInteger`, the behavior also differs. An upper bound like `Number` does not invent a universal addition operation for all numbers.

**Choosing the right abstraction:**

- When only approximate statistics/display are needed, converting via `doubleValue()` can be suitable if precision limits are acceptable.
- When exact arithmetic on `BigDecimal` is required, use the specific `BigDecimal.add`, `multiply` APIs and rounding rules.
- When a custom algorithm across multiple numeric types is needed, consider passing an addition function/strategy with an explicit signature instead of unchecked casts.

## 10. Upper Bounds Differ from the `? extends U` Wildcard

The two syntaxes look similar but serve **two different purposes**:

```java
<T extends Number>           // Declares a type variable named T with an upper bound.
List<? extends Number>       // Uses a wildcard in a parameterized type.
```

### 10.1. A type parameter is named and reused

```java
static <T extends Number> T first(List<T> numbers) {
    return numbers.get(0);
}
```

`T` appears in **both the input parameter and the return type**. When the caller passes `List<Integer>`, the result is type-checked as `Integer`, not merely as `Number`.

### 10.2. A wildcard only represents an unknown type at that position

```java
static double sumWildcard(List<? extends Number> numbers) {
    double total = 0;
    for (Number value : numbers) {
        total += value.doubleValue();
    }
    return total;
}
```

The method accepts `List<Integer>`, `List<Double>`, and compatible `Number` subtype lists. It only needs to read each `Number`, and **does not need to name the element type** or return a specific `T`.

### Comparison table

| Point of comparison | `<T extends Number>` | `? extends Number` |
| --- | --- | --- |
| Role | Declares a named type parameter | Specifies a wildcard when using a generic type |
| Has a name `T` to reuse in multiple places? | Yes | No |
| When appropriate | Linking input and output types, multiple parameters of the same type, algorithms that must preserve `T` | Only reading from a structure containing numbers of some subtype |
| Used in method declaration | `static <T extends Number> ...` | Wildcards are not used as declared type parameters |
| Used in `List` | `List<T>` after `T` has been declared | `List<? extends Number>` |
| Allows adding an arbitrary `Number` to the list? | Must match the exact `T` and list kind | No, because the specific element type is unknown |

Example:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> numbers = integers;

// numbers.add(3.14); // Does not compile.
// numbers.add(10);   // Also does not compile.
```

Because `numbers` could actually reference a `List<Integer>`, the compiler must prevent adding a `Double` or an arbitrary `Number`. Adding `null` is possible via applicable operations, though that is unhelpful when the goal is adding valid numbers.

### Upper bounds do not make generic containers covariant

```java
List<Integer> integers = new ArrayList<>();

// Does not compile:
// List<Number> allNumbers = integers;

List<? extends Number> readNumbers = integers; // Valid.
```

`Integer extends Number` does not make `List<Integer>` a subtype of `List<Number>`: Java generic types are **invariant** by default. Upper bounds on `T` and the `? extends Number` wildcard help write flexible APIs in different ways, but do not alter that rule.

## 11. Bounds and Inheritance Between Generic Classes

A subclass can **preserve or narrow** the bound of a type parameter when passing it to a superclass:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NumberBox<N extends Number> extends Box<N> {
    NumberBox(N value) {
        super(value);
    }

    double asDouble() {
        return get().doubleValue();
    }
}
```

`Box<T>` accepts any reference type, whereas `NumberBox<N>` only accepts subtypes of `Number`. `NumberBox<Integer>` is valid; `NumberBox<String>` is invalid.

Conversely, if the superclass already has a bound:

```java
class NumericStore<T extends Number> {}

// Does not compile:
// class BadStore<T> extends NumericStore<T> {}
```

The compiler cannot guarantee that a completely unconstrained `T` satisfies `T extends Number` required by `NumericStore`. Fix it by keeping the bound:

```java
class GoodStore<T extends Number> extends NumericStore<T> {}
```

Or pass a specific valid subtype directly:

```java
class IntegerStore extends NumericStore<Integer> {}
```

Bounds on a superclass/interface are part of its contract: a subclass passing a type argument must satisfy the constraint required by the parent type.

## 12. Bounds and Type Erasure at Runtime

Java generics are primarily implemented via **type erasure**: the compiler checks types at compile time, then erases most type arguments and type variables in the bytecode. With `T extends Number`, the erased type of `T` is typically the **leftmost bound** `Number`, rather than `Object` as for an unbounded type parameter.

In:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

the compiled code can call `Number.doubleValue()` because the erasure of the type variable resolves to `Number`. When multiple bounds are present, the compiler may insert casts and bridge methods if needed to preserve polymorphic behavior.

This **does not** create a separate runtime class for each `T`, nor does it make the following checks valid:

```java
// Does not compile:
// if (object instanceof List<Integer>) { ... }

// Does not compile:
// T item = new T();

// Does not compile:
// T[] items = new T[10];
```

If you need to create an object of type `T`, a safer approach is to accept a **factory** of type `Supplier<T>` or a passed-in constructor/factory:

```java
static <T extends Number> T fromFactory(
        java.util.function.Supplier<T> supplier) {
    return supplier.get();
}
```

The caller can pass `() -> Integer.valueOf(5)`; that is a real object created by the factory, not `new T()` with the compiler guessing a constructor across every subclass.

If runtime type checking is needed for a single value, you can pass `Class<T>` into the method and use `Class.cast` or the corresponding check method. However, `Class<List<Integer>>` does not fully represent a nested generic type at runtime in the form `List<Integer>.class`; validating complex structures may require a type reference/schema or element-by-element checking.

## 13. Common Misconceptions and Pitfalls

**Pitfall 1 — using `implements` in a bound:** do not write `<T implements Runnable>`. Type parameter bounds always use `extends`, even when `Runnable` is an interface.

**Pitfall 2 — thinking `T extends Number` only accepts `Number` itself:** the bound allows both `Number` and compatible subtypes. `Integer`, `Long`, `Double`, and `BigDecimal` are all valid examples.

**Pitfall 3 — calling a method not present in the bound:** `value.compareTo(other)` is not guaranteed with `T extends Number`. You need an appropriate `Comparable` bound or a strategy.

**Pitfall 4 — using arithmetic operators directly on `T`:** `a + b` is invalid for two variables typed only as `T extends Number`. Switch to operations guaranteed by the bound or use a concrete abstraction.

**Pitfall 5 — placing multiple class bounds or getting the order wrong:**

```java
// Invalid:
// <T extends Runnable & Number>
// <T extends Number & java.util.AbstractList<T>>
```

If a class is present, it must come first; subsequent bounds are interfaces. There cannot be two distinct superclasses for a single type parameter.

**Pitfall 6 — forgetting that bounds must be satisfied in subclasses:** if `Parent<T extends Number>`, then `Child<T> extends Parent<T>` is invalid when `T` does not yet have a compatible bound.

**Pitfall 7 — assuming an upper bound eliminates `null`:** compatible reference types can still hold `null`. Calling `doubleValue()` on `null` still throws `NullPointerException`; validation and generic types are two separate concerns.

**Pitfall 8 — confusing a type parameter with a wildcard:** `<T extends Number>` creates a reusable type name; `? extends Number` is an unknown exact type at a single position. Choose based on whether input and output need to be linked.

**Pitfall 9 — assuming `T extends Number` means all numbers compare the same way:** `Number` does not declare `compareTo`; `BigDecimal` and `Double` also have different arithmetic semantics. Do not infer properties not present in the bound.

**Pitfall 10 — using unchecked casts to bypass a bound:** `(T) arbitraryObject` does not turn the actual object into `T`, and can produce unchecked warnings and runtime errors. Design a concrete contract or validate at the boundary.

**Pitfall 11 — expecting `T` to have a default constructor:** even with an upper bound, `new T()` remains invalid. Use a factory/supplier or pass in an already-created object.

**Pitfall 12 — using `T` as a primitive type argument:** `List<int>` and `<T extends int>` are invalid. Use an appropriate wrapper/reference type or a primitive-specialized structure if performance requires it.

**Pitfall 13 — getting the order wrong in multiple bounds:** when a class bound appears, it must come first; `T extends Comparable<T> & Number` is invalid because `Number` is a class placed after an interface.

**Pitfall 14 — forgetting precision limits of numeric conversions:** `doubleValue()` is type-valid but does not guarantee preserving all digits of a `BigDecimal` or every `long`. Check business requirements before using a general algorithm via `double`.

## 14. Workflow for Choosing an Appropriate Upper Bound

Before declaring `<T extends U>`, start from **the operations actually needed**:

1. **List the methods to be called**: `doubleValue()`, `length()`, `compareTo()`, `id()`, or `name()`?
2. **Find the smallest suitable common contract**: `Number`, `CharSequence`, `Comparable<? super T>`, or a custom business interface?
3. **Check whether all expected type arguments** satisfy the bound; one concrete class does not necessarily represent all subtypes.
4. **Determine whether the output needs to preserve `T`**: return `T`, `List<T>`, or only a fixed type like `double` or `String`?
5. **Consider a wildcard** if the method only reads from a generic structure and does not need to name the type to link multiple positions.
6. **Account for null, empty data, and precision**: bounds only describe type capabilities, not value constraints.
7. **Keep the signature as simple as meets the contract**: every bound should have a clear reason; avoid adding unused constraints.

| Need | Commonly suitable upper bound |
| --- | --- |
| Access `doubleValue()` or `longValue()` | `<T extends Number>` |
| Read string/character length | `<T extends CharSequence>` |
| Compare elements of the same type or compatible supertype | `<T extends Comparable<? super T>>` |
| Need both `Number` features and `compareTo` | `<T extends Number & Comparable<T>>` when compatible with actual type arguments |
| Need an ID of a specific type | `<T extends HasId<String>>` |
| Need both an ID and a name | `<T extends Identified<String> & Named>` |
| Only iterate a list of numbers to read | `List<? extends Number>` may suffice, without needing a named `T` |

## 15. Self-Check Exercises

**Question 1.** Why can't `static <T> double doubleValue(T value)` call `value.doubleValue()` directly?

**Answer:** `T` has no upper bound expressing that capability. If the compiler allowed it, the method could be called with `String` or any reference type without `doubleValue()`. Add `T extends Number` when the true intent is to work with `Number`.

**Question 2.** With `static <T extends Number> double twice(T value)`, is `twice(4)` valid?

**Answer:** Yes. The `int` literal is boxed compatibly to `Integer` during generic method inference/invocation. `Integer` is a subtype of `Number`.

**Question 3.** Can a method with `T extends Number` call `compareTo()` on `T`?

**Answer:** No. `Number` does not declare `compareTo`. If comparison is needed, constrain with `Comparable<? super T>` or appropriate multiple bounds.

**Question 4.** How many contracts does `<T extends Identified<String> & Named>` require `T` to satisfy?

**Answer:** Both: `Identified<String>` and `Named`. The `&` represents the intersection of bounds; the chosen class must satisfy all of them.

**Question 5.** Can `List<Integer>` be assigned directly to `List<Number>`? Can it be assigned to `List<? extends Number>`?

**Answer:** It cannot be assigned directly to `List<Number>` because generic types are invariant. It can be assigned to `List<? extends Number>` to read values of an unknown subtype; you cannot add an arbitrary `Number` through that wildcard reference.

**Question 6.** Why can't you write `new T()` in a `<T extends Number>` method?

**Answer:** An upper bound does not guarantee that every subtype of `Number` has a valid no-arg constructor, and erasure does not retain the type argument for direct instantiation. Use a factory or a passed-in object.

**Question 7.** If the parent class is `class NumericStore<T extends Number>`, is `class Child<T> extends NumericStore<T>` valid?

**Answer:** No, because `Child`'s `T` is unbounded. You need `class Child<T extends Number> extends NumericStore<T>` or to choose a specific type argument satisfying `Number`.

**Question 8.** Does `max(List<String>)` in the example rely on string length or `compareTo`?

**Answer:** It relies on `compareTo`, i.e. the natural comparison order of `String` per the Java contract, not length. A function's name does not imply business criteria on its own.

## Summary

The `<T extends U>` syntax places an **upper bound** on type parameter `T`, enabling the compiler to check and permit operations guaranteed by `U`. A bound can be a class, an interface, a type variable, or multiple bounds combined with `&`. A method with `T extends Number` can call `doubleValue()` but **cannot** automatically call `compareTo()` or use arithmetic operators directly on `T`; adding capabilities requires adding bounds or designing an appropriate abstraction. When input and output types must be precisely linked, a named type parameter is more useful than a wildcard; when only reading data, `? extends U` can be simpler. Upper bounds primarily guarantee **compile-time types**, and do not replace `null` checks, numeric precision, runtime data validation, or business rules.