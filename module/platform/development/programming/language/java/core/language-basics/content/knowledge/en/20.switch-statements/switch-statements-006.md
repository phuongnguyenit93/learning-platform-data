# Switch Expressions Returning a Value — Java 17+

Since Java 14, `switch` is no longer only a **branching statement** (*switch statement*) — it also has an **expression** form (*switch expression*) to **produce a value**. Java 17 supports this feature in full without needing to enable preview.

~~~java
int month = 7;
String season = switch (month) {
    case 12, 1, 2 -> "winter";
    case 3, 4, 5 -> "spring";
    case 6, 7, 8 -> "summer";
    case 9, 10, 11 -> "autumn";
    default -> "invalid";
};
// season == "summer"
~~~

A `switch` expression can appear on the right-hand side of an assignment, inside a `return`, or as an argument to a method. **Difference from a switch statement:** the entire `switch (...) { ... }` construct evaluates to **a single value**, rather than merely controlling statements.

## 1. Syntax and Core Rules

The most common form uses **switch rules** with the arrow `->`:

~~~java
String label = switch (number) {
    case 0 -> "zero";
    case 1, 2 -> "small";
    default -> "other";
};
~~~

Java evaluates `number`, selects the matching label, and then evaluates the expression after `->`. **No fall-through occurs** from one branch to the next, and **no `break` is needed** to stop falling through.

| Property | Switch expression |
| --- | --- |
| Role | Value-producing expression, can be assigned or used in `return` |
| Single-branch value | `case X -> expression;` |
| Multi-statement branch | `case X -> { ... yield value; }` |
| Multiple labels with same result | `case A, B -> value;` |
| Exhaustiveness | Must be **exhaustive**: every input value has a handling path |
| Fall-through with `->` form | No |
| Semicolon `;` after `}` | Required when the whole construct sits inside an assignment statement |

Branches with different types must satisfy the **type rules of switch expressions** and the usage context. You cannot arbitrarily return any type per branch and assume Java will always convert them to the same type.

## 2. Directly Runnable Java 17+ Demo

Create a UTF-8 file named **`SwitchExpressionDemo.java`**:

~~~java
public class SwitchExpressionDemo {
    enum Day {
        MON, TUE, WED, THU, FRI, SAT, SUN
    }

    static String category(int number) {
        return switch (number) {
            case 0 -> "zero";
            case 1, 2 -> "small";
            default -> "other";
        };
    }

    static String kind(Day day) {
        return switch (day) {
            case MON, TUE, WED, THU, FRI -> "work";
            case SAT, SUN -> "rest";
        };
    }

    static int score(int level) {
        return switch (level) {
            case 0 -> 0;
            case 1, 2 -> {
                int computed = level * 10;
                System.out.println("computed=" + computed);
                yield computed;
            }
            default -> -1;
        };
    }

    static String direction(int code) {
        return switch (code) {
            case 1:
                yield "left";
            case 2:
                yield "right";
            default:
                yield "unknown";
        };
    }

    static String traditional(int code) {
        String result;
        switch (code) {
            case 1:
                result = "left";
                break;
            case 2:
                result = "right";
                break;
            default:
                result = "unknown";
        }
        return result;
    }

    static String safeStatus(String input) {
        if (input == null) {
            return "missing";
        }
        return switch (input) {
            case "ON" -> "enabled";
            case "OFF" -> "disabled";
            default -> "unknown";
        };
    }

    static String requireNonNegative(int number) {
        return switch (number) {
            case 0 -> "zero";
            default -> {
                if (number < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield "positive";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("== arrow rules ==");
        System.out.println("category0=" + category(0));
        System.out.println("category2=" + category(2));
        System.out.println("category9=" + category(9));

        System.out.println("== exhaustive enum ==");
        System.out.println("monday=" + kind(Day.MON));
        System.out.println("sunday=" + kind(Day.SUN));

        System.out.println("== yield ==");
        System.out.println("score0=" + score(0));
        System.out.println("score2=" + score(2));
        System.out.println("score9=" + score(9));

        System.out.println("== colon expression ==");
        System.out.println("direction1=" + direction(1));
        System.out.println("direction9=" + direction(9));

        System.out.println("== statement comparison ==");
        System.out.println("traditional2=" + traditional(2));

        System.out.println("== String and null ==");
        System.out.println("statusON=" + safeStatus("ON"));
        System.out.println("statusOther=" + safeStatus("PAUSE"));
        System.out.println("statusNull=" + safeStatus(null));

        System.out.println("== exceptions ==");
        System.out.println("nonNegative0=" + requireNonNegative(0));
        System.out.println("nonNegative3=" + requireNonNegative(3));
        try {
            requireNonNegative(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        var inferred = switch (1) {
            case 1 -> "yes";
            default -> "no";
        };
        System.out.println("inferred=" + inferred);
    }
}
~~~

Open PowerShell or Bash in the directory containing the file; requires **JDK 17 or higher**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchExpressionDemo.java
java SwitchExpressionDemo
~~~

**Exact expected stdout** of `java SwitchExpressionDemo` (excluding JDK version info):

~~~text
== arrow rules ==
category0=zero
category2=small
category9=other
== exhaustive enum ==
monday=work
sunday=rest
== yield ==
score0=0
computed=20
score2=20
score9=-1
== colon expression ==
direction1=left
direction9=unknown
== statement comparison ==
traditional2=right
== String and null ==
statusON=enabled
statusOther=unknown
statusNull=missing
== exceptions ==
nonNegative0=zero
nonNegative3=positive
caught=negative
inferred=yes
~~~

The program uses standard Java; no third-party libraries are required. The output above is determined by Java 17's branch selection and execution order.

## 3. How Does a Multi-Statement Branch Return a Result?

With `case -> expression`, the expression right after the arrow is the result. If you need calculations or logging, use a block and `yield`: `case 1 -> { int x = 10; yield x * 2; }`. `yield` exits the **switch expression**, not the entire method like `return`.

Switch expressions also allow `case:` labels, e.g., `case 1: yield "ONE";`. The dedicated lesson on `yield` goes deeper into conditional paths and missing-value errors.

## 4. Expressions Must Cover All Cases

For `int` and `String`, `default` is normally required to handle unlisted values. For an enum, listing all constants can make a switch expression exhaustive without `default`. Adding an enum constant later can prompt recompilation errors where switch expressions need an added case. Rules for proving exhaustiveness and choosing result types are analyzed in a separate lesson.

## 5. How `->` Differs from `case:` and Switch Statements

| Construct | Produces a value? | Has fall-through? | How it completes |
| --- | --- | --- | --- |
| `switch (x) { case 1: ... break; }` | No: **statement** | Possible | `break`, `return`, or end of block |
| `switch (x) { case 1 -> ... }` | No if used as a **statement** | No | End of switch rule |
| `var y = switch (x) { case 1 -> v; ... };` | Yes: **expression** | No | Expression value or `yield` |
| `var y = switch (x) { case 1: yield v; ... };` | Yes: **expression** | Colon form has sequential execution flow | `yield`/`throw` or other valid execution path |

The arrow `->` **is not synonymous with switch expression**: Java 17 also allows switch **statements** with `case ->`. Distinguish them by **whether the context consumes a value from the switch**.

Inside one `switch` block, do not mix `case ...:` labels with `case ... ->`. In a colon-style switch expression, every normal path must produce a value according to Java's rules.

## 6. Result Types, `var`, and `null`

~~~java
var label = switch (option) {
    case 1 -> "start";
    default -> "other";
};
~~~

Here `label` infers type `String` from the switch expression; `var` does not "change type dynamically" based on whichever branch runs. The compiler determines the type from **the branches and the target context**.

Standard Java 17 `switch` does not treat a `null` `String` or wrapper number as matching a default label:

~~~java
String value = null;
// String result = switch (value) {
//     case "ON" -> "enabled";
//     default -> "unknown";
// };
// At runtime: NullPointerException on a null selector.
~~~

If you need to handle null, check **before** passing it into `switch`; the `safeStatus` method in the demo does this.

## 7. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "`switch` is always a statement." | Java 17 also has switch **expressions** |
| "Having `->` means it is definitely a switch expression." | Switch statements can also use `->` |
| "A `->` branch needs `break`." | No fall-through occurs, so it is normally unnecessary |
| "Inside `-> { ... }`, use `return` to produce a value." | Use **`yield`** |
| "`yield` is equivalent to `return` from the method." | `yield` returns a value from the switch expression |
| "A switch expression can omit remaining cases without default." | It must be **exhaustive** |
| "`default` automatically catches a null selector." | Not in standard Java 17 switch |
| "`var` changes type at runtime depending on the case." | Type is determined at compile time |
| "You can mix `case X:` and `case Y ->`." | They cannot be mixed in the same switch |

## 8. Self-Check

1. What does `int n = switch (2) { case 1 -> 10; case 2 -> 20; default -> 0; };` produce?  
   *Answer:* `20`.
2. What value does the branch `case 1 -> { int x = 5; yield x * 2; }` produce?  
   *Answer:* `10`.
3. Does `yield` also exit the enclosing method?  
   *Answer:* No; it supplies a value out of the switch expression.
4. Can you use `case 1: yield "one";` in a switch expression?  
   *Answer:* Yes.
5. Is a switch expression on `int` with one `case 1` branch and no `default` exhaustive?  
   *Answer:* No.
6. Is `case 1 -> System.out.println("x");` necessarily a switch expression?  
   *Answer:* No; it can be a switch statement.
7. Why must a `null` `String` be handled before a standard Java 17 switch?  
   *Answer:* A null selector can cause `NullPointerException`.

## Checklist

- [ ] Understand that a switch **expression** produces a value for assignment, `return`, or passing to a method.
- [ ] Use `case -> value` for single-expression branches; use `yield` when the branch is a multi-statement block.
- [ ] Remember that the `->` form does not fall through to the next case.
- [ ] Ensure exhaustive branch coverage; choose `default` or list every enum constant.
- [ ] Distinguish `yield` from `return` and `break`.
- [ ] Do not confuse a switch statement using `->` with a switch expression.
- [ ] Understand that the result type is determined at compile time and handle null selectors when needed.

**Conclusion:** Switch expressions let you select **a single value** directly across multiple cases, reducing the pattern of declaring a variable and assigning it in every branch. In Java 17, prefer `->` for independent branches, use `yield` when a processing block is needed, and maintain **exhaustiveness** across cases.