# `yield` in `switch expression` (Java 21+)

## 1. The Role of `yield`

Since Java 14 (JEP 361), `switch` can be used as an **expression** (*switch expression*) that returns a value, rather than only as a control-flow statement. That result can be assigned to a variable, passed as an argument, or returned from a method:

~~~java
int score = 85;
String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> "B";
    default -> "C";
};
System.out.println(grade); // B
~~~

With a `case X -> expression;` branch, the expression on the right-hand side of `->` is evaluated and becomes the result of the entire switch expression; **there is no need to write `yield`**.

However, a branch may need to run multiple statements before producing a result: variable declarations, intermediate processing, data validation, or `if` branches. In that case, use `-> { ... }` and **`yield value;`** to supply a value to the enclosing switch expression:

~~~java
int score = 85;
String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> {
        String label = "B";
        yield label;
    }
    default -> "C";
};
System.out.println(grade); // B
~~~

In the `case 8` block, the `yield label;` statement terminates the **switch expression**, not the enclosing method. The method can still continue executing after the expression has produced its value.

**Version:** `yield` and switch expressions have been stable since Java 14. Type patterns, record patterns, and `when` guards in `switch` have been stable since **Java 21** (JEP 441/JEP 440). This article uses **JDK 21+** to demonstrate all of those capabilities together; `--enable-preview` is not needed.

## 2. Three Branch Forms in Arrow-Style Switch Expressions

| Branch form | When to use | Behavior |
| --- | --- | --- |
| `case X -> expression;` | Only a single expression is needed | Evaluates to the expression value, without `yield` |
| `case X -> { ... yield value; }` | Multiple statements are needed | `yield` supplies the value for the switch expression |
| `case X -> throw new ...;` | Error data branch | Throws an exception, no need to supply a value |

Example:

~~~java
int quantity = 3;
String message = switch (quantity) {
    case 0 -> "Hết hàng";
    case 1 -> "Một sản phẩm";
    case 2, 3 -> {
        String detail = "Số lượng: " + quantity;
        yield detail;
    }
    default -> throw new IllegalArgumentException("Ngoài phạm vi");
};
System.out.println(message); // Số lượng: 3
~~~

`yield` is a **statement** with the syntax `yield <expression>;`; the expression of `yield` must not have type `void`. Therefore:

~~~java
// The standalone cases below illustrate syntax and are not a standalone program.

// WRONG: yield is a statement and cannot be placed directly after the arrow.
// case 2 -> yield "Hai";

// RIGHT, direct expression:
case 2 -> "Hai";

// RIGHT, block with yield:
case 2 -> {
    yield "Hai";
}
~~~

If no intermediate variables or multi-line logic are needed, prefer the expression branch because it is concise and easy to understand.

## 3. Distinguishing `yield`, `return`, `break`, and `throw`

- **`yield result;`**: turns `result` into the result of the **nearest enclosing switch expression**. This is what `yield` is for.
- **`return result;`**: returns a value from the enclosing **method or lambda**. `return` is not used in place of `yield` to jump out of a switch expression.
- **`break;`**: terminates a loop or a **switch statement** in valid structure; it does not provide a result for a switch expression. `break` cannot be used to exit a switch expression that needs a value.
- **`throw exception;`**: causes evaluation to complete abruptly. A branch can `throw` instead of `yield` because there is no normal execution path that requires a value.

Compare the two methods:

~~~java
static String withMoreWork(int level) {
    String name = switch (level) {
        case 1 -> "Cơ bản";
        case 2 -> {
            yield "Nâng cao";
        }
        default -> "Khác";
    };
    return "Cấp độ: " + name;
}

static String returnSwitch(int level) {
    return switch (level) {
        case 1 -> "Cơ bản";
        case 2 -> {
            yield "Nâng cao";
        }
        default -> "Khác";
    };
}
~~~

`withMoreWork(2)` returns `"Cấp độ: Nâng cao"`: after `yield`, Java continues with `return "Cấp độ: " + name;`. `returnSwitch(2)` returns `"Nâng cao"`: `return` applies to the **entire switch expression** after the branch has produced a value.

Do not confuse `yield` with returning from a method or with the `break` statement of a traditional switch statement.

## 4. All Normal Paths Must Produce a Value

A switch expression must have a result type, and the selected branch **must not complete normally without returning a value**. Every execution path in a block must reach a `yield`, or complete abruptly such as with `throw`.

Valid example:

~~~java
static String sign(int n) {
    return switch (n) {
        case 0 -> "zero";
        default -> {
            if (n > 0) {
                yield "positive";
            } else {
                yield "negative";
            }
        }
    };
}
~~~

Both branches of the `if` call `yield`. Conversely, the following snippet **intentionally does not compile**:

~~~java
int result = switch (1) {
    case 1 -> {
        int value = 10;
        System.out.println(value);
        // Missing yield or throw; the block can complete normally.
    }
    default -> 0;
};
~~~

Fix this by adding `yield value;` after `println`. If there is an error path, `throw` can be used:

~~~java
int size = 4;
int result = switch (size) {
    case 0 -> 0;
    default -> {
        if (size < 0) {
            throw new IllegalArgumentException("size âm");
        }
        yield size * 3;
    }
};
System.out.println(result); // 12
~~~

On the normal path `size >= 0`, the block produces the value `size * 3`; on the negative size path, it throws an exception. **Do not** write `yield System.out.println("x");` because `println` has type `void`. Call `println` separately and then `yield` an appropriate value.

## 5. Combining `yield` with Type Patterns in `case` (Java 21)

Pattern matching for `switch` allows checking an object's type and introducing a pattern variable directly in the `case` label. Once matched, the variable can be used in the guard and the corresponding block:

~~~java
static String describe(Object input) {
    return switch (input) {
        case String text -> {
            String clean = text.strip();
            yield "Văn bản: " + clean;
        }
        case Integer number -> {
            int doubled = number * 2;
            yield "Số nhân đôi: " + doubled;
        }
        case null -> "Không có dữ liệu";
        default -> "Loại khác";
    };
}
~~~

- `case String text` matches only when `input` is a `String` and not `null`. `text` has the static type `String` inside the block.
- `case Integer number` binds the variable `number` of type `Integer` in another branch.
- `yield` returns the result string; it does **not** check types and does **not** bind pattern variables.
- Each pattern variable is scoped to its own branch; `text` is no longer in scope in `case Integer number`.

**`case null`** is needed if the selector can be null and you want to handle it intentionally. For a switch expression over a reference type, `default` does not automatically catch null; without `case null`, a null input typically causes a `NullPointerException`.

## 6. `when` Guards, Pattern Ordering, and `yield`

A `when` guard adds a condition to a case pattern. For example, distinguishing a blank string from a regular string:

~~~java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> {
            yield "Chuỗi trắng";
        }
        case String s -> {
            String normalized = s.strip();
            yield "Nội dung: " + normalized;
        }
        case null -> "null";
        default -> "Khác";
    };
}
~~~

Flow: Java checks whether `input` is a `String`, and only then evaluates `s.isBlank()`. If the guard is true, execution enters the first block; if the guard is false, it continues searching for a matching case and can match `case String s` below.

**Order matters:** `case String s when s.isBlank()` must appear **before** the unguarded `case String s`. If the general String pattern is placed first, it shadows the more specific pattern and can cause a compile-time dominance error.

You can mix `-> expression` and `-> { ... yield ...; }` branches in the same arrow-style switch expression; only use a block in branches that actually have multiple steps.

## 7. `yield` After Deconstructing a Record Pattern

Java 21 record patterns allow deconstructing component values directly in `case`:

~~~java
record Point(int x, int y) {}

static String formatPoint(Object obj) {
    return switch (obj) {
        case Point(int x, int y) when x == y -> {
            int total = x + y;
            yield "Điểm chéo, tổng = " + total;
        }
        case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")";
        case null -> "null";
        default -> "Không phải Point";
    };
}
~~~

`x` and `y` in the first branch are bound from the two components of `Point`, and can be used in `when x == y` and inside the block. `yield` supplies the result string computed from them. The second branch uses `var` to infer that `x` and `y` have type `int`, returning the expression directly.

In this example:

- Record pattern: determines whether the object matches the record structure and binds its components.
- Guard: an additional condition on the deconstructed data.
- Yield: only **produces the value returned from the switch expression** once the branch is selected.
- The general branch `Point(var x, var y)` is placed after the guarded branch to avoid shadowing the specific branch.

For reference-type components, `var` can receive `null`. Do not assume every deconstructed component is non-null; if you need to call a method on a component, check it before using it.

## 8. The `case: ... yield` Form and Differences from a Switch Statement

In addition to arrow syntax, switch expressions support colon-labeled groups and `yield`:

~~~java
int n = 2;
int value = switch (n) {
    case 0:
        yield 0;
    case 1, 2:
        yield n * 10;
    default:
        yield -1;
};
System.out.println(value); // 20
~~~

These cases belong to a **switch expression** because the entire `switch (n) { ... }` is assigned to `value`. Branches using `:` must provide a result via `yield`. Colon syntax follows traditional control-flow rules and can easily cause confusion about fall-through, so new code usually prefers `case ... -> ...`.

**Do not mix** `case X:` labels and `case Y ->` rules in the same switch block. Choose one form consistently.

Compared to a **switch statement**:

~~~java
int n = 2;
switch (n) {
    case 2:
        System.out.println("Hai");
        break;
    default:
        System.out.println("Khác");
}
~~~

Here `break` only terminates the switch statement. There is no value for the entire `switch` to assign to a variable, and `yield` is not a way to return a value from a switch statement.

## 9. Exhaustiveness, Result Types, and Nested Switches

**Exhaustiveness:** a switch expression must cover all cases that the Java type checker considers possible. With an `Object` selector, `default` is usually needed for unlisted types; `case null` may be needed to handle null separately. With an enum or sealed hierarchy whose branches already cover every case, `default` is sometimes unnecessary under exhaustiveness rules.

**Value type:** the branches of a switch expression must return values compatible with the expression's result type. For example:

~~~java
static double asDouble(Object input) {
    return switch (input) {
        case Integer n -> n.doubleValue();
        case Double d -> {
            yield d;
        }
        case null -> 0.0;
        default -> -1.0;
    };
}
~~~

Every value-producing branch is compatible with `double`. Branches that reject data can use `throw` without producing a value.

**Nested switch expressions:** `yield` always targets the **nearest** enclosing switch expression:

~~~java
int outer = 1;
int inner = 2;

int answer = switch (outer) {
    case 1 -> {
        int part = switch (inner) {
            case 0 -> 0;
            case 2 -> {
                yield 20;      // Result of switch(inner).
            }
            default -> -1;
        };
        yield part + 1;        // Result of switch(outer).
    }
    default -> 0;
};
System.out.println(answer); // 21
~~~

`yield 20` gives `part = 20`, and execution continues to compute `part + 1`. Only `yield part + 1` completes the outer switch. `yield` cannot be used to jump across the boundary of a method, constructor, initializer, or lambda nested inside a switch expression.

## 10. Complete Java 21+ Example with Verified Output

Save to file **`YieldSwitchDemo.java`**:

~~~java
public class YieldSwitchDemo {
    record Point(int x, int y) {}
    record Box(String label, int quantity) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Không có dữ liệu";
            case String s when s.isBlank() -> {
                yield "Chuỗi chỉ có khoảng trắng";
            }
            case String s -> {
                String clean = s.strip();
                yield "Văn bản: " + clean;
            }
            case Point(int x, int y) when x == y -> {
                int sum = x + y;
                yield "Điểm chéo, tổng = " + sum;
            }
            case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")";
            case Box(var label, var quantity) when quantity > 0 -> {
                String name = label == null ? "?" : label.strip();
                yield name + ": " + quantity;
            }
            default -> "Không hỗ trợ";
        };
    }

    static int level(int score) {
        return switch (score) {
            case 0: yield 0;
            case 1, 2: yield 10 * score;
            default: yield -1;
        };
    }

    static int length(Object input) {
        return switch (input) {
            case String s -> {
                if (s.isBlank()) {
                    yield 0;
                }
                yield s.length();
            }
            case null -> 0;
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe("   "));
        System.out.println(describe(new Point(4, 4)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(new Box("  sách  ", 3)));
        System.out.println(describe(new Box(null, 2)));
        System.out.println(describe(new Box("bút", 0)));
        System.out.println(describe(null));
        System.out.println(level(2));
        System.out.println(level(9));
        System.out.println(length("  "));
        System.out.println(length("Java"));
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac --release 21 YieldSwitchDemo.java
java YieldSwitchDemo
~~~

Output:

~~~text
Văn bản: Java
Chuỗi chỉ có khoảng trắng
Điểm chéo, tổng = 8
Điểm (2, 5)
sách: 3
?: 2
Không hỗ trợ
Không có dữ liệu
20
-1
0
4
~~~

Explanation of the cases:

- Non-blank string: `strip()` and `yield` return the normalized string.
- Whitespace-only string: the `s.isBlank()` guard matches the first branch.
- `Point(4, 4)`: record pattern and `x == y` guard, computes the sum and then `yield`s.
- `Point(2, 5)`: arrow branch with a direct expression.
- `Box("  sách  ", 3)`: the `label` component variable is processed and then `yield`ed; `Box(null, 2)` uses `"?"` to handle a null component.
- `Box("bút", 0)`: the `quantity > 0` guard is false, falling through to `default`.
- Null selector enters `case null`.
- `level` demonstrates `case: yield` syntax; `length` demonstrates that you can `yield` early on one path, then `yield` on the remaining path.

## 11. Common Mistakes and How to Fix Them

| Mistake | Cause | Fix |
| --- | --- | --- |
| `case 1 -> yield 10;` | `yield` is a statement, not an expression on the right-hand side of an arrow | `case 1 -> 10;` or `case 1 -> { yield 10; }` |
| Block case missing `yield` | The branch can complete normally without a value | Add `yield` on every required path or `throw` |
| `yield System.out.println(...);` | `println` returns `void` | Separate the print statement and `yield` a value |
| Using `break` to get a value from a switch expression | `break` does not supply a value and cannot jump out of a switch expression | Use `yield value;` |
| Using `return` instead of `yield` in a case block | `return` targets the method, not the switch expression | `yield` in the branch, `return switch(...)` at the method level if needed |
| Using only `default` and expecting it to handle null | `default` is not a null branch | Add `case null` |
| Forgetting to cover a possible selector type | The switch expression may not be exhaustive | Add specific cases or `default` |
| Placing a general `String s` branch before `String s when ...` | The general branch dominates the specific branch | Place the guarded branch first |
| Mixing `case X:` and `case Y ->` | The two switch block forms cannot be mixed | Use one form consistently |
| Using `case ... when` or record patterns on JDK 17 as standard syntax | Pattern switch and record patterns are standard from Java 21 | Use JDK 21+ |
| Confusing `yield` with exiting the entire method | `yield` only completes the nearest switch expression | Use `return` outside the expression if you want to return from the method |

## 12. Exercises and Solutions

**Exercise 1.** Write a method using `return switch (obj)` to return `"blank"` if `obj` is a blank string, the stripped string if it is a regular string, `"null"` if the input is null, and `"other"` for other types. Use `yield` in the String-handling block.

**Exercise 2.** What is missing in the following snippet?

~~~java
int n = 2;
int x = switch (n) {
    case 2 -> {
        int doubled = n * 2;
        // No value produced for this branch yet.
    }
    default -> -1;
};
~~~

**Exercise 3.** For the nested switch in section 9, what is the printed result? Which switch does each of the two `yield` statements target?

**Exercise 4.** Given `record Point(int x, int y) {}`, write a case with `when x == y`, compute the sum of the two coordinates, and `yield` the string `"Tổng = ..."`. Why must this case appear before the general case `Point(var x, var y)`?

**Solution hints:**

~~~java
// Exercise 1: place inside a class.
static String normalize(Object obj) {
    return switch (obj) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            yield s.strip();
        }
        case null -> "null";
        default -> "other";
    };
}

// Exercise 2: add 'yield doubled;' at the end of the case 2 block.

// Exercise 4: branch placed in a switch over Object or Point:
// case Point(int x, int y) when x == y -> {
//     yield "Tổng = " + (x + y);
// }
~~~

Exercise 3 produces `21`; `yield 20` targets the `inner` switch, while `yield part + 1` targets the `outer` switch. Exercise 4 requires placing the guarded branch first so the general branch does not dominate it.

## References

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expressions and `yield` since Java 14.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns and `when` since Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns since Java 21.
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
- [JLS 21, `14.21 Yield](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21) and [`15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
