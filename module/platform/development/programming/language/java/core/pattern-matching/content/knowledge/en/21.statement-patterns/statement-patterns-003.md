# Patterns in Java's `for` Statement

## 1. Where Does Pattern Matching Appear in a `for` Loop?

In Java, a **pattern** describes a structural/type check and can introduce a *pattern variable* when matching succeeds. For `for` loops, you must distinguish between two syntactic forms:

```java
// Basic for: three parts init, condition, update
for (int i = 0; condition; i++) {
    // body
}

// Enhanced for: iterate over each element
for (Object item : items) {
    // body
}
```

In a **basic `for`**, the condition expression can contain `instanceof` combined with a type pattern or a record pattern. When the condition expression matches and evaluates to `true`, the pattern variable can be used **in the loop body and in the `ForUpdate` part**, according to Java's *flow scoping* rules (§6.3.2.5).

In an **enhanced `for`**, the `Object item` part in the header is a **regular loop variable declaration**, not a pattern. You can place `instanceof`, a record pattern, or a `switch` with pattern `case`s **inside the loop body** to process each element.

One common point of confusion regarding versions: Java 20 previewed record patterns directly in the enhanced `for` header; **Java 21 removed that syntax** when record patterns became a standard feature. Therefore, `for (Point(var x, var y) : points)` is **invalid in Java 21**. The complete examples in this article use JDK 21 or later and do not require enabling preview features.

## 2. Basic `for`: Patterns in the Condition Expression

Short example:

```java
Object[] values = {"ab", "c", 42, "z"};

for (int i = 0;
     i < values.length && values[i] instanceof String word;
     i++) {
    System.out.println(word.toUpperCase());
}
```

Order of execution:

1. `int i = 0` runs once at the start of the loop.
2. Java checks `i < values.length`. If false, the condition terminates immediately due to `&&`.
3. When an element remains, Java checks `values[i] instanceof String word`. If it is a `String`, the pattern variable `word` is bound.
4. **Only when the entire condition is `true`** does the loop body execute, and `word` can be used without casting.
5. After the loop body, `i++` runs and Java re-evaluates the condition.

An important difference compared to putting an `if` in the body: **a pattern that fails to match in the condition terminates the entire loop**. With the array above, the loop processes `"ab"` and `"c"`, then stops at `42`; it **does not automatically skip** `42` to reach `"z"`.

With `null`, the expression `value instanceof String word` returns `false`, so the loop also terminates if the type check is in the condition.

## 3. Complete Example: Pattern Variable Used in Both Body and `ForUpdate`

A lesser-known rule is that a pattern variable introduced by the condition when `true` is in scope **in the update part as well**. `ForUpdate` can consist of multiple *statement expressions*, such as method calls and index increments, separated by commas.

Save to `ForConditionDemo.java`:

```java
public class ForConditionDemo {
    public static void main(String[] args) {
        Object[] items = {"ab", "c", 42, "z"};

        for (int i = 0;
             i < items.length && items[i] instanceof String word;
             System.out.println("length=" + word.length()), i++) {

            System.out.println("body=" + word);
        }

        System.out.println("stopped");
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 ForConditionDemo.java
java ForConditionDemo
```

Output:

```text
body=ab
length=2
body=c
length=1
stopped
```

`word` is validly in scope in `System.out.println("body=" + word)` **and** `System.out.println("length=" + word.length())` in the update part. The update part runs **after** the body on each iteration, which explains the order of the output lines.

On the iteration checking the element `42`, the type pattern does not match; the body and `ForUpdate` for that iteration **do not run**. The clause `i < items.length` ensures there is no out-of-bounds access before attempting `instanceof`.

This is a direct example of the JLS 21 §6.3.2.5 rule: a *pattern variable introduced by the condition when true* is definitely matched in `ForUpdate` and the contained statement.

## 4. When You Want to Skip Non-Matching Elements, Put the Pattern in the Body

Many real-world tasks involve iterating over a collection containing multiple data types and processing only the elements of the desired type. For this requirement, it is usually clearer to use an enhanced `for` and check the pattern with `if`:

```java
for (Object item : items) {
    if (item instanceof String word) {
        System.out.println(word);
    }
}
```

Here, `item` is the **loop variable**, while `word` is the **pattern variable**. If `item` does not match, only the `if` branch is skipped; the enhanced `for` still moves on to the next element.

An even more useful style is a **guard clause** with `continue`.

Save to `ForSkipDemo.java`:

```java
import java.util.Locale;

public class ForSkipDemo {
    public static void main(String[] args) {
        Object[] values = {"alpha", 42, null, "beta"};

        for (Object value : values) {
            if (!(value instanceof String word)) {
                continue;
            }

            System.out.println("word="
                    + word.toUpperCase(Locale.ROOT));
        }
    }
}
```

```bash
javac --release 21 ForSkipDemo.java
java ForSkipDemo
```

Output:

```text
word=ALPHA
word=BETA
```

The condition `!(value instanceof String word)` is `true` when the element is not a `String`; `continue` moves to the next element. To reach `System.out.println(...)` afterward, Java knows that the `continue` branch was not taken, meaning the match must have succeeded. Therefore, `word` is in valid scope on the print line.

This is the effect of **flow scoping**, not that the variable `word` exists unconditionally. `null` does not match the type pattern `String word`, so it is also safely skipped.

## 5. Record Patterns in Enhanced `for` — The Valid Way in Java 21

Record patterns support deconstructing the components of a record. In an enhanced `for` loop, Java 21 allows using them in an `instanceof` expression **inside the body**.

Save to `ForRecordDemo.java`:

```java
public class ForRecordDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Object[] values = {
            new Point(2, 5),
            "skip",
            new Point(3, 4)
        };

        for (Object value : values) {
            if (value instanceof Point(var x, var y)) {
                System.out.println("Point sum=" + (x + y));
            }
        }
    }
}
```

```bash
javac --release 21 ForRecordDemo.java
java ForRecordDemo
```

Output:

```text
Point sum=7
Point sum=7
```

On iterations with a `Point`, the record pattern `Point(var x, var y)` checks the record, extracts its components via the corresponding accessors, and binds `x`, `y` (both inferred here as `int`). For the string `"skip"`, matching fails, but **the loop still continues**.

If the input contains `null`, the record pattern also does not match `null`; the result of `instanceof` is `false`.

Using a record pattern in the condition of a basic `for` is also valid:

```java
for (int i = 0;
     i < values.length
         && values[i] instanceof Point(var x, var y);
     i++) {
    System.out.println(x + y);
}
```

**Behavioral difference:** the basic `for` loop above stops immediately when it encounters the first element that is not a `Point`. It is suitable when the list to be processed is a **contiguous prefix** of matching elements at the beginning; whereas for a mixed dataset that needs to be traversed completely, you should use `if` in the body.

## 6. Invalid Syntax: Record Pattern Directly in the Enhanced `for` Header

Although it looks like deconstructing each element, **the following snippet does not compile with Java 21**:

```java
record Point(int x, int y) {}

void print(Point[] points) {
    // Invalid syntax in Java 21:
    for (Point(var x, var y) : points) {
        System.out.println(x + y);
    }
}
```

`Point(var x, var y)` is a record pattern, but the variable declaration position at the start of an enhanced `for` in Java 21 does not accept record patterns. That is the difference between **Java 20's preview syntax** and **Java 21's final syntax**.

The correct way to write it in Java 21:

```java
void print(Point[] points) {
    for (Point point : points) {
        if (point instanceof Point(var x, var y)) {
            System.out.println(x + y);
        }
    }
}
```

This snippet is an **illustration inside a class/scope where the `Point` record is already declared**; it is not a standalone Java file. If the array only contains valid `Point` objects, the simplest approach is usually to use the accessors `point.x()` and `point.y()` directly. Use a record pattern when it helps express a type check/deconstruction or when using the same logic to handle multiple data types.

If `point` can be `null`, `instanceof Point(...)` returns `false`, whereas calling `point.x()` directly will throw a `NullPointerException`.

## 7. Variable Scope: Not Every Position in `for` Sees the Pattern Variable

For a basic `for`:

```java
for (int i = 0;
     i < values.length && values[i] instanceof String word;
     i++) {
    System.out.println(word.length()); // Valid.
}
```

`word` is introduced when the condition is true, so the compiler allows using it in the body and `ForUpdate`. It **does not exist by default in the `ForInit` part** (which runs before the matching condition), and **does not exist by default in code after the loop**. After the loop ends, the condition may have become false either because there were no more elements or because the pattern failed.

For an enhanced `for`, the scope of the pattern variable is controlled by where the pattern appears:

```java
for (Object item : values) {
    if (item instanceof String word) {
        System.out.println(word);
    }
    // Cannot assume `word` has always matched here.
}
```

Another approach is to add a secondary condition with `&&`, which only evaluates the right-hand side when matching succeeds:

```java
for (Object item : values) {
    if (item instanceof String word && !word.isBlank()) {
        System.out.println(word.trim());
    }
}
```

At `!word.isBlank()`, `word` is already known to be a `String`. This is a familiar combination of pattern matching and short-circuit evaluation.

## 8. Advanced Case: A Pattern Variable Can Be in Scope After a Basic `for`

JLS 21 also specifies a rare but valid case: **if the `for` condition becomes `false` precisely when a pattern is confirmed to match**, and the loop body **has no `break` targeting that loop**, the pattern variable can be brought into scope after the loop.

An example using the negated expression `!(... instanceof String result)` to find the first string:

Save to `ForFindDemo.java`:

```java
import java.util.Locale;

public class ForFindDemo {
    public static void main(String[] args) {
        Object[] values = {1, 2, "done"};
        int index = 0;
        Object current = values[index];

        for (;
             !(current instanceof String result);
             current = values[++index]) {
            // Continue until current matches String.
        }

        System.out.println("found="
                + result.toUpperCase(Locale.ROOT));
    }
}
```

```bash
javac --release 21 ForFindDemo.java
java ForFindDemo
```

Output:

```text
found=DONE
```

The `for` loop only finishes normally when `!(current instanceof String result)` is `false`, meaning `current` **has matched** `String result`. Therefore, `result` is valid in the statement after the loop.

**Precondition of the example:** we know for sure the array contains `"done"` before going out of bounds. If there is no matching element, the update `values[++index]` can throw an `ArrayIndexOutOfBoundsException`. This snippet is meant to illustrate the exact language scoping rule; when writing real programs, the safe approach is usually a loop with bounds checking and an explicit result variable.

Adding a `break` targeting the loop, or combining conditions so the loop could also stop for another reason, can cause the compiler to **no longer guarantee** that the pattern matched upon exiting the loop. Do not mechanically apply the `result`-after-`for` rule to every loop statement.

## 9. Using `switch` Patterns in the Loop Body

`for` is also commonly combined with **pattern matching for `switch`** (standardized in Java 21). Here, `switch` is a statement/expression **inside the body**, rather than replacing the header syntax of `for`.

Save to `ForSwitchDemo.java`:

```java
public class ForSwitchDemo {
    public static void main(String[] args) {
        Object[] values = {"hi", 2, null, 3.5};

        for (Object value : values) {
            String description = switch (value) {
                case String text -> "S:" + text;
                case Integer number -> "I:" + number;
                case null -> "NULL";
                default -> "OTHER";
            };

            System.out.println(description);
        }
    }
}
```

```bash
javac --release 21 ForSwitchDemo.java
java ForSwitchDemo
```

Output:

```text
S:hi
I:2
NULL
OTHER
```

This is an easy-to-read approach when you need to classify each element across multiple types. `case null` handles `null` values explicitly; the pattern variable `text` or `number` is only usable in its corresponding `case` branch.

## 10. Which Construct Should You Choose in Practice?

| Goal | Suitable Approach | Points to Note |
| --- | --- | --- |
| Process a contiguous sequence of matching elements from the start of a list | Basic `for` with `instanceof` in the condition | Stops immediately at the first non-matching element |
| Scan an entire list mixing multiple types | Enhanced `for` + `if (item instanceof T t)` | Non-matching elements are skipped |
| Scan a list of records and deconstruct components | Enhanced `for` + record pattern in the body | Java 21 does not accept record patterns in the enhanced-for header |
| Classify multiple types on each iteration | Enhanced `for` + `switch` pattern | Pay attention to `null`, `default`, and the scope of each `case` |
| Need the pattern variable in the update of a basic `for` as well | Pattern in the condition of a basic `for` | The variable is only definitely matched when the condition is true |
| Find up to the first matching element | Loop with a pattern-checking condition or iterate and `break` | Maintain bounds checks and handle the not-found result |

If you only need to process strings already known to be `String`, adding `instanceof String s` does not make the code better. Patterns are useful when the input has a general type (`Object`, an interface, or a supertype) or when you need to deconstruct a record with multiple components.

## 11. Common Mistakes

1. **Misreading preview syntax:** `for (Point(var x, var y) : points)` appeared in some Java 20 preview documentation, but was removed from Java 21.
2. **Thinking `instanceof` in the condition is a filter that skips elements:** in a basic `for`, a `false` condition **terminates the loop**. To skip, use `if`/`continue` in the body.
3. **Using a pattern variable when matching is not guaranteed to have succeeded:** the compiler only allows it where flow scoping guarantees it is bound.
4. **Using a pattern variable in `ForInit`:** a variable coming from the condition does not exist yet before the condition is evaluated.
5. **Assuming a pattern variable always exists after `for`:** only special flow-scoping cases qualify, such as the negated example and a loop without `break`.
6. **Forgetting the array bounds check before `items[i]`:** place `i < items.length` before `&&` to guard the access, especially for empty inputs.
7. **Confusing `null` with a successful match:** `null instanceof String word` and `null instanceof Point(var x, var y)` are both `false`. In `switch`, consider `case null`.
8. **Thinking enhanced `for (String value : strings)` is a type pattern:** this is standard loop variable declaration syntax; `String value` does not have the `instanceof` check of pattern matching.
9. **Overlooking when `ForUpdate` runs:** the update part runs after the body (including the `continue` path for a basic `for`) and only when the loop proceeds to the next iteration; it does not run when the initial condition is `false`.
10. **Using record patterns on JDK 17 and being surprised by errors:** `instanceof` type patterns were stabilized earlier, whereas **record patterns** became standard in Java 21.

## 12. Checklist When Writing Patterns in Loops

Before choosing a syntax, determine:

- Do you want to **stop** when encountering a non-matching element or **continue iterating**?
- Is the pattern variable needed in the **body**, **`ForUpdate`**, or only inside an `if`/`switch` branch?
- Can the input type be `null`, and can the collection be empty?
- Are you writing code for **Java 21** or reading Java 20 preview documentation?
- If using a record pattern, is it inside **`instanceof` or `switch`** in a valid syntactic position, or mistakenly placed directly in the enhanced-for header?

**Takeaway:** in Java 21, a **basic `for` can introduce a pattern variable from its condition for use in the body and update**; whereas an **enhanced `for` iterates over elements using a regular loop variable**, and pattern matching is placed in the loop body when checking or deconstruction is needed.

## Official References

- [Java Language Specification 21 — §6.3.2.5 Scope for Pattern Variables in `for` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.5)
- [Java Language Specification 21 — §14.14.1 Basic `for` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.1)
- [Java Language Specification 21 — §14.14.2 Enhanced `for` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.2)
- [Oracle Java SE 21 — Java Language Changes (removal of record patterns in enhanced `for` header)](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
