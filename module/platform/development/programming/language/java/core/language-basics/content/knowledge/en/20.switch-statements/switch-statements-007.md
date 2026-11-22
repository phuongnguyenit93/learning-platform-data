# `yield` in Switch Expression Branch Blocks — Java 17+

## 1. Goal: A Switch Branch Produces a Value

Since Java 14, **switch expressions** have been a stable feature, so Java 17 supports them directly **without `--enable-preview`**. Unlike a switch statement, a switch expression **produces a result** to assign, return, or use inside another expression.

~~~java
int code = 2;
String label = switch (code) {
    case 1 -> "ONE";
    case 2 -> {
        String message = "TWO";
        yield message;
    }
    default -> "OTHER";
};
System.out.println(label); // TWO
~~~

In `case 2 -> { ... }`, the block contains multiple statements. The **`yield message;` statement supplies the value `"TWO"` for the entire switch expression** and finishes that branch. This is the primary purpose of `yield`.

Lesson goals:

- Distinguish `-> value` branches from `-> { ... yield value; }`.
- Understand how `yield` differs from `break` and `return`.
- Know how to use `yield` when a branch needs computation, condition checks, or temporary variables.
- Ensure valid paths **produce a value** or **throw an exception**.
- Know switch expression syntax with `case:` labels and how result types, `default`, and enums work.

## 2. When Is `yield` Not Needed?

An arrow branch that only needs **a single expression** writes the result directly:

~~~java
int number = 1;
String name = switch (number) {
    case 1 -> "ONE";
    case 2 -> "TWO";
    default -> "OTHER";
};
~~~

If you want to both log and compute a result, use a **branch block** and `yield`:

~~~java
String name = switch (number) {
    case 1 -> {
        System.out.println("Matched one");
        yield "ONE";
    }
    case 2 -> "TWO";
    default -> "OTHER";
};
~~~

**Exact stdout with `number = 1`:**

~~~text
Matched one
~~~

The final value of the switch expression is `"ONE"`; the snippet above does not print `name` yet.

**Invalid syntax:**

~~~java
// String s = switch (number) {
//     case 1 -> {
//         "ONE"; // Does not replace yield; a string literal is not a valid statement expression.
//     }
//     default -> "OTHER";
// };
~~~

A `{ ... }` block in a switch expression **does not implicitly return the value of its last expression** as in some other languages. When returning a result from a block, use `yield result;` explicitly.

## 3. Exact Role of `yield`

Syntax:

~~~java
yield expression;
~~~

Meaning:

1. Evaluates `expression` after the `yield` keyword.
2. Uses the resulting value as the result of the **enclosing switch expression**.
3. Transfers control out of the switch expression to continue the surrounding program.

Example:

~~~java
int base = 6;
int computed = switch (base) {
    case 6 -> {
        int doubleBase = base * 2;
        int extra = 3;
        yield doubleBase + extra;
    }
    default -> 0;
};
System.out.println(computed); // 15
~~~

`yield` is not a variable declaration and **does not assign directly** to `computed`; the assignment happens because the switch expression returned the value 15.

**A `yield` terminates the executed path.** Statements placed after `yield` on the same execution path cannot execute; if the compiler determines a following statement is unreachable, the program will not compile.

## 4. `yield`, `break`, `return`, `throw`: Not Interchangeable

| Construct | Purpose | Effect |
|---|---|---|
| `yield value;` | Supplies the result of a **switch expression** | Exits the switch expression, continuing the enclosing expression/statement |
| `break;` | Exits a switch **statement** or loop | Produces no value for a switch expression |
| `return value;` | Returns the result of a **method** | Exits the method, not just the switch |
| `throw exception;` | Reports an error via an exception | Does not return normally; a switch expression may have a `throw` branch |

In a traditional switch statement:

~~~java
switch (code) {
    case 1:
        System.out.println("one");
        break; // Ends the switch statement; does not return a value.
    default:
        System.out.println("other");
}
~~~

In a switch expression:

~~~java
String result = switch (code) {
    case 1 -> {
        yield "ONE"; // Value of the switch expression.
    }
    default -> "OTHER";
};
~~~

**Wrong:**

~~~java
// String result = switch (code) {
//     case 1 -> { break; } // Do not use break to exit a switch expression.
//     default -> "OTHER";
// };
// String result = switch (code) {
//     case 1 -> { break "ONE"; } // Java 17 has no break value syntax.
//     default -> "OTHER";
// };
~~~

To exit the entire method early, place `return` outside the switch expression or design branches to return values and write `return switch (...)`:

~~~java
static String describe(int code) {
    return switch (code) {
        case 1 -> "ONE";
        default -> "OTHER";
    };
}
~~~

## 5. `yield` Inside `if/else` Within a Branch Block

Not every branch computes its value with a single simple formula. Sub-conditions can be used:

~~~java
static String sign(int value) {
    return switch (Integer.signum(value)) {
        case -1 -> {
            yield "NEGATIVE";
        }
        case 0 -> "ZERO";
        default -> {
            yield "POSITIVE";
        }
    };
}
~~~

Or use multiple `yield` statements along mutually exclusive paths:

~~~java
static int normalize(int input) {
    return switch (input) {
        case 0 -> 0;
        default -> {
            if (input < 0) {
                yield -1;
            }
            yield 1;
        }
    };
}
~~~

When `input < 0`, `yield -1;` ends the switch expression; `yield 1;` runs only when the preceding condition is false.

**You do not need** an intermediate result variable after each sub-branch if a `yield` at the end of the block is clearer. However, for long branches, consider extracting the logic into a helper method for easier testing.

## 6. Every Path Must Produce a Result or Throw an Exception

A switch expression must provide a value on every path that can **complete normally**. The following example is missing a `yield` when `value <= 0`:

~~~java
// int result = switch (code) {
//     case 1 -> {
//         if (value > 0) {
//             yield value;
//         }
//         // ERROR: there is a path reaching the end of the block without producing a value.
//     }
//     default -> 0;
// };
~~~

Fix:

~~~java
int result = switch (code) {
    case 1 -> {
        if (value > 0) {
            yield value;
        }
        yield 0;
    }
    default -> 0;
};
~~~

A branch **may throw an exception** instead of returning a value:

~~~java
int result = switch (code) {
    case 1 -> 100;
    case 2 -> {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
        yield value * 2;
    }
    default -> 0;
};
~~~

This is valid: the path with `throw` does not complete normally, while the valid path has `yield`.

**Mistake to avoid:** writing `yield;` (without a value). A switch expression requires an expression after `yield`; there is no standalone `yield;` syntax.

## 7. Colon Syntax `case:` in a Switch Expression

A switch expression can still use `case VALUE:` statement groups, and when a branch computes a value it uses **`yield`**:

~~~java
static String word(int code) {
    return switch (code) {
        case 1:
            yield "ONE";
        case 2:
        case 3:
            String message = "TWO_OR_THREE";
            yield message;
        default:
            yield "OTHER";
    };
}
~~~

With `code=2`, the program returns `"TWO_OR_THREE"`.

**Differences from arrow form:**

- `case 2 -> "TWO";`: the result is written right after `->`.
- `case 2 -> { yield "TWO"; }`: must `yield` from the block.
- `case 2: yield "TWO";`: traditional statement group using `yield`.

In the `case:` form, **fall-through still matters** if a path does not end with `yield`/`throw` before the next label. In a switch expression, write clearly so there is no confusing fall-through.

**Do not mix `case:` and `case ->` in the same switch block.**

## 8. `yield` Must Return a Value Compatible with the Target Type

The compiler checks that every branch produces a value compatible with the result context. A `double` target can accept an `int` in one branch:

~~~java
double amount = switch (code) {
    case 1 -> { yield 10; }
    default -> 2.5;
};
~~~

With `code == 1`, `amount` is `10.0`. `yield` does not bypass type checking; choose an explicit result type when business logic requires consistency. The next lesson goes deeper into target typing and numeric conversions.

## 9. Case Coverage and `default`

A switch expression must be exhaustive: for `int`/`String`, `default` is usually present; for an enum, all constants can be listed. This requirement is **independent** of each block needing `yield` or `throw` on every applicable path. `default` does not automatically handle a `null` selector in standard Java 17. The next lesson focuses on proving exhaustiveness and result types.

## 10. `break` Inside a Nested Loop in a Branch Does Not Replace `yield`

An arrow branch can contain a **loop**, and `break;` inside that loop exits only the **innermost loop**. After the loop, you still need to supply a result for the switch expression:

~~~java
int count = switch (code) {
    case 1 -> {
        int sum = 0;
        for (int i = 1; i <= 5; i++) {
            if (i == 3) {
                break; // Exits for, does not return a switch value.
            }
            sum += i;
        }
        yield sum;
    }
    default -> 0;
};
~~~

When `code == 1`, the loop sums `1 + 2` and stops, and `yield sum;` returns **3**.

**Principle:** each control construct has its own purpose; a loop's `break` does not replace a switch expression's `yield`.

## 11. Variable Scope and Side Effects in Branches

Variables declared inside a rule block `case -> { ... }` are scoped to that block:

~~~java
String result = switch (code) {
    case 1 -> {
        String message = "first";
        yield message;
    }
    default -> {
        String message = "other"; // Valid: different block.
        yield message;
    }
};
~~~

Placing temporary variables inside the block avoids name collisions and improves maintainability.

Only the selected branch is evaluated at runtime:

~~~java
static int trace(String name, int value) {
    System.out.println("evaluated " + name);
    return value;
}

int n = switch (code) {
    case 1 -> {
        yield trace("one", 10);
    }
    default -> {
        yield trace("other", 20);
    }
};
~~~

With `code == 1`, only `evaluated one` is printed; the default branch is not called.

However, **do not rely on side effects to determine business results** when logging/validation can be separated from calculation. `yield` makes the returned value clear; it does not make operations inside the branch atomic or thread-safe.

## 12. Complete Java 17 Program

Save the file as **`SwitchYieldDemo.java`**:

~~~java
public final class SwitchYieldDemo {
    private SwitchYieldDemo() {}

    enum Channel { WEB, MOBILE, API }

    static String channelName(Channel channel) {
        return switch (channel) {
            case WEB -> "BROWSER";
            case MOBILE -> {
                String label = "PHONE";
                yield label;
            }
            case API -> "SERVICE";
        };
    }

    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        }
        return switch (score / 10) {
            case 10, 9 -> "A";
            case 8, 7 -> {
                String label = "B";
                yield label;
            }
            case 6, 5 -> "C";
            default -> "D";
        };
    }

    static String fromColon(int code) {
        return switch (code) {
            case 1:
                yield "ONE";
            case 2:
            case 3:
                String label = "TWO_OR_THREE";
                yield label;
            default:
                yield "OTHER";
        };
    }

    static int sign(int value) {
        return switch (value) {
            case 0 -> {
                System.out.println("zero branch");
                yield 0;
            }
            default -> {
                if (value < 0) {
                    yield -1;
                }
                yield 1;
            }
        };
    }

    static int sumUntilThree(int code) {
        return switch (code) {
            case 1 -> {
                int sum = 0;
                for (int i = 1; i <= 5; i++) {
                    if (i == 3) {
                        break;
                    }
                    sum += i;
                }
                yield sum;
            }
            default -> 0;
        };
    }

    static double promoted(int code) {
        return switch (code) {
            case 1 -> {
                yield 10;  // int: converted to double.
            }
            default -> 2.5;
        };
    }

    static int checkedDouble(int value) {
        return switch (value) {
            case 0 -> 0;
            default -> {
                if (value < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield value * 2;
            }
        };
    }

    static int trace(String name, int value) {
        System.out.println("evaluated " + name);
        return value;
    }

    static int traceChoice(int code) {
        return switch (code) {
            case 1 -> {
                yield trace("one", 10);
            }
            default -> {
                yield trace("other", 20);
            }
        };
    }

    static void statementExample(int code) {
        switch (code) {
            case 1 -> System.out.println("statement:one");
            default -> System.out.println("statement:other");
        }
    }

    public static void main(String[] args) {
        System.out.println("channel WEB=" + channelName(Channel.WEB));
        System.out.println("channel MOBILE=" + channelName(Channel.MOBILE));
        System.out.println("channel API=" + channelName(Channel.API));

        System.out.println("grade -1=" + grade(-1));
        System.out.println("grade 49=" + grade(49));
        System.out.println("grade 50=" + grade(50));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 100=" + grade(100));

        System.out.println("colon 1=" + fromColon(1));
        System.out.println("colon 2=" + fromColon(2));
        System.out.println("colon 3=" + fromColon(3));
        System.out.println("colon 4=" + fromColon(4));

        System.out.println("sign 0=" + sign(0));
        System.out.println("sign -5=" + sign(-5));
        System.out.println("sign 5=" + sign(5));

        System.out.println("loop 1=" + sumUntilThree(1));
        System.out.println("loop 9=" + sumUntilThree(9));
        System.out.println("numeric promotion=" + promoted(1));

        System.out.println("checked 7=" + checkedDouble(7));
        try {
            System.out.println(checkedDouble(-2));
        } catch (IllegalArgumentException ex) {
            System.out.println("checked -2=" + ex.getMessage());
        }

        System.out.println("trace result=" + traceChoice(1));
        statementExample(1);
        statementExample(2);
    }
}
~~~

**Requirements:** JDK 17 or higher, open terminal in the directory containing `SwitchYieldDemo.java`; no Maven/Gradle, external libraries beyond the JDK, or preview flags needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchYieldDemo.java
java -cp . SwitchYieldDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchYieldDemo.java
java -cp . SwitchYieldDemo
~~~

### Exact expected stdout

~~~text
channel WEB=BROWSER
channel MOBILE=PHONE
channel API=SERVICE
grade -1=INVALID
grade 49=D
grade 50=C
grade 70=B
grade 90=A
grade 100=A
colon 1=ONE
colon 2=TWO_OR_THREE
colon 3=TWO_OR_THREE
colon 4=OTHER
zero branch
sign 0=0
sign -5=-1
sign 5=1
loop 1=3
loop 9=0
numeric promotion=10.0
checked 7=14
checked -2=negative
evaluated one
trace result=10
statement:one
statement:other
~~~

**Quick explanation:**

1. `channelName` handles the enum exhaustively; the MOBILE branch creates a variable and uses `yield`, without needing `default`.
2. `grade` validates the 0–100 range before switching, so `grade(100)` is A and `grade(-1)` is INVALID.
3. `fromColon` illustrates that the `case:` form of a switch expression can also use `yield`.
4. `sign(0)` prints `zero branch` **before** `sign 0=0` because the call is evaluated before printing the full concatenated string.
5. `sumUntilThree(1)` adds 1 and 2; `break` exits only `for`, and `yield` returns the sum 3.
6. `promoted(1)` returns 10.0 according to the switch expression's `double` type in this context.
7. `checkedDouble(-2)` throws an exception rather than `yield`ing from the error path.
8. Only `evaluated one` appears: the default branch of `traceChoice(1)` is not evaluated.
9. `statementExample` uses `case ->` but **produces no value**, unlike the methods returning `switch`.

## 13. Common Mistakes

| Mistake or confusion | Issue | Fix |
|---|---|---|
| `case 1 -> { "ONE"; }` | Does not produce a value; literal is not a valid statement | `yield "ONE";` |
| `case 1 -> { break; }` | Cannot use `break` to exit a switch expression | `yield value;` |
| `break "ONE";` | Java 17 has no break-with-value | `yield "ONE";` |
| Forgetting `yield` on one path in a block | Switch expression may complete without a result | Ensure every path yields/throws |
| `yield;` | Missing value expression | `yield expression;` |
| Thinking `return` and `yield` are the same | `return` exits method, `yield` exits switch expression | Pick the right control level |
| Thinking `->` branches always need `yield` | Simple expressions return directly | `case 1 -> "ONE";` |
| Thinking `->` branches fall through | `->` rules do not fall through | Use separate branches or group `case 1, 2` |
| Using `case:` and forgetting fall-through effects | Can run into the next group | Design `yield`/`throw` paths clearly |
| Missing `default` for a switch expression on `int` | Does not cover all values | Add `default` |
| Trying to force branches to return incompatible types | Does not compile | Choose a valid common/target type |
| Using `break` in a loop and thinking it returned from switch | Only exits the loop | `yield` after the loop |
| Putting new pattern switch `case null` into regular Java 17 code | Different mode/feature | Check for null before switching |

## 14. Exercises with Solutions

### Exercise A — Adding `yield`

Fill in the missing part so the computation branch returns the sum:

~~~java
int n = 3;
int value = switch (n) {
    case 3 -> {
        int sum = 1 + 2 + 3;
        yield sum;
    }
    default -> 0;
};
System.out.println(value);
~~~

**Solution:** use `yield sum;`, stdout:

~~~text
6
~~~

### Exercise B — Predicting print order

~~~java
int n = 1;
String value = switch (n) {
    case 1 -> {
        System.out.println("inside");
        yield "ONE";
    }
    default -> "OTHER";
};
System.out.println(value);
~~~

**Solution:**

~~~text
inside
ONE
~~~

### Exercise C — Two paths in the same block

Requirement: `n > 0` returns 1, otherwise returns -1:

~~~java
int result = switch (code) {
    case 1 -> {
        if (n > 0) {
            yield 1;
        }
        yield -1;
    }
    default -> 0;
};
~~~

**Solution:** both paths of case 1 return a value via `yield`.

### Exercise D — Distinguishing switch statement and expression

~~~java
switch (code) {
    case 1 -> System.out.println("one");
    default -> System.out.println("other");
}
~~~

**Solution:** this is a **switch statement** because it is used to execute statements; no yield is needed. To produce a value, write `String result = switch (code) { case 1 -> "ONE"; default -> "OTHER"; };`.

### Exercise E — `break` inside a loop

Why does `break;` of a `for` loop inside a case block not replace `yield`?

**Solution:** An unlabeled `break` exits the **innermost loop**. Afterward, the case block still needs `yield` or an exception-throwing path so the switch expression produces a result.

### Exercise F — Colon-style labels

Complete the switch expression using `case:` labels:

~~~java
String result = switch (code) {
    case 1:
        yield "ONE";
    case 2:
        yield "TWO";
    default:
        yield "OTHER";
};
~~~

**Solution:** the `case:` form can be used in Java 17 switch expressions, replacing `break` with `yield` when returning a result.

## 15. Checklist and Conclusion

- [ ] Know that a switch expression produces a value and can be used in assignments/`return`.
- [ ] Know that `case x -> expression` returns a value directly.
- [ ] Know how to use `case x -> { ... yield expression; }` when a branch has multiple statements.
- [ ] Understand that `yield` ends the switch expression and passes the value outward.
- [ ] Do not replace `yield` with `break`, `return`, or `break value`.
- [ ] Ensure every path that can complete normally returns a result or throws an exception.
- [ ] Understand that `yield` can appear inside `if/else` within a branch block.
- [ ] Know that `case:`-style switch expressions also use `yield`.
- [ ] Remember arrow rules `->` do not fall through, while `case:` form requires considering fall-through.
- [ ] Understand result type rules, numeric conversion, target typing, and type errors.
- [ ] Know that switch expressions must cover the selector; an exhaustive enum may omit default.
- [ ] Distinguish `break` of a nested loop inside a branch from `yield` of the switch.
- [ ] Compile and run `SwitchYieldDemo.java` with Java 17+; verify every line of exact stdout.

**Conclusion:** In Java 17, when a **switch expression** branch is a `{ ... }` block, use **`yield value;`** to return a value for the entire switch expression. A simple branch can be written `case ... -> value` without yield. Clearly distinguish `yield` (returns the switch expression's value), `break` (exits a statement/loop), and `return` (exits a method), while ensuring complete paths and compatible result types.