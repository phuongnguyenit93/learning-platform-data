# When Is a Pattern Variable Initialized in Java?

**Answer:** A pattern variable is **created and initialized at the moment a value successfully matches the pattern at runtime**. With `value instanceof String text`, when the value of `value` is non-`null` and is a `String`, Java binds that exact reference to `text`; starting from the control-flow point where the compiler proves the match has occurred, you can use `text` as a variable of type `String`. If the pattern does not match, `text` is not initialized for that check.

What must be kept distinct is **when initialization happens at runtime** versus **the scope where it can be accessed at compile time** (`flow scoping`). Java does not allow reading a pattern variable at a location where the pattern is not guaranteed to have matched, even if the developer believes the actual input will always have the right type.

## 1. From the `instanceof` Check to an Initialized Variable

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

When the condition is evaluated:

1. Java evaluates the expression on the left-hand side of `instanceof` to obtain the value to check.
2. If the value is `null` or incompatible with `String`, the type pattern fails: `instanceof` returns `false`, and no `text` is available from this match attempt.
3. If the value matches, the pattern variable `text` is initialized with the checked value (in the example, the reference to the string `"Java"`). The check returns `true`.
4. Execution enters the `if` branch, where `text` already has a value with static type `String`. There is no need to write `(String) value` or a separate assignment statement.

`text` is not pre-initialized to `null` like an object field; it is a local variable declared by the pattern and initialized by the matching process. If the input value is an empty `String` `""`, the pattern **still matches**: the condition only checks the type, not whether the string has content.

| Value of `value` | `value instanceof String text` | Is `text` assigned a value? |
| --- | --- | --- |
| `"Java"` | `true` | Yes, a reference to `"Java"` |
| `""` | `true` | Yes, a reference to the empty string |
| `42` (an `Integer`) | `false` | No |
| `null` | `false` | No |

## 2. Initialized Immediately After the Pattern Matches, Even If the Overall `if` Condition May Be False

```java
Object value = "   ";

if (value instanceof String text && !text.isBlank()) {
    System.out.println("Non-blank: " + text);
} else {
    System.out.println("Not a non-blank String");
}
```

`instanceof String text` has **matched and initialized `text`**, because `"   "` is a `String`. Only then does Java evaluate `!text.isBlank()`, which returns `false`; therefore the entire `&&` expression is `false` and the `else` branch runs. Output:

```text
Not a non-blank String
```

Therefore, **"the pattern matched" does not mean "the entire `if` condition is `true`"**. Inside the `else` branch, `text` cannot be used: this branch can also be reached when `value` is `null` or an `Integer`, where the pattern never matched.

The `&&` operator uses short-circuit evaluation: the right-hand side is only executed if the left-hand side is `true`. Thus `text` is already initialized when `text.isBlank()` is evaluated. Conversely, the following snippet **does not compile**:

```java
// WRONG: the right-hand side of || runs when the instanceof on the left is false.
if (value instanceof String text || text.isEmpty()) {
    // ...
}
```

On the right-hand side of `||`, there is no guarantee that `text` has matched. A valid expression with a different meaning is `!(value instanceof String text) || text.isBlank()`: the right-hand side only runs when the initial `instanceof` check is **true**, so `text` is already initialized.

## 3. Variable Scope Depends on Control-Flow Paths

Java uses **flow scoping**: the compiler examines which paths can reach each location and only allows using the variable when every valid path guarantees that the pattern has matched.

**In the true branch:**

```java
if (input instanceof String s) {
    System.out.println(s.length()); // Valid: s is initialized
} else {
    // s is not in scope here
}
// Normally s cannot be used here: the if condition may have failed.
```

**With negation `!`:**

```java
if (!(input instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println(s.length()); // Valid: the else branch means the match succeeded
}
```

**After an early exit (guard clause):**

```java
static void printLength(Object input) {
    if (!(input instanceof String s)) {
        return;
    }
    System.out.println(s.length()); // Valid: reaching here requires a successful match
}
```

This is not a "late initialization" via a new assignment statement. `s` was initialized **when the pattern matched in the `instanceof` check**; the compiler deduces that after `return`, every continuing path has a valid `s`.

**Ternary operator:** With `input instanceof String s ? s.length() : 0`, `s` is initialized in the `?` branch when the condition is true, but cannot be referenced in the `:` branch when the pattern is false.

**Loops:** `while (input instanceof String s)` checks the pattern each time the condition is evaluated. On each successful match, `s` is bound to the value from that check; `s` can be used inside the loop body. You should not infer from the language rules that the JVM must allocate a new object for the variable on every iteration.

## 4. Standalone Java 17+ Program

Save the following snippet in a file named `PatternVariableLifecycle.java`:

```java
public class PatternVariableLifecycle {
    static void describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            System.out.println("String: " + text + " (" + text.length() + ")");
        } else {
            System.out.println("Khong phai chuoi khac rong");
        }
    }

    static void printAfterGuard(Object input) {
        if (!(input instanceof String text)) {
            System.out.println("Bo qua: khong phai String");
            return;
        }
        System.out.println("Sau guard: " + text.toUpperCase());
    }

    public static void main(String[] args) {
        describe("Java");
        describe("   ");
        describe(12);
        describe(null);
        printAfterGuard("pattern");
        printAfterGuard(99);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 PatternVariableLifecycle.java
java PatternVariableLifecycle
```

Expected output:

```text
String: Java (4)
Khong phai chuoi khac rong
Khong phai chuoi khac rong
Khong phai chuoi khac rong
Sau guard: PATTERN
Bo qua: khong phai String
```

Explanation: for `"Java"`, the pattern matches, `text` is initialized, and then `isBlank()` returns `false`, so it enters the true branch. For `"   "`, `text` **is still initialized**, but the additional condition is not satisfied. For `12` and `null`, the pattern does not match. In `printAfterGuard`, `return` eliminates the non-matching paths, so `text` can be used after the `if`.

## 5. `switch` and Record Patterns: Java 21+

In a `switch` using patterns (a standard feature since Java 21), a `case` variable is initialized when the selector value matches that `case`'s pattern, **before** evaluating the `when` guard condition and before running the branch body:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "Text: " + s;
        case String s -> "Blank String";
        case Integer n -> "Integer: " + n;
        case null -> "Null";
        default -> "Other";
    };
}
```

In `case String s when !s.isBlank()`, `s` already has a value when `when` calls `s.isBlank()`. If the `when` condition is false, `switch` continues checking the next matching branch. Variables with the same name `s` in the two `case` labels above belong to separate scopes. `case null` handles the `null` value without declaring a pattern variable.

A **record pattern** (standard since Java 21) both tests a record and deconstructs its components using nested patterns:

```java
record Pair(Object left, Object right) {}

static void inspectPair(Object value) {
    if (value instanceof Pair(String left, Integer right)) {
        System.out.println(left + ": " + right);
    }
}
```

Only when the record and **both component patterns** match does the `if` branch run with `left` and `right` initialized from the components. If one component does not match (for instance, `right` is `null`), the entire record pattern fails and those variables cannot be used in the success branch.

The two examples in this section require `javac --release 21` (or compiling on JDK 21+ with the corresponding language level); the example in section 4 is Java 17 compatible.

## 6. Misconceptions to Avoid

- **Confusing declaration with initialization:** the `instanceof String s` syntax declares the pattern variable; `s` only receives a value when the pattern matches successfully at runtime. You do not need—and are not allowed—to add `s = ...` syntax inside the type pattern itself.
- **Confusing the pattern result with the overall condition result:** `instanceof` can be true and initialize `s`, while the check after `&&` sends the `if` into the `else` branch.
- **Confusing scope with object lifetime:** a pattern variable holds a reference to the matched object; it does not copy the `String` object. Reassigning the source variable later does not automatically update the value bound to the pattern variable.
- **Assuming pattern variables are always `final`:** since Java 16's `instanceof` pattern matching, a pattern variable is not implicitly `final`; it can be reassigned within its valid scope (unless declared `final`). Reassigning `s` does not change the source variable's value.
- **Assuming a match with `null`:** the type pattern `String s` does not match `null`, unlike a cast `(String) null` which evaluates to `null`.
- **Using the variable outside where the compiler proves a match:** on the right-hand side of `||` with a non-negated `instanceof` condition, in the `else` branch, or after the `if`, the initialization guarantee may be missing and will be rejected at compile time.

**Rule of thumb:** *When pattern matching succeeds, the variable is initialized; Java only allows using the variable along paths where that successful match is guaranteed.* Keeping these two ideas separate makes it easier to read logical expressions, guard clauses, `switch`, and record patterns accurately.

### Official Documentation

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
