# Subtyping of Type Arguments Does Not Automatically Create Subtyping for Generics

In Java, an inheritance relationship between two **type arguments** does not automatically become an inheritance relationship between two **generic types** constructed from them. This is the **invariance** property of generics. Mastering this rule helps avoid type-assignment errors, design proper read/write APIs, and choose appropriate wildcards.

## 1. Distinguishing Element Type Relationships from Container Type Relationships

Because `Integer` is a subtype of `Number`, we can assign an `Integer` to a `Number` variable:

```java
Integer integer = 42;
Number number = integer; // Valid: Integer is a subtype of Number.
```

However, that relationship does **not** imply:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // COMPILE ERROR.
```

Written in subtyping notation:

- `Integer <: Number` is true.
- `List<Integer> <: List<Number>` is **false**.
- `ArrayList<Integer> <: List<Integer>` is **true**, because `ArrayList<E>` implements `List<E>` with the same type argument `Integer`.
- `List<Integer> <: List<? extends Number>` is **true**; the right-hand side is a wildcard type, not `List<Number>`.

The rule applies similarly to `Set<String>` and `Set<Object>`, `Map<String, Integer>` and `Map<String, Number>`, or `Box<Dog>` and `Box<Animal>`: each type parameterization must be considered separately, even if one or more arguments have an inheritance relationship. Java generics are neither covariant nor contravariant by default with respect to their type arguments.

**Note:** `List<Number>` can certainly hold `Integer`, `Double`, `Long`, etc. objects because each of those elements is a `Number`. This is different from assigning **an entire** `List<Integer>` to a `List<Number>` variable.

## 2. Why Does Java Forbid an Assignment That Seems Reasonable?

Suppose the compiler allowed `List<Integer>` to be treated as `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
// Suppose the following assignment were allowed (in reality, it is a COMPILE ERROR):
List<Number> numbers = integers;

numbers.add(3.14);           // Double is also a Number, so from numbers' perspective this is valid.
Integer value = integers.get(0); // Yet the Integer list now contains a Double!
```

Both variables point to the same list. If the assignment were allowed, the contract "every element of `List<Integer>` is an `Integer`" could be broken through the `List<Number>` variable. Java blocks the error right at **compile time**, instead of allowing the list's element type to be corrupted.

This is a fundamental reason, not merely a syntactic limitation. Invariance protects type safety when a data structure has both **read** and **write** capabilities.

## 3. Runnable Java 17 Example: Element Type vs. List Type

Save as `InvarianceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InvarianceDemo {
    static void printNumbers(List<? extends Number> values) {
        for (Number number : values) {
            System.out.println(number);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2));

        // List<Number> invalid = integers; // Does not compile.
        List<? extends Number> readable = integers; // Valid.
        System.out.println(readable.get(0));

        List<Number> numbers = new ArrayList<>();
        numbers.add(3);   // Integer is treated as Number.
        numbers.add(2.5); // Double is treated as Number.
        System.out.println(numbers);

        printNumbers(integers); // Accepts List<Integer> via wildcard.
    }
}
```

Run with Java 17 or later:

```bash
javac InvarianceDemo.java
java InvarianceDemo
```

Output:

```text
1
[3, 2.5]
1
2
```

In this example, `List<Number>` allows adding multiple subclasses of `Number` into the list it manages itself. The `readable` variable only carries the guarantee "a list with some concrete element type that is a subtype of `Number`"; the compiler does not know whether that concrete type is `Integer` or `Double`. Therefore, `readable.get(0)` reads as `Number`, while `readable.add(3)` will not compile.

## 4. Wildcards Express the Necessary Compatibility Relationships

Java uses **wildcards** to allow APIs to work with generics that have different type arguments without breaking the invariance of `List<T>`.

| Declaration | Accepted examples | Read out as | What elements can be added? |
| --- | --- | --- | --- |
| `List<Number>` | `List<Number>` | `Number` | `Number` and its subtypes |
| `List<? extends Number>` | `List<Integer>`, `List<Double>`, `List<Number>` | `Number` | Cannot add any specific `Number` value; only `null` is allowed by the type system |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>` | `Object` | `Integer` and subtypes of `Integer` (if any) |
| `List<?>` | `List<String>`, `List<Integer>`, etc. | `Object` | Only `null` is allowed by the type system |

The table describes permissions **according to the static type system**. The actual list may also not support modification; for example, a list created with `List.of(...)` will throw `UnsupportedOperationException` when a mutating operation is called even when the expression is type-valid.

### 4.1. `? extends Number`: Suitable for **Reading** Numeric Values

`List<? extends Number>` means "a list of some unknown type, where that type is `Number` or a subtype of `Number`." Therefore:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number n = source.get(0); // Valid.
Object o = source.get(0); // Valid.

// source.add(3);   // Does not compile.
// source.add(3.5); // Does not compile.
```

With `source.add(3)`, the compiler cannot guarantee that the actual element type of `source` is `Integer`; it could also be `List<Double>`. Reading as `Number` is safe in all cases. `extends` in a wildcard includes the upper bound type itself: `List<Number>` can also be assigned to `List<? extends Number>`.

### 4.2. `? super Integer`: Suitable for **Writing** `Integer`

`List<? super Integer>` means "a list of some unknown type, where that type is `Integer` or a supertype of `Integer`." We can add `Integer`, because every matching list accepts this value:

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);    // Valid.
destination.add(20);    // Valid.
Object item = destination.get(0); // Only guaranteed to read as Object.

// Number n = destination.get(0); // Does not compile.
// destination.add(2.5);         // Does not compile.
```

If the real type is `List<Object>`, reading can only guarantee `Object`. If the real type is `List<Integer>`, `Double` cannot be added. These are the two constraints that must be kept for the wildcard to remain safe.

### 4.3. `?`: Accepts Any Type Argument, with Limited Operations

`List<?>` is appropriate when you only need to iterate, count, check emptiness, or inspect elements as `Object`:

```java
static void printSize(List<?> items) {
    System.out.println(items.size());
}
```

`List<?>` is **not** equivalent to `List<Object>`. A `List<String>` can be passed to `List<?>`, but cannot be assigned to `List<Object>`. And `List<?>` does not allow adding arbitrary `Object` values.

## 5. Complete Example: PECS, Reading from Source and Writing to Destination

The practical rule **PECS** stands for *Producer Extends, Consumer Super*:

- **Producer:** a parameter that primarily supplies values to the method → `? extends T`.
- **Consumer:** a parameter that primarily receives values added by the method → `? super T`.

Example saved as `WildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardDemo {
    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number number : source) {
            total += number.doubleValue();
        }
        return total;
    }

    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        System.out.println(sum(integers));
        addDefaults(numbers);
        addDefaults(objects);

        System.out.println(numbers);
        System.out.println(objects);
        Object first = objects.get(0);
        System.out.println(first);
    }
}
```

```bash
javac WildcardDemo.java
java WildcardDemo
```

Output:

```text
6.0
[10, 20]
[10, 20]
10
```

`sum` can handle `List<Integer>`, `List<Double>`, or `List<Number>` because it only retrieves values and uses the `Number` API. `addDefaults` can write two integers into `List<Integer>`, `List<Number>`, or `List<Object>` because all of those target types accept `Integer`.

PECS is a guideline for choosing parameter types based on data flow direction, **not** a rule that every list must always be declared with a wildcard. When a method both reads and adds the same type `T`, a `List<T>` with a concrete type parameter may be more appropriate.

## 6. Generic Methods Connect Two Structures with Different Arguments

When both input and output must share a type relationship, use a **method type parameter** combined with wildcards. This directly expresses the requirement "read values of type `T` or a subtype and transfer them into a destination that accepts `T` or a supertype."

Save as `TransferDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class TransferDemo {
    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        copyAll(integers, numbers);
        System.out.println(numbers);

        List<String> words = List.of("Java", "Generics");
        List<Object> objects = new ArrayList<>();
        copyAll(words, objects);
        System.out.println(objects);
    }
}
```

```bash
javac TransferDemo.java
java TransferDemo
```

Output:

```text
[1, 2, 3]
[Java, Generics]
```

Both calls work without casting. The compiler infers a `T` that satisfies the upper/lower bound relationship at each call site. For `copyAll(integers, numbers)`, `Integer` fits as `T`: `List<Integer>` provides elements of type `Integer` and `List<Number>` accepts them.

**Limitation of the example:** source and destination should be suitable lists for copying; do not use this loop to claim that all concurrent reads and writes on the same list, or on lists modified concurrently from another thread, are safe. Those concerns are independent of generic invariance rules.

## 7. Generic Class/Interface Inheritance Remains Valid When Type Arguments Match

Do not confuse the invariance rule with Java forbidding inheritance between generic types. Inheritance relationships declared on classes/interfaces still apply:

```java
ArrayList<Integer> arrayList = new ArrayList<>();
List<Integer> list = arrayList; // Valid: ArrayList<Integer> implements List<Integer>.
```

Similarly, consider the declaration:

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

class IntegerBox extends Box<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
```

Then:

```java
Box<Integer> first = new IntegerBox(42); // Valid.
Box<? extends Number> second = new IntegerBox(42); // Valid.

// Box<Number> wrong = new IntegerBox(42); // Does not compile.
```

`IntegerBox` directly extends `Box<Integer>`, not `Box<Number>`. To compile this snippet on its own, put both classes in the same source file with any filename and a class with `main` if you want to run it; the snippets in this section are meant to illustrate type relationships, not a program with output.

For custom interfaces, the rule is the same: if `interface Repository<T>`, then `Repository<Dog>` does not automatically become a subtype of `Repository<Animal>` merely because `Dog extends Animal`.

## 8. Type Parameter Bounds Do Not Make Generic Types Covariant

Declaration:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T getValue() {
        return value;
    }
}
```

The bound `T extends Number` only restricts the **allowed type arguments** when creating `NumberBox<T>`, such as `Integer`, `Double`, or `Number`. It does not create a subtyping relationship between `NumberBox<Integer>` and `NumberBox<Number>`:

```java
NumberBox<Integer> intBox = new NumberBox<>(10);

// NumberBox<Number> wrong = intBox; // Does not compile.
NumberBox<? extends Number> readOnlyView = intBox; // Valid.
Number value = readOnlyView.getValue();             // Valid.
```

The two statements "`T` must belong to the `Number` family" and "parameterizations `NumberBox<T>` have an inheritance relationship with one another" are two separate issues.

## 9. Invariance Also Applies to Nested Generics

A common trap is assuming that having a wildcard at the **inner level** makes the **outer-level** list automatically compatible:

```java
List<List<Integer>> matrix = new ArrayList<>();

// List<List<? extends Number>> wrong = matrix; // Does not compile.
List<? extends List<? extends Number>> view = matrix; // Valid.
```

`List<Integer>` is compatible with `List<? extends Number>`, but that does not make `List<List<Integer>>` compatible with `List<List<? extends Number>>`. The outer `List<...>` level is still invariant. A wildcard at the outer level allows reading compatible sublists while disallowing arbitrarily adding new sublists.

When designing nested generic APIs, examine type relationships **at each level**. Only add wildcards at the levels where the API truly needs flexibility; avoid making signatures unnecessarily hard to read.

## 10. Contrast with Arrays: Arrays Are Covariant but Checked at Runtime

Java arrays allow `Integer[]` to be assigned to `Number[]`, unlike `List<Integer>` and `List<Number>`. That flexibility of arrays comes with a runtime type check.

Save as `ArrayContrast.java`:

```java
public class ArrayContrast {
    public static void main(String[] args) {
        Number[] values = new Integer[1]; // Valid for arrays.
        values[0] = 1;                     // Integer: valid at runtime.

        try {
            values[0] = 3.14; // Double cannot reside in an actual Integer[].
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
```

```bash
javac ArrayContrast.java
java ArrayContrast
```

Output:

```text
ArrayStoreException
```

Meanwhile, Java generics check most relationships between type arguments at compile time; type argument information is generally erased by **type erasure** in bytecode. Type erasure **does not mean** `List<Integer>` can be safely assigned to `List<Number>`. It is precisely the compile-time invariance rule that protects the element contract. Unchecked casts or raw types can break type safety and lead to `ClassCastException` at a later read site; that is not a valid workaround for a rejected assignment.

## 11. Common Mistakes and How to Fix Them

### Mistake 1: Requiring `List<Number>` When the Method Only Reads

```java
static double average(List<Number> values) { // Too strict if only reading is needed.
    return values.stream().mapToDouble(Number::doubleValue).average().orElse(0);
}
```

If you want to accept both `List<Integer>` and `List<Double>`, change the parameter to:

```java
static double average(List<? extends Number> values) {
    return values.stream().mapToDouble(Number::doubleValue).average().orElse(0);
}
```

Changing the signature does not turn the input list into a `List<Number>`; it simply describes the method's **read** requirement accurately.

### Mistake 2: Adding Elements Through `? extends Number`

```java
List<? extends Number> values = new ArrayList<Integer>();
// values.add(100); // Does not compile even though 100 is an Integer.
```

If the method needs to add `Integer` values to lists capable of accepting them, consider `List<? super Integer>`. If you want to own a list holding multiple kinds of `Number`, create a new `List<Number>`:

```java
List<Number> values = new ArrayList<>();
values.add(100);
values.add(3.14);
```

### Mistake 3: Thinking `List<?>` Is `List<Object>`

```java
List<String> strings = List.of("a", "b");
List<?> anything = strings; // Valid.

// List<Object> objects = strings; // Does not compile.
```

`List<Object>` can accept additional `Object` values; `List<?>` cannot. The two types make different promises about the data.

### Mistake 4: Casting via a Raw Type to Bypass the Compiler

```java
List<Integer> integers = new ArrayList<>();
// Avoid the following: raw types and unchecked conversions lose safety guarantees.
// List<Number> unsafe = (List) integers;
```

Do not use this in application code. Redesign the signature with `? extends`, `? super`, a generic method, or create a destination list with a genuinely appropriate type argument.

### Mistake 5: Considering Inheritance of Only One Argument in Multi-Parameter Generics

`Map<String, Integer>` does not become `Map<String, Number>` merely because `Integer extends Number`. If an API only reads values, consider a signature tailored to that specific need, such as `Map<String, ? extends Number>`. The same applies to nested generics as in Section 9.

### Mistake 6: Confusing Invariance with Collection Mutability

Wildcards describe read/write capabilities **according to the type system**. They do not guarantee that a collection is mutable, thread-safe, ordered, or free of `null`. For example, `List.of(1, 2)` is an unmodifiable list; attempting `add` will fail at runtime even though it is declared as `List<Integer>`.

## 12. How to Choose an API Signature

Ask yourself which direction the data flows:

1. **Want a list that can hold multiple kinds of `Number` and add them yourself:** use `List<Number>`.
2. **Want to accept any list whose elements belong to the `Number` family for reading:** use `List<? extends Number>`.
3. **Want to pass `Integer` values into a list that can receive them:** use `List<? super Integer>`.
4. **Only need to check size, iterate as `Object`, or check emptiness:** use `List<?>`.
5. **Want to link input and output in a type-safe way:** use a generic method `<T>` combining `? extends T` and `? super T` according to data direction.
6. **Want to both read and write the exact same element type decided by the caller:** consider `List<T>`; wildcards are not always needed.

Some self-check questions:

- Can `List<Integer>` be directly assigned to `List<Number>`? **No.**
- Can `List<Integer>` be passed to `List<? extends Number>`? **Yes.**
- Does a `List<? extends Number>` allow adding an `Integer`? **No**, because the concrete element type is unknown.
- Can `List<Number>` be passed to `List<? super Integer>`? **Yes.**
- Does a `List<? super Integer>` allow reading directly as `Integer`? **No**, only `Object` is guaranteed.
- Is `ArrayList<Integer>` a subtype of `List<Integer>`? **Yes**, due to interface implementation with the same type argument.

**Takeaway:** the relationship `S extends T` does not make `G<S>` a subtype of `G<T>`. When you want to accept multiple parameterizations of a generic, express the exact read/write requirement using wildcards or method type parameters.