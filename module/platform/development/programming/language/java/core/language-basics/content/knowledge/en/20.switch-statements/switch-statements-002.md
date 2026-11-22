# `case`, `default`, and Duplicate Labels in Java

> **Java core — language-basics / Switch**  
> **Environment:** Java 17+, preview disabled, standard library only.  
> **Goal:** Choose valid `case` labels, understand `default` and non-matching cases, recognize duplicate label errors; distinguish traditional `case ...:` syntax from modern `case ... ->` syntax.

## 1. What Are `case` Labels Used For?

`switch` evaluates a selector expression (*selector*) and matches the result against labels. In an `if/else if` chain, we write conditions; with `switch`, we list the matched values:

~~~java
int code = 2;

switch (code) {
    case 1:
        System.out.println("ONE");
        break;
    case 2:
        System.out.println("TWO");
        break;
    default:
        System.out.println("OTHER");
}
// Output: TWO
~~~

Here:

- `case 1:` and `case 2:` are labels for two values.
- `default:` is the starting point when no `case` label matches.
- `break` exits the statement-form `switch`, preventing execution from continuing from the selected branch into subsequent branches.

A `switch` can have multiple `case` labels, but **must not have two labels with the same value** in the same block.

## 2. Which Values Can Be Used as Labels?

In standard Java 17 `switch` (without preview enabled), selectors support integer types `byte`, `short`, `char`, `int`, their corresponding wrapper classes, `String`, and `enum`. Do not directly use `long`, `float`, `double`, or `boolean` as selectors.

For integers/strings, a normal `case` label must be a **compile-time constant expression** (*compile-time constant*) of a type compatible with the selector; it cannot be a value computed at runtime:

~~~java
static final int BASE = 2;

// Valid in switch (code):
// case 1:
// case BASE + 1:     // Constant 3 because BASE is a constant variable.
// case 'A':          // Character has a corresponding numeric value; valid for int.
~~~

Invalid examples (for illustration only, do not include in runnable code):

~~~java
int runtime = 2;
// case runtime:             // Not a compile-time constant.
// case Integer.parseInt("2"): // Method call is not a compile-time constant.
~~~

If the selector is `byte`, the integer label `case 128` is invalid because it is outside the `byte` value range. If the selector is `String`, use constant string labels like `case "go"`. For `enum`, labels use the **unqualified constant name**, e.g., `case LOW`, not `case Level.LOW` in standard Java 17 switch.

## 3. Duplicate Labels: Immediate Compile-Time Error

Duplicate labels do not need to be written identically. Two constant expressions that **evaluate to the same value** are also duplicates:

~~~java
// DOES NOT COMPILE — both labels equal 2:
// switch (number) {
//     case 2:   System.out.println("first");  break;
//     case 1+1: System.out.println("second"); break;
// }
~~~

Similarly:

~~~java
// DOES NOT COMPILE in a switch (int):
// case 65:
// case 'A': // Character 'A' has value 65.

// DOES NOT COMPILE in a switch (String):
// case "go":
// case "g" + "o": // Same constant string "go".
~~~

Duplicate labels do not become "two valid options" like two independent `if` statements. Java **refuses to compile** because two labels in the same `switch` cannot be distinguished.

**How to fix:** Merge labels if different values truly share one handler, or keep only **one** label for the same value. You cannot fix duplicate labels by adding `break`.

## 4. Grouping Multiple Valid Labels into One Branch

In traditional `switch`, multiple consecutive `case` labels can lead to the same body:

~~~java
switch (code) {
    case 1:
    case 2:
        System.out.println("SMALL");
        break;
    default:
        System.out.println("OTHER");
}
~~~

In Java 17 arrow syntax, use a comma-separated label list:

~~~java
String group = switch (code) {
    case 1, 2 -> "SMALL";
    case 3 -> "THREE";
    default -> "OTHER";
};
~~~

**`case 1, 2` represents two different values in the same group** — completely valid. However, `case 1, 1` or placing another `case 2` in a different branch is still a duplicate label.

Arrow `->` branches **do not fall through automatically** (*no fall-through*); `switch` can also be used as an expression to return a value. Do not mix `case ...:` and `case ... ->` in the same `switch`.

## 5. Role and Placement of `default`

`default` is used when **no `case` label matches**, not as "a branch that always runs after all cases":

~~~java
int code = 9;
switch (code) {
    case 1:
        System.out.println("ONE");
        break;
    default:
        System.out.println("OTHER"); // code = 9.
}
~~~

Key points to remember:

- At most **one** `default` label in a `switch`; declaring `default` twice is a compile error.
- For a `switch` **statement**, `default` may be omitted; if no label matches and there is no `default`, the `switch` body is skipped.
- For a `switch` **expression**, every possible value must be covered (*exhaustive*); typical `int` or `String` labels require `default`. In contrast, a switch expression on an `enum` can omit `default` if all enum constants are listed.
- In colon-style `:` `switch`, `default` **is not required to be last**. If `break` is missing, execution can continue from `default` into a subsequent `case`.
- `default` does not handle `null` for `String`/enum/wrapper selectors in non-preview Java 17; a `null` selector throws `NullPointerException` before entering any branch.

Example intentionally placing `default` between labels to demonstrate fall-through:

~~~java
static String unusualOrder(int code) {
    StringBuilder result = new StringBuilder();
    switch (code) {
        case 0:
            result.append("ZERO");
            break;
        default:
            result.append("DEFAULT-");
        case 2:
            result.append("TWO");
            break;
    }
    return result.toString();
}
// unusualOrder(0) = "ZERO"
// unusualOrder(2) = "TWO"
// unusualOrder(9) = "DEFAULT-TWO"
~~~

This syntax is valid, but **not recommended** unless fall-through is intentional. In practice, place `default` clearly, use `break` with `:`, or prefer `->` when only a single branch should run.

## 6. `String`, `enum`, and Java 17 Compatibility

`switch` on `String` matches **string content** rather than just comparing two references with `==`; it is case-sensitive:

~~~java
String text = new String("go");

String action = switch (text) {
    case "go" -> "MOVE";
    case "stop" -> "HALT";
    default -> "UNKNOWN";
};
// action = "MOVE".
~~~

With `enum`:

~~~java
enum Level { LOW, MEDIUM, HIGH }

static String label(Level level) {
    return switch (level) {
        case LOW -> "low";
        case MEDIUM -> "medium";
        case HIGH -> "high";
    };
}
~~~

The `switch` expression on `Level` lists all three constants, so `default` is unnecessary. If `level == null`, it still throws `NullPointerException`. Check for `null` **before the switch** if data may be missing.

Syntax like `case null` or type patterns (*pattern matching for switch*) does not belong to standard Java 17 switch without preview enabled; do not use them to replace `default` in this lesson.

## 7. Standalone Java 17+ Program

Create file **`SwitchCaseLabelsDemo.java`**:

~~~java
public final class SwitchCaseLabelsDemo {
    private static final int BASE = 2;

    enum Level { LOW, MEDIUM, HIGH }

    private static String classic(int code) {
        switch (code) {
            case 1:
            case 2:
                return "SMALL";
            case 3:
                return "THREE";
            default:
                return "OTHER";
        }
    }

    private static String arrow(int code) {
        return switch (code) {
            case 1, 2 -> "SMALL";
            case 3 -> "THREE";
            default -> "OTHER";
        };
    }

    private static String constantCase(int code) {
        return switch (code) {
            case BASE + 1 -> "THREE";
            default -> "OTHER";
        };
    }

    private static String byText(String text) {
        return switch (text) {
            case "go" -> "MOVE";
            case "stop" -> "HALT";
            default -> "UNKNOWN";
        };
    }

    private static String byLevel(Level level) {
        return switch (level) {
            case LOW -> "low";
            case MEDIUM -> "medium";
            case HIGH -> "high";
        };
    }

    private static String unusualOrder(int code) {
        StringBuilder result = new StringBuilder();
        switch (code) {
            case 0:
                result.append("ZERO");
                break;
            default:
                result.append("DEFAULT-");
            case 2:
                result.append("TWO");
                break;
        }
        return result.toString();
    }

    public static void main(String[] args) {
        System.out.println("classic1=" + classic(1));
        System.out.println("classic2=" + classic(2));
        System.out.println("classic3=" + classic(3));
        System.out.println("classic9=" + classic(9));
        System.out.println("arrow2=" + arrow(2));
        System.out.println("arrow3=" + arrow(3));
        System.out.println("arrow9=" + arrow(9));
        System.out.println("constant3=" + constantCase(3));

        System.out.println("stringGo=" + byText(new String("go")));
        System.out.println("stringStop=" + byText("stop"));
        System.out.println("stringOther=" + byText("GO"));
        System.out.println("enumLow=" + byLevel(Level.LOW));
        System.out.println("enumHigh=" + byLevel(Level.HIGH));

        System.out.println("default0=" + unusualOrder(0));
        System.out.println("default2=" + unusualOrder(2));
        System.out.println("default9=" + unusualOrder(9));

        try {
            byText(null);
        } catch (NullPointerException ex) {
            System.out.println("nullSelector=NullPointerException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 SwitchCaseLabelsDemo.java
java SwitchCaseLabelsDemo
~~~

**Exact expected stdout:**

~~~text
classic1=SMALL
classic2=SMALL
classic3=THREE
classic9=OTHER
arrow2=SMALL
arrow3=THREE
arrow9=OTHER
constant3=THREE
stringGo=MOVE
stringStop=HALT
stringOther=UNKNOWN
enumLow=low
enumHigh=high
default0=ZERO
default2=TWO
default9=DEFAULT-TWO
nullSelector=NullPointerException
~~~

The example `default9=DEFAULT-TWO` intentionally demonstrates **fall-through in `:`-style switch** when `default` appears before `case 2` without a `break`. This is not the behavior of the `->` form.

## 8. Common Mistakes and Exercises

| Error | Cause | How to avoid |
| --- | --- | --- |
| `case 2` and `case 1 + 1` | Duplicate constant value | Keep only one value |
| `case value` with a regular variable | Value is not a compile-time constant | Use a valid constant or `if` |
| Two `default` labels | `default` must be unique | Have only one default branch |
| Forgetting `break` in `:` syntax | Unintended fall-through | Add `break` or use `->` |
| Assuming `default` catches `null` | Non-preview Java 17 does not do this | Check `null` beforehand |
| Writing `case Level.LOW` for enum | Enum labels must be unqualified names | Use `case LOW` |
| Omitting `default` when switch expression is not exhaustive | No result for all values | Add `default` or cover all enum values |

**Exercise 1.** Write a `switch` so that codes 1 and 2 share the result `"SMALL"`, code 3 yields `"THREE"`, and any other code yields `"OTHER"`. Implement it using both `:` and `->`.

**Exercise 2.** Explain why in the same `int` switch, two labels `case 3` and `case 1 + 2` are rejected despite being written differently.

**Exercise 3.** Try adding a second `default` label to a sample `switch`. State what kind of error occurs and how to fix it.

**Exercise 4.** Predict `unusualOrder(9)` and `unusualOrder(2)`. Why are they not the same even though `default` is placed before `case 2`?

**Exercise 5.** Write a `switch` expression on an enum with all three constants; explain when `default` can be omitted, and how to handle it beforehand if the selector is nullable.

### Key Takeaway

**`case` selects valid constant values, and labels in the same `switch` must not have duplicate values.** `default` is the branch when no case matches, can appear at most once, and does not automatically handle `null` in standard Java 17. Use multiple **distinct** labels to share handling; remember `break` in `:` syntax or use `->` to prevent unintended fall-through.