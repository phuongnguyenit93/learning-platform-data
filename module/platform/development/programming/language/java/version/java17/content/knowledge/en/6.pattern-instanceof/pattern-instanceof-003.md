# Flow-Based Variable Scope with `instanceof` Patterns in Java 17

## 1. Why Doesn't a Pattern Variable Have the Same Scope as a Regular Local Variable?

Java 17 supports **pattern matching for `instanceof`** as a stable feature. When checking whether an object belongs to a specific type, you can simultaneously declare a **pattern variable** to use the object with its confirmed type.

Previously, we used to write:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

With Java 17, the snippet above can be shortened to:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

The expression `value instanceof String text` both checks the type and introduces the variable `text`. When the match succeeds, `text` has static type `String`, so you can call `length()` without a manual cast. If `value` is not a `String` or is `null`, the match fails and `text` does not hold a usable value.

Notably, **the declaration location alone does not determine everywhere `text` can be used**. The compiler analyzes the execution paths a program can take and only allows access to the variable where the match **is definitely known to have succeeded**. This mechanism is called **flow scoping** — *variable scoping based on control flow*.

> Quick rule of thumb: only use a pattern variable on paths where the compiler determines that the pattern has matched. On paths that do not prove this, the variable is not in scope.

Flow-based scoping is most evident with `if`, `else`, `!`, `&&`, `||`, conditional expressions, and loops. This article focuses on the rules in effect in **Java 17**, requiring no preview features.

## 2. Basic Case: Variable Is in Scope in the Success Branch

Consider a method taking an `Object`:

~~~java
static void printLength(Object item) {
    if (item instanceof String text) {
        System.out.println("Length: " + text.length());
    } else {
        System.out.println("Not a String");
    }
}
~~~

Execution flow:

1. If `item` is a `String`, the pattern matches, `text` is assigned that reference, and it is used in the `if` branch.
2. If `item` is not a `String`, or is `null`, the condition is false and the program runs the `else` branch. In this branch, `text` is **not in scope**.
3. After the entire `if/else` statement, `text` normally cannot be used because the program may have taken the non-matching branch.

Example that **does not compile**:

~~~java
static void invalidScope(Object item) {
    if (item instanceof String text) {
        System.out.println(text.length()); // Valid
    } else {
        // System.out.println(text);     // Error: text is not in scope
    }

    System.out.println(text);             // Compile error
}
~~~

The reason is not merely the `{ }` braces of the `if`: if the condition fails, `text` was never produced from a successful match. Therefore Java disallows using it at the end of the method.

Path diagram:

~~~text
                    item instanceof String text
                             /       \
                         true         false
                          |             |
                 text is usable      text is not
                     in if            usable
                          \             /
                           \           /
                           after if/else
                     text is not guaranteed
~~~

**A `null` reference** always makes `instanceof String text` return `false`; the `instanceof` operator does not throw `NullPointerException` in this case. However, if you call a method on `item` before checking for `null`, that call can still throw an exception as usual.

## 3. The `&&` Operator: The Right-Hand Side Can Use a Variable from the Left-Hand Side

In Java, `&&` is a logical AND with **short-circuit evaluation**. The right-hand side is evaluated only when the left-hand side is true. Therefore, if the left-hand side is an `instanceof` pattern, the right-hand side is allowed to use the pattern variable.

~~~java
static boolean isLongText(Object item) {
    return item instanceof String text && text.length() > 10;
}
~~~

The program evaluates in order:

~~~text
item instanceof String text ?
    ├── false -> returns false, does NOT call text.length()
    └── true  -> text matched; evaluates text.length() > 10
                  ├── false -> returns false
                  └── true  -> returns true
~~~

The following snippet is also valid:

~~~java
if (item instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Here, there are two guarantees upon entering the `if` body: `item` matches `String` and `text` does not contain only whitespace. The right-hand side of `&&` can use `text` because **to reach the right-hand side, the match on the left-hand side must have succeeded**.

The key point is that `&&` allows using the variable on the **right-hand side of the expression**, not that the variable always exists after the entire statement:

~~~java
static void printNonBlank(Object item) {
    if (item instanceof String text && !text.isBlank()) {
        System.out.println(text);
    }

    // System.out.println(text); // Error: pattern match is not guaranteed
}
~~~

### Comparison with the non-short-circuit AND operator

Java also has the `&` operator for booleans. That operator evaluates **both sides**, not only when the left-hand side is true. Therefore, do not replace `&&` with `&` when the right-hand side relies on a pattern variable from the left-hand side:

~~~java
// Invalid: the right-hand side can run even if item is not a String
if (item instanceof String text & text.length() > 3) {
    System.out.println("Long text");
}
~~~

Keep `&&` when the subsequent condition depends on the success of the preceding check.

## 4. The `||` Operator: Why Does a Similar Style Cause an Error?

The OR operator `||` also uses short-circuit evaluation, but **the right-hand side runs only when the left-hand side is false**. If the left-hand side is `item instanceof String text`, then the right-hand side runs precisely when the pattern **did not match**; `text` does not exist on this path.

Example of a **compile error**:

~~~java
// Wrong: text is not in scope on the right-hand side of ||
if (item instanceof String text || text.isEmpty()) {
    System.out.println("Something matched");
}
~~~

Compare directly:

| Expression | When does the right-hand side run? | Can the right-hand side use the pattern variable? |
|---|---|---|
| `item instanceof String text && text.length() > 3` | When `instanceof` is **true** | **Yes** |
| `item instanceof String text || text.isEmpty()` | When `instanceof` is **false** | **No** |

This comes from the **evaluation flow**, not a rule saying "pattern variables work inside all conditional expressions."

However, `||` **can** be used with a pattern variable if we invert the condition using `!` so that the case reaching the right-hand side corresponds to a pattern match:

~~~java
static boolean isMissingOrBlank(Object item) {
    return !(item instanceof String text) || text.isBlank();
}
~~~

Explanation:

- If `item` is not a `String`, `!(item instanceof String text)` is `true`. The `||` operator returns `true` immediately without evaluating `text.isBlank()`.
- If `item` is a `String`, the negation is `false`. Now the right-hand side is evaluated, and `text` **has been produced by a successful match**.

This snippet is both valid and a classic illustration of how a pattern variable's scope **is inferred through logical operations**.

## 5. The `!` Operator Flips the Path Where the Variable Is Guaranteed

Pay attention to the negation operator:

~~~java
if (!(item instanceof String text)) {
    System.out.println("Not a String");
} else {
    System.out.println("String length: " + text.length());
}
~~~

When the `if` branch runs, the `instanceof` expression inside `!` returned `false`. Hence `text` is not in scope in the `if` branch. When the `else` branch runs, the negation returned `false`, corresponding to `instanceof` returning `true`. Variable `text` **is in scope** inside the `else` branch.

We can visualize it as:

~~~text
if (!(item instanceof String text))
                |
                v
         Negation result?
          /            \
       true            false
        |                |
  pattern did         pattern
   not match          matched
        |                |
    if branch        else branch
  cannot use         can use
     text              text
~~~

This differs from a variable declared at the top of a method, which always exists from its declaration point to the end of the appropriate lexical scope. A pattern variable is brought into scope **strictly along paths compatible with a successful match**.

## 6. Guard Clauses: Using a Pattern Variable in Subsequent Statements

A *guard clause* is a branch that checks an invalid condition and exits the method early with `return` or `throw`. Combined with negation `!`, it lets you use the pattern variable in the code **after the `if` statement**.

~~~java
static int requireLength(Object item) {
    if (!(item instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // By this point, item instanceof String has definitely matched.
    return text.length(); // Valid in Java 17
}
~~~

The compiler's reasoning:

1. If the pattern does not match, the `if` condition is true and the program throws an exception. This path **cannot continue** to `return text.length()`.
2. If execution reaches the `return` statement, the exception-throwing branch did not run; that means the pattern must have matched.
3. Therefore, `text` is in scope for the remainder of the method.

Similarly, `return` can be used:

~~~java
static String requireText(Object item) {
    if (!(item instanceof String text)) {
        return "Input is not text";
    }

    return "Input: " + text.strip();
}
~~~

The first `return` branch ends the call. The last line only executes if `text` matched, so the code is valid.

### Why can't `return`/`throw` be omitted?

**Invalid** example:

~~~java
static void badGuard(Object item) {
    if (!(item instanceof String text)) {
        System.out.println("Not text");
    }

    System.out.println(text.length()); // Compile error
}
~~~

The `if` branch in this example only prints a message and then **continues running**. Thus the final line could still receive a non-`String` `item`. The compiler disallows using `text` there.

The deciding factor is not the name "guard", but **whether every continuing path guarantees a successful match**.

### Guard combined with `||`

A common pattern in input-validation code:

~~~java
static String requireNonBlankText(Object item) {
    if (!(item instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "Expected a non-blank String");
    }

    return text.strip();
}
~~~

When exiting the `if` without throwing an exception, both rejection conditions were false. That means `item` matched `String text` and `text` is not blank. `text` is both validly used on the right-hand side of `||` and still in scope after the guard.

Conversely, **you cannot use `text` inside this `if` body** without an additional check: the `if` body could execute simply because `item` is not a `String`, in which case the pattern never matched.

## 7. Variable Scope in Conditional Expressions `? :`

The conditional operator `condition ? valueIfTrue : valueIfFalse` chooses one of two branches based on a boolean value. Therefore, the pattern variable can be used in the branch where the type check is guaranteed to have succeeded.

~~~java
static String display(Object item) {
    return item instanceof String text
            ? "Text: " + text.strip()
            : "Other value";
}
~~~

In the branch after `?`, `instanceof` was true, so `text` can be used. In the branch after `:`, the check failed, so `text` cannot be used:

~~~java
// Invalid: the third branch runs when instanceof is false
String label = item instanceof String text
        ? "Text: " + text
        : text.toString();
~~~

With a negated expression, the guaranteed direction flips:

~~~java
String label = !(item instanceof String text)
        ? "Not a String"
        : text.toUpperCase();
~~~

In the third branch of the last expression, the negation is `false`, meaning `item instanceof String text` actually matched.

A pattern variable does not become a variable outside the entire expression simply because it appeared in one branch of `? :`.

## 8. Scope in `while` Loops

A `while` condition is evaluated before each iteration. If the condition is an `instanceof` pattern, **every entry into the loop body** corresponds to a successful match.

~~~java
static int countStringStages(Object current) {
    int stages = 0;

    while (current instanceof String text) {
        stages++;
        System.out.println("Text stage: " + text);
        current = text.length();
    }

    return stages;
}
~~~

If we call `countStringStages("Java")`:

1. On the first check, `current` is `String`, `text` receives `"Java"`; the loop body runs once.
2. Inside the loop body, `current` is assigned the integer `4` (autoboxed to `Integer` because the variable has type `Object`).
3. On the next check, `current` is `Integer`, so the `String` pattern does not match and the loop ends.

The returned result is `1`. Variable `text` **is in scope inside the `while` body**, but **not in scope after the loop**, because the loop can terminate when the pattern fails or never run at all.

~~~java
while (current instanceof String text) {
    System.out.println(text.length()); // Valid
    current = text.length();
}

// System.out.println(text); // Error: out of scope
~~~

The same rule appears when a loop condition combines `instanceof` and `&&`:

~~~java
while (current instanceof String text && !text.isEmpty()) {
    System.out.println(text);
    current = text.substring(1);
}
~~~

Here, every entry into the loop body guarantees `current` is a **non-empty** string. Calling `substring(1)` shortens the string, so for any finite string input, the loop will terminate.

## 9. Variable Names and Non-Overlapping Scopes

Java avoids "poisoning" a pattern variable name merely because it already appeared in an `instanceof` check. When two patterns have **non-overlapping** scopes, you can reuse the same variable name.

~~~java
static void inspect(Object value) {
    if (value instanceof String data) {
        System.out.println("String: " + data.length());
    }

    if (value instanceof Integer data) {
        System.out.println("Integer: " + data.intValue());
    }
}
~~~

In these two independent `if` statements, the usage regions of `data` do not overlap; `data` in the first branch has type `String`, whereas `data` in the second branch has type `Integer`.

Conversely, you cannot declare two variables with the same name **that are simultaneously in scope**:

~~~java
static void collision(Object value) {
    if (value instanceof String text) {
        // String text = "another"; // Error: collides with pattern variable name
        System.out.println(text);
    }
}
~~~

This demonstrates that flow scoping determines **where a pattern variable is in effect**; within that region, standard variable naming and declaration collision rules still apply.

Prefer meaningful names such as `customer`, `message`, or `list` instead of always using `s` or `x`. Even though reusing a name in two independent regions is legal, if it makes code harder to read, using distinct names is usually better.

## 10. Complete Example Compilable with Java 17

Create directory `src/demo` and file `src/demo/FlowScopeDemo.java` with the following contents:

~~~java
package demo;

public final class FlowScopeDemo {
    private FlowScopeDemo() {
    }

    public static void main(String[] args) {
        Object[] inputs = {"  Java 17  ", "", 42, null};

        for (Object input : inputs) {
            System.out.println(describe(input));
        }

        System.out.println(
                "Validated: " + requireNonBlankText("  hello  "));

        System.out.println(
                "String stages: " + countStringStages("abc"));
    }

    private static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "Text: " + text.strip();
        }

        if (input instanceof String blankText) {
            return "Blank text";
        }

        if (input instanceof Integer number) {
            return "Integer: " + number;
        }

        return input == null ? "null" : "Other object";
    }

    private static String requireNonBlankText(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected a non-blank String");
        }

        return text.strip();
    }

    private static int countStringStages(Object current) {
        int stages = 0;

        while (current instanceof String text) {
            stages++;
            current = text.length();
        }

        return stages;
    }
}
~~~

Directly applied points:

- `describe` uses `&&` to ensure `text` matched before calling `isBlank()`, then proceeds to classify blank strings and integers.
- `requireNonBlankText` uses `!`, `||`, and an exception-throwing guard so that `text` is in scope at the `return` statement.
- `countStringStages` uses `text` inside the `while` body, where every iteration has already satisfied `instanceof String`.
- When the input is `null`, all corresponding `instanceof` checks are false and `describe` selects `"null"`.

### Compile and run

In the root directory containing `src`, run:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/FlowScopeDemo.java
java -cp out demo.FlowScopeDemo
~~~

The `javac` command requires JDK 17 or a newer JDK that supports `--release 17`. The `-d out` option places bytecode in the `out` directory, while `java -cp out` runs the class by its fully qualified package name.

Expected output:

~~~text
Text: Java 17
Blank text
Integer: 42
null
Validated: hello
String stages: 1
~~~

To observe a scope error yourself, try adding `System.out.println(text);` at the end of `describe`, outside all branches. The compiler will reject it because at that location there is no pattern variable named `text` guaranteed to have matched.

## 11. Quick-Reference Table of Flow Scoping Scenarios

The examples below assume `value` is an expression of type `Object`.

| Scenario | Where `s` can be used | Explanation |
|---|---|---|
| `if (value instanceof String s) { ... }` | `if` body | Body runs when match is true. |
| `if (value instanceof String s) { ... } else { ... }` | `if` body; not in `else` | `else` corresponds to a failed match. |
| `if (!(value instanceof String s)) { ... } else { ... }` | `else` branch | Negation inverts the condition. |
| `value instanceof String s && s.length() > 0` | Right-hand side of `&&` | Right-hand side only runs after a true match. |
| `value instanceof String s \|\| s.isEmpty()` | Not usable on the right-hand side; error | Right-hand side runs when match is false. |
| `!(value instanceof String s) \|\| s.isEmpty()` | Right-hand side of `\|\|` | Right-hand side runs when negation is false, i.e., match is true. |
| `if (!(value instanceof String s)) return;` | Statements after the guard in the same scope | Only the true-match path continues. |
| `while (value instanceof String s) { ... }` | `while` body | Every loop entry is a true match. |
| `value instanceof String s ? s.length() : 0` | Second branch of `? :` | Branch is chosen when match is true. |

**Remember:** the table illustrates common positions; Java's exact rules are defined by whether an expression **introduces a pattern variable when true** or **when false**, combined with the control flow of the enclosing statements. Do not infer scope merely from sharing the same curly braces.

## 12. Common Errors and How to Read Their Causes

### 12.1. Using the variable after `if` even though the false branch can still continue

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
// System.out.println(text); // Error
~~~

**Fix:** place the code requiring `text` inside the matching branch, or switch to a negated guard with `return`/`throw` when the pattern does not match.

### 12.2. Using the variable on the right-hand side of `||` without negation

~~~java
// if (value instanceof String text || text.isBlank()) { ... }
~~~

**Fix:** if the goal is "not a String **or** a blank string", write `!(value instanceof String text) || text.isBlank()`. If you want to check "is a String **and** is not blank", write `value instanceof String text && !text.isBlank()`.

### 12.3. Assuming `instanceof` always lets you continue after checking

~~~java
if (!(value instanceof String text)) {
    System.out.println("Invalid value");
}
// System.out.println(text.length()); // Error
~~~

**Fix:** when the value is invalid, terminate the path with `return` or `throw`, if the contract allows. Printing a log and continuing is not enough to prove `text` matched.

### 12.4. Confusing `null` with a matching value

~~~java
Object value = null;

if (value instanceof String text) {
    // Does not run; text does not receive null in this branch.
    System.out.println(text.length());
}
~~~

**Fix:** if `null` is a case that needs handling, check or respond to it according to a separate contract. In Java 17, an `instanceof` pattern does not match `null`.

### 12.5. Confusing `instanceof` patterns with `switch` patterns from newer Java versions

Java 17 finalized pattern matching for `instanceof`. However, pattern matching forms for `switch` in Java 17 are a **preview feature**, requiring preview mode to be enabled when used. This article intentionally uses Java 17's current `instanceof`, `if`, and logical operators; preview `switch` syntax is not needed to practice flow scoping.

### 12.6. Checking a type when the expression already has the exact static type

When an object already has static type `String`, you usually do not need `instanceof String text`. For example, if a parameter is `String input`, use `input` directly or perform appropriate `null` checks. `instanceof` patterns are most useful at boundaries working with `Object`, supertypes, or interfaces where multiple implementations may appear.

## 13. Practice Exercises

### Exercise 1 — Predict valid positions

Assume `Object input`:

~~~java
if (input instanceof String s && s.length() > 3) {
    System.out.println(s);
} else {
    // Can s be used here?
}
// Can s be used here?
~~~

Explain each position based on the paths where the `instanceof` condition is true or false.

### Exercise 2 — Fix the `||` error

The following snippet is invalid:

~~~java
if (input instanceof String s || s.isBlank()) {
    System.out.println("Invalid");
}
~~~

Fix it so the condition means: **the input value is not a `String` or is an empty/blank string**. Then explain why the right-hand side of `||` can use `s` in the new version.

### Exercise 3 — Refactor to a guard

Starting from this code:

~~~java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.strip());
    } else {
        throw new IllegalArgumentException("Not a String");
    }
}
~~~

Rewrite it using `if (!(input instanceof String text))` and a guard that throws an exception so the print statement moves **after** the `if`. Explain why `text` remains in scope.

### Exercise 4 — Loop and termination

Add to a method:

~~~java
Object current = "abcd";
int count = 0;
while (current instanceof String s && !s.isEmpty()) {
    count++;
    current = s.substring(1);
}
System.out.println(count);
~~~

Predict the printed value and explain what happens when `current` becomes the empty string. Can `s` be used in the `println` statement after the loop?

### Exercise 5 — Conditional expression paths

Write a `? :` expression that returns the string's length if `input` is a `String`, or `-1` otherwise. Then try modifying it to use the pattern variable in the `false` branch and explain why that version is invalid.

### Suggested Answers

1. `s` is usable in the `if` body and on the right-hand side of `&&`; it is not guaranteed in `else` or after the entire `if`.
2. Write `if (!(input instanceof String s) || s.isBlank())`. When the right-hand side runs, the negation was false, so the pattern matched.
3. Write the guard `if (!(input instanceof String text)) { throw ...; }` followed by `System.out.println(text.strip());`. The non-matching branch cannot reach the print statement.
4. The value of `count` is `4`. When the string becomes empty, `!s.isEmpty()` is false and the loop stops. `s` is not in scope after the loop.
5. `input instanceof String s ? s.length() : -1`. The third branch only runs when the pattern did not match, so `s` cannot be used in that branch.

## 14. Mindset for Applying This in Real Source Code

Flow scoping encourages code that clarifies the relationship between **conditions** and **validated data**. When reading a branch:

- With `&&`, ask: **what must be true to evaluate the right-hand side?**
- With `||`, ask: **what must be false to evaluate the right-hand side?**
- With `!`, remember that the true/false outcome of the outer expression is inverted relative to the inner check.
- With a `throw` or `return` guard, ask: **can non-matching paths still reach the statements below?**
- With loops, ask: **what condition is always true upon each entry to the body?** and **why is that no longer guaranteed after the loop?**

By analyzing code this way, you can write concise conditions while maintaining exact control over pattern variable scope. This is an important foundation when Java 17 processes multi-type data, from `Object` parameters to interfaces and object hierarchies.

### References

- [Java Language Specification, Java SE 17 — Section 6.3, Scope of a Declaration (Pattern Variables)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3).
- [Java Language Specification, Java SE 17 — Section 15.20.2, Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
