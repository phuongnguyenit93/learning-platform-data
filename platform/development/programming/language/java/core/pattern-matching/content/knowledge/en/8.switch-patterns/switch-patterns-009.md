# Yield in switch expressions — Java Core Pattern Matching

## 1. What is Yield?

In Java, a **`switch expression`** is an expression that **evaluates to a value**. That value can be assigned to a variable, passed into a method, or returned by another method via `return`. When a `switch expression` branch only needs a single expression, Java allows a concise form:

~~~java
String label = switch (code) {
    case 200 -> "OK";
    case 404 -> "NOT_FOUND";
    default -> "UNKNOWN";
};
~~~

However, a branch often has to do multiple things: compute intermediate variables, call methods, use `if`, or normalize data. With an arrow branch that has a **block** `{ ... }`, we use **`yield expression;`** to specify **the value that the branch supplies to the `switch expression`**:

~~~java
String label = switch (code) {
    case 200 -> {
        String message = "OK";
        yield message.toLowerCase();
    }
    default -> "UNKNOWN";
};
~~~

When `code == 200`, the `switch expression` evaluates to `"ok"`. The statement `yield message.toLowerCase();` **does not terminate the enclosing method**; it finishes evaluating the current `switch expression` and returns the value to wherever the expression is used.

**Version milestones:** `switch expression` and `yield` became standard in **Java 14**; Java 17 supports them normally without enabling preview features. **Pattern matching for switch** (labels such as `case String s`, `when`, and other patterns) became standard in **Java 21**. The two features are related, though they were not introduced in the same version.

## 2. How does a switch statement differ from a switch expression?

In traditional Java, `switch` is typically a **statement**: each case executes statements or side effects and does not produce a single overall value. A `switch expression` is written to represent a computation that produces a result.

| Criterion | Switch statement | Switch expression |
| --- | --- | --- |
| Purpose | Execute statements/side effects | Produce a value |
| Usage | Stands alone as a statement | Assigned to a variable, passed as an argument, used in `return`, etc. |
| `break;` | Can exit the statement | Cannot replace `yield` |
| `yield result;` | Not used directly for a plain switch statement | Supplies a value to the switch expression |
| `case X -> expression` | Rule-style statement that can contain an appropriate statement expression | Expression branch that produces a value |
| `case X -> { ... }` | Block containing statements | Block must have a path that supplies a value via `yield` or completes abruptly in a valid way |
| Exhaustiveness | Not every switch statement needs to be exhaustive | **Must be exhaustive** |

Two ways of doing the same thing:

~~~java
// Assume code is a previously declared int variable.
String oldLabel;
switch (code) {
    case 0:
        oldLabel = "ZERO";
        break;
    default:
        oldLabel = "OTHER";
        break;
}

String newLabel = switch (code) {
    case 0 -> "ZERO";
    default -> "OTHER";
};
~~~

This is **illustrative code** placed inside a Java method. In the first example, `break;` controls exiting the switch statement. In the second example, **the value of the entire switch expression** is assigned directly to `newLabel`.

Do not distinguish a statement from an expression solely by the presence of the arrow `->`: Java also has switch statements that use `->` rules. Check whether **the switch is used as a value** or not.

## 3. Three ways to express a branch value

### 3.1. A single expression after the arrow

~~~java
String outcome = switch (status) {
    case 0 -> "NEW";
    case 1 -> "ACTIVE";
    default -> "UNKNOWN";
};
~~~

Each expression to the right of `->` is itself the result of the branch, so **do not write `yield`**. This is the preferred form when the logic is concise.

### 3.2. A block after the arrow with yield

~~~java
String outcome = switch (status) {
    case 0 -> "NEW";
    case 1 -> {
        String prefix = "ACT";
        String suffix = "IVE";
        yield prefix + suffix;
    }
    default -> "UNKNOWN";
};
~~~

A **block** is different from an **expression**: a block contains multiple statements and does not inherently have a value like an expression does. `yield prefix + suffix;` passes the result `"ACTIVE"` to the switch expression.

Valid:

~~~java
case 1 -> {
    yield "ACTIVE";
}
~~~

Invalid if `yield` is written directly after `->` without a block:

~~~java
case 1 -> yield "ACTIVE"; // COMPILE ERROR
~~~

You can fix this as `case 1 -> "ACTIVE";` or `case 1 -> { yield "ACTIVE"; }`.

A block that has a final statement/expression without `yield` is also invalid:

~~~java
case 1 -> {
    String text = "ACTIVE";
} // COMPILE ERROR: block completes normally without yielding
~~~

Java does not automatically treat the value of a variable assigned inside the block as the value of the switch expression.

### 3.3. Case groups using colons

A switch expression also accepts the traditional `case X:` syntax:

~~~java
String outcome = switch (status) {
    case 0:
        yield "NEW";
    case 1:
        yield "ACTIVE";
    default:
        yield "UNKNOWN";
};
~~~

Here, `yield` is required so that the value of the switch expression is determined. `case:` can have **fall-through**:

~~~java
String label = switch (code) {
    case 1:
    case 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

When `code` is 1 or 2, the result is `"SMALL"`. If fall-through is not needed, the syntax `case 1, 2 -> "SMALL";` is usually easier to read.

**Do not use `break "SMALL";`.** Older preview releases had a different syntax, but Java 17/21 officially use **`yield value;`** when returning a value from a colon branch of a switch expression.

## 4. Complete Java 17 program

Save as **`YieldBasicsDemo.java`**:

~~~java
public class YieldBasicsDemo {
    enum Status { NEW, ACTIVE, SUSPENDED, CLOSED }

    static String message(Status status) {
        return switch (status) {
            case NEW -> "Awaiting activation";
            case ACTIVE -> {
                String label = "Running";
                yield label + " now";
            }
            case SUSPENDED, CLOSED -> {
                String suffix = status == Status.SUSPENDED
                        ? "Paused" : "Finished";
                yield suffix;
            }
        };
    }

    static int normalizedScore(int score) {
        return switch (score / 10) {
            case 10, 9 -> 5;
            case 8 -> {
                int result = 4;
                yield result;
            }
            case 7 -> 3;
            default -> 1;
        };
    }

    static String code(int value) {
        return switch (value) {
            case 0:
                yield "ZERO";
            case 1:
            case 2:
                yield "SMALL";
            default:
                yield "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(message(Status.NEW));
        System.out.println(message(Status.ACTIVE));
        System.out.println(message(Status.SUSPENDED));
        System.out.println(message(Status.CLOSED));
        System.out.println(normalizedScore(95));
        System.out.println(normalizedScore(82));
        System.out.println(normalizedScore(61));
        System.out.println(code(0));
        System.out.println(code(2));
        System.out.println(code(4));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac YieldBasicsDemo.java
java YieldBasicsDemo
~~~

Output:

~~~text
Awaiting activation
Running now
Paused
Finished
5
4
1
ZERO
SMALL
OTHER
~~~

Explanation:

1. `NEW -> "Awaiting activation"` produces a value directly with an arrow expression, without needing `yield`.
2. `ACTIVE -> { ... yield ...; }` uses a block to compute `label`, then `yield` returns the string `"Running now"`.
3. The `SUSPENDED, CLOSED` branch combines two enum constants, computes `suffix` from `status`, and yields the result.
4. `normalizedScore` shows that `yield` **is not limited to String**: in the `score = 82` case, the `case 8` branch returns an `int` of 4.
5. The `code` method uses `case:` label groups, including fall-through from `case 1` to `case 2`.

`message` does not need `default` because it covers **all constants of the Status enum**. However, passing `status == null` into a switch on this enum will throw `NullPointerException`; that is **different** from the exhaustiveness requirement for non-null enum constants.

## 5. Yield, return, break: three different meanings

The most common confusion is seeing both `yield` and `return` in the same method:

~~~java
static String classify(int code) {
    return switch (code) {
        case 200 -> {
            String result = "OK";
            yield result;
        }
        default -> "OTHER";
    };
}
~~~

Here there are **two value transfers at two different levels**:

- `yield result;` makes the selected **switch expression** evaluate to `"OK"`.
- `return switch (...) { ... };` makes **the `classify` method** return the result of the switch expression to its caller.

If the switch expression is on the right-hand side of an assignment, execution continues after the assignment:

~~~java
static String decorate(int code) {
    String result = switch (code) {
        case 200 -> {
            yield "OK";
        }
        default -> "OTHER";
    };
    return "[" + result + "]";
}
~~~

For `code = 200`, this method returns `"[OK]"`: `yield` only finishes evaluating the switch expression, and then the final `return` line still runs.

**Intentionally invalid code:**

~~~java
static int invalidBreak(int code) {
    return switch (code) {
        case 1 -> {
            break; // COMPILE ERROR: cannot use break to exit a switch expression
        }
        default -> 0;
    };
}
~~~

~~~java
static int invalidReturn(int code) {
    return switch (code) {
        case 1 -> {
            return 10; // COMPILE ERROR: return cannot exit a switch expression
        }
        default -> 0;
    };
}
~~~

If you need the result 10, write `case 1 -> 10;` or `case 1 -> { yield 10; }`. If you truly want a branch to exit the method early in its own way, consider an `if` structure or a switch statement.

In addition, `yield` is a **yield statement** with the syntax `yield expression;`, not a function to import or an API on a class. Java treats `yield` as a *restricted identifier* with a specific syntactic role in this context.

## 6. Every path must yield or complete abruptly in a valid way

A switch expression must produce a value. For a branch block, the compiler checks **every control-flow path that can reach the end of the block**.

Valid example with multiple `yield` statements:

~~~java
static String grade(int score) {
    return switch (score / 10) {
        case 10, 9 -> "A";
        case 8 -> {
            if (score >= 85) {
                yield "B+";
            }
            yield "B";
        }
        default -> "OTHER";
    };
}
~~~

When `score` is in 80–89, one of the two `yield` statements is guaranteed to execute. Having multiple `yield` statements in the same block is not an error; each execution path runs only one `yield` statement.

A branch can **throw an exception** instead of producing a value:

~~~java
static int points(int level) {
    return switch (level) {
        case 1 -> {
            yield 10;
        }
        case 2 -> {
            throw new IllegalArgumentException("invalid level");
        }
        default -> 0;
    };
}
~~~

When `level == 2`, the caller receives the exception; the switch expression does not produce a value on that path. This is valid because the branch **completes abruptly** via `throw`. Conversely, a `case -> { ... }` block that **runs to the end without yielding or throwing** is a compile-time error.

Do not confuse "every block must contain `yield`" with the actual rule. **A single-expression branch does not need `yield`; a branch that throws an exception does not need `yield` either.** The requirement is that every path of the switch expression that completes normally must produce an appropriate value.

## 7. Exhaustiveness: yield does not replace default

`yield` only determines **the value returned from the selected branch**; it does not cause missing cases to be handled automatically.

Example:

~~~java
static String size(int count) {
    return switch (count) {
        case 0 -> "empty";
        case 1 -> "single";
        default -> {
            String text = count > 1 ? "multiple" : "invalid";
            yield text;
        }
    };
}
~~~

For an open type selector like `int`, `default` covers the remaining numbers. For an enum where all constants are listed, the compiler can prove exhaustiveness without `default`, as in the `YieldBasicsDemo` example.

In Java 21, a set of type patterns over a sealed hierarchy can also guarantee exhaustiveness when all appropriate subtypes are covered. Either way, the cases must also be **applicable**, not dominated by an earlier case, and conform to the rules of `switch`.

A switch expression that has `yield` in all its blocks is still **invalid** if it does not cover all valid input cases. These are two independent kinds of errors:

- **Missing yield**: a branch block can complete normally without producing a value.
- **Missing exhaustiveness**: there is a selector case not covered by any branch.

## 8. Java 21: yield combined with switch patterns and when

Pattern matching for switch was standardized in **Java 21**, including type patterns, `when` guards, and handling `null` with `case null`.

Save as **`YieldPatternDemo.java`**:

~~~java
public class YieldPatternDemo {

    static String describe(Object input) {
        return switch (input) {
            case null -> "NULL";

            case String s when s.isBlank() -> {
                yield "BLANK";
            }

            case String s -> {
                String cleaned = s.strip();
                yield "TEXT(" + cleaned.length() + "):" + cleaned;
            }

            case Integer n when n < 0 -> {
                String output = "NEGATIVE:" + n;
                yield output;
            }

            case Integer n -> "INT:" + n;

            default -> "OTHER:" + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  \t  "));
        System.out.println(describe(" Java "));
        System.out.println(describe(-7));
        System.out.println(describe(4));
        System.out.println(describe(2.5));
    }
}
~~~

Commands on **JDK 21**:

~~~bash
javac YieldPatternDemo.java
java YieldPatternDemo
~~~

Exact output:

~~~text
NULL
BLANK
TEXT(4):Java
NEGATIVE:-7
INT:4
OTHER:Double
~~~

Step-by-step explanation:

1. `case null` matches a `null` selector directly: the result is `"NULL"`. This is a special Java 21 switch label, not an `instanceof` type pattern.
2. `case String s when s.isBlank()` is selected only when the input is a `String` and the guard is true. The block contains `yield "BLANK";`. If the branch only needs to return this string, it can be written concisely as `-> "BLANK";`.
3. `case String s` matches the remaining `String` values. The pattern variable `s` is in scope inside the block, used to call `strip()`, and then `yield` produces the switch value.
4. `case Integer n when n < 0` matches negative integers, with an intermediate variable in the block followed by `yield`; `case Integer n` matches the remaining integers.
5. `default` matches other types; thanks to `case null`, this branch does not run for `null`, so `input.getClass()` does not cause a `NullPointerException` on `null`.

**Case ordering matters.** If `case String s` is placed before `case String s when s.isBlank()`, the more specific later branch is **dominated** — every `String` has already been caught by the general branch — and the compiler rejects it. `yield` does not solve dominance errors; the guarded branch must be placed first.

**Null also needs explicit handling.** In Java 21, a switch on a reference type without `case null` normally throws `NullPointerException` when the selector is `null`, **even if `default` is present**. `default -> { yield ...; }` does not replace `case null`.

## 9. The type of yield must match the switch expression type

In a switch expression, the values of `-> expression` branches and the expressions of `yield expression;` statements all participate in type checking. They must be compatible with the **target type context** where the switch expression appears.

Example:

~~~java
int priority = switch (category) {
    case "HIGH" -> 10;
    case "MEDIUM" -> {
        int base = 3;
        yield base + 2;
    }
    default -> 0;
};
~~~

Assume `category` is a previously declared `String` variable. The branch results are compatible with `int`, so the expression can be assigned to `int priority`.

**Intentionally invalid** code:

~~~java
int count = switch (category) {
    case "A" -> 1;
    default -> {
        yield "unknown"; // COMPILE ERROR: String is not compatible with int
    }
};
~~~

`yield` is not an arbitrary type cast. For reference types, `yield null;` can be valid if the context allows it, but it passes an **actual null value** to the consumer of the switch expression. If the result type is a primitive like `int`, `null` cannot be used in place of an integer.

Local variables created inside a case block do not escape outside the switch:

~~~java
String display = switch (mode) {
    case 1 -> {
        String temporary = "alpha";
        yield temporary.toUpperCase();
    }
    default -> "other";
};
~~~

`temporary` only exists inside the block. Outside, only **`display`**, which holds the yielded value, can be used.

## 10. Nested switch expressions: yield belongs to the innermost switch

Illustrative Java 17+ example:

~~~java
static String nested(int value) {
    return switch (value) {
        case 1 -> {
            String part = switch (value + 1) {
                case 2 -> {
                    yield "TWO";
                }
                default -> "OTHER";
            };
            yield "Outer:" + part;
        }
        default -> "NONE";
    };
}
~~~

- `nested(1)` returns `"Outer:TWO"`.
- `nested(0)` returns `"NONE"`.

`yield "TWO";` terminates the **inner switch expression** `switch (value + 1)`, causing `part` to be assigned `"TWO"`. Then `yield "Outer:" + part;` terminates the **outer switch expression**.

Therefore, do not think of `yield` as "exiting all nested switches" or "exiting the method". It targets the innermost enclosing switch expression. Nor can you place `yield` inside a lambda/method/initializer nested within a switch and use it to exit a switch expression outside those boundaries.

## 11. Common errors and how to fix them

| Situation | Why it is wrong | How to fix |
| --- | --- | --- |
| `case 1 -> yield 10;` | A yield statement is not an expression directly after the arrow | `case 1 -> 10;` or `case 1 -> { yield 10; }` |
| `case 1 -> { int x = 10; }` in a switch expression | The block has a path that completes without a value | Add `yield x;` |
| `yield;` | A yield statement requires an expression | `yield result;` |
| `break 10;` | Obsolete/invalid syntax in Java 17 and Java 21 | Use `yield 10;` |
| `break;` instead of `yield` in a switch expression | Does not supply a value and is invalid for exiting a switch expression | `yield` or `throw` |
| `return 10;` inside a switch expression | Cannot return from inside a switch expression | `yield 10;`; `return switch(...)` to return from the method |
| Has `yield` but still missing branches | `yield` does not guarantee exhaustiveness | Add the required `case`/`default` |
| `case String s` before `case String s when ...` | General branch dominates the guarded branch | Put the more specific case first |
| Using Java 21 `case null`/pattern switch with Java 17 | Not yet a standard feature in Java 17 | Use JDK 21+ |
| Using `yield` in a regular switch statement | A statement does not produce a value | Use a statement with `break`; or write a switch expression |

In particular, **`yield` is not a replacement for every `break` and `return`**. It only serves the context of producing a value from a switch expression.

## 12. How should yield be used in real code?

**A single expression:** use `-> expression` directly:

~~~java
case String s -> s.toUpperCase();
~~~

**Multiple computation steps:** use `-> { ... yield ...; }`:

~~~java
case String s -> {
    String cleaned = s.strip();
    String result = "[" + cleaned + "]";
    yield result;
}
~~~

**Branching inside a case:** multiple valid `yield` statements may be used:

~~~java
case String s -> {
    if (s.isBlank()) {
        yield "(empty)";
    }
    yield s.strip();
}
~~~

The three snippets above are **illustrative branches of a switch expression with Java 21 type patterns**, not standalone programs. For a simple branch, do not add a block and `yield` just for the sake of having multiple lines. For a complex branch, a block and `yield` help clearly separate the processing steps and the returned value.

For switch patterns, handle `case null` if needed, place specific guards before general branches, check exhaustiveness, and ensure every block is valid. Do not lump dominance errors, null selector errors, and missing-yield errors into one cause: those are three distinct rules.

## 13. Self-check questions

**Question 1.** Are both of the following forms valid in a switch expression?

~~~java
case 200 -> "OK";
~~~

~~~java
case 200 -> {
    yield "OK";
}
~~~

**Answer:** Yes. The first form is more concise if the branch only needs a single expression.

**Question 2.** In `return switch(code) { case 1 -> { yield 10; } default -> 0; };`, which statement terminates the switch expression, and which statement terminates the method?

**Answer:** `yield 10;` supplies the value to the switch expression; `return` returns the value of the switch expression from the method.

**Question 3.** Does the snippet below compile?

~~~java
int n = switch (code) {
    case 1 -> {
        int value = 10;
    }
    default -> 0;
};
~~~

**Answer:** No. The `case 1` block completes normally without yielding. You need to add `yield value;`.

**Question 4.** In Java 21, can `case String s when s.isBlank()` be placed after `case String s`?

**Answer:** No. The broader `String` branch dominates the guarded branch; swap the order of the cases.

**Question 5.** In the nested switch example, which switch does `yield "TWO";` return to?

**Answer:** The inner switch `switch (value + 1)`; the outer switch still needs another value from `yield "Outer:" + part;`.

## 14. Official specification references

- [Java Language Specification 21 — switch Expressions, Section 15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression syntax, typing, exhaustiveness, and control flow.
- [Java Language Specification 21 — The yield Statement, Section 14.21](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21): syntax and meaning of `yield expression;`.
- [Java Language Specification 21 — The switch Statement, Section 14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch statements, switch rules, case labels.
- [Java Language Specification 21 — Patterns, Section 14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): pattern matching and related rules.

**Takeaway:** For a `switch expression`, `case ... -> expression` directly produces a value; when a multi-step block is needed, use `case ... -> { ... yield value; }`, or `yield` in a colon branch. `yield` returns a value to the **innermost switch expression**, and does not replace a method's `return` or a switch statement's `break`. In Java 21, type patterns/`when` and `case null` make branch selection richer, but the `yield` rules remain the same.
