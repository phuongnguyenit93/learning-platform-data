# Combining `instanceof` with `&&` and Short-Circuit Evaluation Rules in Java 17

When checking whether an object belongs to a specific type, Java 17 allows **declaring a variable directly inside the `instanceof` expression**. Combining this syntax with the `&&` operator lets you check the type, read properties, and check additional conditions **within the same safe expression**.

Typical example:

```java
Object value = "Java 17";

if (value instanceof String text && text.length() >= 5) {
    System.out.println(text.toUpperCase());
}
```

The key point lies in the order of evaluation:

1. Java evaluates `value instanceof String text`.
2. Only when that check succeeds does the pattern variable `text` hold a `String` value and the right-hand side `text.length() >= 5` get evaluated.
3. The `if` block runs only when **both conditions** are `true`.

This mechanism is called **short-circuit evaluation**, and it connects directly to **pattern variable scope** (*flow scoping*).

> In Java 17, *pattern matching for `instanceof`* is already a standard feature (finalized in Java 16, JEP 394). The examples in this lesson do not require enabling preview features.

## 1. Review: Traditional `instanceof` and Type Patterns

Before type patterns, a familiar style was:

```java
static void printLength(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

We performed two actions: checking the type with `instanceof` and casting with `(String) value`.

With a type pattern in Java 17:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Syntax:

```text
expression instanceof Type pattern_variable_name
                           └───────────────────┘
                          only usable when matched
```

In the example `value instanceof String text`:

- `value` is the expression to check, typically having a static type of `Object` or another supertype/interface.
- `String` is the **type to match against**.
- `text` is the **pattern variable**, having static type `String` if the check matches.
- There is no need to repeat the `(String) value` cast in the branch where the check succeeded.

If `value == null`, the expression `value instanceof String text` evaluates to `false`; Java does not create a valid `String` for `text` along that path.

### What a type pattern does not do

A type pattern **does not alter the original object** and does not turn every branch into a `String`. Variable `text` can only be used at positions where the compiler proves that pattern matching occurred.

```java
Object value = 123;

if (value instanceof String text) {
    System.out.println(text.length()); // Does not run
}
```

An `Integer` object does not match `String`. The program does not throw `ClassCastException` simply because the `instanceof` check failed.

## 2. How Does `&&` Short-Circuit?

The **conditional-and** operator `&&` takes operands of type `boolean` (or `Boolean` that can be unboxed) and evaluates **from left to right**.

For the expression:

```java
A && B
```

The execution rules are:

- Evaluate `A` first.
- If `A` is `false`, **skip `B` completely** and return `false`.
- If `A` is `true`, proceed to evaluate `B` and use `B`'s result as the overall result.

Truth table:

| `A` | Is `B` evaluated? | If `B` is `false` | If `B` is `true` |
|---|---|---|---|
| `false` | No | Result `false` | Result `false` |
| `true` | Yes | Result `false` | Result `true` |

Flow diagram:

```text
           Evaluate A
               |
         +-----+-----+
         |           |
      A=false      A=true
         |           |
   Skip B       Evaluate B
         |           |
     false        Result of B
```

This is very useful when **the right-hand side is only safe or meaningful after the left-hand condition is satisfied**.

A common pre-pattern example:

```java
String name = null;

if (name != null && !name.isBlank()) {
    System.out.println(name);
}
```

Because `name != null` is `false`, Java **does not call** `name.isBlank()`, avoiding a `NullPointerException` on that call.

With type patterns, the `instanceof` condition does even more: it checks the type and provides a properly typed variable for the rest of the expression.

## 3. Why Can `instanceof ... && ...` Use the Pattern Variable?

Here is the key example:

```java
Object input = "Hello";

if (input instanceof String text && text.length() > 3) {
    System.out.println("String is long enough: " + text);
}
```

We can read this in plain words as:

> If `input` is a `String`, call it `text`; **and if** the length of `text` is greater than 3, execute the `if` body.

The compiler allows using `text` on the right-hand side because `&&` guarantees that side only runs when the left-hand side is `true`. When `input instanceof String text` is `true`, the pattern variable `text` has **matched the pattern** and holds a value.

This rule belongs to **flow scoping**:

- A pattern variable does not merely have a fixed scope determined by curly braces like a regular local variable.
- Its scope depends on **the control-flow paths where the pattern is definitely matched**.
- On the right-hand side of `&&`, if the left-hand side is an expression that brings the pattern variable into scope **when true**, the variable is allowed to be used.

Four cases of the example:

| Value of `input` | `input instanceof String text` | Does `text.length() > 3` run? | Does `if` body run? |
|---|---|---|---|
| `null` | `false` | No | No |
| `100` (Integer) | `false` | No | No |
| `"Hi"` | `true` | Yes; returns `false` | No |
| `"Hello"` | `true` | Yes; returns `true` | Yes |

At the line calling `text.length()`, Java already knows `text` is a `String`. Therefore, no cast is needed and there is no risk of calling `length()` on a `null` value from this type-pattern match.

## 4. Reading the Evaluation Order with Multiple `&&` Operators

The `&&` operator can chain multiple conditions:

```java
Object value = "Java 17";

if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 5
        && text.startsWith("Java")) {
    System.out.println("Valid: " + text);
}
```

Java evaluates sequentially:

1. `value instanceof String text`. If it does not match, stop.
2. `!text.isBlank()`. If the string contains only whitespace, stop.
3. `text.length() >= 5`. If too short, stop.
4. `text.startsWith("Java")`. If it does not have the right prefix, the overall result is `false`.
5. When all are `true`, execute the `if` body.

Viewed as a guard chain:

```text
Is it a String?
    |
    +-- no -------------------> false
    |
    +-- yes --> Non-blank?
                   |
                   +-- no ----> false
                   |
                   +-- yes --> Long enough?
                                 |
                                 +-- no ----> false
                                 |
                                 +-- yes --> Right prefix?
                                             |
                                             +-- no ----> false
                                             |
                                             +-- yes --> enter if
```

The `&&` operator is left-associative; even with multiple `&&` operators, conditions are evaluated in the exact order written.

**Good habit:** check the **type or prerequisite condition** first, then place operations that depend on that condition on the right. Cheap, simple conditions capable of eliminating false cases are typically placed early to avoid costly work later.

## 5. Why Won't Reversing the Order Compile?

This is an error:

```java
Object input = "Hello";

// ERROR: text has not been declared at the start of the expression.
// if (text.length() > 3 && input instanceof String text) {
//     System.out.println(text);
// }
```

`text` is only introduced on the **later side**; it cannot be used on the **earlier side** of `&&`. Java does not "look ahead" to the right-hand side to supply variables to the left-hand side.

Correct way:

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

A similar error is calling a `String`-specific method on an `Object` variable before checking the type:

```java
Object input = "Hello";

// COMPILE ERROR: Object does not have length().
// if (input.length() > 3 && input instanceof String text) {}
```

Even though the actual object is a string, **the static type of `input` is still `Object`**. A type pattern provides a new variable `text` with static type `String` at valid positions.

## 6. Where Can the Pattern Variable Be Used After the Condition?

Consider:

```java
Object value = "Java 17";

if (value instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // Valid
} else {
    System.out.println("Not a sufficiently long string");
    // System.out.println(text); // ERROR
}

// System.out.println(text);     // ERROR in this case
```

In the `if` branch body, the entire conditional expression was `true`, so `text` is definitely assigned.

In the `else` branch, the condition may be false because:

- `value` is not a `String`; in this case **there is no** matched pattern variable.
- `value` is a `String` but `text.length() >= 4` is false.

Thus Java does not allow arbitrarily using `text` in `else`. After the entire `if`, it likewise cannot guarantee that matching succeeded.

### Not "a variable only exists inside the braces of `if`"

A pattern variable's scope is governed by **control flow**. There are cases where using it after `if` is allowed, if the non-matching branch **definitely terminates execution**:

```java
static int lengthOfString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }

    // Reaches here only because instanceof matched.
    return text.length();
}
```

In this example, `text` is valid at the `return` line. Java proved that if it did not match, the method throws an exception and does not continue to that line.

This technique is called a **guard clause** and is useful when handling invalid data early. The rule is not based on "the variable lives until the end of the function", but on **every path capable of reaching that statement having matched the pattern**.

## 7. Using `&&` with Conditions That Throw Exceptions or Perform Expensive Work

Short-circuit evaluation is useful because the right-hand side might call methods and trigger side effects.

```java
static boolean isAllowed(String text) {
    System.out.println("Checking content...");
    return text.startsWith("APP-");
}

static void process(Object value) {
    if (value instanceof String text && isAllowed(text)) {
        System.out.println("Accepted");
    }
}
```

Sample calls:

```java
process(123);
process("APP-2026");
```

Only the call with the string prints:

```text
Checking content...
Accepted
```

The call `process(123)` does not run `isAllowed`. This means:

- Less unnecessary work.
- No access to the pattern variable when the type check fails.
- Avoiding exceptions that could arise from calling methods on an unsuitable value type.

However, **`&&` does not "swallow" exceptions**: if the left-hand side or an evaluated right-hand side throws an exception, evaluation terminates abnormally and the exception propagates outward. It only **skips subsequent operands** upon encountering `false`.

Additionally, if the left-hand side has type `Boolean` and value `null`, unboxing to evaluate the condition can still throw `NullPointerException`. In our `instanceof` examples here, the left-hand side produces a primitive `boolean`, so there is no nullable unboxing issue in the type check itself.

## 8. Distinguishing `&&` from `&` in Boolean Expressions

When both operands are booleans, `&&` and `&` can yield the same **final value** while differing in **how they evaluate**:

| Operator | Usable with booleans? | When left-hand side is `false` | Suitable for guarding a pattern-dependent right-hand side? |
|---|---|---|---|
| `&&` | Yes | Skips the right-hand side | **Yes** |
| `&` | Yes | Still evaluates the right-hand side | **No** |

A non-pattern example to observe the difference:

```java
static boolean trace() {
    System.out.println("Right-hand side ran");
    return true;
}

static void demo() {
    boolean a = false && trace();
    boolean b = false & trace();
}
```

When running `demo()`, only the expression with `&` calls `trace()` and prints the message.

### Specifically with pattern variables

You cannot mechanically replace `&&` with `&`:

```java
Object value = "Hello";

// VALID
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}

// ERROR: text is not guaranteed to be in scope on the right-hand side of &.
// if (value instanceof String text & text.length() > 3) {}
```

**Why?** When `&` takes boolean operands, the right-hand side is still evaluated even when the left-hand side is `false`. The pattern variable might not have matched then, so Java does not grant permission to use it on the right-hand side as `&&` does.

To see the consequence of lacking short-circuiting in traditional casting code:

```java
Object value = 42;

// true/false on the left does not block the cast afterward.
// boolean wrong = value instanceof String & ((String) value).length() > 0;
// At runtime: ClassCastException

boolean safe = value instanceof String
        && ((String) value).length() > 0; // false, no cast
```

With Java 17, the more concise and readable version is:

```java
boolean safe = value instanceof String text && text.length() > 0;
```

**Note:** `&` is also a bitwise operator for integer types; here we are only comparing `&` and `&&` when operating on boolean operands.

## 9. Why Can't `||` Replace `&&`?

`||` is **conditional-or**: the right-hand side is evaluated only if the left-hand side is `false`.

When writing:

```java
Object value = "Hello";

// COMPILE ERROR:
// if (value instanceof String text || text.length() > 3) {
//     System.out.println(text);
// }
```

the right-hand side `text.length() > 3` can only run when `value instanceof String text` **fails**. At that moment `text` is not matched, so it cannot be used.

Comparison:

| Left-hand expression | Operator | When right-hand side runs | Is `text` guaranteed matched? |
|---|---|---|---|
| `value instanceof String text` | `&&` | When `instanceof` is true | **Yes** |
| `value instanceof String text` | `||` | When `instanceof` is false | **No** |
| `!(value instanceof String text)` | `||` | When negation is false, i.e., `instanceof` is true | **Yes** |

The last row is an interesting rule in Java 17: with **negation `!`**, the logical direction flips.

### Valid case with `!` and `||`

Example of a condition to **reject** non-string or blank input:

```java
static String requireNonBlankString(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected nonblank String");
    }

    return text;
}
```

Step-by-step explanation:

1. If `value` is not a string, `!(value instanceof String text)` is `true`; `||` short-circuits and **does not call** `text.isBlank()`.
2. If `value` is a string, the negated expression is `false`; `text` has matched, so the right-hand side `text.isBlank()` is allowed to use it.
3. If the string is empty or whitespace-only, an exception is thrown.
4. If the check passes, the entire `if` is `false` and execution continues with `text` matched.

This condition carries the same validation meaning as accepting in the form:

```java
if (value instanceof String text && !text.isBlank()) {
    // Valid input
}
```

However, where `text` can be used must be analyzed by the specific **control flow**; the two expressions do not have identical variable scope at every position.

### Incorrect negation case with `&&`

```java
// ERROR: right-hand side runs when instanceof did NOT match.
// if (!(value instanceof String text) && text.isBlank()) {}
```

When adding or removing `!`, you must re-evaluate the meaning of `&&`/`||`. Simply swapping one operator is not enough.

## 10. Parentheses and Operator Precedence

Java has operator precedence rules. In this lesson, the order to remember is:

1. Parentheses `(...)` determine explicit grouping for evaluation.
2. The `instanceof` type comparison has higher precedence than `&&`.
3. `&&` has higher precedence than `||`.

Example:

```java
if (value instanceof String text && text.length() > 3) {
    // ...
}
```

is interpreted as:

```java
if ((value instanceof String text) && (text.length() > 3)) {
    // ...
}
```

You can use parentheses to make intent explicit when needed.

If mixing in `||` or negation, proactively write parentheses so readers can see **which branch is the guarding condition**:

```java
static boolean hasValidName(Object value) {
    return value instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
```

And when there is an independent alternative condition, you can structure it clearly into separate statements:

```java
static boolean accepted(Object value, boolean allowMissing) {
    if (allowMissing && value == null) {
        return true;
    }

    return value instanceof String name && !name.isBlank();
}
```

This avoids creating a complex expression that forces readers to trace pattern variable scope backward through multiple `&&`, `||`, and `!` operators.

## 11. Combining Multiple Patterns and Multiple Conditions

An `&&` expression can contain **multiple distinct type checks**, each introducing its own pattern variable.

```java
static boolean sameText(Object left, Object right) {
    return left instanceof String first
            && right instanceof String second
            && !first.isBlank()
            && first.equalsIgnoreCase(second);
}
```

At `first.equalsIgnoreCase(second)`:

- `left instanceof String first` returned `true`.
- `right instanceof String second` returned `true`.
- `!first.isBlank()` returned `true`.

Thus both `first` and `second` are in scope and have static type `String`. Neither `left` nor `right` needs casting.

### Do not declare two pattern variables with the same name in the same expression

```java
// ERROR: two pattern variables with the same name s conflict.
// if (left instanceof String s && right instanceof String s) {}
```

Choose different names:

```java
if (left instanceof String first && right instanceof String second) {
    System.out.println(first + " / " + second);
}
```

Java tracks which branch creates each pattern variable. Reusing the same name can conflict at compile time, even if you expect runtime execution to follow a specific branch.

### Avoid name collisions with existing local variables

```java
String text = "existing";
Object value = "new";

// ERROR: pattern variable text collides with local text already in scope.
// if (value instanceof String text && text.length() > 2) {}
```

Choose a new name for the pattern:

```java
if (value instanceof String matched && matched.length() > 2) {
    System.out.println(matched);
}
```

## 12. Practical Example: Validating Structured Input

Suppose an API accepts `Object` from multiple sources and only accepts request codes formatted as strings starting with `"REQ-"`, at least eight characters long.

```java
static boolean isRequestCode(Object input) {
    return input instanceof String code
            && code.length() >= 8
            && code.startsWith("REQ-");
}
```

Cases:

| `input` | Result | Reason |
|---|---|---|
| `null` | `false` | Does not match `String` |
| `12345` | `false` | Is an integer |
| `"REQ-"` | `false` | Shorter than 8 characters |
| `"DOC-2026"` | `false` | Wrong prefix |
| `"REQ-2026"` | `true` | Right type, length, prefix |

This is where `&&` shines: **check the data type first, check the content second**. No nested `if` blocks and no repeated casts.

### Example with an interface

Type patterns are not limited to `String`. You can check an interface such as `CharSequence`:

```java
static boolean startsWithJava(Object input) {
    return input instanceof CharSequence text
            && text.length() >= 4
            && text.charAt(0) == 'J'
            && text.charAt(1) == 'a'
            && text.charAt(2) == 'v'
            && text.charAt(3) == 'a';
}
```

For a `String` or `StringBuilder` with matching content, the check can succeed because both implement `CharSequence`. When using `text`, the compiler only guarantees **`CharSequence`** methods, such as `length()` or `charAt()`; to call `String`-specific methods like `isBlank()`, you need the corresponding `String` type pattern.

### Example with a numeric type

```java
static boolean positiveNumber(Object input) {
    return input instanceof Number number
            && number.doubleValue() > 0.0;
}
```

`Number` is the superclass of numeric wrappers like `Integer` and `Double`. If the input is not a `Number`, Java does not call `doubleValue()`.

Keep in mind that converting to `double` can lose precision for certain numeric types; the example above is solely to demonstrate patterns and `&&`. When handling currency or large integers, choose comparison types suitable for your business requirements.

## 13. Complete Example Runnable on JDK 17

Create the file `PatternAndDemo.java`:

```java
public class PatternAndDemo {
    static boolean startsWithJava(Object value) {
        return value instanceof String text
                && !text.isBlank()
                && text.length() >= 5
                && text.startsWith("Java");
    }

    static String describe(Object value) {
        if (value instanceof String text && text.length() > 0) {
            return "String(" + text.length() + "): " + text;
        }

        return "Not a non-empty String";
    }

    public static void main(String[] args) {
        Object[] samples = {
                null,
                123,
                "",
                "Hi",
                "Java",
                "Java 17"
        };

        for (Object sample : samples) {
            System.out.println(
                    String.valueOf(sample)
                            + " -> "
                            + startsWithJava(sample)
                            + " | "
                            + describe(sample)
            );
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 PatternAndDemo.java
java PatternAndDemo
```

Expected output:

```text
null -> false | Not a non-empty String
123 -> false | Not a non-empty String
 -> false | Not a non-empty String
Hi -> false | String(2): Hi
Java -> false | String(4): Java
Java 17 -> true | String(7): Java 17
```

Observe the inputs `null` and `123`. Every call such as `text.isBlank()`, `text.length()`, and `text.startsWith(...)` is skipped when the `instanceof` check is false. For `"Hi"`, the type check is true but the length `>= 5` condition is false, so the `startsWith` call at the end of the `&&` chain in `startsWithJava` does not need to run either.

## 14. Pitfalls When Combining Patterns and Short-Circuiting

### Pitfall 1 — Using `||` instead of `&&`

```java
// Wrong: text is not in a valid scope on the right-hand side of ||.
// if (input instanceof String text || text.length() > 3) {}
```

Fix when you want both conditions to be true:

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

### Pitfall 2 — Using `&` instead of `&&`

```java
// Wrong: & evaluates both operands and does not grant flow scope like &&.
// if (input instanceof String text & text.length() > 3) {}
```

Fix by using `&&`.

### Pitfall 3 — Checking properties before checking the type

```java
// Wrong: matched has not been declared yet.
// if (matched.length() > 3 && input instanceof String matched) {}
```

Fix by placing `instanceof String matched` on the left.

### Pitfall 4 — Using a pattern variable outside matched paths

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text); // Correct
}

// Wrong: input is not guaranteed to match the type.
// System.out.println(text);
```

Fix by placing statements needing `text` in the matched branch or using a guard clause that exits early on non-matching paths.

### Pitfall 5 — Believing short-circuiting checks every aspect of data validity

```java
Object input = "  ";

if (input instanceof String text && text.length() > 0) {
    System.out.println("Has content"); // Still runs for whitespace-only strings
}
```

`&&` only governs evaluation order and conditional execution; **it does not itself define which data is considered valid**. If you require non-whitespace characters, use `!text.isBlank()`:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println("Has actual content");
}
```

### Pitfall 6 — Assuming Java 17 supports patterns for all data types

In Java 17, *type patterns* of `instanceof` apply to **appropriate reference types**; you cannot write a pattern for primitive `int` values:

```java
int number = 42;

// Wrong in Java 17.
// if (number instanceof int n) {}
```

If a variable already has type `String`, checking it with `instanceof String text` provides no useful type check either; in Java 17, cases where the expression's static type is a subtype of the pattern type can be rejected at compile time. Patterns are best suited when you need to **check and narrow from a supertype/interface to a specific type**.

## 15. Self-Practice Exercises and Explanations

### Exercise 1 — Which operands are evaluated?

Given:

```java
Object value = 15;

if (value instanceof String text
        && text.length() > 2
        && text.startsWith("A")) {
    System.out.println("OK");
}
```

**Question:** How many checks are actually executed?

**Explanation:** Only `value instanceof String text` is evaluated. The result is `false`, so both `text.length()` and `text.startsWith("A")` are skipped. The `if` block does not run.

### Exercise 2 — Fix the variable-scope bug

Broken snippet:

```java
// if (obj instanceof String text || text.isEmpty()) {
//     System.out.println("Empty");
// }
```

If the requirement is **only print the message when `obj` is an empty `String`**, fix it as:

```java
if (obj instanceof String text && text.isEmpty()) {
    System.out.println("Empty");
}
```

If the requirement is **print a message when `obj` is not a `String` or is an empty `String`**, use:

```java
if (!(obj instanceof String text) || text.isEmpty()) {
    System.out.println("Not a string or empty string");
}
```

Two different business requirements lead to different correct expressions.

### Exercise 3 — Why does the following fail to compile?

```java
Object left = "ABC";
Object right = "XYZ";

// Wrong: two pattern variables with the same name.
// if (left instanceof String s
//         && right instanceof String s
//         && s.length() > 2) {
//     System.out.println(s);
// }
```

**Explanation:** Both type patterns attempt to declare `s` in potentially overlapping scopes. Use distinct names like `first` and `second` to represent the two independent objects.

### Exercise 4 — Choose an appropriate guard clause

Write a method taking `Object` and returning the length of a **non-blank** string, otherwise throwing `IllegalArgumentException`.

Suggestion in Java 17:

```java
static int lengthOfNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected nonblank String");
    }

    return text.length();
}
```

Self-check questions:

1. If `input` is `null`, does Java call `text.isBlank()`?
2. If `input` is `42`, why does `ClassCastException` not occur?
3. If `input` is `"   "`, why does the method throw an exception?
4. Why is `text` valid on the `return` line?

**Answers:** (1) No, `||` stops at the `true` left-hand side. (2) No forced cast is performed; `instanceof` returns `false`. (3) The type pattern matches, but `isBlank()` returns `true`. (4) Every execution path reaching `return` has passed both the type and content checks, because the invalid branch ended with `throw`.

## 16. Takeaways When Reading or Writing `instanceof` with `&&`

The most common formula:

```java
if (obj instanceof SomeType value
        && check1(value)
        && check2(value)) {
    use(value);
}
```

Read it as a guard chain:

- `obj instanceof SomeType value`: check the type and bind pattern variable `value`.
- `&& check1(value)`: runs only when the pattern matched.
- `&& check2(value)`: runs only when all prior conditions are true.
- `if` block: executes when all are true; `value` has valid scope here.

When negating a condition with `!` or replacing `&&` with `||`, **the direction in which the pattern variable is definitely matched also changes**. That is why you need to understand both parts: **short-circuit evaluation at runtime** and **variable scope checking at compile time**.

## Official References for Java 17

- [JLS Java SE 17 — `15.20.2: the `instanceof` operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [JLS Java SE 17 — `15.23: conditional-and operator `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23).
- [JLS Java SE 17 — `15.24: conditional-or operator `||`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.24).
- [JLS Java SE 17 — `6.3.1.1: scope of pattern variables with `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.1).
- [JLS Java SE 17 — `6.3.1.2–6.3.1.3: scope with `||` and `!`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.2).
- [JLS Java SE 17 — `6.3.2: scope in `if` and other statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2).
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
