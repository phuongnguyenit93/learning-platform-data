# Pattern Variables in Nested Blocks (Java 17+)

## 1. The Problem: How Far Does a Pattern Variable Exist When There Are Multiple Levels of Braces?

In Java, a **pattern variable** is a variable declared inside a pattern. With a type pattern in `instanceof`, the common syntax is:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

The expression `value instanceof String text` both checks whether the runtime value is a `String` and binds the matched object to the variable `text` of type `String`. Code inside the `if` branch can call `text.length()` without casting.

When **nested blocks** appear — `{ ... }` pairs inside `if`, `else`, loops, or standalone blocks — two sets of rules together determine where `text` can be used:

1. **Block lexical scope:** a variable declared inside a child block does not automatically become available outside that block.
2. **Flow scoping:** a pattern variable is only in scope at locations where the compiler can prove the pattern match has succeeded. Because of this, a pattern variable can sometimes still be used after an `if` statement if the non-matching branch exits via `return` or `throw`.

Key point: **nested blocks do not automatically discard a pattern variable inherited from an enclosing block**. If the pattern has matched and the variable is still in scope, ordinary child blocks can still access it. Conversely, braces cannot make an unmatched pattern variable valid.

The rules below apply to **type patterns in `instanceof` on Java 17+**. Pattern matching for `instanceof` was standardized in Java 16 via JEP 394; no preview flags are needed on Java 17.

## 2. Mental Model: Combining Block Scope and Definite Matching

Consider a multi-level structure:

```java
Object value = "  Java  ";

if (value instanceof String text) {
    // Level 1: String matched, text is usable.
    if (!text.isBlank()) {
        // Level 2: text is still in scope.
        {
            // Level 3: a standalone block can also read text.
            System.out.println(text.strip());
        }
    }
}
```

At every level inside the first `if` branch, the condition `value instanceof String text` has already succeeded. There is no need to check the type again in each block.

At the same time, the scope of an ordinary local variable declared in an inner block extends only within that block:

```java
if (value instanceof String text) {
    {
        int length = text.length();
        System.out.println(length);
    }

    System.out.println(text);   // Valid: text is still in the matched branch.
    // System.out.println(length); // Error: length was declared in the child block.
}
```

From this example, we need to distinguish **the origin of the two variables**:

- `text` is introduced by a type pattern in the `if` condition, so it is valid at points in the `if` branch where the match is guaranteed.
- `length` is an ordinary local variable declared inside the child block, so it cannot be accessed from the parent block after the child block ends.

Do not infer scope merely from "how many pairs of braces a variable is inside." Determine **where the variable is declared**, and for a pattern variable, **whether every execution path reaching the use site must have matched the pattern**.

## 3. Pattern Variables in Nested `if` Statements

### 3.1. Pattern in the Outer `if`, Used in the Inner `if`

```java
static String description(Object input) {
    if (input instanceof String text) {
        if (!text.isBlank()) {
            if (text.length() >= 4) {
                return "Long: " + text.strip();
            }
            return "Short: " + text.strip();
        }
        return "Blank";
    }
    return "Not a string";
}
```

Across all three condition levels, `text` is already confirmed to be a `String` from the outer level. Calling `isBlank()`, `length()`, and `strip()` are all valid. No `(String) input` cast is needed.

For `input = " Java "`, the result is `"Long: Java"`. For `input = "a"`, the result is `"Short: a"`; for `input = null`, the result is `"Not a string"`.

### 3.2. Pattern Declared Only in the Inner `if`

```java
static String firstText(Object input) {
    if (input instanceof java.util.List<?> items) {
        if (!items.isEmpty()) {
            Object first = items.get(0);

            if (first instanceof String text) {
                return text.strip();
            }

            // Cannot use text here:
            // first might not be a String.
        }

        // Cannot use text here:
        // the block checking first has ended.
        return "No matching first element";
    }
    return "Not a list";
}
```

`items` is introduced at the outer level, so it can be used in any child block of the matched branch. `text` is introduced in an inner condition, so it can only be used at points where **`first instanceof String text` is true**.

If `input` is a list whose first element is an `Integer`, the `if (first instanceof String text)` branch does not run; no `text` is bound on that path.

### 3.3. Multiple Patterns at Different Levels

```java
static String repeat(Object left, Object right) {
    if (left instanceof String text) {
        if (right instanceof Integer times) {
            if (times > 0) {
                return text.repeat(times);
            }
        }
        return "Not repeated";
    }
    return "Left is not text";
}
```

In the deepest block, **both `text` and `times`** are in scope: reaching that point guarantees that `left` matched `String` and `right` matched `Integer`. At `return "Not repeated"` after the inner `if`, `text` is still valid, but `times` cannot be used unconditionally because `right` might not be an `Integer`.

This rule enables a clean style for step-by-step checks: outer-level pattern variables remain available at inner levels; inner-level pattern variables are usable only where their corresponding condition is guaranteed.

## 4. The `else` Branch in Nested Blocks

A common misconception is: "A pattern variable was declared in the `if` condition, so the `else` paired with that `if` knows about it too." This is **false** for positive type patterns.

```java
if (input instanceof String text) {
    System.out.println(text.length()); // Valid.
} else {
    // System.out.println(text); // COMPILE ERROR.
    System.out.println("Not text");
}
```

The `else` branch runs when `instanceof` returns `false`. The variable `text` has not matched, so it cannot be used there.

Similarly, inside nested blocks:

```java
if (input instanceof java.util.List<?> items) {
    if (items.get(0) instanceof String first) {
        System.out.println(first.length());
    } else {
        // first is not in scope in this branch.
        System.out.println("First element is not text");
    }

    // items is valid here; first is not guaranteed.
}
```

This snippet is a **scope illustration** that assumes `items` is non-empty; calling `items.get(0)` on an empty list throws `IndexOutOfBoundsException`. In real code, check `!items.isEmpty()` before accessing the first element, as shown in the complete example later.

### Reusing a Pattern Variable Name in `else if`

Two mutually exclusive branches can use the same pattern variable name if their scopes do not overlap:

```java
static String label(Object value) {
    if (value instanceof String item) {
        return "TEXT:" + item;
    } else if (value instanceof Integer item) {
        return "NUMBER:" + item;
    } else {
        return "OTHER";
    }
}
```

The two `item` variables here are **two distinct declarations** with non-overlapping scopes. In the first branch, `item` is a `String`; in the second branch, `item` is an `Integer`. Each branch can only use the variable matched by its own pattern.

Although valid, when nesting gets deep, using distinct names like `text` and `number` usually makes the code easier to read.

## 5. Nested Blocks Do Not Let a Pattern Variable Escape Its Enclosing Scope

Consider this snippet:

```java
if (input instanceof String text) {
    {
        String normalized = text.strip();
        System.out.println(normalized);
    }

    // text is still valid inside the if branch.
    System.out.println(text.length());

    // normalized is out of scope.
    // System.out.println(normalized); // COMPILE ERROR.
}

// text is not guaranteed here.
// System.out.println(text); // COMPILE ERROR.
```

There are three levels to distinguish:

1. **Method level:** the parameter `input` is in scope across its declaration region.
2. **Matched `if` branch:** `text` is in scope throughout this branch, including child blocks.
3. **Inner standalone block:** `normalized` is in scope only inside the block where it is declared.

Child blocks do not extend `normalized` outward, nor do they shrink `text`'s scope just because a new pair of braces appears.

### A Subtle Boundary: The Enclosing Block Still Acts as a Limit

```java
static String withinBlock(Object input) {
    {
        if (!(input instanceof String text)) {
            return "NO";
        }
        System.out.println(text); // Valid: after the guard clause in the same block.
    }

    // System.out.println(text); // Invalid: outside the block containing the if.
    return "DONE";
}
```

Even when the non-matching branch executes `return`, the scope introduced by `if` remains tied to **the block enclosing that statement**. In this example, code after the standalone block cannot use `text`.

This shows that **flow scoping does not override block scoping rules**; both rules apply together.

## 6. Guard Clauses in Nested Blocks: Variables Remaining in Scope After `if`

A useful idiom is a negated type check:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_TEXT";
    }

    // Reached only if input instanceof String text was true.
    return text.strip();
}
```

Control-flow explanation:

- If `input` is not a `String` or is `null`, `instanceof` evaluates to `false`, the negation evaluates to `true`, and the method returns immediately.
- If execution reaches `text.strip()`, the negation was `false`, so the underlying pattern is guaranteed to have matched.

With **nested blocks**, the same rule holds:

```java
static String nestedGuard(Object outer, Object inner) {
    if (!(outer instanceof String prefix)) {
        return "INVALID_PREFIX";
    }

    {
        if (!(inner instanceof String suffix)) {
            return "INVALID_SUFFIX";
        }
        return prefix + ":" + suffix;
    }
}
```

Inside the child block:

- `prefix` already matched at the outer level and remains usable.
- `suffix` is proven to have matched because the non-matching branch returns.
- `return prefix + ":" + suffix` uses both variables together.

### Why Merely Logging an Error and Continuing Is Not Enough

```java
// DOES NOT COMPILE:
// if (!(input instanceof String text)) {
//     System.out.println("Not a String");
// }
// System.out.println(text.length());
```

The non-matching branch only prints a message and falls through. There is a path to `text.length()` along which `text` has not matched. If the goal is to filter out invalid types, you must `return` or `throw`, or use an `else` branch where the pattern is guaranteed.

### Distinguishing `return` and `break`

`return` exits the method; an unlabeled `break` only exits the innermost loop or `switch`. In nested blocks containing loops, **you cannot mechanically replace `return` with `break` and assume the pattern variable remains in scope for all subsequent statements**. You must trace the exact execution path after `break`.

## 7. Pattern Variables in Loops with Child Blocks

Loops often introduce multiple nested blocks: the loop body, an `if` branch, and a computation block inside that branch.

```java
static int sumLengths(Object[] values) {
    int total = 0;

    for (Object value : values) {
        if (value instanceof String text) {
            {
                String normalized = text.strip();
                total += normalized.length();
            }

            // text is still usable inside this if branch.
            // normalized is no longer usable here.
        }

        // Cannot use text here: in this iteration,
        // value might not be a String.
    }

    return total;
}
```

On each iteration, `value` is the current element. When the pattern matches, `text` belongs to that check and can be used in the branch's child blocks. No `text` variable is guaranteed after the `if` branch, nor is `text` available outside the loop.

Do not describe a pattern variable as "persisting across all iterations." The accurate model is: **each time the condition is evaluated, if the pattern matches, the variable is bound to that check's value within its allowed scope**.

## 8. Naming and Duplicate Declarations in Nested Blocks

As with Java local variables, an ordinary child block **cannot redeclare a local variable name that is already in scope from an enclosing block**. This rule also affects pattern variables.

Example that does not compile:

```java
// INVALID:
// if (input instanceof String text) {
//     {
//         String text = "other"; // Clashes with pattern variable already in scope.
//         System.out.println(text);
//     }
// }
```

Even a pre-existing local variable can cause a new pattern variable declaration to be rejected:

```java
// INVALID:
// String text = "existing";
// if (input instanceof String text) {  // Clashes with local variable text.
//     System.out.println(text);
// }
```

The fix is to use different names, or simply use the existing variable if its type is already specific enough.

In two blocks with **non-overlapping scopes**, reusing a name is valid:

```java
if (first instanceof String text) {
    System.out.println(text);
}

if (second instanceof String text) {
    System.out.println(text);
}
```

The two `text` variables above are two separate declarations in two independent `if` statements. They do not coexist in an overlapping scope.

### Pattern Variables and Lambdas in Child Blocks

A lambda can capture a pattern variable from an enclosing scope if that variable is `final` or **effectively final** (not reassigned after its initial binding):

```java
if (input instanceof String text) {
    Runnable action = () -> System.out.println(text.toUpperCase());
    action.run();
}
```

This is a valid illustration inside a method with `Object input`. If `text` were reassigned in this branch, the lambda could be rejected because `text` would no longer be effectively final. The requirement for lambdas to capture local variables is a separate Java rule, in addition to the pattern having matched.

## 9. Complete Java 17 Program: Observing Scope Levels

Create the file **`NestedPatternScopeDemo.java`**:

```java
import java.util.List;

public class NestedPatternScopeDemo {

    static String firstElement(Object input) {
        if (input instanceof List<?> items) {
            if (items.isEmpty()) {
                return "EMPTY_LIST";
            }

            Object first = items.get(0);
            if (first instanceof String text) {
                if (text.isBlank()) {
                    return "BLANK_STRING";
                }

                {
                    String clean = text.strip();
                    return "TEXT:" + clean;
                }
            }

            return "OTHER_ELEMENT";
        }
        return "NOT_LIST";
    }

    static String withEarlyReturn(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_TEXT";
        }

        {
            String normalized = text.strip();
            if (normalized.isEmpty()) {
                return "BLANK";
            }
            return "OK:" + normalized;
        }
    }

    static String combine(Object left, Object right) {
        if (left instanceof String text) {
            if (right instanceof Integer count) {
                if (count > 0) {
                    return text.repeat(count);
                }
            }
            return "NO_REPEAT";
        }
        return "NOT_STRING";
    }

    static int totalLength(Object[] inputs) {
        int total = 0;
        for (Object input : inputs) {
            if (input instanceof String text) {
                {
                    String normalized = text.strip();
                    total += normalized.length();
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(firstElement(List.of("  Java  ")));
        System.out.println(firstElement(List.of("  ")));
        System.out.println(firstElement(List.of(42)));
        System.out.println(firstElement(List.of()));
        System.out.println(firstElement(null));

        System.out.println(withEarlyReturn("  scope  "));
        System.out.println(withEarlyReturn(12));
        System.out.println(withEarlyReturn("  "));

        System.out.println(combine("Go", 2));
        System.out.println(combine("Go", 0));
        System.out.println(combine(7, 2));

        System.out.println(totalLength(
                new Object[] {" a ", null, 12, "BB", " "}));
    }
}
```

Use JDK 17 or newer:

```bash
javac --release 17 NestedPatternScopeDemo.java
java NestedPatternScopeDemo
```

Printed output, in exact order:

```text
TEXT:Java
BLANK_STRING
OTHER_ELEMENT
EMPTY_LIST
NOT_LIST
OK:scope
NOT_TEXT
BLANK
GoGo
NO_REPEAT
NOT_STRING
3
```

**Why does this program work?**

1. `firstElement` matches `List<?> items` and checks for an empty list before fetching the first element. If the first element is `String text`, both the `if (text.isBlank())` block and the standalone block containing `clean` can read `text`. A `null` input does not match `List`, so it returns `NOT_LIST`.
2. `withEarlyReturn` takes the first branch only when the input is not a `String`; afterward, `text` is guaranteed inside the child block. A whitespace-only string becomes empty after `strip()`.
3. `combine` uses `text` from the outer branch and `count` from the inner branch. Only when the repeat count is greater than 0 does it return the repeated string; all other cases are handled by their respective branches.
4. `totalLength` inspects each element independently, summing only the lengths of `String` values after `strip()`: `" a "` has length 1, `"BB"` has length 2, `" "` has length 0; the total is 3.

The examples intentionally place standalone blocks in several spots so learners can observe the difference between a pattern variable introduced by a condition and a local variable declared inside a block.

## 10. Common Mistakes with Deeply Nested Blocks

| Mistake | Why Is It Wrong? | How to Fix |
| --- | --- | --- |
| Using `text` in the `else` of `if (x instanceof String text)` | `else` means the pattern did not match | Only use `text` in a branch guaranteed to match |
| Using `text` after an `if` whose non-matching branch can fall through | There is no guarantee `text` was assigned | Use `return`/`throw` in the guard branch or move the code into the matching branch |
| Using local variable `clean` outside its declaring block | Local variables follow block scope | Move the usage into the same block or declare the variable at the appropriate level |
| Declaring `String text` in a child block while pattern variable `text` is in scope | Duplicate name declaration in overlapping scopes | Choose a different name |
| Assuming every child block knows a sibling branch's pattern variable | A sibling branch may not match the same pattern | Trace the exact control-flow path and condition |
| Calling `list.get(0)` without checking for an empty list | Runtime error, not a variable scope error | Check `isEmpty()` or size first |
| Using `text` after leaving the block enclosing the statement that introduced it | The lexical block scope has ended | Return the result from the block or redesign the data flow |

Another note: `instanceof` returns `false` for `null`, so no pattern variable is ever bound for a `null` value. If your problem requires handling `null`, you must provide an explicit branch for it.

## 11. Self-Assessment Exercises

### Exercise 1 — Which Variables Are Still in Scope?

Assume `Object value` is already declared:

```java
if (value instanceof String text) {
    int count = text.length();

    if (count > 2) {
        String message = text.toUpperCase();
        System.out.println(message);
    }

    System.out.println(text);
    System.out.println(count);
    // System.out.println(message); // (A)
}
// System.out.println(text);         // (B)
```

**Answer:** Both `System.out.println(text)` and `System.out.println(count)` in the outer branch are valid. Uncommenting line (A) causes an error because `message` belongs to the inner `if` block. Uncommenting line (B) causes an error because after the outer `if`, there is no guarantee `value` matched `String`.

### Exercise 2 — Spot the Error in a Sibling Branch

```java
// DOES NOT COMPILE:
// if (value instanceof String text) {
//     System.out.println(text.length());
// } else {
//     if (value == null) {
//         System.out.println(text); // (A)
//     }
// }
```

**Answer:** Line (A) is wrong. Entering `else` proves the first `instanceof` condition **did not match**. Opening another `if (value == null)` block inside `else` does not change that.

### Exercise 3 — Fix a Negated Condition to Use the Variable After a Child Block

Given this method:

```java
static String demo(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not String");
    }
    return text.toUpperCase(); // Error
}
```

**Fix:** Replace the standalone print statement with an exit path:

```java
static String demo(Object input) {
    if (!(input instanceof String text)) {
        return "Not String";
    }
    return text.toUpperCase();
}
```

After the `if`, all remaining paths require that the `String text` pattern has matched.

### Exercise 4 — Implement It Yourself

Write a method that takes `Object input`. If it is a non-empty `List<?>` and its first element is a `String` with at least 3 characters after `strip()`, return that element in uppercase. Otherwise, return `"INVALID"`. Use three levels of checks and only use pattern variables in matched regions. Test with `List.of("  java  ")`, `List.of("x")`, `List.of(5)`, `List.of()`, and `null`.

Expected results in order: `"JAVA"`, `"INVALID"`, `"INVALID"`, `"INVALID"`, `"INVALID"`.

## 12. Summary and Application

For **pattern variables in nested blocks**, you can follow a short checklist when reading code:

1. Identify which expression introduces the variable, such as `if (input instanceof String text)`.
2. Find the branches where that expression is guaranteed true; child blocks of those branches can use `text`.
3. Find where execution leaves that branch, especially `else`, after `if`, and after exiting the block containing the statement.
4. If the variable is still used after `if`, verify that the non-matching path truly **cannot fall through** because of `return` or `throw`.
5. Also check the scope of local variables declared in smaller blocks and watch out for name collisions.

**Main takeaway:** `{ }` braces determine the lexical scope of many local variables, while pattern variables also require **guaranteed pattern matching along the control flow**. A child block can use a pattern variable from a parent block as long as that guarantee holds. Relying on indentation alone is not enough to determine variable scope.

## Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [Java SE 17 Language Specification, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
