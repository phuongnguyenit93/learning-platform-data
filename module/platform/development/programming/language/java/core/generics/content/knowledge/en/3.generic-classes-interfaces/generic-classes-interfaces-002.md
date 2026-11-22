# Using `T` for Fields, Parameters, Return Values, and Constructors in Java

## 1. Why Does a Class Need a Type Parameter `T`?

In Java, a **generic class** accepts type parameters so that multiple objects can share the same behavior while maintaining different data contracts. For example, a value holder can store a `String` in one place and an `Integer` in another without creating two nearly identical classes.

```java
// Illustrative snippet; place inside an appropriate class or Java file.
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}

Box<String> title = new Box<>("Java");
String text = title.get();
title.set("Generics");
// title.set(123); // Compile error: Box<String> only accepts String.

Box<Integer> count = new Box<>(3);
int n = count.get(); // Unboxing from Integer.
```

`T` is the **type parameter name**, declared after the class name in `class Box<T>`. `T` is not a keyword or a concrete class; the compiler uses it to link the types of fields, constructors, method parameters, and return values. When using `Box<String>`, the positions carrying `T` are checked consistently against `String`. With `Box<Integer>`, they are checked against `Integer`.

A class can have multiple type parameters, such as `Pair<K, V>`; `T` is simply a common convention for a general type. Other conventions include `E` (element), `K` (key), `V` (value), and `R` (result). Use descriptive names if the relationships among multiple types become hard to follow.

**The four most important positions for `T` in a class:**

| Position | Example | Meaning |
| --- | --- | --- |
| Field | `private T value;` | The object stores a value of type `T`. |
| Method parameter | `void set(T value)` | Only accepts arguments compatible with `T`. |
| Return value | `T get()` | The caller receives a value of the exact type of the generic object. |
| Constructor parameter | `Box(T initialValue)` | The initial value must be compatible with type `T` of the new object. |

This is a consistency relationship: the same type parameter appearing in multiple positions ensures that incoming and outgoing data are checked under **a single contract**.

## 2. Scope of `T` in a Class Declaration

The foundational syntax is:

```java
class ClassName<T> {
    // Can use T in instance fields and methods.
}
```

`T` belongs to the class declaration's scope and can appear in:

- Instance field types: `T value`, `List<T> items`, `Optional<T> result`.
- Constructor and instance method parameters: `Box(T value)`, `void set(T value)`.
- Return types: `T get()`, `List<T> snapshot()`.
- Other parameterized types: `Comparable<T>`, `Function<T, String>`, or `Map<String, T>`.
- Type bound declarations or implementing/extending generic types, following specific rules in later sections.

The concrete type `T` is only known when source code uses the class, such as `Box<String>`. Inside the body of `Box<T>`, the compiler must ensure all operations are valid for **every allowed type `T`**, not just for `String`. Therefore:

```java
// Illustrative snippet inside class Box<T>:
// value.length();          // Invalid: unknown whether T has length().
// value.toString();        // Valid when value is non-null because every reference has toString().
// T another = value;       // Valid.
```

This restriction is very helpful: it prevents a generic class from accidentally depending on an API available only on one concrete data type.

### `T` Is a Reference Type

Generic type arguments must be **reference types**. You cannot write `Box<int>` or `List<boolean>`; write `Box<Integer>` or `List<Boolean>`. Java automatically performs boxing/unboxing in many contexts:

```java
Box<Integer> number = new Box<>(42); // int is boxed into Integer.
int result = number.get();           // Integer is unboxed into int.
```

Boxing does not turn `T` into a true primitive inside the class; consider performance and `null` when primitive-like data appears at high frequency.

## 3. Using `T` as a Field Type

The field `private T value;` requires the stored value to belong to the type of each `Box<T>` instance. Fields should be `private` and only expose valid operations through methods:

```java
final class Slot<T> {
    private T value;

    Slot(T initial) {
        this.value = initial;
    }

    T get() {
        return value;
    }

    void set(T replacement) {
        value = replacement;
    }
}
```

The field of a `Slot<String>` object carries a `String` constraint at compile time. Declaring `private` does not by itself create immutability; `set` can still replace the data. If a class only stores a fixed value, you can design the field as `private final T value` and omit the setter:

```java
final class ImmutableBox<T> {
    private final T value;

    ImmutableBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`final` guarantees that **the field reference is not reassigned after initialization**, not that the referenced object is always immutable. If `T` is an `ArrayList` or another mutable object, holders of the reference can still modify its contents. To obtain a safe snapshot for a collection, consider defensive copying.

A field holding a generic collection can also use `T` as the element type:

```java
// Illustrative snippet, import java.util.*.
final class Bag<T> {
    private final List<T> items = new ArrayList<>();

    void add(T item) {
        items.add(item);
    }

    List<T> snapshot() {
        return List.copyOf(items);
    }
}
```

Here `List<T>` means a list of `T` elements, unlike `List<?>` (unknown element type) and raw `List` (discarding generic information). `List.copyOf` creates an unmodifiable list and rejects `null` elements, so the `Bag` contract needs to handle/reject `null` consistently when adding.

## 4. Using `T` in Constructors

A constructor establishes valid state when creating an object. In a generic class, a constructor can accept a `T` parameter and assign it to a field of the same type:

```java
final class Message<T> {
    private final T payload;

    Message(T payload) { // T comes from Message<T>.
        this.payload = payload;
    }

    T payload() {
        return payload;
    }
}

Message<String> hello = new Message<>("Xin chào");
Message<Integer> status = new Message<>(200);
// Message<Integer> wrong = new Message<>("OK"); // Incompatible with Integer.
```

**Common syntax pitfall:** the constructor declaration is `Message(T payload)`, **not** `Message<T>(T payload)`. The class's type parameter is already declared on `class Message<T>`. The diamond `<>` only appears in **object creation expressions**, such as `new Message<>("Xin chào")`, so the compiler can infer the type argument.

You can write both sides explicitly:

```java
Message<String> a = new Message<String>("Xin chào");
Message<String> b = new Message<>("Xin chào"); // Diamond since Java 7.
```

Both variables carry the `Message<String>` contract. Avoid the raw form `new Message("Xin chào")` because it easily produces unchecked warnings and weakens type checking.

### Constructors Accepting Types Related to `T`

A class holding `List<T>` might want to accept a source collection of a subtype of `T`. When the constructor only **reads** the input, the wildcard `? extends T` is usually more flexible:

```java
// Illustrative snippet, import java.util.*.
final class Basket<T> {
    private final List<T> items;

    Basket(Collection<? extends T> source) {
        this.items = new ArrayList<>(source);
    }

    List<T> snapshot() {
        return List.copyOf(items);
    }
}

Basket<Number> numbers = new Basket<>(List.of(1, 2, 3));
// Each Integer element is accepted as a Number.
```

`Collection<? extends T>` can provide elements belonging to `T` or a subtype of `T`. The compiler allows copying them into `List<T>`. This follows the **producer extends** direction. When designing a constructor, clearly distinguish data ownership requirements: `this.items = new ArrayList<>(source)` creates a copy of the list, preventing modifications to the source collection from directly affecting the data inside the class.

Do not confuse a regular constructor using the class's `T` with a **generic constructor that has its own type parameter**:

```java
// Illustrative snippet; import java.util.function.Function.
final class ConvertedBox<T> {
    private final T value;

    <U> ConvertedBox(U source, Function<? super U, ? extends T> convert) {
        this.value = convert.apply(source);
    }

    T get() {
        return value;
    }
}

// Inside a method:
ConvertedBox<Integer> length = new ConvertedBox<>("Java", String::length);
int n = length.get(); // 4
```

`T` belongs to `ConvertedBox<T>`, while `U` belongs only to the constructor, inferred from the argument `"Java"`. This generic constructor is still a constructor of `ConvertedBox<Integer>` because `convert` produces an `Integer`. Do not redeclare `<T>` on a constructor just to use the class's `T`: using the same name can **shadow** the class's type parameter, causing misunderstanding of the contract.

## 5. Using `T` as a Method Parameter Type

Setters, updates, and collection-adding operations can accept `T` to forbid wrong-typed data at compile time:

```java
final class MutableBox<T> {
    private T value;

    MutableBox(T initial) {
        value = initial;
    }

    void set(T replacement) {
        value = replacement;
    }

    T swap(T replacement) {
        T old = value;
        value = replacement;
        return old;
    }
}

MutableBox<String> label = new MutableBox<>("A");
label.set("B");
String old = label.swap("C"); // old is "B".
// label.set(123);            // Error: Integer is not String.
```

In `swap(T replacement)`, `T` is both **the input type** and **the result type**; this is a relationship that replacing everything with `Object` would lose. The compiler knows `MutableBox<String>.swap(...)` returns `String` and only accepts data compatible with `String`.

A `T` parameter does not mean only **one exact runtime class** can be passed. If `T` is `Number`, valid subclasses can be passed:

```java
MutableBox<Number> box = new MutableBox<>(1);
box.set(2.5);                // Double is a Number.
Number stored = box.swap(3L); // Long is a Number.
```

However, `MutableBox<Integer>` is not automatically a `MutableBox<Number>`. Java generic classes are **invariant** by default. This rule prevents putting a `Double` into an object that promised to hold `Integer`.

### Do Not Treat `T` as Having Arbitrary Operations

If a method wants to add/subtract values, `T` does not automatically have arithmetic operators:

```java
// Invalid inside class Accumulator<T>:
// T add(T a, T b) { return a + b; }
```

You must model the operation properly via bounds, function arguments, or an addition strategy:

```java
import java.util.function.BinaryOperator;

final class Combiner<T> {
    private final BinaryOperator<T> combine;

    Combiner(BinaryOperator<T> combine) {
        this.combine = combine;
    }

    T join(T a, T b) {
        return combine.apply(a, b);
    }
}

// Combiner<Integer> adder = new Combiner<>(Integer::sum);
// int total = adder.join(2, 3); // 5
```

`BinaryOperator<T>` describes how to combine two values of type `T` into a result also of type `T`, without depending on a concrete operator.

## 6. Using `T` as a Return Type

Getters and computation methods can directly return `T`:

```java
T get() {
    return value;
}
```

If the reference variable is `Box<String>`, the expression `get()` is checked by the compiler as `String`; the caller does not need to cast manually from `Object`:

```java
Box<String> textBox = new Box<>("Generics");
String upper = textBox.get().toUpperCase();
// int impossible = textBox.get(); // Compile error.
```

A getter does not have to return just a single `T`; it can return a structure containing `T` to preserve element type information:

```java
// Illustrative snippet inside class Bag<T>.
List<T> snapshot() {
    return List.copyOf(items);
}
```

Because the return type is `List<T>`, users of `Bag<String>` receive `List<String>` and do not have to cast each element. This is a direct benefit of combining generics with the Java Collections Framework.

### Potentially Absent Values

If business logic allows data to be absent, consider an explicit contract:

```java
// Illustrative snippet when class has field T value, import java.util.Optional.
Optional<T> find() {
    return Optional.ofNullable(value);
}
```

`Optional.ofNullable` returns empty when `value == null`; `Optional.of(value)`, by contrast, throws `NullPointerException` on `null`. Do not use `Optional<T>` for every getter out of habit: choose it when **possible absence** is the genuine meaning of the API. For constructors and setters, `Objects.requireNonNull(value)` may be appropriate if the class does not allow null.

## 7. `T` on Interfaces and Implementing Classes

A generic interface expresses a contract for multiple data types. An interface does not have its own constructors, yet it can declare methods that accept/return `T`; implementing classes own the fields and constructors.

```java
interface Store<T> {
    void put(T value);
    T get();
}

final class MemoryStore<T> implements Store<T> {
    private T value;

    MemoryStore(T initialValue) {
        value = initialValue;
    }

    @Override
    public void put(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
```

Callers use the interface with a concrete type:

```java
Store<String> welcome = new MemoryStore<>("Xin chào");
welcome.put("Tạm biệt");
String message = welcome.get();
// welcome.put(123); // Compile error.
```

Interfaces allow different implementations to keep the same contract, such as storing in memory, reading from a file, or caching. When implementing, you can **forward the type parameter** like `class MemoryStore<T> implements Store<T>` or **fix the type** like `class StringStore implements Store<String>`. If the type is fixed, the implemented methods must accept/return `String`.

An interface should generally define behavior independent of the implementation; do not use `Object` for parameters and force callers to cast just because multiple data types participate.

## 8. `T` Across Superclasses, Subclasses, and Multiple Type Parameters

When extending a generic class, the subclass can continue keeping `T`:

```java
class BaseHolder<T> {
    private final T value;

    BaseHolder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NamedHolder<T> extends BaseHolder<T> {
    private final String name;

    NamedHolder(String name, T value) {
        super(value);
        this.name = name;
    }

    String name() {
        return name;
    }
}
```

`NamedHolder<Integer>` extends `BaseHolder<Integer>`. The `super(value)` call passes the exact type `T` to the superclass constructor. A subclass can also fix the type argument:

```java
class TextHolder extends BaseHolder<String> {
    TextHolder(String value) {
        super(value);
    }
}
```

When needing to describe two related kinds of data, use two separate type parameters instead of forcing everything into a single `T`:

```java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> result = new Pair<>("Tuổi", 20);
String label = result.left();
Integer age = result.right();
```

A generic `record` (Java 17+) creates reference-immutable components, a canonical constructor, and accessors typed as `L`/`R`. With a record, declaring components in parentheses after the record name defines the state; the compiler generates accessors `left()` and `right()` returning the exact declared types.

## 9. Bounds: When `T` Must Support a Specific API

With an unbounded `class DataBox<T>`, the compiler only knows `T` is a reference type. If the logic needs the ability to convert a number to `double`, use an **upper bound**:

```java
final class NumberBox<T extends Number> {
    private final T number;

    NumberBox(T number) {
        this.number = number;
    }

    T get() {
        return number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}

NumberBox<Integer> a = new NumberBox<>(7);
NumberBox<Double> b = new NumberBox<>(2.5);
// NumberBox<String> wrong = new NumberBox<>("7"); // Bound error.
```

Thanks to `T extends Number`, the compiler allows calling `doubleValue()` on the `number` field. The return type of `get()` is still the concrete `T`, so `NumberBox<Integer>.get()` returns `Integer` at compile time.

A bound can be an interface: `<T extends Comparable<T>>`, without using the `implements` keyword in the type parameter list. You can combine a class and interfaces like `<T extends Number & Comparable<T>>`, where the class bound (if present) must appear before the interface bounds.

Choose bounds based on **the behavior actually needed**. A bound that is too broad loses type-checking power; a bound that is too narrow prevents the API from accepting data types it could validly process.

## 10. Distinguishing the Class's `T`, Generic Methods, and `static` Members

A generic class does not force every method inside it to use `T`. A method can declare **its own type parameter**:

```java
final class Helper<T> {
    private final T value;

    Helper(T value) {
        this.value = value;
    }

    T get() { return value; } // T belongs to Helper<T>.

    static <U> U choose(U first, U second) {
        return first;
    }
}
```

`choose`'s `U` belongs to the method. This also explains why a `static` method can be generic:

```java
String word = Helper.choose("A", "B");
Integer number = Helper.choose(1, 2);
```

Conversely, the type `T` declared on `class Helper<T>` **cannot be referenced from a static context of the class**:

```java
class Wrong<T> {
    // static T shared;         // Compile error.
    // static T build() { ... } // Error: T belongs to the generic class.
}
```

Reason: `static` members belong to the shared class, and are not duplicated per `Helper<String>` and `Helper<Integer>`. To make a static method work with multiple types, declare its own type parameter, such as `static <U> U identity(U value)`.

**Note on name collisions:** It is possible to write `<T> T method(T arg)` inside `class Helper<T>`, but the method's new `T` will shadow the class's `T` and easily cause confusion. Use a different name (`U`, `R`) when they are two independent type parameters.

## 11. When Constructors and Methods Work with Collections Containing `T`

A very common mistake is assuming every structure carrying subtype elements can be assigned to a supertype structure:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> nums = integers; // Invalid: generics are invariant.
```

To only **read** data for a constructor or method, use `Collection<? extends T>`. To **write** `T` values into a destination passed from outside, use `Collection<? super T>` when appropriate:

```java
// Illustrative snippet inside a utility class, import java.util.*.
static <T> void copy(
        Collection<? extends T> source,
        Collection<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}

// Inside a method:
List<Integer> source = List.of(2, 4, 6);
List<Number> destination = new ArrayList<>();
copy(source, destination);
```

The **PECS (Producer Extends, Consumer Super)** principle explains both sides:

- `source` produces `T`, so `? extends T` allows safe reading.
- `destination` consumes `T`, so `? super T` allows adding `T` elements.

If your class needs to both read and update values consistently, using the exact parameter `T` in fields, setters, and getters remains the clearest choice. Wildcards should only be added where they genuinely broaden the argument range without breaking the contract.

One design detail: if `List<T> snapshot()` returned from the class is an unmodifiable copy, callers cannot directly alter internal state. However, if `T` is a mutable object, deep copying or immutable data types may still be needed to prevent modification through aliases of individual elements.

## 12. Limitations to Understand: Erasure, Object Creation, and Arrays

Java generics uses **type erasure** in its standard runtime representation. The compiler checks type constraints and may insert casts/bridge methods as needed. A `Box<T>` class does not generate a separate runtime class for each `T`.

Therefore, the following snippet is invalid inside a generic class without a value-creation tool:

```java
class CannotConstruct<T> {
    // T value = new T();           // Cannot instantiate T directly.
    // Class<T> type = T.class;      // No class literal T.class.
    // T[] values = new T[10];      // Cannot create an array of T directly.
    // boolean test = value instanceof T; // T is not reifiable.
}
```

If a constructor needs to create a `T` value itself, **pass a typed factory**, such as `Supplier<? extends T>`:

```java
import java.util.Objects;
import java.util.function.Supplier;

final class FactoryBox<T> {
    private final T value;

    FactoryBox(Supplier<? extends T> supplier) {
        value = Objects.requireNonNull(supplier.get());
    }

    T get() { return value; }
}

// FactoryBox<StringBuilder> box =
//     new FactoryBox<>(StringBuilder::new);
```

`Supplier<? extends T>` is responsible for creating a value of type `T` or a subtype of `T`. When runtime constructor reflection via `Class<T>`/reflection is needed, explicit type information must also be passed and exceptions handled; a constructor cannot be inferred solely from the erased type parameter name `T`.

Another limitation is that you cannot use type arguments to distinguish two overloads if after erasure they have identical signatures:

```java
// Cannot declare both simultaneously in the same class:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
// Both parameters erase to List, causing a name clash.
```

Do not abuse raw types or unchecked casts to work around this limitation: rename the methods or design a truly generic method.

## 13. Runnable Example: Fields, Constructors, Parameters, Results, and Interfaces

The following program gathers the `T` member forms into a standalone file. It simultaneously illustrates a mutable field, a class taking only an initial value, a generic interface, a factory, and a bound.

Create the file **`GenericMembersDemo.java`** with the entire contents:

```java
import java.util.*;
import java.util.function.Supplier;

public class GenericMembersDemo {
    interface Store<T> {
        void put(T value);
        T get();
    }

    static final class Slot<T> implements Store<T> {
        private T value;

        Slot(T initialValue) {
            this.value = Objects.requireNonNull(initialValue);
        }

        @Override
        public void put(T value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public T get() {
            return value;
        }

        T swap(T replacement) {
            T previous = value;
            put(replacement);
            return previous;
        }
    }

    static final class Basket<T> {
        private final List<T> items;

        Basket(Collection<? extends T> initial) {
            items = new ArrayList<>(initial);
        }

        void add(T value) {
            items.add(Objects.requireNonNull(value));
        }

        List<T> snapshot() {
            return List.copyOf(items);
        }
    }

    record Person(String name) {}

    static final class FactoryBox<T> {
        private final T value;

        FactoryBox(Supplier<? extends T> factory) {
            value = Objects.requireNonNull(factory.get());
        }

        T get() { return value; }
    }

    static final class NumberBox<T extends Number> {
        private final T number;

        NumberBox(T number) { this.number = number; }
        double asDouble() { return number.doubleValue(); }
    }

    static <U> U select(U first, U second, boolean chooseSecond) {
        return chooseSecond ? second : first;
    }

    public static void main(String[] args) {
        Slot<String> name = new Slot<>("Lan");
        System.out.println("initial: " + name.get());
        System.out.println("previous: " + name.swap("Mai"));
        System.out.println("current: " + name.get());

        Slot<Integer> count = new Slot<>(3);
        count.put(5);
        System.out.println("count: " + count.get());

        Basket<Number> numbers = new Basket<>(List.of(1, 2, 3));
        numbers.add(2.5);
        System.out.println("basket: " + numbers.snapshot());

        FactoryBox<Person> person = new FactoryBox<>(() -> new Person("An"));
        System.out.println("factory: " + person.get().name());

        NumberBox<Integer> numberBox = new NumberBox<>(7);
        System.out.println("asDouble: " + numberBox.asDouble());
        System.out.println("select: " + select("first", "second", true));
    }
}
```

Compile and run on **JDK 17+**:

```bash
javac -Xlint:all GenericMembersDemo.java
java GenericMembersDemo
```

Exact stdout output (run on JDK 21; no warnings when compiled with `-Xlint:all`):

```text
initial: Lan
previous: Lan
current: Mai
count: 5
basket: [1, 2, 3, 2.5]
factory: An
asDouble: 7.0
select: second
```

Explaining the type relationships:

1. `Slot<T>` declares `private T value`: the constructor `Slot(T)` accepts the initial value, `put(T)` updates it, `get(): T` reads it, and `swap(T): T` returns the old value. All share the **class's** type parameter.
2. `Store<T>` keeps the method contract independent of the storage mechanism; `Slot<String>` implements `Store<String>` without casts.
3. `Basket<T>` holds the field `List<T>`, the constructor takes a `Collection<? extends T>` source, and the getter `snapshot()` returns `List<T>` as an unmodifiable copy.
4. `FactoryBox<T>` obtains the value from `Supplier<? extends T>` instead of trying to call `new T()`; the constructor ensures the factory returns a non-null value.
5. `NumberBox<T extends Number>` constrains `T` to grant permission to call `doubleValue()`.
6. `select` is a **static generic method**, declaring its own `<U>`, independent of the type parameters of the nested classes above.

The example uses `Objects.requireNonNull` with `Slot` and `FactoryBox` to enforce non-null acceptance. For `Basket`, the constructor assumes the source collection has non-null elements because `snapshot()` uses `List.copyOf`; in production designs, unify the null policy as soon as the source is received, for example by checking each input element.

## 14. Common Mistakes and Self-Checks

| Mistake | Why It Is Wrong or Risky | Solution |
| --- | --- | --- |
| `class Box { Object value; }` then casting in the getter | Loses the type relationship between input and output, risking `ClassCastException` | Use `class Box<T>`, `T value`, and `T get()`. |
| `class Box<T> { Box<T>(T value) {} }` | Constructors do not write type arguments after the constructor name | Write `Box(T value)`. |
| `new Box("Java")` | Creates an object in raw form, which can produce warnings and weaken type checking | Use `new Box<>("Java")` with a target type or `new Box<String>("Java")`. |
| `Box<int>` | Generics accept reference types | Use `Box<Integer>`. |
| `static T cache;` inside `class Box<T>` | The class's `T` cannot be used in a static context | Use an instance field or a static method declaring its own `<U>`. |
| `T v = new T();` | Cannot instantiate `T` directly due to type erasure | Pass `Supplier<? extends T>` or another factory. |
| Getter returns `Object` even though the field is `T` | Users are forced to cast and lose type safety | Return `T` directly or a container `List<T>`/`Optional<T>`. |
| Setter accepts `Object` | Allows values that violate the object's contract | Use `void set(T value)`. |
| Returning a mutable `List<T>` field directly | Callers can mutate internal state bypassing the API | Consider a `List.copyOf` copy and manage mutable elements. |
| Using `List<Integer>` where `List<Number>` is required | Generics are invariant | Use a consistent type or a directional wildcard when only reading/writing. |
| `T extends Number` but trying to call an API only on `Integer` | The bound only guarantees members of `Number` | Change the API, perform deliberate runtime checks, or pick a suitable bound. |
| Using `<T>` on a method with the same name `T` as the class | The new type parameter shadows the class parameter | Choose a different name (`<U>`), and only declare a generic method when needed. |
| Getter can return `null` while callers assume data is always present | Easily throws `NullPointerException` | Enforce invariants from the constructor or represent absence with `Optional<T>` when appropriate. |

A quick way to review a generic class is to trace the flow: **value passed into constructor/setter -> field `T` -> getter or processing method -> return value `T`**. If at any step you are forced to cast from `Object`, check where the type parameter is being lost.

## 15. Practice Exercises and Self-Assessment Criteria

**Exercise 1 — Immutable class.** Write `final class ReadOnlyBox<T>` with a `private final T value` field, constructor `ReadOnlyBox(T value)`, and getter `T get()`. Create `ReadOnlyBox<String>` and `ReadOnlyBox<Integer>` objects. Try passing a `String` into `ReadOnlyBox<Integer>` to observe the compile error.

**Exercise 2 — Setter and previous value.** Extend `MutableBox<T>` with a method `T replace(T next)` that returns the old value before updating. Try calling it with `MutableBox<String>`; explain why the exact return type is `String` rather than `Object`.

**Exercise 3 — Generic interface.** Define `interface Cache<K, V>` with `void put(K key, V value)` and `Optional<V> find(K key)`. Write an implementation based on `Map<K,V>`. Verify that `Cache<String, Integer>` rejects calls with wrong-typed keys or values at compile time. Note that `Map<K,V>` uses two parameters because keys and values are two different kinds of data.

**Exercise 4 — Constructor with wildcard.** Write `class Numbers<T extends Number>` with a constructor taking `Collection<? extends T>`. Create `Numbers<Number>` from `List<Integer>`, then return the sum as a `double` by iterating over the elements and calling `doubleValue()`. Explain why `Collection<T>` in the constructor is less flexible when accepting subtype sources.

**Exercise 5 — Cannot `new T()`.** Write `class LazyValue<T>` that accepts `Supplier<? extends T>` in its constructor and creates the object on the first call to `T get()`. Decide for yourself how to cache the result and whether to accept null; you must clearly document the class's contract.

After completing the exercises, learners should be able to answer four questions with confidence: **Where is `T` declared? What type does the field hold? What types do the constructor and setter accept? What type does the getter guarantee to return?** When all four reference the same type parameter, Java can check the entire data pipeline at compile time, enabling general-purpose class and interface designs while preserving type safety.
