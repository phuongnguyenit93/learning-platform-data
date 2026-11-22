# Pattern Variable Scope Across Blocks in Java (Java 21+)

## 1. Scope Does Not Depend Only on Curly Braces

When encountering a **pattern variable**, many people have the habit of guessing the variable's scope by looking for the nearest pair of `{ ... }` braces. This approach is not enough. In Java, the scope of a variable declared by a pattern also depends on **control flow**: the compiler only allows using the variable where it knows for certain that the pattern has **matched**.

Consider two examples:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`text` can be used inside the `if` body, because this branch only executes when `value` is a non-null `String`. In the snippet below, `text` can also be used **after the `if` block ends**:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length());
```

The reason: if the negated condition is true, the method has already `return`ed; to reach the print statement, the pattern must have matched. This is **flow scoping** — scope inferred from the execution path of the program, not just from the position of braces.

In this article, we look at pattern variables in **statements**: `if/else`, `&&` and `||` conditions, `while`, nested blocks, and `switch` branches. We also distinguish the scope of variables destructured from a record pattern versus regular local variables.

**Version:** Type patterns with `instanceof` have been an official feature since Java 16; record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been stable since **Java 21**. The complete programs below use JDK 21+ and do not require `--enable-preview`.

## 2. What Is a Pattern Variable?

A pattern variable is introduced along with a **type pattern** or a **record pattern**, for example:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Here, `String text` checks the type and declares the variable `text`. We do not have to write `(String) value` manually, and the compiler can determine where `text` is guaranteed to have a value.

Java 21 record patterns allow further destructuring of components:

```java
record Point(int x, int y) {}

if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

`x` and `y` are two pattern variables, inferring the `int` type from the `Point` declaration. **They are only in scope when the `Point(...)` pattern succeeds**, not everywhere a variable named `x` is mentioned.

### How Do Scope, Lifetime, and Definite Matching Differ?

- **Scope:** the locations in the source code where the compiler allows referencing that variable name.
- **Lifetime:** a runtime execution concern; it should not be equated with the positions of opening/closing braces in source code.
- **Definitely matched:** the compiler's conclusion that the pattern has matched along the path to an expression or statement. Flow scoping leverages this conclusion to determine where the variable is allowed to be used.

Do not confuse a pattern variable with an object's field, or with a local variable that can be accessed outside a branch just because it was assigned somewhere in the program.

## 3. `if`: The Variable Is Only Usable in Branches That Guarantee the Pattern Is True

Basic example:

```java
static void inspect(Object input) {
    if (input instanceof String s) {
        System.out.println("Độ dài: " + s.length());
    } else {
        System.out.println("Không phải chuỗi");
    }
}
```

- In the condition `input instanceof String s`, `s` is only bound when the pattern is true.
- In the `then` block, `s` is in scope.
- In the `else` block, `s` is **not in scope** because this branch runs when the pattern is false.
- After the entire `if/else` where both branches can complete normally, `s` is **not in scope**: the path from the `else` branch does not guarantee the pattern matched.

Example that **intentionally does not compile**:

```java
if (input instanceof String s) {
    System.out.println(s);
} else {
    System.out.println(s); // Error: s is not in scope in else.
}
System.out.println(s);     // Error: after if, execution may come from the false branch.
```

Do not fix this by casting unconditionally, because when `input` is not a `String`, it can throw a `ClassCastException`. Place the action that needs the variable in a branch that truly knows the pattern is true, or reorganize the control flow.

### Two Nested Blocks

```java
if (input instanceof String s) {
    int len = s.length();
    {
        String first = len > 0 ? s.substring(0, 1) : "(rỗng)";
        System.out.println(first);
    }
    System.out.println("Số ký tự: " + len);
    // first is NO LONGER in scope here.
}
// s and len are NOT in scope here.
```

Here, `s` is brought into the `if` body's scope via matching; `len` is a local variable of the `if` block; `first` is a local variable of the smaller nested block. Therefore, **pattern variable scope** and **regular local variable scope** can coexist in the same piece of code but are governed by different rules.

## 4. `&&`: The Right-Hand Side Knows the Pattern Has Matched

Consider:

```java
if (input instanceof String s && s.length() >= 3) {
    System.out.println("Chuỗi có ít nhất 3 ký tự: " + s);
}
```

`&&` evaluates with **short-circuiting**:
1. Check `input instanceof String s`.
2. If false, stop; do not read `s.length()`.
3. If true, `s` is definitely bound, so the second condition is valid.
4. If both are true, the `if` body can use `s`.

You can combine multiple conditions:

```java
if (input instanceof String s
        && !s.isBlank()
        && s.startsWith("J")) {
    System.out.println("Chuỗi J: " + s.strip());
}
```

You can add parentheses for logical groupings without breaking the matching guarantee:

```java
if (input instanceof String s
        && (s.startsWith("J") || s.startsWith("K"))) {
    System.out.println(s);
}
```

Here, `||` **comes after** the `instanceof ... &&` condition and is inside a group that is only evaluated when `s` already exists. What matters is not "having `||` is always wrong", but whether the location using the variable is guaranteed that the pattern has matched.

### Common Mistake with `||`

Example that **does not compile**:

```java
if (input instanceof String s || s.isEmpty()) {
    System.out.println("...");
}
```

The right-hand side `s.isEmpty()` is only evaluated when the left-hand side is false, meaning when `s` **has not been bound**. The compiler rejects that reference.

One fix is to place the condition needing `s` after `&&`. If the problem is "not a string or an empty string", express it explicitly:

```java
if (!(input instanceof String)) {
    System.out.println("Không phải chuỗi");
} else if (((String) input).isEmpty()) {
    System.out.println("Chuỗi rỗng");
}
```

In Java 21, you can use the pattern variable directly with the `else` branch of a negated condition (see the next section), avoiding manual casting.

## 5. Negated Conditions and Early Return: Variables Can Cross Block Boundaries

**Surprising point:** there are cases where a pattern variable can be used **after an `if` block**, if the compiler proves that every continuing path has matched the pattern.

```java
static String uppercase(Object input) {
    if (!(input instanceof String s)) {
        return "Không phải chuỗi";
    }
    return s.strip().toUpperCase(java.util.Locale.ROOT);
}
```

Reading the flow:

- If it is not a `String`, the negated condition is true, and the method returns immediately.
- To reach `return s.strip()...`, the negated condition must be false.
- That means `input instanceof String s` **was true**; therefore `s` is in scope on the second line.

This is a classic example of **flow scoping** across a block boundary. The fact that the `if`'s closing `}` appears before `return s` does **not** mean `s` goes out of scope.

### Variant with `throw`

```java
static int lengthOrFail(Object input) {
    if (!(input instanceof String s)) {
        throw new IllegalArgumentException("Expected String");
    }
    return s.length();
}
```

`throw` also terminates the normal flow of the failure branch. If execution reaches the last line, the pattern is guaranteed to have matched.

### `else` of a Negated Condition

```java
if (!(input instanceof String s)) {
    System.out.println("Không phải chuỗi");
} else {
    System.out.println("Độ dài: " + s.length());
}
```

The `else` branch runs when the negation is false, so `s` is bound. This is how to express "not a string or an empty string" without casting:

```java
if (!(input instanceof String s)) {
    System.out.println("Không phải chuỗi");
} else if (s.isEmpty()) {
    System.out.println("Chuỗi rỗng");
} else {
    System.out.println("Chuỗi có nội dung");
}
```

**Note:** do not assume that a pattern variable always survives past every negated `if`. If the false branch of the match can still **continue normally** after the block, the compiler cannot guarantee the variable is bound. It is `return`/`throw` or an explicit branch structure that makes this safe.

## 6. Pattern Variables in a `while` Statement

The `while` condition is re-evaluated before each iteration. A pattern variable is in scope in the `while` body when the match in the condition is true.

```java
static int countCharacters(Object input) {
    int count = 0;
    while (input instanceof String s && !s.isEmpty()) {
        count++;
        input = s.substring(1);
    }
    return count;
}
```

Explanation:
- If `input` is not a string, the loop is not entered.
- If it is a non-empty string, `s` exists in the loop body.
- After each iteration, `input` is replaced by the string without its first character; the loop re-checks the pattern on the next iteration.
- When the string is empty, the guard is false and the loop terminates. **`s` is not in scope at the statement after the `while` loop** in this example.

For example, `countCharacters("abc")` returns `3`, while `countCharacters("")` and `countCharacters(42)` both return `0`.

```java
// Intentionally does NOT compile if placed right after the while above:
System.out.println(s); // s is not in scope after the loop.
```

Do not confuse the `input` variable that already exists outside the loop with `s` newly introduced in the condition. The input can be reassigned, but that does not extend the scope of `s`.

In real loops, be careful to avoid an infinite `while`: if the pattern condition is always true and the body does not change the relevant state, the loop may never terminate. That is an algorithmic bug, not a scoping error.

## 7. Pattern Variables in `switch` Statements and `case` Blocks

With pattern matching `switch`, a branch's pattern variable is in scope within the **`when` guard and the body of that branch**. Using `case ... -> { ... }` syntax makes the scope clear and avoids fall-through:

```java
record Point(int x, int y) {}

static void print(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case Point(var x, var y) when x == 0 && y == 0 -> {
            String label = "gốc tọa độ";
            System.out.println(label);
        }
        case Point(var x, var y) -> {
            int sum = x + y;
            System.out.println("Tổng tọa độ: " + sum);
        }
        case String s -> {
            System.out.println("Chuỗi: " + s);
        }
        default -> System.out.println("Kiểu khác");
    }
}
```

**How to read the scope:**
- In `case Point(var x, var y) when ...`, `x` and `y` are already bound after matching, so they can be used in the guard.
- In the block to the right of `->`, `x` and `y` are usable. The variable `label` only exists inside the first branch's block.
- In the next `case Point(var x, var y)` branch, those are **two different pattern variables**, even though they share the names `x` and `y`; no value is carried over from the previous branch.
- `s` in `case String s` only belongs to the string branch; it cannot be referenced in the `Point` branch or after the `switch`.
- When the selector is `null`, `case null` handles it separately. Do not rely on `default` to automatically accept null in an enhanced switch.

**There is no fall-through** in branches using `->`. The `case ... :` syntax still belongs to `switch` statements, but with pattern variables you must pay special attention to scoping rules and the prohibition against falling through into a branch whose pattern has not matched; using `->` is usually easier to review.

### A `when` Condition Does Not Extend Scope Outside the Branch

```java
case String s when s.length() > 5 -> {
    System.out.println("Chuỗi dài: " + s);
}
```

`s` is usable in the guard and block because they are only evaluated after matching. However, `s` does not exist in `default` or in statements after the `switch`.

**Branch ordering:** place patterns with specific guards before general patterns. The following snippet **does not compile** due to dominance:

```java
switch (input) {
    case String s -> System.out.println("Mọi chuỗi");
    case String s when s.length() > 5 ->
        System.out.println("Chuỗi dài"); // dominated
    default -> System.out.println("Khác");
}
```

The first `case String s` pattern already matches every non-null string, making the later branch unreachable. Swap the order of the two branches to ensure proper priority handling. This is a **branch reachability** rule, separate from the concept of scope, though it often comes up together when organizing multiple `case` blocks.

## 8. Nested Record Patterns and Scope of Leaf Variables

In Java 21, record patterns can be nested:

```java
record Point(int x, int y) {}
record Route(String name, Point start, Point end) {}

if (input instanceof Route(
        var name,
        Point(var x1, var y1),
        Point(var x2, var y2))) {
    System.out.println(name + ": (" + x1 + ", " + y1
        + ") -> (" + x2 + ", " + y2 + ")");
}
```

The `println` statement only executes when **Route, start, and end** all match the record patterns. If `start == null` or `end == null`, one of the two `Point(...)` patterns does not match; the `if` body does not run. The variables `x1, y1, x2, y2` therefore cannot be used on a path where the nested pattern fails.

Sometimes we need to keep the component as-is instead of requiring it to be a non-null record:

```java
if (input instanceof Route(var name, var start, var end)) {
    System.out.println("Có Route: " + name);
    if (start == null || end == null) {
        System.out.println("Thiếu điểm đầu hoặc cuối");
    }
}
```

Here `start` and `end` are extracted from the components using `var`; a null reference component can still be bound by the corresponding unconditional pattern. Inside the `if` block, they are in scope to be used in null checks. **Scope** and **nullability** are two different things: a variable that is in scope can still hold `null`.

If you need to access `start.x()`, you must ensure `start != null` using a guard or condition. A variable "existing" in terms of scope does not mean every method call on it is safe.

## 9. Complete Java 21 Example: `if`, Early Return, `while`, and `switch`

Create the file **`PatternVariableBlockScopeDemo.java`**:

```java
public class PatternVariableBlockScopeDemo {
    record Point(int x, int y) {}
    record Box(Point point, String label) {}

    static void readIf(Object value) {
        if (value instanceof String s && s.length() >= 3) {
            int len = s.length();
            System.out.println("if: " + s + " (" + len + ")");
        } else {
            System.out.println("if: không khớp");
        }
    }

    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "không phải chuỗi";
        }
        // Only the String-matched branch remains, so text is still in scope.
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }

    static int countCharacters(Object value) {
        int count = 0;
        while (value instanceof String s && !s.isEmpty()) {
            count++;
            value = s.substring(1);
        }
        return count;
    }

    static void readSwitch(Object value) {
        switch (value) {
            case null -> System.out.println("switch: null");

            case Point(var x, var y) when x == 0 && y == 0 -> {
                String kind = "gốc";
                System.out.println("switch: " + kind);
            }

            case Point(var x, var y) -> {
                int sum = x + y;
                System.out.println("switch: điểm (" + x + "," + y
                        + "), tổng=" + sum);
            }

            case Box(Point(var x, var y), var label)
                    when label != null && !label.isBlank() -> {
                System.out.println("switch: hộp " + label
                        + " tại (" + x + "," + y + ")");
            }

            case Box b ->
                System.out.println("switch: hộp thiếu dữ liệu");

            case String s -> {
                String trimmed = s.strip();
                System.out.println("switch: chuỗi '" + trimmed + "'");
            }

            default -> System.out.println("switch: kiểu khác");
        }
    }

    public static void main(String[] args) {
        readIf("Java");
        readIf("Hi");
        System.out.println("guard: " + normalize("  java  "));
        System.out.println("guard: " + normalize(42));

        readSwitch(new Point(0, 0));
        readSwitch(new Point(2, 5));
        readSwitch(new Box(new Point(1, 3), "A"));
        readSwitch(new Box(null, "A"));
        readSwitch("  ok  ");
        readSwitch(null);
        readSwitch(10);

        System.out.println("while: " + countCharacters("abc"));
    }
}
```

Compile and run with JDK 21 or newer from the directory containing the file:

```bash
javac --release 21 -encoding UTF-8 PatternVariableBlockScopeDemo.java
java PatternVariableBlockScopeDemo
```

Output:

```text
if: Java (4)
if: không khớp
guard: JAVA
guard: không phải chuỗi
switch: gốc
switch: điểm (2,5), tổng=7
switch: hộp A tại (1,3)
switch: hộp thiếu dữ liệu
switch: chuỗi 'ok'
switch: null
switch: kiểu khác
while: 3
```

### Scope Analysis by Output

- **Two `readIf` calls:** for `"Java"`, the pattern matches and `len` is declared in the `then` block; for `"Hi"`, the `String s` pattern matches, but `s.length() >= 3` is false, so it enters `else`. `s` is not used in `else`.
- **Two `normalize` calls:** the negated branch performs an early `return`. Only string inputs reach the line using `text` after the `if` block.
- **`Point(0,0)`:** the guarded branch uses its own `x` and `y`; the variable `kind` exists within the first `case` block.
- **`Point(2,5)`:** the first guard is false, and the next `Point(var x, var y)` branch creates a **separate** set of pattern variables, computing `sum = 7` inside its corresponding block.
- **`Box(Point(1,3),"A")`:** the nested pattern extracts `x`, `y`, and `label`; the guard requires a non-null, non-blank label.
- **`Box(null,"A")`:** the nested `Point(...)` record pattern does not match; the `case Box b` branch catches the remaining `Box`, showing that eliminating one branch does not leak `x`/`y` variables to the fallback branch.
- **`String`, `null`, and integer:** each type is handled by the matching case or `default`; the variable `trimmed` only exists inside the string block.
- **`while` loop:** `s` is rebound to the value of `value` on each condition check, and is only usable inside the loop when the pattern is true.

The output illustrates how **braces create regular blocks**, while **pattern success combined with control flow** determines where a pattern variable can be used.

## 10. Quick Reference Table for Variable Scope

| Construct | Where Is the Pattern Variable Usable? | Where Is It Not Usable? |
| --- | --- | --- |
| `if (obj instanceof String s) { ... }` | `then` body | Regular `else`; after an `if` where the false path continues |
| `if (obj instanceof String s && s.length()>0)` | Right-hand side of `&&`, `then` body when the condition is true | Right-hand side of `||` instead of `&&` in a similar condition |
| `if (!(obj instanceof String s)) return;` | Code after the `if` in the same flow when the failure branch has terminated | Body of the negated branch (where the pattern did not match) |
| `if (!(obj instanceof String s)) { ... } else { ... }` | `else` block | `then` block of the negated condition |
| `while (obj instanceof String s && ...) { ... }` | Right-hand side of `&&` and loop body | After the loop in typical examples |
| `case String s when ... -> { ... }` | `when` guard and the block of that exact `case` | Other `case`s and after the `switch` |
| `case Route(..., Point(var x, var y)) -> ...` | Branch/guard after all nested patterns match | Paths where `Point(...)` does not match |

**Key takeaway:** a pattern variable's scope is not decided by a single `}` brace. Ask: **"Does any path exist to this line where the pattern has not matched?"** If yes, the compiler generally will not allow using the variable on that line.

## 11. Compile Errors and How to Fix Them

### Error 1: Using a Pattern Variable Outside a Branch That Guarantees a Match

```java
if (value instanceof String s) {
    System.out.println(s.length());
}
System.out.println(s); // ERROR: value might not be a String.
```

Fix by placing the operation that needs `s` inside the `if` body; or use negation + `return`/`throw` if you want to handle the success case at the end of the method.

### Error 2: Reading the Variable in `else` of a Positive Match

```java
if (value instanceof String s) {
    System.out.println(s);
} else {
    System.out.println(s); // ERROR: there is no String s yet.
}
```

If the requirement is to describe invalid input, use `value` itself or an error message in `else`. If you want to use `s` in the `else` branch, consider switching to the negated form as in section 5.

### Error 3: Using `||` When the Pattern Is Not Guaranteed to Match

```java
if (value instanceof String s || s.length() > 3) { // ERROR
    // ...
}
```

Fix with `&&` when the logic needs to chain an additional condition **after a successful match**. `||` is only safe with a reference to `s` when the entire expression structure guarantees `s` is already bound beforehand.

### Error 4: Using Another `case`'s Variable

```java
switch (value) {
    case String s -> System.out.println(s.length());
    case Integer n -> System.out.println(s); // ERROR: s does not belong to this branch.
    default -> System.out.println("other");
}
```

Use `n` in the `Integer` branch, or a variable declared in an outer scope if shared data is genuinely needed. Do not try to share pattern variables across `case`s.

### Error 5: Confusing Scope with Null-Safety

```java
record Message(String text) {}
if (value instanceof Message(var text)) {
    System.out.println(text.length()); // Possible NPE if text is null.
}
```

`text` **is in scope**, but the `Message.text` component can be null. Fix with `text != null` before calling methods, or validate when constructing the record. Valid scope does not guarantee non-null contents.

### Error 6: Redeclaring a Name in a Block That Already Has a Pattern Variable

```java
if (value instanceof String s) {
    String s = "new"; // ERROR: duplicates a variable name already in scope.
}
```

Choose a different name or keep a single one. Independent variables between blocks/`case`s whose scopes genuinely do not overlap can reuse names, though you should not overuse identical names to the point of hurting readability.

### Error 7: A Local Variable in a Child Block Used in the Parent Block

```java
if (value instanceof String s) {
    {
        int size = s.length();
        System.out.println(size);
    }
    System.out.println(size); // ERROR: size is only in scope inside the child block.
}
```

This is a **regular local variable** scoping error, not a special pattern variable rule. The fix is to move the `size` declaration to the outer block if it needs to be used in both places.

## 12. Method for Reading and Reviewing Variable Scope

When reviewing code containing patterns, you can follow this process:

1. **Find where pattern variables are declared**: `String s`, `Point(var x, var y)`, `case Box b`, etc.
2. **Determine the conditions for the pattern to match**: what type must the input have; for nested record patterns, which inner records must be non-null?
3. **List the control-flow branches**: `then`, `else`, right-hand side of `&&`/`||`, `while` loop, guard, and body of each `case`.
4. **For each line using a variable, ask whether execution can reach here if the pattern is false**. If not, the scope may be valid; if it can, rearrange the code.
5. **Check local blocks**: variables declared like `int len`, `String first`, etc., follow the brace scope of their own block; they do not extend outward.
6. **Check null separately**: a valid pattern variable can hold a null reference component; do not equate `scope` with safety when calling methods.
7. **Check `switch case` ordering and coverage**: do not let a general case shadow a guarded case; add `case null`/`default` according to policy.

Code organization should highlight the valid path. A negated condition with a clear `return` can make the "happy path" less nested; however, you should not turn every condition into a chain of complex negations. For `switch`, keeping `-> { ... }` branches short helps readers immediately see which variable belongs to which branch.

## 13. Exercises with Suggested Answers

**Exercise 1.** Which snippet is valid? Why?

```java
// A
if (obj instanceof String s && s.length() > 2) {
    System.out.println(s);
}

// B: NOT valid
if (obj instanceof String s || s.length() > 2) {
    System.out.println(s);
}
```

Answer: **A**. The right-hand side of `&&` is only evaluated if `instanceof` is true, so `s` already has a value. In B, the right-hand side of `||` is evaluated when `instanceof` is false, so `s` is not guaranteed to exist.

**Exercise 2.** Why is the last line valid?

```java
if (!(obj instanceof String s)) {
    throw new IllegalArgumentException("not a string");
}
System.out.println(s);
```

Answer: if execution reaches the last line, the failure branch did not continue; the compiler can conclude that the `String s` pattern definitely matched.

**Exercise 3.** Fix the error in `else`:

```java
if (obj instanceof Integer n) {
    System.out.println(n + 1);
} else {
    System.out.println(n); // wrong
}
```

Hint: in `else`, only print a message like `"Không phải Integer"` or `obj`'s data, because `n` does not exist in the failure branch.

**Exercise 4.** Given `record Box(Point point, String label) {}`, if `new Box(null, "A")` is passed into the `switch` in the complete example, which branch runs? Answer: `case Box b`, because the nested `Point(var x, var y)` does not match null.

**Exercise 5.** Extend `readSwitch`: add a `case String s when s.isBlank() -> ...` branch before `case String s -> ...`. Predict the output for a whitespace-only string. Explain why the guarded branch must appear before the general `String` branch.

**Exercise 6.** Place `System.out.println(s);` after the `while` loop in `countCharacters`. Is it valid? Answer: **no**, because the loop exit path does not guarantee the pattern still matches and `s` is no longer in scope there.

## 14. Key Takeaways and References

- Both **block scope** of regular local variables and **flow scoping** of pattern variables affect where a variable name is allowed to appear.
- `if (x instanceof T v)` allows using `v` in the success branch.
- `&&` allows using the pattern variable in subsequent conditions thanks to short-circuiting; `||` does not provide the same guarantee.
- `if (!(x instanceof T v)) return;` is an important pattern: the variable `v` remains in scope **after the `if` block** on the valid path.
- In `while`, a pattern variable is usable when the current condition has matched; it does not automatically exist after the loop.
- In a `switch` statement using `case ... -> { ... }`, pattern variables and guards belong to **that exact branch**. Nested record patterns add leaf variables but do not make them exist in non-matching branches.
- **A variable in scope can still hold `null`** if it receives a nullable reference component.

Official sources:
- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — Scope of a Declaration (`6.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
