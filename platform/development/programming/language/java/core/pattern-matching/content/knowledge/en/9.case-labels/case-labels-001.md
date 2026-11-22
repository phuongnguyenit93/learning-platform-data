# `case` Syntax with Type Patterns in Java

**Topic:** Java Core Pattern Matching → Case label  
**Platform:** Java 21 or later for pattern matching in `switch` (JEP 441). The `instanceof Type variable` syntax has been standard since Java 16, but that does not mean `switch` supports type patterns in Java 17.

## 1. What Is a Type Pattern in `case` Used For?

When a variable is declared with a broad type such as `Object`, an interface, or a superclass, its runtime value can belong to many concrete types. Before Java 21, developers often used an `if / else if` chain with `instanceof` to distinguish each type. Pattern matching for `switch` lets you write those classification branches directly using a **type pattern** in a `case` label.

A type pattern has the form **`Type variable`**, such as `String text`, `Integer number`, or `CharSequence chars`. When the selector matches the type, Java binds the checked value to the *pattern variable* and executes the corresponding branch.

Short example on Java 21:

```java
static String kind(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

Key point: `case String text` is simultaneously a **type check condition** and a **pattern variable declaration**. When this branch runs, `text` has static type `String`; no cast is needed. If the object is an `Integer`, the `String` branch does not match and Java evaluates the next matching branch.

## 2. Standard Syntax in Java 21

In a `switch` expression or `switch` statement, a type pattern label typically uses the syntax:

```java
case Type variable -> expression
case Type variable -> { /* statement(s) */ }
case Type variable when condition -> expression
```

Examples of standalone labels (placed inside an appropriate `switch`):

```java
case String text -> text.length();
case Integer number -> number.intValue();
case Number number when number.doubleValue() > 0 -> 1;
```

In this example, `Type` is a reference type allowed in pattern position; `variable` is the variable name that can be used in the `when` condition and the body of the selected branch. **These are separate illustrative snippets**, not three labels combined into a single standalone `switch`, because the result types, branch ordering, and remaining cases need to be designed for a specific method.

There are two common forms for writing the body:

**Arrow rule `->`** (preferred for new examples):

```java
case String text -> "Text:" + text;
case Integer number -> {
    System.out.println("Đã nhận số nguyên");
    yield "Number:" + number;
}
```

With a `switch` **expression**, a block on the right-hand side of `->` must use `yield` to return a value from the block to the `switch` expression (unless the block cannot complete normally). This is not a `return` from the enclosing method.

**Colon `:` in a `switch` statement**:

```java
case String text:
    result = "Text:" + text;
    break;
```

The colon form supports familiar statements; `break` is typically used to terminate a branch in a `switch` statement and avoid falling through (*fall-through*) to subsequent branches. When using pattern variables, scoping and definite assignment rules make fall-through between pattern labels error-prone; using `->` keeps the intent clear.

### 2.1. `Type variable` vs. Constant `case`

`case String text` checks a group of values by **runtime type**; `case "hello"` checks a **specific string constant**. Similarly, `case Integer number` checks an `Integer` object, whereas `case 10` is an integer constant label (which must be valid for the selector type and `switch` label rules).

You cannot write `case String ->` and expect the compiler to invent a variable: a type pattern consists of **both a type and a variable name**. If you want to use `String text`, you must declare the full pattern.

## 3. How Type Patterns Work in a `switch` Expression

Example:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "String dài " + text.length();
        case Number number -> "Number: " + number;
        default -> "Other";
    };
}
```

Evaluation order:

1. `switch` evaluates the selector `value` **once** to select a branch.
2. If `value == null`, the `case null` branch is selected.
3. If it is non-null and a `String`, `case String text` matches; `text` holds that value and has static type `String`.
4. If it is a `Number` such as `Integer` or `Double`, the `case Number number` branch can match.
5. Values not covered by earlier cases go to `default`.

Because this is a `switch` **expression**, every executed branch must produce a `String` value, and all cases must be handled according to the compiler's *exhaustiveness* rules. In this example, `default` covers the types not explicitly listed.

## 4. The `when` Guard: A Condition After the Type Pattern Matches

Since Java 21, you can add a condition using **`when`**:

```java
case String text when text.isBlank() -> "Blank String";
case String text -> "String: " + text;
```

The compiler evaluates `text.isBlank()` **only after** the type pattern `String text` matches. Therefore, inside the guard condition, `text` has type `String` and can call `String` methods. If the guard returns `false`, `switch` continues checking other matching labels; in this example, the second branch handles non-blank strings.

You must place the guarded branch **before** the general `String` branch. If you write:

```java
// DOES NOT COMPILE: the subsequent branch is dominated.
case String text -> "String";
case String text when text.isBlank() -> "Blank";
```

The first `case String text` branch already accepts every non-null string, making the more specific branch after it unreachable. The syntax `case String text && text.isBlank()` appeared in earlier preview stages; in standard Java 21, use `when`.

Guards are well suited for small, clear conditions (length, state, value range). If a condition is complex or has side effects, consider moving the logic into a separate method for easier testing and maintenance.

## 5. Label Ordering and Dominance Rules

Type patterns can overlap according to inheritance/interface relationships. For example, every `Integer` is a `Number`, so a broader `Number` label will shadow an `Integer` label placed after it:

```java
// DOES NOT COMPILE: case Integer is dominated by case Number.
case Number number -> "Number";
case Integer integer -> "Integer";
```

Reverse the order:

```java
case Integer integer -> "Integer";
case Number number -> "Number";
```

The rule for overlapping patterns is: **put specific cases first, then general cases**. Similarly, placing `case CharSequence chars` before `case String text` shadows `String`, because `String` implements `CharSequence`.

A `default` branch does not declare a pattern variable. Placing `default` after the specific classification branches makes the code easier to read.

Guard dominance is governed by language rules: do not assume the compiler can prove arbitrary boolean propositions. Clear ordering and testing with representative inputs help keep code unambiguous.

## 6. `null` Does Not Match Top-Level Type Patterns

**`null` is not an instance of `String`, `Number`, `Object`, or any other reference type.** Therefore, when the selector is `null`, `case String text` is not the label that handles it.

For a `switch` with patterns in Java 21:

```java
return switch (value) {
    case null -> "NULL";
    case String s -> "String";
    default -> "Other";
};
```

If the selector can be `null` and the `switch` has no `case null` (or an equivalent label such as `case null, default`), evaluating a `null` selector normally throws `NullPointerException`. **`default` alone does not handle `null`.**

When you want to combine `null` and other cases into the same branch, Java 21 allows the syntax:

```java
case null, default -> "Unknown";
```

This is a branch-selection rule for `null`, not a new type pattern. A broad pattern such as `case Object object` is still not the default way to catch `null`.

## 7. What Is the Scope of a Pattern Variable?

Given:

```java
switch (value) {
    case String text -> System.out.println(text.length());
    case Integer number -> System.out.println(number + 1);
    default -> System.out.println("Other");
}
```

- `text` is in scope inside the `String` branch, and inside that pattern's `when` guard if present.
- `number` is only in scope where the `Integer number` pattern has matched.
- `text` and `number` do not remain in scope **after** the `switch` or inside the `default` branch.
- Declaring a pattern variable does not change the original declared type of `value` across the method.

This is similar to `instanceof` *flow scoping*: the compiler only allows a variable to be used where it can prove the pattern has matched. Do not cast the selector again once you already have a valid pattern variable.

## 8. Type Patterns and Generics

In `switch (Object input)`, `case java.util.List<?> items` can check that the value is a `List` and provide a variable of type `List<?>`:

```java
static int sizeIfList(Object input) {
    return switch (input) {
        case java.util.List<?> items -> items.size();
        case null, default -> -1;
    };
}
```

The `?` means an unknown element type; `List<?>` is a form that can be properly checked at runtime (*reifiable*). By contrast:

```java
// DOES NOT COMPILE when the selector only has type Object:
// case java.util.List<String> items -> items.size();
```

Because of **type erasure**, the runtime cannot prove that every element of a `List` object is a `String` using only a `List<String>` type pattern. Check individual elements when business logic requires it, or enforce the type contract at the input API boundary.

In Java 21, the type patterns in `case` covered in this lesson apply to **reference types**. Do not copy pattern syntax for `int`, `double`, or `boolean` and assume Java 21 already supports all primitive patterns from newer Java versions or preview proposals.

## 9. Complete Java 21 Example

Create the file **`CaseTypePatternDemo.java`**:

```java
public class CaseTypePatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Blank String";
            case String s -> "String(" + s.length() + "):" + s;
            case Integer n when n >= 0 -> "Nonnegative Integer:" + n;
            case Integer n -> "Negative Integer:" + n;
            case Number n -> "Other Number:" + n;
            default -> "Other:" + value.getClass().getSimpleName();
        };
    }

    static String describeStatement(Object value) {
        String result;
        switch (value) {
            case null:
                result = "NULL";
                break;
            case String text:
                result = "TEXT:" + text;
                break;
            default:
                result = "OTHER";
                break;
        }
        return result;
    }

    public static void main(String[] args) {
        Object[] samples = {null, "   ", "Java", 0, -2, 3.5, true};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
        System.out.println(describeStatement("Hi"));
        System.out.println(describeStatement(null));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 CaseTypePatternDemo.java
java CaseTypePatternDemo
```

Output:

```text
NULL
Blank String
String(4):Java
Nonnegative Integer:0
Negative Integer:-2
Other Number:3.5
Other:Boolean
TEXT:Hi
NULL
```

Step-by-step explanation:

1. `null` matches `case null` and returns `NULL`; it is not routed to `case String s`.
2. The three-space string matches `String s` and the guard `s.isBlank()` returns `true`, so it prints `Blank String`.
3. `"Java"` is not blank, so it reaches the general `String s` type pattern and prints `String(4):Java`.
4. The value `0` is a non-negative `Integer`, matching the branch guarded by `n >= 0`; `-2` enters the remaining `Integer n` branch.
5. `3.5` is boxed to `Double`; it is not an `Integer`, but it is a `Number`, so it prints `Other Number:3.5`.
6. `true` is a `Boolean`, matching none of the earlier branches, so it enters `default` and prints `Other:Boolean`.
7. The `describeStatement` method shows the colon syntax requiring `break` to end each branch; `"Hi"` prints `TEXT:Hi` and `null` prints `NULL`.

The example uses `when`, type patterns, and `switch` expressions, which are standard since Java 21; no preview flags are needed. When running it, make sure the project compiler actually uses JDK 21+ and the appropriate `--release` level.

## 10. Exhaustiveness and Sealed Hierarchies

Not every `switch` expression needs a `default` branch if the compiler can prove the cases are exhaustive. When the selector has a **sealed hierarchy**, type patterns can cover all permitted subtypes:

```java
sealed interface Result permits Success, Failure {}
record Success(String message) implements Result {}
record Failure(int code) implements Result {}

static String summarize(Result result) {
    return switch (result) {
        case Success success -> success.message();
        case Failure failure -> "Error:" + failure.code();
    };
}
```

This is an **illustrative snippet** that must be placed alongside the corresponding type declarations in a Java 21 file. The compiler knows that `Result` only has those permitted direct subtypes, so it can verify exhaustiveness of the `switch`. However, if the selector is actually `null`, a `switch` without `case null` still does not treat `null` as handled. For inputs that must accept `null`, add an explicit branch.

Type patterns in `case` are only one part of pattern matching; record patterns such as `case Point(int x, int y)` also allow deconstructing components, but that is a different kind of pattern and should be distinguished when reading code.

## 11. Common Mistakes

| Mistake | Cause | How to Fix |
| --- | --- | --- |
| Writing `case String ->` | Missing the type pattern variable | Use `case String text ->` |
| Using `case String s && guard` on Java 21 | Old preview syntax, not the standard syntax | Use `case String s when guard ->` |
| Placing `case Number n` before `case Integer i` | The broader pattern dominates the narrower pattern | Order specific branches first |
| Placing `case String s` before `case String s when ...` | The guarded `String` branch is dominated | Place the guarded branch before the general pattern |
| Assuming `default` catches `null` | `switch` has separate rules for `null` | Use `case null` or check before `switch` |
| Using a pattern variable outside its matching branch | The pattern is not guaranteed to have matched | Use the variable only in `when` and its branch |
| Misusing `case List<String> list` with `Object` | Erased type arguments cannot be verified | Use `List<?>`, then check elements if needed |
| Missing a branch in a `switch` expression | The compiler cannot prove exhaustiveness | Add the missing pattern or a valid `default` |
| Writing `case ...:` and forgetting `break` | Can fall through or hit pattern variable scoping errors | Prefer `->`; if using colon, control flow explicitly |
| Running on Java 17 | Type patterns for `switch` are not a standard feature in Java 17 | Use JDK 21+ for this lesson |

## 12. Practice Exercises and Completion Criteria

1. Write a `switch (Object value)` that returns distinct descriptive strings for `String`, `Integer`, `Double`, `null`, and other types. Use pattern variables to extract data in each branch.
2. Add a `when` guard for an empty or whitespace-only `String`; make sure the guarded branch comes before the general `String` branch.
3. Intentionally swap the order of `case Number n` and `case Integer i`, compile, read the dominance error, and fix it.
4. Write the same method using a `switch` expression with `->` and a `switch` statement using `case ...:` with `break`. Compare variable scope and `return`/`yield` behavior.
5. Try passing `null` into a `switch` that only has `default`, then add `case null` to observe the difference.
6. Write `case java.util.List<?> list` to get `list.size()`; explain why you cannot guarantee the list's elements are `String` when only `Object` is known initially.
7. Predict the output of `CaseTypePatternDemo`, compile it, and compare against all 9 output lines.

**Completion criteria:** You can write `case Type variable` syntax correctly, distinguish arrow rules from colon statements, use `when` guards, and explain dominance, exhaustiveness, pattern variable scope, `null` handling, and limitations with generic types.

**Official Documentation:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).