# `Enum<E extends Enum<E>>` and Its Relationship with Concrete Enum Types in Java

## Learning Objectives

After this lesson, you will be able to accurately read the type bound `E extends Enum<E>`, explain why `enum Status` corresponds to `Enum<Status>`, write generic methods usable across multiple enums while preserving compile-time type checking, and choose properly among `Enum<E>`, `Enum<?>`, `Class<E>`, `EnumSet<E>`, and `EnumMap<E, V>`.

## 1. The Recursive Bound in the `Enum` Declaration

The declaration of Java's base class takes the form:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // This is only a partial declaration illustrating the type signature,
    // not the full source code of java.lang.Enum.
}
```

Here:

- `E` is the **type parameter**.
- `E extends Enum<E>` constrains `E` to be a subtype of `Enum` parameterized by **E itself**.
- `Enum<E>` is the generic parent class providing common behavior for enums, including `name()`, `ordinal()`, `compareTo(E)`, and `getDeclaringClass()`.
- Having a type parameter reappear inside its own bound is called **F-bounded polymorphism** (*recursive type bound*, or *self-referential type bound*).

The word "recursive" here refers to a **compile-time relationship between types**. It does not mean a method calls itself, an object infinitely contains itself, or Java has to generate an endless inheritance chain.

You can read the expression `E extends Enum<E>` as: "This method accepts a concrete enum type E whose base class is `Enum<E>`."

## 2. From an `enum` Declaration to `Enum<ThatType>`

Consider two independent enums:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

enum State {
    NEW, RUNNING, DONE
}
```

In terms of type relationships, the compiler treats them as **inheritance-equivalent** to:

```java
// Conceptual diagram, NOT Java you are allowed to declare yourself:
final class Priority extends Enum<Priority> { /* ... */ }
final class State extends Enum<State> { /* ... */ }
```

This is an explanatory diagram, **not two classes you need or are allowed to write yourself**: Java forbids ordinary classes from directly extending `java.lang.Enum`. When you write `enum Priority`, the compiler automatically generates the enum class, the constants `LOW`, `MEDIUM`, `HIGH`, and the required initialization mechanism. An enum cannot `extends` another class and cannot inherit from another enum, though it can `implements` interfaces.

The key relationship is:

| Concrete type | Related parent type | Inherited `Comparable` type argument |
| --- | --- | --- |
| `Priority` | `Enum<Priority>` | `Comparable<Priority>` |
| `State` | `Enum<State>` | `Comparable<State>` |

Therefore, `Priority.LOW.compareTo(Priority.HIGH)` is valid. Comparing with `State.NEW` is invalid at compile time. Two enums may contain identical constant names, yet remain **two distinct types**.

`Enum` itself implements `Comparable<E>`, so the signature `compareTo(E other)` ties the comparison parameter to the exact enum type. Ordering is based on the declaration order of constants, not alphabetical order by name.

## 3. Writing Reusable Algorithms While Preserving Exact Types

A common pattern is writing a method:

```java
static <E extends Enum<E>> E someOperation(E value) {
    // ...
}
```

The `<E extends Enum<E>>` clause **declares** the method's type parameter; the `E` before the method name is the **return type**; `E value` is the method's parameter. For each call, the compiler infers `E` from the actual enum: `Priority`, `State`, or another enum.

The following example is a complete Java 17+ program.

**File `EnumBoundDemo.java`:**

```java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Objects;

public class EnumBoundDemo {
    enum Level {
        LOW, MEDIUM, HIGH
    }

    enum Stage {
        NEW, RUNNING, DONE
    }

    static <E extends Enum<E>> E next(E current) {
        Objects.requireNonNull(current, "current");

        Class<E> enumType = current.getDeclaringClass();
        E[] constants = enumType.getEnumConstants();
        int nextIndex = (current.ordinal() + 1) % constants.length;
        return constants[nextIndex];
    }

    static <E extends Enum<E>> boolean before(E left, E right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) < 0;
    }

    static <E extends Enum<E>> E byName(Class<E> enumType, String name) {
        return Enum.valueOf(enumType, name);
    }

    public static void main(String[] args) {
        System.out.println(next(Level.LOW));
        System.out.println(next(Stage.DONE));
        System.out.println(next(Level.HIGH));
        System.out.println(before(Level.LOW, Level.HIGH));

        EnumSet<Level> selected = EnumSet.of(Level.LOW, Level.HIGH);
        System.out.println(selected.contains(Level.HIGH));

        EnumMap<Level, String> captions = new EnumMap<>(Level.class);
        captions.put(Level.MEDIUM, "Trung bình");
        System.out.println(captions.get(Level.MEDIUM));

        System.out.println(byName(Level.class, "MEDIUM"));
        System.out.println(Level.LOW.getDeclaringClass().getSimpleName());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac EnumBoundDemo.java
java EnumBoundDemo
```

**Exact stdout:**

```text
MEDIUM
NEW
LOW
true
true
Trung bình
MEDIUM
Level
```

Part-by-part explanation:

1. `next` accepts a **concrete enum value**, obtains the declaring enum class via `getDeclaringClass()`, and then retrieves the constants list via `Class<E>.getEnumConstants()`. The modulo wraps back to the first constant when the value is at the end.
2. `before` calls `compareTo` with two values of the same type E. For example, `before(Level.LOW, Level.HIGH)` returns `true`.
3. `EnumSet<Level>` creates a set constrained to `Level`; `EnumMap<Level, String>` creates a map whose keys belong to `Level`.
4. `byName` passes a `Class<E>` and a constant name to `Enum.valueOf`, so the return type remains E. `byName(Level.class, "MEDIUM")` returns `Level.MEDIUM`.

**Examples that intentionally do not compile** if added to the program's `main`:

```java
// before(Level.LOW, Stage.NEW);           // No single matching E exists.
// EnumSet<Stage> wrong = EnumSet.of(Level.LOW); // Wrong element type.
// Level wrongValue = byName(Stage.class, "NEW"); // Return type is Stage.
```

These lines are only meant to illustrate compile errors; keep them commented out when running the program.

## 4. Why Write `E extends Enum<E>` Instead of Just `E extends Enum`?

`Enum` is a **generic** class. Writing `Enum` without passing a type argument uses a **raw type**, losing part of the compiler's type checking and potentially causing unchecked warnings.

Comparison:

```java
// Recommended signature: preserves the exact relationship between E and Enum<E>.
static <E extends Enum<E>> E requireTyped(E constant) {
    return constant;
}

// Signature illustrating raw type; avoid using in new APIs.
// static <E extends Enum> E requireRaw(E constant) {
//     return constant;
// }
```

The first signature explicitly affirms the `Enum<E>` relationship, allowing `compareTo(E)`, `Class<E>`, `EnumSet<E>`, and `EnumMap<E, V>` to be used in compliance with the library's type bounds. The raw-type signature cannot express this relationship and introduces unchecked-warning risks during deeper operations.

Also distinguish:

- `<E extends Enum<E>>`: **declares a named type variable E**, keeping a consistent relationship across multiple parameters, return values, and `Class<E>`.
- `Enum<?>`: refers to **any enum value**, suitable when you only need to read `name()`, `ordinal()`, or display it. The `?` does not guarantee that two independent references belong to the same enum type.
- `Enum` (raw): drops generic parameter information; avoid in new code.
- `Enum<Level>`: the base class type bound to a specific enum; generic methods generally use `E` rather than hardcoding `Level`.

For instance, the following snippet can print two names, but should not attempt to compare them with `compareTo`:

```java
Enum<?> first = Level.LOW;
Enum<?> second = Stage.NEW;
System.out.println(first.name());
System.out.println(second.name());
// first.compareTo(second); // Does not compile: two different wildcard captures.
```

This snippet is illustrated within the scope of the `EnumBoundDemo` class in the previous section, where `Level` and `Stage` were already declared.

## 5. Connection with `Class<E>`, `Enum.valueOf`, `EnumSet`, and `EnumMap`

Java APIs frequently reuse the same recursive bound:

| API | Representative signature or usage | Role of `E` |
| --- | --- | --- |
| `Enum.valueOf` | `<T extends Enum<T>> T valueOf(Class<T>, String)` | The passed-in class determines the exact return enum type. |
| `Class<E>.getEnumConstants()` | `E[] getEnumConstants()` | Retrieves constants as an array with the exact element type E. |
| `EnumSet` | `EnumSet<E extends Enum<E>>` | A set of constants belonging to the same enum. |
| `EnumMap` | `EnumMap<K extends Enum<K>, V>` | Keys belong to the same enum, while value type V is arbitrary. |
| `Enum.compareTo` | `int compareTo(E other)` | Only compares with constants of the same concrete enum type. |

In particular, `values()` is a `static` method generated by the compiler **on each concrete enum** (e.g., `Level.values()`). It is **not** an instance method or a shared static method on `Enum<E>`; therefore you cannot write `E.values()` inside a generic method.

When you need constants from a generic type, pass `Class<E>` or call `current.getDeclaringClass()`, then invoke `getEnumConstants()`. A useful API pattern, placed **inside a Java class**, is:

```java
static <E extends Enum<E>> EnumSet<E> allOf(Class<E> type) {
    return EnumSet.allOf(type);
}

static <E extends Enum<E>, V> EnumMap<E, V> newMap(Class<E> type) {
    return new EnumMap<>(type);
}
```

`EnumSet` and `EnumMap` are specialized for enum keys or elements, often saving memory and running more efficiently than general-purpose structures where appropriate. `EnumSet` does not accept `null` elements; `EnumMap` forbids `null` keys but allows `null` values.

Note when using `Enum.valueOf`: the name must **exactly match** the declared constant name, case-sensitively; a nonexistent name leads to `IllegalArgumentException`, and a `null` argument can lead to `NullPointerException`. If input comes from users, validate or handle exceptions at the input boundary.

## 6. When an Enum Has Constant-Specific Class Bodies

An enum can declare a custom body per constant (*constant-specific class body*) to override methods:

**File `EnumClassDemo.java`:**

```java
public class EnumClassDemo {
    enum Operation {
        ADD {
            @Override
            int apply(int a, int b) {
                return a + b;
            }
        },
        SUBTRACT {
            @Override
            int apply(int a, int b) {
                return a - b;
            }
        };

        abstract int apply(int a, int b);
    }

    public static void main(String[] args) {
        System.out.println(Operation.ADD.getClass() == Operation.class);
        System.out.println(Operation.ADD.getDeclaringClass() == Operation.class);
        System.out.println(Operation.ADD.compareTo(Operation.SUBTRACT) < 0);
        System.out.println(Operation.ADD.apply(2, 3));
    }
}
```

Run:

```bash
javac EnumClassDemo.java
java EnumClassDemo
```

Stdout:

```text
false
true
true
5
```

For `ADD`, `getClass()` returns the separate runtime class generated by the compiler for the constant body, so comparing against `Operation.class` yields `false`. Meanwhile, `getDeclaringClass()` still returns `Operation.class`: that is **the enum type declaring the constant**. Both `ADD` and `SUBTRACT` still have the `Enum<Operation>` type relationship and can be compared via `compareTo` with each other.

Therefore, in generic libraries working with enums, **prefer `getDeclaringClass()`** to obtain `Class<E>`. Do not assume that `constant.getClass() == SomeEnum.class` is always true.

## 7. What Does an F-Bound Help With and What Does It Not Guarantee?

Recursive bounds also appear outside enums:

```java
abstract class SelfTyped<T extends SelfTyped<T>> {
    abstract T copy();
}
```

The idea is to express operations that return or take a type tied to the implementing type itself. However, for user-defined generic classes, an F-bound **does not automatically prove that T is the current class**. In the type system, a class can pass a different type as long as that type satisfies the bound. For `enum`, Java adds a language rule: extending `Enum<E>` is fixed by the compiler per enum, creating a self-referential relationship accurate to that concrete enum class.

Likewise, an F-bound does **not** make a runtime-instantiable "type E" appear out of thin air. Java generics use **type erasure**; generic code cannot write `new E()`, `new E[10]`, or `E.values()`. For enums, you also cannot manually construct constants with `new Level()`. Obtain constants via `Level.values()`, `Class<E>.getEnumConstants()`, or lookup via `Enum.valueOf`.

## 8. Common Mistakes and Fixes

| Mistake | Why it is wrong or error-prone | Proper approach |
| --- | --- | --- |
| Using `<E extends Enum>` in new APIs | Raw type loses the `E`-to-`Enum<E>` relationship. | Use `<E extends Enum<E>>`. |
| Passing two different enum types into one `compareTo` call | `Comparable<E>` constrains the comparison type; another enum type does not match. | Compare only within the same E or define explicit conversion logic. |
| Calling `E.values()` | `values()` is generated per concrete enum, and does not exist on a type variable. | Use `Class<E>.getEnumConstants()`. |
| Using `getClass()` to identify the declaring enum | A constant with its own class body can have a runtime subclass. | Use `getDeclaringClass()`. |
| Using `ordinal()` as a database or protocol ID | Inserting or reordering declarations changes ordinals. | Use a dedicated stable identifier; also be cautious when renaming `name()`. |
| Casting between `Enum<?>` or using raw `Enum` to bypass errors | Bypasses type checking and can fail at runtime. | Keep `Class<E>`/type parameter E attached to the data from the start. |
| Comparing constant names to infer enum order | Enum ordering follows **declaration**, not alphabetical order. | Use `compareTo` when declaration order is genuinely wanted, or a custom domain comparator. |

A simple rule of thumb: when a function **only needs to print the name**, `Enum<?>` is usually enough. When a function needs to **return the exact enum type**, compare two constants, or build an enum set or map, use `<E extends Enum<E>>`.

## 9. Self-Check Exercises

1. Given `enum Color { RED, GREEN, BLUE }`, predict `next(Color.BLUE)` using the algorithm in section 3. **Answer:** `RED`, because the modulo operator wraps back to index 0.
2. Why is `before(Level.LOW, Stage.NEW)` rejected at compile time? **Answer:** `Level` and `Stage` are tied to `Enum<Level>` and `Enum<Stage>` respectively; no single E matches both arguments.
3. For an enum with constant-specific class bodies, should you use `getClass()` or `getDeclaringClass()` to obtain `Class<E>`? **Answer:** `getDeclaringClass()`.
4. Inside `static <E extends Enum<E>>`, why can't you call `E.values()`? **Answer:** E is a type parameter, whereas `values()` is a static method generated individually for each enum class.
5. When should you avoid using `ordinal()`? **Answer:** When you need a durable ID for persistence or data exchange across software versions.

**Key takeaway:** `Enum<E extends Enum<E>>` connects each concrete enum type to itself within the generic type system. Thanks to this relationship, a single algorithm can apply to many enums while preserving parameter types, return types, and comparison operations right at compile time.
