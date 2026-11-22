# Designing a Value-Holding Class `Box<T>` in Java Generics

A simple need when designing an API is **storing a value and retrieving that same value with the exact declared type**. We could write separate `StringBox`, `IntegerBox`, and `CustomerBox` classes for each type, but the classes would repeat the same structure. We could also use an `Object` field, yet callers would often have to cast manually and risk encountering a `ClassCastException`.

Java Generics allows defining **a single `Box<T>` class**: `T` is a *type parameter* representing the type of value that the box holds. When using `Box<String>`, `Box<Integer>`, or `Box<Customer>`, the compiler checks the data against the specified type. This lesson focuses on how to design the class, constructor, field, methods, and usage contract of `Box<T>`, along with practical decisions such as whether to allow `null` or allow replacing the value.

## 1. Defining the Contract of `Box<T>`

At a minimum, a `Box<T>` needs to answer the following questions:

1. **What does the box store?** A value of type `T`.
2. **How is the value put in?** Through a constructor or a factory method (`factory method`).
3. **How is the value retrieved?** A `T get()` method so callers receive the exact declared type.
4. **Can the value be changed after initialization?** The main example uses a `final` field and has no setter, meaning the reference to the value is fixed after the constructor.
5. **Does it accept `null`?** The main example **does not accept `null`**, in order to keep the contract easy to understand. This is a specific design decision, not a requirement of generics.

For a simple version, the API will look like:

```java
public final class Box<T> {
    private final T value;

    public Box(T value) { /* store value */ }

    public T get() { /* return value */ }
}
```

This is only a **signature sketch**. The next section is the complete Java code. `T` is not the name of a concrete class, nor is it a variable storing data. It is a type parameter declared at `<T>`; in each use such as `Box<String>`, the compiler interprets `T` according to the corresponding type argument.

## 2. Complete Implementation of `Box<T>`

Create the file **`Box.java`**:

```java
import java.util.Objects;

public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public T get() {
        return value;
    }

    public static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

### Explaining Each Component

**`public final class Box<T>`:** `<T>` declares the type parameter in the class scope; `final` prevents subclassing, helping keep the box design simple and fixed. A generic class does not have to be `final`; this is a choice made in the example.

**`private final T value`:** a field of type `T`, hidden from external code by `private`. `final` ensures this reference is assigned during initialization and cannot be reassigned afterward. `final` does **not** by itself make the object that the field points to immutable.

**`public Box(T value)`:** the constructor accepts the exact type `T` specified where the class is used. For example, with `Box<String>`, passing an `Integer` into the constructor will be incompatible with that contract.

**`Objects.requireNonNull(value, "value")`:** rejects `null` at initialization time, throwing `NullPointerException` with the message `value`. This decision avoids having a box that is valid according to the API yet holds no value. If the problem needs to represent "a value may be absent," a different contract should be designed and clearly documented, such as a class that allows `null` or using `Optional<T>` when appropriate.

**`public T get()`:** returns the value with type `T` at the Java source interface. With `Box<String>`, callers use `get()` as a `String` expression without needing an explicit cast.

**`public static <U> Box<U> of(U value)`:** this is a convenience factory method and **is itself a generic method**. A `static` method cannot directly use the class's type parameter `T`, so it declares its own `<U>`. Calling `Box.of("Java")` allows the compiler to infer `U` as `String` in an appropriate context.

The design has both a constructor and a factory to illustrate two valid ways of instantiating it. A real project can choose one as its primary API, depending on its needs.

## 3. Using `Box<T>` with Different Data Types

Create the file **`BoxDemo.java`** next to `Box.java`:

```java
import java.util.List;

public class BoxDemo {
    public static void main(String[] args) {
        Box<String> language = new Box<>("Java");
        Box<Integer> count = Box.of(7);
        Box<List<String>> topics = Box.of(List.of("core", "generics"));
        Box<Double> ratio = Box.of(3.14);

        System.out.println(language.get().toUpperCase());
        System.out.println(count.get() + 5);
        System.out.println(String.join(" | ", topics.get()));
        System.out.println("Box contains: " + ratio.get());
    }
}
```

Run with **Java 17 or later** in the directory containing the two files:

```bash
javac -encoding UTF-8 Box.java BoxDemo.java
java BoxDemo
```

Standard output (`stdout`):

```text
JAVA
12
core | generics
Box contains: 3.14
```

Interpreting the statements:

- `new Box<>("Java")` uses the **diamond operator** `<>`. The target type `Box<String>` helps the compiler infer the type argument of the instantiation expression.
- `Box.of(7)` infers `Integer` for the factory method, because `7` can be autoboxed from `int` to `Integer`.
- `Box<List<String>>` shows that `T` can be another **parameterized type**, not just simple classes.
- `Box<Double>` can accept `3.14` via autoboxing to `Double`.
- `get()` is called through variables with clear types; the compiler determines the methods of the result such as `String.toUpperCase()` or integer addition without requiring the caller to write a cast.

All four uses share **a single `Box<T>` definition**. We do not need to write four separate classes with the same responsibility.

## 4. Tracing a Single `T` Across the `Box` Contract

Within `Box<T>` itself, **a single type parameter** connects three places: the field `private final T value` stores the exact type, the constructor `Box(T value)` receives the exact type, and the getter `T get()` returns the exact type. For example:

```java
Box<String> title = new Box<>("Generics");
String text = title.get();
```

At the use site of `Box<String>`, both the constructor argument and the getter result must be compatible with `String`. If the class needs a setter, the signature should be `void set(T value)` rather than `set(Object)`; the fixed-value `Box` in this lesson intentionally does **not** provide a setter.

This is how to read **the contract of the box**, not the entirety of type variable scoping rules: when designing more complex classes, you also need to consider `T` across multiple method parameters, interfaces, subclasses, bounded type parameters, and static generic methods. Those cases do not change the main idea: keep the same `T` in places that must be type-related, instead of falling back to `Object`.

## 5. Comparing with a Box Using `Object`

A non-generic implementation is:

```java
final class ObjectBox {
    private final Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

This is a **standalone illustrative class**; it does not belong to the two files of the `BoxDemo` example. When used inside a method:

```java
ObjectBox raw = new ObjectBox("Java");
String text = (String) raw.get();
```

the caller must cast from `Object` back to `String`. If another place creates an `ObjectBox` containing an `Integer` while the reader still casts it to `String`, the cast statement can throw `ClassCastException` at runtime.

In the generic version:

```java
Box<String> typed = Box.of("Java");
String text = typed.get();

// Box<String> wrong = Box.of(42); // Does not compile: incompatible types
```

The wrong data type can be detected at compile time, close to where the value is created or passed. Generics is especially useful when many components share an API but require a clear type contract.

## 6. Important Design Choices

### 6.1. Fixed-Value Box or Mutable-Value Box?

The main version uses `private final T value` and only has `get()`. Users cannot call `set(...)` because the API does not expose a method to replace the value. This is suitable for a box holding a value established at creation time.

If the problem requirement is to **replace the value over time**, another class can use a non-`final` field and a setter that accepts the exact type `T`.

Complete example in the file **`MutableBox.java`**:

```java
import java.util.Objects;

public final class MutableBox<T> {
    private T value;

    public MutableBox(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public T get() {
        return value;
    }

    public void set(T newValue) {
        this.value = Objects.requireNonNull(newValue, "newValue");
    }
}
```

Usage example **inside a method**, after declaring the class above:

```java
MutableBox<String> status = new MutableBox<>("NEW");
status.set("DONE");
System.out.println(status.get()); // DONE
// status.set(10);                 // Compile error: 10 is not a String
```

Thus `set(T)` still preserves the type contract. However, a box whose value can be changed requires synchronization considerations if shared across threads; this version is **not designed to be thread-safe**.

### 6.2. `final` on a Field Does Not Guarantee Deep Immutability

Consider the case where `T` is a mutable `List<String>`. Create the file **`AliasingDemo.java`** and use it alongside `Box.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AliasingDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Box<List<String>> shared = Box.of(source);
        source.add("B");
        System.out.println(shared.get());

        Box<List<String>> snapshot = Box.of(List.copyOf(source));
        source.add("C");
        System.out.println(snapshot.get());
    }
}
```

Run:

```bash
javac -encoding UTF-8 Box.java AliasingDemo.java
java AliasingDemo
```

`stdout`:

```text
[A, B]
[A, B]
```

Explanation:

- `shared` holds the exact same `ArrayList` reference as the `source` variable. Even though the `value` field is `final`, calling `source.add("B")` still mutates the list object that both references point to.
- `snapshot` holds a copy of the list created with `List.copyOf(source)`. When `"C"` is added to `source` afterward, the list inside `snapshot` does not change. `List.copyOf` creates a list that cannot be modified via the list API; it also does not automatically deep-copy elements that are mutable objects.

**Design takeaway:** `Box<T>` keeps the reference fixed, but cannot by itself guarantee that every `T` is immutable. If you want to protect mutable data, clearly define copying rules, data ownership, or choose immutable value types at the usage boundary.

### 6.3. Should `null` Be Allowed?

The main example intentionally uses `Objects.requireNonNull`. Therefore:

```java
// Box<String> absent = new Box<>(null); // Compiles, but throws NullPointerException at runtime
```

The type argument `String` itself does not mean the variable cannot hold `null`; rejecting `null` comes from the **constructor logic**.

Another design could allow `null` by simply assigning `this.value = value;`, but then the API must clearly document the meaning of an absent value. You should not both allow `null` and implicitly assume `get()` always returns data on which methods can be called.

### 6.4. Should `equals()`, `hashCode()`, and `toString()` Be Implemented?

`Box<T>` above is a regular class inheriting default behavior from `Object`. Two boxes holding two equal values are **not automatically considered equal by content**:

```java
Box<String> first = Box.of("Java");
Box<String> second = Box.of("Java");
System.out.println(first.equals(second)); // false with the current Box
```

If the application needs to compare boxes by value, use them as map keys, or display their contents, you can additionally design `equals()`, `hashCode()`, and `toString()` following a consistent contract. This is a decision about the **semantics of the Box object**, separate from generics' type parameterization capability. You should not automatically assume a generic class has record-like comparison semantics.

## 7. Combining with a Generic Interface

A value-holding class can implement a **generic interface** that describes the capability of reading data. Architectural example:

```java
interface ValueSource<T> {
    T get();
}

final class ReadOnlyBox<T> implements ValueSource<T> {
    private final T value;

    ReadOnlyBox(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
```

These are **illustrative class/interface declarations**; they can be placed together in a single non-`public` file or split into appropriate files. `ReadOnlyBox<T> implements ValueSource<T>` means the type argument `T` is kept consistent across the interface contract. For example, `ValueSource<String> source = new ReadOnlyBox<>("Java");` allows code to depend on the `get()` capability without needing to know how the value is stored internally.

It is not necessary to create an interface for a single class if there is no need for abstraction. Choosing an interface is useful when there are multiple ways to provide a value sharing one contract, such as a box with a pre-existing value and a source that computes a value on demand.

## 8. Limitations to Understand When Designing `Box<T>`

### 8.1. Only Reference Types Can Be Used as Type Arguments

`Box<int>` is invalid because `int` is a primitive type. Use the wrapper class `Integer`:

```java
Box<Integer> number = Box.of(42);
int value = number.get(); // Auto-unboxing Integer -> int
```

Java also has wrapper classes such as `Long`, `Double`, and `Boolean`. If a problem processes integers or floating-point numbers at large scale, boxing and object allocation overhead can affect performance; `Box<Integer>` does not replace every primitive optimization case.

### 8.2. Two Different Parameterized Types Are Not Automatically Compatible

`String` is a subtype of `Object`, but **`Box<String>` is not a subtype of `Box<Object>`**. Java generics are **invariant** by default:

```java
Box<String> stringBox = Box.of("Java");
// Box<Object> objectBox = stringBox; // Invalid: incompatible types
```

If a function only needs to **read** the value from any kind of box, you can use the wildcard `Box<?>`:

```java
static void printValue(Box<?> box) {
    System.out.println(box.get());
}
```

The `printValue` snippet is an **illustrative method**, which needs to be placed inside a class. `Box<?>` represents a box with an unknown type argument. The usage type of `box.get()` can be treated as `Object`; you cannot assume it is `String` or `Integer`. Wildcards should appear when they genuinely express a flexibility need at an API boundary.

### 8.3. Type Parameters Are Largely Erased at Runtime

Java generics are primarily checked **at compile time** and executed with the `type erasure` mechanism. The program does not generate a runtime `Box<String>` class completely independent of `Box<Integer>`. You cannot write:

```java
// if (someObject instanceof Box<String>) { ... } // Invalid
```

because the JVM does not retain `Box<String>`'s `String` type information for that kind of check. You can check `instanceof Box<?>` to know the object is a `Box`, but that **does not prove** what type of data the box is currently holding.

### 8.4. Raw Types Can Break the Type Contract

Legacy code may omit the type argument and use `Box` instead of `Box<String>`. Raw types can lead to warnings and allow wrong-typed data to appear through operations that are not fully checked. Avoid:

```java
Box raw = Box.of(10); // Raw type; loses type parameter information at the use site
```

Replace with:

```java
Box<Integer> typed = Box.of(10);
```

Running `javac -Xlint:rawtypes,unchecked` helps detect many unsafe generic usages. Generics significantly reduces cast errors, but cannot guarantee safety if developers deliberately ignore warnings or use unchecked casts.

### 8.5. Do Not Use the Class's `T` Directly in `static` Members

The following snippet is **invalid code**:

```java
class WrongBox<T> {
    // static T shared;        // Invalid: static context cannot reference the class's T
    // static T value() { ... } // Invalid for the same reason
}
```

A generic `static` method must declare **its own** type parameter, for example `static <U> Box<U> of(U value)` in `Box.java`. That explains why the `of` factory uses `U` instead of directly using the class's `T`.

## 9. Common Mistakes and How to Fix Them

| Situation | Why Is It a Problem? | Better Design |
|---|---|---|
| `class Box { Object value; }` and repeatedly casting after `get()` | The contract does not specify the value type at the usage site. | `class Box<T> { T value; }` and `T get()`. |
| `Box<String> b = Box.of(123);` | `Integer` is incompatible with `String` in the target contract. | Pass `"123"` or use `Box<Integer>` depending on the actual data. |
| `Box<int> b` | Generics requires reference types. | `Box<Integer> b`. |
| `private Object value; public T get() { return (T) value; }` | The implementation creates an unchecked cast, easily hiding wrong-typed data. | Store the `T value` field directly; rely on the compiler's type checking. |
| `Box raw = new Box("x");` | Omitting the type argument weakens type checking and causes warnings. | `Box<String> box = new Box<>("x");`. |
| Using `final T value` and thinking an inner `List<T>` cannot change | `final` locks the reference, not the object's state. | Choose an immutable type or create an appropriate copy. |
| Constructor allows `null` while getter assumes it is always non-`null` | The contract for an absent value is unclear. | Clearly decide the `null` policy in the constructor and API. |
| Expecting two `Box` instances with the same content to automatically satisfy `equals` | Generics does not automatically generate content-based comparison. | Define value semantics if business logic requires it. |

In particular, there is no need to build a complex generic system just to store a single value. `Box<T>` is only a small example showing that **data types become part of the public contract**; in real applications, only add methods and abstractions when business behavior requires them.

## 10. Self-Check

1. In the declaration `class Box<T>`, what does `T` represent? Where is it used across `private final T value`, `Box(T value)`, and `T get()`?
2. Why is `Box<String> a = new Box<>("Java");` valid, while `Box<String> b = new Box<>(123);` is invalid?
3. In the `Box` version using `Objects.requireNonNull`, if `Box.of(null)` is called, when does the error occur and why?
4. Why can `Box<List<String>>` hold an `ArrayList` whose content changes even though the `value` field is `final`?
5. Why must the factory `static <U> Box<U> of(U value)` declare `<U>` independently of the class's `T`?
6. If a function only prints the value of a box without caring about the concrete type, what advantage does the signature `void printValue(Box<?> box)` have over accepting `Box<String>`?

**Suggested answers:** (1) `T` is the class's type parameter, used consistently for the stored data, the value accepted by the constructor, and the type returned by the getter. (2) The value `123` is incompatible with the required `String`. (3) It throws `NullPointerException` when executing the constructor, because of the class's policy of not accepting `null`. (4) `final` does not prevent modifying the contents of the referenced object. (5) A `static` method does not belong to a specific `Box<T>` instance, so it must have its own type parameter. (6) The wildcard indicates that the function can read any box without assuming the type of data inside.

When designing a good `Box<T>`, start from a simple contract: **store a value of the right type, return the right type, hide the data field, and decide the `null` policy and mutability of the value**. Generics protects type relationships at compile time; other guarantees such as deep immutability, content-based comparison, and thread safety need to be designed separately according to your needs.
