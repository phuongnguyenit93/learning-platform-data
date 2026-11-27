# Negating Conditions and Early Exits with `instanceof` Patterns in Java 17

When checking an object's data type, Java 17 allows writing **pattern matching for `instanceof`** to both confirm the type and declare a variable already cast to that type. This feature has been an official part of the language since Java 16 and is stable in Java 17.

A very common situation in real-world code is: **if the object is not of the right type, exit the method or skip the element; if it is of the right type, continue processing**. This expression style combines three key concepts:

- Negating the `instanceof` result with the `!` operator.
- Writing a **guard clause** — a branch that checks an error condition and exits early.
- Understanding **flow scoping** — a pattern variable's scope depends on whether the compiler can prove the type check succeeded.

This lesson presents those rules through Java 17 code snippets usable in modern applications.

## 1. From Traditional `instanceof` to Pattern Variables

Before pattern matching, code handling a string from an `Object` variable was typically written like this:

```java
public static void printLength(Object value) {
    if (!(value instanceof String)) {
        return;
    }

    String text = (String) value;
    System.out.println(text.length());
}
```

The code above works, but requires both checking with `instanceof` and explicitly casting with `(String) value`.

With Java 17, it can be shortened:

```java
public static void printLength(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    System.out.println(text.length());
}
```

In the expression `value instanceof String text`:

| Component | Role |
| --- | --- |
| `value` | Expression containing the object to check. |
| `String` | Type to check against. |
| `text` | **Pattern variable** receiving the value typed as `String` if the check succeeds. |
| `!` | Negates the `instanceof` result. |
| `return` | Exits the method if the object is not a `String`. |

Notably, even though `text` is written **inside the `if` condition**, it is still usable **after the `if` statement**. This is a result of *flow scoping* rules; the variable does not merely live within the nearest pair of curly braces.

## 2. Why Is `text` Valid After the Negated Condition?

Re-examine the snippet:

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }

    return text.length();
}
```

At execution time, there are two possibilities:

1. `input` is **not** a `String`: the expression `input instanceof String text` is `false`; after negation, the `if` condition becomes `true` and `return 0` immediately terminates the method.
2. `input` **is** a `String`: the `instanceof` expression is `true`; negation yields `false`; the program skips the `if` branch and continues to `text.length()`. At this point `text` is definitely assigned.

Program flow path:

```text
                         Object input
                              |
                              v
                 input instanceof String text
                      /                 \
                   false                true
                    |                    |
                    v                    v
                Negate (!)           Negate (!)
                    |                    |
                   true                 false
                    |                    |
                    v                    v
                if branch           Skip if branch
                return 0                 |
                                         v
                                 text is assigned
                                         |
                                         v
                                return text.length()
```

The compiler can prove that **every path reaching the final statement** has passed the type check successfully. Therefore, `text` is valid at that position.

This rule does not mean every pattern variable is usable after every `if`. It only exists in locations where control flow guarantees the pattern matched.

## 3. Contrast: Negation Alone Is Not Enough

**Wrong — the failed-check branch can still fall through:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not a string");
    }

    System.out.println(text.length()); // COMPILE ERROR
}
```

If `input` is an `Integer`, after printing the message, execution still continues to `text.length()` even though there is no matched `text` variable. Therefore the compiler disallows using `text` here.

**Right — add an early exit:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not a string");
        return;
    }

    System.out.println(text.length());
}
```

**Right — handle the success branch directly inside `else`:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not a string");
    } else {
        System.out.println(text.length());
    }
}
```

In `else`, the negated condition failed, which is equivalent to `instanceof` succeeding. Hence `text` can be used in `else`.

If you choose the guard clause version with `return`, the main processing logic stays at a shallower indentation level and needs no `else`.

## 4. Standard Syntax for a Guard Clause with `instanceof` Patterns

A commonly used pattern is:

```java
static Result process(Object input) {
    if (!(input instanceof ExpectedType value)) {
        // Handle input of the wrong type.
        return fallbackResult();
    }

    // value has type ExpectedType here.
    return use(value);
}
```

The names `Result`, `ExpectedType`, `fallbackResult`, and `use` above are illustrative placeholders. Complete Java 17 example:

```java
public class PatternGuardDemo {
    static String normalizeName(Object input) {
        if (!(input instanceof String name)) {
            return "UNKNOWN";
        }

        String normalized = name.strip();

        if (normalized.isBlank()) {
            return "UNKNOWN";
        }

        return normalized;
    }

    public static void main(String[] args) {
        System.out.println(normalizeName("  Minh  "));
        System.out.println(normalizeName(123));
        System.out.println(normalizeName("   "));
    }
}
```

Output:

```text
Minh
UNKNOWN
UNKNOWN
```

Compile with Java 17:

```bash
javac --release 17 -encoding UTF-8 PatternGuardDemo.java
java PatternGuardDemo
```

Here two conditions are handled independently:

- `!(input instanceof String name)`: rejects non-`String` data.
- `normalized.isBlank()`: rejects strings of the right type that have no content after trimming leading and trailing whitespace.

Pattern matching handles **type checking**, while validating the data inside the type remains up to the application.

## 5. Combining Negation with `throw` to Report Invalid Input

Not every situation should return a default value. For APIs requiring properly typed input, the appropriate approach may be **throwing an exception**:

```java
public class StrictNumberDemo {
    static int doubleInteger(Object input) {
        if (!(input instanceof Integer number)) {
            throw new IllegalArgumentException(
                    "input must be an Integer"
            );
        }

        return Math.multiplyExact(number, 2);
    }

    public static void main(String[] args) {
        System.out.println(doubleInteger(12)); // 24
        System.out.println(doubleInteger("12")); // IllegalArgumentException
    }
}
```

For non-`Integer` input, `throw` terminates the normal execution path of the method. Consequently, when execution reaches `Math.multiplyExact(number, 2)`, the pattern `Integer number` is guaranteed to have matched.

Using `Math.multiplyExact` in the example makes multiplication throw `ArithmeticException` if the result overflows the `int` range; that is a separate rule for arithmetic calculations, not a requirement of pattern matching.

Common meaningful early-exit styles:

| Statement | Control-flow effect | Suitable scenario |
| --- | --- | --- |
| `return;` | Ends a `void` method. | Skip processing when input is unsuitable. |
| `return value;` | Ends the method and returns a result. | A valid fallback value exists. |
| `throw new ...` | Throws an exception; does not continue normally. | Input violates the method's contract. |
| `continue;` | Skips the remainder of the current iteration. | Filtering out wrong-typed elements in a loop. |
| `break;` | Exits the loop or breakable construct. | Stop iterating upon encountering an unsuitable element. |

The common thread is that **execution flow cannot continue to the code using the pattern variable along any path where the pattern has not matched**.

## 6. Using `continue` to Skip Wrong-Typed Elements in a Loop

When iterating over a `List` of `Object` containing mixed data types, a guard clause with `continue` is often clearer than nesting multiple `if` branches.

```java
import java.util.List;

public class FilterNames {
    public static void main(String[] args) {
        List<Object> values = List.of(
                "  An  ",
                100,
                "  Bình  ",
                false,
                "  Chi  "
        );

        for (Object item : values) {
            if (!(item instanceof String name)) {
                continue;
            }

            System.out.println(name.strip());
        }
    }
}
```

Output:

```text
An
Bình
Chi
```

On each iteration:

- If `item` is not a string, `continue` immediately moves to the next element.
- If `item` is a string, the negated condition is `false`, so `name` is safely used for the rest of the iteration.

**Contrast — omitting `continue` is invalid:**

```java
for (Object item : values) {
    if (!(item instanceof String name)) {
        System.out.println("Skipping");
    }

    System.out.println(name.strip()); // COMPILE ERROR
}
```

Without an early-exit statement, the compiler cannot guarantee `name` always exists at the `println` statement.

## 7. Using `break` When Encountering an Unsuitable Element

Similar to `continue`, `break` can eliminate the non-matching path from the remaining code inside a loop.

```java
import java.util.List;

public class ReadPrefix {
    public static void main(String[] args) {
        List<Object> values = List.of(
                "first",
                "second",
                42,
                "fourth"
        );

        for (Object item : values) {
            if (!(item instanceof String text)) {
                break;
            }

            System.out.println(text.toUpperCase());
        }
    }
}
```

Output:

```text
FIRST
SECOND
```

When `42` is encountered, `break` exits the loop so `text.toUpperCase()` will not execute on that iteration.

Distinction:

- `continue`: skips **one iteration** and continues checking subsequent elements.
- `break`: stops **the entire nearest enclosing loop** (unless a label specifies an outer loop).

Therefore, choosing `continue` or `break` is a decision about **business semantics**, not merely a trick to bring a pattern variable into scope.

## 8. Negation and the `&&` Operator: Which Condition Is Checked First?

Java uses **short-circuit evaluation** for `&&` and `||`:

- For `A && B`: `B` is evaluated only if `A` is `true`.
- For `A || B`: `B` is evaluated only if `A` is `false`.

This order determines when a pattern variable is definitely assigned.

### 8.1. Using `&&` after an affirmative `instanceof` check

**Right:**

```java
static boolean isLongName(Object input) {
    return input instanceof String name && name.length() >= 5;
}
```

`name.length()` runs only when `input instanceof String name` is `true`. By then, `name` holds a `String` value.

### 8.2. Do not use `&&` immediately after a negated `instanceof` to read the variable

**Wrong:**

```java
static boolean invalid(Object input) {
    return !(input instanceof String name) && name.isBlank();
    //                                     ^  ERROR: name is not guaranteed to exist
}
```

The `&&` operator evaluates the right-hand side only when the left-hand side is `true`. However, the left-hand side `!(input instanceof String name)` equals `true` precisely when the pattern **did not match**. Thus `name` cannot be used on the right-hand side.

A valid way to express "not a string or is an empty/blank string" appears in the next section.

## 9. Negation and the `||` Operator: Checking Invalid Type or Data

When you want to **reject objects that are not `String` or are blank strings**, you can combine negation with `||`:

```java
static String requireNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "Need a non-blank String"
        );
    }

    return text;
}
```

Why is this valid?

1. If `input` is not a `String`, `!(input instanceof String text)` equals `true`. Because of `||`, Java **does not evaluate** `text.isBlank()`. The whole condition is `true` and throws an exception.
2. If `input` is a `String`, the negated side equals `false`. Only then does Java evaluate `text.isBlank()`, at which point `text` is already assigned.
3. If the entire condition is `false`, `input` is definitely a non-blank string, so `return text` is valid after the `if`.

The example can be extended to normalize the string:

```java
static String requireNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Invalid input");
    }

    return text.strip();
}
```

With the requirement **to accept only strings that have content after trimming leading/trailing whitespace**, `text.isBlank()` is sufficient to reject whitespace-only strings.

### Comparison table of four logical patterns

| Expression | Can the pattern variable be used on the right-hand side? | Explanation |
| --- | --- | --- |
| `input instanceof String text && text.length() > 3` | **Yes** | Right-hand side runs when `instanceof` matched. |
| `!(input instanceof String text) || text.isBlank()` | **Yes** | Right-hand side runs when negation is `false`, meaning the pattern matched. |
| `input instanceof String text || text.isBlank()` | **No** | Right-hand side runs when `instanceof` failed. |
| `!(input instanceof String text) && text.isBlank()` | **No** | Right-hand side runs when negation is `true`, meaning the pattern failed. |

Practical rule: **do not mechanically memorize "`&&` works, `||` fails"**. Check **which case causes the right-hand side to be evaluated** and whether the pattern has matched in that case.

## 10. Negated Conditions with Multiple Error Branches

When checking multiple properties, keep the **failure condition** and **error message** clear.

For example, an API that only accepts positive integers:

```java
public class QuantityChecker {
    static int requirePositiveInteger(Object input) {
        if (!(input instanceof Integer quantity)) {
            throw new IllegalArgumentException(
                    "quantity must be of type Integer"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be greater than 0"
            );
        }

        return quantity;
    }

    public static void main(String[] args) {
        System.out.println(requirePositiveInteger(8));
    }
}
```

Splitting into two guard clauses as above works well when callers need error messages distinguishing **wrong type** from **invalid value**.

They can be combined into one condition:

```java
static int requirePositiveInteger(Object input) {
    if (!(input instanceof Integer quantity) || quantity <= 0) {
        throw new IllegalArgumentException(
                "Need an Integer greater than 0"
        );
    }

    return quantity;
}
```

Both styles are valid in Java 17. Choose splitting or combining depending on how specifically each error needs to be explained to API callers.

## 11. How Is `null` Handled?

An `instanceof` pattern expression does not match when the object is `null`:

```java
Object input = null;

if (!(input instanceof String text)) {
    System.out.println("Not a String");
    return;
}

// For the null case, execution does not reach here.
```

Here `input instanceof String text` is `false`, so negation is `true` and the early exit runs. No `NullPointerException` occurs simply from checking `instanceof` against `null`.

The `||` example likewise does not access an unassigned variable:

```java
static boolean valid(Object input) {
    return input instanceof String text && !text.isBlank();
}

static boolean invalid(Object input) {
    return !(input instanceof String text) || text.isBlank();
}
```

When `input == null`:

- `valid(input)` returns `false`.
- `invalid(input)` returns `true`.
- Neither calls `text.isBlank()` due to short-circuiting rules.

This does not mean all nested conditions are immune to `null` errors. If you call `input.toString()` **before** checking the type, that operation can still throw `NullPointerException`.

## 12. Without an Early Exit: Variable Scope Is Typically Limited

Compare three versions with similar goals.

### Version A — success branch inside `if`

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip());
    }

    // Cannot use text here: the instanceof branch might not have matched.
}
```

This is suitable when handling only one case of the right type without needing to exit the method.

### Version B — error branch exits early with `return`

```java
static void print(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    System.out.println(text.strip());
}
```

This is suitable when the entire remainder of the method requires `value` to be a `String`.

### Version C — has `else` without needing to exit the whole method

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println("String: " + text.strip());
    } else {
        System.out.println("Other type");
    }
}
```

This is suitable when each branch has independent handling. Not every use of a pattern variable needs a guard clause; a guard clause is only beneficial when the failure condition should stop early.

## 13. What Does Flow Scoping with Negation Mean for API Design?

Writing guard clauses helps place preconditions at the top of a method and keep the main logic in a clear, linear flow.

Example handling a request that only accepts objects classified as `String`:

```java
public class UserService {
    static String toLoginId(Object rawId) {
        if (!(rawId instanceof String id)) {
            throw new IllegalArgumentException(
                    "rawId must be a String"
            );
        }

        String cleaned = id.strip();

        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException(
                    "rawId must not be blank"
            );
        }

        if (cleaned.length() > 30) {
            throw new IllegalArgumentException(
                    "rawId must not exceed 30 characters"
            );
        }

        return cleaned;
    }
}
```

The sequence of checks at the start of the method successively rejects:

1. Non-`String` objects (including `null`).
2. Empty strings after normalization.
3. Strings exceeding the example's length limit.

When execution reaches `return cleaned`, the main processing is guaranteed both the **type** and the **data conditions** required by the method.

If an API parameter is already declared as `String` and does not need to accept other types, you can check `null`/content directly; there is no need to force every API to accept `Object` just to use pattern matching. `instanceof` patterns are especially useful at boundaries where data can genuinely have multiple possible types.

## 14. Common Mistakes

### Mistake 1 — forgetting parentheses around the expression before `!`

**Wrong:**

```java
if (!input instanceof String text) {
    return;
}
```

The `!` operator applies to its operand before the `instanceof` expression is parsed as the author intended; writing it this way is invalid for an `Object`.

**Right:**

```java
if (!(input instanceof String text)) {
    return;
}
```

Pattern to remember: `!(expression instanceof Type variable)`.

### Mistake 2 — using the variable after a check branch that can complete normally

**Wrong:**

```java
static void inspect(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Wrong type");
    }

    System.out.println(text.length()); // ERROR
}
```

**Right:** the wrong-type branch must exit early, or move the code using `text` into a branch guaranteed to have matched.

### Mistake 3 — confusing `&&` and `||`

**Wrong:**

```java
static boolean bad(Object input) {
    return input instanceof String text || text.isEmpty();
}
```

**Right if you want to accept non-empty strings:**

```java
static boolean good(Object input) {
    return input instanceof String text && !text.isEmpty();
}
```

**Right if you want to detect invalid values:**

```java
static boolean isBad(Object input) {
    return !(input instanceof String text) || text.isEmpty();
}
```

Determine whether the expression's goal is checking **validity** or **invalidity**, and choose the corresponding logical operator.

### Mistake 4 — thinking a pattern variable exists everywhere in the method

**Wrong:**

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text);
    }

    System.out.println(text); // ERROR
}
```

Outside the `if`, there is no guarantee that `input` matched `String`. Unlike a local variable declared at the start of a method, a pattern variable's scope is tied to **paths that definitely matched**.

### Mistake 5 — confusing `instanceof` patterns with pattern syntax newer than Java 17

Java 17 officially supports **type patterns** in `instanceof`, such as `input instanceof String text`.

Do not write standard Java 17 exercises using syntax finalized in newer Java releases, such as **record deconstruction patterns**:

```java
// Not valid instanceof syntax at the Java 17 level:
if (input instanceof Point(int x, int y)) {
    // ...
}
```

If `Point` is a record in Java 17, you can still check its **type** using:

```java
record Point(int x, int y) {}

static void showPoint(Object input) {
    if (!(input instanceof Point point)) {
        return;
    }

    System.out.println(point.x() + ", " + point.y());
}
```

Similarly, pattern matching in `switch` is not yet a standard feature of Java 17; it is a different syntax and is unnecessary for the examples in this lesson.

### Mistake 6 — assuming type matching also validates the value

`input instanceof String text` only confirms that the value is non-`null` and of the appropriate type. It does **not** guarantee minimum length, valid format, or any business rule.

```java
static String requireEmailLike(Object input) {
    if (!(input instanceof String email)) {
        throw new IllegalArgumentException("Need a String");
    }

    email = email.strip();

    if (email.isBlank() || !email.contains("@")) {
        throw new IllegalArgumentException("Invalid value");
    }

    return email;
}
```

Checking `contains("@")` in the example is only an illustration of a simple business condition; it is **not a complete email address validator**.

### Mistake 7 — creating name conflicts with an existing local variable

A pattern variable has its own name and follows Java's variable scoping and declaration rules.

**Wrong — declaring a duplicate name inside a scope that already has that variable:**

```java
static void show(Object input) {
    String text = "fallback";

    if (input instanceof String text) { // ERROR: text is already declared
        System.out.println(text);
    }
}
```

**Right — choose a different pattern variable name:**

```java
static void show(Object input) {
    String fallback = "fallback";

    if (input instanceof String text) {
        System.out.println(text);
    } else {
        System.out.println(fallback);
    }
}
```

## 15. Comprehensive Practice with Three Types of Early Exit

The following exercise uses `return`, `continue`, and `throw` to show that each early-exit form has its own semantics.

Create the file `EarlyExitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class EarlyExitDemo {

    static String render(Object input) {
        if (!(input instanceof String text)) {
            return "[unsupported]";
        }

        return text.strip().toUpperCase();
    }

    static List<String> onlyNonBlankStrings(List<Object> items) {
        List<String> result = new ArrayList<>();

        for (Object item : items) {
            if (!(item instanceof String text)) {
                continue;
            }

            String cleaned = text.strip();

            if (cleaned.isBlank()) {
                continue;
            }

            result.add(cleaned);
        }

        return List.copyOf(result);
    }

    static int requireInteger(Object input) {
        if (!(input instanceof Integer number)) {
            throw new IllegalArgumentException(
                    "Need an Integer, received another type"
            );
        }

        return number;
    }

    public static void main(String[] args) {
        System.out.println(render("  java  "));
        System.out.println(render(17));

        var source = new ArrayList<Object>();
        source.add("  Lan  ");
        source.add(123);
        source.add("   ");
        source.add("  Nam  ");
        source.add(null);

        System.out.println(onlyNonBlankStrings(source));
        System.out.println(requireInteger(42));
    }
}
```

Run with Java 17:

```bash
javac --release 17 -encoding UTF-8 EarlyExitDemo.java
java EarlyExitDemo
```

Expected output:

```text
JAVA
[unsupported]
[Lan, Nam]
42
```

Analysis:

- `render` uses `return` to handle non-string objects immediately.
- `onlyNonBlankStrings` uses `continue` to skip individual elements of the wrong type or blank strings, then collects the result into an unmodifiable list.
- `requireInteger` uses `throw` when the input type requirement is violated.

All three use pattern variables without explicit casting.

## 16. Self-Practice Exercises

### Exercise 1 — complete the guard clause

Given the code:

```java
static String normalize(Object raw) {
    if (!(raw instanceof String text)) {
        // Fill in the appropriate exit statement.
    }

    return text.strip();
}
```

Modify it so the method returns `"N/A"` when `raw` is not a `String`; when it matches `String`, return the string with `strip()` applied.

### Exercise 2 — choose the logical operator

Write the method:

```java
static boolean isValidUsername(Object raw) {
    // True only when raw is a String and not blank.
}
```

Use `instanceof String username` and `&&` to write a single `return` expression. Then write a version using negation and `||` to detect the **invalid** case.

### Exercise 3 — fix the variable-scope bug

Given the broken code:

```java
static void describe(Object value) {
    if (!(value instanceof Number number)) {
        System.out.println("Unsupported");
    }

    System.out.println(number.doubleValue());
}
```

Fix it in two ways: (1) add a `return` statement in the wrong-type branch; (2) place the code using `number` inside an `else` branch.

### Exercise 4 — distinguish `continue` from `break`

Given the list:

```java
List<Object> values = List.of("A", 10, "B", "C");
```

Write two loops with the same check:

```java
if (!(value instanceof String text)) {
    // continue or break
}
```

One version uses `continue`, the other uses `break`. Predict what values will be printed and explain why the two results differ.

### Exercise 5 — `null` check

Write a method returning `false` if the input is `null`, not a `String`, or is a blank string; otherwise return `true`. Use a single `return` expression with `instanceof String text` without causing a `NullPointerException`.

## 17. Quick Reference

| Goal | Java 17 pattern |
| --- | --- |
| Handle when the type matches | `if (obj instanceof Type value) { use(value); }` |
| Return early when type is wrong | `if (!(obj instanceof Type value)) return fallback;` |
| Throw an exception when type is wrong | `if (!(obj instanceof Type value)) throw new IllegalArgumentException(...);` |
| Skip iteration when type is wrong | `if (!(obj instanceof Type value)) continue;` |
| Stop loop when type is wrong | `if (!(obj instanceof Type value)) break;` |
| Check right type **and** sub-condition | `obj instanceof Type value && valid(value)` |
| Reject wrong type **or** invalid data | `!(obj instanceof Type value) || invalid(value)` |
| Use pattern variable after `if` | Ensure every non-matching branch exits the execution flow reaching the point of use. |

**Core principle:** In Java 17, a pattern variable's scope depends on **control flow**. When a negated condition `!(obj instanceof Type value)` leads to `return`, `throw`, `continue`, or `break` in the appropriate context, the continuing code can use `value` because the non-matching path has been eliminated. Understanding this rule helps you write concise, type-safe, and easy-to-follow guard clauses.
