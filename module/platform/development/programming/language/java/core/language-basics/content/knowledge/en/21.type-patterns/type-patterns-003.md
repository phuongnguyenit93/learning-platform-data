# Condition-Flow-Dependent Scope of Pattern Variables — Java 17+

## 1. What Is Pattern Variable Scope?

Java 17 supports **pattern matching for `instanceof`** (a stable feature since Java 16). The syntax checks a type and declares a **pattern variable** in the same expression:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

**Exact stdout:**

~~~text
7
~~~

When the condition `value instanceof String text` is true, Java has confirmed that `value` is a `String` and assigned the corresponding reference to the pattern variable `text`, without needing a manual cast.

The key point of this lesson: **the scope of `text` does not depend solely on `{ }` braces, but also on the conditional control flow**. The compiler only allows using a pattern variable where it can prove that the pattern has **definitely matched**. That mechanism is called **flow scoping**.

## 2. Reading Control Flow Instead of Only Looking at Braces

A type pattern avoids having to rewrite a cast after `instanceof`; the point to analyze here is **which branch guarantees that the pattern has matched**. For instance, in `if (value instanceof String text)`, the `if` body can use `text` because the condition is true, whereas `else` has no such guarantee. When the condition does not match and execution continues, `text` cannot be used after the entire `if`.

The following sections examine `&&`, `||`, negation, early-return guards, the ternary operator, and `else if` individually to derive this rule from control flow. When `value == null`, the type check fails without throwing NPE.

## 3. In the True `if` Branch, the Pattern Variable Is Usable

~~~java
static String inspect(Object value) {
    if (value instanceof String text) {
        return "LEN:" + text.length();
    }
    return "NOT_STRING";
}
~~~

- When the condition is true, `text` is guaranteed to be a `String`.
- When the condition is false, `text` cannot be used in the `else` branch of that positive check.
- After the entire `if`, if there is still a path where the pattern did not match, `text` is also **not considered definitely in scope**.

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Valid.
} else {
    System.out.println("not a String");
    // System.out.println(text); // COMPILE ERROR: text is not in scope here.
}
// System.out.println(text); // ERROR if there is a path where the pattern has not matched.
~~~

In this example, the variable `text` can only be used in the branch where the compiler knows the pattern matched. Do not treat a pattern variable name like a local variable declared unconditionally at the top of a method.

## 4. Combining `instanceof` with `&&`: The Right-Hand Side Knows the Pattern Matched

The `&&` operator evaluates from left to right and **short-circuits**: if the left-hand side is `false`, the right-hand side does not execute.

~~~java
static boolean isLongString(Object value) {
    return value instanceof String text && text.length() >= 4;
}
~~~

The right-hand side `text.length() >= 4` is evaluated only when `value instanceof String text` is true, so `text` has definitely matched the pattern there.

| `value` | `instanceof` Branch | Right-Hand Side `text.length()` | Result |
|---|---|---|---|
| `"Java"` | true | Evaluated: 4 | true |
| `"Go"` | true | Evaluated: 2 | false |
| `Integer.valueOf(7)` | false | **Skipped** | false |
| `null` | false | **Skipped** | false |

You can add guards or method calls that use the pattern variable only after the match:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.length() <= 20) {
    System.out.println(text.strip());
}
~~~

**Order matters:** put the pattern check on the left, and only then use the pattern variable in subsequent conditions.

## 5. Why Does `||` with a Positive Pattern Check Not Allow Using the Variable on the Right-Hand Side?

Consider this incorrect attempt:

~~~java
// if (value instanceof String text || text.isEmpty()) {
//     System.out.println("accepted");
// }
~~~

This is a **compile error**, not merely a risk of `NullPointerException`.

With `A || B`, Java evaluates `B` only if `A` is **false**. But `A` here is `value instanceof String text`, so upon reaching `B`, the pattern **has not matched**. Therefore, the variable `text` is not in valid scope on the right-hand side.

**Comparison:**

- `value instanceof String text && text.length() > 0` — **valid**.
- `value instanceof String text || text.length() > 0` — **invalid**.
- `value instanceof String text` standalone in an `if` — the variable is only usable in branches where it is guaranteed to have matched.

Do not try to work around the compile error with an arbitrary cast on the right-hand side; first determine whether the business requirement is "and" or "or".

## 6. Negation `!` Changes the Flow That Determines Scope

With a negated expression:

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
} else {
    System.out.println(text.length()); // Valid.
}
~~~

In the `else` branch, the negation `!(...)` is false, meaning the inner pattern **matched**. Therefore, the compiler allows using `text`.

Conversely:

~~~java
if (!(value instanceof String text)) {
    // System.out.println(text.length()); // Invalid.
}
~~~

In this `if` branch, the type check **did not match**, so there is no valid `text` variable.

**Reasoning tip:** instead of looking only at braces, ask: *for execution to reach the statement under consideration, must the `instanceof` expression necessarily have been true?*

## 7. Guard Clause: The Pattern Variable Can Be Used After an `if` Statement

A very useful pattern in methods:

~~~java
static String describe(Object value) {
    if (!(value instanceof String text)) {
        return "NOT_STRING";
    }

    return "TEXT:" + text.strip();
}
~~~

If the value is not a String, the method **returns immediately**. Consequently, to reach `return "TEXT:" + text.strip()`, the `instanceof` check must have succeeded, so `text` is in valid scope **even after the closing `}` of the `if`**.

This demonstrates that flow scoping **is not simply scope from an opening brace to a closing brace**.

~~~java
if (!(value instanceof String text)) {
    return "NOT_STRING";
}
// text can be used here because the failing branch has returned.
~~~

However, if the failing branch only logs and continues:

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
}
// System.out.println(text.length()); // ERROR: the failing path still reaches here.
~~~

**Note:** within the same method, a snippet with `return` must match the return type. Examples with `return` are placed inside methods returning `String`.

## 8. `||` Can Be Valid When the Check Is Negated

The following expression is **valid**:

~~~java
static String validate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return "VALID:" + text.strip();
}
~~~

Flow-based explanation:

1. `!(value instanceof String text)` is true if the value is not a String; because `||` short-circuits, `text.isBlank()` is **not called**.
2. If the left-hand side is false, `value instanceof String text` was true; therefore the right-hand side is allowed to use `text`.
3. After the `if` statement, execution can continue only when the entire condition is false. That guarantees `text` is a String and **not blank**, so `text.strip()` is safe.

| Input | Result |
|---|---|
| `" Java "` | `VALID:Java` |
| `"   "` | `INVALID` |
| `Integer.valueOf(3)` | `INVALID` |
| `null` | `INVALID` |

Quick comparison:

~~~java
// Valid: positive pattern check and use &&.
value instanceof String text && !text.isBlank()

// Valid: negate pattern, then use || in the guard.
!(value instanceof String text) || text.isBlank()

// Invalid: positive pattern with ||, using text on the right-hand side.
// value instanceof String text || text.isBlank()
~~~

The compiler's mechanism is based on **logical control flow**, not on whether variables share the same name in an expression.

## 9. Using `||` to Return a Boolean When Not a String or an Empty String

~~~java
static boolean emptyOrNotString(Object value) {
    return !(value instanceof String text) || text.isEmpty();
}
~~~

Results:

- `42` → true because it is not a String; the right-hand side is skipped.
- `""` → true because it is an empty String.
- `"ok"` → false because it is a non-empty String.

In this example, the requirement is "**not a String OR an empty String**", so using `||` with a negated pattern is appropriate.

**Do not infer** that every `||` case allows using a pattern variable. What decides it is whether, when the program must evaluate the right-hand side, the pattern is already **definitely matched**.

## 10. Pattern Variables in the Conditional Operator `?:`

The ternary operator also has clear true/false branches:

~~~java
static int stringLengthOrMinusOne(Object value) {
    return value instanceof String text ? text.length() : -1;
}
~~~

The true branch of `?:` executes only when `value instanceof String text` is true, so `text.length()` is valid. The false branch has no guarantee that the pattern matched:

~~~java
// int n = value instanceof String text
//         ? text.length()
//         : text.length(); // Invalid in the false branch.
~~~

This form is suitable when an expression returns a simple result. With multiple checks or when errors must be reported, an explicit `if/else` can be easier to read.

## 11. Scope in `else if` and Other Pattern Variables

~~~java
static String describeValue(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "TEXT:" + text.strip();
    } else if (value instanceof Integer number) {
        return "INTEGER:" + (number + 1);
    }
    return "OTHER";
}
~~~

- `text` is valid only in positions guaranteed by the String check branch.
- `number` is valid only in the Integer check branch.
- `text` cannot be used in the Integer branch when the String condition could have been false.
- After the entire chain, there is no guarantee that either pattern matched, so the pattern variables do not become method-wide variables.

**Note on extra conditions:** a String can match `instanceof String text` yet be rejected by `!text.isBlank()`. In that case it does not automatically become an Integer; the example ultimately returns `OTHER`.

In complex expressions, reusing the same variable name across multiple patterns with overlapping scopes can cause duplicate declaration errors. Name variables by type or meaning (`text`, `number`) and keep conditions readable.

## 12. Limitations and Pitfalls to Avoid

| Case | Valid? | Reason |
|---|---|---|
| `if (o instanceof String s) { s.length(); }` | Yes | Pattern matches in the true branch |
| `if (o instanceof String s && s.length() > 2)` | Yes | Right-hand side runs only when the pattern matches |
| `if (o instanceof String s \|\| s.length() > 2)` | **No** | Right-hand side runs only when the pattern does not match |
| `if (!(o instanceof String s)) { return; } use(s);` | Yes, in an appropriate `void` method | The non-matching path has exited |
| `if (!(o instanceof String s)) { log(); } use(s);` | **No** | The non-matching branch can still continue |
| `if (!(o instanceof String s)) ... else use(s);` | Yes | The `else` branch guarantees the pattern matched |
| `!(o instanceof String s) \|\| s.isEmpty()` | Yes | Evaluating the right-hand side requires the pattern to have matched |
| `o instanceof String s ? s.length() : -1` | Yes | The true branch guarantees a match |
| `o instanceof String s ? 0 : s.length()` | **No** | The false branch does not guarantee a match |

Several Java 17 points worth remembering:

- With `Object candidate = null;`, the expression `candidate instanceof String s` returns `false` without throwing NPE; there is no pattern variable `s` on that path. **Do not write the literal `null instanceof String s` directly in Java 17**: that is a type pattern rejected at compile time (an unconditional pattern for the type of the `null` literal). A non-binding type check `null instanceof String` is valid and evaluates to `false`.
- Do not use `switch` pattern matching as a default stable feature of Java 17: in this version it is a **preview** feature; this lesson uses stable `instanceof` patterns that compile normally with `--release 17`.
- The compiler generally rejects an `instanceof` pattern that is trivially always true based on static types (for example, testing `instanceof String s` on a variable already declared as `String`). Use type patterns where the expression has a sufficiently broad type, such as `Object` or an appropriate interface.
- Only use pattern variables in flows where the type has been confirmed; do not force casts or redeclare variables just to "get past the compiler" if the logical expression is actually wrong.

## 13. Complete Java 17 Program

Create a file with the exact name **`PatternFlowScopeDemo.java`**:

~~~java
import java.util.Locale;

public final class PatternFlowScopeDemo {
    private PatternFlowScopeDemo() {}

    static String inspect(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.strip().toUpperCase(Locale.ROOT);
        } else if (input instanceof Integer number) {
            return "INTEGER:" + (number + 1);
        }
        return "OTHER";
    }

    static String positiveBranch(Object value) {
        if (value instanceof String text) {
            return "STRING:" + text.length();
        }
        return "NOT_STRING";
    }

    static boolean longEnough(Object value) {
        return value instanceof String text && text.length() >= 4;
    }

    static String afterGuard(Object value) {
        if (!(value instanceof String text)) {
            return "NO_STRING";
        }
        return "AFTER_GUARD:" + text.length();
    }

    static String rejectInvalid(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "REJECT";
        }
        return "ACCEPT:" + text.strip();
    }

    static boolean emptyOrNotString(Object value) {
        return !(value instanceof String text) || text.isEmpty();
    }

    static int conditionalLength(Object value) {
        return value instanceof String text ? text.length() : -1;
    }

    static String negativeElse(Object value) {
        if (!(value instanceof String text)) {
            return "ELSE:NO";
        } else {
            return "ELSE:YES:" + text.length();
        }
    }

    static boolean traced(String label, boolean answer) {
        System.out.println("checked " + label);
        return answer;
    }

    static boolean tracedAnd(Object value) {
        return value instanceof String text
                && traced("length", text.length() >= 2);
    }

    public static void main(String[] args) {
        Object[] inputs = {
            " Java ", "   ", Integer.valueOf(41), null, "Go"
        };
        for (Object value : inputs) {
            System.out.println("inspect=" + inspect(value));
        }

        System.out.println("positive String=" + positiveBranch("Hi"));
        System.out.println("positive Integer=" + positiveBranch(5));

        System.out.println("long Java=" + longEnough("Java"));
        System.out.println("long Go=" + longEnough("Go"));
        System.out.println("long null=" + longEnough(null));

        System.out.println("guard String=" + afterGuard("abc"));
        System.out.println("guard Integer=" + afterGuard(5));

        System.out.println("reject blank=" + rejectInvalid("  "));
        System.out.println("reject number=" + rejectInvalid(5));
        System.out.println("accept text=" + rejectInvalid(" x "));

        System.out.println("empty non-string=" + emptyOrNotString(5));
        System.out.println("empty String=" + emptyOrNotString(""));
        System.out.println("nonempty String=" + emptyOrNotString("ok"));

        System.out.println("length hello=" + conditionalLength("hello"));
        System.out.println("length other=" + conditionalLength(5));

        System.out.println("negated else String=" + negativeElse("abc"));
        System.out.println("negated else null=" + negativeElse(null));

        System.out.println("traced Integer=" + tracedAnd(5));
        System.out.println("traced String=" + tracedAnd("Hi"));
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file; do not use external libraries outside the JDK, Maven, Gradle, or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PatternFlowScopeDemo.java
java -cp . PatternFlowScopeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PatternFlowScopeDemo.java
java -cp . PatternFlowScopeDemo
~~~

### Exact expected stdout

~~~text
inspect=TEXT:JAVA
inspect=OTHER
inspect=INTEGER:42
inspect=OTHER
inspect=TEXT:GO
positive String=STRING:2
positive Integer=NOT_STRING
long Java=true
long Go=false
long null=false
guard String=AFTER_GUARD:3
guard Integer=NO_STRING
reject blank=REJECT
reject number=REJECT
accept text=ACCEPT:x
empty non-string=true
empty String=true
nonempty String=false
length hello=5
length other=-1
negated else String=ELSE:YES:3
negated else null=ELSE:NO
traced Integer=false
checked length
traced String=true
~~~

**Why is the output like this?**

1. `inspect` uses `text` only when the String pattern matches and the string is not blank; `Integer` is handled with the variable `number` in a separate branch.
2. `longEnough` demonstrates that `&&` allows accessing `text.length()` on the right-hand side and skips the right-hand side for null or Integer.
3. `afterGuard` can use `text` after `if` because the non-matching path has returned.
4. `rejectInvalid` uses `||` with a negated pattern to reject blank Strings; after the guard, only valid non-blank strings remain.
5. `emptyOrNotString` returns true for a non-String object or an empty string; it skips `text.isEmpty()` if the pattern does not match.
6. `conditionalLength` uses the pattern variable in the true branch of `?:`.
7. `negativeElse` uses `text` in the `else` branch when the negation is false.
8. `tracedAnd(5)` **does not print `checked length`** because `instanceof` is false; `tracedAnd("Hi")` calls `traced`.

## 14. Common Mistakes and Fixes

| Mistake | Reason | Fix |
|---|---|---|
| Using the pattern variable in the `else` of a positive check | The `else` branch might not match | Use the variable in the true branch |
| Writing `o instanceof String s \|\| s.isBlank()` | The right-hand side of OR runs only when the pattern fails to match | Use `&&` for the positive branch, or `!(...) \|\| ...` if logic requires |
| Using `s` after `if` when the non-matching branch continues | Not guaranteed to be definitely matched | Use a `return`/`throw` guard clause in the failing branch |
| Thinking `{ }` braces are the only rule for scope | Java uses conditional flow analysis | Examine the true/false paths |
| Using `s` in the true branch of `!(o instanceof String s)` | That branch means no match | Use in `else` or after an early-return guard |
| Using `s` in the false branch of `?:` on a positive check | No guarantee the pattern matched | Use only in the true branch |
| Thinking `null instanceof String s` throws NPE | `instanceof` returns false for null | Can be used as a null-safe type guard |
| Writing redundant casts despite having a pattern variable | Causes redundant code/bad casts | Use the pattern variable directly in valid scope |
| Hiding side effects inside type conditions | Makes flow/output hard to reason about | Separate checks and side effects when needed |
| Using preview pattern switch without flags on JDK 17 | Compile error/unstable feature | Use stable `instanceof` patterns |

## 15. Exercises with Answers

### Exercise A — Pattern variable in `&&`

~~~java
Object value = "Java";
boolean valid = value instanceof String text && text.length() == 4;
System.out.println(valid);
~~~

**Answer:** prints `true`. The right-hand side runs only when the pattern matches.

### Exercise B — Why is `||` wrong?

~~~java
// boolean bad = value instanceof String text || text.isEmpty();
~~~

**Answer:** if the right-hand side of `||` is evaluated, the pattern on the left-hand side was false; `text` has not definitely matched, so it is not in scope. Fix depending on intent:

~~~java
boolean nonempty = value instanceof String text && !text.isEmpty();
~~~

Or when you want "not a String **or** an empty String":

~~~java
boolean emptyOrWrongType =
        !(value instanceof String text) || text.isEmpty();
~~~

### Exercise C — Using a variable after a guard clause

~~~java
static String uppercase(Object value) {
    if (!(value instanceof String text)) {
        return "UNKNOWN";
    }
    return text.toUpperCase(Locale.ROOT);
}
~~~

**Answer:** valid, because the failing path has returned. With `value = "hi"`, returns `"HI"`.

### Exercise D — Comparing two negation structures

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
} else {
    System.out.println(text.length());
}
~~~

**Answer:** `text` is usable inside `else`, because reaching `else` means the pattern matched.

### Exercise E — Conditional operator

~~~java
Object value = "abc";
int length = value instanceof String text ? text.length() : -1;
System.out.println(length);
~~~

**Answer:** `3`. The variable `text` is in scope in the true branch of `?:`, not in the false branch.

## 16. Checklist and Conclusion

- [ ] Know Java 17's `object instanceof Type variable` syntax.
- [ ] Understand that a pattern variable exists only on flows where the compiler proves the pattern matched.
- [ ] Use the pattern variable in the true branch of `if (o instanceof T t)`.
- [ ] Understand that `&&` allows using the pattern variable on the right-hand side of a positive check.
- [ ] Know why `||` with a positive check does not allow using the pattern variable on the right-hand side.
- [ ] Understand how negation `!` changes which branch guarantees the pattern matched.
- [ ] Use guards like `if (!(o instanceof T t)) return/throw` to use `t` after the guard.
- [ ] Know that `!(o instanceof T t) || ... t ...` can be valid with short-circuiting.
- [ ] Know that a pattern variable is usable in the true branch of the `?:` operator on a positive check.
- [ ] Do not use a pattern variable on the failing path or after an `if` when the failing path continues.
- [ ] Know that `instanceof` on null returns false without throwing NPE.
- [ ] Compile and run `PatternFlowScopeDemo.java` with Java 17+ and verify exact stdout.

**Conclusion:** Pattern variable scope in Java 17 is determined by **control flow and the type information the compiler can prove**. With positive `instanceof`, the variable is available in the true branch and on the right-hand side of `&&`; with negation, the variable can appear in `else`, on the right-hand side of an appropriate `||`, or after an early-exit guard clause. Understanding flow scoping helps reduce redundant casts without using variables on type-unchecked paths.
