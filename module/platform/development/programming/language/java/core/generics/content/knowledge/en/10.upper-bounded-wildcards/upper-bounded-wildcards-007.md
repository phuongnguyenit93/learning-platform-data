# Applying `? extends T` for Data-Supplying Inputs in Java Generics

When a method parameter **supplies data for the method to read and process** (*producer/source*), the generally appropriate declaration is **`? extends T`**. It allows an API to accept a list or collection of `T` **and subtypes of `T`** while preserving compile-time type checking.

For example, a summing method only needs to retrieve elements as `Number`. It does not need to add `Number` values into the passed-in list. Therefore, the parameter `List<? extends Number>` fits better than `List<Number>`: `List<Integer>`, `List<Double>`, and `List<Number>` can all be used as data sources.

This rule is the first half of **PECS — Producer Extends, Consumer Super**. This lesson focuses on the **Producer Extends** half, meaning how to design and use **input parameters that supply elements**.

## 1. What Does "Data-Supplying Input" Mean?

A collection is a **producer** for a method when that method primarily **retrieves elements from the collection** to read, analyze, transform, aggregate, or write to another destination.

Common scenarios:

- Computing sums, averages, or extrema from a list of numbers.
- Reading a list of strings for display or logging.
- Iterating over a collection of objects inheriting a common superclass or implementing a common interface.
- Copying elements from a source list to a destination list.
- Producing a new result from the elements of an input.

**Producer and consumer are roles of a parameter in a specific operation**, not immutable traits of an object. The same `ArrayList<Integer>` can be a data source for a `sum` method, yet a data destination for an `addDefaults` method.

Example illustrating intent:

```java
static double sum(List<? extends Number> source) {
    double result = 0.0;
    for (Number n : source) {
        result += n.doubleValue();
    }
    return result;
}
```

The name `source` and the `for` loop show that the method only **takes values supplied by the list**. It does not need to know whether that list has type argument `Integer`, `Double`, or `BigDecimal`; every element is a `Number` on which `doubleValue()` can be called.

The value computed here uses floating-point `double`, which can incur precision error in certain calculations. For financial domains requiring decimal precision, design dedicated calculations using `BigDecimal`; wildcards do not govern arithmetic rules.

## 2. Why Is `List<Number>` Too Restrictive for Input Data?

An API that **only accepts and reads numeric data** has no need to force callers to convert `List<Integer>` into `List<Number>`:

```java
static double sum(Iterable<? extends Number> source) {
    double total = 0;
    for (Number value : source) total += value.doubleValue();
    return total;
}
```

`List<Integer>` is not a subtype of `List<Number>` because generics are invariant. However, `Iterable<? extends Number>` accepts `List<Integer>`, `List<Double>`, and `List<Number>`; callers do not have to use unchecked casts or create copies merely to satisfy an overly strict signature.

This lesson takes the parameter's **producer role** as the starting point: not just adding a wildcard, but also choosing the **smallest necessary** input interface. If you only iterate over elements, `Iterable<? extends Number>` can be better than `List<? extends Number>` because it does not require indexed access or list-modifying methods.

## 3. Mechanism: Safe Reading Thanks to the Upper Bound

With `Iterable<? extends CharSequence>`, a method can read each element as `CharSequence` and call `length()`, `charAt()`, or `toString()`:

```java
static int totalLength(Iterable<? extends CharSequence> source) {
    int total = 0;
    for (CharSequence item : source) total += item.length();
    return total;
}
```

Both `String` lists and `StringBuilder` lists fit because both classes implement `CharSequence`. A wildcard whose upper bound is an **interface** still uses the `extends` keyword. Capture and upper-bound mechanics were covered earlier in this chapter; here we apply them to **design a minimal input parameter that requires no casting and does not force callers into a single container type**.

## 4. Why Can Elements Usually Not Be Added to a Producer?

A producer `List<? extends Number>` might actually be a `List<Double>`, so `add(10)` is disallowed by the compiler. Forbidding insertion of new values allows the API to read data without breaking the caller's element-type contract.

| Operation on `List<? extends Number>` | Compile-time | Meaning |
| --- | --- | --- |
| `Number n = source.get(0)` | Allowed | Every element belongs to a subtype of `Number` |
| `source.add(10)` | Rejected | Unknown whether the hidden subtype accepts `Integer` |
| `source.add(null)` | Type-allowed | Runtime may forbid null/mutation |
| `source.clear()` | Type-allowed | Does not add a new element, yet can alter data |

In a **producer API**, what matters more than testing `add` calls is the **behavioral contract**: should the method modify the source or not? If it promises not to modify, keep the implementation read-only and test that behavior. `? extends` by itself does not make a list immutable or strictly read-only.

## 5. Designing a Method That Accepts Multiple Data Types

When a method needs to operate on the same behavior of a **superclass or interface**, use the upper bound at the right level.

### 5.1. Numeric Source

```java
static double average(List<? extends Number> source) {
    if (source.isEmpty()) {
        throw new IllegalArgumentException("source must not be empty");
    }

    double total = 0.0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total / source.size();
}
```

This method accepts `List<Integer>`, `List<Long>`, `List<Float>`, `List<Double>`, `List<BigDecimal>`, etc., because all of them provide `Number`. It has read access and uses `size()` and `isEmpty()`; it has no need to write to the source.

Note on the method contract: `source` must be non-empty; otherwise, the method actively throws `IllegalArgumentException`. If the caller passes `null`, for instance, `NullPointerException` will occur; `Objects.requireNonNull(source)` can be used in APIs needing clearer error reporting.

### 5.2. Common Interface Source

```java
static void display(Iterable<? extends CharSequence> source) {
    for (CharSequence text : source) {
        System.out.println(text.length());
    }
}
```

This example can accept `List<String>` and `List<StringBuilder>`. It only needs the common `length()` property of `CharSequence`. Declaring with `Iterable` instead of `List` also enables accepting data sources that do not necessarily support indexed access.

### 5.3. Base Class Source in an Object Model

```java
class Animal {
    String name() {
        return "animal";
    }
}
class Dog extends Animal {
    @Override
    String name() {
        return "dog";
    }
}

static void printNames(Iterable<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

These declarations are **illustrative snippets that need to be placed in an appropriate class/file context**, not a standalone program with `main`. `printNames` can be used with `List<Animal>` or `List<Dog>`. If the signature were `Iterable<Animal>`, `List<Dog>` could not be passed directly due to invariance.

Common point across all three examples: the method cares about **reading behavior through `T`**, rather than needing permission to insert new `T` objects into the source.

## 6. Choosing the Minimal Input Interface

Wildcards provide flexibility over **element types**; choosing the input interface also provides flexibility over **collection types**.

Options:

- `Iterable<? extends T>`: needs `for-each`, does not require `size()` or indexed access.
- `Collection<? extends T>`: needs iteration, `size()`, `isEmpty()`, or general `Collection` operations.
- `List<? extends T>`: needs ordering and positional access via `get(index)`.
- `Stream<? extends T>`: the API genuinely accepts a stream to execute a pipeline; stream sources have their own lifecycle and single-use consumption semantics, so do not automatically use them in place of `Collection`.

For example, a summing method only needs `Iterable`:

```java
static double sum(Iterable<? extends Number> source) {
    double total = 0.0;
    for (Number n : source) {
        total += n.doubleValue();
    }
    return total;
}
```

This both expresses that the source is **read** and permits more input implementations. If the method needs `source.size()`, `Iterable` does not provide that method; in that case use `Collection<? extends Number>` or `List<? extends Number>` as needed.

Do not pick `List<? extends T>` purely out of habit when the algorithm only needs a loop: a smaller interface makes the API contract clearer.

## 7. Copying From Producer to Consumer: Combining `extends` With `super`

When an operation has **two parameters**, one supplying data and one receiving data, the signature should express both roles:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Here:

1. `source` is the **producer**: supplies values of type `T` or subtypes of `T`, so it uses `? extends T`.
2. `destination` is the **consumer**: accepts `T` values, so it uses `? super T`.
3. The type variable `T` links the two roles; the compiler verifies the relationship at the call site.

Example:

```java
List<Integer> integers = List.of(2, 4, 6);
List<Number> numbers = new ArrayList<>();

appendAll(integers, numbers); // Valid.
System.out.println(numbers);  // [2, 4, 6]
```

If both parameters were written as `List<?>`, you could not safely do `destination.add(source.get(0))`, because each wildcard might represent a different type. If the source parameter were written as `List<T>`, the API would be less flexible than `? extends T` when needing to accept a subtype of the `T` determined by the destination.

This is one of the most useful PECS cases: **input supplying values → `extends`; output receiving values → `super`**.

A familiar standard-library example is `Collection.addAll(Collection<? extends E> c)`: the argument `c` is read to append elements to the target collection, so it uses `? extends E`.

Note: the `appendAll` method is written using a loop. If `source` and `destination` reference the same `ArrayList`, adding elements while iterating can lead to `ConcurrentModificationException` or unintended behavior. If aliasing source and destination is allowed, specify the requirement clearly and consider taking a snapshot first.

## 8. Runnable Java 17+ Program

The following standalone example demonstrates numeric sources, character-sequence sources, and safe copying to a destination. No libraries outside the JDK are needed.

Create the file **`ProducerExtendsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;

public class ProducerExtendsDemo {
    static double sum(Iterable<? extends Number> source) {
        double result = 0.0;
        for (Number n : source) {
            result += n.doubleValue();
        }
        return result;
    }

    static String joinText(Iterable<? extends CharSequence> source) {
        StringJoiner joined = new StringJoiner(" | ");
        for (CharSequence value : source) {
            joined.add(value.toString());
        }
        return joined.toString();
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static List<Number> twice(List<? extends Number> source) {
        List<Number> output = new ArrayList<>();
        for (Number value : source) {
            output.add(value.doubleValue() * 2);
        }
        return output;
    }

    public static void main(String[] args) {
        List<Integer> ints = List.of(2, 4, 6);
        List<Double> doubles = List.of(1.5, 2.5);

        System.out.println("sum integers = " + sum(ints));
        System.out.println("sum doubles = " + sum(doubles));

        List<Number> mixed = new ArrayList<>();
        appendAll(ints, mixed);
        appendAll(doubles, mixed);
        System.out.println("mixed = " + mixed);

        System.out.println("twice = " + twice(doubles));

        List<StringBuilder> words = List.of(
                new StringBuilder("A"),
                new StringBuilder("B"));
        System.out.println("text = " + joinText(words));
    }
}
```

Compile and run:

```bash
javac ProducerExtendsDemo.java
java ProducerExtendsDemo
```

**Exact stdout:**

```text
sum integers = 12.0
sum doubles = 4.0
mixed = [2, 4, 6, 1.5, 2.5]
twice = [3.0, 5.0]
text = A | B
```

How to read the output:

- `sum(ints)` and `sum(doubles)` can both be called because `Iterable<? extends Number>` accepts two different element sources; elements are read as `Number`.
- `appendAll` transfers values from two separate sources into a `List<Number>` capable of accepting both `Integer` and `Double`.
- `twice` only **reads** the source list and builds a **new list** holding auto-boxed `Double` values assigned into `List<Number>`. It does not modify `doubles`.
- `joinText` accepts `List<StringBuilder>` because `StringBuilder` implements `CharSequence`.

The code illustrates the difference between **broadly readable source types** and **explicitly defined result/destination types**. A wildcard on a source parameter does not force the return type to also be a wildcard.

## 9. Comparing `? extends T`, `T`, and `? super T` in Signatures

Suppose we have:

```java
static void readNumbers(List<? extends Number> source) { /* read */ }
static void updateNumbers(List<Number> list) { /* read and add Number */ }
static void putIntegers(List<? super Integer> destination) { /* add Integer */ }
```

The three signatures serve three different needs:

| Need | Suitable parameter type | Reason |
| --- | --- | --- |
| Read numbers from `List<Integer>`, `List<Double>`, `List<Number>` | `List<? extends Number>` | Every element can be read as `Number` |
| Read and add arbitrary `Number` values in a single list permitting any `Number` | `List<Number>` | Exact element type is known for both reading and writing |
| Add `Integer` into `List<Integer>`, `List<Number>`, or `List<Object>` | `List<? super Integer>` | Destination is guaranteed to accept `Integer` |
| Only need to iterate numbers, no concrete `List` needed | `Iterable<? extends Number>` | Minimal source contract |
| Need to read from a source and write to another destination with a type relationship | `<T>` with `? extends T` / `? super T` | Expresses and checks the relationship |

This table describes **what the type system accepts**, without guaranteeing that a concrete collection always supports modification at runtime.

One design tip: if a method takes a source solely to read, express that with `? extends T` directly in the signature; do not force callers to cast or manually copy `List<Integer>` into `List<Number>` unnecessarily.

## 10. Common Mistakes and Misconceptions

### 10.1. Using `List<Number>` for a Read-Only Parameter

```java
static void printAll(List<Number> numbers) {
    for (Number n : numbers) {
        System.out.println(n);
    }
}
```

If you want to accept both `List<Integer>` and `List<Double>`, change the parameter to `List<? extends Number>`. Do not perform unsafe casts to bypass the compiler.

### 10.2. Assuming `extends` Grants Permission to Add Any Subtype

This is a wrong assumption:

```java
static void addSample(List<? extends Number> source) {
    // source.add(Integer.valueOf(1)); // COMPILE ERROR.
    // source.add(Double.valueOf(2));  // COMPILE ERROR.
}
```

`? extends Number` means **one unknown subtype**, not a list arbitrarily mixing every subtype of `Number`. When you genuinely need to mix `Integer` and `Double`, create or accept `List<Number>`.

### 10.3. Confusing a Producer Parameter With an Immutable Object

`List<? extends Number>` can still reference a modifiable `ArrayList<Integer>`. `clear()` and `remove(...)` can compile. To promise that a method does not modify a collection, follow that design—using defensive copies/unmodifiable views when a stronger contract is needed. **Wildcards are not a data-immutability mechanism.**

### 10.4. Overusing Wildcards in Return Types

`static List<? extends Number> createNumbers()` may be valid, yet forces callers to deal with an unknown element type even when the API author knows the exact list created.

If returning a numeric list to which multiple subtypes may be added, `List<Number>` is usually clearer. If always creating a list of `Integer`, returning `List<Integer>` is clearer. Prefer wildcards in **parameters** when widening accepted inputs; choose return types according to the true output contract.

### 10.5. Using `List<?>` Even Though the Algorithm Needs `Number`

`List<?>` can accept `List<String>`, so `get()` is only safely usable as `Object`. If the algorithm calls `doubleValue()`, the `? extends Number` bound lets the compiler guarantee every element is compatible and avoids unnecessary checks or casts.

### 10.6. Confusing Wildcards With Generic Type Parameters

A simple read-only method can be written as:

```java
static void inspect(List<? extends Number> source) {
    for (Number number : source) {
        System.out.println(number);
    }
}
```

There is no need to write:

```java
static <T extends Number> void inspectTyped(List<T> source) {
    for (T number : source) {
        System.out.println(number);
    }
}
```

Both signatures work for multiple `Number` types. If `T` appears **only once** and no additional operations require a unified concrete type, a wildcard is usually cleaner. When expressing **a relationship across multiple parameters or between input and output**, a generic type parameter `<T>` is usually more valuable.

### 10.7. Assuming `extends` Automatically Converts or Copies the List

`List<? extends Number> source = integers` only creates a **reference** to the same list; it does not construct a new `List<Number>` and does not convert every element to `Number` via copying.

If you want a new list of type `List<Number>` to add diverse numbers, you can create:

```java
List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(4.5);
```

This constructor creates a structurally new list; existing elements are copied by reference (shallow copy).

### 10.8. Thinking `List<int>` Can Be Used as a Source

Java generics accept **reference types**, so `List<int>` is invalid. For primitive integers, use `List<Integer>` with boxing/unboxing, or choose `IntStream` in algorithms where primitive streams fit better.

## 11. Producer Identification Exercises

Examine the following three methods and determine which wildcard should be used:

**Scenario A — inspecting object names:** A method iterates over a list of objects implementing the `CharSequence` interface, calls `length()`, and prints the result; it adds nothing to the list. The appropriate answer is `Iterable<? extends CharSequence>`. This accepts `List<String>` and `List<StringBuilder>`.

**Scenario B — aggregating numbers:** A method sums numbers from `Collection<Integer>`, `Collection<Double>`, or `Collection<Number>` using `doubleValue()`. The appropriate answer is `Collection<? extends Number>` (or `Iterable<? extends Number>` if `Collection`-specific APIs are not needed).

**Scenario C — adding elements from source to destination:** Source `List<Integer>` and destination `List<Number>`, while wanting the algorithm to work for other compatible type pairs. The appropriate answer is `<T> void appendAll(List<? extends T> source, List<? super T> destination)`.

Quickly check the following declarations:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(1.5, 2.5);
List<? extends Number> source1 = ints;    // Valid.
List<? extends Number> source2 = doubles; // Valid.

Number a = source1.get(0);                // Valid.
// source1.add(3);                        // COMPILE ERROR.
// List<Number> nums = ints;              // COMPILE ERROR.
```

What to remember in all scenarios: **widening the set of accepted input types** with a wildcard only makes sense when actual operations remain type-safe; if a method needs to insert elements into the source itself, re-evaluate the parameter's role and signature.

## Key Takeaways

- A **Producer** is a parameter that **supplies elements** for an algorithm to read; it is commonly declared with `? extends T`.
- `? extends T` allows a method to read elements as `T` from collections whose element type is `T` or a subtype of `T`.
- **Generics are invariant**, so `List<Integer>` is not `List<Number>`; wildcards solve the need to accept broader sources.
- `List<? extends T>` **does not allow adding non-null values of a concrete type** to the source, because the true element type is unknown.
- `extends` **does not mean immutable**, does not automatically copy the list, and does not guarantee that the collection supports modification.
- When both source and destination are present, combine **`? extends T` for the source** and **`? super T` for the destination**.
- Choose `Iterable`, `Collection`, or `List` according to the exact operations the algorithm requires; prefer the smallest interface that sufficiently expresses the contract.

A method signature designed around its true role accepts a wider variety of inputs without unchecked casts, while preventing unsafe write operations right at compile time.