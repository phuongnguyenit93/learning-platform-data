# Trade-offs Between Type Safety and Generality in Java Generics and Pattern Matching

**Context:** Java Core Pattern Matching — *Generics and reifiable types*. The examples use Java 17+; the record pattern and pattern `switch` sections use the stable syntax of **Java 21**. The goal is to know when to keep strict types at compile time, when to accept general data (`Object`, `List<?>`, generic wildcards), and what must be checked at the runtime boundary so you do not lose type safety.

A system that receives data from multiple sources often faces a design tension: the more **general** an API is, the more kinds of input it can accept, but the harder it is to prove at compile time that a specific operation on the data is safe. Conversely, an API that requires a type that is too strict is easy to misuse with other valid data sources. Java addresses this with its static type system, generics, wildcards, pattern matching, and runtime checks — **each mechanism provides a different kind of guarantee**.

## 1. Two Goals to Distinguish

**Type safety:** the compiler can detect using a value as an incompatible type, or a runtime check is performed before the program relies on that type. For example, when a method accepts `List<String>` from controlled Java code without unchecked conversions, calling `get` has static type `String`; you do not need to cast each element manually.

**Generality (flexibility):** the same API, expression, or algorithm can work with more value types. For example, `List<?>` can reference `List<String>`, `List<Integer>`, and many other `List<T>` instances.

In return, when only `List<?>` is known, calling `list.get(0)` is treated as a value of type `Object` (in an example with no other type bounds). The compiler **does not allow assuming** it is a `String`.

```java
import java.util.List;

class Example {
    static void show(List<?> values) {
        Object first = values.get(0); // Valid if the list is non-empty
        // String text = values.get(0); // Compile error: cannot prove String
    }
}
```

Note: for an empty list, `get(0)` throws `IndexOutOfBoundsException`. Type safety does **not** mean every access is valid with respect to indices or null values.

**The right trade-off** is to keep concrete types when they are known, widen types where diverse inputs must be accepted, and restore guarantees with well-founded checks before specialized processing.

## 2. Foundation of the Limitation: Type Erasure and Reifiable Types

### 2.1. Type erasure — `List<String>` does not carry full `String` info at runtime

Java generics are primarily checked at **compile time**. According to JLS `4.6, *type erasure* removes most type arguments when translating to executable form:

- `List<String>` and `List<Integer>` have the same erasure, `List`.
- A type variable `T` is mapped to the erasure of its bound (typically `Object` if there is no explicit bound).
- Therefore, merely checking whether an object is a `List` at runtime **cannot confirm** that every element inside is a `String`.

```java
Object value = java.util.List.of("Java", "Generics");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
    // Still unknown whether all elements are actually Strings.
}
```

`instanceof List<?>` checks that the object is a list, not the element type. That is why a successful match against `List<?>` provides only **a partial guarantee**.

### 2.2. Reifiable types — types that can be fully identified at runtime

JLS `4.7 calls a type *reifiable* if its necessary type information is available at runtime. The cases directly relevant to this topic:

| Type | Reifiable? | Meaning for checks |
| --- | --- | --- |
| `String`, `Number`, `Runnable` | Yes | Can check class/interface type directly. |
| `List<?>` | Yes | Known to be a `List`, specific element type is unknown. |
| `List<String>`, `List<Integer>` | No | Specific type arguments are erased from normal runtime checks. |
| `List` (raw type) | Yes | Can be checked as a List, but drops source-code generic guarantees. |
| `String[]` | Yes | Arrays have runtime element type checks. |
| `List<String>[]` | No | Cannot create an array directly with `new List<String>[n]`. |

A reifiable type **does not mean** that every domain property inside the object has been verified. `List<?>` is reifiable, yet its elements may be of many different types.

### 2.3. Why did Java choose erasure?

Erasure supports compatibility with Java code and libraries that existed before generics. The cost is that the runtime does not carry full `T` information to automatically verify arbitrary parameterized type assignments. For this reason, Java does not have an `obj instanceof List<String>` operation that can reliably validate every element of a list when the input has the general type `Object`.

## 3. Generics Enable Generalization While Preserving Static Type Safety

### 3.1. `List<T>`: general over a concrete type chosen by the caller

```java
static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
```

When calling `String name = first(List.of("An", "Bình"));`, the compiler infers `T` as `String`. When calling it with `List<Integer>`, the compiler infers the corresponding type.

Benefit: one algorithm applies to many types **while the type relationship between parameter and result is preserved**. This is controlled generality, usually better than accepting and returning `Object`.

Limitation: `<T>` does not automatically create a token carrying runtime information about `T`. If a method receives data from JSON, reflection, a raw collection, or an `Object` of unknown origin, the compiler cannot guarantee that the input actually obeys the `T` contract based solely on the generic parameter name.

### 3.2. `List<?>`: accepts any `List<T>` while using elements safely

```java
static int sizeOfAnyList(java.util.List<?> values) {
    return values.size();
}
```

Both `sizeOfAnyList(List.of("A"))` and `sizeOfAnyList(List.of(1, 2))` are valid. If the algorithm only needs the length, `List<?>` is a good contract: it does not force callers to convert types or copy data.

Intentional downside: you cannot add a non-`null` value of an arbitrary type to `List<?>`, because the compiler does not know what element type the list permits. You can read elements as `Object`; further checks are needed if you want to call APIs specific to `String` or `Number`.

**Usage pattern:** reading metadata only, counting, iterating, printing via `Object.toString()`, or performing operations that do not require a specific element type.

### 3.3. Bounded wildcards: increasing reusability with necessary guarantees

```java
static double sum(java.util.List<? extends Number> values) {
    double result = 0.0;
    for (Number number : values) {
        result += number.doubleValue();
    }
    return result;
}
```

Both `sum(List.of(1, 2))` and `sum(List.of(2.5, 3.5))` compile. Using `? extends Number` allows **reading** every element as a `Number`.

```java
static void addOne(java.util.List<? super Integer> values) {
    values.add(1);
    Object first = values.get(0);
}
```

`? super Integer` allows **writing** `Integer` into an appropriate list; when reading generically, only `Object` is guaranteed. This is the *PECS* (*Producer Extends, Consumer Super*) principle, applied based on actual API behavior rather than mechanically.

**Generic invariance:** `List<Integer>` is not a subtype of `List<Number>`, even though `Integer` is a subtype of `Number`. If you want to accept lists of any `Number` for read-only access, use `List<? extends Number>`; do not cast `List<Integer>` to `List<Number>`.

## 4. How Far Does Pattern Matching Help with General Inputs?

### 4.1. From `Object` to `List<?>`: checking the "outer shape"

```java
static String describe(Object input) {
    if (input instanceof java.util.List<?> list) {
        return "List size=" + list.size();
    }
    return "not-list";
}
```

When the pattern matches, the compiler knows the variable `list` has type `List<?>`. You can call `size()`, `isEmpty()`, and iterate over elements of type `Object`. However, `input instanceof List<?> list` **does not prove** that the list contains only `String`s.

The example below **does not compile** with `Object` as the static type of the source:

```java
// DOES NOT COMPILE:
static void invalid(Object input) {
    // if (input instanceof java.util.List<String> strings) {
    //     System.out.println(strings.get(0).length());
    // }
}
```

The reason is not that "Java forbids all angle brackets `<...>` in patterns". The exact reason is that the type check requires a safe cast under the JLS applicability rules, whereas an arbitrary `Object` cannot be validated as `List<String>` through erasure alone.

### 4.2. Important exception since Java 16: a sufficiently narrow static type can allow parameterized types

Do not memorize the absolute claim that "`instanceof` always requires a reifiable type". Since Java 16, JLS `15.20.2 relaxed the restriction compared to earlier versions: an `instanceof` type check can use a **non-reifiable** parameterized type when a *checked cast* is possible given the known static type.

```java
import java.util.ArrayList;
import java.util.List;

class RefinementExample {
    static void check(List<Integer> numbers) {
        if (numbers instanceof ArrayList<Integer> array) {
            System.out.println(array.size());
        }
    }
}
```

This Java 17+ snippet **is valid**. The `Integer` information is already present in the **static type** of `numbers`; `instanceof` here distinguishes `ArrayList` from other `List` implementations, rather than re-verifying at runtime that every element is an `Integer`.

Do not infer that `Object input` can be checked with `input instanceof ArrayList<Integer>` in the same way. If the source has lost generic information, a container class check cannot recover evidence of the element type.

### 4.3. `switch` with type patterns: classifying runtime types, not checking erased element types

```java
static String category(Object input) {
    return switch (input) {
        case null -> "null";
        case java.util.List<?> list -> "list of size " + list.size();
        case String text -> "string " + text;
        default -> "other";
    };
}
```

This is a Java 21 `switch` expression, selecting a branch based on the runtime structure that Java can check. The `List<?>` branch can handle any list; it cannot distinguish `List<String>` from `List<Integer>` by pattern alone.

If you need to process by **element type**, perform validation **inside** the `List<?>` branch or design the data model into types with dedicated semantics instead of relying solely on generic parameters.

## 5. Practical Choice: Keep Input Types Broad, Then Check at the Boundary

Suppose an API receives `Object` from an external plug-in. The goal is to produce a `List<String>` for safe internal use. You cannot verify it with `input instanceof List<String>`; nor should you perform an unchecked cast and confidently call `String.length()`.

**The right approach:** check the container with `List<?>`, check **each element**, and build a new strongly typed list:

```java
static java.util.List<String> validateStrings(Object input) {
    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("Expected a list");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object element : source) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException("Expected strings only");
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

**What is actually guaranteed:**

- If the method returns normally, every element has passed the `String` check.
- When encountering a `null` element, `instanceof String` returns `false`, so the method rejects it. This is an intentional policy; if null is valid, a different rule and output representation must be defined.
- The result is a list **unmodifiable through the `List` API** thanks to `List.copyOf`. The input list can be mutated later without changing the structure of the returned list.
- Only one level of element type is checked; if elements are mutable objects, `List.copyOf` **does not perform a deep copy**.

Cost: it must traverse **O(n)** elements and may allocate **O(n)** additional memory. In return, the data boundary is verified once so the rest of the application can use a genuine `List<String>`.

This pattern is very useful when receiving input from parsed data, reflection, raw collections, Java interop, or uncontrolled APIs.

## 6. Avoid Raw Types and Unchecked Casts Without Evidence

### 6.1. Raw types: general on the surface, but lose the compile-time contract

```java
// Example illustrating legacy code; do not apply in new APIs:
java.util.List raw = new java.util.ArrayList();
raw.add("Java");
raw.add(42);
```

`List` (raw) allows legacy operations but drops generic parameter checking. It is still a reifiable type per JLS `4.7; this **does not make it type-safe**.

Compared to `List<?>`:

- `List<?>` acknowledges that the element type is unknown and prevents arbitrary additions.
- Raw `List` allows adding elements without a clear generic contract, easily producing warnings and *heap pollution*.

If you only need to observe general data, prefer **`List<?>`**. Only use raw types at genuinely necessary legacy boundaries and isolate the conversion site.

### 6.2. Unchecked cast: a warning with a specific meaning

```java
// TYPE-UNSAFE example; do not run as a validation solution:
Object input = java.util.List.of(1, 2, 3);
@SuppressWarnings("unchecked")
java.util.List<String> strings = (java.util.List<String>) input;

// The container cast may pass the runtime check...
String first = strings.get(0); // ClassCastException when reading Integer as String
```

Initially, the runtime only checks that the value is a `List`. The generic parameter `String` is not verified, so accessing it with static type `String` can trigger a compiler-inserted cast and cause a **delayed** `ClassCastException`.

`@SuppressWarnings("unchecked")` only silences the compiler diagnostic; it **does not** add runtime checks and does not make the cast safer. If an unchecked cast is unavoidable due to library design, place it in a small method with a clear contract, validate invariants on input or use a construction mechanism that guarantees the type, and document why it is safe right at that spot.

### 6.3. Checks that "look right" but are insufficient

```java
// Does not prove the entire list contains Strings:
if (input instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.get(0) instanceof String) {
    // Remaining elements could still be Integer, null, etc.
}
```

Checking only the first element does not verify the entire collection. If the requirement is "every element is a String", you must iterate through all elements or receive data from an API that already has a trustworthy contract for it.

## 7. Class Tokens: Increasing Generality of Runtime Validation

When the same validation logic needs to return multiple element types, you can introduce a **`Class<T>` token**:

```java
static <T> java.util.List<T> checkedList(
        Object input, Class<T> elementType) {
    java.util.Objects.requireNonNull(elementType);

    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("not-a-list");
    }

    java.util.List<T> result = new java.util.ArrayList<>();
    for (Object element : source) {
        if (!elementType.isInstance(element)) {
            throw new IllegalArgumentException("invalid-element");
        }
        result.add(elementType.cast(element));
    }
    return java.util.List.copyOf(result);
}
```

Example:

```java
java.util.List<String> names =
        checkedList(java.util.List.of("A", "B"), String.class);
java.util.List<Integer> counts =
        checkedList(java.util.List.of(1, 2), Integer.class);
```

`Class.isInstance` checks the runtime type of each element; `Class.cast` produces a value of the corresponding type `T`. In this example, `null` is rejected because `isInstance(null)` is `false`. The method is general while still preserving the `List<T>` result **because the caller provided runtime evidence for the element type itself**.

Token limitation: Java has `String.class` and `Integer.class`, but **does not have** `List<String>.class`. A `Class<List>` only identifies the container type at runtime and does not fully describe nested generic structures. If data has a structure like `Map<String, List<User>>`, you need recursive checks, an explicit schema, or a parser library with a suitable generic type representation; you cannot validate everything with a simple `Class<T>` alone.

## 8. Generic Record Patterns: More Expressive Structure, Still Does Not Eliminate Erasure

In Java 21, record patterns help check a record's type and deconstruct its components. With a generic record:

```java
record Box<T>(T value) {}
```

You can check the component by its runtime type:

```java
static String describeBox(Object input) {
    return switch (input) {
        case null -> "null";
        case Box(String value) -> "Box item: " + value;
        case Box(var value) -> "Box other: " + value;
        default -> "other";
    };
}
```

Note very carefully:

- `Box(String value)` checks that the object is a matching `Box` **and that the actual component can match `String value`**. It does not generally check that every `Box<T>` was declared with type argument `String`.
- `Box(var value)` is a record pattern that infers the component's type from context; when the selector has static type `Object`, you must not assume `value` is `String`. In this example, it can receive `Integer` or `null`.
- If the input is already declared as `Box<String>` from type-safe code, the compiler can leverage the static type information for finer inference; that is a guarantee from the **static source**, not a generic parameter suddenly becoming reified at runtime.
- Record patterns with type arguments and inference are subject to applicability/inference rules (`14.30, `18.5.5). Do not conclude that any pattern like `Box<String>(...)` is valid just because the record is generic. If the input is raw or `Object`, you must consider checked-cast feasibility and each component.

The trade-off here is gaining expressive structure to extract data while still respecting the limits erasure imposes on parameterized type checks.

## 9. Complete Java 21 Program: Checking Container, Elements, and Record

Create the file **`GenericSafetyDemo.java`** with the following content:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericSafetyDemo {
    record Box<T>(T value) {}

    static <T> List<T> checkedList(Object input, Class<T> elementType) {
        Objects.requireNonNull(elementType);
        if (!(input instanceof List<?> source)) {
            throw new IllegalArgumentException("not-a-list");
        }

        List<T> result = new ArrayList<>();
        for (Object element : source) {
            if (!elementType.isInstance(element)) {
                throw new IllegalArgumentException("invalid-element");
            }
            result.add(elementType.cast(element));
        }
        return List.copyOf(result);
    }

    static String inspect(Object input) {
        if (input instanceof List<?> list) {
            return "List size=" + list.size();
        }
        return "not-list";
    }

    static String boxValue(Object input) {
        return switch (input) {
            case null -> "null";
            case Box(String value) -> "Box item: " + value;
            case Box(var value) -> "Box other: " + value;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object one = List.of("A", "B");
        Object two = List.of("A", 3);
        Object three = List.of(1, 2);

        System.out.println(inspect(one));
        System.out.println(checkedList(one, String.class));

        try {
            System.out.println(checkedList(two, String.class));
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }

        System.out.println(checkedList(three, Integer.class));
        System.out.println(boxValue(new Box<>("Hi")));
        System.out.println(boxValue(new Box<>(10)));
        System.out.println(boxValue(new Box<>(null)));
        System.out.println(boxValue(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 GenericSafetyDemo.java
java GenericSafetyDemo
```

Output:

```text
List size=2
[A, B]
invalid-element
[1, 2]
Box item: Hi
Box other: 10
Box other: null
null
```

Explanation:

1. `inspect(one)` only proves that `one` is a `List<?>`, so it only prints the element count 2.
2. `checkedList(one, String.class)` checks each element as `String`, creates the resulting `List<String>`, and prints `[A, B]`.
3. `checkedList(two, String.class)` encounters element `3` which is an `Integer`, fails right at the validation point, and throws `IllegalArgumentException("invalid-element")`; no need to wait for a late cast error.
4. `checkedList(three, Integer.class)` accepts the entire list of integers and returns `[1, 2]`.
5. `Box<>("Hi")` matches the record pattern with a `String` component; `Box<>(10)` enters the general record branch; `Box<>(null)` is still a non-null record object, so the `var value` branch receives null.
6. Finally, a **null selector** is handled by `case null`. It differs from the non-null record with a null component on the preceding line.

This pattern achieves both goals: **inputs broad enough** to accept data from many sources, and **outputs with clear type guarantees** after passing the validation boundary.

## 10. Comparing Architectural Choices

| Option | Input flexibility | Type guarantee | Cost / risk | When to use |
| --- | --- | --- | --- | --- |
| `List<String>` | Only String lists per generic contract | Very strong at compile time if source is trusted and has no unchecked conversions | Does not accept `List<Integer>` | APIs where data is already well-known |
| `List<T>` | Reuses algorithm for many `T` | Preserves input/output type relationship at compile time | Runtime does not automatically know `T` | Generic algorithms |
| `List<?>` | Accepts any `List<T>` | Guarantees container is a List; elements read as Object | Cannot perform specialized operations on unchecked elements | Reading, iterating, checking size |
| `List<? extends Number>` | Accepts many forms of Number lists | Elements safely read as Number | Restricts write operations | Summing, statistics |
| `Object` + `instanceof List<?>` | Accepts any object | Must verify container type first | Runtime branching; elements still unknown | Boundaries of heterogeneous data |
| `Object` + per-element check + typed copy | Very broad input, strict output | Can prove elements match checked type | O(n) traversal, copying, rejects invalid data | Parsing, importing, plug-ins |
| Raw `List` / unchecked cast | Easily bypasses compiler barriers | No complete evidence for element types | Heap pollution, delayed errors, warnings | Controlled legacy compatibility |

**No single choice is always best.** Inside an application with a strict data model, starting with `List<T>` or dedicated domain types is usually easier to maintain. When receiving schema-less data, start with `Object`/`List<?>`, then validate and return a strict type. Protecting the boundary matters more than adding lots of casts.

## 11. Design Pitfalls and Java Mistakes to Avoid

1. **Believing `List<?>` guarantees all elements have the same type.** It only expresses that the element type is unknown; checking one element does not validate the entire list.
2. **Confusing reifiable with type-safe.** Raw `List` is reifiable, yet operating on raw types can cause heap pollution.
3. **Saying `instanceof` forbids all parameterized types.** Java 16+ allows certain checked-cast-compatible checks when the static type is narrow enough; read `15.20.2`.
4. **Saying pattern matching automatically recovers erased generic arguments.** A `List<?>` pattern does not recover `T`; record patterns describe components further but do not reconstruct all runtime generic arguments.
5. **Casting `List<Integer>` to `List<Object>` or `List<Number>`.** Generics are invariant; use bounded wildcards or appropriate copying/conversion.
6. **Hiding warnings with `@SuppressWarnings("unchecked")` without controlling the source.** This suppresses the warning, not adding any runtime check.
7. **Using `Class<T>` for complex nested types like `List<String>`.** `List<String>.class` does not exist; deeper structural validation requires a schema, validator, or an appropriate library type token.
8. **Not defining a null policy.** `isInstance(null)` returns false; `List.copyOf` also rejects null elements. State clearly whether null is rejected or represented.
9. **Assuming copying creates a deep copy.** `List.copyOf` prevents mutating the list through the returned API, but does not automatically clone mutable elements.
10. **Building a long `instanceof` classifier for a fixed set of subtypes.** If you control the model and it is finite, consider a `sealed interface` with matching type/record patterns, or polymorphism via methods on the types themselves. Keep runtime branches at system boundaries when the initial contract is truly general.

## 12. Exercises to Verify Understanding of the Trade-offs

**Exercise 1 — checking guarantee levels.** Given `Object x = List.of(1, "A");`, does `x instanceof List<?> list` match? Can `list` be treated as `List<String>` right away?

**Answer:** It matches because it is a list. You cannot safely treat the whole list as `List<String>`: the first element is `Integer`, and the runtime check did not verify any generic argument.

**Exercise 2 — choosing a signature.** Write a method that only sums any list of `Integer` or `Double`. Should it accept `List<Number>`, `List<?>`, or `List<? extends Number>`?

**Answer:** `List<? extends Number>` accurately expresses read-only access to `Number` elements and allows both list types, whereas `List<Number>` does not directly accept `List<Integer>` due to generic invariance.

**Exercise 3 — type erasure.** Why should `Object x = new ArrayList<String>(); if (x instanceof ArrayList<String> a) ...` not be used to validate element types? Under what circumstances can similar syntax be valid?

**Answer:** The static type `Object` does not carry the `String` type argument needed for a checked cast. If the input has static type `List<String>`, the refinement `instanceof ArrayList<String>` is valid since Java 16 in a compatible context; it checks the implementation class, not every element again.

**Exercise 4 — data boundary.** A plug-in returns `Object`, but an internal API must return `List<Long>` and reject `null`. Write `checkedList(input, Long.class)` following the pattern above; test the three inputs `List.of(1L, 2L)`, `List.of(1L, "2")`, and `List.of("2")`.

**Answer:** The first input succeeds. The other two inputs fail on the `String` element (`"2"` is not automatically converted to `Long`). If you want to parse strings into numbers, that is an **additional data conversion rule**, not a type check.

**Exercise 5 — record pattern.** Given `record Box<T>(T value) {}` and `Object x = new Box<>(5);`, is the `case Box(String s)` branch selected? What about `case Box(var item)`?

**Answer:** The `String` branch does not match the `Integer` component. The `var item` branch can match and `item` receives the value `5`; do not infer that the generic parameter `T` has been fully checked at runtime.

## Official References

- [JLS Java SE 21 `4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5): generic types, type arguments, and wildcards.
- [JLS Java SE 21 `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): erasure mapping and runtime information limits.
- [JLS Java SE 21 `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): exact definition of reifiable types.
- [JLS Java SE 21 `4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8): legacy code compatibility and risk of losing generic checks.
- [JLS Java SE 21 `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked/unchecked casts.
- [JLS Java SE 21 `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): type comparison and pattern matching, including the exception for non-reifiable parameterized types since Java 16.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, and applicability conditions.
- [JLS Java SE 21 `18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): type argument inference for record patterns.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): official examples of patterns on generic records.
