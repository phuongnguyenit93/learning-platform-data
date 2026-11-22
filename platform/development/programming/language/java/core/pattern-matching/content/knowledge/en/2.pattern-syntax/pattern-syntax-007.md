# Pattern Resolution by Expression Type in Java

## 1. Goal: Why Is the Same Pattern Sometimes Valid and Sometimes an Error?

In Java, pattern matching is not just a runtime check on an object. **Before running, the compiler must determine whether a pattern can be applied to the type of the expression being tested.** This process is commonly explained as *pattern applicability / resolution by expression type*: taking the **static type** (*compile-time type*) of the expression to check compatibility with the pattern, determining the type of the bound variable, and in some cases inferring type arguments of a record pattern.

For example, the expression `value` may hold a `String` object at runtime while having a **static type** of `Object`, `CharSequence`, or `String` depending on where it is declared. Compilation rules apply to that static type, without guessing based on the actual object that will be passed in later.

After this lesson, you will be able to:

- Distinguish between the **static type of the expression**, the **type required by the pattern**, and the **actual runtime class of the value**.
- Predict whether a type pattern in `instanceof` is syntactically/type-valid or causes a compile error.
- Explain why a pattern variable has a definite type and why `var` can change how a pattern is analyzed.
- Understand how the expression type supports type inference in generic record patterns (Java 21+).
- Analyze `switch` branches by selector type, `case` applicability, ordering, dominance, and `null` handling.
- Recognize the key difference between Java 17 and Java 21 regarding *unconditional patterns* in `instanceof`.

## 2. Two Phases That Must Not Be Confused

Suppose there is an `expression` with static type `T` and a type pattern `U variable`.

**Compile-time phase:**

1. Java determines the static type `T` from the expression on the left-hand side of `instanceof`, or from the `switch` selector.
2. Java checks whether the pattern is **applicable at T**. For a reference type pattern `U` in Java 21, the core condition is that `T` has a *checked cast conversion* to `U` according to the Java language rules. Otherwise, the program has a compile error.
3. If it is a record pattern, the compiler also examines the record type, the component patterns, and may infer type arguments of a generic record from type `T`.
4. The type of the pattern variable is determined from the pattern and static inference rules. It does not automatically become a more specific class just because the runtime value has that class.

**Runtime phase:**

1. The expression is evaluated to a value.
2. Java attempts to match the value against the pattern (object type, record structure, component patterns, and `when` clause if present).
3. If it matches, the pattern variable is initialized and can be used in the scope where control flow guarantees the pattern has matched.
4. With `instanceof`, a `null` value makes the pattern matching result `false`, even if the pattern is considered *unconditional* by static type.

Key point: **applicable** only means "the pattern is valid to try"; it **does not guarantee** that every runtime value will match.

| Property | When is it determined? | Example |
| --- | --- | --- |
| Static type of the expression (`T`) | Compile time | `Object input` means `input` has static type `Object` |
| Type of the type pattern (`U`) | Compile time | `String text` requires type `String` |
| Whether the pattern is applicable at `T` | Compile time | `Object` can be tested against `String` |
| Whether the runtime value matches | Runtime | If `input` is actually `Integer`, `String text` does not match |
| Type of the pattern variable | Compile time | `text` has type `String` after the matching branch |

## 3. Java 17 Example: One Object, Multiple Static Type Views

The following is a **complete program** runnable on Java 17+. Save it as `StaticTypeResolutionDemo.java`.

~~~java
public class StaticTypeResolutionDemo {
    static String describe(Object expression) {
        if (expression instanceof String text && !text.isBlank()) {
            return "String:" + text.toUpperCase();
        }
        if (expression instanceof Number number) {
            return "Number:" + number.intValue();
        }
        return "Other";
    }

    static String charSequence(CharSequence expression) {
        if (expression instanceof String text) {
            return "String length=" + text.length();
        }
        return "Other CharSequence";
    }

    public static void main(String[] args) {
        Object wide = "Java";
        CharSequence interfaceView = "hi";
        System.out.println(describe(wide));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(charSequence(interfaceView));
        System.out.println(charSequence(new StringBuilder("ok")));
        var inferred = "Java";
        Object widened = inferred;
        System.out.println(describe(widened));
    }
}
~~~

~~~bash
javac --release 17 StaticTypeResolutionDemo.java
java StaticTypeResolutionDemo
~~~

Output:

~~~text
String:JAVA
Number:12
Other
String length=2
Other CharSequence
String:JAVA
~~~

Analysis:

- `Object wide = "Java";`: the variable `wide` has **static type** `Object`, while the runtime value is `String`. The pattern `String text` is applicable at `Object` and matches at runtime.
- In `describe(12)`, the integer argument is boxed into `Integer` to be passed to the `Object` parameter. The `String` pattern does not match; the `Number` pattern matches because `Integer` is a subclass of `Number`.
- With `null`, neither type pattern in `instanceof` matches, so it returns `Other`.
- `CharSequence interfaceView = "hi";` still holds a `String`. The pattern `String text` is applicable at `CharSequence`: a `String` object can be viewed through the `CharSequence` interface.
- `new StringBuilder("ok")` is also a `CharSequence` but not a `String`, so the same pattern does not match at runtime.
- `var inferred = "Java";` causes Java to infer the **static type** of `inferred` as `String`. The assignment `Object widened = inferred;` creates an expression of a wider type; the call `describe(widened)` still uses the same `String` value at runtime.

In the pattern `expression instanceof String text`, `text` has type `String`. If the pattern is `expression instanceof Number number`, the variable `number` has type `Number`, even though the runtime object may be an `Integer` or `Double`. You cannot call `Integer`-specific methods on `number` without an appropriate check/cast.

## 4. Compatibility Is Decided by the Expression Type

Read each example in order: **expression type → pattern to try → whether the compiler allows it → result if run**.

| Static type of expression | Pattern | Java 17/21 | Explanation |
| --- | --- | --- | --- |
| `Object` | `String s` | Valid | There are `Object` instances at runtime that are also `String` |
| `CharSequence` | `String s` | Valid | `String` implements `CharSequence` |
| `Number` | `Integer n` | Valid | `Integer` is a subclass of `Number` |
| `Integer` | `String s` | Compile error | Two classes are incompatible under checked cast |
| `String` | `String s` | Java 17: error; Java 21: valid | Version difference regarding *unconditional patterns* in `instanceof` |
| `Object` | `Number n` | Valid | Can match values of type `Integer`, `Double`, ... |

### Error Example Due to Incompatible Classes

This is a **snippet intentionally written not to compile**; do not add it to the runnable program above:

~~~java
static boolean invalid(Integer expression) {
    return expression instanceof String text; // COMPILE ERROR
}
~~~

Java knows `Integer` is a `final` class and cannot be a `String`; there is no valid checked cast in this case. The error occurs at compile time; it does not wait for the program to run and return `false`.

Conversely, when writing:

~~~java
Object expression = Integer.valueOf(7);
boolean matched = expression instanceof String text;
~~~

Java allows it because the static type is `Object`; the expression returns `false` because the actual value is `Integer`. **Having the same runtime value does not mean the same compile-time validity check result.**

### Java 17 vs. Java 21 Difference: A Pattern That Already Covers the Static Type

With Java 17, the following snippet is rejected by `javac --release 17` (*unconditional patterns in instanceof are not supported in -source 17*):

~~~java
static boolean test(String expression) {
    return expression instanceof String text;
}
~~~

Starting from Java 21, a type pattern that covers the static type like this is allowed. The following program **runs on Java 21+**:

~~~java
public class UnconditionalTypeDemo {
    static String describe(String expression) {
        return expression instanceof String text
            ? "Matched:" + text.length()
            : "No match";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 UnconditionalTypeDemo.java
java UnconditionalTypeDemo
~~~

Output:

~~~text
Matched:4
No match
~~~

"Unconditional" is a concept about the **static type relationship of the pattern**. It does not turn `null` into a `String` object; `instanceof` with `null` still returns `false`. In practice, if the input is already a `String`, there is usually no need to use a type pattern again to confirm the obvious; you only need to handle `null` if necessary.

## 5. Inference with `var` Does Not Change the Rules

Two roles of `var` must be distinguished:

**Local variables in Java 10+:**

~~~java
var expression = "hello";   // expression has static type String
Object wider = expression;  // wider has static type Object
~~~

`var` is inferred from the initializer expression; it does **not** mean the variable has a dynamic type or type `Object`. Therefore, if you write `expression instanceof String s`, Java 17 may reject the unconditional form, whereas `wider instanceof String s` is valid. Java 21 allows both checks.

**Pattern variable in a type pattern at `instanceof`:**

~~~java
if (wider instanceof String text) {
    System.out.println(text.length());
}
~~~

Here you use the type name `String`; you **do not write** `wider instanceof var text` in Java 17/21. `var` has a different role: it is supported for component patterns directly inside a record pattern (Java 21+), as shown in the next section.

## 6. Generic Record Patterns: Expression Type Helps Infer Component Types

A generic record can be declared as `record Envelope<T>(T payload) {}`. In Java 21, a record pattern both checks the record type and deconstructs its components. When writing `Envelope(var item)`, the compiler can use the **static type of the expression** to infer the generic parameter of the record pattern and the type of `item`.

Here is the complete program saved in `RecordTypeResolutionDemo.java`:

~~~java
record Envelope<T>(T payload) {}

public class RecordTypeResolutionDemo {
    static String typed(Envelope<String> expression) {
        if (expression instanceof Envelope(var item)) {
            return "Upper:" + item.toUpperCase();
        }
        return "Not envelope";
    }

    static String unknown(Object expression) {
        if (expression instanceof Envelope(var item)) {
            return "Payload:" + item;
        }
        return "Not envelope";
    }

    public static void main(String[] args) {
        System.out.println(typed(new Envelope<>("java")));
        System.out.println(unknown(new Envelope<>(42)));
        System.out.println(unknown("hello"));
    }
}
~~~

~~~bash
javac --release 21 RecordTypeResolutionDemo.java
java RecordTypeResolutionDemo
~~~

Output:

~~~text
Upper:JAVA
Payload:42
Not envelope
~~~

**Why do the two methods differ?**

- `typed(Envelope<String> expression)` knows the type parameter is `String`. With `Envelope(var item)`, Java has enough static information to infer the type of `item` as `String`. Calling `item.toUpperCase()` is valid.
- `unknown(Object expression)` only knows the static type is `Object`. The record pattern recognizes `Envelope` at runtime, but cannot deduce `T = String` just by inspecting the actual payload. In this case, `item` is seen as `Object`.
- If you replace `return "Payload:" + item;` with `return item.toUpperCase();` in `unknown`, the compiler reports that `toUpperCase()` does not exist on `Object`.
- A record pattern does not "read back generic type arguments" that were removed by *type erasure* at runtime. Type inference depends on information already available at compile time.

The applicability of a record pattern does not only consider the outer record: the component patterns must also be compatible with the declared type of each record component. For example, in `record Point(int x, int y)`, the pattern `Point(int x, int y)` binds two components of type `int`, whereas you cannot arbitrarily describe this integer component as a `String` object. Record patterns are a finalized feature since Java 21.

## 7. Generic Type Patterns: Adding Type Arguments Does Not Automatically Make It Checkable

The generic case makes it clearer why Java checks the **static type of the expression**. The following program runs on Java 17:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericResolutionDemo {
    static String describe(List<String> words) {
        if (words instanceof ArrayList<String> items) {
            return "ArrayList size=" + items.size();
        }
        return "Other list size=" + words.size();
    }

    public static void main(String[] args) {
        System.out.println(describe(new ArrayList<>(List.of("a", "b"))));
        System.out.println(describe(List.of("a")));
    }
}
~~~

~~~bash
javac --release 17 GenericResolutionDemo.java
java GenericResolutionDemo
~~~

Output:

~~~text
ArrayList size=2
Other list size=1
~~~

The static type `List<String>` already carries the type argument information; Java allows the check against `ArrayList<String>` because the corresponding conversion is valid under checked cast rules. This **does not mean** Java checks every element of the generic collection at runtime.

On the other hand, the following snippet **intentionally does not compile** in Java 17/21:

~~~java
static boolean invalid(Object expression) {
    return expression instanceof java.util.List<String> values;
}
~~~

From an arbitrary `Object`, Java cannot perform a safe runtime check to verify the `String` type argument of a `List` due to *type erasure*. The compiler reports that `Object` cannot be safely cast to `List<String>` in this check. If you only need to know whether it is a `List`, you can use `expression instanceof List<?> values` (with `import java.util.List;`), then inspect/interpret each element as needed. Avoid assuming that `List<?>` is `List<String>`.

## 8. In `switch`, the Selector Expression Also Determines Which Cases Are Valid

Starting in Java 21, `switch` with patterns works on reference types with these rules:

1. **Selector type:** The compiler takes the static type of the expression in `switch (expression)`.
2. **Case compatibility:** Each case pattern must be applicable at that selector type. For example, `case String s` can be applied when the selector is `Object` or `CharSequence`; `case Integer i` is an error when the selector is `CharSequence` in Java 21.
3. **Ordering and dominance:** Branches are evaluated in the order they appear. A broader pattern placed earlier can make a narrower pattern after it unreachable, and Java will report a compile error.
4. **Exhaustiveness:** A `switch` expression must cover all possibilities; an enhanced `switch` statement using patterns must also be exhaustive. `default` is commonly used as the fallback branch.
5. **Null:** `case null` handles the `null` value separately. Without a matching branch, switching on `null` can throw `NullPointerException`.

Complete program saved in `SwitchResolutionDemo.java`:

~~~java
public class SwitchResolutionDemo {
    static String describe(Object expression) {
        return switch (expression) {
            case null -> "Null";
            case String text when text.isBlank() -> "Blank String";
            case String text -> "String:" + text.length();
            case Number number -> "Number:" + number.intValue();
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchResolutionDemo.java
java SwitchResolutionDemo
~~~

Output:

~~~text
Null
Blank String
String:4
Number:7
Other
~~~

Here, the selector type is `Object`, so both `String` and `Number` cases are valid to try. The runtime value determines which branch matches. The guard `when text.isBlank()` is only evaluated after the pattern `String text` has matched, so `text` has type `String` inside the guard.

### Invalid Case: Case Incompatible with the Selector Type

The following snippet **intentionally does not compile**:

~~~java
static int invalid(CharSequence expression) {
    return switch (expression) {
        case Integer number -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

The static type `CharSequence` has no valid checked cast to the `Integer` class (a `final` class that does not implement `CharSequence`). The selector type is checked before Java matches runtime values.

### Invalid Case: A Broader Pattern Dominates a Narrower Pattern

The following snippet also **intentionally does not compile**:

~~~java
static int invalid(Object expression) {
    return switch (expression) {
        case CharSequence value -> 1;
        case String text -> 2; // COMPILE ERROR: dominated
        default -> 3;
    };
}
~~~

Every `String` is a `CharSequence`, so the first branch already covers all values the second branch intends to catch. When you need to distinguish `String` from other `CharSequence` implementations, place `case String text` **before** `case CharSequence value`.

Note: **pattern resolution does not mean Java automatically picks the "most specific case" regardless of order** like a method overload resolver. Java applies static applicability/dominance checks and uses the valid case order at runtime.

## 9. Important Misconceptions

1. **"If the actual value is a String, the compiler surely knows."** Incorrect: with an `Object` parameter, the compiler must handle every possible value of type `Object`. The pattern variable is bound according to the pattern, not by predicting the data.
2. **"A valid pattern means it always matches."** Incorrect: `Object expression = 7; expression instanceof String s` is valid, yet returns `false`.
3. **"Any two reference types can be compared with a pattern."** Incorrect: types without a corresponding checked cast conversion, such as `Integer` and `String`, cause a compile error.
4. **"`var` is always `Object`."** Incorrect: `var expression = "Java"` infers type `String`; and `var` in a generic record component is inferred from the component and the record's type context.
5. **"Generic parameters are checked at runtime."** Incorrect: `List<?>` only determines the appropriate class/type relationship; it does not verify that elements are `String`. Java allows certain generic pattern checks when the static type is specific enough, but it cannot bypass type erasure.
6. **"An unconditional pattern always matches `null`."** Incorrect: with `instanceof`, `null` returns `false`. In addition, Java 17 and Java 21 differ in accepting unconditional type patterns.
7. **"In `switch`, the more specific case is automatically prioritized."** Incorrect: ordering and dominance are part of the validity rules.

## 10. Exercises and Explained Answers

**Exercise 1 (Java 17+):** Given `Object expression = "Java";` and `CharSequence expression2 = "Java";`. Can both use `instanceof String s`?

**Answer:** Yes. For both static types `Object` and `CharSequence`, a valid checked cast to `String` exists. At runtime both match because the value is a `String`.

**Exercise 2 (Java 17 and Java 21):** Consider `String expression = "Java";` with the pattern `expression instanceof String s`. Is there a compilation difference?

**Answer:** Yes. With `--release 17`, this unconditional case is rejected; with `--release 21`, it is valid. For a `null` value, `instanceof` is still `false`.

**Exercise 3 (Java 21+):** Given:

~~~java
record Box<T>(T value) {}

static void inspect(Box<String> known, Object unknown) {
    if (known instanceof Box(var first)) {
        System.out.println(first.toUpperCase());
    }
    if (unknown instanceof Box(var second)) {
        System.out.println(second);
    }
}
~~~

What types does the compiler see for `first` and `second`?

**Answer:** `first` is `String` thanks to the static type `Box<String>` of `known`. `second` is `Object` because `unknown` only has static type `Object`, so `second.toUpperCase()` cannot be called directly. This is a snippet that can be placed inside a class and requires Java 21+.

**Exercise 4 (Java 21+):** In `switch(Object x)`, why does `case CharSequence cs` before `case String s` cause an error, while swapping the order can be valid?

**Answer:** `CharSequence` covers `String`; placing it first makes `case String` unreachable. Placing `String` first allows catching the narrower case before `CharSequence`. Do not forget to add `default` or other cases if exhaustiveness is required.

## 11. Checklist When Reading a Pattern

When encountering confusing pattern matching code, ask yourself in order:

1. What **static type** does this expression have at the point being tested? Is it declared with `var`, an interface type, a generic type, or an explicit cast?
2. What **type** is the pattern requiring? Is it a type pattern or a record pattern with nested components?
3. Is the pattern **applicable** at that static type? Are there generic/checked cast issues or Java version differences?
4. If valid, can the **runtime value** match? How will `null` be handled?
5. What type does the pattern variable have, and in which control-flow region can it be used? With `switch`, is any case *dominated*, and is the `switch` exhaustive?

Mastering the chain **static type of expression → valid pattern → actual object matches → pattern variable is used** will help you read, write, and debug pattern matching code more accurately.

### Further Reading in the Specification

- Java SE 21 JLS `15.20.2 — `instanceof` and pattern matching: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21 JLS `14.30.3 — Applicability, unconditional, and dominance: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3
- Java SE 21 JLS `14.11.1 — Rules of `switch` blocks: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1