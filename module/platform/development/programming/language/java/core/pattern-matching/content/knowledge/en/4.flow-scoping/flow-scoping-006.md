# Variable Scope in else — Flow Scoping of Pattern Variables

## 1. Core question: why can else sometimes use a pattern variable, and sometimes not?

Since Java 16 (and finalized in Java 17+), you can write a **type pattern** directly in `instanceof`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`text` is a **pattern variable**: it only has a value after the expression `value instanceof String text` matches. Unlike an ordinary local variable whose scope is mainly based on block braces, the scope of a pattern variable also depends on **the control flow of the program** (*flow scoping*).

The key question for `else` is not `was the variable declared in the same if statement?`, but rather:

> **When the program enters the else branch, can the compiler prove with certainty that the pattern matched and the pattern variable has been initialized?**

- If **yes**, the pattern variable is *in scope* in `else`.
- If **no**, referencing the pattern variable name in `else` causes a compile error.

Simply negating the condition with `!` can shift the scope of the pattern variable from the `if` branch to the `else` branch. This is the core focus of this lesson.

## 2. Positive condition: direct instanceof does not bring the pattern variable into else

Consider the following illustrative example (placed inside a Java 17+ method):

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());  // Valid: text is a String
} else {
    System.out.println("Không phải String");
}
```

Execution flow:

1. If `value` is actually a `String`, the expression `instanceof String text` returns `true`, assigns the matching reference to `text`, and executes the `if` branch.
2. If `value` is another object or `null`, the expression returns `false`, **no String is assigned to `text`**, and the `else` branch executes.

Because the `else` branch only occurs when the match **fails**, the following code is **intentionally invalid**:

```java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println(text.length()); // COMPILE ERROR: text is not in scope
    }
}
```

The compiler must prevent reading a variable that the currently executing branch does not guarantee has been initialized. `text` does not automatically receive `null` in `else`. This is a **variable scope error at compile time**, not a `NullPointerException` at runtime.

Also note: if you declare **another variable** yourself inside `else`, that is a new variable and follows the normal scoping rules of local variables; it does not make the pattern variable `text` from the `if` branch available.

## 3. Negating the condition: else is where the pattern definitely matches

Now invert the condition:

```java
static String upper(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải String";
    } else {
        return text.toUpperCase();
    }
}
```

In the expression `!(value instanceof String text)`:

- When the condition is **true**, the `instanceof` inside `!` is **false**, so `text` is **not** in scope in the `if` branch.
- When the condition is **false**, the original `instanceof` is definitely **true**, so `text` **has matched** and is in scope in the `else` branch.

Diagram:

```text
value instanceof String text?
├── true  → text has been assigned
│           → !(...) = false
│           → enters else  → can use text
└── false → text has not been assigned
            → !(...) = true
            → enters if    → cannot use text
```

Common point of confusion: `else` **does not need** the `if` branch to have `return` or `throw` in order to use `text`. The mere fact that **the negated condition is false** is enough to prove the pattern match succeeded. The `return` in the example helps the method return a result, but it does not create the scope inside `else`.

Conversely, the following snippet is intentionally invalid:

```java
static void invalidNegated(Object value) {
    if (!(value instanceof String text)) {
        System.out.println(text); // COMPILE ERROR: text is not in scope in the if branch
    } else {
        System.out.println(text); // Valid
    }
}
```

## 4. Complete program: testing both directions

File **`ElseFlowDemo.java`**, using Java 17 or later:

```java
public class ElseFlowDemo {

    static String direct(Object value) {
        if (value instanceof String text) {
            return "String length=" + text.length();
        } else {
            return "Not a String";
        }
    }

    static String inverted(Object value) {
        if (!(value instanceof String text)) {
            return "Not a String";
        } else {
            return "Upper=" + text.toUpperCase();
        }
    }

    static String guarded(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Rejected";
        } else {
            return "Trim=" + text.trim();
        }
    }

    static String chained(Object value) {
        if (!(value instanceof String text)) {
            return "Other";
        } else if (text.isEmpty()) {
            return "Empty";
        } else {
            return "Text=" + text;
        }
    }

    static int lengthOrThrow(Object value) {
        if (value instanceof String text) {
            // Execution can continue in this branch.
        } else {
            throw new IllegalArgumentException("Need String");
        }

        // Every path reaching here has matched String text.
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(direct("Java"));
        System.out.println(direct(42));
        System.out.println(inverted("java"));
        System.out.println(inverted(null));
        System.out.println(guarded("  Java  "));
        System.out.println(guarded("  "));
        System.out.println(guarded(42));
        System.out.println(chained(""));
        System.out.println(chained("Hi"));
        System.out.println(chained(42));
        System.out.println(lengthOrThrow("Java"));
    }
}
```

Compile and run:

```bash
javac ElseFlowDemo.java
java ElseFlowDemo
```

Output:

```text
String length=4
Not a String
Upper=JAVA
Not a String
Trim=Java
Rejected
Rejected
Empty
Text=Hi
Other
4
```

The two methods `direct` and `inverted` demonstrate swapping scope between `if` and `else`. `guarded` illustrates combining `!` with `||`, `chained` illustrates nested `else if`, and `lengthOrThrow` is the case where the pattern variable remains in scope **after the entire if-else statement** because the non-matching branch always ends with `throw`.

The sections below explain why these cases are valid.

## 5. Java's standard rules for if/else branches

The Java Language Specification (JLS) describes the **definitely matched** state: at a given point in code, the compiler proves a pattern variable has definitely been initialized because the pattern matched.

For a condition expression `e` in `if (e) S else T`:

- A pattern variable introduced by `e` **when true** is in scope in branch `S` (`if`).
- A pattern variable introduced by `e` **when false** is in scope in branch `T` (`else`).

The phrase `introduced when false` does not contradict pattern matching. Normally `value instanceof String s` only introduces `s` **when true**. However, `!(value instanceof String s)` inverts the boolean result, so it introduces `s` **when false**.

| if condition | `s` in if branch | `s` in else branch | Explanation |
| --- | --- | --- | --- |
| `value instanceof String s` | Yes | No | if true ⇒ pattern matched |
| `!(value instanceof String s)` | No | Yes | if false ⇒ original pattern matched |
| `value instanceof String s && !s.isBlank()` | Yes | No | if false could be because it is not a String |
| `!(value instanceof String s) || s.isBlank()` | No | Yes | if false ⇒ is a String and not blank |
| `value instanceof String s || otherCondition` | Not guaranteed | No | if true could be due to the right-hand side; if false the pattern did not match |

The table covers **scope within the two branches of if-else**. To use `s` after the entire statement, you also need to consider which paths can complete normally; see section 8.

## 6. Role of &&: a true condition guarantees a match, a false condition does not

This section helps avoid wrong reasoning about `else`. With short-circuit AND:

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Đủ dài: " + text);
} else {
    System.out.println("Không đủ điều kiện");
}
```

The expression `text.length() >= 4` is only evaluated if `instanceof` has matched. Therefore, `text` is valid on the **right-hand side of `&&`** and in the `if` branch.

But why **cannot `else` use `text`**? The AND condition evaluates to false in **at least two cases**:

1. `value` **is not a String**, so `instanceof` is false and `text` is not assigned.
2. `value` is a String whose length is less than 4, so `text` was assigned, yet the entire AND expression is still false.

The compiler cannot determine which case occurred upon entering `else`. Therefore:

```java
static void invalidAnd(Object value) {
    if (value instanceof String text && text.length() >= 4) {
        System.out.println(text);
    } else {
        System.out.println(text); // COMPILE ERROR
    }
}
```

**Rule of thumb:** `instanceof T t && extraCheck(t)` allows using `t` in the **if** branch, but does not automatically allow using `t` in `else`.

## 7. Role of || combined with negation: else is guaranteed to match

Compare the valid snippet:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "Rejected";
    } else {
        return text.strip();
    }
}
```

Read the condition as: **not a String OR is a String that only contains whitespace**. In a short-circuit OR expression:

1. If `value` is not a String, the left-hand side `!(... instanceof String text)` is true; the right-hand side does not run, and `if` is taken.
2. If `value` is a String, the left-hand side is false; **`text` has matched**, so the right-hand side `text.isBlank()` is allowed to access it.
3. Only when **both sides are false** does execution enter `else`. That proves `value` is a String and `!text.isBlank()` is true. Hence `text` is valid in `else`.

Logic diagram:

```text
!(value instanceof String text) || text.isBlank()
       A                      ||       B
- A = true  → did not match String → enter if
- A = false → matched String       → evaluate B
   - B = true  → blank string      → enter if
   - B = false → non-blank string  → enter else (text definitely has a value)
```

Conversely, writing `value instanceof String text || fallback` **does not bring `text` into the if branch**, because the whole expression can be true **solely because `fallback` is true** when `value` is not a String.

A similar trap is using `&&` after a negated condition:

```java
static void invalidNegatedAnd(Object value, boolean flag) {
    if (!(value instanceof String text) && flag) {
        System.out.println("Nhánh if");
    } else {
        System.out.println(text); // COMPILE ERROR
    }
}
```

The AND condition can be false because `flag` is false **even if `value` is not a String**. Thus entering `else` does not prove `text` matched.

## 8. else if is an if nested inside else: how does scope propagate?

In Java, the `else if (...)` syntax is structurally **another if statement inside the else branch** of the outer statement. Therefore, you must examine the condition of the outer `if` first.

### 8.1. Positive condition chain: a variable from an earlier branch does not carry to later branches

```java
static String classify(Object value) {
    if (value instanceof String text) {
        return "String: " + text;
    } else if (value instanceof Integer number) {
        return "Integer: " + number;
    } else {
        return "Other";
    }
}
```

This is an **illustrative method**: place it in a Java 17+ class to call it. `text` can only be used in the String branch; `number` can only be used in the Integer branch. The final `else` branch has no guarantee for either type, so **neither pattern variable is available**.

You cannot put `text.length()` in the `else if` condition here: reaching it means `value instanceof String text` was already **false**.

### 8.2. Negated condition chain: the variable remains valid in inner else if and else

```java
static String inspect(Object value) {
    if (!(value instanceof String text)) {
        return "Other";
    } else if (text.isEmpty()) {
        return "Empty";
    } else if (text.length() < 4) {
        return "Short: " + text;
    } else {
        return "Long: " + text;
    }
}
```

The path entering the entire `else` branch of the outer statement already guarantees `text` is a String. Therefore `text` can be used in:

- The condition of the first `else if`.
- The condition of the second `else if`.
- The bodies of the corresponding `else if` branches.
- The final `else` branch of the inner chain.

This is **not** pattern variable access `everywhere in the method`. Only locations along paths where the compiler proves the pattern matched are allowed access.

## 9. After if-else: when does the variable's scope continue?

**Inside else** and **after the entire if-else** are two different questions. With a plain condition:

```java
static void invalidAfter(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("Other");
    }
    System.out.println(text); // COMPILE ERROR
}
```

Both branches can complete normally; reaching the final statement does not prove which branch just ran. Therefore `text` cannot be used after `if-else`.

However, Java also analyzes **which branch cannot complete normally**, such as due to `return` or `throw`:

```java
static int lengthOrThrow(Object value) {
    if (value instanceof String text) {
        // The matching path can continue.
    } else {
        throw new IllegalArgumentException("Need String");
    }
    return text.length(); // VALID: the non-matching path threw
}
```

Here `text` is introduced when the condition is **true**; the `if` branch can complete normally, while the `else` branch **cannot**. If the program reaches `return text.length()`, the only remaining case is that the pattern matched.

The guard clause style is also valid:

```java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // VALID: every continuing path is a String
}
```

Avoid the mechanical assumption `if there is a return somewhere, the variable leaks out of scope`. The compiler examines **paths reaching the point of use**, including true/false expressions and whether each branch can complete normally. A single unmatched path that can continue is enough to make the pattern variable unavailable after the statement.

### Quick decision table

| Code pattern | Inside else | After the entire if-else |
| --- | --- | --- |
| `if (o instanceof String s) { ... } else { ... }`; both branches complete normally | `s` not in scope | Not in scope |
| `if (!(o instanceof String s)) { ... } else { ... }`; both branches complete normally | `s` in scope | Not in scope |
| `if (o instanceof String s) { ... } else { throw ...; }` | `s` not in scope | `s` in scope if the matching branch can continue |
| `if (!(o instanceof String s)) { return; } else { ... }` | `s` in scope | `s` can be in scope when the else branch completes normally |

In the last row, the method must have a return type compatible with the `return` statement and the `else` branch. If a branch also cannot complete normally, the specific JLS rules continue to apply.

## 10. Does null make the pattern variable in else become null?

No. For the type pattern `String text` in `instanceof`, **null does not match**.

```java
static String render(Object value) {
    if (!(value instanceof String text)) {
        return "Not a String";
    } else {
        return "Value=" + text;
    }
}
```

- `render(null)` returns `"Not a String"`: `!` inverts the `false` result of `instanceof` to `true`, so it enters the `if` branch.
- `render("Hi")` returns `"Value=Hi"`: the negated condition is false, so it enters `else` and `text` holds the actual String reference.

Therefore, in the **else of a negated type pattern**, when the pattern variable is in scope, the reference value has already been matched according to the pattern condition; no manual cast is needed. However, do not generalize this conclusion to **all nested patterns in records**: null-matching rules for deconstruction and component patterns have their own specifics.

## 11. Java 21: same principle with record patterns

Flow scoping does not apply only to single type patterns. Since **Java 21**, record patterns can extract components and those pattern variables are also subject to control-flow analysis.

File **`ElseRecordDemo.java`**:

```java
public class ElseRecordDemo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        if (!(value instanceof Point(int x, int y))) {
            return "Other";
        } else {
            return "Point=" + x + "," + y;
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(null));
    }
}
```

Run with JDK 21+:

```bash
javac ElseRecordDemo.java
java ElseRecordDemo
```

Output:

```text
Point=2,3
Other
```

The variables `x` and `y` are extracted **only when the record pattern `Point(int x, int y)` matches**. If the negated condition is false, the original pattern is true; hence both variables are in scope in `else`. When `value` is null, the outer `Point(...)` pattern does not match, so it enters the `if` branch.

**Version constraint:** `instanceof String s` has been a standard feature since Java 16 and works normally on Java 17. Record patterns are a standard feature since Java 21. The `ElseRecordDemo` code does not compile on Java 17 as a standard feature.

## 12. Common mistakes and fixes

| Mistake or misconception | Cause | Correct approach |
| --- | --- | --- |
| Using `s` in else of `if (o instanceof String s)` | Else corresponds to a failed match | Use the original object or a different branch; only use `s` when definitely matched |
| Thinking `!(o instanceof String s)` lets you use `s` in the if branch | Inverting true/false does not make the pattern match | Use `s` in else or after a guard clause with return/throw |
| Using `s` in else of `o instanceof String s && check(s)` | false could be due to `instanceof` failing | Split into separate branches or use an appropriate negated expression with `||` |
| Using `s` in the then branch of `o instanceof String s || fallback` | true could be solely due to fallback | Split conditions; do not assume every path assigned `s` |
| Using `s` after if-else even though both branches continue | Cannot know whether the taken path matched | Make the non-matching branch terminate, or only use `s` inside the guaranteed branch |
| Assuming `else if` always sees all variables from the previous condition | Each `else if` is an if nested in else, depending on incoming flow | Check the outer if condition; with `!(... instanceof T t)`, the variable can be used in else-if |
| Thinking null gives the pattern variable a null value in else | For `instanceof` type patterns, null does not match | Handle null via the non-matching branch; do not dereference an unmatched pattern variable |

During code review, a simple self-check is to **list every way the if condition can be false**. If there is even one way where the pattern has not matched, the pattern variable cannot be used in `else`.

## 13. Self-check

**Question 1.** Which snippet compiles?

```java
// (A)
if (obj instanceof String s) {
    use(s);
} else {
    use(s); // ?
}

// (B)
if (!(obj instanceof String s)) {
    fallback();
} else {
    use(s); // ?
}
```

Assume `obj` is `Object`, and `use`/`fallback` are appropriately declared methods. **Answer:** (A) fails to compile because else only runs after the pattern fails to match; (B) is valid because else only runs when the original pattern matched. The snippets are **illustrative code, not standalone programs**.

**Question 2.** Why does this snippet fail in else?

```java
if (obj instanceof String s && s.length() > 5) {
    System.out.println("long");
} else {
    System.out.println(s); // ?
}
```

**Answer:** The path into else can be `obj` not being a String (pattern unmatched) or a String with length ≤ 5 (pattern matched). Because a match is not guaranteed on **every** path, `s` is not in scope in else.

**Question 3.** Why can the following snippet use `s` in else?

```java
if (!(obj instanceof String s) || s.isEmpty()) {
    System.out.println("missing or empty");
} else {
    System.out.println(s.toUpperCase());
}
```

**Answer:** For the OR condition to be false, **both sides must be false**: `obj` is definitely a String and `s.isEmpty()` is false. Therefore `s` is already assigned when entering else.

## 14. Official references

For Java 17/21, these rules are specified in the JLS:

- [JLS 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): the `definitely matched` concept, pattern variable scope.
- [JLS 21 §6.3.1.1–6.3.1.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1): how `&&`, `||`, and `!` introduce variables when true/false.
- [JLS 21 §6.3.2.2 — if Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.2): pattern variable rules in if branches, else branches, and after if-else.
- [JLS 21 §15.20.2 — instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): matching conditions of `instanceof`.

**Conclusion:** A pattern variable is in scope in `else` when **the if condition being false implies the pattern matched**. For a direct `instanceof`, that is usually not the case; for `!(... instanceof T t)`, it is. When combining `&&`, `||`, `else if`, or continuing after if-else, reason over all program paths and the *definitely matched* rules, not just curly braces.
