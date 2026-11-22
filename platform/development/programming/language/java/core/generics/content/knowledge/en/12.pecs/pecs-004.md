# When the Same Parameter Both Supplies and Receives Data: How Does PECS Apply?

## 1. The Problem and the Core Rule

The **PECS** (*Producer Extends, Consumer Super*) rule helps choose wildcards in Java Generics:

- A parameter that **supplies** elements to be read as type `T` (*producer*) usually suits `? extends T`.
- A parameter that **receives** elements of type `T` to be written (*consumer*) usually suits `? super T`.

However, if **the same parameter**, such as a single `List`, both supplies elements to be read and receives elements of the same type to be written, you should not mechanically pick one of the two wildcards. When you need to tightly bind the type of the element read to the type of the element to be written, prefer a **named type parameter**:

```java
static <T> void replaceFirst(List<T> values, T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

In this signature, `T` appears in both `List<T>` and `T replacement`, forcing the replacement value's type to be compatible with the list's element type. For transformations that take an element out and write it back, you can use `List<T>`, `UnaryOperator<T>`, or a generic helper `<T>` to preserve the same type.

**Rule to remember:** PECS is a guide based on **the read/write role of a parameter**, not a mandate that every `List` parameter must be declared with a wildcard.

## 2. Why Is `? extends T` Not Enough When You Want to Write T?

Consider a source that only needs reading:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}
```

`source` can be `List<Integer>`, `List<Double>`, or `List<Number>`. Every element can be read as `Number`.

But if the same variable must accept an arbitrary `Number`:

```java
static void wrong(List<? extends Number> values) {
    Number old = values.get(0); // Type-valid if index is valid
    values.set(0, old);         // COMPILATION ERROR
    values.add(5);              // COMPILATION ERROR
}
```

`? extends Number` represents **a concrete yet unknown element type**. A list might actually be `List<Integer>`; a `Number` value received from elsewhere might be `Double`. Thus `set` or `add` with an arbitrary `Number` cannot be guaranteed safe.

Even when the value `old` was just read from the list itself, writing `values.set(0, old)` is still rejected because once declared as `Number old`, only `Number` information is retained, no longer tightly linked to the unknown captured type of `values`.

`values.add(null)` and `values.set(0, null)` are exceptions that **can compile** because `null` is compatible with the unknown reference type. However, the actual list may forbid modification or reject `null`; this exception does not solve the requirement of writing a useful `T` value.

## 3. Why Is `? super T` Not Enough When You Need to Read Exact T?

A lower bound suits a destination receiving values:

```java
static void appendInteger(List<? super Integer> destination) {
    destination.add(10); // Type-valid
}
```

`destination` can be `List<Integer>`, `List<Number>`, or `List<Object>`. Every such list can accept an `Integer`.

Yet if the method needs to read an `Integer` from that same destination:

```java
static void wrongRead(List<? super Integer> values) {
    Integer value = values.get(0); // COMPILATION ERROR
    Object valueAsObject = values.get(0); // Valid if index is valid
}
```

The list could actually be `List<Object>` and hold non-`Integer` values. Therefore, an element read through `? super Integer` is only guaranteed to be `Object`.

Switching from `? extends T` to `? super T` solves the permission to **write T**, but loses the guarantee of **reading T**. Both wildcards are designed to describe **the direction of data usage**; they cannot replace an exact type relationship that must hold in both directions.

## 4. The Primary Solution: Use `List<T>` When the Same T Is Needed

When the value read and the value written must belong to **the exact same element type**, name that type in the signature:

```java
static <T> void replaceFirst(List<T> values, T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

Example:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
replaceFirst(names, "Chi"); // T is String

List<Integer> ages = new ArrayList<>(List.of(18, 20));
replaceFirst(ages, 21); // T is Integer
```

A generic method is a **type template**: each call infers a `T` compatible with the arguments. This flexibility differs from a fixed parameter `List<Object>`, which does not directly accept `List<String>` or `List<Integer>` because Java generics are invariant by default.

If you need to write a transformation where **the new value derives from the old value**, use `UnaryOperator<T>`:

```java
import java.util.List;
import java.util.function.UnaryOperator;

static <T> void updateFirst(
        List<T> values,
        UnaryOperator<T> operation) {
    if (!values.isEmpty()) {
        T oldValue = values.get(0);
        T newValue = operation.apply(oldValue);
        values.set(0, newValue);
    }
}
```

`UnaryOperator<T>` has the form `T -> T`, meaning it accepts and returns **the same T**. Thus the result's type is permitted to be written back into `List<T>`.

Example:

```java
List<String> words = new ArrayList<>(List.of("java", "generics"));
updateFirst(words, String::toUpperCase); // [JAVA, generics]

List<Integer> scores = new ArrayList<>(List.of(3, 4));
updateFirst(scores, n -> n * 10);       // [30, 4]
```

Note: a `List<T>` may be a list that does not support modification (for instance `List.of(...)`). The signature only guarantees **compile-time type safety**, not that `set` works at runtime. If the list does not support `set`, the method may throw `UnsupportedOperationException`.

## 5. When You Only Have `List<?>`: Use a Wildcard Capture Helper

Sometimes an external API only knows a list containing some arbitrary type:

```java
List<?> unknown = new ArrayList<>(List.of("A", "B"));
```

If you need to swap **existing elements**, you do not need to know the concrete type, as long as all moved values remain in **the same list** and preserve that type. A safe way to express this is to call a generic helper:

```java
static <T> void swapFirstTwo(List<T> values) {
    if (values.size() < 2) {
        return;
    }

    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}

static void reorderUnknown(List<?> values) {
    swapFirstTwo(values);
}
```

At the call `swapFirstTwo(values)`, Java can **capture the wildcard** into a type parameter `T` for the duration of a single call. Inside the helper, `get` and `set` use the exact same `T`, so no cast is needed and there is no risk of introducing a new element of a different type into the list.

Writing it directly as follows generally does not compile:

```java
static void badSwap(List<?> values) {
    Object first = values.get(0);
    values.set(0, first); // COMPILATION ERROR
}
```

`Object` is too broad for the unknown element type. Even `values.set(0, values.get(0))` can be rejected because separate wildcard uses are captured independently and not linked in the way `set` requires.

Standard utilities can also be used:

```java
import java.util.Collections;
import java.util.List;

static void reverseUnknown(List<?> values) {
    Collections.reverse(values);
}

static void swapUnknown(List<?> values) {
    if (values.size() >= 2) {
        Collections.swap(values, 0, 1);
    }
}
```

`Collections.reverse` and `Collections.swap` both accept wildcard-typed lists and perform operations safely on the existing elements. They still require the list to support the corresponding mutating operations; for example, a `List.of` list does not allow modification.

**Distinction to recognize:** the helper can **move, copy back, or transform under the same T**; it does not grant permission to arbitrarily insert a `Number` into a `List<Integer>`.

## 6. Two Easily Confused Cases: One List with Two Roles vs. Two Lists with Two Roles

The design must be based on whether **the same object** both reads and writes or there are **two distinct parameters**.

### Case A: The Same List Is Both Source and Destination

Examples: replacing the first element, swapping two elements, rotating order, normalizing strings, applying a `T -> T` transformation.

```java
static <T> void swapFirstTwo(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

**Recommendation:** `List<T>` with a named type parameter `T`. If the API only needs to reorder elements without handling them specifically, `List<?>` at the outer API paired with a helper/library utility can also be appropriate.

Reason: the method wants to guarantee that an element taken from the list itself can be placed back into the list with **the same type**.

### Case B: Two Separate Lists, One Reading Source and One Writing Destination

Example: copying `Integer` values from `List<Integer>` to `List<Number>` or `List<Object>`.

```java
static <T> void copyAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

**Recommendation:** apply PECS per parameter: `source` uses `? extends T`, `destination` uses `? super T`.

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyAll(integers, numbers); // Valid
copyAll(integers, objects); // Valid
```

If both sides were rigidly written as `List<T>`:

```java
static <T> void restrictiveCopy(List<T> src, List<T> dest) {
    dest.addAll(src);
}
```

then the call `restrictiveCopy(List<Integer>, List<Number>)` is **invalid**, because `List<Integer>` and `List<Number>` do not share the same type argument `T`. This is where PECS wildcards make the API more flexible while staying safe.

**Do not confuse** the `copyAll` method just written with `Collections.copy(destination, source)`: `copyAll` here appends elements to the end of the destination, whereas `Collections.copy` replaces values at already-existing positions and requires the destination list to have enough elements.

Also, if `source` and `destination` are **the same list**, do not `for-each` over it while calling `add` on it: many implementations (such as `ArrayList`) detect structural modification during iteration and throw `ConcurrentModificationException`. Handle the aliasing case if the API allows source and destination to be the same object, such as copying a snapshot before adding.

## 7. A Parameter That Both Reads and Adds New Values: Determining Type Obligations

Not every “read then write” case simply needs `List<T>` without further design thought. Identify **where the written value comes from**:

| Situation | Recommended parameter type | Why |
| --- | --- | --- |
| Only reads elements as `T` | `List<? extends T>` | Source may have a narrower element type than `T` |
| Only receives `T` values to write | `List<? super T>` | Destination may have a broader element type than `T` |
| Reads and writes back elements of **the same type** within one list | `List<T>` with helper `<T>` when needed | Keeps exact type link between `get` and `set` |
| Reads `T`, applies `T -> T`, then writes back | `List<T>`, `UnaryOperator<T>` | Transformation result is always valid `T` |
| Only rearranges existing elements, actual type does not matter | `List<?>` + `Collections.swap/reverse` or helper `<T>` | Uses wildcard capture, introduces no foreign type |
| Transfers elements between separate source and destination | `List<? extends T>` and `List<? super T>` | PECS fits each role |
| Replaces element with a concrete `Number` value | List must actually allow receiving `Number`, e.g. `List<Number>` or `List<? super Number>` | A `List<Integer>` cannot accept `Double` |

Distinguish **a type parameter `T`** (representing a type and linking multiple positions) from **a wildcard `?`** (an unknown element type at the usage site). A generic method can both declare `T` and use wildcards on parameters with separate roles.

### 7.1. Does Bounding `T extends Number` Solve the Both-Read-and-Write Case?

You can bound `T` if the algorithm genuinely needs `Number` functionality:

```java
static <T extends Number> T first(List<T> values) {
    return values.get(0);
}
```

If you want to **replace** an element with a `T` value, you still must use `T` itself:

```java
static <T extends Number> void replaceFirst(
        List<T> values,
        T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

Having `<T extends Number>` does **not** allow adding an arbitrary `Double` into `List<T>`, because `T` might be `Integer`. Nor does `List<? extends T>` allow adding an arbitrary `T`, because the list's element type could be narrower than `T`.

### 7.2. No Need for Wildcards Just to Accept Multiple List Types

A method declared as `<T> void process(List<T>)` can be called with both `List<String>` and `List<Integer>`, inferring `T` separately each time. Therefore, you do not have to use `List<?>` merely to accept multiple list types.

```java
static <T> void keepSameType(List<T> values) {
    if (!values.isEmpty()) {
        T current = values.get(0);
        values.set(0, current);
    }
}
```

This example uses `set` with the old value itself to demonstrate type consistency; in real code, perform a meaningful transformation or omit `set` if unneeded.

## 8. Complete Java 17+ Example

Save the file `PecsBothDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.UnaryOperator;

public class PecsBothDemo {
    // A List that both supplies T and receives T back.
    static <T> void replaceFirst(
            List<T> values,
            UnaryOperator<T> operation) {
        if (!values.isEmpty()) {
            values.set(0, operation.apply(values.get(0)));
        }
    }

    // Helper using the same T for both get and set operations.
    static <T> void swapFirstTwo(List<T> values) {
        if (values.size() >= 2) {
            T first = values.get(0);
            values.set(0, values.get(1));
            values.set(1, first);
        }
    }

    // Outer API does not need to know the concrete element type.
    static void reorderUnknown(List<?> values) {
        swapFirstTwo(values);
    }

    // Two parameters with separate roles: producer and consumer.
    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("cat", "dog", "bird"));
        replaceFirst(words, String::toUpperCase);
        System.out.println("Replace: " + words);

        List<?> unknownWords = words;
        reorderUnknown(unknownWords);
        System.out.println("Swap: " + words);

        List<Integer> scores = new ArrayList<>(List.of(2, 4));
        replaceFirst(scores, x -> x * 10);
        System.out.println("Numbers: " + scores);

        List<Number> numbers = new ArrayList<>();
        copyAll(scores, numbers);
        System.out.println("Copy to numbers: " + numbers);

        List<Object> objects = new ArrayList<>();
        copyAll(words, objects);
        System.out.println("Copy to objects: " + objects);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PecsBothDemo.java
java PecsBothDemo
```

Exact output:

```text
Replace: [CAT, dog, bird]
Swap: [dog, CAT, bird]
Numbers: [20, 4]
Copy to numbers: [20, 4]
Copy to objects: [dog, CAT, bird]
```

Explanation:

1. `replaceFirst` reads `String` and writes back `String` after converting to uppercase.
2. `reorderUnknown` accepts `List<?>` and relies on the generic helper to capture the actual type; swapping works without casting.
3. The same `replaceFirst` method accepts `List<Integer>` with an `Integer -> Integer` transformation, proving `T` is inferred per call.
4. `copyAll(scores, numbers)` uses `? extends T` for the `Integer` source and `? super T` for the `Number` destination.
5. `copyAll(words, objects)` is also safe because `List<Object>` can receive `String` elements.

All lists in the example are modifiable `ArrayList` instances where the algorithm needs to write, so the output does not depend on a write operation forbidden by `List.of`.

## 9. Common Mistakes

### 9.1. Trying to Use `? extends T` When Elements Need Updating

```java
static void incorrect(List<? extends Number> values) {
    Number value = values.get(0);
    values.set(0, value); // Does not compile
}
```

**Fix:** place the same `T` across the entire read/write relationship if you need to operate on the actual element type:

```java
static <T extends Number> void correct(List<T> values) {
    if (!values.isEmpty()) {
        T value = values.get(0);
        values.set(0, value);
    }
}
```

The `correct` example demonstrates type safety; reassigning the same value in practice produces no business change.

### 9.2. Trying to Read T from `? super T`

```java
static void incorrect(List<? super Integer> values) {
    Integer first = values.get(0); // Does not compile
}
```

**Fix:** use `List<Integer>` or `<T> List<T>` if you need the exact type when reading; or read as `Object` if the API only needs `Object`-level handling.

### 9.3. Unnecessarily Declaring Two Parameters with the Same `List<T>`

```java
static <T> void copy(List<T> source, List<T> target) {
    target.addAll(source);
}
```

This signature is stricter than actually required if source and target may differ in type argument in a safe direction (e.g., `Integer` to `Number`). Separate the roles with `? extends T` and `? super T` when appropriate.

### 9.4. Using Raw Types or Unchecked Casts to Insert New Values into `List<?>`

```java
// Dangerous code, should not be used:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List<?> values) {
    List raw = values;
    raw.add("not necessarily correct");
}
```

If `values` points to a `List<Integer>`, the statement above can insert a `String` into the list. The failure may only appear later when another place reads and casts the element to `Integer`. This is **heap pollution**, not how PECS is applied.

### 9.5. Assuming `List<T>` Means Modifiable

```java
List<String> immutable = List.of("A", "B");
swapFirstTwo(immutable); // Compiles, but may throw UnsupportedOperationException
```

The generics type system does not guarantee mutability of a `List`'s contents. If a method's contract requires modifying data, the API documentation must clearly state that the list must support `set`, `add`, or `remove` accordingly; a new `ArrayList` can be created if modifying the input is not permitted.

## 10. Self-Check

Assume `import java.util.*;` is present. Determine which cases **compile**, which operations may **fail at runtime**, and fix the signatures where needed.

**A — Same list both read and written**

```java
static <T> void swap(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

**B — Using `extends` wildcard with `Number`**

```java
static void change(List<? extends Number> list) {
    Number n = list.get(0);
    list.set(0, n);
}
```

**C — Using `super` wildcard with `Integer`**

```java
static void change(List<? super Integer> list) {
    Integer n = list.get(0);
    list.add(n);
}
```

**D — Copying two lists under PECS**

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
List<Integer> source = List.of(1, 2);
List<Number> target = new ArrayList<>();
copy(source, target);
```

**E — `List<?>` calling a helper with a type parameter**

```java
static <T> void swapFirstTwo(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
List<?> unknown = new ArrayList<>(List.of("A", "B"));
swapFirstTwo(unknown);
```

These examples are **standalone illustrative snippets**: `static` methods must be placed inside a class, and calls/variable declarations in valid locations; do not merge all identically named methods into one class assuming it forms a complete file.

**Answers:**

- **A:** Compiles. `List<T>` keeps the same type for `get` and `set`; runtime may reject `set` if the list does not support modification.
- **B:** Does not compile. `Number` is an upper bound and is not guaranteed compatible with the hidden element type of `List<? extends Number>`.
- **C:** Does not compile at assigning `get` to `Integer`: `List<? super Integer>` only guarantees reading as `Object`. Adding a known `Integer` by itself is valid if separated.
- **D:** Compiles and runs successfully with an `ArrayList` target, resulting in `[1, 2]`.
- **E:** Compiles and runs with `ArrayList`; the generic method captures the wildcard to ensure the same element type is read and written.

## 11. API Signature Selection Checklist

When facing a generic parameter that needs reading and/or writing, determine:

1. **What type of value is read out?** If only a supertype `T` interface is needed, `? extends T` may suffice.
2. **Where does the written value come from?** If passing a `T` from outside into the parameter, `? super T` is a candidate.
3. **Must the same list read and write the exact actual type?** Use `List<T>` with type parameter `<T>`, or a wildcard capture helper.
4. **Are there two separate source/destination lists?** Apply PECS to each parameter individually.
5. **Is the object modifiable?** Check the runtime contract of `List`; do not infer it from `T`, `extends`, or `super`.
6. **Can source and destination reference the same list?** Consider a snapshot or an algorithm that does not iterate and add concurrently to avoid structural modification issues.

### Key Takeaway to Remember

When **the same parameter both supplies and receives elements of the same type**, using **`List<T>` and a named type parameter `<T>`** is the most common way to keep the type relationship exact. If the outside only has `List<?>` or `List<? extends T>`, operations on existing elements can be delegated to a generic helper to safely **capture** the hidden type. If **two parameters have separate data directions**, PECS still applies: **`? extends T` on the source, `? super T` on the destination**.
