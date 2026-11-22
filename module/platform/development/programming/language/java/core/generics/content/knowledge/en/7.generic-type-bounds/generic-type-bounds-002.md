# Bounds with Classes or Interfaces in Java Generics

In Java Generics, an explicitly unbounded type parameter such as `<T>` can represent many different reference types. That helps code reuse, but the compiler only guarantees the operations available on `Object`. If an algorithm must call `doubleValue()`, `compareTo()`, `run()`, or a method belonging to a specific interface, you need a **type bound** right at the type parameter declaration.

The basic syntax is `<T extends Bound>`. `Bound` can be a **class** or an **interface**; in both cases Java uses the `extends` keyword. For multiple simultaneous requirements, you can use bounds joined with `&`, such as `<T extends Number & Comparable<T>>`. These bounds are checked primarily **at compile time** and participate in type inference at each call site.

This article explains the mechanism, syntax, how to apply bounds to classes, interfaces, records, and generic methods, multiple bounds, generic inheritance, runnable Java 17+ examples, connections to wildcards and type erasure, and common mistakes. The goal is to know **when a bound is needed, what the compiler can prove from a bound, and when not to make an API more complex than necessary**.

## 1. Choosing Between a Class Bound and an Interface Bound

Without a bound, an ordinary type variable `T` is only guaranteed the capabilities of `Object`; therefore you cannot call `value.doubleValue()` on any `T`. With `<T extends Number>`, the compiler knows the `doubleValue()` method exists, though this also **narrows the set of type arguments** to types compatible with `Number`.

This article focuses on answering the design question: **when should you choose a class as a bound, when should you choose an interface, and how does that choice change the API?**

- **Class bound** such as `Number`: reuses an existing contract while requiring an inheritance relationship with the class.
- **Interface bound** such as `Runnable`: requires a capability that classes across different inheritance hierarchies can implement.
- **Parameterized interface bound** such as `Identified<ID>`: preserves the type relationship of a result or identifier through a generic contract.

If you only need `double twice(Number value)` with no `T` relationship to preserve, a signature taking `Number` directly can be simpler. In the following sections, the class/interface comparison is verified with standalone Java 17 programs.

## 2. Bounding with a Class: `<T extends Number>`

The first program shows the same generic method working with two subtypes of `Number`.

Create `ClassBoundDemo.java`:

```java
public class ClassBoundDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static <T extends Number> T chooseFirst(T first, T second) {
        return first;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(twice(2.5));

        Integer selected = chooseFirst(10, 20);
        System.out.println(selected);
    }
}
```

Compile and run:

```bash
javac ClassBoundDemo.java
java ClassBoundDemo
```

`stdout` output:

```text
6.0
5.0
10
```

### Reading each constraint

**`twice(T value)`:** the compiler allows calling `doubleValue()` on `value` because `T` is bounded by `Number`. The call `twice(3)` uses boxing as needed to produce a reference type; generic type arguments do not accept primitive `int` directly. The function's result is primitive `double`.

**`chooseFirst(T first, T second)`:** both parameters and the return type use **the same type variable `T`**. With two `Integer` arguments, a valid type choice is `T=Integer`; the caller can receive `Integer` without casting.

The `Number` bound only requires values compatible with `Number`; it **does not** force both arguments to have the exact same runtime class. If the two types differ, the compiler can solve the constraints to find a suitable type (for example, a common supertype) depending on the target context. Do not use `<T extends Number>` as a mechanism to check that "two runtime classes must be equal".

### What operations does a class bound allow?

With `<T extends Number>`, the compiler can allow appropriate public instance methods from `Number` such as `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`. However, it **does not** automatically allow calling methods that only exist on `Integer` or `BigDecimal` and are not part of `Number`'s contract.

For example, `value.compareTo(other)` is not guaranteed from the `Number` bound alone. `Number` does not declare `compareTo`. If the algorithm also needs comparison, you must add an interface bound or accept a separate `Comparator`.

### Which types satisfy the `Number` bound?

`Integer`, `Long`, `Double`, `Float`, `Short`, `Byte`, `java.math.BigDecimal`, and `java.math.BigInteger` are all examples of `Number` subtypes. `String` is not a subtype of `Number`, even though you can convert a numeric string to a number using a parse method.

`Number` is an abstract class, yet it is completely valid as a bound; a type argument can be `Number` itself or a compatible subtype. **A bound does not require calling `new Number()`**, and being an abstract class is not an obstacle to a generic constraint.

## 3. Bounding with an Interface: Still Using `extends`

Generic declaration:

```java
static <T extends Runnable> void execute(T task) {
    task.run();
}
```

The `extends` keyword here applies to the **`Runnable` interface**, even though a concrete class implementing the interface uses `implements Runnable`. These are two different syntactic positions:

- `class Job implements Runnable`: a **class** implementing an interface.
- `<T extends Runnable>`: a **type parameter** whose upper bound is an interface.
- Do not write `<T implements Runnable>`; that is invalid syntax.

### Example with `Runnable`

Create `InterfaceBoundDemo.java`:

```java
public class InterfaceBoundDemo {
    static final class Printer implements Runnable {
        private final String message;

        Printer(String message) {
            this.message = message;
        }

        @Override
        public void run() {
            System.out.println(message);
        }
    }

    static <T extends Runnable> void execute(T task) {
        task.run();
    }

    public static void main(String[] args) {
        execute(new Printer("running"));
        execute(() -> System.out.println("lambda"));
    }
}
```

Compile and run:

```bash
javac InterfaceBoundDemo.java
java InterfaceBoundDemo
```

`stdout`:

```text
running
lambda
```

`Printer` implements `Runnable`, so it is valid as an argument to `execute`. Java also infers how to call `execute` with a lambda, because the generic parameter context carries the functional interface bound `Runnable`.

If you pass an object that does not implement `Runnable`, the compiler cannot prove the bound and will reject the call. A generic method does not automatically turn an arbitrary object into a `Runnable`; a proper type relationship must exist.

### An interface that is itself generic

A bound does not have to be a non-generic interface. For example:

```java
interface Identified<ID> {
    ID id();
}

static <ID, T extends Identified<ID>> ID extractId(T value) {
    return value.id();
}
```

This is an illustrative declaration snippet (the method must be placed inside an appropriate class). In `<ID, T extends Identified<ID>>`, both `ID` and `T` are type parameters of the method; `T` is bounded by **an interface with the type argument `ID` applied**. Therefore `extractId` returns the exact `ID` type corresponding to the input value.

The key point is not the variable names `ID` or `T`, but the **relationship written in the bound**: `T` must implement `Identified<ID>` in a compatible parameterized way.

## 4. A Complete Program: Bounding with a Generic Interface

Create `GenericInterfaceBoundDemo.java`:

```java
public class GenericInterfaceBoundDemo {
    interface Identified<ID> {
        ID id();
    }

    record User(Long id, String name) implements Identified<Long> {
    }

    record Product(String id, String title)
            implements Identified<String> {
    }

    static <ID, T extends Identified<ID>> ID extractId(T item) {
        return item.id();
    }

    public static void main(String[] args) {
        User user = new User(42L, "Lan");
        Product product = new Product("P-5", "Book");

        Long userId = extractId(user);
        String productId = extractId(product);

        System.out.println(userId);
        System.out.println(productId);
    }
}
```

Run:

```bash
javac GenericInterfaceBoundDemo.java
java GenericInterfaceBoundDemo
```

`stdout`:

```text
42
P-5
```

Analysis:

1. `Identified<ID>` is a generic interface; `ID` represents the identifier type.
2. `User` fixes the interface to `Identified<Long>`; `Product` fixes it to `Identified<String>`.
3. `<ID, T extends Identified<ID>>` declares two type parameters and links them.
4. `extractId(user)` can infer a result compatible with `Long`; `extractId(product)` is compatible with `String`.
5. The generic bound allows calling `item.id()` and preserves the return type relationship with the interface. It does not verify whether the ID value exists in a database; that is a separate business requirement.

A method taking only `Identified<ID>` can also suffice for this problem:

```java
static <ID> ID extractId(Identified<ID> item) {
    return item.id();
}
```

The shorter signature still preserves the `ID` relationship. You only need `T extends Identified<ID>` when the exact subtype `T` must appear elsewhere in the method or in the return contract.

## 5. Multiple Bounds: A Type Parameter Must Satisfy Multiple Requirements

If an algorithm needs both a base class and an interface, you can write **multiple bounds**:

```java
<T extends SomeClass & SomeInterface>
```

The `&` here represents the **intersection of bounds**: `T` must be compatible with both bounds. Syntax rules:

1. There can be **at most one explicit class bound**, and if present it **must come first**.
2. After the class bound there can be one or more interface bounds.
3. If all bounds are interfaces, you can start with any interface and join the others with `&`.
4. Use `extends` **once** before the list of bounds; remaining bounds are joined with `&`.
5. Bounds are not a union `|`; `T` must satisfy **all** conditions, not just one.

Valid examples:

```java
<T extends Number & Comparable<T>>
<T extends Runnable & AutoCloseable>
<T extends java.io.Serializable & Comparable<T>>
```

The lines above are sample type-parameter list declarations (not standalone runnable programs). Conversely, `<T extends Runnable & Number>` is invalid because if `Number` is used as a class bound, it must come first.

### Why isn't `Number` enough for comparison?

`Number` provides conversions to primitive numeric types but does not declare `compareTo`. When you need to return the larger value according to a natural ordering, you must guarantee both the ability to accept a value of type `T` and comparability.

```java
static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`Integer`, `Long`, and `Double` all fit this signature in separate calls because each wrapper implements `Comparable` for its corresponding type. `java.math.BigDecimal` also satisfies it. However, a custom `Number` subclass that does not implement `Comparable<T>` will not fit, even if it has `doubleValue()`.

## 6. Example Combining a Class Bound and an Interface Bound

Create `MultipleBoundDemo.java`:

```java
public class MultipleBoundDemo {
    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T extends Number & Comparable<T>> double doubledMax(
            T a, T b) {
        return larger(a, b).doubleValue() * 2;
    }

    public static void main(String[] args) {
        Integer topScore = larger(8, 12);
        Double topPrice = larger(2.5, 1.5);

        System.out.println(topScore);
        System.out.println(topPrice);
        System.out.println(doubledMax(3, 7));
    }
}
```

Run:

```bash
javac MultipleBoundDemo.java
java MultipleBoundDemo
```

`stdout`:

```text
12
2.5
14.0
```

In `larger`:

- `Number` allows treating the values as `Number` objects, though this method alone only uses `compareTo`.
- `Comparable<T>` allows calling `a.compareTo(b)` with `b` of type `T`.
- Return type `T` preserves the type relationship with the two parameters.
- `doubledMax` needs both `compareTo` to find the larger element and `doubleValue()` to return `double`.

Separate examples with `Integer` and `Double` do not mean a generic method can arbitrarily compare an `Integer` with a `Double` by calling `compareTo`. The two wrappers implement `Comparable` with different type arguments; a call mixing both types does not arbitrarily satisfy the `Comparable<T>` bound. If the goal is comparing mixed `Number` types, define a specific comparison strategy (such as converting to `double`, noting precision loss) rather than assuming a common natural order.

### When should you choose `Comparable<? super T>`?

An often more flexible signature is:

```java
static <T extends Comparable<? super T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`Comparable<? super T>` accepts cases where a type `T` is comparable with **a supertype of `T`**, such as via an inherited `Comparable<Base>` interface on a subtype. This style is common in the Java Collections API. It does not require `T` to be a `Number`; `String` can also be compared.

The signature `<T extends Number & Comparable<? super T>>` is used when you need **both** `Number` behavior and natural ordering. Choose the minimal yet correct bound so you do not exclude other valid types.

## 7. Multiple Interface Bounds: No Class Bound Needed

If an algorithm needs two independent interface contracts, you can constrain `T` with both:

```java
static <T extends Runnable & AutoCloseable> void executeAndClose(T task)
        throws Exception {
    try (task) {
        task.run();
    }
}
```

This is a valid Java 17 method when placed in a class. `Runnable` guarantees `run()`; `AutoCloseable` allows using `task` in try-with-resources to close it after execution, even if `run` throws an exception.

### Complete program

Create `InterfaceIntersectionDemo.java`:

```java
public class InterfaceIntersectionDemo {
    static final class Job implements Runnable, AutoCloseable {
        @Override
        public void run() {
            System.out.println("running");
        }

        @Override
        public void close() {
            System.out.println("closed");
        }
    }

    static <T extends Runnable & AutoCloseable> void executeAndClose(T task)
            throws Exception {
        try (task) {
            task.run();
        }
    }

    public static void main(String[] args) throws Exception {
        executeAndClose(new Job());
    }
}
```

Compile and run:

```bash
javac InterfaceIntersectionDemo.java
java InterfaceIntersectionDemo
```

`stdout`:

```text
running
closed
```

`Job` must implement **both** `Runnable` and `AutoCloseable`. An object implementing only `Runnable` does not satisfy the other bound. The order of interface bounds may not change which members the compiler can prove, but bound order matters in **type erasure**, because the first bound is used when erasing the type variable.

Note: `AutoCloseable.close()` can declare throwing `Exception`, so the example permits the exception via `throws Exception`. This is a normal exception contract, not a special privilege of Generics.

## 8. Generic Class with a Class Bound

Bounds do not apply only to generic methods. You can declare them directly on a class:

```java
class NumericBox<T extends Number> {
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

This is an illustrative class without `main`. `T extends Number` is scoped across the instance members of `NumericBox`: the field `value` has type `T`, `get()` returns `T`, and `asDouble()` calls a method available on `Number`.

With `NumericBox<Integer>`, `get()` has expression type `Integer`; with `NumericBox<java.math.BigDecimal>`, it has type `BigDecimal`. Both can call `asDouble()`.

### Full example

Create `BoundedClassDemo.java`:

```java
public class BoundedClassDemo {
    static final class NumericBox<T extends Number> {
        private final T value;

        NumericBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> count = new NumericBox<>(6);
        NumericBox<Double> weight = new NumericBox<>(1.25);

        Integer countValue = count.get();

        System.out.println(countValue);
        System.out.println(count.twice());
        System.out.println(weight.twice());
    }
}
```

Run `javac BoundedClassDemo.java` then `java BoundedClassDemo`:

```text
6
12.0
2.5
```

`NumericBox<String>` is a compile error because `String` does not satisfy `Number`. Java does not automatically parse a string like `"6"` into a number to satisfy a generic bound.

If a class has multiple type parameters, constrain only the variables that need it:

```java
class Measurement<ID, N extends Number> {
    private final ID id;
    private final N value;

    Measurement(ID id, N value) {
        this.id = id;
        this.value = value;
    }

    ID id() { return id; }
    N value() { return value; }
}
```

Here `ID` has no explicit bound; `N` is bounded by `Number`. You can use `Measurement<String,Integer>` or `Measurement<Long,Double>`. `N`'s bound does not apply to `ID`.

## 9. Generic Interfaces and Records with Bounds

A generic interface can constrain its own type parameter:

```java
interface NumericSource<T extends Number> {
    T read();
}
```

Every class implementing `NumericSource<T>` must pass a type argument matching the bound. If the subclass remains generic, it must forward that constraint.

A record also supports bounds:

```java
record Range<T extends Comparable<? super T>>(T from, T to) {
    Range {
        if (from.compareTo(to) > 0) {
            throw new IllegalArgumentException("from > to");
        }
    }
}
```

Record components `from` and `to` share type `T`. The `Comparable<? super T>` bound lets the compiler call `compareTo`; the compact constructor enforces the **business invariant** "from is not greater than to". A generic type bound by itself does not guarantee the ordering of two values — the check inside the constructor does that.

Create `BoundedRecordDemo.java`:

```java
public class BoundedRecordDemo {
    record Range<T extends Comparable<? super T>>(T from, T to) {
        Range {
            if (from.compareTo(to) > 0) {
                throw new IllegalArgumentException("from > to");
            }
        }
    }

    public static void main(String[] args) {
        Range<Integer> pageRange = new Range<>(1, 5);
        Range<String> nameRange = new Range<>("A", "Z");

        System.out.println(pageRange.from() + ".." + pageRange.to());
        System.out.println(nameRange.from() + ".." + nameRange.to());
    }
}
```

Run:

```bash
javac BoundedRecordDemo.java
java BoundedRecordDemo
```

`stdout`:

```text
1..5
A..Z
```

If `from` or `to` is null, the example will throw `NullPointerException` when calling `compareTo`. You can add `Objects.requireNonNull` if you want a clearer error and message; a generic bound does not forbid null on its own.

## 10. Bounds and Inheritance: Subclasses Must Forward Constraints Properly

Suppose the superclass requires `T extends Number`:

```java
class NumericStore<T extends Number> {
    final T value;

    NumericStore(T value) {
        this.value = value;
    }
}
```

A subclass that remains generic must provide a type argument that always satisfies the superclass's bound:

```java
class AuditedStore<N extends Number> extends NumericStore<N> {
    AuditedStore(N value) {
        super(value);
    }
}
```

This is a valid declaration; `AuditedStore<Integer>` becomes a `NumericStore<Integer>`, and `AuditedStore<Double>` becomes a `NumericStore<Double>`. `N` belongs to the subclass and is **forwarded** as the parent's type argument.

Conversely:

```java
// Does not compile:
// class BadStore<U> extends NumericStore<U> {
//     BadStore(U value) { super(value); }
// }
```

Because `U` has no bound, the compiler cannot prove `U` is always compatible with `Number`. You can fix this with `U extends Number`, or fix the subclass to `extends NumericStore<Integer>` when business semantics only need `Integer`.

### Complete runnable example

Create `BoundedInheritanceDemo.java`:

```java
public class BoundedInheritanceDemo {
    static class NumericStore<T extends Number> {
        private final T value;

        NumericStore(T value) {
            this.value = value;
        }

        double doubleValue() {
            return value.doubleValue();
        }
    }

    static final class AuditedStore<N extends Number>
            extends NumericStore<N> {
        private final String label;

        AuditedStore(String label, N value) {
            super(value);
            this.label = label;
        }

        void print() {
            System.out.println(label + "=" + doubleValue());
        }
    }

    public static void main(String[] args) {
        AuditedStore<Integer> items = new AuditedStore<>("items", 3);
        AuditedStore<Double> weight = new AuditedStore<>("kg", 2.5);

        items.print();
        weight.print();
    }
}
```

Run:

```bash
javac BoundedInheritanceDemo.java
java BoundedInheritanceDemo
```

`stdout`:

```text
items=3.0
kg=2.5
```

The bound does not need to be repeated using **the exact same letter name** as in the parent: `NumericStore<T>` and `AuditedStore<N>` declare two type parameters belonging to two different classes. The clause `extends NumericStore<N>` together with `N`'s bound ensures a valid mapping.

## 11. Bounds Do Not Create Subtype Relationships Between Parameterizations

Even though `Integer extends Number`:

```java
NumericBox<Integer> integers = new NumericBox<>(5);
// NumericBox<Number> numbers = integers; // Invalid.
```

The illustrative line above assumes `NumericBox<T extends Number>` has already been declared.

Generic types are normally **invariant** in their type arguments. The bound `T extends Number` only restricts **which types can be used as `T`**, and does not make `NumericBox<Integer>` a subtype of `NumericBox<Number>`.

To let a method read values from different kinds of `NumericBox`, it can accept a wildcard:

```java
static void printValue(NumericBox<? extends Number> box) {
    Number n = box.get();
    System.out.println(n);
}
```

`? extends Number` here is an **upper-bounded wildcard** used as a type argument, different from `<T extends Number>` which is a **named type parameter declaration**. Both syntaxes express an upper limit, yet serve two different roles.

### When to use a type parameter, when to use a wildcard?

- Use `<T extends Number>` when you need to **name type `T` and link `T` across multiple positions**, such as `T min(T a,T b)`.
- Use `List<? extends Number>` when a parameter primarily **supplies** values read as `Number` without needing to carry the specific element type into the result.
- Use `List<? super Integer>` when you need to **add `Integer`** to a list that can hold `Integer` or a supertype of `Integer`; this is a lower-bounded wildcard, not a multiple bound on a type parameter.
- Avoid using raw types just to bypass compile-time bounds.

In particular, Java **does not declare a lower bound for a named type parameter** in the form `<T super Number>`. That syntax is invalid. `super` appears in **wildcard type arguments**, such as `List<? super Number>`.

## 12. Recursive Bounds and `Comparable`

Some generic interfaces describe objects that can operate on their own type. Java allows a type parameter to appear within its own bound:

```java
<T extends Comparable<T>>
```

This is a **recursive bound**, not a runtime loop. It states that type `T` must be compatible with `Comparable<T>`. When writing a generic method that needs ordering, `Comparable` is a familiar choice.

### Why is `Comparable<? super T>` more flexible?

Suppose class `Animal` implements `Comparable<Animal>`; a subtype `Dog extends Animal` inherits the ability to compare against `Animal`. `Dog` does not necessarily implement `Comparable<Dog>` directly. Thus:

```java
<T extends Comparable<? super T>>
```

can accept `Dog` through `Comparable<Animal>` — comparison typed for a **supertype** of `Dog`. This is why many signatures in the JDK use the pattern `Comparable<? super T>` instead of `Comparable<T>`.

### Demonstrating example

Create `ComparableBoundDemo.java`:

```java
public class ComparableBoundDemo {
    static class Animal implements Comparable<Animal> {
        private final int weight;

        Animal(int weight) {
            this.weight = weight;
        }

        @Override
        public int compareTo(Animal other) {
            return Integer.compare(weight, other.weight);
        }

        @Override
        public String toString() {
            return "Animal(" + weight + ")";
        }
    }

    static final class Dog extends Animal {
        Dog(int weight) {
            super(weight);
        }
    }

    static <T extends Comparable<? super T>> T greater(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Dog light = new Dog(5);
        Dog heavy = new Dog(9);

        Dog winner = greater(light, heavy);
        System.out.println(winner);
    }
}
```

Run:

```bash
javac ComparableBoundDemo.java
java ComparableBoundDemo
```

`stdout`:

```text
Animal(9)
```

`Dog` satisfies `Comparable<? super Dog>` because it inherits `Comparable<Animal>`, and `Animal` is a supertype of `Dog`. The result can still be used with static type `Dog` when inference chooses `T=Dog`.

Do not infer that every subtype of a type implementing `Comparable` has a total order suited to your business logic. If `compareTo` is defined inconsistently with `equals` or is non-transitive, sorting algorithms and ordered collections may behave unpredictably. A bound only proves **the ability to call the method**, not the correctness of the comparison algorithm.

## 13. Multiple Bounds and Members with Matching Signatures

If bounds contain methods with the same name, the compiler must determine that there is a **compatible** inherited method contract. Multiple bounds are not a mechanism for merging arbitrary APIs with conflicting return types.

Example of two interfaces with compatible method signatures:

```java
interface Named {
    String name();
}

interface Labeled {
    String name();
}

static <T extends Named & Labeled> String display(T value) {
    return value.name();
}
```

This is an illustrative declaration snippet: the two interfaces declare the same `String name()` method, so one implementation can satisfy both with a single method.

If two interfaces define methods with the same parameter signature but incompatible return types, you cannot assume the intersection bound is valid. Java applies inherited method and return-type conflict rules.

Another note: only one explicit class bound is allowed and the class bound must come first. Syntax like `<T extends ClassA & ClassB>` with two class bounds is invalid, even if `ClassB` has an inheritance relationship with `ClassA`. When a combined contract is needed, typically one class comes first followed by interfaces.

## 14. Type Erasure: How Bounds Affect the Erased Type

Java Generics use **type erasure** at compile time. Bound checking occurs at compile time; type variables are not preserved as a specialized runtime type per type argument.

Rules to remember:

1. A type parameter without an explicit bound is usually erased to `Object`.
2. `<T extends Number>` is erased to `Number`.
3. `<T extends Runnable & AutoCloseable>` is erased to **the first bound, `Runnable`**; the compiler still enforces the other bounds in source code and may insert necessary casts.
4. Generic types `List<Integer>` and `List<String>` do not become two different runtime `ArrayList` classes solely because of their type arguments.
5. The compiler may generate bridge methods or casts to maintain generic contracts and polymorphism after erasure.

### Observing bounds via reflection

Create `ErasureBoundDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class ErasureBoundDemo {
    static <T extends Number> double doubleValue(T number) {
        return number.doubleValue();
    }

    public static void main(String[] args) throws Exception {
        Method method = ErasureBoundDemo.class
                .getDeclaredMethod("doubleValue", Number.class);
        TypeVariable<?> type = method.getTypeParameters()[0];

        System.out.println(type.getName());
        System.out.println(type.getBounds()[0].getTypeName());
        System.out.println(method.getParameterTypes()[0].getTypeName());
    }
}
```

Compile/run:

```bash
javac ErasureBoundDemo.java
java ErasureBoundDemo
```

`stdout`:

```text
T
java.lang.Number
java.lang.Number
```

`getTypeParameters()` reads the metadata of type parameter `T` from the **method declaration**. `getBounds()` reports the upper bound `Number`. The runtime parameter of the method has been erased to `Number`, so reflection looks up the method with `Number.class`, not with a nonexistent `T.class`.

This **does not** mean reflection can recover the exact type argument inferred at each method invocation. Generic declaration metadata is different from each call creating a specialized runtime method.

### Do not overload solely based on erased bounds/type arguments

Example:

```java
// Cannot declare both in the same class:
// void add(java.util.List<String> list) {}
// void add(java.util.List<Integer> list) {}
```

Both parameters erase to `List`, causing a name clash. Similarly, two generic methods whose parameter signatures match after erasure cannot be distinguished merely by type variable names `T` and `U`.

## 15. Class Tokens and Factories: Bounds Do Not Allow `new T()`

Even with `T extends Number` or `T extends Runnable`, Java still does not allow writing:

```java
// Invalid in a generic method/class:
// T value = new T();
// Class<T> runtimeType = T.class;
```

A bound guarantees **type relationships and a set of methods**; it does not guarantee a constructor that can be invoked directly via `T`, nor does it create a runtime class token named `T`.

If you need to create a value of type `T`, you should **accept a factory or `Supplier`** from the caller:

Create `BoundedFactoryDemo.java`:

```java
import java.util.function.Supplier;

public class BoundedFactoryDemo {
    static final class Task implements Runnable {
        @Override
        public void run() {
            System.out.println("task");
        }
    }

    static <T extends Runnable> T createAndRun(
            Supplier<? extends T> factory) {
        T task = factory.get();
        task.run();
        return task;
    }

    public static void main(String[] args) {
        Task task = createAndRun(Task::new);
        System.out.println(task.getClass().getSimpleName());
    }
}
```

Run:

```bash
javac BoundedFactoryDemo.java
java BoundedFactoryDemo
```

`stdout`:

```text
task
Task
```

`Supplier<? extends T>` produces a value compatible with `T`, and the bound `T extends Runnable` allows calling `run()`. This is how to combine a factory with a generic bound without violating `new T()`.

If the factory returns `null`, `task.run()` will throw `NullPointerException`; if you need a clearer message, add `Objects.requireNonNull(factory.get())`. Generic bounds do not guarantee non-null.

## 16. Bounds Can Be Parameterized Generic Types

An upper bound can be a generic interface with a type argument applied:

```java
<T extends Comparable<T>>
<T extends Comparable<? super T>>
<T extends java.lang.Iterable<String>>
```

For example, `<T extends Iterable<String>>` tells the compiler every `T` can be iterated over and each yielded element has type `String` at the source-code level. An implementation of `Iterable<String>`, such as `List<String>`, fits.

Create `ParameterizedInterfaceBoundDemo.java`:

```java
import java.util.List;

public class ParameterizedInterfaceBoundDemo {
    static <T extends Iterable<String>> int totalLength(T values) {
        int total = 0;
        for (String value : values) {
            total += value.length();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(totalLength(List.of("Java", "Core")));
    }
}
```

Run:

```bash
javac ParameterizedInterfaceBoundDemo.java
java ParameterizedInterfaceBoundDemo
```

`stdout`:

```text
8
```

`List<String>` implements `Iterable<String>` and satisfies the bound. `List<Integer>` does not satisfy `Iterable<String>`. This is a constraint on **how the generic interface is parameterized**, not just on the raw interface name.

Distinguish between:

- `T extends Iterable<String>`: named type parameter `T` must implement an interface with element type `String`.
- `Iterable<? extends CharSequence>`: wildcard allows a producer whose element type is a subtype of `CharSequence`.
- `Iterable<T>`: when `T` has already been declared elsewhere, this is a **type argument usage**, not declaring a new type variable.

## 17. Practical Rules for Choosing an Appropriate Bound

| Algorithm need | Appropriate bound/declaration | Reason |
| --- | --- | --- |
| Only accept numeric objects and call `doubleValue` | `<T extends Number>` or `Number` directly | Compiler knows `Number`'s methods |
| Accept a task and call `run` | `<T extends Runnable>` or `Runnable` | Requires the interface's behavior |
| Both `run` and `close` | `<T extends Runnable & AutoCloseable>` | Must have both capabilities simultaneously |
| Preserve the exact returned numeric type | `<T extends Number> T choose(T a,T b)` | Return type is tied to the same named `T` |
| Natural comparison across types | `<T extends Comparable<? super T>>` | Compares `T` with `T` via `Comparable` |
| Both `Number` and `Comparable` | `<T extends Number & Comparable<? super T>>` | Contract includes numeric conversion and ordering |
| Read a list of various numeric types | `List<? extends Number>` | Wildcard suffices when element type need not be named |
| Allow adding `Integer` to a target list | `List<? super Integer>` | Lower-bounded wildcard in a consumer position |
| Only compute the average of two `Number`s | `double average(Number a,Number b)` | Does not necessarily need to be generic |
| Return a mapped result of a different type from input | `<T,R> R convert(T input,Function<? super T,? extends R> f)` | `T` links input, `R` links result type |

Do not add bounds just because "every generic method looks more professional with `extends`". Every bound **narrows the set of usable type arguments**, so it should have a genuine reason tied to operations or type relationships.

### Too broad vs. too narrow bounds

- Too broad: using `<T>` while the body needs `doubleValue()` → compiler refuses the call.
- Just right: using `<T extends Number>` when `doubleValue()` is genuinely needed.
- Too narrow: using `<T extends Integer>` when only `Number` is needed → syntactically **valid**, yet `Integer` is final so this bound allows no subtypes beyond `Integer`; using `Integer` directly is usually clearer.
- Overly complex: using multiple bounds when the algorithm only uses methods from one bound → API is harder to reuse than necessary.

Even though a `final` class can still appear as a bound, it usually brings no type-reuse benefit; being a "final class" **does not automatically make `<T extends FinalClass>` syntactically invalid**.

## 18. Common Mistakes When Bounding Type Parameters

### 18.1. Using `implements` instead of `extends` on a type parameter

Wrong:

```java
// <T implements Runnable> // Invalid.
```

Right:

```java
<T extends Runnable>
```

`implements` is used when a class implements an interface; type parameters use `extends` regardless of whether the upper bound is a class or an interface.

### 18.2. Putting a class bound after an interface

Wrong:

```java
// <T extends Runnable & Number> // Wrong class/interface order.
```

Right if you genuinely need both bounds and have a matching type:

```java
<T extends Number & Runnable>
```

`Number` is a class bound so it comes first. The syntax example does not assert that standard JDK numeric wrappers implement `Runnable`; a custom `Number` subclass could implement `Runnable` to satisfy the requirement.

### 18.3. Repeating the `extends` keyword for each bound

Wrong:

```java
// <T extends Number extends Comparable<T>>
```

Right:

```java
<T extends Number & Comparable<T>>
```

Between bounds, use `&`; do not repeat `extends`.

### 18.4. Assuming `Number` supports `compareTo`

`Number` has no `compareTo`. If the algorithm calls that method, you need a `Comparable` bound or a suitable `Comparator`. Do not cast every `Number` to `Comparable` to bypass the compiler; not every `Number` subtype has a natural ordering.

### 18.5. Confusing a bound with a wildcard

`<T extends Number>` **declares `T`**. `List<? extends Number>` **uses a wildcard**. The two syntaxes appear in different positions and are not arbitrarily interchangeable. There is no valid `<T super Number>` form.

### 18.6. Failing to forward bounds when extending a generic class

If the parent requires `T extends Number`, then child `Child<U> extends Parent<U>` must ensure `U` satisfies the corresponding bound. Add `U extends Number` or use a suitable concrete type argument.

### 18.7. Assuming a bound makes every `T` instantiable

`new T()` is invalid based on a bound alone; you need a factory, supplier, or runtime type information. Bounds do not guarantee a no-arg constructor.

### 18.8. Thinking `T` cannot receive `null` because it has a bound

`T extends Number` is still a reference type; `null` satisfies static type checking. Calling a method on a `null` value throws `NullPointerException`. If non-null is required, check at runtime or use an explicit API policy.

### 18.9. Mixing incompatible `Number` types when comparing

`Integer` and `Double` both extend `Number`, but there is no common `Comparable<Number>` implemented by each wrapper. A `<T extends Number & Comparable<T>>` bound does not automatically make comparing two different wrappers valid. Choose an explicit comparison type or comparator.

### 18.10. Hiding errors with raw types/unchecked casts

Bounds help the compiler detect contract violations; raw types and unchecked casts can discard those guarantees. If you encounter warnings, trace the API and fix the generic declaration/type argument rather than silencing warnings unconditionally.

## 19. Exercises with Solutions

### Exercise 1 — Class bound

Given:

```java
static <T extends Number> double triple(T value) {
    return value.doubleValue() * 3;
}
```

Are `triple(4)` and `triple(1.5)` valid? What about `triple("4")`?

**Answer:** Both numeric calls are valid and return `12.0` and `4.5`. `String` does not extend `Number`, so the string call fails to compile. This is an excerpt method for study, without `main`.

### Exercise 2 — Interface bound

Given:

```java
static <T extends CharSequence> int length(T value) {
    return value.length();
}
```

Why are `String` and `StringBuilder` valid? Because both implement `CharSequence`. An `Integer` has no such interface relationship, so it is invalid.

### Exercise 3 — Class and interface simultaneously

```java
static <T extends Number & Comparable<T>> T smaller(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b;
}
```

Explanation: `Number` guarantees the numeric methods, `Comparable<T>` guarantees `compareTo`, and `T` preserves the return type. `smaller(3,7)` returns `3`; `smaller(2.0,1.5)` returns `1.5`.

### Exercise 4 — Two interfaces

Write a `Task` class implementing `Runnable` and `AutoCloseable`. Pass an object into `<T extends Runnable & AutoCloseable> void executeAndClose(T)`. If the class only implements `Runnable`, what happens? The compiler rejects it for missing `AutoCloseable`. If it has both, try-with-resources calls `close` after `run`.

### Exercise 5 — Bound on a class

Given `class Holder<T extends Number>`. Why is `Holder<Integer>` valid while `Holder<String>` is not? Because the type argument must satisfy the upper bound `Number`. Passing a string containing digits to the constructor cannot fix the type error via boxing or automatic parsing.

### Exercise 6 — Inheriting bounds

```java
class Parent<T extends Number> {}
class Good<U extends Number> extends Parent<U> {}
// class Bad<U> extends Parent<U> {}
```

Why is `Good` valid while `Bad` is not? `Good` guarantees every `U` is a `Number` subtype; `Bad` cannot provide that guarantee to the superclass.

### Exercise 7 — Named bound or wildcard?

A method only sums all elements in a list of numbers. Would you accept `List<Number>` or `List<? extends Number>`? You should use the upper-bounded wildcard if you want to accept `List<Integer>`, `List<Double>`, etc., to **read** as `Number`. There is no need to declare `<T extends Number>` yourself if the return type is not tied to a specific `T` and a wildcard suffices.

### Exercise 8 — Recursive bound

A class `Base` implements `Comparable<Base>`; class `Derived extends Base`. Why can `<T extends Comparable<? super T>>` match `Derived`? Because `Derived` can compare against `Base`, which is a supertype of `Derived`, via the inherited interface.

### Exercise 9 — Bound order

Classify:

```java
<T extends Number & Comparable<T>>     // Valid.
<T extends Runnable & AutoCloseable>   // Valid.
<T extends Runnable & Number>          // Invalid: class comes second.
<T extends Number & Runnable>          // Valid in terms of order.
```

A declaration that is valid in **bound syntax** does not mean existing types automatically satisfy it; you must examine concrete classes/interfaces as type arguments.

### Exercise 10 — Simplifying an overly generic API

You see:

```java
static <T extends Number> double plus(T a, T b) {
    return a.doubleValue() + b.doubleValue();
}
```

If the API only needs to add two `Number`s and return a `double`, is writing `static double plus(Number a, Number b)` acceptable? Yes. That concrete signature also accepts two `Number` arguments of different subtypes, and is clearer when there is no need to preserve a named `T` between input and output.

## 20. Checklist When Designing a Type Bound

Before adding `extends` to a type parameter, check:

1. **Which methods** does the method or class need to call on `T`? Do those methods belong to `Object`, a class, or an interface?
2. Is a single class bound enough, or are additional interface bounds genuinely needed?
3. If there are multiple bounds, does the **class come first**, followed by interfaces?
4. Does the bound require **all** contracts matching business needs, or is it accidentally excluding useful type arguments?
5. Does the type parameter appear in **multiple positions that need type linkage**? If not, using a concrete type or wildcard might be simpler.
6. If the method is inside a generic class, is it using the class's `T` or accidentally declaring a new `T` on the method?
7. If a subclass forwards a type parameter to a superclass, are the parent's bounds satisfied?
8. Does the caller intend to pass generic containers with different type arguments? Remember invariance, and consider wildcards for producer/consumer roles.
9. Are you confusing a compile-time bound with runtime validation, non-null guarantees, factories, or constructors?
10. When raw type/unchecked warnings appear, have you fixed the type relationship instead of making ungrounded casts?

## 21. Summary

**Bounds with classes or interfaces** are how the Java compiler knows which capabilities a generic type variable has. `<T extends Number>` grants access to operations guaranteed by `Number`; `<T extends Runnable>` requires the `Runnable` interface contract; `<T extends Number & Comparable<T>>` combines a class bound with an interface bound; `<T extends Runnable & AutoCloseable>` requires multiple interfaces simultaneously.

Bounds take effect at the **generic declaration**, are checked when type arguments are applied, and participate in inference. They do not allow `new T()`, do not forbid `null` automatically, do not make generic types covariant, and do not prove business algorithm correctness. Choose the **smallest bound that guarantees the operations actually needed**, keep a named type parameter when multiple positions must be linked, and use a wildcard or concrete type when that is simpler.