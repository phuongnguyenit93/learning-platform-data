# Combining `instanceof` with Statement Blocks

**Topic:** Java Core Pattern Matching → Basic instanceof  
**Applicable versions:** Java 17 and later; `instanceof` syntax with a *pattern variable* became standard in Java 16.

## 1. Why combine `instanceof` with statement blocks?

A variable with a broad declared type such as `Object` can reference objects of many actual types. `instanceof` returns `true` when the value is non-`null` and the object is compatible with the checked reference type; otherwise it returns `false`. We typically place the check inside an `if` condition, then use a **statement block** `{ ... }` to group operations that should only run after the check succeeds.

Blocks create clear boundaries: in the true branch, we process the data according to its confirmed type; in `else` or `else if`, we handle non-matching cases. This organization both prevents invalid casts and makes the code easier to follow when multiple sequential operations are involved.

## 2. Traditional approach: check then cast inside the block

Illustrative example (code placed in a method with a variable `value` of type `Object`):

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println("Độ dài: " + text.length());
    System.out.println("Chữ hoa: " + text.toUpperCase());
} else {
    System.out.println("Không phải chuỗi");
}
```

In the `if` branch, `instanceof String` indicates that the cast `(String) value` can be performed safely on **the value just checked**, provided there is no relevant change between the check and the cast. The variable `text` declared inside `{ ... }` has scope from its declaration point to the end of the block. The `else` branch runs when `value` is another type or `null`.

Do not place the cast before the condition:

```java
// Logically wrong: may throw ClassCastException before the check.
String text = (String) value;
if (value instanceof String) {
    System.out.println(text.length());
}
```

The code above is only an **unsafe** example, not a pattern to use. If `value` is an `Integer`, the cast fails before the program reaches `if`. Casting `null` to `String` by itself does not throw `ClassCastException`, but calling `text.length()` will fail without an additional check.

## 3. Modern approach: type pattern directly in the `if` condition

Java allows combining the type check and the declaration of a typed variable into a single expression:

```java
if (value instanceof String text) {
    System.out.println("Độ dài: " + text.length());
    System.out.println("Chữ hoa: " + text.toUpperCase());
} else {
    System.out.println("Không phải chuỗi");
}
```

Here:

- `String` is the type being checked.
- `text` is the *pattern variable*; it is bound to the matched object with static type `String`.
- The `if` block only runs when the pattern matches. There is no need to write `(String) value` inside the block.
- `text` is not available in the `else` branch of the example above because that branch only runs when the pattern does not match.

Both approaches serve the same purpose in simple scenarios. A pattern variable eliminates a casting step and avoids accidentally re-casting a variable that has changed. When working with Java 17+ projects, prefer this style when it makes the code clearer.

## 4. Nested blocks and `if / else if / else` chains

After identifying the right type, a block can contain multiple statements and nested conditions:

```java
if (value instanceof String text) {
    if (text.isBlank()) {
        System.out.println("Chuỗi rỗng hoặc chỉ có khoảng trắng");
    } else {
        System.out.println("Số ký tự: " + text.length());
    }
} else if (value instanceof Integer number) {
    System.out.println("Số nguyên: " + number);
} else {
    System.out.println("Kiểu khác hoặc null");
}
```

Execution order:

1. Check `String`; if true, the first block runs and the program does not evaluate subsequent `else if` branches.
2. If not `String`, try `Integer`; inside its corresponding block, `number` has type `Integer`.
3. If neither matches, run the `else` block.

Statements inside the blocks can call methods, declare local variables, or return results. You should use `{ ... }` even when a branch has only one statement so that adding lines later does not accidentally alter control flow. When braces are omitted, `if` controls only **one statement** immediately following the condition.

## 5. Variable scope: regular blocks and flow scoping

For regular local variables, scope is largely determined by the declaration position and curly braces:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
// Cannot use the local variable text here.
```

For pattern variables, Java also analyzes **control flow** (*flow scoping*): the variable is only in scope where the compiler can prove the pattern has matched. The following examples illustrate the rule:

```java
if (value instanceof String text) {
    System.out.println(text.length()); // Valid: the pattern has matched.
} else {
    System.out.println("Không phải String");
    // text.length();                 // Invalid: text is out of scope.
}
```

In a condition using the `&&` operator, the right-hand operand is only evaluated if the left-hand operand is `true`. Therefore, the second check can use the pattern variable:

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Chuỗi có ít nhất 4 ký tự");
}
```

Conversely, in an `||` condition, the right-hand branch can make the whole expression true when the pattern **does not** match, so the pattern variable cannot be used as guaranteed to exist:

```java
// DOES NOT COMPILE:
// if (value instanceof String text || text.isEmpty()) { }
// Because when value is not a String, text has not been assigned a value.
```

Negation cases require observing all paths of the program. When the non-matching branch exits the method with `return`, the pattern variable can continue to be used after the block:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid: to reach here, value must match String.
}
```

This is a noteworthy advantage of flow scoping: the compiler determines safe locations based on actual execution paths, rather than simply assuming a pattern variable can only be used inside the `if` braces.

## 6. Complete example running on Java 17+

Create the file **`InstanceofBlocksDemo.java`**:

```java
public class InstanceofBlocksDemo {
    static void describe(Object value) {
        if (value instanceof String text) {
            if (text.isBlank()) {
                System.out.println("Blank");
            } else {
                System.out.println("Text(" + text + ") length=" + text.length());
            }
        } else if (value instanceof Integer number) {
            System.out.println("Integer=" + number);
        } else {
            System.out.println("Other");
        }
    }

    static boolean hasAtLeastFourChars(Object value) {
        return value instanceof String text && text.length() >= 4;
    }

    public static void main(String[] args) {
        describe("Java");
        describe("   ");
        describe(7);
        describe(null);

        System.out.println("Long Java=" + hasAtLeastFourChars("Java"));
        System.out.println("Long Hi=" + hasAtLeastFourChars("Hi"));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 InstanceofBlocksDemo.java
java InstanceofBlocksDemo
```

Exact output:

```text
Text(Java) length=4
Blank
Integer=7
Other
Long Java=true
Long Hi=false
```

**Explanation:**

- `"Java"` matches `String text`, enters the `!text.isBlank()` branch, and prints length `4`.
- `"   "` is still a `String`; `isBlank()` returns `true`, so it prints `Blank`.
- `7` is autoboxed to `Integer` when passed to the `Object` parameter, so it enters the `Integer number` branch.
- `null` does not match any of the type patterns above, so it enters `else`.
- The `hasAtLeastFourChars` method shows that `&&` both guards access to `text.length()` and returns `false` for short strings or non-`String` objects.

If you want to use the traditional style, replace `if (value instanceof String text)` with `if (value instanceof String)`, then declare `String text = (String) value;` at the top of the block; the subsequent branches keep the same meaning.

## 7. Common mistakes when combining with blocks

| Issue | Why it is wrong or risky | How to fix |
| --- | --- | --- |
| Casting before `instanceof` | May throw `ClassCastException` before the check | Cast inside the matched branch or use a type pattern |
| Using `text` in the `else` of `if (value instanceof String text)` | The `else` branch does not guarantee the pattern matched | Only use `text` where flow scoping permits |
| Using `text` on the right-hand side of `||` in the same condition | The right-hand branch can run when the pattern does not match | Use `&&`, or split into clear separate branches |
| Forgetting to handle `null` | `instanceof` returns `false` for `null` | Handle in `else` or check `null` separately |
| Checking one variable but casting another | The check does not guarantee the other variable has the same type | Use the exact value that was checked or use a pattern variable directly |
| Reassigning `value` and casting again after the check | The new value may no longer be the confirmed type | Do not rely on an old check result for a modified value |
| Omitting `{ ... }` when there are multiple operations | Only the first statement belongs to `if` | Use full blocks for branches |
| Writing `value instanceof java.util.List<String>` | Type arguments are usually erased at runtime, not a valid reifiable check | Use `List<?>` and check elements as needed |

A long block containing many type checks is often a sign to consider extracting a method. If behavior belongs to individual classes in the same hierarchy, polymorphism (`override`) may be more appropriate than repeatedly adding `else if`.

## 8. Self-check exercises

1. Write a method `printShape(Object value)` using `if / else if / else` to distinguish `String`, `Integer`, and other values, with each branch having a `{ ... }` block.
2. Inside the `String` handling block, add a nested `if` to distinguish an `isEmpty()` string from a string with content. Explain why `"   "` has `isEmpty() == false` but `isBlank() == true`.
3. Convert code with `instanceof` + manual cast to `instanceof String text` syntax, ensuring `text` is not used out of scope.
4. Write a method that returns `-1` if the parameter is not a `String`, and otherwise returns the string length; try both a regular `if` block form and a negated early-`return` form.
5. Try compiling the invalid `||` example in section 5, read the compiler error, then fix it using `&&` or by splitting branches.

**Completion criteria:** able to trace the execution flow of blocks, accurately determine when a cast is safe, use pattern variable scope correctly, and predict results for `String`, `Integer`, non-matching objects, and `null`.

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [Java Language Specification, `instanceof` operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2).
