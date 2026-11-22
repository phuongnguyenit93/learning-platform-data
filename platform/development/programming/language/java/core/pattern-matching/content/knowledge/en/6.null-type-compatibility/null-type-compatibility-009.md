# Distinguishing Compile-Time Errors from `false` Results with `instanceof`

## 1. Two Very Different Outcomes When Checking Types

When learning Java Pattern Matching, beginners often encounter two situations that look similar on the surface but are fundamentally different:

- **Compile-time error:** The compiler determines that the `instanceof` expression or the usage of the pattern variable is invalid according to Java's type and scoping rules. The program **does not compile successfully** to run that code.
- **Runtime `false` result:** The `instanceof` expression is **valid in the language**, the program compiles, but the actual value at runtime does not match the queried type. The expression evaluates to the boolean `false`.

Example using the same type pattern but different **static types** for the input variable:

```java
// VALID: static type is Object, actual type is Integer.
Object value = 42;
if (value instanceof String text) {
    System.out.println(text.length());
}
// Condition is false; nothing is printed.
```

```java
// DOES NOT COMPILE on Java 17:
Integer value = 42;
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
```

In the first example, the variable `value` has the static type `Object`, so holding a `String` is a valid type possibility. The compiler allows the check, even though the current value is an `Integer` and the check returns `false`.

In the second example, `Integer` and `String` are classes with no inheritance relationship that allows the requested type conversion; both are `final` classes. With a variable of **static type `Integer`**, the compiler can conclude that this `String` check is invalid. Therefore, the code fails at compile time, and no boolean `false` result is produced by that expression.

**Guiding question:** "Is the expression valid for Java to run?" must be answered **before** "At runtime, does the value match the type?".

This lesson focuses on `instanceof` with **type patterns** (`value instanceof String text`) on **Java 17+**. This feature has been standard since Java 16 under JEP 394. Examples marked **DOES NOT COMPILE** are for error analysis only; the complete program later in the lesson is runnable Java 17 code.

## 2. Three Pieces of Information to Separate: Static Type, Runtime Type, and Pattern Type

Consider the following snippet:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

There are three distinct pieces of information:

1. **Static type of the left-hand expression:** `Object`. The compiler knows `value` is declared as `Object`.
2. **Actual runtime type of the object:** `String`. The currently assigned value is a string object.
3. **Type of the right-hand pattern:** `String`. The pattern checks whether the actual value belongs to this type and, if it matches, binds the variable `text` of type `String`.

The compiler checks **type compatibility** between (1) and (3) to decide whether to accept the expression. Only after the code is valid and executed does Java inspect (2) to return `true` or `false`.

Common point of confusion: **the static type does not necessarily match the runtime type**. An `Object` variable can hold a `String`, `Integer`, `ArrayList`, a record, or `null`. The same check on an `Object` variable can yield different results depending on the assigned object.

### Type Patterns vs. Traditional Type Checks

Java has two common forms:

```java
// Traditional type check:
if (value instanceof String) {
    // Only checks the type.
}

// Type pattern:
if (value instanceof String text) {
    // Checks the type and introduces the variable String text.
}
```

Both can return `false` at runtime. However, **type patterns also have their own compile-time rule**: if the static type of the left-hand expression is already a subtype of the pattern type, Java 17 rejects that pattern because the check would always succeed for every non-`null` value (Section 5). Do not mechanically apply this rule to the traditional `instanceof String` form.

## 3. A Valid Case That Returns `false`: The `null` Value

Example:

```java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không khớp");
}
```

The program prints:

```text
Không khớp
```

Reason:

- The static type `Object` allows testing for `String`, so the compiler accepts it.
- The runtime value is `null`. According to `instanceof` rules, **`null` does not match any type pattern**, so the condition is `false`.
- The `if` branch does not run; the variable `text` is not initialized for use. The `else` branch runs.

This is not a `NullPointerException`. The `instanceof` check itself on a `null` reference safely returns `false`.

Compare:

```java
Object input = null;
boolean isString = input instanceof String;
System.out.println(isString); // false
```

Both `input instanceof String` and `input instanceof String text` fail to match when the value is `null` (with static type `Object` as shown here).

### Do Not Confuse This with Calling a Method on `null`

```java
Object input = null;

// Safe: type check, result is false.
boolean matched = input instanceof String;

// If uncommented, the following line throws NullPointerException at runtime:
// System.out.println(input.toString());
```

A `NullPointerException` occurs when attempting to use a `null` reference to invoke a method or access a member inappropriately, not from a valid `instanceof` check.

### Unexpected Case: The Value Is `null`, Yet the Code Still Fails to Compile

```java
String text = null;

// DOES NOT COMPILE on Java 17:
// if (text instanceof String sameText) {
//     System.out.println(sameText);
// }
```

Even though the programmer sees that `text` is currently `null`, **the compiler checks the static type `String`** of the expression, not the fact that the variable is currently assigned `null`. The pattern `String sameText` is an unnecessary type pattern because `String` is already the static type of `text`; JLS 17 treats this as a compile-time error.

If you only want to check whether a `String` variable is non-`null`, write it directly:

```java
String text = null;
if (text != null) {
    System.out.println(text.length());
}
```

Or use the traditional type check form (which remains valid in the language):

```java
String text = null;
System.out.println(text instanceof String); // false
```

**Conclusion for `null`:** A valid `instanceof` encountering `null` returns `false`; however, a **type pattern that is invalid due to its static type** still causes a compile-time error, even when the concrete value is `null`.

## 4. A Valid Case That Returns `false`: A Runtime Object of a Different Type

A variable with a sufficiently general static type can hold many different objects. The compiler allows checking potentially compatible types, while the result depends on the actual object:

```java
Object value = Integer.valueOf(10);

System.out.println(value instanceof String); // false
System.out.println(value instanceof Integer); // true
System.out.println(value instanceof Number); // true
```

All of the checks above **compile** because the left-hand expression has static type `Object`. The runtime value is an `Integer`, so it is not a `String`, but it is an `Integer` and also a `Number`.

With a type pattern:

```java
Object value = Integer.valueOf(10);

if (value instanceof String text) {
    System.out.println("Text: " + text);
} else {
    System.out.println("Không phải chuỗi");
}
```

Output:

```text
Không phải chuỗi
```

`false` has a normal meaning in business logic: the program can fall through to `else`, return a default value, or try another type pattern.

### Case of a Superclass with Multiple Subclasses

```java
Number value = Double.valueOf(2.5);

if (value instanceof Integer number) {
    System.out.println("Integer: " + number);
} else {
    System.out.println("Không phải Integer");
}
```

Output:

```text
Không phải Integer
```

The test `value instanceof Integer number` is **valid**, because a `Number` variable can hold an `Integer`; however, on this run it holds a `Double`, so the pattern returns `false`.

If `value = Integer.valueOf(7)` is assigned, the same statement will match and the variable `number` will be bound to the `Integer` object.

### The Same Applies to Interfaces

```java
CharSequence sequence = new StringBuilder("Hi");

if (sequence instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Không phải String");
}
```

The code is valid: `CharSequence` has different implementations, including `String`. However, the runtime object is a `StringBuilder`, so the result is `false` and `Không phải String` is printed.

This clearly distinguishes **possible type compatibility** from an **actual successful match**.

## 5. Compile-Time Error Type 1: Static Types Cannot Be Appropriately Converted

Java does not permit arbitrary type comparisons. With a type pattern, the static type of the expression must be compatible with the pattern type according to the language's cast-conversion rules.

**Example that does not compile on Java 17:**

```java
Integer count = 12;

// INVALID:
// if (count instanceof String text) {
//     System.out.println(text.length());
// }
```

`Integer` and `String` are both distinct `final` classes with no inheritance relationship that would allow an `Integer` object to also be a `String`. The compiler has enough information to reject it before execution.

Compare with a variable of type `Object`:

```java
Object count = Integer.valueOf(12);
if (count instanceof String text) {
    System.out.println(text);
}
// Valid, but the condition returns false at runtime.
```

When the source has type `Object`, the compiler cannot conclude that all runtime values are not `String`: another `Object` value could point to a `String`. Therefore, the check is accepted.

**Note:** Different type names do not automatically mean an error. A class and its subclass, or a class and an interface that objects might implement, can still form a valid check. Evaluate **Java type convertibility**, rather than guessing from type names.

### Primitive Types in Java 17

On Java 17, the left-hand expression of `instanceof` must have a reference type or the `null` type; type patterns in this lesson use reference types:

```java
int age = 21;

// DOES NOT COMPILE on Java 17:
// if (age instanceof Integer n) { ... }
```

To use `instanceof` in a boxed number example, you can declare:

```java
Object age = Integer.valueOf(21);

if (age instanceof Integer n) {
    System.out.println(n + 1); // 22
}
```

`int` and `Integer` are two different types: `Integer` is a reference type wrapping an integer object; `int` is a primitive type. Do not confuse this Java 17 rule with language changes in newer Java versions.

## 6. Compile-Time Error Type 2: The Type Pattern Already Guaranteed to Match by Static Type

A special rule of **pattern `instanceof` in Java 17**: if the static type `S` of the left-hand expression is already a subtype of the pattern type `T`, the expression is rejected. The goal is to eliminate a pattern check that serves no purpose for non-`null` values.

```java
String value = "Java";

// DOES NOT COMPILE:
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
```

Because `value` already has static type `String`, the author can call `value.length()` directly.

The rule also applies when the pattern type is a supertype:

```java
String value = "Java";

// DOES NOT COMPILE on Java 17:
// if (value instanceof CharSequence chars) {
//     System.out.println(chars.length());
// }
```

`String` implements `CharSequence`, so any non-`null` `String` value is always a `CharSequence`; the type pattern above is considered a redundant check.

**However**, the traditional `instanceof` check that does not declare a pattern variable can still be valid:

```java
String value = "Java";

System.out.println(value instanceof String);       // true
System.out.println(value instanceof CharSequence); // true
```

Therefore, specifically distinguish **`value instanceof String`** from **`value instanceof String text`** when encountering a compile-time error.

### Checking a Subclass Is Valid

```java
Number value = Integer.valueOf(5);

if (value instanceof Integer integer) {
    System.out.println(integer * 2); // 10
}
```

The static type `Number` is **not** a subtype of `Integer`; a `Number` object could be an `Integer`, `Double`, etc. Hence, the check is useful and valid.

## 7. Compile-Time Error Type 3: Using Generics That Cannot Be Fully Checked at Runtime

Java uses **type erasure** for most parameterized generic type information. When the source has type `Object`, you cannot directly check with a type pattern that a value is a `List<String>`:

```java
Object value = java.util.List.of("a", "b");

// DOES NOT COMPILE:
// if (value instanceof java.util.List<String> texts) {
//     System.out.println(texts.size());
// }
```

The parameterized type `List<String>` is not a *reifiable* type suitable for checking this way at runtime. Instead, check against `List<?>`:

```java
Object value = java.util.List.of("a", "b");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
```

When the pattern `List<?> items` matches, Java only guarantees that the value is a `List`; it **does not guarantee** that each element is a `String`:

```java
Object value = java.util.List.of(1, 2);

if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
// Prints nothing: the list matches, but each Integer element does not match String.
```

The error on `List<String>` does not mean an actual list containing integers will cause `instanceof List<?>` to fail. The `List<?>` check is still **valid** and can evaluate to `true`; to verify the contents, you must check each element individually.

## 8. Compile-Time Error Type 4: Pattern Variable Scope Is Not Guaranteed

Even when the `instanceof` test itself is valid, **how the pattern variable is used** can prevent the entire code from compiling.

Error example:

```java
Object value = "Java";

// DOES NOT COMPILE:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("Done");
// }
```

The `||` operator only evaluates its right-hand side when the left-hand side is `false`. At that point, the type pattern `String text` **did not match**, so the variable `text` cannot be used on the right-hand side.

Valid way to check for a non-blank string:

```java
Object value = "Java";

if (value instanceof String text && !text.isBlank()) {
    System.out.println(text); // Java
}
```

The right-hand side of `&&` only executes when the `instanceof` check has succeeded. This is the **flow scoping** rule, unrelated to whether runtime returns `false`. Code that uses a pattern variable outside its valid scope is rejected at compile time.

You can also write an early-return condition:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip();
}
```

`text` is valid on the right-hand side of `||` because to reach it, the negated expression `!(value instanceof String text)` must be `false`, meaning the pattern matched. After the `if`, all invalid paths have already returned, so `text` is guaranteed to be in scope.

## 9. Comparison Table: When Is It a Compile-Time Error vs. When Does It Return `false`?

The examples in the table are evaluated under Java 17; each row assumes the variable is declared as described, without mixing duplicate variable declarations in the same block.

| Input and expression | Compiles? | Result / explanation |
| --- | --- | --- |
| `Object x = null; x instanceof String s` | Yes | `false`: `null` does not match |
| `Object x = 7; x instanceof String s` | Yes | `false`: runtime type is `Integer` |
| `Object x = "Hi"; x instanceof String s` | Yes | `true`: runtime type is `String` |
| `Number n = 2.5; n instanceof Integer i` | Yes | `false`: runtime type is `Double` |
| `Number n = 2; n instanceof Integer i` | Yes | `true`: runtime type is `Integer` |
| `CharSequence c = new StringBuilder("a"); c instanceof String s` | Yes | `false`: runtime type is `StringBuilder` |
| `Integer n = 7; n instanceof String s` | No | Static type and pattern type are not compatibly convertible |
| `String s = "Hi"; s instanceof String t` | No | Redundant type pattern: static type is already `String` |
| `String s = null; s instanceof String t` | No | Still errors based on static type, even though the value is `null` |
| `String s = "Hi"; s instanceof String` | Yes | `true`: this is a traditional type check |
| `Object x = List.of("a"); x instanceof List<String> l` | No | Cannot check this parameterized type |
| `Object x = List.of("a"); x instanceof List<?> l` | Yes | `true`: checks `List`, not element types |
| `int n = 1; n instanceof Integer i` | No | Primitive source type is invalid in Java 17 |
| `x instanceof String s || s.isEmpty()` with `Object x` | No | Right-hand side can run when the pattern has not matched |

`List` in the table is shorthand for `java.util.List` or imported from `java.util.List`. The table cells are **illustrative expression snippets**, not standalone Java files.

## 10. Complete Java 17 Example: Valid Checks and Actual Outputs

Create the file **`FalseVsCompileDemo.java`**:

```java
import java.util.List;

public class FalseVsCompileDemo {

    static String describe(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text.length();
        }
        if (value instanceof Integer number) {
            return "INTEGER:" + number;
        }
        if (value instanceof List<?> items) {
            return "LIST:" + items.size();
        }
        return "NO_MATCH";
    }

    static String numberKind(Number value) {
        if (value instanceof Integer number) {
            return "INT:" + number;
        }
        return "OTHER_NUMBER";
    }

    static String normalize(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "INVALID";
        }
        return "OK:" + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(3.14));
        System.out.println(describe(List.of("a", "b")));
        System.out.println(describe(null));

        System.out.println(numberKind(3));
        System.out.println(numberKind(3.0));

        System.out.println(normalize("  X  "));
        System.out.println(normalize("   "));
        System.out.println(normalize(null));
    }
}
```

Compile with JDK 17 or newer:

```bash
javac --release 17 FalseVsCompileDemo.java
java FalseVsCompileDemo
```

Exact output:

```text
TEXT:4
INTEGER:7
NO_MATCH
LIST:2
NO_MATCH
INT:3
OTHER_NUMBER
OK:X
INVALID
INVALID
```

Explanation:

1. `"Java"` matches `String`, `text.length()` is 4.
2. `7` is boxed to `Integer` when passed to the `Object` parameter; the `Integer number` branch matches.
3. `3.14` is boxed to `Double`; since it is not a `String`, `Integer`, or `List`, all checks return `false` and the method returns `NO_MATCH`.
4. `List.of("a", "b")` matches `List<?> items` and has 2 elements.
5. `null` does not match any type pattern in `describe`.
6. With a parameter of static type `Number`, checking `Integer` is valid; `3` matches `Integer`, while `3.0` is a `Double` and returns `OTHER_NUMBER`.
7. `normalize` combines negated `instanceof`, `||`, and `return` to filter out wrong types, blank strings, or `null` without accessing an unmatched pattern variable.

The program contains only valid expressions; **the intentionally failing snippets from earlier sections are not copied into this file**. If you want to observe `javac` error messages, test each failing snippet in a separate scratch file and fix it before running the complete program.

## 11. `false` from `instanceof` vs. Cast Exceptions

A valid `instanceof` check **does not throw `ClassCastException` simply because the pattern does not match**:

```java
Object value = Integer.valueOf(9);

if (value instanceof String text) {
    System.out.println(text);
} else {
    System.out.println("Không phải String");
}
```

The snippet above prints `Không phải String`.

Conversely, an explicit cast may be allowed by the compiler but **fail at runtime**:

```java
Object value = Integer.valueOf(9);

// Compiles, but throws ClassCastException if executed:
// String text = (String) value;
```

When casting `Object` to `String`, the compiler allows it because the static type `Object` does not rule out the runtime possibility of a `String`. However, the current object is an `Integer`, so the cast fails at runtime.

We can distinguish three outcomes:

| Case | Example | What happens |
| --- | --- | --- |
| Compile-time error | `Integer n = 1; n instanceof String s` | Cannot run |
| Valid type check, no match | `Object x = 1; x instanceof String s` | Evaluates to `false`; no exception thrown |
| Syntactically valid explicit cast that fails at runtime | `Object x = 1; String s = (String) x;` | Throws `ClassCastException` |

This explains why `instanceof` is commonly used to **safely check before accessing** an object as a specific type.

## 12. How to Self-Diagnose When an `instanceof` Check Does Not Work

Follow this order:

1. **Confirm the Java version.** Type patterns for `instanceof` have been standard since Java 16; use JDK 17 or newer and configure the proper language level or `--release 17`.
2. **Read the static type on the left.** Is the variable declared as `Object`, `Number`, `String`, `Integer`, or which interface? This is what the compiler sees, distinct from the runtime object.
3. **Check the type in the pattern.** Can the right-hand type be compatible according to Java rules? If conversion is completely impossible, it is a compile-time error; if the source is already a subtype of the pattern type, the type pattern is also rejected in Java 17.
4. **Check generic validity.** `List<String>` cannot be directly checked at runtime from an `Object`; try `List<?>` if you need to identify a list object.
5. **Check pattern variable scope.** The variable can only be used when all paths reaching that point have confirmed the pattern matched. Misusing `||`, `else`, or using the variable outside the branch are separate compile-time errors.
6. **If the code compiles, inspect the runtime value.** Is the value `null`? What type is the object? Does it actually belong to the pattern type or a suitable subclass/implementation? When it does not match, `instanceof` returns `false`.
7. **Do not conflate `false` with exceptions.** `false` is a valid boolean value; `ClassCastException` usually relates to an invalid runtime cast; `NullPointerException` can come from misusing a `null` reference.

Do not "fix" compile-time errors by scattering arbitrary casts. If a check makes no sense for the current static type, revisit the type declarations, interface design, or data flow.

## 13. Practice: Predict "Compile-Time Error", `true`, or `false`

### Exercise 1: Same Value, Two Static Types

**A:**

```java
Object x = Integer.valueOf(10);
boolean result = x instanceof String s;
```

**B:**

```java
Integer x = Integer.valueOf(10);
// boolean result = x instanceof String s;
```

**Answer:** A compiles and `result == false`. Uncommenting B causes a compile-time error because `Integer` and `String` are incompatible for this check. Both runtime values are `Integer`, but the static types differ.

### Exercise 2: `null` and the Redundant Type Pattern Rule

**A:**

```java
Object x = null;
boolean result = x instanceof String s;
```

**B:**

```java
String x = null;
// boolean result = x instanceof String s;
```

**Answer:** A is valid and returns `false`. B still fails to compile if uncommented, because the static type `String` is already a subtype (itself) of the pattern type `String`. `null` is not an exception to that compile-time rule.

### Exercise 3: Checking Subclasses of `Number`

```java
Number a = Double.valueOf(4.5);
Number b = Integer.valueOf(4);

boolean one = a instanceof Integer i;
boolean two = b instanceof Integer j;
```

**Answer:** Both expressions compile. `one == false` because `a` is actually a `Double`, while `two == true` because `b` is actually an `Integer`.

### Exercise 4: Generics and Variable Scope

Suppose `Object x = java.util.List.of("hi")`:

```java
// Does not compile in this case:
// if (x instanceof java.util.List<String> words) { ... }

// Valid:
if (x instanceof java.util.List<?> words) {
    System.out.println(words.size());
}
```

The output of the valid snippet is `1`. The `List<?>` pattern confirms the list type, not that each element is a `String`.

### Exercise 5: Choose a Valid Implementation

Write a method `String greeting(Object candidate)` that satisfies:

- If `candidate` is a `String` that is non-empty after `strip()`, return `"Hello "` concatenated with the normalized string.
- For objects of other types, blank strings, and `null`, return `"UNKNOWN"`.
- Do not use explicit casts and do not call methods on the pattern variable in an unmatched branch.

One solution:

```java
static String greeting(Object candidate) {
    if (!(candidate instanceof String name) || name.isBlank()) {
        return "UNKNOWN";
    }
    return "Hello " + name.strip();
}
```

The method returns `"Hello An"` for `"  An "`, and `"UNKNOWN"` for `null`, `123`, or `"   "`. The code compiles on Java 17.

## 14. Key Takeaways

For type patterns in Java 17, clearly separate **two phases**:

**Compile-time phase:** Java checks the validity of the left-hand static type against the right-hand pattern; it rejects incompatible checks, statically redundant type patterns, invalid generic types, and out-of-scope pattern variable usages. When an error occurs in this phase, the program produces no `true` or `false` result for the offending expression.

**Runtime phase:** Once compiled validly, `instanceof` inspects the actual object. If it is `null` or does not match the pattern type, the expression returns `false`; if it matches, it returns `true` and the pattern variable is bound for use within its valid scope.

**Quick rule of thumb:** *"Cannot be validly checked statically" is a compile-time error; "valid check whose runtime value does not match" is `false`.* Understanding this boundary helps diagnose Java errors faster and avoids confusing `null` or type incompatibility with runtime cast errors.

## Official References

- [Java SE 17 Language Specification §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [Java SE 17 Language Specification §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
- [Java SE 17 Language Specification §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
