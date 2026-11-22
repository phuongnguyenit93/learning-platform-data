# Limits of `_`, `const`, and `goto` as Names in Java 17+

Three cases that easily cause confusion when naming things in Java are the standalone underscore `_` along with the two words `const` and `goto`. They **cannot be used as identifiers** (names of variables, classes, methods, etc.) in Java 17, though their reasons and histories are not entirely identical:

- `_` (a single underscore alone) became a reserved keyword starting in **Java 9**. The `_` character is still allowed **inside longer names** such as `_count`, `value_`, or `__`.
- `const` and `goto` are **reserved** by Java, even though Java **does not provide a `const` constant declaration syntax or a `goto` jump statement**.
- Instead of `const` when preventing reassignment, Java uses `final`; class-level constants are commonly declared with `static final`. Instead of unconditional jumps, Java provides structured control-flow constructs such as `if`, `for`, `while`, `break`, `continue`, and `return`.

This lesson focuses on **Java/JDK 17 and later**, showing which names are valid, how to replace them with proper syntax, and how to verify them yourself with `javac`.

## 1. Why are these three names invalid?

| Syntax | On Java 17 | Explanation |
| --- | --- | --- |
| `int _ = 1;` | **Compile error** | Standalone `_` is a reserved keyword |
| `int const = 2;` | **Compile error** | `const` is a reserved keyword, even though Java implements no `const` statement |
| `int goto = 3;` | **Compile error** | `goto` is a reserved keyword, even though Java has no `goto` statement |
| `int _count = 1;` | **Valid** | The underscore is only part of the name |
| `int count_ = 2;` | **Valid** | The name is not standalone `_` |
| `int __ = 3;` | **Valid** | Two underscores form an identifier distinct from `_` |
| `int constValue = 4;` | **Valid** | Does not match the exact `const` token |
| `int gotoCount = 5;` | **Valid** | Does not match the exact `goto` token |
| `String text = "const goto _";` | **Valid** | The characters are inside a *string literal*, not identifiers |

**Key point:** the compiler treats `const` as a reserved token, whereas `constValue` is **a distinct identifier**, not split into the keyword `const` and suffix `Value`. The same applies to `gotoCount`.

In Java, names are case-sensitive. `GotoCount` is not the `goto` token, yet naming should still follow readable conventions, such as `gotoCount` for variables and `GotoCounter` for classes.

### Identifier rules to remember

A regular Java name can start with a letter, `_`, or `$` under Java character rules, but **cannot start with a digit**. Digits may appear after the first character. Reserved keywords and literals such as `true`, `false`, and `null` cannot be used as names either.

The `$` character is grammatically valid, yet usually reserved for auto-generated code or special cases; in learning code, prefer meaningful names like `totalCount` or `maxRetries`.

Distinguish these two cases:

~~~java
int item_2 = 10; // Valid.
int _item = 20;  // Valid.
// int 2item = 30; // Invalid: starts with a digit.
// int _ = 40;     // Invalid on Java 17: standalone "_".
~~~

## 2. Observing the errors from `javac`

Create the following file **`BadNames.java`** to **intentionally test the errors**:

~~~java
public class BadNames {
    public static void main(String[] args) {
        int _ = 1;
        int const = 2;
        int goto = 3;
        System.out.println("Khong chay den day");
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 BadNames.java
~~~

**Result:** compilation **fails**. `javac` will point out the tokens that cannot be used as identifiers; the exact count and wording of diagnostics may vary by compiler version. **There is no program output**, because the `main` method is never executed.

When fixing the errors, remove the invalid lines one by one or change them to:

~~~java
int _value = 1;
int constValue = 2;
int gotoCount = 3;
System.out.println(_value + constValue + gotoCount); // 6
~~~

The four statements above are a snippet **placed inside a method**, not a standalone Java file.

## 3. `const` does not replace `final` in Java

If you want a value not to be reassigned after initialization, use `final`:

~~~java
final int retryLimit = 3;
// retryLimit = 4; // Invalid: cannot reassign a final variable.
~~~

If you need a shared constant in a class, a common pattern is:

~~~java
static final int MAX_RETRIES = 3;
~~~

| Intent | Java approach | Notes |
| --- | --- | --- |
| Prevent reassigning a local variable | `final int limit = 3;` | `final` prevents reassignment, not the `const` token |
| Class constant | `static final int MAX_RETRIES = 3;` | Constant names are usually written in uppercase with `_` |
| Unchanging string value | `final String APP_NAME = "Demo";` | `String` object contents are already immutable |
| Prevent reassigning a reference | `final StringBuilder b = new StringBuilder();` | You **can still** call `b.append(...)` to mutate the object's contents |

A `static final` field is not necessarily a *compile-time constant*: that also depends on its type and **initializer expression**. For example, `static final int X = 3;` is a simple constant expression; `static final int X = Integer.parseInt("3");` is a field assigned only once whose value is computed at runtime.

**Do not confuse this:** `final` does not automatically make every object *immutable*. It restricts reassigning the variable/reference according to Java's rules.

## 4. No `goto`: use structured control flow

Java has no `goto label;` statement. Some control-flow constructs suited to practical needs:

| Purpose | Appropriate construct |
| --- | --- |
| Conditional branching | `if` / `else`, `switch` |
| Repeating multiple times | `for`, `while`, `do-while` |
| Exiting a loop | `break;` |
| Skipping the rest of an iteration | `continue;` |
| Intentionally exiting multiple loop levels | `break label;` on a labeled loop/block |
| Jumping immediately to the next iteration of an outer loop | `continue label;` with **a label placed on a loop** |
| Ending a method | `return;` or `return value;` |

A label is an **identifier followed by a colon**. You can write `scan:`, but **not** `goto:` because `goto` is a reserved keyword.

With `break outer;`, Java terminates the statement labeled `outer`. With `continue outer;`, Java advances to the next iteration of the **loop** labeled `outer`; you cannot `continue` to a label placed on an arbitrary non-loop block.

Labels should be used sparingly: multiple overlapping labels make execution flow hard to follow. For simple searches, `return` from a small method is often even clearer.

## 5. Runnable Java 17 example: valid names and labels instead of `goto`

Create a file **`ReservedNamesDemo.java`**:

~~~java
public class ReservedNamesDemo {
    private static final int MAX_RETRIES = 3;

    static int countProcessed(int[][] rows) {
        int processed = 0;

        scan:
        for (int row = 0; row < rows.length; row++) {
            for (int column = 0; column < rows[row].length; column++) {
                int value = rows[row][column];

                if (value == -1) {
                    continue scan; // Skip the rest of the row.
                }

                if (value == 99) {
                    break scan; // Exit both loops.
                }

                processed++;
            }
        }
        return processed;
    }

    public static void main(String[] args) {
        int _count = 2;
        int __ = 3;
        int constValue = 5;
        int gotoCount = 7;

        int[][] rows = {
            {4, 5},
            {7, -1, 8},
            {9, 99, 10}
        };

        System.out.println("maxRetries=" + MAX_RETRIES);
        System.out.println(
                "legalNamesSum=" + (_count + __ + constValue + gotoCount));
        System.out.println("processed=" + countProcessed(rows));
    }
}
~~~

**Compile and run on Windows PowerShell or Linux/Bash** — using the exact same commands:

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 ReservedNamesDemo.java
java ReservedNamesDemo
~~~

Expected output:

~~~text
maxRetries=3
legalNamesSum=17
processed=4
~~~

### Why is the result 4?

The data is traversed sequentially:

1. First row contains `4`, `5`: both are counted, `processed = 2`.
2. Second row: `7` is counted, `processed = 3`. Upon encountering `-1`, `continue scan;` **skips `8`** and moves to the third row.
3. Third row: `9` is counted, `processed = 4`. Upon encountering `99`, `break scan;` exits both loops, **without examining `10`**.

`continue scan` and `break scan` have well-defined control scopes, unlike an arbitrary `goto`-style jump.

Regarding variable names: `_count`, `__`, `constValue`, and `gotoCount` are all valid; their sum is `2 + 3 + 5 + 7 = 17`. Although `__` is syntactically valid, in real programs you should choose more expressive names.

`MAX_RETRIES` illustrates a `static final` declaration, **not** a `const` statement.

## 6. Common errors and misconceptions

| Misconception | Fact in Java 17 | How to handle |
| --- | --- | --- |
| "`_` is a short variable name so it must be valid" | Standalone `_` is a keyword since Java 9 | Use `_value` or a descriptive name like `count` |
| "`const` has no feature so it can be used for naming" | Still a reserved keyword | Use names like `constValue`; use `final` to prevent reassignment |
| "`goto` isn't runnable so it can be used as a label" | No; reserved keywords cannot be identifiers | Use labels like `scan:` or `outer:` |
| "Any name containing `_` is invalid" | Only **standalone** `_` is prohibited by this rule | `_count`, `item_2`, `__` are valid |
| "`final` makes objects completely immutable" | Not true for all objects | Distinguish reference reassignment from mutating object state |
| "`break outer` is identical to `goto`" | `break` only jumps to the end of a validly labeled statement | Use structured control flow |
| "`continue label` can jump to any label" | The target label must be on an appropriate loop | Only use `continue` with loop labels |
| "Code with `const`/`goto` will run and then throw an error" | Errors are caught **at compile time**, before running `main` | Fix identifiers/syntax before running `java` |

One more note: underscores in numeric literals, such as `1_000`, only improve readability of **digits**, not a variable named `_`. These are two completely different syntactic contexts.

## 7. Self-practice exercises

**Exercise 1 — Name classification.** Which names can be declared as `int` variables on Java 17?

~~~text
_    __    _score    score_    const    constValue
goto    gotoCount    2score    score2
~~~

*Answer:* Valid: `__`, `_score`, `score_`, `constValue`, `gotoCount`, `score2`. Invalid: `_`, `const`, `goto`, and `2score` (starts with a digit).

**Exercise 2 — Fix the errors.** What is wrong with the following snippet?

~~~java
// Intentionally INVALID snippet; do not place in a running example.
final int const = 3;
goto: for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
~~~

*Suggested answer:* Both `const` as a variable name and `goto` as a label are invalid. Change them to `final int maxTries = 3;` and label `loop:`, or omit the label if unnecessary.

**Exercise 3 — Predict before running.** In `ReservedNamesDemo`, if `99` is changed to `11`, what will `processed` equal?

*Answer:* `6`. There is no longer a `99` stopping value; the loop still skips `8` due to `-1`, then counts `9`, `11`, and `10`.

**Exercise 4 — Try `continue`.** Remove the label in `continue scan;` so it becomes `continue;`. With the original data, does the `processed` result change?

*Answer:* Yes: it becomes `5`. `continue;` only skips to the next iteration of the **inner loop**, so after `-1` it still processes `8`, before hitting `99` in the next row.

**Exercise 5 — `final` and objects.** Given:

~~~java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17"); // Valid.
// message = new StringBuilder("Other"); // Invalid: reassigning a final variable.
~~~

Why is the `append` statement valid? *Answer:* `final` prevents changing the reference stored in the variable, not necessarily mutating the state of the referenced object.

## Key takeaways

On **Java 17+**, standalone `_`, `const`, and `goto` **cannot be used as names**. `const` and `goto` are reserved words even though Java implements no statements with those names; standalone `_` has been reserved since Java 9, while `_` can still be part of longer identifiers. Use `final`/`static final` to restrict reassignment, and use labeled `break`/`continue`, `return`, or appropriate control-flow constructs instead of looking for `goto` syntax.
