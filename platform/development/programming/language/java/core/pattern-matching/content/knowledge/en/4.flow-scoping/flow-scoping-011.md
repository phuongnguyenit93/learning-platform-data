# Relationship between reachability and definite matching in Java

**Topic:** Flow scoping of pattern variables, placed in the context of control-flow analysis in the Java Language Specification (JLS). The examples use Java 17 or later and focus on `instanceof`; the corresponding rules are presented according to JLS Java SE 21. No preview features need to be enabled.

A common question: **Why can a variable declared in `instanceof` be used after an `if` statement in one place, while in another place Java reports that the variable does not exist?** To answer this accurately, we need to distinguish three concepts analyzed by the compiler:

1. **Reachability:** is the statement considered *reachable* according to the static rules of the JLS?
2. **Can complete normally:** can the statement finish and transfer control to the statement immediately following it without completing abruptly via `return`, `throw`, or another control transfer?
3. **Definite matching:** at a given point in the control flow, does the compiler know for certain that the pattern has matched and the **pattern variable** has received a value?

These are three related analyses, but they are **not identical**. A statement can be *reachable* while a pattern variable is still **not definitely matched** at that point.

## 1. Reachability according to JLS `14.22

**Reachability** answers the question: *Is there a structurally valid path from the beginning of the method, constructor, or initializer block to this statement?*

JLS `14.22 defines static rules for determining reachability. A statement considered **unreachable** causes a compile-time error. This analysis is primarily based on statement structure and the ability to complete normally, not on a tool that predicts all runtime values.

Example that **does not compile**:

```java
static void unreachableExample() {
    return;
    System.out.println("Never reached here"); // Unreachable statement
}
```

The `println` line stands immediately after `return` in the same block. There is no normal path to it, so the compiler reports an error.

### Reachability is a conservative analysis, not a runtime simulation

Compare two **independent illustrative** snippets:

```java
static void accepted() {
    if (false) {
        System.out.println("Never printed");
    }
}
```

The `if (false)` snippet above is accepted by Java; the `if` body does not execute in practice, but the reachability rules for `if` still consider it reachable.

```java
// DOES NOT COMPILE:
static void rejected() {
    while (false) {
        System.out.println("Unreachable");
    }
}
```

With `while (false)`, the JLS has a special rule that causes the loop body to be considered unreachable. This difference shows that you cannot replace the JLS definition with the intuition of “which statement will actually run”.

## 2. “Can complete normally” connects reachability with flow scoping

In JLS `14.22, a statement **can complete normally** if, according to the language rules, it can finish so that control flow continues to the next statement.

- A `return` or `throw` statement does not complete normally: it leaves the method or throws an exception.
- A valid `break` statement transfers control out of the construct it targets; having a **reachable** `break` is an important factor in loop completion and pattern scope rules.
- An `if` statement can complete normally if there is a valid path through the `if` construct without abrupt completion.
- For loop constructs, the special rules of `while`, `for`, and `do` determine whether it is possible to exit the loop normally.

Example:

```java
static String check(Object obj) {
    if (!(obj instanceof String text)) {
        return "Not a string";
    }
    return text.toUpperCase(); // Valid
}
```

The reason `text` is valid after `if` is **not** merely because the `return text.toUpperCase()` line is reachable. What matters is that **every path continuing after the `if` has already had the `String text` match succeed**. The failing path ended with `return`, so it cannot reach the final line.

If `return` is removed from the failing branch:

```java
// DOES NOT COMPILE:
static void broken(Object obj) {
    if (!(obj instanceof String text)) {
        System.out.println("Not a string");
    }
    System.out.println(text.length()); // text is not definitely matched
}
```

The last line is **reachable**, but there is a path to it when `obj` is not a `String`. Therefore, `text` is not within the scope proven to have matched. Replacing a flow-terminating statement with a statement that only prints a message changes the flow scoping rules.

## 3. What is definite matching according to JLS `6.3?

**Definite matching** is the static guarantee that, at the position where a pattern variable is to be used, the match that produces that variable has definitely succeeded. In the JLS, these rules primarily describe how a variable is **introduced by** an expression **when true**, **when false**, or by a statement; that variable is **definitely matched** at the appropriate positions.

A simple check:

```java
obj instanceof String text
```

This “introduces” the variable `text` **when true**: if the entire expression is true, `obj` has matched the type pattern `String text` and `text` holds the corresponding reference. If false, there is no guarantee about `text`.

When negated:

```java
!(obj instanceof String text)
```

The variable `text` is introduced **when false**, because when the negated expression is false, the inner `instanceof` check must be true. This explains why `if (!(...)) return;` can bring the variable into scope for use after the `if`.

### A brief comparison table

| Analysis | Question | Example |
| --- | --- | --- |
| **Reachability** (`14.22) | Is there a path to the **statement**? | A statement after `return` is unreachable. |
| **Can complete normally** (`14.22) | Can the statement proceed to the next statement? | A branch containing only `throw` cannot complete normally. |
| **Definite matching** (`6.3) | Has the pattern variable definitely been initialized because the match succeeded? | After `if (!(obj instanceof String s)) return;`, `s` is definitely matched. |
| **Definite assignment** (`16) | Has a regular local variable definitely been assigned a value before being read? | `int n;` can only be used when every valid path has assigned `n`. |

**Definite matching and definite assignment are not two names for the same check.** The rules for a pattern variable and its scope are in `6.3; the definite assignment rules for regular local variables are in `16.

## 4. Definite matching in conditional expressions: `&&`, `||`, and `!`

### 4.1. With `&&`: the true path on the left-hand side

```java
static boolean isLongString(Object obj) {
    return obj instanceof String text && text.length() >= 4;
}
```

The right-hand side of `&&` is evaluated only if the left-hand side is true. At the time `text.length()` runs, `String text` has already matched, so `text` is **definitely matched** there.

Conversely:

```java
// DOES NOT COMPILE:
static boolean invalid(Object obj) {
    return obj instanceof String text || text.isBlank();
}
```

The right-hand side of `||` runs when the left-hand side is **false**, which is precisely when `text` is not guaranteed to have a value. This error is a scoping/definite matching error, unrelated to unreachable statements.

### 4.2. With `!` and `||`: a negated condition can make `||` valid

The `!` operator flips how **when true/when false** information is propagated:

```java
static String usableText(Object obj) {
    if (!(obj instanceof String text) || text.isBlank()) {
        return "missing";
    }
    return "valid: " + text;
}
```

This snippet is **valid**:

1. The right-hand side `text.isBlank()` of `||` only runs when `!(obj instanceof String text)` is **false**, meaning `String text` has matched.
2. When the entire `if` condition is **true**, the method returns `"missing"` and terminates.
3. Only when the `if` condition is **false** does the program reach the final line, and at that point `text` has definitely matched and is not blank.

This is a direct example of how definite matching depends on both the **logical value of the expression** and the **ability to complete normally** of the enclosing statement.

### 4.3. The ternary expression `?:`

```java
static String label(Object obj) {
    return obj instanceof String text ? text.toUpperCase() : "other";
}
```

`text` is definitely matched in the middle branch (the **true** branch); it cannot be assumed to have matched in the `"other"` branch. Parentheses around an expression do not break matching information, whereas assigning the expression's result to another `boolean` variable does not by itself create a new pattern scope.

## 5. Relationship in `if`: reachable branch vs. definitely matched branch

### 5.1. Inside the `then` branch of `instanceof`

```java
static void show(Object obj) {
    if (obj instanceof String text) {
        System.out.println(text.length()); // Valid
    } else {
        System.out.println("other");
        // text is not in scope here.
    }
}
```

The `then` branch is reachable and has the match condition true; `text` is definitely matched inside it. The `else` branch may also be reachable, but has no match guarantee.

### 5.2. After `if` with a terminating failure path

```java
static int requireLength(Object obj) {
    if (!(obj instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.length(); // Valid
}
```

According to `6.3.2.2`, a variable introduced **when false** by the `if` condition expression can be introduced by the `if` statement itself when the `then` branch body **cannot complete normally**. After this `if` statement, every continuing path corresponds to the negated expression being false, meaning the pattern has matched.

### 5.3. After `if / else` with only one branch able to continue

```java
static String requireText(Object obj) {
    if (obj instanceof String text) {
        System.out.println("Matched");
    } else {
        throw new IllegalArgumentException("Expected String");
    }
    return text; // Valid
}
```

JLS `6.3.2.2` allows a pattern variable from the **true** condition branch to be introduced after `if / else` when the `then` branch can complete normally while the `else` branch cannot. The symmetric case also exists: a variable introduced by the **false** condition can appear after `if / else` if the `then` branch cannot complete normally while `else` can.

**Key takeaway:** Writing `if (obj instanceof String text)` does not automatically mean `text` always exists after the `if` statement. You must consider **every path that can reach the point of use**, especially which branch terminates with `return` or `throw`.

## 6. Relationship in `while` and `for`: the role of a reachable `break`

### 6.1. `while` without a `break` exiting the loop

```java
static String untilString(Object initial) {
    Object current = initial;
    while (!(current instanceof String text)) {
        current = "ready";
    }
    return text; // Valid: the loop only completes normally when the pattern matches.
}
```

On each condition check, when `current` is not a `String`, the negated condition is true and the loop runs. If the loop completes normally by the condition becoming **false**, `current instanceof String text` was true, so `text` is definitely matched after the loop.

JLS `6.3.2.3` uses a very specific condition: the pattern variable is introduced **when false** by the loop condition expression and **there is no reachable `break` targeting the loop**. In the example above, the loop body assigns `current = "ready"`, ensuring an exit case and keeping the example finite.

### 6.2. Adding a reachable `break` loses the post-loop guarantee

```java
// DOES NOT COMPILE:
static void brokenLoop(Object initial) {
    Object current = initial;
    while (!(current instanceof String text)) {
        if (current == null) {
            break; // Can exit without matching String text.
        }
        current = "ready";
    }
    System.out.println(text); // Not definitely matched.
}
```

The `break` can take execution to the final line with `current == null`, meaning `text` has no value. Consequently, the compiler does not allow using `text` after the loop.

Subtle point: the JLS checks whether `break` is **reachable according to static rules**. It does not require proving from runtime data that the `break` branch will actually occur. A `break` targeting another loop or another label must be analyzed according to its actual control target.

### 6.3. With the basic `for` loop

The rules in `6.3.2.5` are similar: a variable introduced by the condition **when true** can be used in the loop body and update section; to use a variable **after the loop** from the **when false** condition, the rule regarding a reachable `break` targeting that loop must also be satisfied.

```java
static String basicFor(Object initial) {
    Object current = initial;
    for (; !(current instanceof String text); current = "done") {
        // Empty body, no break.
    }
    return text; // Valid after the negated condition becomes false.
}
```

With `do...while`, the JLS also considers variables introduced **when false** by the condition, along with the reachable `break` rule. However, the `do` body executes before the condition is evaluated for the first time; you cannot arbitrarily use a variable declared in the condition inside the loop body.

## 7. Reachable is not enough: two easily confused situations

### Situation A: the statement is reachable, but the pattern is not guaranteed to match

```java
// DOES NOT COMPILE:
static void notDefinitelyMatched(Object obj) {
    if (obj instanceof String text) {
        System.out.println("String");
    }
    System.out.println(text.length());
}
```

The final line is reachable in both cases—whether `obj` is a `String` or not. Precisely because there is a **non-matching** path reaching it, `text` is not definitely matched.

### Situation B: storing the `instanceof` result in a `boolean` does not preserve the variable's scope

```java
// DOES NOT COMPILE:
static void booleanAlias(Object obj) {
    boolean matches = obj instanceof String text;
    if (matches) {
        System.out.println(text.length());
    }
}
```

The runtime reasoning “if `matches` is true then `text` has matched” sounds reasonable, but the JLS does not propagate definite matching through an **intermediate `boolean` variable** in this way. The pattern variable `text` is introduced by the `instanceof` expression at its corresponding position; it does not become in scope elsewhere merely by saving the check result.

The right approach is to keep the `instanceof` expression in the condition that permits using the variable:

```java
static void directCheck(Object obj) {
    if (obj instanceof String text) {
        System.out.println(text.length());
    }
}
```

## 8. Distinguishing definite matching from definite assignment (`16)

A regular local variable must be **definitely assigned** before it is read:

```java
static int lengthOrZero(Object obj) {
    int result;

    if (obj instanceof String text) {
        result = text.length();
    } else {
        result = 0;
    }

    return result; // Valid: result is assigned in both branches.
}
```

At `return result`, `result` is definitely assigned because both branches assigned it. However, `text` is only definitely matched inside the `then` branch; `text` cannot be used on that return line.

Similarly, a snippet does not compile if the assignment in the `else` branch is omitted:

```java
// DOES NOT COMPILE:
static int incomplete(Object obj) {
    int result;
    if (obj instanceof String text) {
        result = text.length();
    }
    return result; // Variable result might not have been initialized.
}
```

**Definite assignment** guards against reading an unassigned local variable; **definite matching** determines which parts of a program may reference a variable declared from a successful pattern match. Both depend on static paths, but they are specified in different JLS chapters.

## 9. Complete program: comparing the rules

Create a file named **`ReachabilityMatchingDemo.java`** with the code below. The example uses only stable features in Java 17:

```java
public class ReachabilityMatchingDemo {
    static String describe(Object value) {
        // The non-matching branch ends with return.
        if (!(value instanceof String text)) {
            return "not-string";
        }
        // Only the matched path can reach here.
        return "String: " + text.toUpperCase();
    }

    static String guarded(Object value) {
        // && is not the only way to use a pattern variable safely.
        // After negation, the right side of || only runs when String has matched.
        if (!(value instanceof String text) || text.isBlank()) {
            return "missing";
        }
        return "valid: " + text;
    }

    static String scanUntilString(Object initial) {
        Object current = initial;
        while (!(current instanceof String text)) {
            current = "ready"; // No break exiting the loop.
        }
        return "loop: " + text;
    }

    static String ifElse(Object value) {
        if (value instanceof String text) {
            System.out.println("inside: " + text.length());
        } else {
            throw new IllegalArgumentException("need String");
        }
        return "after-if: " + text;
    }

    static int lengthOrZero(Object value) {
        int result;
        if (value instanceof String text) {
            result = text.length();
        } else {
            result = 0;
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(42));
        System.out.println(guarded("ABC"));
        System.out.println(guarded("  "));
        System.out.println(guarded(2));
        System.out.println(scanUntilString(5));
        System.out.println(scanUntilString("ok"));
        System.out.println(ifElse("flow"));
        System.out.println(lengthOrZero("hello"));
        System.out.println(lengthOrZero(null));
    }
}
```

Compile and run in the directory containing the file with **JDK 17 or later**:

```bash
javac --release 17 -encoding UTF-8 ReachabilityMatchingDemo.java
java ReachabilityMatchingDemo
```

Output:

```text
String: JAVA
not-string
valid: ABC
missing
missing
loop: ready
loop: ok
inside: 4
after-if: flow
5
0
```

**Reading the output by control flow:**

1. `describe("java")` bypasses the `return` branch for non-matching values; `text` is used safely on the following line.
2. `describe(42)` terminates immediately in the non-matching branch.
3. `guarded("ABC")` demonstrates that negation and `||` allow checking `text.isBlank()`; a non-blank string reaches the final line.
4. `guarded("  ")` returns `missing` because `text` matches but is blank; `guarded(2)` also returns `missing` because it does not match.
5. Both calls to `scanUntilString` finish when the negated condition becomes `false`; there is no `break` exiting with an unmatched pattern.
6. `ifElse("flow")` goes through the `then` branch, which can complete normally; the `else` branch only throws an exception, so `text` can be used after the `if` statement.
7. `lengthOrZero` clearly illustrates the difference: `result` is definitely assigned at the end, whereas `text` is only in scope inside the matching branch.

## 10. How to reason about any piece of code

When you see a pattern variable used after an `if` or a loop, check in order:

1. **Declaration site:** which pattern declares the variable, such as `obj instanceof String text`?
2. **Certain logical branch:** is the match introduced **when true** or **when false**? Do `!`, `&&`, `||`, or `?:` change where it may be used?
3. **Control flow:** to reach the point where the variable is used, can the program take a path where the pattern fails?
4. **Normal completion:** does the failing branch have a `return` or `throw` and cannot continue? For `if / else`, which branch continues?
5. **Loops:** is there any reachable `break` targeting the loop itself that allows exiting without the condition becoming false?
6. **Statement reachability:** is the statement using the variable reachable? If not, that is a separate unreachable statement error; if so, definite matching still needs to be checked.
7. **Regular variables:** if the code also uses regular local variables like `result`, check the definite assignment rules as well.

Try predicting before compiling:

**Exercise A.** Is the following snippet valid?

```java
static int testA(Object obj) {
    if (!(obj instanceof String s)) return -1;
    return s.length();
}
```

**Answer:** Yes. Only a successful match reaches `s.length()`.

**Exercise B.** Is the following snippet valid?

```java
// DOES NOT COMPILE:
static int testB(Object obj) {
    if (obj instanceof String s) {
        System.out.println("yes");
    }
    return s.length();
}
```

**Answer:** No. `return` is reachable, but the non-matching branch also reaches that line; `s` is not definitely matched.

**Exercise C.** Why can simply adding a `break` to the body of `while (!(obj instanceof String s))` remove the ability to use `s` after the loop?

**Answer:** Because a reachable `break` can transfer control out of the loop before the condition expression becomes `false`. At the point after the loop, there is no longer a guarantee that `instanceof String s` ever succeeded.

**Exercise D.** What happens if `if (!(obj instanceof String s)) return;` is changed to `if (!(obj instanceof String s)) System.out.println("skip");`?

**Answer:** The failing branch can complete normally. After the `if`, `s` is no longer guaranteed by definite matching; using `s` there causes a compile-time error.

## 11. Reasoning pitfalls to avoid

- **Equating “reachable” with “matched”.** Reachability checks whether there is a path to a statement; definite matching checks whether a pattern variable is guaranteed to be bound on that path.
- **Assuming that just because code “won't actually run” the compiler knows it too.** The JLS uses explicit structural rules, not arbitrary inferences from runtime state.
- **Overlooking the concept of “can complete normally”.** This property is what determines whether a pattern variable can be brought out after `if`/`if-else`.
- **Forgetting the impact of a reachable `break` in a loop.** An additional exit path can prevent the pattern from being definitely matched after the loop.
- **Confusing `definite matching` with `definite assignment`.** Pattern variables and regular local variables follow their respective rules in `6.3` and `16`.
- **Extracting a pattern condition into a `boolean` variable and expecting to still access the pattern variable.** Scope must follow the expression/statement forms specified by the JLS; there is no general `boolean` alias inference mechanism.
- **Misusing `&&`/`||`.** Consider which logical branch causes the right-hand side to run; `a instanceof String s && s.length() > 0` is valid, whereas the unnegated `||` version is not.

## Official specifications

- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow scoping, *introduced by*, *definitely matched*, and rules for `if`/loops.
- [JLS Java SE 21 `14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22): reachability and *can complete normally*.
- [JLS Java SE 21 `16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se21/html/jls-16.html): definite assignment analysis for local variables.
- [JLS Java SE 21 `15.20.2 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): type-matching condition.
- [JLS Java SE 21 `14.9 — `if` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.9), [`14.12 — `while` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.12): control-flow rules analyzed when determining definite matching.
