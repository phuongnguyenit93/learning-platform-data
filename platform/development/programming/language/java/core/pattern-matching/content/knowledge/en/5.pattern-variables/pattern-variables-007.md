# Pattern Variables in Guards: Condition Checking and Scope Guarantees in Java

## 1. Pattern Variables and the Guard Concept

A **pattern variable** is a variable introduced when a **pattern** matches a value. For example, since Java 16, **instanceof** supports type patterns:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

The expression **value instanceof String text** checks that **value** refers to a non-**null** **String** object. If true, **text** is bound to that object and has the static type **String**. If false, **text** is not bound; the compiler does not allow using the variable on execution paths where a successful match is not guaranteed.

In the context of pattern matching, the term **guard** has two related uses:

- **Guard clause**: checks an invalid case and exits early with **return** or **throw**. When a guard eliminates all non-matching paths, subsequent code can use the pattern variable.
- **Guard condition of a pattern in switch**: since **Java 21**, the syntax **case Type variable when condition -> ...** selects the branch only when both the pattern matches and the **when** condition holds. The pattern variable can be used in the **when** expression and in the body of the branch.

Both mechanisms rely on the rule that **a variable is valid only where the compiler has proven the match succeeds**. However, they differ in syntax, placement, and supported Java versions. The Java 17 section below explains guard clauses and logical conditions; the Java 21 section introduces **when** in **switch**.

## 2. Guard Clauses with instanceof: Exit on Invalid Cases

Suppose a method accepts **Object**, but only processes the input when it is a **String**. The legacy approach requires checking and then casting:

~~~java
static int legacyLength(Object value) {
    if (!(value instanceof String)) {
        return -1;
    }
    String text = (String) value;
    return text.length();
}
~~~

The version using a pattern variable and a guard clause:

~~~java
static int patternLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
~~~

Reading the control flow from top to bottom:

1. If **value** is not a **String** or is **null**, the **instanceof** expression evaluates to **false**, negating with **!** yields **true**, and the method returns **-1**.
2. If execution reaches **return text.length()**, the early-exit branch did not run. That happens only when **value instanceof String text** is **true**.
3. The compiler therefore allows **text** to appear after the **if** block, with static type **String**; no manual cast is needed.

This is the benefit of **flow scoping**: the scope of a pattern variable depends on **program control flow**, not merely curly braces.

If you omit **return** in the non-matching branch, that conclusion no longer holds:

~~~java
// Intentionally WRONG example; cannot be compiled as a complete method.
if (!(value instanceof String text)) {
    System.out.println("Not a string");
}
System.out.println(text.length()); // Error: an unmatched path still exists
~~~

A guard clause establishes proof only when the failure case **cannot continue** to the point where the variable is used. **throw** also accomplishes this; a **println** statement or setting a status flag does not.

## 3. Combining Guards with && and ||

Both **&&** and **||** use short-circuit evaluation from left to right:

- For **left && right**, the right-hand side is evaluated only when the left-hand side is **true**.
- For **left || right**, the right-hand side is evaluated only when the left-hand side is **false**.

A **positive** guard condition typically uses **&&**:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

The right-hand side uses **text** safely because it runs only when **instanceof** has matched. If **value** is **null** or another type, **text.isBlank()** is never called.

A **negated** guard condition typically uses **||** combined with an early exit:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "(no string)";
    }
    return text.strip();
}
~~~

The expression **!(value instanceof String text)** is true when there is no match. If that happens, **||** stops immediately and **text.isBlank()** does not run. Conversely, the right-hand side of **||** is evaluated only when the negation is false, meaning **instanceof** matched and **text** is in scope.

When the entire guard condition is **false**, we know both:

- **value** is a non-**null** **String** and **text** has been bound.
- **text.isBlank()** is **false**.

Because the **true** branch executed **return**, the code after the guard is allowed to use **text**. Do not confuse this with the following expression:

~~~java
// WRONG: when instanceof on the left-hand side is false, the right-hand side of || must run,
// but the pattern variable text has not been bound yet.
if (value instanceof String text || text.isBlank()) {
    System.out.println("...");
}
~~~

The right rule is to **check whether each execution path guarantees the variable has matched**, not to memorize that **&&** is always valid and **||** is always invalid. **||** in the negated guard above is completely valid.

Another example with multiple **&&** conditions:

~~~java
if (value instanceof String text
        && text.startsWith("ID-")
        && text.length() > 3) {
    System.out.println("ID: " + text.substring(3));
}
~~~

Each right-hand condition is evaluated after the left-hand conditions return **true**. Type safety for **text** is preserved throughout the condition chain. However, **instanceof** only verifies the type; the **"ID-"** prefix and length rules are business checks that must be written explicitly.

## 4. Complete Example with Java 17

Save the file **PatternGuardDemo.java**:

~~~java
public class PatternGuardDemo {
    static String summarize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isBlank()) {
            return "blank";
        }

        String normalized = text.strip();
        if (normalized.length() < 3) {
            return "too short";
        }
        return "ok: " + normalized;
    }

    static String category(Object value) {
        if (value instanceof String text && text.startsWith("ID-")) {
            return "id: " + text.substring(3);
        }
        if (value instanceof Integer count && count >= 0) {
            return "non-negative: " + count;
        }
        return "unmatched";
    }

    static String singleGuard(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "missing";
        }
        return "text: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(summarize("  Java  "));
        System.out.println(summarize("   "));
        System.out.println(summarize(9));
        System.out.println(summarize(" A "));

        System.out.println(category("ID-42"));
        System.out.println(category(3));
        System.out.println(category(-1));
        System.out.println(category(null));

        System.out.println(singleGuard("  ok "));
        System.out.println(singleGuard("  "));
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 PatternGuardDemo.java
java PatternGuardDemo
~~~

Expected output:

~~~text
ok: Java
blank
not a string
too short
id: 42
non-negative: 3
unmatched
unmatched
text: ok
missing
~~~

**Explanation:** In **summarize**, the first guard rejects **Integer 9**; whitespace-only input is caught by **isBlank()**; the string **" A "** after **strip()** is only one character long so it is caught by the length guard; only **"  Java  "** reaches **ok: Java**. In **category**, the **&&** conditions allow checking the prefix or the sign of the number right after matching **String** or **Integer**. **-1** and **null** do not match any branch. In **singleGuard**, negating the pattern together with **||** guarantees that code after **return** only processes non-blank strings.

The program uses pattern matching for **instanceof** (standard since Java 16), **String.isBlank()**, and **String.strip()** (Java 11+). There is no preview syntax and Java 21 is not required.

## 5. When Is a Pattern Variable Valid After a Guard?

Comparison of cases:

| Construct | Can the variable be used at the corresponding position? | Reason |
| --- | --- | --- |
| **if (obj instanceof String s) { use s; }** | Yes, inside the true branch | The branch runs only when matched |
| **if (obj instanceof String s && s.length() > 0)** | Yes, on the right-hand side of **&&** and in the true branch | The right-hand side runs only when **instanceof** is true |
| **if (!(obj instanceof String s)) return; use s;** | Yes, after the guard | The non-matching path has terminated |
| **if (!(obj instanceof String s) || s.isBlank()) return; use s;** | Yes, on the right-hand side of **||** and after the guard | The right-hand side runs only when matched; the failure branch exited |
| **if (!(obj instanceof String s)) println(...); use s;** | No, in the statement after **if** | The non-matching path can still continue |
| **if (obj instanceof String s || s.isBlank())** | No, on the right-hand side of **||** | The right-hand side runs when **instanceof** is false |

The snippets in the table are **syntax patterns for comparison**, not standalone runnable programs. In the sample expressions, **use s** indicates where the variable is used.

A common misconception is that a **guard clause** automatically turns a pattern variable into a global or method-wide variable. After a guard with **return**, the compiler allows the variable to exist in the remaining reachable code; if control flow changes—for instance, replacing **return** with a logging statement—the valid scope changes as well.

### Using throw When Data Has the Wrong Type

If an API strictly requires a string input, it can throw an exception instead of returning a fallback value:

~~~java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a non-null String");
    }
    return text.strip();
}
~~~

**throw** terminates the non-matching path, so **text** is valid in the **return** statement after the guard. This is an **illustrative method snippet**, not a standalone program. The exception message makes clear that **null** is not accepted either.

## 6. Switch Pattern Guards with when — Java 21+

Since **Java 21**, pattern matching for **switch** is a standard feature. You can add a guard condition directly to a **case** label using the **when** keyword:

~~~java
case String text when text.isBlank() -> "blank";
~~~

Its semantics consist of two steps: first, the switch checks whether the value matches **String text**; only if it matches does it evaluate **text.isBlank()**. If the guard evaluates to **false**, the switch continues checking subsequent **case** labels. The variable **text** has static type **String** both in the **when** expression and in the body of the selected branch.

Save the file **WhenGuardDemo.java** and compile with **JDK 21+**:

~~~java
public class WhenGuardDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text when text.length() >= 5 ->
                    "long: " + text.strip();
            case String text -> "short: " + text.strip();
            case Integer number when number >= 0 ->
                    "non-negative: " + number;
            case Integer number -> "negative: " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("    "));
        System.out.println(classify("Java SE"));
        System.out.println(classify("ok"));
        System.out.println(classify(3));
        System.out.println(classify(-4));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 WhenGuardDemo.java
java WhenGuardDemo
~~~

Output:

~~~text
blank
long: Java SE
short: ok
non-negative: 3
negative: -4
null
~~~

The three **String** labels are ordered from specific conditions to the unguarded branch. If **case String text -> ...** appeared before the **String ... when ...** labels, the later labels would be shadowed by the general branch and the compiler could report a **dominated case** error.

**case null** must be handled explicitly if you want to return **"null"**: the **default** branch does not replace **null** handling in pattern switches. **when** expressions must produce a boolean; if the guard does not hold, the switch looks for the next case branch. A guard can call methods, so avoid unpredictable side effects or operations that may throw unhandled exceptions. In particular, **when** on a pattern variable of a type does not prove that fields inside that object are non-**null**.

**Version distinction:** **instanceof String text** and guard clauses run on Java 17; the **case String text when ...** syntax is a standard Java 21 language feature. Do not put **when** examples into code compiled with JDK 17 because it will not compile.

## 7. Common Mistakes and How to Avoid Them

**Mistake 1 — Using the variable in the non-matching branch.** Writing **if (!(obj instanceof String s)) { System.out.println(s); }** is invalid: this body runs when the **String** match fails. Use **s** only after exiting the failure branch, or inside a branch proven to match.

**Mistake 2 — Placing business conditions before the type check.** The expression **s.length() > 0 && obj instanceof String s** is invalid because **s** has not been introduced on the left-hand side. Put **instanceof String s** first, followed by **s.length() > 0**.

**Mistake 3 — Confusing positive || with negated ||.** **obj instanceof String s || s.isBlank()** is invalid; **!(obj instanceof String s) || s.isBlank()** is valid because **s.isBlank()** needs to run only if the match succeeded. Always check which side is evaluated when the preceding condition is true or false.

**Mistake 4 — Only logging in the guard and then using the variable afterward.** If the non-matching branch only calls **println** and continues, the variable is not guaranteed to be bound. Use **return**, **throw**, or move the processing into the matching branch.

**Mistake 5 — Assuming a type pattern validates the data itself.** **obj instanceof String s** does not verify that a string is non-blank or matches an ID, URL, or email format. Those constraints must be expressed with separate guard conditions and tested for edge cases.

**Mistake 6 — Forgetting null handling.** **null instanceof String s** is **false**, so a negated guard clause typically catches **null** as well. With Java 21 **switch**, if you want to handle **null** as a business state, declare **case null**; do not expect **default** to do that.

**Mistake 7 — Placing a general case before a case with when.** In a Java 21 switch, pattern order affects which branch can be selected and dominance checking. Place specific guarded branches before the unguarded general pattern of the same type.

**Mistake 8 — Using when syntax on JDK 17.** Only Java 21 standardized switch pattern guards with **when**. For Java 17 projects, use **if (obj instanceof T x && condition(x))** or a guard clause before processing.

## 8. Choosing the Right Guard

Use a **guard clause + return/throw** when invalid input types or missing preconditions must halt the entire process. This keeps the rest of the method focused on valid cases and leverages the pattern variable without casting.

Use **&&** when the type check and a few secondary conditions can be expressed concisely in the same **if** without needing separate error messages for each reason.

Use **switch ... case Type variable when condition** when the project uses **Java 21+**, needs to classify multiple types or multiple conditions of the same type, and each branch returns a clear result. Order specific branches before general ones and handle **null** according to the API contract.

When testing the code, include test cases for: matching type with passing guard, matching type with failing guard, non-matching type, **null**, and potentially overlapping case orderings (if using switch). This verifies both business correctness and variable scope.

**Conclusion:** a pattern variable can be used only when the compiler has proof that the match succeeded. In Java 17, guard clauses and short-circuit operators establish that proof through control flow; in Java 21, **when** adds guard conditions directly to switch pattern labels. Understanding scoping properly eliminates redundant casts while preserving type safety and clear execution paths.