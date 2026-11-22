# Pattern applicability and checked cast compatibility in Java

## 1. Two concepts answering two different questions

When writing pattern matching, for example `value instanceof String text`, Java must answer **two questions in strict order**:

1. **At compile time:** Is the pattern `String text` *applicable* to the **static type** of the expression `value`? To decide, the compiler relies on permitted type conversions; for reference types, the core criterion is **checked cast compatibility**.
2. **At runtime:** If the check is type-valid, does the **actual value** match the pattern? Only when it matches is the pattern variable `text` initialized and usable within its appropriate scope.

The two questions are not interchangeable. A pattern can be valid at compile time yet fail to match at runtime. Conversely, even if you "know for sure" that a value holds a `String`, you still cannot write a pattern that violates the static typing rules.

This article uses **Java 21 (JLS 21)** as the reference to explain type patterns, record patterns, and pattern `switch`. Examples that use only `instanceof` type patterns are compatible with Java 17 (a standard feature since Java 16); record pattern examples require Java 21 (a standard feature since Java 21). Changes in newer Java releases and *preview* features are not implicitly applied to the Java 21 rules.

## 2. What is pattern applicability?

In JLS 21 §14.30.3, a pattern `p` being **applicable at type T** means that **the static type T of the input value permits testing pattern p**.

For a **type pattern declaring a variable of reference type U**, the primary rule is:

> A pattern of reference type U is applicable at reference type T when **T is checked cast convertible to U**.

You can remember this with the following diagram:

```text
Expression to check
  └── static type T
         └── is there a checked cast conversion T → U?
                ├── No  → compile error: pattern is not applicable
                └── Yes → allowed to compile
                            └── at runtime, test value against pattern
                                   ├── Does not match → false / check next case
                                   └── Matches        → initialize pattern variable
```

Example:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`value` has static type `Object`, not `String`, even though the actual object is a string. Because `Object → String` is a **checked** narrowing reference conversion, `String text` is applicable at `Object`. At runtime, the object is indeed a `String`, so the `if` branch is executed.

If you change the value to `Integer.valueOf(10)`, it **still compiles** because the variable's static type is still `Object`, but the `String` check returns `false`. Therefore, `applicable` **does not mean** `always matches`.

### Distinguishing three terms

| Concept | What does it ask? | Phase |
| --- | --- | --- |
| *Pattern applicability* | Given static type T, is this pattern allowed to be used? | Compile time |
| *Checked cast compatibility* | Can T be converted via an accepted cast to perform a type test for U? | Compile time |
| *Pattern matching* | Does the current value actually satisfy the pattern and initialize the pattern variable? | Runtime |

Applicability is the condition for the compiler to **accept an expression containing a pattern**; the true/false result comes from **runtime matching**. Beyond applicability, a construct like `switch` also has its own rules regarding shadowed cases (*domination*) and completeness (*exhaustiveness*).

## 3. Checked cast compatibility: why can't every cast be used in a pattern?

JLS 21 §5.5 calls a value **checked cast compatible** with a target reference type if there is a casting conversion to that type, **excluding narrowing reference conversions that are not fully checked (*unchecked*)**.

For reference source and target types, the common cases are:

- **Identity:** the same type, such as `String → String`.
- **Widening reference:** from a subclass to a compatible superclass or interface, such as `String → CharSequence`.
- **Checked narrowing reference:** from a general type to a more specific type when Java can verify the required compatibility, such as `Object → String`, `Number → Integer`.
- **Unchecked narrowing reference:** a cast that is only valid with an `unchecked` warning because generic type information is erased at runtime, such as `Object → List<String>`. This form **does not** satisfy checked cast compatibility.

The word `checked` here is **a property that permits a type-based test**; it does not mean *every* conversion generates a runtime check instruction. Identity and widening reference conversions do not need a dynamic cast check. Conversely, an `unchecked` cast may still check the erased part of the type (for example, the `List` class) but **cannot verify the `String` type argument**.

Further classification in JLS §5.1.6.3:

- *Completely unchecked:* after type erasure, the type relationship is like an upcast; the JVM needs no runtime check.
- *Partially unchecked:* after type erasure, the relationship is like a downcast; the JVM can still check the raw type, but cannot guarantee the generic type arguments.

Both are **unchecked narrowing reference conversions**; do not confuse `partially unchecked` with **checked cast compatibility**. If the conversion required to apply a pattern is an unchecked narrowing conversion, the pattern is rejected at compile time.

### Quick prediction table for Java 21

| Static type T of expression | Pattern U | Applicable? | Reason |
| --- | --- | --- | --- |
| `Object` | `String s` | Yes | `Object → String` is checked narrowing |
| `CharSequence` | `String s` | Yes | `CharSequence → String` can be checked |
| `Number` | `Integer n` | Yes | `Integer` is a subclass of `Number` |
| `String` | `Integer n` | No | These two classes cannot share an instance |
| `Object` | `List<?> list` | Yes | Wildcard parameter does not require verifying a specific element type |
| `Object` | `List<String> list` | No | Casting from `Object` requires unchecked narrowing |
| `List<Integer>` | `ArrayList<Integer> list` | Yes | Source type retains compatible generic information; downcast is checked |
| `List<Integer>` | `ArrayList<String> list` | No | The two parameterizations are provably distinct; no valid casting conversion exists |

Notably, **a generic target is not automatically forbidden**. For example, `List<Integer> → ArrayList<Integer>` is allowed because the static type relationship is tight enough, whereas `Object → List<String>` is not. Thus, the rule "patterns cannot be used with any generic type" is false.

## 4. Program demonstrating valid cases (Java 17+)

Save as **`ApplicabilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ApplicabilityDemo {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "String=" + text.length();
        }
        if (value instanceof List<?> items) {
            return "List=" + items.size();
        }
        return "Other=" + String.valueOf(value);
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify(List.of("a", "b")));
        System.out.println(classify(null));

        List<Integer> numbers = new ArrayList<>(List.of(4, 5));
        if (numbers instanceof ArrayList<Integer> concrete) {
            System.out.println("First=" + concrete.get(0));
        }
    }
}
```

Compile and run with JDK 17 or JDK 21:

```bash
javac ApplicabilityDemo.java
java ApplicabilityDemo
```

Exact output:

```text
String=4
List=2
Other=null
First=4
```

Explanation of each case:

1. `Object → String` is allowed to be tested with `instanceof String text`. The value `"Java"` actually matches, so its length `4` is retrieved.
2. `Object → List<?>` is a valid test. From `items` we know **this is a `List`**, without knowing the exact type of each element.
3. `null` does not match a type pattern on the right-hand side of `instanceof`, so `classify(null)` reaches the final branch and returns `Other=null`.
4. `List<Integer> → ArrayList<Integer>` is a valid check because the source already carries compatible `Integer` type information; the actual object is an `ArrayList`, so `First=4` is printed.

The last example is a common point of confusion: `ArrayList<Integer>` is not a generally reifiable type, yet matching against it is valid here thanks to **the static type of the source expression**. The condition is that the compiler can prove the required casting conversion is checked.

## 5. Code snippets that do NOT compile and why

**The code snippets below intentionally contain errors. Do not merge them into the runnable file in Section 4.**

### 5.1. Two incompatible classes

```java
String text = "abc";
if (text instanceof Integer n) { // COMPILE ERROR
    System.out.println(n);
}
```

`String` and `Integer` are two classes with no compatible inheritance relationship; no instance can simultaneously belong to both classes. The compiler rejects this based purely on **static types**, without needing to run the condition.

Similarly, `Number n` is not checked cast convertible to `String` because `String` is a final class and cannot be a subtype of `Number`.

### 5.2. Unchecked generic cast vs. a valid pattern

```java
Object value = java.util.List.of("A", "B");

@SuppressWarnings("unchecked")
java.util.List<String> casted = (java.util.List<String>) value;
// The cast above can compile, but it is inherently unchecked.

if (value instanceof java.util.List<String> names) { // COMPILE ERROR
    System.out.println(names.size());
}
```

For `Object → List<String>`, the JVM can verify that it is a `List`, but **cannot verify that each element has type `String`** because generics are erased. An explicit cast may be permitted with an unchecked warning, whereas a type pattern requires checked cast compatibility and is therefore **disallowed**.

Instead, check `List<?>` and validate elements individually:

```java
static void printStrings(Object value) {
    if (value instanceof java.util.List<?> items) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            } else {
                System.out.println("Không phải String: " + item);
            }
        }
    }
}
```

This is **an illustrative method**: place it inside a class and call it from a program. The `List<?>` pattern only verifies the list type; the `String text` pattern checks **each element**. Do not use `@SuppressWarnings("unchecked")` to pretend a runtime type check was performed.

### 5.3. `provably distinct` generics even when using a subclass

```java
java.util.List<Integer> numbers = java.util.List.of(1, 2);

if (numbers instanceof java.util.ArrayList<String> wrong) { // COMPILE ERROR
    System.out.println(wrong);
}
```

`List<Integer>` and `ArrayList<String>` differ in their type arguments, so no reference conversion is permitted. The compiler knows this without inspecting the contents of the list.

### 5.4. No automatic boxing of primitives for instanceof patterns

```java
int number = 42;
if (number instanceof Integer boxed) { // COMPILE ERROR in Java 21
    System.out.println(boxed);
}
```

In Java 21, the left-hand operand of `instanceof` must be a reference type or the null type; `int` does not meet that requirement. If you actually need a pattern:

```java
Object number = Integer.valueOf(42);
if (number instanceof Integer boxed) {
    System.out.println(boxed.intValue()); // 42
}
```

Here, `Object` holds an `Integer` that was **already boxed**. Do not assume `instanceof` automatically boxes primitives in Java 21; primitive pattern features in newer JDKs were preview features with their own rules.

## 6. Record patterns: applicability also checks each component (Java 21)

JLS 21 §14.30.3 specifies an additional condition for a **record pattern** with record type `R` and component pattern list `L`. This pattern is applicable at static type `T` if:

1. `T` is **checked cast convertible** to `R`.
2. For **each component pattern** `p` in `L`, `p` is applicable at **the declared type of the corresponding component** of record `R`.

In other words, a record pattern must pass **two levels of type checking**: the outer record type and the inner component patterns. Nested patterns are checked recursively using the same principle.

Standalone example, save as **`RecordApplicabilityDemo.java`**, requires JDK 21:

```java
public class RecordApplicabilityDemo {
    record Packet(Object payload) {}
    record Envelope(Packet packet) {}

    static String decode(Object input) {
        if (input instanceof Envelope(Packet(String text))) {
            return "Text=" + text;
        }
        if (input instanceof Envelope(Packet(Integer number))) {
            return "Int=" + number;
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(decode(new Envelope(new Packet("OK"))));
        System.out.println(decode(new Envelope(new Packet(7))));
        System.out.println(decode(new Envelope(new Packet(null))));
        System.out.println(decode(null));
    }
}
```

```bash
javac RecordApplicabilityDemo.java
java RecordApplicabilityDemo
```

Output:

```text
Text=OK
Int=7
Other
Other
```

Why is this program valid?

- `input` has static type `Object` and has a checked cast conversion to the `Envelope` record.
- The `packet` component of `Envelope` has type `Packet`, so the record pattern `Packet(...)` is applicable there.
- The `payload` component of `Packet` has type `Object`, so both `String text` and `Integer number` are applicable at `Object`.
- At runtime, the data must also match **all** levels of the pattern. The value `Packet(null)` does not match the `String` or `Integer` type patterns, so it returns `Other`; `decode(null)` also returns `Other`.

Conversely, suppose a record has a component already declared as `String`:

```java
record Label(String value) {}

Object input = new Label("x");
if (input instanceof Label(Integer n)) { // COMPILE ERROR
    System.out.println(n);
}
```

The type pattern `Integer n` is **not applicable at the component type `String`**. Even though `Object → Label` is a permitted test at the outer level, the overall pattern is still invalid because the inner level is wrong.

**Note on null:** `null` at the *input position of the entire record pattern* does not match. For a component pattern inside a record, Java 21 has specific rules for *null-matching type patterns* when that pattern is unconditional at the component type. You should not oversimplify by claiming that every nested type pattern rejects null; in this example, the component has type `Object`, and the `String`/`Integer` patterns are not unconditional at `Object`.

## 7. An applicable pattern does not guarantee a valid switch

In Java 21, a `switch` with type patterns still requires **each case pattern to be applicable at the selector type**. Beyond that condition, the compiler checks **case ordering**, **domination**, and **exhaustiveness**.

Valid example:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text: " + s;
        case Integer n -> "int: " + n;
        default -> "other";
    };
}
```

This is **a Java 21 illustrative method**; it must be placed inside a class to compile. Both `String` and `Integer` patterns are applicable at the `Object` selector; at runtime, `switch` selects the matching case.

Two distinct error categories must be distinguished:

- **Applicability error:** a `switch` with a `String` selector includes `case Integer n`; there is no suitable checked cast conversion from `String` to `Integer`. The case is rejected because **the types cannot be compatible**.
- **Dominance error:** with selector `Object`, placing `case Number n` **before** `case Integer i`; every `Integer` is a `Number`, so the subsequent `Integer` case is shadowed. Both patterns are applicable at `Object`, yet **the case ordering is still invalid**.

Similarly, adding `when` is a filtering condition evaluated after matching; a guard cannot turn an inapplicable pattern into a valid one. A `switch expression` must also be exhaustive over all possible cases, typically using `default` or a set of patterns proven to cover all possibilities.

## 8. Checked cast compatibility does not mean the cast will succeed

Compare three situations with the same value of static type `Object`:

```java
Object value = 123;

boolean matches = value instanceof String s; // false

// Executing the line below will throw ClassCastException:
// String text = (String) value;

// Generic check not allowed by the specification:
// if (value instanceof java.util.List<String> strings) { }
```

- The line `instanceof String s` **compiles** because `Object → String` is checked cast convertible, then returns `false` because the actual object is an `Integer`.
- The cast `(String) value` **is syntactically and type-wise valid**, but if executed, it fails with `ClassCastException`.
- `List<String>` used with an `Object` input in a pattern **does not compile**, because it would rely on an unchecked narrowing conversion.

In summary, distinguish between **a cast that is allowed to be written**, **a cast that can be properly checked against the target type**, **a pattern allowed at the static type**, and **an actual value matching**. These are four related but distinct ideas.

## 9. How to analyze an “inconvertible types” or “unsafe cast” error yourself

When the compiler rejects a pattern, follow these steps in order:

1. **Identify the static type T** from the variable declaration, return type, or type inference. Do not rely on `toString()`, debug data, or `getClass()` of a value you happen to know.
2. **Identify the pattern U or record R**; if it is a record pattern, note the declared type of each component.
3. **Check the conversion T → U/R**: is it identity, widening, or narrowing? If the types can be checked, the pattern has a chance of being applicable; if they are unrelated or provably distinct, stop at the compile-time error.
4. **Check generics:** does the narrowing require an unchecked cast? If so, consider `<?>`, designing an API with more accurate types, or checking elements individually. Never use an unchecked cast to assert certainty about data types.
5. **If it is a record pattern, repeat the check for every component**. One inapplicable component makes the entire record pattern inapplicable.
6. **If it is a switch, also check dominance and exhaustiveness**. These two errors are independent of applicability errors.
7. **Finally, ask whether the runtime value will match**. A non-matching case typically returns `false` or moves to another case, whereas using a direct cast can throw `ClassCastException`.

### Self-check questions

**Question 1.** `Object x = java.util.List.of("A");` — why is `x instanceof List<?> items` valid while `x instanceof List<String> items` is invalid?

**Answer:** The expression has **static type `Object`**. Checking `List<?>` only needs to verify the list type, whereas `List<String>` requires verifying the generic type argument, for which the runtime does not retain enough information. The latter requires an unchecked narrowing conversion.

**Question 2.** `List<Integer> numbers = new ArrayList<>();` — why is `numbers instanceof ArrayList<Integer> a` valid?

**Answer:** The source static type already constrains `Integer` in `List<Integer>`, and the conversion to `ArrayList<Integer>` is checked narrowing; the JVM only needs to check the `ArrayList` class at runtime, while type-argument compatibility is proven from the static type.

**Question 3.** Given `record Box(String text) {}`, can `Box(Integer n)` be used as a record pattern to test an `Object` value?

**Answer:** No. Although `Object` can be tested for whether it is a `Box`, the `text` component has static type `String`, and `Integer n` is not applicable at `String`.

## 10. Authoritative references

The rules in this article are based on the **Java Language Specification, Java SE 21**:

- [JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): defines applicability, unconditional patterns, and dominance.
- [JLS §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): defines checked cast compatibility.
- [JLS §5.1.6.1–5.1.6.3 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.6): permitted conversions, checked/unchecked, completely/partially unchecked.
- [JLS §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): compile-time conditions and runtime behavior of `instanceof`.

**Key takeaway:** Pattern applicability asks whether the **static type** permits the test; checked cast compatibility is the core criterion for reference patterns; record patterns also check each component. Once a pattern passes compile-time checks, matching the data remains a runtime decision.
