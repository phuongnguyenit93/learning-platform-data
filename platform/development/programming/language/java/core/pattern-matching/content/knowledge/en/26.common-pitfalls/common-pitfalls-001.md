# Using a Pattern Variable Outside Its Flow Scope

## 1. When Does This Error Occur?

In Java, a **pattern variable** is a variable declared by a pattern. For example, in the expression `value instanceof String text`, the name `text` only has meaning when the `String` type check succeeds. Java uses control-flow analysis (*flow scoping*) to determine **the points in a program where the compiler can guarantee that a pattern variable has been bound**.

A common mistake when refactoring legacy code is introducing `String text` into `instanceof`, and then trying to use `text` anywhere in the method:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}

// DOES NOT COMPILE: value might not be a String,
// so text is not bound on all paths.
// System.out.println(text.length());
```

The call `text.length()` is commented out because **this is an intentionally invalid example**. Even when the sample data is actually `"Java"`, the compiler still checks all possible paths based on the static type `Object`, rather than letting the programmer infer on their own that `value` always matches.

Do not confuse **flow scope** with the scope of ordinary local variables: a pattern variable does not depend solely on `{}` braces; it also depends on whether the pattern has definitely matched **at the point of use**. The goal of this lesson is to identify invalid locations, understand why they fail, and fix them without unintended behavior changes.

## 2. Core Rule: A Variable Exists Only Where the Pattern Definitely Matches

Consider the expression:

```java
value instanceof String text
```

It performs two tasks:

1. Checks whether the value of `value` matches the type pattern `String`.
2. **If it succeeds**, binds the variable `text` with static type `String` to the exact value that was checked.

When `value == null` or is a non-`String` object, the pattern does not match and there is no valid `text` variable to use on that branch. Having the compiler reject the variable name outside its scope helps prevent "using data that has not been type-checked" bugs.

With a simple `if`:

```java
if (value instanceof String text) {
    // Valid: in the branch where the pattern matched.
    System.out.println(text.length());
} else {
    // INVALID if uncommented:
    // System.out.println(text.length());
}
```

The `else` branch executes when the `instanceof` condition is false, so `text` is not bound here.

**Key takeaway:** "A variable is written in an `if` expression" does not mean it is usable in both branches or below the entire `if`. Flow scoping describes what the compiler can prove, not a programmer's assumption about the data that will run.

## 3. With &&: Using the Variable on the Right-Hand Side When the Left Pattern Matches

Java evaluates the `&&` operator using **short-circuiting**. The right-hand side is only evaluated if the left-hand side is `true`. Therefore, this is valid:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

Execution flow:

- If `value` is not a `String` or is `null`, `instanceof` is `false` and `text.isBlank()` does not run.
- If `value` is a `String`, `text` is bound before Java evaluates the right-hand side of `&&`.
- If `text` is not blank according to `isBlank()`, the `if` body runs and can use `text`.

You can chain additional dependent conditions:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 4) {
    System.out.println("Hợp lệ: " + text);
}
```

The condition reads in order: **match type → check content → check length → process**.

**Do not arbitrarily replace `&&` with `&`.** For boolean operands, `&` evaluates both sides without the short-circuiting of `&&`. When later operands are only valid if the preceding pattern matched, `&&` is what properly expresses this dependency.

## 4. With ||: Why Can't a Pattern Variable Usually Be Used on the Right-Hand Side?

The `||` operator also short-circuits, but its right-hand side is evaluated when **the left-hand side is false**. Therefore, the following example is invalid:

```java
// DOES NOT COMPILE: text might not be bound yet.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

If the left-hand side `value instanceof String text` is false, `text` does not exist on the path that needs to evaluate `text.isBlank()`. The compiler does not allow that usage.

Another variant that is easy to fall into:

```java
boolean fallback = true;

// DOES NOT COMPILE if text is used in the body:
// if (value instanceof String text || fallback) {
//     System.out.println(text.toUpperCase());
// }
```

The entire `if` condition can be true **simply because `fallback` is true**, even when `value` is not a `String`. Consequently, inside the `if` body there is also no guarantee that `text` has been bound.

How to fix it depends on your intent:

- If the processing **requires** a `String`, use `&&` to check dependent conditions after the pattern.
- If an independent alternative condition is allowed, split it into two branches with clear purposes; only use `text` in the branch where it matched.
- If the result is just a boolean and the pattern variable is not needed in another branch, you can use `instanceof String` without binding a variable.

An example fix that keeps the two cases distinct:

```java
if (value instanceof String text) {
    System.out.println("Chuỗi: " + text);
} else if (fallback) {
    System.out.println("Đường dự phòng");
}
```

Here, each path has its own responsibility and does not try to use `text` when `value` does not match.

## 5. Negating a Pattern and Guard Clauses: Valid When the Failure Branch Exits Early

A particularly useful idiom in real-world code is **checking for a non-match and exiting the method**, for example:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

On the last line, `text` is valid even though it is not inside the `if` braces. Reason:

1. `!(value instanceof String text)` is true when the pattern **does not match**.
2. The non-matching case terminates immediately with `return 0`.
3. Every path that can reach `return text.length()` has already passed the `instanceof String text` test successfully.

This is an effect of flow analysis, commonly called a **guard clause**. You can use `throw` instead of `return` when an invalid input type is a contract violation:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text;
}
```

However, **negating `instanceof` does not automatically extend the scope**. The following example is still invalid:

```java
// DOES NOT COMPILE if text is used after if:
// if (!(value instanceof String text)) {
//     System.out.println("Sai kiểu");
// }
// System.out.println(text.length());
```

The non-matching branch only prints a message and **still continues**, so at the subsequent statement the compiler cannot guarantee that `text` exists. To use the variable after `if`, the failure branch must actually terminate the relevant path, or you must move the variable usage into the matching branch.

### Note on Combining the Negation Operator

The expression:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text);
```

is valid with respect to flow scope if placed in an appropriate `void` method. However, **do not assume** that all combinations of `!`, `&&`, and `||` yield the same scope: analyze which conditions cause Java to reach each operand or branch, and verify that all paths reaching the variable's usage guarantee the pattern has matched.

## 6. Using Patterns in the ?: Operator and Boolean Assignments

### Conditional (Ternary) Operator

A pattern can bind a variable for use in the branch selected when the condition is true:

```java
String label = value instanceof String text
        ? "Độ dài: " + text.length()
        : "Không phải chuỗi";
```

If `value` is a `String`, the expression in the branch after `?` validly uses `text`. If it does not match, the branch after `:` is selected and cannot assume `text` exists.

Invalid example:

```java
// DOES NOT COMPILE:
// String label = value instanceof String text
//         ? "Là String"
//         : "Không phải String: " + text.length();
```

The `false` branch has no guarantee about the pattern variable.

### Storing Only the Boolean Result Does Not Carry the Variable Over

```java
boolean isString = value instanceof String text;

// DOES NOT COMPILE: text does not automatically become
// a local variable usable after the boolean assignment.
// System.out.println(text.length());
```

`isString` is an ordinary boolean variable. Even though it receives the result of `instanceof`, reading `isString` later does not establish flow scope for `text`. If you genuinely need the checked object, perform the check and processing within an appropriate control structure or use a guard clause as shown above.

## 7. In switch: A Variable Belongs Only to the Matched Case

Since **Java 21**, pattern matching for `switch` together with record patterns allows selecting branches and extracting data inside an expression:

```java
return switch (value) {
    case String text when !text.isBlank() ->
            "Chuỗi: " + text.toUpperCase();
    case String text ->
            "Chuỗi trống";
    case Integer number ->
            "Số: " + number;
    case null ->
            "Thiếu dữ liệu";
    default ->
            "Loại khác";
};
```

This is an illustrative snippet inside a method returning `String`, with `value` already declared. Important rules:

- The variable `text` in `case String text when ...` is valid in the **`when` guard** and the body of that specific case.
- The next `case String text` branch has a **separate** pattern variable, even though it shares the same name.
- The variable `number` exists only in the `Integer` case.
- You cannot use `text` from the `String` case inside the `Integer` case or after the entire `switch`.
- The unguarded `case String text` branch must be placed **after** the guarded, more specific branch; placing it before can cause the later case to be *dominated* and produce a compile error.
- `case null` handles a `null` selector, while `default` handles other types.

If a case needs multiple operations before producing the result of a `switch expression`, you can use a block and `yield`; the pattern variable still remains within the valid scope of that case:

```java
return switch (value) {
    case String text -> {
        String result = text.strip().toUpperCase();
        yield "Chuỗi: " + result;
    }
    case null -> "Thiếu dữ liệu";
    default -> "Loại khác";
};
```

Because scope depends on the case structure, in new code you should prefer **switch rules using `->`** so variable boundaries are easy to read, rather than mixing multiple branches with *fall-through*.

## 8. Nested Record Patterns: Scope of Inner Variables

Consider two records:

```java
record Note(String message) {}
record Envelope(String id, Note note) {}
```

You can match and deconstruct them in a nested way:

```java
if (value instanceof Envelope(
        String id, Note(String message))
        && !message.isBlank()) {
    System.out.println(id + ": " + message);
}
```

With **JDK 21**, the compiler matches the components of `Envelope` and `Note`, then allows using `id` and `message` in places where the pattern has matched. Both variables follow flow scoping rules; extracting them from a record does not make them exist everywhere.

One case to watch out for is when a nested component is `null`. If `note` of `Envelope` is `null`, the pattern `Note(String message)` does not match; therefore **the entire nested pattern** fails, and the condition `!message.isBlank()` is not evaluated.

Similarly, if `note` exists but `message` is `null`, the pattern `String message` does not match. In this case, `message.isBlank()` is not called either. However, if you replace it with `var message` and the component type can hold `null`, you must check for null yourself before calling methods on the component; do not assume every record deconstruction rules out null.

When classifying multiple cases:

```java
return switch (value) {
    case Envelope(String id, Note(String message))
            when !message.isBlank() -> id + ": " + message;
    case Envelope envelope -> "Thiếu thông tin";
    case null -> "Không có phong bì";
    default -> "Không phải phong bì";
};
```

The general `Envelope envelope` branch placed afterward handles objects whose inner structure does not match or whose guard fails. This is an illustrative example inside a method returning `String`.

## 9. Complete Java 21 Program

Create the file **`PatternFlowScopeDemo.java`**. The program uses only valid syntax; the non-compiling patterns from earlier sections have been commented out separately.

```java
import java.util.Locale;

public class PatternFlowScopeDemo {
    record Note(String message) {}
    record Envelope(String id, Note note) {}

    static String inspect(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi: " + text.strip().toUpperCase(Locale.ROOT);
        }
        return "Không có chuỗi hợp lệ";
    }

    static String required(Object value) {
        if (!(value instanceof String text)) {
            return "Sai kiểu";
        }
        return "Dài: " + text.length();
    }

    static String classify(Object value) {
        return switch (value) {
            case String text when !text.isBlank() ->
                    "Có chữ: " + text.toUpperCase(Locale.ROOT);
            case String ignored ->
                    "Chuỗi trống";
            case Integer number when number > 0 ->
                    "Số dương: " + number;
            case Integer number ->
                    "Số không dương: " + number;
            case null ->
                    "Thiếu dữ liệu";
            default ->
                    "Kiểu khác";
        };
    }

    static String inspectEnvelope(Object value) {
        return switch (value) {
            case Envelope(String id, Note(String message))
                    when !message.isBlank() ->
                    id + ": " + message;
            case Envelope envelope ->
                    "Phong bì thiếu thông tin";
            case null ->
                    "Không có phong bì";
            default ->
                    "Không phải phong bì";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(" Java "));
        System.out.println(inspect(12));
        System.out.println(required("abc"));
        System.out.println(required(null));

        System.out.println(classify("hello"));
        System.out.println(classify(" "));
        System.out.println(classify(3));
        System.out.println(classify(-2));
        System.out.println(classify(null));
        System.out.println(classify(3.5));

        System.out.println(inspectEnvelope(
                new Envelope("E1", new Note("OK"))));
        System.out.println(inspectEnvelope(
                new Envelope("E2", null)));
        System.out.println(inspectEnvelope(
                new Envelope("E3", new Note(null))));
        System.out.println(inspectEnvelope(null));
        System.out.println(inspectEnvelope("khác"));
    }
}
```

Compile and run with **JDK 21 or later**; no preview flags needed:

```bash
javac -encoding UTF-8 PatternFlowScopeDemo.java
java PatternFlowScopeDemo
```

Standard output:

```text
Chuỗi: JAVA
Không có chuỗi hợp lệ
Dài: 3
Sai kiểu
Có chữ: HELLO
Chuỗi trống
Số dương: 3
Số không dương: -2
Thiếu dữ liệu
Kiểu khác
E1: OK
Phong bì thiếu thông tin
Phong bì thiếu thông tin
Không có phong bì
Không phải phong bì
```

Explanation:

1. `inspect(" Java ")` matches `String text` and is not blank; `strip()` removes leading/trailing whitespace and `toUpperCase(Locale.ROOT)` produces `JAVA`.
2. `inspect(12)` does not match `String`, so the right-hand side of `&&` and the `if` body do not run; it returns `Không có chuỗi hợp lệ`.
3. `required("abc")` passes the negated guard and validly uses `text.length()` after the `if`. `required(null)` exits early with `Sai kiểu`.
4. `classify("hello")` matches the `String` case with the `!text.isBlank()` guard; `classify(" ")` fails the guard and selects the unguarded `String` case.
5. The two integers `3` and `-2` enter separate `Integer` cases, distinguished by `number > 0`; `null` enters `case null`; the floating-point number `3.5` is another type and enters `default`.
6. `Envelope("E1", Note("OK"))` matches the nested pattern and the guard is true, so it returns `E1: OK`.
7. `Envelope("E2", null)` does not match `Note(...)`. `Envelope("E3", Note(null))` does not match `String message`. Both are handled by the general `Envelope envelope` case.
8. `inspectEnvelope(null)` returns `Không có phong bì` and the string `"khác"` enters `default`.

Throughout the entire program, there is no place where a pattern variable is used in a branch where the compiler cannot prove the pattern has matched. That is why concise idioms remain scope-safe.

## 10. Valid vs. Invalid Comparison Table

| Situation | Conceptual Example | Valid? | Reason |
| --- | --- | --- | --- |
| Variable in the matching `if` branch | `if (o instanceof String s) { use(s); }` | Yes | The branch runs when the pattern is true. |
| Variable in `else` of a positive test | `if (o instanceof String s) ... else use(s);` | No | The `else` branch runs when the pattern is false. |
| Variable on the right-hand side of `&&` | `o instanceof String s && !s.isBlank()` | Yes | `&&` evaluates the right-hand side only when the pattern is true. |
| Variable on the right-hand side of `||` | `o instanceof String s || s.isBlank()` | No | The right-hand side is evaluated only when the pattern is false. |
| Variable after a negated test with `return` | `if (!(o instanceof String s)) return; use(s);` | Yes, in a suitable method | The non-matching branch has terminated. |
| Variable after a negated test without exit | `if (!(o instanceof String s)) log(); use(s);` | No | The non-matching path still reaches `use(s)`. |
| Variable in the true branch of `?:` | `o instanceof String s ? s.length() : 0` | Yes | The expression after `?` runs when the pattern is true. |
| Variable in the false branch of `?:` | `o instanceof String s ? 1 : s.length()` | No | The expression after `:` does not guarantee the pattern matched. |
| Variable in `when` | `case String s when s.length() > 0 -> ...` | Yes | The guard is evaluated only when the case pattern has matched. |
| Pattern variable across another case | `case String s -> ...; case Integer i -> use(s);` | No | Each case has its own scope. |

In this table, `use(...)` and `log()` are **illustrative function names** for discussing scope, not built-in Java APIs. Expressions marked "No" are used to explain errors, not as runnable code.

## 11. Related Pitfalls During Refactoring

### 11.1. Moving Statements Out of the Branch to "Reduce Nesting"

Before:

```java
if (value instanceof String text) {
    System.out.println(text);
}
```

After moving the statement out:

```java
// INVALID: cannot move the processing outside the if in this way.
// if (value instanceof String text) {
//     // ...
// }
// System.out.println(text);
```

**Fix:** Keep the processing inside the matching branch or use a negated guard with an early return. When switching to a guard clause, make sure to preserve the exact behavior of the non-matching branch.

### 11.2. Assuming a Boolean Flag Preserves the Bound Variable

```java
boolean accepted = value instanceof String text;

// INVALID: accepted does not open a flow scope for text.
// if (accepted) {
//     System.out.println(text);
// }
```

**Fix:** Use the pattern condition directly in the control structure that needs the variable; if you want to avoid repeating the check, organize the logic into a method that accepts `String` after the pattern has matched.

### 11.3. Confusing Flow Scope with Component Nullability

`value instanceof Envelope envelope` proves `envelope` is non-null and has type `Envelope`, but it does not prove `envelope.note()` is non-null. When accessing reference components, consider appropriate null checks or nested patterns. Do not let a type pattern test give the impression that all inner data has been validated.

### 11.4. Naming Conflicts with Existing Variables

If a local variable `text` already exists in a scope overlapping with the pattern declaration, adding `instanceof String text` can cause a duplicate variable name error or a scope error. Choose a different name for the pattern variable, or intentionally refactor the scope of the old variable. Do not work around it by removing the type check.

### 11.5. Confusing Compile-Time Errors with Runtime Errors

Using a pattern variable where it is not bound is an error **caught by the compiler**; the program never reaches execution to throw a `NullPointerException` from that invalid usage itself. However, a `null` component bound with `var` whose methods are called without checking can throw a `NullPointerException` at runtime; that is a separate issue.

## 12. Quick Fix Checklist

When you see an error about a pattern variable not existing or not being in a valid scope, check:

1. In **which pattern** is the variable declared, and can that pattern fail to match?
2. Is the usage site in the true `if` branch, `else`, or after the entire `if`?
3. If `&&` or `||` is present, which side is evaluated when the pattern is true or false?
4. With `!`, does the failure branch have a `return`, `throw`, or appropriate way to terminate the path?
5. In `switch`, is the variable being used within the exact `case`/`when` that bound it?
6. If the value is needed in multiple places, should you move the logic into the branch, use a guard clause, or redesign the method?
7. Are you confusing pattern variable scope with a component being guaranteed non-null?
8. After fixing, have you compiled with the right Java version and tested matching, non-matching, and `null` inputs?

## 13. Self-Check

Given:

```java
Object input = "hello";
```

**Question A:** Why is the following example invalid?

```java
// DOES NOT COMPILE:
// if (input instanceof String s) {
//     System.out.println(s.length());
// }
// System.out.println(s.toUpperCase());
```

**Answer:** The line outside `if` can run when `input` is not a `String`. The compiler cannot guarantee that `s` is bound. Move the processing line into the true branch or use an early-return guard.

**Question B:** Is the following valid?

```java
if (input instanceof String s && s.length() >= 3) {
    System.out.println(s.toUpperCase());
}
```

**Answer:** Valid. `&&` guarantees that `s.length()` is called only after the `String s` pattern matches. With the sample data, the program prints `HELLO`.

**Question C:** When handling `case Envelope(String id, Note(String message)) when !message.isBlank()`, where is `message` valid?

**Answer:** In the `when` guard and the body of that exact case. If another case handles an `Envelope` missing a component, that case needs its own pattern variable (for example, `case Envelope envelope`) and cannot borrow `message` from the previous case.

**Remember:** A pattern variable may only be used where **the compiler proves the pattern has definitely matched**. Do not look only at where it is declared: read the condition flow and exit paths. Use `&&` in the right places, avoid false assumptions with `||`, leverage guard clauses with `return`/`throw`, and keep variables within their own `switch` case. Understanding flow scoping helps avoid compile errors when refactoring from `instanceof` and manual casts to pattern matching.
