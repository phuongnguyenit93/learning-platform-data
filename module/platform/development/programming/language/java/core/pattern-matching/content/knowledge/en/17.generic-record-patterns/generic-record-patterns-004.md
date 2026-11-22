# Wildcards in Generic Record Patterns (Java 21)

## 1. Objectives and Context

This lesson focuses on using **wildcards (`?`)** in **generic record patterns** to read data from records with unknown type parameters, combined with nested patterns while preserving type safety. After this lesson, you will be able to:

- Write and read `Box<?>(var value)`, `Box<?>(String text)`, `Pair<?, ?>(...)`, and nested record patterns.
- Distinguish **wildcards** from concrete types, `Object`, and **raw types**.
- Explain the limitations of runtime matching due to **type erasure**, including cases that fail to compile.
- Understand the static type of extracted variables, and the difference between `?` and bounds from the generic declaration.
- Recognize that wildcards do not create copies of data and do not guarantee immutability.

**Version:** Record classes have been a standard feature since Java 16; record patterns (JEP 440) and pattern matching for `switch` have been standard features since **Java 21**. The complete examples in this lesson use JDK 21 or newer, without needing `--enable-preview`.

## 2. What Does a Wildcard Mean in a Record Pattern?

Consider a generic record declaration:

```java
record Box<T>(T value) {}
```

An object can be created as `new Box<>("Java")`, `new Box<>(42)`, or `new Box<>(List.of(1, 2))`. When code only receives `Object input`, it does not yet know what type of data the record holds. The **unbounded wildcard** `?` expresses "a `Box` with some type parameter, whose concrete type is currently unknown":

```java
Object input = new Box<>("Java");

if (input instanceof Box<?>(var value)) {
    System.out.println(value); // Java
}
```

`Box<?>(var value)` consists of two parts:

1. **`Box<?>`** checks that the outer record shape is `Box` with an unspecified type parameter. The `?` is not a variable, has no value to assign, and does not infer `T = Object`.
2. **`(var value)`** is the component pattern. Java retrieves the `value()` component of `Box` and assigns it to the variable `value` when the match succeeds. For `Box<T>` with an unbounded `T`, the safe static type available from this variable is `Object`.

The `?` can appear multiple times when a record has multiple type parameters:

```java
record Pair<L, R>(L left, R right) {}

Object input = new Pair<>("total", 12);
if (input instanceof Pair<?, ?>(String label, Integer count)) {
    System.out.println(label + "=" + count); // total=12
}
```

Here, `Pair<?, ?>` does not check that `L` was declared as `String` or `R` was declared as `Integer`. Instead, the two **component patterns** `String label` and `Integer count` check the actual values via runtime type checks. If a value does not match, the entire pattern fails.

### Comparison with Similar Forms

| Form | Meaning |
| --- | --- |
| `Box<?>` | `Box` with an unknown type parameter; the outer type can be checked at runtime |
| `Box<Object>` | `Box` parameterized specifically with `Object` at the static type level |
| `Box<String>` | `Box` with type argument `String`; from `Object`, the `String` type argument cannot be directly verified at runtime |
| `Box` (raw type) | Bypasses compiler generic checks; should be avoided when not interacting with legacy APIs |
| `Box<?>(String text)` | Checks `Box`, then checks that the component value is actually a `String` |

Java generics are **invariant**: `Box<String>` is not a subtype of `Box<Object>`, but it can be referenced as `Box<?>`. Use `<?>` when you want to *inspect* data independently of the type parameter and without assuming a concrete type.

## 3. From Wildcards to Component Type Checking

Record patterns and type patterns can be combined directly in `instanceof` or `switch`:

```java
record Box<T>(T value) {}

static String describe(Object input) {
    return switch (input) {
        case Box<?>(String text) -> "String: " + text;
        case Box<?>(Integer number) -> "Integer: " + number;
        case Box<?>(var value) -> "Other: " + value;
        case null -> "null";
        default -> "not Box";
    };
}
```

The branches are evaluated in order:

- `Box<?>(String text)` matches only if the input is a `Box` and the component value is a non-`null` `String`.
- `Box<?>(Integer number)` works similarly for `Integer`.
- `Box<?>(var value)` matches any remaining component values, **including a `null` component**. The variable `value` does not have a more specific type for calling methods specific to `String` or `Integer`.
- `case null` handles the case where **the entire input** is `null`; this is different from `new Box<>(null)`.
- `default` handles values that are not `Box`.

For example, `new Box<Number>(42)` can still match `Box<?>(Integer number)`: the pattern checks that the **value** is an `Integer`, not that the original type argument `T` is `Integer`.

When adding a `Box<?>(List<?> items)` branch, Java checks that the component is a `List`, but does not verify its element type. You can only know for sure that `items` has type `List<?>`, not `List<String>`.

## 4. Nested Wildcard Record Patterns

You can nest record patterns when a component of the outer record is itself a generic record:

```java
record Box<T>(T value) {}
record Envelope<T>(Box<T> payload, String tag) {}

Object input = new Envelope<>(new Box<>("book"), "VN");

if (input instanceof Envelope<?>(Box<?>(String item), String tag)) {
    System.out.println(item + "@" + tag); // book@VN
}
```

The matching process proceeds from outside to inside:

1. Check that `input` is an `Envelope<?>` and retrieve `payload()` and `tag()`.
2. Check that `payload` is a `Box<?>`.
3. Check that `payload.value()` is actually a `String`, then bind `item`.
4. Check that `tag()` is a `String` and bind `tag`.

If any step fails, the overall pattern does not match; pattern variables do not enter scope for the success branch. Nested record patterns use **accessors** to retrieve components, rather than creating new records or casting generic arguments to unproven types.

With multiple parameters, `Pair<?, ?>(var left, var right)` is also valid; each `?` represents a potentially different unknown type. Do not implicitly assume that two `?` wildcards represent the same type.

## 5. Complete Java 21 Program

Save the code below as **`WildcardRecordPatternDemo.java`**. The program demonstrates wildcards in the outer record, nested patterns, multiple type parameters, bounds in record declarations, and the effect on mutable lists.

```java
import java.util.*;

public class WildcardRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(Box<T> payload, String tag) {}
    record NumberBox<T extends Number>(T value) {}
    record Batch<E>(List<E> items) {}

    static String describe(Object input) {
        return switch (input) {
            case Box<?>(String s) -> "String: " + s;
            case Box<?>(Integer n) -> "Integer: " + n;
            case Box<?>(List<?> items) -> "List size: " + items.size();
            case Box<?>(var value) -> "Other: " + value;
            case null -> "null";
            default -> "not Box";
        };
    }

    static String nested(Object input) {
        return switch (input) {
            case Envelope<?>(Box<?>(String name), String tag) ->
                    name + "@" + tag;
            case Envelope<?>(Box<?>(var value), var tag) ->
                    value + "@" + tag;
            default -> "unknown";
        };
    }

    static void inspectPair(Object input) {
        if (input instanceof Pair<?, ?>(String name, Integer count)) {
            System.out.println("Pair: " + name + "=" + count);
        }
    }

    static void readBounded(Object input) {
        if (input instanceof NumberBox<?>(var n)) {
            Number number = n;
            System.out.println("Number: " + number);
        }
    }

    static void changeList(Batch<?> batch) {
        if (batch instanceof Batch<?>(var items)) {
            System.out.println("Before clear: " + items);
            items.clear();
            System.out.println("After clear: " + items);
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box<>("Java")));
        System.out.println(describe(new Box<>(12)));
        System.out.println(describe(new Box<>(List.of("A", "B"))));
        System.out.println(describe(new Box<>(3.5)));
        System.out.println(describe(new Box<>(null)));
        System.out.println(describe(null));
        System.out.println(describe("plain text"));

        System.out.println(nested(new Envelope<>(new Box<>("book"), "VN")));
        System.out.println(nested(new Envelope<>(new Box<>(2026), "ID")));

        inspectPair(new Pair<>("score", 8));
        inspectPair(new Pair<>("score", "eight"));
        readBounded(new NumberBox<>(5.5));

        List<String> mutable = new ArrayList<>(List.of("A", "B"));
        changeList(new Batch<>(mutable));
        System.out.println("Original: " + mutable);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 21 WildcardRecordPatternDemo.java
java WildcardRecordPatternDemo
```

**Exact output:**

```text
String: Java
Integer: 12
List size: 2
Other: 3.5
Other: null
null
not Box
book@VN
2026@ID
Pair: score=8
Number: 5.5
Before clear: [A, B]
After clear: []
Original: []
```

Result analysis:

- `Box<String>` and `Box<Integer>` are recognized by the **runtime component type**, not by checking the generic argument `T`.
- `Box<List<String>>` enters the `List<?>` branch because the component has runtime type `List`. The branch does not prove that the elements are `String`.
- `Box<Double>` enters `Box<?>(var value)`. With `new Box<>(null)`, `var value` can still receive `null`, which differs from a `null` input object.
- The `Envelope<?>` pattern handles multiple levels; the branch for `String` comes before the general `var` branch.
- `Pair<?, ?>(String name, Integer count)` prints a line for the pair with values `"score"`, `8`. The pair `("score", "eight")` does not match and prints nothing.
- `NumberBox<?>` has a type parameter `T extends Number` directly in the record declaration. Therefore, `var n` can be safely assigned to a `Number` variable.
- `Batch<?>` does not prohibit `clear()` on a mutable list; that change propagates back to the `mutable` variable passed into the constructor.

## 6. Type Erasure: What Can Wildcards Do and Not Do?

Java generics are primarily checked at **compile time**. After type erasure, the runtime generally knows the object is a `Box`, but does not retain enough information to reliably distinguish `Box<String>` from `Box<Integer>`.

Because all type arguments of `Box<?>` are unbounded wildcards, it is a **reifiable type**, which can be used in checks from an `Object` value. Conversely, `Box<String>` or `Box<? extends Number>` is not reifiable in that way.

The following examples **intentionally fail to compile** when `input` has declared type `Object`:

```java
record Box<T>(T value) {}

// Error: cannot fully check T == String at runtime.
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}

// Error: cannot check the bound of the type argument in Box at runtime.
if (input instanceof Box<? extends Number>(var number)) {
    System.out.println(number);
}

// Error: elements of List<String> cannot be checked via generics at runtime.
if (input instanceof Box<?>(List<String> names)) {
    System.out.println(names);
}
```

The block above consists only of **compile-error examples for analysis**, not code to place into `main` to run.

**How to fix when you need to match a `String` value:**

```java
if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

**How to fix when the component is a `List`:** match `Box<?>(List<?> items)`, then check each element with `instanceof String` or use a verified API/data type. Do not cast `List<?>` to `List<String>` just because the record happens to contain string-like sample data.

**How to work with bounds:** place the bound on the declaration, such as `record NumberBox<T extends Number>(T value) {}`. In `NumberBox<?>(var n)`, `n` can be treated as `Number` thanks to the declaration constraint. Alternatively, when you already have a `Box<? extends Number> numericBox` variable from static checking in the calling API, `Number n = numericBox.value();` is valid. Do not treat `instanceof Box<? extends Number>` on an `Object` as a runtime verification of that bound.

## 7. Wildcard Capture and Pattern Variable Scope

With `Box<?>(var value)`, the `?` means some type exists, but **which type it is remains unknown**. The compiler does not allow you to infer `value` as `String` on your own:

```java
if (input instanceof Box<?>(var value)) {
    Object ok = value;
    // String notSafe = value; // does not compile without a type check
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

With `record Batch<E>(List<E> items) {}`, `Batch<?>(var items)` lets you read the list as `List<?>`. Because the element type is unknown, operations that add arbitrary elements are unsafe:

```java
if (batch instanceof Batch<?>(var items)) {
    Object first = items.isEmpty() ? null : items.get(0);
    // items.add("X"); // compile error: unknown whether E accepts String
    items.clear();       // type-safe; mutates the list if mutable
}
```

This example assumes `batch` is a variable of an appropriate type, such as `Batch<?>`. `items.clear()` may succeed (as in the complete program) or throw `UnsupportedOperationException` if the list does not support modification.

**Usage principle:** after deconstructing with `<?>`, process the component using operations common to the known type. To use operations specific to a subtype, perform a corresponding pattern check on the component or provide a type token/validation through the API design.

## 8. Wildcards Are Not an Immutability Mechanism

Records keep their component fields `private final`, but are only **shallowly immutable** if a component points to a mutable object. The `?` does not copy data and does not prevent mutations allowed by the component's API.

In the complete program:

```java
List<String> mutable = new ArrayList<>(List.of("A", "B"));
Batch<?> batch = new Batch<>(mutable);

if (batch instanceof Batch<?>(var items)) {
    items.clear();
}
System.out.println(mutable); // []
```

Even though `Batch<?>` does not reveal the element type, the list is still the **same object** that was passed in. `List<?>` prevents adding an arbitrary `String` for type safety; it does **not** automatically block `clear()`, `remove(...)`, or other structural mutation methods.

If the problem requires keeping data stable, perform a defensive copy in the record's constructor:

```java
record SafeBatch<E>(List<E> items) {
    SafeBatch {
        Objects.requireNonNull(items);
        items = List.copyOf(items);
    }
}
```

`List.copyOf` creates or reuses an unmodifiable list, isolating it from subsequent changes to the source mutable list; it does not deep-copy mutable elements. If `E` is an object with setters, elements can still change through their references. The example above is an **illustrative declaration** that can be placed in a Java class containing other records; it does not include `main`.

With record patterns, the accessor provided by the record is used to retrieve the component. If the accessor returns an array or mutable object, the bound variable can expose that exact reference; to protect arrays, you typically have to copy both on input **and** when returning from the accessor, while also considering the `equals`/`hashCode` contract.

## 9. Design Rules, Branch Ordering, and Common Pitfalls

| Situation | How to Handle |
| --- | --- |
| Only need to know the input is a generic record and read its contents | Use `Box<?>(var value)` |
| Need to handle `String`/`Integer` components specifically | Use `Box<?>(String s)` or `Box<?>(Integer n)` |
| Record has multiple independent type parameters | Use the matching number of wildcards, e.g., `Pair<?, ?>(...)` |
| Component is another generic record | Use a nested pattern, e.g., `Envelope<?>(Box<?>(String s), var tag)` |
| Need to know the element type of `List<?>` | Check each element or verify at the API boundary |
| Need to preserve a subtype bound on a record | Declare `T extends Number` on the record or use an already-checked API type |
| Component may be mutable | Use defensive copies/immutable components; wildcards do not solve immutability |
| Input value may be `null` | Separate `case null` from a record with a `null` component |

Mistakes to avoid:

1. **Writing `Box<String>(var s)` to check a generic type from `Object`.** Type erasure does not provide that check; use `Box<?>(String s)` to check the *component value*.
2. **Misunderstanding `Box<?>(String s)` as guaranteeing the record was created with `T = String`.** A `Box<Object>` containing a `String` can also match.
3. **Assuming `Box<?>(List<?> xs)` proves all elements are the same type.** It only proves the component is a `List`.
4. **Placing `case Box<?>(var value)` before specific branches.** The general branch can shadow specific branches, causing `switch` to report a dominated case error.
5. **Reading `?` as `Object` or a raw type.** Wildcards preserve static generic checking; raw types lose that protection.
6. **Calling `String`-specific methods on an unchecked `var value` variable.** Use a component type pattern or `instanceof`.
7. **Thinking `Box<?>(var value)` protects the inner data.** Patterns only access via accessors; copying and immutability must be handled by the record's design.
8. **Confusing `new Box<>(null)` with a `null` input.** When using `var` for the component, the former can still match the record, whereas the latter requires `case null`.
9. **Running record patterns on JDK 17 without checking the version.** Record classes existed in JDK 17, but record patterns became a standard feature in Java 21.

## 10. Self-Check Questions

**Question 1.** Why does `Box<?>` work with `Object input`, while `Box<String>` is unsuitable for runtime testing of the type argument?  
*Answer:* `Box<?>` is reifiable, whereas Java type erasure does not retain the concrete `T = String` information for reliable runtime matching.

**Question 2.** Will `Box<?>(String s)` match `new Box<Object>("x")`?  
*Answer:* Yes. It checks that the outer object is a `Box` and that the component is actually a `String`.

**Question 3.** Does `Pair<?, ?>(String a, Integer b)` force the two wildcards to be related to the same type?  
*Answer:* No. They are independent; the component patterns check each actual value.

**Question 4.** In `NumberBox<T extends Number>`, why can `NumberBox<?>(var n)` read `n` as `Number`?  
*Answer:* Because the upper bound `T extends Number` is declared in the record type, so the component variable has that upper bound at the static type level.

**Question 5.** Why does `Batch<?>(var items)` disallow `items.add("A")` while allowing `items.clear()`?  
*Answer:* The element type is unknown so adding a `String` could be type-unsafe; `clear()` does not add elements so it is valid under generics, even though it can mutate a mutable list.

**Question 6.** How do wildcards help make a record immutable?  
*Answer:* Wildcards do not make data immutable. You need immutable component design, defensive copies, and appropriate accessors.

## References

- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Java Language Specification 21 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
- [Oracle Java Tutorials — Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html)
