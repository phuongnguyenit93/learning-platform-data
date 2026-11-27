# Pattern Matching for `instanceof` in Java 17: `null`, Incompatible Types, and Non-Matching Cases

In Java 17, **pattern matching for `instanceof`** lets you check an object's type and, when the check succeeds, obtain that object via a properly typed variable. However, this statement is often misunderstood in three scenarios: when the object is **`null`**, when the object has **a different runtime type than the checked type**, or when **the two types cannot be compatible even at compile time**. Understanding the difference between these scenarios helps you handle input data safely, write correct fallback branches, and avoid compile errors.

This lesson focuses on the behavior in **Java 17**, where pattern matching for `instanceof` is already a standard feature (JEP 394) and does not require `--enable-preview`.

## 1. Syntax and Meaning of the Check

Basic example:

```java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

The expression `value instanceof String text` consists of:

| Component | Role |
| --- | --- |
| `value` | Expression being checked. Its runtime value may belong to various reference types, or `null`. |
| `String` | Reference type with which the object must be compatible at runtime to match the pattern. |
| `text` | **Pattern variable** assigned and usable only where the compiler determines the check matched. |
| `instanceof` | Returns `boolean`: `true` when the pattern matches; `false` when it does not. A type-invalid expression is flagged as an error **at compile time**. |

In meaning, the snippet above is equivalent to manual type checking and casting:

```java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

The advantage is that Java only creates `text` when the check succeeds, avoiding rewriting the cast inside the valid branch.

### Three scenarios to distinguish

| Scenario | Example | Result |
| --- | --- | --- |
| Value is `null` | `Object x = null; x instanceof String s` | **`false`**. |
| Declared type can be compatible, but actual object does not match | `Object x = 42; x instanceof String s` | **`false`**. |
| Two types cannot be compatible under language rules | `String x = "a"; x instanceof Integer n` | **Compile error**. |

Distinguishing **`false` at runtime** from **compile-time type errors** is the core focus of this lesson.

## 2. When the Object Is `null`: The Pattern Does Not Match

With a **type pattern** like `String text`, a `null` value always makes `instanceof` return `false`:

```java
public class NullPatternDemo {
    public static void main(String[] args) {
        Object value = null;

        if (value instanceof String text) {
            System.out.println("String has " + text.length() + " characters");
        } else {
            System.out.println("Does not match String");
        }
    }
}
```

Output:

```text
Does not match String
```

No `NullPointerException` occurs merely because `value` is `null`: the `instanceof` operator checks and returns `false`. Variable `text` is not used in the `if` branch because that branch does not execute.

### 2.1. Checking `null` before `instanceof` is not mandatory

The following snippet is valid and safe for `null` values:

```java
static int stringLengthOrZero(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

If `value` is `null`, the method returns `0`. Inside the matching branch, `text` is guaranteed to be a **non-null** reference, because `null` does not match this type pattern.

However, if the application needs to distinguish **`null`** from **an object of another type**, separate the branches explicitly:

```java
static String describe(Object value) {
    if (value == null) {
        return "No data";
    }

    if (value instanceof String text) {
        return "String: " + text;
    }

    return "Object of another type";
}
```

If there is only an `else`, then `null`, `Integer`, `List<?>`, and any non-`String` objects all enter the same branch. That may be fine for some problems, but it does not always express the business meaning.

### 2.2. `instanceof` does not protect other operations from `null`

```java
Object value = null;

System.out.println(value instanceof String); // false

// The line below throws NullPointerException when executed:
// System.out.println(((Object) value.toString()) instanceof String text);
```

On the commented line, Java must call `value.toString()` **before** obtaining a value to pass to `instanceof`. Calling a method on a `null` reference causes the failure while evaluating the left-hand expression, not from the type check itself.

Similarly, `if (value instanceof String text && text.length() > 0)` is safe against `null` thanks to short-circuiting, whereas `if (value.toString() instanceof String text)` is not.

## 3. When the Runtime Type Does Not Match: Returns `false`, No Automatic Conversion

An `Object` variable can hold references to many kinds of objects:

```java
Object value = Integer.valueOf(25);

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Not a String");
}
```

Output:

```text
Not a String
```

In terms of **static type** (`Object`), the check is valid: an `Object` variable can point to a `String`. But at **runtime**, the current object is an `Integer`, so the `String text` pattern does not match.

This also applies to inheritance and interfaces:

```java
Object first = new java.util.ArrayList<String>();
Object second = "Hello";

System.out.println(first instanceof java.util.List<?>);  // true
System.out.println(second instanceof java.util.List<?>); // false
```

`instanceof` only checks whether the object belongs to the desired type; it **does not convert** data to that type. For example, the string `"25"` does not automatically turn into an `Integer`:

```java
Object value = "25";

if (value instanceof Integer number) {
    System.out.println(number + 1);
} else {
    System.out.println("Not an Integer");
}
```

To convert a numeric string into an integer, handle it explicitly—for example with `Integer.parseInt(text)` after matching `String`—and handle invalid content:

```java
static Integer tryParseInteger(Object value) {
    if (!(value instanceof String text)) {
        return null;
    }

    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return null;
    }
}
```

`null` as the return value of the method above indicates failure to convert under this example's design; in real applications you might choose `OptionalInt`, a dedicated result type, or another error-reporting strategy to distinguish non-string input from malformed strings.

## 4. Types Incompatible at Compile Time

In Java 17, the compiler checks whether the expression and type pattern can possibly have a valid type relationship. If it determines there is **no possibility of matching**, the program fails with an error **before running**.

### 4.1. Two classes that cannot convert to each other

Example that **intentionally does not compile**:

```java
String text = "hello";

// Compile error: String cannot be an Integer.
if (text instanceof Integer number) {
    System.out.println(number);
}
```

`String` and `Integer` are concrete classes with no compatible inheritance relationship. An object of type `String` cannot simultaneously be an object of type `Integer`, so there is no runtime situation where this pattern could succeed.

Compare with the valid snippet:

```java
Object value = "hello";

if (value instanceof Integer number) {
    System.out.println(number);
} else {
    System.out.println("Does not match Integer");
}
```

The second snippet compiles because a variable with **static type `Object`** could hold an `Integer` in other calls; in this particular case, the actual object is a `String`, so the result is `false`.

> **Do not change all variables to `Object` just to bypass type errors.** Informative declared types help the compiler catch modeling mistakes. When facing an "inconvertible types" error, inspect the intended types and data flow first.

### 4.2. Redundant pattern because the static type is already a subtype

Java 17 also detects checks that are **always true for every non-null value** of the expression under the subtype relationship. The following is also a **compile error**:

```java
String text = "hello";

// Compile error: static type String is already a subtype of String.
if (text instanceof String matched) {
    System.out.println(matched);
}
```

Another example:

```java
Integer number = 7;

// Compile error: Integer is already a subtype of Number.
if (number instanceof Number matched) {
    System.out.println(matched);
}
```

Reason: type patterns in Java 17 syntax are designed to **test and refine an uncertain type**, not to create an alias for an already-known type. The expression could still be `null`, yet the possibility of `null` does not make those type patterns valid checks in this context.

Replace with a check suited to the actual goal:

```java
String text = getText();

if (text != null) {
    System.out.println(text.length());
}
```

Here `getText()` represents a method returning `String`; the example focuses on how to check for `null`. If you want to give the variable a new name, assign a regular variable in the appropriate scope.

### 4.3. Do not use a primitive directly as the checked object

Intentionally invalid example:

```java
int number = 10;

// Compile error: left-hand operand is not a reference type.
if (number instanceof Integer boxed) {
    System.out.println(boxed);
}
```

`int` is a primitive, not a reference to an `Integer`. Pattern matching for `instanceof` in Java 17 operates on **reference types**; Java does not autobox a primitive operand just to make this check valid.

If you need to handle an object that might be an `Integer` wrapper, start from a reference:

```java
Object value = Integer.valueOf(10);

if (value instanceof Integer number) {
    System.out.println(number + 1);
}
```

When comparing or processing a variable that is already `int`, use `int` operations directly instead of `instanceof`.

### 4.4. Do not arbitrarily check type-erased generic arguments

Java uses **type erasure** for generics. Therefore, you cannot use a type pattern with generic type arguments that cannot be fully checked at runtime:

```java
Object value = java.util.List.of("a", "b");

// Compile error: cannot check List<String> with instanceof.
if (value instanceof java.util.List<String> items) {
    System.out.println(items);
}
```

In Java 17, the appropriate approach is to check a runtime-checkable type, such as `List<?>`:

```java
Object value = java.util.List.of("a", "b");

if (value instanceof java.util.List<?> items) {
    System.out.println("Element count: " + items.size());
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        } else {
            System.out.println("Element is not a String");
        }
    }
}
```

`List<?>` states that the value is a list, **without asserting the element type**. If business rules require every element to be a `String`, validate them with appropriate logic. Be sure to check each element and handle `null` elements or other types according to the input contract.

## 5. What Happens When a Pattern Does Not Match?

When `value instanceof String text` returns `false`:

- The corresponding `if` body **does not run**.
- The pattern variable `text` **is not considered matched**; it cannot be used where the compiler cannot prove a `true` result.
- If there is an `else`, execution enters the `else` branch.
- If there is no `else`, execution continues after the `if` statement.
- A non-matching `instanceof` itself **does not throw `ClassCastException`**.

Example:

```java
static void printAsString(Object value) {
    if (value instanceof String text) {
        System.out.println("String: " + text);
    } else {
        System.out.println("Input is not a string");
    }

    System.out.println("Continuing processing");
}
```

Inputs `null`, `Integer`, and `List` all enter `else`, then print `Continuing processing`. No casting error occurs because accessing `text` only happens when the pattern matches.

### 5.1. Using a default branch for polymorphic input

Suppose an API accepts `Object`:

```java
static String format(Object value) {
    if (value == null) {
        return "<null>";
    }

    if (value instanceof String text) {
        return "String(" + text.length() + "): " + text;
    }

    if (value instanceof Integer number) {
        return "Integer: " + number;
    }

    return "Unsupported type: " + value.getClass().getSimpleName();
}
```

The method distinguishes three cases: `null`, supported types, and unsupported types. The line `value.getClass()` is placed **after** the `null`-handling branch, so it is safe in this example.

If wrong-typed data must be rejected, you can `throw new IllegalArgumentException(...)` in the final branch instead of returning a string. If a non-matching type is a valid case, returning a default result is also reasonable. `instanceof` only reports match/non-match, while the business meaning of `false` is up to you.

### 5.2. Distinguishing type checking from forced casting

```java
Object value = Integer.valueOf(7);

if (value instanceof String text) {
    // Does not enter here.
}

// Intentionally broken example at runtime if executed:
// String text = (String) value;  // ClassCastException
```

A non-matching `instanceof` simply evaluates to `false`. Casting `(String) value` without checking can trigger `ClassCastException` when the actual object is not a `String`. Thus, pattern matching helps reduce the risk of unsafe casts when handling multi-type data.

## 6. Pattern Variable Scope When the Condition Is True or False

Java 17 applies **flow scoping**: a pattern variable can only be used at locations where control flow guarantees the check succeeded. Do not think of it as simply scoped to all `{}` braces or the entire method.

### 6.1. In the `if` branch when the check succeeds

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Valid
    } else {
        // System.out.println(text); // Compile error: pattern match not guaranteed
    }

    // System.out.println(text); // Compile error in this flow
}
```

The `else` branch is chosen **because** the pattern did not match, so `text` cannot be used as a `String` value there.

### 6.2. `&&` works properly thanks to short-circuit evaluation

```java
static boolean isNonBlankString(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

The expression on the right of `&&` is evaluated only when the left is `true`. Therefore, at `!text.isBlank()`, the compiler knows `text` has been assigned a valid `String`. For `null` or other types, the left-hand side is `false`, the right-hand side does not run, and the whole expression returns `false`.

### 6.3. `||` does not guarantee the pattern matched

Example that intentionally does not compile:

```java
Object value = "hello";

// Compile error: if the left-hand side is false, the right-hand side still runs while text is unmatched.
if (value instanceof String text || text.isBlank()) {
    System.out.println("...");
}
```

With `||`, when the left-hand side is **false**, Java must evaluate the right-hand side to determine the result. At that time, the pattern variable `text` has not been established. The compiler rejects accessing `text` at an unsafe position.

Use `&&` when the right-hand side needs data from a match on the left-hand side:

```java
if (value instanceof String text && text.isBlank()) {
    System.out.println("Empty or whitespace-only string");
}
```

If you also want to handle the **non-matching** case, write separate branches for clarity:

```java
if (value instanceof String text) {
    if (text.isBlank()) {
        System.out.println("Blank string");
    }
} else {
    System.out.println("Not a String or is null");
}
```

### 6.4. When negating the condition and exiting early

A pattern variable can be used **after `if`** if the non-matching branch definitely exits the method:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    // Reaching here means the pattern matched.
    return text.length();
}
```

This is a useful **guard clause** when immediately rejecting `null` or wrong-typed objects. Note that `!` negates the result of the entire `instanceof` expression, while `text` still only holds a value where the pattern matched.

Conversely, if the non-matching branch **does not exit** and only logs before continuing, you cannot use `text` outside the `if` by default.

## 7. Checking Multiple Types: Branch Order and Non-Matching Cases

In real applications, multiple types can be related by inheritance. For instance, `Integer` and `Double` are both `Number`s.

```java
static String numberKind(Object value) {
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    if (value instanceof Double decimal) {
        return "Double: " + decimal;
    }
    if (value instanceof Number number) {
        return "Other Number: " + number;
    }
    return "Not a number";
}
```

Here we check **specific types first** and the parent type `Number` afterward. If `value instanceof Number number` were placed at the top, every `Integer` and `Double` would enter the `Number` branch, preventing the specific branches below from running in this `if`-with-`return` flow.

This is a **processing-order** issue, not a bug in the pattern itself: an `Integer` object genuinely matches both the `Integer` and `Number` patterns when tested from a sufficiently general static type like `Object`.

For a non-numeric type such as `"12"`, all conditions return `false` and the method returns `Not a number`. There is no implicit conversion from string to number.

## 8. Complete Java 17 Program: Classifying `null`, Matches, and Non-Matches

Create the file `InstanceofCases.java`:

```java
public class InstanceofCases {
    public static void main(String[] args) {
        inspect(null);
        inspect("  Java 17  ");
        inspect(21);
        inspect(7L);
        inspect(new Object());
        inspect("   ");
    }

    static void inspect(Object value) {
        if (value == null) {
            System.out.println("Null value");
        } else if (value instanceof String text && !text.isBlank()) {
            System.out.println("String: " + text.strip());
        } else if (value instanceof String blankText) {
            System.out.println("Blank string: length " + blankText.length());
        } else if (value instanceof Integer number) {
            System.out.println("Integer: " + number);
        } else if (value instanceof Number number) {
            System.out.println("Other Number: " + number);
        } else {
            System.out.println("No match: "
                    + value.getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac InstanceofCases.java
java InstanceofCases
```

Output:

```text
Null value
String: Java 17
Integer: 21
Other Number: 7
No match: Object
Blank string: length 3
```

Key observations:

1. `null` enters the `value == null` branch. Without that branch, all type patterns fail to match and execution falls into the default branch.
2. Non-blank strings match `String text && !text.isBlank()` and are processed after trimming leading/trailing whitespace with `strip()`.
3. `21` is autoboxed to an `Integer` object when passed to the `Object` parameter, then matches `Integer number`.
4. `7L` is autoboxed to `Long`, does not match `Integer`, but matches `Number`.
5. `new Object()` matches none of the specialized types and reaches the final branch.
6. A whitespace-only string fails `!text.isBlank()` in the first condition, yet still matches the `String blankText` type pattern in the next branch; `blankText` is bound by an **independent check**.

In an API receiving data from multiple sources, this checking pattern cleanly distinguishes missing data, properly typed data, and out-of-scope types.

## 9. `instanceof` with Interfaces and General Types

You do not have to check a concrete class. A pattern can check an interface implemented by an object:

```java
interface Printable {
    String printText();
}

class Invoice implements Printable {
    @Override
    public String printText() {
        return "Invoice";
    }
}

class OtherValue {
}

public class InterfacePatternDemo {
    public static void main(String[] args) {
        printIfPossible(new Invoice());
        printIfPossible(new OtherValue());
        printIfPossible(null);
    }

    static void printIfPossible(Object value) {
        if (value instanceof Printable printable) {
            System.out.println(printable.printText());
        } else {
            System.out.println("Printing not supported");
        }
    }
}
```

Output:

```text
Invoice
Printing not supported
Printing not supported
```

A type might not sit in the same class hierarchy branch as the checked interface and still **be able** to implement that interface; Java allows many valid type relationships via interfaces. Therefore, compile-time compatibility checks do not just compare class names, but follow Java 17's **reference type conversion rules**.

When an interface represents a capability, such as `Printable`, checking the interface is often more flexible than listing concrete classes. A newly added implementation class later will still be supported without modifying `instanceof Printable printable`.

## 10. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `instanceof` returns `false` when the variable is `null` | `null` does not match Java 17 type patterns. | If a dedicated message is needed, check `value == null` first. |
| `false` even though the data looks similar | Runtime type differs from the checked type; `instanceof` does not compare contents or convert values. | Distinguish type checking from `equals` comparisons or parsing data. |
| Compiler reports `inconvertible types` | Static type and pattern type cannot have a valid relationship. | Review the data model and declared types. |
| Compiler reports a redundant pattern check / expression type is already a subtype | Patterns cannot be used to test a type the compiler already knows is a subtype. | Use the variable directly or `!= null` when only checking for `null`. |
| Compiler reports pattern variable not found in `else` | Variable is only guaranteed assigned when the pattern matches. | Use only in the true branch or where flow scoping permits. |
| Compiler reports variable missing on the right of `\|\|` | The right-hand side can run when the left pattern is `false`. | Use `&&` for conditions accessing the matched variable, or split branches. |
| Compiler rejects `List<String>` in `instanceof` | Generic type arguments cannot be fully checked at runtime. | Use `List<?>`, then check elements if needed. |
| Input `"12"` does not match `Integer` | It is a `String`, not an `Integer` wrapper. | Check `String` and parse the number with an appropriate API. |
| A broad branch catches all objects | Checked superclass/interface before specific subclasses in an `if/else if` chain. | Handle specific branches first or design polymorphic handling via interfaces. |
| `NullPointerException` appears in an expression containing `instanceof` | An operation before the check dereferenced `null`. | Ensure the left-hand expression evaluates safely without calling methods on `null`. |

Note that exact compiler error messages can vary across `javac`, IDEs, and JDK updates; the important part is distinguishing a **compile-time type error** from a **non-matching pattern at runtime**.

## 11. Self-Practice Exercises

### Exercise 1 — Result with `null`

```java
Object input = null;

if (input instanceof String text && text.length() > 2) {
    System.out.println("A");
} else {
    System.out.println("B");
}
```

**Question:** What does the program print? Does it throw `NullPointerException`?

**Answer:** Prints `B`, no exception thrown. `input instanceof String text` is `false`, so `text.length()` is never evaluated.

### Exercise 2 — Static type and runtime type

```java
Object a = "42";
Object b = Integer.valueOf(42);

System.out.println(a instanceof Integer);
System.out.println(b instanceof Integer);
```

**Answer:** `false` then `true`. `"42"` is a string; `42` is boxed in an `Integer`. Both variables have declared static type `Object`, so both checks are valid at compile time.

### Exercise 3 — Spot the compile errors

```java
String message = "hello";

// A
if (message instanceof Integer n) {
    System.out.println(n);
}

// B
if (message instanceof String text) {
    System.out.println(text);
}
```

**Answer:** Both A and B are rejected in Java 17. A has incompatible types; B is a redundant pattern check because static type `String` is already a subtype of the checked type. To test whether an object is a `String`, use a variable with a suitable static type such as `Object`. If you only want to know whether `message` is `null`, use `message != null`.

### Exercise 4 — Fix the variable-scope bug

```java
static boolean longText(Object value) {
    // Fix this condition:
    // return value instanceof String text || text.length() > 5;
    return value instanceof String text && text.length() > 5;
}
```

**Answer:** Change `||` to `&&`. The left check must be true before `text` can be read on the right-hand side, while returning `false` when `value` is `null` or not a `String`.

### Exercise 5 — Handle out-of-scope data

Write a method `read(Object value)` as follows: `null` returns `"missing"`, `String` returns the `strip()`ped content, `Integer` returns its string representation, and any other type returns `"unsupported"`. Apply pattern matching for `instanceof` without manual casting.

Hint:

```java
static String read(Object value) {
    if (value == null) {
        return "missing";
    }
    if (value instanceof String text) {
        return text.strip();
    }
    if (value instanceof Integer number) {
        return number.toString();
    }
    return "unsupported";
}
```

Test it with `null`, `" abc "`, `12`, `12L`, and `new Object()` to observe the difference between **matching**, **non-matching**, and **cases needing a default branch**.

## 12. Decision-Making Summary

When encountering an expression `value instanceof T variable` in Java 17, reason in this order:

1. **Is the expression type-valid at compile time?** If the static type cannot convert to `T`, or the type pattern is redundant because the static type is already a subtype of `T`, the compiler rejects it.
2. **Is the runtime value `null`?** If so, the type pattern does not match and the result is `false`.
3. **Does the runtime object belong to `T`?** If so, the pattern matches and the variable is usable where flow scoping allows. Otherwise, the expression returns `false`.
4. **What should happen on non-match?** Depending on the API contract, choose an `else` branch, default value, error message, or `throw` an exception; do not use the pattern variable where a match is not guaranteed.

This is the foundation for safely leveraging pattern matching for `instanceof`: eliminating manual casts while keeping full control over `null`, unexpected types, and post-check control flow.

### References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394) — proposal finalized in Java 16 and included in Java 17.
- [Java Language Specification SE 17 — §15.20.2 Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — typing rules, runtime behavior, and type patterns.
- [Java Language Specification SE 17 — §6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) — scope and flow scoping of pattern variables.
- [Java Language Specification SE 17 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30) — syntax and semantics of type patterns.
