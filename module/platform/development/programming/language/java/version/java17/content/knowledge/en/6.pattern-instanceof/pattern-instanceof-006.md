# Conditions for Using Variables After `if` and Errors with `||` in Pattern Matching for `instanceof` (Java 17)

When you write `if (value instanceof String text)`, Java does more than check the data type: if the check succeeds, Java also creates the variable `text` of type `String` so you can use it without manual casting. However, **a pattern variable does not exist everywhere after an `if` statement**. Java only allows using it at locations where control flow guarantees the check matched (*definitely matched*).

This is the **flow scoping** rule. Understanding this rule is especially important when using `&&`, `||`, negation `!`, and early-exit branches via `return` or `throw`.

> **Version scope:** Pattern matching for `instanceof` has been standard since Java 16 (JEP 394) and is stable in Java 17; the examples below do not need `--enable-preview`. Only use syntax applicable to Java 17 and later, without relying on earlier preview builds.

## 1. From Traditional `instanceof` to Pattern Variables

Before pattern matching, check-then-cast code was typically written like this:

~~~java
static void printLength(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
~~~

In Java 17, you can write it concisely:

~~~java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
~~~

The expression:

~~~java
value instanceof String text
~~~

consists of three parts:

| Component | Meaning |
|---|---|
| `value` | Expression to check, with static type `Object` in the example |
| `String` | Type that the object must match |
| `text` | Pattern variable of type `String`, available only where Java determines a match occurred |

If `value` references a `String` object, the check returns `true` and `text` binds to that reference. If `value` is an object of another type or `null`, the result is `false`; there is no valid `String` value to use through `text`.

The difference from the old approach is that you **do not have to manually declare and cast**. In return, you need to understand the scope of the variable created by the check.

## 2. Core Rule: The Variable Only Exists Where Definitely Matched

Look at this:

~~~java
static void demo(Object value) {
    if (value instanceof String text) {
        // true branch: instanceof succeeded.
        System.out.println(text.toUpperCase());
    } else {
        // false branch: no guarantee value is a String.
        // System.out.println(text); // COMPILE ERROR.
    }

    // After the whole if-else, both branches can converge here.
    // System.out.println(text); // COMPILE ERROR.
}
~~~

In the `true` branch, Java knows for certain that `value` is a `String`, so `text` is usable. In the `false` branch, the check did not match, so `text` is not in a valid scope.

**Outside a regular `if`, `text` is not automatically usable either**, because execution reaching that point does not prove the condition was true:

~~~java
static void printIfString(Object value) {
    if (value instanceof String text) {
        System.out.println("Received string: " + text);
    }

    // Wrong: if value is not a String, execution still reaches here.
    // System.out.println(text.length());
}
~~~

We can visualize this as:

~~~text
                    value instanceof String text
                             /       \
                         true         false
                          |             |
                     text valid    text absent
                          \             /
                           \           /
                         After regular if
                    not sure text matched
~~~

Java relies on **actual control flow**, not on whether the variable was written "before" or "after" in line order.

### 2.1. Quick orientation table

| Usage location of `text` | Valid? | Reason |
|---|---|---|
| Inside `if (value instanceof String text)` branch | **Yes** | True condition means the pattern matched |
| Inside `else` of the same check | **No** | `else` only runs when the pattern did not match |
| After a regular `if` with no exit branch | **No** | There is a path through the false condition |
| Right-hand side of `value instanceof String text && ...` | **Yes** | `&&` evaluates the right-hand side only if the left-hand side is true |
| Right-hand side of `value instanceof String text \|\| ...` | **No** | `\|\|` evaluates the right-hand side only if the left-hand side is false |
| After `if (!(value instanceof String text)) return;` | **Yes** | Reaching the next line means the non-matching branch exited |
| Inside `if (!(value instanceof String text))` branch | **No** | This branch runs when the pattern did not match |

## 3. Why Can `&&` Use the Pattern Variable?

The logical operator `&&` (*conditional AND*) evaluates from left to right and **stops immediately upon encountering `false`** (*short-circuit evaluation*).

Example:

~~~java
static boolean isLongText(Object value) {
    return value instanceof String text && text.length() >= 10;
}
~~~

This is valid code in Java 17:

1. Java evaluates `value instanceof String text`.
2. If the result is `false`, the entire `&&` expression is `false`; `text.length()` **is not executed**.
3. If the result is `true`, `text` is bound to a `String`; only then does Java evaluate `text.length() >= 10`.

Diagram:

~~~text
value instanceof String text
      |
      +--- false ------> result false
      |
      +--- true
             |
             v
      text.length() >= 10  (text is usable)
             |
             v
         true / false
~~~

We can combine multiple conditions:

~~~java
static boolean isUsefulText(Object value) {
    return value instanceof String text
            && !text.isBlank()
            && text.length() <= 100;
}
~~~

With the condition above:

- `value = "Java 17"`: valid, result `true`.
- `value = "   "`: is a `String` but blank according to `isBlank()`, result `false`.
- `value = 17`: not a `String`, stops right at `instanceof`, result `false`.
- `value = null`: `instanceof` returns `false`, neither `text.isBlank()` nor `text.length()` executes.

With a type check like the one above, adding `value != null` before `instanceof` is usually unnecessary, since `null instanceof String` inherently returns `false`.

### 3.1. The position of the check matters greatly

Correct way:

~~~java
if (value instanceof String text && text.startsWith("J")) {
    System.out.println(text);
}
~~~

The following causes an error:

~~~java
// WRONG: text is used before the pattern declares and matches it.
// if (text.startsWith("J") && value instanceof String text) {
//     System.out.println(text);
// }
~~~

`&&` does not swap the order of its two sides; evaluating the left-hand side first is what allows the right-hand side to use the variable.

### 3.2. `&&` can be combined with `||` inside the safe region

Not every occurrence of `||` makes code invalid. What matters is **whether the variable has already been proven to match before evaluating the expression containing `||`**.

Valid example:

~~~java
static boolean needsReview(Object value) {
    return value instanceof String text
            && (text.isBlank() || text.length() > 20);
}
~~~

When Java reaches the parenthesized expression, `value instanceof String text` has definitely returned `true`. Therefore **both sides** of `(text.isBlank() || text.length() > 20)` are allowed to use `text`.

The safety boundary lies at the outer `&&`.

## 4. Why Does `||` Often Cause Errors with Pattern Variables?

`||` (*conditional OR*) also evaluates from left to right, but **runs the right-hand side only when the left-hand side is `false`**.

Consider this invalid code:

~~~java
static boolean wrong(Object value) {
    // COMPILE ERROR:
    // return value instanceof String text || text.isEmpty();
    return false;
}
~~~

If `value instanceof String text` returns `true`, the `||` operator already has result `true` and **skips the right-hand side**. If Java needs to evaluate `text.isEmpty()`, that means `instanceof` just **returned `false`**. At that very moment `text` does not validly exist!

Diagram:

~~~text
value instanceof String text
      |
      +--- true -------> result true
      |
      +--- false
             |
             v
       text.isEmpty()        <-- ERROR: text has not matched
~~~

Therefore, `||` **cannot be used to take a pattern variable from an affirmative left-hand side and use it directly on the right-hand side**.

### 4.1. Even if the right-hand side doesn't use the variable, inside `if` can still fail

Consider:

~~~java
static void wrongInside(Object value, boolean allowFallback) {
    // WRONG example if the code using text is uncommented:
    if (value instanceof String text || allowFallback) {
        // System.out.println(text.length()); // ERROR.
        System.out.println("One condition was true");
    }
}
~~~

Why can't `text` be used in the `if` body?

- Case A: `value` is a `String`. The left-hand side is true, `text` has a value.
- Case B: `value` is not a `String` but `allowFallback` is true. The whole `||` expression is still true, **even though `text` never matched**.

Because of Case B, Java disallows using `text` inside that `if` branch.

**Distinguishing the two errors**:

| Code pattern | Error location | Cause |
|---|---|---|
| `value instanceof String text \|\| text.isBlank()` | Right-hand side of `\|\|` | Right-hand side runs when the pattern failed |
| `if (value instanceof String text \|\| flag) { use(text); }` | `if` body | True condition is insufficient to prove the pattern matched |

### 4.2. Common fix: use `&&` if both conditions must be true

If the goal is "the object must be a `String` and its content is not blank", write:

~~~java
static boolean hasContent(Object value) {
    return value instanceof String text && !text.isBlank();
}
~~~

This is a case where both conditions must hold **simultaneously**, so `&&` is used.

### 4.3. Fix when an OR operation is genuinely needed

Suppose the rule is "accept the value if it is a string **or** fallback is allowed":

~~~java
static boolean shouldProcess(Object value, boolean allowFallback) {
    return value instanceof String || allowFallback;
}
~~~

We only need the boolean value, so there is no need to declare a pattern variable.

If you also need to process `String` specifically when it actually occurs, split the branches:

~~~java
static void process(Object value, boolean allowFallback) {
    if (value instanceof String text) {
        System.out.println("String: " + text.strip());
    } else if (allowFallback) {
        System.out.println("Fallback processing");
    } else {
        System.out.println("Skip");
    }
}
~~~

This properly expresses the two cases: only the `String` branch has the variable `text`.

## 5. Important Exception: Valid Use of `||` After Negation `!`

`||` does not always conflict with pattern variables. A common pattern is:

~~~java
static boolean isValidUsername(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }

    return text.length() >= 3;
}
~~~

This code is **valid**. Let's analyze it:

- `value instanceof String text` is true ⇒ negation `!(...)` is `false` ⇒ `||` must evaluate the right-hand side. By then `text` is definitely matched.
- `value instanceof String text` is false ⇒ negation is `true` ⇒ `||` stops immediately, **without calling `text.isBlank()`**.
- If the entire `if` is true, the function returns `false`.
- If execution reaches `return text.length() >= 3;`, the entire `if` condition was false. That can only happen when `text` matched and is not blank.

This is the **guard clause** mechanism (early rejection condition): reject invalid inputs and continue working with the validated variable.

Flow progression:

~~~text
!(value instanceof String text)
            |
      +-----+-----+
      |           |
     true        false
      |           |
      v           v
  OR stops    text.isBlank()
  (returns        |
   false)     +---+---+
              |       |
             true    false
              |       |
              v       v
       returns false  continue
                          |
                          v
                   use text safely
~~~

**Do not invert negation incorrectly.** The following snippet is invalid:

~~~java
// WRONG: right-hand side only runs when !(instanceof) is true,
// i.e., when the pattern has not matched.
//
// if (!(value instanceof String text) && text.isBlank()) {
//     ...
// }
~~~

The simple rule is to check **the condition under which the right-hand side runs**, rather than merely looking at whether the expression contains `&&` or `||`.

## 6. When Can a Variable Be Used After an `if` Statement?

This is the most important part when applying flow scoping in real programs.

### 6.1. After a regular `if`: cannot be used by default

~~~java
static int lengthOrZero(Object value) {
    if (value instanceof String text) {
        System.out.println("This is a string");
    }

    // Wrong: value could be an Integer or null.
    // return text.length();

    return 0;
}
~~~

On the line after `if`, Java does not know whether the `true` branch executed.

### 6.2. After a negated `if` with `return`: usable

~~~java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    // Reaching here means the non-matching branch exited the method.
    return text.length();
}
~~~

Mechanism:

1. Not a `String` ⇒ `if` condition is true ⇒ executes `return 0`.
2. Is a `String` ⇒ `if` condition is false ⇒ skips `return 0`.
3. Every path **able to reach the final line** guarantees `text` matched.

Hence, the pattern variable can appear **after the closing brace of `if`**, even though it was declared in the condition.

### 6.3. After a negated `if` with `throw`: usable

~~~java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException(
                "Value must have type String");
    }

    return text.strip();
}
~~~

`throw` also prevents the non-matching branch from continuing to the following statements. Therefore, `text` is guaranteed matched on the continuing path.

This pattern suits argument validation at the beginning of a method:

~~~java
static void saveIdentifier(Object input) {
    if (!(input instanceof String identifier)) {
        throw new IllegalArgumentException("Identifier must be a String");
    }

    if (identifier.isBlank()) {
        throw new IllegalArgumentException("Identifier must not be blank");
    }

    System.out.println("Save: " + identifier.strip());
}
~~~

### 6.4. After a negated `if` without exiting: not usable

Compare:

~~~java
static void broken(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a string");
    }

    // ERROR if uncommented:
    // System.out.println(text.length());
}
~~~

Because the non-matching branch only prints a message and keeps going, execution can reach the final line without `text` having matched. Adding `!` alone is **not enough** to extend variable scope; you must examine the program's execution paths.

### 6.5. When the method also needs an `else` branch

If you want to handle both cases side by side, the simple and clear approach is to put the variable's usage inside the matching branch:

~~~java
static String display(Object value) {
    if (value instanceof String text) {
        return text.toUpperCase();
    } else {
        return "(not a string)";
    }
}
~~~

If you want to filter out unsuitable input and then write linear logic, use a negated guard clause like section 6.2 or 6.3.

## 7. Comprehensive Example Runnable on Java 17

Create the file **`PatternFlowDemo.java`**:

~~~java
import java.util.Locale;

public class PatternFlowDemo {

    // Pattern 1: && guarantees the right-hand side has the pattern variable.
    static boolean hasShortContent(Object value) {
        return value instanceof String text
                && !text.isBlank()
                && text.length() <= 12;
    }

    // Pattern 2: ! + return to use the variable after if.
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "(not a String)";
        }

        return text.strip().toUpperCase(Locale.ROOT);
    }

    // Pattern 3: || is valid because the instanceof condition is negated.
    static boolean validCode(Object value) {
        if (!(value instanceof String code) || code.isBlank()) {
            return false;
        }

        return code.length() >= 3;
    }

    // Pattern 4: OR between two situations, handling String in its own branch.
    static String describe(Object value, boolean fallback) {
        if (value instanceof String text) {
            return "String: " + text;
        } else if (fallback) {
            return "Fallback value";
        } else {
            return "Unsupported";
        }
    }

    public static void main(String[] args) {
        System.out.println(hasShortContent("Java 17"));
        System.out.println(hasShortContent(17));
        System.out.println(normalize("  Java 17  "));
        System.out.println(normalize(null));
        System.out.println(validCode("ABC"));
        System.out.println(validCode("  "));
        System.out.println(describe("hello", false));
        System.out.println(describe(42, true));
    }
}
~~~

Compile and run with **JDK 17**:

~~~bash
javac --release 17 PatternFlowDemo.java
java PatternFlowDemo
~~~

Output:

~~~text
true
false
JAVA 17
(not a String)
true
false
String: hello
Fallback value
~~~

The first three methods illustrate positions where Java has sufficient proof that the pattern matched. The last method illustrates applying `||` at the business-requirement level while isolating the branch that needs the pattern variable.

## 8. Additional Easily Confused Scenarios

### 8.1. The `else` of a negated condition

If an `if` condition is negated, the `else` branch is where the pattern is definitely matched:

~~~java
static void print(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a String");
    } else {
        System.out.println(text.length()); // Valid.
    }
}
~~~

Upon entering `else`, `!(instanceof)` is `false`, so the underlying `instanceof` must have been `true`.

### 8.2. The ternary operator `? :`

Flow scoping also applies to conditional expressions:

~~~java
static String label(Object value) {
    return value instanceof String text
            ? text.toUpperCase()
            : "(other)";
}
~~~

`text` is valid in the `?` branch when the condition is true; the `:` branch cannot assume `text` exists.

### 8.3. The variable only exists in the justified part of the expression

~~~java
static boolean longEnough(Object value) {
    boolean result = value instanceof String text
            && text.length() >= 5;

    // Invalid:
    // System.out.println(text);
    return result;
}
~~~

Variable `text` is usable during evaluation of `&&`; assigning the boolean variable `result` to `true` or `false` does not turn the pattern variable into a local variable usable on subsequent lines.

### 8.4. Combining independent conditions does not create a safe relationship

~~~java
static void check(Object value, boolean approved) {
    if (value instanceof String text || approved) {
        // Cannot use text here.
        System.out.println("Allowed to continue");
    }
}
~~~

Do not deduce "we entered `if`, so the pattern matched." With `||`, **another operand** can make the condition true.

### 8.5. `null`, `instanceof`, and method calls

When `value == null`, `value instanceof String text` returns `false`; it **does not throw `NullPointerException`**. Therefore:

~~~java
static boolean nonBlankString(Object value) {
    return value instanceof String text && !text.isBlank();
}
~~~

is a null-safe pattern with respect to `value`: the right-hand side runs only when `value` is genuinely a `String`.

### 8.6. Do not confuse pattern variables with fields or regular declarations

~~~java
if (value instanceof String text) {
    System.out.println(text);
}
~~~

`text` is not an automatically generated field on the class, nor a variable independently declared at the top of the method. Its scope is determined by **matching conditions and control-flow structures**.

If you need to retain a value across multiple independent branches, design the flow explicitly: return early for unsuitable cases, or assign to another local variable after validating the type.

## 9. How to Locate and Fix Compile Errors Related to `||`

When the compiler does not recognize a pattern variable or reports it is out of scope, read the logical expression in evaluation order:

1. Find the `instanceof Type variable` position.
2. Identify which operand or branch uses the variable.
3. Ask: **Is there any execution path reaching this location when `instanceof` returned `false`?**
4. If **yes**, that location is not guaranteed to have the pattern variable.
5. Choose the fix that matches the business intent: `&&`, a separate `if/else` branch, or a guard clause using `!` with `return`/`throw`.

Step-by-step conversion example.

**Broken code:**

~~~java
// Wrong: text is used on the right-hand side of ||.
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

If the intent is "only process non-blank strings", use `&&`:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println("Valid string: " + text);
}
~~~

If the intent is "reject when not a string **or** is a blank string", use negation:

~~~java
static void validate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Invalid string");
    }

    System.out.println("Valid string: " + text);
}
~~~

If the intent is "accept a string, or allow fallback", split the branches:

~~~java
static void handle(Object value, boolean fallback) {
    if (value instanceof String text) {
        System.out.println("Handling string: " + text);
    } else if (fallback) {
        System.out.println("Fallback processing");
    }
}
~~~

These three fixes correspond to **three different logical requirements**; do not mechanically change `||` to `&&` if it alters the condition's meaning.

## 10. Scenario Table: Right or Wrong?

Lines labeled "Wrong" illustrate compile errors and should not be put together into a single runnable file.

| Condition / usage snippet | Valid in Java 17? | Explanation |
|---|---|---|
| `if (o instanceof String s) { use(s); }` | Yes | The `true` branch guarantees a match |
| `if (o instanceof String s) {} else { use(s); }` | **Wrong** | The `false` branch has no `s` |
| `if (o instanceof String s) {} use(s);` | **Wrong** | After `if`, execution may have taken the non-matching path |
| `if (o instanceof String s && s.length() > 3) { use(s); }` | Yes | Right-hand side of `&&` runs only after matching |
| `if (o instanceof String s \|\| s.length() > 3) {}` | **Wrong** | Right-hand side of `\|\|` runs when not matched |
| `if (o instanceof String s \|\| flag) { use(s); }` | **Wrong** | `flag` can make the condition true when not matched |
| `if (!(o instanceof String s)) return; use(s);` | Yes | The non-matching branch exited |
| `if (!(o instanceof String s)) { use(s); }` | **Wrong** | The `if` body runs when not matched |
| `if (!(o instanceof String s) \|\| s.isBlank()) return; use(s);` | Yes | `s` exists on the right-hand side of `\|\|` and on the continuing path |
| `if (o instanceof String s && (s.isBlank() \|\| s.length() > 3)) {}` | Yes | The inner `\|\|` is guarded by `&&` |

In the table, `use(s)` is an illustrative placeholder for using the variable such as `System.out.println(s)`; `use` itself is not a built-in Java API.

## 11. Practice Exercises

### Exercise 1: Can the variable be used after `if`?

Given:

~~~java
static void show(Object value) {
    if (value instanceof String text) {
        System.out.println("Valid string");
    }

    // System.out.println(text.length());
}
~~~

**Question:** If the last line is uncommented, will it compile? Why or why not?

**Answer:** No. The last line still runs when `value` is an `Integer`, `null`, or another type; Java cannot prove `text` matched.

### Exercise 2: Fix the broken `||` expression

~~~java
// Wrong:
// if (value instanceof String text || text.length() > 5) {
//     System.out.println(text);
// }
~~~

**Requirement:** Only print strings longer than 5 characters.

**Answer:**

~~~java
if (value instanceof String text && text.length() > 5) {
    System.out.println(text);
}
~~~

The business condition requires both "is a `String`" and "longer than 5 characters" simultaneously, so `&&` is the right choice.

### Exercise 3: Use the variable after `if` without casting

Given:

~~~java
static int getLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    // TODO: return the length of text.
}
~~~

**Answer:**

~~~java
static int getLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    return text.length();
}
~~~

Because the non-matching path returned via `return`, the final line can only run when `text` matched.

### Exercise 4: Evaluate a trickier expression

~~~java
static boolean isAcceptable(Object value) {
    return value instanceof String text
            && (text.startsWith("A") || text.endsWith("Z"));
}
~~~

**Question:** Is there an error with `||`?

**Answer:** No. The entire parenthesized expression is evaluated only when `instanceof` on the left-hand side of `&&` has matched, so `text` is valid in both the `startsWith` and `endsWith` checks.

### Exercise 5: Fix the guard clause to match the intended goal

Requirement: Reject if `value` is not a `String` **or** is a whitespace-only string; otherwise print the string in uppercase.

**Reference answer:**

~~~java
import java.util.Locale;

class Example {
    static void printNormalized(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Need a non-empty string");
        }

        System.out.println(text.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

This is a completely valid `||` case: `text` is only used when the left-hand side proved the `instanceof` check succeeded.

## 12. Remembering How to Reason About Flow Scoping

Do not memorize a simplistic rule like "`&&` is always right, `||` is always wrong." The more accurate rule is:

> **A pattern variable is available only on control-flow paths where Java can prove the pattern match succeeded.**

Three most common cases in Java 17:

~~~java
// (1) Inside the matching if branch:
if (value instanceof String text) {
    System.out.println(text.length());
}

// (2) On the right-hand side of &&:
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}

// (3) After a negated guard clause:
if (!(value instanceof String text)) {
    throw new IllegalArgumentException();
}
System.out.println(text.length());
~~~

Memorable `||` patterns:

~~~java
// WRONG: right-hand side runs when instanceof is false.
// value instanceof String text || text.isBlank()

// RIGHT: right-hand side runs when instanceof is true.
// !(value instanceof String text) || text.isBlank()
~~~

When reading a condition, ask yourself: **"For the program to reach where the variable is used, must `instanceof` necessarily have returned `true`?"** If the answer is yes, Java generally allows the pattern variable to appear at that location.

## 13. References

- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): standard feature and *flow scoping* model.
- [Oracle Java SE 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): syntax and pattern variable scope.
- [Java Language Specification 17 — `6.3 Scope of a Declaration`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scoping rules and how expressions introduce pattern variables.
- [Java Language Specification 17 — `15.20.2 Type Comparison Operator instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): semantics of the type check and pattern.
